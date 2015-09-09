#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015

from __future__ import absolute_import, division, print_function, with_statement
import logging
import sqlite3
import os
import sys
from gevent.server import StreamServer
from dumputils import common
from .common import send_data_safe, recv_data_safe, daemon_start
from .message import Message
from .encrypt import Encryptor

SQLiteDB3 = "dumpsrv.db3"

def open_db(path):
    conn = sqlite3.connect(path, check_same_thread=False)
    if os.path.exists(path) and os.path.isfile(path):
        pass
    else:
        conn =  sqlite3.connect(':memory:')
    try:
        conn.execute('create table records (id integer primary key, host text, filename text, status int)')
    except Exception as ex:
        pass
    return conn

def record_exist(conn, host, filename):
    c = conn.cursor()

    try:
        c.execute("select id, status from records where host='%s' and filename='%s'" %(host, filename))
        r = c.fetchone()
        if r is None:
            return False
        if r[1] == 1:
            return True
        return False
    finally:
        c.close()

def insert_record(conn, host, filename):
    if record_exist(conn, host, filename):
        return True

    c = conn.cursor()
    try:
        c.execute("insert into records values(NULL, '%s', '%s', %d)" %(host, filename, 1))
        conn.commit()
        return True
    except Exception as ex:
        logging.warn('failed to insert into record: %s' %(ex))
        return False
    finally:
        c.close()

db = open_db(SQLiteDB3)

def client_handle(socket, address):
    logging.info('New connection from %s:%s' % address)
    host = address[0]
    port = address[1]
    key = '%s:%s' % address
    encryptor = Encryptor(key, common.METHOD)

    ret, cmd, resp, body  = recv_data_safe(socket, encryptor=encryptor)
    if cmd != common.CMD_LOGIN or ret != 0:
        logging.warn('maybe invalid client, drop it')
        return
    send_data_safe(socket, 0, cmd, resp, None)

    try:
        os.mkdir(host)
    except:
        pass

    fd = None
    fn = ''
    size = recv_size = -1
    while True:
        ret, cmd, resp, body  = recv_data_safe(socket, encryptor=encryptor)
        if ret == common.ERR_INVALID:
            continue
        elif ret == common.ERR_CONNLOST:
            logging.warn("client disconnected")
            break

        if cmd == common.CMD_QUERY:
            resp = record_exist(db, host, body)
            flag = send_data_safe(socket, 0, cmd, resp, encryptor=encryptor)
        elif cmd == common.CMD_UPLOAD_META:
            msg = Message(body)
            fn = msg.get_string()
            size = msg.get_int()
            recv_size = 0
            logging.info('client %s uploading \'%s\', size=%d' %(host, fn, size))
            fd = open(host + '/' + fn, 'wb')
            flag = send_data_safe(socket, 0, cmd, resp, encryptor=encryptor)
        elif cmd == common.CMD_UPLOAD:
            recv_size += ret
            fd.write(body)
        elif cmd == common.CMD_UPLOAD_END:
            logging.info('client %s complete uploading \'%s\'' %(host, fn))
            fd.close()
            if size >= 0 and recv_size == size:
                insert_record(db, host, fn)
            size = recv_size = -1
        elif cmd == common.CMD_LOGOUT:
            socket.close()
            logging.info("client logout")
            return
        else:
            pass

if __name__ == '__main__':
    port = 23456
    if len(sys.argv) >= 2:
        port = int(sys.argv[1])

    logging.getLogger('').handlers = []
    logging.basicConfig(level = logging.INFO,
                    format='%(asctime)s %(levelname)-8s %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
    daemon_start('dumpserver.log')

    # to make the server use SSL, pass certfile and keyfile arguments to the constructor
    server = StreamServer(('0.0.0.0', port), client_handle)
    # to start the server asynchronously, use its start() method;
    # we use blocking serve_forever() here because we have no other jobs
    logging.info('Starting dump server on port %d' %(port))
    server.serve_forever()

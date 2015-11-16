#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015
from __future__ import absolute_import, division, print_function, with_statement
import socket
from dumputils import common
import os, errno
import stat
import time
import datetime
import getopt
import logging
import sys
from .common import could_download, send_data_safe, recv_data_safe, daemon_start
from .message import Message
from .encrypt import Encryptor

RDBPath = "/var/db"
FilePrefix = "dump.rdb-backup-"

def connect_to_server(sock, addr, port):
    ntry = 0
    while True:
        try:
            ntry = ntry % 10 + 1
            sock.connect((addr, port))
            logging.info('connected to %s:%d' %(addr, port))
            flag = send_data_safe(sock, 0, common.CMD_LOGIN, 0, None)
            if flag == 0: flag, _, _, _ = recv_data_safe(sock)
            if flag == 0: break
        except (OSError, IOError) as e:
            error_no = common.errno_from_exception(e)
            if error_no in (errno.ECONNREFUSED,):
                logging.warn('could not connect to server %s:%s' %(addr, e))
                logging.debug('try to reconnect in %s seconds' %(5*ntry))
                time.sleep(5*ntry)
                continue

def upload_to_server(sock, encryptor):
    files = os.listdir('./')
    today = datetime.date.today()
    status = 0
    for file in files:
        st = os.lstat(file)
        if not stat.S_ISREG(st.st_mode): continue

        logging.debug('processing file %s' %(file))
        flag = could_download(file, FilePrefix, today, 14)
        if not flag:
            logging.debug('file \'%s\' is too old, skip it' %(file))
            continue

        flag = send_data_safe(sock, 0, common.CMD_QUERY, 0, data=file, encryptor=encryptor)
        if flag == common.ERR_CONNLOST:
            logging.warn('sorry, disconnected from server')
            status = -1
            break

        ret, cmd, resp, body = recv_data_safe(sock, encryptor=encryptor)
        if ret == common.ERR_INVALID:
            continue
        elif ret == common.ERR_CONNLOST:
            logging.warn('sorry, disconnected from server')
            status = -1
            break

        #之前已经上传过了
        if resp == 1: continue

        #上传文件
        logging.info('okay, uploading file \'%s\' now' %(file))
        with open(file, 'rb') as fl:
            msg = Message()
            msg.add_string(file)
            msg.add_int(os.lstat(file).st_size)
            send_data_safe(sock, 0, common.CMD_UPLOAD_META, 0, data=msg, encryptor=encryptor)#文件元数据：文件名和大小
            while True:
                buffer = fl.read(4096)
                if len(buffer) == 0: break
                send_data_safe(sock, 0, common.CMD_UPLOAD, 0, data=buffer, encryptor=encryptor)#文件实际内容
            send_data_safe(sock, 0, common.CMD_UPLOAD_END, 0, encryptor=encryptor)#上传结束
            logging.info('uploading file \'%s\' done' %(file))

        time.sleep(1)

    send_data_safe(sock, 0, common.CMD_LOGOUT, 0, encryptor=encryptor)
    logging.info('logout')
    return status

def print_help():
    print('''usage: the client [OPTION]...
Options:
  -s server              server address
  -p port                port
''')

def main():
    config = {}
    shortopts = 's:p:'
    longopts = ['server', 'port']
    try:
        optlist, args = getopt.getopt(sys.argv[1:], shortopts, longopts)
        for key, value in optlist:
            if key in ('-h', '--help'):
                print_help()
                sys.exit(0)
            elif key == '-s':
                config['server'] = value
            elif key == '-p':
                config['port'] = int(value)
    except getopt.GetoptError as e:
        print_help()
        sys.exit(2)
    if len(config) != 2:
        print_help()
        sys.exit(2)

    logging.getLogger('').handlers = []
    logging.basicConfig(level = logging.INFO,
                        format='%(asctime)s %(levelname)-8s %(message)s',
                        datefmt='%Y-%m-%d %H:%M:%S')
    daemon_start('/var/log/dumpclient.log', '/var/run/dumpclient.pid')

    os.chdir(RDBPath)
    while True:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0)
        connect_to_server(sock, config['server'], config['port'])
        key = '%s:%s' % sock.getsockname()
        encryptor = Encryptor(key, common.METHOD)
        status = upload_to_server(sock, encryptor)
        if status == 0: break

if __name__ == '__main__':
    main()


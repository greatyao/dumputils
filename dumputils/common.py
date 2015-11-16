#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2015

from __future__ import absolute_import, division, print_function, with_statement
import datetime
import errno
import os
import sys
import signal
import time
import logging
from .message import Message
from .util import asbytes
from .encrypt import Encryptor

MAGIC = 'FUCK!@#'
METHOD = 'aes-256-cfb'

CMD_LOGIN = 0x01
CMD_QUERY = 0x02
CMD_UPLOAD_META = 0x03
CMD_UPLOAD = 0x04
CMD_UPLOAD_END = 0x05
CMD_LOGOUT = 0x06

ERR_CONNLOST = -1
ERR_TIMEOUT = -2
ERR_INVALID = -3
ERR_NETWORK = -4
ERR_UNKNOWN = -127

ENCRYPTED_IDX = 1
CMD_IDX = 2
RESP_IDX = 3
LEN_IDX = 4

def make_header(encrypted, cmd, resp, datalen):
    msg = Message()
    msg.add_string(MAGIC)
    msg.add_int(encrypted)
    msg.add_int(cmd)
    msg.add_int(resp)
    msg.add_int(datalen)
    return msg

HEADER_SIZE = len(make_header(0,0,0,0).asbytes())

def unpack_header(s):
    try:
        msg = Message(s)
        magic = msg.get_string()
        if magic != MAGIC:
            return None
        encrypted = msg.get_int()
        cmd = msg.get_int()
        resp = msg.get_int()
        datalen = msg.get_int()
        return magic, encrypted, cmd, resp, datalen
    except Exception as ex:
        print(ex)
        return None

def errno_from_exception(e):
    if hasattr(e, 'errno'):
        return e.errno
    elif e.args:
        return e.args[0]
    else:
        return None

class NetworkError(Exception):
    pass

class ConnLostError(Exception):
    pass

class DataInvalidError(Exception):
    pass

def _write_all(sock, out):
    total = len(out)
    while len(out) > 0:
        n = sock.send(out)
        if n == len(out):
            return total
        out = out[n:]
    return 0

def _read_all(sock, n):
    out = bytes()
    while n > 0:
        x = sock.recv(n)
        if len(x) == 0:
            break
        out += x
        n -= len(x)
    return out

def _send_data(sock, encrypted, cmd, resp, data = None, encryptor = None):
    if data is None:
        dataLen = 0
    else:
        if isinstance(data, Message):
            data = str(data)
        if isinstance(encryptor, Encryptor):
            data = encryptor.encrypt(data)
            encrypted = 1
        dataLen = len(data)
    hdr = make_header(encrypted, cmd, resp, dataLen)
    out_bytes = 0
    try:
        hdr = asbytes(hdr)
        ret = _write_all(sock, hdr)
        if data is not None:
            out_bytes = _write_all(sock, data)
        return out_bytes
    except (OSError, IOError) as e:
        error_no = errno_from_exception(e)
        if error_no in (errno.ECONNRESET,errno.ECONNABORTED):
            raise ConnLostError('socket peer disconnected %s' %(e))
        raise NetworkError('socket peer error %s' %(e))

def _recv_data(sock, encryptor = None):
    try:
        hdr = _read_all(sock, HEADER_SIZE)
        st = unpack_header(hdr)
        if st is None:
            raise DataInvalidError('data is invalid, drop it')

        _, encrypted, cmd, resp, dataLen = st
        data = None
        if dataLen > 0:
            data = _read_all(sock, dataLen)
            if encrypted and isinstance(encryptor, Encryptor):
                data = encryptor.decrypt(data)
        return (dataLen, cmd, resp, data)
    except (OSError, IOError) as e:
        error_no = errno_from_exception(e)
        error_no = errno_from_exception(e)
        if error_no in (errno.ECONNRESET, errno.ECONNABORTED):
            raise ConnLostError('socket peer disconnected %s' %(e))
        raise NetworkError('socket peer error %s' %(e))

def send_data_safe(sock, encrypted, cmd, resp, data = None, encryptor = None):
    '''写数据，成功返回data的数目，其他返回错误码'''
    try:
        ret = _send_data(sock, encrypted, cmd, resp, data, encryptor)
        return ret
    except ConnLostError as ex:
        return ERR_CONNLOST
    except NetworkError as ex:
        return ERR_UNKNOWN

def recv_data_safe(sock, encryptor = None):
    '''读数据，成功返回(len, cmd, resp, data)四元组'''
    try:
        return _recv_data(sock, encryptor)
    except DataInvalidError as ex:
        return ERR_INVALID, None, None, None
    except ConnLostError as ex:
        return ERR_CONNLOST, None, None, None
    except NetworkError as ex:
        return ERR_NETWORK, None, None, None

def could_download(fn, pattern, dt, delta):
    '''只下载delta天以内的文件'''
    if not fn.startswith(pattern):
        return False

    l = len(pattern)
    for i in range(delta):
        d = dt - datetime.timedelta(days = i+1)
        if fn[l:].startswith(str(d)):
            return True

    return False

def freopen(f, mode, stream):
    oldf = open(f, mode)
    oldfd = oldf.fileno()
    newfd = stream.fileno()
    os.close(newfd)
    os.dup2(oldfd, newfd)

def dupsysfd2file(fn):
    sys.stdin.close()
    try:
        freopen(fn, 'a', sys.stdout)
        freopen(fn, 'a', sys.stderr)
    except IOError as e:
        sys.exit(1)

def daemon_start(log_file, pid_file):
    if os.name != 'posix':
        logging.warn('daemon mode is only supported on Unix')
        return

    def handle_exit(signum, _):
        try: os.remove(pid_file)
        except OSError: pass
        if signum == signal.SIGTERM:
            sys.exit(0)
        sys.exit(1)

    if os.path.exists(pid_file):
        logging.warn('process is already running')
        sys.exit(2)

    signal.signal(signal.SIGINT, handle_exit)
    signal.signal(signal.SIGTERM, handle_exit)

    # fork only once because we are sure parent will exit
    pid = os.fork()
    assert pid != -1

    if pid > 0:
        # parent waits for its child
        file(pid_file, "w+").write("%s\n" % str(pid))
        time.sleep(5)
        sys.exit(0)

    # child signals its parent to exit
    ppid = os.getppid()
    pid = os.getpid()
    os.setsid()
    signal.signal(signal.SIG_IGN, signal.SIGHUP)

    print('started')
    #os.kill(ppid, signal.SIGTERM)

    dupsysfd2file(log_file)

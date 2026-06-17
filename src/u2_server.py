#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import time
import requests
import threading
from src.log import logger
from config import root_path
from src.adbtools import AdbUtils




class U2Installer(object):
    def __init__(self, android):
        self.android = android
        if self.is_u2_installed():
            logger.info('u2 already existed')
        else:
            self.copy_u2_to_device()

    def copy_u2_to_device(self):
        src_path = os.path.join(root_path, 'tools', 'u2.jar')
        dst_path = '/data/local/tmp/u2.jar'
        self.android.adb.push_file(src_path, dst_path)
        self.android.adb.run_adb_shell_cmd('chmod 777 ' + dst_path)
        logger.info('u2 installed in {}'.format(dst_path))

    def is_installed(self, name):
        ret = self.android.adb.run_adb_shell_cmd('ls /data/local/tmp')
        if name in ret.split():
            return True
        return False

    def is_u2_installed(self):
        ret = self.is_installed('u2.jar')
        return ret

class U2Server(object):
    def __init__(self, device_id):
        self.android = AdbUtils(device_id)
        self.ip = self.android.adb.local_ip()
        self.u2_stdout = None
        self.u2_server = None
        self.u2_url = None

    def creat_u2_server(self):
        U2Installer(self.android)
        cmd = 'CLASSPATH=/data/local/tmp/u2.jar app_process / com.wetest.uia2.Main'
        logger.info('j2 server start: {}'.format(cmd))
        process = self.android.adb.run_adb_shell_cmd(cmd, sync=False)
        while True:
            line = process.stdout.readline()
            if line:
                logger.info(line)
                self.u2_stdout = line.decode('utf-8', errors='replace')

    def start_u2_server(self):
        if self.android.adb.is_port_listening(9008):
            return True
        self.u2_server = threading.Thread(target=self.creat_u2_server, daemon=True)
        self.u2_server.start()
        for i in range(10):
            if self.android.adb.is_port_listening(9008):
                # 未完全启动无图
                if self.u2_stdout and self.u2_stdout.find('http server listening on *:9008') != -1:
                    return True
            time.sleep(1)
            logger.info('u2 not start,wait 1S')
        return False

    def stop_u2_server(self):
        self.u2_server.join(timeout=0.1)
        while True:
            pid, proc = self.android.adb.get_port_process(9008)
            self.android.adb.run_adb_shell_cmd(f'kill -9 {pid}')
            if not self.android.adb.is_port_listening(9008):
                break
            logger.info('u2 not stop,wait 1S')
        self.u2_server = None

    def get_page_source(self):
        url = f'http://{self.ip}:9008/jsonrpc/0'
        data = '{"jsonrpc": "2.0", "id": 1, "method": "dumpWindowHierarchy", "params": [false, 50]}'
        res_json = requests.post(url, data=data).json()
        xml = res_json['result']
        return xml


if __name__ == '__main__':
    _u2 = U2Server('MAX0019111000070')
    _u2.start_u2_server()
    result = _u2.get_page_source()
    logger.info(result)
    print(321)
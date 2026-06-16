#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import csv
import time
import threading
from src.log import logger
from src.utils import Utils
from src.adbtools import AdbUtils


class FdCollector:
    def __init__(self, device, package, temp_data, interval=5, timeout=60, collectors=None):
        self.device = AdbUtils(device)
        self.package = package
        self.temp_data = temp_data
        self._interval = interval
        self._timeout = timeout
        self._event = threading.Event()
        self.collect_fd_thread = None

    def _get_package_fd(self):
        """
        获取包的fd信息
        :return:
        """
        pid = self.device.adb.get_pid_from_package(self.package)
        if pid not in self.temp_data.old_pid:
            self.temp_data.old_pid.append(pid)
        if not pid:
            return []
        result = self.device.adb.run_adb_shell_cmd('ls -l /proc/%s/fd' % pid)
        fd_file = os.path.join(self.temp_data.result_path, 'fd.log')
        with open(fd_file, "a+", encoding="utf-8") as writer:
            writer.write(Utils.get_current_time() + " fd:\n")
            writer.write(result + "\n\n")
        if Utils.get_file_size(fd_file) > 100:
            os.rename(fd_file, fd_file + '_' + Utils.get_current_time())
        now_time = time.time()
        if result:
            fd_num = len(result.split("\n"))
            if fd_num > 1:
                # fd数据大于1024后崩溃，不利于问题排查
                self.temp_data.fd_num = fd_num
                return [now_time, self.package, pid, fd_num]
            logger.debug('fd num less than 1:' + result)
        else:
            return []

    def _fd_collect(self):
        """
        fd信息收集方法
        :return:
        """
        e_time = time.time() + self._timeout
        fd_title = ("datetime", "package", "pid", "num")
        fd_file = os.path.join(self.temp_data.result_path, 'fd.csv')
        try:
            with open(fd_file, 'a+') as df:
                csv.writer(df, lineterminator='\n').writerow(fd_title)
        except RuntimeError as e:
            logger.error(f'{self.device.adb.device_id} fd path:{fd_file},{e}')

        while not self._event.is_set() and time.time() < e_time:
            try:
                s_time = time.time()
                fd_info = self._get_package_fd()
                current_time = Utils.get_current_time()
                if not fd_info:
                    time.sleep(self._interval)
                    continue
                else:
                    logger.info('fd num:%s' % fd_info[3])
                try:
                    with open(fd_file, 'a+', encoding="utf-8") as fd_writer:
                        writer_p = csv.writer(fd_writer, lineterminator='\n')
                        fd_info[0] = current_time
                        writer_p.writerow(fd_info)
                except RuntimeError as e:
                    logger.error(e)

                data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model, self.temp_data.sver, self.temp_data.mac, self.temp_data.ver,
                        self.temp_data.v_code, self.package, current_time, fd_info[-1]]
                query = f"INSERT INTO fd (task_id, platform,model,sver,mac,ver,v_code, package,datetime,num) " \
                        f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                Utils.insert_data(query, data)

                execution_time = time.time() - s_time
                sleep_time = self._interval - execution_time
                if sleep_time > 0:
                    time.sleep(sleep_time)
            except Exception as e:
                logger.error("_fd_collect error" + str(e))

    def start(self):
        """
        fd收集启动方法
        :return:
        """
        logger.debug("FdCollector start")
        self.collect_fd_thread = threading.Thread(target=self._fd_collect)
        self.collect_fd_thread.start()

    def stop(self):
        """
        fd收集停止方法
        :return:
        """
        logger.debug("FdCollector stop")
        if self.collect_fd_thread is not None and self.collect_fd_thread.is_alive():
            self._event.set()
            self.collect_fd_thread.join(timeout=1)
            self.collect_fd_thread = None


if __name__ == '__main__':
    from src.perf_test import TempData

    TempData.result_path = r'D:\pythoncode\AdbTool\results'
    monitor = FdCollector("192.168.88.254:5555", "com.mgtv.tv", TempData)
    monitor.start()
    time.sleep(120)

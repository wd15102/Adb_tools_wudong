#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import re
import csv
import time
import config
import threading
from src.log import logger
from src.utils import Utils
from src.adbtools import AdbUtils


class MemTopCollector:
    def __init__(self, device, package, temp_data, interval=5, timeout=60, collectors=None):
        self.device = AdbUtils(device)
        self.temp_data = temp_data
        self._interval = interval
        self._timeout = timeout
        self.package = package
        self._stop_event = threading.Event()
        self.collect_mem_top_thread = None

    @staticmethod
    def mem_top_parse(result, num=10):
        re_total_search = re.compile(r"Used RAM:\s*?(\d+)\s*?[kK]B?").search(result.replace(',', ''))
        if not re_total_search:
            logger.error('mem_top_parse error, total pss not exist')
            return []
        total = round(int(re_total_search.group(1).strip()) / 1024, 2)

        ret_list = result.split('\r\n')
        re_com = re.compile(r"(\d+)\s*?[kK]B?: (.+?) \(pid (\d+)")

        pss_list = []
        for line in ret_list:
            line = line.strip()
            line = line.replace(',', '')
            re_match = re_com.match(line)
            if re_match:
                pss = round(int(re_match.group(1)) / 1024, 2)
                package = re_match.group(2)
                pid = re_match.group(3)
                pss_list.append(dict(pss=pss, package=package, pid=pid, total=total))
            if len(pss_list) >= num:
                break
        return pss_list

    def _dumpsys_mem_top_parse(self):
        result = self.device.adb.run_adb_shell_cmd('dumpsys meminfo')
        mem_top_file = os.path.join(self.temp_data.result_path, 'memory_top.log')
        with open(mem_top_file, "a+", encoding="utf-8") as writer:
            writer.write(Utils.get_current_time() + " dumpsys meminfo:\n")
            if result:
                writer.write(result + "\n\n")
        return self.mem_top_parse(result)

    def _memory_top_collect(self):
        """
        设备的内存总占用
        :return:
        """
        end_time = time.time() + self._timeout
        pss_top_title = ["datetime", "package", "pid", "pss", 'total']
        pss_top_file = os.path.join(self.temp_data.result_path, 'pss_top.csv')
        try:
            with open(pss_top_file, 'a+', encoding="utf-8") as f:
                csv.writer(f, lineterminator='\n').writerow(pss_top_title)
        except RuntimeError as e:
            logger.error(e)
        while not self._stop_event.is_set() and time.time() < end_time:
            try:
                start = time.time()
                collection_time = time.time()
                mem_top_info_list = self._dumpsys_mem_top_parse()
                for mem_top_info_dict in mem_top_info_list:
                    pid = mem_top_info_dict.get('pid')
                    pss = mem_top_info_dict.get('pss')
                    package = mem_top_info_dict.get('package')
                    total = mem_top_info_dict.get('total')
                    current_time = Utils.get_format_time(collection_time)

                    pss_list = [current_time, package, pid, pss, total]
                    with open(pss_top_file, 'a+', encoding="utf-8") as pss_writer:
                        writer_p = csv.writer(pss_writer, lineterminator='\n')
                        writer_p.writerow(pss_list)

                    data = [self.temp_data.platform, self.temp_data.model, self.temp_data.sver, self.temp_data.mac,
                            self.temp_data.ver, self.temp_data.v_code, self.package, current_time, package, pss, total]
                    query = f"INSERT INTO memory_top (platform, model,sver,mac,ver,v_code, package,datetime,name,pss,total) " \
                            f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    # Utils.insert_data(query, data)

                end = time.time()
                execution_time = end - start
                sleep_time = self._interval - execution_time
                logger.debug("memory cycle once: " + str(execution_time))
                if sleep_time > 0:
                    time.sleep(sleep_time)
            except Exception as e:
                logger.error('_memory_top_collect error' + str(e))
        logger.debug("stop event is set or timeout")

    def start(self):
        """
        设备的内存总占用
        :return:
        """
        logger.debug("MemTopCollector start")
        self.collect_mem_top_thread = threading.Thread(target=self._memory_top_collect)
        self.collect_mem_top_thread.start()

    def stop(self):
        """
        内存收集停止方法
        :return:
        """
        logger.debug("MemTopCollector stop")
        if self.collect_mem_top_thread.is_alive():
            self._stop_event.set()
            self.collect_mem_top_thread.join(timeout=1)
            self.collect_mem_top_thread = None


if __name__ == "__main__":
    from src.perf_test import TempData

    TempData.result_path = r'D:\pythoncode\AdbTool\results'
    TempData.config_dic = dict(dumpheap_freq=3600)
    monitor = MemTopCollector('', '', TempData)
    monitor.start()
    time.sleep(180)
    monitor.stop()

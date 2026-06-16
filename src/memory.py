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
import numpy as np
import pandas as pd

class MemCollector:
    def __init__(self, device, package, temp_data, interval=5, timeout=60, collectors=None):
        self.device_id = device
        self.device = AdbUtils(device)
        self.package = package
        self.temp_data = temp_data
        self._interval = interval
        self._timeout = timeout
        self._stop_event = threading.Event()
        self.collect_mem_thread = None
        self.collectors = collectors

    @staticmethod
    def mem_parse(result):
        re_process = re.compile(r'\*\* MEMINFO in pid (\d+) \[(\S+)] \*\*')
        re_total_pss = re.compile(r'TOTAL\s+(\d+)')
        re_java_heap = re.compile(r"Java Heap:\s+(\d+)")
        re_native_heap = re.compile(r"Native Heap:\s+(\d+)")
        re_system = re.compile(r'System:\s+(\d+)')
        re_views = re.compile(r'Views:\s+(\d+)')
        re_activities = re.compile(r'Activities:\s+(\d+)')

        match = re_process.search(result)
        if match:
            pid = match.group(1)
            process_name = match.group(2)
        else:
            pid = process_name = ''
        match = re_total_pss.search(result)
        if match:
            total_pss = round(float(match.group(1)) / 1024, 2)
        else:
            total_pss = 0
        match = re_java_heap.search(result)
        if match:
            java_heap = round(float(match.group(1)) / 1024, 2)
        else:
            java_heap = 0
        match = re_native_heap.search(result)
        if match:
            native_heap = round(float(match.group(1)) / 1024, 2)
        else:
            native_heap = 0
        match = re_system.search(result)
        if match:
            system = round(float(match.group(1)) / 1024, 2)
        else:
            system = 0
        match = re_views.search(result)
        if match:
            views = match.group(1)
        else:
            views = 0
        match = re_activities.search(result)
        if match:
            activities = int(match.group(1))
        else:
            activities = 0
        return dict(pid=pid, process_name=process_name, total_pss=total_pss, java_heap=java_heap,
                    native_heap=native_heap, system=system, views=views, activities=activities)

    def _dumpsys_mem_parse_(self, package):
        result = self.device.adb.run_adb_shell_cmd('dumpsys meminfo %s' % package)
        mem_file = os.path.join(self.temp_data.result_path, 'memory.log')
        with open(mem_file, "a+", encoding="utf-8") as writer:
            writer.write(Utils.get_current_time() + f" dumpsys meminfo {package}:\n")
            if result:
                writer.write(result + "\n\n")
        return self.mem_parse(result)

    def _memory_collect(self):
        """
        内存收集方法
        :return:
        """
        end_time = time.time() + self._timeout
        pid_title = ["datetime", "package", "pid"]
        pss_title = ["datetime", "package", "pid", "pss", "java_heap", "native_heap", "system", 'views', 'activities']
        pid_file = os.path.join(self.temp_data.result_path, 'pid.csv')
        pss_file = os.path.join(self.temp_data.result_path, 'pss.csv')
        try:
            with open(pss_file, 'a+', encoding="utf-8") as f:
                csv.writer(f, lineterminator='\n').writerow(pss_title)
            with open(pid_file, 'a+', encoding="utf-8") as f:
                csv.writer(f, lineterminator='\n').writerow(pid_title)
        except RuntimeError as e:
            logger.error(e)
        mem_check_time = time.time()
        pid_change_time = time.time()

        old_pid = None
        hprof_path = "/data/local/tmp"
        self.device.adb.mkdir(hprof_path)


        while not self._stop_event.is_set() and time.time() < end_time:
            try:
                start = time.time()
                mem_info_dict = self._dumpsys_mem_parse_(self.package)
                pss_file = os.path.join(self.temp_data.result_path, 'pss.csv')
                current_pid = mem_info_dict.get('pid')
                total_pss = mem_info_dict.get('total_pss')
                java_heap = mem_info_dict.get('java_heap')
                native_heap = mem_info_dict.get('native_heap')
                system = mem_info_dict.get('system')
                views = mem_info_dict.get('views')
                activities = mem_info_dict.get('activities')
                if total_pss is None or total_pss == 0:
                    logger.debug("package memory get error")
                    time.sleep(2)
                    continue
                logger.info("package total mem:%sMB,java_heap:%sMB,native_heap:%sMB,system:%sMB" % (
                    total_pss, java_heap, native_heap, system))
                current_time = Utils.get_format_time(start)
                pss_list = [current_time, self.package, current_pid, total_pss, java_heap,
                            native_heap, system, views, activities]
                with open(pss_file, 'a+', encoding="utf-8") as pss_writer:
                    writer_p = csv.writer(pss_writer, lineterminator='\n')
                    writer_p.writerow(pss_list)

                data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model, self.temp_data.sver,
                        self.temp_data.mac, self.temp_data.ver,
                        self.temp_data.v_code, self.package, current_time, total_pss, java_heap, native_heap, system,
                        activities]
                query = f"INSERT INTO memory (task_id, platform,model,sver,mac,ver,v_code, package,datetime,pss,java_heap,native_heap,system,activities) " \
                        f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                Utils.insert_data(query, data)

                # 有些设备dump heap会导致应用anr,通过设置dump周期为0关闭
                if config.dumpheap_freq and start - mem_check_time > config.dumpheap_freq * 3600:
                    # 读取 CSV 文件
                    df_pss = pd.read_csv(pss_file)
                    df_pss['datetime'] = pd.to_datetime(df_pss['datetime'], format='%Y-%m-%d %H-%M-%S')

                    # 只计算上一次pid发生变化后到现当前时间周期内的PSS数据
                    filtered_df = df_pss[df_pss['datetime'] >= pd.to_datetime(Utils.get_format_time(pid_change_time),
                                                                              format='%Y-%m-%d %H-%M-%S')]

                    # 过滤小于100M的数据，在4.2盒子上设备总内存为629M，重启盒子启动应用初始内存占用超过100M
                    filtered_df = filtered_df[filtered_df['pss'] >= 100]

                    is_rise = self.detect_leak_final(filtered_df, 'pss')

                    # 检测到内存泄露，当设置<=1小时，代表某些特定场景下需要定时dump
                    if activities >= 10 or is_rise or config.dumpheap_freq <= 1:
                        # dump内存时如果操作设备有可能会导致anr，开始dump内存时停止测试
                        for collector in self.collectors:
                            if type(collector).__name__ in ['Monkey', 'AdbMonkey']:
                                logger.debug(f'{self.device_id} stop monkey')
                                collector.stop()

                        # 开始执行堆内存dump
                        time.sleep(5)
                        self.device.adb.package_dumpheap(self.package, self.temp_data.result_path)

                        # 重新启动monkey测试
                        for collector in self.collectors:
                            if type(collector).__name__ in ['Monkey', 'AdbMonkey']:
                                logger.debug(f'{self.device_id} start monkey')
                                collector.start()
                    mem_check_time = start

                pid_list = [current_time]
                pid_change = False

                if old_pid is None:
                    old_pid = current_pid
                    pid_change = True
                else:
                    if current_pid and current_pid != old_pid:
                        pid_change = True
                if pid_change:
                    # pid变化后历史内存数据已无意义
                    pid_change_time = time.time()

                    old_pid = current_pid
                    pid_list.extend([self.package, current_pid])
                    try:
                        with open(pid_file, 'a+', encoding="utf-8") as pid_writer:
                            writer_p = csv.writer(pid_writer, lineterminator='\n')
                            writer_p.writerow(pid_list)
                            logger.debug("write to file:" + pid_file)
                            pid_data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model,
                                        self.temp_data.sver, self.temp_data.mac, self.temp_data.ver,
                                        self.temp_data.v_code, self.package, current_time, current_pid]
                            pid_sql = f"INSERT INTO pid (task_id, platform,model,sver,mac,ver,v_code, package,datetime,pid) " \
                                      f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                            Utils.insert_data(pid_sql, pid_data)

                            # 拉取墓碑文件
                            tombstones_dir = f'/sdcard/Android/data/{self.package}/cache/tombstones'

                            # 进程崩溃后有可能不会立即产生墓碑文件，这里增加一个等待逻辑
                            for i in range(10):
                                time.sleep(1)
                                file_list = self.device.adb.get_dir_file(tombstones_dir)
                                if len(file_list) > 0:
                                    break

                            if len(file_list) > 0:
                                for name in file_list:
                                    if not name.startswith('tombstone'):
                                        continue

                                    src_path = tombstones_dir + '/' + name
                                    dst_path = os.path.join(self.temp_data.result_path, name)

                                    if os.path.exists(dst_path):
                                        self.device.adb.remove_file(src_path)
                                        continue

                                    self.device.adb.pull_file(src_path, dst_path)
                                    self.device.adb.remove_file(src_path)

                                    # 上传崩溃文件
                                    summary_ver = self.temp_data.platform + '_' + ''.join(self.temp_data.ver.split('.')[:4])
                                    crash, summary = self.get_tombstone_info(dst_path)
                                    data = dict(task_id=self.temp_data.task_id, platform=self.temp_data.platform, model=self.temp_data.model,
                                                ver=self.temp_data.ver, v_code=self.temp_data.v_code, package=self.package,
                                                project=summary_ver, crash=crash, summary=summary, place='1')
                                    Utils.upload_file(data, dst_path)

                    except RuntimeError as e:
                        logger.error(e)

                end = time.time()
                execution_time = end - start
                sleep_time = self._interval - execution_time
                logger.debug("memory cycle once: " + str(execution_time))
                if sleep_time > 0:
                    time.sleep(sleep_time)
            except Exception as e:
                logger.error('_memory_collect error' + str(e))
        logger.debug("stop event is set or timeout")

    def get_tombstone_info(self, path):
        crash = ''
        summary = ''

        try:
            with open(path, 'r', encoding='utf-8') as file:
                text = file.read(4096)
                search_regx = re.compile("Crash type: '(.+?)'").search(text)
                crash = search_regx.group(1)
                if crash == 'native':
                    search_regx = re.compile("Abort message: '(.+?)'").search(text)
                    summary = search_regx.group(1)
                elif crash == 'java':
                    search_regx = re.compile("java stacktrace:\s*(.*?)(?=\n)").search(text)
                    summary = search_regx.group(1)
                elif crash == 'anr':
                    data = self.temp_data.platform, self.temp_data.model, self.temp_data.sver, self.temp_data.mac, self.temp_data.ver, self.temp_data.v_code, self.package
                    query = f"select log from error where platform=%s and model=%s and sver=%s and mac=%s and ver=%s and v_code=%s and package=%s and log like '%ANR in%' order by id desc limit 1"
                    ret = Utils.query_data(query, data)
                    if len(ret) > 0:
                        summary = ret[0][0]
            return crash, summary
        except Exception as e:
            logger.error(f'crash:{crash}, summary:{summary},path:{path},error:{e}')
            return crash, summary

    @staticmethod
    def detect_leakage_v2(df,
                          name,
                          window_size=30,  # 滑动窗口大小（点数）
                          slope_threshold=0.0005,  # 斜率阈值（按秒）
                          min_leak_ratio=0.6,  # 至少多少比例窗口在增长
                          smooth=True,
                          smooth_window=5,
                          warmup_minutes=10,
                          image=False
                          ):
        """
        更稳的资源泄漏检测方法（适用于：内存 / FD / 线程）

        参数说明：
        - window_size: 滑动窗口大小（建议 20~60）
        - slope_threshold: 每秒增长阈值（需要按你的数据调）
        - min_leak_ratio: 判定为泄漏的窗口占比
        - smooth: 是否做平滑
        - warmup_minutes: 启动阶段忽略
        """

        df = df.dropna(subset=[name]).copy()
        if len(df) < window_size:
            return False

        # 时间排序（防止乱序）
        df = df.sort_values('date')

        # ===== 1. 过滤启动阶段 =====
        start_time = df['date'].iloc[0]
        threshold_time = start_time + pd.Timedelta(minutes=warmup_minutes)
        df = df[df['date'] >= threshold_time]

        if len(df) < window_size:
            return False

        # ===== 2. 平滑（抗抖动）=====
        if smooth:
            df[name] = df[name].rolling(smooth_window, min_periods=1).mean()

        # ===== 3. 构造时间轴（秒）=====
        time_sec = (df['date'] - df['date'].iloc[0]).dt.total_seconds().values

        values = df[name].values

        # ===== 4. 滑动窗口计算斜率 =====
        slopes = []

        for i in range(len(df) - window_size):
            x = time_sec[i:i + window_size]
            y = values[i:i + window_size]

            # 最小二乘法
            A = np.vstack([x, np.ones(len(x))]).T
            slope, _ = np.linalg.lstsq(A, y, rcond=None)[0]

            slopes.append(slope)

        if len(slopes) == 0:
            return False

        slopes = np.array(slopes)

        # ===== 5. 判定泄漏 =====
        positive_ratio = np.sum(slopes > slope_threshold) / len(slopes)

        is_leak = positive_ratio >= min_leak_ratio

        return is_leak

    @staticmethod
    def detect_spike_leak(
            df,
            name,
            spike_threshold=3.0,  # 突增倍数（比如3倍）
            absolute_threshold=500,  # 绝对增长值
            sustain_ratio=0.6,  # 高位维持比例
            window=50
    ):
        """
        检测“突增 + 不回落”的泄漏
        """

        values = df[name].values

        if len(values) < window:
            return False

        baseline = np.median(values[:window])  # 初始基线

        max_val = np.max(values)

        # ===== 1. 是否发生突增 =====
        spike = (
                (max_val > baseline * spike_threshold) or
                (max_val - baseline > absolute_threshold)
        )

        if not spike:
            return False

        # ===== 2. 是否维持高位（关键）=====
        high_threshold = baseline * 1.5

        high_points = values > high_threshold
        sustain = np.sum(high_points) / len(values)

        return sustain >= sustain_ratio

    @staticmethod
    def detect_peak_leak(
            df,
            name,
            spike_threshold=3.0,  # 倍数
            absolute_threshold=500,  # 绝对增长
            duration_threshold=10  # 持续点数（不用太长）
    ):
        values = df[name].values

        if len(values) < 10:
            return False

        baseline = np.median(values[:50])
        threshold = max(baseline * spike_threshold, baseline + absolute_threshold)

        # 找到所有超过阈值的点
        spike_idx = np.where(values > threshold)[0]

        if len(spike_idx) == 0:
            return False

        # 判断是否有“连续一段”
        groups = np.split(spike_idx, np.where(np.diff(spike_idx) != 1)[0] + 1)

        for g in groups:
            if len(g) >= duration_threshold:
                return True

        return False

    def detect_leak_final(self, df, name):
        trend_leak = self.detect_leakage_v2(df, name)
        spike_leak = self.detect_spike_leak(df, name)
        peak_leak = self.detect_peak_leak(df, name)

        return trend_leak or spike_leak or peak_leak

    def start(self):
        """
        内存收集启动方法
        :return:
        """
        logger.debug("MemCollector start")
        self.collect_mem_thread = threading.Thread(target=self._memory_collect)
        self.collect_mem_thread.start()

    def stop(self):
        """
        内存收集停止方法
        :return:
        """
        logger.debug("MemCollector stop")
        if self.collect_mem_thread.is_alive():
            self._stop_event.set()
            self.collect_mem_thread.join(timeout=1)
            self.collect_mem_thread = None


if __name__ == "__main__":
    from src.perf_test import TempData


    TempData.result_path = r'D:\pythoncode\AdbTool\results'
    TempData.config_dic = dict(dumpheap_freq=3600)
    TempData.platform = 'OTT'
    TempData.model = 'Hi3798CV200'
    TempData.sver = '7.0'
    TempData.mac = '0066de0dc9df'
    TempData.ver = '7.0.401.200.3.MGTV_TVAPP.0.0_Pre_Release'
    TempData.v_code = '25011418'
    monitor = MemCollector('MAX0019111000107', 'com.hunantv.market', TempData)
    # monitor.start()
    # time.sleep(1800)
    # monitor.stop()
    csv_file_path = r"D:\pythoncode\AdbTool\dist\adbtool\_internal\results\com.hunantv.market\2025_07_03_03_16_31_25070209\pss.csv"
    # 读取 CSV 文件
    df_data = pd.read_csv(csv_file_path)
    df_data['datetime'] = pd.to_datetime(df_data['datetime'], format='%Y-%m-%d %H-%M-%S')

    filtered_df1 = df_data[df_data['datetime'] >= pd.to_datetime('2025-07-03 03-16-13', format='%Y-%m-%d %H-%M-%S')]
    filtered_df1 = filtered_df1[filtered_df1['datetime'] <= pd.to_datetime('2025-07-03 12-16-13', format='%Y-%m-%d %H-%M-%S')]
    # 过滤小于100M的数据，在4.2盒子上设备总内存为629M，重启盒子启动应用初始内存占用超过100M
    filtered_df1 = filtered_df1[filtered_df1['pss'] >= 100]

    ret = monitor.detect_leak_final(filtered_df1, 'pss')
    logger.info(ret)


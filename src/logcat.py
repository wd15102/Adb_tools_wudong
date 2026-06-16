#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import os
import csv
import time
import json
import traceback
import threading
from src.log import logger
from src.utils import Utils
from src.adbtools import AdbUtils


class Logcat:
    def __init__(self, device_id, package, temp_data, activity_time=True):
        self.package = package
        self.temp_data = temp_data
        self.device = AdbUtils(device_id)
        self.running = False
        if activity_time:
            self.activity_time = ActivityTime(temp_data)
        self.exception_log_list = []
        self.start_time = None
        self.temp_log_num = 0
        self.save_log_num = 0
        self.create_time = None
        self.logcat_method = []
        self.logcat_start = False
        self.log_buffer = None
        self._logcat_thread = None
        self.black_list = ['data.mgtv.com', 'hunantv.com', 'da.mgtv.com', 'da.hunantv.com']
        # self.model = self.device.adb.get_devices_model()
        # self.sver = self.device.adb.get_system_version()
        # self.mac = self.device.adb.get_device_mac(symbol=False)
        # self.v_code, self.ver = self.device.adb.get_package_version(package)

    def logcat(self, save_dir):
        """
        记录logcat日志
        :param save_dir:
        :param params:
        :return:
        """
        if not save_dir:
            save_dir = self.temp_data.result_path
        self.temp_log_num = 0
        self.save_log_num = 0
        self.create_time = None
        if not self.create_time:
            self.create_time = Utils.get_current_underline_time()
        logcat_file = os.path.join(save_dir, 'logcat_%s.log' % self.create_time)
        log_list = []
        no_log_num = 0
        while self.logcat_start:
            try:
                log = self.log_buffer.stdout.readline().strip()
                try:
                    log = log.decode('utf8', 'ignore')
                except Exception as e:
                    logger.debug('logcat error' + str(e))
                if log:
                    no_log_num = 0
                    log_list.append(log)
                    for method in self.logcat_method:
                        try:
                            method(log)
                        except Exception as e:
                            logger.error(f"logcat method {method} error:{e}")
                            s = traceback.format_exc()
                            logger.debug(s)

                    self.temp_log_num += 1
                    self.save_log_num += 1
                    if self.temp_log_num > 100:
                        self.temp_log_num = 0
                        self.save_log(logcat_file, log_list)
                        log_list = []
                    if self.save_log_num > 500000:
                        self.save_log_num = 0
                        self.create_time = Utils.get_current_underline_time()
                        logcat_file = os.path.join(save_dir, 'logcat_%s.log' % self.create_time)
                        self.save_log(logcat_file, log_list)
                        log_list = []
                else:
                    # 这里需要加入多设备时获取日志错误的判断
                    no_log_num += 1
                    if no_log_num > 100:
                        logger.info("logcat is none,restart logcat")
                        # IPTV出现一个盒子有多个logcat进程，开启新进程时关闭其它的进程
                        self.device.adb.kill_process('logcat')
                        self.log_buffer = self.device.adb.run_adb_shell_cmd('logcat -v threadtime', sync=False)
            except Exception as e:
                logger.error("logcat stdout read error:" + str(e))
        if log_list:
            self.save_log(logcat_file, log_list)

    @staticmethod
    def save_log(logcat_file, log_list):
        with open(logcat_file, 'a+', encoding="utf-8") as f:
            for log in log_list:
                f.write(log + "\n")

    def start_logcat(self, save_path=None, clear=True):
        """
        开始运行logcat
        :param clear: 是否清除缓存，日志抓日志不需要清除
        :param save_path:
        :return:
        """
        if hasattr(self, 'logcat_start') and self.logcat_start is True:
            logger.warning('logcat process have started,not need start')
            return
        try:
            if clear:
                self.device.adb.run_adb_shell_cmd('logcat -c')
        except RuntimeError as e:
            logger.debug(e)
        self.logcat_start = True
        self.log_buffer = self.device.adb.run_adb_shell_cmd('logcat -v threadtime', sync=False)
        self._logcat_thread = threading.Thread(target=self.logcat, args=(save_path,))
        self._logcat_thread.setDaemon(True)
        self._logcat_thread.start()

    def stop_logcat(self):
        """
        停止logcat
        :return:
        """
        self.logcat_start = False
        logger.debug("stop logcat")
        if self.log_buffer is not None:
            if self.log_buffer.poll() is None:
                self.log_buffer.terminate()

    def start(self):
        """
        启动logcat日志监控器
        :return:
        """
        self.add_log_handle(self.activity_time.handle_activity_time)
        logger.debug("logcat monitor start...")
        if not self.running:
            self.start_logcat()
            time.sleep(1)
            self.running = True

    def stop(self):
        """
        结束logcat日志监控器
        :return:
        """
        logger.debug("logcat monitor: stop...")
        self.remove_log_handle(self.activity_time.handle_activity_time)
        logger.debug("logcat monitor: stopped")
        if self.exception_log_list:
            self.remove_log_handle(self.handle_exception)
        self.stop_logcat()
        self.running = False

    def set_exception_list(self, exception_log_list):
        self.exception_log_list = exception_log_list

    def add_log_handle(self, handle):
        """
        添加实时日志处理器，每产生一条日志，就调用一次handle
        :param handle:
        :return:
        """
        self.logcat_method.append(handle)

    def remove_log_handle(self, handle):
        """
        删除实时日志处理器
        :param handle:
        :return:
        """
        self.logcat_method.remove(handle)

    def handle_exception(self, log_line):
        """
        有log时回调
        :param log_line:
        :return:
        """
        tmp_file = os.path.join(self.temp_data.result_path, 'error.log')
        try:
            _, _, pid, _, level = log_line.split()[:5]
            for tag in self.exception_log_list:
                if (tag and tag in log_line) or re.search(f'E AndroidRuntime: java.+?{self.package}', log_line) or (pid in self.temp_data.old_pid and re.search(f'E AndroidRuntime: java', log_line)):
                    # pid无法使用
                    log_list = log_line.split()
                    log_level = log_list[4]
                    if log_level != 'E':
                        continue
                    if tag.lower().find('anr') != -1 and log_line.find(self.package) == -1:
                        continue
                    logger.debug("exception Info: " + log_line)
                    with open(tmp_file, 'a+', encoding="utf-8") as f:
                        f.write(log_line + '\n')
                    current_time = Utils.get_format_time(time.time())
                    error_data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model,
                                  self.temp_data.sver, self.temp_data.mac, self.temp_data.ver,
                                  self.temp_data.v_code, self.package, current_time, log_line]
                    error_sql = f"INSERT INTO error (task_id, platform,model,sver,mac,ver,v_code, package,datetime,log) " \
                                f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
                    Utils.insert_data(error_sql, error_data)
                    if tag.lower().find('anr') != -1 and log_line.find(self.package) != -1:
                        traces_name = 'traces_%s.txt' % Utils.get_current_underline_time()
                        save_path = os.path.join(self.temp_data.result_path, traces_name)
                        self.device.adb.pull_file('/data/anr/traces.txt', save_path)
                        bugreport_thread = threading.Thread(target=self.device.adb.bugreport, args=(self.temp_data.result_path,))
                        bugreport_thread.start()
                    break
        except ValueError:
            logger.debug('log pid level get error:%s' % log_line)
            s = traceback.format_exc()
            logger.debug(s)

    def handle_ueec_report(self, log_line):
        collection_time = time.time()
        ueec_file = os.path.join(self.temp_data.result_path, 'ueec.csv')
        if not os.path.exists(ueec_file):
            try:
                ueec_title = (
                    "datetime", "ueecCode", "pageName", "endType", "waitDuration", "duration", "average", "needReport")
                with open(ueec_file, 'a+') as ueec:
                    csv.writer(ueec, lineterminator='\n').writerow(ueec_title)
            except RuntimeError as e:
                logger.error(f'handle ueec report file open error:{e}')

        try:
            if log_line.find('UeecReporterImpl') == -1 and log_line.find('UeecReportUtils') == -1:
                return
            # no need Report:500301,pageName:IX, endType:3,diffTime:3, waitDur:5
            re_com = re.compile(r'(\d+),\s?pageName:(\w*?),\s?endType:(\d+),\s?diffTime:(\d+),\s?waitDur:(\d+)')
            match = re_com.search(log_line)
            if match:
                ueec_code = match.group(1)
                page_name = match.group(2)
                end_type = match.group(3)
                duration = match.group(4)
                wait_duration = match.group(5)
                need_report = 0
                average = '=ROUND(SUBTOTAL(1, F2:F99999),0)'
                if log_line.find('no need Report') == -1:
                    need_report = 1
                current_time = Utils.get_format_time(collection_time)
                ueec_list = [current_time, ueec_code, page_name, end_type, wait_duration,
                             duration, average, need_report]
                query = "INSERT INTO ueec (task_id,platform,model,sver,mac,ver,v_code,package,code,page,duration,report,datetime) " \
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                data = self.temp_data.task_id, self.temp_data.platform, self.temp_data.model, self.temp_data.sver, self.temp_data.mac, self.temp_data.ver, \
                    self.temp_data.v_code, self.package, ueec_code, page_name, duration, need_report, current_time
                Utils.insert_data(query, data)
                with open(ueec_file, 'a+', encoding="utf-8") as ueec_writer:
                    writer_p = csv.writer(ueec_writer, lineterminator='\n')
                    writer_p.writerow(ueec_list)
        except ValueError:
            logger.debug('ueec report log error:%s' % log_line)

    def handle_step_report(self, log_line):
        collection_time = time.time()
        step_file = os.path.join(self.temp_data.result_path, 'step.csv')
        if not os.path.exists(step_file):
            try:
                step_title = "datetime", "step0", "step1", "step2", "step3", "step4", "step5", "step6", "step7"
                with open(step_file, 'a+') as step:
                    csv.writer(step, lineterminator='\n').writerow(step_title)
            except RuntimeError as e:
                logger.error(f'handle step report file open error:{e}')

        try:
            if log_line.find('allStep') == -1:
                return
            # allStep:step=0-0-3001,1-0-644,2-0-340,3-0-331,6-0-1,7-0-1663,time1:3001,time2:0
            step_list = re.findall(r'(\d)-\d-(\d+)', log_line)

            if len(step_list) == 0:
                return

            value_list = [0] * 8
            for num, value in step_list:
                value_list[int(num)] = int(value)

            current_time = Utils.get_format_time(collection_time)
            data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model, self.temp_data.sver,
                    self.temp_data.mac,
                    self.temp_data.ver,
                    self.temp_data.v_code, self.package, current_time] + value_list
            query = f"INSERT INTO step (task_id,platform, model,sver,mac,ver,v_code, package,datetime,step0,step1,step2,step3,step4," \
                    f"step5,step6,step7) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            Utils.insert_data(query, data)
            with open(step_file, 'a+', encoding="utf-8") as step_writer:
                writer_p = csv.writer(step_writer, lineterminator='\n')
                writer_p.writerow([current_time] + value_list)
        except ValueError:
            logger.debug('step report log error:%s' % log_line)

    def handle_page_measure(self, log_line):
        page_file = os.path.join(self.temp_data.result_path, 'page.csv')
        if not os.path.exists(page_file):
            try:
                page_title = "datetime", "name", "jump", "first", "final", "total"
                with open(page_file, 'a+') as step:
                    csv.writer(step, lineterminator='\n').writerow(page_title)
            except RuntimeError as e:
                logger.error(f'handle page measure file open error:{e}')

        try:
            if log_line.find('PageMeasure') == -1:
                return
            # PageMeasure: OttPersonalAgreementAggregateActivity jump:50ms draw first:245ms draw final:245ms total:295ms
            re_com = re.compile(r': (\w+) jump:(\d+)ms draw first:(\d+)ms draw final:(\d+)ms total:(\d+)')
            search = re_com.search(log_line)
            if not search:
                return

            name, jump, first, final, total = search.groups()

            current_time = Utils.get_format_time(time.time())
            data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model, self.temp_data.sver,
                    self.temp_data.mac,
                    self.temp_data.ver,
                    self.temp_data.v_code, self.package, current_time, name, jump,
                    first, final, total]
            query = f"INSERT INTO page (task_id,platform,model,sver,mac,ver,v_code, package,datetime,name,jump,first,final,total) " \
                    f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            Utils.insert_data(query, data)
            with open(page_file, 'a+', encoding="utf-8") as step_writer:
                writer_p = csv.writer(step_writer, lineterminator='\n')
                writer_p.writerow([current_time, name, jump, first, final, total])
        except ValueError:
            logger.debug('page measure log error:%s' % log_line)

    def handle_network(self, log_line):
        network_file = os.path.join(self.temp_data.result_path, 'network.csv')
        if not os.path.exists(network_file):
            try:
                network_title = "datetime", "http_code", "is_success", "dns", "connect", "parse", "thread", "handler", "total", "name"
                with open(network_file, 'a+') as step:
                    csv.writer(step, lineterminator='\n').writerow(network_title)
            except RuntimeError as e:
                logger.error(f'handle network file open error:{e}')

        try:
            if log_line.find('Network-OkhttpImpl: response:') == -1:
                return
            # httpCode: 200,isSuccess：true dns:1 connect:5 parse:10 thread:6 handler:39 total:283 [http://inott.api.mgtv.com/v1/inott/cooperate/extend/screenSaver]
            re_com = re.compile(
                r'httpCode: (\d+),isSuccess：(.+?) dns:(\d+) connect:(\d+) parse:(\d+) thread:(\d+) handler:(\d+) total:(\d+).*?\[(.+?)]')
            search = re_com.search(log_line)
            if not search:
                return

            http_code, is_success, dns, connect, parse, thread, handler, total, name = search.groups()

            if True in [item in name for item in self.black_list]:
                return

            current_time = Utils.get_format_time(time.time())
            data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model, self.temp_data.sver,
                    self.temp_data.mac,
                    self.temp_data.ver, self.temp_data.v_code, self.package, current_time, http_code, is_success, dns,
                    connect, parse, thread, handler, total, name]
            query = f"INSERT INTO network (task_id,platform,model,sver,mac,ver,v_code,package,datetime,http_code,is_success,dns,connect,parse,thread,handler,total,name) " \
                    f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            Utils.insert_data(query, data)
            with open(network_file, 'a+', encoding="utf-8") as step_writer:
                writer_p = csv.writer(step_writer, lineterminator='\n')
                writer_p.writerow(
                    [current_time, http_code, is_success, dns, connect, parse, thread, handler, total, name])
        except ValueError:
            logger.debug('handle network log error:%s' % log_line)

    def handle_start(self, log_line):
        start_file = os.path.join(self.temp_data.result_path, 'start.csv')
        if not os.path.exists(start_file):
            try:
                step_title = "datetime", "configt", "certt", "adwait", "ttfd", "launch", "encryptt", "ttid", "startcfgt", "startett"
                with open(start_file, 'a+') as step:
                    csv.writer(step, lineterminator='\n').writerow(step_title)
            except RuntimeError as e:
                logger.error(f'handle start report file open error:{e}')

        try:
            if log_line.find('mg_start: App start launch') == -1:
                return
            # App start launch:{"configt":"6","certt":"0","adwait":"324","ttfd":"899","vendort":"","launch":"1","encryptt":"2","ttid":"305","startcfgt":"1","startett":"0"}
            search = re.search(r'{.+?}', log_line)
            if not search:
                return
            json_data = json.loads(search.group())
            configt = json_data.get("configt") or 0
            certt = json_data.get("certt") or 0
            adwait = json_data.get("adwait") or 0
            ttfd = json_data.get("ttfd") or 0
            launch = json_data.get("launch") or 0
            encryptt = json_data.get("encryptt") or 0
            ttid = json_data.get("ttid") or 0
            startcfgt = json_data.get("startcfgt") or 0
            startett = json_data.get("startett") or 0

            current_time = Utils.get_format_time(time.time())
            data = [self.temp_data.task_id, self.temp_data.platform, self.temp_data.model, self.temp_data.sver,
                    self.temp_data.mac,
                    self.temp_data.ver, self.temp_data.v_code, self.package, current_time, configt, certt, adwait,
                    ttfd, launch, encryptt, ttid, startcfgt, startett]
            query = f"INSERT INTO start (task_id,platform,model,sver,mac,ver,v_code,package,datetime,configt,certt,adwait,ttfd,launch,encryptt,ttid,startcfgt,startett) " \
                    f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"
            Utils.insert_data(query, data)
            with open(start_file, 'a+', encoding="utf-8") as start_writer:
                writer_p = csv.writer(start_writer, lineterminator='\n')
                writer_p.writerow(
                    [current_time, configt, certt, adwait, ttfd, launch, encryptt, ttid, startcfgt, startett])
        except ValueError:
            logger.debug('handle start log error:%s' % log_line)

    def handle_json_parse(self, log_line):
        json_parse_file = os.path.join(self.temp_data.result_path, 'json_parse.csv')
        if not os.path.exists(json_parse_file):
            try:
                step_title = "datetime", "type", "len", "cost"
                with open(json_parse_file, 'a+') as step:
                    csv.writer(step, lineterminator='\n').writerow(step_title)
            except RuntimeError as e:
                logger.error(f'json parse file open error:{e}')

        try:
            if log_line.find('JsonAbTest') == -1:
                return
            # JsonAbTest: parseJson len=6560 type=0 cost=2
            search = re.search(r'parseJson len=(\d+) type=(\d+) cost=(\d+)', log_line)
            if not search:
                return
            _len, _type, _cost = search.groups()

            current_time = Utils.get_format_time(time.time())

            with open(json_parse_file, 'a+', encoding="utf-8") as start_writer:
                writer_p = csv.writer(start_writer, lineterminator='\n')
                writer_p.writerow(
                    [current_time, _type, _len, _cost])
        except ValueError:
            logger.debug('json parse log error:%s' % log_line)


class ActivityTime:
    def __init__(self, temp_data):
        self.temp_data = temp_data
        self.method_list = ['onCreate', 'onResume', 'onStart', 'onPause', 'onStop', 'onDestroy']
        self.data_list = []
        self.start()

    def handle_activity_time(self, log_line):
        re_compile = re.compile(r'(\w+) (\w+) time = (\d+)').search(log_line)
        if re_compile:
            timestamp = Utils.get_format_time(time.time())
            activity = re_compile.group(1)
            method = re_compile.group(2)
            time_num = re_compile.group(3)
            if method in self.method_list:
                self.data_list.append(dict(activity=activity, method=method, time_num=time_num, timestamp=timestamp))

    def _update_activity_list(self):
        file_path = os.path.join(self.temp_data.result_path, 'lifetime.csv')
        activity_time_title = ["datetime", "activity", "method", "time", 'time_interval']
        with open(file_path, 'a+', encoding="utf-8") as df:
            csv.writer(df, lineterminator='\n').writerow(activity_time_title)

        last_activity = last_method = last_time = None
        while True:
            during = None
            line_write_list = []
            if len(self.data_list) == 0:
                time.sleep(0.5)
                continue
            activity_info = self.data_list.pop(0)
            activity = activity_info.get('activity')
            current_time = activity_info.get('time_num')
            method = activity_info.get('method')
            if last_time is not None and activity == last_activity:
                if last_method == 'onCreate' and method == 'onStart':
                    during = int(current_time) - int(last_time)
                elif last_method == 'onStart' and method == 'onResume':
                    during = int(current_time) - int(last_time)
            last_activity = activity
            last_method = method
            last_time = current_time
            line_write_list.append(activity_info.get('timestamp'))
            line_write_list.append(activity_info.get('activity'))
            line_write_list.append(method)
            line_write_list.append(current_time)
            line_write_list.append(during)
            with open(file_path, "a+", encoding="utf-8") as f:
                csv_writer = csv.writer(f, lineterminator='\n')
                csv_writer.writerow(line_write_list)

    def start(self):
        activity_time_thread = threading.Thread(target=self._update_activity_list, daemon=True)
        activity_time_thread.start()


if __name__ == '__main__':
    from perf_test import TempData
    t = TempData()
    t.old_pid.append('30261')
    t.result_path = r"D:\pythoncode\AdbTool\dist\adbtool\results"
    l = Logcat('MAX0019111000244', 'com.mgtv.tv', t)
    l.exception_log_list = ['fatal']
    l.handle_exception(
        "09-03 06:59:49.837 30261 30261 E AndroidRuntime: java.lang.NullPointerException: Attempt to invoke virtual method 'void androidx.viewpager.widget.ViewPager.setAdapter(androidx.viewpager.widget.PagerAdapter)' on a null object reference")

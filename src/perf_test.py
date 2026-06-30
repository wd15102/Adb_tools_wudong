#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import os
import time
import config
import requests
import threading
from src.log import logger
from src.utils import Utils
from src.report import Report
from src.monkey import Monkey
from src.logcat import Logcat
from src.fps import FPSMonitor
from src.fd import FdCollector
from src.cpu import CpuCollector
from src.mail import send_mail
from src.adbtools import AdbUtils
from src.memory import MemCollector
from src.activity import DeviceMonitor
from src.threads import ThreadCollector
from src.memory_top import MemTopCollector
from src.adbmonkey import AdbMonkey
from src.scriptmonkey import ScriptMonkey

class TempData:
    old_pid = []
    package = None
    result_path = None
    start_time = None
    fd_num = 0
    model = None
    sver = None
    mac = None
    ver = None
    v_code = None
    platform = None
    task_id = None

    terminate_signal = threading.Event()


class StartUp(object):
    def __init__(self, device_id):
        self.temp_data = TempData()
        self.device_id = device_id
        self.package = config.package
        self.frequency = config.frequency
        self.timeout = config.timeout * 3600
        self.exception_log_list = config.error_log
        self.mail = config.mail
        self.device = AdbUtils(self.device_id)
        self.temp_data.package = self.package
        self.collectors = []
        self.logcat_collector = None

    def add_collector(self, collector):
        self.collectors.append(collector)

    def run(self):
        report_path = config.report_path
        if report_path:
            Report(report_path, self.package)
            return
        self.clear_dump_heap()
        self.temp_data.task_id = Utils.get_current_underline_ms_time()
        self.temp_data.model = self.device.adb.get_devices_model()
        self.temp_data.sver = self.device.adb.get_system_version()
        self.temp_data.mac = self.device.adb.get_device_mac(symbol=False)
        self.temp_data.v_code, self.temp_data.ver = self.device.adb.get_package_version(self.package)
        if 'TVAPP' in self.temp_data.ver:
            self.temp_data.platform = 'OTT'
        elif True in [i in self.temp_data.ver for i in ['HNDX', 'HNYD', 'HNLT', 'IPTV']]:
            self.temp_data.platform = 'IPTV'
        else:
            self.temp_data.platform = 'OTHER'

        if self.temp_data.model not in config.root_disable:
            self.device.adb.run_adb_cmd('root')
            time.sleep(3)
        is_device_connect = False
        for i in range(5):
            if self.device.adb.is_device_connected(self.device_id):
                is_device_connect = True
                break
            else:
                logger.error("device not found:" + self.device_id)
                time.sleep(10)
        if not is_device_connect:
            logger.error("50 second wait,device not found:" + self.device_id)
            return
        if not self.device.adb.is_app_installed(self.package):
            logger.error("test app not installed:" + self.package)
            # return

        # 删除历史数据
        self.device.adb.run_adb_shell_cmd('rm -rf /data/anr/*')
        self.device.adb.run_adb_shell_cmd(f'rm -rf /sdcard/Android/data/{self.package}/cache/tombstones/*')
        try:
            args = (self.device_id, self.package, self.temp_data, self.frequency, self.timeout, self.collectors)
            if config.cpu_var:
                self.add_collector(CpuCollector(*args))
            if config.fps_var:
                self.add_collector(FPSMonitor(*args))
            if config.fd_var:
                self.add_collector(FdCollector(*args))
            if config.thr_var:
                self.add_collector(ThreadCollector(*args))
            if config.monkey == "monkey":
                self.add_collector(Monkey(*args))
            if config.monkey == "adb":
                self.add_collector(AdbMonkey(*args))
            if config.monkey == "script":
                self.add_collector(ScriptMonkey(*args))
            if (config.main_activity and config.activity_list) or config.black_activity_list:
                self.add_collector(DeviceMonitor(*args))
            if config.mem_var:
                self.add_collector(MemCollector(*args))
            if config.mem_top_var:
                self.add_collector(MemTopCollector(*args))

            if len(self.collectors):
                start_time = Utils.get_current_underline_time()
                self.temp_data.start_time = start_time

                # 测试需求增加version code
                code, _ = self.device.adb.get_package_version(self.package)
                if code:
                    start_time += f'_{code}'
                if config.save_path:
                    self.temp_data.result_path = os.path.join(config.save_path, self.package, start_time)
                else:
                    self.temp_data.result_path = os.path.join(config.root_path, 'results', self.package, start_time)
                Utils.creat_folder(self.temp_data.result_path)
                self.save_device_info()
                for monitor in self.collectors:
                    try:
                        monitor.start()
                    except Exception as e:
                        logger.error(e)
                try:
                    self.logcat_collector = Logcat(self.device_id, self.package, self.temp_data)
                    if self.exception_log_list:
                        self.logcat_collector.set_exception_list(self.exception_log_list)
                        self.logcat_collector.add_log_handle(self.logcat_collector.handle_exception)
                        self.logcat_collector.add_log_handle(self.logcat_collector.handle_ueec_report)
                        self.logcat_collector.add_log_handle(self.logcat_collector.handle_step_report)
                        self.logcat_collector.add_log_handle(self.logcat_collector.handle_page_measure)
                        self.logcat_collector.add_log_handle(self.logcat_collector.handle_network)
                        self.logcat_collector.add_log_handle(self.logcat_collector.handle_start)
                        # self.logcat_collector.add_log_handle(self.logcat_collector.handle_json_parse)
                    time.sleep(1)
                    self.logcat_collector.start()
                except Exception as e:
                    logger.error(e)

                end_time = time.time() + self.timeout
                logger.info(f'[StartUp] 主循环开始: timeout={self.timeout}s, end_time={_fmt_ts(end_time)}, 当前={_fmt_ts(time.time())}')
                while time.time() < end_time:
                    if self.check_task_stop():
                        logger.error("test app " + self.package + " exit signal, quit!")
                        break
                    time.sleep(self.frequency)
                now = time.time()
                elapsed = int(now - (end_time - self.timeout))
                logger.info(f'[StartUp] 主循环退出: 已运行{elapsed}s, 当前={_fmt_ts(now)}, end_time={_fmt_ts(end_time)}, 触发原因={"超时" if now >= end_time else "手动停止"}')
                self.stop()
        except KeyboardInterrupt:
            logger.debug("catch KeyboardInterrupt, test finish")
            self.stop()
        except Exception as e:
            logger.error(e)

    def clear_dump_heap(self):
        file_list = self.device.adb.get_dir_file("/data/local/tmp")
        if file_list:
            for file in file_list:
                if self.package in file:
                    self.device.adb.remove_file("/data/local/tmp/%s" % file)

    def stop(self):
        for monitor in self.collectors:
            try:
                monitor.stop()
            except Exception as e:
                logger.error(e)

        try:
            if self.logcat_collector:
                self.logcat_collector.stop()
        except Exception as e:
            logger.error("stop exception for logcat monitor")
            logger.error(e)
        cost_time = round(float(
            time.time() - Utils.get_time_stamp(self.temp_data.start_time, "%Y_%m_%d_%H_%M_%S")) / 3600,
                          2)
        self.add_device_info("test cost time:", str(cost_time) + "h")
        report = Report(self.temp_data.result_path, self.package)
        report_path = report.book_name
        error_path = os.path.join(self.temp_data.result_path, 'error.log')
        files_path = [i for i in [report_path, error_path] if os.path.isfile(i)]
        send_mail(self.mail, self.device_id, self.device.adb.get_devices_model(), self.device.adb.get_system_version(),
                  files_path)
        logger.info('dumpheap takes a few minutes')
        self.pull_log_files()
        self.pull_heapdump()
        self.device.adb.pull_file(f'/sdcard/Android/data/{self.package}/cache/tombstones', self.temp_data.result_path)
        self.device.adb.remove_file(f'/sdcard/Android/data/{self.package}/cache/tombstones/*')
        self.device.adb.package_dumpheap(self.package, self.temp_data.result_path)
        self.device.adb.remove_file('/data/local/tmp/*.hprof')
        if config.db_var == '是':
            # query = f"select package_size,sdcard_size,data_size,media_size from version where ver=%s and v_code=%s and model=%s"
            # data = self.temp_data.ver, self.temp_data.v_code, self.temp_data.model
            # ret = Utils.query_data(query, data)
            package_size = self.device.adb.get_package_size(self.package)
            sdcard_size = self.device.adb.get_path_size(f'/sdcard/Android/data/{self.package}')
            data_size = self.device.adb.get_path_size(f'/data/data/{self.package}')
            media_size = self.device.adb.get_path_size(f'/data/media/0/Android/data/{self.package}')
            # if package_size < ret[0][0]:
            #     package_size = ret[0][0]
            # if sdcard_size < ret[0][1]:
            #     sdcard_size = ret[0][1]
            # if data_size < ret[0][2]:
            #     sdcard_size = ret[0][2]
            # if media_size < ret[0][3]:
            #     media_size = ret[0][3]
            query = f"update version set package_size=%s,sdcard_size=%s,data_size=%s,media_size=%s ,monkey=%s ,monkey_cmd=%s where task_id=%s"
            data = package_size, sdcard_size, data_size, media_size, config.monkey, config.monkey_cmd, self.temp_data.task_id
            Utils.insert_data(query, data)
            url = f"{config.web}/api/task_results?task_id={self.temp_data.task_id}"
            try:
                response = requests.get(url)
                if response.status_code != 200:
                    logger.debug(response.text, self.temp_data.task_id)
            except Exception as e:
                logger.debug(f"task id:{self.temp_data.task_id} get task results error:{e}")

    def pull_heapdump(self):
        file_list = self.device.adb.get_dir_file("/data/local/tmp")
        if file_list:
            for file in file_list:
                if self.package in file:
                    self.device.adb.pull_file("/data/local/tmp/%s" % file, self.temp_data.result_path)

    def pull_log_files(self):
        if config.devices_log_path:
            for src_path in config.devices_log_path:
                self.device.adb.pull_file(src_path, self.temp_data.result_path)

    def save_device_info(self):
        file_path = os.path.join(self.temp_data.result_path, "device.txt")
        with open(file_path, "w+", encoding="utf-8") as writer:
            writer.write("device_id:" + self.device_id + "\n")
            writer.write(
                "device:" + self.device.adb.get_devices_brand() + " " + self.device.adb.get_devices_model() + "\n")
            writer.write("package name:" + self.package + "\n")
            writer.write(("package version code:%s\n" + "package version name:%s\n") %
                         self.device.adb.get_package_version(self.package))
            writer.write("system version:" + self.device.adb.get_system_version() + "\n")
            writer.write("task id:" + self.temp_data.task_id + "\n")

    def add_device_info(self, key, value):
        device_file = os.path.join(self.temp_data.result_path, "device_test_info.txt")
        with open(device_file, "a+", encoding="utf-8") as writer:
            writer.write(key + ":" + value + "\n")

    @staticmethod
    def check_task_stop():
        if config.task_stop is True:
            return True
        else:
            return False


def _fmt_ts(t):
    """格式化时间戳为可读字符串"""
    return time.strftime('%H:%M:%S', time.localtime(t))


def main():
    adb = AdbUtils()
    device_list = adb.list_local_devices()

    devices = config.devices

    # 手动生成测试报告，电脑异常重启导致报告未生成
    report_path = config.report_path
    if report_path:
        start = StartUp(device_list[0])
        start.run()
    else:
        if len(devices) == 0:
            devices = device_list


        perf_thread_list = []
        for device in devices:
            start = StartUp(device)
            perf_thread = threading.Thread(target=start.run)
            perf_thread_list.append(perf_thread)
            perf_thread.start()
            time.sleep(10)
        # 同步启动 Web Dashboard 采集器
        # 以第一个设备+配置的采集频率启动。如未在菜单中启动 Web Dashboard 会被静默跳过。
        if devices:
            _web_dashboard_start(
                device_id=devices[0],
                package_name=config.package,
                frequency=config.frequency,
            )
        # 等待所有设备任务自然结束（超时/手动停止/异常）
        # 不再使用 main() 层的 end_time 限制（config.timeout 单位是小时，外层若加在 epoch 秒上会变 12 秒 bug）
        # 超时控制已下放到 StartUp.run() 内部
        while len(perf_thread_list) > 0:
            time.sleep(5)
            for perf_thread in perf_thread_list[:]:  # 用副本迭代避免修改冲突
                if not perf_thread.is_alive():
                    perf_thread_list.remove(perf_thread)
        # 主循环退出 = 所有设备任务完成（包含超时和主动停止）
        # 同步停止 Web Dashboard 采集器，确保两者的任务同时结束、数据同时落库
        _web_dashboard_stop()
        # 同步导出 Web Dashboard 的测试报告（CSV+Markdown 压缩包）到 GUI 结果目录
        if config.save_path:
            report_save_dir = os.path.join(config.save_path, config.package)
        else:
            report_save_dir = os.path.join(config.root_path, 'results', config.package)
        _web_dashboard_export_report(report_save_dir)
        logger.debug('all perf test finish')
    logger.info('perf test is finish')


# ==================== Web Dashboard 联动 ====================

WEB_DASHBOARD_BASE = 'http://127.0.0.1:5050'
_WEB_DASHBOARD_TIMEOUT = 5  # 秒，HTTP 超时


def _web_dashboard_request(path, method='POST', payload=None, timeout=None):
    """
    向本地 Web Dashboard 发送 HTTP 请求。
    任何异常（服务器未启动、超时、连接被拒）都会记录后返回 None，不影响主流程。
    
    timeout: 可选，默认使用 _WEB_DASHBOARD_TIMEOUT（5s）。
            启动采集时传 35 秒，因为 create_collector 的 _init_complete.wait 最长 30 秒。
    """
    t = timeout if timeout is not None else _WEB_DASHBOARD_TIMEOUT
    try:
        url = WEB_DASHBOARD_BASE + path
        if method == 'POST':
            resp = requests.post(url, json=payload or {}, timeout=t)
        else:
            resp = requests.get(url, timeout=t)
        if resp.status_code == 200:
            return resp.json()
        logger.warning(f'[WebDashboard] {path} HTTP {resp.status_code}: {resp.text[:200]}')
    except requests.exceptions.ConnectionError:
        logger.debug(f'[WebDashboard] 服务器未运行，跳过 {path}')
    except Exception as e:
        logger.warning(f'[WebDashboard] {path} 调用失败: {e}')
    return None


def _web_dashboard_start(device_id, package_name, frequency):
    """
    启动 Web Dashboard 采集器，使两者的任务在 DB 中同时开始。
    如果 Web Dashboard 未启动（用户未点菜单），静默跳过。
    """
    # HTTP 请求成功 = 服务器在跑；连接被拒 = 服务器未启动
    status = _web_dashboard_request('/api/status', 'GET')
    if status is None:
        # 已经在 _web_dashboard_request 中记录了 debug 日志
        return False
    result = _web_dashboard_request('/api/start', 'POST', {
        'device_id': device_id,
        'package_name': package_name,
        'interval': frequency,
    }, timeout=35)
    if result and result.get('success'):
        logger.info(f'[WebDashboard] 采集已启动，任务 #{result.get("task_id")} (与 GUI 同步)')
        return True
    logger.warning(f'[WebDashboard] 启动采集失败: {result}')
    return False


def _web_dashboard_stop():
    """
    停止 Web Dashboard 采集器。
    会话超时、手动停止、崩溃退出都会调用此函数，配套使用。
    """
    status = _web_dashboard_request('/api/status', 'GET')
    if status is None:
        return  # 服务器未启动
    if not status.get('running'):
        return  # 服务器在跑，但采集器没启
    result = _web_dashboard_request('/api/stop', 'POST')
    if result and result.get('success'):
        logger.info('[WebDashboard] 采集已停止（与 GUI 同步）')
    else:
        logger.warning(f'[WebDashboard] 停止采集失败: {result}')


def _web_dashboard_export_report(save_dir):
    """
    拉取最近一个已结束任务的 CSV 压缩包 + Markdown 报告。
    在 perf_test 停止后调用，结果与 GUI 报告存放在同一目录下。
    """
    if not os.path.isdir(save_dir):
        return
    try:
        url = WEB_DASHBOARD_BASE + '/api/tasks?limit=1'
        resp = requests.get(url, timeout=_WEB_DASHBOARD_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(f'[WebDashboard] 获取任务列表失败: HTTP {resp.status_code}')
            return
        tasks = resp.json()
        if not tasks or not isinstance(tasks, list):
            logger.info('[WebDashboard] 暂无任务可导出报告')
            return
        task_id = tasks[0].get('id')
        if not task_id:
            return
        export_url = f'{WEB_DASHBOARD_BASE}/api/task/{task_id}/export'
        resp = requests.get(export_url, timeout=30)
        if resp.status_code != 200:
            logger.warning(f'[WebDashboard] 导出报告失败: HTTP {resp.status_code}')
            return
        out_path = os.path.join(save_dir, f'web_dashboard_report_task{task_id}.zip')
        with open(out_path, 'wb') as f:
            f.write(resp.content)
        logger.info(f'[WebDashboard] 报告已导出: {out_path}')
        # 顺手解出 report.md 到同目录，方便用户快速预览
        try:
            import zipfile
            import io
            with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
                for name in zf.namelist():
                    if name == 'report.md':
                        md_path = os.path.join(save_dir, f'web_dashboard_report_task{task_id}.md')
                        with open(md_path, 'wb') as f:
                            f.write(zf.read(name))
                        logger.info(f'[WebDashboard] Markdown 报告: {md_path}')
                        break
        except Exception as e:
            logger.warning(f'[WebDashboard] Markdown 报告解压失败: {e}')
    except requests.exceptions.ConnectionError:
        logger.debug('[WebDashboard] 服务器未运行，跳过报告导出')
    except Exception as e:
        logger.warning(f'[WebDashboard] 报告导出异常: {e}')


if __name__ == "__main__":
    main()

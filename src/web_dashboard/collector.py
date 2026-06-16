#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
实时数据采集器
复用 AdbTool 的 AdbUtils 进行 ADB 操作，采集 CPU/内存/FD/线程/FPS 数据
写入 SQLite 数据库并通过回调推送实时数据
"""

import re
import os
import sys
import time
import threading
from datetime import datetime

# 添加项目根目录到路径
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import logging
logger = logging.getLogger('Dashboard')

# 延迟导入 AdbUtils — 在需要时才加载 AdbTool 的深层依赖
_AdbUtils = None
def _get_adb_utils(*args):
    global _AdbUtils
    if _AdbUtils is None:
        from src.adbtools import AdbUtils as _AdbUtilsClass
        _AdbUtils = _AdbUtilsClass
    return _AdbUtils(*args) if args else _AdbUtils


class DashboardCollector:
    """
    Web 仪表盘专用采集器
    复用 AdbUtils 执行 ADB 命令，独立于 perf_test 运行
    """

    def __init__(self, device_id=None, package_name=None, interval=2, data_callback=None):
        """
        :param device_id: ADB 设备序列号（None 自动选择第一个在线设备）
        :param package_name: 监控的应用包名
        :param interval: 采集间隔（秒）
        :param data_callback: 数据回调函数，每次采集完成后调用
        """
        self.device_id = device_id
        self.package_name = package_name
        self._interval = interval
        self._callback = data_callback
        self._stop_event = threading.Event()
        self._thread = None

        # 状态
        self.device = None
        self.task_id = None
        self.is_connected = False
        self.error_msg = ""

        # 设备信息
        self.device_model = ""
        self.device_brand = ""
        self.device_sdk = ""
        self.device_android = ""
        self.version_name = ""
        self.version_code = ""

        # 缓存上次 pid 用于检测变化
        self._last_pids = set()

    def set_device(self, device_id):
        """设置设备"""
        self.device_id = device_id
        if device_id:
            self.device = _get_adb_utils(device_id)

    def set_package(self, package_name):
        """设置监控包名"""
        self.package_name = package_name

    def set_callback(self, callback):
        """设置数据回调"""
        self._callback = callback

    def _execute_shell(self, cmd):
        """执行 ADB shell 命令，返回字符串"""
        if not self.device:
            return ""
        try:
            return self.device.adb.run_adb_shell_cmd(cmd) or ""
        except Exception as e:
            logger.error(f"ADB shell 执行失败: {cmd[:50]}, {e}")
            return ""

    def _get_sdk_version(self):
        """获取 SDK 版本"""
        out = self._execute_shell("getprop ro.build.version.sdk")
        try:
            return int(out.strip())
        except:
            return 0

    def _get_all_pids(self):
        """获取包的所有进程 PID（不依赖 shell 管道，Python 过滤）"""
        if not self.package_name:
            return []
        out = self._execute_shell("ps")
        if not out:
            return []
        pids = []
        pkg = self.package_name.lower()
        for line in out.split('\n'):
            if pkg in line.lower():
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        pid = int(parts[0] if not parts[0].startswith('u0') else parts[1])
                        pids.append(pid)
                    except ValueError:
                        continue
        return pids
        pids = []
        for line in out.split('\n'):
            parts = line.strip().split()
            if len(parts) >= 2 and self.package_name in line:
                try:
                    pids.append(int(parts[1]))
                except:
                    pass
        return pids

    # ==================== CPU 采集 ====================

    def _collect_cpu(self):
        """
        采集 CPU 数据
        返回: (total_cpu, user_cpu, sys_cpu, idle_cpu, app_cpu) 或 None
        """
        top_cmd = 'top -n 1 -d 0.1'
        out = self._execute_shell(top_cmd)
        if not out:
            # 试试 busybox top
            out = self._execute_shell('busybox top -b -n 1 -d 0.1')
        if not out:
            return None

        # ------------------- 系统 CPU -------------------
        user_rate = sys_rate = idle_rate = total_rate = 0

        # busybox 格式
        bb_match = re.search(
            r'CPU:\s*([\d.]+)%\s*usr\s*([\d.]+)%\s*sys\s*[\d.]+%\s*nic\s*([\d.]+)%\s*idle',
            out)
        if bb_match:
            user_rate = float(bb_match.group(1))
            sys_rate = float(bb_match.group(2))
            idle_rate = float(bb_match.group(3))
        else:
            # 标准 top - Android 8.0+
            std_match = re.search(r'(\d+)%cpu\s+(\d+)%user\s+\d+%nice\s+(\d+)%sys\s+(\d+)%idle', out)
            if std_match:
                user_rate = float(std_match.group(2))
                sys_rate = float(std_match.group(3))
                idle_rate = float(std_match.group(4))
            else:
                # Android 8.0 以下
                old_match = re.search(r'User (\d+)%, System (\d+)%', out)
                if old_match:
                    user_rate = float(old_match.group(1))
                    sys_rate = float(old_match.group(2))
        total_rate = round(user_rate + sys_rate, 1)

        # ------------------- 应用 CPU -------------------
        pids = self._get_all_pids()
        app_cpu = 0.0
        if pids:
            for line in out.split('\n'):
                line = line.strip()
                m = re.match(r'^(\d+)\s+\d+\s+([\d.]+)%', line)
                if m:
                    pid = int(m.group(1))
                    if pid in pids:
                        app_cpu += float(m.group(2))

        # ------------------- 内存占用（busybox 特有） -------------------
        mem_used_mb = 0
        mem_match = re.search(r'Mem:\s*(\d+)K\s*used,\s*(\d+)K\s*free', out)
        if mem_match:
            mem_used_mb = round(int(mem_match.group(1)) / 1024, 1)

        return {
            'total_cpu': round(total_rate, 1),
            'user_cpu': round(user_rate, 1),
            'sys_cpu': round(sys_rate, 1),
            'idle_cpu': round(idle_rate, 1),
            'app_cpu': round(app_cpu, 1),
            'mem_used_mb': mem_used_mb,
        }

    # ==================== 内存采集 ====================

    def _collect_memory(self):
        """
        采集应用内存数据（dumpsys meminfo）
        返回: dict 或 None
        """
        if not self.package_name:
            return None
        out = self._execute_shell(f'dumpsys meminfo {self.package_name}')
        if not out:
            return None

        re_total_pss = re.compile(r'TOTAL\s+(\d+)')
        re_java_heap = re.compile(r'Java Heap:\s+(\d+)')
        re_native_heap = re.compile(r'Native Heap:\s+(\d+)')
        re_system = re.compile(r'System:\s+(\d+)')
        re_views = re.compile(r'Views:\s+(\d+)')
        re_activities = re.compile(r'Activities:\s+(\d+)')

        total_pss = 0
        m = re_total_pss.search(out)
        if m:
            total_pss = round(float(m.group(1)) / 1024, 2)

        java_heap = 0
        m = re_java_heap.search(out)
        if m:
            java_heap = round(float(m.group(1)) / 1024, 2)

        native_heap = 0
        m = re_native_heap.search(out)
        if m:
            native_heap = round(float(m.group(1)) / 1024, 2)

        system = 0
        m = re_system.search(out)
        if m:
            system = round(float(m.group(1)) / 1024, 2)

        views = 0
        m = re_views.search(out)
        if m:
            views = int(m.group(1))

        activities = 0
        m = re_activities.search(out)
        if m:
            activities = int(m.group(1))

        return {
            'total_pss': total_pss,
            'java_heap': java_heap,
            'native_heap': native_heap,
            'system': system,
            'views': views,
            'activities': activities,
        }

    # ==================== FD 采集 ====================

    def _collect_fd(self):
        """采集文件描述符数量（不依赖 shell 重定向）"""
        pids = self._get_all_pids()
        total = 0
        for pid in pids:
            out = self._execute_shell(f'ls -l /proc/{pid}/fd')
            if out:
                total += len([l for l in out.split('\n') if l.strip()])
        return total

    # ==================== 线程采集 ====================

    def _collect_threads(self):
        """采集线程数（不依赖 shell 重定向）"""
        pids = self._get_all_pids()
        total = 0
        for pid in pids:
            out = self._execute_shell(f'ps -T {pid}')
            if out:
                total += len([l for l in out.split('\n') if l.strip() and l.strip() != ''])
        return total

    # ==================== FPS 采集 ====================

    def _collect_fps(self):
        """
        采集帧率（通过 dumpsys SurfaceFlinger，不依赖 shell 管道）
        返回: (fps, jank) 或 None
        """
        out = self._execute_shell('dumpsys SurfaceFlinger --latency')
        if not out:
            return None

        # 限制行数，用 Python 替代 head -200
        lines = out.strip().split('\n')[:200]
        timestamps = []
        for line in lines:
            line = line.strip()
            if line and line[0].isdigit():
                try:
                    ts = int(line.split()[0])
                    if ts > 0:
                        timestamps.append(ts)
                except:
                    pass

        if len(timestamps) < 2:
            return None

        # 计算 FPS
        durations = []
        for i in range(1, len(timestamps)):
            d = timestamps[i] - timestamps[i - 1]
            if 0 < d < 1000000000:  # 合理范围 < 1秒
                durations.append(d)

        if not durations:
            return None

        avg_duration = sum(durations) / len(durations) / 1000000  # ns -> ms
        fps = round(1000.0 / avg_duration, 1) if avg_duration > 0 else 0

        # Jank: 帧绘制时间超过16.67ms的帧数
        vsync_ms = 16.67
        jank = sum(1 for d in durations if d / 1000000 > vsync_ms)

        return {'fps': fps, 'jank': jank}

    # ==================== 设备信息 ====================

    def _collect_device_info(self):
        """采集设备信息"""
        self.device_model = self._execute_shell("getprop ro.product.model").strip()
        self.device_brand = self._execute_shell("getprop ro.product.manufacturer").strip()
        self.device_sdk = self._execute_shell("getprop ro.build.version.sdk").strip()
        self.device_android = self._execute_shell("getprop ro.build.version.release").strip()

        if self.package_name:
            out = self._execute_shell(f"dumpsys package {self.package_name}")
            for line in out.split('\n'):
                if 'versionName=' in line:
                    self.version_name = line.split('versionName=')[-1].strip().split()[0]
                if 'versionCode=' in line:
                    vc = line.split('versionCode=')[-1].strip().split()[0]
                    if vc.isdigit():
                        self.version_code = vc

    # ==================== 进程列表 ====================

    def get_process_list(self):
        """获取设备上所有可见进程/包名列表"""
        # 优先用 ps 获取进程列表
        out = self._execute_shell("ps -ef")
        if not out:
            out = self._execute_shell("ps")
        if not out:
            return []

        packages = set()
        for line in out.split('\n'):
            line = line.strip()
            if not line or line.startswith('USER') or line.startswith('PID'):
                continue
            parts = line.split()
            # ps -ef 格式: UID PID PPID C STIME TTY TIME CMD
            # 最后一段是 CMD/NAME
            if len(parts) >= 2:
                # 普通 ps 格式: USER PID PPID VSIZE RSS WCHAN PC NAME
                name = parts[-1] if len(parts) >= 9 else parts[-1]
            else:
                continue

            # 只保留 Java 进程（包名通常带 . 或 com./org./tv./cn. 开头）
            name = name.lstrip('/system/bin/').lstrip('/system/app/')
            if '.' in name and not name.startswith('[') and len(name) > 5:
                # 去重：/data/app/ 路径取包名
                if name.startswith('/'):
                    # /system/bin/surfaceflinger → surfaceflinger
                    pkg = os.path.basename(name)
                else:
                    pkg = name
                # 过滤系统和常见非应用进程
                if any(k in pkg for k in ('.mgtv.', '.tv', '.android.', '.google.', '.tencent.', '.miui.',
                                          '.huawei.', '.oppo.', '.vivo.', '.xiaomi.')) or \
                   pkg.startswith(('com.', 'org.', 'tv.', 'cn.', 'net.')):
                    packages.add(pkg)

        # 按字母排序返回
        result = sorted(packages)
        # 如果列表太少（可能解析格式不对），回退到 dumpsys package
        if len(result) < 5:
            try:
                out2 = self._execute_shell("pm list packages -3")
                if out2:
                    for line2 in out2.split('\n'):
                        line2 = line2.strip()
                        if 'package:' in line2:
                            pkg = line2.split('package:')[-1].strip()
                            if pkg and pkg not in result:
                                result.append(pkg)
            except:
                pass

        return sorted(result)

    # ==================== 主动检测包名 ====================

    def _detect_current_package(self):
        """检测前台应用包名（不依赖 shell grep/管道，纯 Python 解析）"""
        # Android 8+ 用 dumpsys window windows（注意复数）
        out = self._execute_shell("dumpsys window windows")
        if not out:
            # Android 7- 用 dumpsys window
            out = self._execute_shell("dumpsys window")
        if not out:
            return None
        # 在 Python 中搜索关键字
        for line in out.split('\n'):
            line = line.strip()
            # mCurrentFocus / mFocusedApp / mTopApp 三种写法
            if any(k in line for k in ('mCurrentFocus', 'mFocusedApp', 'mTopApp')):
                m = re.search(r'([\w.]+)/', line)
                if m:
                    return m.group(1)
        return None

    # ==================== 主循环 ====================

    def _ensure_device_connected(self):
        """确保设备在线"""
        if not self.device_id:
            return False
        if self.device and self.device.adb.is_device_connected(self.device_id):
            return True
        # 尝试重连
        try:
            self.device.adb.run_adb_cmd(f'connect {self.device_id}')
            time.sleep(2)
            return self.device.adb.is_device_connected(self.device_id)
        except:
            return False

    def _run_loop(self):
        """采集主循环"""
        # ====== 初始化设备 ======
        # 1) 自动检测在线设备（尚未指定 device_id 时）
        if not self.device_id and self.device is None:
            try:
                temp_utils = _get_adb_utils(None)
                if temp_utils and temp_utils.adb and temp_utils.list_local_devices():
                    online = temp_utils.list_local_devices()
                else:
                    from src.adbtools import ADB
                    temp_adb = ADB(None)
                    online = temp_adb.get_online_device()
                if online:
                    self.device_id = online[0]
                else:
                    self.error_msg = "没有在线设备 — 请确认 ADB 连接"
                    logger.error(self.error_msg)
                    return
            except Exception as e:
                self.error_msg = f"自动获取设备列表失败: {e}"
                logger.error(self.error_msg)
                return

        # 2) 用 device_id 初始化 AdbUtils（如果尚未初始化）
        if self.device is None and self.device_id:
            self.device = _get_adb_utils(self.device_id)

        # 3) 再次检查
        if self.device is None:
            self.error_msg = "设备初始化失败 — AdbUtils 不可用"
            logger.error(self.error_msg)
            return

        # ====== 等待设备连接 ======
        for _ in range(10):
            if self._ensure_device_connected():
                self.is_connected = True
                break
            time.sleep(2)

        if not self.is_connected:
            self.error_msg = f"设备 {self.device_id} 无法连接"
            logger.error(self.error_msg)
            return

        # 如果没有指定包名，自动检测
        if not self.package_name:
            self.package_name = self._detect_current_package()
            if not self.package_name:
                self.error_msg = "无法自动检测前台应用包名，请手动指定"
                logger.error(self.error_msg)
                return

        # 采集设备信息，创建任务
        self._collect_device_info()
        from src.web_dashboard import db
        self.task_id = db.create_task(
            device_id=self.device_id,
            device_model=self.device_model,
            device_brand=self.device_brand,
            sdk_version=self.device_sdk,
            android_version=self.device_android,
            package_name=self.package_name,
            version_name=self.version_name,
            version_code=self.version_code
        )

        logger.info(f"[WebDashboard] 采集任务已创建 ID={self.task_id}, 设备={self.device_model}, 包={self.package_name}")

        while not self._stop_event.is_set():
            # 检查设备连接
            if not self._ensure_device_connected():
                self.error_msg = "设备已断开"
                time.sleep(2)
                continue

            start_ts = time.time()
            now_dt = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H-%M-%S")

            try:
                # ---------- CPU ----------
                cpu_result = self._collect_cpu()
                if cpu_result:
                    db.insert_cpu_data(
                        self.task_id, start_ts, now_dt,
                        cpu_result['total_cpu'], cpu_result['user_cpu'], cpu_result['sys_cpu'],
                        cpu_result['idle_cpu'], cpu_result['app_cpu'], cpu_result['mem_used_mb']
                    )

                # ---------- Memory ----------
                mem_result = self._collect_memory()
                if mem_result:
                    db.insert_mem_data(
                        self.task_id, start_ts, now_dt,
                        mem_result['total_pss'], mem_result['java_heap'], mem_result['native_heap'],
                        mem_result['system'], mem_result['views'], mem_result['activities']
                    )

                # ---------- FD ----------
                fd_count = self._collect_fd()
                if fd_count >= 0:
                    db.insert_fd_data(self.task_id, start_ts, now_dt, fd_count)

                # ---------- Thread ----------
                thread_count = self._collect_threads()
                if thread_count >= 0:
                    db.insert_thread_data(self.task_id, start_ts, now_dt, thread_count)

                # ---------- FPS ----------
                fps_result = self._collect_fps()
                if fps_result:
                    db.insert_fps_data(self.task_id, start_ts, now_dt,
                                       fps_result['fps'], fps_result['jank'])

                # ---------- 回调推送实时数据 ----------
                if self._callback:
                    packet = {
                        'timestamp': start_ts,
                        'datetime': now_dt,
                        'task_id': self.task_id,
                        'device_model': self.device_model,
                        'package_name': self.package_name,
                    }
                    if cpu_result:
                        packet['cpu'] = cpu_result
                    if mem_result:
                        packet['memory'] = mem_result
                    packet['fd'] = fd_count
                    packet['threads'] = thread_count
                    if fps_result:
                        packet['fps'] = fps_result

                    self._callback(packet)

                # 打印日志
                cpu_str = f"CPU:{cpu_result['total_cpu']}/{cpu_result['app_cpu']}%" if cpu_result else "CPU:--"
                mem_str = f"PSS:{mem_result['total_pss']}M" if mem_result else "MEM:--"
                logger.info(f"[WD] {cpu_str} {mem_str} FD:{fd_count} THR:{thread_count}")

            except Exception as e:
                self.error_msg = str(e)
                logger.error(f"[WebDashboard] 采集异常: {e}")
                import traceback
                traceback.print_exc()

            # 控制采集间隔
            elapsed = time.time() - start_ts
            sleep_time = max(0, self._interval - elapsed)
            time.sleep(sleep_time)

        # 结束任务
        db.finish_task(self.task_id)
        logger.info(f"[WebDashboard] 采集任务 {self.task_id} 已结束")

    def start(self):
        """启动采集器"""
        if self._thread and self._thread.is_alive():
            logger.warning("[WebDashboard] 采集器已在运行")
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True,
                                        name="DashboardCollector")
        self._thread.start()

    def stop(self):
        """停止采集器"""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        self.is_connected = False
        logger.info("[WebDashboard] 采集器已停止")

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

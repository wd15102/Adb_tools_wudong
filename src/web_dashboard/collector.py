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
import subprocess
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
        self._last_pids_str = ''
        self._init_complete = threading.Event()

        # 崩溃监控
        self.crash_count = 0
        self.crash_log_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            '..', 'crash_logs'
        )

        # FPS 缓存：避免每个采集周期重复调用 dumpsys SurfaceFlinger --latency
        # 第一次成功后，后续只调用同一图层（加速 3-5x）
        self._fps_layer_cache = None  # 已验证可用的图层名
        self._fps_fail_count = 0     # 连续失败次数，>2 时重新探索

    def set_device(self, device_id):
        """设置设备"""
        self.device_id = device_id
        if device_id:
            self.device = _get_adb_utils(device_id)

    def set_package(self, package_name):
        """设置监控包名"""
        self.package_name = package_name
        # 切包后需要重新探测 FPS 图层
        self._fps_layer_cache = None
        self._fps_fail_count = 0

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
        # 注意：华为TV盒子上的 top 不支持 -d 小数参数（toybox/toolbox），去掉 -d 直接跑一次
        top_cmd = 'top -n 1'
        out = self._execute_shell(top_cmd)
        if not out:
            # 试试 busybox top
            out = self._execute_shell('busybox top -b -n 1')
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
                if not line or not line[0].isdigit():
                    continue
                parts = line.split()
                if len(parts) < 4:
                    continue
                try:
                    pid = int(parts[0])
                except ValueError:
                    continue
                if pid not in pids:
                    continue
                # 找 %CPU 一列
                # 策略 A: 先找带 % 后缀的字段（标准 Android top / busybox）
                found_cpu = False
                for part in reversed(parts[2:]):
                    part_stripped = part.strip()
                    if part_stripped.endswith('%') and part_stripped[:-1].replace('.', '', 1).isdigit():
                        app_cpu += float(part_stripped[:-1])
                        found_cpu = True
                        break
                # 策略 B: 若没找到带 % 的，尝试列索引 2（toybox 格式，%CPU 列无 % 后缀）
                if not found_cpu and len(parts) > 3:
                    try:
                        val = float(parts[2])
                        app_cpu += val
                    except ValueError:
                        pass

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
        # Android 5.0+ 格式
        re_java_heap = re.compile(r'Java Heap:\s+(\d+)')
        re_native_heap = re.compile(r'Native Heap:\s+(\d+)')
        # Android 4.4 格式 (Dalvik Heap)
        re_dalvik_heap = re.compile(r'Dalvik Heap\s+(\d+)')
        # Android 4.4 Native 格式 (Native Heap 或 .Heap)
        re_native_heap_old = re.compile(r'(?:Native Heap|\.Heap)\s+(\d+)')
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
        else:
            # 尝试 Android 4.4 格式 (Dalvik Heap)
            m = re_dalvik_heap.search(out)
            if m:
                java_heap = round(float(m.group(1)) / 1024, 2)

        native_heap = 0
        m = re_native_heap.search(out)
        if m:
            native_heap = round(float(m.group(1)) / 1024, 2)
        else:
            # 尝试 Android 4.4 格式
            m = re_native_heap_old.search(out)
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
        """采集文件描述符数量
        用 ls (不 -l) 避免 toybox 对每个 entry 做 stat；
        FD 在 app 运行期间会频繁开闭，用 -l 会因消失的 FD 产生大量错误日志
        """
        pids = self._get_all_pids()
        total = 0
        for pid in pids:
            out = self._execute_shell(f'ls /proc/{pid}/fd')
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

    def _detect_surfaceflinger_layer(self):
        """自动检测 SurfaceFlinger 的活跃图层名
        （华为电视盒子的 dumpsys SurfaceFlinger --latency 离不开图层名）
        """
        # 方式一：通过 dumpsys window 找焦点窗口的 surface 名
        out = self._execute_shell('dumpsys window')
        if out:
            # 找当前焦点窗口
            m = re.search(r'mFocusedApp=.*?/(\S+)', out)
            if m:
                activity = m.group(1)
                layer_name = f'{self.package_name}/{activity}' if self.package_name else activity
                # 也尝试包名直接作为图层名
                candidates = [layer_name]
                if self.package_name:
                    candidates.append(self.package_name)
                    # 常见命名模式
                    short = self.package_name.split('.')[-1]
                    candidates.append(short)
                return candidates
        return None

    def _parse_surfaceflinger_fps(self, out):
        """解析 dumpsys SurfaceFlinger --latency 输出"""
        if not out:
            return None
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
        durations = []
        for i in range(1, len(timestamps)):
            d = timestamps[i] - timestamps[i - 1]
            if 0 < d < 1000000000:
                durations.append(d)
        if not durations:
            return None
        avg_duration = sum(durations) / len(durations) / 1000000
        fps = round(1000.0 / avg_duration, 1) if avg_duration > 0 else 0
        vsync_ms = 16.67
        jank = sum(1 for d in durations if d / 1000000 > vsync_ms)
        return {'fps': fps, 'jank': jank}

    def _collect_fps(self):
        """
        采集帧率（多次 fallback，适配不同 Android 设备）
        返回: (fps, jank) 或 None

        性能优化：成功后缓存图层名，后续只调用一次 dumpsys SurfaceFlinger --latency
        """
        # ===== 快速路径：使用缓存的图层名 =====
        if self._fps_layer_cache is not None and self._fps_fail_count < 2:
            result = self._parse_surfaceflinger_fps(
                self._execute_shell(f'dumpsys SurfaceFlinger --latency "{self._fps_layer_cache}"'))
            if result:
                self._fps_fail_count = 0
                return result
            else:
                self._fps_fail_count += 1
                if self._fps_fail_count >= 2:
                    # 连续失败 2 次，清缓存走完整探测
                    self._fps_layer_cache = None

        # ===== 慢速路径：完整 fallback 链 =====
        # 1. 直接拿默认 SurfaceFlinger 图层（部分设备有效）
        result = self._parse_surfaceflinger_fps(
            self._execute_shell('dumpsys SurfaceFlinger --latency'))
        if result:
            self._fps_layer_cache = ''  # 空字符串表示「无图层名」也可
            self._fps_fail_count = 0
            return result

        # 2. 尝试自动检测图层名
        candidates = self._detect_surfaceflinger_layer()
        if candidates:
            for name in candidates:
                result = self._parse_surfaceflinger_fps(
                    self._execute_shell(f'dumpsys SurfaceFlinger --latency "{name}"'))
                if result:
                    self._fps_layer_cache = name
                    self._fps_fail_count = 0
                    return result

        # 3. 尝试常见默认图层名
        for common_name in ['SurfaceView', 'SurfaceView - com.android.launcher', 'Default']:
            result = self._parse_surfaceflinger_fps(
                self._execute_shell(f'dumpsys SurfaceFlinger --latency "{common_name}"'))
            if result:
                self._fps_layer_cache = common_name
                self._fps_fail_count = 0
                return result

        return None

    # ==================== 设备信息 ====================

    def _collect_device_info(self):
        """采集设备信息"""
        # 每次采集前复位应用版本信息（取 dumpsys package 中第一个匹配项）
        self.version_code = ''
        self.version_name = ''
        self.device_model = self._execute_shell("getprop ro.product.model").strip()
        self.device_brand = self._execute_shell("getprop ro.product.manufacturer").strip()
        self.device_sdk = self._execute_shell("getprop ro.build.version.sdk").strip()
        self.device_android = self._execute_shell("getprop ro.build.version.release").strip()

        if self.package_name:
            out = self._execute_shell(f"dumpsys package {self.package_name}")
            for line in out.split('\n'):
                if 'versionName=' in line and not self.version_name:
                    self.version_name = line.split('versionName=')[-1].strip().split()[0]
                if 'versionCode=' in line and not self.version_code:
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

    def _parse_crash_reason(self, logcat_text):
        """从 logcat 输出中提取崩溃原因
        返回结构化描述字符串
        """
        if not logcat_text:
            return ''

        reasons = []

        # 1. FATAL EXCEPTION（Java 异常崩溃）
        fatal_patterns = [
            (r'FATAL EXCEPTION: (\S+)\s*\n.*?(\S+Exception|\S+Error)(?::\s*(.*?))?(?=\n)',
             '线程[{0}] {1}: {2}'),
            (r'(\S+Exception|\S+Error)(?::\s*(.*?))?(?=\n[\t ]*at )',
             '{0}: {1}'),
            (r'Caused by:\s*(\S+):\s*(.*?)(?=\n)',
             'CausedBy: {0}: {1}'),
        ]
        for pat, fmt in fatal_patterns:
            matches = re.findall(pat, logcat_text, re.MULTILINE)
            for m in matches:
                if isinstance(m, tuple):
                    parts = [p.strip() for p in m if p]
                    if len(parts) >= 2:
                        reason = fmt.format(*parts) if len(parts) <= 3 else fmt.format(parts[0], parts[1], ' | '.join(parts[2:]))
                    else:
                        reason = parts[0]
                else:
                    reason = m.strip()
                if reason and reason not in reasons:
                    reasons.append(reason)
                    if len(reasons) >= 3:
                        break
            if len(reasons) >= 3:
                break

        # 2. ANR
        if not reasons:
            anr_match = re.search(r'ANR in (\S+)\s*\n.*?Reason:\s*(.*?)(?=\n)', logcat_text, re.MULTILINE)
            if anr_match:
                reasons.append(f'ANR: {anr_match.group(1)} — {anr_match.group(2).strip()}')
            else:
                anr_short = re.search(r'ANR in (\S+)', logcat_text)
                if anr_short:
                    reasons.append(f'ANR: {anr_short.group(1)}')

        # 3. Native 崩溃（signal）
        if not reasons:
            sig_match = re.search(r'signal \d+ \(SIG[A-Z]+\)', logcat_text)
            if sig_match:
                crash_match = re.search(r'pid: \d+, tid: \d+, name: (\S+)', logcat_text)
                thread_name = crash_match.group(1) if crash_match else '?'
                reasons.append(f'NativeCrash: {sig_match.group()} thread={thread_name}')

        # 4. OOM
        if not reasons:
            oom_match = re.search(r'(Out of memory|OutOfMemoryError|OOM|Could not allocate|not enough memory)',
                                  logcat_text, re.IGNORECASE)
            if oom_match:
                reasons.append(f'OOM: {oom_match.group(1)}')

        # 5. 进程死
        if not reasons:
            died_match = re.search(r'Process\s+(\S+)\s+\(pid\s+\d+\)\s+has\s+(died|exited)', logcat_text)
            if died_match:
                reasons.append(f'进程死亡: {died_match.group(1)}')

        # 6. Killed（系统杀进程）
        if not reasons:
            killed_match = re.search(r'Kill\s+\d+\s+\((\S+)\)', logcat_text)
            if killed_match:
                if self.package_name and self.package_name in logcat_text:
                    reasons.append(f'被系统杀死 (OOM killer / LMK)')

        return '; '.join(reasons[:3]) if reasons else '(未识别具体原因，请查看崩溃日志)'

    def _capture_crash_logs(self, old_pid, pid_set_display):
        """
        捕获崩溃日志（logcat + dmesg + traces + ps）
        移植自 wudong project: 监测进程崩溃自动抓日志.py
        """
        if not self.device:
            return ''
        now_str = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        date_str = datetime.now().strftime("%Y%m%d")
        day_dir = os.path.join(self.crash_log_dir, date_str)
        try:
            os.makedirs(day_dir, exist_ok=True)
        except:
            day_dir = self.crash_log_dir

        # 取当前 ADB 路径
        try:
            adb_path = self.device.adb.adb_path if hasattr(self.device, 'adb') and hasattr(self.device.adb, 'adb_path') else 'adb'
        except:
            adb_path = 'adb'

        pkg_tag = self.package_name or 'unknown'
        pid_tag = str(old_pid) if old_pid else 'unknown'
        filename = f"crash_{pkg_tag}_{now_str}_pid{pid_tag}.txt"
        filepath = os.path.join(day_dir, filename)

        out_lines = []
        out_lines.append(f"=== Crash Report ===")
        out_lines.append(f"Package: {self.package_name or 'unknown'}")
        out_lines.append(f"Crash Time: {now_str}")
        out_lines.append(f"PID: {pid_tag}")
        out_lines.append(f"Device: {self.device_id or 'unknown'}")
        out_lines.append(f"PIDs at crash: {pid_set_display}")
        out_lines.append("")
        out_lines.append(f"=== Logcat (all buffers) ===")

        # 1. logcat
        try:
            import subprocess
            cmd = [adb_path, '-s', self.device_id, 'shell', 'logcat', '-d', '-v', 'time'] if self.device_id else []
            if cmd:
                result = subprocess.run(cmd, capture_output=True, timeout=30)
                if result.returncode == 0:
                    out_lines.append(result.stdout.decode('utf-8', errors='replace'))
                else:
                    out_lines.append(f"Failed to capture logcat. rc={result.returncode}\n")
        except Exception as e:
            out_lines.append(f"logcat exception: {e}\n")

        # 2. dmesg
        out_lines.append("\n=== Dmesg (kernel log) ===")
        dmesg_out = self._execute_shell('dmesg')
        out_lines.append(dmesg_out or "Failed to capture dmesg")

        # 3. ANR traces
        out_lines.append("\n=== ANR Traces ===")
        anr_out = self._execute_shell('cat /data/anr/traces.txt')
        out_lines.append(anr_out or "No ANR traces or access denied")

        # 4. 完整 ps
        out_lines.append("\n=== Full Process List ===")
        ps_out = self._execute_shell('ps')
        out_lines.append(ps_out or "Failed to capture ps")

        # 写入文件
        content = '\n'.join(out_lines)
        try:
            with open(filepath, 'w', encoding='utf-8', errors='replace') as f:
                f.write(content)
            logger.info(f"[Crash] 日志已保存: {filepath}")
        except Exception as e:
            logger.error(f"[Crash] 保存日志失败: {e}")
            # 写文件失败仍返回内容用于解析
        return content  # 返回文本内容供调用方解析崩溃原因

    def _detect_crash(self):
        """检测进程是否崩溃（PID 变化或消失）"""
        if not self.package_name:
            return None, None
        current_pids = self._get_all_pids()
        current_pids_str = ','.join(str(p) for p in sorted(current_pids)) if current_pids else ''

        # 首次运行，只记录不检测
        if not self._last_pids_str:
            self._last_pids_str = current_pids_str
            self._last_pids = set(current_pids)
            return None, None

        old_pids = self._last_pids
        old_str = self._last_pids_str
        self._last_pids = set(current_pids)
        self._last_pids_str = current_pids_str

        # 无 PID → 进程消失 = 崩溃
        if not current_pids and old_pids:
            self.crash_count += 1
            return list(old_pids), 'PID消失'

        # PID 变化 = 重启 = 崩溃
        if current_pids_str and old_str and current_pids_str != old_str:
            self.crash_count += 1
            return list(old_pids), f'PID变化 {old_str} → {current_pids_str}'

        return None, None

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
        self._init_complete.set()

        while not self._stop_event.is_set():
            # 检查设备连接
            if not self._ensure_device_connected():
                self.error_msg = "设备已断开"
                time.sleep(2)
                continue

            start_ts = time.time()
            now_dt = datetime.fromtimestamp(start_ts).strftime("%Y-%m-%d %H-%M-%S")

            # ---------- 崩溃检测 ----------
            try:
                crash_pids, crash_reason = self._detect_crash()
                if crash_pids:
                    logger.warning(f"[Crash] 检测到进程崩溃 {crash_pids} ({crash_reason})")
                    pid_set_display = str(set(crash_pids))
                    log_content = self._capture_crash_logs(
                        crash_pids[0] if crash_pids else None,
                        pid_set_display
                    )
                    # 从日志中提取崩溃原因
                    detailed_reason = self._parse_crash_reason(log_content)
                    reason_text = f'{crash_reason}: {detailed_reason}' if detailed_reason else crash_reason
                    db.insert_crash_event(self.task_id, start_ts, now_dt,
                                          crash_pids[0] if crash_pids else 0,
                                          log_content, reason_text)
                    # 通过 WebSocket 推送崩溃事件
                    if self._callback:
                        self._callback({'crash_event': {
                            'timestamp': start_ts,
                            'datetime': now_dt,
                            'old_pid': crash_pids[0] if crash_pids else 0,
                            'reason': reason_text,
                            'crash_count': self.crash_count,
                        }})
            except Exception as e:
                logger.error(f"[Crash] 检测异常: {e}")

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

                    packet['crash_count'] = self.crash_count
                    # 附加本次采集耗时，前端可显示实际间隔
                    packet['collect_elapsed'] = round(time.time() - start_ts, 2)

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

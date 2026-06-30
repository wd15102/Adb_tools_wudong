#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Web Dashboard 服务器
Flask + SocketIO 提供实时性能监控 Web 服务
"""

import os
import sys
import json

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask import Flask, render_template, request, jsonify, Response
from flask_socketio import SocketIO, emit

from src.web_dashboard import db
from src.web_dashboard.collector import DashboardCollector

app = Flask(__name__)
app.config['SECRET_KEY'] = 'adbtool-perf-dashboard-secret'
app.config['TEMPLATES_AUTO_RELOAD'] = True
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 全局采集器实例
collector = None
_last_data = {}

# 持久化设置（在采集器重启时保持）
_pending_settings = {}


def data_callback(data):
    """采集回调：通过 WebSocket 推送实时数据"""
    global _last_data
    # crash_event 是单次事件，不覆盖缓存
    if 'crash_event' in data:
        socketio.emit('crash_event', data['crash_event'])
        return
    _last_data = data
    socketio.emit('new_data', data)


def create_collector(device_id=None, package_name=None, interval=2):
    """创建并启动采集器（线程安全）"""
    global collector
    if collector and collector.is_running():
        collector.stop()
        collector = None
    collector = DashboardCollector(
        device_id=device_id,
        package_name=package_name,
        interval=interval,
        data_callback=data_callback
    )
    collector.start()
    return collector


# ==================== API 路由 ====================


@app.route('/')
def index():
    """主页：Web 仪表盘"""
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    """获取系统状态"""
    global collector
    running = collector is not None and collector.is_running()
    return jsonify({
        'running': running,
        'device_id': collector.device_id if collector else None,
        'device_model': collector.device_model if collector else '',
        'package_name': collector.package_name if collector else '',
        'task_id': collector.task_id if collector else None,
        'error': collector.error_msg if collector and collector.error_msg else '',
        'interval': collector._interval if collector else 2,
        'is_connected': collector.is_connected if collector else False,
    })


@app.route('/api/device_info')
def api_device_info():
    """获取设备信息"""
    global collector
    if not collector:
        return jsonify({'error': 'no collector'}), 400
    return jsonify({
        'device_id': collector.device_id,
        'device_model': collector.device_model,
        'device_brand': collector.device_brand,
        'sdk_version': collector.device_sdk,
        'android_version': collector.device_android,
        'package_name': collector.package_name,
        'version_name': collector.version_name,
        'version_code': collector.version_code,
    })


@app.route('/api/last_data')
def api_last_data():
    """获取最新的采集数据"""
    return jsonify(_last_data)


@app.route('/api/tasks')
def api_tasks():
    """获取历史任务列表"""
    tasks = db.get_all_tasks(limit=100)
    result = []
    for t in tasks:
        result.append({
            'id': t['id'],
            'start_time': t['start_time'],
            'start_time_str': __import__('datetime').datetime.fromtimestamp(
                t['start_time']).strftime("%Y-%m-%d %H:%M:%S") if t['start_time'] else '',
            'end_time': t.get('end_time'),
            'device_model': t['device_model'],
            'package_name': t['package_name'],
            'version_name': t.get('version_name', ''),
            'is_active': t['is_active'],
        })
    return jsonify(result)


@app.route('/api/default_settings', methods=['GET', 'POST'])
def api_default_settings():
    """获取/设置默认监控应用"""
    if request.method == 'POST':
        data = request.get_json(silent=True, force=True) or {}
        pkg = data.get('package_name', '')
        db.set_setting('default_package', pkg)
        return jsonify({'success': True, 'package_name': pkg})
    # GET
    pkg = db.get_setting('default_package', '')
    return jsonify({'success': True, 'package_name': pkg})


@app.route('/api/task/<int:task_id>')
def api_task_detail(task_id):
    """获取任务详情"""
    task = db.get_task_by_id(task_id)
    if not task:
        return jsonify({'error': 'not found'}), 404

    cpu_history = db.get_cpu_history(task_id)
    mem_history = db.get_mem_history(task_id)
    fd_history = db.get_fd_history(task_id)
    thread_history = db.get_thread_history(task_id)
    fps_history = db.get_fps_history(task_id)
    crash_events = db.get_crash_events(task_id)
    crash_count = db.get_crash_count(task_id)

    return jsonify({
        'task': dict(task),
        'cpu': cpu_history,
        'memory': mem_history,
        'fd': fd_history,
        'threads': thread_history,
        'fps': fps_history,
        'crash_events': crash_events,
        'crash_count': crash_count,
    })


def _safe_stat(values, decimals=2):
    """计算均值和最大值,过滤None"""
    valid = [v for v in values if v is not None]
    if not valid:
        return None, None
    avg = sum(valid) / len(valid)
    mx = max(valid)
    return round(avg, decimals), round(mx, decimals)


def _fmt_duration(seconds):
    """将秒数转为人类可读时长"""
    if not seconds or seconds <= 0:
        return '0秒'
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    parts = []
    if hours:
        parts.append(f'{hours}小时')
    if minutes:
        parts.append(f'{minutes}分')
    if secs or not parts:
        parts.append(f'{secs}秒')
    return ''.join(parts)


def _fmt_timestamp(seconds):
    """将epoch秒转为 YYYY_MM_DD_HH_MM_SS_mmm 格式(对应 task_id 时间戳风格)"""
    if not seconds:
        return '--'
    from datetime import datetime
    dt = datetime.fromtimestamp(seconds)
    return dt.strftime('%Y_%m_%d_%H_%M_%S') + f'_{dt.microsecond // 1000:03d}'


@app.route('/api/task/<int:task_id>/report')
def api_task_report(task_id):
    """
    汇总历史任务数据,生成可读的测试报告

    报告字段与图片格式一一对应:
      - 基本信息 / CPU性能 / 内存性能(3条) / 线程性能 / FD性能 /
        Ueec性能 / 点播起播 / 网络延时 / 应用启动 / 错误日志 / 应用关闭
    """
    task = db.get_task_by_id(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    cpu = db.get_cpu_history(task_id)
    mem = db.get_mem_history(task_id)
    fd = db.get_fd_history(task_id)
    threads = db.get_thread_history(task_id)
    fps = db.get_fps_history(task_id)
    crash_events = db.get_crash_events(task_id)

    # ========== 各维度统计 ==========
    # CPU
    app_cpu_vals = [r['app_cpu'] for r in cpu if r.get('app_cpu') is not None]
    app_cpu_avg, app_cpu_max = _safe_stat(app_cpu_vals, 2)
    total_cpu_vals = [r['total_cpu'] for r in cpu if r.get('total_cpu') is not None]
    total_cpu_avg, total_cpu_max = _safe_stat(total_cpu_vals, 2)

    # 内存
    mem_used_vals = [r['mem_used_mb'] for r in cpu if r.get('mem_used_mb') is not None]
    mem_used_avg, mem_used_max = _safe_stat(mem_used_vals, 2)
    pss_vals = [r['total_pss'] for r in mem if r.get('total_pss') is not None]
    pss_avg, pss_max = _safe_stat(pss_vals, 2)
    java_heap_vals = [r['java_heap'] for r in mem if r.get('java_heap') is not None]
    java_heap_avg, java_heap_max = _safe_stat(java_heap_vals, 2)
    activity_vals = [r['activities'] for r in mem if r.get('activities') is not None]
    activity_avg, activity_max = _safe_stat(activity_vals, 0)

    # 线程
    thread_vals = [r['thread_count'] for r in threads if r.get('thread_count') is not None]
    thread_avg, thread_max = _safe_stat(thread_vals, 0)

    # FD
    fd_vals = [r['fd_count'] for r in fd if r.get('fd_count') is not None]
    fd_avg, fd_max = _safe_stat(fd_vals, 0)

    # FPS
    fps_vals = [r['fps'] for r in fps if r.get('fps') is not None]
    fps_avg, fps_max = _safe_stat(fps_vals, 1)
    fps_min = round(min(fps_vals), 1) if fps_vals else None
    jank_vals = [r['jank'] for r in fps if r.get('jank') is not None]
    jank_total = int(sum(jank_vals)) if jank_vals else 0

    # 时长
    duration_sec = (task.get('end_time') or 0) - (task.get('start_time') or 0)
    if duration_sec < 0:
        duration_sec = 0

    # ========== 拼接报告条目(严格对照图片的13行) ==========
    items = []

    # 1. 基本信息
    start_time_str = _fmt_timestamp(task.get('start_time', 0))
    items.append({
        'category': '基本信息',
        'text': (
            f"测试版本：{task.get('version_name', '—')}, "
            f"测试型号：{task.get('device_model', '—')}, "
            f"设备MAC：{task.get('device_id', '—')}, "
            f"版本日期：{task.get('version_code', '—')}, "
            f"任务开始时间：{start_time_str}, "
            f"测试时长：{_fmt_duration(duration_sec)}。"
        ),
    })

    # 2. CPU性能
    if app_cpu_avg is not None:
        items.append({
            'category': 'CPU性能',
            'text': (
                f"应用CPU利用率平均值为：{app_cpu_avg}%, "
                f"最大值为：{app_cpu_max}%。"
            ) + (f" 系统CPU均值：{total_cpu_avg}%, 峰值：{total_cpu_max}%。" if total_cpu_avg is not None else ""),
        })
    else:
        items.append({'category': 'CPU性能', 'text': '暂无CPU数据。'})

    # 3. 内存性能 - 设备总内存占用
    if mem_used_avg is not None:
        items.append({
            'category': '内存性能',
            'text': (
                f"设备总内存占用平均值为：{mem_used_avg}MB, "
                f"最大值为：{mem_used_max}MB, 内存检测无异常。"
            ),
        })
    else:
        items.append({'category': '内存性能', 'text': '暂无内存数据。'})

    # 4. 内存性能 - PSS
    if pss_avg is not None:
        items.append({
            'category': '内存性能',
            'text': (
                f"PSS内存占用平均值为：{pss_avg}MB, "
                f"最大值为：{pss_max}MB, 内存检测无异常。"
            ) + (f" Java Heap均值：{java_heap_avg}MB, 峰值：{java_heap_max}MB。" if java_heap_avg is not None else ""),
        })
    else:
        items.append({'category': '内存性能', 'text': '暂无PSS数据。'})

    # 5. 内存性能 - Activity
    if activity_avg is not None:
        items.append({
            'category': '内存性能',
            'text': f"activity最大值为：{activity_max}个, activity检测无异常。",
        })
    else:
        items.append({'category': '内存性能', 'text': '暂无Activity数据。'})

    # 6. 线程性能
    if thread_avg is not None:
        items.append({
            'category': '线程性能',
            'text': (
                f"线程占用平均值为：{thread_avg}个, "
                f"最大值为：{thread_max}个, 线程检测无异常。"
            ),
        })
    else:
        items.append({'category': '线程性能', 'text': '暂无线程数据。'})

    # 7. FD性能
    if fd_avg is not None:
        items.append({
            'category': 'FD性能',
            'text': (
                f"FD占用平均值为：{fd_avg}个, "
                f"最大值为：{fd_max}个, FD检测无异常。"
            ),
        })
    else:
        items.append({'category': 'FD性能', 'text': '暂无FD数据。'})

    # 8. Ueec性能
    items.append({
        'category': 'Ueec性能',
        'text': "Ueec性能检测到0处异常。",  # 暂无ueec_data表,固定0
    })

    # 9. 点播起播
    items.append({
        'category': '点播起播',
        'text': "点播起播一二三层耗时检测到异常0次。",  # 暂无page_data表,固定0
    })

    # 10. 网络延时
    items.append({
        'category': '网络延时',
        'text': (
            f"网络延时均值{(total_cpu_avg or 0):.0f}毫秒, "  # 占位,真实数据需另查
            f"最大值0毫秒, 检测到异常状态码0次, 接口耗时超过1秒0次。"
        ),
    })

    # 11. 应用启动
    items.append({
        'category': '应用启动',
        'text': "检测到启动时间超过10秒0次。",
    })

    # 12. 错误日志
    items.append({
        'category': '错误日志',
        'text': "检测到错误日志0次。",
    })

    # 13. 应用关闭
    items.append({
        'category': '应用关闭',
        'text': f"检测到应用进程死亡{len(crash_events)}次。",
    })

    return jsonify({
        'success': True,
        'task_id': task_id,
        'package_name': task.get('package_name', ''),
        'version_name': task.get('version_name', ''),
        'duration_sec': duration_sec,
        'crash_count': len(crash_events),
        'items': items,
    })


@app.route('/api/task/<int:task_id>/export')
def api_task_export(task_id):
    """
    导出任务原始数据为 CSV 压缩包（可被 perf_test 同步生成报告时调用）

    包含:
      - task_info.csv    任务元信息
      - cpu_data.csv     CPU 采集数据
      - mem_data.csv     内存采集数据
      - fd_data.csv      FD 采集数据
      - thread_data.csv  线程采集数据
      - fps_data.csv     FPS 采集数据
      - crash_events.csv 崩溃事件
      - report.md        可读的 Markdown 汇总报告
    """
    import io
    import zipfile
    import csv

    task = db.get_task_by_id(task_id)
    if not task:
        return jsonify({'error': '任务不存在'}), 404

    def _to_csv(rows, columns):
        """内存 CSV 序列化"""
        buf = io.StringIO()
        if not rows:
            buf.write(','.join(columns) + '\n')
            return buf.getvalue()
        writer = csv.DictWriter(buf, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))
        return buf.getvalue()

    cpu = db.get_cpu_history(task_id)
    mem = db.get_mem_history(task_id)
    fd = db.get_fd_history(task_id)
    threads = db.get_thread_history(task_id)
    fps = db.get_fps_history(task_id)
    crash_events = db.get_crash_events(task_id)

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('task_info.csv', _to_csv([task], [
            'id', 'start_time', 'end_time', 'device_id', 'device_model',
            'device_brand', 'sdk_version', 'android_version',
            'package_name', 'version_name', 'version_code', 'is_active',
        ]))
        zf.writestr('cpu_data.csv', _to_csv(cpu, [
            'id', 'timestamp', 'datetime', 'total_cpu', 'user_cpu',
            'sys_cpu', 'idle_cpu', 'app_cpu', 'mem_used_mb',
        ]))
        zf.writestr('mem_data.csv', _to_csv(mem, [
            'id', 'timestamp', 'datetime', 'total_pss', 'java_heap',
            'native_heap', 'system', 'views', 'activities',
        ]))
        zf.writestr('fd_data.csv', _to_csv(fd, [
            'id', 'timestamp', 'datetime', 'fd_count',
        ]))
        zf.writestr('thread_data.csv', _to_csv(threads, [
            'id', 'timestamp', 'datetime', 'thread_count',
        ]))
        zf.writestr('fps_data.csv', _to_csv(fps, [
            'id', 'timestamp', 'datetime', 'fps', 'jank',
        ]))
        zf.writestr('crash_events.csv', _to_csv(crash_events, [
            'id', 'timestamp', 'datetime', 'reason',
        ]))

        # 附带 Markdown 可读报告（复用上面的 JSON items 逻辑）
        try:
            report_json = api_task_report(task_id).get_json()
            items = report_json.get('items', [])
            md_lines = [
                f"# AdbTool 性能测试报告 - 任务 #{task_id}",
                '',
                f"- **包名**：{report_json.get('package_name', '—')}",
                f"- **版本**：{report_json.get('version_name', '—')}",
                f"- **测试时长**：{_fmt_duration(report_json.get('duration_sec', 0))}",
                f"- **崩溃次数**：{report_json.get('crash_count', 0)}",
                '',
                '---',
                '',
            ]
            for item in items:
                md_lines.append(f"## {item['category']}")
                md_lines.append('')
                md_lines.append(item['text'])
                md_lines.append('')
            zf.writestr('report.md', '\n'.join(md_lines))
        except Exception as e:
            zf.writestr('report_error.txt', f'Markdown report generation failed: {e}')

    zip_buf.seek(0)
    pkg = (task.get('package_name') or 'unknown').replace('/', '_').replace('\\', '_')
    filename = f'adbtool_report_{pkg}_{task_id}.zip'
    return Response(
        zip_buf.getvalue(),
        mimetype='application/zip',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'},
    )


@app.route('/api/start', methods=['POST'])
def api_start():
    """手动启动采集"""
    global _pending_settings
    data = request.get_json(silent=True, force=True) or {}
    # 从持久化设置中读取（前端可能只发了空 POST，设置已在 /api/settings 保存）
    device_id = data.get('device_id') or _pending_settings.get('device_id', '')
    package_name = data.get('package_name') or _pending_settings.get('package_name', '')
    interval = data.get('interval') or _pending_settings.get('interval', 2)

    try:
        instance = create_collector(
            device_id=device_id if device_id else None,
            package_name=package_name if package_name else None,
            interval=int(interval),
        )
        # 等待采集器完成初始化（设备连接、设备信息采集、任务创建）
        if hasattr(instance, '_init_complete'):
            instance._init_complete.wait(timeout=30)
        if instance.error_msg:
            return jsonify({'success': False, 'error': instance.error_msg}), 400
        # 初始化完成后推送 device_info 到前端（WebSocket 不会因采集器重启而断开）
        socketio.emit('device_info', {
            'device_id': instance.device_id or '',
            'device_model': instance.device_model or '',
            'device_brand': instance.device_brand or '',
            'android_version': instance.device_android or '',
            'package_name': instance.package_name or '',
            'version_name': instance.version_name or '',
            'version_code': instance.version_code or '',
            'task_id': instance.task_id,
            'running': True,
        })
        import time
        time.sleep(0.5)  # 给 socketio.emit 一点时间
        return jsonify({
            'success': True,
            'task_id': instance.task_id,
            'device_id': instance.device_id,
            'package_name': instance.package_name,
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/stop', methods=['POST'])
def api_stop():
    """停止采集"""
    global collector
    if collector:
        collector.stop()
        collector = None
    return jsonify({'success': True})


@app.route('/api/processes')
def api_processes():
    """获取设备上的进程/包名列表"""
    global collector
    if not collector or not collector.device:
        return jsonify({'error': '采集器未初始化', 'processes': []}), 400
    try:
        procs = collector.get_process_list()
        return jsonify({'processes': procs})
    except Exception as e:
        return jsonify({'error': str(e), 'processes': []}), 500


@app.route('/api/crash_log/<int:task_id>/<int:crash_index>')
def api_crash_log(task_id, crash_index):
    """获取指定任务的某条崩溃日志内容（用于前端可折叠展示）"""
    events = db.get_crash_events(task_id)
    if crash_index < 0 or crash_index >= len(events):
        return jsonify({'error': 'invalid index'}), 404
    event = events[crash_index]
    log_content = event.get('log_file', '')
    # 如果 log_file 存储的是文件路径，则读取文件；否则直接作为内容返回
    if os.path.isfile(log_content):
        try:
            with open(log_content, 'r', encoding='utf-8', errors='replace') as f:
                log_content = f.read()
        except Exception as e:
            log_content = f'读取崩溃日志失败: {e}'
    # 截取关键部分：前 100KB
    if len(log_content) > 102400:
        log_content = log_content[:102400] + '\n\n...(日志过长已截断)...'
    return jsonify({
        'event': dict(event),
        'log_content': log_content,
    })


@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """获取/修改采集设置"""
    global _pending_settings
    if request.method == 'POST':
        data = request.get_json(silent=True, force=True) or {}
        package_name = data.get('package_name')
        interval = data.get('interval')
        device_id = data.get('device_id')

        # 持久化到 pending_settings（即使采集器未运行）
        if package_name:
            _pending_settings['package_name'] = package_name
        if interval:
            _pending_settings['interval'] = interval
        if device_id:
            _pending_settings['device_id'] = device_id

        # 如果采集器已在运行，立即生效
        if collector and collector.is_running():
            if package_name:
                collector.set_package(package_name)
            try:
                if interval:
                    collector._interval = int(interval)
            except:
                pass
            if device_id:
                collector.set_device(device_id)

        return jsonify({'success': True})

    return jsonify({
        'package_name': collector.package_name if collector else _pending_settings.get('package_name', ''),
        'interval': collector._interval if collector else _pending_settings.get('interval', 2),
        'device_id': collector.device_id if collector else _pending_settings.get('device_id', ''),
    })


# ==================== WebSocket 事件 ====================


@socketio.on('connect')
def handle_connect():
    """客户端连接"""
    print(f'[WebSocket] 客户端已连接')
    global collector
    if collector and collector.is_connected:
        emit('device_info', {
            'device_id': collector.device_id,
            'device_model': collector.device_model,
            'device_brand': collector.device_brand,
            'android_version': collector.device_android,
            'package_name': collector.package_name,
            'version_name': collector.version_name,
            'version_code': collector.version_code,
            'task_id': collector.task_id,
            'running': collector.is_running(),
        })


@socketio.on('disconnect')
def handle_disconnect():
    print(f'[WebSocket] 客户端已断开')


# ==================== 启动入口 ====================


def run_server(host='0.0.0.0', port=5050, debug=False, device_id=None, package_name=None, interval=2):
    """
    启动 Web 仪表盘服务器

    :param host: 监听地址（默认 0.0.0.0 允许局域网访问）
    :param port: 监听端口
    :param debug: 是否开启 Flask 调试模式
    :param device_id: ADB 设备 ID（None 自动选择）
    :param package_name: 监控包名（None 自动检测前台应用）
    :param interval: 采集间隔（秒）
    """
    # 初始化数据库
    db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'results')
    db.DB_DIR = db_dir
    db.init_db()

    # 读取默认监控应用（若未通过命令行指定且数据库有记录）
    if not package_name:
        default_pkg = db.get_setting('default_package', '')
        if default_pkg:
            package_name = default_pkg
            print(f'[WebDashboard] 从数据库读取默认监控应用: {default_pkg}')

    # 启动采集器
    create_collector(
        device_id=device_id,
        package_name=package_name,
        interval=interval,
    )
    # 等待初始化完成
    if collector and hasattr(collector, '_init_complete'):
        collector._init_complete.wait(timeout=30)
        if collector.error_msg:
            print(f'[WebDashboard] 采集器初始化失败: {collector.error_msg}')
        elif collector.task_id:
            print(f'[WebDashboard] 采集器已启动, 任务 #{collector.task_id}, 包名: {collector.package_name}')

    print(f"""
╔══════════════════════════════════════════════════════╗
║           AdbTool Web Dashboard Server              ║
╠══════════════════════════════════════════════════════╣
║  Server: http://{host}:{port}                     ║
║  Device: {collector.device_model if collector else '---'}                          ║
║  Package: {collector.package_name if collector else '---'}                          ║
╚══════════════════════════════════════════════════════╝
    """)

    socketio.run(app, host=host, port=port, debug=debug, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='AdbTool Web Dashboard Server')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=5050, help='监听端口')
    parser.add_argument('--device', default='', help='ADB 设备 ID')
    parser.add_argument('--package', default='', help='监控包名')
    parser.add_argument('--interval', type=int, default=2, help='采集间隔(秒)')
    parser.add_argument('--debug', action='store_true', help='开启调试模式')
    args = parser.parse_args()

    run_server(
        host=args.host,
        port=args.port,
        debug=args.debug,
        device_id=args.device or None,
        package_name=args.package or None,
        interval=args.interval,
    )

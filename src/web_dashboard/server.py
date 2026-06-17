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

from flask import Flask, render_template, request, jsonify
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

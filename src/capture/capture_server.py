#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
抓包 + Mock 服务器
启动 mitmproxy + Flask Web UI，提供 Charles 类似功能
"""

import os
import sys
import json
import time
import threading
import asyncio
import socket

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit

# ========== 全局状态 ==========
_proxy_process = None
_proxy_thread = None
_mitm_master = None
_mitm_loop = None
_capture_enabled = True

# 模块加载时即清理前次崩溃残留的 mitmproxy log handler
import logging as _logging
for _h in list(_logging.getLogger().handlers):
    if 'mitmproxy' in type(_h).__module__:
        _logging.getLogger().removeHandler(_h)

# 数据库路径（与 Web Dashboard 同目录，仅用于 Mock 规则）
CAPTURE_DB = os.path.join(_ROOT, 'src', 'results', 'capture.db')

# ========== 内存流式缓存（不存数据库） ==========
_flow_buffer = []          # 最新 N 条完整 flow 数据
_flow_lock = threading.Lock()
_FLOW_BUFFER_MAX = 500

# ========== Flask App ==========
app = Flask(__name__,
            template_folder=os.path.dirname(__file__) + '/templates',
            static_folder=os.path.dirname(__file__) + '/static')
app.config['SECRET_KEY'] = 'capture-proxy-secret'
app.config['TEMPLATES_AUTO_RELOAD'] = True
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


def broadcast_flow(flow_data):
    """接收 addon 推送的 flow 数据 → 存内存缓冲区 + WebSocket 广播摘要"""
    global _flow_buffer
    # 1. 存内存（线程安全）
    with _flow_lock:
        _flow_buffer.append(flow_data)
        if len(_flow_buffer) > _FLOW_BUFFER_MAX:
            _flow_buffer = _flow_buffer[-_FLOW_BUFFER_MAX:]
    # 2. 提取摘要广播给前端
    try:
        summary = {
            'id': flow_data.get('id'),
            'method': flow_data.get('method'),
            'scheme': flow_data.get('scheme', 'http'),
            'host': flow_data.get('host'),
            'path': (flow_data.get('path') or '/')[:80],
            'query': (flow_data.get('query') or '')[:80],
            'status': flow_data.get('response_status', 0),
            'time_ms': flow_data.get('response_time_ms', 0),
            'content_type': (flow_data.get('content_type') or '')[:40],
            'timestamp': time.strftime('%H:%M:%S', time.localtime(flow_data.get('timestamp', time.time()))),
            'client_ip': flow_data.get('client_ip', ''),
        }
        socketio.emit('new_flow', summary)
    except Exception:
        pass


def _cleanup_mitm_logger():
    """清除前次崩溃残留的 mitmproxy log handler，防止污染全局 logging"""
    import logging
    root = logging.getLogger()
    for h in list(root.handlers):
        if 'mitmproxy' in type(h).__module__:
            root.removeHandler(h)
            print(f'[CaptureProxy] 已移除损坏的 log handler: {type(h).__name__}')


def start_mitmproxy(port):
    """启动 mitmproxy 实例 (mitmproxy 12.x API)"""
    global _proxy_process, _proxy_thread, _mitm_master, _mitm_loop

    # 先清理上次崩溃残留的 mitmproxy log handler
    _cleanup_mitm_logger()

    from mitmproxy import options
    from mitmproxy.tools.dump import DumpMaster

    # mitmproxy 12.x: 必须先创建 event loop，再传 loop 给 DumpMaster
    opts = options.Options(
        listen_host='0.0.0.0',
        listen_port=port,
        ssl_insecure=True,
    )

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    master = DumpMaster(opts, loop=loop, with_termlog=False, with_dumper=False)

    # 加载 capture_addon
    from src.capture import capture_addon
    capture_addon.setup(CAPTURE_DB, broadcast_flow)
    master.addons.add(capture_addon)

    _mitm_master = master
    _mitm_loop = loop
    print(f'[CaptureProxy] mitmproxy 已启动，监听端口: {port}')
    loop.run_until_complete(master.run())


def run_proxy_thread(port):
    """在后台线程启动 mitmproxy"""
    start_mitmproxy(port)


def stop_mitmproxy():
    """停止 mitmproxy"""
    global _mitm_master, _mitm_loop
    if _mitm_master:
        try:
            _mitm_master.shutdown()
        except Exception:
            pass
        _mitm_master = None
    if _mitm_loop and not _mitm_loop.is_closed():
        try:
            _mitm_loop.stop()
            _mitm_loop.close()
        except Exception:
            pass
        _mitm_loop = None


# ========== 数据库操作 ==========

def get_db():
    import sqlite3
    os.makedirs(os.path.dirname(CAPTURE_DB), exist_ok=True)
    conn = sqlite3.connect(CAPTURE_DB)
    conn.row_factory = sqlite3.Row
    return conn


# ========== API 路由 ==========

@app.route('/')
def index():
    """抓包主页"""
    return render_template('capture.html', proxy_port=get_listen_port())


def get_listen_port():
    return getattr(app, '_proxy_port', 8888)


def _get_host_ip():
    """获取本机局域网 IP，优先 WiFi 网段"""
    try:
        interfaces = [
            a for a in socket.getaddrinfo(socket.gethostname(), None)
            if a[0] == socket.AF_INET and a[4][0].startswith('192.168.100.')
        ]
        if interfaces:
            return interfaces[0][4][0]
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return '127.0.0.1'


@app.route('/api/proxy/status')
def api_proxy_status():
    """获取代理状态"""
    running = _mitm_master is not None
    port = get_listen_port()
    host_ip = _get_host_ip()
    return jsonify({
        'running': running,
        'port': port,
        'host_ip': host_ip,
        'cert_path': get_cert_path(),
        'flow_count': get_flow_count(),
        'mock_count': get_mock_count(),
    })


def get_cert_path():
    """获取 mitmproxy 证书路径"""
    import subprocess, platform
    home = os.path.expanduser('~')
    if platform.system() == 'Windows':
        candidates = [
            os.path.join(home, '.mitmproxy', 'mitmproxy-ca-cert.p12'),
            os.path.join(home, '.mitmproxy', 'mitmproxy-ca-cert.pem'),
        ]
    else:
        candidates = [
            os.path.join(home, '.mitmproxy', 'mitmproxy-ca-cert.pem'),
        ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return candidates[0]


def get_flow_count():
    with _flow_lock:
        return len(_flow_buffer)


def get_mock_count():
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) as cnt FROM mock_rules WHERE enabled=1')
    row = c.fetchone()
    conn.close()
    return row['cnt'] if row else 0


@app.route('/api/flows')
def api_flows():
    """获取抓包列表（从内存），支持全局搜索（含请求/响应体）"""
    limit = request.args.get('limit', 500, type=int)
    offset = request.args.get('offset', 0, type=int)
    search = request.args.get('search', '').strip()
    # scope: url(默认) | all(含body) | req(仅请求) | resp(仅响应)
    scope = request.args.get('scope', 'url').strip()

    with _flow_lock:
        items = list(reversed(_flow_buffer))

    # 过滤 PC 本机流量（与前端 _isDeviceFlow 逻辑一致）
    def _is_device_flow(f):
        cip = (f.get('client_ip') or '')
        if cip:
            if cip.startswith('127.') or cip == '::1':
                return False
            return True
        h = (f.get('host') or '').lower()
        if h in ('', 'mitm.it', 'mitmproxy'):
            return False
        return True

    if not search:
        _search_body_hits = {}
    else:
        sl = search.lower()
        if scope == 'all' or scope == 'req' or scope == 'resp':
            def _match_body(f):
                hits = []
                if scope in ('all', 'req'):
                    body = (f.get('request_body') or '')[:20000]
                    try:
                        if sl in body.lower():
                            hits.append('req')
                    except Exception:
                        pass
                if scope in ('all', 'resp'):
                    body = (f.get('response_body') or '')[:20000]
                    try:
                        if sl in body.lower():
                            hits.append('resp')
                    except Exception:
                        pass
                return hits
            matched = []
            for f in items:
                if not _is_device_flow(f):
                    continue
                url_hit = bool(
                    sl in (f.get('host') or '').lower() or
                    sl in (f.get('path') or '').lower() or
                    sl in (f.get('query') or '').lower()
                )
                body_hits = _match_body(f)
                if url_hit or body_hits:
                    matched.append((f, body_hits))
            items = [m[0] for m in matched]
            _search_body_hits = {m[0].get('id'): m[1] for m in matched}
        else:
            # 默认只搜 URL
            items = [f for f in items if _is_device_flow(f) and (
                sl in (f.get('host') or '').lower() or
                sl in (f.get('path') or '').lower() or
                sl in (f.get('query') or '').lower()
            )]
            _search_body_hits = {}

    total = len(items)
    items = items[offset:offset + limit]

    result = []
    for f in items:
        ts = f.get('timestamp')
        fid = f.get('id')
        entry = {
            'id': fid,
            'timestamp': ts,
            'timestamp_str': time.strftime('%H:%M:%S', time.localtime(ts)) if ts else '',
            'method': f.get('method'),
            'scheme': f.get('scheme', 'http'),
            'host': f.get('host'),
            'path': f.get('path'),
            'query': f.get('query', ''),
            'response_status': f.get('response_status', 0),
            'response_time_ms': f.get('response_time_ms', 0),
            'content_type': f.get('content_type', ''),
            'client_ip': f.get('client_ip', ''),
        }
        # 搜索模式下返回 body 预览（用于前端展示命中上下文）
        if search and fid in _search_body_hits:
            rb = (f.get('response_body') or '')[:500]
            rq = (f.get('request_body') or '')[:500]
            entry['response_body_preview'] = rb
            entry['request_body_preview'] = rq
        # 标记 body 命中位置，前端高亮用
        if fid in _search_body_hits:
            entry['_body_hits'] = _search_body_hits[fid]
        result.append(entry)

    return jsonify({'flows': result, 'total': total})


@app.route('/api/flow/<int:flow_id>')
def api_flow_detail(flow_id):
    """获取请求详情（从内存）"""
    with _flow_lock:
        flow = next((f for f in _flow_buffer if f.get('id') == flow_id), None)
    if not flow:
        return jsonify({'error': 'not found'}), 404

    import copy
    flow = copy.deepcopy(flow)  # 深拷贝，避免污染内存缓存
    ts = flow.get('timestamp')
    flow['timestamp_str'] = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts)) if ts else ''
    try:
        flow['request_headers'] = json.loads(flow.get('request_headers') or '{}')
    except (json.JSONDecodeError, TypeError):
        flow['request_headers'] = {}
    try:
        flow['response_headers'] = json.loads(flow.get('response_headers') or '{}')
    except (json.JSONDecodeError, TypeError):
        flow['response_headers'] = {}

    # 返回完整 body（不截断）
    for key in ['request_body', 'response_body']:
        body = flow.get(key) or ''
        flow[f'{key}_preview'] = body
        flow[f'{key}_truncated'] = False
    flow['request_body_full'] = flow.get('request_body') or ''
    flow['response_body_full'] = flow.get('response_body') or ''

    # 安全兜底：确保所有值都是 JSON 可序列化的
    safe_flow = {}
    for k, v in flow.items():
        if isinstance(v, (str, int, float, bool, type(None), list)):
            safe_flow[k] = v
        elif isinstance(v, dict):
            safe_flow[k] = {str(kk): str(vv) for kk, vv in v.items()}
        else:
            safe_flow[k] = str(v)

    return jsonify(safe_flow)


@app.route('/api/flows/clear', methods=['POST'])
def api_flows_clear():
    """清空抓包记录（从内存）"""
    global _flow_buffer
    with _flow_lock:
        _flow_buffer = []
    return jsonify({'success': True})


# ========== Mock 规则 CRUD ==========

@app.route('/api/mock_rules')
def api_mock_rules():
    """获取 Mock 规则列表"""
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM mock_rules ORDER BY id ASC')
    rows = [dict(r) for r in c.fetchall()]
    conn.close()
    return jsonify({'rules': rows})


@app.route('/api/mock_rules', methods=['POST'])
def api_mock_rules_add():
    """添加 Mock 规则"""
    data = request.get_json(silent=True, force=True) or {}
    required = ['name', 'match_type', 'match_pattern', 'action']
    for k in required:
        if not data.get(k):
            return jsonify({'error': f'missing {k}'}), 400

    conn = get_db()
    c = conn.cursor()
    c.execute('''
        INSERT INTO mock_rules (name, enabled, match_type, match_pattern, action, action_value, action_body, created_at)
        VALUES (?, 1, ?, ?, ?, ?, ?, ?)
    ''', (
        data['name'],
        data['match_type'],
        data['match_pattern'],
        data['action'],
        data.get('action_value', ''),
        data.get('action_body', ''),
        time.time(),
    ))
    rule_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'id': rule_id})


@app.route('/api/mock_rules/<int:rule_id>', methods=['PUT'])
def api_mock_rules_update(rule_id):
    """更新 Mock 规则"""
    data = request.get_json(silent=True, force=True) or {}
    fields = []
    values = []
    for k in ['name', 'enabled', 'match_type', 'match_pattern', 'action', 'action_value', 'action_body']:
        if k in data:
            fields.append(f'{k}=?')
            values.append(data[k])
    if not fields:
        return jsonify({'error': 'no fields to update'}), 400
    values.append(rule_id)

    conn = get_db()
    c = conn.cursor()
    c.execute(f'UPDATE mock_rules SET {", ".join(fields)} WHERE id=?', values)
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/mock_rules/<int:rule_id>', methods=['DELETE'])
def api_mock_rules_delete(rule_id):
    """删除 Mock 规则"""
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM mock_rules WHERE id=?', (rule_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})


@app.route('/api/proxy/start', methods=['POST'])
def api_proxy_start():
    """启动代理"""
    data = request.get_json(silent=True, force=True) or {}
    port = data.get('port', 8888)
    app._proxy_port = port
    # 已在启动脚本中自动启动，此处用作重启
    threading.Thread(target=run_proxy_thread, args=(port,), daemon=True).start()
    return jsonify({'success': True, 'port': port})


@app.route('/api/proxy/stop', methods=['POST'])
def api_proxy_stop():
    """停止代理"""
    stop_mitmproxy()
    return jsonify({'success': True})


# ========== WebSocket ==========

@socketio.on('connect')
def handle_connect():
    emit('status', {'connected': True})


@app.route('/api/export/flow/<int:flow_id>')
def api_export_flow(flow_id):
    """导出单个请求为 curl 命令（Charles 风格：-H "Key: Value" --compressed "URL"）"""
    with _flow_lock:
        f = next((x for x in _flow_buffer if x.get('id') == flow_id), None)
    if not f:
        return jsonify({'error': 'not found'}), 404
    method = f.get('method', 'GET')
    url = f"{f.get('scheme', 'http')}://{f.get('host', '')}{f.get('path', '')}"
    if f.get('query'):
        url += f"?{f.get('query', '')}"

    parts = ['curl']
    # 非 GET 才显式指定方法
    if method != 'GET':
        parts.append(f'-X {method}')
    # 请求头
    try:
        hdrs = json.loads(f.get('request_headers') or '{}')
        for k, v in hdrs.items():
            val = str(v).replace('"', '\\"')
            parts.append(f'-H "{k}: {val}"')
    except Exception:
        pass
    # 请求体
    body = f.get('request_body') or ''
    if body:
        escaped = body[:5000].replace('"', '\\"')
        parts.append(f'--data-raw "{escaped}"')
    # 压缩 & URL
    parts.append('--compressed')
    parts.append(f'"{url}"')
    curl = ' '.join(parts)
    return jsonify({'curl': curl, 'url': url})


def _check_port_available(port):
    """检查端口是否可用，不可用时打印提示"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        if result == 0:
            print(f'\n⚠️  端口 {port} 已被占用！')
            print(f'   请关闭占用该端口的程序（如 Charles、Fiddler）后重启。')
            print(f'   或修改 CAPTURE_SERVER.py 中的 proxy_port 参数。\n')
            return False
        return True
    except Exception:
        return True


def run_server(port=5051, proxy_port=8888, debug=False):
    """启动抓包服务器"""
    os.makedirs(os.path.dirname(CAPTURE_DB), exist_ok=True)
    app._proxy_port = proxy_port

    # 先初始化 addon 的数据库
    from src.capture import capture_addon
    capture_addon.setup(CAPTURE_DB, broadcast_flow)

    # 检测代理端口是否可用
    _check_port_available(proxy_port)

    # 后台启动 mitmproxy
    threading.Thread(target=run_proxy_thread, args=(proxy_port,), daemon=True).start()

    host_ip = _get_host_ip()

    print(f"""
╔══════════════════════════════════════════════════════╗
║              AdbTool 抓包 & Mock 服务器              ║
╠══════════════════════════════════════════════════════╣
║  Web UI:     http://{host_ip}:{port}                  ║
║  代理端口:    {proxy_port} (设备需设置此端口为代理)    ║
║  证书路径:    {get_cert_path()}              ║
║                                                     ║
║  📱 安卓设备设置代理:                               ║
║     设置 → WiFi → 代理 → 手动                       ║
║     主机名: {host_ip}                               ║
║     端口:   {proxy_port}                              ║
║                                                     ║
║  🔒 HTTPS 抓包需安装证书:                           ║
║     浏览器访问 http://mitm.it                        ║
║     或 adb push 证书到设备                           ║
╚══════════════════════════════════════════════════════╝
    """)

    socketio.run(app, host='0.0.0.0', port=port, debug=debug, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='AdbTool Capture & Mock Server')
    parser.add_argument('--port', type=int, default=5051, help='Web UI 端口')
    parser.add_argument('--proxy-port', type=int, default=8888, help='代理端口')
    parser.add_argument('--debug', action='store_true', help='调试模式')
    args = parser.parse_args()
    run_server(port=args.port, proxy_port=args.proxy_port, debug=args.debug)

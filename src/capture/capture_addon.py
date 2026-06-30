#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Mitmproxy 抓包插件：实时捕获 HTTP/HTTPS 流量并支持 Mock（纯内存，不存数据库）
"""

import json
import time
import sqlite3
import os
import re
from urllib.parse import urlencode

# 由服务器设置的流量回调（接收完整 flow dict）
_on_flow = None
_db_path = None


def _decode_unicode_json(text):
    """
    将 JSON 中的 \uXXXX 转义序列解码为实际中文。
    只对 JSON 内容进行处理，其他内容原样返回。
    """
    if not text:
        return text
    
    # 检测是否是 JSON（简单判断：以 { 或 [ 开头）
    stripped = text.strip()
    if not (stripped.startswith('{') or stripped.startswith('[')):
        return text
    
    try:
        # 解析 JSON 再重新序列化，ensure_ascii=False 会输出中文
        data = json.loads(text)
        return json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    except (json.JSONDecodeError, ValueError):
        # 不是有效 JSON，原样返回
        return text

# ========== Init ==========

def setup(db_path, flow_callback):
    """初始化（db_path 仅用于 mock_rules 表，不需要或 None 时跳过）"""
    global _on_flow, _db_path
    _on_flow = flow_callback
    _db_path = db_path
    # 仅初始化 mock_rules 表，流量不落盘
    if db_path:
        _init_mock_db(db_path)


def _init_mock_db(db_path):
    """初始化 Mock 规则表（仅 mock_rules，无 flows 表）"""
    conn = sqlite3.connect(db_path)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS mock_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            enabled INTEGER DEFAULT 1,
            match_type TEXT,
            match_pattern TEXT,
            action TEXT,
            action_value TEXT,
            action_body TEXT,
            created_at REAL
        )
    ''')
    conn.commit()
    conn.close()


# ========== Mock 规则 ==========

def _get_mock_rules():
    """获取所有已启用的 Mock 规则"""
    if not _db_path or not os.path.exists(_db_path):
        return []
    try:
        conn = sqlite3.connect(_db_path)
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute('SELECT * FROM mock_rules WHERE enabled=1 ORDER BY id ASC')
        rows = [dict(r) for r in c.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []


def _match_rule(flow, rules):
    """检查 flow 是否匹配某条规则，返回第一条匹配的"""
    for r in rules:
        mt = r['match_type']
        mp = r['match_pattern']
        host = flow.request.host
        path = flow.request.path
        url = f"{host}{path}"

        matched = False
        if mt == 'host':
            if mp == host or mp in host:
                matched = True
        elif mt == 'path':
            if mp in path:
                matched = True
        elif mt == 'host_path':
            if mp in url:
                matched = True
        elif mt == 'regex':
            if re.search(mp, url):
                matched = True

        if matched:
            return r
    return None


# ========== Mitmproxy Hooks ==========

def request(flow):
    """请求到达时 - 检查 Mock 规则 (Map Remote / Drop)"""
    rules = _get_mock_rules()
    if not rules:
        return

    rule = _match_rule(flow, rules)
    if not rule:
        return

    action = rule['action']

    if action == 'map_remote':
        target = rule['action_value']
        if target:
            flow.request.url = target
            from urllib.parse import urlparse
            parsed = urlparse(target)
            if parsed.hostname:
                flow.request.host = parsed.hostname
                flow.request.headers['Host'] = parsed.hostname
            if parsed.port:
                flow.request.port = parsed.port

    elif action == 'drop':
        flow.kill()


# 设备流量过滤：通过 TCP 客户端地址区分设备和 PC
# 机顶盒设备 IP 段（WiFi 网段）
_DEVICE_IP_PREFIXES = ('192.168.100.', '192.168.')
# PC 本机回环地址
_LOCAL_ADDRS = ('127.0.0.1', '::1', 'localhost', '[::1]')
# 需要排除的内部域名（mitmproxy 自身）
_INTERNAL_HOSTS = ('mitm.it', 'mitmproxy')


def _is_device_flow(flow):
    """
    判断是否为来自设备的流量。
    
    策略优先级:
    1. 通过 flow.client_conn.peername 获取 TCP 对端 IP → 匹配设备网段则放行
    2. 排除 mitmproxy 内部请求 (mitm.it 等)
    3. 其余全部放行（保守策略，宁可多显示不遗漏）
    
    注意: 设备 App 可能将上报地址配为 127.0.0.1:PORT，
          所以不能简单按 host==127.0.0.1 过滤！
    """
    # 排除 mitmproxy 内部请求
    host = getattr(flow.request, 'host', '') or ''
    if host.lower() in _INTERNAL_HOSTS or not host:
        return False
    
    # 尝试从 TCP 连接获取客户端真实 IP
    client_ip = '<unknown>'
    try:
        client_conn = getattr(flow, 'client_conn', None)
        if client_conn is not None:
            peer = getattr(client_conn, 'peername', None)
            if peer and len(peer) > 0:
                client_ip = peer[0]
                # 如果客户端是本机回环 → PC 自己发的请求 → 过滤掉
                if client_ip.startswith('127.') or client_ip == '::1':
                    return False
                # 如果客户端在设备网段 → 放行
                for prefix in _DEVICE_IP_PREFIXES:
                    if client_ip.startswith(prefix):
                        return True
                # 非 127 也非已知设备网段 → 放行（可能是其他设备）
                return True
    except Exception as e:
        import sys
        print(f'[capture] _is_device_flow exception: {e}', file=sys.stderr)
    
    # 无法获取客户端 IP 或 peername 为空 → 保守放行
    # 打印一次调试信息帮助排查
    print(f'[capture] flow passthrough: host={host} client_ip={client_ip}', file=sys.stderr)
    return True


def response(flow):
    """响应到达时 - Mock 响应 + 推送流量到前端"""
    # 过滤非设备流量
    if not _is_device_flow(flow):
        return
    start = time.time()

    # 1. 检查 Mock 规则 (Map Local / Status Code / Delay)
    rules = _get_mock_rules()
    if rules:
        rule = _match_rule(flow, rules)
        if rule:
            action = rule['action']
            if action == 'map_local':
                filepath = rule.get('action_value', '')
                fixed_body = rule.get('action_body', '')
                if fixed_body:
                    flow.response.set_text(fixed_body)
                elif filepath and os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        flow.response.set_text(f.read())

            elif action == 'status_code':
                try:
                    flow.response.status_code = int(rule['action_value'])
                except (ValueError, TypeError):
                    pass

            elif action == 'delay':
                try:
                    delay = float(rule['action_value'])
                    if delay > 0:
                        time.sleep(delay)
                except (ValueError, TypeError):
                    pass

    # 2. 构建完整 flow 数据（纯内存，不写数据库）
    elapsed = (time.time() - start) * 1000
    flow_id = int(time.time() * 1000) % 100000000 + hash(flow.request.url) % 10000

    # 提取客户端 IP（用于区分设备/PC 来源）
    client_ip = ''
    try:
        cc = getattr(flow, 'client_conn', None)
        if cc is not None:
            pn = getattr(cc, 'peername', None)
            if pn and len(pn) > 0:
                client_ip = pn[0]
    except Exception:
        pass

    try:
        flow_data = {
            'id': flow_id,
            'timestamp': time.time(),
            'method': flow.request.method,
            'scheme': flow.request.scheme,
            'host': flow.request.host,
            'port': flow.request.port,
            'path': flow.request.path.split('?')[0],
            'query': urlencode(dict(flow.request.query)) if flow.request.query else '',
            'client_ip': client_ip,
            'request_headers': json.dumps(dict(flow.request.headers), ensure_ascii=False),
            'request_body': _decode_unicode_json(flow.request.get_text(strict=False)[:65536]) if flow.request.content else '',
            'response_status': flow.response.status_code if flow.response else 0,
            'response_headers': json.dumps(dict(flow.response.headers), ensure_ascii=False) if flow.response else '{}',
            'response_body': _decode_unicode_json(flow.response.get_text(strict=False)) if flow.response and flow.response.content else '',
            'response_body_size': len(flow.response.get_text(strict=False)) if flow.response and flow.response.content else 0,
            'response_time_ms': round(elapsed, 1),
            'content_type': flow.response.headers.get('Content-Type', '')[:80] if flow.response else '',
        }
    except Exception:
        import traceback
        traceback.print_exc()
        flow_data = {
            'id': flow_id,
            'timestamp': time.time(),
            'method': getattr(flow.request, 'method', 'UNKNOWN'),
            'host': getattr(flow.request, 'host', ''),
            'path': getattr(flow.request, 'path', '/'),
            'client_ip': client_ip,
            'response_status': 0,
            'response_time_ms': round(elapsed, 1),
        }

    # 3. 推送给服务器（服务器负责广播 + 内存存储）
    if _on_flow:
        try:
            _on_flow(flow_data)
        except Exception:
            pass


addons = [__name__]  # mitmproxy 会寻找 request/response 函数

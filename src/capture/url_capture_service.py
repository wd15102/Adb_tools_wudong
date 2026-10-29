#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
URL 抓取服务
============
抓取指定域名（默认 henanyddpepg.cslgtest.imgo.tv）下的全部请求 URL，
实时去重并保存为列表文件，同时自动把电视设备全局代理指向本服务。

用法:
    python src/capture/url_capture_service.py
    python src/capture/url_capture_service.py --port 8888 \
        --host henanyddpepg.cslgtest.imgo.tv --out capture_henanyddpepg

输出文件（--out 目录下，每次启动自动清空重建）:
    urls.txt    每行一个完整 URL（去重，按首次抓取顺序）—— 列表形式
    urls.json   详细记录 [{time, method, url}]
"""

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlencode

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ADB = os.path.join(_ROOT, 'tools', 'windows', 'adb.exe')

# addon 状态（由服务启动时设置）
_state = {
    'host': '',
    'out_dir': '',
    'seen': set(),
    'lock': threading.Lock(),
}


def _full_url(flow):
    """获取完整请求 URL（含 query）。flow.request.path 已含 query，需拆开再拼"""
    path = flow.request.path.split('?')[0]
    qs = urlencode(dict(flow.request.query)) if flow.request.query else ''
    url = '%s://%s%s' % (flow.request.scheme, flow.request.host, path)
    if qs:
        url += '?' + qs
    return url


def _write_url(url, flow):
    out_dir = _state['out_dir']
    try:
        with open(os.path.join(out_dir, 'urls.txt'), 'a', encoding='utf-8') as f:
            f.write(url + '\n')
        record = {
            'time': time.strftime('%Y-%m-%d %H:%M:%S'),
            'method': flow.request.method,
            'url': url,
        }
        with open(os.path.join(out_dir, 'urls.json'), 'a', encoding='utf-8') as f:
            f.write(json.dumps(record, ensure_ascii=False) + '\n')
        print('[%s] %s %s' % (time.strftime('%H:%M:%S'), flow.request.method, url))
    except Exception as e:
        print('[url-capture] write error: %s' % e, file=sys.stderr)


# ========== Mitmproxy Hook ==========

def request(flow):
    """请求到达时：匹配目标域名 → 去重 → 实时写入列表文件"""
    host = (flow.request.host or '').lower()
    target = _state['host'].lower()
    if host != target and not host.endswith('.' + target):
        return
    url = _full_url(flow)
    with _state['lock']:
        if url in _state['seen']:
            return
        _state['seen'].add(url)
        _write_url(url, flow)


# ========== ADB 代理控制 ==========

def _adb(*args):
    try:
        r = subprocess.run([ADB] + list(args), capture_output=True, text=True, timeout=20)
        return r.returncode, (r.stdout or '') + (r.stderr or '')
    except Exception as e:
        return -1, str(e)


def set_device_proxy(ip, port):
    """设置设备全局 HTTP 代理 -> 本机代理端口"""
    return _adb('shell', 'settings', 'put', 'global', 'http_proxy', '%s:%d' % (ip, port))


def clear_device_proxy():
    """清除设备全局代理"""
    return _adb('shell', 'settings', 'delete', 'global', 'http_proxy')


def get_device_proxy():
    code, out = _adb('shell', 'settings', 'get', 'global', 'http_proxy')
    return out.strip()


# ========== 启动 mitmproxy ==========

def start_mitmproxy(port):
    from mitmproxy import options
    from mitmproxy.tools.dump import DumpMaster

    opts = options.Options(
        listen_host='0.0.0.0',
        listen_port=port,
        ssl_insecure=True,
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    master = DumpMaster(opts, loop=loop, with_termlog=False, with_dumper=False)
    master.addons.add(sys.modules[__name__])  # 本模块即 addon（request 钩子）
    print('[url-capture] mitmproxy 已启动，监听 0.0.0.0:%d' % port, flush=True)
    try:
        loop.run_until_complete(master.run())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()


def _port_available(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        result = s.connect_ex(('127.0.0.1', port))
        s.close()
        return result != 0
    except Exception:
        return True


def main():
    ap = argparse.ArgumentParser(description='AdbTool URL 抓取服务（指定域名 -> 列表文件）')
    ap.add_argument('--port', type=int, default=8888, help='代理监听端口 (默认 8888)')
    ap.add_argument('--host', default='henanyddpepg.cslgtest.imgo.tv', help='要抓取的域名')
    ap.add_argument('--out', default=os.path.join(_ROOT, 'capture_henanyddpepg'), help='输出目录')
    ap.add_argument('--proxy-ip', default='192.168.31.245', help='设备代理指向的电脑 IP')
    ap.add_argument('--no-set-proxy', action='store_true', help='不自动设置设备代理')
    ap.add_argument('--no-clear', action='store_true', help='退出时不自动清除设备代理')
    args = ap.parse_args()

    if not _port_available(args.port):
        print('[url-capture] 端口 %d 被占用，请关闭占用程序后重试' % args.port)
        sys.exit(1)

    os.makedirs(args.out, exist_ok=True)
    _state['host'] = args.host
    _state['out_dir'] = args.out
    for fn in ('urls.txt', 'urls.json'):
        p = os.path.join(args.out, fn)
        if os.path.exists(p):
            os.remove(p)

    print('=' * 60)
    print('[url-capture] 抓取域名: %s' % args.host)
    print('[url-capture] 列表文件 : %s' % os.path.join(args.out, 'urls.txt'))
    print('=' * 60, flush=True)

    # 设置设备全局代理
    if not args.no_set_proxy:
        code, out = set_device_proxy(args.proxy_ip, args.port)
        if code == 0:
            print('[url-capture] 设备代理已设置: %s:%d (%s)' % (args.proxy_ip, args.port, get_device_proxy()))
        else:
            print('[url-capture] 设置设备代理失败: %s' % out)
        if not args.no_clear:
            import atexit
            atexit.register(lambda: (clear_device_proxy(),
                                     print('[url-capture] 已清除设备代理')))

    print('[url-capture] 服务已就绪，请开始操作电视 …', flush=True)
    start_mitmproxy(args.port)


if __name__ == '__main__':
    main()

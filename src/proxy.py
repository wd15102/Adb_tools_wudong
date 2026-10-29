#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
import asyncio
import threading
from src import addon
from src.log import logger
from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.tools.web.master import WebMaster


class HttpProxy:
    mit_master = None
    thread = None
    loop = None

    def __init__(self, listen_port, up_port=None):
        super(HttpProxy, self).__init__()
        self.init(int(listen_port), up_port)

    @classmethod
    def init(cls, listen_port, up_port=None):
        if cls.mit_master:
            return
        cls.start(listen_port, up_port)

    @staticmethod
    async def _run_master(listen_port, up_port, loop):
        """在事件循环中运行 master，显式传入 loop。
        up_port 非空时以 upstream 模式运行：改写后的请求会转发给上游代理（如 Charles），
        从而在 Charles 上也能看到改写后的 dispatcher.do.xx。
        """
        _mode = None
        if up_port:
            _mode = [f"upstream:http://127.0.0.1:{up_port}"]
        opts = options.Options(
            listen_host='0.0.0.0',
            listen_port=listen_port,
            mode=_mode,
            ssl_insecure=True
        )
        # mitmproxy 12.x: 必须显式传 loop，否则 asyncio.get_running_loop() 会失败
        HttpProxy.mit_master = DumpMaster(
            opts,
            loop=loop,
            with_termlog=False,
            with_dumper=False
        )
        HttpProxy.mit_master.addons.add(addon)
        await HttpProxy.mit_master.run()

    @staticmethod
    def loop_in_thread(loop, listen_port, up_port):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(HttpProxy._run_master(listen_port, up_port, loop))

    @classmethod
    def start(cls, listen_port, up_port=None, master='dump'):
        if not master:
            return
        cls.loop = asyncio.new_event_loop()
        cls.thread = threading.Thread(target=cls.loop_in_thread,
                                      args=(cls.loop, int(listen_port), up_port), daemon=True)
        cls.thread.start()
        time.sleep(1)

    @classmethod
    def stop(cls):
        master = getattr(cls, 'mit_master', None)
        loop = getattr(cls, 'loop', None)
        # 关键：mitmproxy 的 shutdown() 只设置 should_exit，不会关闭监听 server 的 socket，
        # 在 Windows 上会导致端口一直占用、无法重新监听。
        # 必须先主动关闭 proxyserver 每个实例的监听 server，才能真正释放端口。
        if master is not None and loop is not None and not loop.is_closed():
            try:
                ps = master.addons.get('proxyserver')
                if ps is not None:
                    async def _close_servers():
                        for inst in list(ps.servers):
                            try:
                                await inst.stop()
                            except Exception:
                                pass
                    fut = asyncio.run_coroutine_threadsafe(_close_servers(), loop)
                    fut.result(timeout=5)
                    logger.info('HttpProxy: proxyserver 监听已关闭，端口已释放')
            except Exception as e:
                logger.error(f'HttpProxy close servers error: {e}')
        if master is not None:
            try:
                master.shutdown()
            except Exception:
                pass
        if getattr(cls, 'thread', None) and cls.thread.is_alive():
            cls.thread.join(timeout=3)
        if loop is not None and not loop.is_closed():
            try:
                loop.stop()
                loop.close()
            except Exception:
                pass
        cls.mit_master = None
        cls.thread = None
        cls.loop = None

    @classmethod
    def restart(cls, listen_port, up_port=None, master='dump'):
        cls.stop()
        while cls.is_running():
            time.sleep(0.1)
        cls.start(listen_port, up_port, master)

    @classmethod
    def is_running(cls):
        return getattr(cls, 'thread', None) and cls.thread.is_alive()


if __name__ == '__main__':
    mit = HttpProxy(9999)
    time.sleep(999999)

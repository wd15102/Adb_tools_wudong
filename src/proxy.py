#!/usr/bin/env python
# -*- coding: utf-8 -*-
import time
import asyncio
import threading
from src import addon
from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster
from mitmproxy.tools.web.master import WebMaster


class HttpProxy:
    mit_master = None
    thread = None
    loop = None

    def __init__(self, listen_port):
        super(HttpProxy, self).__init__()
        self.init(int(listen_port))

    @classmethod
    def init(cls, listen_port):
        if cls.mit_master:
            return
        cls.start(listen_port)

    @staticmethod
    async def _run_master(up_port, loop):
        """在事件循环中运行 master，显式传入 loop"""
        opts = options.Options(
            listen_host='0.0.0.0',
            listen_port=6666,
            mode=[f"upstream:http://127.0.0.1:{up_port}"],
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
    def loop_in_thread(loop, up_port):
        asyncio.set_event_loop(loop)
        loop.run_until_complete(HttpProxy._run_master(up_port, loop))

    @classmethod
    def start(cls, up_port, master='dump'):
        if not master:
            return
        cls.loop = asyncio.new_event_loop()
        cls.thread = threading.Thread(target=cls.loop_in_thread, args=(cls.loop, up_port), daemon=True)
        cls.thread.start()
        time.sleep(1)

    @classmethod
    def stop(cls):
        if getattr(cls, 'mit_master', None):
            cls.mit_master.shutdown()
        if getattr(cls, 'thread', None) and cls.thread.is_alive():
            cls.thread.join(timeout=3)
        if getattr(cls, 'loop', None) and not cls.loop.is_closed():
            cls.loop.stop()
            cls.loop.close()
        cls.mit_master = None
        cls.thread = None
        cls.loop = None

    @classmethod
    def restart(cls, listen_port, master='dump'):
        cls.stop()
        while cls.is_running():
            time.sleep(0.1)
        cls.start(listen_port, master)

    @classmethod
    def is_running(cls):
        return getattr(cls, 'thread', None) and cls.thread.is_alive()


if __name__ == '__main__':
    mit = HttpProxy(9999)
    time.sleep(999999)

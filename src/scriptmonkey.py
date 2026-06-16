#!/usr/bin/env python
# -*- coding: utf-8 -*-
import re
import os
import time
import config
import threading
from src.log import logger
from src.adbtools import AdbUtils
from lxml import etree
from src.u2_server import U2Server
from src.focus_move import AndroidTVFocus

class ScriptMonkey:
    def __init__(self, device, package, temp_data, interval=5, timeout=9999999, collectors=None):
        self.device = AdbUtils(device)
        self.package = package
        self._interval = 2
        self._timeout = timeout
        self._stop_event = threading.Event()
        self.script_monkey_thread = None
        self.script = config.monkey_cmd
        self.temp_data = temp_data
        self.main_activity = self.device.adb.get_main_activity(package)
        self.COMMAND_MAP = {
            "启动应用": "start_app",
            "停止应用": "stop_app",
            "等待页面出现文本信息": "wait_until_page_contains",
            "等待页面出现元素信息": "wait_until_page_contains_element",
            "按次数上移": "key_up",
            "按次数下移": "key_down",
            "按次数左移": "key_left",
            "按次数右移": "key_right",
            "确认键": "key_ok",
            "菜单键": "key_menu",
            "首页键": "key_home",
            "执行命令": "exec_command",
            "返回首页": "back_home",
            "返回顶部导航": "back_menu_focused",
            "焦点移动到文本": "focus_move_to_text",
            "焦点移动到元素": "focus_move_to_element",
            "等待": time.sleep
        }
        self.u2_server = U2Server(device)
        self.u2_server.start_u2_server()
        self.controller = AndroidTVFocus()
        self.move_dict = {'向上': 19, '向下': 20, '向左': 21, '向右': 22}

    def run_line(self, line):
        parts = re.split(r'\s{2,}', line.rstrip())
        if not parts:
            return

        cmd = parts[0]
        args = parts[1:]

        if cmd not in self.COMMAND_MAP:
            raise ValueError(f"未知命令: {cmd}")

        method_name = self.COMMAND_MAP[cmd]
        if isinstance(method_name, str):
            method = getattr(self, method_name)
        else:
            method = method_name

        # 自动识别参数类型
        parsed_args = []
        for a in args:
            try:
                parsed_args.append(int(a))
            except ValueError:
                parsed_args.append(a)

        method(*parsed_args)

    def _script_monkey(self):
        """
        adb monkey执行方法
        :return:
        """
        end_time = time.time() + self._timeout
        script_path = os.path.join(config.root_path, 'script', self.script)
        while not self._stop_event.is_set() and time.time() < end_time:
            try:
                with open(script_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        logger.info(line)
                        if not line or line.startswith("#"):
                            continue
                        self.run_line(line)
            except Exception as e:
                logger.error(e)

    def start_app(self):
        top_activity = self.device.adb.get_focus_window_activity()
        if top_activity.find(self.package) == -1:
            self.device.adb.start_activity(f'{self.package}/{self.main_activity}')

    def stop_app(self):
        self.device.adb.force_stop_package(self.package)

    def find_element_by_xpath(self, xpath):
        page_source = self.u2_server.get_page_source()
        tree = etree.fromstring(page_source.encode('utf-8'))
        element = tree.xpath(xpath)
        if len(element) > 0:
            return element[0]
        return None

    def wait_until_page_contains(self, text, timeout=10):
        e_time = time.time() + timeout
        while True:
            page_source = self.u2_server.get_page_source()
            if text in page_source:
                return True
            if time.time() > e_time:
                return False
            time.sleep(0.2)

    def wait_until_page_not_contains(self, text, timeout=5):
        e_time = time.time() + timeout
        while True:
            page_source = self.u2_server.get_page_source()
            if text not in page_source:
                return True
            if time.time() > e_time:
                logger.error(f'{text} present in {timeout} second')
                return False
            time.sleep(0.2)

    def wait_until_page_contains_element(self, xpath, timeout=5):
        e_time = time.time() + timeout
        while True:
            try:
                element = self.find_element_by_xpath(xpath)
                if element is not None:
                    return True
            except Exception as e:
                logger.debug(e)
            if time.time() > e_time:
                return False
            time.sleep(0.2)

    def press_key(self, key, nums=1, sec=2):
        for n in range(nums):
            self.device.adb.run_adb_shell_cmd(f'input keyevent {key}')
            time.sleep(sec)

    def key_up(self, nums=1, sec=2):
        self.press_key(19, nums, sec)

    def key_down(self, nums=1, sec=2):
        self.press_key(20, nums, sec)

    def key_left(self, nums=1, sec=2):
        self.press_key(21, nums, sec)

    def key_right(self, nums=1, sec=2):
        self.press_key(22, nums, sec)

    def key_ok(self, nums=1, sec=2):
        self.press_key(23, nums, sec)

    def key_back(self, nums=1, sec=2):
        self.press_key(4, nums, sec)

    def key_menu(self, nums=1, sec=2):
        self.press_key(82, nums, sec)

    def key_home(self, nums=1, sec=2):
        self.press_key(3, nums, sec)

    def exec_command(self, cmd):
        self.device.adb.run_adb_shell_cmd(f'am start -d "{cmd}"')

    def back_display_text(self, text):
        for i in range(10):
            try:
                self.wait_until_page_contains(text, 2)
                return
            except AssertionError:
                self.key_back(1, 1)

    def back_display_element(self, element):
        for i in range(10):
            ret = self.wait_until_page_contains_element(element, 2)
            if ret:
                return
            self.key_back()

    def back_home(self):
        xpath = """//*[contains(@resource-id,"channel_navigate_view_id")]"""
        self.back_display_element(xpath)

    def back_menu_focused(self):
        xpath = """//*[contains(@resource-id,"channel_navigate_view_id")]/*[@focused='true' and @focusable='true']"""
        self.back_display_element(xpath)

    def focus_move_to_element(self, locator):
        element = f'{locator}[@focusable="true"][@clickable="true"]'
        ret = self.wait_until_page_contains_element(element)
        if not ret:
            locator = f'locator/ancestor-or-self::*[@focusable="true" and @clickable="true"][1]'
        else:
            locator = locator
        for i in range(10):
            element = self.find_element_by_xpath(locator)
            bounds = element.attrib.get('bounds')
            page_source = self.u2_server.get_page_source()
            direction_list = self.controller.move_to_target(page_source, bounds)
            for direction in direction_list:
                self.device.adb.run_adb_shell_cmd(f'input keyevent {self.move_dict[direction]}')
            if len(direction_list) == 0:
                break

    def focus_move_to_text(self, text):
        locator = None
        text_locator = f'//*[@text="{text}"]'
        desc_locator = f'//*[@content-desc="{text}"]'

        for i in range(20):
            text_ret = self.wait_until_page_contains_element(text_locator, 1)
            if text_ret:
                locator = text_locator
                break

            desc_ret = self.wait_until_page_contains_element(desc_locator, 1)
            if desc_ret:
                locator = desc_locator
                break

            time.sleep(0.5)
        if locator:
            self.focus_move_to_element(locator)

    def start(self):
        """
        script monkey启动方法
        :return:
        """
        logger.debug("script monkey start")
        self._stop_event.clear()
        self.script_monkey_thread = threading.Thread(target=self._script_monkey)
        self.script_monkey_thread.start()

    def stop(self):
        """
        script monkey停止方法
        :return:
        """
        logger.debug("scrpit monkey stop")
        if self.script_monkey_thread.is_alive():
            self._stop_event.set()
            self.script_monkey_thread.join(timeout=1)
            self.script_monkey_thread = None
            self.u2_server.stop_u2_server()


if __name__ == "__main__":
    from src.perf_test import TempData

    TempData.result_path = r'D:\pythoncode\AdbTool\results'
    config.monkey_cmd = '直播'
    scr = ScriptMonkey('MAX0019071000087', 'com.mgtv.tv', TempData)
    scr.start()
    time.sleep(10000)

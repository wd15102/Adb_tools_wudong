#!/usr/bin/env python
# -*- coding: utf-8 -*-
import io
import os
import cv2
import sys
import time
import socket
import struct
import threading
import numpy as np
import tkinter as tk
from src.log import logger
from config import root_path
from PIL import Image, ImageTk
from src.adbtools import AdbUtils
from collections import OrderedDict


# https://github.com/openatx/stf-binaries/tree/0.3.0/node_modules/%40devicefarmer/minicap-prebuilt/prebuilt/armeabi-v7a/lib/android-30


class MNCInstaller(object):
    def __init__(self, android):
        self.android = android
        self.abi = self.android.adb.get_cpu_abi()
        self.sdk = self.android.adb.get_sdk_version()
        if self.is_mnc_installed():
            logger.info('minicap already existed')
        else:
            self.copy_mnc2device()
            self.copy_mnc_so2device()

    def copy_mnc2device(self):
        src_path = os.path.join(root_path, 'tools', 'minicap-prebuilt', 'prebuilt', self.abi, 'bin', 'minicap')
        dst_path = '/data/local/tmp/minicap'
        self.android.adb.push_file(src_path, dst_path)
        self.android.adb.run_adb_shell_cmd('chmod 777 ' + dst_path)
        logger.info('minicap installed in {}'.format(dst_path))

    def copy_mnc_so2device(self):
        src_path = os.path.join(root_path, 'tools', 'minicap-prebuilt', 'prebuilt', self.abi, 'lib',
                                'android-%s' % self.sdk, 'minicap.so')
        dst_path = '/data/local/tmp/minicap.so'
        self.android.adb.push_file(src_path, dst_path)
        self.android.adb.run_adb_shell_cmd('chmod 777 ' + dst_path)
        logger.info('minicap.so installed in {}'.format(dst_path))

    def is_installed(self, name):
        ret = self.android.adb.run_adb_shell_cmd('ls /data/local/tmp')
        if name in ret.split():
            return True
        return False

    def is_mnc_installed(self):
        ret = self.is_installed('minicap') and self.is_installed('minicap.so')
        return ret


class Banner:
    def __init__(self):
        self.__banner = OrderedDict(
            [('version', 0),
             ('length', 0),
             ('pid', 0),
             ('realWidth', 0),
             ('realHeight', 0),
             ('virtualWidth', 0),
             ('virtualHeight', 0),
             ('orientation', 0),
             ('quirks', 0)
             ])

    def __setitem__(self, key, value):
        self.__banner[key] = value

    def __getitem__(self, key):
        return self.__banner[key]

    def keys(self):
        return self.__banner.keys()

    def __str__(self):
        return str(self.__banner)


class KeyMap:
    key_map = {
        'Up': 19,
        'Down': 20,
        'Left': 21,
        'Right': 22,
        'Escape': 4,
        'Return': 23,
        'Cancel': 3,
        'Next': 82
    }


class MiniCap(object):
    def __init__(self, master, device_id, banner, text, update_interval=50):
        self.master = master
        self.text = text
        self.update_interval = update_interval  # 更新间隔（毫秒）

        self.android = AdbUtils(device_id)
        self.mini_server = None
        self.buffer_size = 4096
        self.banner = banner
        self.__socket = None
        self.stop_event = threading.Event()
        self.screen_record = None
        self.ratio = 1
        self.mini_stdout = None

        self.canvas = tk.Canvas(self.master, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.master.bind('<Key>', self.on_key_press)

        self.current_image = None
        self.image_lock = threading.Lock()
        self.rectangle_list = None  # 用于存储红框的标识符
        self.start_screen_record()
        #
        self.master.bind("<Configure>", self.resize_event)
        self.update_frame()

    def on_key_press(self, event):
        key = event.keysym
        if KeyMap.key_map.get(key):
            cmd = f'input keyevent {KeyMap.key_map.get(key)}'
        else:
            cmd = f'input text {key}'
        t = threading.Thread(target=self.android.adb.run_adb_shell_cmd, args=(cmd,))
        t.start()

    def creat_minicap_server(self):
        MNCInstaller(self.android)
        width, height = self.android.adb.get_wm_size()
        screen_size = f'{width}x{height}@{int(width * self.ratio)}x{int(height * self.ratio)}/0'
        cmd = 'LD_LIBRARY_PATH=/data/local/tmp /data/local/tmp/minicap -P ' + screen_size
        logger.info('minicap server start: {}'.format(cmd))
        self.mini_stdout = None
        process = self.android.adb.run_adb_shell_cmd(cmd, sync=False)
        # process.communicate()
        while True:
            line = process.stdout.readline()
            if line:
                logger.info(line)
                self.mini_stdout = line.decode()

    def start_mini_server(self):
        if self.android.adb.is_process_running('minicap'):
            return True
        self.mini_server = threading.Thread(target=self.creat_minicap_server, daemon=True)
        self.mini_server.start()
        for i in range(10):
            if self.android.adb.is_process_running('minicap'):
                # 未完全启动无图
                if self.mini_stdout and self.mini_stdout.find('JPG encoder') != -1:
                    return True
            time.sleep(1)
            logger.info('minicap not start,wait 1S')
        return False

    def stop_mini_server(self):
        self.mini_server.join(timeout=0.1)
        while True:
            self.android.adb.kill_process('/data/local/tmp/minicap')
            if not self.android.adb.is_process_running('/data/local/tmp/minicap'):
                break
            logger.info('minicap not start,wait 1S')
        self.mini_server = None

    def minicap_screen_shot(self):
        src_path = '/data/local/tmp/fastcap_temp.png'
        dst_path = os.path.join(root_path, 'result', 'fastcap_temp.png')
        self.android.adb.pull_file(src_path, dst_path)
        logger.info('export screen shot to {}'.format(dst_path))

    def socket_connect(self, host, port):
        try:
            self.__socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.__socket.connect((host, port))
        except socket.error as e:
            self.text.insert('insert', f'socket连接失败:{e}\n')
            self.__socket = None
            logger.error(e)

    @staticmethod
    def on_image_transferred(data):
        file_name = str(time.time()) + '.jpg'
        with open(file_name, 'wb') as f:
            for b in data:
                f.write((b).to_bytes(1, 'big'))

    def resize_event(self, event=None):
        """根据窗口大小调整图像显示"""
        if self.current_image is not None:
            canvas_width = self.master.winfo_width() if self.master.winfo_width() != 1 else self.current_image.width
            canvas_height = self.master.winfo_height() if self.master.winfo_height() != 1 else self.current_image.height

            image_ratio = self.current_image.width / self.current_image.height
            window_ratio = canvas_width / canvas_height

            if window_ratio > image_ratio:
                new_height = canvas_height
                new_width = int(new_height * image_ratio)
            else:
                new_width = canvas_width
                new_height = int(new_width / image_ratio)

            # 使用cv2
            resized_image = cv2.resize(np.array(self.current_image), (new_width, new_height),
                                       interpolation=cv2.INTER_LANCZOS4)

            photo = ImageTk.PhotoImage(Image.fromarray(resized_image))

            self.canvas.delete("all")
            self.canvas.create_image(canvas_width // 2, canvas_height // 2, image=photo, anchor=tk.CENTER)
            self.canvas.image = photo
            if self.rectangle_list:
                x_ratio = new_width / self.current_image.width
                y_ratio = new_height / self.current_image.height
                x_offset = (canvas_width - new_width) // 2
                y_offset = (canvas_height - new_height) // 2
                for rect in self.rectangle_list:
                    scaled_rect = [
                        int(rect[0] * x_ratio) + x_offset,
                        int(rect[1] * y_ratio) + y_offset,
                        int(rect[2] * x_ratio) + x_offset,
                        int(rect[3] * y_ratio) + y_offset
                    ]
                    self.canvas.create_rectangle(*scaled_rect, outline='red', width=2)

    def update_frame(self):
        """定时更新图像"""
        with self.image_lock:
            if self.current_image:
                self.resize_event()
        self.master.after(self.update_interval, self.update_frame)

    def canvas_display(self):
        self.start_screen_record()
        last_image = None

        while not self.stop_event.is_set():
            if len(self.image_list) == 0 and last_image is None:
                file_path = os.path.join(root_path, 'tools', 'screen_img.jpg')
                image = Image.open(file_path)
                image = image.resize((width, height), Image.Resampling.LANCZOS)
                last_image = image
            elif len(self.image_list) == 0 and last_image is not None:
                continue
            else:
                # data = self.image_list.pop(0)
                data = self.image_list[-1]  # 只取最新的一帧，部分盒子全部帧显示时太卡
                self.image_list = []

                im_io = io.BytesIO(data)
                image = Image.open(im_io)
                last_image = image

            image = ImageTk.PhotoImage(image)

            if canvas.winfo_exists():
                canvas.create_image(0, 0, anchor='nw', image=image)
            abc = None
            abc = image  # 解决摄像头图像闪烁的问题..

    def _screen_record_thread(self):
        read_banner_bytes = 0
        banner_length = 24
        read_frame_bytes = 0
        frame_body_length = 0
        data = []
        while not self.stop_event.is_set():
            try:
                if not self.__socket:
                    return
                chunk = self.__socket.recv(self.buffer_size)
            except socket.error as e:
                logger.info(e)
                chunk = ''
            cursor = 0
            buf_len = len(chunk)
            while cursor < buf_len:
                if read_banner_bytes < banner_length:
                    try:
                        b_list = struct.unpack("<2b5i2b", chunk)
                    except Exception as e:
                        logger.error(f'struct unpack error:{e}')
                        self.start_screen_record()
                        break
                    for k, v in zip(self.banner.keys(), b_list):
                        self.banner.__setitem__(k, v)
                    cursor = buf_len
                    read_banner_bytes = banner_length
                elif read_frame_bytes < 4:
                    frame_body_length += (chunk[cursor] << (read_frame_bytes * 8)) >> 0
                    cursor += 1
                    read_frame_bytes += 1
                else:
                    if buf_len - cursor >= frame_body_length:
                        data.extend(chunk[cursor:cursor + frame_body_length])

                        # np_data = np.frombuffer(bytearray(data), dtype=np.uint8)
                        # image = cv2.imdecode(np_data, cv2.IMREAD_COLOR)

                        image_stream = io.BytesIO(bytearray(data))
                        image = Image.open(image_stream)

                        with self.image_lock:
                            self.current_image = image
                        cursor += frame_body_length
                        frame_body_length = read_frame_bytes = 0
                        data = []
                    else:
                        data.extend(chunk[cursor:buf_len])
                        frame_body_length -= buf_len - cursor
                        read_frame_bytes += buf_len - cursor
                        cursor = buf_len
        logger.info("screen_record thread stop")

    def start_screen_record(self):
        logger.info("screen_record thread start")
        if self.screen_record is not None:
            self.close()
        self.stop_event.clear()
        self.start_mini_server()
        # is_process_running会导致图片数据接收异常，以下命令必须在之后
        self.android.adb.run_adb_cmd('forward tcp:1717 localabstract:minicap')
        self.socket_connect('localhost', 1717)
        self.screen_record = threading.Thread(target=self._screen_record_thread)
        self.screen_record.start()

    def close(self):
        if self.screen_record is not None:
            self.stop_event.set()
            try:
                if self.__socket:
                    self.__socket.close()
            except Exception as e:
                logger.debug(e)
            self.screen_record.join()
            self.screen_record = None
            self.current_image = None

    def draw_rectangle(self, rectangle_list):
        self.rectangle_list = rectangle_list


def screen_minicap(master, device_id, text, update_interval=50):
    screen = MiniCap(master, device_id, Banner(), text, update_interval)
    return screen


if __name__ == '__main__':
    root = tk.Tk()
    app1 = MiniCap(root, 'MAX0019111000070', Banner(), '')
    root.protocol("WM_DELETE_WINDOW", app1.close)
    root.mainloop()
    logger.info('start_screen_record')

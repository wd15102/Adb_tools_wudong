#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import time
import cv2
import threading
import numpy as np
import tkinter as tk
from src import scrcpy
from PIL import Image, ImageTk
from src.log import logger

# 定义事件线程
def thread_ui(func, *args):
    """开启一个新线程任务"""
    t = threading.Thread(target=func, args=args)
    t.setDaemon(True)
    t.start()


class ScreenScrcpy:
    def __init__(self, master, device_id=None, update_interval=50, max_fps=30):
        self.master = master
        self.update_interval = update_interval  # 更新间隔（毫秒）

        self.now_device = device_id
        self.now_client = scrcpy.Client(device=device_id, max_fps=max_fps, bitrate=4000000) if self.now_device else None

        self.canvas = tk.Canvas(self.master, bg="black")
        self.canvas.pack(fill=tk.BOTH, expand=True)

        self.canvas.bind("<Button-1>", self.mouse_click)
        self.master.bind("<Key>", self.on_key_press)

        self.current_image = None
        self.image_lock = threading.Lock()

        self.rectangle_list = None  # 用于存储红框的标识符

        # 监听设备屏幕数据
        if self.now_device:
            self.now_client.add_listener(scrcpy.EVENT_FRAME, self.main_frame)
            thread_ui(self.now_client.start)

        self.master.bind("<Configure>", self.resize_event)
        self.update_frame()

    def update_frame(self):
        """定时更新图像"""
        with self.image_lock:
            if self.current_image:
                self.resize_event()
        self.master.after(self.update_interval, self.update_frame)

    def main_frame(self, frame: np.ndarray):
        """监听设备的屏幕数据并更新最新帧"""
        if frame is not None:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame_rgb)
            # 只保留最新的一帧
            with self.image_lock:
                self.current_image = image

    def resize_event(self, event=None):
        """根据窗口大小调整图像显示"""
        if self.current_image:
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

            # logger.debug(f'image resize:new width:{new_width}, new height:{new_height}, canvas width:{canvas_width},'
            #              f'canvas height:{canvas_height}, image ratio:{str(image_ratio)}')
            # resized_image = self.current_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # cv2处理图像更快
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

    def mouse_click(self, event):
        """处理鼠标点击事件"""
        if self.now_client and self.current_image:
            canvas_width = self.canvas.winfo_width()
            canvas_height = self.canvas.winfo_height()

            ratio = min(canvas_width / self.current_image.width, canvas_height / self.current_image.height)
            x_offset = (canvas_width - self.current_image.width * ratio) // 2
            y_offset = (canvas_height - self.current_image.height * ratio) // 2

            x = (event.x - x_offset) / ratio
            y = (event.y - y_offset) / ratio

            if 0 <= x <= self.current_image.width and 0 <= y <= self.current_image.height:
                self.now_client.control.touch(int(x), int(y), scrcpy.ACTION_DOWN)
                self.now_client.control.touch(int(x), int(y), scrcpy.ACTION_UP)

    def on_key_press(self, event):
        if (event.state & 0x4) and event.keysym == 'v':  # 0x4 表示 Control 键被按下
            clipboard_text = self.master.clipboard_get()
            if self.now_client:
                self.now_client.control.text(clipboard_text)
            return

        """处理键盘按键事件"""
        key_code = self.key_code(event.keysym)
        if key_code != -1 and self.now_client:
            self.now_client.control.keycode(key_code, scrcpy.ACTION_DOWN)
            self.now_client.control.keycode(key_code, scrcpy.ACTION_UP)

    @staticmethod
    def key_code(keys):
        """将 Tkinter 的按键符号映射到 Android 的按键代码"""
        if len(keys) == 1:
            if '0' <= keys <= '9':
                return ord(keys) - ord('0') + 7
            if 'A' <= keys <= 'Z':
                return ord(keys) - ord('A') + 29
            if 'a' <= keys <= 'z':
                return ord(keys) - ord('a') + 29

        # 特殊按键处理
        key_mapping = {
            'Return': scrcpy.KEYCODE_ENTER,
            'BackSpace': scrcpy.KEYCODE_DEL,
            'Tab': scrcpy.KEYCODE_TAB,
            'Escape': scrcpy.KEYCODE_BACK,
            'Left': scrcpy.KEYCODE_DPAD_LEFT,
            'Right': scrcpy.KEYCODE_DPAD_RIGHT,
            'Up': scrcpy.KEYCODE_DPAD_UP,
            'Down': scrcpy.KEYCODE_DPAD_DOWN,
            'space': scrcpy.KEYCODE_SPACE,
            'Shift_L': scrcpy.KEYCODE_SHIFT_LEFT,
            'Shift_R': scrcpy.KEYCODE_SHIFT_RIGHT,
            'Control_L': scrcpy.KEYCODE_CTRL_LEFT,
            'Control_R': scrcpy.KEYCODE_CTRL_RIGHT,
            'Alt_L': scrcpy.KEYCODE_ALT_LEFT,
            'Alt_R': scrcpy.KEYCODE_ALT_RIGHT,
            'F1': scrcpy.KEYCODE_F1,
            'F2': scrcpy.KEYCODE_F2,
            'F3': scrcpy.KEYCODE_F3,
            'F4': scrcpy.KEYCODE_F4,
            'F5': scrcpy.KEYCODE_F5,
            'F6': scrcpy.KEYCODE_F6,
            'F7': scrcpy.KEYCODE_F7,
            'F8': scrcpy.KEYCODE_F8,
            'F9': scrcpy.KEYCODE_F9,
            'F10': scrcpy.KEYCODE_F10,
            'F11': scrcpy.KEYCODE_F11,
            'F12': scrcpy.KEYCODE_F12,
            'Insert': scrcpy.KEYCODE_INSERT,
            'Delete': scrcpy.KEYCODE_FORWARD_DEL,
            'Home': scrcpy.KEYCODE_HOME,
            'End': scrcpy.KEYCODE_MOVE_END,
            'Page_Up': scrcpy.KEYCODE_PAGE_UP,
            'Page_Down': scrcpy.KEYCODE_PAGE_DOWN,
            'Cancel': scrcpy.KEYCODE_HOME,
            'Next': 82
        }

        # 返回映射的按键代码，如果没有映射，则返回 -1
        return key_mapping.get(keys, -1)

    def close(self):
        """关闭事件，停止 scrcpy 客户端"""
        self.now_client.stop()

    def draw_rectangle(self, rectangle_list):
        self.rectangle_list = rectangle_list


# 主程序入口
def screen_scrcpy(master, device_id, update_interval=50, max_fps=30):
    screen = ScreenScrcpy(master, device_id, update_interval, max_fps)
    return screen


if __name__ == "__main__":
    root = tk.Tk()
    app1 = ScreenScrcpy(root, 'MAX0019111000070')
    root.protocol("WM_DELETE_WINDOW", app1.close)
    root.mainloop()

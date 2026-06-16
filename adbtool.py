#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import sys
import config
import platform
import pyautogui
import subprocess
from src.gui import Gui
from src.download import SoftDownload, download_main

version = '260224'
download = SoftDownload(version)

if download.check_version() and pyautogui.confirm(text='有新版本，是否更新', title='通知', buttons=['OK', 'Cancel']) == 'OK':
    download_main(download)
    if pyautogui.confirm(text='应用下载完成，是否安装', title='通知', buttons=['OK', 'Cancel']) == 'OK':
        # 执行目录下程序并往下执行退出主程序
        os_platform = platform.system()
        if os_platform == 'windows':
            app_path = os.path.join(config.root_path, 'tools', 'dist', 'upgrade.exe')
        else:
            app_path = os.path.join(config.root_path, 'tools', 'dist', 'upgrade')
        subprocess.Popen([app_path, download.filename, config.root_path])
        sys.exit()
else:
    gui = Gui(version)
    gui.start()

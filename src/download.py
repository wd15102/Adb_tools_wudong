import os
import config
import _thread
import requests
from src.log import logger
from src.utils import Utils
from tkinter.ttk import Progressbar
from tkinter import Tk, Label, IntVar, DoubleVar, messagebox


class SoftDownload:
    def __init__(self, soft_version):
        self.soft_version = soft_version
        self.soft_update_url = None
        self.root = None
        self.progress_var = None
        self.label_var = None
        self.progress_bar = None
        self.os_platform = Utils.get_os_platform()
        self.filename = None

    def init_ui(self, root):
        self.root = root
        self.root.title('软件更新')
        self.root.geometry('300x100')
        self.progress_var = IntVar()
        self.label_var = DoubleVar()
        self.label_var.set(0.0)
        label = Label(self.root, text='开始下载软件，请等待···')
        label.pack(pady=5)

        self.progress_bar = Progressbar(self.root, length=200, mode='indeterminate')
        self.progress_bar.pack(pady=5)

    @staticmethod
    def tip_show(msg):
        messagebox.showwarning('提示', msg)

    def soft_download_with_thread(self):
        # 下载进度工具条
        self.progress_var.set(0)
        self.progress_bar.start(60)

        # 软件下载线程
        _thread.start_new_thread(self._soft_download, ())

    def check_version(self):
        url = f'http://{config.server_ip}/apk/version'
        try:
            req = requests.get(url, stream=True, verify=False)
        except Exception as e:
            logger.debug(e)
            return
        if req is None or str(req.status_code) != '200':
            return
        latest_version = req.text

        # 版本比对
        return self.compare_version(latest_version)

    def _update_progressbar(self):
        self.progress_bar['value'] = self.label_var.get()

    def _end_download(self):
        self.progress_bar.stop()
        self.root.destroy()
        logger.debug('root destroy')

    @staticmethod
    def get_remote_file_size(url, proxy=None):
        """通过content-length头获取远程文件大小"""
        try:
            req = requests.head(url, proxies={'http': proxy, 'https': proxy} if proxy else None, verify=False)
            file_size = int(req.headers.get('Content-Length', 0))
            return file_size
        except Exception as e:
            logger.debug(e)
            return 0

    def _soft_download(self):
        self.label_var.set(0.0)
        if self.os_platform == 'Windows':
            apk_name = 'adbtool.zip'
        else:
            apk_name = 'mac-adbtool.zip'
        latest_soft_url = f'http://{config.server_ip}/apk/{apk_name}'
        latest_size = self.get_remote_file_size(latest_soft_url)
        result_dir = os.path.join(config.root_path, 'results')
        if not os.path.exists(result_dir):
            os.mkdir(result_dir)
        file_name = os.path.join(result_dir, 'latest_version.zip')
        self.filename = file_name

        logger.debug('apk download start')
        start_size = 0
        with requests.get(latest_soft_url, stream=True, verify=False) as r:
            with open(file_name, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    if not chunk:
                        continue
                    start_size += len(chunk)
                    f.write(chunk)
                    f.flush()
                    self.label_var.set(100.0 * start_size / latest_size)
        logger.debug('apk download completed')
        self._end_download()

    def compare_version(self, latest_version):
        return int(self.soft_version) < int(latest_version)


def download_main(dialog):
    app = Tk()
    app.geometry('0x0')
    dialog.init_ui(root=app)
    dialog.soft_download_with_thread()
    app.mainloop()


if __name__ == '__main__':
    download = SoftDownload(soft_version='240721')
    if download.check_version():
        download_main(download)


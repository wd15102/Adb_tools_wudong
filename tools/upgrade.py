import os
import sys
import stat
import shutil
import zipfile
import platform
from config import server_ip
from threading import Thread
from tkinter import Tk, Label, IntVar, DoubleVar, messagebox, Text
from tkinter.ttk import Progressbar


class SoftUpgrade:
    def __init__(self, zip_name, target):
        self.zip_name = zip_name
        self.target = target
        self.root = None
        self.text = None
        self.progress_var = None
        self.label_var = None
        self.progress_bar = None

    def init_ui(self, root):
        self.root = root
        self.root.title('软件更新')
        self.root.geometry('400x250')
        self.progress_var = IntVar()
        self.label_var = DoubleVar()
        self.label_var.set(0.0)

        Label(self.root, text='开始更新软件，请等待···').pack(pady=5)

        self.progress_bar = Progressbar(self.root, length=300, mode='determinate', maximum=100)
        self.progress_bar.pack(pady=5)

        self.text = Text(self.root, height=10)
        self.text.pack(pady=5)

    @staticmethod
    def tip_show(msg):
        messagebox.showinfo('提示', msg)

    def append_log(self, msg):
        self.root.after(0, lambda: self.text.insert('end', msg + '\n'))

    def update_progress(self, percent):
        self.root.after(0, lambda: self.progress_bar.config(value=percent))

    def end_update(self):
        def close():
            self.progress_bar.stop()
            self.tip_show('软件更新完成')
            self.root.destroy()
        self.root.after(0, close)

    @staticmethod
    def list_files_in_directory(directory_path):
        file_list = []
        for root, dirs, files in os.walk(directory_path):
            for file in files:
                file_list.append({'root': root, 'file': file})
        return file_list

    @staticmethod
    def set_executable_permission(file_path):
        if platform.system().lower() == 'darwin':
            st = os.stat(file_path)
            os.chmod(file_path, st.st_mode | stat.S_IEXEC)

    def soft_upgrade_with_thread(self):
        self.progress_var.set(0)
        self.progress_bar.start(10)
        Thread(target=self._soft_upgrade, daemon=True).start()

    def _soft_upgrade(self):
        self.label_var.set(0.0)
        extract_folder = os.path.dirname(self.zip_name)
        upgrade_log = os.path.join(extract_folder, 'upgrade.log')
        try:
            if os.path.exists(upgrade_log):
                os.remove(upgrade_log)
        except Exception:
            pass

        try:
            with zipfile.ZipFile(self.zip_name, 'r') as zip_ref:
                zip_ref.extractall(extract_folder)
        except Exception as e:
            self.append_log(f"解压失败: {e}")
            self.tip_show(f"升级失败：解压失败\n{e}")
            return

        self.target = os.path.dirname(self.target)
        source_folder = os.path.join(extract_folder, 'adbtool')

        file_list = self.list_files_in_directory(source_folder)
        total_files = len(file_list)

        with open(upgrade_log, 'a+', encoding="utf-8") as f:
            f.write(f'源文件目录：{source_folder}\n')
            f.write(f'目标文件目录：{self.target}\n')

        for index, file_info in enumerate(file_list):
            root = file_info['root']
            filename = file_info['file']
            source_path = os.path.join(root, filename)
            target_path = source_path.replace(source_folder, self.target)

            log_line = f'正在更新：{target_path}'
            self.append_log(log_line)
            with open(upgrade_log, 'a+', encoding="utf-8") as f:
                f.write(log_line + '\n')

            try:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                shutil.copyfile(source_path, target_path)
                self.set_executable_permission(target_path)
            except Exception as e:
                err_line = f'文件替换错误：{e}'
                self.append_log(err_line)
                with open(upgrade_log, 'a+', encoding="utf-8") as f:
                    f.write(f'更新异常：{e}\n')

            percent = round((index + 1) * 100.0 / total_files, 2)
            self.update_progress(percent)

        # 删除临时文件
        try:
            os.remove(self.zip_name)
        except Exception as e:
            self.append_log(f"无法删除zip包：{e}")
        try:
            shutil.rmtree(source_folder)
        except Exception as e:
            self.append_log(f"无法删除临时目录：{e}")

        self.end_update()

    def check_running_path(self):
        """
        macOS下检测程序是否运行于只读挂载卷（如DMG中的 /Volumes/ 路径）
        如果是，弹窗提示用户复制到 /Applications 后再运行，退出程序。
        """
        if platform.system().lower() == 'darwin':
            # 取执行文件绝对路径
            executable_path = os.path.abspath(sys.argv[0])
            if executable_path.startswith('/Volumes/'):
                # 弹窗提示
                root = Tk()
                root.withdraw()  # 隐藏主窗口
                messagebox.showerror(
                    "运行路径错误",
                    f"当前程序运行于只读磁盘映像（DMG）中。\n请将程序拖动到“/Applications”文件夹或其他可写目录后再运行。\n下载路径：http://{server_ip}/apk/adbtool.dmg"
                )
                root.destroy()
                sys.exit(1)


def upgrade_main():
    if len(sys.argv) < 3:
        print("用法: python upgrade.py <zip路径> <目标路径>")
        return

    filename, target = sys.argv[1], sys.argv[2]
    upgrade = SoftUpgrade(filename, target)

    # 检测运行路径，防止 dmg 只读导致更新失败
    upgrade.check_running_path()

    app = Tk()
    upgrade.init_ui(root=app)
    upgrade.soft_upgrade_with_thread()
    app.mainloop()


if __name__ == '__main__':
    upgrade_main()

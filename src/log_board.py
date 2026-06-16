import time
import tkinter as tk
from collections import deque
import threading
import subprocess
import re
import random


class HighPerfLogDisplay(tk.Toplevel):
    def __init__(self, master=None, device_id=None):
        super().__init__(master)
        self.title("High Performance Log Viewer")
        self.geometry("1100x750")

        self.device_id = device_id
        self.proc = None
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        # ===== 高性能核心 =====
        self.buffer = deque(maxlen=5000)
        self.queue = deque()

        # ===== 状态 =====
        self.running = True
        self.paused = False
        self.auto_scroll = tk.BooleanVar(value=True)

        # ===== 过滤 =====
        self.filter_var = tk.StringVar()
        self.regex_var = tk.BooleanVar()
        self.case_var = tk.BooleanVar(value=False)  # 新增：大小写匹配
        self.pkg_var = tk.StringVar()

        # ===== 等级过滤 =====
        self.level_vars = {
            "V": tk.BooleanVar(value=True),
            "D": tk.BooleanVar(value=True),
            "I": tk.BooleanVar(value=True),
            "W": tk.BooleanVar(value=True),
            "E": tk.BooleanVar(value=True),
        }

        # ===== 高亮 =====
        self.highlight_input = tk.StringVar()
        self.highlight_keywords = []

        self.total_lines = 0

        self._build_ui()
        self._start_thread()
        self._schedule_update()

    # ================= UI =================
    def _build_ui(self):
        # ===== 工具栏 =====
        top = tk.Frame(self)
        top.pack(fill=tk.X, padx=5, pady=5)

        tk.Label(top, text="过滤:").pack(side=tk.LEFT)
        tk.Entry(top, textvariable=self.filter_var, width=20).pack(side=tk.LEFT)

        tk.Checkbutton(top, text="正则", variable=self.regex_var).pack(side=tk.LEFT)
        tk.Checkbutton(top, text="大小写匹配", variable=self.case_var).pack(side=tk.LEFT)  # 新增

        tk.Button(top, text="应用", command=self._apply_filter).pack(side=tk.LEFT)
        tk.Button(top, text="清空", command=self._clear_filter).pack(side=tk.LEFT)

        tk.Label(top, text="包名:").pack(side=tk.LEFT, padx=10)
        tk.Entry(top, textvariable=self.pkg_var, width=20).pack(side=tk.LEFT)

        # 等级过滤
        for lvl in ["V", "D", "I", "W", "E"]:
            tk.Checkbutton(top, text=lvl, variable=self.level_vars[lvl]).pack(side=tk.LEFT)

        tk.Button(top, text="暂停", command=self.pause).pack(side=tk.LEFT, padx=5)
        tk.Button(top, text="继续", command=self.resume).pack(side=tk.LEFT)

        tk.Button(top, text="清空日志", command=self.clear_log).pack(side=tk.LEFT, padx=5)

        tk.Checkbutton(top, text="自动滚动", variable=self.auto_scroll).pack(side=tk.LEFT)

        # ===== 高亮 =====
        hl_frame = tk.Frame(self)
        hl_frame.pack(fill=tk.X, padx=5)

        tk.Label(hl_frame, text="高亮:").pack(side=tk.LEFT)
        tk.Entry(hl_frame, textvariable=self.highlight_input, width=20).pack(side=tk.LEFT)
        tk.Button(hl_frame, text="添加", command=self._add_highlight).pack(side=tk.LEFT)
        tk.Button(hl_frame, text="清空", command=self._clear_highlight).pack(side=tk.LEFT, padx=5)  # 新增清空按钮

        self.hl_container = tk.Frame(hl_frame)
        self.hl_container.pack(side=tk.LEFT, padx=10)

        # ===== 日志区 =====
        frame = tk.Frame(self)
        frame.pack(fill=tk.BOTH, expand=True)

        # ✅ 自动换行
        self.text = tk.Text(frame, wrap="word")
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        scroll = tk.Scrollbar(frame, command=self.text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.text.config(yscrollcommand=scroll.set)

        # ===== 状态栏 =====
        self.status = tk.Label(self, text="Ready", anchor="w")
        self.status.pack(fill=tk.X)

    # ================= 日志线程 =================
    def _start_thread(self):
        def run():
            while self.running:
                try:
                    cmd = ["adb"]
                    if self.device_id:
                        cmd += ["-s", self.device_id]
                    cmd += ["logcat", "-v", "threadtime"]

                    self.proc = subprocess.Popen(
                        cmd,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE
                    )

                    while self.running:
                        raw = self.proc.stdout.readline()
                        if raw == b'':
                            raise Exception("logcat disconnected")

                        line = raw.decode("utf-8", errors="ignore")
                        self.queue.append(line)

                except Exception as e:
                    if not self.running:
                        return
                    print("logcat异常，准备重连:", e)
                    for _ in range(20):
                        if not self.running:
                            return
                        time.sleep(0.1)
                finally:
                    if self.proc:
                        try:
                            self.proc.kill()
                        except:
                            pass
                        self.proc = None

        threading.Thread(target=run, daemon=True).start()

    # ================= UI调度 =================
    def _schedule_update(self):
        if not self.paused:
            self._flush_logs()
        self.after(100, self._schedule_update)

    def _flush_logs(self):
        if not self.queue:
            return

        batch = []

        for _ in range(min(len(self.queue), 300)):
            line = self.queue.popleft()
            self.total_lines += 1

            if self._filter(line):
                self.buffer.append(line)
                batch.append(line)

        if not batch:
            return

        start_index = self.text.index("end-1c")
        self.text.insert("end", "".join(batch))

        self._apply_highlight(batch, start_index)

        if len(self.buffer) >= self.buffer.maxlen:
            self.text.delete("1.0", "200.0")

        if self.auto_scroll.get():
            self.text.see("end")

        self.status.config(text=f"总日志: {self.total_lines} | 当前显示: {len(self.buffer)}")

    # ================= 过滤 =================
    def _filter(self, line):
        pkg = self.pkg_var.get().strip()
        if pkg and pkg not in line:
            return False

        m = re.search(r"\s([VDIWE])\s", line)
        if m and not self.level_vars[m.group(1)].get():
            return False

        keyword = self.filter_var.get().strip()
        if keyword:
            flags = 0 if self.case_var.get() else re.IGNORECASE
            if self.regex_var.get():
                if not re.search(keyword, line, flags):
                    return False
            else:
                if self.case_var.get():
                    if keyword not in line:
                        return False
                else:
                    if keyword.lower() not in line.lower():
                        return False

        return True

    # ================= 高亮 =================
    def _apply_highlight(self, batch, start_index):
        base_line = int(start_index.split(".")[0])

        for i, line in enumerate(batch):
            for kw, color in self.highlight_keywords:
                for match in re.finditer(kw, line):
                    start = f"{base_line + i}.{match.start()}"
                    end = f"{base_line + i}.{match.end()}"
                    self.text.tag_add(kw, start, end)
                    self.text.tag_config(
                        kw,
                        foreground="white",
                        background=color,
                        font=("Consolas", 10, "bold")
                    )

    def _add_highlight(self):
        kw = self.highlight_input.get().strip()
        if not kw:
            return

        color = random.choice(["red", "orange", "blue", "green", "purple"])
        self.highlight_keywords.append((kw, color))

        lbl = tk.Label(self.hl_container, text=kw, fg=color)
        lbl.pack(side=tk.LEFT, padx=2)

        self.highlight_input.set("")

    # ================= 新增：清空高亮 =================
    def _clear_highlight(self):
        # 清空关键字列表
        self.highlight_keywords.clear()
        # 删除 UI 中的所有标签
        for widget in self.hl_container.winfo_children():
            widget.destroy()
        # 清除 Text 中所有高亮标签
        for tag in self.text.tag_names():
            self.text.tag_delete(tag)

    # ================= 控制 =================
    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def clear_log(self):
        self.text.delete("1.0", "end")
        self.buffer.clear()

    def _apply_filter(self):
        self.clear_log()

    def _clear_filter(self):
        self.filter_var.set("")
        self.regex_var.set(False)
        self.case_var.set(False)  # 重置大小写匹配
        self._apply_filter()

    def on_close(self):
        print("关闭日志窗口...")

        self.running = False
        self.paused = True

        # 关闭 adb 进程
        if self.proc:
            try:
                self.proc.kill()
            except:
                pass
            self.proc = None

        # 清空队列（防止UI继续刷新）
        self.queue.clear()

        # 销毁窗口
        self.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()

    win = HighPerfLogDisplay(root,'MAX0019071000087')
    root.mainloop()
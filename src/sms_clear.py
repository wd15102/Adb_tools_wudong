import os
import json
import requests
import tkinter as tk
from config import root_path
from tkinter import ttk, messagebox

from src.utils import Utils


class SmsClear(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("短信限制")
        self.geometry("560x300")
        self.resizable(False, False)
        self.iconbitmap(os.path.join(root_path, 'tools', 'favicon_new.ico'))

        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        # -------------------
        # 1. 手机号码输入框
        # -------------------
        tk.Label(self, text="手机号码：").grid(row=0, column=0, padx=(20, 5), pady=10, sticky="e")
        self.phone_number = tk.Entry(self, width=60)
        self.phone_number.grid(row=0, column=1, columnspan=8, padx=5, pady=10, sticky="w")

        # -------------------
        # 2. 环境下拉框
        # -------------------
        tk.Label(self, text="所属环境：").grid(row=1, column=0, padx=(20, 5), pady=10, sticky="e")
        self.evn_var = tk.StringVar(value="正式环境")
        self.protocol_combo = ttk.Combobox(
            self, textvariable=self.evn_var,
            values=["正式环境", "测试环境"],
            state="readonly", width=10
        )
        self.protocol_combo.grid(row=1, column=1, padx=5, pady=10, sticky="w")

        tk.Label(self, text="测试环境需开启VPN，正式环境勿开启系统代理").grid(row=1, column=2, columnspan=10, pady=(10, 5))

        # -------------------
        # 3. 发送按钮
        # -------------------
        self.send_button = tk.Button(
            self, text="发送请求", command=self.on_send_click,
            state="normal", width=12
        )
        self.send_button.grid(row=2, column=0, columnspan=10, pady=(10, 5))

        # -------------------
        # 5. 输出文本框
        # -------------------
        tk.Label(self, text="执行结果：").grid(row=3, column=0, padx=(20, 5), pady=(5, 0), sticky="ne")

        text_frame = tk.Frame(self)
        text_frame.grid(row=3, column=1, columnspan=8, padx=5, pady=(5, 10), sticky="nsew")

        self.text = tk.Text(text_frame, width=60, height=8, wrap="word")
        self.text.pack(side="left", fill="both", expand=True)

        scroll = tk.Scrollbar(text_frame, command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.config(yscrollcommand=scroll.set)

    # -------------------
    # 发送逻辑
    # -------------------
    def on_send_click(self):
        """点击发送按钮"""
        phone_number = f"""{self.phone_number.get().strip()}"""
        if not phone_number:
            messagebox.showwarning("提示", "请填写手机号码")
            return

        env_var = self.evn_var.get()

        try:
            if env_var == '测试环境':
                url = f'http://10.200.20.42:9221/captcha/clear?appid=aaa&mobile={phone_number}'
                response = requests.get(url=url)
            else:
                utils = Utils()
                utils.host_map = {"sms.ng.imgo.tv": "10.100.4.109"}
                utils.dns_enable()
                url = f'http://sms.ng.imgo.tv/captcha/clear?appid=aaa&operation=&mobile={phone_number}'
                response = requests.get(url=url)
                utils.dns_enable()
            data = response.json()

            # 输出结果到 Text
            self.text.insert("insert", json.dumps(data, indent=4, ensure_ascii=False) + "\n\n")
            self.text.see("end")
        except Exception as e:
            self.text.insert("insert", str(e) + "\n\n")



# -------------------
# 示例使用
# -------------------
if __name__ == "__main__":
    root = tk.Tk()
    root.withdraw()
    SmsClear(root)
    root.mainloop()

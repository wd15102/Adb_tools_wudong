import os
import json
import tkinter as tk
from config import root_path
from tkinter import ttk, messagebox


class CurlRequest(tk.Toplevel):
    def __init__(self, master, send_callback):
        super().__init__(master)
        self.title("Curl 请求窗口")
        self.geometry("560x400")
        self.resizable(False, False)
        self.send_callback = send_callback
        self.iconbitmap(os.path.join(root_path, 'tools', 'favicon_new.ico'))

        # 居中显示
        self.update_idletasks()
        x = (self.winfo_screenwidth() - self.winfo_width()) // 2
        y = (self.winfo_screenheight() - self.winfo_height()) // 2
        self.geometry(f"+{x}+{y}")

        # -------------------
        # 1. Curl 命令输入框
        # -------------------
        tk.Label(self, text="Curl 命令：").grid(row=0, column=0, padx=(20, 5), pady=10, sticky="e")
        self.curl_entry = tk.Entry(self, width=60)
        self.curl_entry.grid(row=0, column=1, columnspan=8, padx=5, pady=10, sticky="w")

        # -------------------
        # 2. 协议下拉框
        # -------------------
        tk.Label(self, text="协议类型：").grid(row=1, column=0, padx=(20, 5), pady=10, sticky="e")
        self.protocol_var = tk.StringVar(value="HTTP")
        self.protocol_combo = ttk.Combobox(
            self, textvariable=self.protocol_var,
            values=["HTTP", "HTTPS"],
            state="readonly", width=10
        )
        self.protocol_combo.grid(row=1, column=1, padx=5, pady=10, sticky="w")

        # -------------------
        # 3. IP + 端口输入框（统一间距）
        # -------------------
        tk.Label(self, text="代理地址：").grid(row=2, column=0, padx=(20, 5), pady=10, sticky="e")

        self.ip_vars = [tk.StringVar() for _ in range(4)]
        self.port_var = tk.StringVar()

        frame = tk.Frame(self)
        frame.grid(row=2, column=1, columnspan=8, sticky="w", padx=5)

        for i in range(4):
            ip_entry = tk.Entry(frame, textvariable=self.ip_vars[i], width=9, justify="center")
            ip_entry.pack(side="left", padx=(0 if i == 0 else 5))
            if i < 3:
                tk.Label(frame, text=".").pack(side="left", padx=(1, 4))

        tk.Label(frame, text=":").pack(side="left", padx=(2, 4))
        self.port_entry = tk.Entry(frame, textvariable=self.port_var, width=9, justify="center")
        self.port_entry.pack(side="left")

        # 输入校验
        for var in self.ip_vars + [self.port_var]:
            var.trace_add("write", self.validate_inputs)

        # -------------------
        # 4. 发送按钮
        # -------------------
        self.send_button = tk.Button(
            self, text="发送请求", command=self.on_send_click,
            state="normal", width=12
        )
        self.send_button.grid(row=3, column=0, columnspan=10, pady=(10, 5))

        # -------------------
        # 5. 输出文本框
        # -------------------
        tk.Label(self, text="执行结果：").grid(row=4, column=0, padx=(20, 5), pady=(5, 0), sticky="ne")

        text_frame = tk.Frame(self)
        text_frame.grid(row=4, column=1, columnspan=8, padx=5, pady=(5, 10), sticky="nsew")

        self.text = tk.Text(text_frame, width=60, height=8, wrap="word")
        self.text.pack(side="left", fill="both", expand=True)

        scroll = tk.Scrollbar(text_frame, command=self.text.yview)
        scroll.pack(side="right", fill="y")
        self.text.config(yscrollcommand=scroll.set)

    # -------------------
    # 输入验证逻辑
    # -------------------
    def validate_inputs(self, *args):
        """输入校验：只有全空或全填时，发送按钮才可用"""
        values = [var.get().strip() for var in self.ip_vars + [self.port_var]]

        all_empty = all(v == "" for v in values)
        all_filled = all(v != "" for v in values)

        if all_empty or all_filled:
            self.send_button.config(state="normal")
        else:
            self.send_button.config(state="disabled")

    # -------------------
    # 发送逻辑
    # -------------------
    def on_send_click(self):
        """点击发送按钮"""
        curl_command = f"""{self.curl_entry.get().strip()}"""
        if not curl_command:
            messagebox.showwarning("提示", "请填写 Curl 命令")
            return

        ip_parts = [v.get().strip() for v in self.ip_vars]
        if not any(ip_parts):
            full_ip = None
        else:
            port = self.port_var.get().strip()
            full_ip = ".".join(ip_parts) + ":" + port

        f_http = self.protocol_var.get() == "HTTP"

        try:
            response = self.send_callback(curl_command, replace_params=None, f_http=f_http, proxy=full_ip)
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
    def send_request(curl_command, replace_params=None, f_http=True, proxy=None):
        print("Curl:", curl_command)
        print("HTTP:", f_http)
        print("Proxy:", proxy)

        # 模拟返回结果
        class DummyResponse:
            def json(self):
                return {"status": "ok", "msg": "测试响应"}
        return DummyResponse()

    root = tk.Tk()
    root.withdraw()
    CurlRequest(root, send_request)
    root.mainloop()

#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import json
import uvicorn
import threading
from fastapi import FastAPI, Body
from urllib.parse import unquote_plus
from config import root_path

app = FastAPI()

@app.post("/")
async def handle_root_post(body: bytes = Body(...)):
    try:
        body_str = body.decode('utf-8', errors='replace')
        if body_str.startswith('data='):
            encoded = body_str[len('data='):]
            decoded = unquote_plus(encoded)  # 解码 URL
            # print(decoded)
            field_dict = json.loads(decoded)
            event_name = field_dict.get('$event_name')
            if event_name == 'flow':
                print(json.dumps(field_dict, indent=4, ensure_ascii=False))
            return {"status": "ok"}
        else:
            return {"status": "ignored", "reason": "no data param"}
    except Exception as e:
        return {"status": "error", "msg": str(e)}

def run_http():
    uvicorn.run(app=app, host='0.0.0.0', port=80, log_level="warning")

def run_https():
    ssl_key = os.path.join(root_path, 'tools', 'localhost.key')
    ssl_cert = os.path.join(root_path, 'tools', 'localhost.crt')  # 推荐用 .crt 或 .pem
    if os.path.exists(ssl_key) and os.path.exists(ssl_cert):
        uvicorn.run(app=app, host='0.0.0.0', port=443, ssl_keyfile=ssl_key, ssl_certfile=ssl_cert, log_level="warning")
    else:
        print("SSL 文件不存在，跳过 HTTPS")

def api_start():
    threading.Thread(target=run_http, daemon=True).start()
    threading.Thread(target=run_https, daemon=True).start()

if __name__ == '__main__':
    api_start()
    import time
    while True:
        time.sleep(10)

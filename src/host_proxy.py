import os
import gzip
import urllib3
import uvicorn
import logging
import requests
import threading
from fastapi import FastAPI, Response, Request
from config import root_path

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
logging.basicConfig(level=logging.INFO)
app = FastAPI()


async def interceptor(request: Request, call_next, proxy):
    # 获取请求的原始数据
    method = request.method
    url = str(request.url)
    headers = dict(request.headers)
    body = await request.body()

    proxies = {f"http": f"http://{proxy}", "https": f"http://{proxy}"}

    with requests.Session() as session:
        session.verify = False
        response = session.request(method, url, headers=headers, data=body, proxies=proxies)

    # 检查原始响应是否使用gzip压缩
    if 'Content-Encoding' in response.headers and response.headers['Content-Encoding'] == 'gzip':
        # 如果是，那么对响应数据进行gzip压缩
        gzip_content = gzip.compress(response.content)
        return Response(content=gzip_content, status_code=response.status_code, headers=response.headers)
    else:
        # 如果不是，那么直接返回响应数据
        return Response(content=response.content, status_code=response.status_code, headers=response.headers)


def run_app(port: int, proxy: str, ssl_key=None, ssl_cert=None):
    app.middleware('http')(lambda request, call_next: interceptor(request, call_next, proxy))
    cfg = uvicorn.Config(app, host="0.0.0.0", port=port, ssl_keyfile=ssl_key, ssl_certfile=ssl_cert)
    server = uvicorn.Server(cfg)
    server.run()


def start_processes(ip_port):
    http_thread = threading.Thread(target=run_app, args=(80, ip_port))
    http_thread.setDaemon(True)
    http_thread.start()
    ssl_key = os.path.join(root_path, 'tools', 'localhost.key')
    ssl_cert = os.path.join(root_path, 'tools', '1935964a.0')
    https_thread = threading.Thread(target=run_app, args=(443, ip_port, ssl_key, ssl_cert))
    https_thread.setDaemon(True)
    https_thread.start()


if __name__ == '__main__':
    start_processes('172.31.28.88:8888')
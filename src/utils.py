#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import time
import config
import platform
import requests
import shlex
import socket
import mysql.connector
from src.log import logger

class Utils:
    def __init__(self):
        self.host_map = None
        self._original_getaddrinfo = None

    @staticmethod
    def get_current_underline_time():
        """
        文件存储时使用
        :return:
        """
        return time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())

    @staticmethod
    def get_current_time():
        """
        数据采集时时间记录
        :return:
        """
        return time.strftime('%Y-%m-%d %H-%M-%S', time.localtime())

    @staticmethod
    def get_format_time(timestamp):
        """
        时间戳格式化
        :param timestamp:
        :return:
        """
        return time.strftime('%Y-%m-%d %H-%M-%S', time.localtime(timestamp))

    @staticmethod
    def get_current_ms_time():
        """
        monkey日志时间记录
        :return:
        """
        ct = time.time()
        ms = (ct - int(ct)) * 1000
        data_head = time.strftime('%m-%d %H:%M:%S', time.localtime())
        time_stamp = "%s.%03d" % (data_head, ms)
        return time_stamp

    @staticmethod
    def get_current_underline_ms_time():
        """
        文件存储时使用
        :return:
        """
        ct = time.time()
        ms = (ct - int(ct)) * 1000
        data_head = time.strftime('%Y_%m_%d_%H_%M_%S', time.localtime())
        time_stamp = "%s_%03d" % (data_head, ms)
        return time_stamp

    @staticmethod
    def get_time_stamp(time_str, format_str):
        """
        字符转换成时间戳
        :param time_str:
        :param format_str:
        :return:
        """
        time_array = time.strptime(time_str, format_str)
        return time.mktime(time_array)

    @staticmethod
    def get_root_dir():
        """
        获取项目根路径
        :return:
        """
        src_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(src_dir)
        return root_dir

    @staticmethod
    def creat_folder(folder):
        """
        目录不存在时创建目录
        :param folder:
        :return:
        """
        if not os.path.exists(folder):
            os.makedirs(folder)

    @staticmethod
    def get_file_size(path, mb=True):
        size = os.path.getsize(path)
        if mb:
            size = size / float(1024 * 1024)
            return round(size, 2)
        else:
            return size

    @staticmethod
    def get_os_platform():
        """
        获取操作系统平台
        :return:
        """
        os_platform = platform.system()
        return os_platform

    @staticmethod
    def insert_data(query, data):
        # 数据库连接配置
        if config.db_var == '否':
            return

        conn = None
        cursor = None

        try:
            conn = mysql.connector.connect(**config.db_config)
            cursor = conn.cursor()

            cursor.execute(query, data)
            conn.commit()

        except Exception as e:
            logger.debug(f'insert data error, query: {query}, data: {data}, error: {e}')

        finally:
            if conn is not None and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def query_data(query, data):
        # 数据库连接配置
        conn = None
        cursor = None

        try:
            conn = mysql.connector.connect(**config.db_config)
            cursor = conn.cursor()

            # 插入数据
            #
            cursor.execute(query, data)
            result = cursor.fetchall()
            return result
        except Exception as e:
            logger.debug(f'query data error, query: {query}, data: {data}, error: {e}')
        finally:
            if conn is not None and conn.is_connected():
                cursor.close()
                conn.close()

    @staticmethod
    def upload_file(data, field_path):
        url = f"{config.web}/performance-report/upload"
        with open(field_path, 'rb') as file:
            files = {'file': (field_path, file)}
            response = requests.post(url, files=files, data=data)
            print(response.json())

    @staticmethod
    def parse_params(params_str):
        """
        将类似 'app_type=1&auth_mode=1' 格式的字符串转换为字典。
        """
        params_str = params_str.strip()
        params_dict = {}
        pairs = params_str.split('&')
        for pair in pairs:
            if '=' in pair:
                key, value = pair.split('=', 1)
                params_dict[key] = value
            else:
                params_dict[pair] = ''
        return params_dict

    @staticmethod
    def parse_curl(curl_command, f_http=True):
        """
        解析 curl 命令并提取 URL、headers 和 params/data。
        """
        tokens = shlex.split(curl_command)

        url = ''
        headers = {}
        params = {}
        data = None
        method = 'GET'

        i = 0
        while i < len(tokens):
            if tokens[i] == 'curl':
                i += 1
                continue
            elif tokens[i].startswith('http'):
                url = tokens[i]
                if '?' in url:
                    url, query_string = url.split('?', 1)
                    params = dict(param.split('=') for param in query_string.split('&'))
                if f_http:
                    url = url.replace('https', 'http')
            elif tokens[i] == '-H':
                header_key, header_value = tokens[i + 1].split(': ', 1)
                headers[header_key] = header_value
                i += 1
            elif tokens[i] == '--data' or tokens[i] == '--data-binary':
                data = tokens[i + 1]
                method = 'POST'
                i += 1
            elif tokens[i] == '-X':
                method = tokens[i + 1]
                i += 1
            i += 1

        return url, headers, params, data, method

    def send_request(self, curl_command, replace_params=None, f_http=True, proxy=None):
        """
        解析 curl 命令，并通过 requests 发送请求，同时支持替换参数。
        """
        url, headers, params, data, method = self.parse_curl(curl_command, f_http)
        if replace_params:
            replace_params = self.parse_params(replace_params)

        # 替换参数
        if replace_params:
            for key, value in replace_params.items():
                if data and key in data:
                    data_dict = self.parse_params(data)
                    data_dict[key] = value
                    data = '&'.join(f'{k}={v}' for k, v in data_dict.items())
                elif key in params:
                    params[key] = value

        # 构造代理字典
        proxies = None
        if proxy:
            proxies = {
                "http": f"http://{proxy}",
                "https": f"http://{proxy}",  # 注意：即使是 HTTPS，这里仍然通常使用 http:// 前缀
            }

        # 发送请求
        if method == 'POST':
            response = requests.post(url, headers=headers, data=data, proxies=proxies, timeout=10, verify=False)
        else:
            response = requests.get(url, headers=headers, params=params, proxies=proxies, timeout=10, verify=False)
        return response

    def _patched_getaddrinfo(self, *args, **kwargs):
        """自定义 DNS 解析逻辑"""
        host = args[0]
        if host in self.host_map:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (self.host_map[host], args[1]))]
        return self._original_getaddrinfo(*args, **kwargs)

    def dns_enable(self):
        """启用 DNS 替换"""
        if self._original_getaddrinfo is None:
            self._original_getaddrinfo = socket.getaddrinfo
            socket.getaddrinfo = self._patched_getaddrinfo

    def dns_disable(self):
        """恢复原始 DNS"""
        if self._original_getaddrinfo is not None:
            socket.getaddrinfo = self._original_getaddrinfo
            self._original_getaddrinfo = None

    def __enter__(self):
        """支持 with 语法"""
        self.dns_enable()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """离开 with 块时自动恢复"""
        self.dns_disable()

if __name__ == '__main__':
    query = f"update version set package_size=%s,sdcard_size=%s,data_size=%s,media_size=%s ,monkey=%s ,monkey_cmd=%s where task_id=%s"
    data = 321, 321, 321, 321, 'script', '321','2026_02_05_17_37_21_069',
    Utils.insert_data(query, data)
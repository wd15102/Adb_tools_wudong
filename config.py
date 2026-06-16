#!/usr/bin/env python
# -*- coding: utf-8 -*-
import os
import json
import requests

root_path = os.path.dirname(__file__)
root_disable = ['Android8.1.0.tv53', 'Q601A', 'M321', 'BA002', 'R2011']
package = 'com.mgtv.tv'
devices = ''
monkey = 'monkey'
monkey_cmd = ''
main_activity = []
activity_list = []
black_activity_list = []
black_list_key = 4
timeout = 12
frequency = 10
dumpheap_freq = 2
error_log = ['ANR in', 'MgtvCrash', 'onPlayerError']
devices_log_path = ['/data/anr']
save_path = None
report_path = None
mail = ['chengyuan@mgtv.com']
log_text = None
task_stop = False
cpu_var = mem_var = thr_var = fd_var = 1
fps_var = mem_top_var = 0
fd_stop_var = '否'
db_var = '是'
server_ip = '172.31.111.166'
db_config = {
    "user": "autotest",
    "password": "!@#123qwe",
    "host": "172.31.111.86",
    "database": "devices"
}
web = 'http://172.31.111.86:9090/'

try:
    res = requests.get(f'http://{server_ip}/db.json', timeout=1)
    if res.status_code == 200:
        text = res.text
        cfg_obj = json.loads(text)
        db_config = cfg_obj.get('db')
        web = cfg_obj.get('web')

except Exception as e:
    print(e)
    pass


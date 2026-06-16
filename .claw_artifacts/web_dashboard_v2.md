# Web 仪表盘 - 第二轮修复 & 功能增强

## 修复：ADB 命令中的 grep 在 Windows 下报错

### 问题
`adb shell dumpsys window | grep mCurrentFocus` 在 Windows 上本地 shell 试图调用 `grep`，但 Windows 没有 grep 命令，报 `'grep' 不是内部或外部命令`。

### 根因
`adbtools.py` 第 136 行：
```python
cmd_str = cmd_str.replace('|grep', '|findstr')
```
只匹配 `|grep`（无空格），但实际 `| grep` 中间有空格，替换失效。

### 修复点
1. **`src/adbtools.py`**：`replace('| grep', '| findstr')`  增加带空格匹配
2. **`src/web_dashboard/collector.py`**：
   - `_detect_current_package()` 改为不依赖 shell pipe，直接 Python 解析 `dumpsys window windows` 输出
   - `_collect_device_info()` 去掉 `| grep -E`，改用 Python 循环搜索

## 新功能：进程列表面板

### 后端（collector.py + server.py）
- `DashboardCollector.get_process_list()` — 通过 `ps -ef` 解析进程列表，回退到 `pm list packages -3`
- `GET /api/processes` — 新增 REST API 端点

### 前端（index.html）
- 进程列表面板显示位置：状态栏上方
- 搜索过滤（实时按包名搜索）
- 点击进程按钮 → 自动切换监控到该进程（调 settings 设置包名 → 停止 → 启动）
- 当前监控进程高亮（active 样式）
- 启动采集后自动加载进程列表，停止后自动隐藏

## 设备自动检测修复

### 问题
Web 仪表盘启动采集时，`device_id=None` 且 `self.device=None`，`_run_loop` 直接访问 `self.device.adb.get_online_device()` 报 `AttributeError: 'NoneType' object has no attribute 'adb'`

### 修复
三步初始化法：
1. 先创建临时 `AdbUtils(None)`/`ADB(None)` 获取在线设备列表
2. 找到设备后初始化 `self.device`
3. 分步检查，每步失败有明确的 error_msg

## 验证
- ✅ 所有 Python 模块语法检查通过
- ✅ 导入链完整（collector / server）
- ✅ Flask 路由全部正常注册，含 `/api/processes`

## 修改文件清单
- `src/adbtools.py` — grep→findstr 空格修复
- `src/web_dashboard/collector.py` — 去 pipe + 进程列表 + 设备检测修复
- `src/web_dashboard/server.py` — 新增 `/api/processes`
- `src/web_dashboard/templates/index.html` — 进程列表面板 + JS 交互

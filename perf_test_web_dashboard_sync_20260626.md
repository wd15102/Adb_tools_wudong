# perf_test 与 Web Dashboard 联动改造 + 报告导出

## 目标

在 GUI 设置 12 小时性能测试后，测试结束时同时停止 Web Dashboard 采集、数据保存至数据库、并自动导出可读测试报告。

## 改动清单

### 1. `src/perf_test.py` — main() 超时 bug 修复 + Web Dashboard 联动

**bug 修复**：原代码 `end_time = time.time() + timeout` 中 `config.timeout` 单位是 **小时**，但直接当 **秒** 加上去，导致外层循环仅运行 timeout 秒就退出。修复后将外层循环改为轮询检测所有 perf_thread 是否存活，超时控制已下放到 `StartUp.run()` 内部（那里正确使用 `self.timeout = config.timeout * 3600`）。

**新增 `_web_dashboard_start()`**：在启动 perf 线程后，通过 HTTP POST `/api/start` 同步启动 Web Dashboard 采集器。静默处理服务器未启动的情况。

**新增 `_web_dashboard_stop()`**：在 main() 等待所有 perf 线程退出后，通过 HTTP POST `/api/stop` 同步停止 Web Dashboard 采集器。

**新增 `_web_dashboard_export_report(save_dir)`**：
- 停止采集后自动拉取最新任务的 CSV 压缩包和 Markdown 报告
- 保存到 `results/{package}/web_dashboard_report_task{N}.zip`
- 同时解压出 `report.md` 到同目录方便预览
- 服务器未运行时静默跳过

### 2. `src/web_dashboard/server.py` — 新增 `/api/task/<id>/export` 导出端点

返回一个 ZIP 压缩包，包含：
- `task_info.csv` — 任务元信息
- `cpu_data.csv` — CPU 采集数据
- `mem_data.csv` — 内存采集数据
- `fd_data.csv` — FD 采集数据
- `thread_data.csv` — 线程采集数据
- `fps_data.csv` — FPS 采集数据
- `crash_events.csv` — 崩溃事件
- `report.md` — Markdown 可读汇总报告（复用 `/api/task/<id>/report` 的统计逻辑）

已添加 `Response` 到 flask import。

### 3. 文件改动

| 文件 | 改动 |
|------|------|
| `src/perf_test.py` | 修复 main() 超时 bug；新增 `_web_dashboard_start/stop/export_report` 三个辅助函数；在 main() 中依次调用 |
| `src/web_dashboard/server.py` | 新增 `/api/task/<int:task_id>/export` 路由；flask import 增加 `Response` |

### 使用方式

1. 启动 AdbTool → 菜单中先启动「🥭 实时性能监控面板」→ 浏览器打开仪表盘 verify 运行正常
2. 点击「性能测试」菜单 → 设置执行时间(如 12 小时) → 确定
3. perf_test 自动同步启动/停止 Web Dashboard 采集器
4. 测试结束后，报告自动导出到 `results/<package>/web_dashboard_report_task<id>.zip`

### 验证

- `py_compile` 验证 perf_test.py 和 server.py 均无语法错误
- `/api/tasks` 返回值是 list（非 dict），已修正解析逻辑

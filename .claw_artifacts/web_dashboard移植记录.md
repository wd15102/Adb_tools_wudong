# Web 仪表盘移植完成记录

## 任务目标
将 wudong 项目的性能可视化功能移植到 AdbTool-maste，构建 Flask + SocketIO + ECharts Web 仪表盘。

## 创建的文件

| 文件 | 说明 |
|------|------|
| `src/web_dashboard/__init__.py` | 模块标识（空） |
| `src/web_dashboard/db.py` | SQLite 数据库层，支持任务创建/数据插入/历史查询 |
| `src/web_dashboard/collector.py` | 实时采集器，复用 AdbUtils 的 ADB shell 命令 |
| `src/web_dashboard/server.py` | Flask + SocketIO 服务器，REST API + WebSocket 推播 |
| `src/web_dashboard/templates/index.html` | ECharts 前端仪表盘（暗色主题，5 个图表面板） |

## 修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/gui.py` | 添加 `launch_dashboard` 方法，在性能测试菜单添加"🌐 Web仪表盘"入口 |

## 安装的依赖
- `flask-socketio` — WebSocket 实时通信
- `requests` — AdbTool 原有依赖
- `psutil` `py-cpuinfo` — AdbTool 原有依赖
- `mysql-connector-python` — AdbTool 原有依赖

## 架构说明

```
[Selenium/EDR 浏览器] ←→ [Flask + SocketIO] ←→ [DashboardCollector] → ADB Shell
                              ↕                          ↕
                        SQLite (perf_dashboard.db)     实时推送
```

- 采集器 `DashboardCollector` 使用延迟导入 `AdbUtils`，避免 AdbTool 的 `config.py` 模块级 HTTP 请求阻塞 Flask 启动
- WebSocket 推播实时数据（CPU/内存/FD/线程/FPS），5 个 ECharts 图表同时更新
- 支持历史任务回看：通过 REST API `/api/tasks`、`/api/task/<id>` 加载已完成的测试数据

## 已验证
- ✅ 所有 Python 模块语法检查通过
- ✅ 模块间 import OK（db / collector / server）
- ✅ Flask 服务器启动正常，全部 API 路由注册正确
- ✅ HTTP 端点（`/`、`/api/status`、`/api/tasks`）返回正确

## 端口 & 启动方式
- **默认端口**: 5050
- **GUI 启动**: 菜单栏 → 性能测试 → 🌐 Web仪表盘（自动打开浏览器）
- **命令行启动**: `python src/web_dashboard/server.py`
- **手动访问**: `http://localhost:5050`

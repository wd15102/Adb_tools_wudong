# Changelog

All notable changes to AdbTool will be documented in this file.

## [Unreleased] - 2026-08-14

### Added
- **抓包代理配置交互化**：启动抓包时弹窗让用户输入电脑 IP 和代理端口，不再硬编码 `192.168.100.6:8888`
- **端口占用检测**：启动前自动检查代理端口和 Web UI 端口（5051）是否被占用，给出明确提示
- **服务器启动验证**：等待启动后验证线程存活 + 端口监听，失败时输出错误信息
- **capture 模块包声明**：新增 `src/capture/__init__.py` 模块入口
- **gui_theme 废弃标记**：新增 `src/gui_theme.py` 标记已弃用的赛博朋克主题

### Changed
- **删除代理优化**：使用多条指令（`settings delete` + `settings put :0`）确保代理清除在所有平台生效
- **代理删除结果判定**：`:0`、`null`、空字符串均视为清除成功，提升兼容性
- **邮件地址更新**：通知邮箱从 `chengyuan@mgtv.com` 更新为 `wudong@mgtv.com`

### Fixed
- `capture_addon._decode_unicode_json` 文档字符串修复为 raw string（`r"""`），避免转义警告
- 服务器启动前增加端口可用性检查，防止启动后无声失败

## [1.0.0] - 2026-06-26

### Added
- **perf_test 与 Web Dashboard 联动**：性能数据实时推送到 Web 仪表盘，支持报告导出
- **Web 仪表盘崩溃监控**：实时展示设备崩溃日志和 ANR 信息
- **赛博朋克主题**：Web UI 深色赛博朋克风格主题
- **Windows ADB 兼容性**：移除所有 ADB shell 命令中的管道和重定向，修复 Windows 执行异常

### Initial Release
- AdbTool 机顶盒/大屏应用全功能自动化测试工具初始版本
- 功能涵盖：ADB 设备管理、性能监控、ANR/崩溃日志采集、抓包 & Mock、Web 仪表盘

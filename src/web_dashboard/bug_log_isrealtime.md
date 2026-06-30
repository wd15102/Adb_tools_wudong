# Bug: selectProcess 未设置 isRealtime

## 现象
采集器正常采集数据（CPU、内存、FD、线程均有读数），但前端曲线空白。

## 根因
`selectProcess` 函数调 `/api/start` 成功后将按钮改为「⏹ 停止」，
但**未设置 `isRealtime = true`**。

`socket.on('new_data', ...)` 的第一行守卫：
```javascript
if (!isRealtime) return; // ← isRealtime=false 时所有数据被静默丢弃
```
若用户之前点过停止按钮（`isRealtime = false`），
随后选择进程触发自动启动，数据永远不会进入渲染流程。

## 修复
- `selectProcess` 中 `/api/start` 成功后添加 `isRealtime = true`
- 同时重构为 `async/await` 链替代嵌套 `.then()`，增加错误处理

## 文件
`src/web_dashboard/templates/index.html` — `selectProcess()` 函数

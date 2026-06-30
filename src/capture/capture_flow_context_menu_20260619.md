# 抓包 UI 改进：右键菜单 + 响应体完整显示

## 改前问题
1. **响应体截断** — 超过 3000 字符以 `... (truncated)` 硬截断，无法看到完整数据
2. **左侧列表无右键菜单** — 无法快速复制 URL、cURL、响应体等，需逐条查看

## 改动内容

### 服务端 (capture_server.py)
1. **响应体截断策略改进**：不再直接截断，改为 `_preview`（前 3000 字符） + `_full`（完整 body 单独字段）+ `_truncated`/`_full_len` 标记，前端按需展开
2. **`/api/flows` 端点**：新增 `scheme`、`query` 字段，供右键菜单构造完整 URL
3. **WebSocket 广播**：同上新增 scheme/query 字段

### 前端 (capture.html)
1. **右键菜单** (Charles 风格)：
   - Copy URL — 从 allFlows 中取 scheme+host+path+query 拼完整 URL 复制到剪贴板
   - Copy cURL Request — 调 `/api/export/flow` 获取 curl 命令
   - Copy Response — 调 detail API 取完整响应体
   - Save Response... — 浏览器下载为 `.json` 文件
   - Find in Flows... — 将当前 flow 的 host 填入搜索框并自动搜索
   - Export Session (HAR) — 导出为 HAR v1.2 格式
2. **响应体「展开全部」按钮**：截断时显示黄底按钮，点击加载完整 body + 重新 JSON 格式化 + 清除搜索缓存
3. **CSS**: 添加右键菜单样式（深色面板、圆角、悬停高亮）

## 使用方式
- 右键左侧任意请求行 → 弹出 Charles 风格菜单
- 响应体被截断时点击黄色「展开全部(N字节)」按钮查看完整数据

## 文件修改
- `capture_server.py` — 响应体截断策略 + API flows 字段补充
- `capture.html` — 右键菜单 + 展开全部 + 对应 CSS

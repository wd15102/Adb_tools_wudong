# AdbTool 桌面GUI · 赛博朋克主题改造

## 时间：2026-06-16 18:50 - 19:15

## 目标
基于用户提供的 AdbTool 桌面主程序截图，对 Tkinter 桌面 GUI 进行"黑科技/赛博朋克"风格重设计。

## 设计风格
- **配色**：深色背景（#0a0e1a）+ 青色高亮（#00d4ff）的科技风配色
- **质感**：玻璃磨砂面板、发光边框、低透明度悬浮效果
- **字体**：Microsoft YaHei（通用标签）+ Consolas（终端输出）
- **细节**：按钮悬停变色发光、超级椭圆前缀、终端式输出框

## 改动内容

### 新增文件：`src/gui_theme.py`
完整的赛博朋克主题模块，提供：
- **色彩常量**：CYAN / DARK_CYAN / PURPLE / PINK / TEXT_PRIMARY 等 20+ 颜色
- **`create_bg_canvas(parent)`**：科技网格背景 Canvas（48px 间隔线 + 中心交叉点发光）
- **`apply_theme(root)`**：全局 ttk 样式配置（暗色主题覆盖 Button / Combobox / Scrollbar / LabelFrame / Entry / Radiobutton）
- **`CyberButton`**：继承 `tk.Button` 的自定义按钮类
  - 默认：暗色背景（#111827）+ 灰色文字（#94a3b8）
  - 悬停：亮色背景（#1e293b）+ 青色文字（#00d4ff）
  - 光标：手型（hand2）

### 修改文件：`src/gui.py`
1. **模块引入**（顶部）：
   - 新增 `import gui_theme`（带 `try/except ImportError` fallback）
   - `Button = gui_theme.CyberButton` 覆写全局 Button → 自动影响全部 25 个按钮

2. **`__init__` 方法**：
   - 窗口标题改为 `"AdbTool · 赛博工程平台"`
   - 应用 `gui_theme.apply_theme(self.root)` 
   - Text 输出框：暗色背景 + 青色光标 + 无边框（等宽字体 Consolas 10pt）
   - 字体：Microsoft YaHei 9pt（通用）/ 10pt Bold（标题）

3. **`start()` 方法**：
   - 新增 `create_bg_canvas()` → `place()` → `lower()` 在最底层

4. **`title_info()` 方法**：
   - 标题文本改为竖线分隔格式 `"│ 设备厂家：XXX  │  设备型号：XXX"`
   - RadioButton 增加 `◉ ` 前缀
   - RadioButton 增加暗色主题配置
   - 设备未连接提示改为 `"⚠ 设备未连接或已下线"`

5. **`text_display()` 方法**：
   - Text 增加发光边框（highlightbackground / highlightthickness / highlightcolor）
   - padding 微调（padx=4, pady=4）

6. **`contact()` 方法**：
   - 版本/联系人标签改为深色文字（#475569）

7. **其他 Label**：`"开adb方法"` 标签增加显式暗色背景

### 一次性影响
- **25 个 Button** 自动继承 CyberButton 样式（悬停发光、暗色背景、手型光标）
- **ttk 控件**（Combobox / Scrollbar / Entry 等）自动应用暗色主题
- **所有子窗口**（性能测试参数窗、遥控器面板等）内的 ttk 控件也会应用主题

## 文件路径
- `D:\WorkCode\AdbTool-maste\src\gui_theme.py`（新增）
- `D:\WorkCode\AdbTool-maste\src\gui.py`（修改）

## 验证
- 语法检查：`py_compile.compile()` 均 PASS
- 模块导入：`from src.gui import Gui` 通过
- 运行时：ADB 相关操作正常（`title_info` 中的设备检测在真实环境中运行）

## 已知限制
- Tkinter 不支持 `rgba()` 颜色 → 已全部转为十六进制（`rgba(0,212,255,0.08)` → `#1a2a40`）
- Canvas 的 `lower()` 方法在 Tkinter 中存在歧义 → 改用 `self.root.tk.call('lower', bg._w)`
- 赛博朋克背景网格使用 `place()` 布局，其他控件使用 `grid()` 布局，需确保 z-order 正确
- 子窗口（Toplevel）的 ttk 控件也会继承主题风格，如需差异化需单独配置

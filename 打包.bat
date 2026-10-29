@echo off

chcp 936 >nul

title AdbTool 打包工具

rem ============================================
rem  AdbTool 打包工具（可放任意位置，自动定位项目根）
rem  打包.bat 可放在：
rem    1. 项目根目录 AdbTool-maste\（原方式）
rem    2. dist\adbtool\ 内（新方式）
rem ============================================
echo.

rem ---- 定位项目根目录（含 .venv 和 adbtool.spec 的目录） ----
rem 注意：for 循环内必须用 !VAR! 延迟展开，%%VAR%% 在整块解析时就固定了
setlocal enabledelayedexpansion
set "PROJ_ROOT=%~dp0"
set "FOUND_ROOT="
for /L %%i in (1,1,6) do (
    if exist "!PROJ_ROOT!.venv\Scripts\python.exe" if exist "!PROJ_ROOT!adbtool.spec" (
        set "FOUND_ROOT=1"
        goto :found_root
    )
    set "PROJ_ROOT=!PROJ_ROOT!..\"
)

:found_root
if not defined FOUND_ROOT (
    echo [错误] 未找到项目根目录（需包含 .venv\Scripts\python.exe 和 adbtool.spec）
    echo 请确认打包.bat 位于项目目录内（如 AdbTool-maste\ 或 AdbTool-maste\dist\adbtool\）
    echo.
    pause
    exit /b 1
)

rem 规范化路径（去掉 ..\ 和尾部反斜杠）
for %%i in ("%PROJ_ROOT%") do set "PROJ_ROOT=%%~fi"

cd /d "%PROJ_ROOT%"

echo ========================================
echo   AdbTool 打包工具
echo   项目根目录: %PROJ_ROOT%
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv\Scripts\python.exe
    echo 请先运行 python -m venv .venv 创建虚拟环境
    echo.
    pause
    exit /b 1
)

echo [1/2] 检查 PyInstaller ...
".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [提示] PyInstaller 未安装，正在安装 ...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败
        echo.
        pause
        exit /b 1
    )
)

echo [2/2] 开始打包（3-5 分钟，请耐心等待）...
echo.
rem 显式指定输出/中间目录，确保无论 bat 放在哪里都输出到项目 dist 下
".venv\Scripts\python.exe" -m PyInstaller adbtool.spec --noconfirm --distpath "%PROJ_ROOT%\dist" --workpath "%PROJ_ROOT%\build"

if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请查看上方日志
) else (
    echo.
    echo ========================================
    echo   [成功] 打包完成
    echo   输出目录: %PROJ_ROOT%\dist\adbtool\
    echo   入口程序: %PROJ_ROOT%\dist\adbtool\adbtool.exe
    echo ========================================
)

echo.
pause

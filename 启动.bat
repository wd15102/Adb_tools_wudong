@echo off
chcp 936 >nul

title AdbTool 启动工具

rem ============================================
rem  AdbTool 一键启动（可放项目内任意位置，自动定位项目根）
rem  双击即可启动，效果等同: .venv\Scripts\python.exe adbtool.py
rem ============================================
echo.

rem ---- 定位项目根目录（含 .venv\Scripts\python.exe 和 adbtool.py 的目录）----
rem 注意：for 循环内必须用 !VAR! 延迟展开，%%VAR%% 在整块解析时就固定了
setlocal enabledelayedexpansion
set "PROJ_ROOT=%~dp0"
set "FOUND_ROOT="
for /L %%i in (1,1,6) do (
    if exist "!PROJ_ROOT!.venv\Scripts\python.exe" if exist "!PROJ_ROOT!adbtool.py" (
        set "FOUND_ROOT=1"
        goto :found_root
    )
    set "PROJ_ROOT=!PROJ_ROOT!..\"
)

:found_root
if not defined FOUND_ROOT (
    echo [错误] 未找到项目根目录（需包含 .venv\Scripts\python.exe 和 adbtool.py）
    echo 请确认 启动.bat 位于项目目录内（如 AdbTool-maste\ 或其子目录）
    echo.
    pause
    exit /b 1
)

rem 规范化路径（去掉 ..\ 和尾部反斜杠）
for %%i in ("%PROJ_ROOT%") do set "PROJ_ROOT=%%~fi"

cd /d "%PROJ_ROOT%"

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到 .venv\Scripts\python.exe
    echo 请先创建虚拟环境: python -m venv .venv
    echo 并安装依赖: .venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

rem ---- 内网路由自检：连着 WiFi 但没有 172.31.0.0/16 路由时提醒（不阻塞启动）----
powershell -NoProfile -Command "if ((Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and $_.MediaType -eq 'Native 802.11' })) { if (-not (Get-NetRoute -DestinationPrefix '172.31.0.0/16' -ErrorAction SilentlyContinue)) { Write-Host '[警告] 未检测到内网路由 172.31.0.0/16，启动后可能连不上内网'; Write-Host '[提示] 请双击运行 设置内网路由.bat 一键修复（仅首次需要，需管理员权限）'; Write-Host '' } }"

echo ========================================
echo   AdbTool 启动中，请稍候...
echo   项目根目录: %PROJ_ROOT%
echo ========================================
echo.

".venv\Scripts\python.exe" adbtool.py

if errorlevel 1 (
    echo.
    echo [提示] 程序异常退出，错误代码: %errorlevel%，请查看上方日志
)

echo.
pause

@echo off
chcp 936 >nul
title AdbTool 一键打包
cd /d "%~dp0"

echo ========================================
echo   AdbTool 一键打包脚本
echo ========================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境：.venv\Scripts\python.exe
    echo 请先运行 python -m venv .venv 并安装依赖
    echo.
    pause
    exit /b 1
)

echo [1/2] 检查打包工具 PyInstaller ...
".venv\Scripts\python.exe" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo [提示] 未安装 PyInstaller，正在安装 ...
    ".venv\Scripts\python.exe" -m pip install pyinstaller
    if errorlevel 1 (
        echo [错误] PyInstaller 安装失败
        echo.
        pause
        exit /b 1
    )
)

echo [2/2] 开始打包（约 3-5 分钟，请耐心等待）...
echo.
".venv\Scripts\python.exe" -m PyInstaller adbtool.spec --noconfirm

if errorlevel 1 (
    echo.
    echo [失败] 打包出错，请查看上方日志
) else (
    echo.
    echo ========================================
    echo   [成功] 打包完成！
    echo   输出目录: dist\adbtool\
    echo   入口程序: dist\adbtool\adbtool.exe
    echo ========================================
)

echo.
pause
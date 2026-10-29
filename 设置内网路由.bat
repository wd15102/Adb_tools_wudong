@echo off
chcp 936 >nul

title AdbTool 内网路由设置

rem ============================================
rem  AdbTool 内网路由设置（需管理员权限，双击运行一次即可）
rem
rem  作用：把内网网段 172.31.0.0/16 的流量固定走 WiFi 网卡，
rem        默认路由保持不变 —— adb 设备继续走有线网络。
rem
rem  路由为持久化路由，重启后依然有效；
rem  换 WiFi 导致网关变化时，重新运行本脚本即可刷新。
rem
rem  如需修改内网网段，同时修改下面两个变量
rem    ROUTE_PREFIX = 网段/前缀长度，ROUTE_MASK = 对应子网掩码
rem    /16 对应 255.255.0.0，/24 对应 255.255.255.0
rem  如需撤销路由：管理员 CMD 运行 route delete 172.31.0.0
rem ============================================
set "ROUTE_PREFIX=172.31.0.0/16"
set "ROUTE_MASK=255.255.0.0"

rem ---- 检查管理员权限，不足则提权重启本脚本 ----
net session >nul 2>&1
if errorlevel 1 (
    echo [提示] 需要管理员权限，将弹出授权窗口，请点击“是”...
    powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
    if errorlevel 1 (
        echo [错误] 获取管理员权限失败，请右键本文件，选择“以管理员身份运行”
        echo.
        pause
    )
    exit /b
)

echo ========================================
echo   AdbTool 内网路由设置
echo   目标网段: %ROUTE_PREFIX%  将走 WiFi
echo   默认路由不变，adb 设备继续走有线
echo ========================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='Stop'; $prefix='%ROUTE_PREFIX%'; $mask='%ROUTE_MASK%'; $wifi=Get-NetAdapter | Where-Object { $_.Status -eq 'Up' -and ($_.MediaType -eq 'Native 802.11' -or $_.InterfaceDescription -match 'Wi-Fi|Wireless|WLAN|802\.11') } | Select-Object -First 1; if (-not $wifi) { Write-Host '[错误] 未找到已连接的 WiFi 网卡，请先连接 WiFi 后重试'; exit 1 }; $cfg=Get-NetIPConfiguration -InterfaceIndex $wifi.InterfaceIndex; $gw=($cfg.IPv4DefaultGateway | Select-Object -First 1).NextHop; $ip=($cfg.IPv4Address | Select-Object -First 1).IPAddress; if (-not $gw) { Write-Host '[错误] 未获取到 WiFi 网关地址'; exit 1 }; Write-Host ('[信息] WiFi 网卡: {0}  索引: {1}  IP: {2}  网关: {3}' -f $wifi.Name,$wifi.InterfaceIndex,$ip,$gw); Write-Host '[1/3] 清理旧路由...'; route.exe delete $prefix 2>&1 | Out-Null; Remove-NetRoute -DestinationPrefix $prefix -PolicyStore PersistentStore -Confirm:$false -ErrorAction SilentlyContinue; Write-Host '[2/3] 添加持久化路由（走 WiFi）...'; $out = route.exe -p add $prefix mask $mask $gw metric 1 if $wifi.InterfaceIndex 2>&1; if ($LASTEXITCODE -ne 0) { Write-Host ('[错误] 路由添加失败: {0}' -f ($out -join ' ')); exit 1 }; Write-Host '[3/3] 验证路由...'; Get-NetRoute -DestinationPrefix $prefix -ErrorAction SilentlyContinue | Format-Table -AutoSize DestinationPrefix,InterfaceAlias,NextHop,RouteMetric | Out-String | Write-Host; $act=Get-NetRoute -DestinationPrefix $prefix -ErrorAction SilentlyContinue; $per=Get-NetRoute -DestinationPrefix $prefix -PolicyStore PersistentStore -ErrorAction SilentlyContinue; if ((-not $act) -or (-not $per)) { Write-Host '[提示] 检测到路由不完整，正在补充...' }; if (-not $act) { New-NetRoute -DestinationPrefix $prefix -InterfaceIndex $wifi.InterfaceIndex -NextHop $gw -RouteMetric 1 | Out-Null }; if (-not $per) { New-NetRoute -DestinationPrefix $prefix -InterfaceIndex $wifi.InterfaceIndex -NextHop $gw -RouteMetric 1 -PolicyStore PersistentStore | Out-Null }; if ((Get-NetRoute -DestinationPrefix $prefix -PolicyStore PersistentStore -ErrorAction SilentlyContinue) -and (Get-NetRoute -DestinationPrefix $prefix -ErrorAction SilentlyContinue)) { Write-Host '[成功] 活动路由 + 持久化路由均已就绪' } else { Write-Host '[警告] 路由可能不完整，请重启电脑后重新运行本脚本' }; $ok=(Test-NetConnection -ComputerName '172.31.111.166' -Port 80 -WarningAction SilentlyContinue).TcpTestSucceeded; if ($ok) { Write-Host '[完成] 路由设置成功，内网服务器 172.31.111.166:80 已可达' } else { Write-Host '[警告] 路由已添加，但服务器仍不可达，请检查 VPN 或防火墙设置' }"

echo.
pause

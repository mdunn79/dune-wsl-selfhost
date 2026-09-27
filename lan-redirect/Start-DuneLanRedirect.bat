@echo off
REM Gaming PC. Manual: window stays open, redirect on until Ctrl+C.
REM Watch: Start-DuneLanRedirect.ps1 -WatchDune  (arms only while Dune is running)
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
  exit /b
)
if /i "%~1"=="watch" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-DuneLanRedirect.ps1" -WatchDune
  goto :end
)
if "%~1"=="" (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-DuneLanRedirect.ps1"
) else (
  powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Start-DuneLanRedirect.ps1" -LanIp %~1
)
:end
echo.
pause

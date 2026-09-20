@echo off
REM Double-click or Run as administrator. Elevates itself, then runs the installer
REM from this folder. Does not wsl --shutdown unless the installer needs it.
cd /d "%~dp0"
net session >nul 2>&1
if %errorlevel% neq 0 (
  powershell.exe -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install-DuneBattlegroup.ps1"
echo.
pause

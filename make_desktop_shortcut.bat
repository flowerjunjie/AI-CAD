@echo off
rem Generate desktop .lnk shortcut pointing to start.bat
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_desktop_shortcut.ps1"
pause

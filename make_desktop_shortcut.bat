@echo off
rem 在桌面生成真正的 .lnk 快捷方式 → 指向 start.bat, 双击即运行
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_desktop_shortcut.ps1"
pause

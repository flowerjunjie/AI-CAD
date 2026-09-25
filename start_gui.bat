@echo off
rem AI-CAD GUI launcher - double-click to open the professional 3-panel GUI.
rem Starts the Python engine bridge (no black console) + vite frontend + browser.
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [X] python not found. Install Python 3.11+ and add to PATH.
  pause
  exit /b 1
)

rem bridge deps (fastapi/uvicorn)
python -m pip install -q fastapi "uvicorn[standard]"
if errorlevel 1 (
  echo [X] pip install failed. Check network / pip mirror.
  pause
  exit /b 1
)

python start_gui.py
pause

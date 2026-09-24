@echo off
rem AI-CAD GUI launcher (Windows)
rem Usage: double-click to open the professional GUI in your browser.
rem   - installs fastapi + uvicorn if missing
rem   - starts the FastAPI engine bridge (no console window)
rem   - opens the GUI (vite dev if node present, else bridge landing page)
rem   - Ctrl+C / close keeps the bridge clean
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [X] python not found. Install Python 3.11+ and add to PATH.
  pause
  exit /b 1
)

echo [1/2] Checking GUI bridge deps (fastapi + uvicorn)...
python -m pip install -q fastapi "uvicorn[standard]"
if errorlevel 1 (
  echo [X] fastapi/uvicorn install failed. Check network or pip mirror.
  pause
  exit /b 1
)

echo [2/2] Launching AI-CAD GUI...
python start_gui.py
if errorlevel 1 (
  echo [X] GUI launch failed. See output above.
  pause
  exit /b 1
)
pause

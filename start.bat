@echo off
rem AI-CAD one-click executable entry (Windows)
rem Usage: double-click, or  start.bat [no-llm|llm]
rem   start.bat       = full pipeline with LLM (online, renders floorplan PNG + auto-opens)
rem   start.bat no-llm = local fast-verify (offline, deterministic)
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [X] python not found. Install Python 3.11+ and add to PATH.
  pause
  exit /b 1
)

echo [1/3] Installing dependencies...
python -m pip install -q -r src\agents\requirements.txt
if errorlevel 1 (
  echo [X] pip install failed. Check network or pip mirror.
  pause
  exit /b 1
)

echo [2/3] Running AI-CAD full pipeline...
python run.py %*
if errorlevel 1 (
  echo [X] run.py failed. See output above.
  pause
  exit /b 1
)

echo [3/3] Done - outputs in output\ :
echo        output\report.html
echo        output\preview.png
echo        output\ai_cad_output.dwg
pause

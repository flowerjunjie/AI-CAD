@echo off
rem ─────────────────────────────────────────────────────────────
rem  AI-CAD · 一键可执行入口 (Windows)
rem  用法: 双击运行, 或命令行  start.bat [no-llm|llm]
rem    start.bat           = 全流程含 LLM (联网, 出图+自动弹窗口型图)
rem    start.bat no-llm    = 纯本地快验 (不联网, 秒级确定结果)
rem ─────────────────────────────────────────────────────────────
setlocal
cd /d "%~dp0"

where python >nul 2>nul
if errorlevel 1 (
  echo [X] 未检测到 python。请先安装 Python 3.11+ 并加入 PATH, 再运行本脚本。
  pause
  exit /b 1
)

echo [1/3] 安装/对齐依赖 (requirements.txt + ezdxf)...
python -m pip install -q -r src\agents\requirements.txt
if errorlevel 1 (
  echo [X] 依赖安装失败, 检查网络或 pip 源。
  pause
  exit /b 1
)

echo [2/3] 运行 AI-CAD 全链路 (本地验证: start.bat no-llm 可跳过联网)...
python run.py %*
if errorlevel 1 (
  echo [X] 运行失败, 见上方输出。
  pause
  exit /b 1
)

echo [3/3] 完成 — 成果在 output/ 目录:
echo        output\report.html   运行报告
echo        output\preview.png   户型图预览 (已自动弹出)
echo        output\ai_cad_output.dwg  生成的 DWG
pause

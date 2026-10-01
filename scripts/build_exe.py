"""
AI-CAD 打包脚本 — PyInstaller 把「桥 + 前端 dist + 引擎 + 样本数据」打成 onedir 交付物。

设计取舍 (事实驱动):
  - onedir 而非 onefile: 桌面面板要求秒开; onefile 每次启动要解压 ~200MB 进临时目录,
    冷启动 30s+ 不可接受。onedir 产物是 `dist/ai_cad_gui/` 目录, 双击 `ai_cad_gui.exe`
    即开专业面板 (浏览器 http://127.0.0.1:<port>)。
  - 数据文件随包: src/ (引擎+桥+前端dist) + data/sample (Agent 样本) 一起进 _internal,
    让 bridge.py 的 _project_root() (__file__ 上溯两级) 在打包态下仍能定位到 data/sample。
  - 启动器 ai_cad_gui.py 独立于开发态 start_gui.py (后者依赖 node 起 vite, 交付态无 node)。

用法:
  python scripts/build_exe.py            # onedir 默认, 产物在 build/dist/ai_cad_gui/
  python scripts/build_exe.py --onefile   # 强制 onefile (调试用, 启动慢)

前置:
  1) pip install pyinstaller
  2) src/client 已 vite build (src/dist 存在) — 没有就先 `cd src/client && npm run build`
  3) src/agents/requirements.txt 装好 (引擎 import 面)

隐藏 import / 数据清单维护在下面 HIDDEN_IMPORTS 和 DATA_FILES, 改打包内容只改这里。
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根
DIST_FRONTEND = os.path.join(ROOT, "src", "dist")
OUT_DIR = os.path.join(ROOT, "build", "dist")
WORK_DIR = os.path.join(ROOT, "build", "work")
SPEC = os.path.join(ROOT, "build", "ai_cad_gui.spec")

# PyInstaller 追不到的懒 import (函数体内才 import 的模块) — 必须显式列出
HIDDEN_IMPORTS = [
    "src.gui.bridge",
    "src.agents.src.graph",
    "src.agents.src.nodes",
    "src.agents.src.nodes.cad_rule_export",
    "src.agents.src.nodes.input_parser",
    "src.agents.src.nodes.intent_structure",
    "src.agents.src.tools",
    "src.agents.src.tools.rag_tools",
    "src.agents.src.tools.cad_tools",
    "src.agents.src.tools.plumbing_extractor",
    "src.agents.src.tools.electrical_extractor",
    "src.agents.src.tools.hvac_extractor",
    "src.agents.src.tools.structural_extractor",
    "src.agents.src.tools.matplotlib_cjk",
    "src.agents.src.tools.clash_detection",
    "src.agents.src.tools.conflict_detection",
    "src.agents.src.tools.permission_model",
    "src.agents.src.tools.collab_protocol",
    "src.rules.src.engine",
    "src.rules.src.dsl",
    "src.rules.src.residential",
    "src.rules.src.fire_safety",
    "src.rules.src.accessibility",
    "src.rules.src.plumbing",
    "src.rules.src.electrical",
    "src.rules.src.hvac",
    "src.rules.src.structural",
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "fastapi.staticfiles",
    "langgraph",
    "ezdxf",
    "matplotlib",
    "chromadb",
]


def frontend_dist_ready() -> bool:
    """前端 dist 必须存在且含 index.html, 否则提示先 build。"""
    idx = os.path.join(DIST_FRONTEND, "index.html")
    return os.path.isfile(idx)


def build(onefile: bool = False) -> int:
    if not frontend_dist_ready():
        print(f"[build_exe] 前端 dist 缺失 ({DIST_FRONTEND})。先跑: cd src/client && npm run build")
        return 1

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",  # 不起黑框
        "--name", "ai_cad_gui",
        "--distpath", OUT_DIR,
        "--workpath", WORK_DIR,
        "--specpath", ROOT,
    ]
    if onefile:
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    for m in HIDDEN_IMPORTS:
        cmd += ["--hidden-import", m]

    # 构建环境同时装了多套 Qt 绑定 (PySide6/PyQt5), 且 torch/tensorflow/onnx
    # 全家桶被 hooks 误追 (src 代码没 import 它们, 只是 chromadb→onnx→torch 传递)。
    # 逐个 exclude, 既解 Qt 冲突又减体积 (torch ~500MB 纯拖累)。
    for x in ["PyQt5", "PyQt6", "PySide6", "PySide2",
              "torch", "torchvision", "torchaudio", "tensorflow",
              "onnxruntime", "onnx", "grpc", "boto3"]:
        cmd += ["--exclude-module", x]

    # 数据文件: 前端 dist + Agent 样本数据 (bridge 的 _project_root 靠它们定位)
    # + DSL 规则 default.json (数据文件, 不被 PYZ 打包, 须 --add-data 单独进;
    #   落到 _internal/src/rules/rules/, 对上 bridge._project_root()/src/rules/rules/)
    for data in [
        os.path.join("src", "dist"),
        os.path.join("data", "sample"),
        os.path.join("src", "rules", "rules"),
    ]:
        if os.path.exists(os.path.join(ROOT, *data.split(os.sep))):
            cmd += ["--add-data", f"{os.path.join(ROOT, *data.split(os.sep))}:{data}"]

    cmd.append(os.path.join(ROOT, "ai_cad_gui.py"))

    print("[build_exe] ", " ".join(cmd))
    print("[build_exe] PyInstaller 构建中 (首次 ~3-5 min, 收集 matplotlib/chromadb 较重)…")
    r = subprocess.run(cmd, cwd=ROOT)
    if r.returncode != 0:
        print(f"[build_exe] PyInstaller 失败 rc={r.returncode}")
        return r.returncode

    # 产物定位
    pkg = os.path.join(OUT_DIR, "ai_cad_gui") if not onefile else os.path.join(OUT_DIR, "ai_cad_gui.exe")
    print(f"[build_exe] 产物: {pkg}")
    print(f"[build_exe] 运行: 双击 exe → 浏览器自动开 http://127.0.0.1:<port>")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--onefile", action="store_true", help="打 onefile (默认 onedir)")
    args = ap.parse_args()
    sys.exit(build(onefile=args.onefile))

"""验证 ai_cad_gui.exe 交付物端到端: 起 exe → /api/health → / (dist 面板) → 浏览器面板元素。

用法:
  python scripts/verify_exe.py
依赖: build_exe.py 已跑过, build/dist/ai_cad_gui/ai_cad_gui.exe 存在。
Windows 下 exe 自带 _internal, 直接 subprocess 起, 探端口, curl 端点。
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "build", "dist", "ai_cad_gui")
EXE = os.path.join(PKG, "ai_cad_gui.exe")


def _find_port_file() -> str:
    """gui_port.txt 落在 RESOURCE_ROOT (onedir 下 = _internal/), 逐级找。"""
    for base in (PKG, os.path.join(PKG, "_internal")):
        pf = os.path.join(base, "gui_port.txt")
        if os.path.isfile(pf):
            return pf
    # 默认返 _internal (onedir 实际落点)
    return os.path.join(PKG, "_internal", "gui_port.txt")


def wait_port() -> int | None:
    """轮询 exe 写的 gui_port.txt 读实际监听端口。"""
    pf = _find_port_file()
    for base in (PKG, os.path.join(PKG, "_internal")):
        cand = os.path.join(base, "gui_port.txt")
        try:
            os.remove(cand)
        except OSError:
            pass
    deadline = time.time() + 60
    while time.time() < deadline:
        for base in (PKG, os.path.join(PKG, "_internal")):
            cand = os.path.join(base, "gui_port.txt")
            if os.path.isfile(cand):
                with open(cand) as f:
                    p = f.read().strip()
                    if p.isdigit():
                        return int(p)
        time.sleep(0.5)
    return None


def main() -> int:
    if not os.path.isfile(EXE):
        print(f"[verify] 产物不存在: {EXE} — 先跑 python scripts/build_exe.py")
        return 1

    print(f"[verify] 启动 {EXE}")
    proc = subprocess.Popen([EXE], cwd=PKG,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x08000000 if os.name == "nt" else 0)
    port = None
    try:
        port = wait_port()
        if port is None:
            print("[verify] 60s 内没读到 gui_port.txt — exe 未起桥, 退出码排查")
            return 1

        print(f"[verify] exe 起桥端口 {port}")
        import urllib.request, json
        # 1) /api/health — 引擎桥
        health = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/health", timeout=30).read().decode())
        print(f"[verify] /api/health → rules={health.get('modules',{}).get('rules')} dsl={health.get('modules',{}).get('dsl')}")
        # 2) / — dist 面板 (StaticFiles 托管, 应返回 React index.html)
        home = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=30).read().decode()
        has_react = "id=\"root\"" in home and ".js" in home
        print(f"[verify] / → {'React 面板 (dist 托管成功)' if has_react else '!! 不是 dist 面板'}")
        # 3) /api/rules confirmed 透出 + M1 点亮链 (给排水/电气/暖通)
        rules = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/api/rules", timeout=30).read().decode())
        confirmed = [r["rule_id"] for r in rules if r.get("confirmed")]
        lit = {lab: any(r.get("confirmed") and r["rule_id"].startswith(pref)
                        for r in rules) for lab, pref in
               [("给排水", "plumbing-"), ("电气", "electrical-"), ("暖通", "hvac-")]}
        print(f"[verify] confirmed 透出: {confirmed}")
        print(f"[verify] M1 点亮: 给排水={lit['给排水']} 电气={lit['电气']} 暖通={lit['暖通']}")
        ok = has_react and len(confirmed) >= 1
        print(f"[verify] {'PASS' if ok else 'FAIL'} — 浏览器开 http://127.0.0.1:{port}")
        return 0 if ok else 2
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("[verify] exe 已收掉")


if __name__ == "__main__":
    sys.exit(main())

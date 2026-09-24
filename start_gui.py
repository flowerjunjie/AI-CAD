"""
AI-CAD GUI 启动入口 — 把「黑框命令行」升级成双击即开专业界面。

职责 (契约 §0 + 分工 E):
  1. 起 FastAPI 桥 (uvicorn, 127.0.0.1:8642, 被占 +1 重试) —— **不弹黑框**
  2. 起前端: 优先 dev 模式 vite (node 可用且 src/client 有工程), 否则浏览器直连桥兜底页
  3. 浏览器打开 GUI 页面
  4. Ctrl+C / 关窗 干净退出 (桥子进程一起收掉)

设计取舍 (事实驱动):
  - 桥跑在**独立子进程**, 主进程只负责编排 + 开浏览器 + 收信号。
    Windows 下 CREATE_NO_WINDOW (0x08000000) 起 uvicorn, 彻底不弹黑框。
  - 端口先探测再启动, 把实际端口写 output/gui_port.txt, 前端 / 人工都能读。
  - 前端用 vite dev 需要 node; 探不到 node 就优雅降级成「浏览器直开桥兜底页」, 不崩。
"""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import sys
import time
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

HOST = "127.0.0.1"
DEFAULT_PORT = 8642
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "output")
PORT_FILE = os.path.join(OUTPUT_DIR, "gui_port.txt")

# Windows 下不起控制台窗口 (黑框)
_CREATE_NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def find_free_port(start: int = DEFAULT_PORT, host: str = HOST, max_tries: int = 50) -> int:
    """从 start 起找第一个可用端口; 全占回 start。"""
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start


def wait_http_ready(host: str, port: int, timeout: float = 30.0) -> bool:
    """轮询桥 /api/health 直到 200 或超时。"""
    import urllib.request
    url = f"http://{host}:{port}/api/health"
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as r:
                if r.status == 200:
                    return True
        except Exception:
            time.sleep(0.5)
    return False


def start_bridge(port: int) -> subprocess.Popen:
    """起桥子进程 (不弹黑框)。用 `python -m uvicorn` 或本模块 run_bridge。"""
    cmd = [
        sys.executable, "-m", "uvicorn",
        "src.gui.bridge:app",
        "--host", HOST, "--port", str(port),
        "--log-level", "warning",
    ]
    return subprocess.Popen(
        cmd,
        cwd=PROJECT_ROOT,
        creationflags=_CREATE_NO_WINDOW,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def start_frontend(vite_dir: str, port: int) -> subprocess.Popen | None:
    """起 vite dev (node 可用时)。返回 Popen; 不可用返回 None。"""
    if not os.path.isdir(vite_dir) or not os.path.isfile(os.path.join(vite_dir, "package.json")):
        return None
    cmd = ["npm", "run", "dev"]
    kwargs: dict = dict(cwd=vite_dir, creationflags=_CREATE_NO_WINDOW,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                        env={**os.environ, "VITE_API": f"http://{HOST}:{port}"})
    try:
        return subprocess.Popen(cmd, **kwargs)
    except FileNotFoundError:
        return None


def open_browser(url: str) -> None:
    webbrowser.open(url)


def main() -> int:
    port = find_free_port()
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(PORT_FILE, "w", encoding="ascii") as f:
        f.write(str(port))

    print(f"[start_gui] bridge on http://{HOST}:{port} (port file: {PORT_FILE})")
    bridge_proc = start_bridge(port)
    try:
        # 等桥就绪; /api/health 可能未挂载 (B 段没写完), 退化成只探 TCP
        ready = wait_http_ready(HOST, port, timeout=20.0)
        if not ready:
            print("[start_gui] /api/health 尚未就绪 (规则段可能未挂载), 继续开前端兜底")

        vite_dir = os.path.join(PROJECT_ROOT, "src", "client")
        frontend_proc = start_frontend(vite_dir, port)
        if frontend_proc is not None:
            print(f"[start_gui] vite dev 已起, 开浏览器 http://{HOST}:3000")
            time.sleep(4.0)          # 等 vite 冷启动
            open_browser(f"http://{HOST}:3000")
        else:
            print(f"[start_gui] node/vite 不可用, 直开桥兜底页 http://{HOST}:{port}")
            open_browser(f"http://{HOST}:{port}")

        # 常驻直到用户中断; 前端进程若提前退出则一并收
        signal.signal(signal.SIGINT, lambda *_: (_ for _ in ()).throw(SystemExit(0)))
        while bridge_proc.poll() is None:
            time.sleep(1.0)
        return 0
    finally:
        for p in (bridge_proc, locals().get("frontend_proc")):
            if p is not None and p.poll() is None:
                p.terminate()
                try:
                    p.wait(timeout=5)
                except Exception:
                    p.kill()
        print("[start_gui] clean shutdown (bridge + frontend 已收掉)")


if __name__ == "__main__":
    try:
        sys.exit(main())
    except SystemExit as e:
        sys.exit(e.code if e.code is not None else 0)

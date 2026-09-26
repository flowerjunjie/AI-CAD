"""
AI-CAD 打包版启动器 — 由 PyInstaller 打成 ai_cad_gui.exe (onedir 交付物)。

与 start_gui.py 的差异 (为什么独立一份):
  - start_gui.py 面向**开发态**: 源码工程 + vite dev server (需 node)。
  - 本文件面向**交付态**: PyInstaller onedir 产物, 用户机器无 node/无工程源码。
    前端直接用 vite build 出的静态 dist (打包时 --add-data 进 _internal),
    由 FastAPI 桥托管 (StaticFiles), 浏览器开 http://127.0.0.1:<port> 即得专业面板。
  - dist 前端 engineApi 的 API 为空字符串 (相对路径), 同源直连桥 /api/*, 零端口配置。

设计取舍 (事实驱动):
  - 桥用**同步 uvicorn.run** (主线程阻塞), 不再套 daemon 线程 + 探测端口竞态。
    先探空端口 → 立刻交给 uvicorn bind (uvicorn 内部会实际占用), 实际监听端口
    写 gui_port.txt, 主进程开浏览器。单进程同步模型, 无子进程递归, 无 TOCTOU。
  - 挂 dist 前先摘掉 bridge E 段的 '@app.get("/")' 兜底路由 (它精确匹配 '/',
    会抢在 mount 的 '/' 前缀之前命中), 让 StaticFiles 接管 '/' 与前端资产; /api/* 全保留。

打包脚本见 scripts/build_exe.py (PyInstaller 命令行 + 数据文件清单)。
"""
from __future__ import annotations

import os
import sys
import time
import webbrowser

PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

HOST = "127.0.0.1"
DEFAULT_PORT = 8642

# PyInstaller 资源根: onedir 下 --add-data 落到 _internal/ (sys._MEIPASS),
# onefile 下解压到临时 _MEIPASS。源码态 (直接 python 跑) 没有 _MEIPASS, 回退文件旁。
try:
    RESOURCE_ROOT = sys._MEIPASS  # 打包态: 资源根 (onedir=_internal, onefile=临时解压目录)
except AttributeError:
    RESOURCE_ROOT = PROJECT_ROOT  # 源码态: 文件旁
DIST_DIR = os.path.join(RESOURCE_ROOT, "src", "dist")
PORT_FILE = os.path.join(RESOURCE_ROOT, "gui_port.txt")


def find_free_port(start: int = DEFAULT_PORT, host: str = HOST, max_tries: int = 50) -> int:
    """从 start 起找第一个可 bind 的端口。

    注意: 探测用的 socket 立即 close, 存在理论上的 TOCTOU (探测后到 uvicorn bind
    之间被抢)。127.0.0.1 loopback + 单用户 GUI 场景下几乎不会发生; 真被抢 uvicorn
    会报 bind 失败, 下方 wait_http_ready 超时分支兜底 (开浏览器提示), 不崩。
    """
    import socket
    for port in range(start, start + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((host, port))
                return port
            except OSError:
                continue
    return start


def mount_frontend_dist(app, dist_dir: str) -> None:
    """把 vite build 的静态 dist 挂到桥的 '/', 让专业面板接管 / 与前端资产。

    bridge.py 的 E 段有 @app.get("/") 兜底路由 (精确匹配 '/'), 会抢在 mount 的
    '/' 前缀之前命中, 导致 '/' 仍回兜底页而非 dist 面板。故挂 dist 前先摘掉这条
    '/' GET route (只动路径=='/' 的, 不碰 /api/*), 再 mount StaticFiles。
    dist 缺失时不挂 (桥保留 E 段兜底页), 启动不崩。
    """
    if not os.path.isdir(dist_dir):
        print(f"[ai_cad_gui] dist 缺失 ({dist_dir}), 仅起桥兜底页")
        return
    from fastapi.staticfiles import StaticFiles
    router = app.router
    keep = [r for r in router.routes
            if not (getattr(r, "path", None) == "/" and "GET" in getattr(r, "methods", set()))]
    router.routes[:] = keep
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="dist")
    print(f"[ai_cad_gui] dist 面板已托管 / ({dist_dir})")


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


def main() -> int:
    import uvicorn
    from src.gui.bridge import app

    port = find_free_port()
    mount_frontend_dist(app, DIST_DIR)
    with open(PORT_FILE, "w", encoding="ascii") as f:
        f.write(str(port))
    print(f"[ai_cad_gui] bridge on http://{HOST}:{port} (port file: {PORT_FILE})")

    # 同步阻塞跑桥; 后台线程开浏览器 (主线程不卡, 窗口可关)
    import threading
    threading.Thread(
        target=lambda: (time.sleep(3.0),
                        (print("[ai_cad_gui] open http://%s:%d" % (HOST, port)),
                         webbrowser.open(f"http://{HOST}:{port}"))[1]),
        daemon=True,
    ).start()
    try:
        uvicorn.run(app, host=HOST, port=port, log_level="warning")
    except KeyboardInterrupt:
        print("\n[ai_cad_gui] clean shutdown")
    return 0


if __name__ == "__main__":
    import sys as _s
    _s.exit(main())

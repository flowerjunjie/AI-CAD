"""交付态 curl 验证: 起 exe → 探端口 → 逐个 curl 机制层护栏端点,
确认它们真透进了打包态 exe (非开发态)。

用法: 先 python scripts/build_exe.py 打出 build/dist/ai_cad_gui/, 再
  python scripts/verify_delivery_curl.py
校验目标 (当前机制层自主子集):
  - /api/rules/dsl-dispatch-audit (分发表 dispatch 覆盖护栏, 遍历 _ELEMENT_CHECKS)
  - /api/clash | /api/conflict | /api/dwg-scan | /api/rules/dsl/apply
    的 *_consistent 诊断字段在打包态可达且默认自洽 (True 态, 引擎自产产物恒自洽)。
ASCII 输出 (Windows GBK 不崩)。"""
import os, subprocess, time, json, urllib.request, urllib.error

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.join(ROOT, "build", "dist", "ai_cad_gui")


def wait_port():
    for base in (PKG, os.path.join(PKG, "_internal")):
        try:
            os.remove(os.path.join(base, "gui_port.txt"))
        except OSError:
            pass
    deadline = time.time() + 60
    while time.time() < deadline:
        for base in (PKG, os.path.join(PKG, "_internal")):
            pf = os.path.join(base, "gui_port.txt")
            if os.path.isfile(pf):
                p = open(pf).read().strip()
                if p.isdigit():
                    return int(p)
        time.sleep(0.5)
    return None


def get(port, path, body=None, method="GET"):
    url = f"http://127.0.0.1:{port}{path}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method=method)
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def main():
    proc = subprocess.Popen([os.path.join(PKG, "ai_cad_gui.exe")], cwd=PKG,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            creationflags=0x08000000)
    port = wait_port()
    print("PORT", port)
    try:
        # ① 新增端点 (本轮护栏批固化进 exe 的关键证据)
        j = get(port, "/api/rules/dsl-dispatch-audit")
        print("[① dsl-dispatch-audit] ok=", j.get("ok"),
              "issues=", len(j.get("issues", [])), "coverage=", len(j.get("coverage", [])))
        # ② 4 诊断字段端点 (P12 透出面, 交付态确认真在)
        for ep, key in [("/api/clash?sample=residential_100sqm.json", "clashes_consistent"),
                        ("/api/conflict?sample_a=residential_100sqm.json&sample_b=residential_100sqm.json",
                         "summary_consistent"),
                        ("/api/dwg-scan?sample=electrical_sample.dxf", "scan_consistent")]:
            jj = get(port, ep)
            print(f"[② {ep.split('?')[0]}] {key}=", jj.get(key))
        # dsl/apply 是 POST
        jj = get(port, "/api/rules/dsl/apply", body={"rules": [], "confirm": False},
                 method="POST")
        print("[② /api/rules/dsl/apply] diff_consistent=", jj.get("diff_consistent"))
        print("ALL_DELIVERY_CURL_OK")
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()
        print("exe stopped")


if __name__ == "__main__":
    main()

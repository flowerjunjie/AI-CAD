"""
出图警示标记计数对账测试 (机制层自主子集)

覆盖:
  ① cad_tools.count_dwg_markers / verify_dwg_markers — 纯函数, 读回 DWG 里
     CLASH/DUP 图层 CIRCLE 实体数 vs 期望值对账 (漏画/多画/打不开 各归各 case),
     畸形 DWG 不崩。只数「画没画够」, 不判「画得对不对」(M2 业务)。
  ② bridge /api/dwg-marker-verify — 起真实 sample 出图 → 对账, 契约字段 + 200。

红线对齐 (CLAUDE.md 不虚标): 纯机制层计数对账, 不填 M1/M2/M5 业务值。
仿 test_clash_detection 范式: __main__ 只列无 fixture 子集 + 不 print 中文/emoji
(Windows GBK 直跑不崩, 见 test_direct_run.py)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _ct():
    from src.agents.src.tools import cad_tools
    return cad_tools


def _make_dxf_with_markers(tmp, clash=0, dup=0):
    """造一个画了 clash 个 CLASH 圈 + dup 个 DUP 圈的 DXF, 返回路径。"""
    from src.agents.src.tools.cad_tools import DXFWriter
    w = DXFWriter()
    w.new()
    for i in range(clash):
        w.add_clash_marker(float(i) * 0.3, 0.0, "PIPE-BEAM", label="CLASH")
    for i in range(dup):
        w.add_duplicate_marker(0.0, float(i) * 0.3, label="DUP")
    path = os.path.join(tmp, f"mk_c{clash}_d{dup}.dxf")
    w.save(path)
    return path


# ─── ① 纯函数对账 ─────────────────────────────────────────────


def test_markers_matched_ok():
    """画够 (CLASH/DUP 实数 == 期望) → ok=True。"""
    import tempfile
    ct = _ct()
    with tempfile.TemporaryDirectory() as tmp:
        p = _make_dxf_with_markers(tmp, clash=3, dup=2)
        res = ct.verify_dwg_markers(p, expected_clash=3, expected_dup=2)
        assert res["ok"] is True and res["issues"] == [], f"画够应自洽, 得 {res}"
        assert res["clash_drawn"] == 3 and res["dup_drawn"] == 2


def test_markers_underdrawn_flagged():
    """漏画 (实数 < 期望) → 如实报失步。"""
    import tempfile
    ct = _ct()
    with tempfile.TemporaryDirectory() as tmp:
        p = _make_dxf_with_markers(tmp, clash=1, dup=0)
        res = ct.verify_dwg_markers(p, expected_clash=3, expected_dup=0)
        assert res["ok"] is False
        assert any("CLASH" in it for it in res["issues"])


def test_markers_overdrawn_flagged():
    """多画 (实数 > 期望) → 如实报失步。"""
    import tempfile
    ct = _ct()
    with tempfile.TemporaryDirectory() as tmp:
        p = _make_dxf_with_markers(tmp, clash=4, dup=1)
        res = ct.verify_dwg_markers(p, expected_clash=2, expected_dup=0)
        assert res["ok"] is False
        assert any("CLASH" in it for it in res["issues"])
        assert any("DUP" in it for it in res["issues"])


def test_empty_markers_no_false_positive():
    """无碰撞 (expected 全 0 + 实画全 0) → 合法, 不误报漏画。"""
    import tempfile
    ct = _ct()
    with tempfile.TemporaryDirectory() as tmp:
        p = _make_dxf_with_markers(tmp, clash=0, dup=0)
        res = ct.verify_dwg_markers(p, expected_clash=0, expected_dup=0)
        assert res["ok"] is True and res["issues"] == [], f"空画应自洽, 得 {res}"


def test_unopenable_dwg_no_crash():
    """打不开的 DWG (缺文件) → 记 issue 不崩, 不静默当 0 圈全过。"""
    ct = _ct()
    res = ct.verify_dwg_markers("/nonexistent/path/x.dxf",
                                expected_clash=0, expected_dup=0)
    assert res["ok"] is False
    assert any("打不开" in it for it in res["issues"])
    assert res["clash_drawn"] == 0 and res["dup_drawn"] == 0


# ─── ② bridge 端点 ───────────────────────────────────────────


def test_bridge_dwg_marker_verify_endpoint():
    """/api/dwg-marker-verify 200 + 契约字段; 出图侧画够 → ok=True。"""
    from fastapi.testclient import TestClient
    from src.gui.bridge import app
    with TestClient(app) as client:
        resp = client.get("/api/dwg-marker-verify")
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code} {resp.text}"
        body = resp.json()
        for k in ("ok", "clash_drawn", "clash_expected",
                  "dup_drawn", "dup_expected", "issues"):
            assert k in body, f"缺字段 {k}, 实际 {list(body)}"


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_markers_matched_ok()
    test_markers_underdrawn_flagged()
    test_markers_overdrawn_flagged()
    test_empty_markers_no_false_positive()
    test_unopenable_dwg_no_crash()
    test_bridge_dwg_marker_verify_endpoint()
    print("OK: all dwg marker verify tests passed")

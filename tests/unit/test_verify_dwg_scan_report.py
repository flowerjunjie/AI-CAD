"""
DWG 图层扫描报告结构自洽体检测试 (机制层自主子集)

覆盖:
  ① dwg_layer_scan.verify_dwg_scan_report — 纯函数, 校验 scan_dwg 报告的
     聚合计数 (layer_count / insert_total / entity_type_totals) 与图层明细是否
     自洽, 防「专家照着一份数字对不上的报告回填映射 dict」被误导。畸形不崩。
  ② bridge /api/dwg-scan 透出 scan_consistent / scan_issues 诊断字段 (端点 200 + 契约)。

红线对齐 (CLAUDE.md 不虚标): 只判「报告自身结构是否自洽」, 不判「哪个图层=梁/柱」
(M2 业务归属, 专家填映射 dict)。仿 test_dwg_layer_scan 范式: __main__ 只列无
fixture 子集 + 不 print 中文/emoji (Windows GBK 直跑不崩)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _dls():
    from src.agents.src.tools import dwg_layer_scan
    return dwg_layer_scan


# ─── ① verify_dwg_scan_report 纯函数 ──────────────────────────


def _consistent_report():
    """一份自洽的报告 (聚合 == 明细)。"""
    return {
        "layers": {
            "WALL": {"entity_counts": {"LINE": 4, "INSERT": 2}, "block_names": ["DW"]},
            "PIPE": {"entity_counts": {"LWPOLYLINE": 3, "INSERT": 1}, "block_names": []},
        },
        "entity_type_totals": {"LINE": 4, "LWPOLYLINE": 3, "INSERT": 3},
        "attrib_tags": {"TAG1": 5},
        "layer_count": 2,
        "insert_total": 3,
    }


def test_consistent_report_ok():
    """聚合全对账通过 → ok=True。"""
    dls = _dls()
    res = dls.verify_dwg_scan_report(_consistent_report())
    assert res["ok"] is True and res["issues"] == [], f"自洽报告应通过, 得 {res}"


def test_layer_count_mismatch_flagged():
    """layer_count ≠ len(layers) → 如实报失步。"""
    dls = _dls()
    rep = _consistent_report()
    rep["layer_count"] = 5  # 谎报
    res = dls.verify_dwg_scan_report(rep)
    assert res["ok"] is False
    assert any("layer_count" in it for it in res["issues"])


def test_insert_total_mismatch_flagged():
    """insert_total ≠ Σ各图层 INSERT → 如实报失步。"""
    dls = _dls()
    rep = _consistent_report()
    rep["insert_total"] = 99
    res = dls.verify_dwg_scan_report(rep)
    assert res["ok"] is False
    assert any("insert_total" in it for it in res["issues"])


def test_entity_total_mismatch_flagged():
    """entity_type_totals 某类型值 ≠ Σ各图层该类型 → 如实报失步。"""
    dls = _dls()
    rep = _consistent_report()
    rep["entity_type_totals"]["LINE"] = 99  # 谎报
    res = dls.verify_dwg_scan_report(rep)
    assert res["ok"] is False
    assert any("LINE" in it for it in res["issues"])


def test_negative_attrib_tag_flagged():
    """attrib_tags 出现负计数 (篡改) → 如实揪出。"""
    dls = _dls()
    rep = _consistent_report()
    rep["attrib_tags"]["BAD"] = -1
    res = dls.verify_dwg_scan_report(rep)
    assert res["ok"] is False
    assert any("负计数" in it or "BAD" in it for it in res["issues"])


def test_malformed_report_no_crash():
    """report 非 dict / layers 非 dict / 条非 dict → 优雅降级不崩。"""
    dls = _dls()
    assert dls.verify_dwg_scan_report("not-dict")["ok"] is False
    rep = _consistent_report()
    rep["layers"] = "not-dict"
    assert dls.verify_dwg_scan_report(rep)["ok"] is False
    rep2 = _consistent_report()
    rep2["layers"]["WALL"] = "not-dict"
    assert dls.verify_dwg_scan_report(rep2)["ok"] is False


def test_empty_report_ok():
    """空报告 (扫不出任何图层, scan_dwg 诚实空态) → 合法, 不误报。"""
    dls = _dls()
    rep = dls._empty_report()
    assert dls.verify_dwg_scan_report(rep)["ok"] is True


# ─── ② 真实样本 + bridge 端点 ─────────────────────────────────


def test_real_electrical_sample_report_self_consistent():
    """真实 electrical_sample.dxf 扫出的报告本身应自洽 (scan_dwg 正确的前提下)。"""
    dls = _dls()
    rep = dls.scan_sample_reader("electrical_sample.dxf", project_root)
    assert rep.get("layer_count", 0) > 0, "真实样本应扫出图层, 否则测试前提不成立"
    res = dls.verify_dwg_scan_report(rep)
    assert res["ok"] is True, f"真实 scan_dwg 产物应自洽, 得 {res['issues']}"


def test_bridge_dwg_scan_exposes_scan_consistent():
    """/api/dwg-scan 透出 scan_consistent/scan_issues 诊断字段 (端点 200 + 契约)。"""
    from fastapi.testclient import TestClient
    from src.gui.bridge import app
    with TestClient(app) as client:
        resp = client.get("/api/dwg-scan?sample=electrical_sample.dxf")
        assert resp.status_code == 200, f"应 200, 实际 {resp.status_code}"
        body = resp.json()
        assert "scan_consistent" in body and "scan_issues" in body
        # 真实样本自洽 (与 test_real_electrical_sample_report_self_consistent 同源)
        assert body["scan_consistent"] is True


if __name__ == "__main__":
    # 只跑无 pytest fixture 依赖的用例 (test_direct_run 会直跑 __main__ 块)
    test_consistent_report_ok()
    test_layer_count_mismatch_flagged()
    test_insert_total_mismatch_flagged()
    test_entity_total_mismatch_flagged()
    test_negative_attrib_tag_flagged()
    test_malformed_report_no_crash()
    test_empty_report_ok()
    test_real_electrical_sample_report_self_consistent()
    test_bridge_dwg_scan_exposes_scan_consistent()
    print("OK: all verify_dwg_scan_report tests passed")

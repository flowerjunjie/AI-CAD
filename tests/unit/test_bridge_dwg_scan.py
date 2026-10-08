"""
M2 制图约定对齐端点测试 — bridge /api/dwg-scan (扫 DWG → 图层/块名/ATTRIB 频率报告)

验证 bridge I 段: 端点接住了 dwg_layer_scan 机制 (CLI 工具 → GUI 可见入口),
但**不冒称自动映射** (只报频率, 不判定 kind 归属 — 业务约定留给人)。
诚实两态: 有 DWG 出真报告, 缺/非 DXF → 404 (不崩不造假)。
__main__ 直跑护栏: 只列无 fixture 子集, ASCII print。
"""
import sys
import os
import json

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from fastapi.testclient import TestClient

from src.gui.bridge import app


def test_dwg_scan_electrical_sample():
    """扫电气样例 → 有 ELEC_OUTLET/ELEC_SWITCH 图层 + INSERT 块名 + ATTRIB 报告。"""
    with TestClient(app) as client:
        resp = client.get("/api/dwg-scan", params={"sample": "electrical_sample.dxf"})
    assert resp.status_code == 200, f"电气样例应 200, 实际 {resp.status_code}"
    body = resp.json()
    assert body["layer_count"] >= 1, f"应扫出图层, 实际 {body['layer_count']}"
    layers = set(body["layers"])
    assert "ELEC_OUTLET" in layers or "ELEC_SWITCH" in layers, f"应有电气图层, 实际 {layers}"
    assert body["insert_total"] >= 1, "电气样例应含 INSERT"
    assert body["available_samples"], "应列出可用样例 (专家切换)"
    assert "note" in body, "应诚实标注『不判定 kind 归属』"
    print("PASS test_dwg_scan_electrical_sample")


def test_dwg_scan_missing_sample_404():
    """不存在的 sample → 404 诚实报错, 不崩不造假。"""
    with TestClient(app) as client:
        resp = client.get("/api/dwg-scan", params={"sample": "no_such.dxf"})
    assert resp.status_code == 404, f"缺样本应 404, 实际 {resp.status_code}"
    assert "样本不存在" in resp.json()["detail"]
    print("PASS test_dwg_scan_missing_sample_404")


def test_dwg_scan_non_dxf_404():
    """非 DXF 文件 (residential_100sqm.json) → 404, 诚实拒绝 (scan 只认 DWG)。"""
    with TestClient(app) as client:
        resp = client.get("/api/dwg-scan", params={"sample": "residential_100sqm.json"})
    assert resp.status_code == 404, f"非 DXF 应 404, 实际 {resp.status_code}"
    print("PASS test_dwg_scan_non_dxf_404")


def test_dwg_scan_does_not_judge_kind():
    """诚实边界: 报告只含频率 + 图层/块名清单, **不**含 kind 归属判定。
    避免端点冒称「自动映射图层→元素种类」(那是业务约定, 留给人回填映射 dict)。"""
    with TestClient(app) as client:
        resp = client.get("/api/dwg-scan", params={"sample": "structural_sample.dxf"})
    assert resp.status_code == 200
    body = resp.json()
    # 报告里不该有「kind」判定字段 (只报频率, 不判归属)
    for layer, info in body["layers"].items():
        assert "kind" not in info, f"图层 {layer} 报告不该含 kind 归属判定"
        assert "block_names" in info, f"图层 {layer} 应含块名清单"
    print("PASS test_dwg_scan_does_not_judge_kind")


def test_dwg_scan_consistent_diagnostic_surfaced():
    """P12 同类收口: /api/dwg-scan 透出自洽诊断 (verify_dwg_scan_report 结果),
    前端 DwgScanSection 消费 scan_consistent 显式「失步才示警」。
    自产报告 (扫真样本) 恒自洽 → scan_consistent=true / scan_issues 空, 不虚标。
    护栏钉死「后端真透出该字段」— 否则前端 interface 声明了却收不到, 又是黑洞。"""
    with TestClient(app) as client:
        resp = client.get("/api/dwg-scan", params={"sample": "electrical_sample.dxf"})
    assert resp.status_code == 200
    body = resp.json()
    assert "scan_consistent" in body, "端点未透出自洽诊断字段 (前端 interface 声明了却收不到)"
    assert body["scan_consistent"] is True, f"自产报告应自洽, 实际 {body.get('scan_issues')}"
    assert body["scan_issues"] == []
    print("PASS test_dwg_scan_consistent_diagnostic_surfaced")


if __name__ == "__main__":
    test_dwg_scan_electrical_sample()
    test_dwg_scan_missing_sample_404()
    test_dwg_scan_non_dxf_404()
    test_dwg_scan_does_not_judge_kind()
    test_dwg_scan_consistent_diagnostic_surfaced()
    print("OK: all dwg-scan endpoint tests passed")

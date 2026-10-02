"""
M2 图层/块名扫描工具单元测试 (dwg_layer_scan)

仿 test_clash_detection 纯函数范式: 用真实 sample DXF 验图层/块名/ATTRIB 频率
报告, 覆盖 ① 真实 DXF 命中 ② 空 reader (doc=None) 诚实空态 ③ 稳定性 (同输入
同输出)。__main__ 只列无 fixture 子集 (全量 pytest 直跑护栏)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _scan(sample: str):
    from src.agents.src.tools.dwg_layer_scan import scan_sample_reader
    return scan_sample_reader(sample, project_root)


def test_scan_electrical_sample_has_layers_and_blocks():
    """电气样例 DWG: 应扫出 ELEC_OUTLET/ELEC_SWITCH 图层 + INSERT 块名。"""
    rep = _scan("electrical_sample.dxf")
    assert rep["layer_count"] >= 1, f"应扫出图层, 实际 {rep['layer_count']}"
    layers = set(rep["layers"])
    assert "ELEC_OUTLET" in layers or "ELEC_SWITCH" in layers, f"应有电气图层, 实际 {layers}"
    assert rep["insert_total"] >= 1, "电气样例应含 INSERT 块"
    # 每个含 INSERT 的图层 block_names 非空 (块名频率报告核心)
    for layer, info in rep["layers"].items():
        if any(info["entity_counts"].get(t, 0) > 0 for t in ("INSERT",)):
            assert info["block_names"], f"图层 {layer} 有 INSERT 但 block_names 空"
    print("PASS test_scan_electrical_sample_has_layers_and_blocks")


def test_scan_structural_sample_reports_beam_layer():
    """结构样例 DWG: 梁/柱图层 + 块名应被报告 (即使含线段, 图层统计不丢)。"""
    rep = _scan("structural_sample.dxf")
    assert rep["layer_count"] >= 1
    layer_names = set(rep["layers"])
    assert any("BEAM" in l or "COLUMN" in l for l in layer_names), \
        f"结构样例应有梁/柱图层, 实际 {layer_names}"
    # entity_type_totals 应含 LINE 或 INSERT (样例至少有一种几何)
    assert rep["entity_type_totals"], "实体类型统计不应全空"
    print("PASS test_scan_structural_sample_reports_beam_layer")


def test_scan_missing_sample_returns_honest_empty():
    """缺文件 → 诚实空报告 (不崩不造假), 与「没数据」vs「错了」区分一致。"""
    rep = _scan("no-such-sample.dxf")
    assert rep["layer_count"] == 0 and rep["insert_total"] == 0
    assert rep.get("note"), "空态应诚实标注来源"
    print("PASS test_scan_missing_sample_returns_honest_empty")


def test_scan_empty_reader_returns_empty_report():
    """reader.doc=None (未 open) → 空报告, 不调用 msp.query。"""
    from src.agents.src.tools.dwg_layer_scan import scan_dwg
    import types
    fake = types.SimpleNamespace(doc=None)
    rep = scan_dwg(fake)
    assert rep["layers"] == {} and rep["layer_count"] == 0
    assert rep.get("note")
    print("PASS test_scan_empty_reader_returns_empty_report")


def test_scan_deterministic_stable_ordering():
    """同输入两次扫描 → 完全一致 (块名按频率降序 + 同频按名序, 可复现)。"""
    a = _scan("electrical_sample.dxf")
    b = _scan("electrical_sample.dxf")
    assert a == b, "同输入应产出同报告 (稳定排序)"
    print("PASS test_scan_deterministic_stable_ordering")


if __name__ == "__main__":
    test_scan_electrical_sample_has_layers_and_blocks()
    test_scan_structural_sample_reports_beam_layer()
    test_scan_missing_sample_returns_honest_empty()
    test_scan_empty_reader_returns_empty_report()
    test_scan_deterministic_stable_ordering()
    print("OK: all dwg_layer_scan tests passed")

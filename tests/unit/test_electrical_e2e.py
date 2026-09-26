"""电气专业端到端测试: 造 DWG → 读 → 抽 → 规则引擎 → 断言。

链路 (全真实调用, 无 mock):
  DXFReader.open() → get_electrical_points()
  → extract_electrical_points() → DslRuleProvider(default.json).upsert_into(RuleEngine())
  → engine.check(elems)

断言目标 (对应 data/sample/electrical_sample.dxf 的 3 个点位):
  - OUTLET_HI 高位插座 2.5m → 命中 electrical-outlet-height-range (超默认上限 2.0)
  - OUTLET_GND 厨卫无接地 kitchen + has_earthing=false
        → 命中 electrical-outlet-earthing-required
  - SWITCH_OK 合规开关 1.3m → 在 switch 区间 [1.2,1.4] 内, 不违规
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 样本 DXF 路径 (由 data/sample/make_electrical_sample_dxf.py 生成)
SAMPLE_DXF = os.path.join(project_root, "data", "sample", "electrical_sample.dxf")
DEFAULT_JSON = os.path.join(project_root, "src", "rules", "rules", "default.json")


def _ensure_sample() -> None:
    """样本 DWG 不存在则先造 (幂等), 保证 e2e 可独立直跑。

    data/sample 非 Python 包 (无 __init__), 故按路径动态加载造样脚本。
    """
    if not os.path.isfile(SAMPLE_DXF):
        import importlib.util

        script = os.path.join(os.path.dirname(SAMPLE_DXF), "make_electrical_sample_dxf.py")
        spec = importlib.util.spec_from_file_location("make_electrical_sample_dxf", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.build_sample_dxf()


def _run() -> tuple[list, list]:
    """跑全链路, 返回 (elems, violations)。"""
    from src.agents.src.tools.cad_tools import DXFReader
    from src.agents.src.tools.electrical_extractor import extract_electrical_points
    from src.rules.src.engine import RuleEngine
    from src.rules.src.dsl import DslRuleProvider

    _ensure_sample()
    reader = DXFReader(SAMPLE_DXF)
    assert reader.open(), f"样本 DXF 打开失败: {SAMPLE_DXF}"
    points = reader.get_electrical_points()
    assert len(points) == 3, f"样本应 3 点位, 实际 {len(points)}: {[p['id'] for p in points]}"

    elems = extract_electrical_points(points)
    engine = RuleEngine()
    DslRuleProvider(DEFAULT_JSON).upsert_into(engine)
    violations = engine.check(elems)
    return elems, violations


def _by_id(elems: list, elem_id: str):
    return next((e for e in elems if e.id == elem_id), None)


def test_sample_dxf_exists():
    """样本 DWG 必须已生成 (缺则先造)。"""
    _ensure_sample()
    assert os.path.isfile(SAMPLE_DXF), f"缺样本 {SAMPLE_DXF}"


def test_e2e_high_outlet_hits_height_range():
    """高位插座 2.5m 命中 electrical-outlet-height-range, 且高度违规仅此一个点位。"""
    elems, violations = _run()
    hi = _by_id(elems, "OUTLET_HI")
    assert hi is not None, f"应读到 OUTLET_HI 点位, 实际 {[e.id for e in elems]}"
    assert hi.height_m == 2.5, f"OUTLET_HI 高度应 2.5 (块属性通道), 实际 {hi.height_m}"

    hits = [v for v in violations if v.rule_id == "electrical-outlet-height-range"]
    assert len(hits) == 1, f"高度违规应恰 1 条, 实际 {len(hits)}: {[v.element_id for v in hits]}"
    assert hits[0].element_id == "OUTLET_HI", \
        f"高度违规应指向 OUTLET_HI, 实际 {hits[0].element_id}"


def test_e2e_kitchen_ungrounded_hits_earthing():
    """厨卫无接地插座命中 electrical-outlet-earthing-required, 且接地违规仅此一个点位。"""
    elems, violations = _run()
    gnd = _by_id(elems, "OUTLET_GND")
    assert gnd is not None, f"应读到 OUTLET_GND 点位, 实际 {[e.id for e in elems]}"
    assert gnd.room_type == "kitchen", f"OUTLET_GND 房间应 kitchen, 实际 {gnd.room_type}"
    assert gnd.has_earthing is False, f"OUTLET_GND has_earthing 应 False, 实际 {gnd.has_earthing}"

    hits = [v for v in violations if v.rule_id == "electrical-outlet-earthing-required"]
    assert len(hits) == 1, f"接地违规应恰 1 条, 实际 {len(hits)}: {[v.element_id for v in hits]}"
    assert hits[0].element_id == "OUTLET_GND", \
        f"接地违规应指向 OUTLET_GND, 实际 {hits[0].element_id}"


def test_e2e_compliant_switch_passes_all_rules():
    """合规开关 1.3m 在 switch 区间内, 3 条电气规则全过 — 该过的过。"""
    elems, violations = _run()
    sw = _by_id(elems, "SWITCH_OK")
    assert sw is not None, f"应读到 SWITCH_OK 点位, 实际 {[e.id for e in elems]}"
    assert sw.height_m == 1.3, f"SWITCH_OK 高度应 1.3 (块属性通道), 实际 {sw.height_m}"
    assert not any(v.element_id == "SWITCH_OK" for v in violations), \
        f"合规开关 1.3m 不应违规, 实际 {[v.rule_id for v in violations if v.element_id == 'SWITCH_OK']}"


def test_e2e_clean_segments_pass_remaining_rules():
    """该过的过: 非违规点位 (厨房低位 0.3m 插座高度合规) 相关规则零命中。"""
    elems, violations = _run()
    # OUTLET_GND 高度 0.3m 在 outlet 区间 [0,2] 内 → 高度规则不应命中它
    assert not any(v.rule_id == "electrical-outlet-height-range"
                   and v.element_id == "OUTLET_GND" for v in violations), \
        "OUTLET_GND 高度 0.3m 合规, 不应命中高度规则"
    # OUTLET_HI 房间 living 且默认接地 → 接地规则不应命中它
    assert not any(v.rule_id == "electrical-outlet-earthing-required"
                   and v.element_id == "OUTLET_HI" for v in violations), \
        "OUTLET_HI (living + 默认接地) 不应命中接地规则"
    # 全量电气违规: 恰是 2 个坏点, 各 1 条, 不串报
    elec = [v for v in violations if v.rule_id.startswith("electrical-")]
    assert len(elec) == 2, f"电气违规应恰 2 条 (高度 1 + 接地 1), 实际 {len(elec)}: " \
                           f"{[(v.rule_id, v.element_id) for v in elec]}"


if __name__ == "__main__":
    test_sample_dxf_exists()
    test_e2e_high_outlet_hits_height_range()
    test_e2e_kitchen_ungrounded_hits_earthing()
    test_e2e_compliant_switch_passes_all_rules()
    test_e2e_clean_segments_pass_remaining_rules()
    print("\nElectrical E2E tests passed!")

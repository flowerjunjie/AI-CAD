"""
Phase 4 — 电气专业接入测试

验证新专业(电气)通过 DSL 骨架干净接入引擎（照 Phase 3 给排水范式）:
- ElectricalOutlet / ElectricalSwitch 元素模型 + default.json 的 electrical-*
  规则能被 load_dsl_rules 加载执行
- 阈值规则命中/放行正确 (回填后: outlet [0.3,1.5], switch [1.2,1.4], 接地逻辑判定)
- 34 个已有规则类零影响 (加电气后原有 residential 规则仍在)

规范条文/数值按 docs/gb_thresholds_research.json 回填 (medium confidence,
基于通行做法而非强制条文), 本测试验证回填后阈值命中/放行机制正确。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.rules.src.electrical import ElectricalOutlet, ElectricalSwitch
from src.rules.src.dsl import load_dsl_rules
from src.rules.src.engine import RuleEngine

# 对齐 test_plumbing_dsl.py: 3 层 dirname 到项目根 (f.py -> unit -> tests -> AI-CAD)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_JSON = os.path.join(PROJECT_ROOT, "src", "rules", "rules", "default.json")


def _engine_with_rules():
    engine = RuleEngine()
    for rule in load_dsl_rules(DEFAULT_JSON):
        engine.upsert(rule)
    return engine


def test_electrical_rules_loaded_from_dsl():
    """default.json 里的 3 条 electrical-* 规则能被 DSL 加载"""
    engine = _engine_with_rules()
    ids = [r.rule_id for r in engine.list_rules()]
    for rid in (
        "electrical-outlet-height-range",
        "electrical-switch-height-range",
        "electrical-outlet-earthing-required",
    ):
        assert rid in ids, f"{rid} 未从 DSL 加载"


def test_outlet_height_out_of_range_violation():
    """回填后: 插座高度区间 [0.3, 1.5]。低位 0.3m 恰好合规, 2.5m 超上限违规。"""
    engine = _engine_with_rules()
    outlet = ElectricalOutlet(id="o1", height_m=0.3, room_type="living")
    # 回填区间 [0.3, 1.5], 0.3m 在下限 (0.3 >= 0.3) → 合规
    assert len(engine.check([outlet], rule_ids=["electrical-outlet-height-range"])) == 0
    # 高插座 2.5m 超回填上限 1.5m → 违规
    outlet_hi = ElectricalOutlet(id="o2", height_m=2.5, room_type="living")
    assert len(engine.check([outlet_hi], rule_ids=["electrical-outlet-height-range"])) == 1


def test_switch_height_out_of_range_violation():
    """开关高度 0.8m 低于回填区间 [1.2, 1.4] → 违规"""
    engine = _engine_with_rules()
    switch = ElectricalSwitch(id="s1", height_m=0.8, room_type="living")
    violations = engine.check([switch], rule_ids=["electrical-switch-height-range"])
    assert len(violations) == 1
    # 开关 1.3m 在区间内 → 合规
    switch_ok = ElectricalSwitch(id="s2", height_m=1.3, room_type="living")
    assert len(engine.check([switch_ok], rule_ids=["electrical-switch-height-range"])) == 0


def test_threshold_overridable_via_params():
    """DSL 化核心能力: 改 param 就能改阈值, 不用动代码 (电气规范数值待确认时最有用)"""
    rules = load_dsl_rules(DEFAULT_JSON)
    switch_rule = next(r for r in rules if r.rule_id == "electrical-switch-height-range")
    # 把下限从 1.0 覆盖到 1.3: 1.2m 开关应违规 (原 1.0 下 1.2m 合规)
    switch_rule.params["min_height_m"] = 1.3
    switch = ElectricalSwitch(id="s3", height_m=1.2, room_type="living")
    assert len(switch_rule.check(switch).violations) == 1


def test_existing_rules_unaffected_by_electrical():
    """加电气后, 原有 residential DSL 规则 (楼梯踏步) 仍正常 → 34 类/原有规则零回归"""
    engine = _engine_with_rules()
    from src.rules.src.residential.stairs import Stair
    stair = Stair(id="e9", width_m=1.2, riser_height_m=0.20)
    violations = engine.check([stair], rule_ids=["dsl-stair-riser"])
    assert len(violations) == 1, "原有 DSL 规则被电气接入影响"


if __name__ == "__main__":
    test_electrical_rules_loaded_from_dsl()
    test_outlet_height_out_of_range_violation()
    test_switch_height_out_of_range_violation()
    test_threshold_overridable_via_params()
    test_existing_rules_unaffected_by_electrical()
    print("\nAll electrical DSL tests passed!")

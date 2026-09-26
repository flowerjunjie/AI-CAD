"""
Phase 5 — 暖通 (HVAC) 专业接入测试

验证新专业(暖通)通过 DSL 骨架干净接入引擎（照 Phase 3 给排水 / Phase 4 电气范式）:
- HvacDuct / HvacUnit / HvacGrille 元素模型 + default.json 的 hvac-*
  规则能被 load_dsl_rules 加载执行
- 阈值占位规则命中/放行正确 (用 param 覆盖验证 DSL 化的核心能力)
- 34 个已有规则类零影响 (加暖通后原有 residential 规则仍在)

规范条文/数值为占位 (TBD), 本测试只验证"接入机制"正确, 不验证数值业务正确性。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.rules.src.hvac import HvacDuct, HvacUnit, HvacGrille
from src.rules.src.dsl import load_dsl_rules
from src.rules.src.engine import RuleEngine

# 对齐 test_electrical_dsl.py: 3 层 dirname 到项目根 (f.py -> unit -> tests -> AI-CAD)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_JSON = os.path.join(PROJECT_ROOT, "src", "rules", "rules", "default.json")


def _engine_with_rules():
    engine = RuleEngine()
    for rule in load_dsl_rules(DEFAULT_JSON):
        engine.upsert(rule)
    return engine


def test_hvac_rules_loaded_from_dsl():
    """default.json 里的 3 条 hvac-* 规则能被 DSL 加载"""
    engine = _engine_with_rules()
    ids = [r.rule_id for r in engine.list_rules()]
    for rid in (
        "hvac-duct-velocity-range",
        "hvac-unit-outdoor-placement",
        "hvac-grille-height-range",
    ):
        assert rid in ids, f"{rid} 未从 DSL 加载"


def test_duct_velocity_out_of_range_violation():
    """风速 12.0 m/s 超上限 10.0 → 违规 (上限已按专家回填从 8.0 放宽到 10.0)"""
    engine = _engine_with_rules()
    duct = HvacDuct(id="d1", duct_type="supply", diameter_mm=100,
                    airflow_m3h=500.0, velocity_ms=12.0)
    violations = engine.check([duct], rule_ids=["hvac-duct-velocity-range"])
    assert len(violations) == 1
    # 风速 4.0 m/s 在区间 [1.5, 10.0] 内 → 合规
    duct_ok = HvacDuct(id="d2", duct_type="supply", diameter_mm=100,
                       airflow_m3h=500.0, velocity_ms=4.0)
    assert len(engine.check([duct_ok], rule_ids=["hvac-duct-velocity-range"])) == 0


def test_outdoor_unit_in_indoor_violation():
    """室外机组装在室内 → 违规"""
    engine = _engine_with_rules()
    unit = HvacUnit(id="u1", unit_type="outdoor", cooling_kw=3.5,
                    location_type="indoor")
    assert len(engine.check([unit], rule_ids=["hvac-unit-outdoor-placement"])) == 1
    # 室外机组装室外 → 合规
    unit_ok = HvacUnit(id="u2", unit_type="outdoor", cooling_kw=3.5,
                       location_type="outdoor")
    assert len(engine.check([unit_ok], rule_ids=["hvac-unit-outdoor-placement"])) == 0


def test_grille_height_out_of_range_violation():
    """风口高度 1.0m 低于占位下限 2.0m → 违规"""
    engine = _engine_with_rules()
    grille = HvacGrille(id="g1", grille_type="supply", height_m=1.0)
    violations = engine.check([grille], rule_ids=["hvac-grille-height-range"])
    assert len(violations) == 1
    # 风口高度 2.5m 在区间内 → 合规
    grille_ok = HvacGrille(id="g2", grille_type="supply", height_m=2.5)
    assert len(engine.check([grille_ok], rule_ids=["hvac-grille-height-range"])) == 0


def test_threshold_overridable_via_params():
    """DSL 化核心能力: 改 param 就能改阈值, 不用动代码 (暖通规范数值待确认时最有用)"""
    rules = load_dsl_rules(DEFAULT_JSON)
    duct_rule = next(r for r in rules if r.rule_id == "hvac-duct-velocity-range")
    # 把上限从 8.0 覆盖到 5.0: 6.0 m/s 应违规 (原 8.0 上限下合规)
    duct_rule.params["max_velocity_ms"] = 5.0
    duct = HvacDuct(id="d3", duct_type="supply", diameter_mm=100,
                    airflow_m3h=500.0, velocity_ms=6.0)
    assert len(duct_rule.check(duct).violations) == 1


def test_existing_rules_unaffected_by_hvac():
    """加暖通后, 原有 residential DSL 规则 (楼梯踏步) 仍正常 → 34 类/原有规则零回归"""
    engine = _engine_with_rules()
    from src.rules.src.residential.stairs import Stair
    stair = Stair(id="h9", width_m=1.2, riser_height_m=0.20)
    violations = engine.check([stair], rule_ids=["dsl-stair-riser"])
    assert len(violations) == 1, "原有 DSL 规则被暖通接入影响"


if __name__ == "__main__":
    test_hvac_rules_loaded_from_dsl()
    test_duct_velocity_out_of_range_violation()
    test_outdoor_unit_in_indoor_violation()
    test_grille_height_out_of_range_violation()
    test_threshold_overridable_via_params()
    test_existing_rules_unaffected_by_hvac()
    print("\nAll hvac DSL tests passed!")

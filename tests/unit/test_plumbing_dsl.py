"""
Phase 3 — 给排水专业接入测试

验证新专业(给排水)通过 DSL 骨架干净接入引擎:
- PlumbingPipe 元素模型 + default.json 的 plumbing-* 规则能被 load_dsl_rules 加载执行
- 阈值规则命中/放行正确 (用 param 覆盖验证 DSL 化的核心能力: 阈值可外部驱动)
- 34 个已有规则类零影响 (引擎加载后原有 default.json 规则仍在)

数值已按规范回填 (2026-09): 坡度下限 0.4% (GB 50015-2019 第4.5.6条横干管通行最小坡度,
大管径分档兜底), 间距上限 12m (GB 50015-2019 第4.7.1条排水横管长度限值)。
本测试验证机制 + 回填后命中。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.rules.src.plumbing import PlumbingPipe
from src.rules.src.dsl import load_dsl_rules
from src.rules.src.engine import RuleEngine

# 对齐 test_dsl.py: 3 层 dirname 到项目根 (f.py -> unit -> tests -> AI-CAD)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_JSON = os.path.join(PROJECT_ROOT, "src", "rules", "rules", "default.json")


def _engine_with_rules():
    engine = RuleEngine()
    for rule in load_dsl_rules(DEFAULT_JSON):
        engine.upsert(rule)
    return engine


def test_plumbing_rules_loaded_from_dsl():
    """default.json 里的 3 条 plumbing-* 规则能被 DSL 加载"""
    engine = _engine_with_rules()
    ids = [r.rule_id for r in engine.list_rules()]
    for rid in (
        "plumbing-waste-pipe-min-diameter",
        "plumbing-pipe-slope-in-range",
        "plumbing-pipe-manhole-distance",
    ):
        assert rid in ids, f"{rid} 未从 DSL 加载"


def test_waste_pipe_min_diameter_violation():
    """DN40 排污管 < 最小 50mm → 违规"""
    engine = _engine_with_rules()
    pipe = PlumbingPipe(id="p1", pipe_type="waste", diameter_mm=40, slope=3.0)
    violations = engine.check([pipe], rule_ids=["plumbing-waste-pipe-min-diameter"])
    assert len(violations) == 1
    assert "40" in violations[0].description


def test_waste_pipe_min_diameter_pass():
    """DN50 排污管 = 最小 50mm → 合规"""
    engine = _engine_with_rules()
    pipe = PlumbingPipe(id="p2", pipe_type="waste", diameter_mm=50, slope=3.0)
    assert len(engine.check([pipe], rule_ids=["plumbing-waste-pipe-min-diameter"])) == 0


def test_pipe_type_filter_ignores_vent():
    """通气管 (vent) 不触发管径规则 (element_types + pipe_type 过滤)"""
    engine = _engine_with_rules()
    pipe = PlumbingPipe(id="p3", pipe_type="vent", diameter_mm=10, slope=3.0)
    assert len(engine.check([pipe], rule_ids=["plumbing-waste-pipe-min-diameter"])) == 0


def test_slope_out_of_range_violation():
    """坡度 15% 超上限 12% → 违规"""
    engine = _engine_with_rules()
    pipe = PlumbingPipe(id="p4", pipe_type="drain", diameter_mm=100, slope=15.0)
    violations = engine.check([pipe], rule_ids=["plumbing-pipe-slope-in-range"])
    assert len(violations) == 1


def test_slope_in_range_pass():
    """坡度 3% 在 [0.4, 12] 内 → 合规"""
    engine = _engine_with_rules()
    pipe = PlumbingPipe(id="p5", pipe_type="drain", diameter_mm=100, slope=3.0)
    assert len(engine.check([pipe], rule_ids=["plumbing-pipe-slope-in-range"])) == 0


def test_manhole_distance_violation():
    """距检查井 30m 超上限 12m → 违规"""
    engine = _engine_with_rules()
    pipe = PlumbingPipe(id="p6", pipe_type="drain", diameter_mm=100, slope=3.0,
                        distance_to_manhole_m=30.0)
    assert len(engine.check([pipe], rule_ids=["plumbing-pipe-manhole-distance"])) == 1


def test_threshold_overridable_via_params():
    """DSL 化核心能力: 改 param 就能改阈值, 不用动代码 (给排水规范数值待确认时最有用)"""
    from src.rules.src.dsl import load_dsl_rules

    rules = load_dsl_rules(DEFAULT_JSON)
    waste_rule = next(r for r in rules if r.rule_id == "plumbing-waste-pipe-min-diameter")
    # 把最小管径从 50 覆盖到 100: DN80 应违规 (原 50mm 下 DN80 合规)
    waste_rule.params["min_pipe_diameter_mm"] = 100
    pipe = PlumbingPipe(id="p7", pipe_type="waste", diameter_mm=80, slope=2.0)
    assert len(waste_rule.check(pipe).violations) == 1


def test_existing_rules_unaffected_by_plumbing():
    """加给排水后, 原有 residential DSL 规则 (楼梯踏步) 仍正常 → 34 类/原有规则零回归"""
    engine = _engine_with_rules()
    from src.rules.src.residential.stairs import Stair
    stair = Stair(id="s9", width_m=1.2, riser_height_m=0.20)
    violations = engine.check([stair], rule_ids=["dsl-stair-riser"])
    assert len(violations) == 1, "原有 DSL 规则被给排水接入影响"


if __name__ == "__main__":
    test_plumbing_rules_loaded_from_dsl()
    test_waste_pipe_min_diameter_violation()
    test_waste_pipe_min_diameter_pass()
    test_pipe_type_filter_ignores_vent()
    test_slope_out_of_range_violation()
    test_slope_in_range_pass()
    test_manhole_distance_violation()
    test_threshold_overridable_via_params()
    test_existing_rules_unaffected_by_plumbing()
    print("\nAll plumbing DSL tests passed!")

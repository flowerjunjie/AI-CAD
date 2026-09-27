"""
Phase 6 — 结构 (Structural) 专业接入测试

验证新专业(结构)通过 DSL 骨架干净接入引擎（照 Phase 3 给排水 / Phase 4 电气 /
Phase 5 暖通范式）:
- StructuralBeam / StructuralColumn 元素模型 + default.json 的 structural-*
  规则能被 load_dsl_rules 加载执行
- 阈值占位规则命中/放行正确 (用 param 覆盖验证 DSL 化的核心能力)
- 已有规则类零回归 (加结构后原有 residential / 其他专业规则仍在)

规范条文/数值为占位 (TBD, code_ref 标 GB 50010 / GB 50011 待确认),
本测试只验证"接入机制"正确, 不验证数值业务正确性。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.rules.src.structural import StructuralBeam, StructuralColumn
from src.rules.src.dsl import load_dsl_rules
from src.rules.src.engine import RuleEngine

# 对齐 test_hvac_dsl.py: 3 层 dirname 到项目根 (f.py -> unit -> tests -> AI-CAD)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
DEFAULT_JSON = os.path.join(PROJECT_ROOT, "src", "rules", "rules", "default.json")


def _engine_with_rules():
    engine = RuleEngine()
    for rule in load_dsl_rules(DEFAULT_JSON):
        engine.upsert(rule)
    return engine


def test_structural_rules_loaded_from_dsl():
    """default.json 里的 4 条 structural-* 规则能被 DSL 加载"""
    engine = _engine_with_rules()
    ids = [r.rule_id for r in engine.list_rules()]
    for rid in (
        "structural-beam-width-depth-ratio",
        "structural-column-min-section",
        "structural-beam-min-height",
        "structural-beam-span-depth-ratio",
    ):
        assert rid in ids, f"{rid} 未从 DSL 加载"


def test_beam_width_depth_ratio_violation():
    """梁深宽比 0.8 (300x240) 低于占位下限 1.5 → 违规"""
    engine = _engine_with_rules()
    beam = StructuralBeam(id="b1", beam_type="main", width_mm=300, depth_mm=240)
    violations = engine.check([beam], rule_ids=["structural-beam-width-depth-ratio"])
    assert len(violations) == 1
    # 深宽比 2.0 (300x600) 在占位区间 [1.5, 4.0] 内 → 合规
    beam_ok = StructuralBeam(id="b2", beam_type="main", width_mm=300, depth_mm=600)
    assert len(engine.check([beam_ok], rule_ids=["structural-beam-width-depth-ratio"])) == 0


def test_column_min_section_violation():
    """框架柱截面短边 250mm 低于占位下限 300mm → 违规"""
    engine = _engine_with_rules()
    col = StructuralColumn(id="c1", column_type="frame", section_mm=250)
    assert len(engine.check([col], rule_ids=["structural-column-min-section"])) == 1
    # 框架柱截面 400mm → 合规
    col_ok = StructuralColumn(id="c2", column_type="frame", section_mm=400)
    assert len(engine.check([col_ok], rule_ids=["structural-column-min-section"])) == 0


def test_column_foundation_exempted():
    """基础 (column_type=foundation) 豁免最小截面检查 → 放行"""
    engine = _engine_with_rules()
    col = StructuralColumn(id="c3", column_type="foundation", section_mm=0)
    assert len(engine.check([col], rule_ids=["structural-column-min-section"])) == 0


def test_threshold_overridable_via_params():
    """DSL 化核心能力: 改 param 就能改阈值, 不用动代码 (结构规范数值待确认时最有用)"""
    rules = load_dsl_rules(DEFAULT_JSON)
    col_rule = next(r for r in rules if r.rule_id == "structural-column-min-section")
    # 把最小截面从 300 覆盖到 500: 400mm 截面柱应违规 (原 300 下限下合规)
    col_rule.params["min_section_mm"] = 500
    col = StructuralColumn(id="c4", column_type="frame", section_mm=400)
    assert len(col_rule.check(col).violations) == 1


def test_beam_min_height_violation():
    """梁最小高度规则: predicate 前置 element.span_m>0, 但 StructuralBeam 现无 span_m。

    现状 (上游未补 span_m): predicate 触发 AttributeError → 规则降级跳过 → 放行 (不误报)。
    这是契约文档 docs/structural-upstream-contract.md 标注的"需上游补 span 字段"前置依赖:
    上游补上 span_m 后本规则才真正生效。此处验证"缺字段时安全放行 + 补齐后按 300mm 下限命中"。
    """
    engine = _engine_with_rules()
    # 梁深 200mm (< 300 下限), 但 span_m 缺失 → 规则安全放行 (不误报)
    beam = StructuralBeam(id="bh1", beam_type="main", width_mm=300, depth_mm=200)
    assert len(engine.check([beam], rule_ids=["structural-beam-min-height"])) == 0
    # 补齐 span_m (模拟上游已补字段) 后, 梁深 200mm < 300mm 下限 → 命中
    beam_active = StructuralBeam(id="bh2", beam_type="main", width_mm=300, depth_mm=200)
    beam_active.span_m = 4.0  # 动态属性模拟上游补齐, 不改元素模型结构
    assert len(engine.check([beam_active], rule_ids=["structural-beam-min-height"])) == 1
    # 合规梁: 深 600mm >= 300mm 下限 → 放行
    beam_ok = StructuralBeam(id="bh3", beam_type="main", width_mm=300, depth_mm=600)
    beam_ok.span_m = 4.0
    assert len(engine.check([beam_ok], rule_ids=["structural-beam-min-height"])) == 0


def test_beam_span_depth_ratio_violation():
    """梁跨高比规则: 依赖 element.span_m (单位换算 span_m*1000/depth_mm)。缺字段安全放行; 补齐后按 [5,20] 拦截。"""
    engine = _engine_with_rules()
    # 缺 span_m → 前置 span_m>0 因 AttributeError 降级 → 放行
    beam_no = StructuralBeam(id="sd1", beam_type="main", width_mm=300, depth_mm=300)
    assert len(engine.check([beam_no], rule_ids=["structural-beam-span-depth-ratio"])) == 0
    # 跨高比 4.0m*1000/600=6.67, 在 [5,20] 内 → 合规
    beam_ok = StructuralBeam(id="sd2", beam_type="main", width_mm=300, depth_mm=600)
    beam_ok.span_m = 4.0
    assert len(engine.check([beam_ok], rule_ids=["structural-beam-span-depth-ratio"])) == 0
    # 跨高比 20m*1000/300=66.7, 超 max 20 → 违规
    beam_bad = StructuralBeam(id="sd3", beam_type="main", width_mm=300, depth_mm=300)
    beam_bad.span_m = 20.0
    assert len(engine.check([beam_bad], rule_ids=["structural-beam-span-depth-ratio"])) == 1
    # 跨高比 4m*1000/1000=4.0, 低于 min 5 → 违规
    beam_shallow = StructuralBeam(id="sd4", beam_type="secondary", width_mm=300, depth_mm=1000)
    beam_shallow.span_m = 4.0
    assert len(engine.check([beam_shallow], rule_ids=["structural-beam-span-depth-ratio"])) == 1


def test_existing_rules_unaffected_by_structural():
    """加结构后, 原有 residential DSL 规则 (楼梯踏步) 仍正常 → 零回归"""
    engine = _engine_with_rules()
    from src.rules.src.residential.stairs import Stair
    stair = Stair(id="s1", width_m=1.2, riser_height_m=0.20)
    violations = engine.check([stair], rule_ids=["dsl-stair-riser"])
    assert len(violations) == 1, "原有 DSL 规则被结构接入影响"


if __name__ == "__main__":
    test_structural_rules_loaded_from_dsl()
    test_beam_width_depth_ratio_violation()
    test_column_min_section_violation()
    test_column_foundation_exempted()
    test_threshold_overridable_via_params()
    test_beam_min_height_violation()
    test_beam_span_depth_ratio_violation()
    test_existing_rules_unaffected_by_structural()
    print("\nAll structural DSL tests passed!")

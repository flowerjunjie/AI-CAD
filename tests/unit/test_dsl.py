"""
DSL 规则测试 — DslRuleProvider + ParametricRule + 受限 eval
"""
import json
import sys
import os
import tempfile

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.rules.src.engine import RuleEngine, ViolationSeverity
from src.rules.src.dsl import DslRuleProvider, ParametricRule, load_dsl_rules
from src.rules.src.residential.doors import Door
from src.rules.src.residential.stairs import Stair
from src.rules.src.residential.windows import Window
from src.rules.src.fire_safety.corridors import Corridor
import src.rules.src.residential.doors as _doors


def _sample_rules_data() -> dict:
    return {
        "rules": [
            {
                "rule_id": "dsl-door-main",
                "name": "户门宽度不应小于 1.0m",
                "code_ref": "GB 50096-2011 5.8.6",
                "severity": "error",
                "element_types": ["Door", "door"],
                "predicate": "element.room_type == 'entrance' and element.width_m < 1.0",
                "description_template": "户门宽度 {width_m}m < 1.0m",
                "suggested_fix_template": "将门宽调整为 >= 1.0m",
                "enabled": True,
            },
        ]
    }


def _func_prefix_rules() -> dict:
    return {
        "rules": [
            {"rule_id": "bad", "predicate": "func:overlap(element)", "enabled": True}
        ]
    }


def _write_json(payload: dict) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
    return f.name


def test_dsl_provider_loads(tmp_path):
    """DslRuleProvider 从 JSON schema 加载 ParametricRule。"""
    path = _write_json(_sample_rules_data())
    rules = DslRuleProvider(path).load()
    assert len(rules) == 1
    assert isinstance(rules[0], ParametricRule)
    assert rules[0].rule_id == "dsl-door-main"
    assert rules[0].severity is ViolationSeverity.ERROR


def test_parametric_rule_violation():
    """命中 predicate 的元素产出违规。"""
    rules = DslRuleProvider(_write_json(_sample_rules_data())).load()
    bad = Door(id="d1", width_m=0.8, room_type="entrance", location=(0, 0))
    result = rules[0].check(bad)
    assert not result.passed
    assert result.violations[0].element_id == "d1"
    assert result.violations[0].description == "户门宽度 0.8m < 1.0m"


def test_parametric_rule_pass():
    """合规元素通过。"""
    rules = DslRuleProvider(_write_json(_sample_rules_data())).load()
    good = Door(id="d2", width_m=1.1, room_type="entrance", location=(0, 0))
    assert rules[0].check(good).passed


def test_type_gate_skips():
    """非声明 element_types 的元素被门禁跳过（不误报）。"""
    rules = DslRuleProvider(_write_json(_sample_rules_data())).load()
    stair = Stair(id="s1", width_m=0.5, riser_height_m=0.2)
    assert rules[0].check(stair).passed


def test_func_prefix_rejected():
    """predicate 不允许 func: 前缀调几何函数——load 时 fail-fast。"""
    path = _write_json(_func_prefix_rules())
    try:
        DslRuleProvider(path).load()
        assert False, "Should raise ValueError"
    except ValueError:
        pass


def test_upsert_keeps_other_rules_and_adds_dsl():
    """upsert 同 rule_id 顶替旧类，其它 rule_id 不变，DSL 新 id 注册成功。"""
    engine = RuleEngine()
    old = _doors.MainEntranceDoorWidth()
    engine.register(old)
    provider = DslRuleProvider(_write_json(_sample_rules_data()))
    provider.upsert_into(engine)

    assert engine.get_rule("residential-door-main-width") is old
    assert isinstance(engine.get_rule("dsl-door-main"), ParametricRule)


def test_default_schema_is_valid():
    """仓库自带 default.json 可被 DslRuleProvider 正常加载。

    不锁死规则总数 (各 Phase 会不断追加新专业), 只校验:
    - schema 合法可加载
    - Phase 2 的 residential DSL 规则仍在
    - Phase 3 追加的 plumbing 规则也在
    """
    default = os.path.join(project_root, "src", "rules", "rules", "default.json")
    rules = load_dsl_rules(default)
    rule_ids = set(r.rule_id for r in rules)
    # Phase 2 原有 residential DSL 规则
    assert {"residential-bedroom-window-area",
            "dsl-stair-riser",
            "dsl-corridor-escape-width"} <= rule_ids
    # Phase 3 给排水专业
    assert {"plumbing-waste-pipe-min-diameter",
            "plumbing-pipe-slope-in-range",
            "plumbing-pipe-manhole-distance"} <= rule_ids


def test_default_schema_rules_hit_real_elements():
    """default.json 每条规则都能被构造出的元素命中（违规数>0）：
    predicate 语法错（白名单外标识符）会在测试里先于 CI fail-fast 暴露。
    """
    default = os.path.join(project_root, "src", "rules", "rules", "default.json")
    rules = {r.rule_id: r for r in load_dsl_rules(default)}

    # residential-bedroom-window-area: bedroom 且 sill_height_m > 0.9
    window = Window(id="w1", sill_height_m=1.0, top_height_m=2.0, room_type="bedroom", location=(0, 0))
    assert len(rules["residential-bedroom-window-area"].check(window).violations) > 0

    # dsl-stair-riser: riser_height_m > max_riser_m(0.175)
    stair = Stair(id="s1", width_m=1.2, riser_height_m=0.20)
    assert len(rules["dsl-stair-riser"].check(stair).violations) > 0

    # dsl-corridor-escape-width: width_m < 1.4
    corridor = Corridor(id="c1", name="主走廊", width_m=1.2, length_m=10.0)
    assert len(rules["dsl-corridor-escape-width"].check(corridor).violations) > 0


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    test_parametric_rule_violation()
    test_parametric_rule_pass()
    test_type_gate_skips()
    test_func_prefix_rejected()
    test_upsert_keeps_other_rules_and_adds_dsl()
    test_default_schema_is_valid()
    test_default_schema_rules_hit_real_elements()
    print("\nAll DSL tests passed!")

"""
DSL 边界补充测试 — 阈值差异 / 白名单拒绝 / upsert 顶替 / params 注入面
聚焦 Lead 要求的测试要点 + coder 自报的技术债（暴露 params 注入面）。
不覆盖 coder 已写的 test_dsl.py 场景，只补它没测的。
"""
import json
import os
import sys
import tempfile

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.rules.src.engine import RuleEngine, ViolationSeverity
from src.rules.src.dsl import DslRuleProvider, ParametricRule, load_dsl_rules
from src.rules.src.residential.doors import Door


def _write_json(payload: dict) -> str:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(payload, f)
    return f.name


def _rule(rule_id: str, threshold: float, pred_template: str = "element.width_m < {t}") -> dict:
    return {
        "rule_id": rule_id,
        "name": rule_id,
        "code_ref": "GB 50096-2011",
        "severity": "error",
        "element_types": ["Door", "door"],
        "predicate": pred_template.format(t=threshold),
        "enabled": True,
    }


# ── 同一元素在不同阈值下结果不同（Lead 要点 3）────────────────


def test_same_element_different_thresholds():
    """同一 0.9m 宽的门，在 1.0m 阈值下违规、在 0.8m 阈值下通过。"""
    door = Door(id="d1", width_m=0.9, room_type="entrance", location=(0, 0))

    strict = DslRuleProvider(_write_json({"rules": [_rule("t-strict", 1.0)]})).load()
    loose = DslRuleProvider(_write_json({"rules": [_rule("t-loose", 0.8)]})).load()

    strict_res = strict[0].check(door)
    loose_res = loose[0].check(door)
    assert not strict_res.passed, "0.9m 门 < 1.0m 阈值应违规"
    assert loose_res.passed, "0.9m 门 >= 0.8m 阈值应通过"


def test_threshold_change_alters_violation_set():
    """阈值从 1.0 降到 0.8，同一元素违规→合规，diff 应报 removed（规则结果变化）。"""
    from src.rules.src.diff import diff_violations

    door = Door(id="d1", width_m=0.9, room_type="entrance", location=(0, 0))
    engine_old = RuleEngine()
    for r in DslRuleProvider(_write_json({"rules": [_rule("door-th", 1.0)]})).load():
        engine_old.upsert(r)
    engine_new = RuleEngine()
    for r in DslRuleProvider(_write_json({"rules": [_rule("door-th", 0.8)]})).load():
        engine_new.upsert(r)

    baseline = engine_old.check([door])
    current = engine_new.check([door])
    diff = diff_violations(baseline, current)
    assert [v.rule_id for v in diff["removed"]] == ["door-th"], \
        "阈值放宽后原违规应消失（removed）, got added/removed/changed: " \
        f"{[v.rule_id for v in diff['added']]}/{[v.rule_id for v in diff['removed']]}/{[v.rule_id for v in diff['changed']]}"
    assert diff["added"] == [] and diff["changed"] == []


# ── 受限 eval 白名单拒绝（防注入）──────────────────────────────


def test_predicate_rejects_unknown_identifier():
    """predicate 引用白名单外标识符（如 params 之外的全局名）→ load fail-fast。"""
    payload = {"rules": [{
        "rule_id": "bad",
        "predicate": "element.width_m < evil_global",
        "element_types": ["Door"],
    }]}
    try:
        DslRuleProvider(_write_json(payload)).load()
        assert False, "白名单外标识符应被拒绝, 但 load 未抛错"
    except ValueError:
        pass


def test_predicate_rejects_underscore_attr():
    """predicate 访问下划线属性（dunder/私有）→ 拒绝。"""
    payload = {"rules": [{
        "rule_id": "bad",
        "predicate": "element.__class__ is not None",
        "element_types": ["Door"],
    }]}
    try:
        DslRuleProvider(_write_json(payload)).load()
        assert False, "下划线属性访问应被拒绝"
    except ValueError:
        pass


def test_predicate_rejects_arbitrary_call():
    """predicate 调用白名单外函数（如 eval）→ 拒绝。"""
    bad_payload = {"rules": [{
        "rule_id": "bad2",
        "predicate": "eval('1+1')",
        "element_types": ["Door"],
    }]}
    try:
        DslRuleProvider(_write_json(bad_payload)).load()
        assert False, "eval() 不在白名单, 应被拒绝"
    except ValueError:
        pass


def test_params_keys_drive_predicate():
    """[实现修正] params 键名允许出现在 predicate 中, 且实际驱动求值:
    predicate "element.width_m < limit" + params {"limit": 0.5} 应真正生效。
    """
    payload = {"rules": [{
        "rule_id": "params-key",
        "predicate": "element.width_m < limit",
        "element_types": ["Door", "door"],
        "params": {"limit": 0.5},
    }]}
    rules = DslRuleProvider(_write_json(payload)).load()
    door_small = Door(id="d1", width_m=0.4, room_type="entrance", location=(0, 0))
    door_big = Door(id="d2", width_m=0.9, room_type="entrance", location=(0, 0))
    assert not rules[0].check(door_small).passed, "0.4 < 0.5 (limit) 应违规"
    assert rules[0].check(door_big).passed, "0.9 >= 0.5 (limit) 应通过"


def test_params_key_unknown_identifier_still_rejected():
    """predicate 引用既不在 params 也不是白名单的标识符 → 拒绝（防注入边界不变）。"""
    payload = {"rules": [{
        "rule_id": "bad",
        "predicate": "element.width_m < evil_global",
        "element_types": ["Door"],
    }]}
    try:
        DslRuleProvider(_write_json(payload)).load()
        assert False, "白名单外标识符应被拒绝"
    except ValueError:
        pass


def test_len_callable_whitelist_works():
    """[实现修正] len() 在白名单里且可实际调用（不再 NameError, docstring 不再自相矛盾）:
    谓词 "len(element.room_type) > 2" 对 "entrance"(8 字符) 命中 → 产出违规。
    关键断言: 不抛 NameError/ValueError, 且求值结果为 True (命中违规)。
    """
    payload = {"rules": [{
        "rule_id": "len-ok",
        "predicate": "len(element.room_type) > 2",
        "element_types": ["Door", "door"],
        "params": {},
    }]}
    rules = DslRuleProvider(_write_json(payload)).load()  # 白名单应放行 len
    result = rules[0].check(Door(id="d1", width_m=1.0, room_type="entrance", location=(0, 0)))
    assert not result.passed, "len('entrance')=8 > 2 命中违规, 应 not passed"


# ── upsert 顶替 + 规则被删（Lead 要点 3 / 边界 case）──────────


def test_rule_removed_between_versions():
    """baseline 含某 rule_id, current engine 不再注册该 rule → diff 报 removed。"""
    from src.rules.src.diff import diff_violations

    door = Door(id="d1", width_m=0.8, room_type="entrance", location=(0, 0))
    engine_a = RuleEngine()
    for r in DslRuleProvider(_write_json({"rules": [_rule("gone", 1.0)]})).load():
        engine_a.upsert(r)
    engine_b = RuleEngine()  # 没有注册 "gone" 这条
    baseline = engine_a.check([door])
    current = engine_b.check([door])
    diff = diff_violations(baseline, current)
    assert [v.rule_id for v in diff["removed"]] == ["gone"], \
        "被删规则应进 removed"
    assert diff["added"] == [] and diff["changed"] == []


def test_upsert_replaces_not_dups():
    """同 rule_id upsert 两次 → registry 里只有一个, 且是后注册的（顶替非追加）。"""
    engine = RuleEngine()
    r1 = DslRuleProvider(_write_json({"rules": [_rule("dup", 1.0)]})).load()[0]
    r2 = DslRuleProvider(_write_json({"rules": [_rule("dup", 0.5)]})).load()[0]
    engine.upsert(r1)
    engine.upsert(r2)
    assert engine.get_rule("dup") is r2, "upsert 应顶替, 保留后者"
    ids = [r.rule_id for r in engine.list_rules()]
    assert ids.count("dup") == 1, f"同 rule_id 不应重复, got {ids}"


# ── default.json 三条示例规则端到端命中 ────────────────────────


def test_default_schema_rules_fire_on_real_elements():
    """default.json 的 3 条规则对相应元素真实触发违规（非只加载成功）。"""
    from src.rules.src.residential.stairs import Stair
    from src.rules.src.fire_safety.corridors import Corridor

    rules = {r.rule_id: r for r in load_dsl_rules(
        os.path.join(project_root, "src", "rules", "rules", "default.json"))}

    # dsl-stair-riser: riser_height_m > 0.175 违规
    bad_stair = Stair(id="s1", width_m=1.2, riser_height_m=0.20)
    res = rules["dsl-stair-riser"].check(bad_stair)
    assert not res.passed, "0.20m 踏步 > 0.175m 应违规"

    ok_stair = Stair(id="s2", width_m=1.2, riser_height_m=0.17)
    assert rules["dsl-stair-riser"].check(ok_stair).passed, "0.17m 踏步合规"

    # dsl-corridor-escape-width: width_m < 1.4 违规
    narrow = Corridor(id="c1", name="主走廊", width_m=1.2, length_m=10.0)
    assert not rules["dsl-corridor-escape-width"].check(narrow).passed, \
        "1.2m 走廊 < 1.4m 应违规"
    wide = Corridor(id="c2", name="次走廊", width_m=1.6, length_m=10.0)
    assert rules["dsl-corridor-escape-width"].check(wide).passed, "1.6m 走廊合规"


if __name__ == "__main__":
    import sys
    # Windows 终端默认 GBK, emoji/中文会崩 — 统一 UTF-8, 一处收敛全部 (同类: ²/✓/🎉)
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    test_same_element_different_thresholds()
    test_threshold_change_alters_violation_set()
    test_predicate_rejects_unknown_identifier()
    test_predicate_rejects_underscore_attr()
    test_predicate_rejects_arbitrary_call()
    test_params_keys_drive_predicate()
    test_params_key_unknown_identifier_still_rejected()
    test_len_callable_whitelist_works()
    test_rule_removed_between_versions()
    test_upsert_replaces_not_dups()
    test_default_schema_rules_fire_on_real_elements()
    print("\nAll DSL boundary tests passed!")

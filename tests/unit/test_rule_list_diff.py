"""
版本对比测试 — 规则清单 diff（设计器改 default.json 后看动了哪些规则）
"""
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.rules.src.diff import diff_rule_lists
from src.rules.src.dsl import DslRuleProvider, load_dsl_rules
from src.rules.src.residential.doors import MainEntranceDoorWidth


def _rules_data(rules) -> dict:
    return {"rules": [
        {
            "rule_id": r["rule_id"],
            "name": r.get("name", ""),
            "severity": r.get("severity", "error"),
            "element_types": r.get("element_types", ["Door", "door"]),
            "predicate": r.get("predicate", "True"),
            "param_defaults": r.get("param_defaults", {}),
            "enabled": r.get("enabled", True),
            "dsl_only": True,
        }
        for r in rules
    ]}


def _write(path, payload) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def test_rule_list_diff_added_removed(tmp_path):
    """new 增删规则 → added / removed 桶。"""
    old = load_dsl_rules(_write(tmp_path / "old.json", _rules_data([
        {"rule_id": "a", "predicate": "element.x > 1"},
        {"rule_id": "b", "predicate": "element.y > 2"},
    ])))
    new = load_dsl_rules(_write(tmp_path / "new.json", _rules_data([
        {"rule_id": "b", "predicate": "element.y > 2"},
        {"rule_id": "c", "predicate": "element.z > 3"},
    ])))
    d = diff_rule_lists(old, new)
    assert [r["rule_id"] for r in d["added"]] == ["c"]
    assert [r["rule_id"] for r in d["removed"]] == ["a"]
    assert d["changed"] == []


def test_rule_list_diff_threshold_change(tmp_path):
    """同 rule_id 的 param_defaults 变了 → changed, 带 from/to。"""
    old = load_dsl_rules(_write(tmp_path / "old.json", _rules_data([
        {"rule_id": "r", "predicate": "element.x > limit", "param_defaults": {"limit": 1.0}},
    ])))
    new = load_dsl_rules(_write(tmp_path / "new.json", _rules_data([
        {"rule_id": "r", "predicate": "element.x > limit", "param_defaults": {"limit": 1.5}},
    ])))
    d = diff_rule_lists(old, new)
    assert len(d["changed"]) == 1
    assert d["changed"][0]["rule_id"] == "r"
    assert d["changed"][0]["fields"]["param_defaults"] == {
        "from": {"limit": 1.0}, "to": {"limit": 1.5}
    }


def test_rule_list_diff_predicate_change(tmp_path):
    """predicate 改了 → changed 桶带 from/to。"""
    old = load_dsl_rules(_write(tmp_path / "old.json", _rules_data([
        {"rule_id": "r", "predicate": "element.x > 1"},
    ])))
    new = load_dsl_rules(_write(tmp_path / "new.json", _rules_data([
        {"rule_id": "r", "predicate": "element.x > 2"},
    ])))
    d = diff_rule_lists(old, new)
    assert len(d["changed"]) == 1
    assert d["changed"][0]["fields"]["predicate"]["from"] == "element.x > 1"
    assert d["changed"][0]["fields"]["predicate"]["to"] == "element.x > 2"


def test_rule_list_diff_identical(tmp_path):
    """两份相同清单 → 三桶全空。"""
    old = load_dsl_rules(_write(tmp_path / "a.json", _rules_data([
        {"rule_id": "r", "predicate": "element.x > 1"},
    ])))
    new = load_dsl_rules(_write(tmp_path / "b.json", _rules_data([
        {"rule_id": "r", "predicate": "element.x > 1"},
    ])))
    d = diff_rule_lists(old, new)
    assert d == {"added": [], "removed": [], "changed": []}


def test_rule_list_diff_hardware_class_vs_dsl(tmp_path):
    """硬编码类无 predicate 概念 vs 同 id 的 DSL 类 → 只报 predicate 差异, 无伪差异。"""
    hw = [MainEntranceDoorWidth()]
    dsl = load_dsl_rules(_write(tmp_path / "d.json", _rules_data([
        {"rule_id": "residential-door-main-width",
         "predicate": "element.room_type == 'entrance' and element.width_m < 1.0",
         "severity": "error"},
    ])))
    d = diff_rule_lists(hw, dsl)
    assert len(d["changed"]) == 1
    # 硬编码类无 predicate 概念, 同 id 的 DSL 覆盖后 predicate 字段应可见
    assert "predicate" in d["changed"][0]["fields"]


if __name__ == "__main__":
    import tempfile
    import pathlib
    with tempfile.TemporaryDirectory() as d:
        test_rule_list_diff_added_removed(pathlib.Path(d))
        test_rule_list_diff_threshold_change(pathlib.Path(d))
        test_rule_list_diff_predicate_change(pathlib.Path(d))
        test_rule_list_diff_identical(pathlib.Path(d))
        test_rule_list_diff_hardware_class_vs_dsl(pathlib.Path(d))
    print("\nAll rule-list diff tests passed!")

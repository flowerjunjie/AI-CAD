"""
批量校验 + 编辑器校验 测试 — Phase 2 规则 DSL 化最小闭环
"""
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.rules.src.engine import RuleEngine, ViolationSeverity
from src.rules.src.batch_check import run_batch_check, BatchCheckReport
from src.rules.src.editor_validate import validate_dsl_json, DslJsonError
from src.rules.src.dsl import (
    DslRuleProvider,
    load_dsl_rules,
    validate_and_load_dsl_rules,
)
from src.rules.src.residential.doors import Door
from src.rules.src.residential.stairs import Stair
from src.rules.src.fire_safety.corridors import Corridor


def _rules_data() -> dict:
    return {
        "rules": [
            {
                "rule_id": "t-door-w",
                "name": "门宽",
                "code_ref": "GB 50096",
                "severity": "error",
                "element_types": ["Door", "door"],
                "predicate": "element.room_type == 'entrance' and element.width_m < 1.0",
                "description_template": "门宽 {width_m}m",
                "suggested_fix_template": "调整到 >= 1.0m",
                "enabled": True,
                "dsl_only": True,
            },
            {
                "rule_id": "t-stair-r",
                "name": "踏步高",
                "code_ref": "GB 50096",
                "severity": "warning",
                "element_types": ["Stair", "stair"],
                "predicate": "element.riser_height_m > max_riser_m",
                "param_defaults": {"max_riser_m": 0.175},
                "description_template": "踏步 {riser_height_m}m",
                "suggested_fix_template": "调整到 <= {max_riser_m}m",
                "enabled": True,
                "dsl_only": True,
            },
        ]
    }


def _write(path, payload) -> str:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False)
    return path


def test_run_batch_check_aggregates(tmp_path):
    """run_batch_check 对一批元素跑启用规则, 按严重级/规则聚合。"""
    rules = load_dsl_rules(_write(tmp_path / "r.json", _rules_data()))
    engine = RuleEngine()
    for r in rules:
        engine.upsert(r)

    elements = [
        Door(id="d1", width_m=0.8, room_type="entrance", location=(0, 0)),  # 命中 door-w
        Door(id="d2", width_m=1.1, room_type="entrance", location=(1, 0)),  # 合规
        Stair(id="s1", width_m=1.2, riser_height_m=0.20),                  # 命中 stair-r
    ]
    report = run_batch_check(elements, engine)
    assert isinstance(report, BatchCheckReport)
    assert report.total == 2
    assert report.error_count == 1
    assert report.warning_count == 1
    assert report.by_rule == {"t-door-w": 1, "t-stair-r": 1}
    assert report.has_errors
    # to_dict 可 JSON 序列化
    assert json.dumps(report.to_dict(), ensure_ascii=False)


def test_run_batch_check_filter_by_rule_ids(tmp_path):
    """rule_ids 过滤只跑指定规则。"""
    rules = load_dsl_rules(_write(tmp_path / "r.json", _rules_data()))
    engine = RuleEngine()
    for r in rules:
        engine.upsert(r)
    elements = [
        Door(id="d1", width_m=0.8, room_type="entrance", location=(0, 0)),
        Stair(id="s1", width_m=1.2, riser_height_m=0.20),
    ]
    report = run_batch_check(elements, engine, rule_ids=["t-door-w"])
    assert report.total == 1
    assert set(report.by_rule) == {"t-door-w"}


def test_validate_dsl_json_clean(tmp_path):
    """合法 JSON → 空错误列表。"""
    p = _write(tmp_path / "ok.json", _rules_data())
    assert validate_dsl_json(p) == []


def test_validate_dsl_json_flags_bad_predicate(tmp_path):
    """predicate 白名单外标识符 → 报错误, 定位到字段。"""
    data = _rules_data()
    data["rules"][0]["predicate"] = "element.width_m < eval('1') "  # eval 不在白名单
    p = _write(tmp_path / "bad.json", data)
    errors = validate_dsl_json(p)
    assert len(errors) == 1
    assert errors[0].rule_index == 0
    assert "predicate" in errors[0].path


def test_validate_dsl_json_flags_func_prefix(tmp_path):
    """func: 前缀调几何函数 → 拒绝（load 会 fail-fast, 校验器要先拦）。"""
    data = {"rules": [{"rule_id": "x", "predicate": "func:overlap(element)"}]}
    p = _write(tmp_path / "fp.json", data)
    errors = validate_dsl_json(p)
    assert len(errors) == 1
    assert "func:" in errors[0].message or "白名单" in errors[0].message


def test_validate_dsl_json_flags_bad_severity(tmp_path):
    """severity 非 error/warning/info → 报错。"""
    data = _rules_data()
    data["rules"][0]["severity"] = "fatal"
    p = _write(tmp_path / "sev.json", data)
    errors = validate_dsl_json(p)
    assert any("severity" in e.path for e in errors)


def test_validate_dsl_json_flags_empty_element_types(tmp_path):
    """element_types 为空 → 报「空=对全部类型放行」错误。"""
    data = _rules_data()
    data["rules"][0]["element_types"] = []
    p = _write(tmp_path / "et.json", data)
    errors = validate_dsl_json(p)
    assert any("element_types" in e.path for e in errors)


def test_validate_dsl_json_multiple_errors_not_shortcircuit(tmp_path):
    """多条错误同时报, 不短路。"""
    data = _rules_data()
    data["rules"][0]["severity"] = "fatal"
    data["rules"][1]["element_types"] = []
    p = _write(tmp_path / "multi.json", data)
    errors = validate_dsl_json(p)
    assert len(errors) >= 2
    assert {e.rule_index for e in errors} == {0, 1}


def test_validate_and_load_roundtrip(tmp_path):
    """合法 → (rules, []); 非法 → ([], errors)。"""
    ok = _write(tmp_path / "ok.json", _rules_data())
    rules, errs = validate_and_load_dsl_rules(ok)
    assert len(rules) == 2 and errs == []

    bad = _write(tmp_path / "bad.json", {"rules": [{"rule_id": "x", "predicate": "func:z()"}]})
    rules, errs = validate_and_load_dsl_rules(bad)
    assert rules == [] and len(errs) == 1


if __name__ == "__main__":
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        import pathlib
        test_run_batch_check_aggregates(pathlib.Path(d))
        test_run_batch_check_filter_by_rule_ids(pathlib.Path(d))
        test_validate_dsl_json_clean(pathlib.Path(d))
        test_validate_dsl_json_flags_bad_predicate(pathlib.Path(d))
        test_validate_dsl_json_flags_func_prefix(pathlib.Path(d))
        test_validate_dsl_json_flags_bad_severity(pathlib.Path(d))
        test_validate_dsl_json_flags_empty_element_types(pathlib.Path(d))
        test_validate_dsl_json_multiple_errors_not_shortcircuit(pathlib.Path(d))
        test_validate_and_load_roundtrip(pathlib.Path(d))
    print("\nAll batch_check / editor_validate tests passed!")

"""
版本对比测试 — baseline 快照存取 + diff 三桶
"""
import json
import sys
import os

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.rules.src.engine import RuleViolation, ViolationSeverity
from src.rules.src.baselines import save_baseline, load_baseline
from src.rules.src.diff import diff_violations


def _v(rule_id, element_id, severity, desc="x") -> RuleViolation:
    return RuleViolation(
        rule_id=rule_id,
        rule_name=rule_id,
        severity=severity,
        description=desc,
        code_ref="REF",
        element_id=element_id,
    )


def test_to_dict_from_dict_roundtrip():
    """RuleViolation.to_dict/from_dict 可 JSON 化且可还原。"""
    v = _v("r1", "e1", ViolationSeverity.ERROR, "door too narrow")
    d = v.to_dict()
    assert d["severity"] == "error"  # 序列化为 .value 字符串
    assert json.dumps(d, ensure_ascii=False)  # 可 JSON 化
    restored = RuleViolation.from_dict(d)
    assert restored.rule_id == "r1"
    assert restored.severity is ViolationSeverity.ERROR
    assert restored.description == "door too narrow"


def test_diff_added_removed(tmp_path):
    """新增 / 消失 / 不变 三桶互斥。"""
    baseline = [_v("a", "e1", ViolationSeverity.ERROR)]
    current = [_v("b", "e2", ViolationSeverity.WARNING)]
    result = diff_violations(baseline, current)
    assert [v.rule_id for v in result["added"]] == ["b"]
    assert [v.rule_id for v in result["removed"]] == ["a"]
    assert result["changed"] == []


def test_diff_changed_severity():
    """同 (rule_id, element_id) 两边都有但 severity 不同 → changed（带 from/to）。"""
    baseline = [_v("r", "e", ViolationSeverity.INFO)]
    current = [_v("r", "e", ViolationSeverity.ERROR)]
    result = diff_violations(baseline, current)
    assert len(result["changed"]) == 1
    assert result["changed"][0].severity is ViolationSeverity.ERROR
    assert result["added"] == []
    assert result["removed"] == []


def test_diff_identity_no_change():
    """两次结果相同 → 三桶全空。"""
    a = [_v("r", "e", ViolationSeverity.ERROR)]
    result = diff_violations(a, [_v("r", "e", ViolationSeverity.ERROR)])
    assert result["added"] == result["removed"] == result["changed"] == []


def test_baseline_save_and_load(tmp_path):
    """save/load baseline 走 data/baselines 路径（显式 tmp_path）。"""
    target = tmp_path / "b.json"
    violations = [_v("r1", "e1", ViolationSeverity.ERROR)]
    save_baseline(violations, "b", path=target)
    loaded = load_baseline("b", path=target)
    assert len(loaded) == 1
    assert loaded[0].severity is ViolationSeverity.ERROR
    assert loaded[0].rule_id == "r1"


def test_baseline_name_rejects_path_traversal():
    """save/load 不显式传 path 时，name 含 .. / 绝对路径 → 拒绝（防路径穿越注入）。"""
    violations = [_v("r1", "e1", ViolationSeverity.ERROR)]
    for evil in ("../evil", "..", "/etc/passwd", "a/b"):
        for fn in (save_baseline, load_baseline):
            try:
                # save_baseline(violations, name) / load_baseline(name) — 签名不同, 分别调
                if fn is save_baseline:
                    fn(violations, evil)
                else:
                    fn(evil)
                assert False, f"路径穿越名 {evil!r} 应被拒, 但 {fn.__name__} 未抛错"
            except ValueError:
                pass


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    test_diff_changed_severity()
    test_diff_identity_no_change()
    test_to_dict_from_dict_roundtrip()
    test_baseline_name_rejects_path_traversal()
    print("\nAll baseline/diff tests passed!")

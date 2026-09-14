"""
版本对比补充测试 — diff 三桶边界 case + baseline 空集往返
聚焦 coder 未覆盖的边界：空 baseline / 全新结果 / severity-only 语义 /
主键 (rule_id, element_id or "") / 确定性。
"""
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from src.rules.src.engine import RuleViolation, ViolationSeverity
from src.rules.src.baselines import save_baseline, load_baseline
from src.rules.src.diff import diff_violations


def _v(rule_id: str, element_id, severity, desc="x", code_ref="REF") -> RuleViolation:
    return RuleViolation(
        rule_id=rule_id,
        rule_name=rule_id,
        severity=severity,
        description=desc,
        code_ref=code_ref,
        element_id=element_id,
    )


# ── diff 三桶边界 ───────────────────────────────────────────────


def test_diff_empty_baseline_all_added():
    """空 baseline + 有 current → 全部进 added，removed/changed 空。"""
    baseline: list[RuleViolation] = []
    current = [_v("r1", "e1", ViolationSeverity.ERROR),
               _v("r2", "e2", ViolationSeverity.WARNING)]
    result = diff_violations(baseline, current)
    assert [v.rule_id for v in result["added"]] == ["r1", "r2"], \
        f"空 baseline 时 current 应全进 added, got {[v.rule_id for v in result['added']]}"
    assert result["removed"] == [], "空 baseline 不可能有 removed"
    assert result["changed"] == [], "空 baseline 不可能有 changed"


def test_diff_empty_current_all_removed():
    """有 baseline + 空 current → 全部进 removed（规则被删 / 问题消失）。"""
    baseline = [_v("r1", "e1", ViolationSeverity.ERROR)]
    result = diff_violations(baseline, [])
    assert [v.rule_id for v in result["removed"]] == ["r1"], \
        f"空 current 时 baseline 应全进 removed, got {[v.rule_id for v in result['removed']]}"
    assert result["added"] == []
    assert result["changed"] == []


def test_diff_both_empty():
    """两边都空 → 三桶全空。"""
    result = diff_violations([], [])
    assert result["added"] == result["removed"] == result["changed"] == []


def test_diff_same_key_same_severity_different_desc_not_changed():
    """主键相同 + severity 相同但 description 变 → 不进任何桶（severity-only 语义）。"""
    baseline = [_v("r", "e", ViolationSeverity.ERROR, desc="旧描述")]
    current = [_v("r", "e", ViolationSeverity.ERROR, desc="新描述")]
    result = diff_violations(baseline, current)
    assert result["added"] == [], "主键相同不应进 added"
    assert result["removed"] == [], "主键相同不应进 removed"
    assert result["changed"] == [], "severity 未变不应进 changed（只看严重度）"


def test_diff_none_element_id_keyed_as_empty():
    """element_id=None 归一到主键 (rule_id, '')，两边 None 视为同一 key。"""
    baseline = [_v("r", None, ViolationSeverity.ERROR)]
    current = [_v("r", None, ViolationSeverity.WARNING)]
    result = diff_violations(baseline, current)
    # 主键都是 ("r", "")，severity 不同 → changed，而非 added+removed
    assert len(result["changed"]) == 1, "两边 element_id=None 应视为同 key, 进 changed"
    assert result["changed"][0].severity is ViolationSeverity.WARNING
    assert result["added"] == result["removed"] == []


def test_diff_changed_reports_from_to():
    """changed 桶里应是 current 侧的 violation（含 to-severity），可展示 from→to。"""
    baseline = [_v("r", "e", ViolationSeverity.INFO)]
    current = [_v("r", "e", ViolationSeverity.ERROR)]
    result = diff_violations(baseline, current)
    assert len(result["changed"]) == 1
    assert result["changed"][0].severity is ViolationSeverity.ERROR, \
        "changed 应报告 current(=to) 的 severity"


def test_diff_deterministic_sorted():
    """多 key 时结果按 (rule_id, element_id) 排序，多次调用稳定一致。"""
    baseline = [_v("r2", "e2", ViolationSeverity.ERROR),
                _v("r1", "e1", ViolationSeverity.ERROR)]
    current = [_v("z", "z", ViolationSeverity.ERROR),
               _v("a", "a", ViolationSeverity.ERROR)]
    r1 = diff_violations(baseline, current)
    r2 = diff_violations(baseline, current)
    assert [v.rule_id for v in r1["added"]] == ["a", "z"], "added 应排序, got 未排序"
    assert [v.rule_id for v in r1["removed"]] == ["r1", "r2"], "removed 应排序"
    assert r1["added"] == r2["added"] and r1["removed"] == r2["removed"], \
        "多次调用结果必须一致（确定性）"


def test_diff_mixed_three_buckets():
    """一次 diff 同时命中三个桶，且互斥（无 key 跨桶出现）。"""
    baseline = [_v("old", "e", ViolationSeverity.ERROR),
                _v("same", "e", ViolationSeverity.INFO)]
    current = [_v("new", "e", ViolationSeverity.ERROR),
               _v("same", "e", ViolationSeverity.ERROR)]
    result = diff_violations(baseline, current)
    assert [v.rule_id for v in result["added"]] == ["new"]
    assert [v.rule_id for v in result["removed"]] == ["old"]
    assert [v.rule_id for v in result["changed"]] == ["same"]
    # 互斥性：same 只在 changed，不在 added/removed
    in_changed = {v.rule_id for v in result["changed"]}
    in_other = {v.rule_id for v in result["added"]} | {v.rule_id for v in result["removed"]}
    assert in_changed.isdisjoint(in_other), "三桶必须互斥, 无 key 跨桶"


# ── RuleViolation 序列化边界 ────────────────────────────────────


def test_violation_roundtrip_none_fields():
    """element_id=None / suggested_fix=None 往返后仍为 None（不丢 None）。"""
    v = RuleViolation(
        rule_id="r", rule_name="n", severity=ViolationSeverity.INFO,
        description="d", code_ref="c", element_id=None, suggested_fix=None,
    )
    restored = RuleViolation.from_dict(v.to_dict())
    assert restored.element_id is None, "None element_id 往返后应保持 None"
    assert restored.suggested_fix is None, "None suggested_fix 往返后应保持 None"
    assert restored.severity is ViolationSeverity.INFO
    assert json.dumps(v.to_dict())  # 可 JSON 化


# ── baseline 空集 ───────────────────────────────────────────────


def test_baseline_empty_roundtrip(tmp_path):
    """保存空 violations 的 baseline → 加载回空列表。"""
    target = tmp_path / "empty.json"
    save_baseline([], "empty", path=target)
    loaded = load_baseline("empty", path=target)
    assert loaded == [], "空 baseline 往返后应为空列表"
    # 文件里 count 应为 0（元数据正确）
    payload = json.loads(target.read_text(encoding="utf-8"))
    assert payload["count"] == 0, "空 baseline 的 count 元数据应为 0"


if __name__ == "__main__":
    import sys
    for _s in (sys.stdout, sys.stderr):
        if hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    test_diff_empty_baseline_all_added()
    test_diff_empty_current_all_removed()
    test_diff_both_empty()
    test_diff_same_key_same_severity_different_desc_not_changed()
    test_diff_none_element_id_keyed_as_empty()
    test_diff_changed_reports_from_to()
    test_diff_deterministic_sorted()
    test_diff_mixed_three_buckets()
    test_violation_roundtrip_none_fields()
    print("\nAll version-diff tests passed!")

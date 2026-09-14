"""
版本对比 — diff 两次 RuleViolation 集合

主键 (rule_id, element_id or "")。产出三桶互斥结果：
  added   — 当前有、baseline 没有（新增违规）
  removed — baseline 有、当前没有（消失违规）
  changed — 两边都有但严重度不同（severity 变化，带 from/to）
"""
from __future__ import annotations

from .engine import RuleViolation


def _key(v: RuleViolation) -> tuple[str, str]:
    return (v.rule_id, v.element_id or "")


def diff_violations(
    baseline: list[RuleViolation],
    current: list[RuleViolation],
) -> dict[str, list[RuleViolation]]:
    """diff 两个 violations 集合，返回 {"added":…, "removed":…, "changed":…}。

    三桶互斥：changed 仅在 (rule_id, element_id) 两边都命中且 severity 不同。
    返回 dict 的 value 是 RuleViolation 对象列表（便于直接展示 from→to）。
    """
    base_map = {_key(v): v for v in baseline}
    curr_map = {_key(v): v for v in current}
    base_keys = set(base_map)
    curr_keys = set(curr_map)

    added = sorted((curr_map[k] for k in (curr_keys - base_keys)), key=_key)
    removed = sorted((base_map[k] for k in (base_keys - curr_keys)), key=_key)
    changed = [
        curr_map[k]
        for k in sorted(base_keys & curr_keys)
        if base_map[k].severity is not curr_map[k].severity
    ]
    return {"added": added, "removed": removed, "changed": changed}

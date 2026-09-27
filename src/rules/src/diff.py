"""
版本对比 — diff 两次 RuleViolation 集合 + diff 两份规则清单

主键 (rule_id, element_id or "")。产出三桶互斥结果：
  added   — 当前有、baseline 没有（新增违规）
  removed — baseline 有、当前没有（消失违规）
  changed — 两边都有但严重度不同（severity 变化，带 from/to）

规则清单 diff：比较两份「已加载规则」的可序列化规格（rule_id 对齐），
输出 added/removed/changed（predicate / severity / param_defaults 任一变化），
供设计器改完 default.json 后看「我到底动了哪些规则」，不依赖元素数据。
"""
from __future__ import annotations

from typing import Any

from .engine import BaseRule, RuleViolation


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


# ─── 规则清单 diff ─────────────────────────────────────────────


def _rule_sig(rule: BaseRule) -> dict[str, Any]:
    """规则的可序列化规格：设计器可编辑的全部字段。

    predicate 只来自 DslRuleSpec（ParametricRule._spec）；硬编码类无
    predicate 概念，取空串 —— 同 id 的 DSL 覆盖类 vs 硬编码类 diff 时
    predicate 变化才可见，两条硬编码类之间不产生伪差异。
    """
    spec = getattr(rule, "_spec", None)
    params = dict(getattr(rule, "param_defaults", {})
                  or getattr(rule, "params", {}) or {})
    return {
        "name": getattr(rule, "name", ""),
        "severity": rule.severity.value if hasattr(rule.severity, "value") else rule.severity,
        "predicate": spec.predicate if spec is not None else "",
        "param_defaults": params,
        "enabled": getattr(rule, "enabled", True),
    }


def diff_rule_lists(
    old_rules: list[BaseRule],
    new_rules: list[BaseRule],
) -> dict[str, list[dict[str, Any]]]:
    """diff 两份规则清单（按 rule_id 对齐）。

    返回 {"added":…, "removed":…, "changed":…}：
      added   — new 有 old 没有的 rule_id
      removed — old 有 new 没有的 rule_id
      changed — 两边都有但 name/severity/predicate/param_defaults/enabled 任一不同
    每个桶的项为 {"rule_id":…, …各字段差异或全量规格}。
    """
    old_map = {r.rule_id: _rule_sig(r) for r in old_rules}
    new_map = {r.rule_id: _rule_sig(r) for r in new_rules}
    added = [
        {"rule_id": rid, **new_map[rid]} for rid in sorted(set(new_map) - set(old_map))
    ]
    removed = [
        {"rule_id": rid, **old_map[rid]} for rid in sorted(set(old_map) - set(new_map))
    ]
    changed = [
        {
            "rule_id": rid,
            "fields": {
                k: {"from": old_map[rid][k], "to": new_map[rid][k]}
                for k in old_map[rid]
                if old_map[rid][k] != new_map[rid][k]
            },
        }
        for rid in sorted(set(old_map) & set(new_map))
        if old_map[rid] != new_map[rid]
    ]
    return {"added": added, "removed": removed, "changed": changed}

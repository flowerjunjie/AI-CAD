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
from .engine import ViolationSeverity


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


# ─── 违规清单结构自洽校验 (机制层, 不判业务值) ─────────────────
# 边界 (呼应 CLAUDE.md 不虚标): 这是「引擎产出→前端 的违规清单自身是否自洽」
# 的校验 — 防幽灵 rule_id (引擎已删/写错) 静默穿透进 /api/pipeline 违规面板且无法
# 溯源, 以及非法 severity 枚举值。只判「清单结构 + rule_id 是否真实存在于引擎」,
# **不判**「这条规则阈值对不对」(那是 M1 业务值)。仿 verify_clashes/verify_summary 范式。


def verify_violations(
    violations: list[dict],
    known_rule_ids: set[str],
) -> dict:
    """校验违规清单 (to_dict 序列化后的 list) 结构自洽。纯函数, 畸形不崩。

    校验三条 (缺哪条报哪条, 全过 → ok=True, issues=[]):
      ① rule_id 非空: 每条必有非空字符串 rule_id (前端据此分组展示)。
      ② severity 合法: severity ∈ ViolationSeverity 合法值 (error/warning/info),
         防序列化后写入非法枚举值导致前端渲染歧义。
      ③ rule_id 已注册: rule_id ∈ known_rule_ids (引擎当前已注册全集) — 防幽灵
         rule_id (引擎删了/写错) 静默穿透进违规清单无从溯源。

    参数:
      violations: list[dict] (RuleViolation.to_dict 产物, 缺字段优雅降级不崩)
      known_rule_ids: 引擎已注册 rule_id 全集 (从 engine.list_rules() 派生, 非本函数取)
    返回 {ok, issues: [str...], checked: int}。
    """
    valid_sev = {s.value for s in ViolationSeverity}
    violations = violations or []
    if not isinstance(violations, list):
        return {"ok": False, "issues": [f"violations 非 list (畸形 {type(violations).__name__})"],
                "checked": 0}
    known = known_rule_ids or set()
    issues: list[str] = []
    for i, v in enumerate(violations):
        tag = f"violations[{i}]"
        if not isinstance(v, dict):
            issues.append(f"{tag} 非 dict")
            continue
        rid = v.get("rule_id")
        sev = v.get("severity")
        if not isinstance(rid, str) or not rid:
            issues.append(f"{tag} 缺 rule_id (={rid!r})")
        elif rid not in known:
            issues.append(f"{tag}.rule_id={rid!r} 不在引擎已注册集合 (幽灵 rule_id, 无从溯源)")
        if sev not in valid_sev:
            issues.append(f"{tag}.severity={sev!r} 非合法枚举 {sorted(valid_sev)}")
    return {"ok": not issues, "issues": issues, "checked": len(violations)}


# ─── 三桶 diff 结果结构自洽校验 (机制层, 通用, diff_violations/diff_rule_lists 共用) ─
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): diff_violations / diff_rule_lists 都产出
# {"added","removed","changed"} 三桶, 但两条通路当前**都没有**校验三桶自身的结构
# 不变量 (同 key 既进 added 又进 changed = 上游 diff 逻辑改动后静默失步)。本函数
# 用 key 提取器注入的方式, 一次护住两条同构通路 (仿 verify_summary 的「产出对账」
# 范式)。纯函数, 只判「三桶自身是否自洽」, 不判桶里业务内容。


def verify_diff_buckets(
    buckets: dict,
    key_of,
) -> dict:
    """校验 {added/removed/changed} 三桶结构自洽 (纯函数, 不崩)。

    key_of: 桶内单项 → key 的提取器 (diff_violations 传 (rule_id, element_id),
    diff_rule_lists 传 rule_id)。不绑死桶 value 类型 (RuleViolation 对象 / dict 均可)。

    校验四条 (缺哪条报哪条, 全过 → ok=True, issues=[]):
      ① added 与 changed 的 key 不交叠 (同一 key 不能既「新增」又「改动」)。
      ② removed 与 changed 的 key 不交叠 (同一 key 不能既「消失」又「改动」)。
      ③ added 桶内 key 无重复。
      ④ changed 桶内 key 无重复。
    畸形输入 (buckets 非 dict / 桶非 list / key_of 取不到) → 计入 issues, 不崩。
    返回 {ok, issues, checked}。
    """
    if not isinstance(buckets, dict):
        return {"ok": False, "issues": [f"buckets 非 dict (畸形 {type(buckets).__name__})"],
                "checked": 0}
    issues: list[str] = []

    def _keys(bucket_name: str) -> tuple[set, int]:
        raw = buckets.get(bucket_name)
        if raw is None:
            return set(), 0
        if not isinstance(raw, list):
            issues.append(f"{bucket_name} 非 list (畸形 {type(raw).__name__})")
            return set(), 0
        keys: set = set()
        for i, item in enumerate(raw):
            try:
                k = key_of(item)
            except Exception:
                issues.append(f"{bucket_name}[{i}] key 提取失败")
                continue
            keys.add(k)
        return keys, len(raw)

    added_keys, _ = _keys("added")
    removed_keys, _ = _keys("removed")
    changed_keys, _ = _keys("changed")

    # 桶内重复 (set 去重后数变小 → 有重复 key)
    for name in ("added", "changed"):
        raw = buckets.get(name) or []
        if isinstance(raw, list):
            try:
                unique = len({key_of(x) for x in raw})
            except Exception:
                continue
            if unique != len(raw):
                issues.append(f"{name} 桶内存在重复 key (diff 上游失步)")

    overlap_ac = added_keys & changed_keys
    if overlap_ac:
        issues.append(f"added ∩ changed 交叠 {sorted(overlap_ac)} (同 key 既新增又改动)")
    overlap_rc = removed_keys & changed_keys
    if overlap_rc:
        issues.append(f"removed ∩ changed 交叠 {sorted(overlap_rc)} (同 key 既消失又改动)")

    checked = sum(len(buckets.get(n) or [])
                  for n in ("added", "removed", "changed")
                  if isinstance(buckets.get(n), list))
    return {"ok": not issues, "issues": issues, "checked": checked}

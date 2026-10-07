"""
批量校验入口 — 一次跑完启用规则, 按严重级/规则聚合

与 @register_rule 的 34 类零改动红线：本模块只做编排, 不改 engine。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .engine import RuleEngine, RuleViolation, ViolationSeverity


@dataclass(frozen=True)
class BatchCheckReport:
    """批量校验聚合结果：全量违规 + 按严重级计数 + 按规则计数。"""

    violations: list[RuleViolation]
    by_severity: dict[str, int]
    by_rule: dict[str, int]

    @property
    def total(self) -> int:
        return len(self.violations)

    @property
    def error_count(self) -> int:
        return self.by_severity.get(ViolationSeverity.ERROR.value, 0)

    @property
    def warning_count(self) -> int:
        return self.by_severity.get(ViolationSeverity.WARNING.value, 0)

    @property
    def info_count(self) -> int:
        return self.by_severity.get(ViolationSeverity.INFO.value, 0)

    @property
    def has_errors(self) -> bool:
        return self.error_count > 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "by_severity": dict(self.by_severity),
            "by_rule": dict(self.by_rule),
            "violations": [v.to_dict() for v in self.violations],
        }


def run_batch_check(
    elements: list[Any],
    engine: RuleEngine | None = None,
    rule_ids: list[str] | None = None,
) -> BatchCheckReport:
    """批量校验入口：对一批元素跑指定（或全部）启用规则, 聚合出报告。

    Args:
        elements: 待检查元素列表
        engine: 引擎实例, None = 全局引擎 (get_engine, 34 类 + DSL upsert 后的全集)
        rule_ids: 只跑这些规则; None = 引擎里所有已注册规则
    """
    from .engine import get_engine  # 延迟 import: 全局引擎在 import 时构建

    eng = engine if engine is not None else get_engine()
    violations = _safe_check(eng, elements, rule_ids)
    return _aggregate(violations)


def _safe_check(
    eng: RuleEngine, elements: list[Any], rule_ids: list[str] | None
) -> list[RuleViolation]:
    """跑 engine.check 但隔离单元素 × 单规则的 AttributeError。

    34 个硬编码 @register_rule 类没有类型门禁 (与 DSL ParametricRule 的
    _matches_type 不同) — 硬编码规则命中没有该属性的元素会 AttributeError
    崩整条批量链。编排层兜住：某元素缺某规则所需属性 → 跳过该元素×该规则,
    不静默吞掉违规, 也让批量扫描不因一条规则炸掉全部。规则类零改动。

    缺属性跳过只在 verbose 时打 warning, 避免同一缺属性在多元素上刷屏。
    """
    target = (
        [eng.get_rule(tid) for tid in rule_ids] if rule_ids else eng.list_rules()
    )
    out: list[RuleViolation] = []
    import logging
    logger = logging.getLogger(__name__)
    seen_missing: set[tuple[str, str, str]] = set()
    for element in elements:
        for rule in target:
            if rule is None:
                continue
            try:
                out.extend(rule.check(element).violations)
            except AttributeError as e:
                key = (rule.rule_id, type(element).__name__,
                       getattr(e, "arg", ""))
                if key not in seen_missing:
                    seen_missing.add(key)
                    logger.warning(
                        "规则 %s 在 %s 上缺属性 %s, 跳过: %s",
                        rule.rule_id, type(element).__name__,
                        getattr(e, "arg", None), e,
                    )
    return out


def _aggregate(violations: list[RuleViolation]) -> BatchCheckReport:
    by_severity: dict[str, int] = {}
    by_rule: dict[str, int] = {}
    for v in violations:
        by_severity[v.severity.value] = by_severity.get(v.severity.value, 0) + 1
        by_rule[v.rule_id] = by_rule.get(v.rule_id, 0) + 1
    return BatchCheckReport(
        violations=list(violations),
        by_severity=by_severity,
        by_rule=by_rule,
    )


# ─── 批量校验报告结构自洽校验 (机制层自主子集, 纯函数) ─────────
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): 校验「BatchCheckReport 聚合计数与
# 明细是否自洽」— by_severity 各档之和 / by_rule 各规则之和 都应等于
# len(violations), 任一失步说明 _aggregate 被改动后未同步、或外部直构了
# 不自洽的 Report (绕过 run_batch_check 工厂)。纯函数, 畸形不崩。
# 不判「某条违规该不该发生」(那是 M1 业务值), 只判「报告自身数字是否自洽」。
# 消费侧 (GUI / 报告导出) 前挂此校验, 把「聚合数字对不上明细」静默失步提前暴露。


def verify_batch_report(report: BatchCheckReport) -> dict:
    """校验 BatchCheckReport 自身聚合一致性。返回 {ok, issues, total, checked} (纯函数)。

    校验:
      ① by_severity 之和 == len(violations)
      ② by_rule 之和 == len(violations)
      ③ by_severity 各档值 ≥ 0 (防手工编辑 Report 写负数计数)
      ④ by_rule 各值 ≥ 0 (同上)
    全过 → ok=True, issues=[]。畸形输入 (report 非 BatchCheckReport / 字段缺失) 不崩。
    """
    issues: list[str] = []
    try:
        violations = list(report.violations or [])
        total = len(violations)
    except Exception:
        return {"ok": False, "issues": ["violations 非 list 或缺失 (畸形 report)"],
                "total": 0, "checked": 0}
    try:
        by_sev = dict(report.by_severity or {})
        by_rule = dict(report.by_rule or {})
    except Exception:
        by_sev, by_rule = {}, {}
        issues.append("by_severity/by_rule 非 dict 或缺失 (畸形 report)")
    sev_sum = sum(by_sev.values())
    rule_sum = sum(by_rule.values())
    if sev_sum != total:
        issues.append(f"by_severity 之和 {sev_sum} ≠ violations 总数 {total} (聚合失步)")
    if rule_sum != total:
        issues.append(f"by_rule 之和 {rule_sum} ≠ violations 总数 {total} (聚合失步)")
    if any(v < 0 for v in by_sev.values()):
        issues.append(f"by_severity 存在负计数: {by_sev}")
    if any(v < 0 for v in by_rule.values()):
        issues.append(f"by_rule 存在负计数")
    return {"ok": not issues, "issues": issues, "total": total,
            "checked": len(by_sev) + len(by_rule)}

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
    violations = eng.check(elements, rule_ids)
    return _aggregate(violations)


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

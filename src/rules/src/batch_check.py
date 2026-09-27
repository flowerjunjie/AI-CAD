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

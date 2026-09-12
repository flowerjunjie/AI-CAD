"""
防火规范规则 — 疏散宽度与距离
参考：GB 50016-2014《建筑设计防火规范》
"""
from typing import Any
from dataclasses import dataclass
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Corridor:
    """走廊元素"""
    id: str
    name: str
    width_m: float
    length_m: float
    is_solid_state_corridor: bool = False


@register_rule
class CorridorMinWidth(BaseRule):
    """走廊最小净宽检查"""
    rule_id = "fire-corridor-min-width"
    name = "疏散走道的净宽度不应小于1.4m"
    code_ref = "GB 50016-2014 第5.5.18条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Corridor) -> RuleResult:
        violations = []
        if element.width_m < 1.4:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"疏散走道宽度 {element.width_m}m 小于规范要求 1.4m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将走廊宽度调整为 >= 1.4m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class CorridorLengthLimit(BaseRule):
    """走廊长度限制"""
    rule_id = "fire-corridor-length"
    name = "房间门至安全出口距离需符合规范"
    code_ref = "GB 50016-2014 第5.5.17条"
    severity = ViolationSeverity.WARNING

    def check(self, element: Corridor) -> RuleResult:
        violations = []
        # 住宅建筑位于两个安全出口之间的房间门到安全出口的距离
        if element.length_m > 40:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"走廊长度 {element.length_m}m 超过建议值，需增加疏散出口",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="在走廊中部增加疏散出口或安全出口",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class DoorClearWidth(BaseRule):
    """疏散门净宽度检查"""
    rule_id = "fire-door-clear-width"
    name = "疏散门的净宽度不应小于0.9m"
    code_ref = "GB 50016-2014 第5.5.19条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Any) -> RuleResult:
        # 简化：检查门宽度
        width = getattr(element, 'width_m', 0)
        violations = []
        if width < 0.9:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"疏散门宽度 {width}m 小于规范要求 0.9m",
                    code_ref=self.code_ref,
                    element_id=getattr(element, 'id', 'unknown'),
                    suggested_fix="将门宽调整为 >= 0.9m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

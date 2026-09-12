"""
住宅套型规范规则 — 走廊宽度检查
参考：GB 50096-2011《住宅设计规范》
"""
from dataclasses import dataclass
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity


@dataclass
class Corridor:
    """走廊元素"""

    id: str
    name: str
    width_m: float
    length_m: float
    is_solid_state_corridor: bool = False  # 是否为套内走廊


@register_rule
class SolidStateCorridorWidth(BaseRule):
    """套内走廊宽度检查"""

    rule_id = "residential-corridor-solid-width"
    name = "套内走廊净宽不应小于 1.2m"
    code_ref = "GB 50096-2011 第5.8.3条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Corridor) -> RuleResult:
        violations = []
        if element.is_solid_state_corridor and element.width_m < 1.2:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"套内走廊宽度 {element.width_m}m 小于规范要求 1.2m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将走廊宽度调整为 >= 1.2m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class LivingSpaceCorridorWidth(BaseRule):
    """居住空间走道宽度检查"""

    rule_id = "residential-corridor-living-width"
    name = "居住空间走道净宽不应小于 1.0m"
    code_ref = "GB 50096-2011 第5.8.3条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Corridor) -> RuleResult:
        violations = []
        if not element.is_solid_state_corridor and element.width_m < 1.0:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"居住空间走道宽度 {element.width_m}m 小于规范要求 1.0m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将走道宽度调整为 >= 1.0m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class CorridorLengthLimit(BaseRule):
    """走廊长度限制"""

    rule_id = "residential-corridor-length"
    name = "走廊长度超过一定值应增加疏散出口"
    code_ref = "GB 50016-2014 第5.5.1条"
    severity = ViolationSeverity.WARNING

    def check(self, element: Corridor) -> RuleResult:
        violations = []
        # 走廊长度超过 30m 需要增加疏散出口
        if element.length_m > 30:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"走廊长度 {element.length_m}m 超过 30m，应增加疏散出口",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="在走廊中部增加疏散出口或安全出口",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

"""
无障碍规范规则
参考：JGJ 50-2019《无障碍设计规范》
"""
from dataclasses import dataclass
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity


@dataclass
class Ramp:
    """坡道元素"""
    id: str
    slope: float  # 坡度比值，如 1/12
    width_m: float
    length_m: float


@register_rule
class RampMinWidth(BaseRule):
    """坡道最小宽度检查"""
    rule_id = "accessibility-ramp-width"
    name = "坡道净宽度不应小于1.2m"
    code_ref = "JGJ 50-2019 第6.5.1条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Ramp) -> RuleResult:
        violations = []
        if element.width_m < 1.2:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"坡道宽度 {element.width_m}m 小于规范要求 1.2m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将坡道宽度调整为 >= 1.2m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class RampMaxSlope(BaseRule):
    """坡道最大坡度检查"""
    rule_id = "accessibility-ramp-slope"
    name = "坡道坡度不应大于1:12"
    code_ref = "JGJ 50-2019 第6.4.2条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Ramp) -> RuleResult:
        violations = []
        # slope 是比值，1/12 ≈ 0.0833
        if element.slope > 1/12:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"坡道坡度 {element.slope:.3f} 大于规范允许值 1/12",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将坡度调整为 <= 1:12",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

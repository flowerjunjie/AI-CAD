"""
住宅规范规则 — 楼梯与电梯
参考：GB 50096-2011《住宅设计规范》
"""
from dataclasses import dataclass
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Stair:
    """楼梯元素"""
    id: str
    width_m: float
    riser_height_m: float = 0.175  # 踏步高度
    tread_depth_m: float = 0.26  # 踏步深度


@register_rule
class StairMinWidth(BaseRule):
    """楼梯最小宽度检查"""
    rule_id = "residential-stair-width"
    name = "楼梯梯段净宽度不应小于1.1m"
    code_ref = "GB 50096-2011 第6.3.1条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Stair) -> RuleResult:
        violations = []
        if element.width_m < 1.1:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"楼梯宽度 {element.width_m}m 小于规范要求 1.1m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将楼梯宽度调整为 >= 1.1m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class StairRiserMaxHeight(BaseRule):
    """楼梯踏步高度限制"""
    rule_id = "residential-stair-riser"
    name = "楼梯踏步高度不应大于0.175m"
    code_ref = "GB 50096-2011 第6.3.2条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Stair) -> RuleResult:
        violations = []
        if element.riser_height_m > 0.175:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"楼梯踏步高度 {element.riser_height_m}m 超过规范限值 0.175m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将踏步高度调整为 <= 0.175m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class StairTreadMinDepth(BaseRule):
    """楼梯踏步深度检查"""
    rule_id = "residential-stair-tread"
    name = "楼梯踏步宽度不应小于0.26m"
    code_ref = "GB 50096-2011 第6.3.2条"
    severity = ViolationSeverity.WARNING

    def check(self, element: Stair) -> RuleResult:
        violations = []
        if element.tread_depth_m < 0.26:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"楼梯踏步深度 {element.tread_depth_m}m 小于规范要求 0.26m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将踏步深度调整为 >= 0.26m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

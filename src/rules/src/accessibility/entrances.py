"""
无障碍规范规则 — 轮椅回转空间与入口
参考：JGJ 50-2019《无障碍设计规范》
"""
from dataclasses import dataclass
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Entrance:
    """入口元素"""
    id: str
    width_m: float
    has_step: bool = False
    has_ramp: bool = False


@dataclass
class TurningSpace:
    """回转空间元素"""
    id: str
    diameter_m: float  # 回转直径


@register_rule
class EntranceNoStep(BaseRule):
    """入口无台阶检查"""
    rule_id = "accessibility-entrance-no-step"
    name = "无障碍入口不应设置台阶"
    code_ref = "JGJ 50-2019 第6.2.1条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Entrance) -> RuleResult:
        violations = []
        if element.has_step and not element.has_ramp:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"入口 {element.id} 有台阶但未设置坡道",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="增设坡道或取消台阶",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class EntranceMinWidth(BaseRule):
    """入口最小宽度检查"""
    rule_id = "accessibility-entrance-width"
    name = "无障碍入口净宽度不应小于1.2m"
    code_ref = "JGJ 50-2019 第6.2.2条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Entrance) -> RuleResult:
        violations = []
        if element.width_m < 1.2:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"入口宽度 {element.width_m}m 小于规范要求 1.2m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将入口宽度调整为 >= 1.2m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class TurningSpaceMinDiameter(BaseRule):
    """轮椅回转空间检查"""
    rule_id = "accessibility-turning-space"
    name = "轮椅回转空间直径不应小于1.5m"
    code_ref = "JGJ 50-2019 第6.3.1条"
    severity = ViolationSeverity.ERROR

    def check(self, element: TurningSpace) -> RuleResult:
        violations = []
        if element.diameter_m < 1.5:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"回转空间直径 {element.diameter_m}m 小于规范要求 1.5m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将回转空间直径调整为 >= 1.5m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

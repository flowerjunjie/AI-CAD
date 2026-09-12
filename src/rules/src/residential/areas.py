"""
住宅套型规范规则 — 面积计算
参考：GB/T 50353-2013《建筑工程建筑面积计算规范》
"""
from dataclasses import dataclass
from src.rules.src.engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Room:
    """房间元素"""

    id: str
    name: str
    length_m: float
    width_m: float
    floor_number: int
    has_colonnettes: bool  # 是否有柱廊


@register_rule
class FullAreaCalculation(BaseRule):
    """全面积计算规则"""

    rule_id = "area-full-calculation"
    name = "结构层高在2.20m及以上的应计算全面积"
    code_ref = "GB/T 50353-2013 第3.0.1条"
    severity = ViolationSeverity.INFO

    def check(self, element: Room) -> RuleResult:
        # This is an info-level rule for area calculation
        # Actual area calculation would be done by a calculator, not a validator
        return RuleResult(passed=True)


@register_rule
class HalfAreaCalculation(BaseRule):
    """半面积计算规则"""

    rule_id = "area-half-calculation"
    name = "有围护结构的楼梯间、挑廊等应按水平投影面积的1/2计算"
    code_ref = "GB/T 50353-2013 第3.0.14条"
    severity = ViolationSeverity.INFO

    def check(self, element: Room) -> RuleResult:
        if element.has_colonnettes:
            # Info only, no violation
            pass
        return RuleResult(passed=True)

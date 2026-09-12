"""
住宅套型规范规则 — 房间面积检查
参考：GB 50096-2011《住宅设计规范》
"""
from dataclasses import dataclass
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Room:
    """房间元素"""

    id: str
    name: str
    length_m: float
    width_m: float
    floor_number: int = 1


@register_rule
class BedroomMinimumArea(BaseRule):
    """卧室最小面积检查"""

    rule_id = "residential-room-bedroom-area"
    name = "卧室面积不应小于 5㎡"
    code_ref = "GB 50096-2011 第5.2.1条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Room) -> RuleResult:
        violations = []
        if element.name in ("卧室", "主卧", "次卧", "书房") and element.length_m * element.width_m < 5:
            area = element.length_m * element.width_m
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"卧室面积 {area:.2f}㎡ 小于规范要求 5㎡",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix=f"将房间尺寸调整为满足面积 >= 5㎡（如 2.5m x 2.0m）",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class LivingRoomMinimumArea(BaseRule):
    """起居室最小面积检查"""

    rule_id = "residential-room-living-area"
    name = "起居室面积不应小于 6㎡"
    code_ref = "GB 50096-2011 第5.2.2条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Room) -> RuleResult:
        violations = []
        if element.name in ("起居室", "客厅") and element.length_m * element.width_m < 6:
            area = element.length_m * element.width_m
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"起居室面积 {area:.2f}㎡ 小于规范要求 6㎡",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix=f"将房间尺寸调整为满足面积 >= 6㎡",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class KitchenMinimumArea(BaseRule):
    """厨房最小面积检查"""

    rule_id = "residential-room-kitchen-area"
    name = "厨房面积不应小于 3.5㎡"
    code_ref = "GB 50096-2011 第5.2.3条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Room) -> RuleResult:
        violations = []
        if element.name in ("厨房",) and element.length_m * element.width_m < 3.5:
            area = element.length_m * element.width_m
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"厨房面积 {area:.2f}㎡ 小于规范要求 3.5㎡",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix=f"将房间尺寸调整为满足面积 >= 3.5㎡",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class BathroomMinimumArea(BaseRule):
    """卫生间最小面积检查"""

    rule_id = "residential-room-bathroom-area"
    name = "卫生间面积不应小于 2.0㎡"
    code_ref = "GB 50096-2011 第5.2.4条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Room) -> RuleResult:
        violations = []
        if element.name in ("卫生间", "浴室", "主卫", "次卫") and element.length_m * element.width_m < 2.0:
            area = element.length_m * element.width_m
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"卫生间面积 {area:.2f}㎡ 小于规范要求 2.0㎡",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix=f"将房间尺寸调整为满足面积 >= 2.0㎡",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

"""
防火规范规则 — 安全出口与疏散
参考：GB 50016-2014《建筑设计防火规范》
"""
from dataclasses import dataclass
from typing import Optional
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Room:
    """房间元素"""
    id: str
    name: str
    area_m2: float
    occupant_count: int = 0
    has_exit: bool = False


@dataclass
class Exit:
    """安全出口"""
    id: str
    width_m: float
    distance_to_room_m: float


@register_rule
class RoomMinExitWidth(BaseRule):
    """房间安全出口宽度检查"""
    rule_id = "fire-room-exit-width"
    name = "房间安全出口净宽度不应小于0.9m"
    code_ref = "GB 50016-2014 第5.5.19条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Exit) -> RuleResult:
        violations = []
        if element.width_m < 0.9:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"安全出口宽度 {element.width_m}m 小于规范要求 0.9m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将出口宽度调整为 >= 0.9m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class RoomMaxExitDistance(BaseRule):
    """房间到安全出口距离检查"""
    rule_id = "fire-room-exit-distance"
    name = "房间门至安全出口的最大距离需符合规范"
    code_ref = "GB 50016-2014 第5.5.17条"
    severity = ViolationSeverity.WARNING

    def check(self, element: Exit) -> RuleResult:
        violations = []
        # 住宅建筑位于两个安全出口之间的房间门到安全出口的距离
        if element.distance_to_room_m > 40:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"房间到安全出口距离 {element.distance_to_room_m}m 超过建议值",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="增加安全出口或缩短疏散距离",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class RoomMinExits(BaseRule):
    """房间最小安全出口数量检查"""
    rule_id = "fire-room-min-exits"
    name = "建筑面积大于50㎡的房间应设2个安全出口"
    code_ref = "GB 50016-2014 第5.5.15条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Room) -> RuleResult:
        violations = []
        if element.area_m2 > 50 and not element.has_exit:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"房间面积 {element.area_m2}㎡ > 50㎡，应设置2个安全出口",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="增设第二个安全出口",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

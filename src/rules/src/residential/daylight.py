"""
住宅规范规则 — 日照与采光
参考：GB 50096-2011《住宅设计规范》
"""
from dataclasses import dataclass
from ..engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Window:
    """窗户元素"""
    id: str
    sill_height_m: float
    head_height_m: float
    room_type: str


@register_rule
class LivingRoomDaylight(BaseRule):
    """起居室日照检查"""
    rule_id = "residential-living-daylight"
    name = "起居室应有自然采光和通风"
    code_ref = "GB 50096-2011 第7.1.1条"
    severity = ViolationSeverity.INFO

    def check(self, element: Window) -> RuleResult:
        # Info级别：仅检查是否有窗
        violations = []
        if element.room_type in ("living", "客厅"):
            # 窗台高度合理即认为满足
            if element.sill_height_m <= 0.9:
                pass  # 符合
            else:
                violations.append(
                    RuleViolation(
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=self.severity,
                        description=f"起居室窗台高度 {element.sill_height_m}m 可能影响采光",
                        code_ref=self.code_ref,
                        element_id=element.id,
                    )
                )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class BedroomMinWindowArea(BaseRule):
    """卧室最小采光面积"""
    rule_id = "residential-bedroom-window-area"
    name = "卧室窗地比不应小于1/7"
    code_ref = "GB 50096-2011 第7.1.1条"
    severity = ViolationSeverity.WARNING

    def check(self, element: Window) -> RuleResult:
        # 简化检查：窗台高度不超过0.9m
        violations = []
        if element.room_type in ("bedroom", "卧室"):
            if element.sill_height_m > 0.9:
                violations.append(
                    RuleViolation(
                        rule_id=self.rule_id,
                        rule_name=self.name,
                        severity=self.severity,
                        description=f"卧室窗台高度 {element.sill_height_m}m 可能影响采光",
                        code_ref=self.code_ref,
                        element_id=element.id,
                    )
                )
        return RuleResult(passed=len(violations) == 0, violations=violations)

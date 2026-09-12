"""
住宅套型规范规则 — 窗台高度检查
参考：GB 50096-2011《住宅设计规范》
"""
from dataclasses import dataclass
from src.rules.src.engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


@dataclass
class Window:
    """窗户元素"""

    id: str
    sill_height_m: float  # 窗台高度（米）
    top_height_m: float  # 窗顶高度（米）
    room_type: str
    location: tuple[float, float]


@register_rule
class WindowSillHeight(BaseRule):
    """窗台高度检查"""

    rule_id = "residential-window-sill-height"
    name = "窗台高度不应大于 0.9m"
    code_ref = "GB 50096-2011 第5.8.7条"
    severity = ViolationSeverity.WARNING

    def check(self, element: Window) -> RuleResult:
        violations = []
        if element.sill_height_m > 0.9:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"窗台高度 {element.sill_height_m}m 超过规范要求 0.9m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将窗台高度调整为 <= 0.9m，或增设防护设施",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class BalconyRailingHeight(BaseRule):
    """阳台栏杆高度检查"""

    rule_id = "residential-balcony-railing-height"
    name = "阳台栏杆净高不应低于 1.05m（中高层）/ 1.10m（高层）"
    code_ref = "GB 50096-2011 第5.8.5条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Window) -> RuleResult:
        """阳台栏杆高度检查（通过窗户元素间接检查）"""
        # TODO: 扩展为专门的 Railing 元素类型
        violations = []
        railing_height = element.top_height_m - element.sill_height_m
        if element.room_type == "balcony" and railing_height < 1.05:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"阳台栏杆高度 {railing_height}m 小于规范要求 1.05m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将栏杆高度调整为 >= 1.05m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)

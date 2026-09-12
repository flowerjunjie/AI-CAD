"""
住宅套型规范规则 — 门宽检查
参考：GB 50096-2011《住宅设计规范》
"""
from dataclasses import dataclass
from src.rules.src.engine import BaseRule, RuleResult, register_rule, ViolationSeverity, RuleViolation


# ─── Data Models ────────────────────────────────────────────────

@dataclass
class Door:
    """门元素"""

    id: str
    width_m: float  # 宽度（米）
    room_type: str  # 所在房间类型
    location: tuple[float, float]  # 位置坐标


# ─── Rules ──────────────────────────────────────────────────────

@register_rule
class MainEntranceDoorWidth(BaseRule):
    """户门宽度检查"""

    rule_id = "residential-door-main-width"
    name = "户门宽度不应小于 1.0m"
    code_ref = "GB 50096-2011 第5.8.6条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Door) -> RuleResult:
        violations = []
        if element.room_type == "entrance" and element.width_m < 1.0:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"户门宽度 {element.width_m}m 小于规范要求 1.0m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将门宽调整为 >= 1.0m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class InteriorDoorWidth(BaseRule):
    """户内门宽度检查"""

    rule_id = "residential-door-interior-width"
    name = "户内门宽度不应小于 0.9m"
    code_ref = "GB 50096-2011 第5.8.6条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Door) -> RuleResult:
        violations = []
        if element.room_type != "entrance" and element.width_m < 0.9:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"户内门宽度 {element.width_m}m 小于规范要求 0.9m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将门宽调整为 >= 0.9m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


@register_rule
class BathroomDoorWidth(BaseRule):
    """卫生间门宽度检查"""

    rule_id = "residential-door-bathroom-width"
    name = "卫生间门宽度不应小于 0.8m"
    code_ref = "GB 50096-2011 第5.8.6条"
    severity = ViolationSeverity.ERROR

    def check(self, element: Door) -> RuleResult:
        violations = []
        if element.room_type == "bathroom" and element.width_m < 0.8:
            violations.append(
                RuleViolation(
                    rule_id=self.rule_id,
                    rule_name=self.name,
                    severity=self.severity,
                    description=f"卫生间门宽度 {element.width_m}m 小于规范要求 0.8m",
                    code_ref=self.code_ref,
                    element_id=element.id,
                    suggested_fix="将门宽调整为 >= 0.8m",
                )
            )
        return RuleResult(passed=len(violations) == 0, violations=violations)


# ─── Demo ───────────────────────────────────────────────────────

if __name__ == "__main__":
    from src.rules.engine import get_engine

    engine = get_engine()
    doors = [
        Door(id="d1", width_m=1.0, room_type="entrance", location=(0, 0)),
        Door(id="d2", width_m=0.8, room_type="interior", location=(3, 0)),
        Door(id="d3", width_m=0.7, room_type="bathroom", location=(6, 0)),
    ]

    violations = engine.check(doors)
    print(f"检查完成，发现 {len(violations)} 条违规：")
    for v in violations:
        print(f"  [{v.severity.value}] {v.rule_name}: {v.description}")

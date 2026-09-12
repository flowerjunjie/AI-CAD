"""
单元测试 — 规则引擎核心逻辑
"""
import sys
import os

# Add project root to path
project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# Import residential modules to trigger rule registration decorators
import src.rules.src.residential.doors
import src.rules.src.residential.windows
import src.rules.src.residential.areas

from src.rules.src.engine import RuleEngine, BaseRule, ViolationSeverity, get_engine
from src.rules.src.residential.doors import Door, MainEntranceDoorWidth, InteriorDoorWidth, BathroomDoorWidth
from src.rules.src.residential.windows import Window, WindowSillHeight


def test_main_door_width_pass():
    """户门宽度 >= 1.0m 应通过"""
    engine = RuleEngine()
    door = Door(id="d1", width_m=1.0, room_type="entrance", location=(0, 0))
    rule = MainEntranceDoorWidth()
    engine.register(rule)
    violations = engine.check([door])
    assert len(violations) == 0, f"Expected 0 violations, got {len(violations)}"
    print("✅ test_main_door_width_pass")


def test_main_door_width_fail():
    """户门宽度 < 1.0m 应违规"""
    engine = RuleEngine()
    door = Door(id="d2", width_m=0.8, room_type="entrance", location=(0, 0))
    rule = MainEntranceDoorWidth()
    engine.register(rule)
    violations = engine.check([door])
    assert len(violations) == 1
    assert violations[0].severity == ViolationSeverity.ERROR
    assert "1.0m" in violations[0].description
    print("✅ test_main_door_width_fail")


def test_interior_door_width():
    """户内门宽度检查"""
    engine = RuleEngine()
    rule = InteriorDoorWidth()

    door_pass = Door(id="d3", width_m=0.9, room_type="interior", location=(0, 0))
    assert rule.check(door_pass).passed

    door_fail = Door(id="d4", width_m=0.7, room_type="interior", location=(0, 0))
    result = rule.check(door_fail)
    assert not result.passed
    assert len(result.violations) == 1
    print("✅ test_interior_door_width")


def test_bathroom_door_width():
    """卫生间门宽度检查"""
    engine = RuleEngine()
    rule = BathroomDoorWidth()

    door_pass = Door(id="d5", width_m=0.8, room_type="bathroom", location=(0, 0))
    assert rule.check(door_pass).passed

    door_fail = Door(id="d6", width_m=0.6, room_type="bathroom", location=(0, 0))
    result = rule.check(door_fail)
    assert not result.passed
    print("✅ test_bathroom_door_width")


def test_window_sill_height():
    """窗台高度检查"""
    engine = RuleEngine()
    rule = WindowSillHeight()

    window_pass = Window(id="w1", sill_height_m=0.8, top_height_m=2.0, room_type="living", location=(0, 0))
    assert rule.check(window_pass).passed

    window_fail = Window(id="w2", sill_height_m=1.0, top_height_m=2.2, room_type="living", location=(0, 0))
    result = rule.check(window_fail)
    assert not result.passed
    print("✅ test_window_sill_height")


def test_batch_check():
    """批量检查多个元素（使用全局规则引擎）"""
    engine = get_engine()
    doors = [
        Door(id="d1", width_m=1.0, room_type="entrance", location=(0, 0)),
        Door(id="d2", width_m=0.8, room_type="entrance", location=(3, 0)),
        Door(id="d3", width_m=0.9, room_type="interior", location=(6, 0)),
    ]
    # Check only main door width rule
    violations = engine.check(doors, rule_ids=["residential-door-main-width"])
    assert len(violations) == 1
    assert violations[0].element_id == "d2"
    print("✅ test_batch_check")


def test_duplicate_rule_rejected():
    """重复注册同一规则应报错"""
    engine = RuleEngine()
    rule = MainEntranceDoorWidth()
    engine.register(rule)
    try:
        engine.register(rule)
        assert False, "Should have raised ValueError"
    except ValueError:
        print("✅ test_duplicate_rule_rejected")


if __name__ == "__main__":
    test_main_door_width_pass()
    test_main_door_width_fail()
    test_interior_door_width()
    test_bathroom_door_width()
    test_window_sill_height()
    test_batch_check()
    test_duplicate_rule_rejected()
    print("\n🎉 All tests passed!")

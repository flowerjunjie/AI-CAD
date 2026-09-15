"""
扩展测试 — 新增规则覆盖
"""
import sys
import os
# 项目根 (含 src 包) — 不是 ../src, 否则直跑时 src.rules 找不到
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

# Import all rule modules to register decorators
# 必须 import 全部 11 个规则模块 — get_engine() 是全局单例, 直跑单文件时
# 只有这里 import 过的模块会注册进引擎; 漏 import 会让 test_total_rule_count
# 因规则数不足而炸 (此前只 import 4 个, 靠别的测试文件先 import 才侥幸绿)。
import src.rules.src.residential.stairs as _stairs
import src.rules.src.residential.doors as _doors
import src.rules.src.residential.rooms as _rooms
import src.rules.src.residential.windows as _windows
import src.rules.src.residential.areas as _areas
import src.rules.src.residential.corridors as _rcorridors
import src.rules.src.residential.daylight as _daylight
import src.rules.src.fire_safety.exits as _exits
import src.rules.src.fire_safety.corridors as _fcorridors
import src.rules.src.accessibility.entrances as _entrances
import src.rules.src.accessibility.ramps as _ramps

from src.rules.src.engine import RuleEngine, ViolationSeverity, get_engine
from src.rules.src.residential.stairs import Stair, StairMinWidth, StairRiserMaxHeight, StairTreadMinDepth
from src.rules.src.fire_safety.exits import Exit, Room, RoomMinExitWidth, RoomMaxExitDistance, RoomMinExits
from src.rules.src.accessibility.entrances import Entrance, TurningSpace, EntranceNoStep, EntranceMinWidth, TurningSpaceMinDiameter


def test_stair_width():
    """楼梯宽度检查"""
    engine = RuleEngine()
    stair = Stair(id="s1", width_m=1.0, riser_height_m=0.175)
    rule = StairMinWidth()
    engine.register(rule)
    violations = engine.check([stair])
    assert len(violations) == 1
    assert violations[0].severity == ViolationSeverity.ERROR
    print("[ok] test_stair_width")


def test_stair_riser():
    """楼梯踏步高度检查"""
    engine = RuleEngine()
    stair = Stair(id="s2", width_m=1.2, riser_height_m=0.20)
    rule = StairRiserMaxHeight()
    engine.register(rule)
    violations = engine.check([stair])
    assert len(violations) == 1
    print("[ok] test_stair_riser")


def test_stair_tread():
    """楼梯踏步深度检查"""
    engine = RuleEngine()
    stair = Stair(id="s3", width_m=1.2, tread_depth_m=0.24)
    rule = StairTreadMinDepth()
    engine.register(rule)
    violations = engine.check([stair])
    assert len(violations) == 1
    print("[ok] test_stair_tread")


def test_exit_width():
    """安全出口宽度检查"""
    engine = RuleEngine()
    exit = Exit(id="e1", width_m=0.8, distance_to_room_m=10)
    rule = RoomMinExitWidth()
    engine.register(rule)
    violations = engine.check([exit])
    assert len(violations) == 1
    assert violations[0].severity == ViolationSeverity.ERROR
    print("[ok] test_exit_width")


def test_exit_distance():
    """安全出口距离检查"""
    engine = RuleEngine()
    exit = Exit(id="e2", width_m=1.0, distance_to_room_m=50)
    rule = RoomMaxExitDistance()
    engine.register(rule)
    violations = engine.check([exit])
    assert len(violations) == 1
    print("[ok] test_exit_distance")


def test_room_min_exits():
    """房间最小出口数量检查"""
    engine = RuleEngine()
    room = Room(id="r1", name="客厅", area_m2=60, has_exit=False)
    rule = RoomMinExits()
    engine.register(rule)
    violations = engine.check([room])
    assert len(violations) == 1
    print("[ok] test_room_min_exits")


def test_entrance_no_step():
    """无障碍入口无台阶检查"""
    engine = RuleEngine()
    entrance = Entrance(id="ent1", width_m=1.5, has_step=True, has_ramp=False)
    rule = EntranceNoStep()
    engine.register(rule)
    violations = engine.check([entrance])
    assert len(violations) == 1
    print("[ok] test_entrance_no_step")


def test_entrance_width():
    """无障碍入口宽度检查"""
    engine = RuleEngine()
    entrance = Entrance(id="ent2", width_m=1.0, has_step=False)
    rule = EntranceMinWidth()
    engine.register(rule)
    violations = engine.check([entrance])
    assert len(violations) == 1
    print("[ok] test_entrance_width")


def test_turning_space():
    """轮椅回转空间检查"""
    engine = RuleEngine()
    space = TurningSpace(id="ts1", diameter_m=1.2)
    rule = TurningSpaceMinDiameter()
    engine.register(rule)
    violations = engine.check([space])
    assert len(violations) == 1
    print("[ok] test_turning_space")


def test_total_rule_count():
    """验证规则总数"""
    engine = get_engine()
    rules = engine.list_rules()
    # 应该至少有25条规则
    assert len(rules) >= 25, f"Expected >= 25 rules, got {len(rules)}"
    print(f"? test_total_rule_count ({len(rules)} rules)")


if __name__ == "__main__":
    import sys as _s
    for _x in (_s.stdout, _s.stderr):
        if hasattr(_x, "reconfigure"): _x.reconfigure(encoding="utf-8", errors="replace")
    test_stair_width()
    test_stair_riser()
    test_stair_tread()
    test_exit_width()
    test_exit_distance()
    test_room_min_exits()
    test_entrance_no_step()
    test_entrance_width()
    test_turning_space()
    test_total_rule_count()
    print("\n? All extended tests passed!")

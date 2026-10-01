"""
规则类分支覆盖补测 — 放行/不适用侧 (覆盖 67-84% 的 5 个规则模块)

背景: test_extended_rules.py 已测了「违规命中」侧, 但 residential/daylight、
residential/corridors、residential/windows、fire_safety/corridors、accessibility/ramps
这 5 个模块的「合规放行」「非适用房间/元素类型跳过」另一侧分支没覆盖 →
.coveragerc 90% 门槛下它们停在 67-84%。本文件按 test_extended_rules 范式
(单例 RuleEngine + register 单规则 + engine.check 断言 violations 数) 补齐两侧,
把低覆盖拉过 90% 门槛。

红线二: 每个用例先读对模块源码确认 dataclass 字段 + 判定阈值 (不猜接口)。
__main__ 直跑护栏: 无 fixture 子集 + ASCII print (Windows GBK 不崩)。
"""
import sys
import os

# 项目根 (含 src 包)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from src.rules.src.engine import RuleEngine, ViolationSeverity

# ── 元素 + 规则类 (各模块独立 dataclass, 同名不同类, 各取所需) ──
from src.rules.src.residential.daylight import (
    Window as DaylightWindow, LivingRoomDaylight, BedroomMinWindowArea)
from src.rules.src.residential.corridors import (
    Corridor as ResCorridor, SolidStateCorridorWidth,
    LivingSpaceCorridorWidth, CorridorLengthLimit as ResCorridorLength)
from src.rules.src.residential.windows import (
    Window as ResWindow, WindowSillHeight, BalconyRailingHeight)
from src.rules.src.fire_safety.corridors import (
    Corridor as FireCorridor, CorridorMinWidth as FireCorridorMinWidth,
    CorridorLengthLimit as FireCorridorLength, DoorClearWidth)
from src.rules.src.accessibility.ramps import (
    Ramp, RampMinWidth, RampMaxSlope)


def _run(rule, element):
    engine = RuleEngine()
    engine.register(rule)
    return engine.check([element])


# ── residential/daylight: 放行 (窗台合规) + 非适用房间类型跳过 ──────────────

def test_daylight_living_room_compliant():
    """起居室窗台 0.5m (<=0.9) 合规 → 0 违规 (放行侧)。"""
    w = DaylightWindow(id="d1", sill_height_m=0.5, head_height_m=2.4, room_type="living")
    assert len(_run(LivingRoomDaylight(), w)) == 0


def test_daylight_living_room_high_sill():
    """起居室窗台 1.2m (>0.9) → 命中 1 违规。"""
    w = DaylightWindow(id="d2", sill_height_m=1.2, head_height_m=2.4, room_type="客厅")
    v = _run(LivingRoomDaylight(), w)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.INFO


def test_daylight_non_living_room_skipped():
    """非起居室 (bedroom) 不套用 LivingRoomDaylight → 0 违规 (不适用侧)。"""
    w = DaylightWindow(id="d3", sill_height_m=1.5, head_height_m=2.4, room_type="bedroom")
    assert len(_run(LivingRoomDaylight(), w)) == 0


def test_bedroom_min_window_area_compliant():
    """卧室窗台 0.7m (<=0.9) → 合规 0 违规。"""
    w = DaylightWindow(id="b1", sill_height_m=0.7, head_height_m=2.4, room_type="bedroom")
    assert len(_run(BedroomMinWindowArea(), w)) == 0


def test_bedroom_min_window_area_violation():
    """卧室窗台 1.1m (>0.9) → 命中 1 违规 (WARNING)。"""
    w = DaylightWindow(id="b2", sill_height_m=1.1, head_height_m=2.4, room_type="卧室")
    v = _run(BedroomMinWindowArea(), w)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.WARNING


# ── residential/corridors: 三规则的 命中/放行/不适用 分支 ───────────────────

def test_res_corridor_solid_narrow_violation():
    """套内走廊 0.9m (<1.2, 套内) → 命中 (ERROR)。"""
    c = ResCorridor(id="rc1", name="套内走廊", width_m=0.9, length_m=5.0,
                    is_solid_state_corridor=True)
    v = _run(SolidStateCorridorWidth(), c)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.ERROR


def test_res_corridor_solid_wide_compliant():
    """套内走廊 1.5m (>=1.2, 套内) → 合规放行 0 违规。"""
    c = ResCorridor(id="rc2", name="套内走廊", width_m=1.5, length_m=5.0,
                    is_solid_state_corridor=True)
    assert len(_run(SolidStateCorridorWidth(), c)) == 0


def test_res_corridor_living_narrow_violation():
    """居住走道 0.8m (<1.0, 非套内) → 命中 (ERROR)。"""
    c = ResCorridor(id="rc3", name="走道", width_m=0.8, length_m=5.0,
                    is_solid_state_corridor=False)
    v = _run(LivingSpaceCorridorWidth(), c)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.ERROR


def test_res_corridor_living_wide_compliant():
    """居住走道 1.2m (>=1.0, 非套内) → 合规放行。"""
    c = ResCorridor(id="rc4", name="走道", width_m=1.2, length_m=5.0,
                    is_solid_state_corridor=False)
    assert len(_run(LivingSpaceCorridorWidth(), c)) == 0


def test_res_corridor_length_over():
    """走廊 35m (>30) → 命中需增加疏散出口 (WARNING)。"""
    c = ResCorridor(id="rc5", name="长走廊", width_m=1.2, length_m=35.0)
    v = _run(ResCorridorLength(), c)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.WARNING


def test_res_corridor_length_ok():
    """走廊 20m (<=30) → 合规放行。"""
    c = ResCorridor(id="rc6", name="短走廊", width_m=1.2, length_m=20.0)
    assert len(_run(ResCorridorLength(), c)) == 0


# ── residential/windows: 窗台 + 阳台栏杆 命中/放行/非适用 ───────────────────

def test_window_sill_compliant():
    """窗台 0.6m (<=0.9) → 合规放行。"""
    w = ResWindow(id="w1", sill_height_m=0.6, top_height_m=2.4,
                  room_type="bedroom", location=(0.0, 0.0))
    assert len(_run(WindowSillHeight(), w)) == 0


def test_window_sill_violation():
    """窗台 1.0m (>0.9) → 命中 (WARNING)。"""
    w = ResWindow(id="w2", sill_height_m=1.0, top_height_m=2.4,
                  room_type="bedroom", location=(0.0, 0.0))
    v = _run(WindowSillHeight(), w)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.WARNING


def test_balcony_railing_low_violation():
    """阳台栏杆 top-sill=0.9m (<1.05) → 命中 (ERROR)。"""
    w = ResWindow(id="b1", sill_height_m=0.9, top_height_m=1.8,
                  room_type="balcony", location=(0.0, 0.0))
    v = _run(BalconyRailingHeight(), w)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.ERROR


def test_balcony_railing_ok_compliant():
    """阳台栏杆 top-sill=1.2m (>=1.05) → 合规放行。"""
    w = ResWindow(id="b2", sill_height_m=0.8, top_height_m=2.0,
                  room_type="balcony", location=(0.0, 0.0))
    assert len(_run(BalconyRailingHeight(), w)) == 0


def test_balcony_railing_non_balcony_skipped():
    """非阳台房间不套栏杆规则 (即使栏杆低也 0 违规, 不适用侧)。"""
    w = ResWindow(id="b3", sill_height_m=0.5, top_height_m=0.6,
                  room_type="bedroom", location=(0.0, 0.0))
    assert len(_run(BalconyRailingHeight(), w)) == 0


# ── fire_safety/corridors: 宽度/长度/门宽 命中/放行 ────────────────────────

def test_fire_corridor_width_violation():
    """疏散走道 1.0m (<1.4) → 命中 (ERROR)。"""
    c = FireCorridor(id="fc1", name="疏散走道", width_m=1.0, length_m=30.0)
    v = _run(FireCorridorMinWidth(), c)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.ERROR


def test_fire_corridor_width_compliant():
    """疏散走道 1.6m (>=1.4) → 合规放行。"""
    c = FireCorridor(id="fc2", name="疏散走道", width_m=1.6, length_m=30.0)
    assert len(_run(FireCorridorMinWidth(), c)) == 0


def test_fire_corridor_length_over():
    """疏散走道 45m (>40) → 命中需增加出口 (WARNING)。"""
    c = FireCorridor(id="fc3", name="疏散走道", width_m=1.6, length_m=45.0)
    v = _run(FireCorridorLength(), c)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.WARNING


def test_fire_corridor_length_ok():
    """疏散走道 30m (<=40) → 合规放行。"""
    c = FireCorridor(id="fc4", name="疏散走道", width_m=1.6, length_m=30.0)
    assert len(_run(FireCorridorLength(), c)) == 0


def test_door_clear_width_violation():
    """疏散门 0.7m (<0.9, 用 width_m 属性) → 命中 (ERROR)。"""
    c = FireCorridor(id="fc5", name="门", width_m=0.7, length_m=1.0)
    v = _run(DoorClearWidth(), c)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.ERROR


def test_door_clear_width_compliant():
    """疏散门 1.0m (>=0.9) → 合规放行。"""
    c = FireCorridor(id="fc6", name="门", width_m=1.0, length_m=1.0)
    assert len(_run(DoorClearWidth(), c)) == 0


def test_door_clear_width_missing_attr():
    """无 width_m 属性的元素 (getattr 默认 0 <0.9) → 命中, 不崩 (边界)。"""
    v = _run(DoorClearWidth(), _NoWidth())
    assert len(v) == 1


# ── accessibility/ramps: 宽度/坡度 命中/放行 ────────────────────────────────

def test_ramp_width_violation():
    """坡道 0.9m (<1.2) → 命中 (ERROR)。"""
    r = Ramp(id="rp1", slope=1 / 12, width_m=0.9, length_m=3.0)
    v = _run(RampMinWidth(), r)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.ERROR


def test_ramp_width_compliant():
    """坡道 1.5m (>=1.2) → 合规放行。"""
    r = Ramp(id="rp2", slope=1 / 12, width_m=1.5, length_m=3.0)
    assert len(_run(RampMinWidth(), r)) == 0


def test_ramp_slope_violation():
    """坡道 1/8 坡度 (>1/12) → 命中 (ERROR)。"""
    r = Ramp(id="rp3", slope=1 / 8, width_m=1.5, length_m=3.0)
    v = _run(RampMaxSlope(), r)
    assert len(v) == 1 and v[0].severity == ViolationSeverity.ERROR


def test_ramp_slope_compliant():
    """坡道 1/15 坡度 (<=1/12) → 合规放行。"""
    r = Ramp(id="rp4", slope=1 / 15, width_m=1.5, length_m=3.0)
    assert len(_run(RampMaxSlope(), r)) == 0


class _NoWidth:
    """无 width_m 属性的哑元素 (测 DoorClearWidth 的 getattr 默认路径)。"""
    id = "no-width-elem"


if __name__ == "__main__":
    test_daylight_living_room_compliant()
    test_daylight_living_room_high_sill()
    test_daylight_non_living_room_skipped()
    test_bedroom_min_window_area_compliant()
    test_bedroom_min_window_area_violation()
    test_res_corridor_solid_narrow_violation()
    test_res_corridor_solid_wide_compliant()
    test_res_corridor_living_narrow_violation()
    test_res_corridor_living_wide_compliant()
    test_res_corridor_length_over()
    test_res_corridor_length_ok()
    test_window_sill_compliant()
    test_window_sill_violation()
    test_balcony_railing_low_violation()
    test_balcony_railing_ok_compliant()
    test_balcony_railing_non_balcony_skipped()
    test_fire_corridor_width_violation()
    test_fire_corridor_width_compliant()
    test_fire_corridor_length_over()
    test_fire_corridor_length_ok()
    test_door_clear_width_violation()
    test_door_clear_width_compliant()
    test_door_clear_width_missing_attr()
    test_ramp_width_violation()
    test_ramp_width_compliant()
    test_ramp_slope_violation()
    test_ramp_slope_compliant()
    print("OK: all rule branch coverage tests passed")

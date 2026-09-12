"""
几何布局引擎单元测试
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _sample_zones():
    """标准三室两厅样本：7 个 zones（含 length/width）"""
    return [
        {"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4},
        {"id": "z2", "name": "主卧", "type": "bedroom", "length": 3, "width": 4},
        {"id": "z3", "name": "次卧", "type": "bedroom", "length": 2.5, "width": 4},
        {"id": "z4", "name": "书房", "type": "bedroom", "length": 2, "width": 4},
        {"id": "z5", "name": "厨房", "type": "kitchen", "length": 2, "width": 3},
        {"id": "z6", "name": "主卫", "type": "bathroom", "length": 2, "width": 2},
        {"id": "z7", "name": "次卫", "type": "bathroom", "length": 1.5, "width": 2},
    ]


def test_layout_rooms_packs_all():
    """所有 zone 都被排进网格，坐标齐全"""
    from src.agents.src.layout import layout_rooms

    rooms = layout_rooms(_sample_zones())
    assert len(rooms) == 7
    for r in rooms:
        assert r["x"] >= 0 and r["y"] >= 0
        assert r["w"] > 0 and r["h"] > 0
        assert r["name"]


def test_layout_rooms_no_overlap():
    """任意两房间矩形不相交（允许边贴边）"""
    from src.agents.src.layout import layout_rooms

    rooms = layout_rooms(_sample_zones())
    for i, a in enumerate(rooms):
        for b in rooms[i + 1:]:
            # 水平分离 或 垂直分离 即为不重叠
            sep_x = (a["x"] + a["w"] <= b["x"] + 1e-6) or (b["x"] + b["w"] <= a["x"] + 1e-6)
            sep_y = (a["y"] + a["h"] <= b["y"] + 1e-6) or (b["y"] + b["h"] <= a["y"] + 1e-6)
            assert sep_x or sep_y, f"{a['name']} 与 {b['name']} 重叠"


def test_layout_sorted_by_area_desc():
    """房间按面积降序排列（贪心核心行为）"""
    from src.agents.src.layout import layout_rooms

    rooms = layout_rooms(_sample_zones())
    areas = [r["area"] for r in rooms]
    assert areas == sorted(areas, reverse=True)


def test_place_doors_shared_wall():
    """相邻房间（location 含 'A→B'）门精确落在共享墙中点（非中心连线中点）"""
    from src.agents.src.layout import layout_rooms, place_doors_on_walls

    zones = [
        {"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4},
        {"id": "z2", "name": "主卧", "type": "bedroom", "length": 3, "width": 4},
    ]
    rooms = layout_rooms(zones)
    doors = [{"id": "d1", "type": "interior", "width_m": 0.9, "location": "客厅→主卧"}]
    placed = place_doors_on_walls(doors, rooms)
    assert len(placed) == 1
    p = placed[0]["position"]
    by = {r["name"]: r for r in rooms}
    a, b = by["客厅"], by["主卧"]
    # 两房间同行左右相邻 → 共享竖直墙 x = a.x + a.w
    shared_x = a["x"] + a["w"]
    lo = max(a["y"], b["y"])
    hi = min(a["y"] + a["h"], b["y"] + b["h"])
    assert abs(p[0] - shared_x) < 1e-6, f"门 x 应精确在共边 x={shared_x}, 实际 {p[0]}"
    assert abs(p[1] - (lo + hi) / 2) < 1e-6, "门 y 应是共边中点"
    assert placed[0]["rotation"] == 0.0, "竖直墙 → 门扇水平开(rot 0)"


def test_door_on_unequal_rooms_still_on_wall():
    """不等高房间：门仍落在共边，不漂到墙内（旧 bug 场景）"""
    from src.agents.src.layout import layout_rooms, place_doors_on_walls

    zones = [
        {"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4},
        {"id": "z2", "name": "主卧", "type": "bedroom", "length": 3, "width": 2},
    ]
    rooms = layout_rooms(zones)
    by = {r["name"]: r for r in rooms}
    shared_x = by["客厅"]["x"] + by["客厅"]["w"]
    placed = place_doors_on_walls(
        [{"id": "d1", "location": "客厅→主卧"}], rooms)[0]
    assert abs(placed["position"][0] - shared_x) < 1e-6


def test_door_not_shared_falls_back_to_outer():
    """两房间不共边 → 门退回匹配房间的外侧边中点（仍在建筑包围盒内）"""
    from src.agents.src.layout import layout_rooms, place_doors_on_walls

    zones = [
        {"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4},
        {"id": "z2", "name": "主卧", "type": "bedroom", "length": 3, "width": 4},
        {"id": "z3", "name": "厨房", "type": "kitchen", "length": 2, "width": 3},
    ]
    rooms = layout_rooms(zones)
    placed = place_doors_on_walls([{"id": "d1", "location": "外墙南侧"}], rooms)[0]
    X0 = min(r["x"] for r in rooms)
    X1 = max(r["x"] + r["w"] for r in rooms)
    assert X0 - 1e-6 <= placed["position"][0] <= X1 + 1e-6


def test_detect_collision_door_window_same_wall():
    """同一面墙上门-窗重叠 → 检出碰撞；不同墙不报"""
    from src.agents.src.layout import detect_opening_collisions

    doors = [
        {"id": "d1", "position": (0.0, 3.5), "width": 0.9, "rotation": 0.0},  # 西墙 x=0, y 3.05~3.95
        {"id": "d2", "position": (5.0, 9.0), "width": 0.9, "rotation": 0.0},  # 另一面墙
    ]
    windows = [
        {"id": "w1", "start": (0.0, 2.6), "end": (0.0, 4.4)},  # 西墙 x=0, y 2.6~4.4 → 与 d1 重叠
        {"id": "w2", "start": (1.0, 13.0), "end": (4.0, 13.0)},  # 北墙，不与任何门同墙
    ]
    collisions = detect_opening_collisions(doors, windows)
    assert len(collisions) == 1, f"应检出 1 处(d1×w1)，实际 {len(collisions)}: {collisions}"
    c = collisions[0]
    assert {c["a_id"], c["b_id"]} == {"d1", "w1"}
    assert c["kind"] == "door-window"
    assert c["overlap_m"] > 0


def test_detect_collision_no_overlap():
    """门/窗同墙但不重叠 → 不报"""
    from src.agents.src.layout import detect_opening_collisions

    doors = [{"id": "d1", "position": (0.0, 1.0), "width": 0.9, "rotation": 0.0}]
    windows = [{"id": "w1", "start": (0.0, 4.0), "end": (0.0, 6.0)}]
    assert detect_opening_collisions(doors, windows) == []


def test_detect_collision_door_door():
    """同一门洞位置两扇门 → door-door 碰撞"""
    from src.agents.src.layout import detect_opening_collisions

    doors = [
        {"id": "d1", "position": (5.0, 8.0), "width": 1.0, "rotation": 0.0},
        {"id": "d2", "position": (5.0, 8.5), "width": 1.0, "rotation": 0.0},
    ]
    c = detect_opening_collisions(doors, [])
    assert len(c) == 1 and c[0]["kind"] == "door-door"


def test_door_single_room_location_to_outer():
    """单向 location（如 '厨房'）→ 落该房间外侧边中点"""
    from src.agents.src.layout import layout_rooms, place_doors_on_walls

    zones = [
        {"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4},
        {"id": "z2", "name": "厨房", "type": "kitchen", "length": 2, "width": 3},
    ]
    rooms = layout_rooms(zones)
    placed = place_doors_on_walls([{"id": "d1", "location": "厨房"}], rooms)[0]
    assert placed["position"] is not None


def test_window_vertical_outer_wall():
    """贴东外墙的房间 → 窗为竖直段（x 不变、y 变化），总跨度 = 边长 60%"""
    from src.agents.src.layout import layout_rooms, place_windows_on_walls

    zones = [
        {"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4},
        {"id": "z2", "name": "主卧", "type": "bedroom", "length": 3, "width": 4},
    ]
    rooms = layout_rooms(zones)
    by = {r["name"]: r for r in rooms}
    # 主卧在右列最右 → 右缘贴东外墙（最长竖直边）
    placed = place_windows_on_walls([{"id": "w2", "room": "主卧"}], rooms)[0]
    assert placed["start"][0] == placed["end"][0], "东外墙 → 竖直窗(x 不变)"
    bed = by["主卧"]
    edge_x = max(r["x"] + r["w"] for r in rooms)  # 东外墙 x
    assert abs(placed["start"][0] - edge_x) < 1e-6, "窗应在东外墙 x 上"
    span = placed["end"][1] - placed["start"][1]
    assert abs(span - bed["h"] * 0.6) < 1e-6, "竖直窗跨度 = 边长 60%"


def test_place_windows_on_outer_wall():
    """窗落在房间最长外侧墙（采光）中点 — 单房间 5x4 → 南墙(下沿 y) 水平窗"""
    from src.agents.src.layout import layout_rooms, place_windows_on_walls

    zones = [{"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4}]
    rooms = layout_rooms(zones)
    windows = [{"id": "w1", "room": "客厅", "sill_height_m": 0.9}]
    placed = place_windows_on_walls(windows, rooms)
    assert len(placed) == 1
    w = placed[0]
    # 最长外侧边 = 水平南墙(下沿 y)，窗 y 坐标 = 房间下沿
    assert abs(w["start"][1] - rooms[0]["y"]) < 1e-6
    # 窗跨度 = 该边(房间 length) 的 60%，居中于边中点
    span = w["end"][0] - w["start"][0]
    assert abs(span - rooms[0]["w"] * 0.6) < 1e-6
    # 中点对齐房间水平中线
    mid = (w["start"][0] + w["end"][0]) / 2
    assert abs(mid - (rooms[0]["x"] + rooms[0]["w"] / 2)) < 1e-6


def test_empty_input():
    """空输入优雅返回空"""
    from src.agents.src.layout import layout_rooms, place_doors_on_walls, place_windows_on_walls

    assert layout_rooms([]) == []
    assert place_doors_on_walls([], []) == []
    assert place_windows_on_walls([], []) == []

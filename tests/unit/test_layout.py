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
    """相邻房间（location 含 'A→B'）门放在两房间中心连线中点"""
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
    assert p is not None
    # 门位置应在整个布局包围盒内
    x1 = max(r["x"] + r["w"] for r in rooms)
    assert p[0] >= 0 and p[0] <= x1


def test_place_windows_on_outer_wall():
    """窗放在房间上沿（外侧）中段"""
    from src.agents.src.layout import layout_rooms, place_windows_on_walls

    zones = [{"id": "z1", "name": "客厅", "type": "living", "length": 5, "width": 4}]
    rooms = layout_rooms(zones)
    windows = [{"id": "w1", "room": "客厅", "sill_height_m": 0.9}]
    placed = place_windows_on_walls(windows, rooms)
    assert len(placed) == 1
    w = placed[0]
    # 窗 y 坐标应等于房间上沿（y + h）
    assert abs(w["start"][1] - (rooms[0]["y"] + rooms[0]["h"])) < 1e-6
    # 窗跨度 = 房间 width 的 60%
    span = w["end"][0] - w["start"][0]
    assert abs(span - rooms[0]["w"] * 0.6) < 1e-6


def test_empty_input():
    """空输入优雅返回空"""
    from src.agents.src.layout import layout_rooms, place_doors_on_walls, place_windows_on_walls

    assert layout_rooms([]) == []
    assert place_doors_on_walls([], []) == []
    assert place_windows_on_walls([], []) == []

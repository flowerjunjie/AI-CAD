"""
墙线拓扑解析单元测试（纯函数，喂内存线段，不落盘）
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _grid_segs():
    """8x6 外框 + 一竖(x=4)一横(y=3)内墙 → 4 个房间"""
    return [
        ((0, 0), (8, 0)), ((8, 0), (8, 6)), ((8, 6), (0, 6)), ((0, 6), (0, 0)),  # 外框
        ((4, 0), (4, 6)),    # 竖内墙
        ((0, 3), (8, 3)),    # 横内墙
    ]


def test_partition_rooms_grid():
    """外框+横竖内墙 → 4 房间（unary_union+polygonize 把外框切成最小格）"""
    from src.agents.src.tools.wall_topology import partition_rooms

    result = partition_rooms(_grid_segs())
    rooms = [r for r in result["rooms"] if not r["is_outer"]]
    assert len(rooms) == 4, f"外框+1竖+1横 内墙应切出 4 房间, 实际 {len(rooms)}"
    # 面积: 4x3 = 12㎡ 各 4 间
    for r in rooms:
        assert abs(r["area"] - 12.0) < 1e-6, f"房间面积应 12, 实际 {r['area']}"


def test_l_shape_keeps_large_hall():
    """L 形主厅(最大封闭面)保留为房间，不再被误当外轮廓剔除"""
    from src.agents.src.tools.wall_topology import partition_rooms

    lshape = [
        ((0, 0), (12, 0)), ((12, 0), (12, 5)),
        ((12, 5), (6, 5)), ((6, 5), (6, 9)), ((6, 9), (0, 9)), ((0, 9), (0, 0)),
        ((0, 5), (6, 5)), ((4, 0), (4, 5)), ((6, 5), (6, 9)), ((0, 3), (4, 3)),
    ]
    result = partition_rooms(lshape)
    rooms = result["rooms"]
    # L 形切出的所有面(含最大主厅)都当房间保留
    assert len(rooms) == 4, f"L 形户型应保留 4 个封闭面, 实际 {len(rooms)}"
    # 最大的那个(主厅 40㎡)也在其中
    areas = [r["area"] for r in rooms]
    assert abs(max(areas) - 40.0) < 1e-6, f"主厅 40㎡ 应保留, 实际 max={max(areas)}"


def test_open_chain_dropped():
    """外框缺一段(悬空) → 该环开放不进 rooms"""
    from src.agents.src.tools.wall_topology import partition_rooms

    segs = [
        ((0, 0), (8, 0)), ((8, 0), (8, 6)), ((8, 6), (0, 6)),  # 缺左边 (0,6)-(0,0)
    ]
    result = partition_rooms(segs)
    # 缺边不成闭合外框, 房间应为 0
    rooms = [r for r in result["rooms"] if not r["is_outer"]]
    assert len(rooms) == 0


def test_min_area_filters():
    """小碎环/薄壁被 min_room_area 过滤"""
    from src.agents.src.tools.wall_topology import partition_rooms

    segs = _grid_segs()
    # 加大面积阈值, 12㎡ 房间会被过滤
    result = partition_rooms(segs, min_room_area=20.0)
    rooms = [r for r in result["rooms"] if not r["is_outer"]]
    assert len(rooms) == 0, "min_room_area=20 应过滤掉 12㎡ 房间"


def test_empty_and_degenerate():
    """空输入/退化线段不崩"""
    from src.agents.src.tools.wall_topology import partition_rooms

    assert partition_rooms([])["rooms"] == []
    # 退化(零长)线段
    result = partition_rooms([((1, 1), (1, 1))])
    assert result["rooms"] == []


def test_colinear_crossing_not_fold():
    """十字路口 4 线相交 → polygonize 正确切出 9 个最小格"""
    from src.agents.src.tools.wall_topology import partition_rooms

    segs = [
        # 外框 3x3
        ((0, 0), (3, 0)), ((3, 0), (3, 3)), ((3, 3), (0, 3)), ((0, 3), (0, 0)),
        # 内部竖
        ((1, 0), (1, 3)), ((2, 0), (2, 3)),
        # 内部横
        ((0, 1), (3, 1)), ((0, 2), (3, 2)),
    ]
    result = partition_rooms(segs)
    rooms = [r for r in result["rooms"] if not r["is_outer"]]
    assert len(rooms) == 9, f"3x3 全网格应切出 9 个房间, 实际 {len(rooms)}"
    for r in rooms:
        assert abs(r["area"] - 1.0) < 1e-6, f"每格 1x1=1㎡, 实际 {r['area']}"

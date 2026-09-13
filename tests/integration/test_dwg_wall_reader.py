"""
集成测试 — DWG/DXF 墙线读取 → 真实户型解析全链路
程序化造 .dxf 喂 DXFReader（ezdxf 写 dxf 无障碍，不依赖真实 .dwg / ODA）
"""
import os
import sys

import pytest

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def _make_test_dxf(path: str, with_doors: bool = False) -> None:
    """造 8x6 外框 + 1 竖 + 1 横内墙的户型图（可选带门洞断墙）。"""
    import ezdxf

    doc = ezdxf.new("AC1027")
    doc.layers.new("WALL")
    doc.layers.new("DOOR")
    msp = doc.modelspace()
    # 外框 4 条
    msp.add_line((0, 0), (8, 0), dxfattribs={"layer": "WALL"})
    msp.add_line((8, 0), (8, 6), dxfattribs={"layer": "WALL"})
    msp.add_line((8, 6), (0, 6), dxfattribs={"layer": "WALL"})
    msp.add_line((0, 6), (0, 0), dxfattribs={"layer": "WALL"})
    # 内墙 2 条（竖 x=4, 横 y=3）
    msp.add_line((4, 0), (4, 6), dxfattribs={"layer": "WALL"})
    msp.add_line((0, 3), (8, 3), dxfattribs={"layer": "WALL"})
    if with_doors:
        # 门洞：竖墙 x=4 处留一段 DOOR（墙在此断开由 DOOR 补边闭合）
        msp.add_line((4, 2.0), (4, 3.0), dxfattribs={"layer": "DOOR"})
    doc.saveas(path)


def test_read_wall_segments_dxf(tmp_path):
    """DXFReader.get_wall_segments 按图层捞墙线，非墙图层排除"""
    from src.agents.src.tools.cad_tools import DXFReader

    p = str(tmp_path / "floorplan.dxf")
    _make_test_dxf(p, with_doors=True)

    reader = DXFReader(p)
    assert reader.open(), "DXF 打开失败"
    segs = reader.get_wall_segments(layer_names=("WALL",))
    # 4 外框 + 2 内墙 = 6 段（DOOR 层不算墙）
    assert len(segs) == 6, f"WALL 图层应 6 段, 实际 {len(segs)}"
    for a, b in segs:
        assert isinstance(a, tuple) and isinstance(b, tuple)


def test_dxf_to_real_topology(tmp_path):
    """程序化 .dxf → 读墙线 → partition_rooms 切出 4 个真实房间"""
    from src.agents.src.tools.cad_tools import DXFReader
    from src.agents.src.tools.wall_topology import partition_rooms

    p = str(tmp_path / "floorplan.dxf")
    _make_test_dxf(p, with_doors=False)

    reader = DXFReader(p)
    assert reader.open()
    segs = reader.get_wall_segments()
    result = partition_rooms(segs)

    rooms = [r for r in result["rooms"] if not r["is_outer"]]
    assert len(rooms) == 4, f"8x6 + 1竖 + 1横 应切 4 房间, 实际 {len(rooms)}"
    for r in rooms:
        assert abs(r["area"] - 12.0) < 1e-6, f"每格 4x3=12㎡, 实际 {r['area']}"
        assert r["polygon"], "房间多边形非空"


def test_door_bridge_closes_gap(tmp_path):
    """门洞补虚拟边：墙在门处断开，DOOR 段补边后仍能闭合切房"""
    from src.agents.src.tools.cad_tools import DXFReader
    from src.agents.src.tools.wall_topology import partition_rooms, add_door_bridge_edges

    p = str(tmp_path / "floorplan_door.dxf")
    _make_test_dxf(p, with_doors=True)

    reader = DXFReader(p)
    assert reader.open()
    wall_segs = reader.get_wall_segments(layer_names=("WALL",))
    door_segs = reader.get_wall_segments(layer_names=("DOOR",))
    # 门段作虚拟边补进墙线, 让断墙闭合
    merged = add_door_bridge_edges(wall_segs, door_segs)
    result = partition_rooms(merged)
    assert result["rooms"], "门洞补边后应仍切出房间"

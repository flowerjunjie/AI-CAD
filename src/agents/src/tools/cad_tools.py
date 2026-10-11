"""
CAD 引擎工具封装 — ezdxf 读写 + COM 接口
双引擎策略：ezdxf 读 + COM 写
"""
from typing import Optional
import math

# 几何数据类已拆到 cad_types.py (破 1051 行); 本模块 re-export 兜住旧 import 路径
# (`from ...cad_tools import Wall/Point/...`) — 20+ 处引用 0 改动 (兼容层, 2026-10-11)。
from src.agents.src.tools.cad_types import (  # noqa: F401
    Point, Wall, Door, Window, Pipe, Beam, Column, Outlet,
    Switch, HvacDuct, HvacUnit, HvacGrille,
)


# DXFReader 已拆到 dxf_reader.py (破 1051 行); re-export 兜旧 import 路径 (兼容层, 2026-10-11)。
from src.agents.src.tools.dxf_reader import DXFReader  # noqa: F401

# DXFWriter + 出图 marker 对账 已拆到 dxf_writer.py (破 1051 行);
# re-export 兜旧 import 路径 (`from ...cad_tools import DXFWriter/verify_dwg_markers`) —
# 全仓 20+ 处引用 0 改动 (兼容层, 2026-10-11)。
from src.agents.src.tools.dxf_writer import (  # noqa: F401
    DXFWriter, count_dwg_markers, verify_dwg_markers,
)


# ─── Demo ───────────────────────────────────────────────────────

if __name__ == "__main__":
    # Demo: 创建简单 DWG
    writer = DXFWriter()
    writer.new()

    # 画一面墙
    writer.add_wall(Wall(
        start=Point(0, 0),
        end=Point(5, 0),
        thickness=0.24
    ))

    # 画一扇门
    writer.add_door(Door(
        position=Point(2, 0),
        width=0.9,
        rotation=0
    ))

    # 保存
    if writer.save("/tmp/demo.dwg"):
        print("Demo DWG saved to /tmp/demo.dwg")
    else:
        print("Failed to save demo DWG")

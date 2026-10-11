"""
CAD 几何数据类 — 出图元素的纯数据结构 (无 ezdxf / 无读写逻辑)。

从 cad_tools.py 拆出 (2026-10-11 文件健康轮: 破 1051 行)。
只依赖标准库 dataclasses, 自包含, 不引 Reader/Writer — 契约面最小。
cad_tools.py 顶部 re-export 本模块全部数据类, 旧 import 路径
(`from ...cad_tools import Wall`) 仍有效 (兼容层, 20+ 处引用 0 改动)。
"""
from dataclasses import dataclass


@dataclass
class Point:
    x: float
    y: float
    z: float = 0.0


@dataclass
class Wall:
    """墙体元素"""
    start: Point
    end: Point
    thickness: float = 0.24  # 默认240墙
    layer: str = "WALL"


@dataclass
class Door:
    """门元素"""
    position: Point
    width: float = 0.9
    height: float = 2.1
    rotation: float = 0.0  # 角度（度）
    layer: str = "DOOR"


@dataclass
class Window:
    """窗户元素"""
    start: Point
    end: Point
    sill_height: float = 0.9
    layer: str = "WINDOW"


@dataclass
class Pipe:
    """给排水管元素（线段，仿 Wall）"""
    start: Point
    end: Point
    diameter_mm: int = 50   # 公称管径 DN
    layer: str = "PIPE"


@dataclass
class Beam:
    """结构梁元素（线段，仿 Pipe；截面宽/高 mm）

    span_m: 跨度 (m)。默认 0.0 保持回归安全；出图侧 add_beam 若见 0 会
    按 start/end 端点几何补算 (上游契约 §2.1 物理来源)。
    """
    start: Point
    end: Point
    width_mm: int = 300
    depth_mm: int = 600
    layer: str = "BEAM"
    span_m: float = 0.0


@dataclass
class Column:
    """结构柱元素（块/矩形，仿 INSERT 点位；截面短边 mm）"""
    position: Point
    section_mm: int = 400
    layer: str = "COLUMN"


@dataclass
class Outlet:
    """电气插座点位（点位类，仿 Column；高度 m）"""
    position: Point
    height_m: float = 0.3
    layer: str = "ELEC_OUTLET"


@dataclass
class Switch:
    """电气开关点位（点位类，仿 Column；高度 m）"""
    position: Point
    height_m: float = 1.3
    layer: str = "ELEC_SWITCH"


@dataclass
class HvacDuct:
    """暖通风管元素（线段类，仿 Pipe；截面/管径 mm）"""
    start: Point
    end: Point
    diameter_mm: int = 100
    layer: str = "HVAC_DUCT"


@dataclass
class HvacUnit:
    """空调机组点位（点位类，仿 Column；制冷量 kW）"""
    position: Point
    cooling_kw: float = 0.0
    layer: str = "HVAC_UNIT"


@dataclass
class HvacGrille:
    """风口点位（点位类，仿 Column；安装高度 m）"""
    position: Point
    height_m: float = 2.5
    layer: str = "HVAC_GRILLE"

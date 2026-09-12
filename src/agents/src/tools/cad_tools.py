"""
CAD 引擎工具封装 — ezdxf 读写 + COM 接口
双引擎策略：ezdxf 读 + COM 写
"""
from dataclasses import dataclass
from typing import Optional
import math


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


class DXFReader:
    """ezdxf DWG 读取器"""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.doc = None
        self.entities = {}

    def open(self) -> bool:
        """打开 DWG 文件"""
        try:
            import ezdxf
            self.doc = ezdxf.readfile(self.file_path)
            self._collect_entities()
            return True
        except ImportError:
            print("ezdxf not installed. Run: pip install ezdxf")
            return False
        except Exception as e:
            print(f"Failed to open DWG: {e}")
            return False

    def _collect_entities(self) -> None:
        """收集所有实体"""
        msp = self.doc.modelspace()
        self.entities = {
            "lines": list(msp.query('LINE')),
            "circles": list(msp.query('CIRCLE')),
            "arcs": list(msp.query('ARC')),
            "text": list(msp.query('TEXT MTEXT')),
            "dimensions": list(msp.query('DIMENSION')),
        }

    def get_layers(self) -> list[str]:
        """获取所有图层"""
        return list(self.doc.layers)

    def get_entity_count(self) -> dict:
        """获取各类型实体数量"""
        return {k: len(v) for k, v in self.entities.items()}


class DXFWriter:
    """ezdxf DWG 写入器"""

    def __init__(self):
        self.doc = None
        self.msp = None

    def new(self, dxfver: str = "AC1027") -> None:
        """创建新文档"""
        import ezdxf
        self.doc = ezdxf.new(dxfver)
        self.msp = self.doc.modelspace()

    def add_wall(self, wall: Wall) -> None:
        """添加墙体"""
        self.msp.add_line(
            (wall.start.x, wall.start.y),
            (wall.end.x, wall.end.y),
            dxfattribs={
                "layer": wall.layer,
            }
        )

    def add_door(self, door: Door) -> None:
        """添加门（简化表示为弧线）"""
        angle = math.radians(door.rotation)
        cx = door.position.x
        cy = door.position.y
        r = door.width
        # 画门扇弧线
        self.msp.add_arc(
            (cx, cy),
            radius=r,
            start_angle=angle,
            end_angle=angle + math.pi / 2,
            dxfattribs={"layer": door.layer}
        )

    def add_window(self, window: Window) -> None:
        """添加窗户（简化表示为双线）"""
        self.msp.add_line(
            (window.start.x, window.start.y),
            (window.end.x, window.end.y),
            dxfattribs={"layer": window.layer}
        )
        # 窗中线
        self.msp.add_line(
            (window.start.x, window.start.y - 0.05),
            (window.end.x, window.end.y - 0.05),
            dxfattribs={"layer": window.layer}
        )

    def add_dimension(self, start: Point, end: Point, offset: float = 0.3, text: str = "") -> None:
        """添加尺寸标注（简化为带文字的引线）"""
        # 标注线
        self.msp.add_line(
            (start.x, start.y + offset),
            (end.x, end.y + offset),
            dxfattribs={"layer": "DIMENSION"}
        )
        # 尺寸界线
        self.msp.add_line((start.x, start.y), (start.x, start.y + offset), dxfattribs={"layer": "DIMENSION"})
        self.msp.add_line((end.x, end.y), (end.x, end.y + offset), dxfattribs={"layer": "DIMENSION"})
        # 标注文字
        mid_x = (start.x + end.x) / 2
        mid_y = start.y + offset + 0.1
        if text:
            self.msp.add_text(text, dxfattribs={"height": 0.15, "layer": "DIMENSION"})

    def save(self, path: str) -> bool:
        """保存 DWG"""
        try:
            self.doc.saveas(path)
            return True
        except Exception as e:
            print(f"Save failed: {e}")
            return False


# ─── COM Interface (Windows only) ───────────────────────────────

class COMCadInterface:
    """AutoCAD COM 接口（Windows 专用）"""

    def __init__(self):
        self._application = None

    @property
    def is_available(self) -> bool:
        """检查 COM 接口是否可用"""
        if self._application is None:
            try:
                import win32com.client
                self._application = win32com.client.Dispatch("AutoCAD.Application")
                return True
            except Exception:
                return False
        return True

    def open_document(self, path: str) -> bool:
        """打开文档"""
        if not self.is_available:
            print("COM interface not available (non-Windows or AutoCAD not installed)")
            return False
        try:
            import win32com.client
            doc = self._application.Documents.Open(path)
            return doc is not None
        except Exception as e:
            print(f"COM open failed: {e}")
            return False

    def draw_line(self, start: tuple, end: tuple) -> bool:
        """绘制直线"""
        if not self.is_available:
            return False
        try:
            import win32com.client
            self._application.ActiveDocument.ModelSpace. \
                AddLine(start, end)
            return True
        except Exception as e:
            print(f"COM draw failed: {e}")
            return False

    def save(self, path: str) -> bool:
        """保存文档"""
        if not self.is_available:
            return False
        try:
            self._application.ActiveDocument.SaveAs(path)
            return True
        except Exception as e:
            print(f"COM save failed: {e}")
            return False


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

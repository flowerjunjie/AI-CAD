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

    def _segments_from_layer(self, layer_names) -> list:
        """按图层取线段核心逻辑 → [(start_xy, end_xy), ...]（2D，z 丢弃）。

        LINE 逐条取 start/end；LWPOLYLINE 展开相邻顶点对（闭合则补首尾）。
        返回与 ezdxf 格式解耦的纯线段。墙/给排水各图层读取共用此法。
        """
        msp = self.doc.modelspace()
        segs = []
        # LINE: 逐条取 start/end
        for layer in layer_names:
            for ln in msp.query(f'LINE[layer=="{layer}"]'):
                segs.append(((ln.dxf.start[0], ln.dxf.start[1]),
                              (ln.dxf.end[0], ln.dxf.end[1])))
        # LWPOLYLINE: 相邻顶点对展开，闭合则补首尾
        for layer in layer_names:
            for lwp in msp.query(f'LWPOLYLINE[layer=="{layer}"]'):
                # ezdxf>=1.0: points() 是上下文管理器, format='xy' 给 (x,y)
                with lwp.points(format='xy') as pts:
                    pts = [(v[0], v[1]) for v in pts]
                n = len(pts)
                if n < 2:
                    continue
                for i in range(n - 1):
                    segs.append((pts[i], pts[i + 1]))
                if getattr(lwp, "closed", False) and n > 2:
                    segs.append((pts[-1], pts[0]))
        return segs

    def get_wall_segments(self, layer_names=("WALL", "WALL_THICK")) -> list:
        """
        按图层读墙线段 → [(start_xy, end_xy), ...]（2D，z 丢弃）。
        支持 LINE + LWPOLYLINE（展开相邻顶点对；闭合则补首尾）。
        返回与 ezdxf 格式解耦的纯线段，供 wall_topology 解析真实户型。
        """
        if self.doc is None:
            raise RuntimeError("调用 get_wall_segments 前需先 open()")
        return self._segments_from_layer(layer_names)

    def get_plumbing_segments(
        self,
        layer_names=("PIPE", "PIPE_WASTE", "PIPE_VENT", "PIPE_DRAIN"),
        include_layer: bool = False,
    ) -> list:
        """按图层读给排水管道线段。

        include_layer=False (默认): 返回纯线段 [(start_xy, end_xy), ...]，
            与 get_wall_segments 形态一致（start/end 为 2 元组）。
        include_layer=True: 返回统一结构化 dict
            [{"start": start_xy, "end": end_xy, "layer": layer}, ...]，
            每条都带来源图层，供 plumbing_extractor 按图层映射管径。
            结构化 dict 消除「纯线段 vs 带图层」的形态歧义。
        """
        if self.doc is None:
            raise RuntimeError("调用 get_plumbing_segments 前需先 open()")
        if not include_layer:
            return self._segments_from_layer(layer_names)
        # 按图层分组再平铺，给每段补上来源图层（统一 dict 形态）
        out = []
        for layer in layer_names:
            for a, b in self._segments_from_layer((layer,)):
                out.append({"start": a, "end": b, "layer": layer})
        return out


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

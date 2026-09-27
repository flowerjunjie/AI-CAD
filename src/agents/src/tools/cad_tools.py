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


@dataclass
class Pipe:
    """给排水管元素（线段，仿 Wall）"""
    start: Point
    end: Point
    diameter_mm: int = 50   # 公称管径 DN
    layer: str = "PIPE"


@dataclass
class Beam:
    """结构梁元素（线段，仿 Pipe；截面宽/高 mm）"""
    start: Point
    end: Point
    width_mm: int = 300
    depth_mm: int = 600
    layer: str = "BEAM"


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

    def get_structural_segments(
        self,
        layer_names=("BEAM", "WALL_SHEAR"),
        include_layer: bool = False,
    ) -> list:
        """按图层读结构梁/承重墙线段（照 get_plumbing_segments 范式）。

        include_layer=False (默认): 纯线段 [(start_xy, end_xy), ...]。
        include_layer=True: 统一结构化 dict
            [{"start": start_xy, "end": end_xy, "layer": layer}, ...]，
            每条带来源图层，供 structural_extractor 按图层映射 beam_type/width_mm。
        契约: docs/structural-upstream-contract.md §2.1
        """
        if self.doc is None:
            raise RuntimeError("调用 get_structural_segments 前需先 open()")
        if not include_layer:
            return self._segments_from_layer(layer_names)
        out = []
        for layer in layer_names:
            for a, b in self._segments_from_layer((layer,)):
                out.append({"start": a, "end": b, "layer": layer})
        return out

    def get_element_blocks(self, layer_names) -> list:
        """通用底座：按图层读 INSERT 块 → 结构化 dict（与 ezdxf 实体解耦）。

        结构/电气/暖通等一切「元素画成 INSERT 块引用」的专业共用这一份
        INSERT 读取逻辑，下游只加各自的「图层/块名 → kind」映射 dict。
        每项: {"block_name": ..., "x": ..., "y": ..., "layer": ...}
        - 插入点取 dxf.insert 前 2 个值 (x, y)，z 丢弃（与线段类一致）
        - 只认 INSERT 实体；同图层的 CIRCLE/多边形不算元素（避免误抓门窗小圆圈）

        实测 (ezdxf 1.4.4): msp.query('INSERT[layer=="<图层>"]')
        返回实体的 .dxf.name / .dxf.insert(3 元组取前 2) / .dxf.layer。
        契约: docs/element-upstream-contract.md §2
        """
        if self.doc is None:
            raise RuntimeError("调用 get_element_blocks 前需先 open()")
        msp = self.doc.modelspace()
        out = []
        for layer in layer_names:
            for ins in msp.query(f'INSERT[layer=="{layer}"]'):
                # ATTRIB 数值透传 (tag → text 值): 电气 height_m/has_earthing、
                # 暖通 velocity_ms/location_type 等「元素画成带属性 INSERT 块」时,
                # 数值就挂在块的 ATTRIB 上。缺则 attrs 为空 dict, 下游 extractor
                # 退回占位默认 (向后兼容: 原 4 键全保留, attrs 为纯增量)。
                attrs = {a.dxf.tag: a.dxf.text for a in ins.attribs}
                out.append({
                    "block_name": ins.dxf.name,
                    "x": ins.dxf.insert[0],
                    "y": ins.dxf.insert[1],
                    "layer": ins.dxf.layer,
                    "attrs": attrs,
                })
        return out

    def get_structural_blocks(self, layer_names=("COLUMN", "FOUNDATION", "NODE")) -> list:
        """按图层读结构 INSERT 块（柱/基础/节点）—— 通用底座的薄封装。

        底层 INSERT 读取只有一份: get_element_blocks。本方法只负责
        结构专业的默认图层组。
        契约: docs/element-upstream-contract.md §2
        """
        return self.get_element_blocks(layer_names)

    def get_electrical_points(self, layer_names=("ELEC_OUTLET", "ELEC_SWITCH")) -> list:
        """按图层读电气插座/开关 INSERT 块 → 点位 dict（喂 electrical_extractor）。

        通用底座 get_element_blocks + 电气「图层 → kind」占位映射。
        每项: {"kind","id","x","y","height_m"(占位),"room_type"(缺省),
               "has_earthing"(缺省, 仅 outlet)} — 字段对齐
        electrical_extractor.extract_electrical_points 的点位契约。
        映射值全 TBD 占位, 业务确认图层/块名约定后改本文件映射, 不改结构。
        契约: docs/element-upstream-contract.md §3
        """
        _LAYER = {"ELEC_OUTLET": "outlet", "ELEC_SWITCH": "switch"}  # TBD: 图层名
        _BLOCK = {"OUTLET_STD": "outlet", "SWITCH_STD": "switch"}   # TBD: 块名
        _DEFAULT = "outlet"  # TBD: 未识别退默认插座
        out = []
        for blk in self.get_element_blocks(layer_names):
            kind = _BLOCK.get(blk["block_name"]) or _LAYER.get(blk["layer"], _DEFAULT)
            # 数值字段: 优先读 INSERT 块 ATTRIB (agent 造样本时可写真实值), 缺则 None
            # 让 extractor 退占位默认。ATTRIB 值全是字符串, 须强转:
            # height_m → float (None 跳过); has_earthing → bool (小写 'true'/'false',
            # 避免 bool('false')==True 的坑, 空值 None 让 extractor 兜底 True)。
            a = blk.get("attrs", {})
            raw_h = a.get("height_m")
            try:
                height_m = float(raw_h) if raw_h not in (None, "") else None
            except (TypeError, ValueError):
                height_m = None
            raw_e = (a.get("has_earthing") or "").strip().lower()
            if raw_e in ("true", "false"):
                has_earthing = raw_e == "true"
            else:
                has_earthing = None  # 缺省, extractor 兜底 True (outlet)
            out.append({
                "kind": kind,
                "id": blk["block_name"],
                "x": blk["x"],
                "y": blk["y"],
                "height_m": height_m,
                "room_type": a.get("room_type"),
                "has_earthing": has_earthing,
            })
        return out

    def get_hvac_points(self, layer_names=("HVAC_DUCT", "HVAC_UNIT", "HVAC_GRILLE")) -> list:
        """按图层读暖通风管/机组/风口 INSERT 块 → 点位 dict（喂 hvac_extractor）。

        通用底座 get_element_blocks + 暖通「图层 → kind」占位映射。
        每项: {"kind","id","x","y"} + kind 对应字段(缺省 None, extractor 兜底占位)。
        字段对齐 hvac_extractor.extract_hvac_points 的点位契约。
        映射值全 TBD 占位, 业务确认图层/块名约定后改本文件映射, 不改结构。
        契约: docs/element-upstream-contract.md §4
        """
        _LAYER = {"HVAC_DUCT": "duct", "HVAC_UNIT": "unit", "HVAC_GRILLE": "grille"}  # TBD
        _BLOCK = {"DUCT_STD": "duct", "UNIT_STD": "unit", "GRILLE_STD": "grille"}  # TBD
        _DEFAULT = "duct"  # TBD: 未识别退默认风管
        out = []
        for blk in self.get_element_blocks(layer_names):
            kind = _BLOCK.get(blk["block_name"]) or _LAYER.get(blk["layer"], _DEFAULT)
            item = {"kind": kind, "id": blk["block_name"], "x": blk["x"], "y": blk["y"]}
            # 只带当前 kind 相关的缺省键 (value None), 让 extractor 按 kind 兜底占位
            _EXTRA = {
                "duct": {"duct_type": None, "diameter_mm": None,
                         "velocity_ms": None, "airflow_m3h": None},
                "unit": {"unit_type": None, "cooling_kw": None, "location_type": None},
                "grille": {"grille_type": None, "height_m": None,
                           "airflow_m3h": None, "room_type": None},
            }
            item.update(_EXTRA.get(kind, {}))
            out.append(item)
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
        """添加墙体（中心线）"""
        self.msp.add_line(
            (wall.start.x, wall.start.y),
            (wall.end.x, wall.end.y),
            dxfattribs={
                "layer": wall.layer,
            }
        )

    def add_wall_thickness(self, wall: Wall) -> None:
        """添加墙体厚度标注 — 在 CENTERLINE 图层画「双线墙」偏置轮廓。

        端点序列 (LWPOLYLINE, close=True):
        水平墙 (|dy|<eps): 上偏置 y+th/2 两条端点 → 下偏置 y-th/2 两条端点
        竖直墙 (|dx|<eps): 右偏置 x+th/2 两条端点 → 左偏置 x-th/2 两条端点
        斜墙: 跳过 (MVP 仅横平竖直布局)
        """
        eps = 1e-9
        dx = wall.end.x - wall.start.x
        dy = wall.end.y - wall.start.y
        t = wall.thickness / 2.0
        if abs(dy) < eps:  # 水平墙: 偏置沿 y
            x0, y0 = wall.start.x, wall.start.y
            x1 = wall.end.x
            pts = [
                (x0, y0 + t), (x1, y0 + t),
                (x0, y0 - t), (x1, y0 - t),
            ]
        elif abs(dx) < eps:  # 竖直墙: 偏置沿 x
            x0, y0 = wall.start.x, wall.start.y
            y1 = wall.end.y
            pts = [
                (x0 + t, y0), (x0 + t, y1),
                (x0 - t, y0), (x0 - t, y1),
            ]
        else:  # 斜墙: MVP 不画
            return
        # 显式建图层 — DWG 二进制格式省略空图层 (零实体), 读回后
        # doc.layers 不含 CENTERLINE, 下游按图层查询会失败
        if "CENTERLINE" not in self.doc.layers:
            self.doc.layers.new("CENTERLINE")
        self.msp.add_lwpolyline(pts, dxfattribs={"layer": "CENTERLINE"})

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

    def add_opening_marker(self, mark: str, position: tuple[float, float],
                           layer: str = "OPENING_TAG") -> None:
        """在门窗旁画编号文字 (M1 / C1 ...) — OPENING_TAG 层。

        P0 最小版: 不真 INSERT 块, 用 TEXT 图例带编号贯穿 layout→出图→标注。
        mark 直接来自 numbering.py 的 number/mark 键, 写在哪由调用方定
        (门在洞口中点旁, 窗在段中点旁), 本方法只负责「画字」。
        """
        if layer not in self.doc.layers:
            self.doc.layers.new(layer)
        txt = self.msp.add_text(mark, dxfattribs={"height": 0.2, "layer": layer})
        txt.dxf.insert = (position[0], position[1])

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

    def add_opening_dimensions(
        self,
        doors: list[dict],
        windows: list[dict],
        offset: float = 0.5,
    ) -> int:
        """添加洞口标注（门宽/窗宽数字），返回标注数量。

        洞口标注 = 「门/窗 宽多少米」，画在洞口上方 (offset) 的 DIMENSION 层。
        - 门: door dict 有 position+width+rotation (来自 place_doors_on_walls)
              rotation==0 → 竖直墙门 (沿 y 展开); 否则 → 水平墙门 (沿 x 展开)
              标注画在洞口中点下方 offset, 文字 = f"{width:.1f}"
        - 窗: window dict 有 start+end (来自 place_windows_on_walls)
              水平窗 (dy≈0) 标在 (mid_x, y-offset); 竖直窗 标在 (x, mid_y-offset)
              文字 = f"{跨度:.2f}"
        文字层: DIMENSION (与 add_dimension 同层, 便于统一开关)
        """
        count = 0
        for d in doors:
            px, py = d.get("position", (0.0, 0.0))
            w = float(d.get("width", 0.9))
            rot = float(d.get("rotation", 0.0))
            if rot == 0.0:
                # 竖直墙门 (沿 y 展开): 洞口中点 (px, py), 标注放下方
                ax, ay = px, py - offset
            else:
                # 水平墙门 (沿 x 展开): 洞口中点 (px, py), 标注放下方
                ax, ay = px, py - offset
            txt = self.msp.add_text(f"{w:.1f}", dxfattribs={"height": 0.15, "layer": "DIMENSION"})
            txt.dxf.insert = (ax, ay)
            count += 1
        for wn in windows:
            (x0, y0), (x1, y1) = wn.get("start", (0.0, 0.0)), wn.get("end", (1.0, 0.0))
            if abs(y0 - y1) < 1e-6:
                span = abs(x1 - x0)
                ax, ay = (x0 + x1) / 2, y0 - offset
            else:
                span = abs(y1 - y0)
                ax, ay = x0, (y0 + y1) / 2 - offset
            txt = self.msp.add_text(f"{span:.2f}", dxfattribs={"height": 0.15, "layer": "DIMENSION"})
            txt.dxf.insert = (ax, ay)
            count += 1
        return count

    def add_pipe(self, pipe: Pipe, label_offset: float = 0.15) -> int:
        """添加给排水管线段 + 管径标注，返回标注条数（0 或 1）。

        出图范式照 add_wall_thickness（线段类元素 LWPOLYLINE 偏置双线）：
        - 管线本体: PIPE 图层 LWPOLYLINE，端点序列 (start, end) 两点（不闭合，
          单条线管段 = 2 顶点 LWPOLYLINE，等价 LINE 但可复用 polyline 读回通道）。
        - 管径标注: 仿 add_opening_dimensions 的「文字 + DIMENSION 层」风格，
          在管段中点上方 offset 处画 TEXT "DN{diameter_mm}"。

        管段支持任意方向（给排水管路可斜走，不做横平竖直限制）。
        显式建图层 — DWG 二进制省略零实体空图层，须先 layers.new 再 add。
        """
        if "PIPE" not in self.doc.layers:
            self.doc.layers.new("PIPE")
        if "PIPE_LABEL" not in self.doc.layers:
            self.doc.layers.new("PIPE_LABEL")
        # 管线本体: LWPOLYLINE 两点（不闭合）
        self.msp.add_lwpolyline(
            [(pipe.start.x, pipe.start.y), (pipe.end.x, pipe.end.y)],
            close=False,
            dxfattribs={"layer": pipe.layer},
        )
        # 管径标注: 中点上方 offset 处 TEXT "DN{管径}"
        mid_x = (pipe.start.x + pipe.end.x) / 2.0
        mid_y = (pipe.start.y + pipe.end.y) / 2.0
        txt = self.msp.add_text(
            f"DN{pipe.diameter_mm}",
            dxfattribs={"height": 0.15, "layer": "PIPE_LABEL"},
        )
        txt.dxf.insert = (mid_x, mid_y + label_offset)
        return 1

    def add_beam(self, beam: Beam, label_offset: float = 0.15) -> int:
        """添加结构梁线段 + 截面标注，返回标注条数（0 或 1）。

        出图范式照 add_pipe（线段类 LWPOLYLINE + 独立标注层 TEXT）：
        - 梁本体: BEAM 图层 LWPOLYLINE，端点序列 (start, end) 两点（不闭合）。
        - 截面标注: 仿 PIPE_LABEL 范式, BEAM_LABEL 层 TEXT "{宽}x{高}"
          画在梁段中点上方 offset 处。

        显式建图层 — DWG 二进制省略零实体空图层，须先 layers.new 再 add。
        """
        if beam.layer not in self.doc.layers:
            self.doc.layers.new(beam.layer)
        if "BEAM_LABEL" not in self.doc.layers:
            self.doc.layers.new("BEAM_LABEL")
        # 梁本体: LWPOLYLINE 两点（不闭合）
        self.msp.add_lwpolyline(
            [(beam.start.x, beam.start.y), (beam.end.x, beam.end.y)],
            close=False,
            dxfattribs={"layer": beam.layer},
        )
        # 截面标注: 中点上方 offset 处 TEXT "{宽}x{高}"
        mid_x = (beam.start.x + beam.end.x) / 2.0
        mid_y = (beam.start.y + beam.end.y) / 2.0
        txt = self.msp.add_text(
            f"{beam.width_mm}x{beam.depth_mm}",
            dxfattribs={"height": 0.15, "layer": "BEAM_LABEL"},
        )
        txt.dxf.insert = (mid_x, mid_y + label_offset)
        return 1

    def add_column(self, col: Column, label_offset: float = 0.15) -> int:
        """添加结构柱（截面矩形）+ 截面标注，返回标注条数（0 或 1）。

        出图范式照 add_opening_marker 的点位范式（以 point 定位）：
        - 柱本体: COLUMN 图层 LWPOLYLINE 正方形（闭合, insert 点为左下顶角,
          边长 = 截面短边 mm/1000 m）, 读回走与 pipe/beam 相同的 polyline 通道。
        - 截面标注: 仿 BEAM_LABEL 范式, COLUMN_LABEL 层 TEXT "{短边}x{短边}"
          画在柱心（插入点上方半边长）上方 offset 处。

        显式建图层 — DWG 二进制省略零实体空图层，须先 layers.new 再 add。
        """
        if col.layer not in self.doc.layers:
            self.doc.layers.new(col.layer)
        if "COLUMN_LABEL" not in self.doc.layers:
            self.doc.layers.new("COLUMN_LABEL")
        half = col.section_mm / 1000.0 / 2.0
        x0, y0 = col.position.x - half, col.position.y - half
        # 柱本体: 闭合正方形 LWPOLYLINE
        self.msp.add_lwpolyline(
            [(x0, y0), (x0 + 2 * half, y0),
             (x0 + 2 * half, y0 + 2 * half), (x0, y0 + 2 * half)],
            close=True,
            dxfattribs={"layer": col.layer},
        )
        # 截面标注: 柱心上方 offset 处 TEXT "{短边}x{短边}"
        txt = self.msp.add_text(
            f"{col.section_mm}x{col.section_mm}",
            dxfattribs={"height": 0.15, "layer": "COLUMN_LABEL"},
        )
        txt.dxf.insert = (col.position.x, col.position.y + label_offset)
        return 1

    def _add_point_symbol(
        self,
        position: Point,
        layer: str,
        side_mm: int,
        label: str,
        label_layer: str,
        label_offset: float,
    ) -> int:
        """点位类通用底座：闭合正方形 LWPOLYLINE（点位符号）+ 高度/编号 TEXT 标注。

        照 add_column 范式（点位画在 position 为中心的正方形 + 独立标注层 TEXT）。
        电气插座/开关、暖通机组/风口共此一份（点位符号几何一致，仅边长/标注文案不同）。
        显式建图层 — DWG 二进制省略零实体空图层，须先 layers.new 再 add。
        """
        if layer not in self.doc.layers:
            self.doc.layers.new(layer)
        if label_layer not in self.doc.layers:
            self.doc.layers.new(label_layer)
        half = side_mm / 1000.0 / 2.0
        x0, y0 = position.x - half, position.y - half
        # 点位符号: 闭合正方形 LWPOLYLINE
        self.msp.add_lwpolyline(
            [(x0, y0), (x0 + 2 * half, y0),
             (x0 + 2 * half, y0 + 2 * half), (x0, y0 + 2 * half)],
            close=True,
            dxfattribs={"layer": layer},
        )
        # 标注: 点位心上方 offset 处 TEXT
        txt = self.msp.add_text(label, dxfattribs={"height": 0.15, "layer": label_layer})
        txt.dxf.insert = (position.x, position.y + label_offset)
        return 1

    def add_outlet(self, outlet: Outlet, label_offset: float = 0.15) -> int:
        """添加电气插座点位（ELEC_OUTLET 正方形 + ELEC_LABEL "H{高度}" 标注）。

        出图范式照 add_column 点位类（点位画成闭合正方形 + 独立标注层 TEXT）。
        边长 0.1m（电气点位符号惯例），标注 "H{height_m:.1f}"（安装高度，如 H1.3）。
        """
        return self._add_point_symbol(
            position=outlet.position,
            layer=outlet.layer,
            side_mm=100,
            label=f"H{outlet.height_m:.1f}",
            label_layer="ELEC_LABEL",
            label_offset=label_offset,
        )

    def add_switch(self, sw: Switch, label_offset: float = 0.15) -> int:
        """添加电气开关点位（ELEC_SWITCH 正方形 + ELEC_LABEL "H{高度}" 标注）。

        出图范式照 add_outlet / add_column 点位类，共用 _add_point_symbol 底座。
        """
        return self._add_point_symbol(
            position=sw.position,
            layer=sw.layer,
            side_mm=100,
            label=f"H{sw.height_m:.1f}",
            label_layer="ELEC_LABEL",
            label_offset=label_offset,
        )

    def add_hvac_duct(self, duct: HvacDuct, label_offset: float = 0.15) -> int:
        """添加暖通风管线段 + 管径标注，返回标注条数（0 或 1）。

        出图范式照 add_pipe 线段类（HVAC_DUCT 层 LWPOLYLINE 两点不闭合
        + HVAC_LABEL 层 "DN{管径}" TEXT，画在管段中点上方 offset 处）。
        """
        if duct.layer not in self.doc.layers:
            self.doc.layers.new(duct.layer)
        if "HVAC_LABEL" not in self.doc.layers:
            self.doc.layers.new("HVAC_LABEL")
        self.msp.add_lwpolyline(
            [(duct.start.x, duct.start.y), (duct.end.x, duct.end.y)],
            close=False,
            dxfattribs={"layer": duct.layer},
        )
        mid_x = (duct.start.x + duct.end.x) / 2.0
        mid_y = (duct.start.y + duct.end.y) / 2.0
        txt = self.msp.add_text(
            f"DN{duct.diameter_mm}",
            dxfattribs={"height": 0.15, "layer": "HVAC_LABEL"},
        )
        txt.dxf.insert = (mid_x, mid_y + label_offset)
        return 1

    def add_hvac_unit(self, unit: HvacUnit, label_offset: float = 0.15) -> int:
        """添加空调机组点位（HVAC_UNIT 正方形 + HVAC_LABEL "K{制冷量}" 标注）。

        出图范式照 add_hvac_grille / add_column 点位类，共用 _add_point_symbol 底座。
        边长 0.3m（机组符号略大于风口），标注 "K{cooling_kw:.1f}"（制冷量 kW）。
        """
        return self._add_point_symbol(
            position=unit.position,
            layer=unit.layer,
            side_mm=300,
            label=f"K{unit.cooling_kw:.1f}",
            label_layer="HVAC_LABEL",
            label_offset=label_offset,
        )

    def add_hvac_grille(self, grille: HvacGrille, label_offset: float = 0.15) -> int:
        """添加风口点位（HVAC_GRILLE 正方形 + HVAC_LABEL "H{高度}" 标注）。

        出图范式照 add_hvac_unit / add_column 点位类，共用 _add_point_symbol 底座。
        边长 0.15m（风口符号），标注 "H{height_m:.1f}"（安装高度，如 H2.5）。
        """
        return self._add_point_symbol(
            position=grille.position,
            layer=grille.layer,
            side_mm=150,
            label=f"H{grille.height_m:.1f}",
            label_layer="HVAC_LABEL",
            label_offset=label_offset,
        )

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

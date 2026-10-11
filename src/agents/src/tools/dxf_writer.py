"""
DXFWriter + 出图警示标记对账 — ezdxf DWG/DXF 写入器 (从 cad_tools.py 拆出,
2026-10-11 文件健康轮)。

职责: 把几何数据类 (cad_types) 画成 ezdxf 实体 (墙/门/窗/管/梁/柱/电气/暖通/
轴网/碰撞标记) + 读回警示圈数对账 (count_dwg_markers / verify_dwg_markers)。
依赖: 数据类从 cad_types import; ezdxf 函数内 import; math 顶部 import。
cad_tools.py 顶部 re-export DXFWriter/两个 marker 函数, 旧 import 路径 0 改动。
"""
import math

from src.agents.src.tools.cad_types import (  # noqa: F401
    Point, Wall, Door, Window, Pipe, Beam, Column, Outlet,
    Switch, HvacDuct, HvacUnit, HvacGrille,
)


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

    # ── 制图惯例线型 (幂等: 已有同名则跳过, 重复调用安全) ──────
    # ezdxf 新建文档只自带 ByBlock/ByLayer/Continuous, 自定义线型须显式建,
    # 否则实体 dxfattribs 写 'DASHED' 读回会变 ByLayer。实测 1.4.4 双写
    # dxf/dwg 均可读回 (见 tests/unit/test_linetypes_dwg_export.py)。
    _LINETYPE_PATTERNS: dict[str, list] = {
        # 管道/管井制图惯例: 虚线
        "DASHED": [0.5, 0.25, -0.25],
        # 轴线制图惯例: 点划线 (长划-点-长划)
        "CENTERLINE": [1.25, 0.75, -0.25, 0.125, -0.25],
    }

    def _ensure_linetypes(self) -> None:
        """幂等确保 DASHED/CENTERLINE 线型存在 (同 layers.new 范式, 先查后建)。"""
        existing = {lt.dxf.name for lt in self.doc.linetypes}
        for name, pattern in self._LINETYPE_PATTERNS.items():
            if name not in existing:
                self.doc.linetypes.add(name, pattern=pattern)

    # ── 图层着色/线宽标准 (M3 出图深化: 图层→精细图元 的制图标准维度) ──────
    # ezdxf layers.new(name, color=ACI, lineweight=1/100mm) 给图层挂属性;
    # matplotlib 渲染按 color 上色, 线宽决定线粗。ACI 色号: 1红 2黄 3绿 4青
    # 5蓝 6品红 7白 8灰。lineweight 单位 1/100 mm (13=0.13mm 细 / 30=0.30mm 中粗
    # / 50=0.50mm 粗)。配色依据建筑/水/电/暖/结构制图惯例, 结构线粗于管线。
    _LAYER_STYLES: dict[str, dict[str, int]] = {
        # 墙体承重主轮廓: 白(7) 粗(50) — 制图最粗实线
        "WALL": {"color": 7, "lineweight": 50},
        "CENTERLINE": {"color": 7, "lineweight": 50},
        # 门窗建筑细部: 灰(8) 细
        "DOOR": {"color": 8, "lineweight": 13},
        "WINDOW": {"color": 8, "lineweight": 13},
        # 水系统: 红(1) 细
        "PIPE": {"color": 1, "lineweight": 13},
        "PIPE_LABEL": {"color": 1, "lineweight": 13},
        "PIPE_WASTE": {"color": 1, "lineweight": 13},
        "PIPE_VENT": {"color": 1, "lineweight": 13},
        "PIPE_DRAIN": {"color": 1, "lineweight": 13},
        # 风系统: 蓝(5) 细
        "HVAC_DUCT": {"color": 5, "lineweight": 13},
        "HVAC_UNIT": {"color": 5, "lineweight": 13},
        "HVAC_GRILLE": {"color": 5, "lineweight": 13},
        "HVAC_LABEL": {"color": 5, "lineweight": 13},
        # 结构: 绿(3) 中粗(30) — 梁柱截面主轮廓, 粗于管线细于墙体
        "BEAM": {"color": 3, "lineweight": 30},
        "BEAM_LABEL": {"color": 3, "lineweight": 13},
        "BEAM_FILL": {"color": 3, "lineweight": 13},
        "COLUMN": {"color": 3, "lineweight": 30},
        "COLUMN_LABEL": {"color": 3, "lineweight": 13},
        "COLUMN_FILL": {"color": 3, "lineweight": 13},
        "FOUNDATION": {"color": 3, "lineweight": 30},
        "NODE": {"color": 3, "lineweight": 13},
        "WALL_SHEAR": {"color": 3, "lineweight": 30},
        # 电气: 黄(2) 细
        "ELEC_OUTLET": {"color": 2, "lineweight": 13},
        "ELEC_SWITCH": {"color": 2, "lineweight": 13},
        "ELEC_LABEL": {"color": 2, "lineweight": 13},
        # 轴网/标注/编号: 白(7) 细
        "AXIS": {"color": 7, "lineweight": 13},
        "DIMENSION": {"color": 7, "lineweight": 13},
        "OPENING_TAG": {"color": 7, "lineweight": 13},
        # 跨专业碰撞标记: 品红(6) 粗(30) — 醒目警示, 区别于所有专业线
        "CLASH": {"color": 6, "lineweight": 30},
        "CLASH_LABEL": {"color": 6, "lineweight": 13},
    }

    def _ensure_layer_styles(self) -> None:
        """幂等给各专业图层套 着色(color) + 线宽(lineweight) 标准。

        仿 _ensure_linetypes 的"先查后建/幂等"范式:
        - 已存在图层 → 属性赋值 layer.color/lineweight (ezdxf setter, 不 new)。
        - 未存在图层 → layers.new(name, color, lineweight) 一次带全样式。
        重复调用全走 setter 分支, no-op 安全。出图前 (save 入口) 统一调,
        覆盖 add_* 内裸建 (无色) 的图层; 不删不改任何既有实体。

        ezdxf 1.4.4 的 layers.new() 不接受 color/lineweight 关键字 (只认 name
        等基础参数), 故未建图层也走 new(name) + 属性赋值, 与已存在分支统一
        成 setter 路径 (同名字段增量, 单一写法)。
        注意: lineweight 须写 dxf.lineweight 原语 (ezdxf 的 layer.lineweight
        高级 setter 会把普通 int 当 ByLayer 吞掉, 读回 -3); color 走 dxf.color
        (ACI 色号 1-256, 读回正常)。
        """
        for name, style in self._LAYER_STYLES.items():
            if name not in self.doc.layers:
                self.doc.layers.new(name)
            layer = self.doc.layers.get(name)
            layer.dxf.color = style["color"]
            layer.dxf.lineweight = style["lineweight"]

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
            txt = self.msp.add_text(text, dxfattribs={"height": 0.15, "layer": "DIMENSION"})
            txt.dxf.insert = (mid_x, mid_y)

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
          线型 DASHED (管道制图惯例虚线) — 经 _ensure_linetypes 幂等建线型后引用。
        - 管径标注: 仿 add_opening_dimensions 的「文字 + DIMENSION 层」风格，
          在管段中点上方 offset 处画 TEXT "DN{diameter_mm}"。

        管段支持任意方向（给排水管路可斜走，不做横平竖直限制）。
        显式建图层 — DWG 二进制省略零实体空图层，须先 layers.new 再 add。
        """
        self._ensure_linetypes()
        if "PIPE" not in self.doc.layers:
            self.doc.layers.new("PIPE")
        if "PIPE_LABEL" not in self.doc.layers:
            self.doc.layers.new("PIPE_LABEL")
        # 管线本体: LWPOLYLINE 两点（不闭合, 虚线 DASHED 符合管道制图惯例）
        self.msp.add_lwpolyline(
            [(pipe.start.x, pipe.start.y), (pipe.end.x, pipe.end.y)],
            close=False,
            dxfattribs={"layer": pipe.layer, "linetype": "DASHED"},
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

    def add_beam(self, beam: Beam, label_offset: float = 0.15, hatch: bool = False) -> int:
        """添加结构梁线段 + 截面标注，返回标注条数（0 或 1）。

        出图范式照 add_pipe（线段类 LWPOLYLINE + 独立标注层 TEXT）：
        - 梁本体: BEAM 图层 LWPOLYLINE，端点序列 (start, end) 两点（不闭合）。
        - 截面标注: 仿 PIPE_LABEL 范式, BEAM_LABEL 层 TEXT "{宽}x{高}"
          画在梁段中点上方 offset 处。
        - hatch=True: 在梁段 (start,end) 处补一个实填充 (BEAM_FILL 层),
          按 截面宽×截面高 比例生成填充区域。最小深化 — 默认 False
          不画填充 (避免全量填充, 保持既有 dwg_export 验收测试不破)。

        显式建图层 — DWG 二进制省略零实体空图层，须先 layers.new 再 add。
        """
        # span_m 缺省 (未传/传 0) 时按端点几何补算 (上游契约 §2.1 物理来源),
        # 让出图侧也带真实跨度; 纯增量, 不影响既有 dwg_export 验收测试。
        if beam.span_m <= 0:
            beam.span_m = math.hypot(
                beam.end.x - beam.start.x, beam.end.y - beam.start.y,
            )
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
        # 最小深化: 按需给梁段补一个实填充 (截面宽×高 比例), BEAM_FILL 层
        if hatch:
            self._add_beam_hatch(beam)
        return 1

    def _add_beam_hatch(self, beam: Beam) -> None:
        """梁段实填充 (BEAM_FILL 层, 按 截面宽×深 比例生成封闭 polygon)。

        用 ezdxf 的 HATCH 实体 (set_solid_fill + add_polyline_path),
        填充区域 = 梁段 (start→end) 两侧各偏移 截面宽/2 形成的矩形。
        深度 (depth_mm) 仅影响标注文案与截面比例示意, 填充几何不画
        3D 深 (2D 平面图惯例, 填充=梁在地面投影面积, 宽=beam 截面宽)。
        显式建 BEAM_FILL 图层 + _ensure_linetypes (实线用 ByLayer)。
        """
        if "BEAM_FILL" not in self.doc.layers:
            self.doc.layers.new("BEAM_FILL")
        # 梁段两侧各偏移 截面宽/2 → 4 顶点矩形 (与 add_wall_thickness 同范式)
        eps = 1e-9
        dx = beam.end.x - beam.start.x
        dy = beam.end.y - beam.start.y
        h = beam.width_mm / 1000.0 / 2.0  # 截面宽/2 (m)
        if abs(dy) < eps:  # 水平梁: 沿 y 偏移
            x0, x1, y = beam.start.x, beam.end.y, beam.start.y
            pts = [(x0, y + h), (x1, y + h), (x1, y - h), (x0, y - h)]
        elif abs(dx) < eps:  # 竖直梁: 沿 x 偏移
            x, y0, y1 = beam.start.x, beam.start.y, beam.end.y
            pts = [(x + h, y0), (x + h, y1), (x - h, y1), (x - h, y0)]
        else:  # 斜梁: 跳过填充 (与 add_wall_thickness MVP 同款限制)
            return
        hatch = self.msp.add_hatch(color=8, dxfattribs={"layer": "BEAM_FILL"})
        hatch.set_solid_fill()
        hatch.paths.add_polyline_path(pts, is_closed=True)

    def add_column(self, col: Column, label_offset: float = 0.15, hatch: bool = False) -> int:
        """添加结构柱（截面矩形）+ 截面标注，返回标注条数（0 或 1）。

        出图范式照 add_opening_marker 的点位范式（以 point 定位）：
        - 柱本体: COLUMN 图层 LWPOLYLINE 正方形（闭合, insert 点为左下顶角,
          边长 = 截面短边 mm/1000 m）, 读回走与 pipe/beam 相同的 polyline 通道。
        - 截面标注: 仿 BEAM_LABEL 范式, COLUMN_LABEL 层 TEXT "{短边}x{短边}"
          画在柱心（插入点上方半边长）上方 offset 处。
        - hatch=True: 在柱截面 (左下顶角→右上) 处补一个实填充 (COLUMN_FILL 层),
          照 _add_beam_hatch 的 HATCH 范式 (柱是正方形, 4 顶点 = 柱本体 4 角)。

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
        # hatch=True: 柱截面实填充 (COLUMN_FILL 层, 4 顶点 = 柱本体 4 角)
        if hatch:
            self._add_column_hatch(x0, y0, half)
        # 截面标注: 柱心上方 offset 处 TEXT "{短边}x{短边}"
        txt = self.msp.add_text(
            f"{col.section_mm}x{col.section_mm}",
            dxfattribs={"height": 0.15, "layer": "COLUMN_LABEL"},
        )
        txt.dxf.insert = (col.position.x, col.position.y + label_offset)
        return 1

    def _add_column_hatch(self, x0: float, y0: float, half: float) -> None:
        """柱截面实填充 (COLUMN_FILL 层, 4 顶点 = 柱本体正方形 4 角)。

        照 _add_beam_hatch 的 ezdxf HATCH 范式: set_solid_fill +
        add_polyline_path (闭合)。显式建 COLUMN_FILL 图层 (先查后建/幂等),
        并 _ensure_layer_styles 让 COLUMN_FILL 套上 M3 结构系配色。
        """
        if "COLUMN_FILL" not in self.doc.layers:
            self.doc.layers.new("COLUMN_FILL")
        pts = [
            (x0, y0), (x0 + 2 * half, y0),
            (x0 + 2 * half, y0 + 2 * half), (x0, y0 + 2 * half),
        ]
        hatch = self.msp.add_hatch(color=8, dxfattribs={"layer": "COLUMN_FILL"})
        hatch.set_solid_fill()
        hatch.paths.add_polyline_path(pts, is_closed=True)

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
        线型 DASHED (风管制图惯例虚线, 同 add_pipe)。
        """
        self._ensure_linetypes()
        if duct.layer not in self.doc.layers:
            self.doc.layers.new(duct.layer)
        if "HVAC_LABEL" not in self.doc.layers:
            self.doc.layers.new("HVAC_LABEL")
        self.msp.add_lwpolyline(
            [(duct.start.x, duct.start.y), (duct.end.x, duct.end.y)],
            close=False,
            dxfattribs={"layer": duct.layer, "linetype": "DASHED"},
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

    def add_axis_grid(
        self,
        x_axes: list,
        y_axes: list,
        layer: str = "AXIS",
    ) -> int:
        """添加轴网 (X 轴 + Y 轴 点划线网格) + 轴号标注，返回轴线条数。

        出图范式照 add_dimension 的「图层先建 + TEXT 标注」；轴线本身用
        CENTERLINE 点划线 (建筑轴网制图惯例)。X/Y 轴各是一条贯穿的 LINE:
        - x_axes = [(号, x坐标, 端点y0, 端点y1), ...] 竖直轴线 (沿 y 走, 固定 x)
          轴号 TEXT 画在轴线下端 (y0 - 0.2) 处, 如 "①②③"。
        - y_axes = [(号, y坐标, 端点x0, 端点x1), ...] 水平轴线 (沿 x 走, 固定 y)
          轴号 TEXT 画在轴线左端 (x0 - 0.2) 处, 如 "A B C"。

        轴线延伸出各房间外轮廓 (y0/y1 由调用方按布局 min/max 外扩),
        与 add_dimension 标注线同理。返回 x_axes + y_axes 总条数。
        显式建图层 + _ensure_linetypes (CENTERLINE 点划线)。
        """
        self._ensure_linetypes()
        if layer not in self.doc.layers:
            self.doc.layers.new(layer)
        count = 0
        for ax in x_axes:
            label, x, y0, y1 = ax
            self.msp.add_line(
                (x, y0), (x, y1),
                dxfattribs={"layer": layer, "linetype": "CENTERLINE"},
            )
            txt = self.msp.add_text(
                label, dxfattribs={"height": 0.2, "layer": layer}
            )
            txt.dxf.insert = (x, y0 - 0.2)
            count += 1
        for ay in y_axes:
            label, y, x0, x1 = ay
            self.msp.add_line(
                (x0, y), (x1, y),
                dxfattribs={"layer": layer, "linetype": "CENTERLINE"},
            )
            txt = self.msp.add_text(
                label, dxfattribs={"height": 0.2, "layer": layer}
            )
            txt.dxf.insert = (x0 - 0.2, y)
            count += 1
        return count

    def add_clash_marker(self, x: float, y: float, kind: str,
                         label: str = "CLASH") -> None:
        """在碰撞点 (x,y) 画红色碰撞圈 + 标注文字 (M4 出图侧, 增量)。

        照 add_column / add_opening_marker 的「独立图层 + 显式建图层」范式:
        - CLASH 图层 CIRCLE (半径 0.2m 警示圈, 品红粗线, 醒目区别于各专业线)
        - CLASH_LABEL 图层 TEXT: kind (如 "PIPE-BEAM"), 画在圈上方 0.25m
        纯增量: 不删不改任何既有实体; 无碰撞时根本不调本方法 → 既有出图 0 变化。
        """
        if "CLASH" not in self.doc.layers:
            self.doc.layers.new("CLASH")
        if "CLASH_LABEL" not in self.doc.layers:
            self.doc.layers.new("CLASH_LABEL")
        self.msp.add_circle(
            (x, y), radius=0.2,
            dxfattribs={"layer": "CLASH", "color": 6, "lineweight": 30},
        )
        txt = self.msp.add_text(label, dxfattribs={"height": 0.15, "layer": "CLASH_LABEL"})
        txt.dxf.insert = (x, y + 0.25)
        _ = kind  # kind 由调用方拼进 label; 保留形参便于日后按 kind 分级画

    def add_duplicate_marker(self, x: float, y: float, label: str = "DUP") -> None:
        """在疑似重复元素点 (x,y) 画琥珀色重复警示圈 + 标注 (M5 出图侧, 增量)。

        照 add_clash_marker 范式, 但用 DUP/DUP_LABEL 独立图层 + 琥珀色 (ACI 32),
        与 M4 碰撞的品红 CLASH 圈区分 (碰撞=元素互撞, 重复=同坐标不同 id)。
        纯增量: 不删不改既有实体; 无重复时不调本方法 → 既有出图 0 变化。
        """
        if "DUP" not in self.doc.layers:
            self.doc.layers.new("DUP")
        if "DUP_LABEL" not in self.doc.layers:
            self.doc.layers.new("DUP_LABEL")
        self.msp.add_circle(
            (x, y), radius=0.2,
            dxfattribs={"layer": "DUP", "color": 32, "lineweight": 30},
        )
        txt = self.msp.add_text(label, dxfattribs={"height": 0.15, "layer": "DUP_LABEL"})
        txt.dxf.insert = (x, y + 0.25)

    def save(self, path: str) -> bool:
        """保存 DWG。出图前统一套图层着色/线宽标准 (幂等, 覆盖裸建图层)。"""
        try:
            self._ensure_layer_styles()
            self.doc.saveas(path)
            return True
        except Exception as e:
            print(f"Save failed: {e}")
            return False


# ─── 出图警示标记计数对账 (机制层自主子集, 纯函数, 只读 DWG 不画) ───
# 出图侧画碰撞 (CLASH 品红圈) / 重复 (DUP 琥珀圈) 时, 设计师看到「清单有 N 条
# 碰撞 / 图上却 M 个圈」的失步无人拦。本函数读回 DWG 里 CLASH/DUP 图层 CIRCLE
# 实体数, 与调用方喂的期望数对账。纯机制层: 只数「画没画够/多画」, 不判
# 「画得对不对/位置准不准」(那是 M2 制图规范)。畸形 DWG (打不开/无该图层) 不崩。


def count_dwg_markers(dxf_path: str) -> dict:
    """读回 DWG 中 CLASH / DUP 图层 CIRCLE 实体数。纯只读, 缺文件/打不开降级 0。

    返回 {clash: int, dup: int, opened: bool} — opened=False 时计数为 0 (不崩)。
    每个 add_clash_marker/add_duplicate_marker 各画 1 个 CIRCLE (半径 0.2), 故
    CLASH/DUP 图层的 CIRCLE 数 = 出图侧实际画的警示圈数。
    """
    out = {"clash": 0, "dup": 0, "opened": False}
    try:
        import ezdxf
        doc = ezdxf.readfile(dxf_path)
    except Exception:
        return out
    out["opened"] = True
    msp = doc.modelspace()
    try:
        out["clash"] = len(msp.query('CIRCLE[layer=="CLASH"]'))
        out["dup"] = len(msp.query('CIRCLE[layer=="DUP"]'))
    except Exception:
        pass  # 契约: 图层查询失败 → 保持默认 0 (opened 已置 True, 计数缺省安全)
    return out


def verify_dwg_markers(dxf_path: str, expected_clash: int, expected_dup: int) -> dict:
    """对账 DWG 警示圈实数 vs 期望数 (纯函数, 不崩)。

    校验 (缺哪条报哪条, 全过 → ok=True, issues=[]):
      ① 打不开 DWG → 无法对账, 记 issue (不静默当 0 圈全过)。
      ② clash 实数 == expected_clash (漏画/多画都报, 防出图侧失步)。
      ③ dup 实数 == expected_dup (同上)。
    空画不判漏 (expected=0 且实数=0 合法, 无碰撞就该 0 圈)。
    返回 {ok, clash_drawn, clash_expected, dup_drawn, dup_expected, issues}。
    """
    expected_clash = max(0, int(expected_clash or 0))
    expected_dup = max(0, int(expected_dup or 0))
    counts = count_dwg_markers(dxf_path)
    issues: list[str] = []
    if not counts["opened"]:
        issues.append("DWG 打不开 (缺文件/非 ezdxf 可读), 无法对账 (不静默当 0 圈)")
    drawn_clash, drawn_dup = counts["clash"], counts["dup"]
    if counts["opened"]:
        if drawn_clash != expected_clash:
            issues.append(f"CLASH 圈数失步: 实画 {drawn_clash} ≠ 期望 {expected_clash}")
        if drawn_dup != expected_dup:
            issues.append(f"DUP 圈数失步: 实画 {drawn_dup} ≠ 期望 {expected_dup}")
    return {"ok": not issues, "clash_drawn": drawn_clash, "clash_expected": expected_clash,
            "dup_drawn": drawn_dup, "dup_expected": expected_dup, "issues": issues}

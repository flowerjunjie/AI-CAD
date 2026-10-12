"""
DXFReader — ezdxf DWG/DXF 读取器 (从 cad_tools.py 拆出, 2026-10-11 文件健康轮)。

按图层读 LINE/LWPOLYLINE 线段 + INSERT 元素块, 与 ezdxf 实体格式解耦成纯数据。
自包含: 只用函数内 `import ezdxf`, 不依赖数据类 / Writer。
cad_tools.py 顶部 re-export DXFReader, 旧 import 路径 0 改动 (兼容层)。
"""


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

    def _segments_by_layer(self, layer_names, include_layer: bool, _caller: str) -> list:
        """线段类元素通用底座: 按图层读 LINE/LWPOLYLINE → 纯线段或带图层 dict。

        include_layer=False → [(start_xy,end_xy),...]; True → [{start,end,layer},...]。
        给排水/结构/墙 共用此法, 各专业只传自己的默认图层组 (开放封闭: 加专业=加一行薄封装)。
        """
        if self.doc is None:
            raise RuntimeError(f"调用 {_caller} 前需先 open()")
        if not include_layer:
            return self._segments_from_layer(layer_names)
        out = []
        for layer in layer_names:
            for a, b in self._segments_from_layer((layer,)):
                out.append({"start": a, "end": b, "layer": layer})
        return out

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
        return self._segments_by_layer(layer_names, include_layer, "get_plumbing_segments")

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
        return self._segments_by_layer(layer_names, include_layer, "get_structural_segments")

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
                height_m = None  # 契约: ATTRIB 非数值 → 缺省, extractor 兜底占位高度 (非吞错)
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

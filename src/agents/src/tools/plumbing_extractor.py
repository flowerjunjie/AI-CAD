"""给排水元素从 DXF 线段的抽取层。

把 DXFReader.get_plumbing_segments 抽出的管道线段配对成 PlumbingPipe
实例，供规则引擎（default.json 的 plumbing-* DSL 条目）做检查。

契约要点:
- 管径按图层映射 (PIPE_WASTE→110 / 其余→50) —— 占位映射, 待业务确认
- 坡度: 有高程标注才按「相邻管段高程差/水平距离」算, 否则占位 0.0
- 距检查井: 取管段中点到最近 manhole_points 的欧氏距离, 无则 0.0
- 不可变: 全部构造新 PlumbingPipe, 不 mutation 入参
"""
from __future__ import annotations

from src.rules.src.plumbing import PlumbingPipe

# 图层名 → (pipe_type, 公称管径 mm)。管径为占位映射, 规范条文待业务确认。
_LAYER_MAP = {
    "PIPE_WASTE": ("waste", 110),   # TBD: 业务确认管径
    "PIPE_VENT": ("vent", 50),      # TBD
    "PIPE_DRAIN": ("drain", 50),    # TBD
    "PIPE": ("drain", 50),          # TBD: 默认排水横管
}
_DEFAULT = ("drain", 50)  # TBD


def _segment_and_layer(item):
    """从 reader 元素取 (start, end, layer)，两种形态零歧义分发。

    - 带图层: reader.get_plumbing_segments(include_layer=True) 的 dict
      {"start":.., "end":.., "layer":..} → 直接读。
    - 纯线段: ((sx,sy),(ex,ey)) → 无图层信息, 退默认 "PIPE"。
    用 isinstance(dict) 判定, 不靠「尾元素是字符串」猜形态。
    """
    if isinstance(item, dict):
        return item["start"], item["end"], item.get("layer") or "PIPE"
    start, end = item[0], item[1]
    return start, end, "PIPE"


def _start_end(item) -> tuple:
    """取 (start_xy, end_xy)。纯线段与带图层(dict) 形态通用。"""
    start, end, _layer = _segment_and_layer(item)
    return start, end


def _slope_from_annotations(ann, start, end, layer_key: str) -> float:
    """有高程标注(相邻管段高程差/水平距离)才算坡度, 否则占位 0.0。

    ann: 可选 dict, 键为图层, 值为 {端点坐标: 高程(m)}。
    端点坐标以 (x,y) 圆元索引, 与线段端点对应。
    """
    if not ann or layer_key not in ann:
        return 0.0
    elev = ann[layer_key]
    if start not in elev or end not in elev:
        return 0.0
    horiz = ((end[0] - start[0]) ** 2 + (end[1] - start[1]) ** 2) ** 0.5
    if horiz == 0.0:
        return 0.0
    return abs(elev[start] - elev[end]) / horiz * 100.0  # 坡度百分比


def _dist_to_manhole(mid, manhole_points) -> float:
    """管段中点到最近检查井/立管的欧氏距离 (m), 无检查井则 0.0。"""
    if not manhole_points:
        return 0.0
    return min(((mid[0] - m[0]) ** 2 + (mid[1] - m[1]) ** 2) ** 0.5
               for m in manhole_points)


def extract_plumbing_pipes(
    segs,
    manhole_points=(),
    annotations=None,
) -> list[PlumbingPipe]:
    """把管道线段配对成 PlumbingPipe 实例列表。

    segs: get_plumbing_segments 的输出。两种形态都支持:
      - include_layer=False → ((start_xy, end_xy), ...)  纯线段, 按默认层 PIPE
      - include_layer=True  → {"start","end","layer"} dict 按各自图层映射管径
    manhole_points: 检查井/立管 2D 坐标点序列, 用于算距检查井距离。
    annotations: 高程标注, 见 _slope_from_annotations。
    """
    pipes = []
    for idx, item in enumerate(segs):
        start, end, layer = _segment_and_layer(item)
        ptype, diam = _LAYER_MAP.get(layer, _DEFAULT)
        mid = (((start[0] + end[0]) / 2.0), ((start[1] + end[1]) / 2.0))
        pipes.append(PlumbingPipe(
            id=f"plumbing-{idx}",
            pipe_type=ptype,
            diameter_mm=diam,
            slope=_slope_from_annotations(annotations, start, end, layer),
            distance_to_manhole_m=_dist_to_manhole(mid, manhole_points),
        ))
    return pipes

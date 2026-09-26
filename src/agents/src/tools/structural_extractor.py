"""结构元素从 DXF 线段/INSERT 块的抽取层（对称 plumbing_extractor）。

结构专业分两族元素（契约 docs/structural-upstream-contract.md §1）:
- 线段类（梁/承重墙）: get_structural_segments 抽出的线段配对成 StructuralBeam
- 块类（柱/基础/节点）: get_structural_blocks 读出的 INSERT dict 转成
  StructuralColumn

对称 plumbing 的分离原则:
- 本层只消费「上游解析层」的输出（纯 dict 契约），永远不直接碰 ezdxf ——
  保持「纯转换层 + 上游解析层」分离。
- 图层/块名 → 类型/截面 是占位映射（全部 TBD，业务确认后改本文件顶部
  dict，不改结构，不重开一轮改代码）。
- 不可变: 全部构造新元素, 不 mutation 入参。
"""
from __future__ import annotations

import logging

from src.rules.src.structural import StructuralBeam, StructuralColumn

logger = logging.getLogger(__name__)

# 线段类: 图层名 → (beam_type, 截面宽 mm)。占位映射, 规范数值 TBD 待业务确认。
_BEAM_LAYER_MAP = {
    "BEAM": ("main", 300),           # TBD: 主梁截面宽
    "WALL_SHEAR": ("shear_wall", 200),  # TBD: 承重墙厚度当宽
}
_BEAM_DEFAULT = ("secondary", 250)   # TBD: 未识别图层退默认次梁


def _beam_type_and_width(layer: str) -> tuple[str, int]:
    """按图层映射 (beam_type, width_mm)，未知图层退默认 + warning。"""
    mapped = _BEAM_LAYER_MAP.get(layer)
    if mapped is None:
        logger.warning("结构线段未知图层 %s, 退默认 %s (TBD 待业务确认)", layer, _BEAM_DEFAULT)
        return _BEAM_DEFAULT
    return mapped


def _depth_from_annotations(ann, start, end) -> int:
    """有截面深标注才取深值, 否则占位 0 (TBD)。

    镜像 plumbing 的高程标注范式: 梁深不来自 DXF 线段 (纯 2D 几何无截面),
    由调用侧按「端点坐标 → 截面深 mm」提供; 查不到即占位 0。
    ann: 可选 dict, 值为 {端点坐标 (x,y) 或 中点坐标: 截面深 mm}。
    优先按段中点查 (最贴合「一条梁一个截面」), 中点缺失再按起点查。
    """
    if not ann:
        return 0
    mid = (((start[0] + end[0]) / 2.0), ((start[1] + end[1]) / 2.0))
    if mid in ann:
        return int(ann[mid])
    if start in ann:
        return int(ann[start])
    return 0


def extract_structural_beams(segs, annotations=None) -> list[StructuralBeam]:
    """把结构梁/承重墙线段配对成 StructuralBeam 实例列表。

    segs: get_structural_segments 的输出。两种形态都支持（照 plumbing）:
      - include_layer=False → ((start_xy, end_xy), ...)  纯线段, 无图层信息
      - include_layer=True  → {"start","end","layer"} dict 按各自图层映射
    顺序与入参一致。截面深缺省占位 0; 有 annotations (端点/中点 → 截面深 mm)
    才按标注取深, 否则保持占位 0 (镜像 plumbing 高程标注范式, 见
    _depth_from_annotations)。平面坐标取中点占位。
    """
    beams = []
    for idx, item in enumerate(segs):
        if isinstance(item, dict):
            start, end, layer = item["start"], item["end"], item.get("layer") or "BEAM"
        else:
            start, end = item[0], item[1]
            layer = "BEAM"  # 纯线段无图层信息, 退主梁占位
        beam_type, width_mm = _beam_type_and_width(layer)
        x = (start[0] + end[0]) / 2.0  # 中点坐标占位
        y = (start[1] + end[1]) / 2.0
        beams.append(StructuralBeam(
            id=f"structural-beam-{idx}",
            beam_type=beam_type,
            width_mm=width_mm,
            depth_mm=_depth_from_annotations(annotations, start, end),
            x=x,
            y=y,
        ))
    return beams


# 块类: 块名 → (column_type, 截面短边 mm)。占位映射, TBD 待业务确认。
_COLUMN_BLOCK_MAP = {
    "COL_K": ("frame", 400),         # TBD: 框架柱截面
    "COL_S": ("construction", 200),  # TBD: 小截面柱 (短边 200mm, < 300 下限, e2e 违规样本)
    "COL_Z": ("construction", 240),  # TBD: 构造柱截面
    "FOUND_S": ("foundation", 0),    # TBD: 基础无柱截面概念, 0 占位
}
_COLUMN_DEFAULT = ("frame", 0)       # TBD: 未识别块名退默认


def _column_type_and_section(block_name: str) -> tuple[str, int]:
    """按块名映射 (column_type, section_mm)，未知块名退默认 + warning。"""
    mapped = _COLUMN_BLOCK_MAP.get(block_name)
    if mapped is None:
        logger.warning("结构块未知块名 %s, 退默认 %s (TBD 待业务确认)", block_name, _COLUMN_DEFAULT)
        return _COLUMN_DEFAULT
    return mapped


def extract_structural_columns(blocks) -> list[StructuralColumn]:
    """把 INSERT 块 dict 转成 StructuralColumn 实例列表。

    blocks: get_structural_blocks 的输出, 每项 dict:
        {"block_name","x","y","layer"}
    顺序与入参一致。截面按 block_name 映射; 缺省占位 0 (TBD)。
    """
    columns = []
    for idx, blk in enumerate(blocks):
        block_name = blk.get("block_name", "")
        column_type, section_mm = _column_type_and_section(block_name)
        columns.append(StructuralColumn(
            id=f"structural-column-{idx}",
            column_type=column_type,
            section_mm=section_mm,
            x=float(blk.get("x", 0.0)),
            y=float(blk.get("y", 0.0)),
        ))
    return columns

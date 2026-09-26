"""造结构专业端到端测试用 DXF → data/sample/structural_sample.dxf。

内容 (图层/块名必须匹配 cad_tools 的结构图层约定, 端点用互异的整数坐标
保证各梁段/柱块可区分):

  BEAM (线段类, 截面深由 e2e 调用侧标注 _DEPTHS 提供, 见 tests/unit/test_structural_e2e.py):
    flat    扁梁段 (0,0)->(4,0)   截面 300×300 → 深宽比 1.0 < 1.5
             → 命中 structural-beam-width-depth-ratio
    good    合规格梁段 (0,10)->(4,10)  截面 300×600 → 深宽比 2.0 (在 [2.0,4.0] 内)
             → 放行, 不误报
  COLUMN (块类, 块名 → 截面短边 mm, 见 structural_extractor._COLUMN_BLOCK_MAP):
    COL_S   小截面柱 块名 COL_S 插入点 (6.0,1.0) → 截面 200mm < 300mm
             → 命中 structural-column-min-section
    COL_K   合规格柱  块名 COL_K 插入点 (8.0,3.0) → 截面 400mm >= 300mm
             → 放行, 不误报

截面深/短边数值与 default.json 回填后的阈值 (GB 50010 高宽比 / GB 50011 最小截面)
同框设计: 扁梁 300/300=1.0 破下限, 合规梁 600/300=2.0 在区间内; 小柱 200 破下限,
合规柱 400 合规。用法:
    python data/sample/make_structural_sample_dxf.py   # 项目根目录下
"""
from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "sample", "structural_sample.dxf")

# e2e 测试读取的样本坐标约定 (与 _make_structural_dxf 端点一致):
#   梁段中点 → 截面深 mm; 块插入点由 extractor 按块名映射截面短边。
FLAT_BEAM_MID = (2.0, 0.0)
GOOD_BEAM_MID = (2.0, 10.0)


def build_sample_dxf() -> str:
    """用 ezdxf 生成结构测试 DXF, 返回落盘路径。"""
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("BEAM", "COLUMN"):
        doc.layers.new(layer)
    # 柱截面按块名映射 (structural_extractor._COLUMN_BLOCK_MAP):
    #   COL_S → construction 构造柱 / 200mm  (小截面, 违规)
    #   COL_K → frame 框架柱 / 400mm        (合规)
    for blk in ("COL_S", "COL_K"):
        doc.blocks.new(blk)
    msp = doc.modelspace()

    # BEAM — 2 条 LINE (截面深由 e2e 侧按中点标注)
    msp.add_line((0, 0), (4, 0), dxfattribs={"layer": "BEAM"})      # flat 扁梁
    msp.add_line((0, 10), (4, 10), dxfattribs={"layer": "BEAM"})    # good 合规梁

    # COLUMN — 2 个 INSERT 块 (ezdxf 1.4.4: add_blockref(name, insert) 位置参)
    msp.add_blockref("COL_S", (6.0, 1.0), dxfattribs={"layer": "COLUMN"})  # 小截面柱
    msp.add_blockref("COL_K", (8.0, 3.0), dxfattribs={"layer": "COLUMN"})  # 合规格柱

    doc.saveas(OUT_PATH)
    return OUT_PATH


if __name__ == "__main__":
    path = build_sample_dxf()
    print(f"结构专业测试 DXF 已生成: {path}")

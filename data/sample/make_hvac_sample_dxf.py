"""造暖通专业端到端测试用 DXF → data/sample/hvac_sample.dxf。

内容 (图层名 + 块名必须匹配 cad_tools.get_hvac_points 的暖通约定,
见 cad_tools.py get_hvac_points + docs/element-upstream-contract.md §4):

  HVAC_DUCT:
    DUCT_STD  INSERT @ (0.0, 0.0)  超速风管
              → 调用侧标注 _HVAC_ANNOTATIONS 给 velocity_ms=12.0
                超 hvac-duct-velocity-range 上限 10.0 → 命中
  HVAC_UNIT:
    UNIT_STD  INSERT @ (4.0, 0.0)  室内装的室外机
              → 调用侧标注 unit_type=outdoor + location_type=indoor
                → 命中 hvac-unit-outdoor-placement
  HVAC_GRILLE:
    GRILLE_STD INSERT @ (2.0, 2.0) 合规送风格栅
              → 调用侧标注 height_m=2.5 (在 [2.0, 4.0] 区间内)
                → 放行, 不误报

ezdxf 1.4.4: doc.blocks.new(name) + msp.add_blockref(name, insert) 位置参。
块名 → kind 映射走 cad_tools.get_hvac_points 的 _BLOCK 占位映射
(DUCT_STD/UNIT_STD/GRILLE_STD), 数值字段靠 e2e 测试按坐标标注,
与 DXF 坐标同框 (镜像 plumbing 高程 / structural 截面标注范式)。

用法:
    python data/sample/make_hvac_sample_dxf.py   # 项目根目录下
"""
from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "sample", "hvac_sample.dxf")

# e2e 测试读取的标注键: 插入点 (x, y) → 数值字段 dict。
# 超速风管 / 室内室外机 / 合规格栅, 坐标与下方 INSERT 一一对应。
DUCT_POS = (0.0, 0.0)
UNIT_POS = (4.0, 0.0)
GRILLE_POS = (2.0, 2.0)


def build_sample_dxf() -> str:
    """用 ezdxf 生成暖通测试 DXF, 返回落盘路径。"""
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("HVAC_DUCT", "HVAC_UNIT", "HVAC_GRILLE"):
        doc.layers.new(layer)
    # INSERT 块定义 (块体内容不影响插入点/name 契约, 造个最小占体)
    for blk in ("DUCT_STD", "UNIT_STD", "GRILLE_STD"):
        doc.blocks.new(blk)
    msp = doc.modelspace()

    # 三个 INSERT 块 (ezdxf 1.4.4: add_blockref(name, insert) 位置参)
    msp.add_blockref("DUCT_STD", DUCT_POS, dxfattribs={"layer": "HVAC_DUCT"})      # 超速风管
    msp.add_blockref("UNIT_STD", UNIT_POS, dxfattribs={"layer": "HVAC_UNIT"})      # 室内室外机
    msp.add_blockref("GRILLE_STD", GRILLE_POS, dxfattribs={"layer": "HVAC_GRILLE"})  # 合规送风格栅

    doc.saveas(OUT_PATH)
    return OUT_PATH


if __name__ == "__main__":
    path = build_sample_dxf()
    print(f"暖通专业测试 DXF 已生成: {path}")

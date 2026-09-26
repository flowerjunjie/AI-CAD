"""造电气专业端到端测试用 DXF → data/sample/electrical_sample.dxf。

电气点位画成 INSERT 块 (块名即点位 kind 约定, 见 cad_tools.get_electrical_points),
真实数值 (height_m / room_type / has_earthing) 走块属性 ATTRIB 通道, 缺省字段不写
ATTRIB 则 get_electrical_points 回读为 None 占位 (由 electrical_extractor 兜底), 与
既有 test_electrical_extractor 的全 None 契约兼容。

内容 (图层名必须匹配 cad_tools 的电气图层约定, 坐标用互异整数保证各点位可区分):

  ELEC_OUTLET:
    OUTLET_HI  高位插座  height_m=2.5   room_type=living
                 → 超 outlet-height 默认上限 2.0 → 命中 electrical-outlet-height-range
    OUTLET_GND 厨卫无接地  height_m=0.3   room_type=kitchen   has_earthing=false
                 → 厨卫插座未接地 → 命中 electrical-outlet-earthing-required
  ELEC_SWITCH:
    SWITCH_OK  合规开关  height_m=1.3   room_type=door
                 → 在 switch 区间 [1.2,1.4] 内, 不违规

用法:
    python data/sample/make_electrical_sample_dxf.py   # 项目根目录下
"""
from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "sample", "electrical_sample.dxf")


def _add_attr_block(doc, block_name: str, attribs: dict[str, str]) -> None:
    """造一个带块属性定义的 INSERT 块 (ezdxf 1.4.4: add_attdef 先定义, 再实例化)。

    每个 key 是 ATTRIB tag (如 height_m), value 存进插入点。块体内容不影响
    插入点/name 契约, 只留最小属性定义让 add_auto_attribs 能实例化。
    """
    blk = doc.blocks.new(block_name)
    for tag in attribs:
        blk.add_attdef(tag, dxfattribs={"insert": (0.0, 0.0), "height": 0.25})


def _insert_outlet(msp, block_name: str, attribs: dict[str, str], layer: str, x: float, y: float) -> None:
    """插一个电气点位 INSERT + 其属性值。"""
    ins = msp.add_blockref(block_name, (x, y), dxfattribs={"layer": layer})
    ins.add_auto_attribs(attribs)


def build_sample_dxf() -> str:
    """用 ezdxf 生成电气测试 DWG, 返回落盘路径。"""
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("ELEC_OUTLET", "ELEC_SWITCH"):
        doc.layers.new(layer)

    # 三个点位块 (块名同时充当点位 id, 与 get_electrical_points 的 block_name 契约一致)
    _add_attr_block(doc, "OUTLET_HI", {"height_m": "2.5", "room_type": "living"})
    _add_attr_block(doc, "OUTLET_GND", {"height_m": "0.3", "room_type": "kitchen", "has_earthing": "false"})
    _add_attr_block(doc, "SWITCH_OK", {"height_m": "1.3", "room_type": "door"})

    msp = doc.modelspace()
    # ELEC_OUTLET — 2 个点位 (高位 + 厨卫无接地)
    _insert_outlet(msp, "OUTLET_HI", {"height_m": "2.5", "room_type": "living"}, "ELEC_OUTLET", 1.0, 2.0)
    _insert_outlet(msp, "OUTLET_GND", {"height_m": "0.3", "room_type": "kitchen", "has_earthing": "false"},
                  "ELEC_OUTLET", 3.0, 1.0)
    # ELEC_SWITCH — 1 个合规点位
    _insert_outlet(msp, "SWITCH_OK", {"height_m": "1.3", "room_type": "door"}, "ELEC_SWITCH", 2.0, 3.0)

    doc.saveas(OUT_PATH)
    return OUT_PATH


if __name__ == "__main__":
    path = build_sample_dxf()
    print(f"电气专业测试 DWG 已生成: {path}")

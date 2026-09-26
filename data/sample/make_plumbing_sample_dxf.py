"""造给排水专业端到端测试用 DXF → data/sample/plumbing_sample.dxf。

内容 (图层名必须匹配 cad_tools 的 plumbing 图层约定, 端点用互异的整数
坐标保证各管段可区分):

  PIPE:
    good    合规格管段 (8,44)->(12,44)     → 不违反 3 条 plumbing 规则
             (贴近检查井 (10,45), 中点 (10,44) 距井 1.0m < 25; 管径 50 >= 最小; 无高程差)
    oversloped 坡度超界段 (0,20)->(10,20)  → 高程差 3.0m, 水平 10m → 坡度 30%,
             超出 default.json 的 max_slope=12.0 → 命中 plumbing-pipe-slope-in-range
    far    距检查井过远段 (0,40)->(20,40)  → 中点 (10,40), 检查井 (10,45)
             距离 5.0m 超不过 25.0 默认上限; 若上限回填收紧到研究值则命中
             plumbing-pipe-manhole-distance
  PIPE_WASTE:
    bad     DN40 管段 (0,10)->(5,10)      → 40 < 50 最小管径
             → 命中 plumbing-waste-pipe-min-diameter

好管段坐标取检查井 (10,45) 近旁, 保证「管径/坡度/距井」三维度真干净,
好管不会被动命中 manhole-distance (上版 good 在 (5,0) 离井 45m 造成误报)。

坡度靠 extractor 的 annotations 参数算 (端点高程差/水平距离), 本脚本只出
线段; 高程标注由 e2e 测试在调用侧提供 (与 DXF 坐标同框, 见
tests/unit/test_plumbing_e2e.py 的 _ELEVATIONS 常量)。

用法:
    python data/sample/make_plumbing_sample_dxf.py   # 项目根目录下
"""
from __future__ import annotations

import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT_PATH = os.path.join(PROJECT_ROOT, "data", "sample", "plumbing_sample.dxf")


def build_sample_dxf() -> str:
    """用 ezdxf 生成测试 DWG, 返回落盘路径。"""
    import ezdxf

    doc = ezdxf.new("AC1027")
    for layer in ("PIPE", "PIPE_WASTE"):
        doc.layers.new(layer)
    msp = doc.modelspace()

    # PIPE — 3 条 LINE (good 段靠检查井, 坐标取 (8,44)->(12,44))
    msp.add_line((8, 44), (12, 44), dxfattribs={"layer": "PIPE"})     # good (贴井, 干净)
    msp.add_line((0, 20), (10, 20), dxfattribs={"layer": "PIPE"})     # oversloped
    msp.add_line((0, 40), (20, 40), dxfattribs={"layer": "PIPE"})     # far from manhole

    # PIPE_WASTE — DN40 偏小管径
    msp.add_line((0, 10), (5, 10), dxfattribs={"layer": "PIPE_WASTE"})  # bad DN40

    doc.saveas(OUT_PATH)
    return OUT_PATH


if __name__ == "__main__":
    path = build_sample_dxf()
    print(f"给排水专业测试 DWG 已生成: {path}")

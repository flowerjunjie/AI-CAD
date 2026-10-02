#!/usr/bin/env python
"""
M2 图层/块名扫描 CLI — 把「各院 DWG 制图约定」从填空题变选择题。

用法:
  python scripts/dwg_layer_scan.py electrical_sample.dxf
  python scripts/dwg_layer_scan.py data/sample/structural_sample.dxf

输出: 图层 × 实体类型 × INSERT 块名 频率报告 (JSON), 业务专家据此回填
映射 dict (docs/element-upstream-contract.md §5 的 TBD 占位) — 不必凭记忆口述
"点位画在哪层、用什么块"。

诚实边界: 只报频率, 不判定 kind 归属; 缺文件/坏 DXF → 空报告 (不崩不造假)。
"""
import json
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

from src.agents.src.tools.dwg_layer_scan import scan_dwg  # noqa: E402
from src.agents.src.tools.cad_tools import DXFReader      # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: python scripts/dwg_layer_scan.py <dxf路径或data/sample下文件名>")
        return 2
    target = sys.argv[1]
    # 兼容「裸文件名 → data/sample/ 下找」与「绝对/相对路径」两种输入
    path = target if os.path.exists(target) else \
        os.path.join(project_root, "data", "sample", target)
    reader = DXFReader(path)
    if not reader.open():
        print(json.dumps({"error": f"无法打开 DXF: {path}"}, ensure_ascii=False))
        return 1
    report = scan_dwg(reader)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())

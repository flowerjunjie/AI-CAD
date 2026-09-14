"""
AI-CAD 户型可视化 — 把真实墙线解析成房间轮廓, 渲染成 PNG 给你看效果。

用法:
    python scripts/render_floorplan.py              # 内置示例 L 形 + 网格户型
    python scripts/render_floorplan.py <图.dxf>     # 渲染你给的 dxf (WALL 图层)

输出: output/floorplan_<name>.png (肉眼验收用)
"""
import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

from src.agents.src.tools.wall_topology import partition_rooms


def build_sample_segs():
    """
    内置示例: 一个自洽的 3 房 L 形户型。
    外墙围成 L 形 (底 12x5 + 左上 6x4), 内墙两端都贯通到外墙(不留断口),
    把 L 形切成 3 个真实房间: 主卧(右下) / 客厅(右上 L 突出部) / 次卧(左上)。
    """
    # L 形外轮廓 (顶点顺序: 底 -> 右 -> 凹角 -> 顶)
    outer = [
        ((0, 0), (12, 0)),          # 南边
        ((12, 0), (12, 5)),         # 东南 (右边下半)
        ((12, 5), (6, 5)),          # 东 -> 凹
        ((6, 5), (6, 9)),           # 凹角竖边
        ((6, 9), (0, 9)),           # 北边
        ((0, 9), (0, 0)),           # 西边
    ]
    # 内墙 (两端贯通到外墙, 切出 3 房)
    inner = [
        ((0, 6), (6, 6)),          # 横墙: 把左上 6x4 区与上部分隔 -> 次卧 6x3
        ((4, 0), (4, 6)),          # 竖墙: 把下半分成 次卧左 + 主卧右
    ]
    return outer + inner


def segs_from_dxf(path: str):
    """从 dxf 的 WALL 图层读墙线段。"""
    from src.agents.src.tools.cad_tools import DXFReader
    reader = DXFReader(path)
    if not reader.open():
        raise SystemExit(f"打不开 {path} (需 ezdxf 能读; 真实 .dwg 需 ODA 转 .dxf)")
    return reader.get_wall_segments()


def _polygon_centroid(poly):
    """多边形质心 (shoelace), 让 L 形房间的标注落在真实重心而非顶点平均。"""
    n = len(poly)
    if n < 3:
        return poly[0] if poly else (0, 0)
    a = cx = cy = 0.0
    for i in range(n):
        x0, y0 = poly[i]
        x1, y1 = poly[(i + 1) % n]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-9:
        return (sum(p[0] for p in poly) / n, sum(p[1] for p in poly) / n)
    return (cx / (6 * a), cy / (6 * a))


def render(segs, out_path: str, title: str):
    import ezdxf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # 中文标题不再变豆腐块 — 收敛到 CJK 字体配置
    from src.agents.src.tools.matplotlib_cjk import configure_cjk
    configure_cjk()

    topo = partition_rooms(segs)
    rooms = [r for r in topo["rooms"] if not r["is_outer"]]

    # 建一份渲染用 dxf: 墙线 + 房间虚框
    doc = ezdxf.new("AC1027")
    doc.layers.new("WALL")
    doc.layers.new("ROOM")
    doc.layers.new("LABEL")
    msp = doc.modelspace()

    # 1. 原墙线 (WALL 层, 黑色粗线)
    for a, b in segs:
        msp.add_line(a, b, dxfattribs={"layer": "WALL"})

    # 原 L 形户型示意 (示例用) — 实际由 build_sample_segs 的坐标画出
    # 2. 解析出的房间 (ROOM 层, 绿色虚线框) + 面积标注 (LABEL 层)
    for i, r in enumerate(rooms):
        poly = r["polygon"]
        for j in range(len(poly)):
            x0, y0 = poly[j]
            x1, y1 = poly[(j + 1) % len(poly)]
            msp.add_line((x0, y0), (x1, y1),
                         dxfattribs={"layer": "ROOM", "linetype": "DASHED"})
        # 房间中心标注 (用真实多边形质心, 而非 bbox 中心 — L 形才不会标错位置)
        import math
        cx, cy = _polygon_centroid(poly)
        msp.add_text(f"Room {i+1}: {r['area']:.1f} m2", dxfattribs={
            "layer": "LABEL", "height": 0.4, "insert": (cx, cy)})

    # 渲染成 PNG (ezdxf 1.4.4: setup_axes + MatplotlibBackend)
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend, setup_axes

    fig, ax = plt.subplots(figsize=(10, 8), dpi=110)
    ctx = RenderContext(doc)
    backend = MatplotlibBackend(ax)
    Frontend(ctx, backend).draw_layout(doc.modelspace(), finalize=True)
    setup_axes(ax)
    ax.set_title(title, fontsize=13)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    plt.savefig(out_path)
    plt.close(fig)
    return topo, rooms


def main():
    # Windows 终端默认 GBK, 打印 ✓/→ 等 Unicode 会崩 — 统一切 UTF-8, 一处收敛全部
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    out_dir = os.path.join(PROJECT_ROOT, "output")
    if len(sys.argv) > 1:
        src = sys.argv[1]
        segs = segs_from_dxf(src)
        name = os.path.splitext(os.path.basename(src))[0]
        title = f"渲染 {src} — WALL 图层解析"
    else:
        segs = build_sample_segs()
        name = "sample_lshape"
        title = "示例 L 形 3 房户型 (真实墙线 → 解析房间)"

    out_path = os.path.join(out_dir, f"floorplan_{name}.png")
    topo, rooms = render(segs, out_path, title)

    print(f"解析出 {len(rooms)} 个房间, 诊断: {topo['diagnostics']}")
    for i, r in enumerate(rooms):
        print(f"  Room {i+1}: 面积 {r['area']:.1f} m2  bbox={tuple(round(v,1) for v in r['bbox'])}")
    print(f"\n✓ 户型图已生成: {out_path}")
    print("  黑色实线 = 原始墙线, 绿色 = 解析出的房间轮廓, 标注 = 房间面积")
    if os.name != "nt":
        import webbrowser
        webbrowser.open(out_path)
    else:
        os.startfile(out_path)


if __name__ == "__main__":
    main()

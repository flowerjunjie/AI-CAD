"""
单元测试 — CAD 制图惯例深化 (Linetype / Axis / Hatch)
验证: DXFWriter._ensure_linetypes 幂等 + add_pipe/hvac_duct DASHED
      + add_axis_grid CENTERLINE 点划线 + add_beam(hatch=True) 填充。
仿 test_wall_thickness.py (出图实体断言 + ezdxf 读回范式)。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)


def test_ensure_linetypes_idempotent():
    """_ensure_linetypes 重复调用不炸 (幂等: 已有同名线型则跳过)。"""
    from src.agents.src.tools.cad_tools import DXFWriter

    writer = DXFWriter()
    writer.new("AC1027")
    writer._ensure_linetypes()
    writer._ensure_linetypes()  # 第二次应 no-op

    import ezdxf
    lt = [l.dxf.name for l in writer.doc.linetypes]
    assert "DASHED" in lt, f"DASHED 线型应存在, 实际 {lt}"
    assert "CENTERLINE" in lt, f"CENTERLINE 线型应存在, 实际 {lt}"
    # 幂等: 重复调用不产生重复项
    names = [l.dxf.name for l in writer.doc.linetypes]
    assert names.count("DASHED") == 1, f"DASHED 应恰好 1 条, 实际 {names}"
    assert names.count("CENTERLINE") == 1, f"CENTERLINE 应恰好 1 条, 实际 {names}"


def test_add_pipe_dashed_linetype():
    """add_pipe: PIPE 层 LWPOLYLINE 线型 = DASHED (管道制图惯例虚线)。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Pipe, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_pipe(Pipe(start=Point(0, 0), end=Point(5, 0), diameter_mm=50))
    assert n == 1, f"add_pipe 应返回 1 条标注, 实际 {n}"

    msp = writer.doc.modelspace()
    lwp = list(msp.query('LWPOLYLINE[layer=="PIPE"]'))[0]
    assert lwp.dxf.linetype == "DASHED", \
        f"管道 LWPOLYLINE 线型应 DASHED, 实际 {lwp.dxf.linetype!r}"


def test_add_hvac_duct_dashed_linetype():
    """add_hvac_duct: HVAC_DUCT 层 LWPOLYLINE 线型 = DASHED (风管制图惯例虚线)。"""
    from src.agents.src.tools.cad_tools import DXFWriter, HvacDuct, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_hvac_duct(HvacDuct(start=Point(0, 0), end=Point(5, 0),
                                      diameter_mm=100))
    assert n == 1, f"add_hvac_duct 应返回 1 条标注, 实际 {n}"

    msp = writer.doc.modelspace()
    lwp = list(msp.query('LWPOLYLINE[layer=="HVAC_DUCT"]'))[0]
    assert lwp.dxf.linetype == "DASHED", \
        f"风管 LWPOLYLINE 线型应 DASHED, 实际 {lwp.dxf.linetype!r}"


def test_add_axis_grid_centerline_linetype():
    """add_axis_grid: AXIS 层轴线 LINE 全部 CENTERLINE 点划线 + 轴号 ①②③/A/B。"""
    from src.agents.src.tools.cad_tools import DXFWriter

    writer = DXFWriter()
    writer.new("AC1027")
    x_axes = [("①", 0.0, -0.5, 5.5), ("②", 2.0, -0.5, 5.5), ("③", 4.0, -0.5, 5.5)]
    y_axes = [("A", 0.0, -0.5, 4.5), ("B", 4.0, -0.5, 4.5)]
    count = writer.add_axis_grid(x_axes, y_axes)
    assert count == 5, f"3 X 轴 + 2 Y 轴 应 5 条, 实际 {count}"

    msp = writer.doc.modelspace()
    # AXIS 层 LINE 全 CENTERLINE
    lines = list(msp.query('LINE[layer=="AXIS"]'))
    assert len(lines) == 5, f"AXIS 层应 5 条 LINE, 实际 {len(lines)}"
    for ln in lines:
        assert ln.dxf.linetype == "CENTERLINE", \
            f"轴线应 CENTERLINE, 实际 {ln.dxf.linetype!r}"
    # 轴号 ①②③ A B 全在 AXIS 层 TEXT
    texts = sorted(t.dxf.text for t in msp.query('TEXT[layer=="AXIS"]'))
    for expected in ("①", "②", "③", "A", "B"):
        assert expected in texts, f"轴号 {expected!r} 未画, 实际 {texts}"


def test_add_beam_hatch_creates_beams_fill():
    """add_beam(hatch=True): BEAM_FILL 层 HATCH 实填充 (最小深化)。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Beam, Point

    writer = DXFWriter()
    writer.new("AC1027")
    n = writer.add_beam(Beam(start=Point(0, 0), end=Point(4, 0),
                             width_mm=300, depth_mm=600), hatch=True)
    assert n == 1, f"add_beam 应返回 1 条标注, 实际 {n}"

    msp = writer.doc.modelspace()
    # BEAM_FILL 层有 HATCH
    hatches = list(msp.query('HATCH[layer=="BEAM_FILL"]'))
    assert len(hatches) == 1, f"BEAM_FILL 应 1 条 HATCH, 实际 {len(hatches)}"
    # BEAM 层 LWPOLYLINE 仍存在 (深化不删既有实体)
    assert len(msp.query('LWPOLYLINE[layer=="BEAM"]')) == 1, "梁本体 LWPOLYLINE 不能丢"


def test_add_beam_default_no_hatch():
    """add_beam 默认 hatch=False 不画填充 (向后兼容: 既有 dwg_export 不破)。"""
    from src.agents.src.tools.cad_tools import DXFWriter, Beam, Point

    writer = DXFWriter()
    writer.new("AC1027")
    writer.add_beam(Beam(start=Point(0, 0), end=Point(4, 0)))

    msp = writer.doc.modelspace()
    assert len(msp.query('HATCH[layer=="BEAM_FILL"]')) == 0, \
        "默认 (hatch=False) 不应画填充"
    assert len(msp.query('LWPOLYLINE[layer=="BEAM"]')) == 1, "梁本体不能丢"


def test_cad_execute_writes_linetypes_roundtrip():
    """cad_execute_node: DASHED 线型 + AXIS 点划线 + 轴号 全量读回核对。
    ezdxf 读回范式 (仿 test_pipe_dwg_export.py 的 e2e 读回)。"""
    import ezdxf
    from src.agents.src.nodes.cad_rule_export import cad_execute_node
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(project_root, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    state = {
        "raw_data": parsed["raw_data"],
        "project_structure": parsed["project_structure"],
        "task_list": parsed["task_list"],
        "output_path": "/tmp/aicad_linetype_test.dwg",
        "auto_mode": True,
    }
    result = cad_execute_node(state)
    assert result.get("final_dwg_path"), "DWG 应生成"

    doc = ezdxf.readfile(result["final_dwg_path"])
    msp = doc.modelspace()
    # DASHED 线型存在
    lt = [l.dxf.name for l in doc.linetypes]
    assert "DASHED" in lt, f"DASHED 线型应存在, 实际 {lt}"
    assert "CENTERLINE" in lt, f"CENTERLINE 线型应存在, 实际 {lt}"
    # 管道 LWPOLYLINE 全 DASHED
    pipe_lwps = list(msp.query('LWPOLYLINE[layer=="PIPE"]'))
    assert len(pipe_lwps) == 2, f"PIPE 应 2 条 LWPOLYLINE, 实际 {len(pipe_lwps)}"
    for p in pipe_lwps:
        assert p.dxf.linetype == "DASHED", f"管道线型应 DASHED, 实际 {p.dxf.linetype!r}"
    # HVAC duct DASHED
    hvac_lwps = list(msp.query('LWPOLYLINE[layer=="HVAC_DUCT"]'))
    assert len(hvac_lwps) == 1, f"HVAC_DUCT 应 1 条 LWPOLYLINE, 实际 {len(hvac_lwps)}"
    assert hvac_lwps[0].dxf.linetype == "DASHED", "风管线型应 DASHED"
    # 轴网点划线 (CENTERLINE) + 轴号
    axis_lines = list(msp.query('LINE[layer=="AXIS"]'))
    assert len(axis_lines) >= 5, f"AXIS 应 >= 5 条线, 实际 {len(axis_lines)}"
    for ln in axis_lines:
        assert ln.dxf.linetype == "CENTERLINE", \
            f"轴线应 CENTERLINE, 实际 {ln.dxf.linetype!r}"
    # 轴号 ①②③ A B 在 AXIS 层
    texts = [t.dxf.text for t in msp.query('TEXT[layer=="AXIS"]')]
    for expected in ("①", "②", "③", "A", "B"):
        assert expected in texts, f"轴号 {expected!r} 未画, 实际 {texts}"
    # 既有 dwg_export 验收的实体数量不被深化破坏
    assert len(msp.query('LWPOLYLINE[layer=="BEAM"]')) == 2, "BEAM 实体数不能变"
    assert len(msp.query('LWPOLYLINE[layer=="COLUMN"]')) == 3, "COLUMN 实体数不能变"
    assert len(msp.query('LWPOLYLINE[layer=="ELEC_OUTLET"]')) == 2, "ELEC_OUTLET 不能变"
    # dimension 任务结果含 axes 键 (深化新增属性)
    dim = [r for r in result["cad_results"] if r["task_id"] == "dim-axis"][0]
    assert dim.get("axes", 0) >= 5, f"axes 键应 >= 5, 实际 {dim.get('axes')}"


if __name__ == "__main__":
    test_ensure_linetypes_idempotent()
    test_add_pipe_dashed_linetype()
    test_add_hvac_duct_dashed_linetype()
    test_add_axis_grid_centerline_linetype()
    test_add_beam_hatch_creates_beams_fill()
    test_add_beam_default_no_hatch()
    test_cad_execute_writes_linetypes_roundtrip()
    print("OK: all CAD drawing-refinement (linetype/axis/hatch) tests passed")

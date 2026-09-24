"""
AI-CAD 一键运行入口
设置 UTF-8 输出 + 加载 .env + 跑完整流程 + 生成 HTML 报告
用法: python run.py            (全流程含 LLM)
      python run.py --no-llm   (纯本地快速验证)
"""
import sys
import os
import json
import html as html_mod

# ─── 编码修复: 强制 stdout 用 UTF-8 ─────────────────────────────
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# 添加项目根目录
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)

# 加载 .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(PROJECT_ROOT, ".env"))
except ImportError:
    pass

# 默认 Agnes 配置（密钥从 .env / 环境变量读取，不硬编码）
os.environ.setdefault("AI_CAD_LLM_PROVIDER", "agnes")
os.environ.setdefault("AGNES_BASE_URL", "https://apihub.agnes-ai.com/v1")
os.environ.setdefault("AGNES_MODEL", "agnes-2.0-flash")

NO_LLM = "--no-llm" in sys.argv
USE_LLM = "--llm" in sys.argv


def section(title):
    print(f"\n{'=' * 56}")
    print(f"  {title}")
    print(f"{'=' * 56}")


def run_rules():
    """规则引擎验证"""
    section("[1/5] 规则引擎")
    import src.rules.src.residential.doors
    import src.rules.src.residential.windows
    import src.rules.src.residential.corridors
    import src.rules.src.residential.rooms
    import src.rules.src.residential.areas
    import src.rules.src.residential.stairs
    import src.rules.src.residential.daylight
    import src.rules.src.fire_safety.corridors
    import src.rules.src.fire_safety.exits
    import src.rules.src.accessibility.ramps
    import src.rules.src.accessibility.entrances

    from src.rules.src.engine import get_engine, ViolationSeverity
    from src.rules.src.residential.doors import Door

    engine = get_engine()
    rules = engine.list_rules()
    sev_count = {"ERROR": 0, "WARNING": 0, "INFO": 0}
    for r in rules:
        sev_count[r.severity.value.upper()] = sev_count.get(r.severity.value.upper(), 0) + 1

    print(f"  已注册规范: {len(rules)} 条")
    print(f"  严重级别:  ERROR={sev_count['ERROR']}  WARNING={sev_count['WARNING']}  INFO={sev_count['INFO']}")

    # 实测一条违规
    bad_door = Door(id="test-d1", width_m=0.6, room_type="entrance", location=(0, 0))
    v = engine.check([bad_door], rule_ids=["residential-door-main-width"])
    print(f"  实测: 0.6m 户门 -> {'检出违规 ✓' if len(v) else '未检出 ✗'}")
    return len(rules)


def run_parser():
    """输入解析验证"""
    section("[2/5] 户型输入解析")
    from src.agents.src.nodes.input_parser import parse_json_input

    sample = os.path.join(PROJECT_ROOT, "data", "sample", "residential_100sqm.json")
    parsed = parse_json_input(sample)
    zones = parsed["project_structure"]["zones"]
    print(f"  样本: {parsed['project_type']} / {parsed['project_structure']['building_area']}㎡")
    print(f"  功能区: {len(zones)} 个  门: {sum(1 for z in parsed.get('raw_data', {}).get('doors', []))}  窗: {sum(1 for z in parsed.get('raw_data', {}).get('windows', []))}")
    print(f"  生成任务: {len(parsed['task_list'])} 个")
    return parsed


def run_cad():
    """CAD 图纸生成验证"""
    section("[3/5] CAD 图纸生成")
    from src.agents.src.tools.cad_tools import DXFWriter, Wall, Door as CADDoor, Window as CADWindow, Point

    out_dwg = os.path.join(PROJECT_ROOT, "output", "ai_cad_output.dwg")
    os.makedirs(os.path.dirname(out_dwg), exist_ok=True)

    writer = DXFWriter()
    writer.new()
    writer.add_wall(Wall(start=Point(0, 0), end=Point(10, 0), thickness=0.24))
    writer.add_wall(Wall(start=Point(10, 0), end=Point(10, 6), thickness=0.24))
    writer.add_door(CADDoor(position=Point(2, 0), width=1.0))
    writer.add_window(CADWindow(start=Point(4, 6), end=Point(6, 6), sill_height=0.9))
    writer.save(out_dwg)

    # 读回验证
    import ezdxf
    doc = ezdxf.readfile(out_dwg)
    msp = doc.modelspace()
    lines = len(list(msp.query("LINE")))
    arcs = len(list(msp.query("ARC")))
    print(f"  输出: {out_dwg}")
    print(f"  实体: {lines} 线条 / {arcs} 弧线 / {len(doc.layers)} 图层")
    print(f"  大小: {os.path.getsize(out_dwg)} bytes")
    return out_dwg


def run_agent(parsed):
    """Agent 端到端"""
    section("[4/5] Agent 端到端流程")
    from src.agents.src.graph import run_agent_demo
    from src.agents.src.nodes.intent_structure import _get_llm
    sample = os.path.join(PROJECT_ROOT, "data", "sample", "residential_100sqm.json")

    # --llm: 真 LLM 主导 — intent+structure 节点生成方案, 不被样本 project_structure 覆盖
    # 默认 / --no-llm: 本地快验 — sample 的 raw_data+task_list 直接驱动 CAD (秒级, 结果确定)
    inject_structure = not USE_LLM
    result = run_agent_demo(
        sample_path=sample, auto_mode=True,
        inject_sample_structure=inject_structure,
    )

    if USE_LLM:
        llm_live = _get_llm() is not None
        print(f"  (LLM 主导模式: intent+structure 由 LLM 生成方案 "
              f"{'— LLM 实例就绪' if llm_live else '— 无 LLM, 静默 fallback 默认住宅'})")
    elif NO_LLM:
        print("  (跳过 LLM, 走本地数据接线: 样本 raw_data 驱动 CAD+规则)")
    print(f"  项目类型: {result.get('project_type')}")
    print(f"  CAD 任务: {len(result.get('cad_results', []))} 个")
    print(f"  规范违规: {len(result.get('rule_violations', []))} 条")
    for v in result.get("rule_violations", []):
        print(f"    - {v['rule_name']}: {v['element_id']}")
    print(f"  DWG: {result.get('final_dwg_path')}")
    return result


def write_report(rule_count, parsed, dwg, agent_result):
    """生成 HTML 报告"""
    out = os.path.join(PROJECT_ROOT, "output", "report.html")
    zones = parsed["project_structure"]["zones"]
    violations = agent_result.get("rule_violations", []) if agent_result else []

    rows = ""
    for z in zones:
        rows += f"<tr><td>{html_mod.escape(z.get('name',''))}</td><td>{z.get('type','')}</td><td>{z.get('area','')}㎡</td></tr>"

    vio_html = "".join(f"<li>{html_mod.escape(v.get('rule_name',''))}</li>" for v in violations) or "<li>无</li>"

    report = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>AI-CAD 运行报告</title>
<style>
  body{{font-family:'Segoe UI',system-ui,sans-serif;max-width:720px;margin:40px auto;padding:0 20px;color:#222}}
  h1{{border-bottom:3px solid #e94560;padding-bottom:8px}}
  .card{{background:#f7f9fc;border-left:4px solid #0f3460;padding:16px 20px;margin:16px 0;border-radius:6px}}
  .num{{font-size:2em;font-weight:700;color:#e94560}}
  table{{width:100%;border-collapse:collapse;margin:10px 0}}
  th,td{{text-align:left;padding:8px;border-bottom:1px solid #eee}}
  .ok{{color:#2ecc71;font-weight:600}}
  .badge{{display:inline-block;background:#0f3460;color:#fff;padding:3px 10px;border-radius:12px;font-size:12px}}
</style></head><body>
<h1>AI-CAD 施工图深化系统 · 运行报告</h1>
<div class="card"><span class="badge">核心能力验证</span>
  <p><span class="num">{rule_count}</span> 条规范规则 &nbsp;·&nbsp;
     <span class="num">{len(parsed['task_list'])}</span> 个 CAD 任务 &nbsp;·&nbsp;
     <span class="num">{len(violations)}</span> 条规范违规</p>
  <p class="ok">✓ 全链路运行成功</p>
</div>
<div class="card"><h3>功能分区 ({len(zones)})</h3>
  <table><tr><th>房间</th><th>类型</th><th>面积</th></tr>{rows}</table>
</div>
<div class="card"><h3>规范违规</h3><ul>{vio_html}</ul></div>
<div class="card"><h3>输出文件</h3><p>{html_mod.escape(str(dwg))}</p></div>
</body></html>"""
    with open(out, "w", encoding="utf-8") as f:
        f.write(report)
    return out


def main():
    print("\n" + "=" * 56)
    print("  AI-CAD 施工图深化系统 · 一键运行")
    print("=" * 56)

    rule_count = run_rules()
    parsed = run_parser()
    dwg = run_cad()
    agent_result = run_agent(parsed)

    section("[5/5] 生成报告")
    report = write_report(rule_count, parsed, dwg, agent_result)
    print(f"  DWG:    {dwg}")
    print(f"  报告:   {report}")
    print(f"\n✓ 全链路运行成功 — 共 {rule_count} 条规范 / {len(parsed['task_list'])} 个任务\n")

    # 体验闭环: 渲染一张真实户型图 + 自动打开 (肉眼验收, 不用手开 CAD)
    if not NO_LLM or "--render" in sys.argv:
        try:
            png = render_and_open(dwg)
            print(f"  户型图: {png}")
        except Exception as e:
            print(f"  [提示] 户型渲染跳过: {e}")


def render_and_open(dwg_path: str) -> str:
    """把 DWG 渲染成 PNG 并自动打开, 让你一眼看到出图效果。"""
    import ezdxf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend, setup_axes
    # 中文标题/标注不再变豆腐块 — 收敛到 CJK 字体配置
    from src.agents.src.tools.matplotlib_cjk import configure_cjk
    configure_cjk()

    doc = ezdxf.readfile(dwg_path)
    msp = doc.modelspace()
    png = os.path.join(PROJECT_ROOT, "output", "preview.png")
    os.makedirs(os.path.dirname(png), exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 7), dpi=110)
    ctx = RenderContext(doc)
    backend = MatplotlibBackend(ax)
    Frontend(ctx, backend).draw_layout(msp, finalize=True)
    setup_axes(ax)
    ax.set_title("AI-CAD 出图预览", fontsize=13)
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(png)
    plt.close(fig)

    if os.name == "nt":
        os.startfile(png)
    else:
        import webbrowser
        webbrowser.open(png)
    return png


if __name__ == "__main__":
    main()

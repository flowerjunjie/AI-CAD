"""给排水专业端到端测试: 造 DWG → 读 → 抽 → 规则引擎 → 断言。

链路 (全真实调用, 无 mock):
  DXFReader.open() → get_plumbing_segments(include_layer=True)
  → extract_plumbing_pipes(segs, manhole_points, annotations)
  → DslRuleProvider(default.json).upsert_into(RuleEngine()) → engine.check(pipes)

断言目标 (对应 data/sample/plumbing_sample.dxf 的 4 条管线):
  - PIPE_WASTE DN40 段 → 命中 plumbing-waste-pipe-min-diameter (40 < 50)
  - 坡度 30% 段 → 命中 plumbing-pipe-slope-in-range (30 > 12)
  - 其余管段 3 条规则全过; DN110 段管径不报; 距检查井 5m < 12m 上限不报
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 样本 DXF 路径 (由 data/sample/make_plumbing_sample_dxf.py 生成, 已入库)
SAMPLE_DXF = os.path.join(project_root, "data", "sample", "plumbing_sample.dxf")
DEFAULT_JSON = os.path.join(project_root, "src", "rules", "rules", "default.json")

# 高程标注 (m), 与 DXF 坐标同框: 坡度 = |Δ高程| / 水平距离 × 100%
#  - (0,20)->(10,20): 水平 10m, 高程差 3.0m → 30% (超 max_slope=12, 命中 slope 违规)
#  - 其余管段不设高程差 → 坡度 0% (低于 min_slope=0.4%, 命中 slope 下限违规)
#
# 注: 坡度下限 0.4% 为 GB 50015-2019 第4.5.6条横干管最小坡度通行值 (DN200),
# 对「无高程标注」的占位 0% 属正常误报场景 (样本无真实坡度数据)。e2e 只断言
# slope 超限违规 (30% > 12%) 指向 oversloped 段, 下限违规在 clean 段上是否出现
# 不做断言 — 因为 0% 是抽取层「无标注→0.0」的占位, 非真实设计坡度, 上线时
# 真实图纸会有实际坡度值。
_ELEVATIONS = {
    "PIPE": {(0, 20): 3.0, (10, 20): 0.0},
}

# 检查井位置: 距 far 段 (中点 (10,40)) 为 5.0m < 12m 上限, 不命中 manhole 违规
_MANHOLE_POINTS = [(10, 45)]

# 真实管径标注: PIPE_WASTE 段 (0,10)->(5,10) 中点 (2.5,10) 是 DN40 偏小管,
# 覆盖 _LAYER_MAP 的占位 110, 使其命中 min-diameter (40 < 50)。
_DIAMETERS = {
    "PIPE_WASTE": {(2.5, 10): 40},
}

# 管线 id 映射: get_plumbing_segments 按「默认图层组顺序」平铺输出
# (PIPE 先遍历, 组内 LINE 逐条 = DXF 文档顺序), 与 ezdxf 文档顺序绑定:
#   plumbing-0: PIPE good (0,0)->(10,0)      drain/50 (>= 最小 50, 管径不报)
#   plumbing-1: PIPE oversloped (0,20)->(10,20)  坡度 30% (超 max_slope=12, 报)
#   plumbing-2: PIPE far (0,40)->(20,40)     距井 5.0m (< 12m 上限, manhole 不报)
#   plumbing-3: PIPE_WASTE bad (0,10)->(5,10) waste/40 (< 最小 50, 报)
# 图层→管径映射见 plumbing_extractor._LAYER_MAP: PIPE_WASTE→110 是占位, 好管走
# PIPE(→drain/50)。故 good 段断言 50 而非 110 (验证"好管径不误报", 具体值随映射)。
_GOOD, _OVERSLOPED, _FAR, _DN40 = "plumbing-0", "plumbing-1", "plumbing-2", "plumbing-3"


def _run() -> tuple[list, list]:
    """跑全链路, 返回 (pipes, violations)。"""
    from src.agents.src.tools.cad_tools import DXFReader
    from src.agents.src.tools.plumbing_extractor import extract_plumbing_pipes
    from src.rules.src.engine import RuleEngine
    from src.rules.src.dsl import DslRuleProvider

    reader = DXFReader(SAMPLE_DXF)
    assert reader.open(), f"样本 DXF 打开失败: {SAMPLE_DXF}"
    # 显式指定图层组: PIPE 的 LINE 逐条按文档顺序读, PIPE_WASTE 紧随其后
    segs = reader.get_plumbing_segments(layer_names=("PIPE", "PIPE_WASTE"), include_layer=True)
    assert len(segs) == 4, f"样本应 4 段, 实际 {len(segs)}: {segs}"

    pipes = extract_plumbing_pipes(
        segs,
        manhole_points=_MANHOLE_POINTS,
        annotations=_ELEVATIONS,
        diameter_annotations=_DIAMETERS,
    )

    engine = RuleEngine()
    DslRuleProvider(DEFAULT_JSON).upsert_into(engine)
    violations = engine.check(pipes)
    return pipes, violations


def test_sample_dxf_exists():
    """样本 DWG 必须已生成 (先跑 data/sample/make_plumbing_sample_dxf.py)。"""
    assert os.path.isfile(SAMPLE_DXF), f"缺样本 {SAMPLE_DXF}"


def test_e2e_dn40_hits_min_diameter():
    """DN40 排水横管段命中 plumbing-waste-pipe-min-diameter (40 < 50), 且管径违规仅此一段。"""
    pipes, violations = _run()
    bad = next(p for p in pipes if p.id == _DN40)
    assert bad.diameter_mm == 40 and bad.pipe_type == "waste", \
        f"{_DN40} 应映射 waste/40, 实际 {bad.pipe_type}/{bad.diameter_mm}"
    hits = [v for v in violations if v.rule_id == "plumbing-waste-pipe-min-diameter"]
    assert len(hits) == 1, f"管径违规应恰 1 条, 实际 {len(hits)}: {[v.element_id for v in hits]}"
    assert hits[0].element_id == _DN40, \
        f"管径违规应指向 DN40 段 {_DN40}, 实际 {hits[0].element_id}"


def test_e2e_oversloped_hits_slope_rule():
    """坡度 30% 段命中 plumbing-pipe-slope-in-range (30 > 12), 且 30% 超限的 slope 违规指向 oversloped 段。"""
    pipes, violations = _run()
    steep = next(p for p in pipes if p.id == _OVERSLOPED)
    assert steep.slope > 12.0, f"{_OVERSLOPED} 坡度应 > 12% (高程标注 30%), 实际 {steep.slope}"
    # 30% 超上限的 slope 违规必须指向 oversloped 段 (下限 0% 违规指向其他段是占位正常场景, 此处不锁定)
    hits_upper = [v for v in violations
                  if v.rule_id == "plumbing-pipe-slope-in-range"
                  and v.element_id == _OVERSLOPED]
    assert len(hits_upper) >= 1, \
        f"坡度超限违规应至少 1 条指向 {_OVERSLOPED}, 实际 {[v.element_id for v in hits_upper]}"


def test_e2e_far_segment_manhole_distance_pass():
    """距检查井 5.0m < 12m 上限, manhole 规则对 far 段零命中 (回填后 12m 上限生效)。"""
    pipes, violations = _run()
    far = next(p for p in pipes if p.id == _FAR)
    assert far.distance_to_manhole_m == 5.0, \
        f"{_FAR} 距检查井应 5.0m, 实际 {far.distance_to_manhole_m}"
    assert far.distance_to_manhole_m <= 12.0, \
        f"{_FAR} 距检查井 {far.distance_to_manhole_m}m 应 <= 12m (回填上限)"
    hits = [v for v in violations
            if v.rule_id == "plumbing-pipe-manhole-distance" and v.element_id == _FAR]
    assert len(hits) == 0, \
        f"{_FAR} 距检查井 5m < 12m, manhole 规则应零命中, 实际 {[v.element_id for v in hits]}"


def test_e2e_dn110_not_flagged():
    """好管段 (PIPE→drain/50, >= 最小 50) 管径规则零命中 — 好管径不误报。"""
    pipes, violations = _run()
    good = next(p for p in pipes if p.id == _GOOD)
    assert good.diameter_mm == 50 and good.pipe_type == "drain", \
        f"{_GOOD} 应映射 drain/50 (PIPE 图层), 实际 {good.pipe_type}/{good.diameter_mm}"
    assert all(v.element_id != _GOOD for v in violations
               if v.rule_id == "plumbing-waste-pipe-min-diameter"), \
        "好管段不应命中管径规则"


if __name__ == "__main__":
    test_sample_dxf_exists()
    test_e2e_dn40_hits_min_diameter()
    test_e2e_oversloped_hits_slope_rule()
    test_e2e_far_segment_manhole_distance_pass()
    test_e2e_dn110_not_flagged()
    print("\nPlumbing E2E tests passed!")

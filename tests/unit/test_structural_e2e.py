"""结构专业端到端测试: 造 DWG → 读 → 抽 → 规则引擎 → 断言。

链路 (全真实调用, 无 mock):
  DXFReader.open() → get_structural_segments(include_layer=True)
    → extract_structural_beams(segs, annotations)      # 梁 (线段类)
  DXFReader.open() → get_structural_blocks()
    → extract_structural_columns(blocks)                # 柱 (块类)
  → DslRuleProvider(default.json).upsert_into(RuleEngine()) → engine.check(elements)

断言目标 (对应 data/sample/structural_sample.dxf):
  - BEAM 扁梁段 (300×300, 深宽比 1.0) → 命中 structural-beam-width-depth-ratio
  - BEAM 合规梁段 (300×600, 深宽比 2.0) → 放行, 不误报
  - COLUMN COL_S (截面短边 200mm)  → 命中 structural-column-min-section
  - COLUMN COL_K (截面短边 400mm)  → 放行, 不误报

截面深不来自 DXF 线段 (纯 2D 几何无截面), 由调用侧按「段中点 → 截面深 mm」
标注提供 (镜像 plumbing 高程标注范式); 柱截面短边由 extractor 按块名映射。
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 样本 DXF 路径 (由 data/sample/make_structural_sample_dxf.py 生成, 已入库)
SAMPLE_DXF = os.path.join(project_root, "data", "sample", "structural_sample.dxf")
DEFAULT_JSON = os.path.join(project_root, "src", "rules", "rules", "default.json")

# 梁截面深标注 (mm), 与 DXF 坐标同框: 段中点 (x,y) → 截面深
#   扁梁 (0,0)->(4,0)  中点 (2.0,0.0)  → 深 300 → 深宽比 300/300 = 1.0 (< 下限, 违规)
#   合规梁 (0,10)->(4,10) 中点 (2.0,10.0) → 深 600 → 深宽比 600/300 = 2.0 (区间内, 合规)
#
# 上游跨度标注 (m), 段中点 (x,y) → 跨度: 供 structural-beam-min-height /
# structural-beam-span-depth-ratio 使用 (两规则 predicate 前置 span_m > 0,
# StructuralBeam 现无 span_m 字段, 需上游按 docs/structural-upstream-contract.md
# 补齐跨度)。e2e 样本暂不喂跨度, 两规则安全放行 (不误报), 补齐后自动生效。
_BEAM_DEPTHS = {
    (2.0, 0.0): 300,
    (2.0, 10.0): 600,
}


def _run() -> tuple[list, list, list]:
    """跑全链路, 返回 (beams, columns, violations)。"""
    from src.agents.src.tools.cad_tools import DXFReader
    from src.agents.src.tools.structural_extractor import (
        extract_structural_beams,
        extract_structural_columns,
    )
    from src.rules.src.engine import RuleEngine
    from src.rules.src.dsl import DslRuleProvider

    reader = DXFReader(SAMPLE_DXF)
    assert reader.open(), f"样本 DXF 打开失败: {SAMPLE_DXF}"

    # 梁: 线段类 — 带图层 dict + 调用侧截面深标注
    segs = reader.get_structural_segments(include_layer=True)
    assert len(segs) == 2, f"样本 BEAM 应 2 段, 实际 {len(segs)}: {segs}"
    beams = extract_structural_beams(segs, annotations=_BEAM_DEPTHS)

    # 柱: 块类 — INSERT 块, 截面短边按块名映射
    blocks = reader.get_structural_blocks()
    assert len(blocks) == 2, f"样本 COLUMN 应 2 块, 实际 {len(blocks)}: {blocks}"
    columns = extract_structural_columns(blocks)

    # 规则引擎: 加载 default.json DSL 规则, 对梁/柱各自命中 structural-* 检查
    engine = RuleEngine()
    DslRuleProvider(DEFAULT_JSON).upsert_into(engine)
    violations = engine.check(beams)
    violations.extend(engine.check(columns))
    return beams, columns, violations


def test_sample_dxf_exists():
    """样本 DXF 必须已生成 (先跑 data/sample/make_structural_sample_dxf.py)。"""
    assert os.path.isfile(SAMPLE_DXF), f"缺样本 {SAMPLE_DXF}"


def test_e2e_flat_beam_hits_ratio_rule():
    """扁梁 (深宽比 1.0 < 下限 1.5) 命中 structural-beam-width-depth-ratio, 且命中点指向该扁梁。"""
    beams, columns, violations = _run()
    flat = [b for b in beams if b.width_mm > 0 and b.depth_mm / b.width_mm < 2.0]
    assert len(flat) == 1, f"应恰 1 根深宽比 < 2.0 的扁梁, 实际 {[b.id for b in flat]}"
    hits = [v for v in violations if v.rule_id == "structural-beam-width-depth-ratio"]
    assert len(hits) == 1, f"梁高宽比违规应恰 1 条, 实际 {len(hits)}: {[v.element_id for v in hits]}"
    assert hits[0].element_id == flat[0].id, \
        f"梁高宽比违规应指向扁梁 {flat[0].id}, 实际 {hits[0].element_id}"
    # 断言具体比值: 300/300 = 1.0 确破下限
    assert flat[0].depth_mm / flat[0].width_mm == 1.0, \
        f"扁梁深宽比应 1.0, 实际 {flat[0].depth_mm}/{flat[0].width_mm}"


def test_e2e_compliant_beam_passes():
    """合规梁 (深宽比 2.0) 不误报 — 深宽比规则零命中。"""
    beams, columns, violations = _run()
    good = [b for b in beams if b.depth_mm / b.width_mm == 2.0]
    assert len(good) == 1, f"应恰 1 根深宽比 2.0 的合规梁, 实际 {[b.id for b in good]}"
    assert all(v.element_id != good[0].id
               for v in violations if v.rule_id == "structural-beam-width-depth-ratio"), \
        f"合规梁 {good[0].id} (深宽比 2.0) 不应命中梁高宽比规则"


def test_e2e_small_column_hits_min_section():
    """小截面柱 (COL_S 短边 200mm < 300) 命中 structural-column-min-section, 且命中点指向该柱。"""
    beams, columns, violations = _run()
    small = [c for c in columns if c.column_type != "foundation" and c.section_mm < 300]
    assert len(small) == 1, f"应恰 1 根短边 < 300 的小截面柱, 实际 {[c.id for c in small]}"
    hits = [v for v in violations if v.rule_id == "structural-column-min-section"]
    assert len(hits) == 1, f"柱最小截面违规应恰 1 条, 实际 {len(hits)}: {[v.element_id for v in hits]}"
    assert hits[0].element_id == small[0].id, \
        f"柱最小截面违规应指向小柱 {small[0].id}, 实际 {hits[0].element_id}"
    # 断言具体截面: 200mm 确破 300mm 下限
    assert small[0].section_mm == 200, \
        f"小截面柱短边应 200mm, 实际 {small[0].section_mm}"


def test_e2e_compliant_column_passes():
    """合规格柱 (COL_K 短边 400mm) 不误报 — 最小截面规则零命中。"""
    beams, columns, violations = _run()
    good = [c for c in columns if c.column_type != "foundation" and c.section_mm >= 300]
    assert len(good) == 1, f"应恰 1 根短边 >= 300 的合规柱, 实际 {[c.id for c in good]}"
    assert all(v.element_id != good[0].id
               for v in violations if v.rule_id == "structural-column-min-section"), \
        f"合规柱 {good[0].id} (短边 400mm) 不应命中柱最小截面规则"


def test_e2e_no_extraneous_structural_hits():
    """全链路结构违规集合应恰好 = {扁梁, 小柱} 两根, 无多余误报。"""
    beams, columns, violations = _run()
    bad_ids = {v.element_id for v in violations if v.rule_id.startswith("structural-")}
    expected = {
        beams[0].id,  # 扁梁
        next(c.id for c in columns if c.section_mm == 200),  # 小截面柱
    }
    assert bad_ids == expected, \
        f"结构违规集合不符: 实际 {bad_ids}, 预期 {expected}"


if __name__ == "__main__":
    test_sample_dxf_exists()
    test_e2e_flat_beam_hits_ratio_rule()
    test_e2e_compliant_beam_passes()
    test_e2e_small_column_hits_min_section()
    test_e2e_compliant_column_passes()
    test_e2e_no_extraneous_structural_hits()
    print("\nStructural E2E tests passed!")

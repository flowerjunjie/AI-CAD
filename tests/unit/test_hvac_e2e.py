"""暖通专业端到端测试: 造 DWG → 读 → 抽 → 规则引擎 → 断言。

链路 (全真实调用, 无 mock):
  DXFReader.open() → get_hvac_points()
  → 调用侧数值标注 _HVAC_ANNOTATIONS (按坐标给 velocity_ms / location_type / height_m)
  → extract_hvac_points(points)
  → DslRuleProvider(default.json).upsert_into(RuleEngine()) → engine.check(elements)

断言目标 (对应 data/sample/hvac_sample.dxf 的 3 个 INSERT 块):
  - HVAC_DUCT  DUCT_STD @ (0,0)   超速风管 velocity_ms=12.0
       → 超上限 10.0 → 命中 hvac-duct-velocity-range
  - HVAC_UNIT  UNIT_STD  @ (4,0)   室内装室外机 unit_type=outdoor + location_type=indoor
       → 命中 hvac-unit-outdoor-placement
  - HVAC_GRILLE GRILLE_STD @ (2,2)  合规送风格栅 height_m=2.5
       → 在 [2.0, 4.0] 区间内 → 放行, 不误报

数值字段不来自 DXF (纯 2D 几何无数值), 由调用侧按「坐标 → 字段」标注提供,
与 DXF 坐标同框 (镜像 plumbing 高程 / structural 截面标注范式)。

规范数值说明:
  - hvac-duct-velocity-range 上限 10.0 已由专家回填并标 confirmed
  - hvac-unit-outdoor-placement 逻辑判定 (回填 code_ref + confirm_note, medium)
  - hvac-grille-height-range [2.0, 4.0] 高位送风放宽 (回填 medium, confirmed)
"""
import os
import sys

project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

# 样本 DXF 路径 (由 data/sample/make_hvac_sample_dxf.py 生成)
SAMPLE_DXF = os.path.join(project_root, "data", "sample", "hvac_sample.dxf")
DEFAULT_JSON = os.path.join(project_root, "src", "rules", "rules", "default.json")

# 暖通数值标注 (按坐标), 与 DXF 坐标同框:
#   DUCT_STD (0,0)   超速风管: velocity_ms=12.0 (超上限 10.0) + 管径/风量占位
#   UNIT_STD (4,0)   室内装室外机: unit_type=outdoor + location_type=indoor
#   GRILLE_STD (2,2) 合规送风格栅: height_m=2.5 (在 [2.0, 4.0] 内)
_HVAC_ANNOTATIONS = {
    (0.0, 0.0): {"velocity_ms": 12.0, "diameter_mm": 100, "airflow_m3h": 500.0,
                 "duct_type": "supply"},
    (4.0, 0.0): {"unit_type": "outdoor", "cooling_kw": 3.5, "location_type": "indoor"},
    (2.0, 2.0): {"height_m": 2.5, "grille_type": "supply", "airflow_m3h": 300.0,
                 "room_type": "living"},
}


def _annotate(points: list[dict]) -> list[dict]:
    """给 reader 产出的点位 dict 按坐标补数值字段 (调用侧标注范式)。"""
    out = []
    for p in points:
        key = (float(p["x"]), float(p["y"]))
        item = dict(p)
        item.update(_HVAC_ANNOTATIONS.get(key, {}))
        out.append(item)
    return out


def _run() -> tuple[list, list]:
    """跑全链路, 返回 (elements, violations)。"""
    from src.agents.src.tools.cad_tools import DXFReader
    from src.agents.src.tools.hvac_extractor import extract_hvac_points
    from src.rules.src.engine import RuleEngine
    from src.rules.src.dsl import DslRuleProvider

    reader = DXFReader(SAMPLE_DXF)
    assert reader.open(), f"样本 DXF 打开失败: {SAMPLE_DXF}"
    points = reader.get_hvac_points()
    assert len(points) == 3, f"样本应 3 个点位, 实际 {len(points)}: {points}"

    annotated = _annotate(points)
    elems = extract_hvac_points(annotated)

    engine = RuleEngine()
    DslRuleProvider(DEFAULT_JSON).upsert_into(engine)
    violations = engine.check(elems)
    return elems, violations


def test_sample_dxf_exists():
    """样本 DWG 必须已生成 (先跑 data/sample/make_hvac_sample_dxf.py)。"""
    assert os.path.isfile(SAMPLE_DXF), f"缺样本 {SAMPLE_DXF}"


def _by_kind(elems, kind: str) -> list:
    """按元素类型过滤 (HvacDuct/HvacUnit/HvacGrille 各字段不同, 不能跨类型访问)。"""
    from src.rules.src.hvac import HvacDuct, HvacUnit, HvacGrille
    cls = {"duct": HvacDuct, "unit": HvacUnit, "grille": HvacGrille}[kind]
    return [e for e in elems if isinstance(e, cls)]


def test_e2e_overspeed_duct_hits_velocity_rule():
    """超速风管 (velocity_ms=12.0 > 上限 10.0) 命中 hvac-duct-velocity-range, 且命中点指向该风管。"""
    elems, violations = _run()
    fast = [e for e in _by_kind(elems, "duct") if e.velocity_ms == 12.0]
    assert len(fast) == 1, f"应恰 1 根超速风管, 实际 {[e.id for e in fast]}"
    hits = [v for v in violations if v.rule_id == "hvac-duct-velocity-range"]
    assert len(hits) == 1, f"风速违规应恰 1 条, 实际 {len(hits)}: {[v.element_id for v in hits]}"
    assert hits[0].element_id == fast[0].id, \
        f"风速违规应指向超速风管 {fast[0].id}, 实际 {hits[0].element_id}"


def test_e2e_indoor_outdoor_unit_hits_placement_rule():
    """室内装室外机 (unit_type=outdoor + location_type=indoor) 命中 hvac-unit-outdoor-placement。"""
    elems, violations = _run()
    indoor = [e for e in _by_kind(elems, "unit")
              if e.unit_type == "outdoor" and e.location_type == "indoor"]
    assert len(indoor) == 1, f"应恰 1 台室内装室外机, 实际 {[e.id for e in indoor]}"
    hits = [v for v in violations if v.rule_id == "hvac-unit-outdoor-placement"]
    assert len(hits) == 1, f"室外机位置违规应恰 1 条, 实际 {len(hits)}: {[v.element_id for v in hits]}"
    assert hits[0].element_id == indoor[0].id, \
        f"位置违规应指向室内室外机 {indoor[0].id}, 实际 {hits[0].element_id}"


def test_e2e_compliant_grille_passes():
    """合规送风格栅 (height_m=2.5, 在 [2.0, 4.0] 区间内) 不误报。"""
    elems, violations = _run()
    grille = [e for e in _by_kind(elems, "grille") if e.height_m == 2.5]
    assert len(grille) == 1, f"应恰 1 个送风格栅, 实际 {[e.id for e in grille]}"
    assert all(v.element_id != grille[0].id
               for v in violations if v.rule_id == "hvac-grille-height-range"), \
        f"合规格栅 {grille[0].id} (2.5m) 不应命中风口高度规则"


def test_e2e_no_extraneous_hvac_hits():
    """全链路暖通违规集合应恰好 = {超速风管, 室内室外机} 两个元素, 无多余误报。"""
    elems, violations = _run()
    bad_ids = {v.element_id for v in violations if v.rule_id.startswith("hvac-")}
    expected = {
        next(e.id for e in _by_kind(elems, "duct") if e.velocity_ms == 12.0),
        next(e.id for e in _by_kind(elems, "unit")
             if e.unit_type == "outdoor" and e.location_type == "indoor"),
    }
    assert bad_ids == expected, \
        f"暖通违规集合不符: 实际 {bad_ids}, 预期 {expected}"


if __name__ == "__main__":
    test_sample_dxf_exists()
    test_e2e_overspeed_duct_hits_velocity_rule()
    test_e2e_indoor_outdoor_unit_hits_placement_rule()
    test_e2e_compliant_grille_passes()
    test_e2e_no_extraneous_hvac_hits()
    print("\nHVAC E2E tests passed!")

"""
快速冒烟验证 — 小改动后秒级确认核心没被改坏 (不用等全量 pytest + Git Bash fork 抖)。

定位: 日常高频验证用。全量 pytest (122 用例) 只在 commit 前 / CI 跑;
本脚本挑出「改坏了立刻炸」的核心不变量, 避开 subprocess (test_direct_run)
和 ezdxf 文件 IO 两个最慢点, 秒级出结果。

覆盖 (都是这几轮沉淀的架构不变量, 改崩一个就说明碰了红线):
- 硬编码规则类 @register_rule 注册正常 + get_engine 非空
- DSL 受限 eval 白名单 (危险调用被拒) — 信任边界
- DSL 缺属性/缺文案 护栏 (不崩校验链)
- _ensure_dsl_rules_loaded dsl_only 判据 (硬编码类重名不被 DSL 顶替)
- rule_check_node 分发表 plumbing/electrical 端到端命中

用法: python scripts/smoke_test.py   (无参数, 直接跑)
"""
import os
import sys
import time

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

_failures = []


def check(name, cond, detail=""):
    mark = "ok" if cond else "FAIL"
    print(f"  [{mark}] {name}" + (f"  — {detail}" if (detail and not cond) else ""))
    if not cond:
        _failures.append(name)


def main():
    t0 = time.time()
    print("smoke_test: 核心不变量秒级验证 (全量 pytest 仅 commit 前跑)")

    # 1. 硬编码规则类注册 + 引擎非空 (import 全部规则模块, 触发 @register_rule)
    import src.rules.src.residential.doors
    import src.rules.src.residential.windows
    import src.rules.src.residential.stairs
    import src.rules.src.residential.rooms
    import src.rules.src.residential.areas
    import src.rules.src.residential.corridors
    import src.rules.src.residential.daylight
    import src.rules.src.fire_safety.exits
    import src.rules.src.fire_safety.corridors
    import src.rules.src.accessibility.entrances
    import src.rules.src.accessibility.ramps
    from src.rules.src.engine import get_engine, RuleEngine
    eng = get_engine()
    n = len(eng.list_rules())
    check("硬编码规则类注册 (get_engine 非空)", n >= 25, f"只有 {n} 条")

    # 2. DSL 受限 eval 白名单: 危险调用必须被拒 (信任边界)
    import json, tempfile
    from src.rules.src.dsl import load_dsl_rules
    from src.rules.src.residential.stairs import Stair

    def _load_rule(pred):
        payload = {"rules": [{
            "rule_id": "smoke-x", "name": "x", "code_ref": "T", "severity": "warning",
            "element_types": ["Stair"], "predicate": pred, "enabled": True,
        }]}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(payload, f)
            return f.name
    for bad in ['__import__("os").system("x")', "getattr(element, 'x')", "open('f')"]:
        try:
            load_dsl_rules(_load_rule(bad))
            check(f"eval 白名单拒绝 {bad!r}", False, "该危险调用未被拒")
        except ValueError:
            check(f"eval 白名单拒绝 {bad!r}", True)

    # 3. DSL 护栏: predicate 引用不存在属性 → 降级不崩
    rule = load_dsl_rules(_load_rule("element.nonexistent_attr_m > 1"))[0]
    try:
        r = rule.check(Stair(id="s", width_m=1.2, riser_height_m=0.17))
        check("DSL 缺属性护栏 (不崩, 降级)", r.passed, "属性缺失未降级")
    except AttributeError:
        check("DSL 缺属性护栏 (不崩, 降级)", False, "AttributeError 未兜住")

    # 4. dsl_only 判据: 硬编码类重名不被 DSL 顶替
    from src.rules.src.dsl import ParametricRule
    from src.rules.src.residential.daylight import BedroomMinWindowArea
    from src.agents.src.nodes import cad_rule_export as cre
    eng2 = RuleEngine()
    eng2.upsert(BedroomMinWindowArea())
    cre._ensure_dsl_rules_loaded(eng2)
    by_id = {r.rule_id: r for r in eng2.list_rules()}
    check("dsl_only 判据 (plumbing 进引擎)", "plumbing-waste-pipe-min-diameter" in by_id)
    check("硬编码类不被 DSL 顶替",
          "residential-bedroom-window-area" not in by_id
          or not isinstance(by_id["residential-bedroom-window-area"], ParametricRule))

    # 5. rule_check_node 端到端: plumbing + electrical + hvac 命中
    from src.agents.src.nodes.cad_rule_export import rule_check_node
    out = rule_check_node({"raw_data": {
        "zones": [], "doors": [], "windows": [],
        "pipes": [{"id": "p", "pipe_type": "waste", "diameter_mm": 40, "slope": 2.0}],
        "outlets": [{"id": "o", "height_m": 2.5, "room_type": "kitchen", "has_earthing": False}],
        "switches": [],
        "hvac_ducts": [{"id": "hd", "duct_type": "supply", "diameter_mm": 100,
                        "airflow_m3h": 500.0, "velocity_ms": 12.0}],
        "hvac_units": [{"id": "hu", "unit_type": "outdoor", "cooling_kw": 3.5,
                        "location_type": "indoor"}],
        "hvac_grilles": [{"id": "hg", "grille_type": "supply", "height_m": 1.0}],
        "structural_beams": [{"id": "sb", "beam_type": "main", "width_mm": 300,
                              "depth_mm": 240}],
        "structural_columns": [{"id": "sc", "column_type": "frame", "section_mm": 250}],
    }})
    ids = {v["rule_id"] for v in out["rule_violations"]}
    check("主链路 plumbing 命中", "plumbing-waste-pipe-min-diameter" in ids)
    check("主链路 electrical 命中",
          "electrical-outlet-height-range" in ids and "electrical-outlet-earthing-required" in ids)
    check("主链路 hvac 命中",
          "hvac-duct-velocity-range" in ids
          and "hvac-unit-outdoor-placement" in ids
          and "hvac-grille-height-range" in ids)
    check("主链路 structural 命中",
          "structural-beam-width-depth-ratio" in ids
          and "structural-column-min-section" in ids)

    print(f"\nsmoke_test: {len(_failures)==0 and '全过' or f'{len(_failures)} 项 FAIL'} "
          f"(用时 {time.time()-t0:.2f}s)")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())

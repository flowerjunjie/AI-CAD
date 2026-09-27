"""
Phase 2 能力演示 — 批量校验 / 编辑器校验 / 规则清单 diff 三块最小闭环

直接跑:  python scripts/demo_phase2.py
输出三块能力的真实结果（不是测试断言, 是可看的演示）。
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.rules.src.engine import get_engine, ViolationSeverity
from src.rules.src.dsl import DslRuleProvider, load_dsl_rules, validate_and_load_dsl_rules
from src.rules.src.batch_check import run_batch_check
from src.rules.src.editor_validate import validate_dsl_json
from src.rules.src.diff import diff_rule_lists, diff_violations
from src.rules.src.residential.doors import Door
from src.rules.src.residential.stairs import Stair
from src.rules.src.fire_safety.corridors import Corridor

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_JSON = ROOT / "src" / "rules" / "rules" / "default.json"


def _banner(title: str) -> None:
    print(f"\n{'='*70}\n  {title}\n{'='*70}")


def demo_batch_check() -> None:
    _banner("① 批量校验 — 一批元素 × 全部启用规则, 按严重级/规则聚合")
    # 单一类型元素混批 (贴近真实调用方: 每个元素类型各自调一次)
    elements = [
        Door(id="d1", width_m=0.8, room_type="entrance", location=(0, 0)),
        Door(id="d2", width_m=1.1, room_type="entrance", location=(1, 0)),
        Stair(id="s1", width_m=1.2, riser_height_m=0.20),
        Stair(id="s2", width_m=1.2, riser_height_m=0.15),
        Corridor(id="c1", name="主走廊", width_m=1.2, length_m=10.0),
    ]
    report = run_batch_check(elements)  # engine=None → 全局引擎(34类 + DSL upsert 全集)
    print(f"  元素数: {len(elements)}")
    print(f"  违规总数: {report.total}")
    print(f"  按严重级: {report.by_severity}")
    print(f"  按规则: {report.by_rule}")
    for v in report.violations:
        print(f"    [{v.severity.value}] {v.rule_id} @ {v.element_id}: {v.description}")

def demo_editor_validate() -> None:
    _banner("② 编辑器校验 — 设计器改完 JSON, 改错立刻知道")
    # 合法 default.json
    errors = validate_dsl_json(DEFAULT_JSON)
    print(f"  default.json 校验: {len(errors)} 错误 (0=合法, 可安全 load)")
    rules, errs = validate_and_load_dsl_rules(DEFAULT_JSON)
    print(f"  validate_and_load → {len(rules)} 条规则, {len(errs)} 条错误")

    # 故意改坏一条 (threshold + predicate 白名单外标识符)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        f.write(json.dumps({
            "rules": [
                {"rule_id": "dsl-stair-riser", "element_types": ["Stair", "stair"],
                 "predicate": "element.riser_height_m > max_riser_m",
                 "param_defaults": {"max_riser_m": 0.175}},
                {"rule_id": "bad-demo", "element_types": ["Door", "door"],
                 "severity": "fatal",
                 "predicate": "element.width_m < open('x')"},  # open 不在白名单
            ]
        }, ensure_ascii=False))
        tmp = f.name
    bad_errors = validate_dsl_json(tmp)
    print(f"  改坏 JSON 校验: {len(bad_errors)} 错误")
    for e in bad_errors:
        print(f"    [{e.rule_index}] {e.path}: {e.message}")


def demo_rule_list_diff() -> None:
    _banner("③ 规则清单 diff — 改 default.json 前后, 看动了哪些规则")
    # 基线 = 当前 default.json
    old = load_dsl_rules(DEFAULT_JSON)

    # 「设计师改完」= 阈值放宽 + 删一条 + 新增一条
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
        rules = json.loads(DEFAULT_JSON.read_text(encoding="utf-8"))["rules"]
        for r in rules:
            if r["rule_id"] == "dsl-stair-riser":
                r["param_defaults"]["max_riser_m"] = 0.18  # 阈值 0.175 → 0.18
        keep = [r for r in rules if r["rule_id"] != "dsl-corridor-escape-width"]  # 删一条
        keep.append({  # 新增一条
            "rule_id": "demo-new-rule", "name": "演示新增", "severity": "info",
            "element_types": ["Corridor", "corridor"],
            "predicate": "element.width_m > 5.0",
            "param_defaults": {}, "enabled": True, "dsl_only": True,
        })
        f.write(json.dumps({"rules": keep}, ensure_ascii=False))
        tmp = f.name
    new = load_dsl_rules(tmp)
    d = diff_rule_lists(old, new)
    print(f"  added:   {[r['rule_id'] for r in d['added']]}")
    print(f"  removed: {[r['rule_id'] for r in d['removed']]}")
    for c in d["changed"]:
        print(f"  changed: {c['rule_id']} → {c['fields']}")


if __name__ == "__main__":
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    # 让批量校验看到「34 类 + DSL 全集」: 先触发引擎构建 + DSL upsert
    _ = get_engine()
    DslRuleProvider(DEFAULT_JSON).upsert_into(get_engine())
    demo_batch_check()
    demo_editor_validate()
    demo_rule_list_diff()
    print("\nPhase 2 三块能力演示完成。")

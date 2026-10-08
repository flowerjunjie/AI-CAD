"""
AI-CAD GUI FastAPI 桥 — F 碰撞/冲突域段 (M4 跨专业碰撞 + M5 两稿改动冲突)。

从 bridge.py 拆出的自包含子模块 (bridge 超 500 红线, 结构性拆分)。
用 APIRouter 承载本域段 /api/clash + /api/conflict + /api/dwg-marker-verify,
bridge.py 顶层 include_router 挂载 (app 注册方式不变, 端点路径 0 改动)。

跨段依赖已解耦: _load_sample_raw / _CLASH_SAMPLE_KEYS 走共享层 bridge_common
(B 段 api_rules_batch_verify 也 import 它, 故上提), 本段不再定义、纯 import。
端点懒 import clash/conflict 工具库, module 收集期不触发重依赖。
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, HTTPException

from src.gui.bridge_common import _load_sample_raw
from src.gui.bridge import ROOT  # 项目根定位 (本段 dwg-marker-verify 出图兜底用)

router = APIRouter()


@router.get("/api/dwg-marker-verify")
def api_dwg_marker_verify(sample: str = "residential_100sqm.json") -> dict:
    """出图警示标记计数对账 (机制层自主子集): 读回真实 DWG 里 CLASH/DUP 圈实数,
    与 detect_clashes/detect_duplicate_elements 的期望数对账, 防出图侧失步
    (清单说有 N 碰撞/DUP 但图上画了 M 个 → 设计师看到圈数对不上无从溯源)。

    诚实边界: 只数「出图侧画没画够/多画」(机制量), **不判**「画的位置/业务对不对」
    (那是 M2 制图规范)。复用 render_sample_png 出图 + 同源 detect_* 期望数, 不重造。
    出图不可用 → 诚实降级 (不造假 0 圈全过)。返回 {sample, ok, clash_drawn,
    clash_expected, dup_drawn, dup_expected, issues, note}。"""
    from src.agents.src.tools.cad_tools import verify_dwg_markers
    try:
        from src.agents.src.tools.clash_detection import detect_clashes
        from src.agents.src.tools.conflict_detection import detect_duplicate_elements
        from src.agents.src.graph import run_agent_demo
        raw = _load_sample_raw(sample)
        # 期望数: 与出图侧同一判据 (detect_clashes / 同稿自比 detect_duplicate_elements)
        exp_clash = len(detect_clashes(raw, tolerance_m=0.15))
        exp_dup = len(detect_duplicate_elements(raw, raw))
        # 起真实 sample 出 DWG (复用出图函数, 拿到 final_dwg_path)
        result = run_agent_demo(sample_path=_sample_path(sample),
                                auto_mode=True, inject_sample_structure=True)
        dwg_path = result.get("final_dwg_path") or os.path.join(
            ROOT, "output", "ai_cad_output.dwg")
    except Exception as e:
        return {"sample": sample, "ok": False, "clash_drawn": 0, "clash_expected": 0,
                "dup_drawn": 0, "dup_expected": 0, "issues": [f"出图不可用: {e}"],
                "note": "DWG 标记对账降级 (出图链路异常), 不造假全过"}
    res = verify_dwg_markers(dwg_path, exp_clash, exp_dup)
    res["sample"] = sample
    res["note"] = ("出图警示圈实数 vs 期望数对账 (机制层, 不判画得对不对); "
                   "CLASH=碰撞圈 DUP=重复圈, 出图侧漏画/多画在此失步可见")
    return res


@router.get("/api/clash")
def api_clash(sample: str = "residential_100sqm.json",
              tolerance_m: Optional[float] = None) -> dict:
    """M4 跨专业碰撞: 读 sample 顶层元素数据调 detect_clashes。

    容差取值通道 (M4 ← default.json 回填, 同 M1 数值范式):
      ① query tolerance_m 显式传 → 来源 "param"
      ② default.json 的 clash-tolerance-range 规则 params.clash_tolerance_m
         → 来源 "dsl" (专家改 JSON 即生效, 零代码)
      ③ 几何默认 0.15m → 来源 "default"
    返回 {sample, tolerance_m, tolerance_source, clashes: [...], count}。
    无碰撞 → count=0 空列表 (诚实, 不造假)。"""
    from src.agents.src.tools.clash_detection import (  # 懒
        detect_clashes, resolve_clash_tolerance, verify_clashes)

    dsl_rule = None
    try:
        from src.agents.src.nodes.cad_rule_export import _dsl_rules_path
        from src.rules.src.dsl import load_dsl_rules
        for r in load_dsl_rules(_dsl_rules_path()):
            if r.rule_id == "clash-tolerance-range":
                dsl_rule = r
                break
    except Exception:
        dsl_rule = None  # JSON 缺/损坏 → 降级几何默认, 不崩
    tol, tol_src = resolve_clash_tolerance(
        default_m=0.15, dsl_rule=dsl_rule,
        params={"clash_tolerance_m": tolerance_m} if tolerance_m else None,
    )
    raw = _load_sample_raw(sample)
    clashes = detect_clashes(raw, tolerance_m=tol)
    # 机制层对账: 碰撞结果与 raw 源是否自洽 (a_id!=b_id / kind 合法 / id 在 raw,
    # 出图侧反查才不兜底原点假圈)。自产必一致; 透出为诊断, 失步不静默穿透出图。
    check = verify_clashes(raw, clashes)
    return {"sample": sample, "tolerance_m": tol, "tolerance_source": tol_src,
            "clashes": clashes, "count": len(clashes),
            "clashes_consistent": check["valid"],
            "clashes_issues": check["issues"]}


@router.get("/api/conflict")
def api_conflict(sample_a: str = "residential_100sqm.json",
                 sample_b: str = "residential_100sqm.json") -> dict:
    """M5 两稿改动冲突: 两份 sample 顶层数据调 detect_conflicts + summarize_conflicts。

    默认开启几何等价类维度 (check_duplicates=True): 同坐标不同 id = 疑似重复元素
    (kind='duplicate', 琥珀色 UI 标注), 捕捉设计师两稿「画了同位置但用了不同 id」
    的常见疏漏。传 check_duplicates=False 可关闭 (老调用方零改动, 向后兼容)。

    返回 {sample_a, sample_b, count, by_category, conflicts, summary}。
    summary 含 value_conflicts/added/removed/duplicates 四维度计数。
    同稿自比 → count=0 空列表 (诚实, 不造假)。"""
    from src.agents.src.tools.conflict_detection import (  # 懒
        detect_conflicts, summarize_conflicts, verify_summary)

    raw_a = _load_sample_raw(sample_a)
    raw_b = _load_sample_raw(sample_b)
    conflicts = detect_conflicts(raw_a, raw_b, check_duplicates=True)
    summary = summarize_conflicts(conflicts)
    # 机制层对账: 汇总计数 vs 冲突列表是否自洽 (summarize 自产必一致;
    # 透出为诊断, 一旦未来上游改动导致失步, 端点如实标 out_of_sync, 不静默穿透 UI)
    check = verify_summary(summary, conflicts)
    return {
        "sample_a": sample_a,
        "sample_b": sample_b,
        "count": len(conflicts),
        "by_category": summary["by_category"],
        "conflicts": conflicts,
        "summary": summary,
        "summary_consistent": check["consistent"],
        "summary_issues": check["issues"],
    }


# 内部符号: _sample_path 供本段 dwg-marker-verify 出图兜底用, 从 bridge 顶层复用
# (它是 C 段的项目根定位薄封装, 非端点, 跨段共享合理)。
from src.gui.bridge import _sample_path  # noqa: E402

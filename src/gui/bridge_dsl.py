"""
AI-CAD GUI FastAPI 桥 — B2+B3 规则 DSL 域段 (编辑 + 写回 default.json)。

从 bridge.py 拆出的子模块 (bridge 超 500 红线, 结构性拆分)。用 APIRouter 承载
/api/rules/dsl + /api/rules/validate + /api/rules/dsl/apply + /api/rules/backfill,
bridge.py 顶层 include_router 挂载 (app 注册方式不变, 端点路径 0 改动)。
跨段依赖: _project_root (bridge 顶层, _dsl_default_path 引用) 顶层 import;
_load_sample_raw (batch-verify 若在此段) 走 bridge_common。
写盘前备份可回滚 + fail-fast 重载兜底 (红线一不留坏盘)。
"""
from __future__ import annotations

import json
import os
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

class DslRulesValidateReq(BaseModel):
    """POST /api/rules/validate 入参: 整份 DSL 规则 JSON (顶层须含 'rules' 数组)。"""

    rules: list
    # 可选: 直接传 {'rules': [...]} 也可 — 前端两种都收, 以 rules 为准


def _dsl_default_path() -> str:
    from src.gui.bridge import _project_root  # 惰性: 规避顶层循环 import
    return os.path.join(_project_root(), "src", "rules", "rules", "default.json")


@router.get("/api/rules/dsl")
def api_rules_dsl() -> dict:
    """default.json 原文 (DSL 规则全字段: predicate/params/param_defaults/enabled...)。
    规则编辑器面板的数据源。文件不可读 → 404 + 诚实 detail, 不造假。"""
    p = _dsl_default_path()
    if not os.path.exists(p):
        raise HTTPException(404, f"DSL 规则文件不存在: {p}")
    with open(p, encoding="utf-8") as fh:
        return json.load(fh)


@router.post("/api/rules/validate")
def api_rules_validate(req: DslRulesValidateReq) -> dict:
    """校验设计器改完的 DSL 规则 JSON (schema + predicate 白名单)。

    复用 editor_validate.validate_dsl_json 的判据 (与 DslRuleProvider.load
    fail-fast 严格一致): validator 说合法 → load 必不炸。
    响应: {valid, error_count, errors: [{path, message, rule_index, rule_id?}]}
      - 文件级错误 (rule_index == -1): path 形如 "<top>" — 非 DSL 文档/JSON 语法错
      - 规则级错误: path 形如 "rules[2].predicate", 带 rule_id 便于前端定位
    """
    import json
    import tempfile
    from dataclasses import asdict
    from src.rules.src.editor_validate import validate_dsl_json

    payload = {"rules": req.rules}
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", suffix=".json", delete=False
    ) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        tmp = fh.name
    try:
        errors = validate_dsl_json(tmp)
        err_dicts = [asdict(e) for e in errors]
    finally:
        os.unlink(tmp)

    # 给规则级错误补 rule_id (前端按 rule_id 定位高亮, 不靠 index 错位)
    try:
        rules_list = req.rules if isinstance(req.rules, list) else []
        for ed in err_dicts:
            if ed["rule_index"] >= 0 and ed["rule_index"] < len(rules_list):
                r = rules_list[ed["rule_index"]]
                if isinstance(r, dict):
                    ed["rule_id"] = r.get("rule_id") or r.get("id") or ""
            else:
                ed.setdefault("rule_id", "")
    except Exception:
        pass  # 补 rule_id 失败不影响 errors 主体

    return {
        "valid": len(errors) == 0,
        "error_count": len(errors),
        "errors": err_dicts,
    }


# ─── B3 规则 DSL 写回域段: 设计器「应用」落盘 default.json (Phase 2 闭环) ───
# 人工确认闸: 先 validate (与 /api/rules/validate 同判据), 不合法 4xx 拒写;
# confirm=False → 只回 diff 预览不落盘; confirm=True → 备份 + 写盘 + fail-fast 重载兜底,
# 写后 DslRuleProvider.load() 仍会炸则回滚到备份。守 34 类零改动 (只写 DSL 数据文件)。

import shutil
from datetime import datetime


# ─── 备份轮转 (机制层, 两类写盘端点共用 — 一个模式埋两处, 统一生命周期) ───
# apply/backfill 每次写盘前都 copy 出 default.json.bak.<ts>, 但**从不删旧备份**
# (apply 仅在写盘失败分支 unlink, 写成功则备份永久留下; backfill 连失败分支都没清)。
# 全仓无 .bak. 清理逻辑 — 每回填/应用一次磁盘就多一个永不清理的文件。
# 统一抽一个轮转: 保留最近 keep 个, 按文件名时间戳排序删旧的。
# 边界 (诚实): 备份是「可回滚」护栏, 轮转不是删光 — 保留最近 N 个 (默认 10),
# 防堆积的同时不破坏"不留坏盘"回滚能力。纯函数, 不碰 default.json 本体。

_DSL_BACKUP_KEEP = 10


def _prune_dsl_backups(main_path: str, keep: int = _DSL_BACKUP_KEEP) -> list[str]:
    """清理 main_path 的旧备份 (default.json.bak.<ts>), 保留最近 keep 个。

    按备份文件名中的时间戳 (mtime 兜底) 从新到旧排序, 只删超出 keep 的旧文件。
    返回实际删除的备份路径列表 (无旧备份可删 → [])。畸形 main_path/无备份不崩。
    """
    # 备份文件名范式: <main_path>.bak.<ts> (见 apply/backfill 的 f"{p}.bak.{ts}"),
    # 前缀 = 主文件完整路径 + ".bak." — 不拆 splitext (那会把 default.json 拆成
    # default 漏掉 .json, 前缀匹配不到真备份 → 轮转变 no-op 静默失效)。
    prefix = f"{main_path}.bak."
    bak_dir = os.path.dirname(main_path)
    try:
        cands = [os.path.join(bak_dir, n) for n in os.listdir(bak_dir)
                 if n.startswith(os.path.basename(prefix))]
    except OSError:
        return []
    cands = [c for c in cands if os.path.isfile(c)]
    if len(cands) <= keep:
        return []
    # 新→旧排序: 优先按文件名时间戳 (default.json.bak.YYYYMMDDHHMMSS), mtime 兜底
    cands.sort(key=lambda c: (os.path.basename(c), os.path.getmtime(c)), reverse=True)
    to_remove = cands[keep:]
    removed: list[str] = []
    for c in to_remove:
        try:
            os.unlink(c)
            removed.append(c)
        except OSError:
            pass  # 单文件删失败不影响其余, 不静默吞 — 记在返回里 (由调用方决策是否报)
    return removed


class DslRulesApplyReq(BaseModel):
    """POST /api/rules/dsl/apply 入参: 整份 DSL 规则 JSON + 人工确认开关。"""

    rules: list
    confirm: bool = False


def _diff_rules(old_rules: list, new_rules: list) -> dict:
    """对比现 default.json 的 rules 与入参 rules, 出「改了/新增/删」三类预览。

    以 rule_id 为键; old/new 只收 list (端点已保证), 字段级差异直接整条比 —
    编辑器可改的字段 (params/enabled/severity/predicate) 任一动到就记 changed。
    """
    old_map = {r.get("rule_id"): r for r in old_rules if isinstance(r, dict)}
    new_ids = {r.get("rule_id") for r in new_rules if isinstance(r, dict)}
    old_ids = set(old_map.keys())

    changed = []
    for r in new_rules:
        if not isinstance(r, dict):
            continue
        rid = r.get("rule_id")
        if rid in old_map and r != old_map[rid]:
            changed.append(rid)
    added = sorted(rid for rid in (new_ids - old_ids) if rid)
    removed = sorted(rid for rid in (old_ids - new_ids) if rid)
    return {"changed": sorted(changed), "added": added, "removed": removed}


def _validate_rules_raise(rules: list) -> None:
    """跑 editor_validate (同 /api/rules/validate 判据); 有错 422 拒写, 不落盘。"""
    import tempfile
    from dataclasses import asdict
    from src.rules.src.editor_validate import validate_dsl_json

    payload = {"rules": rules}
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", suffix=".json", delete=False) as fh:
        json.dump(payload, fh, ensure_ascii=False)
        tmp = fh.name
    try:
        errors = validate_dsl_json(tmp)
    finally:
        os.unlink(tmp)
    if errors:
        raise HTTPException(
            422,
            detail={"reason": "validation_failed", "error_count": len(errors),
                    "errors": [asdict(e) for e in errors]},
        )


@router.post("/api/rules/dsl/apply")
def api_rules_dsl_apply(req: DslRulesApplyReq) -> dict:
    """设计器「应用」落盘 default.json — 带人工确认闸 + 备份回滚。

    流程 (写盘慎重, 每步都可拒):
      1. 先 validate: 不合法 → 422 拒写 (绝不动 default.json)。
      2. confirm=False → 校验通过但**不落盘**, 返回 {status:'pending_confirm', diff}
         让设计器先看改了/新增/删哪些规则再决定。
      3. confirm=True → 备份原文件 (default.json.bak.<ts>) 写盘; 写后用
         DslRuleProvider.load() fail-fast 兜底, 重载失败 → 用备份回滚 + 500。
    响应:
      pending_confirm: {status, diff, valid:True, error_count:0}
      applied:         {status:'applied', diff, backup, applied_rule_count}
    """
    p = _dsl_default_path()
    if not os.path.exists(p):
        raise HTTPException(404, f"DSL 规则文件不存在: {p}")

    # ── 1. 先 validate (不合法 422 拒写, 绝不动盘) ──
    _validate_rules_raise(req.rules)

    # ── 读原文件出 diff ──
    try:
        with open(p, encoding="utf-8") as fh:
            old_data = json.load(fh)
    except (OSError, json.JSONDecodeError) as e:
        raise HTTPException(500, f"原 default.json 不可读, 拒绝写回: {e}")
    old_rules = old_data.get("rules", []) if isinstance(old_data, dict) else []
    diff = _diff_rules(old_rules, req.rules)

    # 机制层自洽诊断 (仿 verify_clashes.clashes_consistent 范式): 三桶 diff
    # (added/removed/changed) 自身是否自洽 — 防上游 diff 逻辑改动后「同一 rule_id
    # 既进 added 又进 changed」的静默失步穿透进落盘预览。给 verify_diff_buckets
    # 接上第一个真实生产消费方 (此前仅测试引用, 孤儿纯函数)。失步不静默进预览。
    from src.rules.src.diff import verify_diff_buckets
    diff_check = verify_diff_buckets(diff, key_of=lambda rid: rid)

    # ── 2. 人工确认闸: 未确认 → 只回 diff 预览, 不落盘 ──
    if not req.confirm:
        return {
            "status": "pending_confirm",
            "valid": True,
            "error_count": 0,
            "diff": diff,
            "diff_consistent": diff_check["ok"],
            "diff_issues": diff_check["issues"],
            "message": "校验通过, 待人工确认。请带 confirm=true 再调本端点落盘。",
        }

    # ── 3. 备份 → 写盘 → fail-fast 重载兜底, 失败回滚 ──
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = f"{p}.bak.{ts}"
    shutil.copyfile(p, backup)  # 备份先成, 写盘才可回滚

    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"rules": req.rules}, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    except OSError as e:
        # 写盘本身失败 → 清备份 (原文件未动), 诚实报错
        if os.path.exists(backup):
            os.unlink(backup)
        raise HTTPException(500, f"default.json 写盘失败: {e}")

    # fail-fast 兜底: 写后必能重载, 否则回滚 (红线一: 不留坏盘)
    from src.rules.src.dsl import DslRuleProvider
    try:
        DslRuleProvider(p).load()
    except Exception as e:
        try:
            shutil.copyfile(backup, p)  # 回滚到备份
        except OSError as rb:
            raise HTTPException(500, f"写盘后重载失败且回滚也失败: load={e} rollback={rb}")
        raise HTTPException(500, f"default.json 写盘后 DslRuleProvider 重载失败, 已回滚: {e}")

    # 写成功 → 轮转旧备份 (保留最近 N 个, 防 .bak. 无界堆积; 刚写的 backup 在保留窗口内)
    _prune_dsl_backups(p)
    return {
        "status": "applied",
        "valid": True,
        "error_count": 0,
        "diff": diff,
        "backup": backup,
        "applied_rule_count": len(req.rules),
    }


class RuleBackfillReq(BaseModel):
    """POST /api/rules/backfill 入参: 单规则轻量回填 (M1 数值回填 GUI 入口)。

    只改指定 rule_id 的 confirmed/confidence/confirm_note/param_defaults,
    比 DSL apply (全量 rules 重写) 轻 — 专家在面板里点「回填」即生效, 零代码。
    诚实边界 (不虚标): 端点只写盘 + fail-fast 重载, 不冒称已点亮 (点亮是前端
    按 confirmed 判定); confidence 须业务侧如实填 (几何默认=medium, 专家背书=high)。"""

    rule_id: str
    confirmed: Optional[bool] = None
    confidence: Optional[str] = None  # low / medium / high
    confirm_note: Optional[str] = None
    params: Optional[dict] = None  # 回填 param_defaults (数值/字符串/布尔, JSON 可序列化)


@router.post("/api/rules/backfill")
def api_rules_backfill(req: RuleBackfillReq) -> dict:
    """M1 数值回填 (GUI 入口, 单规则): 写 default.json 一条规则 + 备份 + fail-fast。

    流程 (照 /api/rules/dsl/apply 写盘范式, 单规则粒度):
      1. 找不到 rule_id → 404 诚实 (列可用规则, 不误写)。
      2. 备份 default.json.bak.<ts> → 写盘 (只改指定规则, 其余原样)。
      3. fail-fast: 写后 DslRuleProvider.load() 重载, 失败 → 回滚 + 500 (不留坏盘)。
    响应: {status:'applied', rule_id, backup, confirmed, confidence,
           param_defaults, note} — note 明示「需跑 /api/rules 验证前端点亮」。"""
    p = _dsl_default_path()
    if not os.path.exists(p):
        raise HTTPException(404, f"DSL 规则文件不存在: {p}")
    with open(p, encoding="utf-8") as fh:
        data = json.load(fh)
    rule = next((r for r in data.get("rules", []) if r.get("rule_id") == req.rule_id), None)
    if rule is None:
        raise HTTPException(404, f"未找到规则 {req.rule_id}; 可用: "
                                  f"{[r.get('rule_id') for r in data.get('rules', [])]}")
    # confidence 白名单 (不虚标: 非法值拒绝写, 不静默降级)
    if req.confidence is not None and req.confidence not in ("low", "medium", "high"):
        raise HTTPException(422, f"confidence 须 low/medium/high, 实际 {req.confidence}")

    if req.confirmed is not None:
        rule["confirmed"] = req.confirmed
    if req.confidence is not None:
        rule["confidence"] = req.confidence
    if req.confirm_note is not None:
        rule["confirm_note"] = req.confirm_note
    if req.params:
        pd = rule.setdefault("param_defaults", {})
        for k, v in req.params.items():
            pd[k] = v
            if k in rule.get("params", {}):
                rule["params"][k] = v

    # 备份 → 写盘 → fail-fast 重载兜底 (红线一: 不留坏盘)
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    backup = f"{p}.bak.{ts}"
    shutil.copyfile(p, backup)
    try:
        with open(p, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        from src.rules.src.dsl import DslRuleProvider
        DslRuleProvider(p).load()  # fail-fast: 重载不炸
    except Exception as e:
        shutil.copyfile(backup, p)  # 回滚
        raise HTTPException(500, f"回填写盘后重载失败, 已回滚: {e}")

    # 写成功 → 轮转旧备份 (与 apply 同一套生命周期, 防 .bak. 无界堆积)
    _prune_dsl_backups(p)
    return {
        "status": "applied", "rule_id": req.rule_id, "backup": backup,
        "confirmed": rule.get("confirmed"), "confidence": rule.get("confidence"),
        "param_defaults": rule.get("param_defaults"),
        "note": "已写盘 — 跑 GET /api/rules 验证前端按 confirmed 点亮占位卡",
    }



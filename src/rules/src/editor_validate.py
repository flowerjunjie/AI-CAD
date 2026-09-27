"""
规则编辑器校验 — 设计器改完 default.json 先校验再 load

校验器与 DslRuleProvider.load() 的 fail-fast 判据严格一致：
validator 说合法 → load 必不抛错；validator 报的错 → load 会抛的同款。
不另造 schema 真源，复用 dsl._build_spec 的解析与 predicate 白名单逻辑。
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .dsl import _build_spec


@dataclass(frozen=True)
class DslJsonError:
    """单条 DSL JSON 校验错误（文件级 / 某条规则级 / 某字段级）。"""

    path: str          # 定位路径，如 "rules[2].predicate"
    message: str       # 人话描述
    rule_index: int    # -1 表示文件级错误（顶层 schema / JSON 语法）


def _validate_rule(raw: dict, index: int, errors: list[DslJsonError]) -> None:
    """校验单条规则；错误逐条 append，不短路（设计器要一次看全）。"""
    pfx = f"rules[{index}]"
    if not isinstance(raw, dict):
        errors.append(DslJsonError(f"{pfx}", "必须是对象", index))
        return
    rid = raw.get("rule_id") or raw.get("id", "")
    if not rid:
        errors.append(DslJsonError(f"{pfx}.rule_id", "缺少 rule_id", index))
    et = raw.get("element_types", ())
    if not et:
        # 空列表 = 门禁放行全部类型 (predicate 对任何元素生效) — 设计器误删
        # element_types 后规则看似在跑实则无差别命中, 必须显式拦下来。
        errors.append(DslJsonError(f"{pfx}.element_types", "element_types 不能为空（空=对所有类型放行）", index))
    elif not isinstance(et, list) or any(not isinstance(t, str) or not t for t in et):
        # _build_spec 对 element_types 只 tuple() 包一层不查形状:
        # 喂字符串会被字符拆分, 结果匹配不到任何类型 — 规则静默空转。这里兜住。
        errors.append(DslJsonError(f"{pfx}.element_types", "element_types 必须是字符串数组", index))
    sev = str(raw.get("severity", "error")).lower()
    if sev not in ("error", "warning", "info"):
        errors.append(DslJsonError(f"{pfx}.severity", f"severity 必须是 error/warning/info, 实际 {sev!r}", index))
    try:
        _build_spec(raw)  # 编译 predicate: 白名单外标识符 / func: 前缀在此 fail-fast
    except ValueError as e:
        errors.append(DslJsonError(f"{pfx}.predicate", str(e), index))


def validate_dsl_json(path: str | Path) -> list[DslJsonError]:
    """校验 DSL 规则 JSON：schema 结构 + 每条 predicate 白名单。

    返回全部错误（空列表 = 合法, 可安全 load）。设计器改完 JSON 先调它,
    有错立刻定位到「哪条规则哪个字段」, 不用等 load 时炸。
    """
    p = Path(path)
    errors: list[DslJsonError] = []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return [DslJsonError(str(p), f"文件不可读或 JSON 语法错: {e}", -1)]
    if not isinstance(data, dict) or "rules" not in data:
        return [DslJsonError(str(p), "顶层必须是 {'rules': [...]}", -1)]
    rules = data["rules"]
    if not isinstance(rules, list):
        return [DslJsonError(str(p), "'rules' 必须是数组", -1)]
    for i, raw in enumerate(rules):
        _validate_rule(raw, i, errors)
    return errors

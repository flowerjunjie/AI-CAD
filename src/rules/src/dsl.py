"""
规则引擎 DSL 化 — 外部数据定义规则阈值

与 @register_rule 增量共存（开放封闭：新能力不改现有 34 个规则类）。
外部 schema = src/rules/rules/default.json，字段：
    rule_id / name / code_ref / severity / element_types /
    predicate / params / param_defaults / description_template /
    suggested_fix_template / enabled

predicate 走受限 eval（白名单：element 属性 + params 键 + 字面量 +
比较 + and/or/not/in + len()），**不允许 func: 前缀调几何函数**
（几何留在 Python 侧）。params 键名与 len() 都可参与 predicate 求值。
"""
from __future__ import annotations

import ast
import json
import keyword
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .engine import BaseRule, RuleResult, RuleViolation, ViolationSeverity

# ─── 受限 eval 白名单 ─────────────────────────────────────────

class _SafeRenderMap(dict):
    """str.format_map 用的 mapping: 缺 key 渲染成 [缺失:xxx] 占位, 不 KeyError。"""

    def __init__(self, base: dict) -> None:
        super().__init__(base)

    def __missing__(self, key: str) -> str:
        return f"[缺失:{key}]"


_ALLOWED_NODES: tuple[type, ...] = (
    ast.Expression, ast.BoolOp, ast.And, ast.Or,
    ast.Compare, ast.Eq, ast.NotEq, ast.Lt, ast.LtE,
    ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.UnaryOp,
    ast.Not, ast.USub, ast.BinOp, ast.Add, ast.Sub,
    ast.Mult, ast.Div, ast.Mod,
    ast.Call,  # 仅允许 len() 一个白名单函数
    ast.Name, ast.Load, ast.Constant,
    ast.Tuple, ast.List, ast.Set, ast.Attribute,
)

_CALLABLE_WHITELIST: dict[str, Any] = {
    "len": len,
}


def _allowed_names(param_keys: set[str]) -> frozenset[str]:
    """predicate 里允许的标识符集合：
    element / 布尔常量 / 白名单可调用函数 / params 键。
    """
    base = {"element", "True", "False", "None", *keyword.kwlist, * _CALLABLE_WHITELIST.keys()}
    return frozenset(base | param_keys)


def _validate_predicate_ast(predicate: str, param_keys: set[str] = frozenset()) -> None:
    """predicate 必须通过白名单语法检查；func: 前缀一律拒绝。"""
    if predicate.strip().startswith("func:"):
        raise ValueError(f"predicate 不允许 func: 前缀调几何函数: {predicate!r}")
    allowed = _allowed_names(param_keys)
    tree = ast.parse(predicate, mode="eval")
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if node.id not in allowed:
                raise ValueError(f"predicate 白名单外标识符: {node.id!r}")
        elif isinstance(node, ast.Call):
            func = node.func
            if not isinstance(func, ast.Name) or func.id not in _CALLABLE_WHITELIST:
                raise ValueError(f"predicate 不允许调用函数: {ast.dump(node)}")
        elif isinstance(node, ast.Attribute):
            if node.attr.startswith("_"):
                raise ValueError(f"predicate 不允许访问下划线属性: {node.attr!r}")


def _compile_predicate(predicate: str, param_keys: set[str] = frozenset()) -> str:
    """编译 predicate 为受限 eval 可用的源码。"""
    _validate_predicate_ast(predicate, param_keys)
    return predicate


# ─── DSL 规则规范（不可变） ─────────────────────────────────────

@dataclass(frozen=True)
class DslRuleSpec:
    """单条 DSL 规则的不可变规格，从 JSON schema 解析而来。"""

    rule_id: str
    name: str
    code_ref: str
    severity: ViolationSeverity
    element_types: tuple[str, ...]
    predicate: str
    params: dict[str, Any] = field(default_factory=dict)
    param_defaults: dict[str, Any] = field(default_factory=dict)
    description_template: str = ""
    suggested_fix_template: str = ""
    enabled: bool = True
    # 纯 DSL 新增专业规则才置 True — 只有它会被主链路 upsert 进引擎;
    # 与 @register_rule 的 34 类重名的「参数覆盖」规则保持默认 False, 不顶替硬编码版
    # (守住 34 类零改动红线)。
    dsl_only: bool = False
    _compiled_predicate: str = ""

    def __post_init__(self) -> None:
        if not self.rule_id:
            raise ValueError("DSL 规则必须有 rule_id")
        # 编译时把当前已知 params 键 + param_defaults 键纳入白名单
        param_keys = set(self.params) | set(self.param_defaults)
        object.__setattr__(
            self, "_compiled_predicate", _compile_predicate(self.predicate, param_keys)
        )


def _build_spec(raw: dict[str, Any]) -> DslRuleSpec:
    sev_raw = raw.get("severity", "error").lower()
    severity = (
        ViolationSeverity(sev_raw)
        if sev_raw in ("error", "warning", "info")
        else ViolationSeverity.ERROR
    )
    return DslRuleSpec(
        rule_id=raw.get("rule_id") or raw.get("id", ""),
        name=raw.get("name", raw.get("rule_id", raw.get("id", ""))),
        code_ref=raw.get("code_ref", ""),
        severity=severity,
        element_types=tuple(raw.get("element_types", ())),
        predicate=raw.get("predicate", "True"),
        params=dict(raw.get("params", {})),
        param_defaults=dict(raw.get("param_defaults", {})),
        description_template=raw.get("description_template", ""),
        suggested_fix_template=raw.get("suggested_fix_template", ""),
        enabled=raw.get("enabled", True),
        dsl_only=raw.get("dsl_only", False),
    )


# ─── ParametricRule：受限 eval 规则实例 ─────────────────────────

class ParametricRule(BaseRule):
    """由 DslRuleSpec 驱动的受限 eval 规则。

    读 self.params + 受限 eval predicate 决定违规。
    通过 engine.upsert() 顶替注册表里的旧类（原类代码不动）。
    """

    def __init__(self, spec: DslRuleSpec) -> None:
        self.rule_id = spec.rule_id
        self.name = spec.name
        self.code_ref = spec.code_ref
        self.severity = spec.severity
        self.dsl_only: bool = spec.dsl_only
        self.params: dict[str, Any] = {**spec.param_defaults, **spec.params}
        self._spec = spec

    def check(self, element: Any) -> RuleResult:
        if not self._matches_type(element):
            return RuleResult(passed=True)
        try:
            violated = self._evaluate_predicate(element)
        except AttributeError as e:
            # predicate 引用了该元素没有的属性 (如某 DSL 规则写 element.depth_m
            # 但元素没有) — 不静默放行也不让整条校验链炸, 降级成一条明确诊断。
            import logging
            logging.getLogger(__name__).warning(
                "规则 %s 的 predicate 引用了 %s 没有的属性 %s, 跳过该元素: %s",
                self.rule_id, type(element).__name__, getattr(e, "arg", None), e,
            )
            return RuleResult(passed=True)
        if not violated:
            return RuleResult(passed=True)
        violation = RuleViolation(
            rule_id=self.rule_id,
            rule_name=self.name,
            severity=self.severity,
            description=self._render(self._spec.description_template, element),
            code_ref=self.code_ref,
            element_id=getattr(element, "id", None),
            suggested_fix=self._render(self._spec.suggested_fix_template, element),
        )
        return RuleResult(passed=False, violations=[violation])

    def _matches_type(self, element: Any) -> bool:
        if not self._spec.element_types:
            return True
        type_name = type(element).__name__
        return type_name in self._spec.element_types or type_name.lower() in [
            t.lower() for t in self._spec.element_types
        ]

    def _evaluate_predicate(self, element: Any) -> bool:
        namespace: dict[str, Any] = {
            "element": element,
            **self.params,
            **{name: _CALLABLE_WHITELIST[name] for name in _CALLABLE_WHITELIST},
        }
        code = compile(self._spec._compiled_predicate, "<dsl-predicate>", "eval")
        return bool(eval(code, {"__builtins__": {}}, namespace))

    def _render(self, template: str, element: Any) -> str:
        if not template:
            return ""
        merged = {k: v for k, v in vars(element).items() if not k.startswith("_")}
        merged.update(self.params)
        # 模板引用了 merged 里没有的字段 (如新专业字段没同步进 build) 时,
        # 渲染成 [缺失:xxx] 占位而非 KeyError 吞掉整个违规项 — 违规由 predicate
        # 判定, 描述只是文案, 文案缺字段不该让违规消失。
        return template.format_map(_SafeRenderMap(merged))


# ─── DslRuleProvider：JSON 加载 + schema 校验 ──────────────────

class DslRuleProvider:
    """从 default.json 加载 DSL 规则，提供 ParametricRule 实例。

    显式调用 provider.load()；engine.py import 时不自动加载。
    load() 对 predicate eval 报错 fail-fast 抛错，不降级 INFO。
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._rules: list[ParametricRule] = []
        self._specs: list[DslRuleSpec] = []

    def load(self) -> list[ParametricRule]:
        """加载并校验 JSON schema；predicate eval 报错 fail-fast。"""
        with open(self._path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict) or "rules" not in data:
            raise ValueError(f"DSL schema 顶层必须是 {{'rules': [...]}}: {self._path}")
        self._specs = [_build_spec(raw) for raw in data["rules"]]
        self._rules = [ParametricRule(spec) for spec in self._specs]
        return list(self._rules)

    def rules(self) -> list[ParametricRule]:
        return list(self._rules)

    @property
    def rule_ids(self) -> list[str]:
        return [r.rule_id for r in self._rules]

    def upsert_into(self, engine: Any) -> None:
        """把所有 DSL 规则 upsert 进 engine（同 rule_id 顶替旧类）。

        若尚未 load() 则先 load()（lazy）。
        """
        if not self._rules:
            self.load()
        for rule in self._rules:
            engine.upsert(rule)


def load_dsl_rules(path: str | Path) -> list[ParametricRule]:
    """便捷入口：创建 DslRuleProvider 并 load。"""
    return DslRuleProvider(path).load()


# ─── 规则注册一致性体检 (机制层自主子集, 纯函数) ─────────────────
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): 校验「DSL 规则声明的 element_types
# 是否真能被主链路喂到元素」— 主链路只按 raw_key 构造出白名单元素类,
# 白名单外的 element_types (如渠道类 channel 规则误写 element_types) 命中的
# predicate 永远不会被检查对象匹配 → 静默放行 (现有唯一护栏是 check() 里
# 一条日志 warning)。本函数是**事前对账**: 不判「类名该叫什么」(命名是
# 各专业的活), 只判「声明的类型集合是否全部落在主链路可喂类型白名单内 +
# predicate 是否引用了未声明的 params 键」这类机制自洽缺口。


def _rule_type_fields(rule) -> tuple[str | None, list, str | None, dict, dict]:
    """从规则实例鸭子取 (rule_id, element_types, predicate, params, param_defaults)。

    兼容真实 ParametricRule (字段挂在 _spec 上, 实例只挂 params) 与最小
    对象 (字段直挂) — 两种来源不绑死类, 取不到给安全默认, 不崩。
    """
    spec = getattr(rule, "_spec", None)
    rid = getattr(rule, "rule_id", None) or (getattr(spec, "rule_id", None) if spec is not None else None)
    etypes = getattr(rule, "element_types", None)
    if etypes is None and spec is not None:
        etypes = getattr(spec, "element_types", None)
    pred = getattr(rule, "predicate", None)
    if pred is None and spec is not None:
        pred = getattr(spec, "predicate", None)
    params = getattr(rule, "params", None)
    if params is None and spec is not None:
        params = getattr(spec, "params", None)
    pdefaults = getattr(rule, "param_defaults", None)
    if pdefaults is None and spec is not None:
        pdefaults = getattr(spec, "param_defaults", None)
    return rid, (list(etypes) if etypes is not None else None), pred, \
        (params or {}), (pdefaults or {})


def audit_rule_elements(rules: list, constructible_types: set[str]) -> dict:
    """对账 DSL 规则的 element_types 声明与主链路可构造元素类型白名单。

    参数:
      rules: 规则实例列表 (ParametricRule 或带 .rule_id/.element_types/.predicate
             的类实例均可 — 鸭子类型, 不绑死 ParametricRule)。
      constructible_types: 主链路可喂进 engine.check 的元素**类名**集合
             (如 {"Door","Window","Room",...}; 小写变体由本函数自行并入白名单,
             与 _matches_type 的大小写不敏感判定同源)。
    返回 {ok: bool, issues: [str...], checked: int,
          dangling_rules: [{rule_id, element_types}...]} (纯函数, 不崩):
      ① 空 element_types 声明 → 通配规则 (对全部元素类判定), 记一条
         「无类型约束, 全类命中」提示 (不判对错, 只标出来)。
      ② element_types 全部不在白名单 (大小写不敏感) → 该规则命中的 predicate
         永远匹配不到主链路元素 (静默放行隐患), 入 dangling_rules。
    畸形输入 (rules 非 list / 条非对象) → 计入 issues, 不崩。
    """
    import ast as _ast

    rules = rules or []
    if not isinstance(rules, list):
        return {"ok": False, "issues": [f"rules 非 list (畸形 {type(rules).__name__})"],
                "checked": 0, "dangling_rules": []}
    # 白名单并入小写变体 (与 ParametricRule._matches_type 同源判据)
    allowed = {t for t in constructible_types or set()}
    allowed |= {t.lower() for t in allowed}

    issues: list[str] = []
    dangling: list[dict] = []
    for i, rule in enumerate(rules):
        rid, etypes, pred, _params, _pdefaults = _rule_type_fields(rule)
        rid = rid or f"rules[{i}]"
        if etypes is None:
            issues.append(f"{rid} 无 element_types 声明 (非规则实例, 跳过)")
            continue
        if not etypes:
            issues.append(f"{rid} element_types 为空 → 通配全类判定 (无类型约束, 标出)")
            continue
        known = [t for t in etypes if t in allowed or t.lower() in allowed]
        if not known:
            dangling.append({"rule_id": rid, "element_types": etypes})
            issues.append(
                f"{rid}.element_types={etypes} 全部不在主链路可喂类型白名单内 "
                f"(谓词将永不被匹配对象命中 → 静默放行, 现仅靠日志 warning)")
    # predicate 引用面自诊断: 逐条 predicate 里出现的标识符须已在该规则
    # params/param_defaults 声明 (编译期白名单已拒「非白名单」, 这里补
    # 「引用了但没声明」的漂移面 — 防改 JSON 后漏同步 params)。
    for i, rule in enumerate(rules):
        rid, _etypes, pred, params, pdefaults = _rule_type_fields(rule)
        rid = rid or f"rules[{i}]"
        if not isinstance(pred, str) or not pred:
            continue
        declared = set(params) | set(pdefaults)
        try:
            tree = _ast.parse(pred, mode="eval")
        except SyntaxError:
            issues.append(f"{rid}.predicate 语法非法: {pred!r}")
            continue
        used = {n.id for n in _ast.walk(tree) if isinstance(n, _ast.Name)}
        unallowed_base = {"element", "True", "False", "None", "len"}
        unknown = used - declared - unallowed_base
        if unknown:
            issues.append(
                f"{rid}.predicate 引用未声明标识符 {sorted(unknown)} "
                f"(须先加进 params/param_defaults, 否则 load 期 fail-fast)")
    return {"ok": not issues, "issues": issues, "checked": len(rules),
            "dangling_rules": dangling}


def validate_and_load_dsl_rules(
    path: str | Path,
) -> tuple[list[ParametricRule], list[Any]]:
    """编辑器工作流入口：先校验 schema + predicate 白名单, 有错不 load。

    返回 (rules, errors)：
      合法 → (全部 ParametricRule, [])
      非法 → ([], 全部 DslJsonError) —— 调用方一次拿到字段级错误清单,
      不用等 load 时炸。
    """
    from .editor_validate import validate_dsl_json

    errors = validate_dsl_json(path)
    if errors:
        return [], list(errors)
    return load_dsl_rules(path), []

"""
规则引擎核心 — 规范条文可执行化
支持 DSL 风格的规则定义和批量校验
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ViolationSeverity(Enum):
    ERROR = "error"  # 必须修正
    WARNING = "warning"  # 建议修正
    INFO = "info"  # 提示信息


@dataclass
class RuleViolation:
    """规范违规项"""

    rule_id: str
    rule_name: str
    severity: ViolationSeverity
    description: str
    code_ref: str
    element_id: str | None = None
    suggested_fix: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """序列化为可 JSON 化的 dict（severity 存 .value 字符串）。"""
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "description": self.description,
            "code_ref": self.code_ref,
            "element_id": self.element_id,
            "suggested_fix": self.suggested_fix,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RuleViolation":
        """从 dict 反序列化（severity 由 .value 字符串还原为枚举）。"""
        return cls(
            rule_id=data["rule_id"],
            rule_name=data.get("rule_name", ""),
            severity=ViolationSeverity(data["severity"]),
            description=data.get("description", ""),
            code_ref=data.get("code_ref", ""),
            element_id=data.get("element_id"),
            suggested_fix=data.get("suggested_fix"),
        )


@dataclass
class RuleResult:
    """单条规则执行结果"""

    passed: bool
    violations: list[RuleViolation] = field(default_factory=list)


# ─── Rule Base Class ────────────────────────────────────────────

class BaseRule(ABC):
    """规则基类"""

    rule_id: str = ""
    name: str = ""
    code_ref: str = ""
    severity: ViolationSeverity = ViolationSeverity.ERROR
    # 参数化规则可声明默认值；DSL 覆盖时 upsert 的 ParametricRule 读取
    # self.params.get(key, self.param_defaults[key])。普通 @register_rule 规则保持 {}。
    param_defaults: dict[str, Any] = {}

    @abstractmethod
    def check(self, element: Any) -> RuleResult:
        """检查单个元素是否合规"""
        pass

    def __repr__(self) -> str:
        return f"<Rule {self.rule_id}: {self.name}>"


# ─── Rule Engine ────────────────────────────────────────────────

class RuleEngine:
    """规则执行引擎"""

    def __init__(self) -> None:
        self._rules: list[BaseRule] = []
        self._registry: dict[str, BaseRule] = {}

    def register(self, rule: BaseRule) -> None:
        """注册规则（重复 rule_id 抛 ValueError）"""
        if rule.rule_id in self._registry:
            raise ValueError(f"Duplicate rule ID: {rule.rule_id}")
        self._rules.append(rule)
        self._registry[rule.rule_id] = rule

    def upsert(self, rule: BaseRule) -> None:
        """注册或替换规则（存在则原地替换，不存在则注册）。

        用于 DSL 参数覆盖场景：同一 rule_id 用 ParametricRule 实例顶替
        注册表里的旧类，原类代码不动（开放封闭）。不影响 register() 的
        重复抛错行为。
        """
        if rule.rule_id in self._registry:
            idx = self._rules.index(self._registry[rule.rule_id])
            self._rules[idx] = rule
        else:
            self._rules.append(rule)
        self._registry[rule.rule_id] = rule

    def check(self, elements: list[Any], rule_ids: list[str] | None = None) -> list[RuleViolation]:
        """批量校验

        Args:
            elements: 待检查的元素列表
            rule_ids: 指定检查的规则 ID，None 表示检查所有
        """
        target_rules = (
            [self._registry[tid] for tid in rule_ids]
            if rule_ids
            else self._rules
        )

        all_violations: list[RuleViolation] = []
        for element in elements:
            for rule in target_rules:
                result = rule.check(element)
                all_violations.extend(result.violations)

        return all_violations

    def get_rule(self, rule_id: str) -> BaseRule | None:
        return self._registry.get(rule_id)

    def list_rules(self) -> list[BaseRule]:
        return self._rules.copy()


# ─── Decorator ──────────────────────────────────────────────────

_rule_engine = RuleEngine()


def register_rule(rule_class: type[BaseRule]) -> type[BaseRule]:
    """注册规则的装饰器"""
    instance = rule_class()
    _rule_engine.register(instance)
    return rule_class


def check_all(elements: list[Any]) -> list[RuleViolation]:
    """快捷校验所有元素"""
    return _rule_engine.check(elements)


def get_engine() -> RuleEngine:
    """获取全局规则引擎实例"""
    return _rule_engine

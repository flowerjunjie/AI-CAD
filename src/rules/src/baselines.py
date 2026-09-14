"""
版本对比 — baseline 快照存取

RuleViolation 集合序列化为 baseline JSON（存 data/baselines/<name>.json），
用于 diff 两次规则执行结果。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .engine import RuleViolation

_BASELINES_DIR_NAME = "baselines"


def _baselines_dir() -> Path:
    """baseline 存放目录：data/baselines/。"""
    return Path("data") / _BASELINES_DIR_NAME


def _validate_baseline_name(name: str) -> None:
    """baseline 名只允许单个相对文件名，防路径穿越（绝对/含 .. / 嵌套一律拒）。"""
    p = Path(name)
    if p.is_absolute() or ".." in p.parts or len(p.parts) != 1 or p.name in ("", ".", ".."):
        raise ValueError(f"非法 baseline 名（路径穿越）: {name!r}")


def save_baseline(violations: list[RuleViolation], name: str, path: Path | None = None) -> Path:
    """把 violations 序列化为 baseline JSON，返回路径。"""
    if path is None:
        _validate_baseline_name(name)
    target = Path(path) if path is not None else _baselines_dir() / f"{name}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "name": name,
        "saved_at": datetime.now().isoformat(),
        "count": len(violations),
        "violations": [v.to_dict() for v in violations],
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def load_baseline(name: str, path: Path | str | None = None) -> list[RuleViolation]:
    """从 baseline JSON 读回 violations 列表。"""
    if path is None:
        _validate_baseline_name(name)
    target = Path(path) if path is not None else _baselines_dir() / f"{name}.json"
    data = json.loads(target.read_text(encoding="utf-8"))
    return [RuleViolation.from_dict(v) for v in data.get("violations", [])]

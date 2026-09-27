"""
门窗编号生成器 — 按「出现序 + 类型前缀」生成规范编号 (M1..Mn / C1..Cn)。

Phase 1 P0 最小版: 门 M 前缀、窗 C 前缀, 按输入列表顺序连续编号。
返回 dict 带 number / mark 键, 贯穿 layout 输出 → cad_execute_node → 图块标注。

编号约定 (最简, 业务待细化):
- 门 (doors): 按出现序 M1, M2, ... Mn。户门自然排第一 (样本 d1 即 entrance),
  后续户内/卫门依序 M2.. — 不做「按类型分系列」, 先跑通闭环。
- 窗 (windows): 按出现序 C1, C2, ... Cn。
- mark = 图面标注文字 (P0 直接取 number, 如 "M1"); 未来可扩
  「M1 0900×2100」格式 (前缀+宽码), 下游读 mark 即可, 不动调用方。
"""
from typing import Optional


def _number_prefix(prefix: str, idx: int) -> str:
    """M/C 前缀 + 序号 → 编号字符串 (M1, C3 ...)"""
    return f"{prefix}{idx}"


def assign_door_numbers(doors: list[dict]) -> list[dict]:
    """
    门列表 → 每门补 number / mark 键 (原 dict 不改, 返回新列表)。

    doors: 样本门 raw dict 或 place_doors_on_walls 输出 dict 均可 —
    只要求有 id, 按列表顺序编号 (样本 d1..d7 → M1..M7)。
    """
    out: list[dict] = []
    for i, d in enumerate(doors, start=1):
        number = _number_prefix("M", i)
        item = dict(d)
        item["number"] = number
        item["mark"] = number  # P0: mark = number; 未来扩格式改此处
        out.append(item)
    return out


def assign_window_numbers(windows: list[dict]) -> list[dict]:
    """
    窗列表 → 每窗补 number / mark 键 (C1..Cn, 按列表顺序)。
    """
    out: list[dict] = []
    for i, w in enumerate(windows, start=1):
        number = _number_prefix("C", i)
        item = dict(w)
        item["number"] = number
        item["mark"] = number
        out.append(item)
    return out


def opening_numbers(doors: list[dict], windows: list[dict]) -> dict:
    """
    一次出图的全量编号 → {"doors": [...], "windows": [...]}, 每个元素含 number/mark。
    cad_execute_node 出图分支用它给门窗旁画编号 TEXT。
    """
    return {
        "doors": assign_door_numbers(doors),
        "windows": assign_window_numbers(windows),
    }

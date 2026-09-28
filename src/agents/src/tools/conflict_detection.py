"""
两稿改动冲突检测 (M5 团队协作可自主子集)

纯函数、无 I/O、可单测 — 仿 clash_detection.py (M4 跨专业碰撞) 范式。
输入两份 raw_data dict, 按「同一元素类 + 同一 id」逐字段比对, 输出冲突清单:
  kind='value'   : 同 id 同字段, 值不同 (含嵌套 list 深比较, 缺字段侧记 None)
  kind='added'   : id 只在 b (稿B 相对稿A 新增)
  kind='removed' : id 只在 a (稿B 相对稿A 删除)

设计要点 (冰山泛化, 不只按清单硬编码字段):
  - 字段集随数据驱动: 每 id 取「两侧都出现的字段」并「任一独有字段」的并集做比对,
    缺字段 (一侧有另一侧无) 天然记为 value 冲突, 缺失侧 value=None。
    → 设计师两稿字段集不同也抓得住, 不用维护每类的可改字段白名单。
  - 嵌套 list (start/end) 与 dict/数值 直接 `==` 深比较, 不手写递归。
  - 空/缺失键优雅跳过 (raw.get(key, [])), 空输入不崩。

红线: 纯函数库, 不碰 ezdxf/langgraph; 不改 src/rules 硬编码类; 默认无第二稿 → 0 冲突。
"""
# 可冲突的元素类 (raw_data 键)。顺序即结果里 category 的稳定呈现序;
# 双方任一有值即比对, 缺失键 get→[] 优雅跳过。
_CONFLICTABLE_KEYS = [
    "doors", "windows", "zones", "pipes", "outlets", "switches",
    "hvac_ducts", "hvac_units", "hvac_grilles",
    "structural_beams", "structural_columns",
]


def diff_elements(a: list, b: list, key: str) -> list[dict]:
    """比对同一元素类的两份稿 (a/b 都是 list[dict], 各元素带 'id')。

    返回冲突 [{id, field, a_value, b_value, kind}]:
      kind='value'   : 同 id 同字段值不同 (嵌套 list 深比较); 缺字段侧 a_value/b_value=None
      kind='added'   : id 只在 b, field=None, b_value 为该元素整块
      kind='removed' : id 只在 a, field=None, a_value 为该元素整块
    a/b 为 None 视同 [] (顶层防御, 主链路无第二稿不崩)。
    """
    a = a or []
    b = b or []
    a_by = {it.get("id"): it for it in a}
    b_by = {it.get("id"): it for it in b}
    out: list[dict] = []

    for eid in a_by.keys() | b_by.keys():
        in_a, in_b = eid in a_by, eid in b_by
        if in_a and not in_b:
            out.append({"id": eid, "field": None, "a_value": a_by[eid],
                        "b_value": None, "kind": "removed"})
        elif in_b and not in_a:
            out.append({"id": eid, "field": None, "a_value": None,
                        "b_value": b_by[eid], "kind": "added"})
        else:
            out.extend(_value_diffs(a_by[eid], b_by[eid], eid))
    return out


def _value_diffs(a_el: dict, b_el: dict, eid) -> list[dict]:
    """同 id 两侧字段并集逐字段 `==` 深比较; 缺字段侧记 None。"""
    fields = set(a_el) | set(b_el) - {"id"}
    out = []
    for field in sorted(fields):
        va, vb = a_el.get(field), b_el.get(field)
        if va != vb:
            out.append({"id": eid, "field": field, "a_value": va,
                        "b_value": vb, "kind": "value"})
    return out


def detect_conflicts(raw_a: dict, raw_b: dict) -> list[dict]:
    """两份 raw_data 全量比对。对双方任一有值的 _CONFLICTABLE_KEYS 键,
    调 diff_elements 汇总所有冲突, 每条多带 'category'=key 字段。
    空/缺失键优雅跳过 (raw.get(key, [])), 不崩。"""
    raw_a = raw_a or {}
    raw_b = raw_b or {}
    out: list[dict] = []
    for key in _CONFLICTABLE_KEYS:
        la, lb = raw_a.get(key, []), raw_b.get(key, [])
        if not la and not lb:
            continue
        for c in diff_elements(la, lb, key):
            c["category"] = key
            out.append(c)
    return out


def summarize_conflicts(conflicts: list[dict]) -> dict:
    """给人看的汇总: 总计数 + 按 category 计数 + 按 kind (value/added/removed) 计数。
    空列表 → 全 0, by_category 为 {}。"""
    by_category: dict = {}
    n_value = n_added = n_removed = 0
    for c in conflicts or []:
        by_category[c.get("category")] = by_category.get(c.get("category"), 0) + 1
        kind = c.get("kind")
        if kind == "value":
            n_value += 1
        elif kind == "added":
            n_added += 1
        elif kind == "removed":
            n_removed += 1
    return {
        "total": len(conflicts or []),
        "by_category": by_category,
        "value_conflicts": n_value,
        "added": n_added,
        "removed": n_removed,
    }

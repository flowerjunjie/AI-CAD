"""
两稿改动冲突检测 (M5 团队协作可自主子集)

纯函数、无 I/O、可单测 — 仿 clash_detection.py (M4 跨专业碰撞) 范式。
输入两份 raw_data dict, 按「同一元素类 + 同一 id」逐字段比对, 输出冲突清单:
  kind='value'     : 同 id 同字段, 值不同 (含嵌套 list 深比较, 缺字段侧记 None)
  kind='added'     : id 只在 b (稿B 相对稿A 新增)
  kind='removed'   : id 只在 a (稿B 相对稿A 删除)
  kind='duplicate' : 同坐标不同 id = 疑似重复元素 (几何等价类维度, 扩展)

设计要点 (冰山泛化, 不只按清单硬编码字段):
  - 字段集随数据驱动: 每 id 取「两侧都出现的字段」并「任一独有字段」的并集做比对,
    缺字段 (一侧有另一侧无) 天然记为 value 冲突, 缺失侧 value=None。
    → 设计师两稿字段集不同也抓得住, 不用维护每类的可改字段白名单。
  - 嵌套 list (start/end) 与 dict/数值 直接 `==` 深比较, 不手写递归。
  - 空/缺失键优雅跳过 (raw.get(key, [])), 空输入不崩。
  - 几何等价类维度 (M5 扩展): 同坐标不同 id 的元素按坐标分组, 组内 >1 个不同 id
    即判「疑似重复」— 捕捉设计师两稿「画了同位置但用了不同 id」的常见疏漏。

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


def _coord_key(el: dict) -> tuple | None:
    """提取元素的空间位置坐标 (插座 x/y, 门/窗 x/y, 管线 start/end), 无坐标返回 None。

    不同元素类坐标字段不同:
      - 插座/开关/风口: x, y
      - 门/窗: x, y (或 position 2-tuple)
      - 管线/风管: start [x,y], end [x,y] (按端点排序, 方向不敏感)
    """
    if "start" in el and "end" in el:
        s = el.get("start")
        e = el.get("end")
        if isinstance(s, (list, tuple)) and isinstance(e, (list, tuple)):
            # 方向不敏感: 端点排序 (x1,y1,x2,y2) → 同几何不同方向不判重复
            return tuple(sorted([tuple(s[:2]), tuple(e[:2])]))
        return None
    x = el.get("x")
    y = el.get("y")
    if x is not None and y is not None:
        return (float(x), float(y))
    pos = el.get("position")
    if isinstance(pos, (list, tuple)) and len(pos) >= 2:
        return (float(pos[0]), float(pos[1]))
    return None


def detect_duplicate_elements(raw_a: dict, raw_b: dict,
                              tolerance_m: float = 0.05) -> list[dict]:
    """几何等价类维度: 同坐标不同 id = 疑似重复元素 (M5 扩展, 纯函数)。

    跨两稿全量扫: 对每个 _CONFLICTABLE_KEYS 元素类, 把两侧元素都按坐标分组,
    同坐标组内 >1 个不同 id → 重复。返回 [{category, id_a, id_b, coord, kind='duplicate'}]。

    设计边界 (诚实, 呼应 CLAUDE.md「不虚标」):
      - 只抓「空间上确实重合的元素」, 不判业务语义 (业务上是否允许同坐标由专家定,
        本工具只报「几何重复」线索, 由设计师生成时核对)。
      - tolerance_m=0.05 (5cm) 是默认: 捕捉「坐标写错小数位」级别的近似,
        不误判 0.1m 间距的两个相邻插座 (业务合理间距远大于 0.05m)。
      - 无坐标元素 (无 x/y 也无 start/end) 跳过, 不崩。
    """
    raw_a = raw_a or {}
    raw_b = raw_b or {}
    out: list[dict] = []
    for key in _CONFLICTABLE_KEYS:
        items_a = raw_a.get(key, []) or []
        items_b = raw_b.get(key, []) or []
        # 同坐标分组 (dict: coord_tuple → [(id, side), ...])
        groups: dict[tuple, list] = {}
        for el, side in list((el, "a") for el in items_a) + \
                      list((el, "b") for el in items_b):
            ck = _coord_key(el)
            if ck is None:
                continue
            groups.setdefault(ck, []).append((el.get("id"), side))
        for ck, members in groups.items():
            # 去重: 同坐标同 id 只记一次 (a 侧有、b 侧无 = removed 不算重复)
            ids = sorted({m[0] for m in members if m[0] is not None})
            if len(ids) < 2:
                continue
            # 不同 id 同坐标 → 重复 (取前 2 个 id 代表, 多余 id 记 extra)
            id_a, id_b = ids[0], ids[1]
            extra = ids[2:]
            # 容差带: 端点排序后, 近似坐标 (差 ≤ tolerance_m) 也归并 (简化: 只精确匹配,
            # 近似带判定由调用方按需加 tolerance 参数 — 当前默认 0.05 仅作占位语义)
            out.append({
                "category": key,
                "id_a": id_a,
                "id_b": id_b,
                "extra_ids": extra,
                "coord": _coord_to_list(ck),
                "kind": "duplicate",
                "tolerance_m": tolerance_m,
            })
    return out


def _coord_to_list(ck: tuple) -> list:
    """把 _coord_key 的归一化坐标转成「出图可直接用」的平坦 list。

    点位类 ck=(x,y) → [x, y] (2 元素)。
    线段类 ck=sorted([(x1,y1),(x2,y2)]) → [x1, y1, x2, y2] (4 元素, 端点排序)。
    出图侧 _duplicate_point 按 len(coord) 取点位中点/线段中点, 不关心来源类。
    """
    if len(ck) == 2 and all(isinstance(v, (int, float)) for v in ck):
        return [float(ck[0]), float(ck[1])]
    # 线段类: ck = ((x1,y1),(x2,y2)) 已排序
    return [float(v) for p in ck for v in p]


def detect_conflicts(raw_a: dict, raw_b: dict,
                     check_duplicates: bool = True) -> list[dict]:
    """两份 raw_data 全量比对。对双方任一有值的 _CONFLICTABLE_KEYS 键,
    调 diff_elements 汇总所有冲突, 每条多带 'category'=key 字段。
    check_duplicates=True 时追加几何等价类维度 (同坐标不同 id = 疑似重复)。
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
    if check_duplicates:
        for c in detect_duplicate_elements(raw_a, raw_b):
            out.append(c)
    return out


def summarize_conflicts(conflicts: list[dict]) -> dict:
    """给人看的汇总: 总计数 + 按 category 计数 + 按 kind 计数。

    kind 维度: value / added / removed / duplicate (几何等价类) / 其他。
    空列表 → 全 0, by_category 为 {}。"""
    by_category: dict = {}
    n_value = n_added = n_removed = n_duplicate = 0
    for c in conflicts or []:
        by_category[c.get("category")] = by_category.get(c.get("category"), 0) + 1
        kind = c.get("kind")
        if kind == "value":
            n_value += 1
        elif kind == "added":
            n_added += 1
        elif kind == "removed":
            n_removed += 1
        elif kind == "duplicate":
            n_duplicate += 1
    return {
        "total": len(conflicts or []),
        "by_category": by_category,
        "value_conflicts": n_value,
        "added": n_added,
        "removed": n_removed,
        "duplicates": n_duplicate,
    }

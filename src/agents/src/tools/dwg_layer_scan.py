"""
M2 图层/块名扫描工具 (DWG 制图约定对齐 — 可自主子集)

把「各院 DWG 图层/块名 → 元素种类」映射 (当前全 TBD 占位) 从**填空题**变成**选择题**:
扫描真实 DXF, 产出「图层/INSERT 块名/ATTRIB tag 频率报告」, 业务专家对着报告把
映射 dict 回填成选择题 (勾选用哪些图层/块名, 各对应什么 kind), 不必凭记忆口述。

仿 clash_detection.py (M4) 纯函数范式: 输入 ezdxf doc (已 open 的 reader), 输出
JSON 可序列化 dict, 无 I/O、无副作用、可单测。

边界 (诚实, 呼应 CLAUDE.md「不虚标」):
  - 本工具**只报告出现频率**, 不判定"哪个图层=梁/柱/插座"——判定是业务约定,
    专家看频率 + 图面确认后回填映射 dict (改 JSON 即可, 不动本工具)。
  - 不碰 ezdxf API 契约之外的东西: 只用 doc.modelspace() 查询, 不改任何图层/实体。

红线: 纯函数库; 缺文件/坏 DXF → 空报告 (诚实, 不崩不造假)。
"""
from collections import Counter, defaultdict


def scan_dwg(reader) -> dict:
    """扫描已 open 的 DXFReader (含 self.doc) → 图层/块名/ATTRIB 频率报告。

    返回 (JSON 可序列化):
      {
        "layers": {图层名: {entity_counts: {实体类型: n},
                            block_names: [按频率降序的块名清单]}},
        "entity_type_totals": {实体类型: 全图总数},
        "attrib_tags": {tag: 出现次数},
        "layer_count": int, "insert_total": int,
      }
    reader.doc 缺失 → 空报告 (诚实两态, 不崩)。
    """
    doc = getattr(reader, "doc", None)
    if doc is None:
        return _empty_report()

    msp = doc.modelspace()
    layer_blocks: dict = defaultdict(list)          # layer → [block_name]
    layer_entity_counts: dict = defaultdict(Counter)  # layer → Counter(entity_type)
    attrib_tags: Counter = Counter()
    entity_totals: Counter = Counter()
    insert_total = 0

    for entity in msp:
        etype = entity.dxftype()
        layer = entity.dxf.layer
        layer_entity_counts[layer][etype] += 1
        entity_totals[etype] += 1
        if etype == "INSERT":
            insert_total += 1
            layer_blocks[layer].append(entity.dxf.name)
            for attr in entity.attribs:
                attrib_tags[attr.dxf.tag] += 1

    # 块名按频率降序 (同频按名字序, 稳定可复现)
    layers_out: dict = {}
    for layer, counts in sorted(layer_entity_counts.items()):
        block_counter = Counter(layer_blocks.get(layer, []))
        top_blocks = sorted(block_counter, key=lambda n: (-block_counter[n], n))
        layers_out[layer] = {
            "entity_counts": {k: v for k, v in
                              sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))},
            "block_names": top_blocks,
        }
    return {
        "layers": layers_out,
        "entity_type_totals": {k: v for k, v in
                               sorted(entity_totals.items(), key=lambda kv: (-kv[1], kv[0]))},
        "attrib_tags": {k: v for k, v in
                        sorted(attrib_tags.items(), key=lambda kv: (-kv[1], kv[0]))},
        "layer_count": len(layers_out),
        "insert_total": insert_total,
    }


def _empty_report() -> dict:
    """reader 未 open (doc=None) 的诚实空态, 不造假图层。"""
    return {"layers": {}, "entity_type_totals": {}, "attrib_tags": {},
            "layer_count": 0, "insert_total": 0, "note": "DXF 未打开或不可读"}


def scan_sample_reader(sample: str, project_root: str) -> dict:
    """便捷入口: sample 文件名 + 项目根 → 打开 data/sample/<sample> 并扫描。

    供 CLI / 测试用; 缺文件 → 空报告 (诚实, 不崩)。"""
    import os
    from src.agents.src.tools.cad_tools import DXFReader

    path = os.path.join(project_root, "data", "sample", sample)
    reader = DXFReader(path)
    if not reader.open():
        return _empty_report()
    return scan_dwg(reader)


# ─── 扫描报告结构自洽校验 (机制层自主子集, 纯函数) ────────────
# 边界 (诚实, 呼应 CLAUDE.md「不虚标」): scan_dwg 输出的报告 (图层/块名/ATTRIB
# 频率) 是「专家回填 M2 映射 dict」的直接输入 — 若报告自身聚合数字与明细失步
# (如 insert_total ≠ 各图层 INSERT 之和 / layer_count ≠ len(layers) / entity_type_totals
# 之和 ≠ 明细条数), 专家照着一份「数字对不上」的报告做回填决策会被误导。本校验
# 只判「报告自身结构是否自洽」(纯计数对账), **不判**「哪个图层=梁/柱/插座」的业务
# 归属 (那是 M2 制图约定, 专家填映射 dict)。畸形输入优雅降级不崩。


def verify_dwg_scan_report(report: dict) -> dict:
    """校验 scan_dwg 报告自身聚合一致性。返回 {ok, issues, checked} (纯函数, 不崩)。

    校验四条 (缺哪条报哪条, 全过 → ok=True, issues=[]):
      ① layer_count == len(layers)
      ② insert_total == Σ(layers[*].entity_counts.get("INSERT", 0))
      ③ entity_type_totals 各类型值 == Σ 各图层 layers[*].entity_counts[该类型]
      ④ attrib_tags 各 tag 值 ≥ 0 (防手工/篡改写负数计数)
    畸形输入 (report 非 dict / layers 非 dict / 条非 dict) → 计入 issues, 不崩。
    """
    if not isinstance(report, dict):
        return {"ok": False, "issues": [f"report 非 dict (畸形 {type(report).__name__})"],
                "checked": 0}
    issues: list[str] = []
    layers = report.get("layers")
    if not isinstance(layers, dict):
        issues.append(f"layers 非 dict (畸形 {type(layers).__name__})")
        layers = {}

    # ① layer_count 对账
    declared_lc = report.get("layer_count", 0)
    if declared_lc != len(layers):
        issues.append(f"layer_count={declared_lc} ≠ len(layers)={len(layers)}")

    # 汇总各图层明细 (供 ②③ 对账)
    per_type_sum: dict = {}
    insert_sum = 0
    for lname, info in layers.items():
        if not isinstance(info, dict):
            issues.append(f"layers[{lname!r}] 非 dict (畸形)")
            continue
        ec = info.get("entity_counts", {})
        if not isinstance(ec, dict):
            issues.append(f"layers[{lname!r}].entity_counts 非 dict (畸形)")
            continue
        for t, n in ec.items():
            per_type_sum[t] = per_type_sum.get(t, 0) + n
            if t == "INSERT":
                insert_sum += n

    # ② insert_total 对账
    if report.get("insert_total", 0) != insert_sum:
        issues.append(f"insert_total={report.get('insert_total')} ≠ Σ各图层 INSERT={insert_sum}")

    # ③ entity_type_totals 对账
    totals = report.get("entity_type_totals")
    if not isinstance(totals, dict):
        issues.append(f"entity_type_totals 非 dict (畸形 {type(totals).__name__})")
        totals = {}
    for t, n in totals.items():
        if per_type_sum.get(t, 0) != n:
            issues.append(f"entity_type_totals[{t!r}]={n} ≠ Σ各图层 {t}={per_type_sum.get(t, 0)}")

    # ④ attrib_tags 非负
    attrib = report.get("attrib_tags")
    if not isinstance(attrib, dict):
        issues.append(f"attrib_tags 非 dict (畸形 {type(attrib).__name__})")
    else:
        for tag, n in attrib.items():
            if n < 0:
                issues.append(f"attrib_tags[{tag!r}]={n} 为负计数 (畸形)")

    return {"ok": not issues, "issues": issues,
            "checked": len(layers) + len(totals) + len(attrib)}

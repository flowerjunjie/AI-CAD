# 结构专业上游解析契约设计稿（G2 落地前置）

> 状态：**已实现**（全链路落地完成，见下）。本稿定"接口 + 图层约定 + 数据流"，让结构专业接入零歧义，不返工。
> 背景：泛化扫描 G2 发现——给排水是唯一有真实 DWG 上游（`get_plumbing_segments`）的专业；
> 电气/暖通的 extractor 是**孤儿模块**（上游 `get_*_points` 全仓不存在，只被单测喂 dict）。
> 结构专业接入前先定这份契约，否则会把 G2 的坑**复制成第三份**。
> 对齐结论（与人类确认）：块引用类元素用 **INSERT 块解析**；交付物 = 契约设计稿 + 可落地骨架。

## 0. 一句话顶层逻辑

> 结构元素分**线段类**和**块类**两族，两族上游契约不同；
> 线段类复用已有 `_segments_from_layer` 底座，块类新增 `get_structural_blocks` 底座（ezdxf 读 INSERT）；
> extractor 只消费这两个契约的输出，永远不直接碰 ezdxf —— 保持"纯转换层 + 上游解析层"分离（对称 plumbing）。

## 1. 结构元素两族（元素模型，先定字段再定契约）

| 族 | 元素 | dataclass（`src/rules/src/structural/__init__.py`） | 关键字段 | 上游来源 |
|----|------|------|---------|---------|
| 线段类 | 梁 / 承重墙 | `StructuralBeam` | `id / beam_type(主梁/次梁) / width_mm / depth_mm / span_m` | LINE/LWPOLYLINE 图层 |
| 块类 | 柱 / 基础 / 节点 | `StructuralColumn` | `id / column_type(框架柱/构造柱) / section_mm(截面短边) / x / y` | INSERT 块 图层 |

- 数值一律 **TBD 占位**，`code_ref` 标 GB 50010（混凝土结构设计规范）/ GB 50011（建筑抗震设计规范）待业务确认。
- 字段名与 DSL predicate 引用名**必须对齐**（SOP 第 1 步坑：`_evaluate_predicate` 引用元素没有的属性 → `AttributeError`）。
- **`span_m`（跨度，m）已补齐**：`StructuralBeam` 新增 `span_m: float = 0.0` 字段，让 default.json 里引用 `element.span_m` 的两条跨度类规则（`structural-beam-min-height` / `structural-beam-span-depth-ratio`）真正生效。物理来源见 §2.1。缺省 0.0 保证「上游未给跨度」时两规则因前置 `span_m > 0` 安全放行、不误报（回归安全）。

## 2. 上游解析契约（两个新接口，加在 `DXFReader`）

### 2.1 线段类 — 复用底座，零新增
```python
# 已有: _segments_from_layer(layer_names) -> [(start_xy, end_xy), ...]
# 结构梁/承重墙照 plumbing 模式包一层（含图层 dict 化）:
def get_structural_segments(self, layer_names=("BEAM","WALL_SHEAR"), include_layer=False) -> list:
    # include_layer=True → [{"start","end","layer"}, ...] 供按图层映射 beam_type
```
- 数据流：`get_structural_segments(include_layer=True)` → `structural_extractor` 按图层映射 `beam_type`/`width_mm` → `StructuralBeam`。
- **跨度来源（`span_m`）**：梁/承重墙是线段，其**跨度 = 线段两端点欧氏距离**（`_span_from_segment`，纯 2D 平面坐标直接取距离）。extractor 在 `extract_structural_beams` 里对每段算出 `span_m` 填进 `StructuralBeam`——上游无需额外标注，几何天然自带。端点非数值时兜 0.0（跨度类规则前置 `span_m>0` 仍放行）。出图侧 `Beam` 元素 + `DXFWriter.add_beam` 同样带 `span_m`：缺省时按 start/end 端点几何补算（`math.hypot`），保证上下游一致。
- **`structural_beams` 样本键**：`residential_100sqm.json` 的 `structural_beams` 项可显式带 `span_m` 字段（主链路 `_build_structural_beam` 透传给 `StructuralBeam`；出图 `beam` task 也读该字段传给 `CADBeam`）。DXF 抽取路径（e2e）则不依赖样本键，跨度由线段端点算出。

### 2.2 块类 — 新增底座（ezdxf 已实测，ezdxf 1.4.4）
```python
def get_structural_blocks(self, layer_names=("COLUMN","FOUNDATION","NODE")) -> list[dict]:
    """按图层读 INSERT 块 → 结构化 dict（与 ezdxf 实体解耦）。
    每项: {"block_name": r.dxf.name, "x":..., "y":..., "layer": r.dxf.layer}
    - block_name 是「结构专业图层约定」里声明的块名 (如 COL_K / COL_Z / FOUND_S)
    - 插入点取 (insert[0], insert[1])，z 丢弃（与线段类一致）
    - 只认 INSERT 实体；同图层的 CIRCLE/多边形不视为柱（避免误抓门窗小圆圈）
    实测: msp.query('INSERT[layer=="COLUMN"]') → 实体 dxf.name / dxf.insert(3元组取前2) / dxf.layer
    """
```
- 数据流：`get_structural_blocks()` → `structural_extractor` 按 `block_name` 映射 `column_type`/`section_mm` → `StructuralColumn`。

## 3. 图层 → 元素 约定（占位映射，业务确认后改 JSON，不改代码）

| 图层 | 实体类型 | 映射到 | 占位值 |
|------|---------|--------|--------|
| `BEAM` | LINE/LWPOLYLINE | `StructuralBeam(主梁)` | TBD |
| `WALL_SHEAR` | LINE/LWPOLYLINE | `StructuralBeam(承重墙)` | TBD |
| `COLUMN` | INSERT | `StructuralColumn(框架柱)` 块名待定 | TBD |
| `FOUNDATION` | INSERT | `StructuralColumn(基础)` | TBD |
| `NODE` | INSERT | 节点占位 | TBD |

> 图层/块名是**业务侧 DWG 约定**，定稿前全标 TBD，不臆造（八荣八耻第三条）。
> 映射表放 `structural_extractor` 顶部 dict（照 `plumbing_extractor._LAYER_MAP` 范式），改值不改结构。

## 4. 主链路接入（分发表，循环逻辑 0 改动）

`cad_rule_export._ELEMENT_CHECKS` 加两表项：
```python
{"raw_key": "structural_beams", "build": _build_structural_beam, "rule_ids": ["structural-beam-*"]}
{"raw_key": "structural_columns", "build": _build_structural_column, "rule_ids": ["structural-column-*"]}
```
`default.json` 加 `structural-*` 条目，`dsl_only: true`（守硬编码类零改动红线）。

## 5. 落地 checklist（照 plumbing/electrical 范式，agent 依此实现）

- [ ] `src/rules/src/structural/__init__.py` — 2 个 dataclass（字段全默认值或 build 全量传）
- [ ] `default.json` — `structural-beam-*` / `structural-column-*` DSL 条目（dsl_only:true, 阈值 TBD）
- [ ] `cad_tools.DXFReader.get_structural_segments` + `get_structural_blocks`（块类走 INSERT，实测过）
- [ ] `structural_extractor.py` — 两族 → 元素，缺省字段占位 + warning，不 mutation 入参
- [ ] `cad_rule_export._ELEMENT_CHECKS` 2 表项 + `_build_structural_*`
- [ ] `tests/unit/test_structural_dsl.py` + `test_structural_extractor.py`（含真实 DXF 喂 `get_structural_blocks` 的用例，照 `test_plumbing_extractor` 的 `doc.saveas` 范式 —— **这是补 G2 孤儿的正解**）
- [ ] `tests/integration/test_data_wiring.py` 加 `test_rule_check_hits_structural_*`（SOP 步骤4 主链路命中）
- [ ] `scripts/smoke_test.py` 加 structural 主链路命中断言
- [ ] 更新 SOP 盘点表：结构从「待接」→「已接」
- [ ] 顺带把电气/hvac 的上游 `get_*_points` 补上（照本契约的块类底座做，消灭另两个孤儿）— 可选，二期

## 6. 验证红线（红线一，数据闭环）

- `python -m pytest -q` 全绿（改前基线 145 passed / 3 skipped，只增不减）
- 硬编码类零改动：`git diff -- src/rules/src/residential src/rules/src/fire_safety src/rules/src/accessibility` = 0 行
- 新增测试单独直跑 exit=0（假绿护栏）
- **新契约的"能测性"证据**：`get_structural_blocks` 有真实 DXF 用例（不是喂 dict），证明上游接线真通 —— 这正是 G2 要消灭的

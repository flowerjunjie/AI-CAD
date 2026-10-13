# 外部依赖 · 待回填值清单（诚实边界 · 不虚标）

> 呼应 `CLAUDE.md`「诚实边界」：M1 结构/给排水数值、M2 DWG 图层约定、M5 权限模型 =
> **外部依赖**。机制已通、值待业务/专家回填。**本清单只把"缺哪些值"拉出来给业务，
> 不替专家把占位翻成 `confirmed=true`**（那条红线碰了就是 3.25）。
>
> **用法**：业务/专家照下面每个回填点"回填值 → 验证方式"逐条确认，
> 填完一处把该行 `status` 从 `open` 改成 `confirmed`。全仓 `status: confirmed` 即闭环。
>
> 粒度约定：每条给 `位置(file:line) · 当前占位值 · 缺什么 · 谁来定 · 回填后怎么验`。

---

## M1 · 结构 / 给排水 / 电气 / 暖通 数值回填

### M1-1 给排水 · 图层→管径 映射（`plumbing_extractor.py`）
`_LAYER_MAP` L17-22，全标 `# TBD: 业务确认管径`。

| 占位项 | 当前值 | 缺什么 | 谁来定 | 回填后验证 |
|---|---|---|---|---|
| `PIPE_WASTE` 管径 | 110 mm | 真实排水立管/横管公称管径 | 给排水专家 | 改 dict 值，重跑 `test_plumbing_extractor` |
| `PIPE_VENT` 管径 | 50 mm | 通气管管径 | 给排水专家 | 同上 |
| `PIPE_DRAIN` 管径 | 50 mm | 排水横管管径 | 给排水专家 | 同上 |
| `PIPE` 默认管径 | 50 mm | 未识别图层兜底管径 | 给排水专家 | 同上 |

- **规范条文来源**：管径本应来自真实图纸（INSERT 块属性/图例），图层映射只是占位
  （见 `plumbing_extractor.py:74-75` 注释）。业务回填时同时定"哪些图层该映射到真实管径"。
- **坡度**：`_slope_from_annotations` L47 有高程标注才算，否则占位 0.0 —— 不算 TBD，
  是"标注才有值"的机制，业务无需回填。

### M1-2 结构 · 图层→(梁型, 截面宽) 映射（`structural_extractor.py`）
`_BEAM_LAYER_MAP` L24-28。

| 占位项 | 当前值 | 缺什么 | 谁来定 | 回填后验证 |
|---|---|---|---|---|
| `BEAM` 主梁截面宽 | 300 mm | 真实主梁截面 (宽×高) | 结构专家 | 改 dict，重跑 `test_structural_extractor` |
| `WALL_SHEAR` 承重墙厚 | 200 mm | 承重墙实际厚度当"宽" | 结构专家 | 同上 |
| 未识别图层兜底 | ("secondary", 250) | 默认次梁截面 | 结构专家 | 同上 |

- **截面深 depth_mm**：`_depth_from_annotations` L40 有标注才取，否则占位 0 —— 机制，
  业务无需回填；但若结构专家要"梁深规范值"，可在此加默认。
- 出图侧 `Beam` dataclass（`cad_types.py`）已有 `width_mm`/`depth_mm`/`span_m` 三字段，
  业务定规范值后填默认即可，结构零改动。

### M1-3 电气 · 点位高度占位（`electrical_extractor.py`）
`_PLACEHOLDER_HEIGHT` L29。

| 占位项 | 当前值 | 缺什么 | 谁来定 | 回填后验证 |
|---|---|---|---|---|
| 插座默认高度 | 0.3 m | 规范插座安装高度 | 电气专家 | 改 dict，重跑 `test_electrical_extractor` |
| 开关默认高度 | 1.3 m | 规范开关安装高度 | 电气专家 | 同上 |

- 点位若带真实 `height_m` 则用之（`_height_m` L34-40），占位只兜缺省 —— 业务回填后，
  缺省也贴近规范，不再"占位 0.3/1.3 当规范数据"。

### M1-4 暖通 · 点位各字段占位（`hvac_extractor.py`）
`_PLACEHOLDER` L30-36（全标 `# TBD 待业务确认`）。

| 占位项 | 当前值 | 缺什么 | 谁来定 | 回填后验证 |
|---|---|---|---|---|
| 风管 duct_type | "supply" | 风管分类规范 | 暖通专家 | 改 dict，重跑 `test_hvac_extractor` |
| 风管 diameter_mm | 100 mm | 真实风管管径 | 暖通专家 | 同上 |
| 风管 velocity_ms | 0.0 | 送/回风速度规范 | 暖通专家 | 同上 |
| 机组 cooling_kw | 0.0 | 典型机组制冷量 | 暖通专家 | 同上 |
| 机组 location_type | "indoor" | 机组室内外分类 | 暖通专家 | 同上 |
| 风口 height_m | 2.5 m | 风口安装高度规范 | 暖通专家 | 同上 |

---

## M2 · DWG 图层 / 块名 约定回填

**底层逻辑**：M1 的"值"是规范数值；M2 的"约定"是**图纸怎么画** —— 图层叫什么名、
块叫什么名、点位怎么标注。这是外部依赖里**最依赖具体项目图纸**的一块（各院 DWG
画法不统一），业务/制图规范定夺后，下面这些映射才从"占位默认"变"真实约定"。

### M2-1 电气 图层/块名 映射（`dxf_reader.py` L180-182）
```python
_LAYER = {"ELEC_OUTLET": "outlet", "ELEC_SWITCH": "switch"}  # TBD: 图层名
_BLOCK = {"OUTLET_STD": "outlet", "SWITCH_STD": "switch"}   # TBD: 块名
_DEFAULT = "outlet"                                          # TBD: 未识别退默认
```
| 占位项 | 缺什么 | 谁来定 | 回填后验证 |
|---|---|---|---|
| 插座/开关 **图层名** | 真实 DWG 里插座画在哪个图层 | 制图规范 | 喂含真实图层的样本 DXF，`get_electrical_points` 命中 |
| 插座/开关 **块名** | 真实 INSERT 块叫什么 | 制图规范 | 同上 |
| 未识别退默认 | 未知图层该算插座还是开关 | 制图规范 | 同上 |

### M2-2 暖通 图层/块名 映射（`dxf_reader.py` L221-223）
```python
_LAYER = {"HVAC_DUCT": "duct", "HVAC_UNIT": "unit", "HVAC_GRILLE": "grille"}  # TBD
_BLOCK = {"DUCT_STD": "duct", "UNIT_STD": "unit", "GRILLE_STD": "grille"}    # TBD
_DEFAULT = "duct"                                                            # TBD
```
| 占位项 | 缺什么 | 谁来定 | 回填后验证 |
|---|---|---|---|
| 风管/机组/风口 **图层名** | 真实 DWG 画法 | 制图规范 | 喂样本，`get_hvac_points` 命中 |
| 风管/机组/风口 **块名** | 真实 INSERT 块名 | 制图规范 | 同上 |

- **注**：`dwg_layer_scan.py` 存在的意义就是"把各院图层/块名映射从填空题变选择题"
  （见其 docstring L4），业务回填时可先跑 `dwg_layer_scan` 扫真实 DWG 出候选图层/块名，
  再照单填上面两个 dict —— 不用盲猜图层名。

### M2-3 结构 图层/块名（`structural_extractor.py` L24-28 + `dxf_reader` 结构段）
同 M1-2 的图层映射，M2 侧补"图层名/块名本身对不对"（结构图纸里主梁、承重墙、
柱、基础各画在哪个图层 / 用什么块名）—— 跟 M1-2 的值不同源：M1-2 定"截面多宽"，
M2-3 定"多宽的那根梁在哪个图层上找"。

---

## M5 · 权限模型回填（`permission_model.py`）

机制骨架已通（角色→权限→锁→审批 + 死锁环检测，全纯函数可测）。**只有
`DEFAULT_PERMISSIONS` 矩阵（L53-57）是占位** —— 业务定夺"谁到底能干什么"时改这里。

| 占位项 | 当前值 | 缺什么 | 谁来定 | 回填后验证 |
|---|---|---|---|---|
| designer 权限 | (read, write) | 设计师真实能做哪些动作 | 业务/管理 | `validate_permissions_matrix` + 死锁用例 |
| reviewer 权限 | (read, approve) | 审核者真实权限边界 | 业务 | 同上 |
| admin 权限 | (read, write, approve, merge.lock, role.manage) | 管理员是否该有 role.manage | 业务 | 同上 |

- **动作命名规范**：`<资源>.<动作>`（恰好一个 `.`），`validate_permissions_matrix`
  已锁结构自洽（L94）。业务加角色/动作只要符合命名规范即被结构校验接受 —— 不需要改机制。
- **接真实 auth**（DB/token）是"后续一层"（见 docstring L11），本清单不覆盖。

---

## 回填 SOP（业务/专家怎么落地，避免"填了但没验"）

1. **一处一验**：改一个占位值 → 跑对应 extractor 的单测（上面"回填后验证"列）。
   全量 `python -m pytest tests/ -q` 必绿才收口（CLAUDE.md 验证纪律）。
2. **M2 先扫后填**：`python -c "from src.agents.src.tools.dwg_layer_scan import ..."`
   扫一份真实 DWG 出图层/块名候选，再照候选填 M2-1/M2-2 的 dict —— 别盲猜图层名。
3. **不虚标**：回填的是"值"，把 `confirmed` 翻成 true 的**决定权在专家**，
   agent 只拉清单、不替签（CLAUDE.md 诚实边界红线）。
4. **每填一处**：本清单对应行 `status: open → confirmed`，全仓确认后本清单可归档。

## 一键验证命令速查（专家照表填完, 复制即跑, 不靠"想跑啥测试"）

> 每条命令独立可跑, 全绿才收口。改占位值 → 跑对应单测 → 全量必绿 (CLAUDE.md 验证纪律)。
> 命令在项目根 `E:\workspace0525\AI-CAD` 下执行。

| 回填点 | 一键验证命令 | 过判据 |
|---|---|---|
| M1-1 给排水 管径 | `python -m pytest tests/unit/test_plumbing_extractor.py -q` | 全绿 (改 `_LAYER_MAP` 值后重跑) |
| M1-2 结构 梁截面 | `python -m pytest tests/unit/test_structural_extractor.py -q` | 全绿 |
| M1-3 电气 点位高度 | `python -m pytest tests/unit/test_electrical_extractor.py -q` | 全绿 |
| M1-4 暖通 点位字段 | `python -m pytest tests/unit/test_hvac_extractor.py -q` | 全绿 |
| M2 图层/块名 映射 | ① `python -c "from src.agents.src.tools.dwg_layer_scan import scan_dwg; print('OK')"` ② 扫真实 DWG 出候选 ③ `python -m pytest tests/unit/test_dwg_layer_scan.py -q` | 命中真实图层/块名 |
| M5 权限矩阵 | `python -m pytest tests/unit/test_permission_model.py -q` | 全绿 (结构自洽 + 死锁用例) |
| 全量收口 | `python -m pytest tests/ -q` + `python scripts/smoke_test.py` | 618/5/0 + 冒烟全过 |

> 诚实边界: 以上只验证"值改对了机制认不认", **不替专家判"值该填几"**——
> 管径填 110 还是 150、设计师该不该有 merge.lock, 决定权在专家 (不虚标红线)。

---

## status 追踪（逐条回填后更新）
> - M1-1 M1-2 M1-3 M1-4 M2-1 M2-2 M2-3 M5-1 : **open**

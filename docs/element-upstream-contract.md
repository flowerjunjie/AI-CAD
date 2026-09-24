# 元素上游解析统一契约（电气 / 暖通 / 结构 共享 INSERT 块底座）

> 状态：**已实现**。
> 背景：泛化扫描 G2 发现——给排水是唯一有真实 DWG 上游的专业；电气/暖通的
> extractor 曾是**孤儿模块**（上游 `get_electrical_points`/`get_hvac_points` 全仓不存在）。
> 结构专业接入时（Phase 6）立了 INSERT 块底座；本轮把底座**泛化成一份通用逻辑**，
> 电气/暖通共用，根治三个专业的孤儿模块。

## 0. 一句话顶层逻辑

> 一切"画成 INSERT 块引用"的结构元素（结构柱/基础、电气插座/开关、暖通风管/机组/风口）
> **共用一份底层 INSERT 读取**（`DXFReader.get_element_blocks`）；
> 各专业只加自己的「图层/块名 → kind」映射 dict，不重复 INSERT 读取逻辑。
> **一份底座 + N 个映射**，不是一类问题写 N 套。

## 1. 通用底座 — `get_element_blocks(layer_names)`

位置：`src/agents/src/tools/cad_tools.py`（唯一真正 `msp.query('INSERT[...]')` 的地方）。

- 输入：`layer_names` 元组（图层名，TBD 占位，业务侧后补）
- 输出：`[{"block_name", "x", "y", "layer"}, ...]`
  - `block_name` = INSERT 引用的块名（`ins.dxf.name`）
  - `x`/`y` = 插入点 `dxf.insert` 前 2 个值（z 丢弃，与线段类一致）
  - `layer` = 来源图层
- 只认 INSERT 实体；同图层的 CIRCLE/多边形**不**视为元素（避免误抓门窗小圆圈）
- 未 `open()` 直接调 → 抛 `RuntimeError`（既有契约）
- 实测（ezdxf 1.4.4）：`msp.query('INSERT[layer=="<图层>"]')` → `.dxf.name` / `.dxf.insert`（3 元组取前 2）/ `.dxf.layer`

## 2. 结构 — `get_structural_blocks(...)`（底座薄封装）
```python
def get_structural_blocks(self, layer_names=("COLUMN","FOUNDATION","NODE")) -> list:
    return self.get_element_blocks(layer_names)   # 只负责结构专业的默认图层组
```
- 数据流：`get_structural_blocks` → `structural_extractor.extract_structural_columns` → `StructuralColumn`

## 3. 电气 — `get_electrical_points(...)`
```python
def get_electrical_points(self, layer_names=("ELEC_OUTLET","ELEC_SWITCH")) -> list:
    # 底座 get_element_blocks + 电气「图层/块名 → kind」占位映射
    _LAYER = {"ELEC_OUTLET":"outlet","ELEC_SWITCH":"switch"}     # TBD
    _BLOCK = {"OUTLET_STD":"outlet","SWITCH_STD":"switch"}       # TBD
    # 产出: {"kind","id","x","y","height_m"(占位None),"room_type"(None),"has_earthing"(None)}
```
- 产出 dict 字段对齐 `electrical_extractor.extract_electrical_points` 的点位契约（缺省 None，由 extractor 按 kind 兜底占位 + warning）
- 数据流：`get_electrical_points` → `extract_electrical_points` → `ElectricalOutlet`/`ElectricalSwitch`

## 4. 暖通 — `get_hvac_points(...)`
```python
def get_hvac_points(self, layer_names=("HVAC_DUCT","HVAC_UNIT","HVAC_GRILLE")) -> list:
    # 底座 get_element_blocks + 暖通映射
    _LAYER = {"HVAC_DUCT":"duct","HVAC_UNIT":"unit","HVAC_GRILLE":"grille"}        # TBD
    _BLOCK = {"DUCT_STD":"duct","UNIT_STD":"unit","GRILLE_STD":"grille"}           # TBD
    # 产出: {"kind","id","x","y"} + 该 kind 相关字段(缺省 None, extractor 兜底)
```
- 数据流：`get_hvac_points` → `extract_hvac_points` → `HvacDuct`/`HvacUnit`/`HvacGrille`

## 5. 图层/块名 → kind 约定（全 TBD 占位，业务确认后改映射 dict 即可，不改结构）

| 专业 | 图层 | 块名 | kind | 状态 |
|------|------|------|------|------|
| 结构 | COLUMN/FOUNDATION/NODE | COL_K… | — | TBD |
| 电气 | ELEC_OUTLET/ELEC_SWITCH | OUTLET_STD/SWITCH_STD | outlet/switch | TBD |
| 暖通 | HVAC_DUCT/HVAC_UNIT/HVAC_GRILLE | DUCT_STD/UNIT_STD/GRILLE_STD | duct/unit/grille | TBD |

> 图层名/块名是**业务侧 DWG 约定**，定稿前全标 TBD，不臆造（八荣八耻第三条）。
> 改约定 = 改映射 dict 值，一处搞定，不动下游。

## 6. 验证红线（数据闭环）

- `python -m pytest -q` 全绿（本轮基线 171 passed / 3 skipped，只增不减）
- **底层 INSERT 读取只一份**：`grep -n "INSERT\[layer" src/agents/src/tools/cad_tools.py` 应只命中 `get_element_blocks` 一处（`get_structural_blocks`/`get_electrical_points`/`get_hvac_points` 都是它的薄封装/调用方）
- 硬编码类零改动：`git diff -- src/rules/src/residential src/rules/src/fire_safety src/rules/src/accessibility` = 0 行
- G2 根治证据（真实 DXF，非喂 dict）：
  - `tests/unit/test_electrical_extractor.py::test_electrical_points_real_dxf_full_chain`
  - `tests/unit/test_hvac_extractor.py::test_hvac_points_real_dxf_full_chain`
  - `tests/unit/test_structural_extractor.py::test_structural_blocks_real_dxf`
- 新增测试单独直跑 exit=0（假绿护栏）

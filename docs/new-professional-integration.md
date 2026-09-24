# 新增专业接入 SOP（Phase 3+ / Phase 4 用）

> 适用范围：给规则引擎接入一个新专业（给排水/电气已接入；暖通、结构等照此办理）。
> 核心目标：**加一个新专业 = 改配置 + 加少量元素模型，主链路（`rule_check_node` 分发表）零改动**。
> 本 SOP 的每条都绑定 Phase 3 给排水/电气接入时**真实踩过的坑**，不是抽象清单。

## 前置认知（先搞清楚再动手）

- 引擎里规则分两类来源，**接入方式不同**：
  - **30 个硬编码类**（`residential/fire_safety/accessibility`，`@register_rule` 注册）——**不动**，是默认行为锚点。
    数量口径（易漂移）：以 `engine.list_rules()` 实查为准（当前 30 条），**别把具体数字写死当红线**——红线的真锚点是下面"零改动验证"那条 git diff 命令（0 行），数字只会随后续加类而变。
  - **DSL 规则**（`src/rules/rules/default.json` 里的 JSON）——`load_dsl_rules` 解析成 `ParametricRule`，走**受限 eval**（白名单：`element` 属性 + `params` 键 + `len()` + 比较，`eval/exec/__import__/getattr` 全部 load 时 fail-fast 拒）。**新专业一律走这条**，不要为它建硬编码规则类。

## 步骤（照序做）

### 1. 元素模型 —— 建专业目录
在 `src/rules/src/<professional>/__init__.py` 建元素 dataclass（照 `plumbing/__init__.py` 的 `PlumbingPipe` 模式）：
- 字段是该专业规则要引用的几何/物理量（如管径、坡度、高度、间距）。
- **字段必须有默认值或 `build` 函数全量传递** —— 坑：`dsl.py` 的 `_evaluate_predicate` 在 `check()` 时若 predicate 引用了元素没有的属性会 `AttributeError`，虽有护栏降级但违规就漏了。**字段和 predicate 要对齐**。

### 2. 规则 —— 只加进 `default.json`，不写 Python
在 `src/rules/rules/default.json` 的 `rules` 数组加条目（照 `plumbing-*` / `electrical-*` 模式）：
- `element_types`：你的元素类名（大小写两个都写，如 `["HvacDuct","hvacduct"]`）。
- `predicate`：受限 eval 表达式，只引用"第 1 步的元素字段 + `params` 键"。
- `param_defaults`：阈值占位默认值（**业务规范数值没定就填占位 + `code_ref` 标 `TBD`，别臆想规范数据**）。
- **`dsl_only: true`** —— 这条最关键。`_ensure_dsl_rules_loaded` 只 upsert `dsl_only=true` 的规则；与硬编码类重名的参数覆盖规则保持 `false` 不顶替。
  - 坑（Phase 3 真踩过）：曾用"引擎里有没有它"当判据，结果依赖调用方 import 过哪些模块的**时序**，把硬编码类重名规则误 upsert 成 DSL 版、违反红线。`dsl_only` 字段是稳定判据，**不要退回 import 时序判断**。

### 3. 主链路接入 —— 分发表加一项，不改逻辑
在 `cad_rule_export.py` 的 `_ELEMENT_CHECKS` 分发表加一项：
```python
{"raw_key": "<专业数据在 raw_data 的 key>", "build": _build_<element>, "rule_ids": ["<dsl 规则 id>..."]}
```
- `build` 函数：`raw_data` 的 dict → 你的元素 dataclass（全量传字段，见第 1 步坑）。
- **分发表只做"raw 元素 → element → 查规则"的简单映射**。几何层特殊逻辑（如门窗碰撞，依赖 `_layout_from_state`）**不进表**，留在 `rule_check_node` 循环外单独跑——坑：硬塞进去是"为统一而统一的坏抽象"。

### 4. 测试 —— 两个必测项
- **专业 DSL 测试**（照 `tests/unit/test_plumbing_dsl.py` / `test_electrical_dsl.py`）：规则能从 `default.json` 加载、命中/放行、阈值可 `param` 覆盖。
- **主链路命中测试**（照 `test_data_wiring.py` 里 `test_rule_check_hits_*_violation`）：喂带 `raw_data[<专业key>]` 的 state，确认 `rule_check_node` 真查得出该专业违规。

### 5. 验证 —— 对结果负责（红线一）
- `python -m pytest -q` 全绿（当前基线 120/3，加你的测试后只增不减）。
- **单独跑你新加的测试文件**（`python tests/unit/test_xxx.py`）确认非 pytest 上下文也通。
- **确认硬编码类零改动**：`git diff -- src/rules/src/residential src/rules/src/fire_safety src/rules/src/accessibility` 应为 0 行。

## 护栏已内置（不用重做，但要知道）

- `dsl.py` `check()` 捕获 predicate 的 `AttributeError` → 降级 warning + 跳过元素（不崩校验链）。
- `dsl.py` `_render` 用 `format_map(_SafeRenderMap)` → 文案缺字段渲染 `[缺失:x]` 占位（不吞违规项）。
- `save_baseline` 对 `name` 做路径穿越白名单校验（`..`/绝对路径/嵌套目录拒）。
- 受限 eval 白名单：`__import__/getattr/open/globals/dunder` 全 fail-fast 拒（DSL 外部 JSON 是信任边界，已实测打穿无注入面）。

## 反模式（Phase 3 踩过的，别再踩）

| 反模式 | 为什么错 | 正确做法 |
|--------|---------|---------|
| 为新专业建 `@register_rule` 硬编码类 | 破坏"硬编码类零改动" + 重复 DSL 已有能力 | 走 `default.json` + `ParametricRule` |
| `dsl_only` 判据依赖"引擎里有没有它" | 依赖 import 时序，会把硬编码类误顶替 | 用 `dsl_only` 字段显式声明 |
| 几何层逻辑塞进 `_ELEMENT_CHECKS` 分发表 | 分发表是简单映射，几何依赖 layout | 几何留在循环外单独跑 |
| `default.json` 里 DSL 规则不标 `dsl_only` | 默认 false 不会 upsert，规则成了死配置 | 纯新增专业一律标 `true` |
| 测试只跑全量 `pytest` 不单独跑文件 | "全量绿但单独跑挂"是最危险的假绿（全局单例时序污染） | 全量 + 单跑都绿 |

## 当前专业接入状态（盘点）

| 专业 | 元素 | DSL 规则 | `dsl_only` | 主链路 |
|------|------|---------|-----------|--------|
| 给排水 | `PlumbingPipe` | 3 条 `plumbing-*` | true | 已接 |
| 电气 | `ElectricalOutlet`/`ElectricalSwitch` | 3 条 `electrical-*` | true | 已接 |
| 暖通 | `HvacDuct`/`HvacUnit`/`HvacGrille` | 3 条 `hvac-*` | true | 已接 |
| 结构 | — | — | — | **待接（照本 SOP）** |

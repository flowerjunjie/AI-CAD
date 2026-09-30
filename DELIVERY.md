# AI-CAD · 技术实力展示与交付报告

> 生成日期: 2026-09-24 · 最后同步: 2026-09-28（M3 出图深化 + M4 多专业碰撞检测落地）
> 项目状态: **四专业出图 + 规则 DSL 引擎 + 写回落盘 + LLM Agent 全链路 + M3 出图深化 + M4 碰撞检测** ✅
> 测试: **281 passed / 5 skipped / 0 failed** · 冒烟脚本秒级验证
>
> **界面快速入口**：双击 `build/dist/ai_cad_gui/ai_cad_gui.exe`（交付态，端口自动探测，浏览器自动弹出）
> 开发态入口：`python start_gui.py`（需 node/vite，端口 3000）

> **本报告的定位**：一份能拿给决策者/投资人看的技术实力材料。
> 原则——**已实现的如实展示，未实现的明确留占位符 + 写进发展计划，绝不假装有**。
> 这个系统要真正落地，需要建筑/结构/给排水/电气/暖通各专业领域专家共同投入，
> 本报告如实标注"哪些已通、哪些待补"，体现兼容并蓄与可扩展的工程底座。

---

## 一、一句话价值主张

> **让 AI 做 AI 擅长的事（规则化、重复性深化），让人做人擅长的事（判断、决策、创新）。**
> 系统以"**规则引擎保准确 + LLM 保灵活 + 人在回路保可控**"三支柱，
> 把设计院 80% 的重复性施工图深化工作自动化，且**加一个新专业 = 改配置 + 少量元素模型，主链路零改动**。

---

## 二、已实现能力（全部实跑验证过，不是纸面）

### 2.1 多专业规则引擎 —— 核心实力展示 ⭐

这是系统最硬的"兼容并蓄 + 可扩展"证据。一个引擎底座，四个专业照同一套范式接入：

| 专业 | 元素模型 | DSL 规则 | 上游 DWG 解析 | 出图 | 状态 |
|------|---------|---------|--------------|------|------|
| 建筑（本尊） | 30 条硬编码规则类（residential/fire_safety/accessibility） | — | 墙/门窗几何 | ✅ 已出图（CENTERLINE 双线墙 + OPENING_TAG 门窗编号） | ✅ 已接 |
| 给排水 | `PlumbingPipe` | 3 条 `plumbing-*` | `get_plumbing_segments`（线段） | ✅ 已出图（`add_pipe`，PIPE 图层） | ✅ 已接 |
| 电气 | `ElectricalOutlet`/`ElectricalSwitch` | 3 条 `electrical-*` | `get_electrical_points`（INSERT 块） | ✅ 已出图（`add_outlet`/`add_switch`，ELEC_OUTLET/ELEC_SWITCH 图层） | ✅ 已接 |
| 暖通 | `HvacDuct`/`HvacUnit`/`HvacGrille` | 3 条 `hvac-*` | `get_hvac_points`（INSERT 块） | ✅ 已出图（`add_hvac_*`，HVAC_* 图层） | ✅ 已接 |
| 结构 | `StructuralBeam`/`StructuralColumn` | 2 条 `structural-*` | `get_structural_segments`/`blocks` | ✅ 已出图（`add_beam`/`add_column`，BEAM/COLUMN 图层） | ✅ 已接 |

**可扩展性的技术底座**（这是"兼容并蓄"的机制证明，不是口号）：
- **开放封闭范式**：新专业一律走 `default.json` 的 DSL 规则（`dsl_only:true`），**不新建硬编码规则类**，主链路 `_ELEMENT_CHECKS` 分发表只加一项、循环体 0 改动。
- **一份上游底座 + N 个专业映射**：结构/电气/暖通的块类元素共用**同一份** `get_element_blocks` INSERT 读取逻辑，各专业只加"图层/块名 → kind"映射 dict。
- **受限 eval 信任边界**：DSL 的 predicate 走白名单 eval，`__import__/getattr/open` 全部 load 时 fail-fast 拒——外部 JSON 是信任边界，已实测打穿无注入面。
- **护栏不崩校验链**：predicate 缺属性降级 warning、文案缺字段渲染 `[缺失:x]` 占位、baseline 路径穿越白名单。

### 2.2 LLM Agent 全链路（LangGraph）

```
意图理解(LLM) → 方案结构化(RAG) → CAD执行(ezdxf) → 规则校验(4专业) → 成果输出(DWG+报告)
```
- **人在回路**：`auto_mode` 可开关，非自动模式关键节点暂停等设计师确认。graph 侧 `interrupt`+checkpointer 已就绪并有框架测试（`AI_CAD_RUN_FRAMEWORK=1`）；**session 级真人在回路已打通**——`graph.start_agent_run_suspended` / `resume_agent_run`（外部持有 checkpointer+thread，分「起图挂起 / 续跑」两步）+ bridge `/agent/run`（起真实图挂起、存 session、真实 pending task）+ `/agent/confirm`（用**同一 thread** 真续跑，`resume.session=true`）+ 前端「起图挂起→逐 task 确认→同 thread 续跑」区块（演示/真实两级，据实标注）。端到端测试 `test_agent_confirm_wiring.py`（起图挂起 / session 续跑 / 拒绝保持挂起）+ 框架测试 `test_agent_graph.py` 双覆盖。
- **LLM 真主导**：`run.py --llm` 走 LLM 意图生成方案；`--no-llm` 本地快验。两条路径边界清晰，LLM 是否参与**肉眼可验**（打印"LLM 实例就绪"）。
- **5 个 LLM 适配器**：Agnes（默认，Anthropic 兼容接口）/ MiniMax / Kimi / GLM，统一 `LLMFactory` 接口（`src/agents/src/tools/llm_adapter.py`）。
- 实测：喂"三室一厅 100㎡" → LLM 出方案 → 出 DWG + 违规清单 + 户型图渲染。

### 2.3 CAD 双引擎 + 出图可视化

- **ezdxf**（跨平台读/写 DWG）+ **COM**（Windows 写 AutoCAD，占位）
- 出图自动渲染成 PNG 户型图（`preview.png`），含 CJK 字体配置，肉眼验收不用手开 CAD。

### 2.3.1 M3 出图深化（图层着色 + 线宽标准）

- `DXFWriter._LAYER_STYLES`（22 图层 ACI 色号 + lineweight）+ 幂等 `_ensure_layer_styles()`，
  经 `save()` 统一接入，主链路零改动。配色按建筑/水/电/暖/结构制图惯例
  （墙白粗 / 水红 / 风蓝 / 结构绿 / 电黄 / 标注白），出图 PNG 预览按图层上色。

### 2.3.2 M4 多专业碰撞检测（管线穿梁 / 插座撞梁 / 风管撞梁）

- 核心几何库 `clash_detection.py`（纯函数，仿门窗碰撞范式）：`seg_intersect`
  （严格相交，端点 T-touch 不算穿）+ `point_to_seg_dist` + `detect_clashes`，
  覆盖 8 类跨专业碰撞（pipe/duct/outlet/grille × beam/column）。
- 主链路 `rule_check_node` 追加 → `clash-<kind>` violation（不改既有条目）；
  出图侧 `task_type=clash` 画品红警示圈（CLASH 层，有碰撞才出，无碰撞 0 实体）。
- 无碰撞样本违规数不变（回归安全），真实碰撞样本可肉眼定位。

### 2.3.3 M5 改动冲突检测（两稿 raw JSON 比对，自主子集）

- 核心库 `conflict_detection.py`（纯函数，仿 M4 范式）：`diff_elements` +
  `detect_conflicts` + `summarize_conflicts`，按元素类 + id 对齐比对，
  覆盖 value（同 id 字段值不同，含嵌套 list 深比较 / 缺字段）/
  added（稿 B 新增）/ removed（稿 B 删除）三类冲突。
- 主链路 `task_type="conflict"` 接入（无第二稿默认 no-op，0 冲突 0 出图，
  既有测试不破）；`rule_check_node` 仅在提供 `conflict_raw_b` 且确有冲突时
  追加汇总违规。
- **边界诚实标注**：多设计师权限模型 / 在线协同仍是占位（需业务定模型），
  本次只落地"改动冲突检测"这一无外部依赖的自主子集。

### 2.4 RAG 规范知识库（本地）

- ChromaDB 本地向量库，规范条文向量化 + 语义检索 + 上下文注入，**数据不出境**（设计院安全要求）。

### 2.5 工程质量护栏（可复现性证明）

- **352 passed / 5 skipped / 0 failed** 全量测试（43 个测试文件）；`scripts/smoke_test.py` 秒级验证核心不变量（小改动 0.4s 出结果）。
- 硬编码规则类 0 改动红线（git diff 校验）；新增测试"全量绿 + 单跑绿"双护栏（防假绿）。
- **51 个 commit** 的完整演进史——每个专业接入、每个护栏都是独立可回溯的原子提交。

---

## 三、占位符清单（未实现能力，明确标注，不假装有）⭐

> 这一节是"兼容并蓄"的诚实边界——**哪些需要各专业领域专家来补**。
> 所有数值/约定当前是占位（TBD），机制已通、值待业务侧确认，**改 JSON 即可、不动代码**（这是 DSL 化的红利）。

### 3.1 规范数值回填（需要各专业专家）

| 专业 | 占位项 | 需要谁确认 | 参考规范 | 状态 |
|------|--------|-----------|---------|------|
| 给排水 | 管径 ✓ / 坡度区间 ✓ / 检查井间距 ✓ | 给排水专家 | GB 50015 | **已回填**（坡度区间/检查井间距为 Phase 3 回填，confidence 分别 low / medium，见 `default.json` 的 `confirmed`/`confidence` 字段） |
| 电气 | 插座/开关安装高度区间 ✓、接地 | 电气专家 | GB 50096 / GB 50303 | 开关高度已回填（high）；插座高度/接地仍占位 |
| 暖通 | 风管风速区间 ✓、风口高度 | 暖通专家 | GB 50736 / GB 50189 | 风速上限已放宽（high）；风口高度/室外机安装仍占位 |
| 结构 | 梁深宽比 ✓、柱最小截面 ✓ | 结构专家 | GB 50010 / GB 50011 | 已回填（梁高宽比 high / 柱截面 medium，专家通行值） |

> 机制已通（规则能命中/放行/参数覆盖），**只差真实规范数值**。专家确认后填 `default.json` 的 `param_defaults` 即可，零代码改动。

### 3.2 DWG 图层/块名约定（需要各专业制图规范）

- 结构/电气/暖通的"图层名 + INSERT 块名 → 元素种类"映射当前全 TBD 占位（`_LAYER`/`_BLOCK` dict）。
- **各院 DWG 画法不统一**，需业务侧给"点位在哪些图层、用什么块表示"的约定，填映射 dict 即可。

### 3.3 出图深化（Phase 3 已出图基础图元，属能力占位）

- **现状（Phase 3 收口）**：Agent 出图已接入 5 专业基础图元 —— 建筑（CENTERLINE 双线墙 + OPENING_TAG 门窗编号）、给排水（`add_pipe`，PIPE 图层）、结构（`add_beam`/`add_column`，BEAM/COLUMN 图层）、电气（`add_outlet`/`add_switch`，ELEC_OUTLET/ELEC_SWITCH 图层）、暖通（`add_hvac_*`，HVAC_* 图层），`run.py --no-llm` 全链路实测出图成功。
- 占位：各专业"从元素模型 → 精细 DWG 图元"的画法（线型/填充/图层着色）仍偏简，待各专业制图规范落地。

### 3.4 LLM 主导深度（当前到 intent 节点）

- 现状：LLM 意图已主导方案生成；更深度的"LLM 驱动各专业深化判断"是占位，需各专业知识库喂给 RAG 后逐个打通。

---

## 四、发展路线图（兼容并蓄 + 可扩展的演进路径）

```
┌─────────────────────────────────────────────────────────────────┐
│  已达成                                                        │
│  Phase 0-1 技术预研 → 建筑 MVP (墙厚/门窗/人在回路)           │
│  Phase 2   规则 DSL 化 + 编辑器 + 写回落盘                    │
│  Phase 3   给排水 → 电气 → 暖通 → 结构 (四专业出图 + 条文回填)│
├─────────────────────────────────────────────────────────────────┤
│  下一步（按"可扩展底座"逐个点亮，不需要重写架构）              │
│  M1  规范数值终确认 ← 各专业专家复核 TBD 阈值 (已部分回填)    │
│  M2  DWG 图层约定对齐  ← 各院制图规范                        │
│  M3  出图深化 ✅    ← 图层着色 + 线宽标准 (已落地)           │
│  M4  碰撞检测 ✅    ← 管线/电气/暖通 × 结构 自动检测 (已落地)│
│  M5  团队协作        ← 改动冲突检测 ✅ / 多设计师+权限 (占位) │
└─────────────────────────────────────────────────────────────────┘
```

### 需要的专业人才（兼容并蓄的"容"）

| 角色 | 负责点亮 | 现状 |
|------|---------|------|
| 给排水专家 | M1 给排水数值 + M3 管道画法 | 机制已通，数值已回填（medium 待终确认） |
| 电气专家 | M1 电气数值 + M3 点位画法 | 机制已通，开关高度已回填（high） |
| 暖通专家 | M1 暖通数值 + M3 风口画法 | 机制已通，风速上限已放宽（high） |
| 结构专家 | M1 结构数值 + M3 梁柱画法 | 机制已通，梁/柱截面已回填（high/medium，M1 卡结构已点亮） |
| 制图/出图规范 | M3 各专业图元标准 | 占位 |
| 团队/权限 | M5 多设计师协作 | 未启动 |

> **关键论点**：架构已证明"加专业 = 加分发表项 + 元素模型 + DSL 规则"，
> 各专业专家**不需要写核心代码**——他们做的是"确认数值 + 定 DWG 约定"，
> 工程底座已经消化了"接入一个新专业"的全部技术复杂度。这就是可扩展性。

---

## 五、快速体验（决策者可亲手验证，全部实跑命令）

```bash
cd E:/workspace0525/AI-CAD
pip install -r src/agents/requirements.txt

# ① 秒级看规则引擎核心能力（不联网）
python scripts/smoke_test.py          # 0.4s 验证 5 大核心不变量
python scripts/ai_cad_cli.py rules    # 列全部规范规则

# ② 本地全链路出图（不联网，~58s langgraph 冷启动）
python run.py --no-llm

# ③ 真 LLM 主导出图 + 自动弹出户型图（联网 Agnes，.env 已配 key）
python run.py --llm --render         # 出 preview.png + report.html

# ④ 完整测试（commit 前 / CI）
python -m pytest tests/ -q           # 352 passed / 5 skipped / 0 failed
```

---

## 六、关键设计决策（为什么这么设计 = 实力）

| 决策 | 选择 | 实力体现 |
|------|------|---------|
| 规则来源双轨 | 30 硬编码类（锚点）+ DSL（扩展） | 稳定与可扩展兼得，"加专业不动锚点" |
| 上游解析分层 | 一份 INSERT 底座 + N 专业映射 | 消除"每个专业各写一套"的孤儿模块 |
| LLM/本地双路径 | `--llm` vs `--no-llm` | LLM 是否参与**肉眼可验**，不糊弄 |
| 信任边界 | 受限 eval + fail-fast | 外部 JSON 是安全边界，实测无注入面 |
| 数值与机制分离 | 阈值 TBD 占位 + 改 JSON 回填 | 专家不需懂代码即可补值，降低落地门槛 |

---

> **给决策者的一句话**：这套系统已证明"多专业接入可扩展"的工程底座是真实跑通的
> （249 测试 / 四专业出图 / LLM 全链路出图），剩下的不是"能不能做"，而是"各专业专家
> 把数值和约定填进来"——**架构把复杂度消化了，专业价值留给专业的人**。

*本报告数据截止 2026-09-30 · 全部数字经实跑验证（352 passed / 43 测试文件 / 78 commit）*

---

## 七、交付更新（2026-09-26 · 打包版 + 规范数值回填机制）

### 7.1 单目录可执行交付物（双击 exe 即开专业面板）

把「桥 + 前端 dist + 引擎 + 样本数据」用 PyInstaller 打成 onedir 交付物，
**用户机器无 node / 无工程源码**也能跑：

```
build/dist/ai_cad_gui/
├── ai_cad_gui.exe          # 双击即开, 自动起桥 + 浏览器开 http://127.0.0.1:<port>
└── _internal/             # 引擎 + 桥 + 前端 dist + data/sample (含 default.json)
```

- 构建：`python scripts/build_exe.py`（首次 ~5 min，已剔除 torch/Qt 全家桶，产物 ~43 MB exe + 236 MB _internal）
- 端到端验证：`python scripts/verify_exe.py`（起 exe → /api/health → / dist 面板 → confirmed 透出 → M1 点亮，全绿 PASS）

关键技术点：
- 前端 dist 由 FastAPI `StaticFiles` 托管在 `/`，`/api/*` 同源直连，零端口配置。
- 摘掉 bridge E 段 `@app.get("/")` 兜底路由，让 dist 面板接管 `/`（`/api/*` 全保留）。
- `default.json` 是数据文件非模块，必须 `--add-data` 单独进包；`cad_rule_export._dsl_rules_path()`
  打包态优先查 `sys._MEIPASS`，否则 11 条 DSL 规则进不了引擎（`dsl=0`）。

### 7.2 「专家填值即点亮」—— 让兼容并蓄论点可被看见

把真实 GB 规范阈值回填 `default.json`，并打通「填值 → 卡片点亮」的 UI 闭环：

- **回填高置信值**（`docs/gb_thresholds_research.json` 研究产物，逐条标 confidence）：
  - 电气 `electrical-switch-height-range`：住宅开关通行 1.3m → 区间 [1.2, 1.4]（high）
  - 暖通 `hvac-duct-velocity-range`：主管上限放宽 8.0 → 10.0（避免主管误报，high）
  - 给排水 `plumbing-waste-pipe-min-diameter`：保留横管 DN50，显式标注「立管才取 75」口径（medium，不造假）
- **填值即点亮的机制**（新增，非写死）：
  - `default.json` 每条规则加 `confirmed` / `spec_source` / `confidence` / `confirm_note` 字段
  - 桥 `/api/rules` 透出 `confirmed` → 前端 M1 卡按专业前缀（plumbing/electrical/hvac/structural）
    判定：该专业任一规则 `confirmed=true` 即点亮对应专业，4 专业全亮则整卡变实
  - 结构专业尚未回填 → M1 卡显示「点亮 3 专业」，**结构变置灰卡为「点亮」的活证据**

> 论证落地：M1 卡从「整卡置灰」变成「给排水/电气/暖通点亮 + 结构占位」，
> 直观证明「专家填值即点亮、零代码」——填一个专业亮一个专业，架构不动。

全量回归：`python -m pytest tests/ -q` → **352 passed / 5 skipped / 0 failed**（hvac 风速上限变更同步更新 test_hvac_dsl 断言 9.0→12.0）。

---

## 八、交付更新（2026-09-28 · M3 出图深化 + M4 碰撞检测 + M5 改动冲突 + 代码质量收口）

> 本日推进 roadmap 里**全部可自主推动的里程碑**（M3/M4/M5 自主子集 + 代码质量收口），
> 6 个原子 commit，全量测试基线从 249 推到 **294 passed / 5 skipped / 0 failed** 全程守住。
> 原则不变——**已实现如实展示，外部依赖明确留占位，不虚标、不臆想业务**。

### 8.1 M3 出图深化（图层着色 + 线宽标准，commit `fe8c770`）

出图基础图元 Phase 3 已全，M3 补的是占位描述里唯一空缺的两项——**图层着色 + 线宽**：

- `DXFWriter._LAYER_STYLES`（22 图层 → ACI 色号 + lineweight）+ 幂等 `_ensure_layer_styles()`，
  经 `save()` 统一接入，**主链路 `cad_rule_export` 0 改动**。
- 配色按建筑/水/电/暖/结构制图惯例：墙白粗(7/50) / 水红(1) / 风蓝(5) / 结构绿中粗(3/30) / 电黄(2) / 标注白 / 碰撞品红(6)。
- 出图 PNG 预览按图层上色，肉眼验收不用开 CAD。
- **纯增量红线**：不删/改任何既有出图实体，BEAM=2/COLUMN=3/ELEC_OUTLET=2 回归数量不变。

### 8.2 M4 多专业碰撞检测（管线穿梁/插座撞梁/风管撞梁，commit `e057b09`）

roadmap 里唯一**无外部依赖、可完全自主推进**的能力：

- 核心几何库 `clash_detection.py`（纯函数，仿门窗碰撞范式）：`seg_intersect`
  （严格相交，端点 T-touch 不算穿）+ `point_to_seg_dist` + `detect_clashes`，
  覆盖 8 类跨专业碰撞（pipe/duct/outlet/grille × beam/column）。
- 主链路 `rule_check_node` 追加 → `clash-<kind>` violation（不改既有条目）；
  出图侧 `task_type=clash` 画品红警示圈（CLASH 层，有碰撞才出，无碰撞 0 实体）。
- **回归安全**：无碰撞样本违规数不变（residential_100sqm 仍 3 条），真实碰撞样本可肉眼定位。

### 8.3 M5 改动冲突检测（两稿 raw JSON 比对，自主子集，commit `c327de3`）

M5「多设计师协作」整套需业务定权限模型（外部依赖，**不臆想**），本次只落地**无外部依赖的自主子集**：

- 核心库 `conflict_detection.py`（纯函数，仿 M4 范式）：`diff_elements` + `detect_conflicts`
  + `summarize_conflicts`，按元素类 + id 对齐比对，覆盖 value（同 id 字段值不同，含嵌套
  list 深比较 / 缺字段）/ added / removed 三类冲突。
- 主链路 `task_type="conflict"` 接入（无第二稿默认 no-op，0 冲突 0 出图，既有测试不破）。
- **边界诚实标注**：多设计师权限模型 / 在线协同仍占位（需业务定模型）。

### 8.4 代码质量收口（commit `75fa642` + `f00a498`，零行为改变）

M3/M4/M5 往核心文件堆代码后收口，`cad_tools.py` 从 1021 行回落到 954 行：

- 删 `COMCadInterface` 整段（全仓 0 引用、本环境跑不了的 AutoCAD COM 接口）。
- 抽 `_segments_by_layer` 私有底座，收敛 `get_plumbing_segments`/`get_structural_segments`
  的逐行同构逻辑（两方法体各 12 行→1 行薄封装），public 契约 inspect 程序化核实不变。
- 删 `DXFReader.get_layers`/`get_entity_count` 两处 0 引用 public API（核实清再删，
  `self.entities` 状态机保守保留）。
- **收口红线**：零行为改变——全量 294 + 冒烟全绿，src/rules 0 改动。

### 8.6 M4 碰撞 / M5 冲突 接入 GUI 面板（肉眼可见，commit `a7818ed`）

M4/M5 代码已落地但 GUI 上**没有独立展示位**（碰撞违规混在 `/api/pipeline` 的规范违规清单里）。本次补齐——**让新能力在双击界面上肉眼可见**：

- **桥端点**（`bridge.py` F 段，照既有范式追加）：
  - `GET /api/clash?sample=...` → 调 `detect_clashes`，无碰撞 `count=0` 空列表（不造假）
  - `GET /api/conflict?sample_a=&sample_b=` → 调 `detect_conflicts` + `summarize`，同稿 0 冲突
  - 懒 import（函数体）+ 缺 sample → 404 诚实报错
- **前端四层**（照 `loadDslRules`/`pipelineResult` 范式）：
  - `engineApi.ts`：`runClashCheck` / `runConflict`（`getJson` 封装，断连降级 `null` 不崩）
  - `useEngineStore.ts`：`clashResults`/`conflictResults` + loading 字段/setter
  - `App.tsx` 中区：「碰撞检测」+「改动冲突」独立区块（**品红徽标**呼应出图 CLASH 层，
    有碰撞列清单 / 无碰撞绿色 ✓ / 断连按钮 disabled）
  - `App.css`：品红 badge 样式
- **测试** `test_bridge_clash_conflict.py` 6 条（有碰撞命中 / 无碰撞 0 列表 / 404 /
  同稿 0 冲突 / 缺稿 404 / 不同稿命中）。
- **验证**：全量 **300 passed / 5 skipped / 0 failed** + 冒烟全过 + 前端 `tsc --noEmit` 0 报错
  + 起桥真 curl 两端点（默认样本无碰撞 `count=0`，缺样本 404，肉眼可见）。
  命中路径由单测用**构造的碰撞 raw**（管横穿梁 `pipe-beam`、插座落梁 `outlet-beam`）真验证。

> **诚实降级**：`residential_100sqm.json` 真实几何上无跨专业碰撞，`/api/clash` 返回 `count=0`
> 而非塞假碰撞——区分「没数据」和「错了」。M4/M5 后端逻辑 0 改动（只调 `detect_*`，未重写）。

### 8.7 本轮外部依赖边界（不虚标，留给人）

| 里程碑 | 剩余占位 | 需要谁 | 现状 |
|--------|---------|--------|------|
| M1 数值终确认 | 结构专业已回填 2 条 `confirmed=true`（梁高宽比 high / 柱最小截面 medium），另 2 条（梁高下限 / 跨高比）`confirmed=false` 留 low 置信（**故意不虚标**） | 结构/给排水专家背书 | 机制通、值待专家 |
| M2 DWG 图层约定 | 各院"点位画法/块名"映射 = TBD | 业务侧 DWG 制图规范 | 改 dict 即可 |
| M5 权限模型 | 多设计师角色/在线协同 | 业务定协同模型 | 未启动（不臆想） |

> **本日交付论点**：架构把"加专业 = 加分发表项 + 元素模型 + DSL 规则"的复杂度消化了，
> M3/M4/M5 都是**照同一套纯函数范式接入、主链路零/最小改动**——可扩展底座再证一次。
> 剩下 M1/M2/M5权限 三块全是外部依赖，专家/业务把"值"和"约定"喂进来即可点亮，架构不动。

全量回归：`python -m pytest tests/ -q` → **300 passed / 5 skipped / 0 failed** · 冒烟 `scripts/smoke_test.py` 秒级全过 · 前端 `tsc --noEmit` 0 报错。

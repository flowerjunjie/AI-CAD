# AI-CAD · 变更记录（CHANGELOG）

> 记录 Phase 0→3 + M3/M4/M5 已完成的里程碑。来源：git commit 演进史 + `run.py --no-llm` 全链路实跑结果。
> 生成日期：2026-09-27；最后同步：2026-09-30（M3 出图深化 + M4 碰撞 + M5 改动冲突 + exe 交付）

---

## 里程碑（一句话一条）

### Phase 1（MVP 补强）

- **f7b4f2d** — Phase 1 墙体厚度双线墙：`cad_tools.add_wall_thickness` 对每条墙在 CENTERLINE 图层生成 LWPOLYLINE 双线墙轮廓（含厚度标注），接入 `cad_rule_export` 主链路，主链路出图实体 12→49。
- **f87ec3f** — Phase 1 门窗编号（M1..M7 / C1..C5，OPENING_TAG 图层）+ 护栏测试稳定性（subprocess 串行 flaky 根治：单文件超时 300s + catch TimeoutExpired）。
- **20e83be** — Phase 1 人在回路：Agent interrupt 暂停 + 确认 API，非自动模式关键节点暂停等设计师确认。

### Phase 2（规则引擎完善）

- **adbc663** — Phase 2 规则引擎 DSL 化：批量校验 / 编辑器校验 / 版本 diff 三件套上引擎。
- **8731ea1** — Phase 2 规则编辑器面板（Electron 前端），设计师可视化改规则、无需改代码。
- **54967dd** — Phase 2 规则列表子面板保留源过滤 tab（hardcoded/dsl/all）。
- **87eb6c1** — Phase 2 规则写回落盘闭环：`/api/rules/dsl/apply` 人工确认闸（确认后写回 default.json），同 commit 完成 Phase 3 给排水出图接入主链路（`cad_tools.add_pipe`，PIPE 图层）。

### Phase 3（四专业出图 + 规范条文回填）

- **9379dd4** — Phase 3 结构（`add_beam`/`add_column`，BEAM/COLUMN 图层）+ 电气（`add_outlet`/`add_switch`，ELEC_OUTLET/ELEC_SWITCH 图层）+ 暖通（`add_hvac_*`，HVAC_* 图层）出图接主链路，复用 pipe/column 范式。
- **d162fc8** — Phase 3 给排水 2 条 TBD 规范条文回填：坡度区间（GB 50015-2019 第 4.5.6 条第 2 款，下限 0.0→0.4%，confidence: low）/ 检查井间距 25→12m（第 4.7.1 条第 3 款，confidence: medium）。

### M3 / M4 / M5（Phase 3 收口后 · 出图深化 + 碰撞/冲突）

> 这一段在 CHANGELOG「最后同步 09-28」之后发生——Phase 3 出图收口后，把「出图深化 → 多专业碰撞 → 改动冲突」三层能力逐层叠上，全程**纯增量**（不改既有实体/出图/测试，新增测试全绿）。

- **7eaecc0** — M3 制图惯例深化：线型/轴线/填充落地，出图观感对齐施工图习惯。
- **5d03251** — 规范数值回填（电气插座/接地 + 暖通室外机/风口 + 结构梁 2 条新增），低置信度如实标注 confidence。
- **fe8c770** — M3 出图深化收口：`DXFWriter._LAYER_STYLES`（22 图层 ACI 色号 + lineweight，配色按建筑/水/电/暖/结构制图惯例：墙白粗/水红/风蓝/结构绿/电黄）+ 幂等 `_ensure_layer_styles()`，经 `save()` 统一接入、主链路 0 改动。新增 `test_layer_style_dwg_export.py`（4 条），全量 264 passed。顺手修 smoke  hvac 风速样本 9.0→12.0（Phase 3 上限回填 10.0 后老断言假红）。
- **e057b09** — M4 多专业碰撞检测：纯几何库 `clash_detection.py`（`seg_intersect`/`point_to_seg_dist`/`detect_clashes`，8 类碰撞：管穿梁/插座撞梁/风管撞梁 等，严格相交——端点 T-touch 不算穿），接入 `rule_check_node`；出图侧 `add_clash_marker` 品红 CIRCLE+TEXT（CLASH 层）。`test_clash_detection.py` 17 条，全量 281 passed。
- **c327de3** — M5 改动冲突检测（自主子集）：纯库 `conflict_detection.py`（`diff_elements` 按元素 id 深比较 value/added/removed，`detect_conflicts` 全量比对 11 类元素，缺字段/空稿优雅跳过），主链路 `task_type=conflict` 最小接入（无第二稿默认 no-op）。`test_conflict_detection.py` 13 条，全量 294 passed。**边界诚实标注：多设计师权限模型 / 在线协同仍是占位（需业务定模型，不臆想）。**
- **75fa642 / f00a498** — 代码质量收口：删 COM 死代码 + 收敛线段读取重复；删 `DXFReader` 两处 0 引用 public API（`get_layers`/`get_entity_count`）。
- **a7818ed** — M4/M5 接入 GUI 面板（肉眼可见）：桥 `GET /api/clash` + `GET /api/conflict`（懒 import、无碰撞 count=0 不造假、缺样本 404 诚实报错）；前端 `engineApi.ts`/`useEngineStore.ts`/`App.tsx` 独立「碰撞检测」「改动冲突」区块（品红徽标）。`test_bridge_clash_conflict.py` 6 条，全量 300 passed + tsc 0 报错 + 起桥真 curl 两端点。
- **68806c6** — 重打包 exe 纳入 M4/M5：`HIDDEN_IMPORTS` 补 `clash_detection`/`conflict_detection`（懒 import 模块 PyInstaller 静态追不到）+ vite `emptyOutDir` 治本（outDir 在根外默认不清空→历史 bundle 虚胖）。`ai_cad_gui.exe` 43.6MB，verify_exe PASS，起 exe curl `/api/clash`+`/api/conflict` 均 200。
- **3422070 / 9cf0342** — 测试与质量护栏收尾：补 bridge 端点 + input_parser/wall_topology 测试（覆盖 78%→94%）；加 `.coveragerc` 门槛 90% + 外部依赖模块（graph/llm_adapter/rag_tools）豁免清单（需真实框架/LLM key/向量库，非漏测）。

### 人在回路 · session 级 + 真实 CAD 数据源（Phase 3 收口后）

> 三根线端到端：确认闸接通（#1）→ 前端确认闸 UI（#2）→ session 级真人在回路（#3）→ 确认闸透真实 CAD task 语义（本轮立项）。

- **人在回路 session 级打通**：graph 层 `start_agent_run_suspended` / `resume_agent_run`（外部持有 MemorySaver + thread，分「起图挂起 / 续跑」两步，不破坏 `run_agent_with_confirmation` 向后兼容）；bridge `POST /agent/run`（起真实图挂起 + 存 session + 真实 pending task）+ `/agent/confirm` 两级 resume（session 级同 thread 真续跑 / 演示级回退默认样本）。前端确认闸「起图挂起→逐 task 确认→同 thread 续跑」区块。
- **确认闸接真实 CAD 数据源（立项 docs/plan-confirm-gate-real-cad.md）**：`/agent/run` 把 `cad_execute_node` 已产的 `cad_results` 按 task_id join 成结构化 `pending[]`（task_id / type / description / 出图 result）+ 图面 `preview_url`，**纯 join 不重算**、老字段向后兼容；`_task_type_of` 从 raw_data/前缀反查 task 图元类型（查不到诚实 unknown）；前端确认闸从裸 task_id 升级为「id · 类型 · 描述」语义化 + 出图预览。数据在 `session["snapshot"]["cad_results"]`，零新数据源。
- 出图深化补 **柱截面填充**（`add_column(hatch=True)` + `COLUMN_FILL` 图层标准，同 `add_beam` HATCH 范式，梁/柱画法拉平）。
- 规则类分支覆盖补盲：`test_rules_branch_coverage.py` 27 条，把 5 个「低于 90% 的纯可测规则模块」（residential 采光/走廊/窗、fire_safety 走廊、accessibility 坡道）拉到 100%，总覆盖 93%→95%。

### 底座（Phase 0）

- **Phase 0 · 墙体厚度标注进主链路** — 见 f7b4f2d。
- **20abbde** — 四专业专家团收口：给排水/电气/暖通/结构各自补齐 e2e 测试、上游 attrs 闸、结构阈值回填。
- **f777285** — 单目录可执行交付物：PyInstaller onedir 打包 + 规范数值「填值即点亮」机制（`confirmed` 字段打通 UI 闭环）。
- **e9c0694** — GUI 一键入口：`start_gui.bat` 双击即开专业面板，vite 代理根治端口漂移。
- **0e724e7** — 前端整包 build 三处 blocker 修复，tsc + vite 全绿。
- **fcd094d** — 专业 GUI 落地：命令行升级为 Electron 桌面面板（5 域专家团交付）。

## 全链路跑通事实（`run.py --no-llm` 实跑验证）

- 规则引擎：**30 条**规范注册（ERROR 21 / WARNING 6 / INFO 3），实测 0.6m 户门检出违规。
- 户型解析：住宅 100㎡ 样本，7 功能区 / 7 门 / 5 窗，生成 12+ 个 CAD 任务。
- CAD 出图：DWG 生成成功，出图含 5 专业图层（建筑 CENTERLINE+OPENING_TAG / 给排水 PIPE / 结构 BEAM+COLUMN / 电气 ELEC_OUTLET+ELEC_SWITCH / 暖通 HVAC_*）。
- Agent 端到端：本地数据接线驱动，规范违规 2 条命中（户内门宽度、门窗碰撞），出 DWG + 报告。
- 四专业 extractor：`plumbing` / `electrical` / `hvac` / `structural` 全接入（上游 INSERT 底座 + N 专业映射）。
- LLM 适配器：**5 个**（Agnes 默认 / MiniMax / Kimi / GLM），统一 `LLMFactory` 接口。
- 全量测试：**352 passed / 5 skipped / 0 failed**（43 个测试文件：unit + integration，当前水位；Phase 0 收口时为 249/36，M3/M4/M5 逐层叠到 352/43，见上「M3/M4/M5」段各 commit 的实跑数）。
- M4/M5 出图：碰撞 `add_clash_marker` 品红 CIRCLE+TEXT（CLASH 层）、改动冲突 `summarize_conflicts` 人读汇总；GUI 面板「碰撞检测」「改动冲突」区块（品红徽标），桥端点 `/api/clash`、`/api/conflict`（无碰撞 count=0 不造假、缺样本 404 诚实报错）。

> 遗留隐患（已解除）：`test_direct_run.py` 护栏测试原靠 subprocess 串行直跑 20 个测试文件（timeout=120s），全量并发时 CPU 抢占偶发 flaky。已将单文件超时提到 300s + 显式 catch `TimeoutExpired` 打印超时文件，连跑 3 次全绿（20-30s/次）。

---

*一句话总结：Phase 0 底座 + Phase 1（墙体/门窗/人在回路）+ Phase 2（规则 DSL 化 + 编辑器 + 写回落盘）+ Phase 3（四专业出图 + 给排水 2 条 TBD 条文回填）+ M3 出图深化（图层着色/线宽）+ M4 多专业碰撞 + M5 改动冲突（自主子集，权限/协同仍占位）已全部收口，全程纯增量、新增测试全绿（352/43），架构把「加专业」的复杂度消化了，剩下的是各专业专家填数值和约定。*

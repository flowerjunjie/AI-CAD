# AI-CAD · 变更记录（CHANGELOG）

> 记录 Phase 0→3 已完成的里程碑。来源：git commit 演进史 + `run.py --no-llm` 全链路实跑结果。
> 生成日期：2026-09-27；最后同步：2026-09-28（Phase 3 收口）

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
- 全量测试：**249 passed / 5 skipped / 0 failed**（36 个测试文件：`tests/unit/` 32 + `tests/integration/` 4）。

> 遗留隐患（已解除）：`test_direct_run.py` 护栏测试原靠 subprocess 串行直跑 20 个测试文件（timeout=120s），全量并发时 CPU 抢占偶发 flaky。已将单文件超时提到 300s + 显式 catch `TimeoutExpired` 打印超时文件，连跑 3 次全绿（20-30s/次）。

---

*一句话总结：Phase 0 底座 + Phase 1（墙体/门窗/人在回路）+ Phase 2（规则 DSL 化 + 编辑器 + 写回落盘）+ Phase 3（四专业出图 + 给排水 2 条 TBD 条文回填）已全部收口，架构把「加专业」的复杂度消化了，剩下的是各专业专家填数值和约定。*

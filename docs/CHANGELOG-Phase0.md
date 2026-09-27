# AI-CAD · Phase 0 变更记录（CHANGELOG）

> 记录 Phase 0 已完成的里程碑。来源：最近 5 条 git commit + `run.py --no-llm` 全链路实跑结果。
> 生成日期：2026-09-27

---

## 里程碑（一句话一条）

- **Phase 1 · 墙体厚度标注进主链路** — `cad_tools.add_wall_thickness` 对每条墙在 CENTERLINE 图层生成 LWPOLYLINE 双线墙轮廓（含厚度标注），由 `cad_rule_export` 主链路调用，新增 4 个单测。主链路出图实体 12→49，规范违规 2 条命中不变。
- **20abbde** — 四专业专家团收口：给排水/电气/暖通/结构各自补齐 e2e 测试、上游 attrs 闸、结构阈值回填。
- **f777285** — 单目录可执行交付物：PyInstaller onedir 打包 + 规范数值「填值即点亮」机制（`confirmed` 字段打通 UI 闭环）。
- **e9c0694** — GUI 一键入口：`start_gui.bat` 双击即开专业面板，vite 代理根治端口漂移。
- **0e724e7** — 前端整包 build 三处 blocker 修复，tsc + vite 全绿。
- **fcd094d** — 专业 GUI 落地：命令行升级为 Electron 桌面面板（5 域专家团交付）。

## 全链路跑通事实（`run.py --no-llm` 实跑验证）

- 规则引擎：**30 条**规范注册（ERROR 21 / WARNING 6 / INFO 3），实测 0.6m 户门检出违规。
- 户型解析：住宅 100㎡ 样本，7 功能区 / 7 门 / 5 窗，生成 12 个 CAD 任务。
- CAD 出图：DWG 生成成功（4 线条 / 1 弧线 / 2 图层，19044 bytes）+ PNG 户型图渲染。
- Agent 端到端：本地数据接线驱动，规范违规 2 条命中（户内门宽度、门窗碰撞），出 DWG + 报告。
- 四专业 extractor：`plumbing` / `electrical` / `hvac` / `structural` 全接入（上游 INSERT 底座 + N 专业映射）。
- LLM 适配器：**5 个**（Agnes 默认 / MiniMax / Kimi / GLM），统一 `LLMFactory` 接口。
- 全量测试：**196 passed / 3 skipped**（28 个测试文件，含 Phase 1 墙体厚度 4 单测）。

> 遗留隐患（已解除）：`test_direct_run.py` 护栏测试原靠 subprocess 串行直跑 20 个测试文件（timeout=120s），全量并发时 CPU 抢占偶发 flaky。已将单文件超时提到 300s + 显式 catch `TimeoutExpired` 打印超时文件，连跑 3 次全绿（20-30s/次）。

---

*一句话总结：Phase 0 预研 + Phase 1~6 四专业接入的底座已全部跑通，架构把「加专业」的复杂度消化了，剩下的是各专业专家填数值和约定。*

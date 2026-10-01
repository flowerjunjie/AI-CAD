# 立项：确认闸接真实 CAD 数据源（人在回路最后一公里）

> 立项日期：2026-09-30 · 优先级：高（P8 级功能，非"改文件"）
> 关联：#1/#2/#3 已把"人在回路确认闸"推到 **session 级真人在回路**
> （起真实图挂起 → 逐 task 确认 → 同 thread 真续跑）。本文档解决**最后一公里**。

---

## 一、立项背景 & 现状盘点（事实驱动，不拍脑袋）

### 已经通了什么（#1→#3 的成果，别重复做）

| 层 | 现状 | 证据 |
|----|------|------|
| graph 层 | `interrupt`+checkpointer 暂停/resume 就绪 | `test_agent_graph.py`（`AI_CAD_RUN_FRAMEWORK=1`）|
| graph 层 session API | `start_agent_run_suspended` / `resume_agent_run`（外部持有 saver+thread）| `graph.py` + 实跑拿 6 真实 pending（door-entrance 等）|
| cad_execute_node | 产**真实 CAD task**（task_id 来自样本 task_list）+ `cad_results` + `human_confirmations` | `cad_rule_export.py:410` |
| bridge `/agent/run` | 起真实图挂起，存 session + 登记真实 pending task | `bridge.py:634` |
| bridge `/agent/confirm` | 有 session 时**同 thread 真续跑**（`resume.session=true`）| `bridge.py:624` |
| 前端 | "起图挂起"按钮 + 真实 task 下拉 + 逐 task 确认 | `App.tsx` 确认闸区块 |

### 真实的 gap（本立项要补的最后一块）

**`/agent/run` 现在只回 `pending_task_ids`（纯 task_id 字符串）。设计师看到的是一串 `door-entrance / door-room-0` 裸 id——他不知道：**

1. **这个 task 是什么**（门？窗？梁？）—— `cad_results` 里有 `task_type`/`description`，没透出
2. **它画在图面哪个位置** —— 出图 `final_dwg_path` 的 PNG 预览没和"待确认 task"关联起来
3. **放行后到底出了哪些图元** —— `cad_results` 的 `count`/图元明细没进确认流程

**根因**：`/agent/run` 直接把 `pending_task_ids` 字符串原样吐出，没把 `cad_execute_node` 已经产好的 `cad_results`（含 task 语义）**结构化 join 进响应**。数据在 `session["snapshot"]["cad_results"]` 里躺着，就差最后一根线没接。

> **诚实边界**：这不是"人在回路没做完"——机制已通到 session 级。这里补的是**"让设计师看得懂待确认项"的展示/数据透出层**，是产品最后一公里，不是架构缺口。

---

## 二、技术方案（最小改动，复用现有，不推倒重来）

### 核心改动（1 个函数 + 类型 + 前端渲染）

**改动 1：`bridge.agent_run` 把 `cad_results` join 进响应**（最小）

现状 `/agent/run` 返回：
```json
{ "thread_id": "...", "pending_task_ids": ["door-entrance", ...], "pending_task_count": 6, "cad_result_count": 17 }
```

改为返回**结构化的 pending 详情**（数据已在 `session["snapshot"]["cad_results"]`，纯 join，不重算）：
```json
{
  "thread_id": "...",
  "preview_url": "/api/preview?sample=residential_100sqm.json",
  "pending": [
    {
      "task_id": "door-entrance",
      "type": "door",
      "description": "入户门 出图",          // 来自 cad_results / task_list.description
      "result": { "status": "pending_confirm", ... },
      "element_summary": "门 1 樘 @ (x,y)"    // 可选：从 raw_data 位置摘出
    }
  ],
  "pending_task_count": 6,
  "cad_result_count": 17
}
```

**关键点**：`pending_task_ids` 和 `cad_results` 都挂在 `session["snapshot"]` 里（`cad_execute_node` 一次性产出的），`agent_run` 只需**按 task_id join** 这两个已存在的结构——**零重算、零新数据源**，纯"把已有数据结构化透出"。

### 改动 2：前端 `App.tsx` 确认闸区块渲染 pending 详情

- task 下拉从"裸 id"升级为 `「door-entrance · 门 · 入户门出图」`
- 放行后展示该 task 的 `cad_results` 明细（出了几樘门 / 什么图元）
- "起图挂起"时关联 `preview_url`，设计师能对照图面看每个待确认 task

### 改动 3：`engineApi.ts` 类型 `AgentRunResult` 加 `pending[]` 结构

---

## 三、任务拆解（原子提交，每步可验证）

| 步 | 内容 | 验证标准 |
|----|------|---------|
| **T1** | `bridge.agent_run` 把 `cad_results` 按 task_id join 进 `pending[]`（含 type/description/result）| 新测试：`/agent/run` 响应含 `pending[]`，每项 `task_id` 与 `pending_task_ids` 对齐、`type` 正确、`description` 非空 |
| **T2** | 前端 `AgentRunResult` 加 `pending[]` 类型 + `App.tsx` 确认闸渲染 task 详情 + 关联 preview | 前端 `tsc+vite` build 全绿；面板肉眼可见 task 语义（非裸 id）|
| **T3** | 放行后展示该 task 的 `cad_results` 出图明细 | `/agent/confirm`（session 级）响应里带该 task 的出图结果，前端渲染 |
| **T4** | 全量回归 + 文档同步（capability-map 人在回路条目、DELIVERY）| 全量绿（当前 386 为基线）|

**TDD 顺序**：T1 先写测试（`/agent/run` 结构化响应断言）→ 实现 → 绿；T3 同理。

---

## 四、风险 & 边界（蓝军自检，先想在哪炸）

| 风险 | 应对 |
|------|------|
| `cad_results` 的 task_id 与 `pending_task_ids` 对不齐（门 task 才挂 confirmations，非门 task 是 completed）| join 时**只取 `status == "pending_confirm"` 的**，非待确认 task 不进 `pending[]`；对不齐就诚实留空，不造假 |
| 改了 `agent_run` 返回结构，破坏现有 3 条 session 测试（`test_agent_confirm_wiring.py`）| **加字段不删字段**：`pending_task_ids`/`pending_task_count` 原样保留（向后兼容），只**追加** `pending[]`。老测试断言的字段不动 |
| 前端类型加 `pending[]`，现有渲染没读它 | 新增字段前端按需渲染，不碰既有逻辑；build 验证 |
| 描述/位置数据源不一致（task_list vs cad_results vs raw_data）| **单一数据源原则**：type/description 取自 `cad_results`（cad_execute_node 已产好），不从 raw_data 二次算 |
| 范围蔓延（想顺手做"多设计师协同"）| **本立项只做"数据透出 + 展示"**；权限/协同模型仍是外部依赖占位，不夹带 |

**红线**：不加新外部依赖；不重算已有数据；向后兼容（老字段保留）；全量回归绿才算收口。

---

## 五、验收标准（Definition of Done）

- [x] `/agent/run` 响应含 `pending[]`（每项：task_id / type / description / 出图 result），且与 `pending_task_ids` 对齐
- [x] 向后兼容：`pending_task_ids` / `pending_task_count` / `cad_result_count` 原字段仍在（老测试不破）
- [x] 前端确认闸 task 下拉显示**语义**（「id · 类型 · 描述」），非裸 id；放行后可见该 task 出图明细
- [x] 前端 build 全绿；全量测试绿（立项时基线 386 passed → 落地后 388 passed，+2 条 T1 新测试）
- [x] capability-map「人在回路」条目 + DELIVERY 同步到"确认闸已透出真实 CAD task 语义"
- [x] 诚实边界守住：没把"多设计师协同"塞进来（那仍是占位）

---

## 六、不做什么（明确划界）

- **不做**多设计师权限/在线协同模型（外部依赖，需业务定）
- **不做** LLM 介入确认（那是另一个能力，确认闸是纯几何/规则域）
- **不做** CAD 出图逻辑本身的改动（`cad_execute_node` 产的 `cad_results` 已够用，只 join 不改产）

---

*本文档是"确认闸接真实 CAD 数据源"的立项，颗粒度到"改哪个函数、加什么字段、写什么测试"。执行按 T1→T4 原子推进，每步全量回归。*

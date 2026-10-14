# 借鉴落地 · 假阴性审计（M1 占位值防漏判）

> 来源：GitHub 同构项目 `2sellyogurt/AI-CAD-Audit-System` 的
> `v7/audit/false_negative_auditor.py`（10★，2026-06 停更，**思想参照，不抄代码**）。
> 本文只写"搬到我们项目的设计 + 为什么这么搬"，**未动主仓代码**（原因见末段）。

## 它做了什么（读源码实查，非照二手描述）

`FalseNegativeAuditor.audit()`：
1. **只抽"原判=合规/通过"的结论**（假阴性定义：该报违规却报通过了）
2. 抽 `sample_rate=10%`，`random.seed(审计周期时间戳)` → **可复现**
3. 每个样本用**独立引擎重判一次**；`原判合规 & 复核不合规` → 记为假阴性
4. 假阴性率 > `threshold` → **熔断建议全量重审** + 给"高频漏判点 TOP5"
5. 历史报告累积 → 季度趋势（平均/最高/最低假阴性率）

## 关键判断：哪些搬、哪些不搬（对着我们真实模块核验过）

**搬的（思想骨架，与我们 verify_* 范式同源）**：
- "抽通过结论 → 双跑 → 报假阴性"这个**方向**——正补我们 M1/M2 的盲区
  （现在只报"检出多少"，不报"该检出却没检出的"）
- **可复现随机 seed + 假阴性率阈值熔断 + 高频漏判 TOP5**（干净可直接用）

**不搬的（读源码才发现的坑，二手描述没点破）**：
- 它双跑靠 **`engine.execute_one(cp, drawing_text)` = LLM/VLM 重审文字**（源码 L119/L126）。
  我们的 **M4 碰撞是纯确定性几何**（`detect_clashes`：线段相交 + 点到线段距离≤容差，
  `clash_detection.py:172-236` 无 LLM/阈值判定）——**几何没判对是代码 bug（测试会炸），
  不是概率性漏检**。给确定性几何做"假阴性双跑" = 造一个不存在的"LLM 重审几何"机制，
  违反 CLAUDE.md 诚实边界（不虚标）。**M4 不做假阴性审计，只可做"完整性审计"**
  （报"哪些图层/元素根本没进检测"，是完备性问题非概率问题）。

## 正确的移植落点：M1 占位值判定（不是 M4）

核验 `plumbing_extractor.py:18-23`：`PIPE→50mm / PIPE_WASTE→110mm` 全是
`# TBD 占位`。规则引擎拿这个**占位值**判"管径合规"——**若占位值恰好让本该违规的
图纸通过了，就是假阴性**。这才有真假阴性风险。所以审计器接 M1，不接 M4。

**设计（对齐项目既有范式，最小改动）**：
- 新增 `src/agents/src/tools/audit/`（新目录，仿 `verify_*` 独立模块）
  `audit_placeholder_verdicts.py`，纯函数、无 I/O（红线：不碰 ezdxf/langgraph）。
- 入参：`verdicts`（本轮 M1 规则判定结果，每条带 `{rule_id, verdict, source_value,
  is_placeholder}`）+ `rechecker`（可选 callable，缺省=用当前值重判）。
- 出参：`{passed_sampled, false_negatives, fn_rate, threshold_breached,
  top_missed_rules}` —— **JSON 可序列化**（呼应全仓 verify_* 范式）。
- 可复现：`random.seed(period_stamp)`；`fn_rate > threshold` 才给"建议全量重审"。
- 诚实边界：**只统计/标记，不自动改占位值**（占位值回填决定权在专家，CLAUDE.md 红线）。

## 为什么不现在写代码（判断，不是偷懒）

M1 占位值**全 open 未回填**（见 `pending-backfill-checklist.md`）——现在接审计器，
`rechecker` 没有真值可比（全是占位），审计跑出来全是"占位 vs 占位"，**空转**。
按 `guardrail-roi-curve` 判据：**等 M1 有第一批专家回填值后再接，那时才有真"通过结论"
可抽、有真"假阴性"可统计**。本设计先行，接时照它落，省架构试错。

## 待办（M1 回填首值后触发）

- [ ] M1 至少 1 组占位值回填为专家真值 → 接 `audit_placeholder_verdicts`
- [ ] `/api/rules/...` 加端点透出 `fn_rate` 诊断（仿 `verify_*` 失步才留痕范式）
- [ ] 前端"规则审计"区显假阴性率（失步才显，正常静默，同 P12 范式）
- [ ] M4 做**完整性审计**（报"未纳入检测的图层/元素"）——这是另一条，非假阴性

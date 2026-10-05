# 测试水位 · 单一事实源

> **本文是「当前测试水位」的唯一权威出处。** 推测试水位只改这一处。
> 其他文档（DELIVERY.md / capability-map.md / INDEX.md / README.md）的
> 「当前测试数字」一律**引用本文**，不再各自硬编码（根治历史散落 281/409/419 的同类坑）。
>
> **历史演进记录**（带「本轮基线 / 立项时 / 改前基线」时间戳的段落）
> 是审计痕迹，**不随本文改**——它们是"当时"的水位，不是"当前"。

## 当前水位

```
python -m pytest tests/ -q   →   505 passed / 5 skipped / 0 failed
```

- **测试文件**：50（49 unit + 4 integration；含文档水位护栏 test_doc_test_waterlevel 5 测试）
- **5 skipped**：外部依赖用例（4 条 langgraph 框架需 `AI_CAD_RUN_FRAMEWORK=1`；
  1 条 LLM 需 `AGNES_API_KEY`），非缺陷。
- **冒烟**：`python scripts/smoke_test.py` 秒级验 5 大核心不变量。
- **覆盖率**：`.coveragerc` `fail_under=90`。
- **数字纠偏 (2026-10-04)**：趋势表 504/513/520/536/546 一段为历轮「上轮+增量」
  推得的水位, 其中 546 那轮全量后台实测输出被 Git-Bash fork 报错吞掉未拿到真数字即回填。
  本轮实跑全量 = **505 passed / 5 skipped / 0 failed** (510 collected − 5 skipped) 为权威;
  自 504 起的历史行保留为演进审计, 但**当前水位以本轮实跑 505 为准, 不再向上推**。

## 刷新方法（推水位后跑这条）

```bash
# 1. 实跑拿权威数字
python -m pytest tests/ -q 2>&1 | tail -1
# 2. 把上面那行数字填进「当前水位」代码块 (只改 452 这处, 别碰历史段落)
# 3. 往「水位趋势」表尾追加一行 (日期 + passed + 触发 + commit), 绝不回改历史行
```

**约定**：CI / 收口 commit 前，把实跑数字回填到本文「当前水位」段；
**绝不**把带时间戳的历史段落（如 DELIVERY 第 250 行"数据截止 2026-09-30 … 409"）当活数字改。

## 水位趋势（历史快照，带 commit 锚点，不随当前水位改）

> 每条 = 某次推水位时的快照，**必须带 commit 短哈希 + 日期**（这是护栏认得
> 出「历史段落」的特征：带 commit 锚点的活数字放行，不判成裸活数字）。
> 推水位时**往表尾追加一行**，绝不回改历史行（那是审计痕迹，改了造假）。

| 日期 | passed | 触发 | commit | 备注 |
|------|-------|------|--------|------|
| 2026-09-30 | 409 | 人在回路 session 级 + M5 权限/协同骨架 | `4812064~`* | 打包交付基线（历史锚点，见 DELIVERY §250 行） |
| 2026-10-03 | 447 | M5 duplicate 出图 + M1 回填 + M2 扫描 + 两轮联动 | `4812064` | 文档同步收口水位 |
| 2026-10-03 | 451 | + 文档水位单一源护栏（test_doc_test_waterlevel 4 测试） | `1a38ba9` | 单一事实源 + 回归护栏 |
| 2026-10-03 | 452 | + 水位趋势表护栏（test_doc_test_waterlevel 5 测试） | `40b5911` | 趋势表带 commit 锚, 护栏认历史快照 |
| 2026-10-04 | 504 | M5 协同正确性地基: verify_event_log 事件日志/锁态自洽校验 + detect_deadlock 等待环检测 (机制层纯函数 + /api/collab/verify + /api/collab/deadlock-check + 端点测试) | `4612205` | 机制层自主子集 (不需外部专家), 非多机一致 |
| 2026-10-04 | 513 | M5 冲突输出自洽校验: conflict_detection.validate_conflicts (结构对称性) + verify_summary (汇总对账) 纯函数 + /api/conflict 透出 summary_consistent 诊断 | `4cb41d3` | 机制层自主子集, 汇总/列表失步不静默穿透 UI |
| 2026-10-04 | 520 | M4 碰撞结果自洽校验: clash_detection.verify_clashes (a_id≠b_id / kind 合法 8 类 / id 在 raw) + CLASH_KINDS 常量与出图侧 label 同源对账 + /api/clash 透出 clashes_consistent 诊断 | `e84f6f9` | 机制层自主子集, 脏碰撞不静默进 DWG 出假圈 |
| 2026-10-04 | 536 | M5 死锁端到端接线: collab_protocol wait-edge 采集层 (record_wait/clear_waits_for, 取锁被拒记 wait / 成功·放锁清) + check_deadlock_from_state 读真实 state.waits 喂 detect_deadlock + /api/collab/deadlock 端点 | `eb7dcd4` | 机制层自主子集, 死锁检测落到真实锁流程 (非仅提交版) |
| 2026-10-04 | 546 | M5 权限矩阵结构自洽校验: permission_model.validate_permissions_matrix + check_action_format (动作命名 <资源>.<动作> / 值类型 / 无重复 / 角色命名) + /api/permission/matrix 端点 (业务回填畸形矩阵前置报异味) | `f9acfcd` | 机制层自主子集, 只校验结构不判业务值 |
| 2026-10-04 | 505 | UI 体验优化 (纯前端, 无 Python 测试增减): App.tsx 协同区块抽 CollabPanel 子组件 (主操作/诊断分层) + 占位卡 m5-collab/m5-team 去重。数字纠偏: 实跑全量权威值, 回退 546 虚高 (上轮后台实测被吞) | `4ecf5b2` | 当前权威水位以本轮实跑 505 为准 |
| 2026-10-05 | 505 | UI 体验优化第二批 (纯前端, 测试数字稳定): P2 出图双通路文案区分 + P4 结果可回溯(清空/最新标注/删 collabOps 死代码) + P10 刷新预览改名 + P5 断连显式错误态。前端 tsc/build 过, 引擎全量实测仍 505 (无回归) | `4d99761` | 纯前端轮, Python 测试水位不变 |
| 2026-10-05 | 505 | UI 体验优化第三批 (纯前端, 测试数字稳定): P5 静默失败泛化 — 提炼通用 fetchError 态 + header 统一错误横幅, 8 个 getJson/postJson 端点 (出图/检索/扫图层/协同/校验/死锁/矩阵) 断连→null 全接入, 不逐区块铺。tsc/build 过, 引擎全量实测仍 505 (无回归) | `03b8d28` | 纯前端轮, Python 测试水位不变 |
| 2026-10-05 | 505 | UI 体验优化第四批 (纯前端, 测试数字稳定): P8 loading 文案统一 (拉元素/取锁/放锁 …→取锁中…) + P9 占位卡行动指引 (可推动/待外部 + 去哪操作) + P11 占位卡「去回填→」跳 DSL 编辑器定位前缀。起桥验 3 前缀命中真实 DSL 规则, 全量实测仍 505 (无回归) | `87e06f6` | 纯前端轮, Python 测试水位不变 |

\* 早期 commit 短哈希已不在当前 git 历史精确映射（演进史见 DELIVERY §七/§八），
趋势表只锚定「日期 + 数字 + 触发点」，历史精确 commit 以 DELIVERY 带日期段落为准。

*最后刷新：2026-10-05 · 505 passed / 5 skipped / 0 failed（UI 体验优化第四批: P8/P9/P11 纯前端, 引擎全量实测稳定 505 无回归）*

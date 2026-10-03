# AI-CAD · 一页纸能力地图（展示用）

> 给决策者/投资人的一页总览。**已实现**用实心 ✅，**待专业专家补**用占位 ▢，一眼看清实力边界。
> 配套：`DELIVERY.md`（详细交付报告）+ `output/preview.png`（LLM 出图）+ `run.py --llm --render`（可亲手跑）。

## 核心实力（一条横线看懂"兼容并蓄 + 可扩展"）

```
            一个引擎底座 · 五个专业照同一范式接入 · 主链路零改动
   ┌──────────────────────────────────────────────────────────────────┐
   │  规则 DSL 引擎（受限 eval + 信任边界护栏）                          │
   │        │                                                        │
   │   加分发表项 + 元素模型 + DSL 规则 = 加一个专业                    │
   │        │                                                        │
   │  ┌─────┴─────┬──────────┬──────────┬──────────┐               │
   │  │ 建筑本体   │ 给排水    │ 电气      │ 暖通     │ 结构          │
   │  │ 30 规则类  │ 3 DSL   │ 3 DSL    │ 3 DSL    │ 2 DSL        │
   │  │ 墙/门窗几何 │ 管径/坡度 │ 插座/开关 │ 风管/风口 │ 梁/柱        │
   │  │   ✅      │   ✅     │   ✅      │   ✅      │   ✅         │
   └──────────────────────────────────────────────────────────────────┘
```

## 能力清单（✅ 已通 / ▢ 占位待补）

```
  工程底座（全部实跑验证）
  ✅ 规则引擎         30 硬编码类 + 18 DSL 规则, 命中/放行/参数覆盖
  ✅ 多专业接入        给排水/电气/暖通/结构 四专业全通 (当前测试水位见 README)
  ✅ 上游 DWG 解析     一份 INSERT 底座 + N 专业映射 (无孤儿模块)
  ✅ LLM Agent        LangGraph 全链路, --llm/--no-llm 双路径可验
  ✅ 出图 + 校验        DWG 生成 + 5 专业出图(建筑/给排水/结构/电气/暖通) + PNG 户型图渲染
  ✅ RAG 规范库        ChromaDB 本地, 数据不出境
  ✅ 规则写回落盘       /api/rules/dsl/apply 人工确认闸 → 写回 default.json (Phase 2)
  ✅ M1 数值回填 CLI    scripts/backfill_rule_values.py + /api/rules/backfill 单规则写盘
                     (专家定值 → default.json → 点亮占位卡, 一行命令 / GUI 面板点「回填」, 零代码)
  ✅ M2 制图约定对齐工具  dwg_layer_scan 扫真实 DXF → 图层/块名/ATTRIB 频率报告 (CLI + GUI「扫图层」按钮,
                     把「各院 DWG 图层/块名映射」从填空题变选择题)
  ✅ M4 碰撞容差取值通道  clash-tolerance-range DSL 规则 + resolve_clash_tolerance 优先级
                     (param>default>几何默认), 专家改 JSON params.clash_tolerance_m 即调参零代码;
                     取值来源透出 /api/clash + /api/rules (M4 容差→M1 卡联动)
  ✅ M5 冲突几何等价类   同坐标不同 id = 疑似重复元素 (detect_duplicate_elements, M5 扩展维度);
                     出图侧 add_duplicate_marker (DUP 琥珀圈, 与 M4 碰撞品红圈区分)
  ✅ M5 协同+duplicate 联动  /api/collab/elements 吐真实 CAD 元素 id + 重复标记, 协同面板取锁前
                     疑似重复琥珀色提示 (只提示不禁止, 业务归属由专家定); 本地锁演示已接桥+GUI

  待各专业专家补（占位, 机制已通、值待定）
  ▢ 规范数值          给排水/结构 已回填(GB 50015/50010/50011, confidence low~medium); 电气/暖通 部分占位
                     (M1 回填 CLI/GUI 已就位, 专家定值改 JSON 即点亮, 不虚标终值)
  ▢ DWG 图层约定      各院"点位画法/块名"映射 = TBD (M2 扫描工具可辅助决策, 定稿仍需业务)
  ✅ 出图深化          图层着色(23 层 ACI+线宽, 含 COLUMN_FILL) + DASHED/CENTERLINE 线型
                     + 梁/柱截面实填充(HATCH) 已落地 (M3 图层着色/线宽/梁填充 + 本轮补柱填充)
  ✅ 多专业碰撞检测    管线穿梁/插座撞梁/风管撞梁 自动检测 (M4, clash_detection 几何库 + 主链路 + 出图红圈
                     + 容差取值通道 param>default, confirmed=true 点亮 M4 占位卡)
  ✅ 改动冲突检测     两稿 raw JSON 按元素 id 比对 (M5 自主子集, conflict_detection 纯函数库)
                     + 几何等价类维度 (同坐标不同 id = 疑似重复, 出图 DUP 琥珀圈)
  ✅ 人在回路       session 级真人在回路: 起真实图挂起 (/agent/run) → 逐 task 确认 → 同 thread 真续跑
                     (graph interrupt+checkpointer + start_agent_run_suspended/resume_agent_run, 前端确认闸区块)
                     已透真实 CAD 数据源: /agent/run 把每个待确认 task 的类型/描述/出图结果 + 图面预览透出
  ◑ 团队协作          机制骨架已通: 角色→权限→资源锁→改动审批→合并 (permission_model 纯函数库,
                     11 测试); 具体角色/权限矩阵值 = 占位配置 (DEFAULT_PERMISSIONS, 需业务定夺回填)
                     在线协同持久层协议已起骨架: 锁/事件持久化 + 事件溯源 + 跨进程快照 (collab_protocol,
                     10 测试, JSON 存储可注入); 本地锁演示通路已接桥+GUI: /api/collab/snapshot +
                     /api/collab/acquire|release (本地单进程演示, 非跨设计师同步; 真·多机在线协同
                     socket/消息总线/CRDT 仍占位, 需业务定协同协议)
                     collab-lock-integrity DSL 规则 confirmed=true 点亮 M5 协同占位卡 (机制已落地, 不虚标)
```

## 一句话实力证明（数据背书）

```
  当前测试水位单一事实源: docs/test-status.md (推水位只改那一处, 本文不再硬编码)
  · 5 专业 · 18 DSL · 30 硬编码类 · M3 出图深化 + M4 碰撞检测 + M5 duplicate
  加一个新专业 = 改 JSON + 元素模型 + 分发表一项, 主链路循环体 0 行改动
  各专业专家"确认数值 + 定约定"即可点亮对应专业, 无需写核心代码
```

## 路线图（点亮顺序）

```
  已达成                              下一步（不需重写架构, 逐个点亮）
  Phase0-1 预研→MVP(墙厚/门窗/人在回路)  M1 数值终确认  ← 各专业专家 (M1 回填 CLI/GUI 已就位)
  Phase2   规则DSL化+编辑器+写回落盘     M2 图层约定    ← 各院制图规范 (M2 扫描工具辅助决策)
  Phase3   四专业出图+给排水条文回填     M3 出图深化    ← 图层着色+线宽标准 (✅ M3 已落地)
                                               M4 碰撞检测    ← 管线/电气/暖通 × 结构 (✅ M4 已落地 + 容差取值通道 → M1 卡)
                                               M5 团队协作    ← 改动冲突 ✅ (含几何等价类出图) / 本地锁演示 ✅ + duplicate 联动
                                                                 (权限模型+在线协同占位)
```

---
> **展示话术**：架构已证明"多专业可扩展"的底座是真跑通的（四专业出图、LLM 出图、session 级人在回路、M5 duplicate 联动，测试水位见 [README](../README.md)「测试与质量」段）。
> 剩下的不是"能不能做"，而是"各专业专家把数值和约定填进来"——**架构把复杂度消化了，专业价值留给专业的人。**

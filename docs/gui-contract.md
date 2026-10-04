# AI-CAD 专业 GUI · 共享契约 (专家团作战地图)

> 本文件是所有专家团的**唯一接口基准**。谁先动谁就按这份写，不许猜接口。
> 目标：把"黑框命令行"升级成专业级 Electron 桌面 GUI —— 已实现的能力真驱动 Python 引擎，
> 未实现的能力置灰卡片 + 操作说明 + 所属专业，诚实标注不造假。

## 0. 顶层架构

```
[ Electron 主进程 ]────IPC────[ React 前端 ]
        │  起子进程                     │  fetch /api/*
        ▼                              ▼
[ Python FastAPI 桥  ]  ──驱动──>  真实 Python 引擎
   src/gui/bridge.py              (规则引擎 / LangGraph Agent / RAG / 渲染)
```

- **前端**：仓库里已有 `src/client/` (React + Electron + zustand + three)。升级它的 `App.tsx`，
  把写死的占位数据换成**真调本地 FastAPI 桥**拿到的数据。开发模式 `localhost:3000` 由 vite 起。
- **桥**：新建 `src/gui/bridge.py`，用 FastAPI + uvicorn，`http://127.0.0.1:8642`，CORS 放行 `localhost:*`。
  它是 GUI 唯一的引擎入口，**已实现能力全部从它出数据**。
- **入口**：`start_gui.bat`（纯 ASCII）起 uvicorn + 拉起 electron；失败兜底 `start_gui.py`。

## 1. FastAPI 桥接口契约 (Python, src/gui/bridge.py)

| 方法·路径 | 请求 | 响应 (JSON) | 底层来源 (已实现) |
|---|---|---|---|
| `GET /api/health` | – | `{"status":"ok","phase":"Phase 6","modules":{"rules":n,"dsl":m,"rag":bool,"llm":bool}}` | get_engine().list_rules() 计数 |
| `GET /api/rules` | – | `[{rule_id,name,code_ref,severity,source,enabled,confirmed,tolerance_source,tolerance_m}]` source∈{hardcoded,dsl}; tolerance_source 仅 clash-tolerance-range 规则带值 (M4 容差→M1 卡联动), 其余 null | engine.list_rules() + DSL + resolve_clash_tolerance |
| `POST /api/pipeline` | `{"sample":"residential_100sqm.json","use_llm":false}` | `{"project_type","zones":[{name,type,area}],"task_count","violations":[violation],"dwg_path","preview_url"}` | run_agent_demo(inject_sample_structure=not use_llm) |
| `GET /api/preview?sample=residential_100sqm.json` | – | 直接返回 PNG bytes (Content-Type image/png) | render_and_open 逻辑抽成只渲染不弹窗 |
| `GET /api/rule-violations` | – | 全量规则实测违规演示 `[{...}]` | engine.check([bad elements]) 演示 |
| `POST /api/rag/search` | `{"query":"疏散走道最小宽度"}` | `{"query","results":[{text,score,category}]}` | RAGKnowledgeBase.search (本地 chroma_db) |
| `POST /api/rules/backfill` | `{rule_id, confirmed?, confidence?, confirm_note?, params?}` | `{status:'applied', backup, confirmed, confidence, param_defaults}` (M1 数值回填 GUI 入口, 单规则写盘+备份+fail-fast; confidence 白名单 low/medium/high 不虚标; 未知规则 404) | default.json 单规则写回 (比 DSL apply 全量重写轻) |
| `GET /api/clash?sample=&tolerance_m=` | – | `{sample, tolerance_m, tolerance_source, clashes:[{a_id,b_id,kind,detail}], count, clashes_consistent, clashes_issues}` | clash_detection.detect_clashes (M4, 容差取值通道 param>default); clashes_consistent/clashes_issues = verify_clashes 机制层对账诊断 (a_id≠b_id + kind 合法 8 类 + id 在 raw, 失步不静默进 DWG 出图) |
| `GET /api/conflict?sample_a=&sample_b=` | – | `{sample_a, sample_b, count, by_category, conflicts:[...], summary{value_conflicts,added,removed,duplicates}, summary_consistent, summary_issues}` | conflict_detection.detect_conflicts (M5 两稿比对 + 几何等价类 duplicate 维度); summary_consistent/summary_issues = verify_summary 机制层对账诊断 (summarize 计数 vs 列表是否自洽, 失步不静默穿透 UI) |
| `GET /api/collab/elements?sample=` | – | `{sample, resources:[{id,category,duplicate_of,coord}], duplicate_count}` | 真实 CAD 元素 id 清单 + 重复标记 (M5 协同+冲突联动, 取锁前看疑似重复) |
| `GET /api/collab/snapshot?designer=` | – | `{designer, write_holders, recent_events, event_count, source}` | collab_protocol.make_snapshot (M5 持久层, 只读) |
| `POST /api/collab/acquire` | `{designer, resource_id, mode}` | 快照 + `{acquired, reason}` (本地锁演示, 非跨设计师同步) | collab_protocol.persistent_acquire |
| `POST /api/collab/release` | `{designer, resource_id}` | 快照 + `{released}` (幂等, 无锁释放→false) | collab_protocol.persistent_release |
| `GET /api/collab/verify` | – | `{valid, issues, replayed_write_holders, source}` | collab_protocol.verify_event_log (M5 协同正确性地基: 事件日志 seq 连续 + 字段完整 + 锁态可回放对齐, 机制层纯判定, 非多机一致) |
| `POST /api/collab/deadlock-check` | `{wait_edges:{holder:target}}` | `{deadlocked, cycle}` | permission_model.detect_deadlock (等待环检测, 三色 DFS; 键值须字符串否则 400; 机制层纯判定) |
| `GET /api/collab/deadlock` | – | `{source, deadlocked, cycle, wait_edges}` | collab_protocol.check_deadlock_from_state (真实锁流程版: 读 state.waits 由 persistent_acquire/release 采集的 wait-edges 投影喂 detect_deadlock, 交叉取锁被拒→环; 缺 state → 空态 deadlocked=false source=empty) |
| `GET /api/permission/matrix` | – | `{roles, valid, issues, malformed_actions}` | permission_model.validate_permissions_matrix (M5 权限矩阵结构自洽校验: 动作命名 <资源>.<动作> / 值类型 / 无重复 / 角色命名; 只查结构不判业务值, 业务回填畸形矩阵前置报异味) |
| `GET /api/dwg-scan?sample=X.dxf` | – | `{sample, layers, entity_type_totals, attrib_tags, layer_count, insert_total}` | dwg_layer_scan (M2 制图约定对齐工具, 图层/块名/ATTRIB 频率报告, 不判定 kind 归属) |

**M2 制图约定对齐工具 (离线 CLI + GUI 双通路)**：
- 离线 CLI：`python scripts/dwg_layer_scan.py <dxf>` → 图层 × 实体类型 × INSERT 块名 × ATTRIB 频率 JSON 报告。
- GUI 通路：前端「扫图层」按钮 → `GET /api/dwg-scan` (同上报告)。
业务专家据此把 `docs/element-upstream-contract.md` §5 的 TBD 映射 dict 回填成选择题 (选图层/块名对应哪种元素种类), 不必凭记忆口述。只报频率, 不判定 kind 归属。

**M5 冲突几何等价类维度**：`/api/conflict` 的 `summary.duplicates` + `conflicts[].kind='duplicate'`
(同坐标不同 id = 疑似重复元素, 捕捉设计师两稿「画了同位置但用了不同 id」的常见疏漏);
出图侧 `cad_execute_node task_type=conflict` 画琥珀色 DUP 圈 (DXFWriter.add_duplicate_marker,
与 M4 碰撞品红 CLASH 圈视觉区分, 无重复 0 实体)。

**violation 结构**（引擎 `RuleViolation.to_dict()` 已固定，桥原样透出）：
```json
{"rule_id","rule_name","severity":"error|warning|info","description","code_ref","element_id","suggested_fix"}
```

**约束**：
- `POST /api/pipeline` 走 `--no-llm` 等价路径（`inject_sample_structure=True`），秒级确定结果；
  `use_llm=true` 时 `inject_sample_structure=False`，但**默认前端不勾**，避免 100s 冷启动 + 联网。
- 预览渲染抽 `bridge.render_sample_png(sample) -> bytes`，**绝不弹窗**（`os.startfile` 那段只在 run.py 里）。
- 所有 import 懒加载（langgraph 冷启动 ~100s，模块收集时不许触发），沿用 `graph.py` 的 lazy 写法。
- 端口 8642 被占就 `+1` 重试，返回实际端口给前端。

## 2. React 前端页面契约 (src/client/src/)

主界面三区布局（沿用现有 `.app` 骨架，升级数据源）：

```
Header:  品牌 + 状态徽章(● 引擎已连接/未连接) + Phase 标签
Main:
  ├─ 左 CAD 视图:   画 <img src={api}/api/preview?sample=...> 真户型图 + 「重新出图」按钮
  │                 (未实现: 专业管/线/柱图元 → 置灰卡片 "出图深化 · 各专业图元标准")
  ├─ 中 Agent 流程:  6 步流水线, 点「运行」→ POST /api/pipeline → 高亮已完成步 + 出 violations
  │                 (M5 协同持久层区块已抽成独立子组件 <CollabPanel />: 日常主操作常显 +
  │                  低频诊断工具(校验/死锁/矩阵)折叠进「诊断工具」子区, 降低认知负荷)
  └─ 右 规则/知识:   GET /api/rules 真规则列表(分 hard/dsl 两 tab) + RAG 检索框(POST /api/rag/search)
Footer:  占位符卡片区 —— 未实现能力置灰, 每张含: 标题 / 一句话操作说明 / 所属专业 / [占位] 徽章
         (M5 协同持久层 + 团队协作 已去重合并为一张 "团队协作 · 在线协同" 卡, 点亮通道
          走 collab- 规则前缀)
```

**占位符卡片数据 (未实现, 前端写死成配置, 不造假数据)**：
```js
const PLACEHOLDERS = [
  {id:"m1-values",  title:"规范数值回填",  desc:"各专业阈值待专家确认后填 default.json, 改 JSON 零代码", domain:"给排水/电气/暖通/结构", owner:"各业专家"},
  {id:"m2-layer",   title:"DWG 图层约定",  desc:"各院点位图层/块名映射待对齐制图规范", domain:"出图规范", owner:"制图规范"},
  {id:"m3-render",  title:"出图深化",      desc:"各专业 元素→图元 画法 (线型/填充/图层着色)", domain:"各专业制图", owner:"各专业制图规范"},
  {id:"m4-collision",title:"多专业碰撞检测",desc:"管线穿梁 / 插座撞梁 自动检测", domain:"多专业协同", owner:"团队工程"},
  {id:"m5-team",    title:"团队协作",      desc:"多设计师 + 改动冲突检测 + 权限", domain:"协同", owner:"团队"},
];
```

**状态**：沿用 zustand；新增 `useEngineStore`（engineConnected, rules, violations, running, lastSample）。
**网络**：`const API = "http://127.0.0.1:8642"`（开发可覆写 `VITE_API`）。所有 fetch 失败 → 顶部徽章变「● 引擎未连接」+ 置灰，**不崩**。

## 3. 各专业域 → 桥/前端 责任切分 (专家团分工)

| 专家团 | 负责 | 关键文件 |
|---|---|---|
| A 前端/桌面 | React 三区 UI + 占位卡片 + zustand + 接 /api | src/client/src/App.tsx 等 |
| B 规则域 | /api/rules + /api/rule-violations 真数据 + 规则分 tab | src/gui/bridge.py (规则段) |
| C Agent 域 | /api/pipeline + /api/preview 真出图 | src/gui/bridge.py (agent 段) |
| D RAG/知识 | /api/rag/search 本地检索真结果 | src/gui/bridge.py (rag 段) |
| E 入口/构建 | start_gui.bat / start_gui.py / electron 起法 / vite 代理 | 根 scripts |

> 桥是**同一个文件** src/gui/bridge.py，但按段切给 B/C/D 各自写各自的路由函数，
> A 和 E 不碰桥逻辑。若并行写同一文件冲突，以「每段一个独立函数 + 底部统一 app.include」收敛。

## 4. 交付红线 (每个专家团交付前自查)

- [ ] 已实现能力：前端拿到的**真数据**能跑通（贴 curl/浏览器截图证据）
- [ ] 未实现能力：只有置灰卡片 + 说明，**无任何伪造数字/假图元**
- [ ] `python -c "import src.gui.bridge"` 不崩（模块收集不触发 langgraph 冷启动）
- [ ] 启动 `start_gui.bat` 后浏览器/Electron 能连上、徽章变绿
- [ ] 纯 ASCII 的 .bat / .py 入口不炸（沿用上一轮 GBK 教训）
- [ ] 不改 `src/rules/` `src/agents/src/` 既有引擎代码（只读调用，不破坏 171 测试）

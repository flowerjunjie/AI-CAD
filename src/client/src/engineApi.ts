import { useEngineStore, type RuleItem, type Violation, type PipelineResult, type RAGResult,
        type DslRuleItem, type DslValidateResp, type DslApplyResp,
        type ClashResult, type ConflictResult,
        type CollabSnapshot, type DwgScanResult } from './useEngineStore';

// 默认走 vite 开发代理 /api (vite.config.ts 转发到 Python 桥), 端口随 start_gui.py
// 动态探测的端口漂移也自动跟随, 不写死 8642。生产 Electron 才用 VITE_API 指绝对桥地址。
const API = (import.meta.env.VITE_API as string | undefined) || '';

async function getJson<T>(path: string): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null; // 断连降级，不崩
  }
}

export async function postJson<T, B>(path: string, body: B): Promise<T | null> {
  try {
    const res = await fetch(`${API}${path}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export function previewUrl(sample: string): string {
  return `${API}/api/preview?sample=${encodeURIComponent(sample)}`;
}

// 轮询 /api/health 判定引擎是否可达，同时拉真规则列表
export async function syncEngine() {
  const store = useEngineStore.getState();
  type Health = { status: string; phase: string };
  const health = await getJson<Health>('/api/health');
  if (health && health.status === 'ok') {
    store.setConnected(true, health.phase || 'Phase');
    const rules = await getJson<RuleItem[]>('/api/rules');
    store.setRules(rules || []);
  } else {
    store.setConnected(false, '—');
  }
}

export async function runPipeline(sample: string, useLlm: boolean) {
  const store = useEngineStore.getState();
  store.setRunning(true);
  store.setLastSample(sample);
  const result = await postJson<PipelineResult, { sample: string; use_llm: boolean }>(
    '/api/pipeline',
    { sample, use_llm: useLlm },
  );
  if (result) {
    store.setPipelineResult(result);
    store.setViolations(result.violations || []);
  }
  store.setRunning(false);
}

export async function runRagSearch(query: string) {
  const store = useEngineStore.getState();
  type RAGResp = { query: string; results: RAGResult[] };
  const resp = await postJson<RAGResp, { query: string; top_k: number }>('/api/rag/search', { query, top_k: 5 });
  store.setRagResults(query, resp?.results || []);
}

// ─── 规则 DSL 编辑器面板（Phase 2）—— 调用桥端点 (src/gui/bridge.py B2 段) ───
// GET /api/rules/dsl: 拉 default.json 原文 (含 predicate/params/param_defaults/enabled)。
// POST /api/rules/validate: 把改后的 JSON 走 validate_dsl_json (与 load fail-fast 同判据)。
// 端点已实现 (bridge.py B2 段), 前端直连, 无需 TODO。

export async function loadDslRules(): Promise<DslRuleItem[]> {
  type DslJson = { rules: DslRuleItem[] };
  const data = await getJson<DslJson>('/api/rules/dsl');
  return data?.rules || [];
}

export async function validateDslRules(rules: DslRuleItem[]): Promise<DslValidateResp | null> {
  // 契约: 桥端点收整份 {'rules': [...]} (bridge.py DslRulesValidateReq.rules 字段)。
  // 响应 {valid, error_count, errors: [{path, message, rule_index, rule_id?}]}。
  const resp = await postJson<DslValidateResp, { rules: DslRuleItem[] }>(
    '/api/rules/validate',
    { rules },
  );
  return resp;
}

// 写回端点 (bridge.py B3 段): 设计器「应用」落盘 default.json, 带人工确认闸。
// confirm=false → 服务端先 validate + 回 diff 预览, 不落盘 (status=pending_confirm)。
// confirm=true  → 备份 + 写盘 + fail-fast 重载兜底 (status=applied)。
// 服务端对非法 rules 直接 422 拒写, 前端拿到 null (postJson 断连/非 2xx 降级)。
export async function applyDslRules(rules: DslRuleItem[], confirm: boolean): Promise<DslApplyResp | null> {
  return postJson<DslApplyResp, { rules: DslRuleItem[]; confirm: boolean }>(
    '/api/rules/dsl/apply',
    { rules, confirm },
  );
}

// ─── M1 数值回填 (bridge B 段, 单规则轻量回填 — 专家在面板点「回填」即点亮占位卡) ───
// POST /api/rules/backfill {rule_id, confirmed?, confidence?, confirm_note?, params?}
// 单规则粒度 (比 DSL apply 全量重写轻): 改 confirmed 标志 / 参数值, 备份可回滚,
// confidence 白名单 (low/medium/high, 不虚标)。响应 {status:'applied', confirmed, backup, note}。

export interface RuleBackfillResp {
  status: 'applied';
  rule_id: string;
  backup: string;
  confirmed?: boolean;
  confidence?: string;
  param_defaults?: Record<string, unknown>;
  note?: string;
}

export async function backfillRule(
  ruleId: string,
  payload: {
    confirmed?: boolean;
    confidence?: 'low' | 'medium' | 'high';
    confirm_note?: string;
    params?: Record<string, unknown>;
  },
): Promise<RuleBackfillResp | null> {
  return postJson<RuleBackfillResp, typeof payload & { rule_id: string }>(
    '/api/rules/backfill',
    { rule_id: ruleId, ...payload },
  );
}

// ─── M4 碰撞 / M5 冲突 (bridge.py F 段) ───
// GET /api/clash?sample=X        → ClashResult (无碰撞 count=0 空列表)
// GET /api/conflict?sample_a=&sample_b= → ConflictResult (同稿自比 0 冲突)
// 断连时 getJson 返回 null, 对应 loading 复位, 不崩。

export async function runClashCheck(sample: string): Promise<ClashResult | null> {
  const store = useEngineStore.getState();
  store.setClashLoading(true);
  const result = await getJson<ClashResult>(
    `/api/clash?sample=${encodeURIComponent(sample)}`,
  );
  store.setClashLoading(false);
  if (result) {
    // 追加而非覆盖: 多次检测不同 sample 可并存, 面板肉眼可区分
    store.setClashResults([...store.clashResults, result]);
  }
  return result;
}

export async function runConflict(sampleA: string, sampleB: string): Promise<ConflictResult | null> {
  const store = useEngineStore.getState();
  store.setConflictLoading(true);
  const result = await getJson<ConflictResult>(
    `/api/conflict?sample_a=${encodeURIComponent(sampleA)}&sample_b=${encodeURIComponent(sampleB)}`,
  );
  store.setConflictLoading(false);
  if (result) {
    store.setConflictResults([...store.conflictResults, result]);
  }
  return result;
}

// ─── M5 在线协同持久层 (bridge.py H 段, 本地锁演示通路) ───
// GET  /api/collab/snapshot?designer=X → CollabSnapshot (诚实两态 source=file|empty)
// POST /api/collab/acquire  {designer, resource_id, mode} → 取锁 (被占 → acquired=false + reason)
// POST /api/collab/release  {designer, resource_id} → 放锁 (无锁幂等 released=false)
// 诚实标注: 本地单进程演示, 非跨设计师同步 (响应 note 字段明示)。

/** POST /api/collab/acquire|release 响应 (快照 + 操作结果, 诚实标注本地演示)。 */
export interface CollabLockOp extends CollabSnapshot {
  acquired?: boolean;
  released?: boolean;
  resource_id: string;
  designer: string;
  mode?: string;
  reason?: string;
}

export async function fetchCollabSnapshot(designer: string): Promise<CollabSnapshot | null> {
  const store = useEngineStore.getState();
  const snap = await getJson<CollabSnapshot>(
    `/api/collab/snapshot?designer=${encodeURIComponent(designer)}`,
  );
  if (snap) store.setCollabSnapshot(snap);
  return snap;
}

export async function collabAcquire(
  designer: string, resourceId: string, mode = 'write',
): Promise<CollabLockOp | null> {
  const store = useEngineStore.getState();
  store.setCollabLoading(true);
  const result = await postJson<CollabLockOp, { designer: string; resource_id: string; mode: string }>(
    '/api/collab/acquire', { designer, resource_id: resourceId, mode },
  );
  store.setCollabLoading(false);
  if (result) {
    store.setCollabSnapshot(result);  // 操作响应即新快照
    store.appendCollabOp(result);
  }
  return result;
}

export async function collabRelease(
  designer: string, resourceId: string,
): Promise<CollabLockOp | null> {
  const store = useEngineStore.getState();
  store.setCollabLoading(true);
  const result = await postJson<CollabLockOp, { designer: string; resource_id: string }>(
    '/api/collab/release', { designer, resource_id: resourceId },
  );
  store.setCollabLoading(false);
  if (result) {
    store.setCollabSnapshot(result);
    store.appendCollabOp(result);
  }
  return result;
}

// ─── M5 协同 + duplicate 联动 (bridge.py H 段, 取锁前看元素是否疑似重复) ───
// GET /api/collab/elements?sample=X → CollabElements (真实 CAD 元素 id 清单
// + duplicate_of 标记, 协同面板资源下拉数据源; 取锁前提示「疑似重复, 建议核对」)。
// 诚实标注: 只报几何重复线索, 不判业务归属 (取锁不被禁止)。

export async function fetchCollabElements(sample: string): Promise<import('./useEngineStore').CollabElements | null> {
  const store = useEngineStore.getState();
  store.setCollabElementsLoading(true);
  const result = await getJson<import('./useEngineStore').CollabElements>(
    `/api/collab/elements?sample=${encodeURIComponent(sample)}`,
  );
  store.setCollabElementsLoading(false);
  if (result) store.setCollabElements(result);
  return result;
}

// ─── M5 协同正确性地基 (bridge.py H 段, 机制层完整性校验 + 死锁环检测) ───
// GET  /api/collab/verify → CollabVerify (事件日志 + 锁态自洽校验, 纯函数机制层)
// POST /api/collab/deadlock-check {wait_edges} → CollabDeadlock (等待环检测)
// 诚实边界: 机制层纯判定, 非「多机协同是否一致」— 真·在线协同待业务定协议。

export async function fetchCollabVerify(): Promise<import('./useEngineStore').CollabVerify | null> {
  const store = useEngineStore.getState();
  const result = await getJson<import('./useEngineStore').CollabVerify>(
    '/api/collab/verify',
  );
  if (result) store.setCollabVerify(result);
  return result;
}

export async function collabDeadlockCheck(
  waitEdges: Record<string, string>,
): Promise<import('./useEngineStore').CollabDeadlock | null> {
  return postJson<
    import('./useEngineStore').CollabDeadlock,
    { wait_edges: Record<string, string> }
  >('/api/collab/deadlock-check', { wait_edges: waitEdges });
}

// ─── M2 制图约定对齐工具 (bridge.py I 段, 扫 DWG → 图层/块名频率报告) ───
// GET /api/dwg-scan?sample=X.dxf → DwgScanResult (诚实两态: 有数据/缺图层空报告)。
// 专家据此把 docs/element-upstream-contract.md §5 的 TBD 映射 dict 回填成选择题。

export async function runDwgScan(sample: string): Promise<DwgScanResult | null> {
  const store = useEngineStore.getState();
  store.setDwgScanLoading(true);
  const result = await getJson<DwgScanResult>(
    `/api/dwg-scan?sample=${encodeURIComponent(sample)}`,
  );
  store.setDwgScanLoading(false);
  if (result) store.setDwgScan(result);
  return result;
}

// ─── 人在回路确认闸 (bridge.py G 段, 演示通路) ───
// POST /agent/confirm {task_id, confirmed, modifications}
// 演示态: bridge 未存住"本 run 的 sample+checkpointer", confirmed=true 时用默认样本
// 真跑一次 graph 挂起→放行→resume (出终态摘要), 非设计师对真实出图结果的逐 task 确认。

/** /agent/confirm 的 resume 通路返回 (bridge._resume_agent_graph)。 */
export interface AgentResumeResult {
  resumed: boolean;
  session?: boolean;          // true = session 级同 thread 真续跑; false = 演示级默认样本
  reason?: string;            // 未放行 / 图侧不可用 / resume 失败 的诚实说明
  thread_id?: string;
  rule_violation_count?: number;
  final_dwg_path?: string;
  export_status?: string;
}

/** POST /agent/confirm 响应。 */
export interface AgentConfirmResult {
  task_id: string;
  confirmed: boolean;
  modifications?: Record<string, unknown> | null;
  status: 'confirmed' | 'pending_confirm';
  resume?: AgentResumeResult; // confirmed=true 才有
}

/** 接真实 CAD 数据源: /agent/run 透出的单个待确认 task (含类型/描述/出图结果)。 */
export interface AgentPendingItem {
  task_id: string;
  type: string;                     // door / window / beam / column / pipe ... (设计师看得懂)
  description: string;              // 来自 cad_results.description
  result: Record<string, unknown>;  // 该 task 的出图结果 (status / count / ...)
}

/** POST /agent/run 响应: 起一次真实图挂起在确认点 (session 级人在回路入口)。 */
export interface AgentRunResult {
  thread_id: string;
  sample: string;
  node: string;
  pending_task_ids: string[];
  pending_task_count: number;
  cad_result_count: number;
  message: string;
  pending?: AgentPendingItem[];     // 接真实 CAD 数据源: 结构化待确认项 (老字段向后兼容)
  preview_url?: string;             // 图面预览 (设计师对照看每个待确认 task)
}

export async function runAgentConfirm(
  taskId: string,
  confirmed: boolean,
): Promise<AgentConfirmResult | null> {
  const store = useEngineStore.getState();
  store.setConfirmLoading(true);
  const result = await postJson<AgentConfirmResult, { task_id: string; confirmed: boolean }>(
    '/agent/confirm',
    {
      task_id: taskId,
      confirmed,
    },
  );
  store.setConfirmLoading(false);
  if (result) {
    // 追加而非覆盖: 多次确认(同/不同 task)可并存, 面板肉眼可区分
    store.setConfirmResults([...store.confirmResults, result]);
  }
  return result;
}

export async function runAgentStart(sample: string): Promise<AgentRunResult | null> {
  const store = useEngineStore.getState();
  store.setConfirmLoading(true);
  const result = await postJson<AgentRunResult, { sample: string }>(
    '/agent/run',
    { sample },
  );
  store.setConfirmLoading(false);
  if (result) {
    // 起图挂起成功 → 记录 thread, 供确认闸操作真实 run (非演示 task)
    store.setAgentRun(result);
  }
  return result;
}

export { API };

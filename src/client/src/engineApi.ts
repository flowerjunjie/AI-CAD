import { useEngineStore, type RuleItem, type Violation, type PipelineResult, type RAGResult,
        type DslRuleItem, type DslValidateResp } from './useEngineStore';

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

export { API };

import { useEngineStore, type RuleItem, type Violation, type PipelineResult, type RAGResult } from './useEngineStore';

// 开发可用 import.meta.env.VITE_API 覆写；默认本地桥
const API = (import.meta.env.VITE_API as string | undefined) || 'http://127.0.0.1:8642';

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
  const resp = await postJson<RAGResp, { query: string }>('/api/rag/search', { query });
  store.setRagResults(query, resp?.results || []);
}

export { API };

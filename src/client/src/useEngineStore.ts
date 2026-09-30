import { create } from 'zustand';

export interface RuleItem {
  rule_id: string;
  name: string;
  code_ref: string;
  severity: string;
  source: 'hardcoded' | 'dsl';
  enabled: boolean;
  confirmed?: boolean;
}

export interface Violation {
  rule_id: string;
  rule_name: string;
  severity: 'error' | 'warning' | 'info';
  description: string;
  code_ref: string;
  element_id: string | null;
  suggested_fix: string | null;
}

export interface ZoneInfo {
  name: string;
  type: string;
  area: number;
}

export interface PipelineResult {
  project_type: string;
  zones: ZoneInfo[];
  task_count: number;
  violations: Violation[];
  dwg_path: string;
  preview_url: string;
}

export interface RAGResult {
  text: string;
  score: number;
  category: string;
}

// ─── M4 跨专业碰撞 / M5 两稿改动冲突 (bridge.py F 段) 数据契约 ───

/** M4 单条碰撞 (bridge /api/clash 的 clashes[i]，对齐 detect_clashes 返回)。 */
export interface ClashItem {
  a_id: string;
  b_id: string;
  kind: string;          // pipe-beam / duct-column / outlet-beam / grille-column ...
  detail: string;        // 中文说明 (如 "管段与梁段相交")
}

/** GET /api/clash 响应 (bridge.py F 段)。 */
export interface ClashResult {
  sample: string;
  tolerance_m: number;
  clashes: ClashItem[];
  count: number;
}

/** M5 单条冲突 (bridge /api/conflict 的 conflicts[i])。 */
export interface ConflictItem {
  id: string;
  field: string | null;  // null = 元素整块 added/removed
  a_value: unknown;
  b_value: unknown;
  kind: 'value' | 'added' | 'removed';
  category: string;      // 元素类: doors/outlets/pipes...
}

/** GET /api/conflict 响应 (bridge.py F 段)。 */
export interface ConflictResult {
  sample_a: string;
  sample_b: string;
  count: number;
  by_category: Record<string, number>;
  conflicts: ConflictItem[];
  summary: {
    total: number;
    by_category: Record<string, number>;
    value_conflicts: number;
    added: number;
    removed: number;
  };
}

// ─── 规则 DSL 编辑器面板（Phase 2）—— 数据契约对齐 default.json / validate_dsl_json ───

/** DSL 规则一条 (default.json 的 rules[i])。编辑面板的数据源。 */
export interface DslRuleItem {
  rule_id: string;
  name: string;
  code_ref: string;
  severity: string; // error / warning / info
  element_types: string[];
  predicate: string;
  params: Record<string, unknown>;
  param_defaults: Record<string, unknown>;
  description_template?: string;
  suggested_fix_template?: string;
  enabled: boolean;
  dsl_only?: boolean;
  spec_source?: string;
  confidence?: string;
  confirmed?: boolean;
  confirm_note?: string;
}

/** validate_dsl_json 单条错误 (对齐 DslJsonError + 桥端点补的 rule_id)。 */
export interface DslValidationError {
  path: string;          // "rules[2].predicate" 或文件级 "<top>"
  message: string;
  rule_index: number;    // -1 = 文件级错误
  rule_id?: string;
}

/** POST /api/rules/validate 响应 (bridge.py B2 段)。 */
export interface DslValidateResp {
  valid: boolean;
  error_count: number;
  errors: DslValidationError[];
}

/** DSL 写回端点的 diff 预览 (改了/新增/删 各 rule_id 列表)。 */
export interface DslApplyDiff {
  changed: string[];
  added: string[];
  removed: string[];
}

/** POST /api/rules/dsl/apply 响应 (bridge.py B3 段, 带人工确认闸)。 */
export interface DslApplyResp {
  status: 'pending_confirm' | 'applied';
  valid: boolean;
  error_count: number;
  diff: DslApplyDiff;
  backup?: string;
  applied_rule_count?: number;
  message?: string;
}

interface EngineState {
  engineConnected: boolean;
  phase: string;
  rules: RuleItem[];
  violations: Violation[];
  running: boolean;
  lastSample: string;
  pipelineResult: PipelineResult | null;
  ragResults: RAGResult[];
  ragQuery: string;
  // M4 碰撞 / M5 冲突 (bridge F 段)
  clashResults: ClashResult[];
  clashLoading: boolean;
  conflictResults: ConflictResult[];
  conflictLoading: boolean;
  // 人在回路确认闸 (bridge G 段, 演示通路)
  confirmResults: import('./engineApi').AgentConfirmResult[];
  confirmLoading: boolean;
  // session 级人在回路: /agent/run 起的真实挂起 run (thread + pending tasks)
  agentRun: import('./engineApi').AgentRunResult | null;
  setConnected: (c: boolean, phase?: string) => void;
  setRules: (r: RuleItem[]) => void;
  setViolations: (v: Violation[]) => void;
  setRunning: (r: boolean) => void;
  setLastSample: (s: string) => void;
  setPipelineResult: (p: PipelineResult | null) => void;
  setRagResults: (q: string, r: RAGResult[]) => void;
  setClashResults: (c: ClashResult[]) => void;
  setClashLoading: (l: boolean) => void;
  setConflictResults: (c: ConflictResult[]) => void;
  setConflictLoading: (l: boolean) => void;
  setConfirmResults: (c: import('./engineApi').AgentConfirmResult[]) => void;
  setConfirmLoading: (l: boolean) => void;
  setAgentRun: (r: import('./engineApi').AgentRunResult | null) => void;
}

export const useEngineStore = create<EngineState>((set) => ({
  engineConnected: false,
  phase: '—',
  rules: [],
  violations: [],
  running: false,
  lastSample: 'residential_100sqm.json',
  pipelineResult: null,
  ragResults: [],
  ragQuery: '',
  clashResults: [],
  clashLoading: false,
  conflictResults: [],
  conflictLoading: false,
  confirmResults: [],
  confirmLoading: false,
  agentRun: null,
  setConnected: (c, phase) => set({ engineConnected: c, ...(phase !== undefined ? { phase } : {}) }),
  setRules: (rules) => set({ rules }),
  setViolations: (violations) => set({ violations }),
  setRunning: (running) => set({ running }),
  setLastSample: (lastSample) => set({ lastSample }),
  setPipelineResult: (pipelineResult) => set({ pipelineResult }),
  setRagResults: (ragQuery, ragResults) => set({ ragQuery, ragResults }),
  setClashResults: (clashResults) => set({ clashResults }),
  setClashLoading: (clashLoading) => set({ clashLoading }),
  setConflictResults: (conflictResults) => set({ conflictResults }),
  setConflictLoading: (conflictLoading) => set({ conflictLoading }),
  setConfirmResults: (confirmResults) => set({ confirmResults }),
  setConfirmLoading: (confirmLoading) => set({ confirmLoading }),
  setAgentRun: (agentRun) => set({ agentRun }),
}));

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
  setConnected: (c: boolean, phase?: string) => void;
  setRules: (r: RuleItem[]) => void;
  setViolations: (v: Violation[]) => void;
  setRunning: (r: boolean) => void;
  setLastSample: (s: string) => void;
  setPipelineResult: (p: PipelineResult | null) => void;
  setRagResults: (q: string, r: RAGResult[]) => void;
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
  setConnected: (c, phase) => set({ engineConnected: c, ...(phase !== undefined ? { phase } : {}) }),
  setRules: (rules) => set({ rules }),
  setViolations: (violations) => set({ violations }),
  setRunning: (running) => set({ running }),
  setLastSample: (lastSample) => set({ lastSample }),
  setPipelineResult: (pipelineResult) => set({ pipelineResult }),
  setRagResults: (ragQuery, ragResults) => set({ ragQuery, ragResults }),
}));

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

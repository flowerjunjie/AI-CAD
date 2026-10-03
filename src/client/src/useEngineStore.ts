import { create } from 'zustand';

export interface RuleItem {
  rule_id: string;
  name: string;
  code_ref: string;
  severity: string;
  source: 'hardcoded' | 'dsl';
  enabled: boolean;
  confirmed?: boolean;
  // M4 容差 + M1 卡联动: 仅 clash-tolerance-range 规则透出 (其余 null, 诚实不乱套)
  tolerance_source?: 'param' | 'dsl' | 'default' | null;
  tolerance_m?: number | null;
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

/** GET /api/clash 响应 (bridge.py F 段, M4 容差取值通道: param > dsl > default)。 */
export interface ClashResult {
  sample: string;
  tolerance_m: number;
  tolerance_source?: 'param' | 'dsl' | 'default';  // 来源标注 (诚实: 不虚标)
  clashes: ClashItem[];
  count: number;
}

/** M5 单条冲突 (bridge /api/conflict 的 conflicts[i])。 */
export interface ConflictItem {
  id: string;
  field: string | null;  // null = 元素整块 added/removed/duplicate
  a_value: unknown;
  b_value: unknown;
  kind: 'value' | 'added' | 'removed' | 'duplicate';  // duplicate = 同坐标不同 id (几何等价类)
  category: string;      // 元素类: doors/outlets/pipes...
  // duplicate 冲突专有字段 (kind='duplicate' 时)
  id_a?: string;         // 重复元素 A 的 id
  id_b?: string;         // 重复元素 B 的 id
  extra_ids?: string[];  // 同坐标第 3+ 个 id (多重重叠)
  coord?: number[];      // 坐标 [x, y] 或端点排序 [x1,y1,x2,y2]
  tolerance_m?: number;  // 判定容差带
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
    duplicates: number;  // 几何等价类维度 (同坐标不同 id = 疑似重复)
  };
}

// ─── M5 在线协同持久层 (bridge.py H 段, 本地锁演示通路) ───

/** 单条协同事件 (append-only, collab_protocol.append_event 的持久化形态)。 */
export interface CollabEvent {
  seq: number;
  type: string;         // lock / unlock / approve / reject / merge
  actor: string;
  resource_id: string;
  payload?: Record<string, unknown>;
}

/** GET /api/collab/snapshot 响应 (bridge.py H 段, 诚实两态 source=file|empty)。 */
export interface CollabSnapshot {
  designer: string;
  write_holders: Record<string, string>;  // resource_id → 持锁设计师
  recent_events: CollabEvent[];
  event_count: number;
  source: 'file' | 'empty';
  note?: string;
}

/** POST /api/collab/acquire|release 响应 (快照 + 操作结果 + 诚实标注)。 */
export interface CollabLockOp extends CollabSnapshot {
  acquired?: boolean;    // acquire 才有: 取锁是否成功 (被占 → false + reason)
  released?: boolean;    // release 才有: 确有该锁被放掉
  resource_id: string;
  designer: string;
  mode?: string;
  reason?: string;
}

// ─── M2 制图约定对齐工具 (bridge.py I 段, 扫 DWG → 图层/块名频率报告) ───

/** 单个图层的扫描结果 (bridge /api/dwg-scan 的 layers[图层名])。 */
export interface DwgLayerInfo {
  entity_counts: Record<string, number>;  // 实体类型 → 数量
  block_names: string[];                  // INSERT 块名 (按频率降序)
}

/** GET /api/dwg-scan 响应 (bridge.py I 段, 诚实两态: 有数据/缺图层空报告)。 */
export interface DwgScanResult {
  sample: string;
  layers: Record<string, DwgLayerInfo>;
  entity_type_totals: Record<string, number>;
  attrib_tags: Record<string, number>;
  layer_count: number;
  insert_total: number;
  available_samples?: string[];
  note?: string;
}

// ─── M5 协同 + duplicate 联动 (bridge.py H 段, 取锁前看元素是否疑似重复) ───

/** 单个可锁资源元素 (bridge /api/collab/elements 的 resources[i])。 */
export interface CollabResource {
  id: string;
  category: string;            // 元素类: doors/outlets/pipes...
  duplicate_of: string | null; // 同坐标不同 id 的对端 (疑似重复, 无则 null)
  coord?: number[];           // 坐标 (仅 duplicate 元素透出)
}

/** GET /api/collab/elements?sample=X 响应 (协同面板资源下拉的数据源)。 */
export interface CollabElements {
  sample: string;
  resources: CollabResource[];
  duplicate_count: number;
  note?: string;
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
  // M5 在线协同持久层 (bridge H 段, 本地锁演示)
  collabSnapshot: import('./useEngineStore').CollabSnapshot | null;
  collabOps: import('./engineApi').CollabLockOp[];
  collabLoading: boolean;
  // M2 制图约定对齐工具 (bridge I 段, 扫 DWG → 图层/块名频率报告)
  dwgScan: import('./useEngineStore').DwgScanResult | null;
  dwgScanLoading: boolean;
  // M5 协同 + duplicate 联动 (bridge H 段, 取锁前看元素是否疑似重复)
  collabElements: import('./useEngineStore').CollabElements | null;
  collabElementsLoading: boolean;
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
  setCollabSnapshot: (s: import('./useEngineStore').CollabSnapshot | null) => void;
  appendCollabOp: (op: import('./engineApi').CollabLockOp) => void;
  setCollabLoading: (l: boolean) => void;
  setDwgScan: (r: import('./useEngineStore').DwgScanResult | null) => void;
  setDwgScanLoading: (l: boolean) => void;
  setCollabElements: (r: import('./useEngineStore').CollabElements | null) => void;
  setCollabElementsLoading: (l: boolean) => void;
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
  collabSnapshot: null,
  collabOps: [],
  collabLoading: false,
  dwgScan: null,
  collabElements: null,
  dwgScanLoading: false,
  collabElementsLoading: false,
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
  setCollabSnapshot: (collabSnapshot) => set({ collabSnapshot }),
  appendCollabOp: (op) => set((s) => ({ collabOps: [...s.collabOps, op] })),
  setCollabLoading: (collabLoading) => set({ collabLoading }),
  setDwgScan: (dwgScan) => set({ dwgScan }),
  setDwgScanLoading: (dwgScanLoading) => set({ dwgScanLoading }),
  setCollabElements: (collabElements) => set({ collabElements }),
  setCollabElementsLoading: (collabElementsLoading) => set({ collabElementsLoading }),
  setConfirmResults: (confirmResults) => set({ confirmResults }),
  setConfirmLoading: (confirmLoading) => set({ confirmLoading }),
  setAgentRun: (agentRun) => set({ agentRun }),
}));

import { create } from 'zustand';
import type { DslRuleItem, DslValidationError } from './useEngineStore';

/**
 * 规则 DSL 编辑器面板的状态 (Phase 2)。独立于 useEngineStore:
 * 规则编辑态 (改了哪条 / 校验结果) 是编辑器私事，不污染主引擎状态。
 * dslRules 是 default.json 的权威拷贝，编辑全部走 setXxx (不可变重建)。
 */

type ValidateStatus = 'idle' | 'local-only' | 'validated-ok' | 'validated-bad' | 'unreachable';

interface RuleEditorState {
  // 原始 default.json (reset 用) + 当前编辑态
  originalRules: DslRuleItem[];
  rules: DslRuleItem[];
  loaded: boolean;
  // 编辑器 UI 态
  selectedRuleId: string | null;
  // 校验态
  validateStatus: ValidateStatus;
  backendErrors: DslValidationError[]; // 后端 /api/rules/validate 返回
  localIssueRuleIds: string[];        // 本地预检命中 rule_id (无具体错误内容, 看面板里该规则的黄字)
  errorForRule: string[];             // 选中规则相关的后端错误消息 (展示在右侧)

  setLoaded: (loaded: boolean) => void;
  setRules: (rules: DslRuleItem[]) => void;
  selectRule: (ruleId: string | null) => void;
  updateParam: (ruleId: string, key: string, value: unknown) => void;
  addParam: (ruleId: string, key: string, value: unknown) => void;
  removeParam: (ruleId: string, key: string) => void;
  setEnabled: (ruleId: string, enabled: boolean) => void;
  setSeverity: (ruleId: string, severity: string) => void;
  reset: () => void;
  setValidateStatus: (s: ValidateStatus) => void;
  setBackendErrors: (errs: DslValidationError[]) => void;
  setLocalIssueRuleIds: (ids: string[]) => void;
}

function ruleOf(rules: DslRuleItem[], ruleId: string): DslRuleItem | undefined {
  return rules.find((r) => r.rule_id === ruleId);
}

export const useRuleEditorStore = create<RuleEditorState>((set) => ({
  originalRules: [],
  rules: [],
  loaded: false,
  selectedRuleId: null,
  validateStatus: 'idle',
  backendErrors: [],
  localIssueRuleIds: [],
  errorForRule: [],

  setLoaded: (loaded) => set({ loaded }),
  setRules: (rules) => set({ rules, originalRules: rules.map((r) => ({ ...r })) }),
  selectRule: (ruleId) => set({ selectedRuleId: ruleId, errorForRule: [] }),

  updateParam: (ruleId, key, value) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.rule_id === ruleId
          ? { ...r, params: { ...r.params, [key]: value } }
          : r,
      ),
    })),

  addParam: (ruleId, key, value) =>
    set((s) => ({
      rules: s.rules.map((r) =>
        r.rule_id === ruleId
          ? { ...r, params: { ...r.params, [key]: value } }
          : r,
      ),
    })),

  removeParam: (ruleId, key) =>
    set((s) => ({
      rules: s.rules.map((r) => {
        if (r.rule_id !== ruleId) return r;
        const params = { ...r.params };
        delete params[key];
        const param_defaults = { ...r.param_defaults };
        delete param_defaults[key];
        return { ...r, params, param_defaults };
      }),
    })),

  setEnabled: (ruleId, enabled) =>
    set((s) => ({
      rules: s.rules.map((r) => (r.rule_id === ruleId ? { ...r, enabled } : r)),
    })),

  setSeverity: (ruleId, severity) =>
    set((s) => ({
      rules: s.rules.map((r) => (r.rule_id === ruleId ? { ...r, severity } : r)),
    })),

  reset: () =>
    set((s) => ({
      rules: s.originalRules.map((r) => ({ ...r })),
      selectedRuleId: s.selectedRuleId,
      validateStatus: 'idle',
      backendErrors: [],
      localIssueRuleIds: [],
      errorForRule: [],
    })),

  setValidateStatus: (validateStatus) => set({ validateStatus }),
  setBackendErrors: (backendErrors) => set({ backendErrors }),
  setLocalIssueRuleIds: (localIssueRuleIds) => set({ localIssueRuleIds, errorForRule: [] }),
}));

export function isRuleModified(originals: DslRuleItem[], current: DslRuleItem[], ruleId: string): boolean {
  const a = ruleOf(originals, ruleId);
  const b = ruleOf(current, ruleId);
  if (!a || !b) return false;
  return (
    JSON.stringify(a.params) !== JSON.stringify(b.params) ||
    a.enabled !== b.enabled ||
    a.severity !== b.severity
  );
}

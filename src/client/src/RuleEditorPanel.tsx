import React, { useEffect, useState } from 'react';
import { useRuleEditorStore, isRuleModified } from './useRuleEditorStore';
import { useEngineStore } from './useEngineStore';
import { loadDslRules, validateDslRules, applyDslRules, backfillRule, runDslAudit } from './engineApi';
import { localCheckAllRules } from './localPredicateCheck';
import type { DslRuleItem, DslApplyDiff, DslAuditResult } from './useEngineStore';

/**
 * 规则 DSL 编辑器面板 (Phase 2) — 设计器不写代码改 default.json。
 * 布局: 左 = 规则列表 (severity/enabled/改没改), 右 = 选中规则详情 (阈值输入 + 开关 + severity)。
 * 校验: 改完点「校验」→ 本地预检 (谓词键名) + 后端 /api/rules/validate (全白名单),
 * 通过 → 可应用; 不过 → 红字逐条定位 (哪条规则哪个字段)。
 */
function RuleEditorPanel() {
  const { rules, originalRules, loaded, selectedRuleId, validateStatus, backendErrors, localIssueRuleIds } =
    useRuleEditorStore();
  const { engineConnected } = useEngineStore();
  const { dslAudit, dslAuditLoading } = useEngineStore();
  const store = useRuleEditorStore;
  const [pendingDiff, setPendingDiff] = useState<DslApplyDiff | null>(null);
  const [applyMsg, setApplyMsg] = useState<string>('');

  /** DSL 信任边界体检: 一键读端点, 看「哪些规则声明类型会落空 / predicate 引用未声明变量」。 */
  const onAudit = () => { void runDslAudit(); };

  useEffect(() => {
    if (!loaded && engineConnected) {
      loadDslRules()
        .then((rs) => {
          store.getState().setRules(rs);
          if (rs.length > 0) store.getState().selectRule(rs[0].rule_id);
        })
        .catch(() => store.getState().setLoaded(true));
    }
  }, [loaded, engineConnected]);

  const selected: DslRuleItem | null = rules.find((r) => r.rule_id === selectedRuleId) || null;
  const canApply = isAnyModified(originalRules, rules) && validateStatus === 'validated-ok' && engineConnected;

  /** 应用 (人工确认闸): 先 confirm=false 拿 diff 预览, 用户二次点击才 confirm=true 落盘。 */
  const onApply = async () => {
    setApplyMsg('');
    if (pendingDiff === null) {
      const preview = await applyDslRules(rules, false);
      if (!preview || preview.status !== 'pending_confirm') {
        setApplyMsg(preview ? '服务端校验未通过, 未落盘' : '无法连接写回端点');
        return;
      }
      setPendingDiff(preview.diff); // 展示 diff, 等用户二次确认
      return;
    }
    // 二次确认: 已拿到 diff, 带 confirm=true 真写盘
    const res = await applyDslRules(rules, true);
    if (res && res.status === 'applied') {
      setApplyMsg(`已写盘 (${res.applied_rule_count} 条) · 备份 ${res.backup}`);
      setPendingDiff(null);
      store.getState().setRules(rules.map((r) => ({ ...r }))); // 刷新 originalRules 基线
    } else {
      setApplyMsg(res ? '写盘失败, 未落盘' : '无法连接写回端点');
    }
  };

  return (
    <div className="dsl-editor">
      <div className="dsl-editor-toolbar">
        <span className={`dsl-editor-status status-${validateStatus}`}>
          {validateStatusLabel(validateStatus, backendErrors.length)}
        </span>
        <button
          className="btn-primary btn-sm"
          onClick={() => runValidation(store, rules)}
          disabled={rules.length === 0 || !engineConnected}
        >
          校验
        </button>
        <button
          className="btn-primary btn-sm"
          onClick={onApply}
          disabled={!canApply}
          title="先预览 diff, 二次点击确认落盘"
        >
          {pendingDiff === null ? '应用' : '确认落盘'}
        </button>
        <button
          className="btn-sm dsl-editor-reset"
          onClick={() => store.getState().reset()}
          disabled={isAnyModified(originalRules, rules)}
        >
          重置
        </button>
        <button
          className="btn-sm dsl-audit-btn"
          onClick={onAudit}
          disabled={!engineConnected || dslAuditLoading}
          title="机制层自洽体检: 声明类型 vs 主链路可喂类对账 (不判业务类名对错)"
        >
          {dslAuditLoading ? '体检中…' : '体检'}
        </button>
      </div>

      {dslAudit !== null && <DslAuditBlock audit={dslAudit} />}

      {pendingDiff !== null && (
        <div className="dsl-apply-preview">
          <div className="dsl-apply-preview-title">待落盘 diff (二次点击「确认落盘」写回 default.json):</div>
          <ul>
            {pendingDiff.changed.map((id) => <li key={`c-${id}`}><span className="chg">改</span> {id}</li>)}
            {pendingDiff.added.map((id) => <li key={`a-${id}`}><span className="add">新增</span> {id}</li>)}
            {pendingDiff.removed.map((id) => <li key={`r-${id}`}><span className="del">删</span> {id}</li>)}
            {pendingDiff.changed.length + pendingDiff.added.length + pendingDiff.removed.length === 0 &&
              <li className="dsl-apply-none">当前无字段改动 (与 default.json 一致)</li>}
          </ul>
        </div>
      )}
      {applyMsg !== '' && <div className="dsl-apply-msg">{applyMsg}</div>}

      {!engineConnected ? (
        <div className="empty-hint">引擎未连接，无法拉取 DSL 规则 (启动 start_gui.bat)</div>
      ) : rules.length === 0 ? (
        <div className="empty-hint">DSL 规则列表为空 (default.json 无 rules)</div>
      ) : (
        <div className="dsl-editor-body">
          <div className="dsl-editor-list">
            {rules.map((r) => {
              const modified = isRuleModified(originalRules, rules, r.rule_id);
              const hasIssue = localIssueRuleIds.includes(r.rule_id) ||
                backendErrors.some((e) => e.rule_id === r.rule_id);
              return (
                <div
                  key={r.rule_id}
                  className={`dsl-rule-row ${selected?.rule_id === r.rule_id ? 'selected' : ''} ${modified ? 'modified' : ''}`}
                  onClick={() => store.getState().selectRule(r.rule_id)}
                >
                  <div className="dsl-rule-row-main">
                    <span className={`rule-sev sev-${r.severity}`}>{r.severity}</span>
                    <span className="dsl-rule-name">{r.name}</span>
                    {hasIssue && <span className="dsl-issue-dot" title="该规则有校验/预检问题" />}
                  </div>
                  <div className="dsl-rule-row-sub">
                    <span className="rule-code">{r.rule_id}</span>
                    {modified && <span className="dsl-mod-tag">已改</span>}
                  </div>
                </div>
              );
            })}
          </div>

          {selected && (
            <div className="dsl-editor-detail">
              <div className="dsl-detail-head">
                <span className="dsl-detail-name">{selected.name}</span>
                <label className="chk">
                  <input
                    type="checkbox"
                    checked={selected.enabled}
                    onChange={(e) => store.getState().setEnabled(selected.rule_id, e.target.checked)}
                  />
                  启用
                </label>
              </div>
              <div className="dsl-detail-code">{selected.code_ref}</div>

              <label className="dsl-detail-label">severity</label>
              <select
                className="dsl-input dsl-input-sev"
                value={selected.severity}
                onChange={(e) => store.getState().setSeverity(selected.rule_id, e.target.value)}
              >
                <option value="error">error</option>
                <option value="warning">warning</option>
                <option value="info">info</option>
              </select>

              <label className="dsl-detail-label">predicate (只读 · 写白名单表达式)</label>
              <div className="dsl-predicate">{selected.predicate}</div>

              <label className="dsl-detail-label">params · 阈值 (不写代码只改值)</label>
              <ParamsEditor rule={selected} />

              <ParamIssues rule={selected} />
              <BackendErrorsForRule ruleId={selected.rule_id} errors={backendErrors} />
              <M1BackfillBlock rule={selected} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/** M1 数值回填 (专家在面板里点「回填」即点亮占位卡, 零代码改 JSON)。
 *  单规则粒度走 /api/rules/backfill: confirmed=true + confidence 选档 + 备注。
 *  诚实边界: 回填后提示「跑 /api/rules 验证前端点亮」, 不冒称已点亮;
 *  confidence 默认 medium (不虚标 high), 备注写明依据条文 (业务侧如实填)。 */
function M1BackfillBlock({ rule }: { rule: DslRuleItem }) {
  const { engineConnected } = useEngineStore();
  const [confidence, setConfidence] = useState<'low' | 'medium' | 'high'>(
    (rule.confidence as 'low' | 'medium' | 'high') || 'medium');
  const [note, setNote] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const onBackfill = async () => {
    setBusy(true);
    setMsg('');
    const res = await backfillRule(rule.rule_id, {
      confirmed: true,
      confidence,
      confirm_note: note.trim() || undefined,
    });
    setBusy(false);
    if (res && res.status === 'applied') {
      setMsg(`已写盘 ${rule.rule_id} (confirmed=${res.confirmed} · ${res.confidence}) · 备份 ${res.backup}`);
      // 回填落盘后刷新规则列表 (originalRules 基线更新, 防「已改」误标)
      loadDslRules().then((rs) => useRuleEditorStore.getState().setRules(rs));
    } else {
      setMsg(res ? `写盘失败 (${res.status})` : '无法连接回填端点');
    }
  };

  return (
    <div className="m1-backfill">
      <div className="m1-backfill-title">M1 回填 · {rule.rule_id}</div>
      <div className="m1-backfill-row">
        <label className="chk">
          <input type="checkbox" checked={!!rule.confirmed} disabled />
          confirmed: {rule.confirmed ? 'true' : 'false'}
        </label>
        <select
          className="dsl-input dsl-input-sev"
          value={confidence}
          onChange={(e) => setConfidence(e.target.value as 'low' | 'medium' | 'high')}
          title="不虚标: 几何默认/机制=medium, 专家按 GB 条文背书才 high"
        >
          <option value="low">low</option>
          <option value="medium">medium</option>
          <option value="high">high</option>
        </select>
        <button
          className="btn-primary btn-sm"
          onClick={onBackfill}
          disabled={!engineConnected || busy}
          title="写 default.json + 备份; 前端按 confirmed 点亮对应占位卡"
        >
          {busy ? '回填中…' : '回填并确认'}
        </button>
      </div>
      <input
        className="dsl-input m1-backfill-note"
        placeholder="回填备注 (写明依据条文, 如 GB 50010 梁高下限)"
        value={note}
        onChange={(e) => setNote(e.target.value)}
      />
      {msg && <div className="m1-backfill-msg">{msg}</div>}
    </div>
  );
}

/** DSL 信任边界体检结果区 (GET /api/rules/dsl-audit, 机制层自洽诊断, 不写盘):
 *  逐条展示 issues + dangling_rules (rule_id + 声明类型); ok=true 且无缺口时显示「无缺口」。
 *  诚实标注: 与端点 note 同源 — 只判声明与可喂类一致性, 不判业务类名该不该存在。 */
function DslAuditBlock({ audit }: { audit: DslAuditResult }) {
  const hasGaps = audit.issues.length > 0 || audit.dangling_rules.length > 0;
  return (
    <div className="dsl-audit">
      <div className="dsl-audit-title">
        DSL 体检 · 对账 {audit.checked} 条
        {audit.note && <span className="dsl-audit-note"> — {audit.note}</span>}
      </div>
      {hasGaps ? (
        <>
          {audit.issues.map((msg, i) => (
            <div key={`i-${i}`} className={`dsl-issue ${audit.dangling_rules.some((d) => msg.startsWith(`${d.rule_id}.`)) ? 'backend' : 'local'}`}>
              {msg}
            </div>
          ))}
          {audit.dangling_rules.map((d) => (
            <div key={`d-${d.rule_id}`} className="dsl-audit-dangling">
              <span className="dsl-issue-path">{d.rule_id}</span>
              声明类型全落空: {d.element_types.join(', ')}
            </div>
          ))}
        </>
      ) : (
        <div className="dsl-audit-clean">无缺口 (element_types 与主链路可喂类对齐, predicate 无未声明引用)</div>
      )}
    </div>
  );
}

function validateStatusLabel(s: string, n: number): string {
  switch (s) {
    case 'idle': return '未校验';
    case 'local-only': return '本地预检命中 (见下方红字)';
    case 'validated-ok': return '校验通过 · 可应用';
    case 'validated-bad': return `校验未通过 · ${n} 处`;
    case 'unreachable': return '无法连接后端校验端点';
    default: return '';
  }
}

function isAnyModified(originals: DslRuleItem[], current: DslRuleItem[]): boolean {
  return current.some((r) => isRuleModified(originals, current, r.rule_id));
}

/** 跑校验: 先本地预检 (谓词键名), 有命中就标黄; 再打后端全量校验 → 红字逐条。 */
async function runValidation(store: typeof useRuleEditorStore, rules: DslRuleItem[]) {
  const s = store.getState();
  const localIssues = localCheckAllRules(rules);
  s.setLocalIssueRuleIds([...localIssues.keys()]);
  s.setValidateStatus(localIssues.size > 0 ? 'local-only' : 'idle');

  const resp = await validateDslRules(rules);
  if (!resp) {
    store.getState().setValidateStatus('unreachable');
    return;
  }
  store.getState().setBackendErrors(resp.errors);
  store.getState().setValidateStatus(resp.valid ? 'validated-ok' : 'validated-bad');
  if (resp.valid) store.getState().setLocalIssueRuleIds([]);
}

function ParamsEditor({ rule }: { rule: DslRuleItem }) {
  const s = useRuleEditorStore;
  const [newKey, setNewKey] = useState('');
  const [newVal, setNewVal] = useState('');
  const keys = Object.keys(rule.params);

  return (
    <div className="dsl-params">
      {keys.length === 0 && <div className="dsl-empty-params">该规则无阈值 params (纯逻辑谓词)</div>}
      {keys.map((k) => (
        <div key={k} className="dsl-param-row">
          <input
            className="dsl-input dsl-input-key"
            value={k}
            readOnly
          />
          <input
            className="dsl-input dsl-input-val"
            type="number"
            step="any"
            value={String(rule.params[k])}
            onChange={(e) => s.getState().updateParam(rule.rule_id, k, parseNumeric(e.target.value))}
          />
          <button
            className="btn-sm dsl-param-del"
            onClick={() => s.getState().removeParam(rule.rule_id, k)}
            title="移除此阈值 (predicate 仍引用它会报「白名单外标识符」)"
          >
            ×
          </button>
        </div>
      ))}
      <div className="dsl-param-row dsl-param-add">
        <input className="dsl-input dsl-input-key" placeholder="新键名" value={newKey} onChange={(e) => setNewKey(e.target.value)} />
        <input className="dsl-input dsl-input-val" placeholder="值" value={newVal} onChange={(e) => setNewVal(e.target.value)} />
        <button
          className="btn-sm"
          disabled={!newKey.trim()}
          onClick={() => {
            s.getState().addParam(rule.rule_id, newKey.trim(), parseNumeric(newVal));
            setNewKey('');
            setNewVal('');
          }}
        >
          +
        </button>
      </div>
    </div>
  );
}

function parseNumeric(v: string): number | string {
  if (v === '' || Number.isNaN(Number(v))) return v; // 留字符串 (非数值型阈值)
  return Number(v);
}

/** 该规则的本地预检问题 (黄字) — 在 ParamsEditor 下方实时提示。 */
function ParamIssues({ rule }: { rule: DslRuleItem }) {
  const issues = localCheckAllRules([rule]).get(rule.rule_id);
  if (!issues || issues.length === 0) return null;
  return (
    <div className="dsl-local-issues">
      {issues.map((m, i) => (
        <div key={i} className="dsl-issue local">{m}</div>
      ))}
    </div>
  );
}

/** 该规则的后端校验错误 (红字) — 校验未通过时逐条定位到字段。 */
function BackendErrorsForRule({ ruleId, errors }: { ruleId: string; errors: { path: string; message: string; rule_id?: string }[] }) {
  const mine = errors.filter((e) => e.rule_id === ruleId);
  if (mine.length === 0) return null;
  return (
    <div className="dsl-backend-errors">
      {mine.map((e, i) => (
        <div key={i} className="dsl-issue backend">
          <span className="dsl-issue-path">{e.path}</span> {e.message}
        </div>
      ))}
    </div>
  );
}

export default RuleEditorPanel;

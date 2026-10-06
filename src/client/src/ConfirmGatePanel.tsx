import React, { useState, useCallback } from 'react';
import { useEngineStore } from './useEngineStore';
import { runAgentConfirm, runAgentStart } from './engineApi';

/**
 * 人在回路确认闸 (bridge /agent/confirm, session 级) — 从 App.tsx 抽出的独立子组件。
 * 起图挂起 → 逐 task 放行/拒绝 → 同 thread 真续跑。缓解 App.tsx 巨型组件。
 * 演示级 (没起图直接确认) vs session 级 (起真实图挂起后对真实 task 确认) 两级。
 */
export default function ConfirmGatePanel() {
  const {
    engineConnected, lastSample,
    confirmResults, confirmLoading, agentRun,
  } = useEngineStore();

  const [confirmTask, setConfirmTask] = useState('door-3');
  const [confirmDecision, setConfirmDecision] = useState(true);

  const handleConfirm = useCallback(async () => {
    await runAgentConfirm(confirmTask, confirmDecision);
  }, [confirmTask, confirmDecision]);

  // 「起图挂起」: 起一次真实 auto_mode=False 图停在确认点, 把真实 pending 灌进 task 下拉
  const handleStartRun = useCallback(async () => {
    const res = await runAgentStart(lastSample);
    if (res && res.pending_task_ids.length > 0) {
      setConfirmTask(res.pending_task_ids[0]);
    }
  }, [lastSample]);

  return (
    <div className="confirm-section">
      <div className="clash-head-row">
        <h3>人在回路 · 确认闸 <span className="confirm-tag">session</span></h3>
        <button
          className="btn-primary btn-sm"
          onClick={handleStartRun}
          disabled={!engineConnected || confirmLoading}
        >
          {confirmLoading ? '起图中…' : '起图挂起'}
        </button>
      </div>
      <p className="clash-empty confirm-hint">
        人工把关通路 — 起图挂起后逐 task 放行/拒绝 (与上方「自动出图」区分: 自动=一键全链路, 这里=同 thread 真续跑)
      </p>
      {agentRun && (
        <div className={`clash-item ${agentRun.pending_task_count > 0 ? 'clash-hit' : 'clash-ok'}`}>
          <span className="clash-scope">
            已挂起 {agentRun.thread_id} · {agentRun.pending_task_count} 个待确认 /
            CAD 已出 {agentRun.cad_result_count} 图元
          </span>
          {(agentRun.pending ?? []).map((p) => (
            <div key={p.task_id} className="pending-line">
              <span className="pending-kind">{p.type}</span>
              <span className="pending-id">{p.task_id}</span>
              {p.description && <span className="pending-desc">{p.description}</span>}
            </div>
          ))}
          {agentRun.preview_url && (
            <a className="pending-preview" href={agentRun.preview_url} target="_blank" rel="noreferrer">
              查看出图预览 →
            </a>
          )}
        </div>
      )}
      <div className="confirm-controls">
        <select
          value={confirmTask}
          onChange={(e) => setConfirmTask(e.target.value)}
          className="conflict-select"
        >
          {(agentRun?.pending_task_ids.length
            ? agentRun.pending_task_ids
            : ['door-3']
          ).map((t) => {
            const p = agentRun?.pending?.find((x) => x.task_id === t);
            const label = p ? `${t} · ${p.type}${p.description ? ' · ' + p.description : ''}` : t;
            return <option key={t} value={t}>{label}{agentRun ? '' : ' (演示)'}</option>;
          })}
        </select>
        <label className="confirm-radio">
          <input
            type="radio"
            name="confirm-decision"
            checked={confirmDecision}
            onChange={() => setConfirmDecision(true)}
          />
          放行
        </label>
        <label className="confirm-radio">
          <input
            type="radio"
            name="confirm-decision"
            checked={!confirmDecision}
            onChange={() => setConfirmDecision(false)}
          />
          拒绝
        </label>
        <button
          className="btn-primary btn-sm"
          onClick={handleConfirm}
          disabled={!engineConnected || confirmLoading}
        >
          {confirmLoading ? '确认中…' : '提交确认'}
        </button>
      </div>
      <p className="clash-empty">
        session 级: 点「起图挂起」起一次真实图停在确认点 → 对真实 task 放行/拒绝 →
        bridge 用同一 thread 真续跑出终态。未起图时提交 = 演示级 (bridge 用默认样本跑通链路)。
      </p>
      {confirmResults.map((r, i) => {
        const isResumed = r.resume?.resumed === true;
        const degraded = r.resume && !r.resume.resumed && r.resume.reason;
        const isSession = r.resume?.session === true;
        return (
          <div key={i} className={`clash-item ${isResumed ? 'clash-ok' : 'clash-hit'}`}>
            {isResumed ? (
              <span className="clash-clean">
                ✓ 已放行 · {isSession ? '同 thread 续跑' : '演示跑'} — 违规{' '}
                {r.resume?.rule_violation_count ?? 0} 条 / 出图{' '}
                {r.resume?.export_status ?? '?'} / {r.resume?.final_dwg_path}
              </span>
            ) : r.status === 'pending_confirm' ? (
              <span className="clash-detail">
                · {r.task_id} 已登记「拒绝」, 图继续挂起 (未 resume)
              </span>
            ) : degraded ? (
              <span className="clash-detail">
                · {r.task_id} 放行未成 — {degraded}
              </span>
            ) : (
              <span className="clash-detail">· {r.task_id} {r.status}</span>
            )}
          </div>
        );
      })}
    </div>
  );
}

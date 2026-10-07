import React, { useState, useCallback } from 'react';
import { useEngineStore } from './useEngineStore';
import { runConflict } from './engineApi';

/**
 * M5 两稿改动冲突检测区块 (bridge /api/conflict) — 从 App.tsx 抽出的独立子组件。
 * 两稿按元素 id 比对 (改值/新增/删除/几何重复)。交互模式与 M4 碰撞 / M2 扫图层
 * 对齐 (loading 态 / 显式 error 态 / 清空结果 三件套)。
 */
export default function ConflictSection() {
  const {
    engineConnected, lastSample,
    conflictResults, conflictLoading, conflictError,
  } = useEngineStore();

  // 两稿默认同 sample (自比 → 0 冲突); 稿B 下拉当前仅 residential_100sqm.json
  const [conflictSampleB, setConflictSampleB] = useState('residential_100sqm.json');

  const handleConflict = useCallback(async () => {
    await runConflict(lastSample, conflictSampleB);
  }, [lastSample, conflictSampleB]);

  const clearAll = () => {
    useEngineStore.getState().setConflictResults([]);
    useEngineStore.getState().setConflictError(false);
  };

  return (
    <div className="conflict-section">
      <div className="clash-head-row">
        <h3>改动冲突 (两稿比对){conflictResults.length > 1 ? <span className="clash-count-note">已 {conflictResults.length} 份</span> : null}
          <span className="tool-tag">M5</span>
        </h3>
        <div className="conflict-controls">
          <select
            value={conflictSampleB}
            onChange={(e) => setConflictSampleB(e.target.value)}
            className="conflict-select"
            title="稿 B 下拉候选 = data/sample/ 下 JSON 文件；当前仅 1 份样本 (真多稿比对待业务提供第 2 稿)"
          >
            <option value="residential_100sqm.json">residential_100sqm.json</option>
          </select>
          <button
            className="btn-primary btn-sm"
            onClick={handleConflict}
            disabled={!engineConnected || conflictLoading}
          >
            {conflictLoading ? '比对中…' : '比冲突'}
          </button>
          {conflictResults.length > 0 && (
            <button
              className="btn-sm clash-clear-btn"
              onClick={clearAll}
              title="清除全部冲突比对结果"
            >
              清空
            </button>
          )}
        </div>
      </div>
      {conflictError && (
        <p className="clash-err">引擎断连或返回异常 · 本次比对未生效, 请检查右上角连接状态后重试</p>
      )}
      {conflictResults.length === 0 && !conflictError && (
        <p className="clash-empty">尚未比对 — 点「比冲突」比对稿A与稿B 的元素改动 (改值/新增/删除)</p>
      )}
      {conflictResults.map((r, i) => (
        <div key={i} className={`clash-item ${r.count > 0 ? 'clash-hit' : 'clash-ok'}`}>
          {i === conflictResults.length - 1 && <span className="clash-latest">最新</span>}
          {r.count > 0 ? (
            <>
              <span className="clash-badge">{r.count}</span>
              <span className="clash-scope">{r.sample_a} vs {r.sample_b}</span>
              {r.conflicts.slice(0, 8).map((c, j) => (
                <div key={j} className="clash-line">
                  <span className={`clash-kind ${c.kind === 'duplicate' ? 'clash-kind-dup' : ''}`}>
                    {c.kind === 'duplicate' ? '重复' : c.kind}
                  </span>
                  <span className="clash-ids">
                    {c.kind === 'duplicate'
                      ? `${c.category}/${c.id_a} ≡ ${c.id_b}${c.extra_ids?.length ? ` +${c.extra_ids.length} 个` : ''} @ (${c.coord?.join(', ')})`
                      : `${c.category}/${c.id}${c.field ? `.${c.field}` : ''}`}
                  </span>
                  {c.kind === 'duplicate'
                    ? <span className="clash-detail">同坐标不同 id (容差 {c.tolerance_m}m)</span>
                    : c.field && <span className="clash-detail">{String(c.a_value)} → {String(c.b_value)}</span>}
                </div>
              ))}
              {r.conflicts.length > 8 && <div className="clash-detail">… 共 {r.conflicts.length} 条</div>}
              {r.summary_consistent === false && (r.summary_issues?.length ?? 0) > 0 && (
                <div className="clash-line clash-diag-bad">
                  <span className="clash-kind">自洽诊断</span>
                  <span className="clash-detail">
                    汇总计数与列表失步 ({r.summary_issues!.length} 处) — 上方条数不可信, 以列表为准
                  </span>
                </div>
              )}
            </>
          ) : (
            <span className="clash-clean">✓ 两稿无改动冲突 · {r.sample_a} vs {r.sample_b}</span>
          )}
        </div>
      ))}
    </div>
  );
}

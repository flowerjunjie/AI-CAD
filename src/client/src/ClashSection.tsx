import React, { useState, useCallback } from 'react';
import { useEngineStore } from './useEngineStore';
import { runClashCheck } from './engineApi';

/**
 * M4 跨专业碰撞检测区块 (bridge /api/clash) — 从 App.tsx 抽出的独立子组件。
 * 品红色呼应出图 CLASH 层。交互模式与 M5 冲突 / M2 扫图层 对齐 (loading 态 /
 * 显式 error 态 / 清空结果 三件套), 主文件不再持有该区块的 state 与渲染。
 */
export default function ClashSection() {
  const {
    engineConnected, lastSample,
    clashResults, clashLoading, clashError,
  } = useEngineStore();

  const handleClash = useCallback(async () => {
    await runClashCheck(lastSample);
  }, [lastSample]);

  const clearAll = () => {
    useEngineStore.getState().setClashResults([]);
    useEngineStore.getState().setClashError(false);
  };

  return (
    <div className="clash-section">
      <div className="clash-head-row">
        <h3>碰撞检测{clashResults.length > 1 ? <span className="clash-count-note">已 {clashResults.length} 份</span> : null}
          <span className="tool-tag">M4</span>
        </h3>
        <div className="clash-head-actions">
          {clashResults.length > 0 && (
            <button
              className="btn-sm clash-clear-btn"
              onClick={clearAll}
              title="清除全部碰撞检测结果"
            >
              清空
            </button>
          )}
          <button
            className="btn-primary btn-sm"
            onClick={handleClash}
            disabled={!engineConnected || clashLoading}
          >
            {clashLoading ? '检测中…' : '检测碰撞'}
          </button>
        </div>
      </div>
      {clashError && (
        <p className="clash-err">引擎断连或返回异常 · 本次检测未生效, 请检查右上角连接状态后重试</p>
      )}
      {clashResults.length === 0 && !clashError && (
        <p className="clash-empty">尚未检测 — 点「检测碰撞」跑 {lastSample} 的跨专业碰撞 (管线/暖通 vs 结构梁柱)</p>
      )}
      {clashResults.map((r, i) => (
        <div key={i} className={`clash-item ${r.count > 0 ? 'clash-hit' : 'clash-ok'}`}>
          {i === clashResults.length - 1 && <span className="clash-latest">最新</span>}
          {r.count > 0 ? (
            <>
              <span className="clash-badge">{r.count}</span>
              <span className="clash-scope">{r.sample}</span>
              {r.tolerance_source && (
                <span className="clash-detail">
                  容差 {r.tolerance_m}m ({r.tolerance_source})
                </span>
              )}
              {r.clashes.map((c, j) => (
                <div key={j} className="clash-line">
                  <span className="clash-kind">{c.kind}</span>
                  <span className="clash-ids">{c.a_id} × {c.b_id}</span>
                  <span className="clash-detail">{c.detail}</span>
                </div>
              ))}
              {r.clashes_consistent === false && (r.clashes_issues?.length ?? 0) > 0 && (
                <div className="clash-line clash-diag-bad">
                  <span className="clash-kind">自洽诊断</span>
                  <span className="clash-detail">
                    {r.clashes_issues!.length} 处脏碰撞 (a≠b / 非法 kind / id 不在 raw) — 出图圈位可能失真
                  </span>
                </div>
              )}
            </>
          ) : (
            <span className="clash-clean">
              ✓ 无跨专业碰撞 · {r.sample}
              {r.clashes_consistent === false && ' · 自洽诊断异常'}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

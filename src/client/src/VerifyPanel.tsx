import React from 'react';
import { useEngineStore } from './useEngineStore';
import { runBatchVerify, runDwgMarkerVerify } from './engineApi';

/**
 * 出图/批量 自洽体检区块 (bridge /api/rules/batch-verify + /api/dwg-marker-verify, 机制层)。
 *
 * 从 App.tsx 检查工具组里抽出的独立子组件 (与 ClashSection / DwgScanSection 同层同范式):
 *   - 批量校验体检 (秒级, 走主链路出元素 + run_batch_check, 不触发出图)
 *   - 出图圈对账 (重依赖, 懒触发 run_agent_demo 全链路出图, 冷启动 ~58s → loading 态防卡死)
 * 诚实边界: 只判「产出数字自身是否自洽 / 出图侧画没画够」, 不判业务对错 (红线二)。
 */
export default function VerifyPanel() {
  const {
    engineConnected, lastSample,
    batchVerify, batchVerifyLoading,
    dwgMarkerVerify, dwgMarkerVerifyLoading,
  } = useEngineStore();

  const handleBatch = React.useCallback(async () => {
    await runBatchVerify(lastSample);
  }, [lastSample]);

  const handleMarker = React.useCallback(async () => {
    await runDwgMarkerVerify(lastSample);
  }, [lastSample]);

  return (
    <div className="verify-section">
      <div className="clash-head-row">
        <h3>出图/批量 自洽体检<span className="tool-tag">机制层</span></h3>
      </div>
      <p className="clash-empty">
        数字自身失步 / 出图侧漏画多画 → 在此可见 (不判业务对错)
      </p>

      {/* 批量校验体检 (秒级) */}
      <div className="verify-controls">
        <button
          className="btn-primary btn-sm"
          onClick={handleBatch}
          disabled={!engineConnected || batchVerifyLoading}
        >
          {batchVerifyLoading ? '批量体检中…' : '批量校验体检'}
        </button>
        <span className="clash-detail">走主链路出元素 + 批量校验, 秒级, 不触发出图</span>
      </div>
      {batchVerify && (
        <div className={`clash-item ${batchVerify.ok ? 'clash-ok' : 'clash-hit'}`}>
          <div className="clash-line">
            <span className="clash-kind">{batchVerify.ok ? '报告自洽' : '报告失步'}</span>
            <span className="clash-scope">
              校验 {batchVerify.checked} / 违规 {batchVerify.total} · {batchVerify.sample}
            </span>
          </div>
          {batchVerify.issues.map((it, i) => (
            <div key={i} className="clash-line"><span className="clash-ids">{it}</span></div>
          ))}
        </div>
      )}

      {/* 出图圈对账 (重依赖, loading 态) */}
      <div className="verify-controls">
        <button
          className="btn-sm verify-marker-btn"
          onClick={handleMarker}
          disabled={!engineConnected || dwgMarkerVerifyLoading}
          title="重依赖: 全链路出图 (~58s 冷启动), 出图 CLASH/DUP 圈实数 vs 期望对账"
        >
          {dwgMarkerVerifyLoading ? '出图对账中 (慢, ~58s)…' : '出图圈对账'}
        </button>
      </div>
      {dwgMarkerVerify && (
        <div className={`clash-item ${dwgMarkerVerify.ok ? 'clash-ok' : 'clash-hit'}`}>
          <div className="clash-line">
            <span className="clash-kind">{dwgMarkerVerify.ok ? '圈数对账' : '圈数失步'}</span>
            <span className="clash-scope">
              CLASH {dwgMarkerVerify.clash_drawn}/{dwgMarkerVerify.clash_expected} ·
              DUP {dwgMarkerVerify.dup_drawn}/{dwgMarkerVerify.dup_expected}
            </span>
          </div>
          {dwgMarkerVerify.issues.map((it, i) => (
            <div key={i} className="clash-line"><span className="clash-ids">{it}</span></div>
          ))}
        </div>
      )}
    </div>
  );
}

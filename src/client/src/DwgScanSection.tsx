import React, { useState, useCallback } from 'react';
import { useEngineStore } from './useEngineStore';
import { runDwgScan } from './engineApi';

const DWG_SCAN_SAMPLES = [
  'electrical_sample.dxf', 'hvac_sample.dxf',
  'plumbing_sample.dxf', 'structural_sample.dxf',
];

/**
 * M2 制图约定对齐工具区块 (bridge /api/dwg-scan, I 段) — 从 App.tsx 抽出的独立子组件。
 * 扫 DWG → 图层/块名/ATTRIB 频率报告, 专家据此把映射 dict 从填空题变选择题。
 * 蓝紫色呼应出图规范。默认扫电气样例 (电气是唯一有真实 DWG 上游的专业)。
 * 交互模式与 M4/M5 对齐: 按钮 loading 态; 断连走 P5 通用 fetchError 横幅 (无区块内 error 态, 与 M4/M5 有本地 error 态的差异是端点契约差异: M2 是读操作、无"清空"语义)。
 */
export default function DwgScanSection() {
  const {
    engineConnected, dwgScan, dwgScanLoading,
  } = useEngineStore();

  const [dwgScanSample, setDwgScanSample] = useState('electrical_sample.dxf');

  const handleDwgScan = useCallback(async () => {
    await runDwgScan(dwgScanSample);
  }, [dwgScanSample]);

  return (
    <div className="dwgscan-section">
      <div className="clash-head-row">
        <h3>DWG 制图约定 <span className="collab-tag">M2</span></h3>
        <div className="dwgscan-controls">
          <select
            value={dwgScanSample}
            onChange={(e) => setDwgScanSample(e.target.value)}
            className="conflict-select"
          >
            {DWG_SCAN_SAMPLES.map((s) => (
              <option key={s} value={s}>{s.replace('_sample.dxf', '')}</option>
            ))}
          </select>
          <button
            className="btn-primary btn-sm"
            onClick={handleDwgScan}
            disabled={!engineConnected || dwgScanLoading}
          >
            {dwgScanLoading ? '扫描中…' : '扫图层'}
          </button>
        </div>
      </div>
      {dwgScan ? (
        <div className={`clash-item ${dwgScan.layer_count > 0 ? 'clash-hit' : 'clash-ok'}`}>
          <div className="clash-line">
            <span className="clash-kind">{dwgScan.sample}</span>
            <span className="clash-scope">
              图层 {dwgScan.layer_count} · INSERT {dwgScan.insert_total}
            </span>
          </div>
          {Object.entries(dwgScan.layers).slice(0, 6).map(([layer, info]) => (
            <div key={layer} className="clash-line">
              <span className="clash-kind dwgscan-layer">{layer}</span>
              <span className="clash-ids">
                {Object.entries(info.entity_counts).map(([t, n]) => `${t}×${n}`).join(' ')}
              </span>
              {info.block_names.length > 0 && (
                <span className="clash-detail">块: {info.block_names.slice(0, 4).join(', ')}</span>
              )}
            </div>
          ))}
          {Object.keys(dwgScan.attrib_tags).length > 0 && (
            <div className="clash-line">
              <span className="clash-kind dwgscan-attr">ATTRIB</span>
              <span className="clash-detail">
                {Object.entries(dwgScan.attrib_tags).map(([t, n]) => `${t}×${n}`).join(' ')}
              </span>
            </div>
          )}
          <p className="clash-empty">
            频率报告 · 专家据此回填映射 dict (docs/element-upstream-contract.md §5), 不判定 kind 归属
          </p>
        </div>
      ) : (
        <p className="clash-empty">点「扫图层」扫 {dwgScanSample} → 图层/块名/ATTRIB 频率报告</p>
      )}
    </div>
  );
}

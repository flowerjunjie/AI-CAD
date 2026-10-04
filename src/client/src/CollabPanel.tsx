import React, { useState } from 'react';
import { useEngineStore } from './useEngineStore';
import {
  fetchCollabSnapshot, collabAcquire, collabRelease,
  fetchCollabElements, fetchCollabVerify, fetchCollabDeadlockLive,
  fetchPermissionMatrix,
} from './engineApi';

/**
 * M5 协同持久层面板 (bridge H 段) — 从 App.tsx 抽出的独立子组件 (缓解 854 行巨型组件)。
 *
 * 使用体验优化 (UI 专家团): 主操作 vs 诊断工具 视觉分层
 *  - 主操作区 (设计师日常): 选设计师/资源 → 取锁/放锁 + 看快照 + 拉元素, 直接可见。
 *  - 诊断工具区 (低频, 机制层自检): 校验/查死锁/看矩阵 折叠进「诊断」子区,
 *    默认收起 — 降低认知负荷, 需要时才展开。
 *  诚实标注: 本地单进程演示, 非跨设计师同步; 真·多机协同待业务定协议。
 */
export default function CollabPanel() {
  const {
    engineConnected, lastSample,
    collabSnapshot, collabOps, collabLoading,
    collabElements, collabElementsLoading,
    collabVerify, collabDeadlock, permissionMatrix,
  } = useEngineStore();

  // 主操作 state (与 App.tsx 抽出的局部 state 保持一致的默认值)
  const [collabDesigner, setCollabDesigner] = useState('alice');
  const [collabResource, setCollabResource] = useState('sheet-a');
  const [showDiag, setShowDiag] = useState(false);

  const handleSnapshot = () => void fetchCollabSnapshot(collabDesigner);
  const handleAcquire = () => collabAcquire(collabDesigner, collabResource, 'write');
  const handleRelease = () => collabRelease(collabDesigner, collabResource);
  const handleElements = () => fetchCollabElements(lastSample);
  const handleVerify = () => void fetchCollabVerify();
  const handleDeadlock = () => void fetchCollabDeadlockLive();
  const handleMatrix = () => void fetchPermissionMatrix();

  // 选中资源的重复标记 (取锁前提示用): duplicate_of 非空 = 疑似重复
  const selected = collabElements?.resources?.find((r) => r.id === collabResource);
  const dupWarn = selected?.duplicate_of ?? null;

  return (
    <div className="collab-section">
      <div className="clash-head-row">
        <h3>协同持久层 <span className="collab-tag">local</span></h3>
        <button
          className="btn-primary btn-sm"
          onClick={handleSnapshot}
          disabled={!engineConnected}
        >
          看快照
        </button>
      </div>

      {/* 主操作区: 日常锁流程 (选设计师/资源 + 取放锁 + 拉元素) */}
      <div className="collab-controls">
        <select value={collabDesigner} onChange={(e) => setCollabDesigner(e.target.value)} className="conflict-select">
          {['alice', 'bob', 'carol'].map((d) => (
            <option key={d} value={d}>{d}</option>
          ))}
        </select>
        <select value={collabResource} onChange={(e) => setCollabResource(e.target.value)} className="conflict-select">
          {collabElements?.resources?.length ? collabElements.resources.map((r) => (
            <option key={r.id} value={r.id}>
              {r.category}/{r.id}{r.duplicate_of ? ` (≈${r.duplicate_of})` : ''}
            </option>
          )) : (
            <option value="sheet-a">sheet-a</option>
          )}
        </select>
        <button
          className="btn-sm collab-scan-btn"
          onClick={handleElements}
          disabled={!engineConnected || collabElementsLoading}
          title="拉当前 lastSample 的真实 CAD 元素清单 (取锁前看是否疑似重复)"
        >
          {collabElementsLoading ? '…' : '拉元素'}
        </button>
        <button className="btn-primary btn-sm" onClick={handleAcquire} disabled={!engineConnected || collabLoading}>
          {collabLoading ? '…' : '取锁'}
        </button>
        <button className="btn-sm collab-release-btn" onClick={handleRelease} disabled={!engineConnected || collabLoading}>
          放锁
        </button>
      </div>

      {/* 取锁前「疑似重复」警示 (高频主流程提示, 常显) */}
      {dupWarn && (
        <div className="clash-item clash-warn">
          <span className="clash-kind clash-kind-dup">疑似重复</span>
          <span className="clash-scope">{collabResource} 与 {dupWarn} 同坐标 (几何等价类)</span>
          <p className="clash-empty">取锁前建议先核对是否为误建 (业务上是否允许同坐标由专家定)</p>
        </div>
      )}

      {/* 快照结果 (主操作, 常显) */}
      {collabSnapshot ? (
        <div className={`clash-item ${Object.keys(collabSnapshot.write_holders).length > 0 ? 'clash-hit' : 'clash-ok'}`}>
          <div className="clash-line">
            <span className="clash-kind">{collabSnapshot.source === 'file' ? '持久快照' : '空态'}</span>
            <span className="clash-scope">
              写锁 {Object.keys(collabSnapshot.write_holders).length} · 事件 {collabSnapshot.event_count}
            </span>
          </div>
          {Object.entries(collabSnapshot.write_holders).map(([res, holder]) => (
            <div key={res} className="clash-line">
              <span className="clash-kind">lock</span>
              <span className="clash-ids">{res} → {holder}</span>
            </div>
          ))}
          {(collabSnapshot.recent_events || []).slice(-4).map((ev) => (
            <div key={ev.seq} className="clash-line">
              <span className="clash-kind">{ev.type}</span>
              <span className="clash-ids">#{ev.seq} {ev.actor}/{ev.resource_id}</span>
            </div>
          ))}
          <p className="clash-empty">本地单进程演示 · 非跨设计师同步 (业务定协议后接在线协同)</p>
        </div>
      ) : (
        <p className="clash-empty">点「看快照」拉协同状态 · 取锁/放锁走本地持久化 (state.json)</p>
      )}

      {/* 诊断工具区 (低频, 机制层自检): 默认折叠, 需要时展开 */}
      <div className="collab-diag">
        <button
          className="collab-diag-toggle"
          onClick={() => setShowDiag((s) => !s)}
          aria-expanded={showDiag}
        >
          {showDiag ? '▾' : '▸'} 诊断工具
          <span className="collab-diag-hint">校验 / 死锁 / 权限矩阵 (机制层自检)</span>
        </button>
        {showDiag && (
          <div className="collab-diag-body">
            <div className="collab-diag-controls">
              <button className="btn-sm collab-scan-btn" onClick={handleVerify} disabled={!engineConnected}>校验日志</button>
              <button className="btn-sm collab-scan-btn" onClick={handleDeadlock} disabled={!engineConnected}>查死锁</button>
              <button className="btn-sm collab-scan-btn" onClick={handleMatrix} disabled={!engineConnected}>看矩阵</button>
            </div>

            {collabVerify && (
              <div className={`clash-item ${collabVerify.valid ? 'clash-ok' : 'clash-hit'}`}>
                <div className="clash-line">
                  <span className="clash-kind">{collabVerify.valid ? '日志自洽' : '日志不自洽'}</span>
                  <span className="clash-scope">
                    回放写锁 {Object.keys(collabVerify.replayed_write_holders).length} ·
                    问题 {collabVerify.issues.length}
                    {collabVerify.source === 'empty' ? ' · 空态' : ''}
                  </span>
                </div>
                {collabVerify.issues.map((it, i) => (
                  <div key={i} className="clash-line"><span className="clash-ids">{it}</span></div>
                ))}
              </div>
            )}

            {collabDeadlock && (
              <div className={`clash-item ${collabDeadlock.deadlocked ? 'clash-hit' : 'clash-ok'}`}>
                <div className="clash-line">
                  <span className="clash-kind">{collabDeadlock.deadlocked ? '死锁环' : '无等待环'}</span>
                  <span className="clash-scope">
                    等待边 {Object.keys(collabDeadlock.wait_edges).length}
                    {collabDeadlock.source === 'empty' ? ' · 空态' : ''}
                  </span>
                </div>
                {collabDeadlock.cycle.length > 0 && (
                  <div className="clash-line">
                    <span className="clash-ids">环: {collabDeadlock.cycle.join(' → ')}</span>
                  </div>
                )}
              </div>
            )}

            {permissionMatrix && (
              <div className={`clash-item ${permissionMatrix.valid ? 'clash-ok' : 'clash-hit'}`}>
                <div className="clash-line">
                  <span className="clash-kind">{permissionMatrix.valid ? '矩阵自洽' : '矩阵异味'}</span>
                  <span className="clash-scope">
                    角色 {Object.keys(permissionMatrix.roles).length} · 问题 {permissionMatrix.issues.length}
                  </span>
                </div>
                {Object.entries(permissionMatrix.roles).map(([role, actions]) => (
                  <div key={role} className="clash-line">
                    <span className="clash-kind">{role}</span>
                    <span className="clash-ids">{actions.join(', ')}</span>
                  </div>
                ))}
                {permissionMatrix.issues.map((it, i) => (
                  <div key={i} className="clash-line"><span className="clash-ids">{it}</span></div>
                ))}
              </div>
            )}
            <p className="clash-empty">机制层自检工具 · 非「多机协同是否一致」(那个仍需业务定协议)</p>
          </div>
        )}
      </div>
    </div>
  );
}

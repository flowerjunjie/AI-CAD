import React, { useEffect, useState, useCallback } from 'react';
import './App.css';
import { useEngineStore } from './useEngineStore';
import { syncEngine, runPipeline, runRagSearch, previewUrl, API,
        runClashCheck, runConflict, runAgentConfirm } from './engineApi';
import { PLACEHOLDERS } from './placeholders';
import RuleEditorPanel from './RuleEditorPanel';

declare global {
  interface Window {
    electronAPI?: {
      healthCheck: () => Promise<any>;
      listRules: () => Promise<any>;
      searchKnowledge: (query: string) => Promise<any>;
    };
  }
}

const STEPS = ['意图理解', '方案结构化', 'CAD执行', '规则校验', '成果输出'];

function App() {
  const {
    engineConnected, phase, rules, violations,
    running, lastSample, pipelineResult, ragResults, ragQuery,
    clashResults, clashLoading, conflictResults, conflictLoading,
    confirmResults, confirmLoading,
  } = useEngineStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [previewKey, setPreviewKey] = useState(0);
  const [useLlm, setUseLlm] = useState(false);
  // Phase 2 规则编辑器: 右侧规则面板加「编辑器」子 tab (列表 / DSL 编辑器)
  const [rulesPane, setRulesPane] = useState<'list' | 'editor'>('list');
  // 列表态源过滤 tab (原 rulesTab, 挪进列表子面板)
  const [shownTab, setShownTab] = useState<'hardcoded' | 'dsl' | 'all'>('all');

  // 启动 + 周期性探测引擎可达性
  useEffect(() => {
    syncEngine();
    const timer = setInterval(syncEngine, 8000);
    return () => clearInterval(timer);
  }, []);

  const shownRules = shownTab === 'all' ? rules : rules.filter((r) => r.source === shownTab);
  const previewSrc = `${API}/api/preview?sample=${encodeURIComponent(lastSample)}`;

  const handleRun = useCallback(async () => {
    await runPipeline(lastSample, useLlm);
    setPreviewKey((k) => k + 1); // 强制重刷 <img>
  }, [lastSample, useLlm]);

  const handleRag = useCallback(async () => {
    if (!searchQuery.trim()) return;
    await runRagSearch(searchQuery);
  }, [searchQuery]);

  // M4 碰撞检测 (bridge /api/clash): 默认用当前 lastSample 检测
  const handleClash = useCallback(async () => {
    await runClashCheck(lastSample);
  }, [lastSample]);

  // M5 改动冲突检测 (bridge /api/conflict): 两稿默认同 sample (自比 → 0 冲突)
  const [conflictSampleB, setConflictSampleB] = useState('residential_100sqm.json');
  const handleConflict = useCallback(async () => {
    await runConflict(lastSample, conflictSampleB);
  }, [lastSample, conflictSampleB]);

  // 人在回路确认闸 (bridge /agent/confirm, 演示通路): 对演示 task 放行/拒绝
  // confirmed=true 时 bridge 真跑一次 graph 挂起→放行→resume 出终态摘要。
  const [confirmTask, setConfirmTask] = useState('door-3');
  const [confirmDecision, setConfirmDecision] = useState(true);
  const handleConfirm = useCallback(async () => {
    await runAgentConfirm(confirmTask, confirmDecision);
  }, [confirmTask, confirmDecision]);

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1>AI-CAD</h1>
          <span className="version">v0.1.0 · 专业 GUI</span>
        </div>
        <div className="header-right">
          <span
            className={`status-badge ${engineConnected ? 'status-ok' : 'status-err'}`}
            title={engineConnected ? `桥: ${API}` : `无法连接 ${API} — 请启动 start_gui.bat`}
          >
            {engineConnected ? '● 引擎已连接' : '● 引擎未连接'}
          </span>
          <span className="phase-tag">{phase}</span>
        </div>
      </header>

      {/* Main */}
      <main className="main">
        {/* 左: CAD 视图 */}
        <section className="panel cad-panel">
          <div className="panel-head-row">
            <h2>CAD 视图 · {lastSample}</h2>
            <button
              className="btn-primary btn-sm"
              onClick={() => setPreviewKey((k) => k + 1)}
              disabled={!engineConnected}
              title="重新拉取真户型图"
            >
              重新出图
            </button>
          </div>

          {engineConnected ? (
            <div className="cad-view-img">
              <img
                key={previewKey}
                src={previewSrc}
                alt="户型图预览"
                onError={(e) => {
                  const img = e.currentTarget;
                  img.style.display = 'none';
                  const holder = img.parentElement!.querySelector<HTMLElement>('.cad-img-fallback');
                  if (holder) holder.style.display = 'flex';
                }}
              />
              <div className="cad-view-placeholder cad-img-fallback" style={{ display: 'none' }}>
                <p>户型图暂不可用</p>
                <p className="hint">桥未返回 PNG，检查 /api/preview</p>
              </div>
            </div>
          ) : (
            <div className="cad-view-placeholder">
              <p>引擎未连接</p>
              <p className="hint">启动 start_gui.bat 后户型图将自动出现</p>
            </div>
          )}

          {pipelineResult && (
            <div className="cad-meta">
              <span>{pipelineResult.project_type}</span>
              <span>{pipelineResult.zones.length} 功能区</span>
              <span>{pipelineResult.task_count} 任务</span>
            </div>
          )}
        </section>

        {/* 中: Agent 流程 */}
        <section className="panel agent-panel">
          <h2>Agent 执行流程</h2>
          <div className="agent-flow">
            {STEPS.map((step, i) => (
              <React.Fragment key={step}>
                <div
                  className={`flow-step ${running ? (i === 0 ? 'active' : 'pending') : pipelineResult ? 'done' : ''}`}
                >
                  <div className="step-dot" />
                  <div className="step-label">{step}</div>
                </div>
                {i < STEPS.length - 1 && <div className="step-arrow">→</div>}
              </React.Fragment>
            ))}
          </div>

          <div className="agent-controls">
            <label className="chk">
              <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
              启用 LLM 主导（联网·较慢）
            </label>
            <button className="btn-primary" onClick={handleRun} disabled={running || !engineConnected}>
              {running ? '运行中…' : '运行流水线'}
            </button>
          </div>

          <div className="agent-status">
            {running ? (
              <p><strong>运行中</strong> — 正在调用 LangGraph 全链路…</p>
            ) : pipelineResult ? (
              <p>
                完成 · <strong>{pipelineResult.violations.length}</strong> 条规范违规 · DWG: {pipelineResult.dwg_path}
              </p>
            ) : (
              <p>当前状态: <strong>{engineConnected ? '等待运行' : '引擎未连接'}</strong></p>
            )}
          </div>

          {/* 违规清单 — 真数据 */}
          {violations.length > 0 && (
            <div className="violations">
              <h3>规范违规 ({violations.length})</h3>
              {violations.map((v, i) => (
                <div key={i} className={`violation sev-${v.severity}`}>
                  <span className="vio-name">{v.rule_name}</span>
                  <span className="vio-desc">{v.description}</span>
                  {v.suggested_fix && <span className="vio-fix">→ {v.suggested_fix}</span>}
                </div>
              ))}
            </div>
          )}

          {/* M4 碰撞检测 — 真数据 (bridge /api/clash, 品红色呼应出图 CLASH 层) */}
          <div className="clash-section">
            <div className="clash-head-row">
              <h3>碰撞检测</h3>
              <button
                className="btn-primary btn-sm"
                onClick={handleClash}
                disabled={!engineConnected || clashLoading}
              >
                {clashLoading ? '检测中…' : '检测碰撞'}
              </button>
            </div>
            {clashResults.length === 0 && (
              <p className="clash-empty">尚未检测 — 点「检测碰撞」跑 {lastSample} 的跨专业碰撞 (管线/暖通 vs 结构梁柱)</p>
            )}
            {clashResults.map((r, i) => (
              <div key={i} className={`clash-item ${r.count > 0 ? 'clash-hit' : 'clash-ok'}`}>
                {r.count > 0 ? (
                  <>
                    <span className="clash-badge">{r.count}</span>
                    <span className="clash-scope">{r.sample}</span>
                    {r.clashes.map((c, j) => (
                      <div key={j} className="clash-line">
                        <span className="clash-kind">{c.kind}</span>
                        <span className="clash-ids">{c.a_id} × {c.b_id}</span>
                        <span className="clash-detail">{c.detail}</span>
                      </div>
                    ))}
                  </>
                ) : (
                  <span className="clash-clean">✓ 无跨专业碰撞 · {r.sample}</span>
                )}
              </div>
            ))}
          </div>

          {/* M5 改动冲突检测 — 真数据 (bridge /api/conflict, 两稿按元素 id 比对) */}
          <div className="conflict-section">
            <div className="clash-head-row">
              <h3>改动冲突 (两稿比对)</h3>
              <div className="conflict-controls">
                <select
                  value={conflictSampleB}
                  onChange={(e) => setConflictSampleB(e.target.value)}
                  className="conflict-select"
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
              </div>
            </div>
            {conflictResults.length === 0 && (
              <p className="clash-empty">尚未比对 — 点「比冲突」比对稿A与稿B 的元素改动 (改值/新增/删除)</p>
            )}
            {conflictResults.map((r, i) => (
              <div key={i} className={`clash-item ${r.count > 0 ? 'clash-hit' : 'clash-ok'}`}>
                {r.count > 0 ? (
                  <>
                    <span className="clash-badge">{r.count}</span>
                    <span className="clash-scope">{r.sample_a} vs {r.sample_b}</span>
                    {r.conflicts.slice(0, 8).map((c, j) => (
                      <div key={j} className="clash-line">
                        <span className="clash-kind">{c.kind}</span>
                        <span className="clash-ids">{c.category}/{c.id}{c.field ? `.${c.field}` : ''}</span>
                        {c.field && <span className="clash-detail">{String(c.a_value)} → {String(c.b_value)}</span>}
                      </div>
                    ))}
                    {r.conflicts.length > 8 && <div className="clash-detail">… 共 {r.conflicts.length} 条</div>}
                  </>
                ) : (
                  <span className="clash-clean">✓ 两稿无改动冲突 · {r.sample_a} vs {r.sample_b}</span>
                )}
              </div>
            ))}
          </div>

          {/* 人在回路确认闸 — 演示通路 (bridge /agent/confirm → graph 挂起→放行→resume) */}
          <div className="confirm-section">
            <div className="clash-head-row">
              <h3>人在回路 · 确认闸 <span className="confirm-tag">演示通路</span></h3>
            </div>
            <div className="confirm-controls">
              <select
                value={confirmTask}
                onChange={(e) => setConfirmTask(e.target.value)}
                className="conflict-select"
              >
                <option value="door-3">door-3</option>
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
              演示态: 提交「放行」→ bridge 真跑一次图挂起→放行→resume, 出终态摘要 (违规数 / DWG 路径 / 出图状态)。
              非设计师对真实出图结果的逐 task 确认 (前端 session 续跑待接)。
            </p>
            {confirmResults.map((r, i) => {
              const isResumed = r.resume?.resumed === true;
              const degraded = r.resume && !r.resume.resumed && r.resume.reason;
              return (
                <div key={i} className={`clash-item ${isResumed ? 'clash-ok' : 'clash-hit'}`}>
                  {isResumed ? (
                    <span className="clash-clean">
                      ✓ 已放行 · 图侧 resume 出终态 — 违规 {r.resume?.rule_violation_count ?? 0} 条 /
                      出图 {r.resume?.export_status ?? '?'} / {r.resume?.final_dwg_path}
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
        </section>

        {/* 右: 规则 + 知识 */}
        <section className="panel rules-panel">
          <div className="panel-head-row">
            <h2>规范规则 · {rules.length}</h2>
            <div className="tabs">
              <button className={`tab ${rulesPane === 'list' ? 'tab-active' : ''}`} onClick={() => setRulesPane('list')}>
                列表
              </button>
              <button className={`tab ${rulesPane === 'editor' ? 'tab-active' : ''}`} onClick={() => setRulesPane('editor')}>
                DSL 编辑器
              </button>
            </div>
          </div>

          {rulesPane === 'list' ? (
            <>
            <div className="rules-list">
              <div className="panel-head-row rules-pane-toggle">
                <div className="tabs">
                  {(['all', 'hardcoded', 'dsl'] as const).map((t) => (
                    <button
                      key={t}
                      className={`tab ${shownTab === t ? 'tab-active' : ''}`}
                      onClick={() => setShownTab(t)}
                    >
                      {t === 'all' ? '全部' : t === 'hardcoded' ? '硬编码' : 'DSL'}
                    </button>
                  ))}
                </div>
              </div>
              {shownRules.length === 0 && <div className="empty-hint">{engineConnected ? '无' : '引擎未连接，规则列表暂空'}</div>}
              {shownRules.map((rule) => (
                <div key={rule.rule_id} className="rule-item">
                  <div className="rule-main">
                    <span className="rule-name">{rule.name}</span>
                    <span className={`rule-sev sev-${rule.severity}`}>{rule.severity}</span>
                  </div>
                  <div className="rule-sub">
                    <span className="rule-code">{rule.code_ref}</span>
                    <span className="rule-src">{rule.source}</span>
                  </div>
                </div>
              ))}
            </div>

            <h2>知识检索 · RAG</h2>
            <div className="search-box">
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="输入规范问题，如：疏散走道最小宽度"
                onKeyDown={(e) => e.key === 'Enter' && handleRag()}
              />
              <button onClick={handleRag} disabled={!engineConnected}>检索</button>
            </div>
            {ragResults.length > 0 && (
              <div className="search-results">
                <div className="rag-hit-line">「{ragQuery}」命中 {ragResults.length} 条</div>
                {ragResults.map((r, i) => (
                  <div key={i} className="result-item">
                    <p>{r.text}</p>
                    <span className="rag-meta">{r.category} · 相关度 {r.score}</span>
                  </div>
                ))}
              </div>
            )}
            </>
          ) : (
            <RuleEditorPanel />
          )}
        </section>
      </main>

      {/* Footer: 占位符卡片（未实现能力，置灰；某专业规则 confirmed=true 即点亮该专业） */}
      <footer className="footer footer-cards">
        <div className="footer-title">发展占位 · 各专业专家补齐</div>
        <div className="placeholder-row">
          {PLACEHOLDERS.map((p) => {
            // 专家填值即点亮: 该占位声明的专业前缀里, 有 confirmed 规则 → 该专业变实
            const litPrefixes = p.disciplinePrefixes?.filter((pref) =>
              rules.some((r) => r.confirmed && r.rule_id.startsWith(pref)),
            ) || [];
            const allLit = litPrefixes.length > 0 && litPrefixes.length === p.domain.split('/').length;
            return (
              <div
                key={p.id}
                className={`placeholder-card ${allLit ? 'placeholder-card-lit' : ''}`}
                title={`负责方: ${p.owner}`}
              >
                <div className="ph-head">
                  <span className={`ph-badge ${allLit ? 'ph-badge-lit' : ''}`}>
                    {allLit ? '已点亮' : litPrefixes.length > 0 ? `点亮 ${litPrefixes.length} 专业` : '占位'}
                  </span>
                  <span className="ph-title">{p.title}</span>
                </div>
                <p className="ph-desc">{p.desc}</p>
                {p.disciplinePrefixes && (
                  <div className="ph-disciplines">
                    {p.disciplinePrefixes.map((pref, i) => {
                      const discLabel = p.domain.split('/')[i] || pref;
                      const lit = litPrefixes.includes(pref);
                      return (
                        <span key={pref} className={`ph-disc ${lit ? 'ph-disc-lit' : ''}`}>
                          {lit ? '●' : '○'} {discLabel}
                        </span>
                      );
                    })}
                  </div>
                )}
                <div className="ph-domain">{p.domain}</div>
              </div>
            );
          })}
        </div>
      </footer>
    </div>
  );
}

export default App;

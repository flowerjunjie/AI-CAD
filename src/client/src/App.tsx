import React, { useEffect, useState, useCallback } from 'react';
import './App.css';
import { useEngineStore } from './useEngineStore';
import { syncEngine, runPipeline, runRagSearch, previewUrl, API } from './engineApi';
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

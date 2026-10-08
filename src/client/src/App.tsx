import React, { useEffect, useState, useCallback } from 'react';
import './App.css';
import { useEngineStore } from './useEngineStore';
import { syncEngine, runPipeline, runRagSearch, previewUrl, API } from './engineApi';
import RuleEditorPanel from './RuleEditorPanel';
import CollabPanel from './CollabPanel';
import ConfirmGatePanel from './ConfirmGatePanel';
import ClashSection from './ClashSection';
import ConflictSection from './ConflictSection';
import DwgScanSection from './DwgScanSection';
import VerifyPanel from './VerifyPanel';
import PlaceholderFooter from './PlaceholderFooter';

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
    fetchError,
    running, lastSample, pipelineResult, ragResults, ragQuery,
  } = useEngineStore();

  const [searchQuery, setSearchQuery] = useState('');
  const [previewKey, setPreviewKey] = useState(0);
  const [useLlm, setUseLlm] = useState(false);
  // Phase 2 规则编辑器: 右侧规则面板加「编辑器」子 tab (列表 / DSL 编辑器)
  const [rulesPane, setRulesPane] = useState<'list' | 'editor'>('list');
  // 列表态源过滤 tab (原 rulesTab, 挪进列表子面板)
  const [shownTab, setShownTab] = useState<'hardcoded' | 'dsl' | 'all'>('all');

  // P11 占位卡 → 回填入口导航: 点「可推动」占位卡的「去回填」→ 切到右栏 DSL 编辑器
  // + 定位到该规则前缀首条规则 + 确保 DSL 规则已加载 (消除「看到占位不知去哪回填」断点)。
  // 具体定位逻辑收口在 PlaceholderFooter, 这里只负责切 tab (rulesPane 是 App 本地 state)。
  const handleGoBackfill = useCallback((_prefixes: string[] | undefined, _ownerId: string) => {
    setRulesPane('editor');
  }, []);

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

  // M4 碰撞 / M5 冲突 / M2 扫图层 / M5 协同 各自的状态与 handler
  // 已分别收口到 ClashSection / ConflictSection / DwgScanSection / CollabPanel。

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

      {/* P5 静默失败显式化 (通用): 最近一次因断连/异常未生效的操作, 统一横幅告知。
          区别于各区块分散置灰 — 设计师点任何端点没反应时, 这里显式说明哪个操作没生效。 */}
      {fetchError && (
        <div className="fetch-error-banner" role="alert">
          <span className="fetch-error-icon">⚠</span>
          <span>{fetchError} — 请确认右上角引擎连接状态后重试</span>
          <button
            className="fetch-error-dismiss"
            onClick={() => useEngineStore.getState().setFetchError(null)}
            aria-label="关闭提示"
          >
            ✕
          </button>
        </div>
      )}

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
              title="重新拉取当前出图预览 (不重跑流水线; 重跑请点中列「运行流水线」)"
            >
              刷新预览
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
              {running ? '运行中…' : '自动出图'}
            </button>
            <span className="ctl-hint">一键跑全链路出图 (无需人工介入); 想逐 task 把关用下方「人在回路」</span>
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

          {/* P1 中列主从分层: 出图/违规是主任务流, 下面是「检查与协同工具」组 (碰撞/冲突/DWG/协同),
              轻量分组标题帮设计师分清「先跑主线还是按需查工具」, 不重排 DOM 层级 */}
          <div className="agent-group-title">检查与协同工具 · 按需运行</div>

          {/* M4 碰撞检测 — 独立子组件 <ClashSection /> (bridge /api/clash, 品红色呼应出图 CLASH 层) */}
          <ClashSection />

          {/* M5 改动冲突检测 — 独立子组件 <ConflictSection /> (bridge /api/conflict, 两稿按元素 id 比对) */}
          <ConflictSection />

          {/* M5 协同持久层 — 独立子组件 CollabPanel (主操作/诊断工具分层, 缓解巨型组件) */}
          <CollabPanel />

          {/* M2 制图约定对齐 — 独立子组件 <DwgScanSection /> (bridge I 段, 扫 DWG → 图层/块名频率报告) */}
          <DwgScanSection />

          {/* 出图/批量 自洽体检 — 独立子组件 <VerifyPanel /> (bridge /api/rules/batch-verify + /api/dwg-marker-verify) */}
          <VerifyPanel />

          {/* 人在回路确认闸 — 独立子组件 <ConfirmGatePanel /> (session 级, 起真实图挂起→逐 task 确认→同 thread 真续跑) */}
          <ConfirmGatePanel />
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

      {/* Footer: 占位符卡片（未实现能力，置灰；某专业规则 confirmed=true 即点亮该专业）
          独立子组件 <PlaceholderFooter /> (P11 去回填导航 + M4 容差联动逻辑一并收口) */}
      <PlaceholderFooter onGoBackfill={handleGoBackfill} />
    </div>
  );
}

export default App;

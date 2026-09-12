import React, { useState, useEffect } from 'react';
import './App.css';

interface AppState {
  status: string;
  phase: string;
  modules: Record<string, string>;
}

declare global {
  interface Window {
    electronAPI?: {
      healthCheck: () => Promise<any>;
      listRules: () => Promise<any>;
      searchKnowledge: (query: string) => Promise<any>;
    };
  }
}

function App() {
  const [appState, setAppState] = useState<AppState | null>(null);
  const [rules, setRules] = useState<any[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadAppState();
    loadRules();
  }, []);

  const loadAppState = async () => {
    try {
      const state = await window.electronAPI?.healthCheck();
      setAppState(state);
    } catch (err) {
      console.error('Failed to load app state:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadRules = async () => {
    try {
      const data = await window.electronAPI?.listRules();
      setRules(data || []);
    } catch (err) {
      console.error('Failed to load rules:', err);
    }
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      const results = await window.electronAPI?.searchKnowledge(searchQuery);
      setSearchResults(results?.results || []);
    } catch (err) {
      console.error('Search failed:', err);
    }
  };

  if (loading) {
    return (
      <div className="app">
        <div className="loading">AI-CAD 正在启动...</div>
      </div>
    );
  }

  return (
    <div className="app">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1>AI-CAD</h1>
          <span className="version">v0.1.0</span>
        </div>
        <div className="header-right">
          <span className={`status-badge ${appState?.status === 'ok' ? 'status-ok' : 'status-err'}`}>
            {appState?.status === 'ok' ? '● 运行中' : '● 已停止'}
          </span>
          <span className="phase-tag">{appState?.phase || 'Phase 0'}</span>
        </div>
      </header>

      {/* Main Content */}
      <main className="main">
        {/* Left Panel - CAD View */}
        <section className="panel cad-panel">
          <h2>CAD 视图</h2>
          <div className="cad-view-placeholder">
            <p>图纸预览区域</p>
            <p className="hint">支持 DWG/DXF 格式</p>
          </div>
        </section>

        {/* Center Panel - Agent Flow */}
        <section className="panel agent-panel">
          <h2>Agent 执行流程</h2>
          <div className="agent-flow">
            {['意图理解', '方案结构化', '任务分解', 'CAD执行', '规则校验', '成果输出'].map((step, i) => (
              <div key={step} className={`flow-step ${i === 0 ? 'active' : ''}`}>
                <div className="step-dot" />
                <div className="step-label">{step}</div>
                {i < 5 && <div className="step-arrow" />}
              </div>
            ))}
          </div>
          <div className="agent-status">
            <p>当前状态: <strong>等待输入</strong></p>
          </div>
        </section>

        {/* Right Panel - Rules & Knowledge */}
        <section className="panel rules-panel">
          <h2>规范规则</h2>
          <div className="rules-list">
            {rules.map(rule => (
              <div key={rule.id} className="rule-item">
                <span className="rule-name">{rule.name}</span>
                <span className="rule-code">{rule.code}</span>
              </div>
            ))}
          </div>

          <h2>知识检索</h2>
          <div className="search-box">
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="输入规范问题..."
              onKeyPress={(e) => e.key === 'Enter' && handleSearch()}
            />
            <button onClick={handleSearch}>检索</button>
          </div>
          {searchResults.length > 0 && (
            <div className="search-results">
              {searchResults.map((result: any, i: number) => (
                <div key={i} className="result-item">
                  <p>{result.content}</p>
                </div>
              ))}
            </div>
          )}
        </section>
      </main>

      {/* Footer */}
      <footer className="footer">
        <span>AI辅助施工图深化系统</span>
        <span>规则引擎保准确 · LLM保灵活 · 人在回路保可控</span>
      </footer>
    </div>
  );
}

export default App;

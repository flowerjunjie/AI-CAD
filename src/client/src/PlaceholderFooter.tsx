import React from 'react';
import { PLACEHOLDERS, type Placeholder } from './placeholders';
import { useEngineStore } from './useEngineStore';
import { useRuleEditorStore } from './useRuleEditorStore';
import { loadDslRules } from './engineApi';

/**
 * Footer 发展占位卡片区 — 从 App.tsx 抽出的独立子组件。
 *
 * 占位卡置灰, 某专业规则 confirmed=true 即点亮该专业;
 * 可推动卡带「去回填」一键跳右栏 DSL 编辑器定位对应规则 (P11 导航)。
 *
 * 父组件通过 onGoBackfill(prefixes, ownerId) 把「切到 DSL 编辑器」的
 * 本地 UI state (rulesPane) 注入, 本组件不直接管理 App 的 rulesPane。
 */

interface PlaceholderFooterProps {
  /** P11 导航: 父组件切到右栏 DSL 编辑器 (rulesPane='editor'), 本组件只负责定位规则 */
  onGoBackfill: (prefixes: string[] | undefined, ownerId: string) => void;
}

/** P11 占位卡 → 回填入口导航: 定位到该规则前缀首条规则 + 确保 DSL 规则已加载 */
function goToBackfill(
  prefixes: string[] | undefined,
  ownerId: string,
  onGoBackfill: PlaceholderFooterProps['onGoBackfill'],
) {
  const s = useRuleEditorStore.getState();
  const prefixesToMatch =
    prefixes && prefixes.length > 0 ? prefixes : [ownerId.replace(/-values$/, '') + '-'];

  const locate = (rules: { rule_id: string }[]) => {
    const target = rules.find((r) => prefixesToMatch.some((p) => r.rule_id.startsWith(p)));
    useRuleEditorStore.getState().selectRule(target ? target.rule_id : null);
  };

  if (!s.loaded || s.rules.length === 0) {
    loadDslRules().then((rs) => {
      if (!rs || rs.length === 0) return;
      locate(rs);
    });
  } else {
    locate(s.rules);
  }

  // 由父组件切 tab (App 的 rulesPane 是本地 state, 子组件不直接操作)
  onGoBackfill(prefixes, ownerId);
}

function PlaceholderCard({ p, onGoBackfill }: { p: Placeholder; onGoBackfill: PlaceholderFooterProps['onGoBackfill'] }) {
  const rules = useEngineStore((st) => st.rules);
  const clashResults = useEngineStore((st) => st.clashResults);

  // 专家填值即点亮: 该占位声明的专业前缀里, 有 confirmed 规则 → 该专业变实
  const litPrefixes = p.disciplinePrefixes?.filter((pref) =>
    rules.some((r) => r.confirmed && r.rule_id.startsWith(pref)),
  ) || [];

  // 全亮判定: 无前缀声明 → 恒不亮 (功能占位, 无回填通道);
  // 有前缀 → 全部前缀 confirmed 才算 "已点亮" (M1 四专业 / M4 clash 容差)
  const allLit = p.disciplinePrefixes?.length
    ? litPrefixes.length === p.disciplinePrefixes.length
    : false;

  // M4 容差 + M1 卡联动: m4-collision 卡点亮时, 透出当前容差取值来源。
  // 首选 /api/rules 的 clash-tolerance-range.tolerance_source (规则列表自带,
  // 不依赖跑过碰撞检测); 兜底最近一次 M4 检测的 tolerance_source。
  // 不虚标: 两个来源都没有 (规则未 confirmed + 没跑过检测) 则不显示。
  let m4TolSource: string | undefined;
  let m4TolVal: number | undefined;
  if (p.id === 'm4-collision') {
    const clashRule = rules.find((r) => r.rule_id === 'clash-tolerance-range');
    if (clashRule?.tolerance_source) {
      m4TolSource = clashRule.tolerance_source;
      m4TolVal = clashRule.tolerance_m ?? undefined;
    } else {
      const lastClash = [...clashResults].reverse().find((r) => r.tolerance_source);
      m4TolSource = lastClash?.tolerance_source;
      m4TolVal = lastClash?.tolerance_m;
    }
  }

  return (
    <div
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
      {/* P9 行动指引: 告诉设计师「这张卡我下一步能干嘛」(可推动去哪 / 纯占位等谁) */}
      {p.actionHint && (
        <p className={`ph-action ${p.disciplinePrefixes ? 'ph-action-doable' : 'ph-action-external'}`}>
          <span className="ph-action-tag">{p.disciplinePrefixes ? '可推动' : '待外部'}</span>
          {p.actionHint}
        </p>
      )}
      {/* P11 回填入口导航: 可推动占位卡 → 一键跳右栏 DSL 编辑器并定位到对应规则 */}
      {p.disciplinePrefixes && (
        <button
          className="ph-go-backfill"
          onClick={() => goToBackfill(p.disciplinePrefixes, p.id, onGoBackfill)}
        >
          去回填 →
        </button>
      )}
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
      {/* M4 容差来源透出 (卡联动): 点亮态才显示, 没跑过检测不虚标 */}
      {allLit && m4TolSource && (
        <div className="ph-tol-source">
          容差 {m4TolVal ?? '?'} m · 来源 <b>{m4TolSource}</b>
        </div>
      )}
      <div className="ph-domain">{p.domain}</div>
    </div>
  );
}

export default function PlaceholderFooter({ onGoBackfill }: PlaceholderFooterProps) {
  return (
    <footer className="footer footer-cards">
      <div className="footer-title">发展占位 · 各专业专家补齐</div>
      <div className="placeholder-row">
        {PLACEHOLDERS.map((p) => (
          <PlaceholderCard key={p.id} p={p} onGoBackfill={onGoBackfill} />
        ))}
      </div>
    </footer>
  );
}

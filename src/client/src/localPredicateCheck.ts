import type { DslRuleItem } from './useEngineStore';

/**
 * 本地 predicate 预检 — 设计器改完阈值/键名，不等后端就先把最常见问题拦下来。
 * 判据对齐 dsl.py 白名单 (element + params 键 + True/False/None + len) 与
 * keyword.kwlist。比 validate_dsl_json 粗 (不做 func: 前缀/函数调用/语法检查)，
 * 只抓「predicate 引用了不存在的 params 键」这类一眼能看出来的错 — 后端
 * /api/rules/validate 仍是权威校验 (谓词全白名单 + schema + 语法)。
 * 返回: 每条规则一个消息数组 (空 = 本地看 OK)。
 */

// Python 保留字 (keyword.kwlist) — predicate 里出现这些不作标识符处理。
const KEYWORDS = new Set([
  'and', 'or', 'not', 'in', 'is', 'if', 'else', 'elif', 'lambda', 'def',
  'class', 'return', 'yield', 'global', 'nonlocal', 'assert', 'pass',
  'break', 'continue', 'del', 'try', 'except', 'finally', 'raise',
  'with', 'as', 'for', 'while', 'assert', 'async', 'await',
]);

// 白名单非 params 标识符 (dsl.py _allowed_names 的 base 去掉 keyword/element)。
const BASE_ALLOWED = new Set(['element', 'True', 'False', 'None', 'len']);

// 抓谓词里的标识符 (含 element.xxx 属性链里的名字), 排除字符串/数字字面量干扰。
// 简化: 先剥掉 '...' / "..." 字符串字面量再抓 \b 标识符。
function extractIdentifiers(predicate: string): string[] {
  const stripped = predicate
    .replace(/'(?:[^'\\]|\\.)*'/g, "''")
    .replace(/"(?:[^"\\]|\\.)*"/g, '""');
  const found = new Set<string>();
  for (const m of stripped.matchAll(/[A-Za-z_][A-Za-z0-9_]*/g)) {
    found.add(m[0]);
  }
  return [...found];
}

/**
 * 单条规则本地预检: predicate 里出现的标识符是否都在白名单内。
 * params 键 = 该规则 params + param_defaults 的键并集 (dsl.py 编译时同样取并集)。
 */
export function localCheckPredicate(rule: DslRuleItem): string[] {
  const issues: string[] = [];
  const paramKeys = new Set([
    ...Object.keys(rule.params || {}),
    ...Object.keys(rule.param_defaults || {}),
  ]);
  const allowed = new Set([...BASE_ALLOWED, ...paramKeys]);
  for (const ident of extractIdentifiers(rule.predicate)) {
    if (KEYWORDS.has(ident) || allowed.has(ident)) continue;
    issues.push(`「${ident}」不在 params 键 (${[...paramKeys].join(', ') || '无'}) 内 — 求值时会 AttributeError`);
  }
  return issues;
}

/** 整份规则本地预检: rule_id → 问题消息数组 (只列有问题的规则)。 */
export function localCheckAllRules(rules: DslRuleItem[]): Map<string, string[]> {
  const result = new Map<string, string[]>();
  for (const r of rules) {
    const issues = localCheckPredicate(r);
    if (issues.length > 0) result.set(r.rule_id, issues);
  }
  return result;
}

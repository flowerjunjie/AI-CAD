// 未实现能力 · 占位配置（数据写死，不造假数字/假图元）
export interface Placeholder {
  id: string;
  title: string;
  desc: string;
  domain: string;
  owner: string;
  /** 该占位对应哪些专业规则前缀；任一前缀的 DSL 规则 confirmed=true 即点亮该专业 */
  disciplinePrefixes?: string[];
}

export const PLACEHOLDERS: Placeholder[] = [
  {
    id: 'm1-values',
    title: '规范数值回填',
    desc: '各专业阈值待专家确认后填 default.json，改 JSON 零代码',
    domain: '给排水/电气/暖通/结构',
    owner: '各业专家',
    disciplinePrefixes: ['plumbing-', 'electrical-', 'hvac-', 'structural-'],
  },
  {
    id: 'm2-layer',
    title: 'DWG 图层约定',
    desc: '各院点位图层/块名映射待对齐制图规范 (GUI「扫图层」按钮 + scripts/dwg_layer_scan.py 可出频率报告辅助决策)',
    domain: '出图规范',
    owner: '制图规范',
  },
  {
    id: 'm3-render',
    title: '出图深化',
    desc: '各专业 元素→图元 画法（线型/填充/图层着色）',
    domain: '各专业制图',
    owner: '各专业制图规范',
  },
  {
    id: 'm4-collision',
    title: '多专业碰撞检测',
    desc: '管线穿梁 / 插座撞梁 自动检测 (容差带已接 default.json 回填通道, 专家改 JSON 即调参)',
    domain: '多专业协同',
    owner: '团队工程',
    disciplinePrefixes: ['clash-'],
  },
  {
    id: 'm5-collab',
    title: '在线协同持久层',
    desc: '锁/事件持久化 + 事件溯源 + 跨进程快照 (机制骨架已落地, 本地锁演示通路已接桥+GUI; 真·多机在线协同待业务定协议)',
    domain: '协同持久',
    owner: '团队',
    disciplinePrefixes: ['collab-'],
  },
  {
    id: 'm5-team',
    title: '团队协作',
    desc: '多设计师 + 改动冲突检测 + 权限',
    domain: '协同',
    owner: '团队',
  },
];

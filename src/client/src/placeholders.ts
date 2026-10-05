// 未实现能力 · 占位配置（数据写死，不造假数字/假图元）
export interface Placeholder {
  id: string;
  title: string;
  desc: string;
  domain: string;
  owner: string;
  /** 该占位对应哪些专业规则前缀；任一前缀的 DSL 规则 confirmed=true 即点亮该专业 */
  disciplinePrefixes?: string[];
  /**
   * P9 行动指引: 设计师「下一步能做什么」的一句话 (纯前端数据, 不造业务值)。
   * 区分「我能推动·去哪操作」(可点亮通道) vs「纯占位·等外部谁」, 消除
   * 「看到占位卡却不知道该干嘛」的认知断点。
   */
  actionHint?: string;
}

export const PLACEHOLDERS: Placeholder[] = [
  {
    id: 'm1-values',
    title: '规范数值回填',
    desc: '各专业阈值待专家确认后填 default.json，改 JSON 零代码',
    domain: '给排水/电气/暖通/结构',
    owner: '各业专家',
    disciplinePrefixes: ['plumbing-', 'electrical-', 'hvac-', 'structural-'],
    actionHint: '可推动 → 右栏「规则 · DSL 编辑器」定位到 plumbing-/electrical-/hvac-/structural- 规则, 点「回填并确认」写 default.json 即点亮',
  },
  {
    id: 'm2-layer',
    title: 'DWG 图层约定',
    desc: '各院点位图层/块名映射待对齐制图规范 (GUI「扫图层」按钮 + scripts/dwg_layer_scan.py 可出频率报告辅助决策)',
    owner: '制图规范',
    domain: '出图规范',
    actionHint: '需外部制图规范 → 先点中栏「扫图层」出图层/块名频率报告, 专家据此定稿映射 dict (机制已就位, 值待人定)',
  },
  {
    id: 'm3-render',
    title: '出图深化',
    desc: '各专业 元素→图元 画法（线型/填充/图层着色）',
    domain: '各专业制图',
    owner: '各专业制图规范',
    actionHint: '需外部各专业制图规范 → 配色/线宽/填充已有默认 (M3 已落地), 各院定稿画法后改 _LAYER_STYLES 即生效',
  },
  {
    id: 'm4-collision',
    title: '多专业碰撞检测',
    desc: '管线穿梁 / 插座撞梁 自动检测 (容差带已接 default.json 回填通道, 专家改 JSON 即调参)',
    domain: '多专业协同',
    owner: '团队工程',
    disciplinePrefixes: ['clash-'],
    actionHint: '可推动 → 右栏 DSL 编辑器定位 clash-tolerance-range 规则, 改 params.clash_tolerance_m 即调容差零代码',
  },
  {
    id: 'm5-team',
    title: '团队协作 · 在线协同',
    desc: '多设计师协同: 改动冲突检测 + 权限矩阵 + 在线协同持久层 (锁/事件持久化/事件溯源/快照 + 死锁/完整性校验; 本地锁演示已接桥+GUI, 真·多机协同待业务定协议)',
    domain: '协同/团队',
    owner: '团队',
    disciplinePrefixes: ['collab-', 'clash-'],
    actionHint: '机制层已通 (中栏「协同持久层」可取锁/放锁/查死锁/看矩阵) → 真·多机在线协同需业务定协议后接入, 本卡等协议',
  },
];

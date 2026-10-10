// 浏览器级验证 B/A/C 三条交互的渲染态: 起 exe 面板 → 真操作触发 → 截图。
// 用法: 先启动面板 (如 start_gui.py / exe), 确认 127.0.0.1:8642 可访问,
//       再跑 `node scripts/ux_shots.js`。产物落 output/ux_*.png (output/ 已 gitignore)。
// 复用系统 Chrome (免下 Chromium), 依赖仓库根 node_modules 里的 playwright。
const { chromium } = require('playwright');

const PANEL = 'http://127.0.0.1:8642/';
const OUT = __dirname + '/output';
const fs = require('fs');
fs.mkdirSync(OUT, { recursive: true });

(async () => {
  const exe = 'C:/Program Files/Google/Chrome/Application/chrome.exe';
  const browser = await chromium.launch({
    executablePath: exe,
    args: ['--remote-debugging-port=9222'],
  });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  await page.goto(PANEL, { waitUntil: 'networkidle', timeout: 30000 });
  // 等引擎徽章变绿 (面板 fetch /api/health 通)
  await page.waitForTimeout(3000);

  // ── C·预览批次标注: 先点「自动出图」出一批, 看预览图下批次标签 ──
  const runBtn = page.getByRole('button', { name: '自动出图' });
  await runBtn.click();
  await page.waitForTimeout(4000); // 等 pipeline + 预览
  const batchTxt = (await page.locator('.cad-batch').innerText().catch(() => ''));
  await page.screenshot({ path: OUT + '/ux_C_batch.png', fullPage: false });
  console.log('C·预览批次标签 =', JSON.stringify(batchTxt));

  // ── B·违规→规则出口: 找「改这条规则」按钮, 点它看跳没跳 DSL 编辑器 ──
  const fixBtns = page.locator('.vio-fix-rule-btn');
  const fixCount = await fixBtns.count();
  let beforeTab = await page.locator('.tab-active').first().innerText().catch(() => '(none)');
  if (fixCount > 0) {
    await fixBtns.first().click();
    await page.waitForTimeout(1500);
    const afterTab = await page.locator('.tab-active').first().innerText().catch(() => '(none)');
    console.log(`B·「改这条规则」按钮数=${fixCount}, 点前 tab=[${beforeTab}] 点后备选 tab=[${afterTab}]`);
    await page.screenshot({ path: OUT + '/ux_B_rule_jump.png', fullPage: false });
  } else {
    console.log('B·未渲染「改这条规则」按钮 (当前 0 违规?) — 违规计数:', await page.locator('.violation').count());
    // 0 违规时 B 按钮本就不该出现 (条件渲染正确), 这是符合预期的空态
  }

  // ── A·RAG 0 命中: 在检索框输个必然 0 命中词 + 检索, 看「0 命中」空态 ──
  const ragInput = page.locator('input[placeholder*="规范"]').first();
  await ragInput.fill('zzz不存在的虚构术语qqq');
  const ragBtn = page.getByRole('button', { name: '检索' });
  await ragBtn.click();
  await page.waitForTimeout(2500);
  const nohit = await page.locator('.rag-no-hit').count();
  const nohitTxt = nohit > 0 ? await page.locator('.rag-no-hit').first().innerText() : '(无 .rag-no-hit 节点)';
  await page.screenshot({ path: OUT + '/ux_A_rag_no_hit.png', fullPage: false });
  console.log('A·RAG 0命中空态节点数=' + nohit + ' 内容=' + JSON.stringify(nohitTxt.slice(0, 60)));

  await browser.close();
  console.log('UX_SHOTS_DONE');
})().catch((e) => {
  console.error('UX shot error:', e.message);
  process.exit(1);
});

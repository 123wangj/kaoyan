import { chromium } from 'playwright';
import fs from 'node:fs/promises';
import path from 'node:path';

const baseURL = 'http://127.0.0.1:8000';
const outputDir = path.resolve('xhs_materials');
await fs.mkdir(outputDir, { recursive: true });

const browser = await chromium.launch({ channel: 'msedge', headless: true });
const context = await browser.newContext({
  viewport: { width: 900, height: 1200 },
  deviceScaleFactor: 1.5,
  locale: 'zh-CN',
  colorScheme: 'light',
  serviceWorkers: 'block',
});
const page = await context.newPage();
await page.route('**/chat/history**', route => route.fulfill({
  status: 200,
  contentType: 'application/json',
  body: JSON.stringify({ messages: [] }),
}));

async function capture(name) {
  await page.screenshot({ path: path.join(outputDir, name), fullPage: false });
}

try {
  await page.goto(`${baseURL}/home`, { waitUntil: 'networkidle' });
  await capture('02-product-home.png');

  const login = await context.request.post(`${baseURL}/api/auth/login`, {
    data: { user_id: 'alice', password: 'abc12345' },
  });
  if (!login.ok()) throw new Error(`登录失败：${login.status()}`);

  await page.goto(`${baseURL}/app`, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.locator('.app-container').waitFor({ state: 'visible', timeout: 15000 });
  await page.waitForTimeout(1800);
  await page.locator('.sidebar-footer').evaluate(el => { el.style.visibility = 'hidden'; });

  await page.evaluate(() => window.switchView('chat'));
  await page.waitForTimeout(600);
  await capture('03-ai-chat.png');

  await page.evaluate(() => window.switchView('question-bank'));
  await page.waitForTimeout(1800);
  await page.locator('#dashUserName').evaluate(el => { el.textContent = '内测体验者'; });
  await capture('04-question-bank.png');

  await page.evaluate(() => window.switchView('exam'));
  await page.waitForTimeout(1200);
  await capture('05-smart-exam.png');

  await page.evaluate(() => window.switchView('study-plan'));
  await page.waitForTimeout(1800);
  await capture('06-study-plan.png');

  await page.evaluate(() => window.switchView('knowledge-graph'));
  await page.waitForTimeout(2500);
  await capture('07-knowledge-graph.png');
} finally {
  await browser.close();
}

console.log(outputDir);

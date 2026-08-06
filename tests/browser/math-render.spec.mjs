import { test, expect } from '@playwright/test';

test('renders standard and repaired LaTeX delimiters without stray symbols', async ({ page }) => {
  await page.setContent(`
    <!doctype html>
    <html><head>
      <script src="http://127.0.0.1:8010/static/app-runtime.js"></script>
    </head><body>
      <div id="question"></div>
      <div id="explanation"></div>
      <div id="chat"></div>
    </body></html>
  `);

  await page.evaluate(async () => {
    await window.KaoyanRuntime.renderMathText(
      document.querySelector('#question'),
      '若 ＄T(n)=2T(n/2)+n＄，求复杂度；除法 n/2 不得被误判。'
    );
    document.querySelector('#explanation').innerHTML = window.KaoyanRuntime.renderMarkdown(
      '行内公式：\\(V-E=1\\)。独立公式：\\[T(n)=O(n\\log n)\\]'
    );
    await window.KaoyanRuntime.renderMath(document.querySelector('#explanation'));
    document.querySelector('#chat').innerHTML = window.KaoyanRuntime.renderMarkdown(
      '修复错误闭合符：$a^2+b^2=c^2$/；修复错误开启符：/$x_1+x_2$。'
    );
    await window.KaoyanRuntime.renderMath(document.querySelector('#chat'));
  });

  await expect(page.locator('#question .katex')).toHaveCount(1);
  await expect(page.locator('#explanation .katex')).toHaveCount(2);
  await expect(page.locator('#explanation .katex-display')).toHaveCount(1);
  await expect(page.locator('#chat .katex')).toHaveCount(2);
  await expect(page.locator('body')).not.toContainText('＄');
  await expect(page.locator('body')).not.toContainText('$/');
  await expect(page.locator('body')).not.toContainText('/$');
});

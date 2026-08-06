import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('kaoyan_token', 'browser-test-token');
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = typeof input === 'string' ? input : input.url;
      if (url.includes('/api/auth/verify')) {
        return Promise.resolve(new Response(JSON.stringify({ valid: true, user_id: 'browser-test' }), {
          status: 200, headers: { 'Content-Type': 'application/json' }
        }));
      }
      return nativeFetch(input, init);
    };
  });
  await page.route('**/static/app.js*', route => route.fulfill({ path: 'static/app.js', contentType: 'application/javascript' }));
  await page.route('**/static/app-runtime.js*', route => route.fulfill({ path: 'static/app-runtime.js', contentType: 'application/javascript' }));
  await page.route('**/api/auth/verify**', route => route.fulfill({ json: { valid: true, user_id: 'browser-test' } }));
  await page.route('**/api/auth/me', route => route.fulfill({ json: { authenticated: true, user_id: 'browser-test' } }));
  await page.route('**/chat/history**', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/user/**', route => route.fulfill({ json: {} }));
  await page.route('**/question-bank/paged**', route => route.fulfill({ json: {
    items: [], total: 0, page: 1, page_size: 36, total_pages: 1,
    filter_options: { years: [], subject_counts: {}, catalog_total: 0 }
  } }));
  const login = await page.request.post('/api/auth/login', {
    data: { user_id: 'alice', password: 'abc12345' }
  });
  expect(login.ok()).toBeTruthy();
  await page.goto('/static/index.html');
  await page.evaluate(() => {
    const host = document.createElement('div');
    host.id = 'step-player-test-host';
    document.querySelector('main')?.prepend(host);
    window.__stepPlayerTest = createStepPlayer(
      host,
      [
        { value: 'A', desc: '初始状态' },
        { value: 'B', desc: '执行比较' },
        { value: 'C', desc: '得到结果' }
      ],
      snapshot => `<div data-frame>${snapshot.value}</div>`,
      { label: '测试过程' }
    );
  });
});

test('supports single-step, progress seeking and play/pause', async ({ page }) => {
  const player = page.locator('#step-player-test-host .step-player');
  await expect(player).toBeVisible();
  await expect(player.locator('[data-step-number]')).toHaveText('步骤 1 / 3');
  await player.locator('[data-step-action="next"]').click();
  await expect(player.locator('[data-frame]')).toHaveText('B');
  await expect(player.locator('[data-step-desc]')).toHaveText('执行比较');
  await player.locator('[data-step-progress]').fill('2');
  await expect(player.locator('[data-frame]')).toHaveText('C');
  await player.locator('[data-step-speed]').selectOption('550');
  await player.locator('[data-step-action="play"]').click();
  await expect(player.locator('[data-step-action="play"]')).toHaveAttribute('aria-pressed', 'true');
  await player.locator('[data-step-action="play"]').click();
  await expect(player.locator('[data-step-action="play"]')).toHaveAttribute('aria-pressed', 'false');
});

test('keeps controls inside a narrow viewport', async ({ page }) => {
  const dimensions = await page.locator('#step-player-test-host .step-player').evaluate(element => ({
    clientWidth: element.clientWidth,
    scrollWidth: element.scrollWidth
  }));
  expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth + 1);
});

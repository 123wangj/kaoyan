import { test, expect } from '@playwright/test';

const questions = Array.from({ length: 36 }, (_, index) => ({
  id: `q-${index + 1}`,
  subject: '数据结构',
  type: 'choice',
  year: '2025',
  content: `用于响应式回归测试的题目 ${index + 1}：下面哪个说法正确？`,
  options: ['A. 选项一', 'B. 选项二', 'C. 选项三', 'D. 选项四'],
  answer: 'B',
  explanation: index === 0 ? '****数据结构\\*\\***' : '测试解析'
}));

test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => {
    localStorage.setItem('kaoyan_token', 'browser-test-token');
    const nativeFetch = window.fetch.bind(window);
    window.fetch = (input, init) => {
      const url = typeof input === 'string' ? input : input.url;
      if (url.includes('/api/auth/verify')) {
        return Promise.resolve(new Response(JSON.stringify({
          valid: true,
          user_id: 'browser-test'
        }), { status: 200, headers: { 'Content-Type': 'application/json' } }));
      }
      return nativeFetch(input, init);
    };
  });
  await page.route('https://cdn.jsdelivr.net/**', route => route.fulfill({
    contentType: 'application/javascript',
    body: ''
  }));
  await page.route('**/static/app.js*', route => route.fulfill({
    path: 'static/app.js',
    contentType: 'application/javascript'
  }));
  await page.route('**/static/app-runtime.js*', route => route.fulfill({
    path: 'static/app-runtime.js',
    contentType: 'application/javascript'
  }));
  await page.route('**/static/styles.css*', route => route.fulfill({
    path: 'static/styles.css',
    contentType: 'text/css'
  }));
  await page.route('**/static/views/school-selection.js*', route => route.fulfill({
    path: 'static/views/school-selection.js',
    contentType: 'application/javascript'
  }));
  await page.route('**/mastery**', route => route.fulfill({ json: {} }));
  await page.route('**/wrong-book**', route => route.fulfill({ json: [] }));
  await page.route('**/study-plan/**', route => route.fulfill({ json: {} }));
  await page.route('**/memory-review/**', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/kg/**', route => route.fulfill({ json: [] }));
  await page.route('**/api/auth/verify**', route => route.fulfill({
    json: { valid: true, user_id: 'browser-test' }
  }));
  await page.route('**/api/auth/me', route => route.fulfill({
    json: { authenticated: true, user_id: 'browser-test' }
  }));
  await page.route(/\/question-bank\/[^/]+\/note$/, route => {
    if (route.request().method() === 'GET') {
      return route.fulfill({ json: { text: '', drawing: { version: 1, strokes: [] } } });
    }
    return route.fulfill({
      json: { success: true, note: { updated_at: new Date().toISOString() } }
    });
  });
  await page.route('**/question-bank/paged**', route => {
    const pageNumber = Number(new URL(route.request().url()).searchParams.get('page') || 1);
    return route.fulfill({
      json: {
        items: questions.map(question => ({
          ...question,
          id: `${question.id}-page-${pageNumber}`,
          content: `${question.content}（第 ${pageNumber} 页）`
        })),
        total: 72,
        page: pageNumber,
        page_size: 36,
        total_pages: 2,
        filter_options: {
          years: ['2025'],
          subject_counts: { '数据结构': 72 },
          catalog_total: 72
        }
      }
    });
  });
  await page.route('**/user/stats/overview**', route => route.fulfill({
    // 模拟新用户或旧接口未返回统计字段，页面仍应稳定显示 0，不能出现 NaN/undefined。
    json: { by_subject_backend: {} }
  }));
  await page.route('**/user/**', route => route.fulfill({ json: {} }));
  await page.route('**/chat/history**', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/daily-push**', route => route.fulfill({
    json: { answer: '今日复习', memory_review: [], pushed_ids: [] }
  }));
  await page.route('**/daily-tasks/today**', route => route.fulfill({ json: { tasks: [] } }));
  // Layout tests load the app shell directly; API auth is mocked above.
  await page.route('http://127.0.0.1:8010/app', route => route.fulfill({
    path: 'static/index.html',
    contentType: 'text/html'
  }));
  await page.goto('/app');
  await page.evaluate(() => window.switchView('question-bank-detail'));
  await expect(page.locator('#questionGrid .question-card')).toHaveCount(36);
});

test('question cards keep a stable non-overlapping grid', async ({ page }) => {
  const cards = page.locator('#questionGrid .question-card');
  const first = await cards.nth(0).boundingBox();
  const second = await cards.nth(1).boundingBox();
  expect(first).not.toBeNull();
  expect(second).not.toBeNull();
  expect(first.width).toBeGreaterThan(260);
  expect(first.height).toBeGreaterThan(150);
  expect(Math.abs(first.y - second.y) < 3 || second.y >= first.y + first.height).toBeTruthy();
  await expect(page.locator('#questionPagination')).toBeVisible();
  await expect(page.locator('#questionPageInfo')).toContainText('1 / 2');
});

test('next page button loads the following question page', async ({ page }) => {
  const nextPage = page.locator('#questionNextPage');
  await expect(nextPage).toBeEnabled();
  await nextPage.click();
  await expect(page.locator('#questionPageInfo')).toContainText('2 / 2');
  await expect(page.locator('#questionGrid .question-card').first()).toContainText('第 2 页');
  await expect(nextPage).toBeDisabled();
  await expect(page.locator('#questionPrevPage')).toBeEnabled();
});

test('navigation adapts without covering question content', async ({ page }, testInfo) => {
  const sidebar = page.locator('.sidebar');
  const main = page.locator('.main-content');
  const sideBox = await sidebar.boundingBox();
  const mainBox = await main.boundingBox();
  expect(sideBox).not.toBeNull();
  expect(mainBox).not.toBeNull();
  if (testInfo.project.name === 'mobile') {
    expect(sideBox.y).toBeGreaterThan(700);
    expect(mainBox.width).toBeGreaterThan(380);
  } else {
    expect(sideBox.x).toBe(0);
    expect(mainBox.x).toBeGreaterThanOrEqual(80);
  }
});

test('school selection runs as a staged agent and exposes learning-loop actions', async ({ page }) => {
  const completed = {
    run_id: 'run-browser-test',
    status: 'completed',
    progress: 100,
    message: '综合分析已完成',
    stages: {
      profile: { status: 'completed', message: '个人学习画像已读取' },
      research: { status: 'completed', message: '已核验公开来源' },
      synthesis: { status: 'completed', message: '已生成行动建议' },
    },
    result: {
      school: '浙江大学',
      major: '计算机科学与技术',
      generated_at: '2026-07-31T18:00:00',
      trend: { predicted_range: [350, 365], direction: '上升' },
      heat: { score: 65, level: '中等关注' },
      institution_consensus: { available: false, sample_size: 0 },
      risk: { score: 52, level: '中风险', confidence: .76, reasons: ['竞争较强'] },
      learning_readiness: {
        available: true,
        score: 68,
        level: '进阶提升',
        attempted: 45,
        progress: 12,
        accuracy: 67,
        weak_subjects: ['计算机网络'],
        signals: { recent_trend_delta: 6, speed_score: 72 },
        subjects: {},
      },
      summary: '建议先提升计算机网络并保持刷题节奏。',
      evidence: [],
      methodology: '公开信息与个人画像综合。',
      disclaimer: '仅供参考。',
    },
  };
  await page.evaluate(() => window.switchView('school-selection'));
  await expect(page.locator('#schoolSelectionForm')).toBeVisible();
  await page.evaluate(run => window.renderSchoolAgentRun(run), {
    ...completed,
    status: 'running',
    progress: 65,
    result: null,
  });
  await expect(page.locator('.school-agent-progress')).toBeVisible();
  await expect(page.locator('.school-agent-stage')).toHaveCount(3);
  await page.evaluate(result => window.renderSchoolSelectionResult(result), completed.result);
  const rendered = await page.evaluate(() => ({
    hero: document.querySelector('.school-result-hero')?.textContent || '',
    actions: Array.from(document.querySelectorAll('.school-action-grid button'))
      .map(button => button.textContent),
  }));
  expect(rendered.hero).toContain('浙江大学');
  expect(rendered.actions).toHaveLength(3);
  expect(rendered.actions.join(' ')).toContain('生成 14 天提升计划');
  expect(rendered.actions.join(' ')).toContain('练习最薄弱科目');
  expect(rendered.actions.join(' ')).toContain('模拟提升后的结果');
});

test('question modal actions remain visible', async ({ page }) => {
  await page.locator('#questionGrid .question-card').nth(0).click();
  await expect(page.locator('#questionModal')).toBeVisible();
  await expect(page.locator('#favoriteBtn')).toBeVisible();
  await expect(page.locator('#openNoteBtn')).toBeVisible();
  await expect(page.locator('#closeModal')).toBeVisible();
  await expect(page.locator('#nextQuestionBtn')).toBeVisible();
});

test('question explanation cleans malformed escaped bold markers', async ({ page }) => {
  await page.locator('#questionGrid .question-card').first().click();
  await page.locator('#showAnswerBtn').click();
  await page.locator('.answer-tab[data-tab="explanation"]').click();
  const explanation = page.locator('#answerContent .question-explanation');
  await expect(explanation).toContainText('数据结构');
  await expect(explanation.locator('strong')).toHaveText('数据结构');
  await expect(explanation).not.toContainText('*');
  await expect(explanation).not.toContainText('\\');
});

test('tablet handwriting canvas accepts a pen stroke', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'tablet');
  await page.locator('#questionGrid .question-card').nth(0).click();
  await page.locator('#openNoteBtn').click();
  await page.locator('[data-note-mode="draw"]').click();
  const canvas = page.locator('#questionNoteCanvas');
  await expect(canvas).toBeVisible();
  const box = await canvas.boundingBox();
  expect(box).not.toBeNull();
  await canvas.dispatchEvent('pointerdown', {
    pointerId: 7, pointerType: 'pen', isPrimary: true, buttons: 1,
    clientX: box.x + 40, clientY: box.y + 50, pressure: 0.45
  });
  for (let step = 1; step <= 12; step += 1) {
    await canvas.dispatchEvent('pointermove', {
      pointerId: 7, pointerType: 'pen', isPrimary: true, buttons: 1,
      clientX: box.x + 40 + (140 * step / 12),
      clientY: box.y + 50 + (80 * step / 12),
      pressure: 0.55
    });
  }
  await canvas.dispatchEvent('pointerup', {
    pointerId: 7, pointerType: 'pen', isPrimary: true, buttons: 0,
    clientX: box.x + 180, clientY: box.y + 130, pressure: 0
  });
  await expect(canvas).toHaveAttribute('data-stroke-count', '1');
});

test('tablet portrait and landscape stay within the viewport', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'tablet');
  for (const viewport of [
    { width: 768, height: 1024, name: 'portrait' },
    { width: 1024, height: 768, name: 'landscape' },
  ]) {
    await page.setViewportSize(viewport);
    await expect(page.locator('#questionGrid .question-card')).toHaveCount(36);
    const shellMetrics = await page.evaluate(() => ({
      viewportWidth: window.innerWidth,
      documentWidth: document.documentElement.scrollWidth,
      mainWidth: document.querySelector('.main-content')?.getBoundingClientRect().width || 0,
      gridWidth: document.querySelector('#questionGrid')?.getBoundingClientRect().width || 0,
    }));
    expect(shellMetrics.documentWidth).toBeLessThanOrEqual(shellMetrics.viewportWidth + 1);
    expect(shellMetrics.mainWidth).toBeGreaterThan(620);
    expect(shellMetrics.gridWidth).toBeLessThanOrEqual(shellMetrics.mainWidth + 1);
    const cardRects = await page.locator('#questionGrid .question-card').evaluateAll(cards =>
      cards.slice(0, 2).map(card => {
        const rect = card.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      })
    );
    expect(cardRects).toHaveLength(2);
    if (viewport.name === 'portrait') {
      expect(cardRects[1].y).toBeGreaterThanOrEqual(cardRects[0].y + cardRects[0].height - 1);
      expect(Math.abs(cardRects[0].width - cardRects[1].width)).toBeLessThan(1);
    } else {
      expect(Math.abs(cardRects[0].y - cardRects[1].y)).toBeLessThan(3);
    }
    await page.screenshot({
      path: `tmp/tablet-${viewport.name}-questions.png`,
      fullPage: false,
    });
  }

  await page.setViewportSize({ width: 768, height: 1024 });
  const cards = page.locator('#questionGrid .question-card');
  expect(await cards.count()).toBeGreaterThan(0);
  await cards.nth(0).click();
  await expect(page.locator('#questionModal')).toBeVisible();
  await page.waitForTimeout(400);
  const modalMetrics = await page.evaluate(() => {
    const modal = document.querySelector('.modal-content')?.getBoundingClientRect();
    const footer = document.querySelector('.modal-footer')?.getBoundingClientRect();
    return {
      modalLeft: modal?.left || 0,
      modalRight: modal?.right || 0,
      modalHeight: modal?.height || 0,
      footerBottom: footer?.bottom || 0,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
  });
  expect(modalMetrics.modalLeft).toBeGreaterThanOrEqual(0);
  expect(modalMetrics.modalRight).toBeLessThanOrEqual(modalMetrics.viewportWidth + 1);
  expect(modalMetrics.modalHeight).toBeLessThanOrEqual(modalMetrics.viewportHeight);
  expect(modalMetrics.footerBottom).toBeLessThanOrEqual(modalMetrics.viewportHeight + 1);
  await page.screenshot({ path: 'tmp/tablet-portrait-modal.png', fullPage: false });

  await page.locator('#showAnswerBtn').click();
  await expect(page.locator('#qaSplitLayout')).toBeVisible();
  const portraitAnswerMetrics = await page.evaluate(() => ({
    splitDirection: getComputedStyle(document.querySelector('#qaSplitLayout')).flexDirection,
    sendHeight: document.querySelector('#qaChatSend')?.getBoundingClientRect().height || 0,
    inputFontSize: parseFloat(getComputedStyle(document.querySelector('#qaChatInput')).fontSize),
  }));
  expect(portraitAnswerMetrics.splitDirection).toBe('column');
  expect(portraitAnswerMetrics.sendHeight).toBeGreaterThanOrEqual(44);
  expect(portraitAnswerMetrics.inputFontSize).toBeGreaterThanOrEqual(16);
  await page.screenshot({ path: 'tmp/tablet-portrait-answer-chat.png', fullPage: false });

  await page.setViewportSize({ width: 1024, height: 768 });
  const landscapeAnswerMetrics = await page.evaluate(() => ({
    splitDirection: getComputedStyle(document.querySelector('#qaSplitLayout')).flexDirection,
    rightWidth: document.querySelector('.qa-right-panel')?.getBoundingClientRect().width || 0,
    modalRight: document.querySelector('.modal-content')?.getBoundingClientRect().right || 0,
    viewportWidth: window.innerWidth,
  }));
  expect(landscapeAnswerMetrics.splitDirection).toBe('row');
  expect(landscapeAnswerMetrics.rightWidth).toBeLessThanOrEqual(390);
  expect(landscapeAnswerMetrics.modalRight).toBeLessThanOrEqual(landscapeAnswerMetrics.viewportWidth + 1);
  await page.screenshot({ path: 'tmp/tablet-landscape-answer-chat.png', fullPage: false });
});

test('tablet question-bank dashboard uses balanced card rows', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'tablet');
  await page.evaluate(() => window.switchView('question-bank'));
  await expect(page.locator('#dashDoneCount')).toHaveText('0');
  await expect(page.locator('#dashDonePercent')).toHaveText('0');
  await expect(page.locator('#dashPassPercent')).toContainText('0%');
  const dashboardText = await page.locator('#question-bank-view').innerText();
  expect(dashboardText).not.toMatch(/NaN|undefined/);

  for (const viewport of [
    { width: 768, height: 1024, name: 'portrait' },
    { width: 1024, height: 768, name: 'landscape' },
  ]) {
    await page.setViewportSize(viewport);
    const statRects = await page.locator('.dash-stats-cards .dash-stat-card').evaluateAll(cards =>
      cards.map(card => {
        const rect = card.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      })
    );
    expect(statRects).toHaveLength(3);
    expect(Math.max(...statRects.map(rect => rect.y)) - Math.min(...statRects.map(rect => rect.y))).toBeLessThan(3);
    expect(Math.max(...statRects.map(rect => rect.height)) - Math.min(...statRects.map(rect => rect.height))).toBeLessThan(3);

    const supportRects = await page.locator('.dash-second-row .dash-card').evaluateAll(cards =>
      cards.map(card => {
        const rect = card.getBoundingClientRect();
        return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
      })
    );
    expect(supportRects).toHaveLength(3);
    if (viewport.name === 'portrait') {
      expect(Math.abs(supportRects[1].y - supportRects[2].y)).toBeLessThan(3);
      expect(supportRects[0].width).toBeGreaterThan(supportRects[1].width * 1.8);
    } else {
      expect(supportRects[1].x).toBeGreaterThan(supportRects[0].x + supportRects[0].width - 1);
      expect(supportRects[2].x).toBeGreaterThan(supportRects[0].x + supportRects[0].width - 1);
      expect(supportRects[2].y).toBeGreaterThan(supportRects[1].y);
    }
    await page.screenshot({
      path: `tmp/tablet-${viewport.name}-question-dashboard.png`,
      fullPage: false,
    });
  }
});

test('tablet landscape prioritizes questions and keeps work panels usable', async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== 'tablet');
  await page.setViewportSize({ width: 1024, height: 768 });

  const listMetrics = await page.evaluate(() => {
    const header = document.querySelector('#question-bank-detail-view .qb-header')?.getBoundingClientRect();
    const tabs = document.querySelector('#question-bank-detail-view .subject-tabs')?.getBoundingClientRect();
    const grid = document.querySelector('#questionGrid')?.getBoundingClientRect();
    const cards = Array.from(document.querySelectorAll('#questionGrid .question-card')).slice(0, 3)
      .map(card => card.getBoundingClientRect());
    return {
      headerHeight: header?.height || 0,
      tabsHeight: tabs?.height || 0,
      gridHeight: grid?.height || 0,
      firstRowYSpread: Math.max(...cards.map(card => card.y)) - Math.min(...cards.map(card => card.y)),
    };
  });
  expect(listMetrics.headerHeight).toBeLessThanOrEqual(70);
  expect(listMetrics.tabsHeight).toBeLessThanOrEqual(60);
  expect(listMetrics.gridHeight).toBeGreaterThan(560);
  expect(listMetrics.firstRowYSpread).toBeLessThan(3);

  await page.locator('#questionGrid .question-card').nth(0).click();
  await page.locator('#openNoteBtn').click();
  const noteMetrics = await page.evaluate(() => {
    const panel = document.querySelector('#questionNotePanel')?.getBoundingClientRect();
    const editor = document.querySelector('#questionNoteText')?.getBoundingClientRect();
    return {
      panelWidth: panel?.width || 0,
      panelBottom: panel?.bottom || 0,
      editorHeight: editor?.height || 0,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
  });
  expect(noteMetrics.panelWidth).toBeLessThan(noteMetrics.viewportWidth * .55);
  expect(noteMetrics.panelBottom).toBeLessThanOrEqual(noteMetrics.viewportHeight);
  expect(noteMetrics.editorHeight).toBeGreaterThan(360);
  await page.locator('#closeNoteBtn').click();
  await page.locator('#closeModal').click();

  await page.evaluate(() => window.switchView('study-plan'));
  await page.waitForTimeout(100);
  await page.evaluate(() => {
    window.renderStudyPlanView({
      ai_summary: '测试计划',
      created_at: '2026-08-07',
      week_count: 1,
      weekly: [{ week: 1, theme: '基础', tasks: [] }],
      answers: {},
    });
  });
  await page.locator('#openPlanAiBtn').click();
  const aiMetrics = await page.evaluate(() => {
    const panel = document.querySelector('#planAiEditor')?.getBoundingClientRect();
    const capabilities = document.querySelector('.plan-ai-capabilities')?.getBoundingClientRect();
    const messages = document.querySelector('.plan-ai-messages')?.getBoundingClientRect();
    const input = document.querySelector('#planAiInput')?.getBoundingClientRect();
    return {
      panelRight: panel?.right || 0,
      panelBottom: panel?.bottom || 0,
      capabilitiesRight: capabilities?.right || 0,
      messagesLeft: messages?.left || 0,
      inputBottom: input?.bottom || 0,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
    };
  });
  expect(aiMetrics.panelRight).toBeLessThanOrEqual(aiMetrics.viewportWidth);
  expect(aiMetrics.panelBottom).toBeLessThanOrEqual(aiMetrics.viewportHeight);
  expect(aiMetrics.capabilitiesRight).toBeLessThan(aiMetrics.messagesLeft);
  expect(aiMetrics.inputBottom).toBeLessThan(aiMetrics.panelBottom);
});

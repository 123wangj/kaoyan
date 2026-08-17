import { test, expect } from '@playwright/test';

const subjects = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
const questions = Array.from({ length: 40 }, (_, index) => ({
  id: `exam-q-${index + 1}`,
  type: 'choice',
  content: `模拟试卷第 ${index + 1} 题的题干`,
  options: ['A. 选项甲', 'B. 选项乙', 'C. 选项丙', 'D. 选项丁'],
  subject: subjects[index % 4],
  difficulty: '基础',
  knowledge_points: [`知识点 ${index % 6 + 1}`]
}));

const baseExam = {
  id: 'browser-exam', title: '408 统考结构模拟卷 · 2026-08-02', status: 'in_progress',
  created_at: '2026-08-02T12:00:00+08:00', questions, answers: {}
};

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
  await page.route('**/exams', route => {
    if (route.request().method() === 'POST') return route.fulfill({ json: baseExam });
    return route.fulfill({ json: { items: [] } });
  });
  await page.route('**/exams/browser-exam/submit', route => route.fulfill({ json: {
    ...baseExam, status: 'submitted', submitted_at: '2026-08-02T12:30:00+08:00',
    duration_seconds: 1800, score: 98, correct_count: 49,
    answers: Object.fromEntries(questions.map((q, i) => [q.id, i === 0 ? 'B' : 'A'])),
    questions: questions.map(q => ({ ...q, answer: 'A', explanation: '这是本题的标准解析。' })),
    report: {
      summary: '本次最需要优先补强的是数据结构。', history_used: true,
      subject_performance: subjects.map(subject => ({ subject, total: 12, correct: 12, accuracy: 100 })),
      weak_points: [{ name: '知识点 1', subject: '数据结构', exam_wrong: 1, exam_total: 2, combined_error_rate: 50 }],
      wrong_details: [{ question_id: 'exam-q-1', selected_answer: 'B', correct_answer: 'A', possible_reason: '可能混淆了相近概念或忽略题干限定。' }]
    }
  }}));
  const login = await page.request.post('/api/auth/login', {
    data: { user_id: 'alice', password: 'abc12345' }
  });
  expect(login.ok()).toBeTruthy();
  await page.goto('/app');
});

test('creates, answers and submits a balanced exam report', async ({ page }) => {
  await page.evaluate(() => window.switchView('exam'));
  await expect(page.locator('#exam-view')).toHaveClass(/active/);
  await expect(page.locator('.exam-hero-card')).toBeVisible();
  await page.locator('.exam-primary').click();
  await expect(page.locator('.exam-sheet-nav button')).toHaveCount(40);
  await page.locator('.exam-options button').first().click();
  await expect(page.locator('.exam-taking-head small')).toContainText('1 / 40');
  page.once('dialog', dialog => dialog.accept());
  await page.locator('.exam-submit').click();
  await expect(page.locator('.exam-score-ring strong')).toHaveText('98');
  await expect(page.locator('.exam-subject-grid > div')).toHaveCount(4);
  await expect(page.locator('.exam-weak-item')).toHaveCount(1);
  await expect(page.locator('.exam-review-item')).toHaveCount(40);
  await expect(page.locator('.exam-reason')).toBeVisible();

  const sidebarBox = await page.locator('.sidebar').boundingBox();
  const reportBox = await page.locator('.exam-score-card').boundingBox();
  expect(sidebarBox).not.toBeNull();
  expect(reportBox).not.toBeNull();
  expect(reportBox.x).toBeGreaterThanOrEqual(sidebarBox.x + sidebarBox.width);
  expect(reportBox.x + reportBox.width).toBeLessThanOrEqual(1440);
});

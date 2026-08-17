import { test, expect } from '@playwright/test';

const practiceQuestions = [1, 2].map(index => ({
  id: `practice-${index}`,
  type: 'choice',
  content: `练习题 ${index}`,
  options: ['A. 甲', 'B. 乙', 'C. 丙', 'D. 丁'],
  answer: 'A',
  explanation: '解析',
  subject: '数据结构',
  year: '2025',
  knowledge_points: ['线性表']
}));
practiceQuestions[1].type = 'multiple_choice';
practiceQuestions[1].answer = 'AC';
practiceQuestions[1].subject = '操作系统';
practiceQuestions[1].knowledge_points = ['进程调度'];
const assessmentSubjects = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
const assessmentQuestions = Array.from({ length: 40 }, (_, index) => ({
  id: `assessment-${index + 1}`,
  type: 'choice',
  content: `画像诊断题 ${index + 1}`,
  options: ['A. 甲', 'B. 乙', 'C. 丙', 'D. 丁'],
  subject: assessmentSubjects[Math.floor(index / 10)],
  chapter: `第 ${index % 8 + 1} 章`,
  difficulty: ['基础', '中等', '困难'][index % 3],
  knowledge_points: [`知识点 ${index + 1}`],
}));

test.beforeEach(async ({ page }) => {
  let dailyGoal = 5;
  await page.addInitScript(() => {
    localStorage.setItem('kaoyan_token', 'browser-test-token');
    if (!sessionStorage.getItem('profile-reminder-test-initialized')) {
      localStorage.setItem('kaoyan_profile_assessment_reminder:browser-test-token', String(Date.now()));
      sessionStorage.setItem('profile-reminder-test-initialized', '1');
    }
  });
  await page.route('**/static/app.js*', route => route.fulfill({ path: 'static/app.js', contentType: 'application/javascript' }));
  await page.route('**/static/app-runtime.js*', route => route.fulfill({ path: 'static/app-runtime.js', contentType: 'application/javascript' }));
  await page.route('**/api/auth/verify**', route => route.fulfill({ json: { valid: true, user_id: 'browser-test' } }));
  await page.route('**/api/auth/me', route => route.fulfill({ json: { authenticated: true, user_id: 'browser-test' } }));
  await page.route('**/api/auth/account', route => route.fulfill({ json: {
    user_id: 'browser-test', nickname: '测试用户', invite_code: 'KYTEST1234',
    phone: '', phone_masked: '', phone_verified: false, wechat_id: '',
    customer_service: { phone: '17635575899', wechat: '17635575899' }
  } }));
  await page.route('**/api/auth/logout', route => route.fulfill({ json: { success: true } }));
  await page.route('**/chat/history**', route => route.fulfill({ json: { messages: [] } }));
  await page.route('**/user/**', route => route.fulfill({ json: {} }));
  await page.route('**/user/profile', route => route.fulfill({ json: {
    answer_stats: { total_questions: 0, correct_count: 0, accuracy: 0, wrong_count: 0 },
    weak_points: [], mastery: [], subject_mastery: {}, wrong_book: [],
    daily_tasks: { tasks: [] }, token_usage: { total_tokens: 0, total_requests: 0 }
  } }));
  await page.route('**/user/profile-assessment/status**', route => route.fulfill({ json: {
    available: true, question_count: 40, has_completed: false, in_progress: false
  } }));
  await page.route('**/user/profile-assessment/start**', route => route.fulfill({ json: {
    id: 'assessment-run-1', status: 'in_progress', question_count: 40, questions: assessmentQuestions
  } }));
  await page.route('**/user/profile-assessment/submit**', async route => {
    const payload = await route.request().postDataJSON();
    await route.fulfill({ json: { success: true, assessment: { result: {
      question_count: 40, correct_count: 40, accuracy: 100,
      subjects: Object.fromEntries(assessmentSubjects.map(subject => [subject, { correct: 10, total: 10, accuracy: 100 }]))
    } }, received_answers: payload.answers } });
  });
  await page.route('**/wrong-book**', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/mastery**', route => route.fulfill({ json: { items: [] } }));
  await page.route('**/study-plan/current**', route => route.fulfill({ json: { plan: null } }));
  await page.route('**/daily-tasks/today**', route => route.fulfill({ json: { tasks: [] } }));
  await page.route('**/daily-review/yesterday**', route => route.fulfill({ json: {
    date: '2026-08-08',
    items: [{ question_id: 'practice-2', was_wrong: true, question: practiceQuestions[1] }]
  } }));
  await page.route('**/user/preferences/daily-goal**', async route => {
    if (route.request().method() === 'PUT') {
      dailyGoal = (await route.request().postDataJSON()).daily_question_goal;
    }
    await route.fulfill({ json: { daily_question_goal: dailyGoal } });
  });
  await page.route('**/question-bank/paged**', route => {
    const url = new URL(route.request().url());
    const subject = url.searchParams.get('subject') || 'all';
    const point = url.searchParams.get('knowledge_point') || 'all';
    let items = practiceQuestions.filter(item => subject === 'all' || item.subject === subject);
    const pointSource = items;
    items = items.filter(item => point === 'all' || item.knowledge_points.includes(point));
    const knowledgePoints = [...new Set(pointSource.flatMap(item => item.knowledge_points))]
      .map(title => ({ title, count: pointSource.filter(item => item.knowledge_points.includes(title)).length }));
    return route.fulfill({ json: {
      items, total: items.length, page: 1, page_size: 36, total_pages: 1,
      filter_options: { years: ['2025'], subject_counts: { 数据结构: 1, 操作系统: 1 }, knowledge_points: knowledgePoints, catalog_total: 2 }
    } });
  });
  await page.route('**/question-bank/submit-answer**', async route => {
    const payload = await route.request().postDataJSON();
    const selected = [...new Set(String(payload.selected_option || '').match(/[A-D]/g) || [])].sort().join('');
    const question = practiceQuestions.find(item => item.id === payload.question_id);
    const correct = question?.answer || '';
    await route.fulfill({ json: {
      success: true, is_correct: selected === correct,
      selected_option: selected, correct_answer: correct, explanation: question?.explanation || ''
    } });
  });
  const login = await page.request.post('/api/auth/login', { data: { user_id: 'alice', password: 'abc12345' } });
  expect(login.ok()).toBeTruthy();
  await page.goto('/app');
});

test('saves a custom daily goal and opens yesterday wrong question', async ({ page }) => {
  await page.evaluate(() => window.switchView('question-bank'));
  await expect(page.locator('#dailyGoalInput')).toHaveValue('5');
  await page.locator('#dailyGoalInput').fill('12');
  await page.locator('#saveDailyGoalBtn').click();
  await expect(page.locator('#noticeList')).toContainText('0/12 题');
  await expect(page.locator('#rollingReviewPanel')).toContainText('复盘错题去重做');
  await page.locator('[data-review-question="practice-2"]').click();
  await expect(page.locator('#modalQuestion')).toContainText('练习题 2');
});

test('practice modal supports previous and next navigation', async ({ page }) => {
  await page.evaluate(() => window.switchToQuestionBankDetail());
  await page.locator('[data-question-id="practice-1"]').click();
  await expect(page.locator('#prevQuestionBtn')).toBeDisabled();
  await page.locator('#nextQuestionBtn').click();
  await expect(page.locator('#modalQuestion')).toContainText('练习题 2');
  await expect(page.locator('#prevQuestionBtn')).toBeEnabled();
  await page.locator('#prevQuestionBtn').click();
  await expect(page.locator('#modalQuestion')).toContainText('练习题 1');
});

test('multiple-choice question keeps multiple selections and grades the full set', async ({ page }) => {
  await page.evaluate(() => window.switchToQuestionBankDetail());
  await page.locator('[data-question-id="practice-2"]').click();
  await expect(page.locator('#modalType')).toHaveText('多选题');
  await page.locator('#modalOptions [data-option="A"]').click();
  await page.locator('#modalOptions [data-option="C"]').click();
  await expect(page.locator('#modalOptions .selected')).toHaveCount(2);
  await page.locator('#submitAnswerBtn').click();
  await expect(page.locator('#answerFeedback')).toContainText('回答正确');
});

test('catalog filters all subjects, a subject, and its knowledge points', async ({ page }) => {
  await page.evaluate(() => window.switchToQuestionBankDetail());
  const colors = await page.locator('#subjectFilter').evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, color: style.color };
  });
  expect(colors.background).toBe('rgb(248, 251, 253)');
  expect(colors.color).toBe('rgb(51, 65, 85)');
  await expect(page.locator('.question-card')).toHaveCount(2);
  await page.locator('#subjectFilter').selectOption('操作系统');
  await expect(page.locator('.question-card')).toHaveCount(1);
  await expect(page.locator('[data-question-id="practice-2"]')).toBeVisible();
  await expect(page.locator('#knowledgePointFilter option')).toContainText(['全部知识点', '进程调度（1）']);
  await page.locator('#knowledgePointFilter').selectOption('进程调度');
  await expect(page.locator('.question-card')).toHaveCount(1);
  await page.locator('#subjectFilter').selectOption('all');
  await expect(page.locator('.question-card')).toHaveCount(2);
});

test('study-plan task restores graded answers without requiring check-in', async ({ page }) => {
  await page.evaluate(question => {
    const host = document.createElement('div');
    host.innerHTML = `
      <div class="dt-row" data-task-id="plan-task-1" data-task-scope="plan">
        <button data-action="complete" disabled>完成打卡</button>
        <div class="dt-workspace"></div>
      </div>`;
    document.body.appendChild(host);
    window.renderTaskWorkspace(host.querySelector('.dt-row'), {
      task: { id: 'plan-task-1' },
      knowledge_points: [],
      questions: [{
        ...question,
        attempt: {
          selected_option: 'AC',
          correct_answer: 'AC',
          is_correct: true,
          explanation: '已保存的解析',
        },
      }],
    });
  }, practiceQuestions[1]);

  const task = page.locator('[data-task-id="plan-task-1"]');
  await expect(task.locator('.dt-option.selected')).toHaveCount(2);
  await expect(task.locator('.dt-q-feedback')).toContainText('已保存的解析');
  await expect(task.locator('[data-action="submit-qs"]')).toHaveText('已批改并保存');
  await expect(task.locator('[data-action="complete"]')).toBeDisabled();
});

test('tablet note opens as a spacious workspace', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await page.evaluate(() => window.switchToQuestionBankDetail());
  await page.locator('[data-question-id="practice-1"]').click();
  await page.locator('#openNoteBtn').click();
  await page.waitForTimeout(300);

  const metrics = await page.locator('#questionNotePanel').evaluate(panel => {
    const panelRect = panel.getBoundingClientRect();
    const editorRect = document.querySelector('#questionNoteText').getBoundingClientRect();
    return {
      panelWidth: panelRect.width,
      panelHeight: panelRect.height,
      panelLeft: panelRect.left,
      editorWidth: editorRect.width,
      editorHeight: editorRect.height,
      viewportWidth: window.innerWidth,
      viewportHeight: window.innerHeight,
      portaledToBody: panel.parentElement === document.body,
      bodyLocked: document.body.classList.contains('note-panel-open'),
    };
  });

  expect(metrics.panelWidth).toBeGreaterThan(metrics.viewportWidth * .94);
  expect(metrics.panelHeight).toBeGreaterThan(metrics.viewportHeight * .9);
  expect(metrics.panelLeft).toBeLessThan(24);
  expect(metrics.editorWidth).toBeGreaterThan(metrics.viewportWidth * .88);
  expect(metrics.editorHeight).toBeGreaterThan(metrics.viewportHeight * .6);
  expect(metrics.portaledToBody).toBeTruthy();
  expect(metrics.bodyLocked).toBeTruthy();

  await page.locator('[data-note-mode="draw"]').click();
  const drawMetrics = await page.evaluate(() => {
    const toolbar = document.querySelector('.note-draw-toolbar');
    const canvas = document.querySelector('#questionNoteCanvas').getBoundingClientRect();
    return {
      canvasHeight: canvas.height,
      toolbarFits: toolbar.scrollWidth <= toolbar.clientWidth,
    };
  });
  expect(drawMetrics.canvasHeight).toBeGreaterThan(metrics.viewportHeight * .5);
  expect(drawMetrics.toolbarFits).toBeTruthy();

  await page.locator('#closeNoteBtn').click();
  expect(await page.locator('#questionNotePanel').evaluate(panel => panel.parentElement.classList.contains('modal-content'))).toBeTruthy();
  expect(await page.evaluate(() => document.body.classList.contains('note-panel-open'))).toBeFalsy();
});

test('quick profile assessment covers 40 questions and produces a profile', async ({ page }) => {
  await page.evaluate(() => window.switchView('profile'));
  await expect(page.locator('.profile-assessment-card')).toContainText('40 题快速建立学习画像');
  await page.locator('#startProfileAssessmentBtn').click();
  await expect(page.locator('.profile-assessment-sheet button')).toHaveCount(40);
  await expect(page.locator('.profile-assessment-question')).toContainText('画像诊断题 1');

  await page.locator('[data-assessment-option="A"]').click();
  await expect(page.locator('.profile-assessment-sheet button.answered')).toHaveCount(1);
  await page.evaluate(() => {
    for (let index = 0; index < 40; index += 1) {
      document.querySelector('[data-assessment-option="A"]')?.click();
      if (index < 39) document.querySelector('[data-assessment-next]')?.click();
    }
  });
  await page.locator('[data-assessment-submit]').click();
  await expect(page.locator('.profile-assessment-result')).toContainText('100.0%');
  await expect(page.locator('.profile-assessment-result article')).toHaveCount(4);
});

test('incomplete profile assessment reminder returns once every three days', async ({ page }) => {
  const reminderKey = 'kaoyan_profile_assessment_reminder:browser-test-token';
  await page.waitForLoadState('networkidle');
  await page.evaluate(key => localStorage.removeItem(key), reminderKey);
  await page.reload();

  const reminder = page.locator('#profileAssessmentReminder');
  await expect(reminder).toBeVisible();
  await expect(reminder).toContainText('40 题');
  await page.locator('[data-profile-reminder-dismiss]').last().click();
  await expect(reminder).toHaveCount(0);

  await page.reload();
  await expect(page.locator('#profileAssessmentReminder')).toHaveCount(0);

  await page.evaluate(key => {
    localStorage.setItem(key, String(Date.now() - 3 * 24 * 60 * 60 * 1000 - 1000));
  }, reminderKey);
  await page.reload();
  await expect(page.locator('#profileAssessmentReminder')).toBeVisible();
});

test('account center exposes invitation, support and logout', async ({ page }) => {
  await page.evaluate(() => window.switchView('profile'));
  await expect(page.locator('.account-security-card')).toContainText('KYTEST1234');
  await expect(page.locator('.account-security-card')).toContainText('17635575899');
  await page.locator('#openAccountSettingsBtn').click();
  await expect(page.locator('#accountSettingsModal')).toContainText('修改密码');
  await page.locator('[data-account-close]').last().click();
  await page.locator('#profileLogoutBtn').click();
  await expect(page).toHaveURL(/\/$/);
});

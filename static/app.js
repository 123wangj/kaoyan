// 全局状态
const state = {
  allQuestions: [],
  currentSubject: 'all',
  filters: {
    subject: 'all',
    knowledgePoint: 'all',
    type: 'all',
    year: 'all',
    status: 'all'
  },
  showFavoritesOnly: false,
  questionMastery: {},
  currentQuestion: null,
  activeAnswerTab: 'answer',
  visualizationCache: {},
  visualizationStep: 0,
  visualizationPlayer: null,
  selectedOption: null,
  answerSubmitted: false,
  qaConversation: [],
  chatStreaming: false,
  noteDrawing: { version: 1, strokes: [] },
  noteTool: 'pen',
  noteToolSizes: { pen: 4, eraser: 18 },
  noteDirty: false,
  dailyGoal: 5,
  rollingReviewItems: [],
  profileAssessment: { current: null, answers: {}, index: 0, startedAt: 0 },
  pagination: {
    page: 1,
    pageSize: 36,
    total: 0,
    totalPages: 1,
    loading: false
  },
  catalog: {
    total: 0,
    years: [],
    subjectCounts: {},
    knowledgePoints: []
  },
  userData: {
    favorites: {},
    answerRecords: {}
  }
};
const scheduleQuestionNoteAutosave = window.KaoyanRuntime.debounce(() => {
  if (state.noteDirty && state.currentQuestion) {
    saveCurrentQuestionNote({ silent: true, autosave: true });
  }
}, 1200);

// ========== localStorage 用户数据管理 ==========
function loadUserData() {
  try {
    const saved = localStorage.getItem('kaoyan_user_data');
    if (saved) {
      state.userData = JSON.parse(saved);
    }
  } catch (e) {
    console.warn('读取用户数据失败', e);
  }
}

// ========== 智能组卷（独立于题库作答记录） ==========
const examState = { current: null, answers: {}, index: 0, startedAt: 0 };

function examDraftKey(id) { return `kaoyan_exam_draft_${id}`; }

function saveExamDraft() {
  if (!examState.current || examState.current.status === 'submitted') return;
  try {
    localStorage.setItem(examDraftKey(examState.current.id), JSON.stringify({
      answers: examState.answers, index: examState.index, startedAt: examState.startedAt
    }));
  } catch (_) {}
}

function examDate(value) {
  if (!value) return '—';
  return new Date(value).toLocaleString('zh-CN', { hour12: false });
}

async function loadExamHome() {
  const root = document.getElementById('examContent');
  if (!root) return;
  root.innerHTML = '<div class="loading">正在读取试卷档案...</div>';
  try {
    const response = await fetch('/exams');
    if (!response.ok) throw new Error('读取失败');
    const data = await response.json();
    const items = data.items || [];
    root.innerHTML = `
      <section class="exam-hero-card">
        <div><span class="exam-kicker">408 · 真题结构</span><h2>生成一份 40 题模拟试卷</h2>
          <p>数据结构 11 题、计组 11 题、操作系统 10 题、计网 8 题，按真实卷面顺序出题。提交后自动评分并生成薄弱点报告。</p></div>
        <button class="exam-primary" type="button" onclick="createBalancedExam(this)">开始组卷</button>
      </section>
      <section class="exam-archive">
        <div class="exam-section-head"><div><span>ARCHIVE</span><h2>历史试卷</h2></div><strong>${items.length} 份</strong></div>
        <div class="exam-history-list">${items.length ? items.map(item => `
          <button class="exam-history-item" type="button" onclick="openExam('${escapeHtml(item.id)}')">
            <span class="exam-history-status ${item.status}">${item.status === 'submitted' ? '已交卷' : '进行中'}</span>
            <span class="exam-history-main"><b>${escapeHtml(item.title || '408 模拟试卷')}</b><small>${examDate(item.created_at)} · ${item.question_count} 题</small></span>
            <span class="exam-history-score">${item.status === 'submitted' ? `${item.score}<small>分</small>` : '继续作答'}</span>
          </button>`).join('') : '<div class="exam-empty">还没有试卷。生成第一份试卷，建立你的模拟考档案。</div>'}</div>
      </section>`;
  } catch (error) {
    root.innerHTML = '<div class="exam-empty">试卷档案加载失败，请稍后重试。</div>';
  }
}

async function createBalancedExam(button) {
  button.disabled = true;
  button.textContent = '正在均衡抽题...';
  try {
    const response = await fetch('/exams', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ question_count: 40 }) });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '组卷失败');
    renderExam(data);
  } catch (error) {
    alert(error.message || '组卷失败');
    button.disabled = false;
    button.textContent = '开始组卷';
  }
}

async function openExam(id) {
  const root = document.getElementById('examContent');
  root.innerHTML = '<div class="loading">正在打开试卷...</div>';
  try {
    const response = await fetch('/exams/' + encodeURIComponent(id));
    const exam = await response.json();
    if (!response.ok) throw new Error(exam.detail || '打开失败');
    renderExam(exam);
  } catch (error) {
    root.innerHTML = `<div class="exam-empty">${escapeHtml(error.message || '试卷打开失败')}</div>`;
  }
}

function renderExam(exam) {
  examState.current = exam;
  if (exam.status === 'submitted') {
    renderExamReport(exam);
    return;
  }
  let draft = {};
  try { draft = JSON.parse(localStorage.getItem(examDraftKey(exam.id)) || '{}'); } catch (_) {}
  examState.answers = draft.answers || {};
  examState.index = Math.min(Number(draft.index || 0), exam.questions.length - 1);
  examState.startedAt = Number(draft.startedAt || Date.now());
  renderExamQuestion();
}

function renderExamQuestion() {
  const exam = examState.current;
  const question = exam.questions[examState.index];
  const selected = examState.answers[question.id] || '';
  const answered = Object.keys(examState.answers).length;
  document.getElementById('examContent').innerHTML = `
    <div class="exam-taking-head">
      <button type="button" class="exam-back" onclick="saveExamDraft();loadExamHome()">← 保存进度并返回</button>
      <div><b>${escapeHtml(exam.title)}</b><small>已答 ${answered} / ${exam.questions.length}</small></div>
      <button type="button" class="exam-submit" onclick="submitCurrentExam()">交卷评分</button>
    </div>
    <div class="exam-taking-layout">
      <aside class="exam-sheet-nav"><strong>答题卡</strong><div>${exam.questions.map((q, i) => `<button type="button" class="${i === examState.index ? 'active' : ''} ${examState.answers[q.id] ? 'answered' : ''}" onclick="goExamQuestion(${i})">${i + 1}</button>`).join('')}</div></aside>
      <article class="exam-question-panel">
        <div class="exam-question-meta"><span>第 ${examState.index + 1} / ${exam.questions.length} 题</span><span>${escapeHtml(question.subject)}</span><span>${escapeHtml(question.difficulty || '常规')}</span></div>
        <h2>${escapeHtml(question.content)}</h2>
        <div class="exam-options">${(question.options || []).map(option => {
          const letter = String(option).trim().charAt(0).toUpperCase();
          return `<button type="button" class="${selected === letter ? 'selected' : ''}" onclick="selectExamAnswer('${letter}')"><b>${letter}</b><span>${escapeHtml(String(option).replace(/^\s*[A-D][.、:：)]?\s*/, ''))}</span></button>`;
        }).join('')}</div>
        <div class="exam-question-actions"><button type="button" ${examState.index === 0 ? 'disabled' : ''} onclick="goExamQuestion(${examState.index - 1})">上一题</button><button type="button" ${examState.index === exam.questions.length - 1 ? 'disabled' : ''} onclick="goExamQuestion(${examState.index + 1})">下一题</button></div>
      </article>
    </div>`;
  window.KaoyanRuntime.renderMath(document.getElementById('examContent'));
}

function selectExamAnswer(letter) {
  examState.answers[examState.current.questions[examState.index].id] = letter;
  saveExamDraft();
  renderExamQuestion();
}

function goExamQuestion(index) {
  examState.index = Math.max(0, Math.min(index, examState.current.questions.length - 1));
  saveExamDraft();
  renderExamQuestion();
}

async function submitCurrentExam() {
  const exam = examState.current;
  const unanswered = exam.questions.length - Object.keys(examState.answers).length;
  if (!confirm(unanswered ? `还有 ${unanswered} 题未作答，确定交卷吗？` : '确定交卷并查看评分报告吗？')) return;
  try {
    const response = await fetch(`/exams/${encodeURIComponent(exam.id)}/submit`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: examState.answers, duration_seconds: Math.round((Date.now() - examState.startedAt) / 1000) })
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '交卷失败');
    localStorage.removeItem(examDraftKey(exam.id));
    renderExam(result);
  } catch (error) { alert(error.message || '交卷失败'); }
}

function renderExamReport(exam) {
  const report = exam.report || {};
  const diagnosis = report.diagnosis_overview || {};
  const studyPlan = report.study_plan || {};
  const minutes = Math.max(1, Math.round(Number(exam.duration_seconds || 0) / 60));
  document.getElementById('examContent').innerHTML = `
    <div class="exam-report-top"><button type="button" class="exam-back" onclick="loadExamHome()">← 返回试卷档案</button><span>${examDate(exam.submitted_at)}</span></div>
    <section class="exam-score-card"><div class="exam-score-ring" style="--score:${Number(exam.score || 0)}"><strong>${exam.score}</strong><span>分</span></div><div><span class="exam-kicker">SCORE REPORT</span><h2>${escapeHtml(exam.title)}</h2><p>答对 ${exam.correct_count} / ${exam.questions.length} 题 · 用时约 ${minutes} 分钟</p><b>${escapeHtml(report.summary || '')}</b></div></section>
    <section class="exam-report-section"><div class="exam-section-head"><div><span>SUBJECTS</span><h2>四科表现</h2></div></div><div class="exam-subject-grid">${(report.subject_performance || []).map(item => `<div><span>${escapeHtml(item.subject)}</span><strong>${item.accuracy}%</strong><small>${item.correct} / ${item.total} 题</small><i><em style="width:${item.accuracy}%"></em></i></div>`).join('')}</div></section>
    <section class="exam-report-section exam-diagnosis-section">
      <div class="exam-section-head"><div><span>WEAK POINTS</span><h2>薄弱点深度诊断</h2></div><small>${report.history_used ? '已结合题库历史作答' : '当前仅依据本次试卷'}</small></div>
      <div class="exam-diagnosis-overview">
        <div><span>最弱科目</span><strong>${escapeHtml(diagnosis.weakest_subject || '—')}</strong><small>${Number(diagnosis.weakest_subject_accuracy || 0)}% 正确率</small></div>
        <div><span>持续性薄弱点</span><strong>${Number(diagnosis.persistent_weakness_count || 0)}</strong><small>本卷与历史均有失分</small></div>
        <div><span>未作答</span><strong>${Number(diagnosis.unanswered_count || 0)}</strong><small>用于判断时间分配问题</small></div>
      </div>
      <p class="exam-evidence-note">${escapeHtml(diagnosis.evidence_note || '')}</p>
      <div class="exam-weak-list">${(report.weak_points || []).map((item, index) => `
        <details class="exam-weak-item priority-${escapeHtml(item.priority || 'medium')}" ${index === 0 ? 'open' : ''}>
          <summary><span class="exam-priority">${escapeHtml(item.priority_label || '需要巩固')}</span><b>${escapeHtml(item.name)}</b><strong>${item.combined_error_rate}%</strong></summary>
          <div class="exam-weak-body">
            <div class="exam-weak-evidence"><b>诊断证据</b><span>${escapeHtml(item.evidence || `${item.subject} · 本卷错 ${item.exam_wrong}/${item.exam_total}`)}</span></div>
            <div class="exam-rate-grid"><span>本卷错误率 <b>${Number(item.exam_error_rate ?? 0)}%</b></span><span>历史错误率 <b>${item.history_error_rate == null ? '样本不足' : `${item.history_error_rate}%`}</b></span><span>关联错题 <b>${(item.wrong_question_ids || []).length} 道</b></span></div>
            <div><b>可能根因</b><ul>${(item.likely_causes || []).map(cause => `<li>${escapeHtml(cause)}</li>`).join('')}</ul></div>
            <div><b>针对性补强方案</b><ol>${(item.action_plan || []).map(action => `<li>${escapeHtml(action)}</li>`).join('')}</ol></div>
          </div>
        </details>`).join('') || '<div class="exam-empty">本次没有明显薄弱点。</div>'}</div>
      <div class="exam-study-plan"><b>建议执行顺序</b><ol>${(studyPlan.immediate || []).map(action => `<li>${escapeHtml(action)}</li>`).join('')}</ol><p><strong>本周安排：</strong>${escapeHtml(studyPlan.within_week || '')}</p><p><strong>复测标准：</strong>${escapeHtml(studyPlan.verification || '')}</p></div>
    </section>
    <section class="exam-report-section"><div class="exam-section-head"><div><span>REVIEW</span><h2>逐题答案与解析</h2></div></div><div class="exam-review-list">${exam.questions.map((q, index) => {
      const selected = exam.answers[q.id] || '';
      const correct = selected === q.answer;
      const wrong = (report.wrong_details || []).find(item => item.question_id === q.id);
      return `<details class="exam-review-item ${correct ? 'correct' : 'wrong'}" ${correct ? '' : 'open'}><summary><span>${index + 1}</span><b>${escapeHtml(q.subject)}</b><p>${escapeHtml(q.content)}</p><strong>${correct ? '正确' : selected ? `错选 ${selected}` : '未作答'}</strong></summary><div class="exam-review-body"><div class="exam-answer-line">你的答案：<b>${selected || '未作答'}</b>　正确答案：<b>${q.answer}</b></div>${wrong ? `<div class="exam-reason"><b>可能原因</b>${escapeHtml(wrong.possible_reason)}</div>` : ''}<div class="exam-explanation"><b>题目解析</b>${formatDetailed(q.explanation || '暂无解析')}</div></div></details>`;
    }).join('')}</div></section>`;
  window.KaoyanRuntime.renderMath(document.getElementById('examContent'));
}

function saveUserData() {
  try {
    localStorage.setItem('kaoyan_user_data', JSON.stringify(state.userData));
  } catch (e) {
    console.warn('保存用户数据失败', e);
  }
}

function isFavorited(questionId) {
  return !!state.userData.favorites[questionId];
}

// ========== 登录态守卫 ==========
const TOKEN_KEY = 'kaoyan_token';
function getToken() {
  try {
    return sessionStorage.getItem(TOKEN_KEY) || localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    return '';
  }
}
function setToken(t) {
  try {
    if (t) sessionStorage.setItem(TOKEN_KEY, t);
    else sessionStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(TOKEN_KEY);
  } catch {}
}
async function ensureLoggedIn() {
  const token = getToken();
  try {
    const headers = token ? { 'Authorization': 'Bearer ' + token } : {};
    const res = await fetch('/api/auth/verify', { headers, credentials: 'same-origin' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok || !data.valid) {
      setToken('');
      return redirectToLogin('登录已失效,请重新登录');
    }
    return true;
  } catch (e) {
    return redirectToLogin('无法连接服务器,请稍后再试');
  }
}
function redirectToLogin(msg) {
  try { sessionStorage.setItem('login_notice', msg || '请先登录'); } catch {}
  window.location.replace('/');
  return false;
}

// 全局 fetch 包装:自动加 Authorization 头;401 时踢回登录页
const _origFetch = window.fetch.bind(window);
const _getRequestInflight = new Map();
const _getRequestCache = new Map();
const _GET_CACHE_TTL_MS = 1800;
// 需鉴权的接口(本应用所有受保护端点)
const _PROTECTED_PREFIX = /^\/(api|chat|question-bank|wrong-book|user|mastery|memory-review|daily-tasks|daily-push|daily-review|study-plan|school-selection|exams|kg|rag)\b/;
const _PUBLIC_API = /\/api\/auth\/(login|register|verify)\b/;
window.fetch = async function (input, init) {
  init = init || {};
  const url = typeof input === 'string' ? input : (input && input.url) || '';
  const method = String(init.method || (typeof input !== 'string' && input.method) || 'GET').toUpperCase();
  const isProtected = _PROTECTED_PREFIX.test(url) && !_PUBLIC_API.test(url);
  if (isProtected) {
    const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined) || {});
    if (!headers.has('Authorization')) {
      const t = getToken();
      if (t) headers.set('Authorization', 'Bearer ' + t);
    }
    init.headers = headers;
    init.credentials = init.credentials || 'same-origin';
  }
  const cacheKey = method === 'GET' && isProtected ? url : '';
  if (cacheKey) {
    const cached = _getRequestCache.get(cacheKey);
    if (cached && Date.now() - cached.createdAt < _GET_CACHE_TTL_MS) {
      return cached.response.clone();
    }
    const inflight = _getRequestInflight.get(cacheKey);
    if (inflight) return (await inflight).clone();
  } else if (method !== 'GET') {
    _getRequestCache.clear();
  }
  const requestPromise = _origFetch(input, init);
  if (cacheKey) _getRequestInflight.set(cacheKey, requestPromise);
  let res;
  try {
    res = await requestPromise;
  } finally {
    if (cacheKey) _getRequestInflight.delete(cacheKey);
  }
  if (cacheKey && res.ok) {
    _getRequestCache.set(cacheKey, { createdAt: Date.now(), response: res.clone() });
  }
  if (isProtected && res.status === 401) {
    setToken('');
    redirectToLogin('登录已失效,请重新登录');
  }
  return res;
};

// 页面打开时立即校验
(async function () {
  // 展示登录回跳提示
  try {
    const notice = sessionStorage.getItem('login_notice');
    if (notice) {
      sessionStorage.removeItem('login_notice');
      setTimeout(() => alert(notice), 200);
    }
  } catch {}
  const ok = await ensureLoggedIn();
  if (!ok) return; // 已在跳转
})();

function getAnswerRecord(questionId) {
  return state.userData.answerRecords[questionId] || null;
}

function toggleFavorite(questionId) {
  if (state.userData.favorites[questionId]) {
    delete state.userData.favorites[questionId];
  } else {
    state.userData.favorites[questionId] = true;
  }
  saveUserData();
  // 更新当前打开题目的收藏按钮状态
  updateFavoriteBtnState(questionId);
  // 重新渲染列表
  renderQuestions();
}

function updateFavoriteBtnState(questionId) {
  const btn = document.getElementById('favoriteBtn');
  if (!btn) return;
  const label = btn.querySelector('.favorite-label');
  if (isFavorited(questionId)) {
    btn.classList.add('favorited');
    btn.title = '取消收藏';
    btn.setAttribute('aria-label', '取消收藏');
    if (label) label.textContent = '已收藏';
  } else {
    btn.classList.remove('favorited');
    btn.title = '收藏此题';
    btn.setAttribute('aria-label', '收藏此题');
    if (label) label.textContent = '收藏';
  }
}

function recordAnswer(questionId, selectedOption, correctAnswer) {
  const normalizedSelected = normalizeAnswerLetters(selectedOption);
  const normalizedCorrect = normalizeAnswerLetters(correctAnswer);
  const isCorrect = normalizedSelected === normalizedCorrect;
  state.userData.answerRecords[questionId] = {
    status: isCorrect ? 'correct' : 'wrong',
    selectedOption: normalizedSelected,
    correctAnswer: normalizedCorrect,
    timestamp: Date.now()
  };
  saveUserData();
}

// 工具函数
function extractYearFromContent(content) {
  const match = content.match(/【(\d{4})\s*统考真题】/);
  return match ? match[1] : null;
}

function getQuestionDisplayYear(question) {
  return question.year || extractYearFromContent(question.content) || '练习题';
}

function normalizeAnswerLetters(value) {
  const matches = String(value || '').toUpperCase().match(/[A-D]/g) || [];
  return [...new Set(matches)].sort().join('');
}

function isMultipleChoiceQuestion(question) {
  const type = String(question?.type || '').toLowerCase();
  return ['multiple_choice', 'multi_choice', 'multiple', '多选', '多选题'].includes(type)
    || question?.multiple === true
    || normalizeAnswerLetters(question?.answer || question?.correct_answer).length > 1;
}

function isChoiceQuestion(question) {
  return Array.isArray(question?.options) && question.options.length > 0;
}

function getQuestionTypeLabel(question) {
  if (isMultipleChoiceQuestion(question)) return '多选题';
  return isChoiceQuestion(question) ? '单选题' : '大题';
}

function formatProgressPercent(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '0%';
  const clamped = Math.max(0, Math.min(100, number));
  const digits = clamped > 0 && clamped < 10 ? 1 : 0;
  return `${clamped.toFixed(digits).replace(/\.0$/, '')}%`;
}

// 初始化
document.addEventListener('DOMContentLoaded', async () => {
  loadUserData();
  window.KaoyanRuntime.registerServiceWorker();
  window.KaoyanRuntime.flushMutations();
  await loadQuestions();
  initEventListeners();
  loadWelcomeName();
  loadChatHistory();
  loadChatStatusBar();
  // 异步刷 dashboard 周边
  renderDashboardNotice();
  renderDashboardTutors();
  maybeShowProfileAssessmentReminder();
});

const PROFILE_ASSESSMENT_REMINDER_INTERVAL_MS = 3 * 24 * 60 * 60 * 1000;

function profileAssessmentReminderKey() {
  const token = getToken();
  return `kaoyan_profile_assessment_reminder:${token ? token.slice(-24) : 'anonymous'}`;
}

function dismissProfileAssessmentReminder() {
  try {
    localStorage.setItem(profileAssessmentReminderKey(), String(Date.now()));
  } catch (_) {}
  document.getElementById('profileAssessmentReminder')?.remove();
  document.body.classList.remove('profile-assessment-reminder-open');
}

async function maybeShowProfileAssessmentReminder() {
  try {
    const response = await fetch('/user/profile-assessment/status', { cache: 'no-store' });
    if (!response.ok) return;
    const assessment = await response.json();
    const reminderKey = profileAssessmentReminderKey();
    if (assessment.has_completed || assessment.available === false) {
      try { localStorage.removeItem(reminderKey); } catch (_) {}
      return;
    }
    const lastShownAt = Number(localStorage.getItem(reminderKey) || 0);
    if (Date.now() - lastShownAt < PROFILE_ASSESSMENT_REMINDER_INTERVAL_MS) return;

    // Showing the prompt starts the cooldown as well, so refreshes never create repeated interruptions.
    try { localStorage.setItem(reminderKey, String(Date.now())); } catch (_) {}
    const modal = document.createElement('div');
    modal.id = 'profileAssessmentReminder';
    modal.className = 'profile-assessment-reminder';
    modal.innerHTML = `
      <div class="profile-assessment-reminder-backdrop" data-profile-reminder-dismiss></div>
      <section class="profile-assessment-reminder-dialog" role="dialog" aria-modal="true" aria-labelledby="profileAssessmentReminderTitle">
        <button type="button" class="profile-assessment-reminder-close" data-profile-reminder-dismiss aria-label="三天后提醒">×</button>
        <span class="profile-assessment-reminder-kicker">40 题 · 四科快速诊断</span>
        <h2 id="profileAssessmentReminderTitle">先让系统更准确地认识你</h2>
        <p>${assessment.in_progress
          ? '你的快速学习画像还没有完成，之前的进度已经保留。继续完成后，所有个性化分析都会更贴合你的真实水平。'
          : '完成一次快速学习画像后，每日补给、学习计划、薄弱点分析和其他个性化建议都会更准确。'}</p>
        <div class="profile-assessment-reminder-benefits"><span>四科均衡覆盖</span><span>约 25–35 分钟</span><span>作答自动保存</span></div>
        <div class="profile-assessment-reminder-actions">
          <button type="button" class="secondary" data-profile-reminder-dismiss>暂不，三天后提醒</button>
          <button type="button" class="primary" data-profile-reminder-start>${assessment.in_progress ? '继续完成画像' : '开始快速画像'}</button>
        </div>
      </section>`;
    document.body.appendChild(modal);
    document.body.classList.add('profile-assessment-reminder-open');
    modal.querySelectorAll('[data-profile-reminder-dismiss]').forEach(button => {
      button.addEventListener('click', dismissProfileAssessmentReminder);
    });
    modal.querySelector('[data-profile-reminder-start]')?.addEventListener('click', async () => {
      dismissProfileAssessmentReminder();
      switchView('profile');
      await loadProfile();
      document.getElementById('startProfileAssessmentBtn')?.click();
    });
  } catch (_) {}
}

document.addEventListener('keydown', event => {
  if (event.key === 'Escape' && document.getElementById('profileAssessmentReminder')) {
    dismissProfileAssessmentReminder();
  }
});

let _activityHeatmapPromise = null;
function loadActivityHeatmap() {
  if (!_activityHeatmapPromise) {
    _activityHeatmapPromise = fetch('/user/stats/heatmap?days=30')
      .then(response => response.ok ? response.json() : { daily: {} })
      .catch(() => ({ daily: {} }));
  }
  return _activityHeatmapPromise;
}

async function loadWelcomeName() {
  const el = document.getElementById('dashUserName');
  const tip = document.getElementById('dashUserTip');
  if (!el) return;
  try {
    const r = await fetch('/api/auth/me');
    if (r.ok) {
      const data = await r.json();
      if (data && (data.user_id || data.username)) {
        el.textContent = data.username || data.user_id;
        const sidebarName = document.getElementById('sidebarUserName');
        if (sidebarName) sidebarName.textContent = data.nickname || data.username || data.user_id;
      }
    }
  } catch (e) { /* 静默 */ }
  if (tip) {
    const h = new Date().getHours();
    let greet = '今天继续推进 408';
    if (h < 6) greet = '夜深了,早点休息,明天再战';
    else if (h < 12) greet = '早上好,新的一天从掌握一个知识点开始';
    else if (h < 18) greet = '下午继续刷题,保持手感';
    else greet = '晚上好,复盘今天的错题效果最好';
    tip.textContent = greet;
  }
}

async function loadChatHistory() {
  const wrap = document.getElementById('chatMessages');
  if (!wrap) return;
  try {
    const r = await fetch('/chat/history?limit=40');
    if (!r.ok) return;
    const data = await r.json();
    const msgs = (data && data.messages) || [];
    if (!msgs.length) return;
    // 有历史:隐藏欢迎卡片,清空原占位内容,按序渲染
    const wg = document.getElementById('welcomeGrid');
    if (wg) wg.style.display = 'none';
    wrap.innerHTML = '';
    msgs.forEach(m => addMessage(m.content || '', m.role === 'user' ? 'user' : 'assistant', m.id));
  } catch (e) {
    console.warn('加载对话历史失败', e);
  }
}

// 加载题目
async function loadQuestions(page = 1) {
  if (state.pagination.loading) return;
  state.pagination.loading = true;
  const grid = document.getElementById('questionGrid');
  if (grid) grid.setAttribute('aria-busy', 'true');
  try {
    const params = new URLSearchParams({
      page: String(Math.max(1, page)),
      page_size: String(state.pagination.pageSize),
      subject: state.filters.subject,
      knowledge_point: state.filters.knowledgePoint,
      year: state.filters.year,
      status: state.filters.status
    });
    if (state.showFavoritesOnly) {
      const favoriteIds = Object.keys(state.userData.favorites || {}).slice(0, 300);
      params.set('favorite_ids', favoriteIds.length ? favoriteIds.join(',') : '__none__');
    }
    const response = await fetch('/question-bank/paged?' + params.toString());
    if (!response.ok) throw new Error('题库加载失败');
    const data = await response.json();
    state.allQuestions = Array.isArray(data.items) ? data.items : [];
    state.pagination.page = Number(data.page || 1);
    state.pagination.total = Number(data.total || 0);
    state.pagination.totalPages = Math.max(1, Number(data.total_pages || 1));
    const options = data.filter_options || {};
    state.catalog.total = Number(options.catalog_total || state.pagination.total);
    state.catalog.years = Array.isArray(options.years) ? options.years : [];
    state.catalog.subjectCounts = options.subject_counts || {};
    state.catalog.knowledgePoints = Array.isArray(options.knowledge_points) ? options.knowledge_points : [];
    populateYearFilter();
    populateKnowledgePointFilter();
    renderQuestions();
    renderDashboard();
  } catch (error) {
    console.error('加载题目失败:', error);
    if (grid) {
      grid.innerHTML = '<div class="question-grid-state">题库加载失败，请检查网络后重试。</div>';
    }
  } finally {
    state.pagination.loading = false;
    if (grid) grid.removeAttribute('aria-busy');
    renderQuestionPagination();
  }
}

function toNonNegativeNumber(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? number : fallback;
}

function calculateProgressPercent(completed, total) {
  const safeCompleted = toNonNegativeNumber(completed);
  const safeTotal = toNonNegativeNumber(total);
  if (safeTotal <= 0) return 0;
  return Math.max(0, Math.min(100, Math.round(safeCompleted / safeTotal * 100)));
}

function renderDashboard() {
  const total = [state.catalog.total, state.pagination.total, state.allQuestions.length]
    .map(value => toNonNegativeNumber(value))
    .find(value => value > 0) || 0;
  // 优先用后端真实统计(避免与「个人中心」数据源不一致);
  // 旧值用 localStorage 兜底,等待 /user/stats/overview 返回后回填
  const records = state.userData.answerRecords || {};
  const answeredIds = Object.keys(records);
  let done = answeredIds.length;
  let correct = answeredIds.filter(id => records[id]?.status === 'correct').length;
  let donePercent = calculateProgressPercent(done, total);

  // 后端补正(总答题数 / 正确数)
  fetch('/user/stats/overview')
    .then(r => r.ok ? r.json() : null)
    .then(data => {
      if (!data) return;
      done = toNonNegativeNumber(data.total_answered);
      correct = toNonNegativeNumber(data.total_correct);
      donePercent = calculateProgressPercent(done, total);
      if (doneCountEl) doneCountEl.textContent = done;
      if (donePercentEl) donePercentEl.textContent = donePercent;
      if (passPercentEl) passPercentEl.innerHTML = donePercent + '<span class="dash-stat-unit">%</span>';
      if (subEl) subEl.textContent = `已做 ${done} / 总 ${total} 题`;
      // 把后端 by_subject 缓存给 renderSubjectsProgress 用
      state.backendSubjectStats = data.by_subject_backend || {};
      renderSubjectsProgress(subjects, subjectCounts, total, state.backendSubjectStats);
    })
    .catch(() => { /* 静默回退到 localStorage 数据 */ });

  document.getElementById('dashTotalCount').innerHTML = total + '<span class="dash-stat-unit">题</span>';
  const doneCountEl = document.getElementById('dashDoneCount');
  const donePercentEl = document.getElementById('dashDonePercent');
  const passPercentEl = document.getElementById('dashPassPercent');
  if (doneCountEl) doneCountEl.textContent = done;
  if (donePercentEl) donePercentEl.textContent = donePercent;
  // 「408 通关进度」= 已做题 / 总题数 (百分比),而非正确率
  if (passPercentEl) passPercentEl.innerHTML = donePercent + '<span class="dash-stat-unit">%</span>';
  const subEl = document.querySelector('.dash-stat-card:nth-child(3) .dash-stat-sub')
              || document.querySelector('[id="dashPassPercent"]')?.parentElement?.querySelector('.dash-stat-sub');
  if (subEl) subEl.textContent = `已做 ${done} / 总 ${total} 题`;

  const subjects = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
  const subjectCounts = {};
  subjects.forEach(s => {
    subjectCounts[s] = Number(state.catalog.subjectCounts[s] || 0);
  });

  let years = new Set();
  state.allQuestions.forEach(q => {
    const y = extractYearFromContent(q.content);
    if (y) years.add(y);
  });
  const yearCount = years.size || 18;
  document.getElementById('dashTotalDetail').textContent = `${Math.ceil(total / Math.max(yearCount, 1))}题×${yearCount}年`;

  renderSubjectsProgress(subjects, subjectCounts, total, state.backendSubjectStats);
  renderCalendarGrid();
  renderDashboardWrongBook();
}

// 题库总览 · 错题本(原位于「个人中心」，现迁移至此处)
async function renderDashboardWrongBook() {
  const listEl = document.getElementById('dashWrongBookList');
  if (!listEl) return;
  const filterEl = document.getElementById('dashWrongBookSubjectFilter');
  const reviewBtn = document.getElementById('dashStartReviewBtn');

  let wrongBookItems = [];
  try {
    const resp = await fetch('/wrong-book?status=open', { cache: 'no-store' });
    if (resp.ok) wrongBookItems = await resp.json();
  } catch (error) {
    console.warn('错题本加载失败', error);
    listEl.innerHTML = '<p class="notice-empty">错题本加载失败，请稍后重试。</p>';
    return;
  }
  if (!Array.isArray(wrongBookItems)) wrongBookItems = [];

  const subjects = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
  const wrongBySubject = {};
  subjects.forEach(s => wrongBySubject[s] = []);
  wrongBookItems.forEach(it => {
    const s = it.subject || '其他';
    if (!wrongBySubject[s]) wrongBySubject[s] = [];
    wrongBySubject[s].push(it);
  });

  if (filterEl) {
    filterEl.innerHTML = ['<option value="all">全部学科 ( ' + wrongBookItems.length + ' )</option>']
      .concat(subjects.filter(s => wrongBySubject[s].length).map(s => `<option value="${s}">${s} ( ${wrongBySubject[s].length} )</option>`))
      .join('');
  }
  if (reviewBtn) {
    if (wrongBookItems.length > 0) {
      reviewBtn.textContent = `开始错题复习模式 (${wrongBookItems.length} 题待复习)`;
      reviewBtn.style.display = 'inline-block';
    } else {
      reviewBtn.style.display = 'none';
    }
  }

  const renderWrongList = (list) => list.length
    ? list.slice(0, 8).map(item => `
      <div class="weak-point-item" style="align-items:flex-start;gap:12px;">
        <div style="flex:1;min-width:0;">
          <div class="weak-point-name">${escapeHtml(item.subject || '')} · ${escapeHtml((item.knowledge_points || []).join('、'))}</div>
          <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;line-height:1.5;">${escapeHtml((item.content || item.question_id || '').slice(0, 120))}${(item.content || '').length > 120 ? '...' : ''}</div>
          <div style="font-size:12px;color:var(--text-secondary);margin-top:4px;">错因：${escapeHtml(item.error_reason || '概念不清')} · 错 ${item.wrong_count || 1} 次 · 复盘 ${item.review_count || 0} 次</div>
        </div>
        <button class="wrong-review-btn" data-question-id="${escapeHtml(item.question_id)}" style="border:0;border-radius:8px;padding:7px 10px;background:var(--primary);color:#fff;cursor:pointer;">标记已掌握</button>
      </div>
    `).join('')
    : '<p style="color: var(--text-secondary)">该学科暂无错题。</p>';

  const bindResolveButtons = () => {
    listEl.querySelectorAll('.wrong-review-btn').forEach(btn => {
      btn.addEventListener('click', async () => {
        await fetch('/wrong-book/' + encodeURIComponent(btn.dataset.questionId) + '/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ result: 'resolved' })
        });
        renderDashboardWrongBook();
      });
    });
  };

  listEl.innerHTML = wrongBookItems.length ? renderWrongList(wrongBookItems) : '<p style="color: var(--text-secondary)">暂无未解决错题。</p>';
  bindResolveButtons();

  if (reviewBtn) {
    reviewBtn.onclick = startWrongBookReview;
  }
  if (filterEl) {
    filterEl.onchange = () => {
      const val = filterEl.value;
      const list = val === 'all' ? wrongBookItems : (wrongBySubject[val] || []);
      listEl.innerHTML = renderWrongList(list);
      bindResolveButtons();
    };
  }
}

function renderSubjectsProgress(subjects, subjectCounts, total, backendSubjectStats) {
  const grid = document.getElementById('subjectsProgressGrid');
  let totalMastery = 0;
  let masterySubjects = 0;

  grid.innerHTML = subjects.map(subject => {
    const count = subjectCounts[subject] || 0;
    // 后端数据库为权威源；只有接口尚未返回时才临时使用本地状态。
    const hasBackend = Boolean(
      backendSubjectStats
      && Object.prototype.hasOwnProperty.call(backendSubjectStats, subject)
    );
    const backend = (backendSubjectStats && backendSubjectStats[subject]) || {};
    const subjectQuestionIds = state.allQuestions
      .filter(q => q.subject === subject)
      .map(q => q.id);
    let mastered = toNonNegativeNumber(backend.mastered);
    let attempted = toNonNegativeNumber(backend.attempted);
    let correct = toNonNegativeNumber(backend.correct);
    if (!hasBackend) {
      // 前端兜底:本次会话内的状态
      let unsure = 0, failed = 0;
      subjectQuestionIds.forEach(id => {
        const status = state.questionMastery[id]
          || (state.userData.answerRecords?.[id]?.status === 'correct' ? 'mastered'
              : state.userData.answerRecords?.[id]?.status === 'wrong' ? 'failed' : null);
        if (status === 'mastered') { mastered++; attempted++; correct++; }
        else if (status === 'unsure') { unsure++; attempted++; }
        else if (status === 'failed') { failed++; attempted++; }
      });
    }
    const done = attempted;
    const rawMasteryScore = backend.mastery_score == null ? null : Number(backend.mastery_score);
    const masteryScore = hasBackend
      ? (Number.isFinite(rawMasteryScore) ? rawMasteryScore : null)
      : (attempted > 0 ? Math.round(correct / attempted * 100) : null);
    const percent = masteryScore == null ? null : Math.max(0, Math.min(100, masteryScore));
    const unfinished = Math.max(count - done, 0);
    const failed = Math.max(done - correct, 0);
    if (percent != null) {
      totalMastery += percent;
      masterySubjects += 1;
    }

    return `
      <div class="subject-progress-card">
        <div class="spc-header">
          <span class="spc-name">${subject}</span>
          <span class="spc-total">${count}题 · 已做 ${done}</span>
        </div>
        <div class="spc-main">
          <span class="spc-percent">${percent == null ? '暂无数据' : formatProgressPercent(percent)}</span>
          <span class="spc-label">${hasBackend ? `完成 ${done} / ${count} 题` : '按题库完成率统计'}</span>
        </div>
        <div class="spc-tags">
          <span class="spc-tag spc-tag-green">答对 ${correct}</span>
          <span class="spc-tag spc-tag-yellow">未答 ${unfinished}</span>
          <span class="spc-tag spc-tag-red">答错 ${failed}</span>
        </div>
      </div>
    `;
  }).join('');

  document.getElementById('avgMasteryRate').textContent = masterySubjects
    ? formatProgressPercent(totalMastery / masterySubjects)
    : '暂无数据';
}

// 根据真实数据生成"今日作战提示"(原写死)
async function renderDashboardNotice() {
  const list = document.getElementById('noticeList');
  if (!list) return;
  const notices = [];
  await loadDailyGoal();
  try {
    const response = await fetch('/user/profile-assessment/status', { cache: 'no-store' });
    if (response.ok) {
      const assessment = await response.json();
      if (!assessment.has_completed) {
        notices.push({
          tag: '画像', cls: 'notice-tag-yellow',
          text: assessment.in_progress ? '40 题快速画像尚未完成，继续作答即可保留进度' : '新用户建议先完成 40 题快速画像，让所有推荐更准确',
          time: assessment.in_progress ? '继续' : '开始', action: 'profile-assessment',
        });
      }
    }
  } catch (_) {}
  const records = state.userData.answerRecords || {};
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayKey = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
  let todayCount = 0;
  Object.values(records).forEach(r => {
    const ts = r.timestamp || r.ts;
    const d = new Date(ts || 0);
    if (isNaN(d.getTime())) return;
    d.setHours(0, 0, 0, 0);
    const k = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    if (k === todayKey) todayCount++;
  });

  // 1) 今日目标
  notices.push({
    tag: '今日', cls: 'notice-tag-blue',
    text: todayCount >= state.dailyGoal ? `今日已刷 ${todayCount} 题，完成每日目标` : `今日已刷 ${todayCount}/${state.dailyGoal} 题，继续推进`,
    time: '现在',
  });

  // 2) 错题提醒
  try {
    const r = await fetch('/wrong-book');
    if (r.ok) {
      const data = await r.json();
      const list = (data.wrong_book || data.questions || data.items || []);
      if (list.length > 0) {
        notices.push({
          tag: '复盘', cls: 'notice-tag-red',
          text: `错题本有 ${list.length} 道题待复盘,优先解决高频错的知识点`,
          time: '建议',
        });
      } else {
        notices.push({
          tag: '复盘', cls: 'notice-tag-green',
          text: '当前没有未解决的错题,继续保持',
          time: '良好',
        });
      }
    }
  } catch (e) { /* 静默 */ }

  // 3) 学习计划
  try {
    const r = await fetch('/study-plan/current');
    if (r.ok) {
      const data = await r.json();
      if (data.plan) {
        notices.push({
          tag: '计划', cls: 'notice-tag-blue',
          text: '已有专属学习计划,按周推进各科任务',
          time: '进行中',
        });
      } else {
        notices.push({
          tag: '计划', cls: 'notice-tag-yellow',
          text: '还没有学习计划,进入「学习计划」页 30 秒生成专属安排',
          time: '待办',
        });
      }
    }
  } catch (e) { /* 静默 */ }

  // 4) 薄弱学科(基于真实数据)
  try {
    const r = await fetch('/mastery');
    if (r.ok) {
      const data = await r.json();
      const items = Array.isArray(data) ? data : (data.items || data.mastery || []);
      if (items.length) {
        const weak = items
          .filter(it => (it.score || 0) < 60)
          .sort((a, b) => (a.score || 0) - (b.score || 0))
          .slice(0, 1)[0];
        if (weak && weak.subject) {
          notices.push({
            tag: '突破', cls: 'notice-tag-red',
            text: `${weak.subject} 题目覆盖进度仅 ${formatProgressPercent(weak.score || 0)},建议先做薄弱点专项练习`,
            time: '重点',
          });
        }
      }
    }
  } catch (e) { /* 静默 */ }

  // 渲染(最多 4 条)
  if (!notices.length) {
    list.innerHTML = '<div class="notice-empty">先去刷几道题,系统会基于你的数据给出今日提示</div>';
    return;
  }
  list.innerHTML = notices.slice(0, 4).map(n => `
    <${n.action ? 'button type="button"' : 'div'} class="notice-item${n.action ? ' is-action' : ''}" ${n.action ? `data-notice-action="${n.action}"` : ''}>
      <span class="notice-tag ${n.cls}">${escapeHtml(n.tag)}</span>
      <span class="notice-text">${escapeHtml(n.text)}</span>
      <span class="notice-time">${escapeHtml(n.time)}</span>
    </${n.action ? 'button' : 'div'}>
  `).join('');
  list.querySelector('[data-notice-action="profile-assessment"]')?.addEventListener('click', async () => {
    switchView('profile');
    await loadProfile();
    document.getElementById('startProfileAssessmentBtn')?.click();
  });
  renderRollingReview();
}

async function loadDailyGoal() {
  try {
    const response = await fetch('/user/preferences/daily-goal');
    if (response.ok) {
      const data = await response.json();
      state.dailyGoal = Math.max(1, Math.min(100, Number(data.daily_question_goal) || 5));
    }
  } catch (_) {}
  const input = document.getElementById('dailyGoalInput');
  const calendarGoal = document.getElementById('calGoal');
  if (input) input.value = String(state.dailyGoal);
  if (calendarGoal) calendarGoal.textContent = String(state.dailyGoal);
}

async function saveDailyGoal() {
  const input = document.getElementById('dailyGoalInput');
  const button = document.getElementById('saveDailyGoalBtn');
  const value = Math.max(1, Math.min(100, Number(input?.value) || 5));
  if (input) input.value = String(value);
  if (button) { button.disabled = true; button.textContent = '保存中'; }
  try {
    const response = await fetch('/user/preferences/daily-goal', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ daily_question_goal: value })
    });
    if (!response.ok) throw new Error('保存失败');
    state.dailyGoal = value;
    await renderDashboardNotice();
    loadDailyTasks().catch(() => {});
  } catch (error) {
    alert(error.message || '每日题量保存失败');
  } finally {
    if (button) { button.disabled = false; button.textContent = '保存'; }
  }
}

async function renderRollingReview() {
  const panel = document.getElementById('rollingReviewPanel');
  if (!panel) return;
  try {
    const response = await fetch('/daily-review/yesterday?limit=5');
    const data = response.ok ? await response.json() : { items: [] };
    state.rollingReviewItems = data.items || [];
    if (!state.rollingReviewItems.length) {
      panel.innerHTML = '<div class="rolling-review-empty">昨日暂无做题记录，今天完成后明日会自动进入滚动复盘。</div>';
      return;
    }
    panel.innerHTML = `
      <div class="rolling-review-head"><b>昨日滚动复盘</b><span>错题优先 · 已自动去重</span></div>
      <div class="rolling-review-list">${state.rollingReviewItems.map(item => `
        <button type="button" data-review-question="${escapeHtml(item.question_id)}">
          <span class="${item.was_wrong ? 'is-wrong' : 'is-done'}">${item.was_wrong ? '昨日错题' : '昨日做过'}</span>
          <p>${escapeHtml(item.question?.content || '题目')}</p><b>${item.was_wrong ? '复盘错题去重做' : '再次复习'} →</b>
        </button>`).join('')}</div>`;
    panel.querySelectorAll('[data-review-question]').forEach(button => {
      button.addEventListener('click', () => {
        const item = state.rollingReviewItems.find(row => row.question_id === button.dataset.reviewQuestion);
        if (item?.question) openQuestion(item.question);
      });
    });
  } catch (_) {
    panel.innerHTML = '<div class="rolling-review-empty">昨日复盘暂时加载失败，请稍后重试。</div>';
  }
}

// 根据真实数据生成"AI 复盘建议"列表(原写死)
async function renderDashboardTutors() {
  const list = document.getElementById('tutorList');
  if (!list) return;
  const items = [];

  // 1) 优先用 user/insights 中的弱项
  try {
    const r = await fetch('/user/insights');
    if (r.ok) {
      const data = await r.json();
      const weak = (data.weak_points || []).slice(0, 3);
      weak.forEach(wp => {
        const subject = wp.subject || '其他';
        const code = subjectCode(subject);
        const score = wp.score != null ? Math.round(wp.score) : null;
        items.push({
          code,
          subject,
          name: wp.knowledge_point || wp.knowledgePoint || '知识点',
          desc: score != null
            ? `题目覆盖进度 ${formatProgressPercent(score)},错 ${wp.wrong ?? wp.error_count ?? 0} 次,优先突破`
            : '需要重点关注,建议先做相关练习',
          badge: score != null && score < 50 ? '危险' : (score != null && score < 70 ? '易错' : '关注'),
          cls: score != null && score < 50 ? 'tutor-item-red' : 'tutor-item-green',
        });
      });
    }
  } catch (e) { /* 静默 */ }

  // 2) 用 mastery 补齐
  if (items.length < 3) {
    try {
      const r = await fetch('/mastery');
      if (r.ok) {
        const data = await r.json();
        const arr = Array.isArray(data) ? data : (data.items || data.mastery || []);
        arr
          .filter(it => (it.score || 0) < 70)
          .sort((a, b) => (a.score || 0) - (b.score || 0))
          .slice(0, 3 - items.length)
          .forEach(it => {
            const subject = it.subject || '其他';
            items.push({
              code: subjectCode(subject),
              subject,
              name: it.knowledge_point || it.chapter || '章节',
              desc: `题目覆盖进度 ${formatProgressPercent(it.score || 0)}, 建议先复盘再做题`,
              badge: it.level === 'weak' || it.level === 'danger' ? '危险' : (it.level === 'partial' ? '易错' : '关注'),
              cls: it.level === 'weak' || it.level === 'danger' ? 'tutor-item-red' : 'tutor-item-green',
            });
          });
      }
    } catch (e) { /* 静默 */ }
  }

  if (!items.length) {
    list.innerHTML = '<div class="tutor-empty">完成若干题目后,这里会列出你最该突破的薄弱点</div>';
    return;
  }
  list.innerHTML = items.slice(0, 3).map(it => `
    <div class="tutor-item ${it.cls}">
      <div class="tutor-avatar">${escapeHtml(it.code)}</div>
      <div class="tutor-info">
        <div class="tutor-name">${escapeHtml(it.subject)} · ${escapeHtml(it.name)}</div>
        <div class="tutor-desc">${escapeHtml(it.desc)}</div>
      </div>
      <span class="tutor-badge">${escapeHtml(it.badge)}</span>
    </div>
  `).join('');
}

function subjectCode(subject) {
  return ({
    '数据结构': 'DS',
    '计算机组成原理': 'CO',
    '操作系统': 'OS',
    '计算机网络': 'CN',
  })[subject] || (subject ? subject.slice(0, 2) : 'KB');
}

function renderCalendarGrid() {
  const grid = document.getElementById('calendarGrid');
  if (!grid) return;
  const WEEKDAYS = ['周一', '周二', '周三', '周四', '周五', '周六', '周日'];
  const DAYS = 30;

  // 1) 默认从 localStorage 拉一份(无网络/接口 401 时降级用)
  const localDaily = {};
  const records = Object.values(state.userData.answerRecords || {});
  records.forEach(r => {
    const ts = r.timestamp || r.ts;
    const d = new Date(ts || Date.now());
    if (isNaN(d.getTime())) return;
    d.setHours(0, 0, 0, 0);
    const key = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    localDaily[key] = (localDaily[key] || 0) + 1;
  });

  // 2) 异步拉后端权威数据(覆盖 localStorage),渲染完再 patch
  loadActivityHeatmap()
    .then(data => {
      if (data && data.daily) {
        const serverDaily = {};
        Object.keys(data.daily).forEach(k => {
          const v = parseInt(data.daily[k], 10) || 0;
          if (v > 0) serverDaily[k] = v;
        });
        // 重新渲染
        _paintCalendar(grid, DAYS, WEEKDAYS, serverDaily);
      }
    })
    .catch(() => { /* 静默降级,继续用 localDaily */ });

  // 3) 立即用 localData 渲染(避免白屏)
  _paintCalendar(grid, DAYS, WEEKDAYS, localDaily);
}

function _paintCalendar(grid, DAYS, WEEKDAYS, daily) {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const todayKey = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');

  // 计算连续天数
  let streak = 0;
  for (let i = 0; i < DAYS; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const k = d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0');
    if ((daily[k] || 0) > 0) streak++;
    else if (i === 0) continue;
    else break;
  }

  // 日历布局：严格渲染最近 30 个自然日,再用空白格按星期对齐。
  const startDate = new Date(today);
  startDate.setDate(startDate.getDate() - (DAYS - 1));
  const startDow = startDate.getDay(); // 0=周日
  const leadingBlanks = startDow === 0 ? 6 : startDow - 1;

  let html = WEEKDAYS.map(day => `<div class="calendar-weekday-header">${day.replace('周', '')}</div>`).join('');
  for (let i = 0; i < leadingBlanks; i++) {
    html += '<div class="calendar-cell calendar-cell-empty" aria-hidden="true"></div>';
  }

  for (let i = 0; i < DAYS; i++) {
    const date = new Date(startDate);
    date.setDate(startDate.getDate() + i);
    const key = date.getFullYear() + '-' + String(date.getMonth() + 1).padStart(2, '0') + '-' + String(date.getDate()).padStart(2, '0');
    const count = daily[key] || 0;
    const isToday = key === todayKey;
    const dayNum = date.getDate();
    const isMonthStart = dayNum === 1 || i === 0;

    let cls = 'calendar-cell';
    let title = key + ' · ' + count + ' 题';
    if (count > 0) {
      const lvl = count <= 2 ? 1 : count <= 5 ? 2 : count <= 10 ? 3 : 4;
      cls += ' active level-' + lvl;
    }
    if (isToday) cls += ' today';
    if (isMonthStart) cls += ' month-start';
    html += `
      <div class="${cls}" title="${title}" data-date="${key}" aria-label="${title}">
        <span class="cal-day-num">${dayNum}</span>
        <span class="cal-day-count">${count > 0 ? count : ''}</span>
      </div>`;
  }

  grid.innerHTML = html;

  const calDaysDone = document.getElementById('calDaysDone');
  const calStreak = document.getElementById('calStreak');
  if (calDaysDone) {
    calDaysDone.textContent = Object.keys(daily).filter(k => (daily[k] || 0) > 0).length;
  }
  if (calStreak) calStreak.textContent = streak;
}

function populateYearFilter() {
  const yearFilter = document.getElementById('yearFilter');
  const selected = yearFilter.value || state.filters.year || 'all';
  const years = new Set(state.catalog.years || []);
  while (yearFilter.options.length > 1) yearFilter.remove(1);
  
  // 添加年份选项
  Array.from(years).sort((a, b) => b - a).forEach(year => {
    const option = document.createElement('option');
    option.value = year;
    option.textContent = year + '年';
    yearFilter.appendChild(option);
  });
  yearFilter.value = Array.from(yearFilter.options).some(option => option.value === selected)
    ? selected
    : 'all';
}

function populateKnowledgePointFilter() {
  const filter = document.getElementById('knowledgePointFilter');
  if (!filter) return;
  const selected = state.filters.knowledgePoint || 'all';
  while (filter.options.length > 1) filter.remove(1);
  (state.catalog.knowledgePoints || []).forEach(item => {
    const title = typeof item === 'string' ? item : item.title;
    const count = typeof item === 'string' ? null : item.count;
    if (!title) return;
    const option = document.createElement('option');
    option.value = title;
    option.textContent = count == null ? title : `${title}（${count}）`;
    filter.appendChild(option);
  });
  const exists = Array.from(filter.options).some(option => option.value === selected);
  if (!exists) state.filters.knowledgePoint = 'all';
  filter.value = exists ? selected : 'all';
}

// 事件监听
function initEventListeners() {
  // 导航切换
  document.querySelectorAll('.nav-item[data-view]').forEach(item => {
    item.addEventListener('click', () => {
      switchView(item.dataset.view);
    });
  });
  
  // 用户信息点击
  document.querySelector('.user-info')?.addEventListener('click', () => {
    switchView('profile');
  });
  document.getElementById('logoutBtn')?.addEventListener('click', logoutAccount);
  document.getElementById('customerServiceBtn')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText('17635575899'); alert('客服微信已复制：17635575899\n客服电话：17635575899'); }
    catch (_) { alert('客服电话/微信：17635575899'); }
  });
  
  document.querySelectorAll('.dash-tab[data-view]').forEach(tab => {
    tab.addEventListener('click', () => {
      switchView(tab.dataset.view);
    });
  });
  
  const gotoBtn = document.getElementById('gotoQuestionBankBtn');
  if (gotoBtn) {
    gotoBtn.addEventListener('click', () => switchToQuestionBankDetail());
  }
  
  // 科目标签切换
  document.querySelectorAll('.subject-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.subject-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.currentSubject = tab.dataset.subject;
      state.filters.subject = tab.dataset.subject;
      state.filters.knowledgePoint = 'all';
      document.getElementById('subjectFilter').value = tab.dataset.subject;
      document.getElementById('knowledgePointFilter').value = 'all';
      loadQuestions(1);
    });
  });
  
  // 筛选器
  document.getElementById('subjectFilter').addEventListener('change', (e) => {
    state.filters.subject = e.target.value;
    state.filters.knowledgePoint = 'all';
    document.getElementById('knowledgePointFilter').value = 'all';
    state.currentSubject = e.target.value;
    if (e.target.value !== 'all') {
      document.querySelectorAll('.subject-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.subject === e.target.value);
      });
    } else {
      document.querySelectorAll('.subject-tab').forEach(tab => {
        tab.classList.toggle('active', tab.dataset.subject === 'all');
      });
    }
    loadQuestions(1);
  });

  document.getElementById('knowledgePointFilter').addEventListener('change', (e) => {
    state.filters.knowledgePoint = e.target.value;
    loadQuestions(1);
  });
  
  document.getElementById('yearFilter').addEventListener('change', (e) => {
    state.filters.year = e.target.value;
    loadQuestions(1);
  });
  
  document.getElementById('statusFilter').addEventListener('change', (e) => {
    state.filters.status = e.target.value;
    loadQuestions(1);
  });
  
  document.getElementById('favoriteFilterBtn').addEventListener('click', () => {
    state.showFavoritesOnly = !state.showFavoritesOnly;
    const btn = document.getElementById('favoriteFilterBtn');
    const text = document.getElementById('favoriteFilterText');
    if (state.showFavoritesOnly) {
      btn.classList.add('active');
      text.textContent = '全部题目';
    } else {
      btn.classList.remove('active');
      text.textContent = '查看收藏';
    }
    loadQuestions(1);
  });
  
  document.getElementById('favoriteBtn').addEventListener('click', () => {
    if (state.currentQuestion) {
      toggleFavorite(state.currentQuestion.id);
    }
  });

  initQuestionNotes();
  
  // 模态框关闭
  document.getElementById('closeModal').addEventListener('click', closeModal);
  document.getElementById('modalOverlay').addEventListener('click', closeModal);
  
  document.getElementById('showAnswerBtn').addEventListener('click', showAnswer);
  document.getElementById('prevQuestionBtn').addEventListener('click', openPreviousQuestion);
  document.getElementById('nextQuestionBtn').addEventListener('click', openNextQuestion);
  document.getElementById('saveDailyGoalBtn')?.addEventListener('click', saveDailyGoal);
  document.getElementById('questionPrevPage')?.addEventListener('click', () => {
    if (state.pagination.page > 1) loadQuestions(state.pagination.page - 1);
  });
  document.getElementById('questionNextPage')?.addEventListener('click', () => {
    if (state.pagination.page < state.pagination.totalPages) loadQuestions(state.pagination.page + 1);
  });
  
  // 答案标签切换
  document.querySelectorAll('.answer-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.answer-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.activeAnswerTab = tab.dataset.tab;
      renderAnswerContent();
    });
  });
  
  // 掌握程度按钮
  document.querySelectorAll('.mastery-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      if (state.currentQuestion) {
        const mastery = btn.dataset.mastery;
        state.questionMastery[state.currentQuestion.id] = mastery;
        closeModal();
        renderQuestions();
      }
    });
  });
  
  // 快捷操作按钮(底部)
  document.querySelectorAll('.quick-action-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const ta = document.getElementById('messageInput');
      ta.value = btn.dataset.text;
      ta.focus();
      _autoresizeTextarea(ta);
      _updateCharCount();
    });
  });

  // 欢迎卡片(点一下填到输入框)
  document.querySelectorAll('.welcome-card').forEach(card => {
    card.addEventListener('click', () => {
      const ta = document.getElementById('messageInput');
      ta.value = card.dataset.text || '';
      ta.focus();
      _autoresizeTextarea(ta);
      _updateCharCount();
    });
  });

  // 输入框:Enter 发送 / Shift+Enter 换行 / 自动撑高 / 字符计数
  const ta = document.getElementById('messageInput');
  if (ta) {
    ta.addEventListener('input', () => {
      _autoresizeTextarea(ta);
      _updateCharCount();
    });
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
        e.preventDefault();
        sendMessage();
      }
    });
  }
  // 移除旧的 keypress 监听(避免双触发)
  // 字符计数初值
  _updateCharCount();
  
  // 发送消息
  document.getElementById('sendBtn').addEventListener('click', sendMessage);
  // (textarea 的 keydown/Enter 已在上面注册,这里不再挂 keypress)

  // 新对话
  const newChatBtn = document.getElementById('newChatBtn');
  if (newChatBtn) newChatBtn.addEventListener('click', startNewChat);

  
  // 题目提问对话
  document.getElementById('qaChatSend').addEventListener('click', sendQAChatMessage);
  document.getElementById('qaChatInput').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') sendQAChatMessage();
  });
}

function switchToQuestionBankDetail(e) {
  if (e) e.preventDefault();
  switchView('question-bank-detail');
}

// 渲染题目
function renderQuestions() {
  const grid = document.getElementById('questionGrid');
  const filteredQuestions = state.allQuestions;
  
  // 更新计数
  document.getElementById('questionCount').textContent = 
    `共 ${state.pagination.total} 道题目 · 第 ${state.pagination.page}/${state.pagination.totalPages} 页`;
  
  // 渲染
  const htmlArr = filteredQuestions.map((question) => {
    const mastery = state.questionMastery[question.id];
    const displayYear = getQuestionDisplayYear(question);
    const hasAnswer = question.answer && question.answer.trim();
    const isFav = isFavorited(question.id);
    const record = getAnswerRecord(question.id);
    
    const typeTag = isChoiceQuestion(question)
      ? `<span class="question-tag type-choice">${isMultipleChoiceQuestion(question) ? '多选题' : '单选题'}</span>`
      : '<span class="question-tag type-big">大题</span>';
    
    const yearTag = displayYear !== '练习题'
      ? `<span class="question-tag year">${displayYear}年</span>`
      : '<span class="question-tag year-practice">练习题</span>';
    
    let statusHtml = '';
    if (record) {
      const icon = record.status === 'correct' ? '✓' : '✗';
      const statusClass = record.status === 'correct' ? 'correct' : 'wrong';
      const statusText = record.status === 'correct' ? '做对' : '做错';
      statusHtml = `<span class="question-status ${statusClass}">${icon} ${statusText}</span>`;
    } else {
      statusHtml = '<span class="question-status unanswered">○ 未做</span>';
    }
    
    const answerBadge = hasAnswer
      ? '<span class="question-answer-badge has-answer">有解析</span>'
      : '<span class="question-answer-badge no-answer">待生成</span>';
    const visualizationBadge = question.visualization?.available
      ? `<span class="question-visualization-badge ${question.visualization.mode === 'simulation' ? 'is-simulation' : ''}">◫ ${escapeHtml(question.visualization.mode_label || question.visualization.label || '可视化')}</span>`
      : '';
    
    const favStar = isFav
      ? '<svg class="favorite-star filled" viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>'
      : '<svg class="favorite-star" viewBox="0 0 24 24"><path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z"/></svg>';
    
    const shortContent = question.content.length > 150
      ? question.content.substring(0, 150) + '...'
      : question.content;
    
    const html = `
      <div class="question-card ${mastery || ''}" data-question-id="${question.id}">
        ${favStar}
        <div class="question-card-header">
          <div class="question-card-meta">
            <span class="question-card-id">${escapeHtml(question.subject || '')}</span>
            ${typeTag}
            ${yearTag}
          </div>
          <div class="question-card-badges">
            ${statusHtml}
            ${answerBadge}
            ${visualizationBadge}
          </div>
        </div>
        <div class="question-card-text">${escapeHtml(shortContent)}</div>
        <div class="question-card-footer">
          <div class="question-card-tags"></div>
          <span style="font-size:0.75rem;color:var(--text-muted);">查看详情 →</span>
        </div>
      </div>
    `;
    return html;
  });

  grid.innerHTML = htmlArr.join('');
  window.KaoyanRuntime.renderMath(grid);
  renderQuestionPagination();
  
  // 绑定点击事件
  grid.querySelectorAll('.question-card').forEach(card => {
    card.addEventListener('click', () => {
      const questionId = card.dataset.questionId;
      const question = state.allQuestions.find(q => q.id === questionId);
      if (question) {
        openQuestion(question);
      }
    });
  });
}

function renderQuestionPagination() {
  const container = document.getElementById('questionPagination');
  if (!container) return;
  const { page, totalPages, total } = state.pagination;
  container.hidden = totalPages <= 1;
  document.getElementById('questionPageInfo').textContent = `第 ${page} / ${totalPages} 页 · ${total} 题`;
  document.getElementById('questionPrevPage').disabled = page <= 1 || state.pagination.loading;
  document.getElementById('questionNextPage').disabled = page >= totalPages || state.pagination.loading;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function formatDetailed(text) {
  if (!text) return '';
  const normalized = String(text)
    .replace(/\\([*_])/g, '$1')
    .replace(/\*{3,}([^*\n]+?)\*{3,}/g, '**$1**');
  const div = document.createElement('div');
  div.textContent = normalized;
  let html = div.innerHTML;
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong style="color:#3b82f6;">$1</strong>');
  html = html.replace(/\n\n/g, '</p><p style="margin:8px 0;">');
  html = '<p style="margin:6px 0;">' + html + '</p>';
  return html;
}

// 打开题目详情
function openQuestion(question) {
  state.visualizationPlayer?.destroy();
  state.visualizationPlayer = null;
  state.currentQuestion = question;
  state.selectedOption = null;
  state.answerSubmitted = false;
  state.qaConversation = [];
  state.activeAnswerTab = 'answer';
  state.visualizationStep = 0;
  document.querySelectorAll('.answer-tab').forEach(tab => {
    tab.classList.toggle('active', tab.dataset.tab === 'answer');
  });
  const visualizationTab = document.getElementById('questionVisualizationTab');
  visualizationTab?.classList.toggle('hidden', !question.visualization?.available);
  if (visualizationTab && question.visualization?.available) {
    visualizationTab.textContent = question.visualization.mode === 'simulation' ? '动态演算' : '步骤图解';
  }
  
  // 更新收藏按钮状态
  updateFavoriteBtnState(question.id);
  
  // 更新元数据
  document.getElementById('modalSubject').textContent = question.subject;
  document.getElementById('modalType').textContent = getQuestionTypeLabel(question);
  document.getElementById('modalYear').textContent = getQuestionDisplayYear(question) + (getQuestionDisplayYear(question) !== '练习题' ? '年' : '');
  
  // 更新题目内容
  window.KaoyanRuntime.renderMathText(document.getElementById('modalQuestion'), question.content);
  
  // 渲染选项
  const optionsDiv = document.getElementById('modalOptions');
  if (question.options && question.options.length > 0) {
    optionsDiv.innerHTML = question.options.map(opt => {
      const label = opt.charAt(0);
      const text = opt.substring(2).trim();
      return `
        <div class="option-item" data-option="${label}">
          <span class="option-label">${label}</span>
          <span class="option-text">${escapeHtml(text)}</span>
          <svg class="option-result-icon correct-icon" viewBox="0 0 24 24"><path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="#10b981"/></svg>
          <svg class="option-result-icon incorrect-icon" viewBox="0 0 24 24"><path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" fill="#ef4444"/></svg>
        </div>
      `;
    }).join('');
    window.KaoyanRuntime.renderMath(optionsDiv);
    
    if (isChoiceQuestion(question)) {
      optionsDiv.innerHTML += `
        <button class="submit-answer-btn" id="submitAnswerBtn" disabled>${isMultipleChoiceQuestion(question) ? '可选择多个选项，选完后提交' : '请先选择一个选项'}</button>
        <div id="answerFeedback" style="display:none;"></div>
      `;
    }
    
    optionsDiv.style.display = 'flex';
  } else {
    optionsDiv.style.display = 'none';
  }
  
  // 绑定选项点击事件
  optionsDiv.querySelectorAll('.option-item').forEach(item => {
    item.addEventListener('click', () => selectOption(item.dataset.option));
  });
  
  // 绑定提交按钮
  const submitBtn = document.getElementById('submitAnswerBtn');
  if (submitBtn) {
    submitBtn.addEventListener('click', submitAnswer);
  }
  
  // 隐藏答案区域和提问面板
  document.getElementById('qaSplitLayout').classList.add('hidden');
  const showAnswerButton = document.getElementById('showAnswerBtn');
  showAnswerButton.style.display = question.answer ? 'block' : 'none';
  showAnswerButton.textContent = question.answer ? '查看答案' : '生成答案';
  
  // 清空聊天记录
  const chatMessages = document.getElementById('qaChatMessages');
  chatMessages.innerHTML = '<div class="qa-chat-placeholder">针对当前题目追问，例如「请用定义重新验证第 3 步，并说明 B 选项错在哪里」</div>';
  
  // 显示模态框
  document.getElementById('questionModal').classList.remove('hidden');
  updateNextQuestionButton();
  loadQuestionNote(question.id);
}

// 选择选项
function selectOption(optionLabel) {
  if (state.answerSubmitted) return;
  const multiple = isMultipleChoiceQuestion(state.currentQuestion);
  const current = new Set(normalizeAnswerLetters(state.selectedOption).split('').filter(Boolean));
  if (multiple) {
    if (current.has(optionLabel)) current.delete(optionLabel);
    else current.add(optionLabel);
    state.selectedOption = [...current].sort().join('');
  } else {
    state.selectedOption = optionLabel;
  }
  
  // 更新选项样式
  document.querySelectorAll('#modalOptions .option-item').forEach(item => {
    item.classList.toggle('selected', normalizeAnswerLetters(state.selectedOption).includes(item.dataset.option));
  });
  
  // 更新提交按钮
  const submitBtn = document.getElementById('submitAnswerBtn');
  if (submitBtn) {
    submitBtn.disabled = !state.selectedOption;
    submitBtn.textContent = multiple && state.selectedOption
      ? `已选 ${state.selectedOption.split('').join('、')}，确认提交`
      : '确认提交';
  }
}

// 提交答案
function submitAnswer() {
  if (!state.selectedOption || state.answerSubmitted) return;
  
  state.answerSubmitted = true;
  const question = state.currentQuestion;
  const correctAnswer = question.answer || '';
  
  // 禁用所有选项
  document.querySelectorAll('#modalOptions .option-item').forEach(item => {
    item.classList.add('disabled');
    item.classList.remove('selected');
  });
  
  const submitBtn = document.getElementById('submitAnswerBtn');
  if (submitBtn) {
    submitBtn.style.display = 'none';
  }
  
  // 显示反馈
  const feedback = document.getElementById('answerFeedback');
  
  if (correctAnswer && correctAnswer.trim()) {
    // 有答案时可以判断对错
    const userAnswer = normalizeAnswerLetters(state.selectedOption);
    const normalizedCorrect = normalizeAnswerLetters(correctAnswer);
    const isCorrect = userAnswer === normalizedCorrect;
    
    // 记录答题结果
    recordAnswer(question.id, userAnswer, correctAnswer);
    syncQuestionBankAnswer(question, userAnswer, correctAnswer);
    
    // 高亮正确和错误选项
    document.querySelectorAll('#modalOptions .option-item').forEach(item => {
      if (normalizedCorrect.includes(item.dataset.option)) {
        item.classList.add('correct');
      }
      if (userAnswer.includes(item.dataset.option) && !normalizedCorrect.includes(item.dataset.option)) {
        item.classList.add('incorrect');
      }
    });
    
    if (isCorrect) {
      feedback.className = 'answer-feedback correct-feedback';
      feedback.innerHTML = '✅ 回答正确！太棒了！';
      feedback.style.display = 'flex';
      
      // 自动标记为掌握
      if (!state.questionMastery[question.id]) {
        state.questionMastery[question.id] = 'mastered';
      }
    } else {
      feedback.className = 'answer-feedback incorrect-feedback';
      feedback.innerHTML = `❌ 回答错误。正确答案是 ${escapeHtml(normalizedCorrect)}${question.visualization?.available ? '<button type="button" class="answer-error-replay" data-open-error-visualization>从疑似错步重播</button>' : ''}`;
      feedback.style.display = 'flex';
      feedback.querySelector('[data-open-error-visualization]')?.addEventListener('click', () => {
        state.activeAnswerTab = 'visualization';
        document.querySelectorAll('.answer-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.tab === 'visualization'));
        renderAnswerContent();
      });
      
      // 标记为不会
      state.questionMastery[question.id] = 'failed';
    }
  } else {
    // 没有答案时，只显示用户选择
    feedback.className = 'answer-feedback';
    feedback.style.backgroundColor = 'rgba(99, 102, 241, 0.08)';
    feedback.style.color = 'var(--primary)';
    feedback.style.border = '1px solid rgba(99, 102, 241, 0.15)';
    feedback.innerHTML = '📝 你选择了选项 ' + state.selectedOption + '。答案正在生成中，请点击"查看答案"获取解析。';
    feedback.style.display = 'flex';
  }
  
  // 显示答案按钮
  document.getElementById('showAnswerBtn').style.display = 'block';
  document.getElementById('showAnswerBtn').textContent = correctAnswer ? '查看解析' : '生成答案';
}

function syncQuestionBankAnswer(question, selectedOption, correctAnswer) {
  const payload = {
    question_id: question.id,
    selected_option: selectedOption,
    correct_answer: correctAnswer,
    question_content: question.content,
    options: question.options || [],
    explanation: question.explanation || '',
    subject: question.subject || '',
    knowledge_points: question.knowledge_points || question.tags || [],
  };
  fetch('/question-bank/submit-answer', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  })
    .then(() => {
      // 提交后异步刷新个人中心(统计/Token/任务) + 题库热力日历
      Promise.all([loadProfile(), loadDailyTasks()]).catch(() => {});
    })
    .catch(e => {
      window.KaoyanRuntime.queueMutation({
        key: 'answer:' + question.id + ':' + Date.now(),
        url: '/question-bank/submit-answer',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      console.warn('学习记录已离线排队', e);
    });
}

function closeModal() {
  closeQuestionNote(true);
  document.getElementById('questionModal').classList.add('hidden');
  state.currentQuestion = null;
}

function getQuestionSequenceFromGrid() {
  return Array.from(document.querySelectorAll('#questionGrid .question-card'))
    .map(card => state.allQuestions.find(question => question.id === card.dataset.questionId))
    .filter(Boolean);
}

function updateNextQuestionButton() {
  const button = document.getElementById('nextQuestionBtn');
  const previousButton = document.getElementById('prevQuestionBtn');
  if ((!button && !previousButton) || !state.currentQuestion) return;
  const sequence = getQuestionSequenceFromGrid();
  const index = sequence.findIndex(question => question.id === state.currentQuestion.id);
  const hasNext = (index >= 0 && index < sequence.length - 1)
    || state.pagination.page < state.pagination.totalPages;
  const hasPrevious = index > 0 || state.pagination.page > 1;
  if (button) {
    button.disabled = !hasNext;
    button.innerHTML = hasNext
      ? '下一题 <span aria-hidden="true">→</span>'
      : '已到最后一题';
  }
  if (previousButton) {
    previousButton.disabled = !hasPrevious;
    previousButton.innerHTML = hasPrevious
      ? '<span aria-hidden="true">←</span> 上一题'
      : '已到第一题';
  }
}

async function openPreviousQuestion() {
  const current = state.currentQuestion;
  if (!current) return;
  const sequence = getQuestionSequenceFromGrid();
  const index = sequence.findIndex(question => question.id === current.id);
  if (index < 0) {
    updateNextQuestionButton();
    return;
  }
  const button = document.getElementById('prevQuestionBtn');
  if (button) button.disabled = true;
  if (state.noteDirty) {
    const saved = await saveCurrentQuestionNote();
    if (!saved) {
      updateNextQuestionButton();
      return;
    }
  }
  closeQuestionNote(false);
  if (index > 0) {
    openQuestion(sequence[index - 1]);
    return;
  }
  if (state.pagination.page > 1) {
    await loadQuestions(state.pagination.page - 1);
    const previousSequence = getQuestionSequenceFromGrid();
    if (previousSequence.length) openQuestion(previousSequence[previousSequence.length - 1]);
    else updateNextQuestionButton();
  }
}

async function openNextQuestion() {
  const current = state.currentQuestion;
  if (!current) return;
  const sequence = getQuestionSequenceFromGrid();
  const index = sequence.findIndex(question => question.id === current.id);
  if (index < 0) {
    updateNextQuestionButton();
    return;
  }

  const button = document.getElementById('nextQuestionBtn');
  button.disabled = true;
  if (state.noteDirty) {
    const saved = await saveCurrentQuestionNote();
    if (!saved) {
      updateNextQuestionButton();
      return;
    }
  }
  closeQuestionNote(false);
  if (index < sequence.length - 1) {
    openQuestion(sequence[index + 1]);
    return;
  }
  if (state.pagination.page < state.pagination.totalPages) {
    const nextPage = state.pagination.page + 1;
    await loadQuestions(nextPage);
    const nextSequence = getQuestionSequenceFromGrid();
    if (nextSequence.length) openQuestion(nextSequence[0]);
    else updateNextQuestionButton();
  }
}

function initQuestionNotes() {
  const openBtn = document.getElementById('openNoteBtn');
  const closeBtn = document.getElementById('closeNoteBtn');
  const fullBtn = document.getElementById('noteFullscreenBtn');
  const saveBtn = document.getElementById('saveNoteBtn');
  const deleteBtn = document.getElementById('deleteNoteBtn');
  const textArea = document.getElementById('questionNoteText');
  const canvas = document.getElementById('questionNoteCanvas');
  if (!openBtn || !canvas) return;

  openBtn.addEventListener('click', openQuestionNote);
  closeBtn.addEventListener('click', () => closeQuestionNote(true));
  saveBtn.addEventListener('click', () => saveCurrentQuestionNote());
  fullBtn.addEventListener('click', toggleQuestionNoteFullscreen);
  deleteBtn.addEventListener('click', deleteCurrentQuestionNote);
  textArea.addEventListener('input', markQuestionNoteDirty);

  document.querySelectorAll('.note-mode-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      document.querySelectorAll('.note-mode-tab').forEach(item => item.classList.toggle('active', item === tab));
      document.querySelectorAll('.note-mode-panel').forEach(panel => {
        panel.classList.toggle('hidden', panel.dataset.notePanel !== tab.dataset.noteMode);
      });
      if (tab.dataset.noteMode === 'draw') {
        if (document.activeElement && typeof document.activeElement.blur === 'function') {
          document.activeElement.blur();
        }
        requestAnimationFrame(() => requestAnimationFrame(resizeNoteCanvas));
      }
    });
  });

  document.getElementById('notePenBtn').addEventListener('click', () => setNoteTool('pen'));
  document.getElementById('noteEraserBtn').addEventListener('click', () => setNoteTool('eraser'));
  [
    { tool: 'pen', inputId: 'notePenSize', outputId: 'notePenSizeValue' },
    { tool: 'eraser', inputId: 'noteEraserSize', outputId: 'noteEraserSizeValue' },
  ].forEach(({ tool, inputId, outputId }) => {
    const input = document.getElementById(inputId);
    const output = document.getElementById(outputId);
    if (!input) return;
    const updateSize = () => {
      const size = Number(input.value);
      state.noteToolSizes[tool] = size;
      if (output) output.value = String(size);
    };
    input.addEventListener('input', updateSize);
    updateSize();
  });
  document.getElementById('noteUndoBtn').addEventListener('click', () => {
    state.noteDrawing.strokes.pop();
    markQuestionNoteDirty();
    redrawNoteCanvas();
  });
  document.getElementById('noteClearDrawingBtn').addEventListener('click', () => {
    state.noteDrawing = { version: 1, strokes: [] };
    markQuestionNoteDirty();
    redrawNoteCanvas();
  });

  let activeStroke = null;
  let activeInputId = null;

  const beginStroke = (clientX, clientY, inputId) => {
    if (activeStroke) return;
    const point = noteCanvasPointFromClient(clientX, clientY);
    activeStroke = {
      tool: state.noteTool,
      color: document.getElementById('noteColor').value,
      size: state.noteToolSizes[state.noteTool],
      points: [point],
    };
    activeInputId = inputId;
    state.noteDrawing.strokes.push(activeStroke);
    canvas.dataset.strokeCount = String(state.noteDrawing.strokes.length);
    redrawNoteCanvas();
  };

  const extendStroke = (clientX, clientY, inputId) => {
    if (!activeStroke || inputId !== activeInputId) return;
    const point = noteCanvasPointFromClient(clientX, clientY);
    const previous = activeStroke.points[activeStroke.points.length - 1];
    if (Math.hypot(point.x - previous.x, point.y - previous.y) < .002) return;
    activeStroke.points.push(point);
    redrawNoteCanvas();
  };

  const finishStroke = inputId => {
    if (!activeStroke || (inputId !== undefined && inputId !== activeInputId)) return;
    activeStroke = null;
    activeInputId = null;
    canvas.dataset.strokeCount = String(state.noteDrawing.strokes.length);
    markQuestionNoteDirty();
  };

  if ('PointerEvent' in window) {
    canvas.addEventListener('pointerdown', event => {
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      event.preventDefault();
      event.stopPropagation();
      beginStroke(event.clientX, event.clientY, event.pointerId);
      try {
        canvas.setPointerCapture(event.pointerId);
      } catch (_) {
        // Some iPad/iPhone webviews expose PointerEvent but not pointer capture.
      }
    }, { passive: false });

    const movePointerStroke = event => {
      if (!activeStroke || event.pointerId !== activeInputId) return;
      if (event.cancelable) event.preventDefault();
      const samples = typeof event.getCoalescedEvents === 'function'
        ? event.getCoalescedEvents()
        : [event];
      samples.forEach(sample => {
        extendStroke(sample.clientX, sample.clientY, event.pointerId);
      });
    };
    canvas.addEventListener('pointermove', movePointerStroke, { passive: false });
    window.addEventListener('pointermove', movePointerStroke, { passive: false });

    const endPointerStroke = event => {
      if (event.pointerId !== activeInputId) return;
      try {
        if (canvas.hasPointerCapture(event.pointerId)) {
          canvas.releasePointerCapture(event.pointerId);
        }
      } catch (_) {}
      finishStroke(event.pointerId);
    };
    canvas.addEventListener('pointerup', endPointerStroke);
    canvas.addEventListener('pointercancel', endPointerStroke);
    window.addEventListener('pointerup', endPointerStroke);
    window.addEventListener('pointercancel', endPointerStroke);
  } else {
    // Compatibility path for older iOS/Android webviews without PointerEvent.
    canvas.addEventListener('touchstart', event => {
      const touch = event.changedTouches[0];
      if (!touch) return;
      event.preventDefault();
      event.stopPropagation();
      beginStroke(touch.clientX, touch.clientY, touch.identifier);
    }, { passive: false });
    canvas.addEventListener('touchmove', event => {
      const touch = Array.from(event.changedTouches).find(item => item.identifier === activeInputId);
      if (!touch) return;
      event.preventDefault();
      extendStroke(touch.clientX, touch.clientY, touch.identifier);
    }, { passive: false });
    const endTouchStroke = event => {
      const touch = Array.from(event.changedTouches).find(item => item.identifier === activeInputId);
      if (!touch) return;
      event.preventDefault();
      finishStroke(touch.identifier);
    };
    canvas.addEventListener('touchend', endTouchStroke, { passive: false });
    canvas.addEventListener('touchcancel', endTouchStroke, { passive: false });

    canvas.addEventListener('mousedown', event => {
      if (event.button !== 0) return;
      event.preventDefault();
      beginStroke(event.clientX, event.clientY, 'mouse');
    });
    window.addEventListener('mousemove', event => {
      if (activeInputId !== 'mouse') return;
      event.preventDefault();
      extendStroke(event.clientX, event.clientY, 'mouse');
    });
    window.addEventListener('mouseup', () => finishStroke('mouse'));
  }
  window.addEventListener('resize', () => {
    const panel = document.getElementById('questionNotePanel');
    if (panel && panel.classList.contains('is-open')) {
      positionQuestionNotePanel(panel);
      resizeNoteCanvas();
    }
  });
  document.addEventListener('keydown', event => {
    const panel = document.getElementById('questionNotePanel');
    if (event.key !== 'Escape' || !panel.classList.contains('is-open')) return;
    event.stopPropagation();
    if (panel.classList.contains('is-fullscreen')) toggleQuestionNoteFullscreen();
    else closeQuestionNote(true);
  });
}

function setNoteTool(tool) {
  state.noteTool = tool;
  document.getElementById('notePenBtn').classList.toggle('active', tool === 'pen');
  document.getElementById('noteEraserBtn').classList.toggle('active', tool === 'eraser');
}

function openQuestionNote() {
  const panel = document.getElementById('questionNotePanel');
  positionQuestionNotePanel(panel);
  panel.classList.add('is-open');
  panel.setAttribute('aria-hidden', 'false');
  document.body.classList.add('note-panel-open');
  requestAnimationFrame(() => requestAnimationFrame(resizeNoteCanvas));
  if (window.matchMedia('(pointer: fine)').matches) {
    document.getElementById('questionNoteText').focus();
  } else {
    document.getElementById('questionNoteText').blur();
  }
}

function closeQuestionNote(saveChanges) {
  const panel = document.getElementById('questionNotePanel');
  if (!panel) return;
  if (saveChanges && state.noteDirty) saveCurrentQuestionNote({ silent: true });
  panel.classList.remove('is-open', 'is-fullscreen');
  panel.setAttribute('aria-hidden', 'true');
  document.body.classList.remove('note-fullscreen-open', 'note-panel-open');
  const fullBtn = document.getElementById('noteFullscreenBtn');
  if (fullBtn) fullBtn.textContent = '⛶ 全屏';
  restoreQuestionNotePanel(panel);
}

function positionQuestionNotePanel(panel) {
  const useTabletWorkspace = window.matchMedia('(min-width: 701px) and (max-width: 1180px)').matches;
  if (useTabletWorkspace && panel.parentElement !== document.body) {
    panel._noteHomeParent = panel.parentElement;
    panel._noteHomeNextSibling = panel.nextSibling;
    document.body.appendChild(panel);
  } else if (!useTabletWorkspace) {
    restoreQuestionNotePanel(panel);
  }
}

function restoreQuestionNotePanel(panel) {
  const parent = panel?._noteHomeParent;
  if (!parent) return;
  const nextSibling = panel._noteHomeNextSibling;
  if (nextSibling && nextSibling.parentElement === parent) parent.insertBefore(panel, nextSibling);
  else parent.appendChild(panel);
  panel._noteHomeParent = null;
  panel._noteHomeNextSibling = null;
}

function toggleQuestionNoteFullscreen() {
  const panel = document.getElementById('questionNotePanel');
  const isFull = panel.classList.toggle('is-fullscreen');
  document.body.classList.toggle('note-fullscreen-open', isFull);
  document.getElementById('noteFullscreenBtn').textContent = isFull ? '退出全屏' : '⛶ 全屏';
  setTimeout(resizeNoteCanvas, 30);
}

async function loadQuestionNote(questionId) {
  state.noteDrawing = { version: 1, strokes: [] };
  state.noteDirty = false;
  document.getElementById('questionNoteText').value = '';
  setNoteSaveStatus('正在读取笔记…');
  document.getElementById('openNoteBtn').classList.remove('has-note');
  try {
    const response = await fetch('/question-bank/' + encodeURIComponent(questionId) + '/note');
    if (!response.ok) throw new Error('笔记读取失败');
    const note = await response.json();
    if (!state.currentQuestion || state.currentQuestion.id !== questionId) return;
    document.getElementById('questionNoteText').value = note.text || '';
    state.noteDrawing = note.drawing && Array.isArray(note.drawing.strokes)
      ? note.drawing
      : { version: 1, strokes: [] };
    const draft = window.KaoyanRuntime.readNoteDraft(questionId);
    const serverTime = Date.parse(note.updated_at || '') || 0;
    if (draft && Number(draft.savedAt || 0) > serverTime) {
      document.getElementById('questionNoteText').value = draft.text || '';
      state.noteDrawing = draft.drawing && Array.isArray(draft.drawing.strokes)
        ? draft.drawing
        : state.noteDrawing;
      state.noteDirty = true;
      setNoteSaveStatus('已恢复本机未同步草稿');
    }
    const hasNote = Boolean((note.text || '').trim() || state.noteDrawing.strokes.length);
    document.getElementById('openNoteBtn').classList.toggle('has-note', hasNote);
    setNoteSaveStatus(note.updated_at ? '上次保存：' + formatNoteTime(note.updated_at) : '与当前题目绑定');
    redrawNoteCanvas();
  } catch (error) {
    console.warn('读取题目笔记失败', error);
    setNoteSaveStatus('暂时无法读取，可继续编辑');
  }
}

async function saveCurrentQuestionNote(options) {
  const question = state.currentQuestion;
  if (!question) return false;
  const questionId = question.id;
  const payload = {
    text: document.getElementById('questionNoteText').value,
    drawing: window.KaoyanRuntime.compactDrawing(state.noteDrawing),
  };
  state.noteDrawing = payload.drawing;
  window.KaoyanRuntime.saveNoteDraft(questionId, payload);
  setNoteSaveStatus('正在保存…');
  try {
    const response = await fetch('/question-bank/' + encodeURIComponent(questionId) + '/note', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.detail || '保存失败');
    state.noteDirty = false;
    window.KaoyanRuntime.clearNoteDraft(questionId);
    const hasNote = Boolean(payload.text.trim() || state.noteDrawing.strokes.length);
    document.getElementById('openNoteBtn').classList.toggle('has-note', hasNote);
    setNoteSaveStatus('已保存 · ' + formatNoteTime(data.note && data.note.updated_at));
    return true;
  } catch (error) {
    console.warn('保存题目笔记失败', error);
    window.KaoyanRuntime.queueMutation({
      key: 'question-note:' + questionId,
      url: '/question-bank/' + encodeURIComponent(questionId) + '/note',
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    state.noteDirty = false;
    setNoteSaveStatus('已保存到本机，联网后自动同步');
    return true;
  }
}

async function deleteCurrentQuestionNote() {
  const question = state.currentQuestion;
  if (!question || !confirm('确定擦除这道题的全部文字和手写笔记吗？')) return;
  try {
    const response = await fetch('/question-bank/' + encodeURIComponent(question.id) + '/note', {
      method: 'DELETE',
    });
    if (!response.ok) throw new Error('擦除失败');
    document.getElementById('questionNoteText').value = '';
    state.noteDrawing = { version: 1, strokes: [] };
    state.noteDirty = false;
    document.getElementById('openNoteBtn').classList.remove('has-note');
    redrawNoteCanvas();
    setNoteSaveStatus('笔记已擦除');
  } catch (error) {
    alert(error.message || '笔记擦除失败');
  }
}

function markQuestionNoteDirty() {
  state.noteDirty = true;
  const question = state.currentQuestion;
  if (question) {
    window.KaoyanRuntime.saveNoteDraft(question.id, {
      text: document.getElementById('questionNoteText').value,
      drawing: window.KaoyanRuntime.compactDrawing(state.noteDrawing)
    });
  }
  setNoteSaveStatus('正在自动保存…');
  scheduleQuestionNoteAutosave();
}

function setNoteSaveStatus(text) {
  const el = document.getElementById('noteSaveStatus');
  if (el) el.textContent = text;
}

function formatNoteTime(value) {
  if (!value) return '刚刚';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '刚刚';
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function noteCanvasPointFromClient(clientX, clientY) {
  const rect = document.getElementById('questionNoteCanvas').getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (clientX - rect.left) / Math.max(rect.width, 1))),
    y: Math.max(0, Math.min(1, (clientY - rect.top) / Math.max(rect.height, 1))),
  };
}

function resizeNoteCanvas() {
  const canvas = document.getElementById('questionNoteCanvas');
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  if (!rect.width || !rect.height) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  canvas.width = Math.round(rect.width * ratio);
  canvas.height = Math.round(rect.height * ratio);
  redrawNoteCanvas();
}

function redrawNoteCanvas() {
  const canvas = document.getElementById('questionNoteCanvas');
  if (!canvas || !canvas.width || !canvas.height) return;
  const context = canvas.getContext('2d');
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const width = canvas.width / ratio;
  const height = canvas.height / ratio;
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  context.clearRect(0, 0, width, height);
  (state.noteDrawing.strokes || []).forEach(stroke => {
    const points = stroke.points || [];
    if (!points.length) return;
    context.save();
    context.globalCompositeOperation = stroke.tool === 'eraser' ? 'destination-out' : 'source-over';
    context.strokeStyle = stroke.color || '#172554';
    context.fillStyle = stroke.color || '#172554';
    context.lineWidth = Number(stroke.size || 4);
    context.lineCap = 'round';
    context.lineJoin = 'round';
    if (points.length === 1) {
      context.beginPath();
      context.arc(points[0].x * width, points[0].y * height, context.lineWidth / 2, 0, Math.PI * 2);
      context.fill();
    } else {
      context.beginPath();
      context.moveTo(points[0].x * width, points[0].y * height);
      points.slice(1).forEach(point => context.lineTo(point.x * width, point.y * height));
      context.stroke();
    }
    context.restore();
  });
}

// 显示答案
async function showAnswer() {
  const question = state.currentQuestion;
  
  // 如果还没有答案，尝试生成
  if (!question.answer || !question.answer.trim()) {
    document.getElementById('showAnswerBtn').style.display = 'none';
    document.getElementById('qaSplitLayout').classList.remove('hidden');
    document.getElementById('answerContent').innerHTML = '<p style="text-align:center;color:var(--text-secondary);">⏳ 正在生成答案和解析，请稍候...</p>';
    
    try {
      const response = await fetch('/question-bank/generate-answer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question_id: question.id, subject: question.subject, content: question.content, options: question.options, type: question.type })
      });
      const data = await response.json();
      if (data.answer) {
        question.answer = data.answer;
        question.explanation = data.explanation || '';
      }
    } catch (error) {
      console.error('生成答案失败:', error);
      document.getElementById('answerContent').innerHTML = `
        <h3>参考答案</h3>
        <p>答案生成失败，请稍后重试。</p>
        <h3>题目解析</h3>
        <p>题目来源：${question.source || '未知'}</p>
      `;
      return;
    }
  }
  
  document.getElementById('qaSplitLayout').classList.remove('hidden');
  document.getElementById('showAnswerBtn').style.display = 'none';
  renderAnswerContent();
}

function renderAnswerContent() {
  const contentDiv = document.getElementById('answerContent');
  const question = state.currentQuestion;
  
  if (!question) return;
  
  if (state.activeAnswerTab === 'visualization') {
    renderQuestionVisualization(question);
  } else if (state.activeAnswerTab === 'answer') {
    const answerText = question.answer || '暂无参考答案';
    const normalizedAnswer = normalizeAnswerLetters(answerText);
    const answerLabel = isChoiceQuestion(question) && normalizedAnswer
      ? `选项 ${normalizedAnswer.split('').join('、')}`
      : answerText;
    
    contentDiv.innerHTML = `
      <h3>参考答案</h3>
      <p class="answer-latex" style="font-size:1.125rem;font-weight:700;color:var(--secondary);"></p>
    `;
    window.KaoyanRuntime.renderMathText(contentDiv.querySelector('.answer-latex'), answerLabel);
    
    if (isChoiceQuestion(question) && normalizedAnswer) {
      const correctOptions = question.options.filter(opt => normalizedAnswer.includes(opt.trim().charAt(0)));
      if (correctOptions.length) {
        const option = document.createElement('p');
        option.style.color = 'var(--text-secondary)';
        contentDiv.appendChild(option);
        window.KaoyanRuntime.renderMathText(option, correctOptions.join('\n'));
      }
    }
  } else {
    contentDiv.innerHTML = `
      <h3>题目解析</h3>
      <div class="question-explanation markdown-body" style="line-height:1.8;"></div>
    `;
    _renderMarkdownInto(
      contentDiv.querySelector('.question-explanation'),
      question.explanation || '暂无解析'
    );
  }
}

async function renderQuestionVisualization(question) {
  const contentDiv = document.getElementById('answerContent');
  if (!question?.visualization?.available) {
    state.activeAnswerTab = 'explanation';
    document.querySelectorAll('.answer-tab').forEach(tab => tab.classList.toggle('active', tab.dataset.tab === 'explanation'));
    renderAnswerContent();
    return;
  }

  const normalizedCorrect = normalizeAnswerLetters(question.answer);
  const wrongOption = state.answerSubmitted && state.selectedOption !== normalizedCorrect ? state.selectedOption : '';
  const cacheKey = `${question.id}:${wrongOption || 'default'}`;
  let spec = state.visualizationCache[cacheKey];
  if (!spec) {
    contentDiv.innerHTML = '<div class="question-visual-loading"><span></span>正在搭建本题图示…</div>';
    try {
      const focusQuery = wrongOption ? `?selected_option=${encodeURIComponent(wrongOption)}` : '';
      const response = await fetch(`/question-bank/${encodeURIComponent(question.id)}/visualization${focusQuery}`);
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || '可视化加载失败');
      state.visualizationCache[cacheKey] = data;
      spec = data;
    } catch (error) {
      contentDiv.innerHTML = `<div class="question-visual-error">${escapeHtml(error.message || '可视化加载失败，请稍后重试')}</div>`;
      return;
    }
  }
  if (state.currentQuestion?.id !== question.id || state.activeAnswerTab !== 'visualization') return;
  paintQuestionVisualization(spec);
}

function visualizationStageMarkup(spec, stepIndex) {
  if (spec.simulation) return simulationStageMarkup(spec.simulation, stepIndex);
  return walkthroughStageMarkup(spec, stepIndex);
}

function createStepPlayer(container, snapshots, renderSnapshot, options = {}) {
  if (!container) return null;
  const steps = Array.isArray(snapshots) && snapshots.length ? snapshots : [{ desc: '暂无步骤' }];
  let current = Math.max(0, Math.min(Number(options.initialStep) || 0, steps.length - 1));
  let timer = null;
  let speed = Number(options.speed) || 1000;
  const label = escapeHtml(options.label || '过程演示');
  container.innerHTML = `
    <div class="step-player" tabindex="0" aria-label="${label}">
      <div class="step-player-stage" data-step-stage></div>
      <div class="step-player-caption" aria-live="polite"><span data-step-number></span><p data-step-desc></p></div>
      <label class="step-player-progress"><span class="sr-only">选择步骤</span><input type="range" min="0" max="${steps.length - 1}" value="${current}" step="1" data-step-progress></label>
      <div class="step-player-controls">
        <button type="button" data-step-action="prev">← 上一步</button>
        <button type="button" class="primary" data-step-action="play" aria-pressed="false">▶ 播放</button>
        <button type="button" data-step-action="next">下一步 →</button>
        <label class="step-player-speed">速度<select data-step-speed aria-label="播放速度"><option value="1600">慢速</option><option value="1000" selected>正常</option><option value="550">快速</option></select></label>
      </div>
    </div>`;
  const root = container.querySelector('.step-player');
  const stage = root.querySelector('[data-step-stage]');
  const number = root.querySelector('[data-step-number]');
  const desc = root.querySelector('[data-step-desc]');
  const range = root.querySelector('[data-step-progress]');
  const playButton = root.querySelector('[data-step-action="play"]');

  function stop() {
    if (timer) window.clearTimeout(timer);
    timer = null;
    playButton.textContent = '▶ 播放';
    playButton.setAttribute('aria-pressed', 'false');
  }

  function render() {
    const snapshot = steps[current] || {};
    stage.innerHTML = renderSnapshot(snapshot, current, steps) || '';
    number.textContent = `步骤 ${current + 1} / ${steps.length}`;
    desc.textContent = snapshot.desc || snapshot.description || snapshot.title || '观察当前状态变化。';
    range.value = String(current);
    root.querySelector('[data-step-action="prev"]').disabled = current === 0;
    root.querySelector('[data-step-action="next"]').disabled = current >= steps.length - 1;
    if (typeof options.onStep === 'function') options.onStep(current, snapshot);
  }

  function move(next) {
    current = Math.max(0, Math.min(next, steps.length - 1));
    render();
  }

  function tick() {
    if (!timer) return;
    if (current >= steps.length - 1) { stop(); return; }
    move(current + 1);
    timer = window.setTimeout(tick, speed);
  }

  root.addEventListener('click', event => {
    const action = event.target.closest('[data-step-action]')?.dataset.stepAction;
    if (!action) return;
    if (action === 'prev') { stop(); move(current - 1); }
    if (action === 'next') { stop(); move(current + 1); }
    if (action === 'play') {
      if (timer) { stop(); return; }
      if (current >= steps.length - 1) move(0);
      playButton.textContent = '⏸ 暂停';
      playButton.setAttribute('aria-pressed', 'true');
      timer = window.setTimeout(tick, speed);
    }
  });
  range.addEventListener('input', () => { stop(); move(Number(range.value)); });
  root.querySelector('[data-step-speed]').addEventListener('change', event => {
    speed = Number(event.target.value) || 1000;
    if (timer) { window.clearTimeout(timer); timer = window.setTimeout(tick, speed); }
  });
  root.addEventListener('keydown', event => {
    if (event.target.matches('input,select,button')) return;
    if (event.key === 'ArrowLeft') { event.preventDefault(); stop(); move(current - 1); }
    if (event.key === 'ArrowRight') { event.preventDefault(); stop(); move(current + 1); }
    if (event.key === ' ') { event.preventDefault(); playButton.click(); }
  });
  render();
  return { destroy: stop, goTo: move, getStep: () => current };
}

function walkthroughStageMarkup(spec, stepIndex) {
  const steps = spec.steps || [];
  return `<div class="visual-walkthrough-map">${steps.map((step, index) => `
    <button type="button" class="visual-walkthrough-card ${index === stepIndex ? 'active' : ''} ${index < stepIndex ? 'visited' : ''}" data-visual-step="${index}">
      <span>${String(index + 1).padStart(2, '0')}</span>
      <p>${escapeHtml(step)}</p>
    </button>`).join('')}</div>`;
}

function simulationStageMarkup(simulation, stepIndex) {
  const stateItem = (simulation.states || [])[stepIndex] || {};
  if (simulation.kind === 'linked_list_head') {
    const withoutHead = stateItem.variant === 'without_head';
    const uniformOperation = stateItem.variant === 'uniform_operation';
    return `<div class="visual-list-lab">
      <div class="visual-list-condition"><b>${withoutHead ? '不带头结点' : uniformOperation ? '统一执行首部插入' : '带头结点'}</b><span>${withoutHead ? '空表：head = NULL' : '空表：HEAD.next = NULL'}</span></div>
      <div class="visual-list-lane" aria-label="${withoutHead ? 'head 直接指向首元结点' : 'head 指向头结点，头结点再指向首元结点'}">
        <i>head</i><em>→</em>
        ${withoutHead ? '' : '<span class="sentinel"><small>头结点</small><b>HEAD</b></span><em>→</em>'}
        ${uniformOperation ? '<span class="active"><small>新结点</small><b>X</b></span><em>→</em>' : ''}
        <span><small>首元结点</small><b>A</b></span><em>→</em><span><small>数据结点</small><b>B</b></span><em>→ NULL</em>
      </div>
      <div class="visual-list-boundary ${withoutHead ? 'warning' : 'success'}">${withoutHead ? '首部插入/删除会改变 head，需要单独判断空表和首结点。' : uniformOperation ? '令 p=HEAD 后，插入仍是 X.next=p.next；p.next=X，无需首部特判。' : 'head 始终稳定；空表、非空表都从 HEAD.next 开始处理。'}</div>
      <div class="visual-sim-result"><span>结论</span><b>${escapeHtml(simulation.result)}</b></div>
    </div>`;
  }
  if (simulation.kind === 'sorting') {
    const maxValue = Math.max(...simulation.original.map(value => Math.abs(value)), 1);
    return `<div class="visual-sort-lab">
      <div class="visual-sort-array">${stateItem.values.map((value, index) => `
        <div class="visual-sort-column ${stateItem.active.includes(index) ? 'active' : ''} ${stateItem.sorted.includes(index) ? 'sorted' : ''}">
          <span style="height:${Math.max(18, Math.abs(value) / maxValue * 112)}px"></span><b>${escapeHtml(value)}</b><small>${index}</small>
        </div>`).join('')}</div>
      <div class="visual-sim-result"><span>算法</span><b>${escapeHtml(simulation.algorithm.toUpperCase())}</b><span>当前序列</span><b>${stateItem.values.map(escapeHtml).join('，')}</b></div>
    </div>`;
  }
  if (simulation.kind === 'page_replacement') {
    return `<div class="visual-page-lab">
      <div class="visual-reference-strip">${simulation.references.map((page, index) => `<span class="${index === stepIndex ? 'active' : ''} ${index < stepIndex ? 'visited' : ''}">${escapeHtml(page)}</span>`).join('')}</div>
      <div class="visual-frame-stack">${stateItem.frames.map((page, index) => `<div><small>页框 ${index + 1}</small><b>${page === null ? '空' : escapeHtml(page)}</b></div>`).join('')}</div>
      <div class="visual-sim-result"><span>本次</span><b class="${stateItem.hit ? 'is-hit' : 'is-fault'}">${stateItem.hit ? '命中' : '缺页'}</b><span>累计缺页</span><b>${stateItem.faults}</b>${stateItem.evicted !== null && stateItem.evicted !== undefined ? `<span>淘汰</span><b>${escapeHtml(stateItem.evicted)}</b>` : ''}</div>
    </div>`;
  }
  if (simulation.kind === 'pipeline') {
    const maxCycle = Math.min(simulation.stages.length + Math.min(simulation.instruction_count, 6) - 1, 10);
    return `<div class="visual-pipeline-lab">
      <div class="visual-pipeline-summary"><div class="${stateItem.focus === 'cycle' ? 'active' : ''}"><small>流水周期</small><b>${escapeHtml(simulation.cycle)} ns</b></div><div class="${stateItem.focus === 'latency' ? 'active' : ''}"><small>首条延迟</small><b>${escapeHtml(simulation.first_latency)} ns</b></div><div class="${stateItem.focus === 'total' ? 'active' : ''}"><small>${escapeHtml(simulation.instruction_count)} 条总耗时</small><b>${escapeHtml(simulation.total)} ns</b></div></div>
      <div class="visual-pipeline-grid" style="--cycles:${maxCycle}">${simulation.rows.map(row => `<div class="visual-pipeline-row"><b>I${row.instruction}</b>${Array.from({length:maxCycle},(_,cycle) => { const cell=row.cells.find(item=>item.cycle===cycle); return `<span class="${cell ? 'filled' : ''}">${cell ? escapeHtml(cell.stage) : ''}</span>`; }).join('')}</div>`).join('')}</div>
    </div>`;
  }
  if (simulation.kind === 'subnet') {
    const candidate = simulation.candidates[stateItem.candidate_index] || simulation.candidates[0];
    const bits = candidate.bits || [];
    let consumed = 0;
    return `<div class="visual-subnet-lab">
      <div class="visual-ip-candidates">${simulation.candidates.map((item, index) => `<span class="${index === stateItem.candidate_index ? 'active' : ''} ${item.valid ? 'valid' : 'invalid'}">${escapeHtml(item.label || index + 1)} · ${escapeHtml(item.ip)}</span>`).join('')}</div>
      ${bits.length ? `<div class="visual-binary-address">${bits.map(octet => { const start=consumed; consumed+=8; const networkBits=Math.max(0,Math.min(8,(candidate.prefix || 0)-start)); return `<div><b>${escapeHtml(octet.slice(0,networkBits))}</b><em>${escapeHtml(octet.slice(networkBits))}</em><small>${parseInt(octet,2)}</small></div>`; }).join('')}</div>` : '<div class="visual-invalid-ip">该地址无法形成合法的 32 位 IP 字段</div>'}
      <div class="visual-sim-result"><span>前缀</span><b>${candidate.prefix !== undefined ? `/${candidate.prefix}` : '—'}</b><span>网络地址</span><b>${escapeHtml(candidate.network || '—')}</b><span>判断</span><b class="${candidate.valid ? 'is-hit' : 'is-fault'}">${candidate.valid ? '可分配' : '不可分配'}</b></div>
    </div>`;
  }
  return '<div class="question-visual-error">该演算类型暂不支持展示。</div>';
}

function paintQuestionVisualization(spec) {
  const contentDiv = document.getElementById('answerContent');
  const steps = spec.steps || [];
  const focusedStep = Number(spec.error_focus?.step);
  const initialStep = Number.isFinite(focusedStep) ? focusedStep : state.visualizationStep;
  const stepIndex = Math.max(0, Math.min(initialStep, steps.length - 1));
  state.visualizationStep = stepIndex;
  state.visualizationPlayer?.destroy();
  contentDiv.innerHTML = `
    <section class="question-visualization" aria-label="${escapeHtml(spec.title)}">
      <header class="question-visual-head">
        <div><span>${escapeHtml(spec.subject)} · ${escapeHtml(spec.mode_label || '过程演示')}</span><h3>${escapeHtml(spec.title)}</h3></div>
        <strong>快照演示</strong>
      </header>
      ${spec.error_focus ? `<aside class="question-visual-error-focus"><b>已定位到疑似出错步骤</b><span>${escapeHtml(spec.error_focus.reason)}</span></aside>` : ''}
      <div data-question-step-player></div>
      ${spec.mode === 'walkthrough' ? `
        <details class="question-visual-full" open>
          <summary>完整题目解析</summary>
          <div class="question-visual-full-content markdown-body"></div>
        </details>` : ''}
      <p class="question-visual-notice">${escapeHtml(spec.notice || '')}</p>
    </section>`;
  const fullExplanation = contentDiv.querySelector('.question-visual-full-content');
  if (fullExplanation) {
    _renderMarkdownInto(fullExplanation, spec.full_explanation || steps.join('\n\n'));
  }
  const snapshots = steps.map((desc, index) => ({ desc, index }));
  state.visualizationPlayer = createStepPlayer(
    contentDiv.querySelector('[data-question-step-player]'),
    snapshots,
    (_, index) => `<div class="question-visual-stage">${visualizationStageMarkup(spec, index)}</div>`,
    { label: spec.title, initialStep: stepIndex, onStep: index => { state.visualizationStep = index; } }
  );
}

// 聊天功能(支持 SSE 流式响应)
async function sendMessage() {
  const input = document.getElementById('messageInput');
  const text = input.value.trim();
  if (!text) return;
  if (state.chatStreaming) return; // 锁住,防双击

  // 隐藏欢迎卡片(一旦开始对话)
  const wg = document.getElementById('welcomeGrid');
  if (wg) wg.style.display = 'none';

  addMessage(text, 'user');
  input.value = '';
  _autoresizeTextarea(input);
  _updateCharCount();

  // 创建 AI 消息外壳(头像+meta+空气泡)
  const shell = _createAssistantShell();
  const messagesDiv = document.getElementById('chatMessages');
  messagesDiv.appendChild(shell.wrapper);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;

  // 占位打字指示
  shell.content.innerHTML = '<span class="typing-indicator"><span></span><span></span><span></span></span>';

  // 锁定发送按钮
  const sendBtn = document.getElementById('sendBtn');
  if (sendBtn) sendBtn.disabled = true;
  state.chatStreaming = true;

  let fullText = '';
  let agentProgress = '';

  try {
    // 尝试 SSE 流式接口
    const response = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_id: 'default', message: text }),
    });
    if (!response.ok) throw new Error('HTTP ' + response.status);

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let sseBuffer = '';
    let renderPending = false;
    const scheduleStreamRender = () => {
      if (renderPending) return;
      renderPending = true;
      requestAnimationFrame(() => {
        renderPending = false;
        _renderMarkdownInto(shell.content, fullText);
        messagesDiv.scrollTop = messagesDiv.scrollHeight;
      });
    };
    shell.content.textContent = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      sseBuffer += decoder.decode(value, { stream: true });
      const lines = sseBuffer.split('\n');
      sseBuffer = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = line.slice(6).trim();
        if (data === '[DONE]') continue;

        try {
          const parsed = JSON.parse(data);
          if (parsed.type === 'chunk') {
            fullText += parsed.content;
            scheduleStreamRender();
          } else if (parsed.type === 'preparing') {
            agentProgress = parsed.content || '正在读取上下文并匹配相关资料';
            if (!fullText) shell.content.textContent = `${agentProgress}…`;
          } else if (parsed.type === 'plan_created') {
            const count = Array.isArray(parsed.plan) ? parsed.plan.length : 0;
            agentProgress = `正在规划 ${count || ''} 个执行步骤…`;
            if (!fullText) shell.content.textContent = agentProgress;
          } else if (parsed.type === 'tool_started') {
            const toolLabels = {
              get_learning_state: '正在读取学习画像',
              get_review_queue: '正在计算复习优先级',
              create_study_plan: '正在生成可执行学习计划',
              search_questions: '正在检索题库',
              search_knowledge: '正在检索知识库',
            };
            agentProgress = toolLabels[parsed.tool] || '正在调用专业辅导能力';
            if (!fullText) shell.content.textContent = `${agentProgress}…`;
          } else if (parsed.type === 'replan') {
            agentProgress = '正在校验并修正结果';
            if (!fullText) shell.content.textContent = `${agentProgress}…`;
          } else if (parsed.type === 'validated') {
            const confidence = Number(parsed.confidence || 0);
            if (!fullText && confidence > 0) {
              shell.content.textContent = `结果校验完成（置信度 ${Math.round(confidence * 100)}%）…`;
            }
          } else if (parsed.type === 'error') {
            if (!fullText) shell.content.textContent = parsed.content || '生成失败';
          } else if (parsed.type === 'done') {
            fullText = parsed.content || fullText;
            renderPending = false;
            _renderMarkdownInto(shell.content, fullText);
          }
        } catch (e) {
          // 忽略解析错误
        }
      }
    }

    if (!fullText) {
      shell.content.textContent = '抱歉,未收到任何回复内容。';
    }
  } catch (error) {
    console.error('发送消息失败:', error);
    // 回退到普通接口
    try {
      const fallbackResp = await fetch('/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'default', message: text })
      });
      const data = await fallbackResp.json();
      const reply = data.answer || data.message || '抱歉,我无法回答这个问题';
      _renderMarkdownInto(shell.content, reply);
    } catch (e2) {
      shell.content.textContent = '抱歉,服务器出现错误';
    }
  } finally {
    if (sendBtn) sendBtn.disabled = false;
    state.chatStreaming = false;
  }
}

// 创建 AI 消息外壳(流式生成用),返回 wrapper/content 引用
function _createAssistantShell() {
  const wrapper = document.createElement('div');
  wrapper.className = 'message assistant';

  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  avatar.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>';

  const body = document.createElement('div');
  body.className = 'message-body';

  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const name = document.createElement('span');
  name.className = 'message-name';
  name.textContent = '考研 AI 助手';
  const time = document.createElement('span');
  time.className = 'message-time';
  time.textContent = _fmtTime(new Date());
  meta.appendChild(name);
  meta.appendChild(time);

  const content = document.createElement('div');
  content.className = 'message-content';

  const actions = document.createElement('div');
  actions.className = 'message-actions';
  const copyBtn = _mkActionBtn('copy', '复制', '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>');
  copyBtn.addEventListener('click', () => {
    navigator.clipboard?.writeText(content.textContent || '').then(() => {
      copyBtn.classList.add('copied');
      setTimeout(() => copyBtn.classList.remove('copied'), 1200);
    });
  });
  const delBtn = _mkActionBtn('delete', '删除', '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>');
  delBtn.addEventListener('click', () => wrapper.remove());
  actions.appendChild(copyBtn);
  actions.appendChild(delBtn);

  body.appendChild(meta);
  body.appendChild(content);
  body.appendChild(actions);

  wrapper.appendChild(avatar);
  wrapper.appendChild(body);
  return { wrapper, content, meta, actions };
}

function _autoresizeTextarea(ta) {
  if (!ta) return;
  ta.style.height = 'auto';
  ta.style.height = Math.min(ta.scrollHeight, 180) + 'px';
}

function _updateCharCount() {
  const ta = document.getElementById('messageInput');
  const cc = document.getElementById('charCount');
  if (!ta || !cc) return;
  const len = (ta.value || '').length;
  const max = parseInt(ta.maxLength || 4000, 10);
  cc.textContent = `${len} / ${max}`;
  cc.style.color = len > max * 0.9 ? '#ef4444' : '';
}

async function loadChatStatusBar() {
  // 拉今日刷题数、连续天数、本周计划进度
  try {
    const d = await loadActivityHeatmap();
    if (d) {
      const daily = d.daily || {};
      const today = new Date();
      const key = today.getFullYear() + '-' + String(today.getMonth() + 1).padStart(2, '0') + '-' + String(today.getDate()).padStart(2, '0');
      const el = document.getElementById('csbToday');
      if (el) el.textContent = daily[key] || 0;
    }
    if (d) {
      const daily = d.daily || {};
      let streak = 0;
      for (let i = 0; i < 30; i++) {
        const dt = new Date(); dt.setDate(dt.getDate() - i);
        const k = dt.getFullYear() + '-' + String(dt.getMonth() + 1).padStart(2, '0') + '-' + String(dt.getDate()).padStart(2, '0');
        if ((daily[k] || 0) > 0) streak++;
        else if (i === 0) continue;
        else break;
      }
      const el = document.getElementById('csbStreak');
      if (el) el.textContent = streak;
    }
    try {
      const r3 = await fetch('/daily-tasks/today');
      if (r3.ok) {
        const d = await r3.json();
        const el = document.getElementById('csbPlan');
        if (el) {
          const total = (d.tasks || []).length || (d.plan ? 1 : 0);
          const done = (d.tasks || []).filter(t => t.completed || t.done).length;
          el.textContent = total ? `${done}/${total}` : '—';
        }
      }
    } catch (e) { /* 静默 */ }
  } catch (e) {
    /* 静默 */
  }
}

function addMessage(text, role, msgId) {
  const messagesDiv = document.getElementById('chatMessages');
  const messageDiv = document.createElement('div');
  messageDiv.className = `message ${role}`;
  if (msgId) messageDiv.dataset.msgId = String(msgId);

  // 头像(AI 用 logo 图标,user 用首字母)
  const avatar = document.createElement('div');
  avatar.className = 'message-avatar';
  if (role === 'assistant') {
    avatar.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>';
  } else {
    avatar.textContent = '我';
  }

  // 消息体容器
  const body = document.createElement('div');
  body.className = 'message-body';

  // meta 行
  const meta = document.createElement('div');
  meta.className = 'message-meta';
  const name = document.createElement('span');
  name.className = 'message-name';
  name.textContent = role === 'assistant' ? '考研 AI 助手' : '我';
  const time = document.createElement('span');
  time.className = 'message-time';
  time.textContent = _fmtTime(new Date());
  meta.appendChild(name);
  meta.appendChild(time);

  // 内容气泡
  const content = document.createElement('div');
  content.className = 'message-content';
  if (role === 'user') {
    content.textContent = text;
  } else {
    _renderMarkdownInto(content, text || '');
  }

  // 操作按钮(只有带 msgId 的历史消息才挂删除;流式过程不挂;初始欢迎语有)
  const actions = document.createElement('div');
  actions.className = 'message-actions';
  const copyBtn = _mkActionBtn('copy', '复制', '<rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>');
  const delBtn = _mkActionBtn('delete', '删除', '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/>');
  copyBtn.addEventListener('click', () => {
    navigator.clipboard?.writeText(text || '').then(() => {
      copyBtn.classList.add('copied');
      setTimeout(() => copyBtn.classList.remove('copied'), 1200);
    });
  });
  if (msgId) {
    delBtn.addEventListener('click', () => deleteChatMessage(msgId, messageDiv));
  } else {
    // 流式/初始消息:删本地 DOM
    delBtn.addEventListener('click', () => messageDiv.remove());
  }
  actions.appendChild(copyBtn);
  actions.appendChild(delBtn);

  body.appendChild(meta);
  body.appendChild(content);
  body.appendChild(actions);

  messageDiv.appendChild(avatar);
  messageDiv.appendChild(body);
  messagesDiv.appendChild(messageDiv);
  messagesDiv.scrollTop = messagesDiv.scrollHeight;
  return messageDiv;
}

function _mkActionBtn(action, title, innerSvg) {
  const b = document.createElement('button');
  b.className = 'msg-action-btn';
  b.dataset.action = action;
  b.title = title;
  b.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${innerSvg}</svg>`;
  return b;
}

function _fmtTime(d) {
  const pad = n => String(n).padStart(2, '0');
  return `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function _renderMarkdownInto(el, text) {
  try { el.innerHTML = window.KaoyanRuntime.renderMarkdown(text || ''); }
  catch (e) { el.textContent = text || ''; }
  if (typeof marked === 'undefined') {
    if (el.dataset.markdownLoading !== 'true') {
      el.dataset.markdownLoading = 'true';
      window.KaoyanRuntime
        .loadScript('https://cdn.jsdelivr.net/npm/marked@15.0.12/marked.min.js', 'marked')
        .then(() => {
          delete el.dataset.markdownLoading;
          if (el.isConnected && window.marked) _renderMarkdownInto(el, text);
        })
        .catch(() => { delete el.dataset.markdownLoading; });
    }
  }
  window.KaoyanRuntime.renderMath(el);
  // 代码块高亮(可选)
  if (typeof hljs !== 'undefined') {
    el.querySelectorAll('pre code').forEach(b => { try { hljs.highlightElement(b); } catch(e) {} });
  }
}

async function deleteChatMessage(msgId, messageDiv) {
  if (!msgId) return;
  if (!confirm('确认删除这条消息?')) return;
  try {
    const r = await fetch('/chat/message/' + encodeURIComponent(msgId), { method: 'DELETE' });
    const data = await r.json().catch(() => ({}));
    if (data && data.success) {
      if (messageDiv) messageDiv.remove();
    } else {
      alert('删除失败:服务器未确认');
    }
  } catch (e) {
    console.error('删除消息失败', e);
    alert('删除失败:' + e);
  }
}

async function startNewChat() {
  if (!confirm('开始新对话将清空当前全部历史,确认?')) return;
  const wrap = document.getElementById('chatMessages');
  try {
    const r = await fetch('/chat/clear', { method: 'POST' });
    const data = await r.json().catch(() => ({}));
    if (data && data.success) {
      // 重置对话区,显示欢迎卡片 + 初始 AI 欢迎语
      if (wrap) {
        wrap.innerHTML = `
          <div class="welcome-grid" id="welcomeGrid">
            <div class="welcome-card" data-text="帮我按备考周期制定完整的 408 学习计划，结合我的题库和知识点安排每日任务。">
              <div class="wc-icon wc-icon-1">📅</div>
              <div class="wc-title">冲刺学习计划</div>
              <div class="wc-desc">按备考周期完整排程，可做题、可打卡</div>
            </div>
            <div class="welcome-card" data-text="出一道 2024 年计算机组成原理的选择题,并给出详细解析和踩分点。">
              <div class="wc-icon wc-icon-2">📝</div>
              <div class="wc-title">智能刷题</div>
              <div class="wc-desc">真题+详解+命题思路</div>
            </div>
            <div class="welcome-card" data-text="根据我近 30 天的错题,分析我的薄弱环节,给出针对性练习建议。">
              <div class="wc-icon wc-icon-3">🎯</div>
              <div class="wc-title">薄弱诊断</div>
              <div class="wc-desc">错因分析+巩固路径</div>
            </div>
            <div class="welcome-card" data-text="用知识图谱串一下「进程同步与互斥」这一章的高频考点。">
              <div class="wc-icon wc-icon-4">🧠</div>
              <div class="wc-title">知识点串联</div>
              <div class="wc-desc">章节考点+逻辑链</div>
            </div>
          </div>
          <div class="message assistant" data-msg-id="">
            <div class="message-avatar">
              <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2 2 7l10 5 10-5-10-5Z"/><path d="m2 17 10 5 10-5"/><path d="m2 12 10 5 10-5"/></svg>
            </div>
            <div class="message-body">
              <div class="message-meta">
                <span class="message-name">考研 AI 助手</span>
                <span class="message-time">刚刚</span>
              </div>
              <div class="message-content">
                <p>新对话已开始 ✨,我是你的 408 考研 AI 学习助手,有什么想问的?</p>
              </div>
              <div class="message-actions">
                <button class="msg-action-btn" data-action="copy" title="复制">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                </button>
                <button class="msg-action-btn" data-action="delete" title="删除">
                  <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
                </button>
              </div>
            </div>
          </div>
        `;
        // 重新挂载欢迎卡片点击
        wrap.querySelectorAll('.welcome-card').forEach(card => {
          card.addEventListener('click', () => {
            const ta = document.getElementById('messageInput');
            ta.value = card.dataset.text || '';
            ta.focus();
            _autoresizeTextarea(ta);
            _updateCharCount();
          });
        });
      }
    } else {
      alert('清空失败');
    }
  } catch (e) {
    console.error('新对话失败', e);
    alert('新对话失败:' + e);
  }
}

// 题目提问对话
async function sendQAChatMessage() {
  const input = document.getElementById('qaChatInput');
  const text = input.value.trim();
  if (!text || !state.currentQuestion) return;
  
  const question = state.currentQuestion;
  const conversationHistory = state.qaConversation.slice(-6);
  
  // 清除占位符
  const placeholder = document.querySelector('.qa-chat-placeholder');
  if (placeholder) placeholder.remove();
  
  // 添加用户消息
  addQAChatMessage(text, 'user');
  state.qaConversation.push({ role: 'user', content: text });
  input.value = '';
  
  // 添加等待消息
  const loadingId = 'qa-loading-msg';
  addQAChatMessage('思考中...', 'assistant', loadingId);
  
  try {
    const response = await fetch('/question-bank/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question_id: question.id,
        user_message: text,
        selected_option: state.selectedOption || '',
        conversation_history: conversationHistory
      })
    });
    
    const data = await response.json();
    
    // 移除加载消息
    const loadingMsg = document.getElementById(loadingId);
    if (loadingMsg) loadingMsg.remove();
    
    const reply = data.reply || '抱歉，我暂时无法回答这个问题。';
    addQAChatMessage(reply, 'assistant');
    state.qaConversation.push({ role: 'assistant', content: reply });
  } catch (error) {
    const loadingMsg = document.getElementById(loadingId);
    if (loadingMsg) loadingMsg.remove();
    addQAChatMessage('抱歉，网络错误，请稍后重试。', 'assistant');
    console.error('QA聊天请求失败:', error);
  }
}

function addQAChatMessage(text, role, id) {
  const container = document.getElementById('qaChatMessages');
  const msgDiv = document.createElement('div');
  msgDiv.className = `qa-chat-message qa-chat-${role}`;
  if (id) msgDiv.id = id;
  
  const avatar = document.createElement('div');
  avatar.className = `qa-chat-avatar qa-avatar-${role}`;
  avatar.textContent = role === 'assistant' ? 'AI' : '我';
  
  const content = document.createElement('div');
  content.className = 'qa-chat-bubble';
  
  if (role === 'assistant') {
    _renderMarkdownInto(content, text);
  } else {
    content.textContent = text;
  }
  
  msgDiv.appendChild(avatar);
  msgDiv.appendChild(content);
  container.appendChild(msgDiv);
  container.scrollTop = container.scrollHeight;
}

function renderMemoryReviewPush(items) {
  if (!Array.isArray(items) || !items.length) return '';
  const dueItems = items.filter(item => item.is_due);
  const visible = (dueItems.length ? dueItems : items).slice(0, 4);
  return `
    <section class="memory-review-card">
      <div class="memory-review-head">
        <div>
          <span class="memory-review-kicker">MEMORY REVIEW</span>
          <h3>该唤醒的旧知识</h3>
          <p>${dueItems.length ? `今天有 ${dueItems.length} 个知识点到期` : '根据你的遗忘节奏，提前安排下一次接触'}</p>
        </div>
        <span class="memory-review-count">${dueItems.length || visible.length}</span>
      </div>
      <div class="memory-review-list">
        ${visible.map(item => `
          <button type="button" class="memory-review-item" data-memory-review-point
                  data-point-id="${escapeHtml(item.knowledge_point_id || '')}"
                  data-point-subject="${escapeHtml(item.subject || '')}"
                  data-point-title="${escapeHtml(item.knowledge_point || '')}">
            <span class="memory-review-subject">${escapeHtml(item.subject || '408')}</span>
            <span class="memory-review-main">
              <strong>${escapeHtml(item.knowledge_point || '')}</strong>
              <small>${escapeHtml(item.reason || '')} · 已 ${item.days_since_review || 0} 天未接触</small>
            </span>
            <span class="memory-review-score">${Math.round(item.mastery_score || 0)}%</span>
          </button>
        `).join('')}
      </div>
      ${typeof Notification !== 'undefined' && Notification.permission === 'default'
        ? '<button type="button" class="memory-reminder-enable" data-enable-memory-reminder>开启到期提醒</button>'
        : ''}
    </section>
  `;
}

function bindMemoryReminder(items) {
  window.KaoyanRuntime.notifyMemoryReview(items);
  document.querySelectorAll('[data-memory-review-point]').forEach(button => {
    button.addEventListener('click', async () => {
      if (button.disabled) return;
      button.disabled = true;
      button.classList.add('is-locating');
      try {
        await navigateToKnowledgePoint(
          button.dataset.pointId || '',
          button.dataset.pointSubject || '',
          button.dataset.pointTitle || ''
        );
      } finally {
        button.disabled = false;
        button.classList.remove('is-locating');
      }
    });
  });
  const button = document.querySelector('[data-enable-memory-reminder]');
  if (!button) return;
  button.addEventListener('click', async () => {
    const permission = await Notification.requestPermission();
    if (permission === 'granted') {
      button.textContent = '提醒已开启';
      button.disabled = true;
      await window.KaoyanRuntime.notifyMemoryReview(items);
    }
  });
}

// 每日推送
function loadDailyContent() {
  const contentDiv = document.getElementById('dailyContent');
  const dailyCacheKey = 'kaoyan_daily_push:' + new Date().toISOString().slice(0, 10);
  contentDiv.innerHTML = '<div class="loading">正在结合你的学习数据生成今日推送...</div>';

  fetch('/daily-push')
    .then(response => response.json())
    .then(data => {
      try { localStorage.setItem(dailyCacheKey, JSON.stringify(data)); } catch {}
      const pushResult = data.push_result;
      const memoryHtml = renderMemoryReviewPush(data.memory_review || []);
      if (!pushResult || !pushResult.questions || pushResult.questions.length === 0) {
        contentDiv.innerHTML = `
          <div class="daily-push-container">
            <div id="dailyTaskPanel"></div>
            ${memoryHtml}
            <h3 style="margin-top: 0">📚 今日知识点</h3>
            <p>${escapeHtml(data.answer || '').replace(/\n/g, '<br>')}</p>
          </div>
        `;
        bindMemoryReminder(data.memory_review || []);
        loadDailyTasks();
        return;
      }

      // 自动确认推送，记录已推送ID
      fetch('/daily-push/acknowledge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: 'u1', pushed_ids: data.pushed_ids || [] })
      }).catch(e => console.warn('保存推送记录失败', e));

      let questionsHtml = '';
      pushResult.questions.forEach((q, idx) => {
        const qNum = idx + 1;
        const qImages = q.images && q.images.length ? q.images : (q.image_url ? [q.image_url] : []);
        const imageHtml = qImages.length ? `
          <div class="question-image-wrap">
            ${qImages.map(src => `<img class="question-image" src="${escapeHtml(src)}" alt="题目配图" loading="lazy">`).join('')}
          </div>
        ` : '';
        let optionsHtml = '';
        q.options.forEach(opt => {
          const label = opt.charAt(0);
          optionsHtml += `
            <div class="dp-option" data-qidx="${idx}" data-option="${label}">
              <span class="dp-option-label">${label}</span>
              <span class="dp-option-text">${escapeHtml(opt.substring(2).trim())}</span>
            </div>
          `;
        });

        questionsHtml += `
          <div class="dp-question-card" data-qidx="${idx}" data-multiple="${isMultipleChoiceQuestion(q) ? '1' : '0'}">
            <div class="dp-q-header">第${qNum}题（${escapeHtml(q.subject)}）${isMultipleChoiceQuestion(q) ? ' · 多选' : ''}</div>
            <div class="dp-q-content">${escapeHtml(q.content)}</div>
            ${imageHtml}
            <div class="dp-options">${optionsHtml}</div>
            <div class="dp-feedback" id="dp-feedback-${idx}" style="display:none;"></div>
          </div>
        `;
      });

      const html = `
        <div class="daily-push-container">
          <div id="dailyTaskPanel"></div>
          ${memoryHtml}
          <div class="dp-header">
            <h3 class="dp-title">📚 今日知识点</h3>
            <span class="dp-subject-badge">${escapeHtml(pushResult.subject)}</span>
          </div>

          <div class="dp-knowledge-card">
            <h4 class="dp-kp-title">${escapeHtml(pushResult.knowledge_point_title)}</h4>
            <p class="dp-kp-content">${escapeHtml(pushResult.knowledge_point_content)}</p>
          </div>

          <hr class="dp-divider">

          <div class="dp-practice-header">
            <h3>🎯 今日练习（选择题）</h3>
            <p class="dp-practice-subtitle">以下2道题基于上述知识点，完成后点击提交查看答案</p>
          </div>

          <div class="dp-questions-area">
            ${questionsHtml}
          </div>

          <div class="dp-actions">
            <button class="dp-submit-btn" id="dpSubmitAll">提交全部答案</button>
            <button class="dp-show-answers-btn" id="dpShowAnswers">查看答案解析</button>
          </div>

          <div class="dp-result" id="dpResult" style="display:none;"></div>
        </div>
      `;

      contentDiv.innerHTML = html;
      window.KaoyanRuntime.renderMath(contentDiv);
      bindMemoryReminder(data.memory_review || []);
      loadDailyTasks();

      // 保存题目数据供后续使用
      contentDiv._pushData = data;
      contentDiv._selectedOptions = {};

      // 绑定选项点击事件
      document.querySelectorAll('.dp-option').forEach(el => {
        el.addEventListener('click', function() {
          const qidx = this.dataset.qidx;
          const option = this.dataset.option;
          const card = this.closest('.dp-question-card');
          const parent = this.closest('.dp-options');
          if (card.dataset.multiple === '1') {
            this.classList.toggle('selected');
            const answer = normalizeAnswerLetters(
              Array.from(parent.querySelectorAll('.dp-option.selected')).map(el => el.dataset.option).join('')
            );
            if (answer) contentDiv._selectedOptions[qidx] = answer;
            else delete contentDiv._selectedOptions[qidx];
          } else {
            parent.querySelectorAll('.dp-option').forEach(o => o.classList.remove('selected'));
            this.classList.add('selected');
            contentDiv._selectedOptions[qidx] = option;
          }
        });
      });

      // 绑定提交按钮
      document.getElementById('dpSubmitAll').addEventListener('click', function() {
        submitDailyPushAnswers(contentDiv);
      });

      // 绑定查看解析按钮
      document.getElementById('dpShowAnswers').addEventListener('click', function() {
        showDailyPushAnswers(contentDiv);
      });
    })
    .catch(error => {
      console.error('加载每日推送失败:', error);
      let cached = null;
      try { cached = JSON.parse(localStorage.getItem(dailyCacheKey) || 'null'); } catch {}
      if (cached) {
        contentDiv.innerHTML = `
          <div class="daily-push-container">
            ${renderMemoryReviewPush(cached.memory_review || [])}
            <h3 style="margin-top: 0">📚 今日离线补给</h3>
            <p>${escapeHtml(cached.answer || '已加载今天缓存的学习内容。').replace(/\n/g, '<br>')}</p>
            <p style="color:var(--text-secondary);font-size:0.82rem;">当前为离线缓存，联网后会自动更新。</p>
          </div>
        `;
        bindMemoryReminder(cached.memory_review || []);
        return;
      }
      contentDiv.innerHTML = `
        <div class="daily-push-container">
          <h3 style="margin-top: 0">📚 今日知识点</h3>
          <p>加载失败，请稍后重试。</p>
          <p style="color:var(--text-secondary);font-size:0.9rem;">错误信息：${error.message}</p>
        </div>
      `;
    });
}

async function loadDailyTasks() {
  const contentDiv = document.getElementById('dailyContent');
  if (!contentDiv) return;

  let panel = document.getElementById('dailyTaskPanel');
  if (!panel) {
    panel = document.createElement('div');
    panel.id = 'dailyTaskPanel';
    contentDiv.prepend(panel);
  }

  try {
    const response = await fetch('/daily-tasks/today');
    const data = await response.json();
    const tasks = data.tasks || [];
    const doneCount = tasks.filter(t => t.status === 'done').length;
    panel.innerHTML = `
      <div class="dt-card">
        <div class="dt-head">
          <h3>✅ 今日任务闭环</h3>
          <span class="dt-progress">${doneCount}/${tasks.length} 已完成</span>
        </div>
        <div class="dt-list">
          ${tasks.map(task => renderTaskRow(task)).join('')}
        </div>
      </div>
    `;

    bindTaskRowEvents(panel);
  } catch (error) {
    panel.innerHTML = '';
    console.warn('加载每日任务失败', error);
  }
}

function renderTaskRow(task) {
  const done = task.status === 'done';
  const score = task.mastery_score;
  const examSourceBadge = task.source === 'recent_exam_report'
    ? `<span class="dt-score dt-score-mid" title="依据最近 7 天已提交试卷的诊断报告生成">近 7 天试卷报告</span>`
    : '';
  const scoreBadge = score === null || score === undefined
    ? `<span class="dt-score dt-score-none">暂无做题记录</span>`
    : `<span class="dt-score ${score >= 75 ? 'dt-score-good' : score >= 50 ? 'dt-score-mid' : 'dt-score-bad'}">进度 ${formatProgressPercent(score)}</span>`;
  return `
    <div class="dt-row ${done ? 'is-done' : ''}" data-task-id="${escapeHtml(task.id)}" data-task-type="${escapeHtml(task.type || '')}">
      <div class="dt-row-main">
        <div class="dt-title-line">
          <span class="dt-title">${escapeHtml(task.title || '')}</span>
          ${examSourceBadge}
          ${scoreBadge}
        </div>
        <div class="dt-desc">${escapeHtml(task.description || '')}</div>
      </div>
      <div class="dt-actions">
        ${done
          ? `<button class="dt-btn dt-btn-done" disabled>✓ 已完成</button>
             <button class="dt-btn dt-btn-undo" data-action="uncomplete" title="撤销完成">撤销</button>`
          : `<button class="dt-btn dt-btn-start" data-action="start">开始复习</button>
             <button class="dt-btn dt-btn-complete" data-action="complete" disabled>完成</button>`}
      </div>
      <div class="dt-workspace" style="display:none;"></div>
    </div>
  `;
}

function bindTaskRowEvents(panel) {
  panel.querySelectorAll('.dt-row').forEach(row => {
    const taskId = row.dataset.taskId;
    const startBtn = row.querySelector('[data-action="start"]');
    const completeBtn = row.querySelector('[data-action="complete"]');
    const undoBtn = row.querySelector('[data-action="uncomplete"]');
    const ws = row.querySelector('.dt-workspace');

    if (startBtn) {
      startBtn.addEventListener('click', async () => {
        startBtn.disabled = true;
        startBtn.textContent = '加载中…';
        ws.style.display = 'block';
        ws.innerHTML = '<div class="dt-loading">正在加载知识点与配套练习…</div>';
        try {
          const res = await fetch('/daily-tasks/' + encodeURIComponent(taskId) + '/material');
          const mat = await res.json();
          if (!mat.task) {
            ws.innerHTML = '<div class="dt-empty">任务不存在或已过期</div>';
            return;
          }
          renderTaskWorkspace(row, mat);
        } catch (e) {
          console.warn('加载任务材料失败', e);
          ws.innerHTML = '<div class="dt-empty">加载失败，请稍后重试</div>';
        }
      });
    }

    if (completeBtn) {
      completeBtn.addEventListener('click', async () => {
        completeBtn.disabled = true;
        completeBtn.textContent = '提交中…';
        await completeDailyTask(taskId);
        await Promise.all([
          loadDailyTasks(),
          loadProfile(),
          Promise.resolve(renderCalendarGrid()),
        ]);
      });
    }

    if (undoBtn) {
      undoBtn.addEventListener('click', async () => {
        if (!confirm('确定要撤销这条任务的完成状态吗？')) return;
        undoBtn.disabled = true;
        try {
          await fetch('/daily-tasks/uncomplete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ task_id: taskId }),
          });
        } catch (e) { console.warn('撤销失败', e); }
        await Promise.all([
          loadDailyTasks(),
          loadProfile(),
          Promise.resolve(renderCalendarGrid()),
        ]);
      });
    }
  });
}

function renderTaskWorkspace(row, mat) {
  const ws = row.querySelector('.dt-workspace');
  const taskId = mat.task?.id || row.dataset.taskId || '';
  const knowledgeList = (mat.knowledge_points && mat.knowledge_points.length)
    ? mat.knowledge_points
    : (mat.knowledge ? [mat.knowledge] : []);
  const qs = mat.questions || [];
  const knowledgeCards = knowledgeList.map((k, index) => `
    <div class="dt-kp-card">
      <div class="dt-kp-head">
        <span class="dt-kp-tag">📌 知识点 ${index + 1}</span>
        <span class="dt-kp-subject">${escapeHtml(k.subject || '')}${k.chapter_title ? ` · ${escapeHtml(k.chapter_title)}` : ''}</span>
      </div>
      <h4 class="dt-kp-title">${escapeHtml(k.title || '')}</h4>
      <div class="dt-kp-content">${escapeHtml(k.content || '').replace(/\n/g, '<br>')}</div>
      ${(k.score_points && k.score_points.length) ? `
        <div class="dt-kp-points">
          <div class="dt-kp-points-title">🎯 考点速记</div>
          <ul>${k.score_points.slice(0, 6).map(p => `<li>${escapeHtml(p)}</li>`).join('')}</ul>
        </div>` : ''}
    </div>
  `).join('');
  const kpHtml = `
    <div class="dt-kp" data-kp-read="0">
      <div class="dt-kp-head">
        <span class="dt-kp-tag">📚 本次知识点（${knowledgeList.length} 个）</span>
      </div>
      ${knowledgeCards || '<div class="dt-empty">该任务暂无知识点材料</div>'}
      <label class="dt-read-check">
        <input type="checkbox" class="dt-read-flag">
        <span>我已认真阅读以上全部知识点</span>
      </label>
    </div>
  `;
  const qsHtml = qs.length
    ? qs.map((q, i) => {
        const qImages = q.images && q.images.length ? q.images : (q.image_url ? [q.image_url] : []);
        const imageHtml = qImages.length ? `
          <div class="question-image-wrap">
            ${qImages.map(src => `<img class="question-image" src="${escapeHtml(src)}" alt="题目配图" loading="lazy">`).join('')}
          </div>
        ` : '';
        return `
        <div class="dt-q" data-qid="${escapeHtml(q.id || '')}" data-qidx="${i}" data-multiple="${isMultipleChoiceQuestion(q) ? '1' : '0'}">
          <div class="dt-q-head">第 ${i + 1} 题${q.subject ? `（${escapeHtml(q.subject)}）` : ''}${isMultipleChoiceQuestion(q) ? ' · 多选' : ''}</div>
          <div class="dt-q-content">${escapeHtml(q.content || '')}</div>
          ${imageHtml}
          <div class="dt-q-options">
            ${(q.options || []).map(opt => `
              <div class="dt-option" data-qidx="${i}" data-option="${escapeHtml((opt || '').charAt(0))}">
                <span class="dt-option-label">${escapeHtml((opt || '').charAt(0))}</span>
                <span class="dt-option-text">${escapeHtml((opt || '').substring(2).trim() || opt)}</span>
              </div>
            `).join('')}
          </div>
          <div class="dt-q-feedback" style="display:none;"></div>
        </div>
      `;
      }).join('')
    : '<div class="dt-empty">该任务暂无配套题目</div>';

  ws.innerHTML = `
    ${kpHtml}
    <div class="dt-qs" data-qs-done="${qs.length ? '0' : '1'}">
      <div class="dt-qs-head">🎯 配套练习（${qs.length} 题）</div>
      ${qsHtml}
      ${qs.length ? '<button class="dt-btn dt-btn-submit-qs" data-action="submit-qs" disabled>提交练习</button>' : ''}
    </div>
  `;
  window.KaoyanRuntime.renderMath(ws);

  qs.forEach(q => {
    if (!q.attempt) return;
    const wrap = ws.querySelector(`.dt-q[data-qid="${CSS.escape(q.id || '')}"]`);
    if (wrap) renderTaskQuestionAttempt(wrap, q.attempt);
  });
  const restoredAllAnswers = qs.length > 0 && qs.every(q => q.attempt);
  if (restoredAllAnswers) {
    ws.querySelector('.dt-qs').dataset.qsDone = '1';
    const restoredSubmitButton = ws.querySelector('[data-action="submit-qs"]');
    if (restoredSubmitButton) {
      restoredSubmitButton.disabled = true;
      restoredSubmitButton.textContent = '已批改并保存';
    }
  }

  // 选中
  ws.querySelectorAll('.dt-option').forEach(el => {
    el.addEventListener('click', () => {
      if (el.classList.contains('disabled') || ws.querySelector('.dt-qs')?.dataset.qsDone === '1') return;
      const qidx = el.dataset.qidx;
      const wrap = el.closest('.dt-q');
      if (wrap.dataset.multiple === '1') {
        el.classList.toggle('selected');
        wrap.dataset.selected = normalizeAnswerLetters(
          Array.from(wrap.querySelectorAll('.dt-option.selected')).map(option => option.dataset.option).join('')
        );
      } else {
        wrap.querySelectorAll('.dt-option').forEach(o => o.classList.remove('selected'));
        el.classList.add('selected');
        wrap.dataset.selected = el.dataset.option;
      }
      // 解锁提交按钮
      const allQ = ws.querySelectorAll('.dt-q');
      const allAnswered = Array.from(allQ).every(q => q.dataset.selected);
      const submitButton = ws.querySelector('[data-action="submit-qs"]');
      if (submitButton) submitButton.disabled = !allAnswered;
    });
  });

  // 阅读勾选
  ws.querySelector('.dt-read-flag').addEventListener('change', e => {
    ws.querySelector('.dt-kp').dataset.kpRead = e.target.checked ? '1' : '0';
    tryUnlockComplete(row);
  });

  // 提交练习
  ws.querySelector('[data-action="submit-qs"]')?.addEventListener('click', async () => {
    const submitBtn = ws.querySelector('[data-action="submit-qs"]');
    submitBtn.disabled = true;
    submitBtn.textContent = '批改中…';
    const results = [];
    for (const q of qs) {
      const wrap = ws.querySelector(`.dt-q[data-qid="${CSS.escape(q.id || '')}"]`);
      if (!wrap) continue;
      if (wrap.dataset.saved === '1') {
        results.push({ id: q.id, is_correct: wrap.dataset.correct === '1' });
        continue;
      }
      const sel = wrap.dataset.selected || '';
      try {
        const r = await fetch('/question-bank/submit-answer', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question_id: q.id,
            selected_option: sel,
            subject: q.subject,
            knowledge_points: q.knowledge_points,
            question_content: q.content,
            options: q.options,
            source: (row.dataset.taskScope === 'plan' ? 'study_plan:' : 'daily_task:') + taskId,
          })
        }).then(r => r.json());
        const correctAnswer = normalizeAnswerLetters(r.correct_answer);
        const correct = Boolean(r.is_correct);
        renderTaskQuestionAttempt(wrap, {
          selected_option: sel,
          correct_answer: correctAnswer,
          is_correct: correct,
          explanation: r.explanation,
        });
        results.push({ id: q.id, is_correct: correct });
      } catch (e) {
        console.warn('批改失败', e);
      }
    }
    if (results.length === qs.length) {
      submitBtn.textContent = '已批改并保存';
      ws.querySelector('.dt-qs').dataset.qsDone = '1';
      // 批改成功即持久化；完成打卡只负责更新计划进度。
      tryUnlockComplete(row);
    } else {
      submitBtn.disabled = false;
      submitBtn.textContent = '部分保存失败，重试批改';
    }
  });

  if (restoredAllAnswers) tryUnlockComplete(row);
}

function renderTaskQuestionAttempt(wrap, attempt) {
  const selected = normalizeAnswerLetters(attempt?.selected_option);
  const correctAnswer = normalizeAnswerLetters(attempt?.correct_answer);
  const correct = Boolean(attempt?.is_correct);
  wrap.dataset.selected = selected;
  wrap.dataset.saved = '1';
  wrap.dataset.correct = correct ? '1' : '0';
  wrap.querySelectorAll('.dt-option').forEach(opt => {
    opt.classList.add('disabled');
    opt.classList.toggle('selected', selected.includes(opt.dataset.option));
    if (correctAnswer.includes(opt.dataset.option)) opt.classList.add('correct');
    if (!correct && selected.includes(opt.dataset.option) && !correctAnswer.includes(opt.dataset.option)) {
      opt.classList.add('incorrect');
    }
  });
  const feedback = wrap.querySelector('.dt-q-feedback');
  if (!feedback) return;
  feedback.style.display = 'block';
  const statusHtml = correct
    ? '<span class="dt-feedback-ok">✓ 答对了</span>'
    : '<span class="dt-feedback-bad">✗ 答案不正确，已记入错题本</span>';
  const answerHtml = correctAnswer
    ? `<div class="dt-answer-line"><strong>正确答案：</strong>${escapeHtml(correctAnswer)}</div>`
    : '<div class="dt-answer-line"><strong>正确答案：</strong>题库暂未返回标准答案</div>';
  const explanation = String(attempt?.explanation || '').trim();
  feedback.innerHTML = `
    <div class="dt-feedback-result">${statusHtml}<span>你的选择：${escapeHtml(selected || '未选择')}</span></div>
    ${answerHtml}
    <div class="dt-explanation">
      <strong>解析：</strong>
      <div>${explanation ? escapeHtml(explanation).replace(/\n/g, '<br>') : '题库暂未返回解析，请稍后重试。'}</div>
    </div>
  `;
}

function tryUnlockComplete(row) {
  const ws = row.querySelector('.dt-workspace');
  const kpRead = ws.querySelector('.dt-kp')?.dataset.kpRead === '1';
  const qsDone = ws.querySelector('.dt-qs')?.dataset.qsDone === '1';
  const btn = row.querySelector('[data-action="complete"]');
  if (!btn) return;
  if (kpRead && qsDone) {
    btn.disabled = false;
    btn.classList.add('dt-btn-active');
  } else {
    btn.disabled = true;
    btn.classList.remove('dt-btn-active');
  }
}

async function completeDailyTask(taskId) {
  if (!taskId) return;
  await fetch('/daily-tasks/complete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ task_id: taskId })
  });
}

function submitDailyPushAnswers(container) {
  const data = container._pushData;
  const selected = container._selectedOptions;
  const pushResult = data.push_result;

  if (Object.keys(selected).length < pushResult.questions.length) {
    alert('请先回答所有题目再提交！');
    return;
  }

  let correctCount = 0;
  let resultHtml = '<h4>📊 作答结果</h4>';

  pushResult.questions.forEach((q, idx) => {
    const userAns = normalizeAnswerLetters(selected[idx]);
    const correctAns = normalizeAnswerLetters(q.answer);
    const isCorrect = userAns === correctAns;

    if (isCorrect) correctCount++;

    const feedbackDiv = document.getElementById(`dp-feedback-${idx}`);
    if (isCorrect) {
      feedbackDiv.className = 'dp-feedback dp-feedback-correct';
      feedbackDiv.innerHTML = '✅ 回答正确！';
    } else {
      feedbackDiv.className = 'dp-feedback dp-feedback-wrong';
      feedbackDiv.innerHTML = `❌ 回答错误。正确答案是 <strong>${correctAns}</strong>`;
    }
    feedbackDiv.style.display = 'block';

    // 标记选项
    const qCard = document.querySelector(`.dp-question-card[data-qidx="${idx}"]`);
    qCard.querySelectorAll('.dp-option').forEach(el => {
      el.classList.add('disabled');
      if (correctAns.includes(el.dataset.option)) {
        el.classList.add('correct');
      }
      if (userAns.includes(el.dataset.option) && !correctAns.includes(el.dataset.option)) {
        el.classList.add('incorrect');
      }
    });

    // 提交答案到服务器
    fetch('/daily-push/submit-answer', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question_id: q.id,
        selected_option: userAns,
        correct_answer: q.answer,
        question_content: q.content,
        options: q.options,
        explanation: q.explanation,
        subject: q.subject,
        knowledge_point: q.knowledge_point,
      })
    }).catch(e => console.warn('保存作答记录失败', e));
  });

  const total = pushResult.questions.length;
  completeDailyTask('daily-push').then(loadDailyTasks).catch(e => console.warn('更新每日任务失败', e));
  const percent = Math.round(correctCount / total * 100);
  let emoji = '😢';
  if (percent >= 100) emoji = '🎉';
  else if (percent >= 50) emoji = '👍';

  resultHtml += `
    <div class="dp-result-summary">
      <div class="dp-result-emoji">${emoji}</div>
      <div class="dp-result-score">${correctCount}/${total}</div>
      <div class="dp-result-text">正确率 ${percent}%</div>
    </div>
  `;

  document.getElementById('dpResult').innerHTML = resultHtml;
  document.getElementById('dpResult').style.display = 'block';
  document.getElementById('dpSubmitAll').disabled = true;
  document.getElementById('dpSubmitAll').textContent = '已提交';
  document.getElementById('dpShowAnswers').style.display = 'inline-block';
}

function showDailyPushAnswers(container) {
  const data = container._pushData;
  const pushResult = data.push_result;

  let html = '<h4>📝 详细解析</h4>';
  pushResult.questions.forEach((q, idx) => {
    html += `
      <div class="dp-explanation-card">
        <div class="dp-explanation-header">第${idx + 1}题 解析</div>
        <div class="dp-explanation-answer">正确答案：<strong>${q.answer}</strong></div>
        <div class="dp-explanation-text">${escapeHtml(q.explanation)}</div>
      </div>
    `;
  });

  const resultDiv = document.getElementById('dpResult');
  if (resultDiv) {
    const existing = resultDiv.querySelector('h4');
    if (existing && existing.textContent === '📝 详细解析') {
      // 已显示解析，不做重复
      return;
    }
    resultDiv.innerHTML += html;
    resultDiv.style.display = 'block';
  }
  document.getElementById('dpShowAnswers').disabled = true;
  document.getElementById('dpShowAnswers').textContent = '解析已显示';
}

// 个人中心
async function loadProfile() {
  try {
    // 学习概览必须与题库总览读取同一时刻、同一统计接口的数据，并绕过 HTTP 缓存。
    const [response, overviewResponse, assessmentResponse, accountResponse] = await Promise.all([
      fetch('/user/profile', { cache: 'no-store' }),
      fetch('/user/stats/overview', { cache: 'no-store' }),
      fetch('/user/profile-assessment/status', { cache: 'no-store' }),
      fetch('/api/auth/account', { cache: 'no-store' }),
    ]);
    if (!response.ok) throw new Error('学习画像加载失败');
    const data = await response.json();
    if (overviewResponse.ok) {
      const overview = await overviewResponse.json();
      data.answer_stats = data.answer_stats || {};
      data.answer_stats.total_questions = toNonNegativeNumber(overview.total_answered);
      data.answer_stats.correct_count = toNonNegativeNumber(overview.total_correct);
      data.answer_stats.accuracy = toNonNegativeNumber(overview.accuracy);
    }
    data.profile_assessment = assessmentResponse.ok
      ? await assessmentResponse.json()
      : { question_count: 40, has_completed: false, in_progress: false };
    data.account = accountResponse.ok ? await accountResponse.json() : {};
    // 基础数据先立即显示；AI 洞察较慢时不阻塞整个个人中心。
    renderProfile(data);
    try {
      const insResp = await fetch('/user/insights');
      if (insResp.ok) {
        data.ai_insights = await insResp.json();
        renderProfile(data);
      }
    } catch (e) {
      console.warn('insights 拉取失败', e);
    }
  } catch (error) {
    console.error('加载用户信息失败:', error);
  }
}

function renderProfile(data) {
  const profileDiv = document.getElementById('profileContent');
  
  const subjects = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
  const assessment = data.profile_assessment || {};
  const assessmentResult = assessment.latest_result || {};
  const account = data.account || {};
  const accountCard = account.user_id ? `
    <section class="account-security-card">
      <div class="account-security-head">
        <div><span>ACCOUNT & SECURITY</span><h3>账号与安全</h3><p>${escapeHtml(account.nickname || account.user_id)} · ${escapeHtml(account.user_id)}</p></div>
        <div class="account-security-actions"><button type="button" id="openAccountSettingsBtn">管理账号</button><button type="button" class="secondary" id="profileLogoutBtn">退出账号</button></div>
      </div>
      <div class="account-security-grid">
        <article><span>我的邀请码</span><strong>${escapeHtml(account.invite_code || '生成中')}</strong><button type="button" id="copyInviteCodeBtn">复制</button></article>
        <article><span>手机号</span><strong>${account.phone_verified ? escapeHtml(account.phone_masked || '') : '未绑定'}</strong><small>用于登录 / 找回密码</small></article>
        <article><span>微信号</span><strong>${escapeHtml(account.wechat_id || '未绑定')}</strong><small>用于客服沟通</small></article>
        <article><span>客服</span><strong>17635575899</strong><small>电话与微信同号</small></article>
      </div>
    </section>` : '';
  const assessmentCard = `
    <section class="profile-assessment-card ${assessment.has_completed ? 'is-complete' : ''}">
      <div class="profile-assessment-copy">
        <span class="profile-assessment-kicker">QUICK PROFILE · 四科诊断</span>
        <h3>${assessment.has_completed ? '学习画像已建立' : '用 40 题快速建立学习画像'}</h3>
        <p>${assessment.has_completed
          ? `最近测评正确率 ${Number(assessmentResult.accuracy || 0).toFixed(1)}%，系统会持续合并题库中的后续作答，动态更新所有个性化分析。`
          : '四科各 10 题，覆盖不同章节与难度。完成后，每日补给、学习计划、薄弱点、择校适配等都会立即使用这份结果。'}</p>
        <div class="profile-assessment-tags"><span>数据结构 10</span><span>组成原理 10</span><span>操作系统 10</span><span>计算机网络 10</span></div>
      </div>
      <div class="profile-assessment-action">
        ${assessment.has_completed ? `<strong>${Number(assessmentResult.accuracy || 0).toFixed(1)}%</strong><small>${assessmentResult.correct_count || 0} / ${assessmentResult.question_count || 40} 正确</small>` : '<strong>40</strong><small>预计 25–35 分钟</small>'}
        <button type="button" id="startProfileAssessmentBtn">${assessment.in_progress ? '继续测评' : assessment.has_completed ? '重新测评' : '开始快速画像'}</button>
      </div>
    </section>`;
  
  let weakPointsHtml = '';
  // 这里只展示真实知识点；诊断文案和各类统计不混入薄弱知识点清单。
  const realWeak = data.weak_points || [];
  const validWeak = (realWeak || []).filter(wp => {
    const name = String(wp.knowledge_point || wp.knowledgePoint || '').trim();
    return name && !name.includes('未标注') && !name.includes('暂无');
  });
  if (validWeak.length > 0) {
    validWeak.forEach(wp => {
      const name = wp.knowledge_point || wp.knowledgePoint || '';
      const subj = wp.subject || '';
      weakPointsHtml += `
        <button class="profile-weak-link profile-point-link" type="button"
          data-point-id="${escapeHtml(wp.knowledge_point_id || '')}"
          data-point-title="${escapeHtml(name)}"
          data-point-subject="${escapeHtml(subj)}"
          aria-label="在知识图谱中查看 ${escapeHtml(name)}">
          <span class="profile-weak-main">
            <span class="profile-weak-subject">${escapeHtml(subj || '其他')}</span>
            <span class="profile-weak-name">${escapeHtml(name)}</span>
          </span>
          <span class="profile-point-arrow" aria-hidden="true">→</span>
        </button>
      `;
    });
  } else {
    weakPointsHtml += '<p style="color: var(--text-secondary)">暂无薄弱知识点记录</p>';
  }

  const masteryItems = data.mastery || [];
  const masteryBySubject = {};
  subjects.forEach(subject => { masteryBySubject[subject] = []; });
  masteryItems.forEach(item => {
    const subject = item.subject || '';
    if (masteryBySubject[subject]) masteryBySubject[subject].push(item);
  });
  const masteryHtml = subjects.map(subject => {
    const summary = data.subject_mastery?.[subject] || {};
    const score = Number(summary.score || 0);
    const points = masteryBySubject[subject]
      .slice()
      .sort((a, b) => Number(a.score || 0) - Number(b.score || 0)
        || String(a.knowledge_point || '').localeCompare(String(b.knowledge_point || ''), 'zh-CN'));
    const pointsHtml = points.length
      ? points.map(item => `
        <button class="profile-mastery-point profile-point-link" type="button"
          data-point-id="${escapeHtml(item.knowledge_point_id || '')}"
          data-point-title="${escapeHtml(item.knowledge_point || '')}"
          data-point-subject="${escapeHtml(subject)}">
          <span class="profile-mastery-point-name">${escapeHtml(item.knowledge_point || '')}</span>
          <span class="profile-mastery-point-data">
            <strong>${formatProgressPercent(Number(item.score || 0))}</strong>
            <small>已做 ${item.attempts || 0}/${item.total_questions || 0} 题</small>
            <i aria-hidden="true">→</i>
          </span>
        </button>
      `).join('')
      : '<p class="profile-mastery-empty">该科目暂无可统计的知识点。</p>';
    return `
      <details class="profile-mastery-subject" data-subject="${escapeHtml(subject)}">
        <summary>
          <span class="profile-mastery-subject-main">
            <strong>${escapeHtml(subject)}</strong>
            <small>完成 ${summary.answer_count || 0}/${summary.question_count || 0} 题 · 点击查看知识点</small>
          </span>
          <span class="profile-mastery-subject-score">${formatProgressPercent(score)}</span>
          <span class="profile-mastery-chevron" aria-hidden="true">⌄</span>
          <span class="profile-mastery-subject-track" aria-hidden="true">
            <i style="width:${Math.max(0, Math.min(100, score))}%"></i>
          </span>
        </summary>
        <div class="profile-mastery-points">${pointsHtml}</div>
      </details>
    `;
  }).join('');

  const taskData = data.daily_tasks || { tasks: [] };
  const taskHtml = (taskData.tasks || []).map(task => `
    <div class="weak-point-item">
      <span class="weak-point-name">${task.status === 'done' ? '✅' : '○'} ${escapeHtml(task.title || '')}</span>
      <span class="weak-point-count">${task.status === 'done' ? '已完成' : '待完成'}</span>
      ${task.status === 'done' ? `<button class="dt-undo-task" data-task-id="${escapeHtml(task.id)}" title="撤销完成" style="margin-left:8px;border:0;background:transparent;color:var(--primary);cursor:pointer;font-size:12px;">撤销</button>` : ''}
    </div>
  `).join('') || '<p style="color: var(--text-secondary)">暂无每日任务。</p>';
  
  profileDiv.innerHTML = `
    ${accountCard}
    ${assessmentCard}
    <div class="profile-section">
      <h3 class="profile-section-title">📊 学习概览</h3>
      <div class="stats-grid">
        <div class="stat-card">
          <div class="stat-value">${data.answer_stats.total_questions}</div>
          <div class="stat-label">已做题数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${data.answer_stats.correct_count}</div>
          <div class="stat-label">正确题数</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${data.answer_stats.accuracy}%</div>
          <div class="stat-label">正确率</div>
        </div>
        <div class="stat-card">
          <div class="stat-value">${data.answer_stats.wrong_count || 0}</div>
          <div class="stat-label">错题数</div>
        </div>
      </div>
    </div>
    
    <div class="profile-section">
      <h3 class="profile-section-title">⚠️ 薄弱知识点</h3>
      <div class="weak-points">
        ${weakPointsHtml}
      </div>
    </div>

    <div class="profile-section">
      <h3 class="profile-section-title">🧠 知识点掌握度</h3>
      <div class="profile-mastery-list">
        ${masteryHtml}
      </div>
    </div>

    <div class="profile-section">
      <h3 class="profile-section-title">✅ 今日任务</h3>
      <div class="weak-points">
        ${taskHtml}
      </div>
    </div>
    
    <div class="profile-section">
      <h3 class="profile-section-title">💎 Token 使用</h3>
      <div style="display: flex; gap: 40px;">
        <div>
          <div style="font-size: 24px; font-weight: 700; color: var(--primary-light); margin-bottom: 4px;">${data.token_usage.total_tokens}</div>
          <div style="font-size: 13px; color: var(--text-secondary)">总 Token 数</div>
        </div>
        <div>
          <div style="font-size: 24px; font-weight: 700; color: var(--primary-light); margin-bottom: 4px;">${data.token_usage.total_requests}</div>
          <div style="font-size: 13px; color: var(--text-secondary)">请求次数</div>
        </div>
      </div>
    </div>
  `;

  document.getElementById('startProfileAssessmentBtn')?.addEventListener('click', () => {
    startProfileAssessment(Boolean(assessment.has_completed && !assessment.in_progress));
  });
  document.getElementById('copyInviteCodeBtn')?.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(account.invite_code || ''); alert('邀请码已复制'); }
    catch (_) { alert(`你的邀请码：${account.invite_code || ''}`); }
  });
  document.getElementById('openAccountSettingsBtn')?.addEventListener('click', () => openAccountSettingsModal(account));
  document.getElementById('profileLogoutBtn')?.addEventListener('click', logoutAccount);

  profileDiv.querySelectorAll('.profile-point-link').forEach(button => {
    button.addEventListener('click', () => {
      navigateToKnowledgePoint(
        button.dataset.pointId || '',
        button.dataset.pointSubject || '',
        button.dataset.pointTitle || ''
      );
    });
  });

  // 今日任务「撤销」按钮(同步 JSON + DB)
  profileDiv.querySelectorAll('.dt-undo-task').forEach(btn => {
    btn.addEventListener('click', async () => {
      const taskId = btn.dataset.taskId;
      if (!taskId || !confirm('确定要撤销这条任务的完成状态吗？')) return;
      btn.disabled = true;
      try {
        await fetch('/daily-tasks/uncomplete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: taskId }),
        });
      } catch (e) { console.warn('撤销失败', e); }
      await Promise.all([loadProfile(), loadDailyTasks()]);
    });
  });
}

function profileAssessmentDraftKey(id) {
  return `kaoyan_profile_assessment_${id}`;
}

function saveProfileAssessmentDraft() {
  const current = state.profileAssessment.current;
  if (!current) return;
  try {
    localStorage.setItem(profileAssessmentDraftKey(current.id), JSON.stringify({
      answers: state.profileAssessment.answers,
      index: state.profileAssessment.index,
      startedAt: state.profileAssessment.startedAt,
    }));
  } catch (_) {}
}

async function startProfileAssessment(force = false) {
  const button = document.getElementById('startProfileAssessmentBtn');
  if (button) { button.disabled = true; button.textContent = '正在组卷…'; }
  try {
    const response = await fetch('/user/profile-assessment/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force }),
    });
    const assessment = await response.json();
    if (!response.ok) throw new Error(assessment.detail || '画像测评生成失败');
    state.profileAssessment.current = assessment;
    state.profileAssessment.answers = {};
    state.profileAssessment.index = 0;
    state.profileAssessment.startedAt = Date.now();
    try {
      const draft = JSON.parse(localStorage.getItem(profileAssessmentDraftKey(assessment.id)) || 'null');
      if (draft) {
        state.profileAssessment.answers = draft.answers || {};
        state.profileAssessment.index = Math.min(Number(draft.index || 0), assessment.questions.length - 1);
        state.profileAssessment.startedAt = Number(draft.startedAt || Date.now());
      }
    } catch (_) {}
    renderProfileAssessmentModal();
  } catch (error) {
    alert(error.message || '画像测评生成失败');
    if (button) { button.disabled = false; button.textContent = '开始快速画像'; }
  }
}

function renderProfileAssessmentModal() {
  const assessment = state.profileAssessment.current;
  if (!assessment?.questions?.length) return;
  let modal = document.getElementById('profileAssessmentModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'profileAssessmentModal';
    modal.className = 'profile-assessment-modal';
    document.body.appendChild(modal);
  }
  const index = state.profileAssessment.index;
  const question = assessment.questions[index];
  const selected = normalizeAnswerLetters(state.profileAssessment.answers[question.id]);
  const answered = Object.keys(state.profileAssessment.answers).filter(id => state.profileAssessment.answers[id]).length;
  const multiple = isMultipleChoiceQuestion(question);
  const images = question.images || [];
  modal.innerHTML = `
    <div class="profile-assessment-backdrop"></div>
    <section class="profile-assessment-dialog" role="dialog" aria-modal="true" aria-label="快速学习画像测评">
      <header class="profile-assessment-header">
        <div><span>快速学习画像</span><strong>${index + 1} / ${assessment.questions.length}</strong></div>
        <div class="profile-assessment-progress"><i style="width:${answered / assessment.questions.length * 100}%"></i></div>
        <button type="button" data-assessment-close aria-label="暂时退出">×</button>
      </header>
      <div class="profile-assessment-layout">
        <aside class="profile-assessment-sheet">
          <p>已答 ${answered} / ${assessment.questions.length}</p>
          <div>${assessment.questions.map((item, itemIndex) => `<button type="button" data-assessment-index="${itemIndex}" class="${itemIndex === index ? 'active' : ''} ${state.profileAssessment.answers[item.id] ? 'answered' : ''}">${itemIndex + 1}</button>`).join('')}</div>
        </aside>
        <main class="profile-assessment-question">
          <div class="profile-assessment-meta"><span>${escapeHtml(question.subject)}</span><span>${escapeHtml(question.chapter || '综合')}</span><span>${escapeHtml(question.difficulty || '基础')}</span>${multiple ? '<span>多选</span>' : ''}</div>
          <h2>${escapeHtml(question.content)}</h2>
          ${images.length ? `<div class="question-image-wrap">${images.map(src => `<img class="question-image" src="${escapeHtml(src)}" alt="题目配图">`).join('')}</div>` : ''}
          <div class="profile-assessment-options">${(question.options || []).map(option => {
            const letter = option.charAt(0);
            return `<button type="button" data-assessment-option="${letter}" class="${selected.includes(letter) ? 'selected' : ''}"><b>${letter}</b><span>${escapeHtml(option.substring(2).trim() || option)}</span></button>`;
          }).join('')}</div>
          <footer>
            <button type="button" data-assessment-prev ${index === 0 ? 'disabled' : ''}>上一题</button>
            ${index === assessment.questions.length - 1
              ? `<button type="button" class="primary" data-assessment-submit ${answered < assessment.questions.length ? 'disabled' : ''}>提交并生成画像</button>`
              : '<button type="button" class="primary" data-assessment-next>下一题</button>'}
          </footer>
        </main>
      </div>
    </section>`;
  window.KaoyanRuntime.renderMath(modal);
  document.body.classList.add('profile-assessment-open');
  modal.querySelector('[data-assessment-close]').addEventListener('click', closeProfileAssessment);
  modal.querySelectorAll('[data-assessment-index]').forEach(button => button.addEventListener('click', () => {
    state.profileAssessment.index = Number(button.dataset.assessmentIndex);
    saveProfileAssessmentDraft();
    renderProfileAssessmentModal();
  }));
  modal.querySelectorAll('[data-assessment-option]').forEach(button => button.addEventListener('click', () => {
    const current = normalizeAnswerLetters(state.profileAssessment.answers[question.id]);
    if (multiple) {
      const values = new Set(current.split('').filter(Boolean));
      if (values.has(button.dataset.assessmentOption)) values.delete(button.dataset.assessmentOption);
      else values.add(button.dataset.assessmentOption);
      state.profileAssessment.answers[question.id] = normalizeAnswerLetters([...values].join(''));
    } else {
      state.profileAssessment.answers[question.id] = button.dataset.assessmentOption;
    }
    saveProfileAssessmentDraft();
    renderProfileAssessmentModal();
  }));
  modal.querySelector('[data-assessment-prev]')?.addEventListener('click', () => {
    state.profileAssessment.index -= 1; saveProfileAssessmentDraft(); renderProfileAssessmentModal();
  });
  modal.querySelector('[data-assessment-next]')?.addEventListener('click', () => {
    state.profileAssessment.index += 1; saveProfileAssessmentDraft(); renderProfileAssessmentModal();
  });
  modal.querySelector('[data-assessment-submit]')?.addEventListener('click', submitProfileAssessment);
}

function closeProfileAssessment() {
  saveProfileAssessmentDraft();
  document.getElementById('profileAssessmentModal')?.remove();
  document.body.classList.remove('profile-assessment-open');
}

async function logoutAccount() {
  try { await fetch('/api/auth/logout', { method: 'POST' }); } catch (_) {}
  setToken('');
  try {
    localStorage.removeItem('kaoyan_user');
    sessionStorage.removeItem('kaoyan_user');
  } catch (_) {}
  window.location.replace('/');
}

function closeAccountSettingsModal() {
  document.getElementById('accountSettingsModal')?.remove();
  document.body.classList.remove('account-settings-open');
}

function openAccountSettingsModal(account) {
  closeAccountSettingsModal();
  const modal = document.createElement('div');
  modal.id = 'accountSettingsModal';
  modal.className = 'account-settings-modal';
  modal.innerHTML = `
    <div class="account-settings-backdrop" data-account-close></div>
    <section class="account-settings-dialog" role="dialog" aria-modal="true" aria-label="账号与安全设置">
      <header><div><span>ACCOUNT CENTER</span><h2>账号与安全</h2></div><button type="button" data-account-close aria-label="关闭">×</button></header>
      <div class="account-settings-body">
        <section><h3>手机号</h3>
          <p>${account.phone_verified ? `已绑定：<strong>${escapeHtml(account.phone_masked || '')}</strong>，可换绑其他手机号。` : '绑定后可用于登录和找回密码。'}</p>
          <label>手机号<input id="accountPhone" type="tel" maxlength="11" inputmode="numeric" placeholder="请输入 11 位手机号"></label>
          <label>验证码
            <span class="account-code-row">
              <input id="accountPhoneCode" type="text" maxlength="6" inputmode="numeric" placeholder="6 位验证码">
              <button type="button" class="secondary" id="sendBindCodeBtn">获取验证码</button>
            </span>
          </label>
          <button type="button" class="primary" id="bindPhoneBtn">${account.phone_verified ? '换绑手机号' : '绑定手机号'}</button>
          <div class="account-form-msg" id="phoneMsg"></div>
        </section>
        <section><h3>微信号</h3><p>用于客服沟通，不会公开展示。</p>
          <label>微信号<input id="accountWechat" maxlength="64" value="${escapeHtml(account.wechat_id || '')}" placeholder="请输入微信号"></label>
          <button type="button" class="primary" id="saveWechatBtn">保存微信号</button><div class="account-form-msg" id="wechatMsg"></div>
        </section>
        <section><h3>修改密码</h3><p>修改后请使用新密码再次登录。</p>
          <label>当前密码<input id="currentPassword" type="password" autocomplete="current-password"></label>
          <label>新密码<input id="newPassword" type="password" minlength="6" autocomplete="new-password"></label>
          <button type="button" class="primary" id="changePasswordBtn">修改密码</button><div class="account-form-msg" id="passwordMsg"></div>
        </section>
        <section class="account-service"><h3>需要帮助？</h3><p>客服电话与微信同号</p><strong>17635575899</strong></section>
      </div>
    </section>`;
  document.body.appendChild(modal);
  document.body.classList.add('account-settings-open');
  modal.querySelectorAll('[data-account-close]').forEach(item => item.addEventListener('click', closeAccountSettingsModal));

  const showMessage = (id, text, success = false) => {
    const element = document.getElementById(id);
    if (element) { element.textContent = text; element.className = `account-form-msg ${success ? 'success' : 'error'}`; }
  };

  // 手机号：获取验证码（60 秒冷却）
  const sendBindCodeBtn = document.getElementById('sendBindCodeBtn');
  sendBindCodeBtn?.addEventListener('click', async () => {
    const phone = document.getElementById('accountPhone')?.value.trim() || '';
    if (!/^1[3-9]\d{9}$/.test(phone)) return showMessage('phoneMsg', '请输入有效的手机号');
    sendBindCodeBtn.disabled = true;
    try {
      const response = await fetch('/api/auth/sms/request', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, purpose: 'bind' })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || '验证码发送失败');
      showMessage('phoneMsg', data.message || '验证码已发送', true);
      let left = 60;
      const label = sendBindCodeBtn.textContent;
      sendBindCodeBtn.textContent = `${left}s`;
      const timer = setInterval(() => {
        left -= 1;
        if (left <= 0) { clearInterval(timer); sendBindCodeBtn.disabled = false; sendBindCodeBtn.textContent = label; }
        else { sendBindCodeBtn.textContent = `${left}s`; }
      }, 1000);
    } catch (error) {
      sendBindCodeBtn.disabled = false;
      showMessage('phoneMsg', error.message || '验证码发送失败');
    }
  });

  // 手机号：绑定 / 换绑
  document.getElementById('bindPhoneBtn')?.addEventListener('click', async () => {
    const phone = document.getElementById('accountPhone')?.value.trim() || '';
    const phoneCode = document.getElementById('accountPhoneCode')?.value.trim() || '';
    if (!/^1[3-9]\d{9}$/.test(phone)) return showMessage('phoneMsg', '请输入有效的手机号');
    if (!/^\d{6}$/.test(phoneCode)) return showMessage('phoneMsg', '请输入 6 位验证码');
    try {
      const response = await fetch('/api/auth/account', {
        method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ phone, phone_code: phoneCode })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) throw new Error(data.detail || data.error || '手机号绑定失败');
      showMessage('phoneMsg', '手机号绑定成功', true);
      setTimeout(() => { closeAccountSettingsModal(); loadProfile(); }, 700);
    } catch (error) { showMessage('phoneMsg', error.message || '手机号绑定失败'); }
  });

  document.getElementById('saveWechatBtn')?.addEventListener('click', async () => {
    const wechatId = document.getElementById('accountWechat')?.value.trim() || '';
    try {
      const response = await fetch('/api/auth/account', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ wechat_id: wechatId }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) throw new Error(data.detail || data.error || '微信号保存失败');
      showMessage('wechatMsg', '微信号已保存', true); setTimeout(() => { closeAccountSettingsModal(); loadProfile(); }, 700);
    } catch (error) { showMessage('wechatMsg', error.message || '微信号保存失败'); }
  });
  document.getElementById('changePasswordBtn')?.addEventListener('click', async () => {
    const currentPassword = document.getElementById('currentPassword')?.value || '';
    const newPassword = document.getElementById('newPassword')?.value || '';
    if (newPassword.length < 6) return showMessage('passwordMsg', '新密码至少 6 位');
    try {
      const response = await fetch('/api/auth/change-password', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) });
      const data = await response.json().catch(() => ({}));
      if (!response.ok || data.success === false) throw new Error(data.detail || data.error || '密码修改失败');
      showMessage('passwordMsg', '密码修改成功，即将退出重新登录', true); setTimeout(logoutAccount, 900);
    } catch (error) { showMessage('passwordMsg', error.message || '密码修改失败'); }
  });
}

async function submitProfileAssessment() {
  const current = state.profileAssessment.current;
  const allAnswered = current?.questions?.every(question => normalizeAnswerLetters(state.profileAssessment.answers[question.id]));
  if (!current || !allAnswered) return;
  const button = document.querySelector('[data-assessment-submit]');
  if (button) { button.disabled = true; button.textContent = '正在生成画像…'; }
  try {
    const response = await fetch('/user/profile-assessment/submit', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        assessment_id: current.id,
        answers: state.profileAssessment.answers,
        duration_seconds: Math.round((Date.now() - state.profileAssessment.startedAt) / 1000),
      }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '画像生成失败');
    try { localStorage.removeItem(profileAssessmentDraftKey(current.id)); } catch (_) {}
    try { localStorage.removeItem(profileAssessmentReminderKey()); } catch (_) {}
    const result = data.assessment?.result || {};
    const modal = document.getElementById('profileAssessmentModal');
    if (modal) modal.innerHTML = `
      <div class="profile-assessment-backdrop"></div>
      <section class="profile-assessment-result">
        <span>PROFILE READY</span><h2>你的初始学习画像已建立</h2>
        <strong>${Number(result.accuracy || 0).toFixed(1)}%</strong>
        <p>答对 ${result.correct_count || 0} / ${result.question_count || 40} 题。此后所有个性化分析都会同时依据本次测评和题库中的后续作答动态更新。</p>
        <div>${Object.entries(result.subjects || {}).map(([subject, item]) => `<article><span>${escapeHtml(subject)}</span><b>${Number(item.accuracy || 0).toFixed(1)}%</b><small>${item.correct}/${item.total}</small></article>`).join('')}</div>
        <button type="button" data-assessment-finish>查看完整画像</button>
      </section>`;
    modal?.querySelector('[data-assessment-finish]')?.addEventListener('click', async () => {
      closeProfileAssessment();
      await loadProfile();
    });
  } catch (error) {
    alert(error.message || '画像生成失败');
    if (button) { button.disabled = false; button.textContent = '提交并生成画像'; }
  }
}

// ========== 错题复习模式 ==========
async function startWrongBookReview() {
  const area = document.getElementById('dashReviewSessionArea');
  if (!area) return;
  area.style.display = 'block';
  area.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-secondary);">正在生成复习卷...</div>';

  try {
    const resp = await fetch('/wrong-book/review-session?count=5');
    const data = await resp.json();

    if (!data.questions || data.questions.length === 0) {
      area.innerHTML = '<div style="padding:16px;text-align:center;color:var(--text-secondary);">' + escapeHtml(data.message || '暂无待复习错题') + '</div>';
      return;
    }

    let currentIdx = 0;
    let correctCount = 0;

    function renderReviewQuestion(idx) {
      if (idx >= data.questions.length) {
        const pct = Math.round(correctCount / data.questions.length * 100);
        area.innerHTML = '<div style="padding:20px;text-align:center;">' +
          '<h3 style="margin:0 0 12px;">复习完成！</h3>' +
          '<div style="font-size:48px;font-weight:700;color:' + (pct >= 80 ? '#10b981' : pct >= 50 ? '#f59e0b' : '#ef4444') + ';">' + pct + '%</div>' +
          '<div style="color:var(--text-secondary);margin:8px 0;">正确 ' + correctCount + ' / ' + data.questions.length + '</div>' +
          '<div style="color:var(--text-secondary);font-size:13px;">剩余待复习：' + (data.remaining || 0) + ' 题</div>' +
          '<button onclick="document.getElementById(\'dashReviewSessionArea\').style.display=\'none\'" style="margin-top:16px;border:0;border-radius:10px;padding:10px 24px;background:var(--primary);color:#fff;cursor:pointer;">关闭</button>' +
          '</div>';
        return;
      }

      const q = data.questions[idx];
      const optionsHtml = (q.options || []).map(opt => {
        const label = opt.charAt(0);
        const text = opt.substring(2).trim();
        return '<div class="review-option" data-option="' + label + '" style="padding:10px 14px;border:1px solid #e5e7eb;border-radius:10px;cursor:pointer;margin-bottom:6px;transition:all 0.15s;">' +
          '<span style="font-weight:600;color:var(--primary);margin-right:8px;">' + label + '.</span>' +
          '<span>' + escapeHtml(text) + '</span></div>';
      }).join('');

      area.innerHTML = '<div style="border:1px solid #e5e7eb;border-radius:14px;padding:20px;background:#fff;">' +
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">' +
        '<span style="font-size:13px;color:var(--text-secondary);">第 ' + (idx+1) + ' / ' + data.questions.length + ' 题</span>' +
        '<span style="font-size:12px;background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:6px;">错 ' + (q.wrong_count || 1) + ' 次</span>' +
        '</div>' +
        '<div style="font-weight:600;font-size:15px;margin-bottom:12px;line-height:1.6;">' + escapeHtml(q.content || '题目内容缺失') + '</div>' +
        '<div style="margin-bottom:16px;">' + optionsHtml + '</div>' +
        '<div id="reviewFeedback" style="display:none;"></div>' +
        '<button id="reviewNextBtn" style="display:none;margin-top:12px;border:0;border-radius:10px;padding:10px 24px;background:var(--primary);color:#fff;cursor:pointer;">下一题</button>' +
        '</div>';

      let selected = false;
      area.querySelectorAll('.review-option').forEach(opt => {
        opt.addEventListener('click', async function() {
          if (selected) return;
          selected = true;
          const chosen = this.dataset.option;
          const correct = (q.correct_answer || '').charAt(0).toUpperCase();
          const isCorrect = chosen === correct;
          if (isCorrect) correctCount++;

          area.querySelectorAll('.review-option').forEach(o => {
            o.style.cursor = 'default';
            if (o.dataset.option === correct) {
              o.style.background = '#ecfdf5';
              o.style.borderColor = '#10b981';
            }
            if (o.dataset.option === chosen && !isCorrect) {
              o.style.background = '#fef2f2';
              o.style.borderColor = '#ef4444';
            }
          });

          const feedback = document.getElementById('reviewFeedback');
          feedback.style.display = 'block';
          if (isCorrect) {
            feedback.innerHTML = '<div style="color:#10b981;font-weight:600;">回答正确！</div>';
          } else {
            feedback.innerHTML = '<div style="color:#ef4444;font-weight:600;">回答错误，正确答案是 ' + correct + '</div>' +
              (q.explanation ? '<div style="color:var(--text-secondary);font-size:13px;margin-top:6px;line-height:1.5;">' + escapeHtml(q.explanation.slice(0, 300)) + '</div>' : '');
          }

          // 提交复习结果
          fetch('/wrong-book/review-submit', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ user_id: 'u1', question_id: q.question_id, is_correct: isCorrect })
          }).catch(e => console.warn('提交复习结果失败', e));

          document.getElementById('reviewNextBtn').style.display = 'inline-block';
          document.getElementById('reviewNextBtn').addEventListener('click', () => renderReviewQuestion(idx + 1));
        });
      });
    }

    renderReviewQuestion(0);
  } catch (error) {
    console.error('错题复习模式启动失败:', error);
    area.innerHTML = '<div style="padding:16px;text-align:center;color:#ef4444;">加载失败，请稍后重试。</div>';
  }
}

function masteryLevelLabel(level) {
  const labels = {
    mastered: '熟练',
    stable: '稳定',
    weak: '薄弱',
    danger: '危险'
  };
  return labels[level] || '待观察';
}

// ========== Knowledge Graph ==========
console.log('app.js loaded, version 2.0');

const kgState = {
  knowledgePoints: [],
  subjects: [],
  chapterInfo: {},
  nodes: [],
  links: [],
  selectedNode: null,
  filters: { subject: 'all', search: '' },
  subjectEnabled: { '数据结构': true, '计算机组成原理': true, '操作系统': true, '计算机网络': true },
  svg: null,
  simulation: null,
  zoomBehavior: null,
  mastery: {},
  subjectProgress: {},
  pinnedPositions: new Map(),
  resizeObserver: null,
  resizeTimer: null,
  lastGraphSize: { width: 0, height: 0 }
};

const knowledgeVisualState = { pointId: '', data: null, tab: 'structure', step: 0, timer: null, player: null };

function closeKnowledgeVisualization() {
  if (knowledgeVisualState.timer) window.clearInterval(knowledgeVisualState.timer);
  knowledgeVisualState.timer = null;
  knowledgeVisualState.player?.destroy();
  knowledgeVisualState.player = null;
  document.getElementById('knowledgeVisualModal')?.classList.add('hidden');
}

async function openKnowledgeVisualization(pointId) {
  if (!pointId) return;
  const modal = document.getElementById('knowledgeVisualModal');
  const body = document.getElementById('knowledgeVisualBody');
  knowledgeVisualState.pointId = pointId;
  knowledgeVisualState.data = null;
  knowledgeVisualState.tab = 'structure';
  knowledgeVisualState.step = 0;
  modal?.classList.remove('hidden');
  if (body) body.innerHTML = '<div class="knowledge-visual-loading">正在建立知识结构、过程与个人练习路径…</div>';
  document.querySelectorAll('[data-knowledge-visual-tab]').forEach(button => button.classList.toggle('active', button.dataset.knowledgeVisualTab === 'structure'));
  try {
    const response = await fetch(`/kg/point/${encodeURIComponent(pointId)}/visualization`);
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || '知识点可视化加载失败');
    knowledgeVisualState.data = data;
    document.getElementById('knowledgeVisualTitle').textContent = data.point.title;
    document.getElementById('knowledgeVisualMeta').textContent = `${data.point.subject} · ${data.point.chapter_title}`;
    renderKnowledgeVisualTab();
  } catch (error) {
    if (body) body.innerHTML = `<div class="knowledge-visual-empty">${escapeHtml(error.message || '加载失败，请稍后重试')}</div>`;
  }
}

function renderKnowledgeVisualTab() {
  const body = document.getElementById('knowledgeVisualBody');
  const data = knowledgeVisualState.data;
  if (!body || !data) return;
  if (knowledgeVisualState.timer) window.clearInterval(knowledgeVisualState.timer);
  knowledgeVisualState.timer = null;
  knowledgeVisualState.player?.destroy();
  knowledgeVisualState.player = null;
  if (knowledgeVisualState.tab === 'structure') renderKnowledgeStructure(body, data);
  else if (knowledgeVisualState.tab === 'process') renderKnowledgeProcess(body, data);
  else if (knowledgeVisualState.tab === 'simulator') renderKnowledgeSimulator(body, data);
  else renderKnowledgePersonal(body, data);
}

function knowledgeRelationHtml(title, items, emptyText) {
  return `<section class="kv-relation-group"><h4>${escapeHtml(title)}</h4><div>${items.length ? items.map(item => `<button type="button" data-related-point="${escapeHtml(item.id)}">${escapeHtml(item.title)}</button>`).join('') : `<span>${escapeHtml(emptyText)}</span>`}</div></section>`;
}

function knowledgeCrossRelationHtml(items) {
  return `<section class="kv-cross-relations"><h4>跨科同构关系</h4>${items.length ? items.map(item => `<button type="button" data-related-point="${escapeHtml(item.id)}"><span>${escapeHtml(item.subject)} · ${escapeHtml(item.theme || '机制关联')}</span><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.explanation || '')}</p></button>`).join('') : '<p>暂无跨科机制关联</p>'}</section>`;
}

function renderKnowledgeStructure(body, data) {
  const structure = data.structure;
  const mission = data.learning_mission || { goals: [], success_criteria: [], check: null };
  const check = mission.check;
  body.innerHTML = `
    <div class="kv-structure-map">
      <section class="kv-mission-hero">
        <div><span>本次学习不是“看完”，而是做到</span><h3>${escapeHtml(data.point.title)}</h3><ul>${mission.goals.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ul></div>
        <div class="kv-success"><b>通过标准</b>${mission.success_criteria.map((item, index) => `<p><span>${index + 1}</span>${escapeHtml(item)}</p>`).join('')}</div>
      </section>
      ${check ? `<section class="kv-precheck" data-kv-precheck><div><span>先做判断 · 再学概念</span><h3>${escapeHtml(check.stem)}</h3></div><div class="kv-precheck-options">${check.options.length ? check.options.map(option => { const label = String(option).trim().charAt(0); return `<button type="button" data-kv-check-option="${escapeHtml(label)}"><b>${escapeHtml(label)}</b>${escapeHtml(String(option).replace(/^[A-Z][.、]\s*/, ''))}</button>`; }).join('') : '<button type="button" class="kv-recall-reveal" data-kv-recall-reveal>我已口述，查看参考要点</button>'}</div><div class="kv-precheck-feedback hidden" data-kv-check-feedback></div></section>` : ''}
      <section class="kv-definition"><span>核心定义</span><h3>一句话抓住本质</h3><p>${escapeHtml(structure.definition)}</p></section>
      <div class="kv-structure-line"></div>
      <section class="kv-reasoning-grid">
        ${structure.analogy ? `<article><span>先建立直觉</span><h4>它像什么？</h4><p>${escapeHtml(structure.analogy)}</p></article>` : ''}
        <article><span>再掌握规则</span><h4>解题时看什么？</h4><ol>${structure.components.map(item => `<li>${escapeHtml(item)}</li>`).join('')}</ol></article>
        ${structure.common_trap ? `<article class="danger"><span>最后排除陷阱</span><h4>最容易错在哪里？</h4><p>${escapeHtml(structure.common_trap)}</p></article>` : ''}
      </section>
      <div class="kv-relation-grid">
        ${knowledgeRelationHtml('前置知识', structure.prerequisites, '这是该路径的起点')}
        ${knowledgeRelationHtml('关联知识', structure.related, '暂无同章关联')}
        ${knowledgeCrossRelationHtml(structure.cross_subject)}
      </div>
      <section class="kv-confusion"><h4>易混关系</h4>${structure.confusions.length ? structure.confusions.map(item => `<div><b>${escapeHtml(item.left)}</b><span>对比</span><b>${escapeHtml(item.right)}</b></div>`).join('') : '<p>当前知识点以独立概念掌握为主。</p>'}</section>
      ${structure.exam_direction ? `<section class="kv-exam-direction"><b>真题会怎么考</b><p>${escapeHtml(structure.exam_direction)}</p></section>` : ''}
    </div>`;
  body.querySelectorAll('[data-related-point]').forEach(button => button.addEventListener('click', () => openKnowledgeVisualization(button.dataset.relatedPoint)));
  body.querySelectorAll('[data-kv-check-option]').forEach(button => button.addEventListener('click', () => {
    const selected = button.dataset.kvCheckOption;
    const correct = String(check.answer || '').toUpperCase().includes(selected.toUpperCase());
    body.querySelectorAll('[data-kv-check-option]').forEach(item => { item.disabled = true; item.classList.toggle('selected-correct', String(check.answer || '').toUpperCase().includes(item.dataset.kvCheckOption.toUpperCase())); item.classList.toggle('selected-wrong', item === button && !correct); });
    const feedback = body.querySelector('[data-kv-check-feedback]');
    feedback?.classList.remove('hidden');
    if (feedback) feedback.innerHTML = `<strong>${correct ? '判断正确：现在解释为什么' : `这次选了 ${escapeHtml(selected)}，正确答案是 ${escapeHtml(check.answer)}`}</strong><p>${escapeHtml(check.analysis || '请回到核心定义，逐项核对条件。')}</p>`;
  }));
  body.querySelector('[data-kv-recall-reveal]')?.addEventListener('click', event => {
    event.currentTarget.disabled = true;
    const feedback = body.querySelector('[data-kv-check-feedback]');
    feedback?.classList.remove('hidden');
    if (feedback) feedback.innerHTML = `<strong>参考要点：${escapeHtml(check.answer)}</strong><p>${escapeHtml(check.analysis)}</p>`;
  });
}

function renderKnowledgeProcess(body, data) {
  const process = data.process;
  if (!process.available) {
    body.innerHTML = '<div class="knowledge-visual-empty"><b>该知识点属于概念理解型</b><span>建议使用结构图与易混关系学习，不强行生成没有真实状态变化的动画。</span></div>';
    return;
  }
  const snapshots = process.stages.map(stage => ({ ...stage, desc: stage.title }));
  body.innerHTML = '<div class="kv-process-lab" data-kv-process-player></div>';
  knowledgeVisualState.player = createStepPlayer(
    body.querySelector('[data-kv-process-player]'), snapshots,
    (stage, current) => `<div class="kv-process-focus"><small>当前阶段 ${current + 1} / ${snapshots.length}</small><strong>${escapeHtml(stage.title)}</strong><div class="kv-state-change"><article><span>输入状态</span><p>${escapeHtml(stage.input)}</p></article><i>→</i><article><span>执行规则</span><p>${escapeHtml(stage.title)}</p></article><i>→</i><article><span>输出状态</span><p>${escapeHtml(stage.output)}</p></article></div><section class="kv-stage-check"><b>${escapeHtml(stage.question)}</b><details><summary>先口答，再看提示</summary><p>${escapeHtml(stage.answer)}</p></details></section></div>`,
    { label: `${data.point.title}过程演示`, initialStep: knowledgeVisualState.step, onStep: index => { knowledgeVisualState.step = index; } }
  );
}

function simulatorFormHtml(simulator) {
  const d = simulator.defaults;
  const predictionPrompts = {
    sorting: ['先预测排序过程', '例如：序列接近有序时，插入排序的移动次数会减少，因为……'],
    page_replacement: ['先预测缺页变化', '例如：页框增加后，LRU 的缺页次数可能会减少，因为……'],
    scheduling: ['先预测调度结果', '例如：改用 SJF 后，平均等待时间会下降，因为……'],
    cache: ['先预测地址划分', '例如：块大小翻倍后，块内偏移位数会增加 1，因为……'],
    number: ['先预测编码结果', '例如：负数采用补码表示时，需要按位取反后加 1，因为……'],
    subnet: ['先预测子网范围', '例如：前缀长度增加 1 后，可用主机数大约减半，因为……'],
    pipeline: ['先预测流水线性能', '例如：缩短最慢流水段后，流水周期会缩短，因为……'],
    stack_queue: ['先预测输出顺序', '例如：相同元素依次进入栈后，输出顺序会反转，因为……']
  };
  const predictionPrompt = predictionPrompts[simulator.type] || ['先写下你的预测', '写下参数变化后，结果会如何变化，并说明原因……'];
  const fields = {
    sorting: `<label>待排序序列<input name="sequence" value="${escapeHtml(d.sequence)}"></label><label>算法<select name="algorithm"><option value="bubble">冒泡</option><option value="insertion">插入</option><option value="selection">选择</option></select></label>`,
    page_replacement: `<label>访问序列<input name="references" value="${escapeHtml(d.references)}"></label><label>页框数<input name="frames" type="number" min="1" max="8" value="${d.frames}"></label><label>算法<select name="algorithm"><option>LRU</option><option>FIFO</option><option>OPT</option></select></label>`,
    scheduling: `<label>运行时间<input name="bursts" value="${escapeHtml(d.bursts)}"></label><label>算法<select name="algorithm"><option>SJF</option><option>FCFS</option><option>RR</option></select></label><label>时间片<input name="quantum" type="number" min="1" value="${d.quantum}"></label>`,
    cache: `<label>主存地址<input name="address" type="number" min="0" value="${d.address}"></label><label>Cache 行数<input name="lines" type="number" min="1" value="${d.lines}"></label><label>路数<input name="ways" type="number" min="1" value="${d.ways}"></label><label>块大小/B<input name="block_size" type="number" min="1" value="${d.block_size}"></label>`,
    number: `<label>十进制数<input name="value" type="number" value="${d.value}"></label><label>位宽<input name="bits" type="number" min="4" max="32" value="${d.bits}"></label>`,
    subnet: `<label>IP 地址<input name="ip" value="${escapeHtml(d.ip)}"></label><label>前缀长度<input name="prefix" type="number" min="0" max="32" value="${d.prefix}"></label>`,
    pipeline: `<label>各段耗时<input name="durations" value="${escapeHtml(d.durations)}"></label><label>指令条数<input name="instructions" type="number" min="1" max="10000" value="${d.instructions}"></label>`,
    stack_queue: `<label>输入元素<input name="values" value="${escapeHtml(d.values)}"></label><label>结构<select name="structure"><option value="stack">栈</option><option value="queue">队列</option></select></label>`
  };
  return `<form class="kv-simulator-form" data-kv-simulator="${escapeHtml(simulator.type)}"><label class="kv-prediction">${escapeHtml(predictionPrompt[0])}<input name="prediction" placeholder="${escapeHtml(predictionPrompt[1])}"></label>${fields[simulator.type] || ''}<button type="submit">验证我的预测</button></form><div class="kv-simulator-output"><div class="kv-await-prediction"><b>先预测，再运行</b><span>只有把结果和自己的判断对照，模拟器才会帮助形成可迁移的解题能力。</span></div></div>`;
}

function kvNumberList(value) {
  return String(value || '').split(/[，,\s]+/).map(Number).filter(Number.isFinite).slice(0, 80);
}

function kvTextList(value) {
  return String(value || '').split(/[，,\s]+/).map(item => item.trim()).filter(Boolean).slice(0, 80);
}

function kvMetric(label, value, note = '') {
  return `<div class="kv-metric"><span>${escapeHtml(label)}</span><strong>${escapeHtml(String(value))}</strong>${note ? `<small>${escapeHtml(note)}</small>` : ''}</div>`;
}

function kvArrayRow(label, values, active = -1) {
  return `<div class="kv-array-row"><b>${escapeHtml(label)}</b><div>${values.map((value, index) => `<span class="${index === active ? 'active' : ''}">${escapeHtml(String(value))}</span>`).join('')}</div></div>`;
}

function renderSimulatorStepPlayer(output, metrics, snapshots, renderSnapshot, label) {
  knowledgeVisualState.player?.destroy();
  output.innerHTML = `${metrics}<div class="kv-snapshot-player" data-kv-snapshot-player></div>`;
  knowledgeVisualState.player = createStepPlayer(
    output.querySelector('[data-kv-snapshot-player]'), snapshots, renderSnapshot,
    { label, initialStep: 0 }
  );
}

function sortingSnapshotMarkup(snapshot) {
  const maxValue = Math.max(...snapshot.values.map(value => Math.abs(value)), 1);
  return `<div class="visual-sort-lab"><div class="visual-sort-array">${snapshot.values.map((value, index) => `<div class="visual-sort-column ${snapshot.active.includes(index) ? 'active' : ''} ${snapshot.sorted.includes(index) ? 'sorted' : ''}"><span style="height:${Math.max(18, Math.abs(value) / maxValue * 112)}px"></span><b>${escapeHtml(value)}</b><small>${index}</small></div>`).join('')}</div></div>`;
}

function runSortingSimulator(form, output) {
  const values = kvNumberList(form.elements.sequence.value);
  const algorithm = form.elements.algorithm.value;
  if (!values.length) throw new Error('请输入至少一个数字');
  const array = [...values];
  const snapshots = [{ values: [...array], active: [], sorted: [], desc: '记录初始序列。' }];
  let comparisons = 0;
  let swaps = 0;
  if (algorithm === 'insertion') {
    for (let i = 1; i < array.length; i += 1) {
      const key = array[i]; let j = i - 1;
      snapshots.push({ values: [...array], active: [i], sorted: Array.from({ length: i }, (_, k) => k), desc: `取出 ${key}，准备插入前面的有序区。` });
      while (j >= 0) {
        comparisons += 1;
        snapshots.push({ values: [...array], active: [j, j + 1], sorted: Array.from({ length: i }, (_, k) => k), desc: `比较 ${array[j]} 与待插入元素 ${key}。` });
        if (array[j] <= key) break;
        array[j + 1] = array[j]; swaps += 1; j -= 1;
        snapshots.push({ values: [...array], active: [j + 1, j + 2], sorted: Array.from({ length: i + 1 }, (_, k) => k), desc: '较大元素右移一个位置。' });
      }
      array[j + 1] = key;
      snapshots.push({ values: [...array], active: [j + 1], sorted: Array.from({ length: i + 1 }, (_, k) => k), desc: `把 ${key} 插入下标 ${j + 1}。` });
    }
  } else if (algorithm === 'selection') {
    for (let i = 0; i < array.length - 1; i += 1) {
      let minimum = i;
      for (let j = i + 1; j < array.length; j += 1) {
        comparisons += 1;
        snapshots.push({ values: [...array], active: [minimum, j], sorted: Array.from({ length: i }, (_, k) => k), desc: `比较当前最小值 ${array[minimum]} 与 ${array[j]}。` });
        if (array[j] < array[minimum]) minimum = j;
      }
      if (minimum !== i) {
        [array[i], array[minimum]] = [array[minimum], array[i]]; swaps += 1;
        snapshots.push({ values: [...array], active: [i, minimum], sorted: Array.from({ length: i + 1 }, (_, k) => k), desc: `交换下标 ${i} 与 ${minimum}，扩展有序区。` });
      }
    }
  } else {
    for (let end = array.length - 1; end > 0; end -= 1) {
      let changed = false;
      for (let i = 0; i < end; i += 1) {
        comparisons += 1;
        snapshots.push({ values: [...array], active: [i, i + 1], sorted: Array.from({ length: array.length - end - 1 }, (_, k) => end + 1 + k), desc: `比较 ${array[i]} 与 ${array[i + 1]}。` });
        if (array[i] > array[i + 1]) {
          [array[i], array[i + 1]] = [array[i + 1], array[i]]; swaps += 1; changed = true;
          snapshots.push({ values: [...array], active: [i, i + 1], sorted: Array.from({ length: array.length - end - 1 }, (_, k) => end + 1 + k), desc: '左侧元素更大，交换相邻元素。' });
        }
      }
      snapshots.push({ values: [...array], active: [end], sorted: Array.from({ length: array.length - end }, (_, k) => end + k), desc: `下标 ${end} 已归位。` });
      if (!changed) break;
    }
  }
  snapshots.push({ values: [...array], active: [], sorted: array.map((_, index) => index), desc: '排序完成，所有元素均已归位。' });
  const metrics = `<div class="kv-metric-grid">${kvMetric('比较次数', comparisons)}${kvMetric('移动/交换', swaps)}${kvMetric('快照数', snapshots.length)}</div>`;
  renderSimulatorStepPlayer(output, metrics, snapshots, sortingSnapshotMarkup, '排序算法逐步演示');
}

function runPageSimulator(form, output) {
  const refs = kvTextList(form.elements.references.value);
  const capacity = Math.max(1, Math.min(8, Number(form.elements.frames.value) || 3));
  const algorithm = form.elements.algorithm.value;
  if (!refs.length) throw new Error('请输入页面访问序列');
  let frames = []; let faults = 0; let fifo = 0; const lastUsed = new Map();
  const snapshots = [{ page: null, hit: null, evicted: null, faults: 0, frames: [], desc: '页框为空，准备读取访问序列。' }];
  refs.forEach((page, index) => {
    const hit = frames.includes(page);
    let evicted = null;
    if (!hit) {
      faults += 1;
      if (frames.length < capacity) frames.push(page);
      else if (algorithm === 'FIFO') { evicted = frames[fifo % capacity]; frames[fifo % capacity] = page; fifo += 1; }
      else if (algorithm === 'OPT') {
        const nextUses = frames.map(item => { const next = refs.slice(index + 1).indexOf(item); return next < 0 ? Infinity : next; });
        const victimIndex = nextUses.indexOf(Math.max(...nextUses)); evicted = frames[victimIndex]; frames[victimIndex] = page;
      } else {
        const victim = frames.reduce((oldest, item) => (lastUsed.get(item) ?? -1) < (lastUsed.get(oldest) ?? -1) ? item : oldest, frames[0]);
        evicted = victim; frames[frames.indexOf(victim)] = page;
      }
    }
    lastUsed.set(page, index);
    snapshots.push({ page, hit, evicted, faults, frames: [...frames], referenceIndex: index, desc: hit ? `访问页面 ${page}：已在页框中，命中。` : `访问页面 ${page}：发生缺页${evicted === null ? '，装入空闲页框' : `，淘汰页面 ${evicted}`}。` });
  });
  const metrics = `<div class="kv-metric-grid">${kvMetric('缺页次数', faults)}${kvMetric('命中次数', refs.length - faults)}${kvMetric('缺页率', `${(faults / refs.length * 100).toFixed(1)}%`)}</div>`;
  renderSimulatorStepPlayer(output, metrics, snapshots, snapshot => `<div class="visual-page-lab"><div class="visual-reference-strip">${refs.map((page, index) => `<span class="${index === snapshot.referenceIndex ? 'active' : ''} ${index < (snapshot.referenceIndex ?? -1) ? 'visited' : ''}">${escapeHtml(page)}</span>`).join('')}</div><div class="visual-frame-stack">${Array.from({ length: capacity }, (_, index) => `<div><small>页框 ${index + 1}</small><b>${escapeHtml(snapshot.frames[index] ?? '空')}</b></div>`).join('')}</div><div class="visual-sim-result"><span>本次</span><b class="${snapshot.hit === null ? '' : snapshot.hit ? 'is-hit' : 'is-fault'}">${snapshot.hit === null ? '待访问' : snapshot.hit ? '命中' : '缺页'}</b><span>累计缺页</span><b>${snapshot.faults}</b>${snapshot.evicted !== null ? `<span>淘汰</span><b>${escapeHtml(snapshot.evicted)}</b>` : ''}</div></div>`, '页面置换逐步演示');
}

function schedulingTimeline(bursts, algorithm, quantum) {
  const jobs = bursts.map((burst, index) => ({ id: `P${index + 1}`, burst, remaining: burst, finish: 0 }));
  const timeline = []; let time = 0;
  const order = algorithm === 'SJF' ? [...jobs].sort((a, b) => a.burst - b.burst) : [...jobs];
  if (algorithm !== 'RR') order.forEach(job => { timeline.push({ id: job.id, start: time, duration: job.burst }); time += job.burst; job.finish = time; });
  else {
    const queue = [...jobs];
    while (queue.length) { const job = queue.shift(); const duration = Math.min(quantum, job.remaining); timeline.push({ id: job.id, start: time, duration }); time += duration; job.remaining -= duration; if (job.remaining) queue.push(job); else job.finish = time; }
  }
  return { jobs, timeline, total: time };
}

function runSchedulingSimulator(form, output) {
  const bursts = kvNumberList(form.elements.bursts.value).map(value => Math.max(1, Math.round(value)));
  const algorithm = form.elements.algorithm.value;
  const quantum = Math.max(1, Number(form.elements.quantum.value) || 2);
  if (!bursts.length) throw new Error('请输入进程运行时间');
  const result = schedulingTimeline(bursts, algorithm, quantum);
  const avgTurnaround = result.jobs.reduce((sum, job) => sum + job.finish, 0) / result.jobs.length;
  const avgWait = result.jobs.reduce((sum, job) => sum + job.finish - job.burst, 0) / result.jobs.length;
  const snapshots = [{ timeline: [], time: 0, desc: '调度开始，等待选择第一个进程。' }];
  result.timeline.forEach((_, index) => {
    const timeline = result.timeline.slice(0, index + 1);
    const active = timeline[timeline.length - 1];
    snapshots.push({ timeline, time: active.start + active.duration, desc: `运行 ${active.id}：${active.start}～${active.start + active.duration}，持续 ${active.duration} 个时间单位。` });
  });
  const metrics = `<div class="kv-metric-grid">${kvMetric('总用时', result.total)}${kvMetric('平均周转', avgTurnaround.toFixed(2))}${kvMetric('平均等待', avgWait.toFixed(2))}</div>`;
  renderSimulatorStepPlayer(output, metrics, snapshots, snapshot => `<div><div class="kv-gantt">${snapshot.timeline.length ? snapshot.timeline.map(item => `<div style="flex:${item.duration}" title="${item.start}–${item.start + item.duration}"><b>${item.id}</b><small>${item.duration}</small></div>`).join('') : '<span class="kv-gantt-empty">等待调度</span>'}</div><div class="kv-gantt-axis"><span>0</span><span>${snapshot.time}</span></div></div>`, '进程调度甘特图逐步演示');
}

function runCacheSimulator(form, output) {
  const address = Math.max(0, Math.floor(Number(form.elements.address.value) || 0));
  const lines = Math.max(1, Math.floor(Number(form.elements.lines.value) || 1));
  const ways = Math.max(1, Math.min(lines, Math.floor(Number(form.elements.ways.value) || 1)));
  const blockSize = Math.max(1, Math.floor(Number(form.elements.block_size.value) || 1));
  const groups = Math.max(1, Math.floor(lines / ways)); const block = Math.floor(address / blockSize);
  const offset = address % blockSize; const group = block % groups; const tag = Math.floor(block / groups);
  output.innerHTML = `<div class="kv-metric-grid">${kvMetric('主存块号', block)}${kvMetric('映射组号', group)}${kvMetric('块内偏移', offset)}${kvMetric('标记 Tag', tag)}</div><div class="kv-formula">地址 ${address} = <b>Tag ${tag}</b> ｜ <b>组 ${group}</b> ｜ <b>偏移 ${offset}</b><small>${lines} 行 ÷ ${ways} 路 = ${groups} 组</small></div>`;
}

function runNumberSimulator(form, output) {
  const bits = Math.max(4, Math.min(32, Math.floor(Number(form.elements.bits.value) || 8)));
  const value = Math.trunc(Number(form.elements.value.value) || 0); const min = -(2 ** (bits - 1)); const max = 2 ** (bits - 1) - 1;
  if (value < min || value > max) throw new Error(`${bits} 位补码范围是 ${min}～${max}`);
  const encoded = value < 0 ? 2 ** bits + value : value; const binary = encoded.toString(2).padStart(bits, '0');
  output.innerHTML = `<div class="kv-metric-grid">${kvMetric('十进制', value)}${kvMetric('十六进制', `0x${encoded.toString(16).toUpperCase()}`)}${kvMetric('表示范围', `${min}～${max}`)}</div><div class="kv-bit-row">${binary.split('').map((bit, index) => `<span class="${index === 0 ? 'sign' : ''}"><b>${bit}</b><small>${index === 0 ? '符号' : bits - index - 1}</small></span>`).join('')}</div>`;
}

function ipv4ToInt(ip) {
  const parts = String(ip).trim().split('.').map(Number);
  if (parts.length !== 4 || parts.some(part => !Number.isInteger(part) || part < 0 || part > 255)) throw new Error('请输入合法 IPv4 地址');
  return parts.reduce((value, part) => value * 256 + part, 0) >>> 0;
}

function intToIpv4(value) { return [24, 16, 8, 0].map(shift => (value >>> shift) & 255).join('.'); }

function runSubnetSimulator(form, output) {
  const ip = ipv4ToInt(form.elements.ip.value); const prefix = Math.max(0, Math.min(32, Number(form.elements.prefix.value) || 0));
  const mask = prefix === 0 ? 0 : (0xFFFFFFFF << (32 - prefix)) >>> 0; const network = (ip & mask) >>> 0; const broadcast = (network | (~mask >>> 0)) >>> 0;
  const usable = prefix <= 30 ? Math.max(0, broadcast - network - 1) : prefix === 31 ? 2 : 1;
  const binary = ip.toString(2).padStart(32, '0');
  output.innerHTML = `<div class="kv-metric-grid">${kvMetric('网络地址', intToIpv4(network))}${kvMetric('广播地址', intToIpv4(broadcast))}${kvMetric('可用地址数', usable)}${kvMetric('掩码', intToIpv4(mask))}</div><div class="kv-ip-bits">${binary.split('').map((bit, index) => `<i class="${index < prefix ? 'network' : 'host'}">${bit}</i>`).join('')}</div><div class="kv-legend"><span>网络位 ${prefix}</span><span>主机位 ${32 - prefix}</span></div>`;
}

function runPipelineSimulator(form, output) {
  const durations = kvNumberList(form.elements.durations.value).map(value => Math.max(0.01, value)); const instructions = Math.max(1, Math.floor(Number(form.elements.instructions.value) || 1));
  if (!durations.length) throw new Error('请输入各流水段耗时');
  const cycle = Math.max(...durations); const first = durations.reduce((sum, value) => sum + value, 0); const total = first + (instructions - 1) * cycle; const sequential = first * instructions;
  const visibleInstructions = Math.min(instructions, 8);
  const maxCycle = durations.length + visibleInstructions - 1;
  const snapshots = Array.from({ length: maxCycle + 1 }, (_, currentCycle) => ({
    currentCycle,
    desc: currentCycle === 0 ? '流水线尚未启动。' : `时钟周期 ${currentCycle}：观察各条指令所在的流水段。`
  }));
  const metrics = `<div class="kv-metric-grid">${kvMetric('流水周期', cycle)}${kvMetric('首条完成', first)}${kvMetric('全部完成', total)}${kvMetric('加速比', (sequential / total).toFixed(2))}</div>`;
  renderSimulatorStepPlayer(output, metrics, snapshots, snapshot => `<div class="visual-pipeline-lab"><div class="visual-pipeline-grid" style="--cycles:${maxCycle}">${Array.from({ length: visibleInstructions }, (_, instruction) => `<div class="visual-pipeline-row"><b>I${instruction + 1}</b>${Array.from({ length: maxCycle }, (_, cycleIndex) => { const stage = cycleIndex - instruction; const filled = stage >= 0 && stage < durations.length && cycleIndex < snapshot.currentCycle; const active = filled && cycleIndex === snapshot.currentCycle - 1; return `<span class="${filled ? 'filled' : ''} ${active ? 'active' : ''}">${filled ? `S${stage + 1}` : ''}</span>`; }).join('')}</div>`).join('')}</div><p class="kv-explain">首条时间 ${first} +（${instructions}−1）× 周期 ${cycle} = ${total}</p></div>`, '指令流水线逐周期演示');
}

function runStackQueueSimulator(form, output) {
  const values = kvTextList(form.elements.values.value); const structure = form.elements.structure.value;
  if (!values.length) throw new Error('请输入操作元素');
  const result = structure === 'stack' ? [...values].reverse() : [...values];
  const snapshots = [{ items: [], output: [], active: '', desc: `${structure === 'stack' ? '栈' : '队列'}初始为空。` }];
  const items = [];
  values.forEach(value => { items.push(value); snapshots.push({ items: [...items], output: [], active: value, desc: `${structure === 'stack' ? '入栈' : '入队'}元素 ${value}。` }); });
  const emitted = [];
  result.forEach(value => {
    if (structure === 'stack') items.pop(); else items.shift();
    emitted.push(value);
    snapshots.push({ items: [...items], output: [...emitted], active: value, desc: `${structure === 'stack' ? '出栈' : '出队'}元素 ${value}。` });
  });
  const metrics = `<div class="kv-metric-grid">${kvMetric('结构', structure === 'stack' ? '栈 LIFO' : '队列 FIFO')}${kvMetric('操作次数', values.length * 2)}${kvMetric('输出顺序', result.join(' → '))}</div>`;
  renderSimulatorStepPlayer(output, metrics, snapshots, snapshot => `<div><div class="kv-container-demo ${structure}">${snapshot.items.length ? snapshot.items.map(value => `<span class="${value === snapshot.active ? 'active' : ''}">${escapeHtml(value)}</span>`).join('') : '<em>空</em>'}</div><p class="kv-explain">已输出：${snapshot.output.length ? escapeHtml(snapshot.output.join(' → ')) : '—'}</p></div>`, '栈与队列操作逐步演示');
}

function runKnowledgeSimulator(form) {
  const output = form.parentElement.querySelector('.kv-simulator-output');
  if (!output) return;
  try {
    const prediction = String(form.elements.prediction?.value || '').trim();
    if (!prediction) throw new Error('请先写下预测，再验证结果');
    const runners = { sorting: runSortingSimulator, page_replacement: runPageSimulator, scheduling: runSchedulingSimulator, cache: runCacheSimulator, number: runNumberSimulator, subnet: runSubnetSimulator, pipeline: runPipelineSimulator, stack_queue: runStackQueueSimulator };
    const runner = runners[form.dataset.kvSimulator];
    if (!runner) throw new Error('当前模拟器尚未配置');
    runner(form, output);
    const transfer = {
      sorting: '不要只看最终序列；把比较次数和移动次数与初始有序程度联系起来。',
      page_replacement: '逐列核对“命中/缺页”，再比较算法或页框数改变后的总缺页次数。',
      scheduling: '先读甘特图得到完成时间，再计算周转与等待；不要直接套平均数。',
      cache: '地址划分必须从块内偏移开始，再算组号，剩余高位才是 Tag。',
      number: '位模式不变，解释方式可以改变；最后务必检查位宽允许的数值范围。',
      subnet: '网络位由前缀固定，主机位全 0/全 1 分别对应网络地址和广播地址。',
      pipeline: '吞吐率由最慢流水段限制，缩短非瓶颈段只会影响首条时间，不一定改变周期。',
      stack_queue: '判断输出顺序前先明确操作端：栈同端进出，队列一端进另一端出。',
    }[form.dataset.kvSimulator] || '';
    output.insertAdjacentHTML('beforeend', `<section class="kv-prediction-review"><span>你的预测</span><p>${escapeHtml(prediction)}</p><b>对照结果时检查</b><p>${escapeHtml(transfer)}</p></section>`);
  } catch (error) { output.innerHTML = `<div class="kv-simulator-error">${escapeHtml(error.message || '参数无法计算')}</div>`; }
}

function renderKnowledgeSimulator(body, data) {
  const simulator = data.simulator;
  if (!simulator.available) {
    body.innerHTML = '<div class="knowledge-visual-empty"><b>该知识点暂不适合参数模拟</b><span>定义、分类和辨析型内容请使用结构图；只有结果会随参数变化的算法与机制才进入动态实验。</span></div>';
    return;
  }
  body.innerHTML = `<div class="kv-simulator-lab"><div class="kv-section-intro"><span>可调参数实验</span><h3>${escapeHtml(simulator.title)}</h3><p>不要先看答案。修改一个变量、写下预测，再用确定性算法验证因果关系。</p></div><section class="kv-lab-challenge"><b>本次实验挑战</b><p>${escapeHtml(simulator.challenge || '')}</p></section>${simulatorFormHtml(simulator)}</div>`;
  const form = body.querySelector('.kv-simulator-form');
  form?.addEventListener('submit', event => { event.preventDefault(); runKnowledgeSimulator(form); });
}

function renderKnowledgePersonal(body, data) {
  const personal = data.personalization; const score = Math.max(0, Math.min(100, Number(personal.mastery_score || 0)));
  body.innerHTML = `<div class="kv-personal-grid"><section class="kv-personal-summary"><div class="kv-mastery-ring" style="--mastery:${score}"><strong>${score.toFixed(0)}%</strong><span>当前掌握度</span></div><div><span>本用户专属分析</span><h3>${personal.wrong_count ? `优先修复 ${personal.wrong_count} 道错题` : '从关联真题开始检验'}</h3><p>${escapeHtml(personal.recommendation)}</p></div></section><section class="kv-metric-grid">${kvMetric('已练题目', personal.attempted)}${kvMetric('关联题目', personal.total_questions)}${kvMetric('相关错题', personal.wrong_count)}</section><section class="kv-personal-questions"><div class="kv-section-intro"><span>关联真题与练习</span><h3>用题目验证是否真正掌握</h3></div>${personal.questions.length ? personal.questions.map((question, index) => `<button type="button" data-kv-question="${index}" class="${question.is_wrong ? 'wrong' : ''}"><span>${question.is_wrong ? '错题优先' : (question.year || '练习题')}</span><p>${escapeHtml(question.content)}</p><b>进入作答 →</b></button>`).join('') : '<div class="knowledge-visual-empty"><span>该知识点暂未关联题目，可先完成结构与过程学习。</span></div>'}</section></div>`;
  body.querySelectorAll('[data-kv-question]').forEach(button => button.addEventListener('click', () => {
    const question = personal.questions[Number(button.dataset.kvQuestion)];
    if (!question) return;
    closeKnowledgeVisualization();
    switchView('question-bank-detail');
    openQuestion(question);
  }));
}

function initKnowledgeVisualization() {
  document.querySelectorAll('[data-knowledge-visual-close]').forEach(element => element.addEventListener('click', closeKnowledgeVisualization));
  document.querySelectorAll('[data-knowledge-visual-tab]').forEach(button => button.addEventListener('click', () => {
    knowledgeVisualState.tab = button.dataset.knowledgeVisualTab; knowledgeVisualState.step = 0;
    document.querySelectorAll('[data-knowledge-visual-tab]').forEach(item => item.classList.toggle('active', item === button)); renderKnowledgeVisualTab();
  }));
  document.addEventListener('keydown', event => { if (event.key === 'Escape' && !document.getElementById('knowledgeVisualModal')?.classList.contains('hidden')) closeKnowledgeVisualization(); });
}

document.addEventListener('DOMContentLoaded', initKnowledgeVisualization);

const subjectColors = {
  '数据结构': '#6366f1',
  '计算机组成原理': '#10b981',
  '操作系统': '#f59e0b',
  '计算机网络': '#ef4444'
};

function getSubjectColor(subject) {
  const map = {
    '数据结构': { main: '#6366f1', light: '#a5b4fc', dark: '#4f46e5' },
    '计算机组成原理': { main: '#10b981', light: '#6ee7b7', dark: '#059669' },
    '操作系统': { main: '#f59e0b', light: '#fcd34d', dark: '#d97706' },
    '计算机网络': { main: '#ef4444', light: '#fca5a5', dark: '#dc2626' }
  };
  return map[subject] || { main: '#6366f1', light: '#a5b4fc', dark: '#4f46e5' };
}

const masteryColors = {
  'mastered': '#10b981',
  'partial': '#f59e0b',
  'weak': '#ef4444',
  'none': '#94a3b8'
};

let kgInitialized = false;

async function initKnowledgeGraph() {
  console.log('initKnowledgeGraph called, kgInitialized:', kgInitialized);
  if (kgInitialized) {
    renderGraphWithLayout();
    return;
  }
  try {
    await window.KaoyanRuntime.loadScript(
      'https://cdn.jsdelivr.net/npm/d3@7.9.0/dist/d3.min.js',
      'd3'
    );
    initKgParticles();
    await loadKgSubjects();
    // 加载用户掌握度数据用于颜色编码
    await loadKgMastery();
    console.log('Loaded subjects:', kgState.subjects.length);
    buildGraph();
    console.log('Built graph - nodes:', kgState.nodes.length, 'links:', kgState.links.length);
    setupGraphEventListeners();
    renderGraphWithLayout();
    setTimeout(bindKgToolbar, 1300);
    kgInitialized = true;
    console.log('Knowledge graph initialized successfully');
  } catch (err) {
    console.error('知识图谱初始化失败:', err);
    const container = document.getElementById('kgGraphContainer');
    if (container) {
      container.innerHTML = '<div class="kg-empty">知识图谱加载失败<br><br><span style="font-size:0.85em;color:#94a3b8;">' + escapeHtml(err.message || String(err)) + '</span></div>';
    }
  }
}

async function loadKgMastery() {
  try {
    const [masteryResp, statsResp] = await Promise.all([
      fetch('/kg/mastery'),
      fetch('/user/stats/overview'),
    ]);
    if (masteryResp.ok) {
      kgState.mastery = await masteryResp.json();
    }
    if (statsResp.ok) {
      const stats = await statsResp.json();
      kgState.subjectProgress = stats.by_subject_backend || {};
    }
  } catch (e) {
    kgState.mastery = {};
    kgState.subjectProgress = {};
    console.warn('加载掌握度数据失败', e);
  }
}

async function loadKgSubjects() {
  const response = await fetch('/kg/subjects');
  if (!response.ok) throw new Error('HTTP ' + response.status);
  const subjects = await response.json();
  kgState.subjects = subjects;
  kgState.chapterInfo = {};
  let totalChapters = 0, totalPoints = 0;
  subjects.forEach(s => {
    totalChapters += s.chapter_count;
    totalPoints += s.point_count;
    s.chapters.forEach(ch => {
      kgState.chapterInfo[s.subject + '||' + ch.chapter_id] = ch;
    });
  });
  // 更新统计卡片
  const statS = document.getElementById('kgStatSubjects');
  const statC = document.getElementById('kgStatChapters');
  const statP = document.getElementById('kgStatPoints');
  if (statS) animateCount(statS, subjects.length);
  if (statC) animateCount(statC, totalChapters);
  if (statP) animateCount(statP, totalPoints);
  renderKgCatalog();
}

function renderKgCatalog() {
  const list = document.getElementById('kgCatalogList');
  if (!list) return;
  list.innerHTML = (kgState.subjects || []).map((subject, subjectIndex) => {
    const color = getSubjectColor(subject.subject).main;
    const chapters = (subject.chapters || []).map(chapter => `
      <button class="kg-catalog-chapter" type="button"
              data-subject="${escapeHtml(subject.subject)}"
              data-chapter="${escapeHtml(chapter.chapter_id)}"
              data-title="${escapeHtml(chapter.chapter_title)}"
              data-count="${escapeHtml(String(chapter.point_count || 0))}">
        <span>${escapeHtml(chapter.chapter_title)}</span>
        <small>${escapeHtml(String(chapter.point_count || 0))}</small>
      </button>
    `).join('');
    return `
      <details class="kg-catalog-subject" ${subjectIndex === 0 ? 'open' : ''}>
        <summary>
          <span><i style="background:${color}"></i>${escapeHtml(subject.subject)}</span>
          <small>${escapeHtml(String(subject.chapter_count || 0))} 章</small>
        </summary>
        <div>${chapters}</div>
      </details>
    `;
  }).join('');

  list.querySelectorAll('.kg-catalog-chapter').forEach(button => {
    button.addEventListener('click', () => {
      openChapterDetail(
        button.dataset.subject,
        button.dataset.chapter,
        button.dataset.title,
        Number(button.dataset.count || 0),
      );
    });
  });
  document.getElementById('kgCatalogOverview')?.addEventListener('click', () => {
    kgState.filters.subject = 'all';
    const subjectFilter = document.getElementById('kgSubjectFilter');
    if (subjectFilter) subjectFilter.value = 'all';
    Object.keys(kgState.subjectEnabled).forEach(subject => {
      kgState.subjectEnabled[subject] = true;
    });
    document.querySelectorAll('.kg-subject-filter input[type="checkbox"]').forEach(input => {
      input.checked = true;
    });
    renderGraphWithLayout();
    setTimeout(() => document.getElementById('kgZoomReset')?.click(), 80);
  });
}

function animateCount(el, target) {
  const duration = 800;
  const start = parseInt(el.textContent, 10) || 0;
  const t0 = performance.now();
  const step = (now) => {
    const p = Math.min(1, (now - t0) / duration);
    const ease = 1 - Math.pow(1 - p, 3);
    el.textContent = Math.round(start + (target - start) * ease);
    if (p < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function initKgParticles() {
  const container = document.getElementById('kgParticles');
  if (!container) return;
  container.innerHTML = '';
  const count = 24;
  const colors = ['#67e8f9', '#a5b4fc', '#f0abfc', '#6ee7b7', '#fcd34d'];
  for (let i = 0; i < count; i++) {
    const p = document.createElement('div');
    p.className = 'kg-particle';
    const size = 2 + Math.random() * 4;
    p.style.width = size + 'px';
    p.style.height = size + 'px';
    p.style.left = Math.random() * 100 + '%';
    p.style.background = colors[Math.floor(Math.random() * colors.length)];
    p.style.color = p.style.background;
    p.style.animationDuration = (8 + Math.random() * 10) + 's';
    p.style.animationDelay = (-Math.random() * 12) + 's';
    container.appendChild(p);
  }
}

function bindKgToolbar() {
  const zoomIn = document.getElementById('kgZoomIn');
  const zoomOut = document.getElementById('kgZoomOut');
  const zoomReset = document.getElementById('kgZoomReset');
  if (kgState.zoomBehavior) {
    if (zoomIn) zoomIn.onclick = () => kgState.svg.transition().duration(220).call(kgState.zoomBehavior.scaleBy, 1.25);
    if (zoomOut) zoomOut.onclick = () => kgState.svg.transition().duration(220).call(kgState.zoomBehavior.scaleBy, 0.8);
    if (zoomReset) zoomReset.onclick = () => {
      kgState.pinnedPositions.clear();
      kgState.nodes.forEach(node => {
        node.fx = null;
        node.fy = null;
      });
      renderGraphWithLayout();
    };
  }
}

function buildGraph() {
  const nodes = [];
  const links = [];
  const nodeMap = new Map();

  // 创建三层图：科目 → 章节 → 知识点，并补充知识点间关系。
  const subjects = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
  const presentSubjects = kgState.subjects.map(s => s.subject);

  subjects.forEach(subject => {
    if (!presentSubjects.includes(subject)) return;
    const color = getSubjectColor(subject);
    const nodeId = 'subject-' + subject;

    // 科目进度严格使用“已完成题数 / 本科题库总数”。
    const subjectStats = (kgState.subjectProgress || {})[subject] || {};
    let masteryLevel = 'none';
    let masteryScore = -1;
    if (Number(subjectStats.total || 0) > 0) {
      masteryScore = Number(subjectStats.mastery_score || 0);
      if (masteryScore >= 85) masteryLevel = 'mastered';
      else if (masteryScore >= 70) masteryLevel = 'partial';
      else if (masteryScore >= 50) masteryLevel = 'weak';
      else masteryLevel = 'danger';
    }

    nodes.push({
      id: nodeId,
      label: subject,
      type: 'subject',
      subject: subject,
      radius: 55,
      color: color.main,
      border: color.dark,
      masteryLevel: masteryLevel,
      masteryScore: masteryScore
    });
    nodeMap.set(nodeId, nodes.length - 1);
  });

  kgState.subjects.forEach(subj => {
    const subject = subj.subject;
    const subjectNodeId = 'subject-' + subject;
    if (!nodeMap.has(subjectNodeId)) return;
    subj.chapters.forEach(chapter => {
      const chapterNodeId = 'chapter-' + subject + '-' + chapter.chapter_id;
      const color = getSubjectColor(subject);
      nodes.push({
        id: chapterNodeId,
        label: chapter.chapter_title,
        type: 'chapter',
        subject: subject,
        chapterId: chapter.chapter_id,
        chapterTitle: chapter.chapter_title,
        chapterOrder: chapter.chapter_order,
        pointCount: chapter.point_count,
        radius: 32,
        color: color.light,
        border: color.main
      });
      nodeMap.set(chapterNodeId, nodes.length - 1);
      links.push({ source: subjectNodeId, target: chapterNodeId, type: 'chapter' });

      (chapter.points || []).forEach(point => {
        const pointNodeId = 'knowledge-' + point.id;
        const masteryItem = (kgState.mastery || {})[point.title] || {};
        nodes.push({
          id: pointNodeId,
          pointId: point.id,
          label: point.title,
          type: 'knowledge',
          subject: subject,
          chapterId: chapter.chapter_id,
          chapterTitle: chapter.chapter_title,
          difficulty: point.difficulty,
          importance: point.importance,
          radius: 8,
          color: color.main,
          border: '#ffffff',
          masteryScore: masteryItem.score ?? -1,
          data: point
        });
        nodeMap.set(pointNodeId, nodes.length - 1);
        links.push({ source: chapterNodeId, target: pointNodeId, type: 'knowledge' });
      });
    });
  });

  kgState.subjects.forEach(subj => {
    subj.chapters.forEach(chapter => {
      (chapter.points || []).forEach(point => {
        const source = 'knowledge-' + point.id;
        (point.related_point_ids || []).forEach(targetId => {
          const target = 'knowledge-' + targetId;
          if (nodeMap.has(source) && nodeMap.has(target) && source < target) {
            links.push({ source, target, type: 'related' });
          }
        });
        (point.cross_subject_relations || []).forEach(relation => {
          const target = 'knowledge-' + relation.target_id;
          if (nodeMap.has(source) && nodeMap.has(target) && source < target) {
            links.push({ source, target, type: 'cross_subject', theme: relation.theme, explanation: relation.explanation });
          }
        });
      });
    });
  });

  kgState.nodes = nodes;
  kgState.links = links;
}

function setupGraphEventListeners() {
  const subjectFilter = document.getElementById('kgSubjectFilter');
  if (subjectFilter) {
    subjectFilter.addEventListener('change', (e) => {
      kgState.filters.subject = e.target.value;
      renderGraphWithLayout();
    });
  }

  const searchInput = document.getElementById('kgSearchInput');
  if (searchInput) {
    searchInput.addEventListener('input', (e) => {
      kgState.filters.search = e.target.value.toLowerCase();
      renderGraphWithLayout();
    });
  }

  const subjectMap = {
    'subject-ds': '数据结构',
    'subject-co': '计算机组成原理',
    'subject-os': '操作系统',
    'subject-cn': '计算机网络'
  };
  Object.keys(subjectMap).forEach(id => {
    const checkbox = document.getElementById(id);
    if (checkbox) {
      checkbox.addEventListener('change', (e) => {
        kgState.subjectEnabled[subjectMap[id]] = e.target.checked;
        renderGraphWithLayout();
      });
    }
  });

  const graphContainer = document.getElementById('kgGraphContainer');
  if (graphContainer && typeof ResizeObserver !== 'undefined' && !kgState.resizeObserver) {
    kgState.resizeObserver = new ResizeObserver(entries => {
      const entry = entries[0];
      if (!entry || !kgInitialized) return;
      const width = Math.round(entry.contentRect.width);
      const height = Math.round(entry.contentRect.height);
      const previous = kgState.lastGraphSize;
      if (Math.abs(width - previous.width) < 2 && Math.abs(height - previous.height) < 2) return;
      kgState.lastGraphSize = { width, height };
      clearTimeout(kgState.resizeTimer);
      kgState.resizeTimer = setTimeout(() => {
        if (document.getElementById('knowledge-graph-view')?.classList.contains('active')) {
          renderGraphWithLayout();
          bindKgToolbar();
        }
      }, 180);
    });
    kgState.resizeObserver.observe(graphContainer);
  }
}

function renderGraphWithLayout() {
  const container = document.getElementById('kgGraphContainer');
  if (!container) {
    console.error('kgGraphContainer not found');
    return;
  }
  console.log('renderGraphWithLayout: container dimensions', container.clientWidth, 'x', container.clientHeight);

  container.innerHTML = '';

  const searchTerm = kgState.filters.search.trim();
  const enabledNodes = kgState.nodes.filter(node => {
    const enabledMatch = kgState.subjectEnabled[node.subject];
    const dropdownMatch = kgState.filters.subject === 'all' || kgState.filters.subject === node.subject;
    return enabledMatch && dropdownMatch;
  });

  // 默认采用“科目 → 章节”的清晰概览，不把 320 个知识点一次性堆到画布上。
  // 搜索时才显示命中的知识点，并自动补齐它们所属的科目和章节。
  let filteredNodes;
  if (!searchTerm) {
    filteredNodes = enabledNodes.filter(node => node.type !== 'knowledge');
  } else {
    const matched = enabledNodes.filter(node =>
      node.label.toLowerCase().includes(searchTerm) ||
      (node.data && node.data.content && node.data.content.toLowerCase().includes(searchTerm))
    );
    const requiredIds = new Set(matched.map(node => node.id));
    matched.forEach(node => {
      requiredIds.add('subject-' + node.subject);
      if (node.chapterId) {
        requiredIds.add('chapter-' + node.subject + '-' + node.chapterId);
      }
    });
    const matchedKnowledgeIds = new Set(matched.filter(node => node.type === 'knowledge').map(node => node.id));
    kgState.links.filter(link => link.type === 'cross_subject').forEach(link => {
      const sourceId = typeof link.source === 'object' ? link.source.id : link.source;
      const targetId = typeof link.target === 'object' ? link.target.id : link.target;
      const neighborId = matchedKnowledgeIds.has(sourceId) ? targetId : matchedKnowledgeIds.has(targetId) ? sourceId : '';
      const neighbor = enabledNodes.find(node => node.id === neighborId);
      if (!neighbor) return;
      requiredIds.add(neighbor.id);
      requiredIds.add('subject-' + neighbor.subject);
      requiredIds.add('chapter-' + neighbor.subject + '-' + neighbor.chapterId);
    });
    filteredNodes = enabledNodes.filter(node => requiredIds.has(node.id));
  }

  const modeHint = document.getElementById('kgViewHint');
  if (modeHint) {
    modeHint.textContent = searchTerm
      ? `搜索结果 · ${filteredNodes.filter(node => node.type === 'knowledge').length} 个知识点（含跨科同构关联）`
      : '概览模式 · 点击章节查看知识点';
  }

  console.log('renderGraphWithLayout: filtered nodes', filteredNodes.length);

  if (filteredNodes.length === 0) {
    container.innerHTML = '<div class="kg-loading">没有匹配的知识点</div>';
    return;
  }

  const filteredNodeIds = new Set(filteredNodes.map(n => n.id));
  const filteredLinks = kgState.links.filter(link => {
    const s = typeof link.source === 'object' ? link.source.id : link.source;
    const t = typeof link.target === 'object' ? link.target.id : link.target;
    return filteredNodeIds.has(s) && filteredNodeIds.has(t);
  });

  const width = container.clientWidth || 800;
  const height = container.clientHeight || 600;
  kgState.lastGraphSize = { width, height };

  if (typeof d3 === 'undefined') {
    console.log('D3 not available, using fallback SVG renderer');
    renderFallbackSVG(container, filteredNodes, filteredLinks, width, height);
    return;
  }

  try {
    console.log('Using D3 renderer');
    renderD3Graph(container, filteredNodes, filteredLinks, width, height);
  } catch (err) {
    console.error('D3渲染失败, 使用回退渲染:', err);
    renderFallbackSVG(container, filteredNodes, filteredLinks, width, height);
  }
}

function renderFallbackSVG(container, nodes, links, width, height) {
  // 三层布局：科目（中心）→ 章节（四周）→ 知识点（章节周围）
  const subjects = nodes.filter(n => n.type === 'subject');
  const chapters = nodes.filter(n => n.type === 'chapter');
  const knowledge = nodes.filter(n => n.type === 'knowledge');

  const cx = width / 2, cy = height / 2;
  const subjectRadius = Math.min(width, height) / 3.5;

  // 科目节点放在画布中心
  if (subjects.length === 1) {
    subjects[0].x = cx;
    subjects[0].y = cy;
  } else {
    subjects.forEach((n, i) => {
      const angle = (i / subjects.length) * 2 * Math.PI - Math.PI / 2;
      n.x = cx + Math.cos(angle) * (subjectRadius * 0.5);
      n.y = cy + Math.sin(angle) * (subjectRadius * 0.5);
    });
  }

  // 章节节点围绕所属科目节点分布
  chapters.forEach((n, i) => {
    const subjNode = subjects.find(s => s.subject === n.subject);
    if (!subjNode) return;
    const siblings = chapters.filter(c => c.subject === n.subject);
    const idx = siblings.indexOf(n);
    const total = siblings.length;
    const angle = (idx / total) * 2 * Math.PI - Math.PI / 2;
    const r = 150 + 20 * (idx % 3);
    n.x = subjNode.x + Math.cos(angle) * r;
    n.y = subjNode.y + Math.sin(angle) * r;
  });

  knowledge.forEach(n => {
    const chapter = chapters.find(
      item => item.subject === n.subject && item.chapterId === n.chapterId
    );
    if (!chapter) {
      n.x = cx;
      n.y = cy;
      return;
    }
    const siblings = knowledge.filter(
      item => item.subject === n.subject && item.chapterId === n.chapterId
    );
    const index = siblings.indexOf(n);
    const angle = (index / Math.max(1, siblings.length)) * Math.PI * 2;
    n.x = chapter.x + Math.cos(angle) * 48;
    n.y = chapter.y + Math.sin(angle) * 48;
  });

  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', '100%');
  svg.setAttribute('height', '100%');
  svg.setAttribute('viewBox', '0 0 ' + width + ' ' + height);

  const g = document.createElementNS('http://www.w3.org/2000/svg', 'g');

  // 画连线
  links.forEach(lk => {
    const s = nodes.find(n => n.id === (typeof lk.source === 'object' ? lk.source.id : lk.source));
    const t = nodes.find(n => n.id === (typeof lk.target === 'object' ? lk.target.id : lk.target));
    if (s && t) {
      const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
      line.setAttribute('x1', s.x); line.setAttribute('y1', s.y);
      line.setAttribute('x2', t.x); line.setAttribute('y2', t.y);
      line.setAttribute('class', `kg-edge ${lk.type === 'cross_subject' ? 'cross-subject' : ''}`);
      line.setAttribute('stroke', lk.type === 'cross_subject' ? '#f59e0b' : (s.color || '#94a3b8'));
      line.setAttribute('stroke-opacity', lk.type === 'cross_subject' ? '0.85' : '0.3');
      line.setAttribute('stroke-width', lk.type === 'cross_subject' ? '2.5' : '1.5');
      if (lk.type === 'cross_subject') line.setAttribute('stroke-dasharray', '7,5');
      g.appendChild(line);
    }
  });

  // 画节点
  nodes.forEach(n => {
    const el = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    el.setAttribute('class', kgState.selectedNode === n.id ? 'kg-node selected' : 'kg-node');
    el.setAttribute('data-id', n.id);
    el.style.cursor = 'pointer';

    const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
    circle.setAttribute('cx', n.x);
    circle.setAttribute('cy', n.y);
    circle.setAttribute('r', n.radius);
    circle.setAttribute('fill', n.color);
    circle.setAttribute('stroke', n.border || n.color);
    circle.setAttribute('stroke-width', kgState.selectedNode === n.id ? '3' : '1.5');
    if (n.type === 'subject') {
      circle.setAttribute('stroke-width', '3');
    }
    if (n.type === 'chapter') {
      circle.setAttribute('stroke-dasharray', '4,3');
    }
    el.appendChild(circle);

    if (n.type !== 'knowledge') {
      const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
      text.setAttribute('x', n.x);
      text.setAttribute('y', n.y + 4);
      text.setAttribute('text-anchor', 'middle');
      text.setAttribute('fill', n.type === 'subject' ? '#fff' : '#1e293b');
      text.setAttribute('font-size', n.type === 'subject' ? '14' : n.type === 'chapter' ? '11' : '9');
      text.setAttribute('font-weight', n.type === 'subject' ? '700' : '500');
      text.setAttribute('pointer-events', 'none');
      let label = n.label;
      if (n.type === 'chapter' && label.length > 8) label = label.substring(0, 8) + '...';
      if (n.type === 'more') label = '更多...';
      text.textContent = label;
      el.appendChild(text);
    }

    el.addEventListener('click', () => selectNode(n));
    g.appendChild(el);
  });

  svg.appendChild(g);
  container.appendChild(svg);
  kgState.svg = svg;

  // 缩放和平移
  let isDragging = false, startX, startY, panX = 0, panY = 0, zoom = 1;
  let dragStartTime = 0;
  container.addEventListener('mousedown', (e) => {
    if (e.target.tagName !== 'circle' && e.target.tagName !== 'text') {
      isDragging = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
      dragStartTime = Date.now();
    }
  });
  container.addEventListener('mousemove', (e) => {
    if (isDragging) {
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      g.setAttribute('transform', 'translate(' + panX + ',' + panY + ') scale(' + zoom + ')');
    }
  });
  container.addEventListener('mouseup', () => { isDragging = false; });
  container.addEventListener('mouseleave', () => { isDragging = false; });
  container.addEventListener('wheel', (e) => {
    e.preventDefault();
    const d = e.deltaY > 0 ? -0.1 : 0.1;
    zoom = Math.max(0.3, Math.min(3, zoom + d));
    g.setAttribute('transform', 'translate(' + panX + ',' + panY + ') scale(' + zoom + ')');
  }, { passive: false });
}

function renderD3Graph(container, nodes, links, width, height) {
  container.innerHTML = '';

  const svg = d3.select(container)
    .append('svg')
    .attr('width', '100%')
    .attr('height', '100%')
    .attr('viewBox', [0, 0, width, height])
    .style('display', 'block');

  kgState.svg = svg;

  // ---------- SVG defs: 滤镜 / 渐变 ----------
  const defs = svg.append('defs');

  // 每个科目生成一个发光滤镜
  const subjects = [...new Set(nodes.map(n => n.subject))];
  const colorOf = subj => (getSubjectColor(subj) || {}).main || '#6366f1';

  subjects.forEach(subj => {
    const fid = 'glow-' + subj;
    const filter = defs.append('filter')
      .attr('id', fid)
      .attr('x', '-50%').attr('y', '-50%')
      .attr('width', '200%').attr('height', '200%');
    filter.append('feGaussianBlur').attr('stdDeviation', '6').attr('result', 'coloredBlur');
    const merge = filter.append('feMerge');
    merge.append('feMergeNode').attr('in', 'coloredBlur');
    merge.append('feMergeNode').attr('in', 'SourceGraphic');
  });

  // 连线渐变
  links.forEach((lk, i) => {
    const s = typeof lk.source === 'object' ? lk.source : nodes.find(n => n.id === lk.source);
    const t = typeof lk.target === 'object' ? lk.target : nodes.find(n => n.id === lk.target);
    if (!s || !t) return;
    const grad = defs.append('linearGradient')
      .attr('id', 'edge-grad-' + i)
      .attr('gradientUnits', 'userSpaceOnUse')
      .attr('x1', s.x || width/2).attr('y1', s.y || height/2)
      .attr('x2', t.x || width/2).attr('y2', t.y || height/2);
    grad.append('stop').attr('offset', '0%').attr('stop-color', colorOf(s.subject)).attr('stop-opacity', 0.7);
    grad.append('stop').attr('offset', '100%').attr('stop-color', colorOf(t.subject)).attr('stop-opacity', 0.2);
  });

  // 装饰用的网格 pattern
  const pattern = defs.append('pattern')
    .attr('id', 'kg-grid-pattern')
    .attr('width', 40).attr('height', 40)
    .attr('patternUnits', 'userSpaceOnUse');
  pattern.append('circle')
    .attr('cx', 20).attr('cy', 20).attr('r', 1)
    .attr('fill', 'rgba(99, 102, 241, 0.15)');

  // 根分组（应用缩放/平移）
  const root = svg.append('g').attr('class', 'kg-root');
  const edgesG = root.append('g').attr('class', 'kg-edges');
  const nodesG = root.append('g').attr('class', 'kg-nodes');

  // ---------- 缩放/平移 ----------
  const zoom = d3.zoom()
    .scaleExtent([0.3, 3])
    .on('zoom', (event) => root.attr('transform', event.transform));
  svg.call(zoom);
  kgState.zoomBehavior = zoom;

  // ---------- 工具提示 ----------
  let tooltip = d3.select(container).select('.kg-tooltip');
  if (tooltip.empty()) {
    tooltip = d3.select(container).append('div').attr('class', 'kg-tooltip');
  }
  const showTip = (event, d) => {
    const color = colorOf(d.subject);
    const rect = container.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    let meta = '';
    if (d.type === 'subject') {
      const subjData = kgState.subjects.find(s => s.subject === d.subject);
      const totalPoints = subjData ? subjData.point_count : 0;
      const chapCount = subjData ? subjData.chapter_count : 0;
      meta = `${chapCount} 个章节 · ${totalPoints} 个知识点`;
      if (d.masteryScore >= 0) {
        const levelLabels = { mastered: '熟练', partial: '稳定', weak: '薄弱', danger: '危险' };
        meta += `<br>题目覆盖进度：${formatProgressPercent(d.masteryScore)} (${levelLabels[d.masteryLevel] || '未知'})`;
      }
    } else if (d.type === 'chapter') {
      meta = `第 ${d.chapterOrder} 章 · ${d.pointCount} 个知识点 · 点击查看详情`;
    } else if (d.type === 'knowledge') {
      meta = `${d.chapterTitle || ''} · ${d.difficulty || '基础'} · ${d.importance || '一般'}`;
      if (d.masteryScore >= 0) meta += `<br>题目覆盖进度：${formatProgressPercent(d.masteryScore)}`;
    }
    tooltip
      .style('left', x + 'px')
      .style('top', y + 'px')
      .style('--accent', color)
      .html(`<div class="kg-tooltip-title">${escapeHtml(d.label)}</div><div class="kg-tooltip-meta">${meta}</div>`)
      .classed('visible', true);
  };
  const hideTip = () => tooltip.classed('visible', false);

  // ---------- 稳定的分区布局：科目 → 章节 → 搜索命中的知识点 ----------
  const subjectOrder = ['数据结构', '计算机组成原理', '操作系统', '计算机网络'];
  const presentSubjectNodes = subjectOrder
    .map(name => nodes.find(n => n.type === 'subject' && n.subject === name))
    .filter(Boolean);

  const marginX = Math.max(135, Math.min(190, width * 0.18));
  const marginY = Math.max(120, Math.min(165, height * 0.22));
  const layoutW = Math.max(260, width - marginX * 2);
  const layoutH = Math.max(240, height - marginY * 2);
  const quadrantMap = {
    '数据结构':       { x: marginX + layoutW * 0.18, y: marginY + layoutH * 0.18 },
    '计算机组成原理': { x: marginX + layoutW * 0.82, y: marginY + layoutH * 0.18 },
    '操作系统':       { x: marginX + layoutW * 0.18, y: marginY + layoutH * 0.82 },
    '计算机网络':     { x: marginX + layoutW * 0.82, y: marginY + layoutH * 0.82 }
  };

  const placeNode = (node, x, y) => {
    const pinned = kgState.pinnedPositions.get(node.id);
    node.layoutX = x;
    node.layoutY = y;
    node.x = pinned ? pinned.x : (Number.isFinite(node.x) ? node.x : x);
    node.y = pinned ? pinned.y : (Number.isFinite(node.y) ? node.y : y);
    node.fx = pinned ? pinned.x : null;
    node.fy = pinned ? pinned.y : null;
  };

  presentSubjectNodes.forEach(node => {
    const target = quadrantMap[node.subject] || { x: width / 2, y: height / 2 };
    placeNode(node, target.x, target.y);
  });

  // 章节按固定圆环均匀排列，避免力导向造成重叠和位置漂移。
  nodes.forEach(n => {
    if (n.type !== 'chapter') return;
    const subjNode = presentSubjectNodes.find(s => s.subject === n.subject);
    if (!subjNode) return;
    const sibs = nodes.filter(c => c.type === 'chapter' && c.subject === n.subject);
    const idx = sibs.indexOf(n);
    const total = sibs.length;
    const ringRadius = Math.max(105, Math.min(145, 92 + total * 5));
    const angle = -Math.PI / 2 + (idx / Math.max(1, total)) * Math.PI * 2;
    placeNode(
      n,
      subjNode.x + Math.cos(angle) * ringRadius,
      subjNode.y + Math.sin(angle) * ringRadius
    );
  });

  // 搜索结果中的知识点围绕所属章节排列；默认概览不绘制知识点。
  nodes.forEach(n => {
    if (n.type !== 'knowledge') return;
    const chapter = nodes.find(
      item => item.type === 'chapter'
        && item.subject === n.subject
        && item.chapterId === n.chapterId
    );
    if (!chapter) return;
    const siblings = nodes.filter(
      item => item.type === 'knowledge'
        && item.subject === n.subject
        && item.chapterId === n.chapterId
    );
    const index = siblings.indexOf(n);
    const angle = -Math.PI / 2 + (index / Math.max(1, siblings.length)) * Math.PI * 2;
    const ringRadius = 48 + Math.floor(index / 10) * 22;
    placeNode(
      n,
      chapter.x + Math.cos(angle) * ringRadius,
      chapter.y + Math.sin(angle) * ringRadius
    );
  });

  // 柔和的弹性布局：目标坐标负责保持整齐，连线与碰撞力负责自然跟随。
  const sim = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(link => {
      if (link.type === 'cross_subject') return 190;
      if (link.type === 'related') return 72;
      const target = typeof link.target === 'object'
        ? link.target
        : nodes.find(node => node.id === link.target);
      return target && target.type === 'knowledge' ? 54 : 126;
    }).strength(link => link.type === 'cross_subject' ? 0.28 : link.type === 'related' ? 0.12 : 0.42))
    .force('charge', d3.forceManyBody().strength(node =>
      node.type === 'subject' ? -170 : node.type === 'chapter' ? -72 : -24
    ))
    .force('collision', d3.forceCollide().radius(node =>
      node.radius + (node.type === 'subject' ? 22 : node.type === 'chapter' ? 15 : 7)
    ).strength(0.82))
    .force('x', d3.forceX(node => node.layoutX).strength(node =>
      node.type === 'subject' ? 0.42 : node.type === 'chapter' ? 0.3 : 0.2
    ))
    .force('y', d3.forceY(node => node.layoutY).strength(node =>
      node.type === 'subject' ? 0.42 : node.type === 'chapter' ? 0.3 : 0.2
    ))
    .velocityDecay(0.58)
    .alpha(0.7)
    .alphaDecay(0.045);

  kgState.simulation = sim;

  // ---------- 连线 ----------
  const linkIdxMap = new Map();
  links.forEach((lk, i) => {
    const s = typeof lk.source === 'object' ? lk.source : nodes.find(n => n.id === lk.source);
    const t = typeof lk.target === 'object' ? lk.target : nodes.find(n => n.id === lk.target);
    if (s && t) linkIdxMap.set(s.id + '||' + t.id, i);
  });

  const link = edgesG.selectAll('path')
    .data(links)
    .join('path')
    .attr('class', d => `kg-edge flow ${d.type === 'cross_subject' ? 'cross-subject' : ''}`)
    .attr('d', d => {
      const s = typeof d.source === 'object' ? d.source : nodes.find(n => n.id === d.source);
      const t = typeof d.target === 'object' ? d.target : nodes.find(n => n.id === d.target);
      if (!s || !t || s.x == null || t.x == null) return '';
      const dx = t.x - s.x, dy = t.y - s.y;
      const dr = Math.sqrt(dx * dx + dy * dy) * 1.2;
      return `M${s.x},${s.y} A${dr},${dr} 0 0,1 ${t.x},${t.y}`;
    })
    .attr('stroke', (d, i) => d.type === 'cross_subject' ? '#f59e0b' : 'url(#edge-grad-' + i + ')')
    .attr('stroke-width', d => d.type === 'cross_subject' ? 2.6 : 1.6)
    .attr('stroke-dasharray', d => d.type === 'cross_subject' ? '8 6' : null)
    .attr('fill', 'none');

  // ---------- 节点 ----------
  const node = nodesG.selectAll('g')
    .data(nodes, d => d.id)
    .join('g')
    .attr('class', d => kgState.selectedNode === d.id ? 'kg-node selected' : 'kg-node')
    .style('cursor', 'pointer');

  // 节点 - 主体圆形（带发光滤镜）
  node.append('circle')
    .attr('class', 'kg-node-core')
    .attr('r', d => d.radius)
    .attr('fill', d => d.color)
    .attr('stroke', d => d.border || d.color)
    .attr('stroke-width', d => d.type === 'subject' ? 2 : 1.5)
    .attr('filter', d => `url(#glow-${d.subject})`);

  // 节点 - 内圈高光
  node.append('circle')
    .attr('class', 'kg-node-highlight')
    .attr('r', d => d.radius * 0.85)
    .attr('fill', 'none')
    .attr('stroke', 'rgba(255,255,255,0.35)')
    .attr('stroke-width', 1)
    .attr('transform', d => `translate(${-d.radius * 0.15}, ${-d.radius * 0.15})`);

  // 节点 - 中心脉冲圆（仅科目）
  node.filter(d => d.type === 'subject').append('circle')
    .attr('class', 'kg-node-pulse')
    .attr('r', d => d.radius)
    .attr('fill', 'none')
    .attr('stroke', d => d.color)
    .attr('stroke-width', 2)
    .attr('opacity', 0.6);

  // 节点 - 旋转外环（仅科目）
  node.filter(d => d.type === 'subject').append('g')
    .attr('class', 'kg-node-outer')
    .each(function(d) {
      const g = d3.select(this);
      const r = d.radius + 14;
      // 4 段弧
      for (let i = 0; i < 4; i++) {
        const startAngle = (i / 4) * 2 * Math.PI;
        const endAngle = startAngle + Math.PI * 0.18;
        const x1 = Math.cos(startAngle) * r;
        const y1 = Math.sin(startAngle) * r;
        const x2 = Math.cos(endAngle) * r;
        const y2 = Math.sin(endAngle) * r;
        const largeArc = endAngle - startAngle > Math.PI ? 1 : 0;
        g.append('path')
          .attr('d', `M${x1},${y1} A${r},${r} 0 ${largeArc},1 ${x2},${y2}`)
          .attr('stroke', d.color)
          .attr('stroke-width', 2)
          .attr('fill', 'none')
          .attr('stroke-linecap', 'round')
          .attr('opacity', 0.85);
      }
      // 4 个小圆点
      for (let i = 0; i < 4; i++) {
        const angle = (i / 4) * 2 * Math.PI + Math.PI / 4;
        g.append('circle')
          .attr('cx', Math.cos(angle) * r)
          .attr('cy', Math.sin(angle) * r)
          .attr('r', 2.5)
          .attr('fill', d.color)
          .attr('opacity', 0.9);
      }
    });

  // 节点 - 掌握度指示环（仅科目，基于学习数据）
  node.filter(d => d.type === 'subject' && d.masteryLevel && d.masteryLevel !== 'none').append('g')
    .attr('class', 'kg-mastery-ring')
    .each(function(d) {
      const g = d3.select(this);
      const ringR = d.radius + 24;
      const masteryColorMap = {
        mastered: '#10b981',
        partial: '#f59e0b',
        weak: '#f97316',
        danger: '#ef4444'
      };
      const mColor = masteryColorMap[d.masteryLevel] || '#94a3b8';
      // 绘制掌握度弧线（按分数比例）
      const fraction = Math.max(0, Math.min(1, (d.masteryScore || 0) / 100));
      const arcAngle = fraction * 2 * Math.PI;
      if (arcAngle > 0.01) {
        const x1 = Math.cos(-Math.PI / 2) * ringR;
        const y1 = Math.sin(-Math.PI / 2) * ringR;
        const x2 = Math.cos(-Math.PI / 2 + arcAngle) * ringR;
        const y2 = Math.sin(-Math.PI / 2 + arcAngle) * ringR;
        const largeArc = arcAngle > Math.PI ? 1 : 0;
        g.append('path')
          .attr('d', `M${x1},${y1} A${ringR},${ringR} 0 ${largeArc},1 ${x2},${y2}`)
          .attr('stroke', mColor)
          .attr('stroke-width', 3.5)
          .attr('fill', 'none')
          .attr('stroke-linecap', 'round')
          .attr('opacity', 0.9);
      }
      // 掌握度分数标签
      if (d.masteryScore >= 0) {
        g.append('text')
          .attr('x', 0)
          .attr('y', -(ringR + 12))
          .attr('text-anchor', 'middle')
          .attr('fill', mColor)
          .attr('font-size', 11)
          .attr('font-weight', 700)
          .text(d.masteryScore + '%');
      }
    });

  // 节点 - 文字
  node.filter(d => d.type !== 'knowledge').append('text')
    .attr('class', d => 'kg-node-text ' + d.type)
    .attr('y', d => d.type === 'subject' ? 5 : 4)
    .text(d => {
      if (d.type === 'subject') return d.label;
      if (d.type === 'more') return '更多...';
      if (d.type === 'chapter') return d.label.length > 8 ? d.label.substring(0, 8) + '…' : d.label;
      return d.label;
    });

  // 节点 - 章节角标（知识点数量）
  node.filter(d => d.type === 'chapter').append('g')
    .attr('class', 'kg-node-badge-group')
    .attr('transform', d => `translate(${d.radius * 0.7}, ${-d.radius * 0.7})`)
    .each(function(d) {
      const g = d3.select(this);
      const text = String(d.pointCount || 0);
      g.append('circle')
        .attr('class', 'kg-node-badge')
        .attr('r', 9)
        .attr('fill', d.color)
        .attr('stroke', '#fff')
        .attr('stroke-width', 1.5);
      g.append('text')
        .attr('class', 'kg-node-badge-text')
        .attr('y', 0.5)
        .text(text);
    });

  // ---------- 交互 ----------
  node.on('click', (event, d) => {
    event.stopPropagation();
    selectNode(d);
  });
  node.on('mouseenter', function(event, d) {
    d3.select(this).select('.kg-node-core')
      .transition().duration(220)
      .attr('r', d.radius * 1.18);
    showTip(event, d);
  });
  node.on('mousemove', function(event, d) {
    showTip(event, d);
  });
  node.on('mouseleave', function(event, d) {
    d3.select(this).select('.kg-node-core')
      .transition().duration(220)
      .attr('r', d.radius);
    hideTip();
  });

  node.call(d3.drag()
    .on('start', (event, d) => {
      if (!event.active) sim.alphaTarget(0.30).restart();
      d.fx = d.x;
      d.fy = d.y;
      d._dragLastX = event.x;
      d._dragLastY = event.y;
    })
    .on('drag', (event, d) => {
      const dx = event.x - (d._dragLastX ?? event.x);
      const dy = event.y - (d._dragLastY ?? event.y);
      d.fx = event.x;
      d.fy = event.y;
      // Pass part of the displacement to directly connected nodes. They stay
      // free, so the graph bends naturally instead of moving as a rigid block.
      links.forEach(edge => {
        const source = typeof edge.source === 'object'
          ? edge.source : nodes.find(item => item.id === edge.source);
        const target = typeof edge.target === 'object'
          ? edge.target : nodes.find(item => item.id === edge.target);
        const neighbor = source === d ? target : (target === d ? source : null);
        if (!neighbor || kgState.pinnedPositions.has(neighbor.id)) return;
        neighbor.x += dx * 0.42;
        neighbor.y += dy * 0.42;
        neighbor.vx = (neighbor.vx || 0) + dx * 0.16;
        neighbor.vy = (neighbor.vy || 0) + dy * 0.16;
      });
      d._dragLastX = event.x;
      d._dragLastY = event.y;
      sim.alpha(Math.max(sim.alpha(), 0.34)).restart();
    })
    .on('end', (event, d) => {
      if (!event.active) sim.alphaTarget(0);
      d.fx = event.x;
      d.fy = event.y;
      kgState.pinnedPositions.set(d.id, {
        x: event.x,
        y: event.y
      });
      delete d._dragLastX;
      delete d._dragLastY;
    })
  );

  // ---------- 模拟 tick ----------
  sim.on('tick', () => {
    link.attr('d', d => {
      const s = d.source, t = d.target;
      if (!s || !t || s.x == null || t.x == null) return '';
      const dx = t.x - s.x, dy = t.y - s.y;
      const dr = Math.sqrt(dx * dx + dy * dy) * 1.2;
      return `M${s.x},${s.y} A${dr},${dr} 0 0,1 ${t.x},${t.y}`;
    });
    node.attr('transform', d => `translate(${d.x}, ${d.y})`);
  });

  // 第一次渲染时居中 - 若用户筛选了单个科目，则聚焦到该科目象限
  setTimeout(() => {
    try {
      let targetBounds = null;
      if (kgState.filters.subject && kgState.filters.subject !== 'all') {
        const sub = presentSubjectNodes.find(n => n.subject === kgState.filters.subject);
        if (sub && sub.x != null) {
          const sibs = nodes.filter(n => n.type === 'chapter' && n.subject === kgState.filters.subject);
          const all = [sub, ...sibs];
          const xs = all.map(n => n.x), ys = all.map(n => n.y);
          targetBounds = {
            x: Math.min(...xs) - 30,
            y: Math.min(...ys) - 30,
            width: Math.max(...xs) - Math.min(...xs) + 60,
            height: Math.max(...ys) - Math.min(...ys) + 60
          };
        }
      }
      const bounds = targetBounds || root.node().getBBox();
      if (bounds.width > 0 && bounds.height > 0) {
        const pad = 80;
        const scale = Math.min(
          (width - pad * 2) / bounds.width,
          (height - pad * 2) / bounds.height,
          1
        );
        const tx = width / 2 - (bounds.x + bounds.width / 2) * scale;
        const ty = height / 2 - (bounds.y + bounds.height / 2) * scale;
        svg.transition().duration(700).call(
          zoom.transform,
          d3.zoomIdentity.translate(tx, ty).scale(scale)
        );
      }
    } catch (e) { /* ignore */ }
  }, 1200);
}

function selectNode(node) {
  kgState.selectedNode = node.id;
  if (node.type === 'chapter') {
    openChapterDetail(node.subject, node.chapterId, node.chapterTitle, node.pointCount);
    return;
  }
  if (node.type === 'knowledge') {
    showKnowledgeNodeDetail(node);
    return;
  }
  if (kgState.svg && typeof kgState.svg.selectAll === 'function') {
    kgState.svg
      .selectAll('.kg-node')
      .classed('selected', item => item.id === node.id);
  }
  showNodeDetail(node);
}

async function showKnowledgeNodeDetail(node) {
  const detailPanel = document.getElementById('kgDetailPanel');
  if (!detailPanel) return;
  detailPanel.innerHTML = '<h3 class="detail-title">' + escapeHtml(node.label) + '</h3><div class="detail-content">知识点详情加载中...</div>';
  try {
    const response = await fetch('/kg/point?point_id=' + encodeURIComponent(node.pointId));
    if (!response.ok) throw new Error('HTTP ' + response.status);
    const point = await response.json();
    const scorePoints = (point.score_points || [])
      .map(item => '<li>' + escapeHtml(item) + '</li>')
      .join('');
    const relatedCount = (point.related_point_ids || []).length
      + (point.cross_subject_point_ids || []).length;
    const crossRelations = (point.cross_subject_relations || []).map(item => {
      const target = kgState.nodes.find(candidate => candidate.pointId === item.target_id);
      return `<li><b>${escapeHtml(item.theme || '跨学科机制')}</b><span>${escapeHtml(target?.label || item.target_id)}</span><p>${escapeHtml(item.explanation || '')}</p></li>`;
    }).join('');
    detailPanel.innerHTML = `
      <h3 class="detail-title">${escapeHtml(point.title || node.label)}</h3>
      <div class="detail-content">
        <p><strong>${escapeHtml(point.subject || node.subject)}</strong> · ${escapeHtml(point.chapter_title || node.chapterTitle || '')}</p>
        <p>${escapeHtml(point.content || '')}</p>
        ${scorePoints ? '<h4>核心踩分点</h4><ul>' + scorePoints + '</ul>' : ''}
        ${crossRelations ? '<h4>跨科同构关系</h4><ul class="kg-cross-relation-list">' + crossRelations + '</ul>' : ''}
        <p>关联知识点：${relatedCount} 个 · 真题示例：${(point.exam_questions || []).length} 道</p>
        <button type="button" class="knowledge-visual-open" data-knowledge-visual-point="${escapeHtml(point.id || node.pointId || '')}">进入可视化学习舱</button>
      </div>
    `;
    detailPanel.querySelector('[data-knowledge-visual-point]')?.addEventListener('click', event => {
      openKnowledgeVisualization(event.currentTarget.dataset.knowledgeVisualPoint);
    });
  } catch (error) {
    detailPanel.innerHTML = '<h3 class="detail-title">' + escapeHtml(node.label) + '</h3><div class="detail-content">详情加载失败。</div>';
  }
}

async function openChapterDetail(subject, chapterId, chapterTitle, pointCount) {
  switchView('chapter-detail');
  const titleEl = document.getElementById('chapterDetailTitle');
  const metaEl = document.getElementById('chapterDetailMeta');
  const contentEl = document.getElementById('chapterDetailContent');
  if (titleEl) titleEl.textContent = subject + ' · ' + chapterTitle;
  if (metaEl) metaEl.textContent = '加载中...';
  if (contentEl) contentEl.innerHTML = '<div class="kg-loading">章节知识点加载中...</div>';

  // 并行加载：知识点详情 + 学习路径推荐
  const chapterPromise = fetch(
    '/kg/chapter?' + new URLSearchParams({ subject, chapter_id: chapterId }).toString()
  ).then(r => r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)));
  const pathPromise = fetch(
    '/kg/path?' + new URLSearchParams({
      user_id: 'u1',
      subject: subject,
      chapter_id: chapterId,
      limit: '3',
    }).toString()
  ).then(r => r.ok ? r.json() : { next: [] }).catch(() => ({ next: [] }));

  try {
    const data = await chapterPromise;
    if (metaEl) metaEl.textContent = '第 ' + data.chapter_order + ' 章 · 共 ' + data.point_count + ' 个知识点';
    if (!data.points || data.points.length === 0) {
      if (contentEl) contentEl.innerHTML = '<div class="kg-loading">该章节暂无知识点。</div>';
      return;
    }
    const colorMap = {
      '数据结构': '#6366f1',
      '计算机组成原理': '#10b981',
      '操作系统': '#f59e0b',
      '计算机网络': '#ef4444'
    };
    const accent = colorMap[subject] || '#6366f1';
    const cardsHtml = data.points.map((p, idx) => {
      const sp = (p.score_points || []).map(s => '<li>' + escapeHtml(s) + '</li>').join('');
      const tags = (p.tags || []).map(t => '<span class="chapter-tag" style="background:' + accent + '1a;color:' + accent + ';">' + escapeHtml(t) + '</span>').join('');
      const importance = p.importance || '一般';
      const impColor = importance === '核心' ? '#ef4444' : (importance === '重要' ? '#f59e0b' : '#94a3b8');
      const examQs = (p.exam_questions || []);
      const examHtml = examQs.length ? examQs.map((q, qi) => {
        const opts = (q.options || []).map((o, oi) => '<div class="exam-option">' + escapeHtml(o) + '</div>').join('');
        return `
          <div class="exam-question-block">
            <div class="exam-q-head">
              <span class="exam-q-year">${escapeHtml(q.year || '')}</span>
              <span class="exam-q-type">${escapeHtml(q.type || '')}</span>
              <span class="exam-q-idx">真题 ${qi + 1}</span>
            </div>
            <div class="exam-q-stem">${escapeHtml(q.stem || '')}</div>
            ${opts ? '<div class="exam-q-options">' + opts + '</div>' : ''}
            <details class="exam-answer-details">
              <summary>查看答案与解析</summary>
              <div class="exam-answer-content">
                <div class="exam-q-answer"><strong>【答案】</strong>${escapeHtml(q.answer || '')}</div>
                <div class="exam-q-analysis"><strong>【解析】</strong>${escapeHtml(q.analysis || '')}</div>
                ${q.score_point ? '<div class="exam-q-score"><strong>【踩分点】</strong>' + escapeHtml(q.score_point) + '</div>' : ''}
              </div>
            </details>
          </div>
        `;
      }).join('') : '';
      const detailHtml = p.detailed_explanation ? `<div class="chapter-point-detail">${formatDetailed(p.detailed_explanation)}</div>` : '';
      return `
        <div class="chapter-point-card" id="chapter-point-${idx + 1}"
          data-point-id="${escapeHtml(p.id || '')}"
          data-point-title="${escapeHtml(p.title || '')}"
          style="border-left:4px solid ${accent};">
          <div class="chapter-point-head">
            <span class="chapter-point-index" style="background:${accent};">${idx + 1}</span>
            <h3 class="chapter-point-title">${escapeHtml(p.title)}</h3>
            <span class="chapter-point-importance" style="background:${impColor}22;color:${impColor};border:1px solid ${impColor}55;">${escapeHtml(importance)}</span>
            <span class="chapter-point-difficulty difficulty-${escapeHtml(p.difficulty || '中等')}">${escapeHtml(p.difficulty || '中等')}</span>
          </div>
          <button type="button" class="knowledge-visual-open" data-knowledge-visual-point="${escapeHtml(p.id || '')}">◫ 可视化学习</button>
          <div class="chapter-point-content">${escapeHtml(p.content)}</div>
          ${sp ? '<div class="chapter-score-points"><h4>踩分点</h4><ul>' + sp + '</ul></div>' : ''}
          ${detailHtml}
          ${examHtml ? '<div class="chapter-exam-section"><h4>📚 历年真题演示（共 ' + examQs.length + ' 道）</h4>' + examHtml + '</div>' : ''}
          ${tags ? '<div class="chapter-tags">' + tags + '</div>' : ''}
        </div>
      `;
    }).join('');

    // 学习路径推荐区
    const pathData = await pathPromise;
    let pathHtml = '';
    if (pathData && pathData.next && pathData.next.length > 0) {
      const nextItems = pathData.next.map(n => {
        const masteryColor = n.mastery_avg >= 70 ? '#10b981' : (n.mastery_avg >= 50 ? '#f59e0b' : '#ef4444');
        const wpList = (n.weak_points || []).slice(0, 3).map(wp => {
          const wpColor = wp.score >= 70 ? '#10b981' : (wp.score >= 50 ? '#f59e0b' : '#ef4444');
          return `<span class="path-wp-chip" style="border-color:${wpColor};color:${wpColor};" title="题目完成进度 ${wp.score}% · 错 ${wp.wrong_count} 次">${escapeHtml(wp.title)} ${wp.score}%</span>`;
        }).join('');
        return `
          <div class="path-next-card" data-subject="${escapeHtml(n.subject)}" data-chapter="${escapeHtml(n.chapter_id)}">
            <div class="path-next-head">
              <span class="path-next-order">第 ${n.chapter_order} 章</span>
              <span class="path-next-title">${escapeHtml(n.chapter_title)}</span>
              <span class="path-next-mastery" style="background:${masteryColor}22;color:${masteryColor};">进度 ${n.mastery_avg}%</span>
            </div>
            ${wpList ? '<div class="path-next-weak">' + wpList + '</div>' : ''}
          </div>
        `;
      }).join('');
      pathHtml = `
        <div class="learning-path-panel" style="border:1px solid #e5e7eb;border-radius:14px;padding:16px 20px;margin-bottom:20px;background:linear-gradient(135deg,#eef2ff 0%, #f5f3ff 100%);">
          <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:12px;">
            <h3 style="margin:0;font-size:16px;color:#1e293b;">🧭 学习路径推荐（按 chapter_order 顺序）</h3>
            <span style="font-size:12px;color:#64748b;">基于关联题目的完成情况生成</span>
          </div>
          <div class="learning-path-list">${nextItems}</div>
        </div>
      `;
      // 点击路径卡片切换章节
      setTimeout(() => {
        document.querySelectorAll('.path-next-card').forEach(card => {
          card.addEventListener('click', () => {
            openChapterDetail(card.dataset.subject, card.dataset.chapter, card.querySelector('.path-next-title').textContent, 0);
          });
        });
      }, 0);
    }

    if (contentEl) {
      const pointTocHtml = data.points.map((point, index) => `
        <button class="chapter-toc-link" type="button" data-chapter-target="chapter-point-${index + 1}">
          <span>${index + 1}</span>${escapeHtml(point.title)}
        </button>
      `).join('');
      contentEl.innerHTML = `
        <div class="chapter-content-layout">
          <aside class="chapter-toc">
            <div class="chapter-toc-title">本章目录</div>
            <button class="chapter-toc-link is-overview" type="button" data-chapter-target="chapter-detail-overview">
              <span>⌂</span>章节总览
            </button>
            <div class="chapter-toc-points">${pointTocHtml}</div>
          </aside>
          <div class="chapter-content-main">
        <div class="chapter-summary" id="chapter-detail-overview">
          <h2>${escapeHtml(subject)} · ${escapeHtml(chapterTitle)}</h2>
          <p>本章节共 ${data.point_count} 个详细知识点，点击左侧目录可快速定位。</p>
        </div>
        ${pathHtml}
        <div class="chapter-points-grid">${cardsHtml}</div>
          </div>
        </div>
      `;
      contentEl.querySelectorAll('[data-chapter-target]').forEach(button => {
        button.addEventListener('click', () => {
          const target = document.getElementById(button.dataset.chapterTarget || '');
          if (!target) return;
          target.scrollIntoView({ behavior: 'smooth', block: 'start' });
          contentEl.querySelectorAll('.chapter-toc-link').forEach(item => item.classList.remove('is-active'));
          button.classList.add('is-active');
        });
      });
      contentEl.querySelectorAll('[data-knowledge-visual-point]').forEach(button => {
        button.addEventListener('click', () => openKnowledgeVisualization(button.dataset.knowledgeVisualPoint));
      });
    }
  } catch (err) {
    if (contentEl) contentEl.innerHTML = '<div class="kg-loading">加载失败: ' + escapeHtml(err.message || String(err)) + '</div>';
  }
}

async function navigateToKnowledgePoint(pointId, subject, pointTitle) {
  let point = null;
  try {
    if (pointId) {
      const response = await fetch('/kg/point?point_id=' + encodeURIComponent(pointId));
      if (response.ok) {
        const payload = await response.json();
        if (payload && payload.chapter_id) point = payload;
      }
    }
    if (!point) {
      const response = await fetch('/kg/subjects');
      if (!response.ok) throw new Error('知识图谱目录加载失败');
      const subjectsData = await response.json();
      const subjectEntry = subjectsData.find(item => item.subject === subject);
      for (const chapter of (subjectEntry?.chapters || [])) {
        const matched = (chapter.points || []).find(item => item.title === pointTitle);
        if (matched) {
          point = {
            ...matched,
            subject,
            chapter_id: chapter.chapter_id,
            chapter_title: chapter.chapter_title,
          };
          break;
        }
      }
    }
    if (!point?.chapter_id) throw new Error('未找到该知识点所在章节');
    await openChapterDetail(
      point.subject || subject,
      point.chapter_id,
      point.chapter_title || '',
      0
    );
    const cards = Array.from(document.querySelectorAll('.chapter-point-card'));
    const target = cards.find(card =>
      (point.id && card.dataset.pointId === String(point.id))
      || card.dataset.pointTitle === String(point.title || pointTitle)
    );
    if (target) {
      target.classList.add('is-profile-target');
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      window.setTimeout(() => target.classList.remove('is-profile-target'), 2600);
    }
  } catch (error) {
    console.warn('知识点定位失败:', error);
    switchView('knowledge-graph');
  }
}

function showNodeDetail(node) {
  const detailPanel = document.getElementById('kgDetailPanel');
  if (!detailPanel) return;

  if (node.type === 'subject') {
    const subj = kgState.subjects.find(s => s.subject === node.subject);
    if (!subj) {
      detailPanel.innerHTML = '<h3 class="detail-title">' + escapeHtml(node.label) + '</h3><div class="detail-content">暂无数据</div>';
      return;
    }
    detailPanel.innerHTML = `
      <h3 class="detail-title">${escapeHtml(node.label)}</h3>
      <div class="detail-content">
        <p>该科目共 ${subj.point_count} 个知识点，分 ${subj.chapter_count} 个章节。</p>
        <h4>章节列表（点击图谱中的章节节点查看）：</h4>
        <ul>
          ${subj.chapters.map(ch => '<li>第 ' + ch.chapter_order + ' 章：' + escapeHtml(ch.chapter_title) + '（' + ch.point_count + ' 个知识点）</li>').join('')}
        </ul>
      </div>
    `;
  } else {
    detailPanel.innerHTML = '<h3 class="detail-title">知识点详情</h3><div class="detail-content">点击章节可查看本章清单；点击知识点节点可查看讲解、考法、掌握度和关联路径。</div>';
  }
}

function switchView(viewName) {
  document.querySelectorAll('.nav-item').forEach(item => {
    item.classList.remove('active');
    if (item.dataset.view === viewName) {
      item.classList.add('active');
    }
  });

  document.querySelectorAll('.view').forEach(view => {
    view.classList.remove('active');
  });

  let viewId = 'chat';
  switch (viewName) {
    case 'question-bank':
      viewId = 'question-bank-view';
      break;
    case 'question-bank-detail':
      viewId = 'question-bank-detail-view';
      break;
    case 'exam':
      viewId = 'exam-view';
      loadExamHome();
      break;
    case 'daily-push':
      viewId = 'daily-push-view';
      loadDailyContent();
      break;
    case 'study-plan':
      viewId = 'study-plan-view';
      loadStudyPlan();
      break;
    case 'school-selection':
      viewId = 'school-selection-view';
      loadSchoolLearningSnapshot();
      {
        const schoolView = document.getElementById('school-selection-view');
        const controllerUrl = schoolView?.dataset.controllerUrl || '/static/views/school-selection.js';
        window.KaoyanRuntime.loadScript(controllerUrl, 'KaoyanSchoolSelectionView')
          .then(controller => controller?.init?.())
          .catch(error => console.warn('择校视图加载失败', error));
      }
      break;
    case 'profile':
      viewId = 'profile-view';
      loadProfile();
      break;
    case 'knowledge-graph':
      viewId = 'knowledge-graph-view';
      break;
    case 'chapter-detail':
      viewId = 'chapter-detail-view';
      break;
    default:
      viewId = 'chat-view';
  }

  const view = document.getElementById(viewId);
  if (view) {
    view.classList.add('active');
  }

  // 如果是知识图谱视图，初始化
  if (viewName === 'knowledge-graph') {
    initKnowledgeGraph();
  }
}

async function loadSchoolLearningSnapshot() {
  const container = document.getElementById('schoolLearningSnapshot');
  if (!container) return;
  try {
    const response = await fetch('/user/profile/summary');
    if (!response.ok) throw new Error('学习画像读取失败');
    const data = await response.json();
    const totalQuestions = Number(data.total_questions || 0);
    const answered = Number(data.total_answered || 0);
    const progress = totalQuestions ? answered / totalQuestions * 100 : 0;
    container.classList.remove('is-loading');
    if (answered <= 0) {
      container.innerHTML = `
        <span>个人学习画像 · 等待数据</span>
        <strong>还没有做题记录</strong>
        <small>完成题目后，进度、正确率和四科均衡度会自动加入择校判断。</small>`;
      return;
    }
    container.innerHTML = `
      <span>个人学习画像 · 自动纳入</span>
      <strong>${answered} 题 · ${Number(data.accuracy || 0).toFixed(1)}% 正确率</strong>
      <small>当前题库覆盖率 ${progress.toFixed(1)}%，还会衡量趋势、速度、重做改善和遗忘风险。</small>`;
  } catch (_) {
    container.classList.remove('is-loading');
    container.innerHTML = `
      <span>个人学习画像</span>
      <strong>暂无可用做题记录</strong>
      <small>完成题目后，进度和正确率会自动加入择校判断。</small>`;
  }
}

function parseSchoolScores(raw) {
  const entries = String(raw || '')
    .split(/[,，;；\n]+/)
    .map(item => item.trim())
    .filter(Boolean);
  const scores = [];
  const years = [];
  let everyEntryHasYear = entries.length > 0;
  entries.forEach((entry) => {
    const match = entry.match(/(?:(20\d{2})\s*[:：\-]?\s*)?([1-4]\d{2})(?:\s*分)?/);
    if (!match) return;
    scores.push(Number(match[2]));
    if (match[1]) years.push(Number(match[1]));
    else everyEntryHasYear = false;
  });
  return { scores, years: everyEntryHasYear ? years : [] };
}

let activeSchoolSelectionStream = null;
let activeSchoolSelectionRunId = null;

function renderSchoolAgentRun(run) {
  const result = document.getElementById('schoolSelectionResult');
  if (!result) return;
  const stages = run.stages || {};
  const stageRows = [
    ['profile', '读取个人学习画像'],
    ['research', '检索官方、机构与公开热度'],
    ['synthesis', '生成个性化研判与行动建议'],
  ];
  const terminal = ['completed', 'failed', 'cancelled'].includes(run.status);
  result.innerHTML = `
    <div class="school-agent-run">
      <div class="school-agent-run-head">
        <div>
          <span class="school-form-kicker">AGENT RUN</span>
          <h2>${escapeHtml(run.message || '正在执行择校分析')}</h2>
        </div>
        <strong>${Math.round(Number(run.progress || 0))}%</strong>
      </div>
      <div class="school-agent-progress"><i style="width:${Math.max(2, Math.min(100, Number(run.progress || 0)))}%"></i></div>
      <div class="school-agent-stages">
        ${stageRows.map(([key, label]) => {
          const status = stages[key]?.status || 'pending';
          return `<div class="school-agent-stage is-${escapeHtml(status)}">
            <span class="school-stage-dot"></span>
            <div><strong>${label}</strong><small>${escapeHtml(stages[key]?.message || '')}</small></div>
            <em>${status === 'completed' ? '已完成' : status === 'running' ? '进行中' : status === 'failed' ? '失败' : '等待'}</em>
          </div>`;
        }).join('')}
      </div>
      ${run.partial?.learning_snapshot ? `
        <div class="school-agent-partial">
          已读取 ${Number(run.partial.learning_snapshot.attempted || 0)} 道作答，
          正确率 ${Number(run.partial.learning_snapshot.accuracy || 0).toFixed(1)}%，
          题库进度 ${Number(run.partial.learning_snapshot.progress || 0).toFixed(1)}%
        </div>` : ''}
      ${run.partial?.research ? `
        <div class="school-agent-partial">
          已核验 ${Number(run.partial.research.evidence_count || 0)} 条来源；
          公开关注度 ${Number(run.partial.research.heat?.score || 0)}/100
        </div>` : ''}
      <div class="school-agent-actions">
        ${!terminal ? '<button type="button" class="school-secondary-btn" onclick="cancelSchoolSelectionRun()">取消任务</button>' : ''}
        ${run.status === 'failed' || run.status === 'cancelled'
          ? '<button type="button" class="school-analyze-btn compact" onclick="retrySchoolSelectionRun()">重试失败步骤</button>'
          : ''}
      </div>
      ${run.error ? `<div class="school-error"><span>${escapeHtml(run.error)}</span></div>` : ''}
    </div>`;
}

function finishSchoolSelectionButton() {
  const button = document.getElementById('schoolAnalyzeBtn');
  if (!button) return;
  button.disabled = false;
  button.classList.remove('is-loading');
  button.querySelector('span').textContent = '开始综合分析';
}

function followSchoolSelectionRun(runId, initialRun) {
  activeSchoolSelectionStream?.close();
  activeSchoolSelectionRunId = runId;
  renderSchoolAgentRun(initialRun);
  const stream = new EventSource(`/school-selection/runs/${encodeURIComponent(runId)}/events`);
  activeSchoolSelectionStream = stream;
  stream.addEventListener('update', (event) => {
    const run = JSON.parse(event.data);
    if (run.status === 'completed' && run.result) {
      stream.close();
      renderSchoolSelectionResult(run.result);
      finishSchoolSelectionButton();
      return;
    }
    renderSchoolAgentRun(run);
    if (['failed', 'cancelled'].includes(run.status)) finishSchoolSelectionButton();
  });
  stream.addEventListener('done', (event) => {
    const run = JSON.parse(event.data);
    stream.close();
    if (run.status === 'completed' && run.result) renderSchoolSelectionResult(run.result);
    else renderSchoolAgentRun(run);
    finishSchoolSelectionButton();
  });
  stream.onerror = () => {
    stream.close();
    fetch(`/school-selection/runs/${encodeURIComponent(runId)}`)
      .then(response => response.json())
      .then(run => {
        if (run.status === 'completed' && run.result) renderSchoolSelectionResult(run.result);
        else renderSchoolAgentRun(run);
        if (['completed', 'failed', 'cancelled'].includes(run.status)) finishSchoolSelectionButton();
      })
      .catch(() => finishSchoolSelectionButton());
  };
}

async function cancelSchoolSelectionRun() {
  if (!activeSchoolSelectionRunId) return;
  const response = await fetch(`/school-selection/runs/${encodeURIComponent(activeSchoolSelectionRunId)}/cancel`, {
    method: 'POST',
  });
  if (response.ok) renderSchoolAgentRun(await response.json());
}

async function retrySchoolSelectionRun() {
  if (!activeSchoolSelectionRunId) return;
  const response = await fetch(`/school-selection/runs/${encodeURIComponent(activeSchoolSelectionRunId)}/retry`, {
    method: 'POST',
  });
  const run = await response.json();
  if (!response.ok) throw new Error(run.detail || '重试失败');
  const button = document.getElementById('schoolAnalyzeBtn');
  if (button) {
    button.disabled = true;
    button.classList.add('is-loading');
  }
  followSchoolSelectionRun(activeSchoolSelectionRunId, run);
}

async function runSchoolSelectionAnalysis() {
  const school = document.getElementById('schoolNameInput')?.value.trim();
  const major = document.getElementById('schoolMajorInput')?.value.trim();
  const targetRaw = document.getElementById('schoolTargetScoreInput')?.value;
  const parsedScores = parseSchoolScores(document.getElementById('schoolScoresInput')?.value);
  const result = document.getElementById('schoolSelectionResult');
  const button = document.getElementById('schoolAnalyzeBtn');
  if (!school || !major || !result || !button) return;
  if (parsedScores.scores.some(score => score < 100 || score > 500)) {
    result.innerHTML = '<div class="school-error">历史分数应在 100 到 500 之间。</div>';
    return;
  }

  button.disabled = true;
  button.classList.add('is-loading');
  button.querySelector('span').textContent = '正在检索与分析';
  renderSchoolAgentRun({
    status: 'queued',
    progress: 2,
    message: '正在创建可恢复的分析任务',
    stages: {},
  });

  try {
    const response = await fetch('/school-selection/runs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        school,
        major,
        historical_scores: parsedScores.scores,
        score_years: parsedScores.years,
        target_score: targetRaw ? Number(targetRaw) : null,
      }),
    });
    const data = await response.json();
    if (!response.ok) {
      const detail = Array.isArray(data.detail)
        ? data.detail.map(item => item.msg).join('；')
        : data.detail;
      throw new Error(detail || '择校分析失败');
    }
    followSchoolSelectionRun(data.run_id, data);
  } catch (error) {
    result.innerHTML = `
      <div class="school-error">
        <strong>分析未完成</strong>
        <span>${escapeHtml(error.message || '网络服务暂时不可用')}</span>
      </div>`;
    finishSchoolSelectionButton();
  }
}

function safeExternalUrl(raw) {
  try {
    const url = new URL(String(raw || ''));
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '#';
  } catch (_) {
    return '#';
  }
}

function renderSchoolSelectionResult(data) {
  const container = document.getElementById('schoolSelectionResult');
  if (!container) return;
  const trend = data.trend || {};
  const heat = data.heat || {};
  const risk = data.risk || {};
  const institution = data.institution_consensus || {};
  const readiness = data.learning_readiness || {};
  const predicted = trend.predicted_range;
  const evidence = Array.isArray(data.evidence) ? data.evidence : [];
  const readinessSubjects = readiness.subjects && typeof readiness.subjects === 'object'
    ? Object.entries(readiness.subjects) : [];
  const signals = readiness.signals || {};
  const sourceLabels = {
    official: '官方',
    institution: '机构',
    community: '讨论',
  };

  container.innerHTML = `
    <div class="school-result-shell">
      <div class="school-result-hero">
        <div>
          <span class="school-form-kicker">综合研判</span>
          <h2>${escapeHtml(data.school)} · ${escapeHtml(data.major)}</h2>
          <p>${escapeHtml(data.generated_at || '')} 更新</p>
        </div>
        <div class="school-risk-seal risk-${risk.score >= 70 ? 'high' : risk.score >= 40 ? 'medium' : 'low'}">
          <strong>${escapeHtml(risk.level || '待评估')}</strong>
          <span>${Math.round(Number(risk.confidence || 0) * 100)}% 置信度</span>
        </div>
      </div>

      <div class="school-metric-grid">
        <article class="school-metric-card">
          <span>趋势区间</span>
          <strong>${predicted ? `${predicted[0]}–${predicted[1]}` : '数据不足'}</strong>
          <small>${escapeHtml(trend.direction || '等待历史分数')}</small>
        </article>
        <article class="school-metric-card heat-card">
          <span>公开关注度代理</span>
          <strong>${Number(heat.score || 0)}<em>/100</em></strong>
          <small>${escapeHtml(heat.level || '数据不足')}</small>
          <div class="school-meter"><i style="width:${Math.max(0, Math.min(100, Number(heat.score || 0)))}%"></i></div>
        </article>
        <article class="school-metric-card">
          <span>机构摘要样本</span>
          <strong>${Number(institution.sample_size || 0)}</strong>
          <small>${institution.available ? `提及中位数 ${institution.median}` : '暂无可核验预测'}</small>
        </article>
        <article class="school-metric-card">
          <span>风险指数</span>
          <strong>${Number(risk.score || 0)}</strong>
          <small>${(risk.reasons || []).length} 项主要因素</small>
        </article>
      </div>

      <div class="school-readiness-card">
        <div class="school-readiness-head">
          <div>
            <span class="school-form-kicker">PERSONAL FIT</span>
            <h3>你的学习画像已纳入判断</h3>
          </div>
          <div class="school-readiness-score">
            <strong>${readiness.available ? Number(readiness.score || 0) : '—'}</strong>
            <span>${escapeHtml(readiness.level || '等待学习数据')}</span>
          </div>
        </div>
        <div class="school-readiness-metrics">
          <span><strong>${Number(readiness.attempted || 0)}</strong> 已做题数</span>
          <span><strong>${Number(readiness.progress || 0).toFixed(1)}%</strong> 题库进度</span>
          <span><strong>${Number(readiness.accuracy || 0).toFixed(1)}%</strong> 当前正确率</span>
        </div>
        <div class="school-signal-grid">
          ${signals.difficulty_weighted_accuracy != null ? `<span>难度加权 <strong>${Number(signals.difficulty_weighted_accuracy).toFixed(1)}%</strong></span>` : ''}
          ${signals.recent_trend_delta != null ? `<span>近30天趋势 <strong>${Number(signals.recent_trend_delta) >= 0 ? '+' : ''}${Number(signals.recent_trend_delta).toFixed(1)}%</strong></span>` : ''}
          ${signals.repeat_improvement != null ? `<span>重做提升 <strong>${Number(signals.repeat_improvement) >= 0 ? '+' : ''}${Number(signals.repeat_improvement).toFixed(1)}%</strong></span>` : ''}
          ${signals.speed_score != null ? `<span>速度指数 <strong>${Number(signals.speed_score).toFixed(0)}</strong></span>` : ''}
          ${signals.retention_score != null ? `<span>记忆保持 <strong>${Number(signals.retention_score).toFixed(0)}</strong></span>` : ''}
          ${signals.plan_completion != null ? `<span>计划完成 <strong>${Number(signals.plan_completion).toFixed(1)}%</strong></span>` : ''}
        </div>
        <div class="school-subject-fit-list">
          ${readinessSubjects.map(([subject, item]) => `
            <div class="school-subject-fit">
              <span>${escapeHtml(subject)}</span>
              <div><i style="width:${Math.max(0, Math.min(100, Number(item.progress || 0)))}%"></i></div>
              <small>${Number(item.attempted || 0) > 0
                ? `${Number(item.accuracy || 0).toFixed(1)}% 正确`
                : '未开始'}</small>
            </div>`).join('') || '<p>完成一些题目后，这里会展示四科进度与正确率。</p>'}
        </div>
        <p class="school-readiness-note">${escapeHtml(readiness.note || '')}</p>
      </div>

      <div class="school-summary-card">
        <div class="school-section-title"><span>01</span><h3>分析报告</h3></div>
        <div id="schoolSummaryMarkdown" class="school-summary-markdown"></div>
      </div>

      <div class="school-action-card">
        <div class="school-section-title"><span>02</span><div><h3>把结论变成下一步</h3><p>计划、练习和目标模拟均使用当前学习画像</p></div></div>
        <div class="school-action-grid">
          <button type="button" onclick="createSchoolSelectionPlan()">生成 14 天提升计划<small>写入学习计划，可逐日执行</small></button>
          <button type="button" onclick="startWeakSubjectPractice()">练习最薄弱科目<small>${escapeHtml((readiness.weak_subjects || [])[0] || '自动选择')}</small></button>
          <button type="button" onclick="toggleSchoolSimulation()">模拟提升后的结果<small>调整正确率和做题进度</small></button>
        </div>
        <div id="schoolActionFeedback" class="school-action-feedback"></div>
        <div id="schoolSimulationPanel" class="school-simulation-panel" hidden>
          <label>目标正确率 <input id="schoolSimAccuracy" type="range" min="30" max="100" value="${Math.max(60, Math.round(Number(readiness.accuracy || 60)))}"><output>${Math.max(60, Math.round(Number(readiness.accuracy || 60)))}%</output></label>
          <label>目标题库进度 <input id="schoolSimProgress" type="range" min="5" max="100" value="${Math.max(30, Math.round(Number(readiness.progress || 30)))}"><output>${Math.max(30, Math.round(Number(readiness.progress || 30)))}%</output></label>
          <button type="button" class="school-analyze-btn compact" onclick="simulateSchoolSelection()">运行模拟</button>
          <div id="schoolSimulationResult"></div>
        </div>
      </div>

      <div class="school-evidence-card">
        <div class="school-section-title">
          <span>03</span>
          <div><h3>来源证据</h3><p>官方优先，机构与讨论分层展示</p></div>
        </div>
        <div class="school-evidence-list">
          ${evidence.length ? evidence.map(item => {
            const url = safeExternalUrl(item.url);
            const type = ['official', 'institution', 'community'].includes(item.source_type)
              ? item.source_type : 'community';
            return `
              <a class="school-evidence-item" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">
                <span class="school-source-badge ${type}">${sourceLabels[type]}</span>
                <span class="school-evidence-copy">
                  <strong>${escapeHtml(item.title || '未命名来源')}</strong>
                  <small>${escapeHtml(item.snippet || item.source_label || '')}</small>
                </span>
                <time>${item.year || '—'}</time>
              </a>`;
          }).join('') : '<div class="school-no-evidence">暂未检索到公开网页证据，请直接核对院校研究生招生官网。</div>'}
        </div>
      </div>

      <div class="school-method-card">
        <strong>口径说明</strong>
        <p>${escapeHtml(data.methodology || '')}</p>
        <p>${escapeHtml(data.disclaimer || '')}</p>
      </div>
    </div>`;

  const summary = document.getElementById('schoolSummaryMarkdown');
  if (summary) _renderMarkdownInto(summary, data.summary || '暂无分析摘要。');
  window.currentSchoolSelectionResult = data;
  document.querySelectorAll('.school-simulation-panel input[type="range"]').forEach(input => {
    input.addEventListener('input', () => {
      if (input.nextElementSibling) input.nextElementSibling.value = `${input.value}%`;
    });
  });
}

function schoolActionFeedback(message, kind = '') {
  const feedback = document.getElementById('schoolActionFeedback');
  if (!feedback) return;
  feedback.className = `school-action-feedback ${kind}`;
  feedback.textContent = message;
}

async function createSchoolSelectionPlan() {
  const data = window.currentSchoolSelectionResult;
  if (!data) return;
  schoolActionFeedback('正在把择校差距拆成 14 天任务…', 'is-loading');
  try {
    const response = await fetch('/school-selection/actions/plan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        school: data.school,
        major: data.major,
        risk: data.risk,
        learning_readiness: data.learning_readiness,
      }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '计划生成失败');
    schoolActionFeedback(`已写入 ${result.plan?.total_tasks || 14} 个可执行任务，正在打开学习计划。`, 'is-success');
    setTimeout(() => switchView('study-plan'), 700);
  } catch (error) {
    schoolActionFeedback(error.message || '计划生成失败', 'is-error');
  }
}

async function startWeakSubjectPractice() {
  const data = window.currentSchoolSelectionResult;
  if (!data) return;
  schoolActionFeedback('正在匹配薄弱科目的真实题目…', 'is-loading');
  try {
    const response = await fetch('/school-selection/actions/practice', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ learning_readiness: data.learning_readiness }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '练习匹配失败');
    state.currentSubject = result.subject;
    state.filters.subject = result.subject;
    const filter = document.getElementById('subjectFilter');
    if (filter) filter.value = result.subject;
    document.querySelectorAll('.subject-tab').forEach(tab => {
      tab.classList.toggle('active', tab.dataset.subject === result.subject);
    });
    schoolActionFeedback(`已匹配 ${result.subject} 的 ${result.question_ids.length} 道优先题目。`, 'is-success');
    switchView('question-bank');
    await loadQuestions(1);
  } catch (error) {
    schoolActionFeedback(error.message || '练习匹配失败', 'is-error');
  }
}

function toggleSchoolSimulation() {
  const panel = document.getElementById('schoolSimulationPanel');
  if (panel) panel.hidden = !panel.hidden;
}

async function simulateSchoolSelection() {
  const accuracy = Number(document.getElementById('schoolSimAccuracy')?.value || 0);
  const progress = Number(document.getElementById('schoolSimProgress')?.value || 0);
  const container = document.getElementById('schoolSimulationResult');
  if (!container) return;
  container.textContent = '正在计算画像变化…';
  try {
    const response = await fetch('/school-selection/simulate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ accuracy, progress }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || '模拟失败');
    container.innerHTML = `
      <strong>${Number(result.baseline?.score || 0)} → ${Number(result.projected?.score || 0)}</strong>
      <span>适配度 ${Number(result.score_delta) >= 0 ? '+' : ''}${Number(result.score_delta || 0).toFixed(1)}；${escapeHtml(result.interpretation || '')}</span>`;
  } catch (error) {
    container.textContent = error.message || '模拟失败';
  }
}

function setupChapterBackButton() {
  const btn = document.getElementById('chapterBackBtn');
  if (btn) {
    btn.addEventListener('click', () => switchView('knowledge-graph'));
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupChapterBackButton);
} else {
  setupChapterBackButton();
}

function setupInteractionEnhancements() {
  const interactiveSelector = [
    '.dash-stat-card',
    '.dash-card',
    '.subject-progress-card',
    '.question-card',
    '.content-card',
    '.profile-section',
    '.stat-card',
    '.subject-stat',
    '.weak-point-item',
    '.chapter-point-card',
    '.pdf-list a'
  ].join(',');

  document.addEventListener('pointermove', (event) => {
    const target = event.target.closest(interactiveSelector);
    if (!target) return;
    const rect = target.getBoundingClientRect();
    const x = ((event.clientX - rect.left) / rect.width) * 100;
    const y = ((event.clientY - rect.top) / rect.height) * 100;
    target.style.setProperty('--mx', `${x}%`);
    target.style.setProperty('--my', `${y}%`);
    target.classList.add('interactive-glow');
  });

  document.addEventListener('pointerdown', (event) => {
    const target = event.target.closest('button, .question-card, .dash-stat-card-highlight, .pdf-list a');
    if (!target) return;
    target.classList.add('press-feedback');
  });

  document.addEventListener('pointerup', () => {
    document.querySelectorAll('.press-feedback').forEach(el => {
      window.setTimeout(() => el.classList.remove('press-feedback'), 120);
    });
  });

  document.addEventListener('pointercancel', () => {
    document.querySelectorAll('.press-feedback').forEach(el => el.classList.remove('press-feedback'));
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupInteractionEnhancements);
} else {
  setupInteractionEnhancements();
}

// ============================================================
// 学习计划 (引导问答 + AI 生成 + 持久化)
// ============================================================
let _planState = { questions: [], answers: {}, idx: 0 };
let _studyPlanCache = null;
let _studyPlanCacheOwner = null;
let _studyPlanLoadedOnce = false;
let _studyPlanLoadSeq = 0;
const _planEditConversations = new Map();
let _planAiEditorOpen = false;

function studyPlanCacheKey() {
  const token = getToken();
  return 'kaoyan_study_plan_cache:' + (token ? token.slice(-24) : 'anonymous');
}

function readStudyPlanCache() {
  const key = studyPlanCacheKey();
  if (_studyPlanCache && _studyPlanCacheOwner === key) return _studyPlanCache;
  _studyPlanCache = null;
  _studyPlanCacheOwner = key;
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== 'object') return null;
    _studyPlanCache = parsed;
    return parsed;
  } catch (e) {
    console.warn('读取学习计划缓存失败', e);
    return null;
  }
}

function writeStudyPlanCache(payload) {
  const key = studyPlanCacheKey();
  _studyPlanCacheOwner = key;
  _studyPlanCache = {
    plan: payload?.plan || null,
    questions: payload?.questions || _planState.questions || [],
    draft: payload?.draft || null,
    savedAt: new Date().toISOString(),
  };
  try {
    localStorage.setItem(key, JSON.stringify(_studyPlanCache));
  } catch (e) {
    console.warn('保存学习计划缓存失败', e);
  }
}

function clearStudyPlanCache() {
  const key = studyPlanCacheKey();
  _studyPlanCache = null;
  _studyPlanCacheOwner = null;
  try { localStorage.removeItem(key); } catch {}
}

function currentPlanEditConversation() {
  const key = studyPlanCacheKey();
  if (!_planEditConversations.has(key)) {
    _planEditConversations.set(key, [{
      role: 'assistant',
      content: '告诉我想调整哪一周或哪项任务。我只能修改计划内容，不能改动打卡和完成进度。'
    }]);
  }
  return _planEditConversations.get(key);
}

function planEditorMessagesHtml() {
  return currentPlanEditConversation().map(item => `
    <div class="plan-ai-message is-${item.role === 'user' ? 'user' : 'assistant'}">
      ${escapeHtml(item.content || '')}
  </div>`).join('');
}

function handlePlanAiEscape(event) {
  if (event.key === 'Escape') setPlanAiEditorOpen(false);
}

function setPlanAiEditorOpen(open) {
  const backdrop = document.getElementById('planAiBackdrop');
  const openButton = document.getElementById('openPlanAiBtn');
  _planAiEditorOpen = Boolean(open && backdrop);
  document.body.classList.toggle('plan-ai-drawer-open', _planAiEditorOpen);
  openButton?.setAttribute('aria-expanded', _planAiEditorOpen ? 'true' : 'false');
  document.removeEventListener('keydown', handlePlanAiEscape);
  if (!backdrop) return;
  backdrop.hidden = !_planAiEditorOpen;
  if (_planAiEditorOpen) {
    document.addEventListener('keydown', handlePlanAiEscape);
    window.setTimeout(() => document.getElementById('planAiInput')?.focus(), 80);
  } else {
    openButton?.focus();
  }
}

function bindPlanAiEditor() {
  const openButton = document.getElementById('openPlanAiBtn');
  const backdrop = document.getElementById('planAiBackdrop');
  const panel = document.getElementById('planAiEditor');
  const closeButton = document.getElementById('closePlanAiBtn');
  const input = document.getElementById('planAiInput');
  const sendButton = document.getElementById('planAiSendBtn');
  if (!openButton || !backdrop || !panel || !input || !sendButton) return;

  openButton.addEventListener('click', () => setPlanAiEditorOpen(true));
  closeButton?.addEventListener('click', () => setPlanAiEditorOpen(false));
  backdrop.addEventListener('click', event => {
    if (event.target === backdrop) setPlanAiEditorOpen(false);
  });
  setPlanAiEditorOpen(_planAiEditorOpen);

  const submit = async () => {
    const message = (input.value || '').trim();
    if (!message || sendButton.disabled) return;
    const conversation = currentPlanEditConversation();
    const priorHistory = conversation.slice(-8);
    conversation.push({ role: 'user', content: message });
    input.value = '';
    sendButton.disabled = true;
    sendButton.textContent = '修改中…';
    const messages = panel.querySelector('.plan-ai-messages');
    if (messages) {
      messages.innerHTML = planEditorMessagesHtml() + '<div class="plan-ai-message is-assistant is-pending">正在核对可修改范围…</div>';
      messages.scrollTop = messages.scrollHeight;
    }
    try {
      const response = await fetch('/study-plan/modify', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message, conversation_history: priorHistory })
      });
      const data = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(data.detail || '计划修改失败');
      conversation.push({
        role: 'assistant',
        content: data.reply || (data.success ? '计划已修改。' : '没有应用任何修改。')
      });
      if (data.plan) {
        writeStudyPlanCache({ plan: data.plan, questions: _planState.questions });
        _planAiEditorOpen = true;
        renderStudyPlanView(data.plan);
      }
    } catch (error) {
      conversation.push({ role: 'assistant', content: '修改失败：' + String(error.message || error) });
      const latestMessages = panel.querySelector('.plan-ai-messages');
      if (latestMessages) latestMessages.innerHTML = planEditorMessagesHtml();
      sendButton.disabled = false;
      sendButton.textContent = '发送修改';
    }
  };

  sendButton.addEventListener('click', submit);
  input.addEventListener('keydown', event => {
    if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
      event.preventDefault();
      submit();
    }
  });
}

function saveStudyPlanDraft() {
  if (!_planState.questions.length) return;
  writeStudyPlanCache({
    plan: null,
    questions: _planState.questions,
    draft: { answers: _planState.answers, idx: _planState.idx },
  });
}

async function loadStudyPlan(options = {}) {
  const { force = false, silent = false } = options;
  const root = document.getElementById('studyPlanContent');
  if (!root) return;
  const seq = ++_studyPlanLoadSeq;
  const cached = readStudyPlanCache();

  if (!force && cached?.plan) {
    _planState.questions = cached.questions || _planState.questions || [];
    renderStudyPlanView(cached.plan, { cachedAt: cached.savedAt });
    if (_studyPlanLoadedOnce) return;
    _studyPlanLoadedOnce = true;
    loadStudyPlan({ force: true, silent: true });
    return;
  }

  if (!force && cached?.questions?.length) {
    _planState.questions = cached.questions;
    if (cached.draft) {
      _planState.answers = cached.draft.answers || {};
      _planState.idx = Math.min(cached.draft.idx || 0, Math.max(_planState.questions.length - 1, 0));
    }
    renderPlanQuestion();
    if (_studyPlanLoadedOnce) return;
    _studyPlanLoadedOnce = true;
    loadStudyPlan({ force: true, silent: true });
    return;
  }

  if (!silent) {
    root.innerHTML = '<div class="plan-loading">正在加载学习计划...</div>';
  }
  try {
    const resp = await fetch('/study-plan/current');
    if (!resp.ok) {
      const errText = await resp.text().catch(() => '');
      throw new Error('服务器返回错误(' + resp.status + ')' + (errText ? ': ' + errText.slice(0, 160) : ''));
    }
    const data = await resp.json();
    if (seq !== _studyPlanLoadSeq && !silent) return;
    _planState.questions = data.questions || [];
    if (data.plan) {
      writeStudyPlanCache(data);
      renderStudyPlanView(data.plan);
    } else {
      _planState.answers = {};
      _planState.idx = 0;
      writeStudyPlanCache({
        plan: null,
        questions: _planState.questions,
        draft: { answers: _planState.answers, idx: _planState.idx },
      });
      if (!silent) renderPlanQuestion();
    }
  } catch (e) {
    console.error('加载学习计划失败', e);
    if (silent && cached?.plan) return;
    root.innerHTML = `<div class="plan-error">
      <strong>学习计划加载失败</strong>
      <span>${escapeHtml(String(e))}</span>
      <button id="planLoadRetryBtn" class="plan-primary-btn">重试</button>
    </div>`;
    document.getElementById('planLoadRetryBtn')?.addEventListener('click', loadStudyPlan);
  }
}

function renderPlanQuestion() {
  if (_planAiEditorOpen) setPlanAiEditorOpen(false);
  const root = document.getElementById('studyPlanContent');
  if (!root) return;
  saveStudyPlanDraft();
  const q = _planState.questions[_planState.idx];
  if (!q) {
    if (_planState.questions.length) submitPlan();
    else root.innerHTML = '<div class="plan-empty">暂时没有可用的引导问题,请稍后重试。</div>';
    return;
  }
  const isLast = _planState.idx === _planState.questions.length - 1;
  const progress = Math.round((_planState.idx + 1) / _planState.questions.length * 100);
  const savedAnswer = _planState.answers[q.key] || '';
  const optionsHtml = q.type === 'text'
    ? `<textarea id="planAnswerText" class="plan-textarea" rows="4" placeholder="可填写额外要求,留空也可">${escapeHtml(savedAnswer === '(无)' ? '' : savedAnswer)}</textarea>`
    : q.options.map((opt, i) => `
        <button class="plan-option${savedAnswer === opt ? ' selected' : ''}" data-opt="${escapeHtml(opt)}" type="button">
          <span class="plan-option-index">${i + 1}</span>
          ${escapeHtml(opt)}
        </button>`).join('');
  root.innerHTML = `
    <div class="plan-builder">
      <div class="plan-progress-head">
        <span>学习计划引导</span>
        <strong>第 ${_planState.idx + 1} / ${_planState.questions.length} 题</strong>
      </div>
      <div class="plan-progress-track"><div style="width:${progress}%"></div></div>
      <h2 class="plan-question-title">${escapeHtml(q.title)}</h2>
      <div class="plan-options">${optionsHtml}</div>
      <div class="plan-actions">
        <button id="planPrevBtn" class="plan-secondary-btn" type="button" ${_planState.idx === 0 ? 'disabled' : ''}>上一题</button>
        <button id="planNextBtn" class="plan-primary-btn" type="button">${isLast ? '生成计划' : '下一题'}</button>
      </div>
    </div>
  `;
  // 绑定选择
  let selected = savedAnswer && q.type !== 'text' ? savedAnswer : null;
  root.querySelectorAll('.plan-option').forEach(btn => {
    btn.addEventListener('click', () => {
      root.querySelectorAll('.plan-option').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
      selected = btn.dataset.opt;
    });
  });
  document.getElementById('planPrevBtn').addEventListener('click', () => {
    _planState.idx = Math.max(0, _planState.idx - 1);
    saveStudyPlanDraft();
    renderPlanQuestion();
  });
  document.getElementById('planNextBtn').addEventListener('click', () => {
    if (q.type === 'text') {
      const val = (document.getElementById('planAnswerText').value || '').trim();
      _planState.answers[q.key] = val || '(无)';
    } else {
      if (!selected) { alert('请选择一个选项'); return; }
      _planState.answers[q.key] = selected;
    }
    _planState.idx += 1;
    saveStudyPlanDraft();
    renderPlanQuestion();
  });
}

async function submitPlan() {
  const root = document.getElementById('studyPlanContent');
  if (!root) return;
  root.innerHTML = '<div class="plan-loading"><strong>正在生成专属计划</strong><span>系统正在结合你的回答和做题数据,通常几秒内完成。</span></div>';
  try {
    const resp = await fetch('/study-plan/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ answers: _planState.answers })
    });
    if (!resp.ok) {
      const errBody = await resp.json().catch(async () => ({ detail: await resp.text().catch(() => '') }));
      throw new Error(errBody.detail || ('服务器返回错误(' + resp.status + ')'));
    }
    const data = await resp.json();
    if (data.plan) {
      writeStudyPlanCache({ plan: data.plan, questions: _planState.questions });
      renderStudyPlanView(data.plan);
    }
    else throw new Error('未返回计划');
  } catch (e) {
    console.error('生成计划失败', e);
    root.innerHTML = `<div class="plan-error">
      <strong>生成失败</strong>
      <span>${escapeHtml(String(e))}</span>
      <div class="plan-actions compact">
        <button id="planBackBtn" class="plan-secondary-btn" type="button">返回修改</button>
        <button id="planRetryBtn" class="plan-primary-btn" type="button">重试生成</button>
      </div>
    </div>`;
    document.getElementById('planBackBtn')?.addEventListener('click', () => {
      _planState.idx = Math.max(_planState.questions.length - 1, 0);
      renderPlanQuestion();
    });
    document.getElementById('planRetryBtn')?.addEventListener('click', submitPlan);
  }
}

function renderStudyPlanView(plan, meta = {}) {
  const root = document.getElementById('studyPlanContent');
  if (!root) return;
  const allTasks = (plan.weekly || []).flatMap(w => w.tasks || []);
  const doneCount = allTasks.filter(task => task.status === 'done').length;
  const totalCount = allTasks.length || Number(plan.total_tasks || 0);
  const progress = totalCount ? Math.round(doneCount / totalCount * 100) : 0;
  const firstIncomplete = (plan.weekly || []).findIndex(
    week => (week.tasks || []).some(task => task.status !== 'done')
  );
  const currentWeekIndex = Math.max(0, firstIncomplete);
  const weeklyHtml = (plan.weekly || []).map((w, weekIndex) => {
    const tasks = w.tasks || [];
    const weekDone = tasks.filter(task => task.status === 'done').length;
    const taskHtml = tasks.length ? tasks.map(task => {
      const done = task.status === 'done';
      const kpChips = (task.knowledge_points || []).map(
        kp => `<span class="plan-kp-chip">${escapeHtml(kp)}</span>`
      ).join('');
      return `
        <div class="dt-row plan-task-row ${done ? 'is-done' : ''}"
             data-task-id="${escapeHtml(task.id || '')}"
             data-task-type="${escapeHtml(task.type || '')}"
             data-task-scope="plan">
          <div class="plan-task-check">${done ? '✓' : escapeHtml(String(task.day || ''))}</div>
          <div class="dt-row-main">
            <div class="dt-title-line">
              <span class="dt-title">${escapeHtml(task.title || '')}</span>
              <span class="plan-task-date">${escapeHtml(task.scheduled_date || '')}</span>
            </div>
            <div class="plan-task-meta">
              <span>${escapeHtml(String(task.estimated_minutes || 0))} 分钟</span>
              <span>${escapeHtml(String(task.question_count || 0))} 道题</span>
              <span>${escapeHtml(String((task.knowledge_point_ids || []).length))} 个知识点</span>
            </div>
            <div class="plan-kp-chips">${kpChips}</div>
          </div>
          <div class="dt-actions">
            ${done
              ? `<button class="dt-btn dt-btn-done" disabled>✓ 已打卡</button>
                 <button class="dt-btn dt-btn-undo" data-action="uncomplete">撤销</button>`
              : `<button class="dt-btn dt-btn-start" data-action="start">开始任务</button>
                 <button class="dt-btn dt-btn-complete" data-action="complete" disabled>完成打卡</button>`}
          </div>
          <div class="dt-workspace" style="display:none;"></div>
        </div>`;
    }).join('') : (w.daily_tasks || []).map(
      task => `<div class="plan-legacy-task">${escapeHtml(task)}</div>`
    ).join('');
    return `
      <details class="plan-week-card" id="plan-week-${weekIndex + 1}" ${weekIndex === currentWeekIndex ? 'open' : ''}>
        <summary class="plan-week-head">
          <div><h3>第 ${escapeHtml(String(w.week || ''))} 周</h3><span>${escapeHtml(w.theme || '')}</span></div>
          <strong>${weekDone}/${tasks.length || (w.daily_tasks || []).length}</strong>
        </summary>
        <div class="plan-week-tasks">${taskHtml}</div>
      </details>`;
  }).join('');
  const planTocHtml = (plan.weekly || []).map((week, weekIndex) => {
    const tasks = week.tasks || [];
    const weekDone = tasks.filter(task => task.status === 'done').length;
    return `
      <button class="plan-toc-link${weekIndex === currentWeekIndex ? ' is-current' : ''}"
              type="button" data-plan-target="plan-week-${weekIndex + 1}">
        <span>第 ${escapeHtml(String(week.week || weekIndex + 1))} 周</span>
        <small>${weekDone}/${tasks.length || (week.daily_tasks || []).length}</small>
      </button>`;
  }).join('');
  const weakHtml = (plan.weak_subjects && plan.weak_subjects.length)
    ? `<div class="plan-note">基于你的做题数据,薄弱学科:${escapeHtml(plan.weak_subjects.join('、'))}</div>`
    : '';
  const answersHtml = Object.entries(plan.answers || {}).map(([k, v]) =>
    `<div class="plan-answer-row"><b>${escapeHtml(k)}</b><span>${escapeHtml(String(v))}</span></div>`
  ).join('');
  const cacheHtml = meta.cachedAt
    ? `<span class="plan-cache-note">已优先显示本地缓存,后台正在同步最新计划</span>`
    : '';
  root.innerHTML = `
    <div class="plan-result" id="plan-overview">
      <div class="plan-layout">
        <aside class="plan-toc" aria-label="学习计划目录">
          <div class="plan-toc-title">计划目录</div>
          <button class="plan-toc-link is-overview" type="button" data-plan-target="plan-overview">
            <span>计划总览</span><small>${progress}%</small>
          </button>
          <div class="plan-toc-weeks">${planTocHtml}</div>
        </aside>
        <div class="plan-content-column">
      <div class="plan-result-head">
        <div>
          <span class="plan-kicker">MY STUDY PLAN</span>
          <h2>我的学习计划</h2>
        </div>
        <div class="plan-head-actions">
          ${cacheHtml}
          <button id="openPlanAiBtn" class="plan-secondary-btn plan-ai-open-btn" type="button"
                  aria-haspopup="dialog" aria-expanded="false">AI 修改计划</button>
          <button id="refreshPlanBtn" class="plan-secondary-btn" type="button">刷新</button>
          <button id="regenPlanBtn" class="plan-secondary-btn" type="button">重新制定</button>
        </div>
      </div>
      <div class="plan-summary">
        <p>${escapeHtml(plan.ai_summary || '已根据你的回答生成专属学习计划')}</p>
        <span>创建于:${escapeHtml(plan.created_at || '')}</span>
      </div>
      <div class="plan-execution-progress">
        <div class="plan-execution-progress-head">
          <strong>${doneCount} / ${totalCount}</strong>
          <span>已完成任务 · ${progress}%</span>
        </div>
        <div class="plan-progress-track"><div style="width:${progress}%"></div></div>
        <p>覆盖 ${escapeHtml(String(plan.covered_knowledge_point_count || 0))} 个知识点；阅读知识点并完成题库练习后才能打卡。</p>
      </div>
      ${weakHtml}
      <div class="plan-section-title">完整 ${escapeHtml(String(plan.week_count || (plan.weekly || []).length))} 周执行计划</div>
      <div class="plan-week-grid">${weeklyHtml || '<p class="plan-empty">未生成周计划</p>'}</div>
      <details class="plan-answers">
        <summary>查看我的回答</summary>
        <div>${answersHtml}</div>
      </details>
        </div>
      </div>
      <div class="plan-ai-backdrop" id="planAiBackdrop" hidden>
        <aside class="plan-ai-editor" id="planAiEditor" role="dialog" aria-modal="true"
               aria-labelledby="planAiEditorTitle">
          <div class="plan-ai-editor-head">
            <div>
              <span id="planAiEditorTitle">AI 计划助手</span>
              <small>仅修改当前用户的计划内容</small>
            </div>
            <button id="closePlanAiBtn" class="plan-ai-close-btn" type="button" aria-label="关闭 AI 计划助手">×</button>
          </div>
          <div class="plan-ai-capabilities" aria-label="AI 计划助手使用范围">
            <div class="is-allowed">
              <b>可以修改</b>
              <span>未完成任务的科目、标题、日期、时长、题量，以及每周主题和计划摘要。</span>
            </div>
            <div class="is-denied">
              <b>不能修改</b>
              <span>已完成任务、打卡和完成率、错题本、掌握度、题库，以及其他用户的数据。</span>
            </div>
            <div class="plan-ai-example">
              <b>示例</b>
              <span>把第2周未完成任务改为操作系统，每天90分钟、12题。</span>
            </div>
          </div>
          <div class="plan-ai-messages" aria-live="polite">${planEditorMessagesHtml()}</div>
          <label class="plan-ai-input-label" for="planAiInput">修改要求</label>
          <textarea id="planAiInput" rows="4" maxlength="1200" placeholder="例如：把第 2 周未完成任务重点调整为操作系统，每天控制在 90 分钟。"></textarea>
          <button id="planAiSendBtn" class="plan-primary-btn" type="button">发送修改</button>
          <p class="plan-ai-safety">所有修改都会在保存前校验；超出范围的要求不会执行。</p>
        </aside>
      </div>
    </div>
  `;
  document.getElementById('refreshPlanBtn')?.addEventListener('click', () => {
    loadStudyPlan({ force: true });
  });
  document.getElementById('regenPlanBtn').addEventListener('click', () => {
    clearStudyPlanCache();
    _planState = { questions: _planState.questions, answers: {}, idx: 0 };
    renderPlanQuestion();
  });
  root.querySelectorAll('[data-plan-target]').forEach(button => {
    button.addEventListener('click', () => {
      const target = document.getElementById(button.dataset.planTarget || '');
      if (!target) return;
      if (target.tagName === 'DETAILS') target.open = true;
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
      root.querySelectorAll('.plan-toc-link').forEach(item => item.classList.remove('is-active'));
      button.classList.add('is-active');
    });
  });
  bindPlanAiEditor();
  bindPlanTaskEvents(root);
}

function updatePlanFromServer(plan) {
  if (!plan) return;
  writeStudyPlanCache({ plan, questions: _planState.questions });
  renderStudyPlanView(plan);
}

function bindPlanTaskEvents(root) {
  root.querySelectorAll('.plan-task-row').forEach(row => {
    const taskId = row.dataset.taskId;
    const workspace = row.querySelector('.dt-workspace');
    const startButton = row.querySelector('[data-action="start"]');
    const completeButton = row.querySelector('[data-action="complete"]');
    const undoButton = row.querySelector('[data-action="uncomplete"]');

    startButton?.addEventListener('click', async () => {
      if (workspace.dataset.loaded === '1') {
        const shouldOpen = workspace.style.display === 'none';
        workspace.style.display = shouldOpen ? 'block' : 'none';
        startButton.textContent = shouldOpen ? '收起任务' : '展开任务';
        return;
      }
      startButton.disabled = true;
      startButton.textContent = '加载中…';
      workspace.style.display = 'block';
      workspace.innerHTML = '<div class="dt-loading">正在加载知识点与题库练习…</div>';
      try {
        const response = await fetch('/study-plan/task/' + encodeURIComponent(taskId) + '/material');
        if (!response.ok) throw new Error('任务材料加载失败');
        const material = await response.json();
        renderTaskWorkspace(row, material);
        workspace.dataset.loaded = '1';
        startButton.disabled = false;
        startButton.textContent = '收起任务';
      } catch (error) {
        workspace.innerHTML = `<div class="dt-empty">${escapeHtml(String(error))}</div>`;
        startButton.disabled = false;
        startButton.textContent = '重试';
      }
    });

    completeButton?.addEventListener('click', async () => {
      completeButton.disabled = true;
      completeButton.textContent = '打卡中…';
      try {
        const response = await fetch('/study-plan/task/complete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: taskId }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '打卡失败');
        updatePlanFromServer(data.plan);
      } catch (error) {
        completeButton.disabled = false;
        completeButton.textContent = '完成打卡';
        alert(String(error));
      }
    });

    undoButton?.addEventListener('click', async () => {
      if (!confirm('确定撤销这项计划任务的打卡吗？')) return;
      undoButton.disabled = true;
      try {
        const response = await fetch('/study-plan/task/uncomplete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ task_id: taskId }),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(data.detail || '撤销失败');
        updatePlanFromServer(data.plan);
      } catch (error) {
        undoButton.disabled = false;
        alert(String(error));
      }
    });
  });
}

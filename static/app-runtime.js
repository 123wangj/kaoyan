(function () {
  'use strict';

  const QUEUE_KEY = 'kaoyan_offline_mutations_v1';
  const NOTE_DRAFT_PREFIX = 'kaoyan_note_draft_v1:';
  const scriptLoads = new Map();

  function debounce(fn, wait) {
    let timer = 0;
    return function (...args) {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => fn.apply(this, args), wait);
    };
  }

  function sanitizeHtml(html) {
    const template = document.createElement('template');
    template.innerHTML = String(html || '');
    const allowedTags = new Set([
      'A', 'B', 'BLOCKQUOTE', 'BR', 'CODE', 'DEL', 'EM', 'H1', 'H2', 'H3',
      'H4', 'H5', 'H6', 'HR', 'I', 'LI', 'OL', 'P', 'PRE', 'STRONG',
      'TABLE', 'TBODY', 'TD', 'TH', 'THEAD', 'TR', 'UL'
    ]);
    const allowedAttrs = new Set(['href', 'title']);
    const walker = document.createTreeWalker(template.content, NodeFilter.SHOW_ELEMENT);
    const elements = [];
    while (walker.nextNode()) elements.push(walker.currentNode);
    elements.forEach(element => {
      if (!allowedTags.has(element.tagName)) {
        element.replaceWith(...element.childNodes);
        return;
      }
      Array.from(element.attributes).forEach(attr => {
        if (!allowedAttrs.has(attr.name.toLowerCase())) element.removeAttribute(attr.name);
      });
      if (element.tagName === 'A') {
        const href = element.getAttribute('href') || '';
        if (!/^(https?:|mailto:|#|\/)/i.test(href)) element.removeAttribute('href');
        element.setAttribute('rel', 'noopener noreferrer');
        element.setAttribute('target', '_blank');
      }
    });
    return template.innerHTML;
  }

  function renderMarkdown(text) {
    const source = normalizeMathText(text)
      .replace(/\\([*_])/g, '$1')
      .replace(/\*{3,}([^*\n]+?)\*{3,}/g, '**$1**');
    const raw = window.marked && typeof window.marked.parse === 'function'
      ? window.marked.parse(source)
      : source.replace(/[&<>"']/g, char => ({
          '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;'
        })[char])
          .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
          .replace(/\n/g, '<br>');
    return sanitizeHtml(raw);
  }

  // Normalize the delimiter variants commonly produced by OCR and LLM output.
  // KaTeX itself deliberately accepts only the standard LaTeX delimiters.
  function normalizeMathText(text) {
    return String(text || '')
      .replace(/＄/g, '$')
      .replace(/\\\[([\s\S]*?)\\\]/g, (_, formula) => `\n$$${formula}$$\n`)
      .replace(/\\\(([^\n]*?)\\\)/g, (_, formula) => `$${formula}$`)
      .replace(/\$([^$\n]+?)\$\s*\//g, (_, formula) => `$${formula}$`)
      .replace(/\/\s*\$([^$\n]+?)\$/g, (_, formula) => `$${formula}$`);
  }

  function normalizeMathTextNodes(element) {
    if (!element || !element.ownerDocument) return;
    const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    nodes.forEach(node => {
      const parent = node.parentElement;
      if (!parent || parent.closest('.katex, pre, code, script, style, textarea')) return;
      const normalized = normalizeMathText(node.nodeValue || '');
      if (normalized !== node.nodeValue) node.nodeValue = normalized;
    });
  }

  function ensureStylesheet(href, marker) {
    if (document.querySelector(`link[data-runtime-style="${marker}"]`)) return;
    const link = document.createElement('link');
    link.rel = 'stylesheet';
    link.href = href;
    link.dataset.runtimeStyle = marker;
    document.head.appendChild(link);
  }

  function renderMath(element) {
    if (!element) return Promise.resolve();
    normalizeMathTextNodes(element);
    ensureStylesheet(
      'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.css',
      'katex'
    );
    return loadScript(
      'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/katex.min.js',
      'katex'
    ).then(() => loadScript(
      'https://cdn.jsdelivr.net/npm/katex@0.16.22/dist/contrib/auto-render.min.js',
      'renderMathInElement'
    )).then(() => {
      if (!element.isConnected || typeof window.renderMathInElement !== 'function') return;
      window.renderMathInElement(element, {
        delimiters: [
          { left: '$$', right: '$$', display: true },
          { left: '$', right: '$', display: false },
          { left: '\\[', right: '\\]', display: true },
          { left: '\\(', right: '\\)', display: false }
        ],
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
        throwOnError: false,
        strict: false
      });
    }).catch(() => {});
  }

  function renderMathText(element, text) {
    if (!element) return Promise.resolve();
    element.textContent = normalizeMathText(text);
    return renderMath(element);
  }

  function observeMath(root) {
    const observedRoot = root || document.body;
    if (!observedRoot || observedRoot.dataset.mathObserver === 'true') return null;
    observedRoot.dataset.mathObserver = 'true';
    const pending = new Set();
    let timer = 0;
    const containsMath = value => /＄|\$|\\\(|\\\)|\\\[|\\\]|\$\/|\/\$/.test(String(value || ''));
    const schedule = node => {
      const element = node.nodeType === Node.ELEMENT_NODE ? node : node.parentElement;
      if (!element || element.closest('.katex, pre, code, script, style, textarea')) return;
      const target = element.closest(
        '.message-content, .qa-chat-bubble, .question-card, .question-explanation, ' +
        '.exam-content, .dp-question-card, .dt-q, .view-container'
      ) || element;
      if (!containsMath(target.textContent)) return;
      pending.add(target);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => {
        const targets = Array.from(pending);
        pending.clear();
        targets.forEach(item => renderMath(item));
      }, 30);
    };
    const observer = new MutationObserver(mutations => {
      mutations.forEach(mutation => {
        if (mutation.type === 'characterData') schedule(mutation.target);
        mutation.addedNodes.forEach(schedule);
      });
    });
    observer.observe(observedRoot, { childList: true, subtree: true, characterData: true });
    schedule(observedRoot);
    return observer;
  }

  function loadScript(src, globalName) {
    if (globalName && window[globalName]) return Promise.resolve(window[globalName]);
    if (scriptLoads.has(src)) return scriptLoads.get(src);
    const promise = new Promise((resolve, reject) => {
      const finish = () => {
        if (globalName && !window[globalName]) {
          reject(new Error(`资源已加载但未提供 ${globalName}: ${src}`));
          return;
        }
        resolve(globalName ? window[globalName] : true);
      };
      const existing = document.querySelector(`script[data-lazy-src="${src}"]`);
      if (existing) {
        existing.addEventListener('load', finish, { once: true });
        existing.addEventListener('error', reject, { once: true });
        return;
      }
      const script = document.createElement('script');
      script.src = src;
      script.async = true;
      script.dataset.lazySrc = src;
      script.referrerPolicy = 'no-referrer';
      script.addEventListener('load', finish, { once: true });
      script.addEventListener('error', () => reject(new Error(`资源加载失败: ${src}`)), { once: true });
      document.head.appendChild(script);
    });
    scriptLoads.set(src, promise);
    return promise;
  }

  function compactDrawing(drawing) {
    const strokes = Array.isArray(drawing && drawing.strokes) ? drawing.strokes : [];
    return {
      version: 1,
      strokes: strokes.map(stroke => {
        const points = Array.isArray(stroke.points) ? stroke.points : [];
        const compact = points.filter((point, index) => {
          if (index === 0 || index === points.length - 1) return true;
          const previous = points[index - 1];
          const dx = Number(point.x || 0) - Number(previous.x || 0);
          const dy = Number(point.y || 0) - Number(previous.y || 0);
          return (dx * dx + dy * dy) >= 0.000004;
        }).map(point => ({
          x: Math.round(Number(point.x || 0) * 10000) / 10000,
          y: Math.round(Number(point.y || 0) * 10000) / 10000
        }));
        return {
          tool: stroke.tool === 'eraser' ? 'eraser' : 'pen',
          color: String(stroke.color || '#172554').slice(0, 16),
          size: Math.max(1, Math.min(30, Number(stroke.size || 4))),
          points: compact
        };
      }).filter(stroke => stroke.points.length)
    };
  }

  function readQueue() {
    try {
      const value = JSON.parse(localStorage.getItem(QUEUE_KEY) || '[]');
      return Array.isArray(value) ? value : [];
    } catch {
      return [];
    }
  }

  function writeQueue(items) {
    localStorage.setItem(QUEUE_KEY, JSON.stringify(items.slice(-100)));
  }

  function queueMutation(item) {
    const items = readQueue();
    const key = item.key || `${item.method || 'POST'}:${item.url}`;
    const next = items.filter(existing => existing.key !== key);
    next.push({ ...item, key, queuedAt: Date.now() });
    writeQueue(next);
  }

  async function flushMutations() {
    if (!navigator.onLine) return;
    const items = readQueue();
    if (!items.length) return;
    const remaining = [];
    for (const item of items) {
      try {
        const response = await fetch(item.url, {
          method: item.method || 'POST',
          headers: item.headers || { 'Content-Type': 'application/json' },
          body: item.body
        });
        if (!response.ok) remaining.push(item);
      } catch {
        remaining.push(item);
      }
    }
    writeQueue(remaining);
  }

  function saveNoteDraft(questionId, payload) {
    try {
      localStorage.setItem(NOTE_DRAFT_PREFIX + questionId, JSON.stringify({
        ...payload,
        savedAt: Date.now()
      }));
    } catch {}
  }

  function readNoteDraft(questionId) {
    try {
      return JSON.parse(localStorage.getItem(NOTE_DRAFT_PREFIX + questionId) || 'null');
    } catch {
      return null;
    }
  }

  function clearNoteDraft(questionId) {
    try { localStorage.removeItem(NOTE_DRAFT_PREFIX + questionId); } catch {}
  }

  async function registerServiceWorker() {
    if (!('serviceWorker' in navigator)) return null;
    try {
      const registration = await navigator.serviceWorker.register('/sw.js', { scope: '/' });
      const notifyUpdate = () => {
        if (document.getElementById('appUpdateBanner')) return;
        const banner = document.createElement('div');
        banner.id = 'appUpdateBanner';
        banner.style.cssText = [
          'position:fixed', 'right:18px', 'bottom:18px', 'z-index:10000',
          'display:flex', 'align-items:center', 'gap:12px', 'padding:12px 14px',
          'border-radius:12px', 'background:#123c3d', 'color:#fff',
          'box-shadow:0 14px 40px rgba(15,23,42,.28)', 'font-size:13px'
        ].join(';');
        banner.innerHTML = '<span>发现新版本</span><button type="button" style="border:0;border-radius:8px;padding:7px 10px;background:#fff;color:#123c3d;font-weight:700;cursor:pointer">立即刷新</button>';
        banner.querySelector('button').addEventListener('click', () => window.location.reload());
        document.body.appendChild(banner);
      };
      if (registration.waiting && navigator.serviceWorker.controller) notifyUpdate();
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing;
        if (!worker) return;
        worker.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) notifyUpdate();
        });
      });
      registration.update().catch(() => {});
      return registration;
    } catch {
      return null;
    }
  }

  async function notifyMemoryReview(items) {
    const due = (Array.isArray(items) ? items : []).filter(item => item && item.is_due);
    if (!due.length || !('Notification' in window) || Notification.permission !== 'granted') return;
    const todayKey = `kaoyan_review_notified:${new Date().toISOString().slice(0, 10)}`;
    if (localStorage.getItem(todayKey)) return;
    const registration = await navigator.serviceWorker?.ready;
    if (registration) {
      await registration.showNotification('今天有知识点需要复习', {
        body: `${due.length} 个知识点已到复习时间，点击开始今日巩固。`,
        icon: '/static/question_images/wd-mcq-_-003-18-81f062ee5d.png',
        tag: 'kaoyan-memory-review',
        data: { url: '/app#daily-push' }
      });
      localStorage.setItem(todayKey, '1');
    }
  }

  window.addEventListener('online', flushMutations);
  window.KaoyanRuntime = {
    debounce,
    sanitizeHtml,
    renderMarkdown,
    normalizeMathText,
    normalizeMathTextNodes,
    renderMath,
    renderMathText,
    observeMath,
    loadScript,
    compactDrawing,
    queueMutation,
    flushMutations,
    saveNoteDraft,
    readNoteDraft,
    clearNoteDraft,
    registerServiceWorker,
    notifyMemoryReview
  };

  const startMathObserver = () => observeMath(document.body);
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startMathObserver, { once: true });
  } else {
    startMathObserver();
  }
})();

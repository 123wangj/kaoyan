/* ============================================================
   408 Pilot · 主页交互
   - 粒子背景
   - 3D 倾斜卡片
   - 滚动入场
   - 数字递增
   - 模态登录 / 注册
   ============================================================ */
(function () {
  'use strict';

  // ---- 工具 ----
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const STORAGE_TOKEN = 'kaoyan_token';
  function getStoredToken() {
    try {
      return sessionStorage.getItem(STORAGE_TOKEN) || localStorage.getItem(STORAGE_TOKEN) || '';
    } catch {
      return '';
    }
  }
  function storeSessionToken(token) {
    try {
      if (token) sessionStorage.setItem(STORAGE_TOKEN, token);
      else sessionStorage.removeItem(STORAGE_TOKEN);
      localStorage.removeItem(STORAGE_TOKEN);
    } catch {}
  }
  const STORAGE_USER  = 'kaoyan_user';

  // ---- Toast ----
  const toastEl = $('#toast');
  let toastTimer = null;
  function toast(msg, type = 'success') {
    if (!toastEl) return;
    toastEl.textContent = msg;
    toastEl.className = 'toast show toast-' + type;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toastEl.className = 'toast';
    }, 2200);
  }

  // ---- 粒子背景：浮动 + 鼠标交互 + 点击涟漪 + 光晕 ----
  (function initParticles() {
    const canvas = $('#particleCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    let dpr = Math.min(window.devicePixelRatio || 1, 1.5); // 1.5x 控功耗
    let w, h;
    let particles = [];
    let mouse = { x: -9999, y: -9999, active: false };
    let ripples = [];          // 点击涟漪
    let trail = [];            // 鼠标拖尾点

    // 浅色科技风配色（紫 / 蓝 / 青 / 粉 / 琥珀）
    const COLORS = ['#6366f1', '#8b5cf6', '#06b6d4', '#ec4899', '#f59e0b', '#10b981'];
    const COUNT_DESKTOP = 90;
    const COUNT_MOBILE  = 36;
    const LINK_DIST = 140;        // 连线距离
    const MOUSE_R   = 160;        // 鼠标影响半径

    function resize() {
      w = canvas.clientWidth;
      h = canvas.clientHeight;
      canvas.width  = Math.floor(w * dpr);
      canvas.height = Math.floor(h * dpr);
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function seed() {
      const count = window.innerWidth < 720 ? COUNT_MOBILE : COUNT_DESKTOP;
      particles = Array.from({ length: count }, () => ({
        x: Math.random() * w,
        y: Math.random() * h,
        vx: (Math.random() - 0.5) * 0.28,
        vy: (Math.random() - 0.5) * 0.28,
        r:  Math.random() * 1.8 + 0.6,
        c:  COLORS[(Math.random() * COLORS.length) | 0],
        a:  Math.random() * 0.55 + 0.25,
        pulse: Math.random() * Math.PI * 2, // 呼吸相位
      }));
    }

    function step() {
      // 半透明清屏 -> 形成柔和拖尾
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = 'rgba(248, 250, 255, 0.18)';
      ctx.fillRect(0, 0, w, h);

      // 1) 鼠标拖尾（每帧最多画 12 个点）
      if (mouse.active) {
        trail.push({ x: mouse.x, y: mouse.y, life: 1 });
        if (trail.length > 14) trail.shift();
      }
      for (let i = 0; i < trail.length; i++) {
        const t = trail[i];
        t.life *= 0.86;
        if (t.life < 0.04) continue;
        ctx.beginPath();
        ctx.fillStyle = `rgba(99,102,241,${t.life * 0.55})`;
        ctx.arc(t.x, t.y, 3 * t.life + 0.6, 0, Math.PI * 2);
        ctx.fill();
      }
      // 清理衰亡的拖尾
      if (trail.length && trail[0].life < 0.05) trail.shift();

      // 2) 粒子运动 + 鼠标交互
      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];
        // 鼠标排斥：距离 < MOUSE_R 则给一个反方向的力
        if (mouse.active) {
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < MOUSE_R * MOUSE_R && d2 > 0.5) {
            const d  = Math.sqrt(d2);
            const f  = (1 - d / MOUSE_R) * 0.08;
            p.vx += (dx / d) * f;
            p.vy += (dy / d) * f;
          }
        }
        // 速度阻尼（让交互后能自然回归）
        p.vx *= 0.985;
        p.vy *= 0.985;
        p.x += p.vx;
        p.y += p.vy;
        // 边界环绕
        if (p.x < -12) p.x = w + 12;
        else if (p.x > w + 12) p.x = -12;
        if (p.y < -12) p.y = h + 12;
        else if (p.y > h + 12) p.y = -12;

        // 呼吸闪烁
        p.pulse += 0.04;
        const a = p.a * (0.7 + 0.3 * Math.sin(p.pulse));

        // 光晕粒子
        ctx.beginPath();
        ctx.fillStyle = hexToRgba(p.c, a * 0.18);
        ctx.arc(p.x, p.y, p.r * 4, 0, Math.PI * 2);
        ctx.fill();
        // 实心点
        ctx.beginPath();
        ctx.fillStyle = hexToRgba(p.c, a);
        ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
        ctx.fill();

        // 邻近连线
        for (let j = i + 1; j < particles.length; j++) {
          const q = particles[j];
          const dx = p.x - q.x;
          const dy = p.y - q.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < LINK_DIST * LINK_DIST) {
            const alpha = (1 - Math.sqrt(d2) / LINK_DIST) * 0.22;
            ctx.strokeStyle = hexToRgba(p.c, alpha);
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(q.x, q.y);
            ctx.stroke();
          }
        }
      }

      // 3) 鼠标到粒子的细线（仅在 hover 半径内）
      if (mouse.active) {
        for (let i = 0; i < particles.length; i++) {
          const p = particles[i];
          const dx = p.x - mouse.x;
          const dy = p.y - mouse.y;
          const d2 = dx * dx + dy * dy;
          if (d2 < MOUSE_R * MOUSE_R) {
            const d = Math.sqrt(d2);
            const alpha = (1 - d / MOUSE_R) * 0.55;
            ctx.strokeStyle = `rgba(99,102,241,${alpha})`;
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(mouse.x, mouse.y);
            ctx.lineTo(p.x, p.y);
            ctx.stroke();
          }
        }
        // 鼠标点上的小光圈
        const grd = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, 26);
        grd.addColorStop(0, 'rgba(99,102,241,0.35)');
        grd.addColorStop(1, 'rgba(99,102,241,0)');
        ctx.fillStyle = grd;
        ctx.beginPath();
        ctx.arc(mouse.x, mouse.y, 26, 0, Math.PI * 2);
        ctx.fill();
      }

      // 4) 点击涟漪扩散
      for (let i = ripples.length - 1; i >= 0; i--) {
        const r = ripples[i];
        r.radius += 2.4;
        r.alpha  *= 0.965;
        if (r.alpha < 0.02) { ripples.splice(i, 1); continue; }
        ctx.strokeStyle = `rgba(99,102,241,${r.alpha})`;
        ctx.lineWidth = 1.4;
        ctx.beginPath();
        ctx.arc(r.x, r.y, r.radius, 0, Math.PI * 2);
        ctx.stroke();
        // 第二圈，更淡
        ctx.strokeStyle = `rgba(139,92,246,${r.alpha * 0.6})`;
        ctx.lineWidth = 0.8;
        ctx.beginPath();
        ctx.arc(r.x, r.y, r.radius * 0.7, 0, Math.PI * 2);
        ctx.stroke();
      }

      requestAnimationFrame(step);
    }

    function hexToRgba(hex, a) {
      const v = hex.replace('#', '');
      const r = parseInt(v.substring(0, 2), 16);
      const g = parseInt(v.substring(2, 4), 16);
      const b = parseInt(v.substring(4, 6), 16);
      return `rgba(${r},${g},${b},${a})`;
    }

    // 鼠标追踪
    canvas.style.pointerEvents = 'none'; // 不抢点击
    window.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = e.clientX - rect.left;
      mouse.y = e.clientY - rect.top;
      mouse.active = true;
    }, { passive: true });
    window.addEventListener('mouseleave', () => { mouse.active = false; });
    // 点击涟漪（绑在窗口上，避免被其它元素吃掉）
    window.addEventListener('click', (e) => {
      const rect = canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      // 一次生成 1~2 圈涟漪
      ripples.push({ x, y, radius: 4, alpha: 0.9 });
      if (Math.random() < 0.5) {
        setTimeout(() => ripples.push({ x, y, radius: 2, alpha: 0.6 }), 90);
      }
    });

    resize();
    seed();
    step();
    let rt;
    window.addEventListener('resize', () => {
      clearTimeout(rt);
      rt = setTimeout(() => { resize(); seed(); }, 200);
    });
  })();

  // ---- 滚动进度条 ----
  (function initScrollProgress() {
    const bar = $('#scrollProgress');
    const nav = $('.top-nav');
    if (!bar) return;
    let ticking = false;
    function update() {
      const doc = document.documentElement;
      const scrollTop = doc.scrollTop || document.body.scrollTop;
      const scrollHeight = (doc.scrollHeight || document.body.scrollHeight) - doc.clientHeight;
      const pct = scrollHeight > 0 ? (scrollTop / scrollHeight) * 100 : 0;
      bar.style.width = pct + '%';
      if (nav) nav.classList.toggle('scrolled', scrollTop > 12);
      ticking = false;
    }
    window.addEventListener('scroll', () => {
      if (!ticking) {
        requestAnimationFrame(update);
        ticking = true;
      }
    }, { passive: true });
    update();
  })();

  // ---- 自定义光标 ----
  (function initCursor() {
    const dot = $('#cursorDot');
    const ring = $('#cursorRing');
    if (!dot || !ring) return;
    // 触屏设备直接禁用
    if (matchMedia('(hover: none)').matches) {
      dot.style.display = 'none';
      ring.style.display = 'none';
      return;
    }
    let mx = window.innerWidth / 2;
    let my = window.innerHeight / 2;
    let rx = mx, ry = my;
    let active = false;

    document.addEventListener('mousemove', e => {
      mx = e.clientX; my = e.clientY;
      dot.style.transform = `translate3d(${mx}px, ${my}px, 0) translate(-50%, -50%)`;
      if (!active) { active = true; loop(); }
    });
    document.addEventListener('mouseleave', () => {
      dot.style.opacity = '0';
      ring.style.opacity = '0';
    });
    document.addEventListener('mouseenter', () => {
      dot.style.opacity = '1';
      ring.style.opacity = '0.8';
    });
    function loop() {
      rx += (mx - rx) * 0.18;
      ry += (my - ry) * 0.18;
      ring.style.transform = `translate3d(${rx}px, ${ry}px, 0) translate(-50%, -50%)`;
      requestAnimationFrame(loop);
    }

    // 悬停在可交互元素上时放大
    const hoverSel = 'a, button, .tilt-card, .feature-card, .showcase-tab, .faq-item summary, input, .btn';
    document.addEventListener('mouseover', e => {
      if (e.target.closest(hoverSel)) {
        dot.classList.add('hover');
        ring.classList.add('hover');
      }
    });
    document.addEventListener('mouseout', e => {
      if (e.target.closest(hoverSel)) {
        dot.classList.remove('hover');
        ring.classList.remove('hover');
      }
    });
  })();

  // ---- 静态 0/1 散点背景（canvas 实现，单图层，零 DOM 节点，平滑滚动） ----
  (function initBinaryBg() {
    const canvas = $('#bgBinary');
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext('2d');
    // 网格大小：64×56
    const cellW = 64;
    const cellH = 56;
    const FONT = '600 16px "SF Mono", Consolas, "Roboto Mono", monospace';
    const COLOR_DIM = 'rgba(67, 56, 202, 0.11)';   // 普通位
    const COLOR_HOT = 'rgba(67, 56, 202, 0.28)';   // 高亮位

    function render() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = window.innerWidth;
      const totalH = Math.max(
        document.documentElement.scrollHeight,
        document.body.scrollHeight,
        window.innerHeight
      );
      // 物理像素尺寸（高分屏下保持清晰）
      canvas.width  = Math.ceil(w * dpr);
      canvas.height = Math.ceil(totalH * dpr);
      canvas.style.width  = w + 'px';
      canvas.style.height = totalH + 'px';
      // 把绘制坐标系缩放到 CSS 像素
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.font = FONT;
      ctx.textBaseline = 'middle';
      ctx.textAlign = 'center';

      const cols = Math.ceil(w / cellW) + 1;
      // 多铺 2 行作为上飘余量
      const rows = Math.ceil(totalH / cellH) + 2;
      for (let r = 0; r < rows; r++) {
        for (let c = 0; c < cols; c++) {
          if (Math.random() > 0.45) continue;
          const ch = Math.random() < 0.5 ? '0' : '1';
          // 同行/列微抖
          const dx = (Math.random() - 0.5) * 14;
          const dy = (Math.random() - 0.5) * 10;
          const x = c * cellW + cellW / 2 + dx;
          const y = r * cellH + cellH / 2 + dy;
          // 8% 高亮位
          const isHot = Math.random() < 0.08;
          ctx.fillStyle = isHot ? COLOR_HOT : COLOR_DIM;
          ctx.fillText(ch, x, y);
        }
      }
    }

    render();
    let rt;
    window.addEventListener('resize', () => {
      clearTimeout(rt);
      rt = setTimeout(render, 250);
    });
    window.addEventListener('load', () => setTimeout(render, 300));
    // 注：上飘效果由 CSS keyframe 动画驱动（GPU 合成器线程），
    //     不再使用 JS rAF，避免抢占主线程导致滚动卡顿
  })();

  // ---- 实时数据流 (ticker) ----
  (function initTicker() {
    const el1 = $('#tickerContent');
    const el2 = $('#tickerContent2');
    if (!el1 || !el2) return;
    const items = [
      { t: '用户 @阿岛 完成 操作系统 章节训练', d: '+12%', up: true },
      { t: 'AI 讲题请求：今日已处理', d: '1,284 次', up: true },
      { t: '408 笔记库更新：里昂学长计网 v2.1', d: '+42 题', up: true },
      { t: '学习计划完成率：今日 78%', d: '+6%', up: true },
      { t: '用户 @Kong 生成冲刺 30 天计划', d: '进度 18%', up: false },
      { t: '用户 @沐辰 操作系统 模考', d: '93 分', up: true },
      { t: '知识图谱更新：进程同步 关联 12 节点', d: '已上线', up: true },
      { t: '用户 @Lemon 数据结构正确率', d: '82%', up: true },
    ];
    const html = items.map(it => `
      <span class="ticker-item">
        <strong>·</strong>${it.t}
        <span class="delta ${it.up ? 'up' : 'down'}">${it.d}</span>
      </span>
    `).join('');
    el1.innerHTML = html;
    el2.innerHTML = html;
  })();

  // ---- 考研倒计时（功能介绍页只显示剩余天数，不展示用户具体进度） ----
  (function initCountdown() {
    const daysEl = $('#cdDays');
    if (!daysEl) return;
    const examDate = new Date('2026-12-26T00:00:00+08:00');
    function update() {
      const days = Math.max(0, Math.ceil((examDate - new Date()) / 86400000));
      daysEl.textContent = days;
    }
    update();
    setInterval(update, 60 * 1000);
  })();

  // ---- Showcase 标签切换 ----
  (function initShowcase() {
    const tabs = $$('.showcase-tab');
    const panes = $$('.showcase-pane');
    if (!tabs.length) return;
    tabs.forEach(tab => {
      tab.addEventListener('click', () => {
        const key = tab.dataset.tab;
        tabs.forEach(t => t.classList.toggle('active', t === tab));
        panes.forEach(p => p.classList.toggle('active', p.dataset.pane === key));
      });
    });
  })();

  // ---- 3D 倾斜卡片 ----
  (function initTilt() {
    const cards = $$('.tilt-card');
    cards.forEach(card => {
      let rect = null;
      let rafId = null;
      let targetX = 0, targetY = 0;
      let curX = 0, curY = 0;

      function enter() {
        rect = card.getBoundingClientRect();
        card.style.transition = 'transform 0.2s ease, box-shadow 0.4s ease';
      }
      function move(e) {
        if (!rect) rect = card.getBoundingClientRect();
        const px = (e.clientX - rect.left) / rect.width;
        const py = (e.clientY - rect.top)  / rect.height;
        targetX = (py - 0.5) * -6;   // 俯仰
        targetY = (px - 0.5) *  6;   // 偏航
        if (!rafId) loop();
      }
      function loop() {
        curX += (targetX - curX) * 0.18;
        curY += (targetY - curY) * 0.18;
        card.style.transform = `perspective(900px) rotateX(${curX.toFixed(2)}deg) rotateY(${curY.toFixed(2)}deg) translateY(-2px)`;
        if (Math.abs(targetX - curX) > 0.05 || Math.abs(targetY - curY) > 0.05) {
          rafId = requestAnimationFrame(loop);
        } else {
          rafId = null;
        }
      }
      function leave() {
        targetX = 0; targetY = 0;
        if (!rafId) loop();
        rect = null;
      }
      card.addEventListener('mouseenter', enter);
      card.addEventListener('mousemove', move);
      card.addEventListener('mouseleave', leave);
    });
  })();

  // ---- 滚动入场 ----
  (function initReveal() {
    const items = $$('.section-head, .feature-card, .arch-step, .arch-panel, .stat-card, .road-step, .final-cta-inner, .hero-decor .decor-card, .hero-metrics .metric');
    items.forEach(el => el.classList.add('reveal'));
    if (!('IntersectionObserver' in window)) {
      items.forEach(el => el.classList.add('in'));
      return;
    }
    const io = new IntersectionObserver(entries => {
      entries.forEach((en, i) => {
        if (en.isIntersecting) {
          // 同批轻微错落
          setTimeout(() => en.target.classList.add('in'), Math.min(i * 60, 200));
          io.unobserve(en.target);
        }
      });
    }, { threshold: 0.12 });
    items.forEach(el => io.observe(el));
  })();

  // ---- 数字递增 ----
  (function initCounters() {
    function animateNum(el, target, duration = 1400) {
      const start = performance.now();
      const isInt = Number.isInteger(target);
      function tick(t) {
        const p = Math.min((t - start) / duration, 1);
        const eased = 1 - Math.pow(1 - p, 3);
        const v = target * eased;
        el.textContent = isInt ? Math.floor(v).toLocaleString() : v.toFixed(1);
        if (p < 1) requestAnimationFrame(tick);
        else el.textContent = isInt ? target.toLocaleString() : target.toFixed(1);
      }
      requestAnimationFrame(tick);
    }

    function run() {
      // hero-metrics 已在 HTML 中展示真实值，无需从 0 递增（避免首屏看到 0）
      $$('.stat-num[data-target]').forEach(el => {
        const target = parseFloat(el.dataset.target);
        const suffix = el.dataset.suffix || '';
        if (isNaN(target)) return;
        const start = performance.now();
        const duration = 1500;
        function tick(t) {
          const p = Math.min((t - start) / duration, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          const v = target * eased;
          const txt = Number.isInteger(target) ? Math.floor(v).toLocaleString() : v.toFixed(1);
          el.textContent = txt + suffix;
          if (p < 1) requestAnimationFrame(tick);
          else el.textContent = (Number.isInteger(target) ? target.toLocaleString() : target.toFixed(1)) + suffix;
        }
        requestAnimationFrame(tick);
      });
    }

    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(entries => {
        if (entries.some(e => e.isIntersecting)) {
          run();
          io.disconnect();
        }
      }, { threshold: 0.2 });
      const target = $('#statsGrid') || $('#heroMetrics');
      if (target) io.observe(target);
    } else {
      run();
    }
  })();

  // ---- 终端逐行输出 ----
  (function initTerminal() {
    const body = $('.terminal-body');
    if (!body) return;
    const lines = $$('.line', body);
    lines.forEach(l => l.style.opacity = '0');
    let i = 0;
    function next() {
      if (i >= lines.length) return;
      const line = lines[i++];
      line.style.transition = 'opacity 0.4s ease';
      line.style.opacity = '1';
      setTimeout(next, 520);
    }
    if ('IntersectionObserver' in window) {
      const io = new IntersectionObserver(entries => {
        if (entries[0].isIntersecting) {
          next();
          io.disconnect();
        }
      }, { threshold: 0.3 });
      io.observe(body);
    } else {
      lines.forEach(l => l.style.opacity = '1');
    }
  })();

  // ---- 跳转到 AI 对话舱 ----
  function goChat(event) {
    if (event) event.preventDefault();
    const token = getStoredToken();
    // 检查登录态
    if (token) {
      window.location.href = '/app';
    } else {
      // 未登录 → 打开登录弹窗，并提示
      openAuth('login', { intent: '登录后即可进入 AI 对话舱' });
    }
  }
  $$('#heroChatBtn, #finalChatBtn').forEach(btn => btn.addEventListener('click', goChat));

  // ---- 模态登录/注册 ----
  const modal       = $('#authModal');
  const modalClose  = $('#modalClose');
  const tabLogin    = $('.modal-tab[data-tab="login"]');
  const tabRegister = $('.modal-tab[data-tab="register"]');
  const formLogin   = $('#loginForm');
  const formReg     = $('#registerForm');
  const loginMsg    = $('#loginMsg');
  const regMsg      = $('#registerMsg');

  function openAuth(tab = 'login', opts = {}) {
    if (!modal) return;
    modal.classList.add('show');
    modal.setAttribute('aria-hidden', 'false');
    switchTab(tab);
    // 清空提示
    if (loginMsg) { loginMsg.textContent = ''; loginMsg.className = 'form-msg'; }
    if (regMsg)   { regMsg.textContent   = ''; regMsg.className   = 'form-msg'; }
    if (opts.intent) {
      if (loginMsg && tab === 'login') {
        loginMsg.textContent = opts.intent;
        loginMsg.className = 'form-msg success';
      }
    }
    // 聚焦首个输入
    setTimeout(() => {
      const first = modal.querySelector('.modal-form.active input');
      if (first) first.focus();
    }, 50);
  }
  function closeAuth() {
    if (!modal) return;
    modal.classList.remove('show');
    modal.setAttribute('aria-hidden', 'true');
    if (window.location.hash === '#authModal') {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }
  function switchTab(tab) {
    $$('.modal-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    $$('.modal-form').forEach(f => f.classList.toggle('active', f.dataset.form === tab));
  }

  // ---- 内测提示弹窗(注册入口用) ----
  function showClosedNotice() {
    let mask = document.getElementById('closedNoticeMask');
    if (!mask) {
      mask = document.createElement('div');
      mask.id = 'closedNoticeMask';
      mask.style.cssText = [
        'position:fixed', 'inset:0', 'z-index:9999',
        'background:rgba(8,12,28,0.78)', 'backdrop-filter:blur(8px)',
        'display:flex', 'align-items:center', 'justify-content:center',
        'animation:closedFadeIn .25s ease'
      ].join(';');
      mask.innerHTML = `
        <div style="position:relative;max-width:420px;width:calc(100% - 40px);background:linear-gradient(160deg,#0f1530 0%,#1a1f44 100%);border:1px solid rgba(120,140,255,0.35);border-radius:18px;padding:32px 28px 26px;box-shadow:0 20px 60px rgba(0,0,0,0.6),inset 0 1px 0 rgba(255,255,255,0.08);text-align:center;color:#e8ecff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;">
          <div style="width:64px;height:64px;margin:0 auto 18px;border-radius:50%;background:linear-gradient(135deg,#6366f1,#8b5cf6);display:flex;align-items:center;justify-content:center;box-shadow:0 8px 24px rgba(99,102,241,0.5);">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="#fff" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">
              <rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>
            </svg>
          </div>
          <h3 style="margin:0 0 10px;font-size:20px;font-weight:600;letter-spacing:0.5px;">注册功能暂未开放</h3>
          <p style="margin:0 0 6px;font-size:14px;line-height:1.7;color:#b8c0e8;">目前正处于内测阶段,暂不支持注册。</p>
          <p style="margin:0 0 18px;font-size:14px;line-height:1.7;color:#b8c0e8;">如想体验,请联系:</p>
          <a href="tel:17635575899" style="display:inline-block;font-size:22px;font-weight:700;color:#a5b4fc;letter-spacing:1.2px;text-decoration:none;padding:10px 24px;border:1.5px solid rgba(165,180,252,0.5);border-radius:999px;background:rgba(99,102,241,0.12);transition:all .2s;" onmouseover="this.style.background='rgba(99,102,241,0.28)';this.style.borderColor='rgba(165,180,252,0.9)'" onmouseout="this.style.background='rgba(99,102,241,0.12)';this.style.borderColor='rgba(165,180,252,0.5)'">176-3557-5899</a>
          <button id="closedNoticeClose" style="margin-top:22px;display:block;width:100%;padding:11px 0;border:none;border-radius:10px;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;font-size:14px;font-weight:500;cursor:pointer;letter-spacing:1px;box-shadow:0 4px 14px rgba(99,102,241,0.4);" onmouseover="this.style.opacity='0.9'" onmouseout="this.style.opacity='1'">我知道了</button>
        </div>
        <style>
          @keyframes closedFadeIn{from{opacity:0}to{opacity:1}}
        </style>
      `;
      document.body.appendChild(mask);
      mask.addEventListener('click', e => { if (e.target === mask) mask.remove(); });
      mask.querySelector('#closedNoticeClose').addEventListener('click', () => mask.remove());
      document.addEventListener('keydown', function esc(e) {
        if (e.key === 'Escape' && document.getElementById('closedNoticeMask')) {
          mask.remove();
          document.removeEventListener('keydown', esc);
        }
      });
    }
  }

  $$('#openLoginBtn, #footerLoginLink').forEach(b => b.addEventListener('click', e => { e.preventDefault(); openAuth('login'); }));
  // 内测阶段：所有“注册”入口改为内测提示
  $$('#openRegisterBtn, #footerRegisterLink, #finalRegisterBtn, #loginFootRegister').forEach(b => b.addEventListener('click', e => {
    e.preventDefault();
    showClosedNotice();
  }));
  // 注册 tab 切换 / 模态内"立即注册"链接也指向内测提示
  if (tabRegister) tabRegister.addEventListener('click', e => { e.preventDefault(); e.stopPropagation(); showClosedNotice(); });
  $$('[data-switch="register"]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); showClosedNotice(); }));
  // 注册表单即使显示也直接拦截提交
  if (formReg) formReg.addEventListener('submit', e => { e.preventDefault(); showClosedNotice(); });
  if (modalClose) modalClose.addEventListener('click', closeAuth);
  if (modal) modal.addEventListener('click', e => { if (e.target === modal) closeAuth(); });
  $$('.modal-tab').forEach(t => t.addEventListener('click', () => switchTab(t.dataset.tab)));
  $$('[data-switch]').forEach(a => a.addEventListener('click', e => { e.preventDefault(); switchTab(a.dataset.switch); }));
  document.addEventListener('keydown', e => { if (e.key === 'Escape') closeAuth(); });

  // /app 登录失效后会重定向到 ?login=required。直接展示登录框，
  // 避免用户到达首页后还需要再次点击，或误以为入口没有响应。
  const entryParams = new URLSearchParams(window.location.search);
  if (entryParams.get('login') === 'required' || window.location.hash === '#authModal') {
    openAuth('login', { intent: '登录后即可进入 AI 对话舱' });
  }

  // 登录提交
  if (formLogin) {
    formLogin.addEventListener('submit', async e => {
      e.preventDefault();
      const fd = new FormData(formLogin);
      const userId  = (fd.get('username') || '').toString().trim();
      const password = (fd.get('password') || '').toString().trim();
      if (!userId || !password) {
        loginMsg.textContent = '请填写用户名和密码';
        loginMsg.className = 'form-msg error';
        return;
      }
      loginMsg.textContent = '正在登录...';
      loginMsg.className = 'form-msg';
      try {
        const res = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ user_id: userId, password })
        });
        const data = await res.json().catch(() => ({}));
        if (data.success === false) {
          loginMsg.textContent = data.error || data.detail || data.message || '登录失败，请检查账号密码';
          loginMsg.className = 'form-msg error';
          return;
        }
        if (!res.ok) {
          loginMsg.textContent = data.detail || data.message || '登录失败，请检查账号密码';
          loginMsg.className = 'form-msg error';
          return;
        }
        // 登录凭证由服务器写入 HttpOnly Cookie，脚本无法读取，降低 XSS 风险。
        storeSessionToken(data.token || data.access_token || data.jwt || '');
        localStorage.setItem(STORAGE_USER, JSON.stringify(data.user || { user_id: userId }));
        loginMsg.textContent = '登录成功，即将进入学习舱...';
        loginMsg.className = 'form-msg success';
        toast('登录成功', 'success');
        setTimeout(() => { window.location.href = '/app'; }, 700);
      } catch (err) {
        console.error(err);
        loginMsg.textContent = '网络异常，请稍后再试';
        loginMsg.className = 'form-msg error';
      }
    });
  }

  // 注册提交
  if (formReg) {
    formReg.addEventListener('submit', async e => {
      e.preventDefault();
      const fd = new FormData(formReg);
      const userId      = (fd.get('username') || '').toString().trim();
      const password    = (fd.get('password') || '').toString();
      const nickname    = (fd.get('display_name') || '').toString().trim();

      if (!/^[A-Za-z0-9_.-]{2,32}$/.test(userId)) {
        regMsg.textContent = '用户名为 2-32 位字母/数字/下划线/点/中划线';
        regMsg.className = 'form-msg error';
        return;
      }
      if (password.length < 6) {
        regMsg.textContent = '密码至少 6 位';
        regMsg.className = 'form-msg error';
        return;
      }

      regMsg.textContent = '正在创建账号...';
      regMsg.className = 'form-msg';
      try {
        const res = await fetch('/api/auth/register', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            user_id: userId,
            password,
            nickname: nickname || undefined
          })
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok || data.success === false) {
          regMsg.textContent = data.detail || data.error || data.message || '注册失败，用户名可能已被占用';
          regMsg.className = 'form-msg error';
          return;
        }
        const token = data.token || data.access_token || data.jwt;
        if (token) {
          localStorage.setItem(STORAGE_TOKEN, token);
          localStorage.setItem(STORAGE_USER, JSON.stringify(data.user || { user_id: userId, nickname }));
        }
        regMsg.textContent = '注册成功，正在为你打开学习舱...';
        regMsg.className = 'form-msg success';
        toast('注册成功', 'success');
        setTimeout(() => { window.location.href = '/'; }, 800);
      } catch (err) {
        console.error(err);
        regMsg.textContent = '网络异常，请稍后再试';
        regMsg.className = 'form-msg error';
      }
    });
  }

  // ---- 已登录态：自动替换 CTA 行为 ----
  (function syncAuthState() {
    const token = getStoredToken();
    const headers = token ? { 'Authorization': 'Bearer ' + token } : {};
    // 静默校验 HttpOnly Cookie；旧版本 token 仅作为迁移兼容。
    fetch('/api/auth/verify', { headers, credentials: 'same-origin' })
      .then(r => r.json().catch(() => ({})))
      .then(data => {
        if (data && data.valid) {
          $$('#openLoginBtn').forEach(b => { b.textContent = '进入学习舱'; b.onclick = goChat; });
        }
      })
      .catch(() => {});
  })();

  // ---- 移动端菜单 ----
  const burger = $('#navBurger');
  const topNav = $('.top-nav');
  if (burger && topNav) {
    burger.addEventListener('click', () => {
      topNav.classList.toggle('nav-mobile-open');
    });
    $$('.nav-links a').forEach(a => a.addEventListener('click', () => topNav.classList.remove('nav-mobile-open')));
  }

  // ---- 笔记库链接：跳到应用页 + 打开 PDF 弹窗（若可用） ----
  const footerPdf = $('#footerPdfLink');
  if (footerPdf) {
    footerPdf.addEventListener('click', e => {
      e.preventDefault();
      const token = getStoredToken();
      window.location.href = token ? '/#pdf' : '/';
    });
  }

  // ---- 「了解功能矩阵」按钮 ----
  const heroFeatureBtn = $('#heroFeatureBtn');
  if (heroFeatureBtn) {
    heroFeatureBtn.addEventListener('click', () => {
      const target = $('#features');
      if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  }
})();

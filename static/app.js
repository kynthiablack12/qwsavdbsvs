const $ = (id) => document.getElementById(id);

let accounts = [];
let logPoller = null;
let activeLogsName = null;
const cards = new Map();

async function api(url, opts = {}) {
  const r = await fetch(url, opts);
  if (r.status === 401) {
    window.location.href = '/login';
    throw new Error('Требуется вход в админку');
  }
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('json') ? await r.json() : await r.text();
  if (!r.ok) throw new Error((data && data.error) || data || `HTTP ${r.status}`);
  return data;
}

async function loadAccounts() {
  try {
    accounts = await api('/api/accounts');
    renderAccounts();
    updateStats();
    accounts.forEach(a => {
      const card = cards.get(a.name);
      if (card) refreshStatus(a.name, card);
    });
  } catch (e) {
    console.error(e);
  }
}

function updateStats() {
  $('statTotal').textContent = accounts.length;
  $('statActive').textContent = accounts.filter(a => a.running).length;
  $('statPrizes').textContent = '…';
  $('empty').classList.toggle('hidden', accounts.length > 0);
  api('/api/prizes/stats').then(s => {
    $('statPrizes').textContent = s.count ?? '–';
  }).catch(() => { $('statPrizes').textContent = '–'; });
}

function renderAccounts() {
  const wrap = $('accounts');
  const seen = new Set();
  accounts.forEach(a => {
    seen.add(a.name);
    let card = cards.get(a.name);
    if (!card) {
      card = createAccountCard(a);
      cards.set(a.name, card);
      wrap.appendChild(card);
    } else {
      wrap.appendChild(card);
      card.classList.toggle('running', !!a.running);
    }
  });
  for (const [name, card] of [...cards]) {
    if (!seen.has(name)) {
      card.remove();
      cards.delete(name);
    }
  }
}

function createAccountCard(a) {
  const card = document.createElement('div');
  card.className = 'account' + (a.running ? ' running' : '');
  card.dataset.name = a.name;

  const initials = (a.name || '?').slice(0, 2).toUpperCase();
  const gameName = a.event_id === 'At99RuZXsCpnFRhpmEZCK' ? 'Монстро-планетяне' : 'Призолето';
  card.innerHTML = `
      <div class="account-head">
        <div class="avatar">${initials}</div>
        <div>
          <div class="account-name">${esc(a.name)}</div>
          <div class="account-device">${esc(gameName)} · ${esc(a.device_id || '')}</div>
        </div>
      </div>
      <div class="account-stats">
        <div class="mini-stat"><b>—</b><span>попыток</span></div>
        <div class="mini-stat"><b>—</b><span>уровень</span></div>
        <div class="mini-stat"><b>—</b><span>бонусов</span></div>
      </div>
      <div class="offers">
        <div class="offers-title">Персональные предложения</div>
        <div class="offers-list"></div>
      </div>
      <div class="account-actions">
        <button class="btn btn-primary" data-act="play">Играть</button>
        <button class="btn btn-ghost btn-sm" data-act="coupons">Купоны</button>
        <button class="btn btn-ghost btn-sm" data-act="prizes">Призы</button>
        <button class="btn btn-ghost btn-sm" data-act="logs">Логи</button>
        <button class="btn btn-danger btn-sm" data-act="del" title="Удалить">Удалить</button>
      </div>`;

  card.querySelector('[data-act="play"]').addEventListener('click', () => playAccount(a.name, card));
  card.querySelector('[data-act="coupons"]').addEventListener('click', () => syncCoupons(a.name, card));
  card.querySelector('[data-act="logs"]').addEventListener('click', () => openLogs(a.name));
  card.querySelector('[data-act="prizes"]').addEventListener('click', () => openPrizes(a.name));
  card.querySelector('[data-act="del"]').addEventListener('click', () => deleteAccount(a.name, card));
  return card;
}

async function refreshStatus(name, card) {
  try {
    const st = await api(`/api/accounts/${encodeURIComponent(name)}/status`);
    const m = card.querySelectorAll('.mini-stat b');
    m[0].textContent = st.attempts ?? '—';
    m[0].classList.toggle('good', (st.attempts ?? 0) > 0);
    m[0].classList.toggle('bad', (st.attempts ?? 0) === 0);
    m[1].textContent = st.last_level ?? '—';
    const row = card.querySelector('.account-stats');
    const old = row.querySelector('.daily-reward');
    if (old) old.remove();
    if (st.indicators && st.indicators.has_ready_daily_login_reward) {
      const el = document.createElement('div');
      el.className = 'daily-reward';
      el.textContent = '+ награда за вход готова';
      row.appendChild(el);
    }
  } catch (e) {
    // card stays with —
  }
  try {
    const ex = await api(`/api/accounts/${encodeURIComponent(name)}/extras`);
    const b = card.querySelectorAll('.mini-stat b')[2];
    const total = (ex.balance && ex.balance.total != null) ? ex.balance.total : null;
    b.textContent = total != null ? total : '—';
    b.classList.toggle('good', total > 0);
    renderOffers(ex.offers, card);
  } catch (e) {
    // offers stay empty
  }
}

function offerUnit(o) {
  const u = o.unit || {};
  if (u.type === 'POINTS') return `${u.value} бонусов`;
  if (u.type === 'PERCENT_DISCOUNT') return `−${u.value}%`;
  if (u.type === 'RUB_DISCOUNT') return `−${u.value} ₽`;
  if (u.value != null) return String(u.value);
  return (o.tag && o.tag.title) || '';
}

function renderOffers(offers, card) {
  const box = card.querySelector('.offers-list');
  const key = JSON.stringify((offers || []).map(o =>
    `${o.id}|${o.status}|${(o.unit || {}).value}|${(o.tag || {}).title}|${o.title}`));
  if (card._offersKey === key) return;
  card._offersKey = key;
  box.innerHTML = '';
  if (!offers || !offers.length) {
    box.innerHTML = '<div class="offer-empty">нет предложений</div>';
    return;
  }
  const maxShow = 3;
  offers.slice(0, maxShow).forEach(o => renderOffer(o, box));
  if (offers.length > maxShow) {
    const more = document.createElement('div');
    more.className = 'offer-more';
    more.textContent = `+ ещё ${offers.length - maxShow}`;
    box.appendChild(more);
  }
}

function renderOffer(o, box) {
  const tag = (o.tag && o.tag.title) || offerUnit(o);
  const active = o.status === 'ACTIVE';
  const el = document.createElement('div');
  el.className = 'offer';
  el.innerHTML = `
    <div class="offer-tag">${esc(tag)}</div>
    <div class="offer-body">
      <div class="offer-title">${esc(o.title || '')}</div>
      <div class="offer-meta"><span>${esc(offerUnit(o))}</span>${active ? '<span class="offer-active">активно</span>' : ''}</div>
    </div>`;
  box.appendChild(el);
}

async function playAccount(name, card) {
  const btn = card.querySelector('[data-act="play"]');
  btn.disabled = true;
  try {
    await api(`/api/accounts/${encodeURIComponent(name)}/play`, { method: 'POST' });
    openLogs(name);
    setTimeout(loadAccounts, 800);
  } catch (e) {
    alert(e.message);
    btn.disabled = false;
  }
}

async function syncCoupons(name, card) {
  const btn = card.querySelector('[data-act="coupons"]');
  btn.disabled = true;
  try {
    const r = await api(`/api/accounts/${encodeURIComponent(name)}/coupons/sync`, { method: 'POST' });
    openLogs(name);
    alert(`Купонов добавлено: ${r.added}`);
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
}

function openLogs(name) {
  activeLogsName = name;
  $('logsTitle').textContent = `Логи — ${name}`;
  $('logsBody').textContent = '';
  $('modalLogs').classList.remove('hidden');
  pollLogs(name);
}

function pollLogs(name) {
  clearInterval(logPoller);
  logPoller = setInterval(async () => {
    if (activeLogsName !== name) return;
    try {
      const r = await fetch(`/api/accounts/${encodeURIComponent(name)}/logs`);
      const text = await r.text();
      const box = $('logsBody');
      if (box.dataset.len !== String(text.length)) {
        box.textContent = text;
        box.dataset.len = String(text.length);
        box.scrollTop = box.scrollHeight;
      }
      const st = await api(`/api/accounts/${encodeURIComponent(name)}/status`).catch(() => null);
      const card = document.querySelector(`.account[data-name="${name}"]`);
      if (card) card.classList.toggle('running', !!(st && st.running));
      loadAccounts();
    } catch (e) { /* ignore */ }
  }, 1500);
}

async function deleteAccount(name, card) {
  if (!confirm(`Удалить аккаунт "${name}"?`)) return;
  try {
    await api(`/api/accounts/${encodeURIComponent(name)}`, { method: 'DELETE' });
    loadAccounts();
  } catch (e) { alert(e.message); }
}

async function renderPrizes(prizes, box) {
  box.innerHTML = '';
  if (!prizes.length) {
    box.innerHTML = '<p class="muted" style="text-align:center;padding:24px">Пока нет выигранных призов</p>';
    return;
  }
  prizes.forEach(p => {
    const items = (() => { try { return JSON.parse(p.items); } catch { return []; } })();
    const disc = items.map(i => `${i.discount_value}%`).join(', ');
    const card = document.createElement('div');
    card.className = 'prize' + (p.is_barcode ? ' barcode' : '');
    const img = p.icon_ref
      ? `<img src="${esc(p.icon_ref)}" alt="" onerror="this.style.display='none'">`
      : `<div class="prize-emoji">🎁</div>`;
    const barcode = p.barcode || '';
    card.innerHTML = `
      <div class="prize-icon">${img}</div>
      <div class="prize-body">
        <div class="prize-name">${esc(p.name || 'Без названия')}</div>
        <div class="prize-meta">
          <span>${p.is_barcode ? '🧾 купон' : '⚡ награда'}</span>
          ${disc ? `<span class="disc">скидка ${disc}</span>` : ''}
          ${p.expiration_date ? `<span>до ${esc(p.expiration_date)}</span>` : ''}
        </div>
        ${barcode ? `
        <div class="prize-barcode" title="${esc(barcode)}">
          <span class="barcode-glyph">▮▮▮▮▮▮</span>
          <span class="barcode-code">${esc(barcode)}</span>
          <button class="btn btn-ghost btn-copy" data-code="${esc(barcode)}">Копировать</button>
        </div>` : ''}
        <div class="prize-sub">уровень ${p.level} · ${esc(p.obtained_at || '')}</div>
      </div>`;
    box.appendChild(card);
    const copyBtn = card.querySelector('.btn-copy');
    if (copyBtn) copyBtn.addEventListener('click', () => copyText(copyBtn.dataset.code, copyBtn));
  });
}

function copyText(text, btn) {
  const done = () => {
    btn.textContent = '✓ Скопировано';
    setTimeout(() => { btn.textContent = 'Копировать'; }, 1500);
  };
  if (navigator.clipboard) {
    navigator.clipboard.writeText(text).then(done, done);
  } else {
    const ta = document.createElement('textarea');
    ta.value = text; document.body.appendChild(ta);
    ta.select(); document.execCommand('copy');
    document.body.removeChild(ta); done();
  }
}

// ---- all prizes button ----
let prizesScope = null;

async function openPrizes(name) {
  prizesScope = name;
  $('prizesSync').classList.remove('hidden');
  $('prizesTitle').textContent = `Призы — ${name}`;
  $('prizesStats').textContent = 'Загрузка…';
  $('prizesList').innerHTML = '';
  $('modalPrizes').classList.remove('hidden');
  try {
    const [prizes, stats] = await Promise.all([
      api(`/api/prizes?account=${encodeURIComponent(name)}`),
      api(`/api/prizes/stats?account=${encodeURIComponent(name)}`),
    ]);
    $('prizesStats').innerHTML = `<span class="pill">наград: <b>${stats.count}</b></span> <span class="pill">игр: <b>${stats.games}</b></span>`;
    renderPrizes(prizes, $('prizesList'));
  } catch (e) {
    $('prizesStats').textContent = e.message;
  }
}

$('prizesSync').addEventListener('click', async () => {
  if (!prizesScope) return;
  const btn = $('prizesSync');
  btn.disabled = true;
  btn.textContent = '↻ Синхронизация…';
  try {
    const r = await api(`/api/accounts/${encodeURIComponent(prizesScope)}/rewards/sync`, { method: 'POST' });
    await openPrizes(prizesScope);
    if (r.added) alert(`Добавлено выигрышей: ${r.added}`);
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = '↻ Синхронизировать';
  }
});

async function openAllPrizes() {
  prizesScope = null;
  $('prizesSync').classList.add('hidden');
  $('prizesTitle').textContent = 'Призы — все аккаунты';
  $('prizesStats').textContent = 'Загрузка…';
  $('prizesList').innerHTML = '';
  $('modalPrizes').classList.remove('hidden');
  try {
    const [prizes, stats] = await Promise.all([api('/api/prizes'), api('/api/prizes/stats')]);
    $('prizesStats').innerHTML = `<span class="pill">наград: <b>${stats.count}</b></span> <span class="pill">игр: <b>${stats.games}</b></span>`;
    renderPrizes(prizes, $('prizesList'));
  } catch (e) {
    $('prizesStats').textContent = e.message;
  }
}
$('prizesClose').addEventListener('click', () => $('modalPrizes').classList.add('hidden'));
$('btnPrizes').addEventListener('click', () => openAllPrizes());

// ---- add account modal ----
let addMode = 'register';

function setAddMode(mode) {
  addMode = mode;
  $('tabRegister').classList.toggle('active', mode === 'register');
  $('tabToken').classList.toggle('active', mode === 'token');
  $('tabLogin').classList.toggle('active', mode === 'login');
  $('formAdd').classList.toggle('hidden', mode === 'token');
  $('formToken').classList.toggle('hidden', mode !== 'token');
  $('fieldsRegister').classList.toggle('hidden', mode !== 'register');
  $('modalTitle').textContent =
    mode === 'login' ? 'Вход в аккаунт' : mode === 'token' ? 'Добавить по токену' : 'Добавить аккаунт';
  if (mode === 'register') $('addPhone').placeholder = '7 912 345-67-89';
}

$('tabRegister').addEventListener('click', () => setAddMode('register'));
$('tabToken').addEventListener('click', () => setAddMode('token'));
$('tabLogin').addEventListener('click', () => setAddMode('login'));

$('formToken').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('modalError').classList.add('hidden');
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>Проверка токена…';
  try {
    await api('/api/accounts/from-token', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: $('tokName').value, refresh_token: $('tokRefresh').value, event_id: $('tokEvent').value }),
    });
    $('modalAdd').classList.add('hidden');
    $('tokName').value = '';
    $('tokRefresh').value = '';
    loadAccounts();
  } catch (err) {
    showModalError(err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Добавить аккаунт';
  }
});

$('btnAdd').addEventListener('click', () => {
  $('modalAdd').classList.remove('hidden');
  $('stepConfirm').classList.add('hidden');
  $('formAdd').classList.remove('hidden');
  $('modalError').classList.add('hidden');
  setAddMode('register');
});
$('modalClose').addEventListener('click', () => $('modalAdd').classList.add('hidden'));
$('logsClose').addEventListener('click', () => {
  $('modalLogs').classList.add('hidden');
  clearInterval(logPoller);
  activeLogsName = null;
});

$('formAdd').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('modalError').classList.add('hidden');
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>Отправка…';
  try {
    const data = { phone: $('addPhone').value };
    if (addMode === 'register') {
      data.name = $('addName').value;
      data.first_name = $('addFirstName').value;
      data.birth_date = $('addBirth').value;
      data.event_id = $('addEvent').value;
    }
    await api('/api/register/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data),
    });
    $('formAdd').classList.add('hidden');
    $('stepConfirm').classList.remove('hidden');
  } catch (err) {
    showModalError(err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Отправить SMS';
  }
});

$('formConfirm').addEventListener('submit', async (e) => {
  e.preventDefault();
  $('modalError').classList.add('hidden');
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true; btn.innerHTML = '<span class="spinner"></span>Проверка…';
  try {
    const body = addMode === 'login'
      ? { phone: $('addPhone').value, code: $('confirmCode').value }
      : { name: $('addName').value, code: $('confirmCode').value };
    await api('/api/register/confirm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    $('modalAdd').classList.add('hidden');
    $('formAdd').classList.remove('hidden');
    $('stepConfirm').classList.add('hidden');
    $('confirmCode').value = '';
    loadAccounts();
  } catch (err) {
    showModalError(err.message);
  } finally {
    btn.disabled = false; btn.textContent = 'Подтвердить';
  }
});

function showModalError(msg) {
  const el = $('modalError');
  el.textContent = msg;
  el.classList.remove('hidden');
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ---- access sessions ----
$('btnAccess').addEventListener('click', () => {
  $('modalAccess').classList.remove('hidden');
  loadSessions();
  fillAccountsSelect();
});
$('accessClose').addEventListener('click', () => $('modalAccess').classList.add('hidden'));

function fillAccountsSelect() {
  const sel = $('accAccount');
  sel.innerHTML = '';
  accounts.forEach(a => {
    const o = document.createElement('option');
    o.value = a.name;
    o.textContent = a.name;
    sel.appendChild(o);
  });
}

async function loadSessions() {
  const box = $('sessionsList');
  try {
    const sess = await api('/api/sessions');
    const entries = Object.entries(sess).filter(([, v]) => v.active);
    if (!entries.length) {
      box.innerHTML = '<p class="muted" style="margin-top:16px">Активных сессий нет</p>';
      return;
    }
    box.innerHTML = entries.map(([token, s]) => `
      <div class="session-row">
        <div>
          <div class="session-name">${esc(s.name)} <span class="session-account">${esc(s.account)}</span></div>
          <div class="muted" style="font-size:11.5px;margin-top:3px">до ${esc(s.expires_at || '—')} · последний вход: ${esc(s.last_seen || 'никогда')}</div>
          <div class="session-link">${esc(location.origin + '/p/' + token)}</div>
        </div>
        <div class="session-actions">
          <button class="btn btn-ghost btn-sm" data-detail="${token}">Детали</button>
          <button class="btn btn-ghost btn-sm" data-copy="${esc(location.origin + '/p/' + token)}">Скопировать</button>
          <button class="btn btn-danger btn-sm" data-revoke="${token}">Отозвать</button>
        </div>
      </div>`).join('');
    box.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => copyText(b.dataset.copy, b)));
    box.querySelectorAll('[data-detail]').forEach(b => b.addEventListener('click', () => openSessionDetail(b.dataset.detail)));
    box.querySelectorAll('[data-revoke]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/sessions/${b.dataset.revoke}`, { method: 'DELETE' });
      loadSessions();
    }));
  } catch (e) {
    box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }
}

$('accCreate').addEventListener('click', async () => {
  const btn = $('accCreate');
  btn.disabled = true;
  try {
    const r = await api('/api/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('accName').value,
        account: $('accAccount').value,
        hours: parseInt($('accHours').value, 10) || 24,
      }),
    });
    $('accName').value = '';
    copyText(r.link, btn);
    loadSessions();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

// ---- coupon share links ----
$('btnCoupons').addEventListener('click', () => {
  $('modalCoupons').classList.remove('hidden');
  loadCouponShares();
  fillCouponAccounts();
  loadCouponList();
});
$('couponsClose').addEventListener('click', () => $('modalCoupons').classList.add('hidden'));
$('cpnAccount').addEventListener('change', loadCouponList);

function fillCouponAccounts() {
  const sel = $('cpnAccount');
  sel.innerHTML = '';
  accounts.forEach(a => {
    const o = document.createElement('option');
    o.value = a.name;
    o.textContent = a.name;
    sel.appendChild(o);
  });
}

async function loadCouponList() {
  const box = $('cpnCoupons');
  const name = $('cpnAccount').value;
  if (!name) { box.innerHTML = '<p class="muted">Выберите аккаунт…</p>'; return; }
  box.innerHTML = '<p class="muted">Загрузка купонов…</p>';
  try {
    const r = await api(`/api/accounts/${encodeURIComponent(name)}/coupons`);
    const cs = r.coupons || [];
    if (!cs.length) { box.innerHTML = '<p class="muted">У аккаунта нет купонов</p>'; return; }
    box.innerHTML = '<div class="cpn-grid">' + cs.map((c, i) => `
      <div class="cpn-card">
        ${c.image ? `<img class="cpn-img" src="${esc(c.image)}" alt="" onerror="this.style.display='none'">` : '<div class="cpn-img cpn-img-empty">🎟️</div>'}
        <div class="cpn-info">
          <div class="cpn-title">${esc(c.title || 'Купон')}</div>
          <div class="muted" style="font-size:11.5px;margin-top:2px">
            ${c.discount_value ? esc((c.discount_type === 'percentDiscount' ? '−' + c.discount_value + '%' : c.discount_value + ' ₽')) : ''}${c.code ? ' · ' + esc(c.code) : ''}
          </div>
          <div class="muted" style="font-size:11px;margin-top:1px">до ${esc(c.expiration_date || '—')}</div>
          <button class="btn btn-primary btn-sm cpn-create" data-id="${esc(c.id)}" data-title="${esc(c.title || '')}">Создать ссылку</button>
        </div>
      </div>`).join('') + '</div>';
    box.querySelectorAll('.cpn-create').forEach(b => b.addEventListener('click', () => createCouponShare(b.dataset.id, b.dataset.title, b)));
  } catch (e) {
    box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }
}

async function createCouponShare(couponId, title, btn) {
  btn.disabled = true;
  try {
    const r = await api('/api/coupons/shares', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        account: $('cpnAccount').value,
        coupon_id: couponId,
        hours: parseInt($('cpnHours').value, 10) || 24,
        name: title,
      }),
    });
    copyText(r.link, btn);
    btn.textContent = '✓ Ссылка создана';
    loadCouponShares();
  } catch (e) {
    alert(e.message);
  } finally {
    setTimeout(() => { if (btn) btn.disabled = false; }, 1500);
  }
}

async function loadCouponShares() {
  const box = $('cpnShares');
  try {
    const shares = await api('/api/coupons/shares');
    const active = shares.filter(s => s.active);
    if (!active.length) {
      box.innerHTML = '<p class="muted" style="margin-top:8px">Ссылок на купоны нет</p>';
      return;
    }
    box.innerHTML = active.map(s => `
      <div class="session-row">
        <div>
          <div class="session-name">${esc(s.title || s.coupon_id)} <span class="session-account">${esc(s.account)}</span></div>
          <div class="muted" style="font-size:11.5px;margin-top:3px">создано ${esc(s.created_at || '—')} · ссылка действует до ${esc(s.expires_at || '—')}</div>
          <div class="session-link">${esc(s.link)}</div>
        </div>
        <div class="session-actions">
          <button class="btn btn-ghost btn-sm" data-copy="${esc(s.link)}">Скопировать</button>
          <button class="btn btn-danger btn-sm" data-revoke="${s.token}">Отозвать</button>
        </div>
      </div>`).join('');
    box.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => copyText(b.dataset.copy, b)));
    box.querySelectorAll('[data-revoke]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/coupons/shares/${b.dataset.revoke}`, { method: 'DELETE' });
      loadCouponShares();
    }));
  } catch (e) {
    box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }
}

// ---- session details ----
$('sessClose').addEventListener('click', () => $('modalSess').classList.add('hidden'));
$('modalSess').addEventListener('click', (e) => { if (e.target === $('modalSess')) $('modalSess').classList.add('hidden'); });

function statusBadge(code) {
  const map = {
    'NEW': 'ok', 'ASSEMBLING': 'ok', 'ON_ASSEMBLE': 'ok', 'READY': 'ok', 'WAITING': 'ok',
    'DELIVERED': 'ok', 'PICKED_UP': 'ok', 'DONE': 'ok',
    'CANCELED': 'bad', 'CANCELED_NO_PAY': 'bad', 'CANCELED_BY_USER': 'bad', 'FAILED': 'bad',
  };
  const cls = map[code] || 'warn';
  return `<span class="sd-badge ${cls}">${esc(code)}</span>`;
}

function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d)) return esc(s);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

async function openSessionDetail(token) {
  $('modalSess').classList.remove('hidden');
  $('sessBody').innerHTML = '<div class="muted">Загрузка данных…</div>';
  try {
    const all = await api('/api/sessions/detailed');
    const s = all.find(x => x.token === token);
    if (!s) { $('sessBody').innerHTML = '<div class="sd-err">Сессия не найдена</div>'; return; }
    renderSessionDetail(s);
  } catch (e) {
    $('sessBody').innerHTML = `<div class="sd-err">${esc(e.message)}</div>`;
  }
}

function renderSessionDetail(s) {
  const bal = s.balance || {};
  const balTile = bal.ok && bal.data && !bal.data.code
    ? `<div class="sd-tile"><div class="t">Бонусы</div><div class="v ok">${esc((bal.data.balance ?? bal.data.availableBalance ?? '—') + ' ₽')}</div></div>`
    : `<div class="sd-tile"><div class="t">Бонусы</div><div class="v danger">заблокирован</div></div>`;
  const alertHtml = bal.ok && bal.data && bal.data.code
    ? `<div class="sd-alert">${esc(bal.data.title || bal.data.message || 'Аккаунт заблокирован')}</div>` : '';

  const activeOrders = s.orders_active
    ? (s.orders_active.length
      ? `<div class="table-wrap"><table class="sd-table">
          <tr><th>Заказ</th><th>Статус</th><th>Сумма</th><th>Товаров</th><th>Создан</th></tr>
          ${s.orders_active.map(o => `<tr>
            <td class="num">${esc(o.order_id)}</td>
            <td>${statusBadge(o.status_code)} ${esc(o.status_name)}</td>
            <td>${esc(o.total)}</td>
            <td>${esc(o.items_count)}</td>
            <td>${fmtDate(o.created_at)}</td>
          </tr>`).join('')}
        </table></div>`
      : '<div class="muted">Активных заказов нет</div>')
    : `<div class="sd-err">${esc(s.orders_active_err || 'не удалось загрузить')}</div>`;

  const history = s.orders_history
    ? (s.orders_history.length
      ? `<div class="table-wrap"><table class="sd-table">
          <tr><th>Заказ</th><th>Статус</th><th>Сумма</th><th>Товаров</th><th>Создан</th></tr>
          ${s.orders_history.slice(0, 15).map(o => `<tr>
            <td class="num">${esc(o.order_id)}</td>
            <td>${statusBadge(o.status_code)} ${esc(o.status_name)}</td>
            <td>${esc(o.total)}</td>
            <td>${esc(o.items_count)}</td>
            <td>${fmtDate(o.created_at)}</td>
          </tr>`).join('')}
        </table></div>`
      : '<div class="muted">Истории заказов нет</div>')
    : `<div class="sd-err">${esc(s.orders_history_err || 'не удалось загрузить')}</div>`;

  const promos = s.promos
    ? (s.promos.length
      ? `<div class="table-wrap"><table class="sd-table">
          <tr><th>Код</th><th>Условие</th><th>Период</th><th>Скидка</th></tr>
          ${s.promos.map(p => `<tr>
            <td class="num">${esc(p.value || '—')}</td>
            <td>${esc((p.rules || []).map(r => r.title).filter(Boolean).join('; ') || p.condition || '—')}</td>
            <td>${esc(p.period || '—')}</td>
            <td>${esc((p.badges || []).join('; '))}</td>
          </tr>`).join('')}
        </table></div>`
      : '<div class="muted">Промокодов нет</div>')
    : `<div class="sd-err">${esc(s.promos_err || 'не удалось загрузить')}</div>`;

  const coupons = s.coupons
    ? (s.coupons.length
      ? s.coupons.slice(0, 10).map(c => `<div class="sd-coupon"><b>${esc(c.title || 'Купон')}</b><div class="m">${esc(c.description || '')}</div><div class="m">${esc(c.endDate ? 'до ' + fmtDate(c.endDate) : '')}</div></div>`).join('')
      : '<div class="muted">Купонов нет</div>')
    : `<div class="sd-err">${esc(s.coupons_err || 'не удалось загрузить')}</div>`;

  $('sessBody').innerHTML = `
    <h2>${esc(s.name)} <span class="session-account">${esc(s.account)}</span></h2>
    <div class="muted" style="margin-top:4px">Сессия до ${esc(s.expires_at || '—')} · последний вход ${esc(s.last_seen || 'никогда')}</div>
    <div class="session-link" style="margin-top:6px">${esc(s.link)}</div>
    ${alertHtml}

    <div class="sd-section"><h3>Пользователь</h3>
      <div class="sd-tiles">
        <div class="sd-tile"><div class="t">Активных заказов</div><div class="v">${esc(s.orders_active ? s.orders_active.length : '—')}</div></div>
        <div class="sd-tile"><div class="t">Всего заказов</div><div class="v">${esc(s.orders_history ? s.orders_history.length : '—')}</div></div>
        <div class="sd-tile"><div class="t">Промокодов</div><div class="v">${esc(s.promos ? s.promos.length : '—')}</div></div>
        <div class="sd-tile"><div class="t">Купонов</div><div class="v">${esc(s.coupons ? s.coupons.length : '—')}</div></div>
        ${balTile}
      </div>
    </div>

    <div class="sd-section"><h3>Активные заказы</h3>${activeOrders}</div>
    <div class="sd-section"><h3>История заказов</h3>${history}</div>
    <div class="sd-section"><h3>Промокоды</h3>${promos}</div>
    <div class="sd-section"><h3>Купоны</h3>${coupons}</div>
  `;
}

// ---- Яндекс Еда: аккаунты и сессии ----
$('btnEda').addEventListener('click', () => {
  $('modalEda').classList.remove('hidden');
  loadEdaAccounts();
  loadEdaSessions();
  fillEdaAccountSelect();
});
$('edaClose').addEventListener('click', () => $('modalEda').classList.add('hidden'));

$('edaTabAccs').addEventListener('click', () => {
  $('edaTabAccs').classList.add('active');
  $('edaTabSess').classList.remove('active');
  $('edaPaneAccs').classList.remove('hidden');
  $('edaPaneSess').classList.add('hidden');
});
$('edaTabSess').addEventListener('click', () => {
  $('edaTabSess').classList.add('active');
  $('edaTabAccs').classList.remove('active');
  $('edaPaneSess').classList.remove('hidden');
  $('edaPaneAccs').classList.add('hidden');
});

let edaAccounts = [];

async function loadEdaAccounts() {
  const box = $('edaAccounts');
  try {
    edaAccounts = await api('/api/eda/accounts');
    if (!edaAccounts.length) {
      box.innerHTML = '<p class="muted" style="margin-top:16px">Аккаунтов Я.Еды нет. Добавьте первый выше.</p>';
      return;
    }
    box.innerHTML = edaAccounts.map(a => `
      <div class="session-row">
        <div>
          <div class="session-name">${esc(a.name)} <span class="session-account">${a.has_token ? 'токен ✓' : 'без токена'}</span></div>
          <div class="muted" style="font-size:11.5px;margin-top:3px">добавлен ${esc(a.added || '—')}${a.uid ? ' · uid ' + esc(a.uid) : ''}</div>
        </div>
        <div class="session-actions">
          <button class="btn btn-danger btn-sm" data-del="${esc(a.name)}">Удалить</button>
        </div>
      </div>`).join('');
    box.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/eda/accounts/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE' });
      loadEdaAccounts();
      fillEdaAccountSelect();
    }));
  } catch (e) {
    box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }
}

function fillEdaAccountSelect() {
  const sel = $('edaSessAccount');
  sel.innerHTML = '';
  edaAccounts.forEach(a => {
    const o = document.createElement('option');
    o.value = a.name;
    o.textContent = a.name;
    sel.appendChild(o);
  });
}

$('edaAccAdd').addEventListener('click', async () => {
  const btn = $('edaAccAdd');
  btn.disabled = true;
  try {
    await api('/api/eda/accounts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('edaName').value.trim(),
        token: $('edaToken').value.trim(),
        yandexuid: $('edaUid').value.trim(),
      }),
    });
    $('edaName').value = '';
    $('edaToken').value = '';
    $('edaUid').value = '';
    loadEdaAccounts();
    fillEdaAccountSelect();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

async function loadEdaSessions() {
  const box = $('edaSessions');
  try {
    const sess = await api('/api/eda/sessions');
    const entries = Object.entries(sess).filter(([, v]) => v.active);
    if (!entries.length) {
      box.innerHTML = '<p class="muted" style="margin-top:16px">Активных сессий нет</p>';
      return;
    }
    box.innerHTML = entries.map(([token, s]) => `
      <div class="session-row">
        <div>
          <div class="session-name">${esc(s.name)} <span class="session-account">${esc(s.account)}</span></div>
          <div class="muted" style="font-size:11.5px;margin-top:3px">до ${esc(s.expires_at || '—')} · последний вход: ${esc(s.last_seen || 'никогда')}</div>
          <div class="session-link">${esc(location.origin + '/d/' + token)}</div>
        </div>
        <div class="session-actions">
          <button class="btn btn-ghost btn-sm" data-copy="${esc(location.origin + '/d/' + token)}">Скопировать</button>
          <button class="btn btn-danger btn-sm" data-revoke="${token}">Отозвать</button>
        </div>
      </div>`).join('');
    box.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => copyText(b.dataset.copy, b)));
    box.querySelectorAll('[data-revoke]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/eda/sessions/${b.dataset.revoke}`, { method: 'DELETE' });
      loadEdaSessions();
    }));
  } catch (e) {
    box.innerHTML = `<p class="muted">${esc(e.message)}</p>`;
  }
}

$('edaSessCreate').addEventListener('click', async () => {
  const btn = $('edaSessCreate');
  btn.disabled = true;
  try {
    const r = await api('/api/eda/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('edaSessName').value.trim(),
        account: $('edaSessAccount').value,
        hours: parseInt($('edaSessHours').value, 10) || 24,
      }),
    });
    $('edaSessName').value = '';
    copyText(location.origin + r.url, btn);
    loadEdaSessions();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

loadAccounts();
setInterval(loadAccounts, 6000);

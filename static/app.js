const $ = (id) => document.getElementById(id);

let accounts = [];
let logPoller = null;
let activeLogsName = null;

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

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s == null ? '' : String(s);
  return d.innerHTML;
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

function fmtDate(s) {
  if (!s) return '—';
  const d = new Date(s);
  if (isNaN(d)) return esc(s);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function fmtDateDb(s) {
  if (!s) return '—';
  let d = new Date(s);
  if (isNaN(d)) d = new Date(String(s).replace(' ', 'T'));
  if (isNaN(d)) return esc(s);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit' });
}

function prizeCat(displayType) {
  const map = { promocode: 'КУПОН', coupon: 'КУПОН', barcode: 'КУПОН', postcard: 'ОТКРЫТКА', booster: 'БУСТЕР', bonus: 'БОНУС', text: 'ТЕКСТ' };
  return map[(displayType || '').toLowerCase()] || 'ПРОЧЕЕ';
}

function downloadCSV(filename, rows) {
  const csv = rows.map(r => r.map(c => '"' + String(c == null ? '' : c).replace(/"/g, '""') + '"').join(';')).join('\r\n');
  const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8;' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

// ================= tabs =================
function switchTab(name) {
  document.querySelectorAll('.db-tabs:not(.sub) .db-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  document.querySelectorAll('.container.wide > .db-pane').forEach(p => {
    const on = p.id === 'pane-' + name;
    p.classList.toggle('active', on);
  });
}
document.querySelectorAll('#dbTabs .db-tab').forEach(b => b.addEventListener('click', () => {
  switchTab(b.dataset.tab);
  const loaders = { accounts: loadAdminAccounts, purchases: loadPurchases, coupons: loadCoupons,
    prizes: loadPrizes, sessions: loadSessions, card: loadCardAdmin, eda: loadEda, auto: loadAuto, samokat: loadSamokat, market: initMarketWow };
  if (loaders[b.dataset.tab]) loaders[b.dataset.tab]();
}));

$('btnRefresh').addEventListener('click', () => {
  const active = document.querySelector('#dbTabs .db-tab.active');
  const loaders = { accounts: loadAdminAccounts, purchases: loadPurchases, coupons: loadCoupons,
    prizes: loadPrizes, sessions: loadSessions, card: loadCardAdmin, eda: loadEda, auto: loadAuto, samokat: loadSamokat, market: initMarketWow };
  loadOverview();
  if (active && loaders[active.dataset.tab]) loaders[active.dataset.tab]();
});

// ================= overview =================
async function loadOverview() {
  try {
    const o = await api('/api/admin/overview');
    $('statTotal').textContent = o.accounts ?? '–';
    $('statActive').textContent = o.running ?? '–';
    $('statPrizes').textContent = o.prizes ?? '–';
    $('statOrders').textContent = o.orders ?? '–';
  } catch (e) { /* ignore */ }
}

// ================= accounts =================
let adminAccounts = [];

async function loadAdminAccounts() {
  try {
    adminAccounts = await api('/api/admin/accounts');
    renderAdminAccounts();
  } catch (e) {
    $('accTable').querySelector('tbody').innerHTML = `<tr><td colspan="8" class="db-empty">${esc(e.message)}</td></tr>`;
  }
}

function renderAdminAccounts() {
  const q = ($('accSearch').value || '').toLowerCase().trim();
  const gf = $('accGameFilter').value;
  let rows = adminAccounts.filter(a => {
    if (gf && a.event_id !== gf) return false;
    if (!q) return true;
    return (a.name || '').toLowerCase().includes(q) || (a.device_id || '').toLowerCase().includes(q);
  });
  $('accCount').textContent = `показано ${rows.length} из ${adminAccounts.length}`;
  const tb = $('accTable').querySelector('tbody');
  tb.innerHTML = rows.map(a => {
    const games = a.games || {};
    const pz = games['pBvsPKf7hGXlGBg5zBnsn'] || {};
    const mn = games['At99RuZXsCpnFRhpmEZCK'] || {};
    const activeGame = a.event_id === 'At99RuZXsCpnFRhpmEZCK' ? mn : pz;
    const attempts = typeof activeGame.attempts === 'number' ? activeGame.attempts : '—';
    const attemptsCls = typeof activeGame.attempts === 'number' ? (activeGame.attempts > 0 ? 'ok' : 'bad') : '';
    const level = activeGame.last_level != null ? activeGame.last_level : '—';
    const bal = typeof a.balance === 'number' ? a.balance : '—';
    const err = a.error ? `<div class="db-err">${esc(a.error)}</div>` : '';
    const status = a.running
      ? '<span class="sd-badge ok">● играет</span>'
      : (a.error ? '<span class="sd-badge bad">ошибка</span>' : '<span class="sd-badge">стоит</span>');
    const attemptsCell = `${attempts} <span class="db-mut">(М:${pz.attempts ?? '?'} Мон:${mn.attempts ?? '?'})</span>`;
    return `<tr>
      <td><div class="acc-cell"><b>${esc(a.name)}</b><div class="db-mut mono">${esc(a.device_id || '')}</div>${err}</div></td>
      <td><select class="game-select db-game" data-name="${esc(a.name)}" data-cur="${esc(a.event_id)}">
        <option value="pBvsPKf7hGXlGBg5zBnsn"${a.event_id !== 'At99RuZXsCpnFRhpmEZCK' ? ' selected' : ''}>М.косметик</option>
        <option value="At99RuZXsCpnFRhpmEZCK"${a.event_id === 'At99RuZXsCpnFRhpmEZCK' ? ' selected' : ''}>Монстро</option>
      </select></td>
      <td><span class="num ${attemptsCls}">${attempts}</span> <span class="db-mut">${attemptsCell}</span></td>
      <td class="num">${level}</td>
      <td class="num">${bal}</td>
      <td class="num">${a.prizes ?? 0}</td>
      <td>${status}</td>
      <td class="col-actions">
        <div class="row-actions">
          <button class="btn btn-primary btn-sm" data-act="play" data-name="${esc(a.name)}">Играть</button>
          <button class="btn btn-ghost btn-sm" data-act="claim" data-name="${esc(a.name)}">Бонус</button>
          <button class="btn btn-ghost btn-sm" data-act="prizes" data-name="${esc(a.name)}">Призы</button>
          <button class="btn btn-ghost btn-sm" data-act="logs" data-name="${esc(a.name)}">Логи</button>
          <button class="btn btn-danger btn-sm" data-act="del" data-name="${esc(a.name)}">✕</button>
        </div>
      </td>
    </tr>`;
  }).join('') || `<tr><td colspan="8" class="db-empty">Аккаунтов нет — нажмите «+ Добавить аккаунт»</td></tr>`;

  tb.querySelectorAll('[data-act="play"]').forEach(b => b.addEventListener('click', () => playAccount(b.dataset.name, b)));
  tb.querySelectorAll('[data-act="claim"]').forEach(b => b.addEventListener('click', () => claimDaily(b.dataset.name, b)));
  tb.querySelectorAll('[data-act="prizes"]').forEach(b => b.addEventListener('click', () => openPrizes(b.dataset.name)));
  tb.querySelectorAll('[data-act="logs"]').forEach(b => b.addEventListener('click', () => openLogs(b.dataset.name)));
  tb.querySelectorAll('[data-act="del"]').forEach(b => b.addEventListener('click', () => deleteAccount(b.dataset.name, b)));
  tb.querySelectorAll('.db-game').forEach(sel => sel.addEventListener('change', async () => {
    const name = sel.dataset.name;
    try {
      await api(`/api/accounts/${encodeURIComponent(name)}/game`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event_id: sel.value }),
      });
      loadAdminAccounts();
    } catch (err) {
      alert(err.message);
      sel.value = sel.dataset.cur;
    }
  }));
}

$('accSearch').addEventListener('input', renderAdminAccounts);
$('accGameFilter').addEventListener('change', renderAdminAccounts);
$('accCsv').addEventListener('click', () => {
  downloadCSV('accounts.csv', adminAccounts.map(a => [a.name, a.event_id === 'At99RuZXsCpnFRhpmEZCK' ? 'Монстро' : 'М.косметик', a.device_id, a.error || '', a.balance ?? '', a.prizes ?? 0]));
});

$('accPlayAll').addEventListener('click', async () => {
  const btn = $('accPlayAll');
  btn.disabled = true;
  const prev = btn.textContent;
  btn.textContent = '▶ Запуск…';
  try {
    const r = await api('/api/accounts/play-all', { method: 'POST' });
    const started = r.results.filter(x => x.status === 'started').length;
    const already = r.results.filter(x => x.status === 'already_running').length;
    alert(`Запущено: ${started}\nУже играли: ${already}`);
    const first = r.results.find(x => x.status === 'started');
    if (first) openLogs(first.name);
    setTimeout(() => { loadAdminAccounts(); loadOverview(); }, 1500);
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
    btn.textContent = prev;
  }
});

async function playAccount(name, btn) {
  btn.disabled = true;
  try {
    await api(`/api/accounts/${encodeURIComponent(name)}/play`, { method: 'POST' });
    openLogs(name);
    setTimeout(() => { loadAdminAccounts(); loadOverview(); }, 1500);
  } catch (e) {
    alert(e.message);
    btn.disabled = false;
  }
}

async function claimDaily(name, btn) {
  btn.disabled = true;
  try {
    const r = await api(`/api/accounts/${encodeURIComponent(name)}/rewards/claim`, { method: 'POST' });
    loadAdminAccounts();
    alert((r.log || []).join('\n') || 'Бонусов нет');
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
}

async function deleteAccount(name, btn) {
  if (!confirm(`Удалить аккаунт "${name}"?`)) return;
  try {
    await api(`/api/accounts/${encodeURIComponent(name)}`, { method: 'DELETE' });
    loadAdminAccounts();
    loadOverview();
  } catch (e) { alert(e.message); }
}

// ================= purchases =================
let purchases = [];

async function loadPurchases() {
  try {
    purchases = await api('/api/admin/purchases');
    renderPurchases();
  } catch (e) {
    $('purTable').querySelector('tbody').innerHTML = `<tr><td colspan="7" class="db-empty">${esc(e.message)}</td></tr>`;
  }
}

function renderPurchases() {
  $('purCount').textContent = `всего ${purchases.length}`;
  const tb = $('purTable').querySelector('tbody');
  tb.innerHTML = purchases.map(it => {
    if (it.kind === 'order') {
      const badge = it.status_code ? (['CANCELED', 'CANCELED_NO_PAY', 'CANCELED_BY_USER', 'FAILED'].includes(it.status_code) ? 'bad' : 'ok') : '';
      return `<tr>
        <td class="num">${fmtDate(it.created_at)}</td>
        <td><b>${esc(it.account)}</b></td>
        <td><span class="sd-badge">заказ</span></td>
        <td><div>№ ${esc(it.order_id || '')}${it.address ? `<div class="db-mut">${esc(it.address)}</div>` : ''}</div></td>
        <td>${it.status_code ? `<span class="sd-badge ${badge}">${esc(it.status_name || it.status_code)}</span>` : (it.error ? `<span class="sd-badge bad">${esc(it.error)}</span>` : '—')}</td>
        <td class="num">${esc(it.total || '—')}${it.items_count ? `<div class="db-mut">${it.items_count} тов.</div>` : ''}</td>
        <td class="col-actions"></td>
      </tr>`;
    }
    const code = it.barcode || it.coupon_id || '';
    return `<tr>
      <td class="num">${fmtDateDb(it.obtained_at)}</td>
      <td><b>${esc(it.account)}</b></td>
      <td><span class="sd-badge">приз</span></td>
      <td><b>${esc(it.name || 'Без названия')}</b></td>
      <td><span class="sd-badge ${it.display_type === 'postcard' ? '' : 'ok'}">${prizeCat(it.display_type)}</span></td>
      <td class="num">${code ? `<span class="mono">${esc(code)}</span>` : '—'}</td>
      <td class="col-actions">${code ? `<button class="btn btn-ghost btn-sm btn-copy" data-code="${esc(code)}">Копировать</button>` : ''}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="db-empty">Пока нет ни заказов, ни призов</td></tr>';
  tb.querySelectorAll('.btn-copy').forEach(b => b.addEventListener('click', () => copyText(b.dataset.code, b)));
}

$('purCsv').addEventListener('click', () => {
  downloadCSV('purchases.csv', purchases.map(it => it.kind === 'order'
    ? ['заказ', it.account, it.order_id, it.status_name || it.status_code, it.total, it.created_at]
    : ['приз', it.account, it.name, prizeCat(it.display_type), it.barcode || it.coupon_id || '', it.obtained_at]));
});

// ================= coupons =================
let allCoupons = [];

async function loadCoupons() {
  try {
    allCoupons = await api('/api/admin/coupons');
    renderCoupons();
  } catch (e) {
    $('cpnTable').querySelector('tbody').innerHTML = `<tr><td colspan="6" class="db-empty">${esc(e.message)}</td></tr>`;
  }
  loadCouponShares();
}

function renderCoupons() {
  $('cpnCount').textContent = `всего ${allCoupons.length}`;
  const tb = $('cpnTable').querySelector('tbody');
  tb.innerHTML = allCoupons.map(c => {
    const disc = c.discount_value
      ? (c.discount_type === 'percentDiscount' ? `−${c.discount_value}%` : `${c.discount_value} ₽`)
      : '—';
    return `<tr>
      <td><b>${esc(c.account)}</b></td>
      <td>${c.image ? `<img class="cpn-thumb" src="${esc(c.image)}" alt="">` : ''}<b>${esc(c.title || 'Купон')}</b>${c.subtitle ? `<div class="db-mut">${esc(c.subtitle)}</div>` : ''}</td>
      <td class="num">${c.code ? `<span class="mono">${esc(c.code)}</span>` : '—'}</td>
      <td>${disc}</td>
      <td class="num">${esc(c.expiration_date || '—')}</td>
      <td class="col-actions">
        <div class="row-actions">
          <button class="btn btn-ghost btn-sm" data-copy="${esc(c.code || '')}">Копировать</button>
          <button class="btn btn-primary btn-sm" data-link="${esc(c.account)}" data-id="${esc(c.id || '')}">Создать ссылку</button>
        </div>
      </td>
    </tr>`;
  }).join('') || '<tr><td colspan="6" class="db-empty">Купонов нет</td></tr>';
  tb.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => copyText(b.dataset.copy, b)));
  tb.querySelectorAll('[data-link]').forEach(b => b.addEventListener('click', () => createCouponShare(b.dataset.link, b.dataset.id, b)));
}

$('cpnCsv').addEventListener('click', () => {
  downloadCSV('coupons.csv', allCoupons.map(c => [c.account, c.title, c.code, c.discount_value, c.expiration_date]));
});

async function createCouponShare(account, couponId, btn) {
  if (!couponId) { alert('Купон без favoriteId'); return; }
  btn.disabled = true;
  try {
    const r = await api('/api/coupons/shares', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account, coupon_id: couponId, hours: parseInt($('cpnHours').value, 10) || 24 }),
    });
    copyText(r.link, btn);
    loadCouponShares();
  } catch (e) {
    alert(e.message);
  } finally {
    setTimeout(() => { btn.disabled = false; }, 1500);
  }
}

async function loadCouponShares() {
  const box = $('cpnShares');
  try {
    const shares = (await api('/api/coupons/shares')).filter(s => s.active);
    if (!shares.length) {
      box.innerHTML = '<p class="muted" style="margin-top:8px">Ссылок на купоны нет</p>';
      return;
    }
    box.innerHTML = shares.map(s => `
      <div class="session-row">
        <div>
          <div class="session-name">${esc(s.title || s.coupon_id)} <span class="session-account">${esc(s.account)}</span></div>
          <div class="muted" style="font-size:11.5px;margin-top:3px">до ${esc(s.expires_at || '—')}</div>
          <div class="session-link">${esc(s.link)}</div>
        </div>
        <div class="session-actions">
          <button class="btn btn-ghost btn-sm" data-copy="${esc(s.link)}">Копировать</button>
          <button class="btn btn-danger btn-sm" data-revoke="${s.token}">Отвязать</button>
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

$('cpnCreate').addEventListener('click', async () => {
  const btn = $('cpnCreate');
  btn.disabled = true;
  try {
    const account = $('cpnAccount').value;
    const id = $('cpnId').value.trim();
    if (!account || !id) { alert('Выберите аккаунт и укажите coupon id'); return; }
    const r = await api('/api/coupons/shares', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ account, coupon_id: id, hours: parseInt($('cpnHours').value, 10) || 24 }),
    });
    copyText(r.link, btn);
    loadCouponShares();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

function fillCouponAccounts() {
  const sel = $('cpnAccount');
  sel.innerHTML = '';
  (accounts.length ? accounts : []).forEach(a => {
    const o = document.createElement('option');
    o.value = a.name;
    o.textContent = a.name;
    sel.appendChild(o);
  });
}

// ================= prizes =================
let allPrizes = [];

async function loadPrizes() {
  try {
    const [prz, stats] = await Promise.all([api('/api/prizes'), api('/api/prizes/stats')]);
    allPrizes = prz;
    $('przCount').textContent = `всего ${stats.count}`;
    renderPrizesTable();
  } catch (e) {
    $('przTable').querySelector('tbody').innerHTML = `<tr><td colspan="7" class="db-empty">${esc(e.message)}</td></tr>`;
  }
}

function renderPrizesTable() {
  const tb = $('przTable').querySelector('tbody');
  tb.innerHTML = allPrizes.map(p => {
    const code = p.barcode || p.coupon_id || '';
    return `<tr>
      <td class="num">${fmtDateDb(p.obtained_at)}</td>
      <td><b>${esc(p.account)}</b></td>
      <td><b>${esc(p.name || 'Без названия')}</b></td>
      <td><span class="sd-badge ${p.display_type === 'postcard' ? '' : 'ok'}">${prizeCat(p.display_type)}</span></td>
      <td class="num">${code ? `<span class="mono">${esc(code)}</span>` : '—'}</td>
      <td class="num">${p.level ?? '—'}</td>
      <td class="col-actions">${code ? `<button class="btn btn-ghost btn-sm btn-copy" data-code="${esc(code)}">Копировать</button>` : ''}</td>
    </tr>`;
  }).join('') || '<tr><td colspan="7" class="db-empty">Пока нет выигранных призов</td></tr>';
  tb.querySelectorAll('.btn-copy').forEach(b => b.addEventListener('click', () => copyText(b.dataset.code, b)));
}

$('przCsv').addEventListener('click', () => {
  downloadCSV('prizes.csv', allPrizes.map(p => [p.account, p.name, prizeCat(p.display_type), p.barcode || p.coupon_id || '', p.level, p.obtained_at]));
});

// ================= sessions =================
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
          <div class="session-name">${esc(s.name)} <span class="session-account">${esc(s.account)}</span> ${modeBadge(s.mode)}</div>
          <div class="muted" style="font-size:11.5px;margin-top:3px">до ${esc(s.expires_at || '—')} · последний вход: ${esc(s.last_seen || 'никогда')}</div>
          <div class="session-link">${esc(location.origin + '/p/' + token)}</div>
        </div>
        <div class="session-actions">
          <button class="btn btn-ghost btn-sm" data-detail="${token}">Детали</button>
          <button class="btn btn-ghost btn-sm" data-copy="${esc(location.origin + '/p/' + token)}">Копировать</button>
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

function fillAccountsSelect() {
  const sel = $('accAccount');
  sel.innerHTML = '';
  (accounts.length ? accounts : []).forEach(a => {
    const o = document.createElement('option');
    o.value = a.name;
    o.textContent = a.name;
    sel.appendChild(o);
  });
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
        mode: $('accMode') ? $('accMode').value : 'both',
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

// ================= Моя карта (админ) =================
let adminCardTimer = null;
function fillCardAccountSelect() {
  const sel = $('cardAccount');
  if (!sel) return;
  sel.innerHTML = '';
  (accounts.length ? accounts : []).forEach(a => {
    const o = document.createElement('option');
    o.value = a.name;
    o.textContent = a.name;
    sel.appendChild(o);
  });
}

function renderAdminCardQr(canvas, text) {
  const qr = qrcode(0, 'M');
  qr.addData(text, 'Byte');
  qr.make();
  const n = qr.getModuleCount();
  const px = Math.max(6, Math.floor((canvas.width - 24) / n));
  const size = n * px + 24;
  canvas.width = size; canvas.height = size;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, size, size);
  ctx.fillStyle = '#111';
  for (let y = 0; y < n; y++) for (let x = 0; x < n; x++)
    if (qr.isDark(y, x)) ctx.fillRect(12 + x * px, 12 + y * px, px, px);
}

function loadCardAdmin() {
  fillCardAccountSelect();
  $('cardStatus').textContent = '';
}

async function showAdminCard() {
  const acc = $('cardAccount').value;
  if (!acc) { alert('Выберите аккаунт'); return; }
  const box = $('cardView');
  box.innerHTML = '<div class="hint">Загрузка карты…</div>';
  try {
    const data = await api('/api/card?account=' + encodeURIComponent(acc));
    const card = data.card || {};
    const bal = data.balance && data.balance.ok && data.balance.data ? data.balance.data : null;
    const balVal = bal != null ? (bal.totalPointBalance ?? bal.balance ?? null) : null;
    const points = balVal != null
      ? (Number(balVal) / 100).toLocaleString('ru-RU', { maximumFractionDigits: 1 }) + ' баллов'
      : '—';
    box.innerHTML = `
      <div style="display:flex;gap:18px;flex-wrap:wrap;align-items:flex-start">
        <div style="background:linear-gradient(135deg,#e4002b,#ff6b00);color:#fff;border-radius:18px;padding:18px;display:flex;flex-direction:column;justify-content:space-between;min-width:280px;box-shadow:0 10px 26px rgba(228,0,43,.25)">
          <div style="font-weight:800;font-size:18px;line-height:1.15">магнит<br>плюс</div>
          <div style="margin-top:14px">
            <div style="font-size:22px;font-weight:800">${esc(points)}${card.statusName ? `<span style="font-size:12px;opacity:.85"> · ${esc(card.statusName)}</span>` : ''}</div>
            <div style="font-size:14px;letter-spacing:1px;margin-top:6px"><span class="num-blur" title="Наведите, чтобы показать">${esc(data.identifierNo || '—')}</span></div>
          </div>
        </div>
        <div><canvas id="adminCardQr" width="260" height="260"></canvas></div>
      </div>
      <div style="margin-top:14px">
        <div style="font-size:13px;color:var(--muted)">Код для кассы</div>
        <div style="font-size:34px;font-weight:800;letter-spacing:4px" id="adminCardCode">${esc(data.code || '')}</div>
        <div style="font-size:12.5px;color:var(--muted);margin-top:4px" id="adminCardTimer"></div>
      </div>`;
    const qrEl = $('adminCardQr');
    if (qrEl && data.qr) renderAdminCardQr(qrEl, data.qr);
    startAdminCardTimer(data);
  } catch (e) {
    box.innerHTML = `<div class="sd-err">${esc(e.message)}</div>`;
  }
}

function startAdminCardTimer(data) {
  clearInterval(adminCardTimer);
  let left = Math.max(0, (data.expires_in || data.step || 300) - 1);
  const tick = () => {
    const t = $('adminCardTimer');
    if (t) t.textContent = 'Код обновится через ' + left + ' с';
    if (left <= 0) { showAdminCard(); return; }
    left--;
  };
  tick();
  adminCardTimer = setInterval(tick, 1000);
}

async function shareCardSession() {
  const acc = $('cardAccount').value;
  if (!acc) { alert('Выберите аккаунт'); return; }
  const name = prompt('Имя человека для сессии:') || '';
  const hours = parseInt(prompt('Срок действия, часов:', '24'), 10) || 24;
  try {
    const r = await api('/api/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: (name || acc).trim(), account: acc, hours, mode: 'card' }),
    });
    copyText(r.link, $('cardShare'));
    $('cardStatus').textContent = 'Сессия создана: ' + r.link;
  } catch (e) {
    alert(e.message);
  }
}

$('cardShow').addEventListener('click', showAdminCard);
$('cardShare').addEventListener('click', shareCardSession);

// ================= EDA =================
let edaAccounts = [];

function switchEdaTab(name) {
  document.querySelectorAll('.db-tabs.sub .db-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $('pane-edaAccs').classList.toggle('active', name === 'edaAccs');
  $('pane-edaSess').classList.toggle('active', name === 'edaSess');
}
document.querySelectorAll('.db-tabs.sub .db-tab').forEach(b => b.addEventListener('click', () => switchEdaTab(b.dataset.tab)));

async function loadEda() {
  await loadEdaAccounts();
  await loadEdaSessions();
  fillEdaAccountSelect();
  fillCouponAccounts();
  fillAccountsSelect();
}

async function loadEdaAccounts() {
  try {
    edaAccounts = await api('/api/eda/accounts');
    const tb = $('edaAccTable').querySelector('tbody');
    tb.innerHTML = edaAccounts.map(a => `
      <tr>
        <td><b>${esc(a.name)}</b></td>
        <td>${esc(a.profile_name || '—')}</td>
        <td>${a.plus_balance != null ? `<span class="sd-badge ok">${esc(String(a.plus_balance))}${esc(a.plus_status && a.plus_status !== 'NO_PLUS' ? ' 🅿' : '')}</span>` : '<span class="db-mut">—</span>'}</td>
        <td class="num">${esc(a.uid || '—')}</td>
        <td>${a.has_token ? '<span class="sd-badge ok">есть</span>' : '<span class="db-mut">—</span>'}</td>
        <td>${a.has_sid ? '<span class="sd-badge ok">есть</span>' : '<span class="db-mut">—</span>'}</td>
        <td>${esc(a.device || '—')}</td>
        <td class="num warmup-cell" data-warmup-name="${esc(a.name)}" data-ready-at="${a.promo_ready_at || ''}">${warmupCell(a)}</td>
        <td class="num">${a.orders != null ? esc(String(a.orders)) : '<span class="db-mut">—</span>'}</td>
        <td class="num">${esc(a.added || '—')}</td>
        <td class="col-actions">
          <button class="btn btn-ghost btn-sm" data-plus="${esc(a.name)}">Плюс</button>
          <button class="btn btn-ghost btn-sm" data-rotate="${esc(a.name)}">Устройство</button>
          <button class="btn btn-danger btn-sm" data-del="${esc(a.name)}">Удалить</button>
        </td>
      </tr>`).join('') || '<tr><td colspan="11" class="db-empty">Аккаунтов Я.Еды нет</td></tr>';
    tb.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/eda/accounts/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE' });
      loadEda();
    }));
    tb.querySelectorAll('[data-rotate]').forEach(b => b.addEventListener('click', async () => {
      const btn = b;
      btn.disabled = true;
      try {
        const r = await api(`/api/eda/accounts/${encodeURIComponent(b.dataset.rotate)}/rotate-device`, { method: 'POST' });
        alert(`Устройство сменено: ${r.device.model}`);
        loadEda();
      } catch (e) {
        alert(e.message);
      } finally {
        btn.disabled = false;
      }
    }));
    tb.querySelectorAll('[data-plus]').forEach(b => b.addEventListener('click', () => plusSubscribe(b.dataset.plus)));
  } catch (e) {
    $('edaAccTable').querySelector('tbody').innerHTML = `<tr><td colspan="11" class="db-empty">${esc(e.message)}</td></tr>`;
  }
}

function warmupCell(a) {
  if (!a.warmup_at && !a.promo_ready_at) return '<span class="db-mut">—</span>';
  if (a.promo_ready_at && a.promo_ready_at * 1000 <= Date.now()) return '<span class="sd-badge ok">готов 🔥</span>';
  return '<span class="sd-badge warn">⏳ …</span>';
}

function fmtLeft(sec) {
  const m = Math.floor(sec / 60), s = Math.round(sec % 60);
  return m > 0 ? `${m} мин ${s} с` : `${s} с`;
}

function tickWarmupCells() {
  document.querySelectorAll('.warmup-cell').forEach(td => {
    const t = Number(td.dataset.readyAt);
    if (!t) return;
    const left = t * 1000 - Date.now();
    if (left <= 0) {
      td.innerHTML = '<span class="sd-badge ok">готов 🔥</span>';
    } else {
      td.innerHTML = `<span class="sd-badge warn">⏳ ${fmtLeft(left / 1000)}</span>`;
    }
  });
}
setInterval(tickWarmupCells, 1000);

async function runEdaWarmup() {
  const btn = $('edaWarmupRun');
  btn.disabled = true;
  try {
    const r = await api('/api/eda/warmup', { method: 'POST' });
    const ok = (r.results || []).filter(x => !x.error);
    const err = (r.results || []).filter(x => x.error);
    let msg = `Прогрев запущен: ${ok.length} аккаунтов`;
    if (err.length) msg += `, ошибок: ${err.length} (${err[0].error})`;
    alert(msg);
    loadEda();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
}
$('edaWarmupRun').addEventListener('click', runEdaWarmup);

let pendingCardAccount = '';
let pendingCardValue = '';

async function plusSubscribe(name) {
  pendingCardAccount = name;
  pendingCardValue = '';
  $('cardError').classList.add('hidden');
  $('cardList').innerHTML = '<div class="card-empty">Загрузка…</div>';
  $('modalCard').classList.remove('hidden');
  await renderCardList();
}

async function renderCardList() {
  const list = $('cardList');
  let cards;
  try {
    const r = await api('/api/eda/cards');
    cards = r.cards || [];
  } catch (e) {
    list.innerHTML = `<div class="card-empty">${esc(e.message)}</div>`;
    return;
  }
  if (!cards.length) {
    list.innerHTML = '<div class="card-empty">Сохранённых карт пока нет — добавь новую ниже</div>';
    return;
  }
  list.innerHTML = cards.map((c, i) => `
    <div class="card-item ${i === 0 ? 'sel' : ''}" data-id="${esc(c.id)}" data-card="${esc(c.card)}" data-label="${esc(c.label)}">
      <div class="card-radio"></div>
      <div class="card-ico">••${esc(c.mask || '')}</div>
      <div class="card-info">
        <b>${esc(c.label || c.mask || c.id)}</b>
        <span>${esc(c.card.split(' ')[0] ? c.card.split(' ')[0] : '')} •••• ${esc(c.mask || '')} · ${esc(c.exp || '')}</span>
      </div>
      <button class="card-del" title="Удалить" data-del="${esc(c.id)}">🗑</button>
    </div>`).join('');
  list.querySelectorAll('.card-item').forEach(it => {
    it.addEventListener('click', () => {
      list.querySelectorAll('.card-item').forEach(x => x.classList.remove('sel'));
      it.classList.add('sel');
    });
    it.querySelector('[data-del]').addEventListener('click', async (e) => {
      e.stopPropagation();
      await api(`/api/eda/cards/${encodeURIComponent(it.dataset.id)}`, { method: 'DELETE' });
      renderCardList();
    });
  });
}

$('cardSave').addEventListener('click', async () => {
  $('cardError').classList.add('hidden');
  let card = '';
  const sel = document.querySelector('#cardList .card-item.sel');
  if (sel) card = sel.dataset.card;
  if (!card) {
    card = buildCardInput();
    if (!card) {
      showCardError('Введи номер, срок и CVC карты или выбери сохранённую');
      return;
    }
  }
  const label = $('cardLabel').value.trim();
  let cardStr = card;
  if (sel) {
    cardStr = card;
  } else {
    $('cardSave').disabled = true;
    $('cardSave').textContent = 'Сохраняю…';
    try {
      const r = await api('/api/eda/cards', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ label, card }),
      });
      cardStr = r.card.card;
      clearCardInput();
    } catch (e) {
      $('cardSave').disabled = false;
      $('cardSave').textContent = 'Сохранить и подключить';
      showCardError(e.message);
      return;
    }
    $('cardSave').disabled = false;
    $('cardSave').textContent = 'Сохранить и подключить';
  }
  pendingCardValue = cardStr;
  $('modalCard').classList.add('hidden');
  await plusSubscribeGo(pendingCardAccount, pendingCardValue);
});

function clearCardInput() {
  $('cardNumber').value = '';
  $('cardExpMonth').value = '';
  $('cardExpYear').value = '';
  $('cardCvc').value = '';
  $('cardLabel').value = '';
}

function buildCardInput() {
  const number = ($('cardNumber').value || '').replace(/\D/g, '');
  const month = ($('cardExpMonth').value || '').replace(/\D/g, '');
  const year = ($('cardExpYear').value || '').replace(/\D/g, '');
  const cvc = ($('cardCvc').value || '').replace(/\D/g, '');
  if (number.length < 13) { showCardError('Номер карты слишком короткий'); return ''; }
  if (!/^\d{1,2}$/.test(month) || +month < 1 || +month > 12) { showCardError('Укажи месяц срока (ММ)'); return ''; }
  if (!/^\d{1,2}$/.test(year)) { showCardError('Укажи год срока (ГГ)'); return ''; }
  if (!/^\d{3,4}$/.test(cvc)) { showCardError('CVC — 3 или 4 цифры'); return ''; }
  return { number, expiry: `${month.padStart(2, '0')}/${year.padStart(2, '0')}`, csc: cvc };
}

// форматирование номера карты по группам и автопереход к сроку
$('cardNumber').addEventListener('input', () => {
  const el = $('cardNumber');
  const digits = el.value.replace(/\D/g, '').slice(0, 19);
  el.value = digits.replace(/(\d{4})(?=\d)/g, '$1 ').trim();
  if (digits.length >= 16) $('cardExpMonth').focus();
});
$('cardExpMonth').addEventListener('input', () => {
  const el = $('cardExpMonth');
  const d = el.value.replace(/\D/g, '').slice(0, 2);
  el.value = d;
  if (d.length === 2) $('cardExpYear').focus();
});
$('cardExpYear').addEventListener('input', () => {
  const el = $('cardExpYear');
  const d = el.value.replace(/\D/g, '').slice(0, 2);
  el.value = d;
  if (d.length === 2) $('cardCvc').focus();
});
$('cardCvc').addEventListener('input', () => {
  const el = $('cardCvc');
  el.value = el.value.replace(/\D/g, '').slice(0, 4);
});

$('cardClose').addEventListener('click', () => $('modalCard').classList.add('hidden'));
$('modalCard').addEventListener('click', (e) => { if (e.target === $('modalCard')) $('modalCard').classList.add('hidden'); });

// ================= Прокси для сессий =================
let _proxyToken = null;

function proxyToShort(url) {
  if (!url) return '';
  const m = url.match(/^https?:\/\/([^@]+)@([^:]+):(\d+)$/);
  if (m) return `${m[2]}:${m[3]}:${m[1]}`;
  return url.replace(/^https?:\/\//, '');
}

function openProxyModal(token, sessData) {
  _proxyToken = token;
  const name = sessData ? sessData.name : token;
  $('proxySessName').textContent = 'Сессия: ' + name;
  $('proxyUrl').value = sessData ? (sessData.proxy || '') : '';
  $('proxyIp').textContent = '';
  $('proxyIp').className = 'proxy-ip';
  $('proxyError').classList.add('hidden');
  $('modalProxy').classList.remove('hidden');
  loadProxyList();
  if (sessData && sessData.proxy) fetchProxyIp(token);
}

$('proxyClose').addEventListener('click', () => $('modalProxy').classList.add('hidden'));
$('modalProxy').addEventListener('click', (e) => { if (e.target === $('modalProxy')) $('modalProxy').classList.add('hidden'); });

async function fetchProxyIp(token) {
  const el = $(`pip-${token}`);
  if (el) el.textContent = '⏳';
  try {
    const r = await api(`/api/eda/sessions/${token}/proxy`);
    if (el) {
      if (r.ip && r.ip.ok) {
        el.textContent = r.ip.ip;
      } else {
        el.textContent = '❌';
        el.title = r.ip ? r.ip.error : 'ошибка';
      }
    }
  } catch (e) {
    if (el) el.textContent = '❌';
  }
}

$('proxyCheck').addEventListener('click', async () => {
  const url = $('proxyUrl').value.trim();
  if (!url) { $('proxyIp').textContent = ''; return; }
  $('proxyIp').textContent = '⏳ проверяю…';
  $('proxyIp').className = 'proxy-ip';
  try {
    const r = await api('/api/eda/proxies/check', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });
    if (r.ok) {
      $('proxyIp').textContent = 'IP: ' + r.ip;
      $('proxyIp').className = 'proxy-ip';
    } else {
      $('proxyIp').textContent = '❌ ' + (r.error || 'недоступен');
      $('proxyIp').className = 'proxy-ip err';
    }
  } catch (e) {
    $('proxyIp').textContent = '❌ ошибка';
    $('proxyIp').className = 'proxy-ip err';
  }
});

$('proxySave').addEventListener('click', async () => {
  if (!_proxyToken) return;
  const url = $('proxyUrl').value.trim();
  try {
    await api(`/api/eda/sessions/${_proxyToken}/proxy`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxy: url }),
    });
    $('modalProxy').classList.add('hidden');
    loadEdaSessions();
  } catch (e) {
    $('proxyError').textContent = e.message;
    $('proxyError').classList.remove('hidden');
  }
});

$('proxyClear').addEventListener('click', async () => {
  if (!_proxyToken) return;
  try {
    await api(`/api/eda/sessions/${_proxyToken}/proxy`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ proxy: '' }),
    });
    $('modalProxy').classList.add('hidden');
    loadEdaSessions();
  } catch (e) {
    $('proxyError').textContent = e.message;
    $('proxyError').classList.remove('hidden');
  }
});

async function loadProxyList() {
  try {
    const proxies = await api('/api/eda/proxies');
    const el = $('proxyList');
    if (!proxies.length) {
      el.innerHTML = '<div class="proxy-empty">Нет сохранённых прокси</div>';
      return;
    }
    el.innerHTML = proxies.map(p => {
      const short = proxyToShort(p.url);
      return `<div class="proxy-item" data-use-proxy="${esc(p.url)}">
        <span class="proxy-name">${esc(p.name)}</span>
        <span class="proxy-url">${esc(short)}</span>
        <button class="proxy-del" data-del-proxy="${esc(p.url)}" title="Удалить">&times;</button>
      </div>`;
    }).join('');
    el.querySelectorAll('[data-use-proxy]').forEach(item => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.proxy-del')) return;
        $('proxyUrl').value = item.dataset.useProxy;
      });
    });
    el.querySelectorAll('[data-del-proxy]').forEach(btn => {
      btn.addEventListener('click', async (e) => {
        e.stopPropagation();
        await api(`/api/eda/proxies/${encodeURIComponent(btn.dataset.delProxy)}`, { method: 'DELETE' });
        loadProxyList();
      });
    });
  } catch (e) {}
}

$('proxyAdd').addEventListener('click', async () => {
  const name = $('proxyNewName').value.trim();
  const url = $('proxyNewUrl').value.trim();
  if (!url) return;
  try {
    await api('/api/eda/proxies', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, url }),
    });
    $('proxyNewName').value = '';
    $('proxyNewUrl').value = '';
    loadProxyList();
  } catch (e) {
    $('proxyError').textContent = e.message;
    $('proxyError').classList.remove('hidden');
  }
});

function showCardError(msg) {
  const el = $('cardError');
  el.textContent = msg;
  el.classList.remove('hidden');
}

async function plusSubscribeGo(name, card) {
  let payload = { card: card.trim() };
  for (let step = 0; step < 5; step++) {
    let r;
    try {
      r = await api(`/api/eda/accounts/${encodeURIComponent(name)}/plus-subscribe`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } catch (e) {
      alert(e.message);
      return;
    }
    if (r.ok && r.stage === 'sms') {
      payload.purchase_token = r.purchase_token || '';
      payload.invoice_id = r.invoice_id || '';
      const sms = prompt(r.message || 'Введи SMS-код от банка:');
      if (!sms) return;
      payload.sms_code = sms.trim();
      continue;
    }
    if (r.ok && r.stage === '3ds') {
      payload.purchase_token = r.purchase_token || '';
      payload.invoice_id = r.invoice_id || '';
      return await run3ds(name, r);
    }
    if (r.ok && r.stage === 'done') {
      alert(`Плюс подключён (${r.status || ''})`);
      loadEda();
      return;
    }
    if (r.ok === false) {
      alert(`Ошибка: ${r.error || 'неизвестно'}`);
      return;
    }
    alert(`Неизвестный ответ: ${JSON.stringify(r || {}).slice(0, 300)}`);
    return;
  }
  alert('Не удалось финализировать подключение за 5 шагов');
}

async function run3ds(name, r) {
  let status;
  try {
    status = await api(`/api/eda/accounts/${encodeURIComponent(name)}/plus-3ds-open`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ purchase_token: r.purchase_token || '', invoice_id: r.invoice_id || '', challenge_url: r.challenge_url || '' }),
    });
  } catch (e) {
    alert(`3DS: ${e.message}`);
    return;
  }
  if (!status.ok) {
    alert(`3DS: ${status.error || 'не удалось открыть форму'}`);
    return;
  }
  alert(`Банк требует подтверждение 3DS.\nОткрываю страницу банка в Chrome.\nВведи SMS-код, а я дождусь оплаты и активирую Плюс.`);
  for (;;) {
    await new Promise(r2 => setTimeout(r2, 3000));
    let st;
    try {
      st = await api(`/api/eda/accounts/${encodeURIComponent(name)}/plus-3ds-status`);
    } catch (e) {
      continue;
    }
    if (st.stage === 'done') {
      alert(`3DS пройден, Плюс подключён (${st.status || ''})`);
      loadEda();
      return;
    }
    if (st.stage === 'failed' || st.stage === 'timeout' || st.stage === 'error') {
      alert(`3DS: ${st.error || st.stage}`);
      return;
    }
  }
}

async function runEdaCheck() {
  const btn = $('edaCheckRun');
  const prog = $('edaCheckProgress');
  const res = $('edaCheckResult');
  btn.disabled = true;
  prog.classList.remove('hidden');
  res.innerHTML = '';
  try {
    const { task_id } = await api('/api/eda/accounts/check', { method: 'POST' });
    const render = (st) => {
      $('edaCheckFill').style.width = `${st.progress || 0}%`;
      $('edaCheckMsg').textContent = `${st.progress || 0}% — ${st.message || ''}`;
    };
    for (;;) {
      const st = await api(`/api/eda/accounts/check/${task_id}`);
      render(st);
      if (st.state === 'done' || st.state === 'error') break;
      await new Promise(r => setTimeout(r, 1500));
    }
    const st = await api(`/api/eda/accounts/check/${task_id}`);
    res.innerHTML = (st.result || []).map(r =>
      `<span class="sd-badge ${r.ok ? 'ok' : 'bad'}">${esc(r.name)}: ${r.ok ? 'OK' : esc(r.message)}</span>`).join(' ');
    const okN = (st.result || []).filter(r => r.ok).length;
    const badN = (st.result || []).length - okN;
    $('edaCheckMsg2').textContent = `${okN} ок${badN ? `, ${badN} проблем` : ''}`;
    loadEda();
  } catch (e) {
    res.innerHTML = `<span class="sd-badge bad">${esc(e.message)}</span>`;
  } finally {
    prog.classList.add('hidden');
    btn.disabled = false;
  }
}

$('edaCheckRun').addEventListener('click', runEdaCheck);

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
        session_id: $('edaSid').value.trim(),
      }),
    });
    $('edaName').value = '';
    $('edaToken').value = '';
    $('edaUid').value = '';
    $('edaSid').value = '';
    loadEda();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

let edaRegTimer = null;
$('edaRegStart').addEventListener('click', async () => {
  const btn = $('edaRegStart');
  btn.disabled = true;
  try {
    const r = await api('/api/eda/reg/start', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('edaRegName').value.trim(),
        count: parseInt($('edaRegCount').value || '1', 10) || 1,
      }),
    });
    $('edaRegMsg').textContent = `запущено задач: ${(r.task_ids || []).length}`;
    pollEdaReg();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

async function pollEdaReg() {
  if (edaRegTimer) return;
  const render = async () => {
    try {
      const r = await api('/api/eda/reg/status');
      const tasks = Object.entries(r.tasks || {});
      if (!tasks.length || tasks.every(([, t]) => t.state === 'done' || t.state === 'failed' || t.state === 'cancelled')) {
        edaRegTimer = null;
        if (tasks.length) loadEda();
        return;
      }
      edaRegTimer = setTimeout(render, 2000);
      const lines = tasks.map(([id, t]) => {
        const st = esc(t.state);
        const err = t.error ? ` <span class="db-err">${esc(t.error)}</span>` : '';
        return `<div>#${esc(id)} [${st}] ${esc(t.name || '')} — ${esc(t.progress || '')}${err}</div>`;
      }).join('');
      $('edaRegMsg').innerHTML = lines;
    } catch (e) {
      edaRegTimer = null;
    }
  };
  await render();
}

async function loadEdaSessions() {
  try {
    const sess = await api('/api/eda/sessions');
    const entries = Object.entries(sess).filter(([, v]) => v.active);
    const tb = $('edaSessTable').querySelector('tbody');
    tb.innerHTML = entries.map(([token, s]) => {
      const proxy = s.proxy || '';
      const proxyShort = proxy ? proxyToShort(proxy) : '';
      const ipCell = proxy
        ? `<span class="proxy-ip-cell" id="pip-${token}">⏳</span>`
        : `<span class="proxy-ip-cell none">—</span>`;
      return `<tr>
        <td><b>${esc(s.name)}</b></td>
        <td><b>${esc(s.account)}</b></td>
        <td><span class="mono db-mut">${esc(location.origin + '/d/' + token)}</span></td>
        <td><span class="mono db-mut" id="sk-${token}">${esc(s.sale_key || '—')}</span></td>
        <td>${ipCell}</td>
        <td class="num">${esc(s.expires_at || '—')}</td>
        <td class="col-actions">
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" data-proxy="${token}">🌐 Прокси</button>
            <button class="btn btn-ghost btn-sm" data-copy="${esc(location.origin + '/d/' + token)}">Ссылка</button>
            <button class="btn btn-ghost btn-sm" data-key="${token}">🔑 Ключ</button>
            <button class="btn btn-danger btn-sm" data-revoke="${token}">Отозвать</button>
          </div>
        </td>
      </tr>`;
    }).join('') || '<tr><td colspan="7" class="db-empty">Активных сессий Еды нет</td></tr>';
    tb.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => copyText(b.dataset.copy, b)));
    tb.querySelectorAll('[data-key]').forEach(b => b.addEventListener('click', async () => {
      const btn = b;
      btn.disabled = true;
      try {
        const r = await api(`/api/eda/${b.dataset.key}/sale-key`, { method: 'GET' });
        const span = $(`sk-${b.dataset.key}`);
        if (span) span.textContent = r.sale_key;
        copyText(r.sale_key, btn);
      } catch (e) {
        alert(e.message);
      } finally {
        btn.disabled = false;
      }
    }));
    tb.querySelectorAll('[data-revoke]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/eda/sessions/${b.dataset.revoke}`, { method: 'DELETE' });
      loadEdaSessions();
    }));
    tb.querySelectorAll('[data-proxy]').forEach(b => b.addEventListener('click', () => openProxyModal(b.dataset.proxy, sess[b.dataset.proxy])));
    entries.forEach(([token, s]) => {
      if (s.proxy) fetchProxyIp(token);
    });
  } catch (e) {
    $('edaSessTable').querySelector('tbody').innerHTML = `<tr><td colspan="7" class="db-empty">${esc(e.message)}</td></tr>`;
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

// ================= Автозаказ Я.Еды =================
let az = { account: '', city: '', addr: null, addrs: [], addrLoc: null, restaurants: [], rest: null, menu: null, cart: null, checkout: null, payment: null, addrData: null, promo: '', phone: '', orderNr: '', items: {} };

function fmtRub(n) {
  const v = parseFloat(n);
  return isNaN(v) ? '—' : v.toLocaleString('ru-RU', { minimumFractionDigits: v % 1 ? 2 : 0 }) + ' ₽';
}

async function loadAuto() {
  if (!$('azAccount')) return;
  try {
    const accs = await api('/api/eda/autozakaz/accounts');
    const sel = $('azAccount');
    sel.innerHTML = '';
    accs.forEach(a => {
      const o = document.createElement('option');
      o.value = a.name;
      o.textContent = a.profile_name ? `${a.name} (${a.profile_name})` : a.name;
      sel.appendChild(o);
    });
    if (az.account && accs.some(a => a.name === az.account)) sel.value = az.account;
    else if (accs.length) sel.value = accs[0].name;
    if (sel.value) await azSelectAccount();
    else azRender('<div class="hint" style="padding:24px">Аккаунтов Я.Еды нет — добавьте их на вкладке «ЕДА»</div>');
  } catch (e) {
    azRender(`<div class="err">${esc(e.message)}</div>`);
  }
}

async function azSelectAccount() {
  az.account = $('azAccount').value;
  az.city = ''; az.addr = null; az.restaurants = []; az.rest = null;
  az.menu = null; az.cart = null; az.checkout = null;
  $('azStatus').textContent = 'Загружаю адреса…';
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cities`);
    const cities = r.cities || [];
    az.addrs = [];
    cities.forEach(c => (c.addresses || []).forEach(a => az.addrs.push(a)));
    const citySel = $('azCity');
    citySel.innerHTML = '';
    cities.forEach(c => {
      const o = document.createElement('option');
      o.value = c.city;
      o.textContent = `${c.city} (${c.addresses.length})`;
      citySel.appendChild(o);
    });
    if (az.city && cities.some(c => c.city === az.city)) citySel.value = az.city;
    else if (cities.length) citySel.value = cities[0].city;
    if (cities.length) azSelectCity();
    else azRender('<div class="hint" style="padding:24px">У аккаунта нет сохранённых адресов</div>');
  } catch (e) {
    azRender(`<div class="err">${esc(e.message)}</div>`);
  }
}

async function azSelectCity() {
  az.city = $('azCity').value;
  az.addr = null; az.restaurants = []; az.rest = null; az.menu = null; az.cart = null;
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cities`);
    const city = (r.cities || []).find(c => c.city === az.city);
    const sel = $('azAddr');
    sel.innerHTML = '';
    (city ? city.addresses : []).forEach(a => {
      const o = document.createElement('option');
      o.value = a.id;
      o.textContent = `${a.short_text}${a.type ? ' — ' + a.type : ''}`;
      sel.appendChild(o);
    });
    if (sel.options.length) {
      sel.selectedIndex = 0;
      az.addr = sel.options[sel.selectedIndex].value;
      az.addrLoc = city && city.addresses[0] ? city.addresses[0].location : null;
      azSelectAddr();
    } else {
      azRender('<div class="hint" style="padding:24px">В этом городе нет адресов</div>');
    }
  } catch (e) {
    azRender(`<div class="err">${esc(e.message)}</div>`);
  }
}

async function azSelectAddr() {
  az.addr = $('azAddr').value;
  const a = (az.addrs || []).find(x => x.id === az.addr);
  az.addrLoc = (a && a.location && a.location.latitude != null) ? a.location : null;
  az.restaurants = []; az.rest = null; az.menu = null; az.cart = null; az.checkout = null;
  az.payment = null; az.available = []; az.promo = ''; az.phone = ''; az.orderNr = ''; az.addrData = null;
  await azLoadCart();
  $('azStatus').textContent = '';
  azRender('<div class="hint" style="padding:24px">Найдите ресторан или магазин через поиск</div>');
}

async function azLoadCart() {
  if (!az.account || !az.addr) return;
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cart?place_slug=${encodeURIComponent(az.rest || '')}`);
    az.cart = r.cart && r.cart.cart ? r.cart.cart : (r.cart || {});
    renderAzCartTotal();
  } catch (e) { /* молча */ }
}

function renderAzCartTotal() {
  const c = az.cart || {};
  const total = parseFloat(c.total);
  const items = (c.items || []).length;
  $('azCartTotal').textContent = items
    ? `🛒 ${items} поз. · ${fmtRub(isNaN(total) ? 0 : total)}`
    : '';
}

async function azSearch() {
  const q = $('azSearch').value.trim();
  if (!az.addr) { alert('Сначала выберите адрес'); return; }
  $('azStatus').textContent = 'Ищу…';
  const lat = az.addrLoc ? az.addrLoc.latitude : undefined;
  const lon = az.addrLoc ? az.addrLoc.longitude : undefined;
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/restaurants?query=${encodeURIComponent(q)}&lat=${lat || ''}&lon=${lon || ''}`);
    az.restaurants = extractPlaces(r.restaurants);
    azRenderPlaces();
  } catch (e) {
    azRender(`<div class="err">${esc(e.message)}</div>`);
  }
}

function extractPlaces(d) {
  const out = [];
  const walk = (o) => {
    if (Array.isArray(o)) { o.forEach(walk); return; }
    if (!o || typeof o !== 'object') return;
    if (o.payload && Array.isArray(o.payload)) {
      o.payload.forEach(p => { if (p && p.slug && !out.some(x => x.slug === p.slug)) out.push(p); });
    }
    Object.values(o).forEach(walk);
  };
  walk(d);
  return out;
}

function azRender(html) {
  const box = $('azBody');
  if (box) box.innerHTML = html;
}

function azRenderPlaces() {
  const list = az.restaurants;
  if (!list.length) { azRender('<div class="hint" style="padding:24px">Ничего не найдено</div>'); return; }
  azRender(`<div class="az-grid">
    ${list.map(p => {
      const price = p.price_cat === 'price_high' ? '💰💰💰' : p.price_cat === 'price_mid' ? '💰💰' : '💰';
      const tags = (p.tags || []).filter(t => t && typeof t === 'string').slice(0, 3).map(t => `<span class="az-tag">${esc(t)}</span>`).join('');
      return `<div class="az-card" data-slug="${esc(p.slug)}" data-name="${esc(p.title || p.brand || p.slug)}">
        <div class="az-card-head"><b>${esc(p.brand || p.title || p.slug)}</b><span class="az-price">${price}</span></div>
        ${p.title ? `<div class="az-card-sub">${esc(p.title)}</div>` : ''}
        ${tags ? `<div class="az-tags">${tags}</div>` : ''}
        <div class="az-card-foot">
          <span class="db-mut">${p.business === 'shop' ? 'магазин' : 'ресторан'}${p.available === false ? ' · недоступен' : ''}</span>
          <button class="btn btn-primary btn-sm">Меню</button>
        </div>
      </div>`;
    }).join('')}
  </div>`);
  document.querySelectorAll('#azBody .az-card').forEach(card => {
    card.addEventListener('click', () => azOpenMenu(card.dataset.slug));
  });
}

async function azOpenMenu(slug) {
  az.rest = slug;
  $('azStatus').textContent = 'Загружаю меню…';
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/menu/${encodeURIComponent(slug)}`);
    az.menu = r.menu;
    az.items = {};
    azRenderMenu();
    await azLoadCart();
  } catch (e) {
    azRender(`<div class="err">${esc(e.message)}</div>`);
  }
}

function menuCategories(d) {
  const cats = [];
  const walk = (o, depth) => {
    if (Array.isArray(o)) { o.forEach(v => walk(v, depth)); return; }
    if (!o || typeof o !== 'object') return;
    const payload = o.payload;
    if (payload && Array.isArray(payload.categories)) {
      payload.categories.forEach(c => {
        if (c && typeof c === 'object' && (c.items || []).length) cats.push(c);
        else if (c && c.categories) walk(c.categories, depth + 1);
      });
    }
    Object.values(o).forEach(v => walk(v, depth));
  };
  walk(d, 0);
  return cats;
}

function collectItems(cats) {
  const out = [];
  cats.forEach(c => {
    (c.items || []).forEach(it => {
      if (it && typeof it === 'object' && it.id != null) out.push({ cat: c.name, ...it });
    });
    if (c.categories) collectItems(c.categories).forEach(x => out.push({ cat: c.name + ' → ' + x.cat, ...x }));
  });
  return out;
}

function azRenderMenu() {
  const items = collectItems(menuCategories(az.menu));
  if (!items.length) { azRender('<div class="hint" style="padding:24px">Меню пустое или не разобралось</div>'); return; }
  azRender(`
    <div class="db-toolbar">
      <button class="backlink" onclick="az.backToPlaces()">‹ Назад к ресторанам</button>
      <span class="db-count">${esc(az.restaurants.find(p => p.slug === az.rest)?.title || az.rest)}</span>
    </div>
    <div class="db-toolbar">
      <input type="search" id="azItemSearch" class="db-search" placeholder="Поиск по меню…" style="max-width:300px">
    </div>
    <div class="az-grid" id="azMenuGrid">
    ${items.map(it => {
      const opt = (it.optionsGroups || []).length;
      return `<div class="az-card" data-id="${it.id}" ${it.available === false ? 'style="opacity:.5"' : ''}>
        <div class="az-card-head"><b>${esc(it.name || 'Товар')}</b><span class="az-price">${fmtRub(it.price ?? it.decimalPrice ?? 0)}</span></div>
        ${it.description ? `<div class="az-card-sub">${esc(it.description)}</div>` : ''}
        ${opt ? `<div class="db-mut">⚠ ${opt} опц.</div>` : ''}
        <div class="az-card-foot">
          <span class="db-mut">${it.measure || ''}</span>
          <div class="az-qty"><button class="btn btn-ghost btn-sm" data-dec="${it.id}">−</button>
            <b data-qty="${it.id}">0</b>
            <button class="btn btn-primary btn-sm" data-inc="${it.id}">+</button></div>
        </div>
      </div>`;
    }).join('')}
    </div>`);
  bindAzMenuClicks();
  $('azItemSearch').addEventListener('input', (e) => {
    const q = e.target.value.trim().toLowerCase();
    document.querySelectorAll('#azMenuGrid .az-card').forEach(card => {
      card.style.display = q && !card.textContent.toLowerCase().includes(q) ? 'none' : '';
    });
  });
}

function bindAzMenuClicks() {
  document.querySelectorAll('#azMenuGrid [data-inc]').forEach(b => b.addEventListener('click', async (e) => {
    e.stopPropagation();
    await azAddItem(b.dataset.inc, 1);
  }));
  document.querySelectorAll('#azMenuGrid [data-dec]').forEach(b => b.addEventListener('click', async (e) => {
    e.stopPropagation();
    if (az.items[b.dataset.dec] > 0) await azAddItem(b.dataset.dec, -1);
  }));
}

async function azAddItem(itemId, delta) {
  if (!az.rest) return;
  az.items[itemId] = (az.items[itemId] || 0) + delta;
  if (az.items[itemId] < 0) az.items[itemId] = 0;
  const q = az.items[itemId];
  document.querySelectorAll(`#azMenuGrid [data-qty="${itemId}"]`).forEach(el => el.textContent = q);
  $('azStatus').textContent = 'Добавляю в корзину…';
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cart`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ place_slug: az.rest, item_id: itemId, qty: 1, lat: az.addrLoc?.latitude, lon: az.addrLoc?.longitude }),
    });
    const cart = r.cart && r.cart.cart ? r.cart.cart : (r.cart || {});
    az.cart = cart;
    renderAzCartTotal();
    $('azStatus').textContent = 'В корзине';
  } catch (e) {
    $('azStatus').textContent = 'Ошибка: ' + e.message;
  }
}

async function azShowCart() {
  if (!az.account) return;
  $('azStatus').textContent = 'Загружаю корзину…';
  try {
    await azLoadCart();
    const c = az.cart || {};
    const items = c.items || [];
    if (!items.length) { azRender('<div class="hint" style="padding:24px">Корзина пуста</div>'); return; }
    azRender(`
      <div class="db-toolbar">
        <button class="backlink" onclick="az.backToMenu()">‹ Назад к меню</button>
        <span class="db-count">Корзина</span>
      </div>
      ${items.map(it => `<div class="az-card">
        <div class="az-card-head"><b>${esc(it.name || it.title || 'Товар')}</b><span class="az-price">${fmtRub((it.price ?? it.decimal_price ?? 0) * (it.quantity || 1))}</span></div>
        <div class="az-card-foot"><span class="db-mut">${it.quantity || 1} шт × ${fmtRub(it.price ?? it.decimal_price ?? 0)}</span></div>
      </div>`).join('')}
      <div class="cart-sum"><span>Итого</span><span class="sum-val">${fmtRub(c.total)}</span></div>
      ${c.delivery_fee ? `<div class="db-mut">Доставка: ${fmtRub(c.delivery_fee)}</div>` : ''}
      <div class="db-toolbar" style="margin-top:12px">
        <button class="btn btn-primary btn-sm" id="azCheckoutGo">💳 Оформить заказ</button>
      </div>`);
    $('azCheckoutGo').addEventListener('click', azCheckout);
  } catch (e) {
    azRender(`<div class="err">${esc(e.message)}</div>`);
  }
}

async function azCheckout(paymentId, paymentType) {
  if (!az.addr || !az.rest) return;
  $('azStatus').textContent = 'Оформляю…';
  try {
    const addr = azBuildAddr();
    az.addrData = addr;
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/web-checkout`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        place_slug: az.rest, address: addr,
        lat: az.addrLoc?.latitude, lon: az.addrLoc?.longitude,
        payment_id: paymentId || 'sbp_qr',
        payment_type: paymentType || 'sbp',
      }),
    });
    az.checkout = r.checkout;
    az.payment = r.payment;
    az.available = r.available || [];
    const cardOffers = az.available.filter((o) => o && o.type === 'card');
    if (cardOffers.length) {
      api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cards/save`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ cards: cardOffers.map((o) => ({ id: o.id, type: 'card', title: o.title || 'Карта' })) }),
      }).catch(() => {});
    }
    try {
      const cc = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cards`);
      az.cards = cc.cards || [];
    } catch (e) { az.cards = az.cards || []; }
    azRenderCheckout(addr);
  } catch (e) {
    azRender(`<div class="err">${esc(e.message)}</div>`);
  }
}

function azBuildAddr() {
  const a = (az.addrs || []).find(x => x.id === az.addr);
  if (!a) return null;
  const addr = {
    city: a.city, street: a.street, house: a.house,
    country: a.country || 'Российская Федерация',
    short_text: a.short_text, full_text: a.full_text,
    location: { latitude: a.location.latitude, longitude: a.location.longitude },
  };
  if (a.uri) addr.uri = a.uri;
  if (a.areas) addr.areas = a.areas;
  if (a.districts) addr.districts = a.districts;
  if ($('azFlat').value.trim()) addr.office = $('azFlat').value.trim();
  if ($('azEntrance').value.trim()) addr.entrance = $('azEntrance').value.trim();
  if ($('azFloor').value.trim()) addr.floor = $('azFloor').value.trim();
  if ($('azIntercom').value.trim()) addr.doorcode = $('azIntercom').value.trim();
  return addr;
}

function azAddrComment(addr) {
  const p = [];
  if (addr.office) p.push('кв ' + addr.office);
  if (addr.entrance) p.push('под ' + addr.entrance);
  if (addr.floor) p.push('эт ' + addr.floor);
  if (addr.doorcode) p.push('домофон ' + addr.doorcode);
  return p.join('; ');
}

function azRenderCheckout(addr) {
  azRender(`
    <div class="db-toolbar">
      <button class="backlink" onclick="az.backToCart()">‹ Назад к корзине</button>
      <span class="db-count">Оформление</span>
    </div>
    <div class="hint">Доставка на: <b>${esc(addr ? addr.full_text : '')}</b>${addr && azAddrComment(addr) ? `<div class="db-mut">${esc(azAddrComment(addr))}</div>` : ''}</div>
    ${azRenderSavedCards()}
    <div class="chk-block">
      <h3>Способ оплаты</h3>
      ${azRenderPayOpts()}
    </div>
    <div class="chk-block">
      <h3>Промокод</h3>
      <div class="db-toolbar">
        <input class="db-search" id="azPromo" style="min-width:240px" placeholder="Например SALE20" value="${esc(az.promo)}" />
        <button class="btn btn-primary btn-sm" id="azPromoGo">Применить</button>
      </div>
      <div class="db-mut" id="azPromoMsg"></div>
    </div>
    <div class="chk-block">
      <h3>Телефон получателя</h3>
      <input class="db-search" id="azPhone" style="min-width:240px" placeholder="+7 900 000-00-00" value="${esc(az.phone)}" />
    </div>
    <div class="db-toolbar" style="margin-top:12px">
      <button class="btn btn-primary" id="azOrderBtn">💳 Оформить заказ</button>
    </div>`);
  $('azPromoGo').addEventListener('click', azApplyPromo);
  $('azPromo').addEventListener('keydown', (e) => { if (e.key === 'Enter') azApplyPromo(); });
  $('azOrderBtn').addEventListener('click', azOrder);
  $('azBindCardBtn').addEventListener('click', azOpenBind);
  $('azBindRefresh').addEventListener('click', azRefreshCards);
}

function azRenderSavedCards() {
  const cards = (az.cards || []).filter((c) => c && (c.type === 'card' || /^card-/.test(c.id || '')));
  if (!cards.length) return '';
  const items = cards.map((c) => {
    const n = c.number || c.short_number || c.method_id || '';
    return `<span class="sd-badge ok">💳 ${esc(c.title || c.id)}${n ? ` · ${esc(String(n).slice(-4))}` : ''}</span>`;
  }).join(' ');
  return `<div class="hint">Мои карты: ${items}</div>`;
}

async function azOpenBind() {
  const msg = $('azBindMsg') || $('azCardsMsg');
  if (!msg) return;
  msg.textContent = 'Создаю форму привязки…';
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cards/bind`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        place_slug: az.rest, address: az.addrData,
        lat: az.addrLoc?.latitude, lon: az.addrLoc?.longitude,
      }),
    });
    if (!r.form_url) { msg.textContent = 'Ошибка: ' + (r.error || 'Траст не вернул форму привязки'); return; }
    msg.innerHTML = 'Форма привязки открыта в новой вкладке — введите номер, срок и CVC, затем код из SMS.<br>После успешной привязки вернитесь сюда и нажмите <b>⟳ Обновить</b>.';
    const rb = $('azBindRefresh') || $('azCardsRefresh');
    if (rb) rb.disabled = false;
    window.open(r.form_url, '_blank', 'noopener');
  } catch (e) {
    msg.textContent = 'Ошибка: ' + e.message;
  }
}

async function azRefreshCards() {
  const msg = $('azBindMsg') || $('azCardsMsg');
  if (!msg) return;
  msg.textContent = 'Обновляю карты из Траста…';
  try {
    await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cards/refresh`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    msg.textContent = 'Карты обновлены.';
    if ($('azCardsList')) {
      await azLoadCardsList();
    } else if ($('azBindMsg')) {
      msg.textContent += ' Пересчитываю оформление…';
      az.payment = null;
      await azCheckout();
    }
  } catch (e) {
    msg.textContent = 'Ошибка обновления карт: ' + e.message;
  }
}

function azCardsBack() {
  if (az.addr) azRenderPlaces();
  else azSelectAccount();
}

async function azCardsPanel() {
  if (!az.account) { azRender('<div class="hint">Сначала выберите аккаунт</div>'); return; }
  azRender(`
    <div class="db-toolbar">
      <button class="backlink" onclick="azCardsBack()">‹ Назад</button>
      <span class="db-count">Мои карты</span>
    </div>
    <div class="db-toolbar" style="margin-top:8px;gap:8px">
      <button class="btn btn-primary btn-sm" id="azCardsAdd">➕ Добавить карту</button>
      <button class="btn btn-outline btn-sm" id="azCardsRefresh">⟳ Обновить из Траста</button>
    </div>
    <div class="db-mut" id="azCardsMsg"></div>
    <div id="azCardsList" class="hint" style="margin-top:8px">Загружаю…</div>`);
  $('azCardsAdd').addEventListener('click', azOpenBind);
  $('azCardsRefresh').addEventListener('click', azRefreshCards);
  await azLoadCardsList();
}

async function azLoadCardsList() {
  const box = $('azCardsList');
  if (!box) return;
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/cards`);
    const cards = (r.cards || []).filter((c) => c && c.id);
    if (!cards.length) {
      box.innerHTML = '<div class="db-mut">Сохранённых карт нет. Нажмите «➕ Добавить карту» — откроется форма Траста.</div>';
      return;
    }
    box.innerHTML = cards.map((c) => {
      const n = String(c.number || c.method_id || '').slice(-4);
      return `<div class="pay-opt"><span>💳 ${esc(c.title || c.id)}</span>${n ? `<span class="db-mut">·· ${esc(n)}</span>` : ''}</div>`;
    }).join('');
  } catch (e) {
    box.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

function azPayIcon(t) {
  return t === 'sbp' ? '🏦' : t === 'add_new_card' ? '➕' : '💳';
}

function azRenderPayOpts() {
  const cur = az.payment || {};
  let avail = (az.available && az.available.length) ? az.available
    : (cur.id || cur.type ? [{ id: cur.id, type: cur.type, title: cur.title }] : []);
  avail = avail.filter((o) => o && o.type !== 'add_new_card');
  const cards = avail.filter((o) => o.type === 'card');
  const others = avail.filter((o) => o.type !== 'card');
  const curId = cur.id || cur.type || '';
  const row = (o) => `
    <div class="pay-opt pay-select" onclick="azCheckout(${esc(JSON.stringify(o.id || o.type))}, ${esc(JSON.stringify(o.type))})">
      <span>${azPayIcon(o.type)} ${esc(o.title || o.type)}</span>
      <span class="st">${o.costForCustomer ? fmtRub(o.costForCustomer) : ''}</span>
      ${curId === (o.id || o.type) ? '<span class="st">✓</span>' : ''}
    </div>`;
  return `<div id="azPayOpts">${others.map(row).join('')}${cards.map(row).join('')}</div>`
    + `<div class="db-toolbar" style="margin-top:8px;gap:8px">
         <button class="btn btn-outline btn-sm" id="azBindCardBtn">➕ Добавить карту</button>
         <button class="btn btn-outline btn-sm" id="azBindRefresh" disabled>⟳ Обновить карты</button>
       </div>
       <div class="db-mut" id="azBindMsg"></div>
       <div class="db-mut">Текущий: ${esc(cur.title || curId || 'не выбран')}${cur.offer_identity ? ` · offer ${esc(String(cur.offer_identity).slice(0, 20))}…` : ''}</div>`;
}

async function azApplyPromo() {
  const code = $('azPromo').value.trim();
  if (!code) return;
  az.promo = code;
  const msg = $('azPromoMsg');
  msg.textContent = 'Применяю…';
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/promocode`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ place_slug: az.rest, code, offer_identity: (az.payment || {}).offer_identity, lat: az.addrLoc?.latitude, lon: az.addrLoc?.longitude }),
    });
    const res = r.result || {};
    if (res.status === 'error') {
      msg.textContent = 'Промокод: ' + (res.err || 'не применился');
    } else {
      msg.textContent = 'Промокод применён, пересчитываю…';
      azCheckout();
    }
  } catch (e) {
    msg.textContent = 'Ошибка: ' + e.message;
  }
}

async function azOrder() {
  if (!az.addrData) { alert('Сначала оформите корзину'); return; }
  const phone = $('azPhone').value.trim();
  az.phone = phone;
  if (!phone) { alert('Укажите телефон получателя'); return; }
  const btn = $('azOrderBtn');
  btn.disabled = true;
  btn.textContent = 'Создаю заказ…';
  const pay = az.payment || {};
  const firstAvail = (az.available || []).find((a) => a && a.type !== 'add_new_card');
  const payment_id = pay.id || pay.type || (firstAvail ? (firstAvail.id || firstAvail.type) : 'sbp_qr');
  const payment_type = pay.type || (firstAvail ? firstAvail.type : 'sbp');
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/order`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ place_slug: az.rest, address: az.addrData, phone, code: az.promo || undefined, lat: az.addrLoc?.latitude, lon: az.addrLoc?.longitude, payment_id, payment_type }),
    });
    az.orderNr = (r.order || {}).orderNr || '';
    azRenderOrder(r.order);
  } catch (e) {
    $('azStatus').textContent = 'Ошибка: ' + e.message;
    btn.disabled = false;
    btn.textContent = '💳 Оформить заказ';
  }
}

function azRenderOrder(o) {
  azRender(`
    <div class="db-toolbar">
      <button class="backlink" onclick="az.backToCart()">‹ Назад к корзине</button>
      <span class="db-count">Заказ создан</span>
    </div>
    <div class="hint">Номер заказа: <b>${esc(o.orderNr || az.orderNr || '—')}</b></div>
    <div class="db-toolbar" style="margin-top:12px">
      <button class="btn btn-primary" id="azTrackBtn">🏦 Показать QR / статус оплаты</button>
    </div>
    <div id="azTrackBox" style="margin-top:12px"></div>
    <details style="margin-top:8px"><summary class="db-mut">Сырой ответ заказа</summary>
      <pre class="db-mut" style="white-space:pre-wrap;word-break:break-all;font-size:11px">${esc(JSON.stringify(o, null, 2))}</pre>
    </details>`);
  $('azTrackBtn').addEventListener('click', azTracking);
}

async function azTracking() {
  const oid = az.orderNr;
  if (!oid) { alert('Нет номера заказа'); return; }
  const box = $('azTrackBox');
  if (!box) return;
  box.innerHTML = '<div class="hint">Запрашиваю статус оплаты и QR…</div>';
  try {
    const r = await api(`/api/eda/autozakaz/${encodeURIComponent(az.account)}/order/${encodeURIComponent(oid)}/qr`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    const q = r.qr || {};
    const pay = q.payment || {};
    const status = pay.status || '';
    const out = [];
    out.push(`<div class="chk-block"><h3>Статус оплаты: ${esc(status) || '—'}</h3>`);
    if (q.qr_url) {
      out.push(`<div style="margin:8px 0">${azQrSvg(q.qr_url)}</div>`);
      out.push(`<div class="db-mut" style="word-break:break-all">Содержимое QR: ${esc(q.qr_url)}</div>`);
    }
    if (pay.error_message) out.push(`<div class="err">${esc(pay.error_message)}</div>`);
    out.push('</div>');
    if (q.purchase_token) {
      let u = `https://trust.yandex.ru/web/payment?purchase_token=${encodeURIComponent(q.purchase_token)}&template_tag=desktop%2Fform`;
      if (q.service_token) u += `&service_token=${encodeURIComponent(q.service_token)}`;
      out.push(`<div class="db-mut" style="word-break:break-all"><a href="${esc(u)}" target="_blank" rel="noopener">Открыть страницу оплаты Траста</a></div>`);
    }
    out.push(`<div class="db-mut">order_id: ${esc(q.order_id || '')}</div>`);
    out.push(`<details style="margin-top:8px"><summary class="db-mut">Сырой ответ</summary>
      <pre class="db-mut" style="white-space:pre-wrap;word-break:break-all;font-size:11px">${esc(JSON.stringify(q, null, 2))}</pre>
    </details>`);
    box.innerHTML = out.join('');
  } catch (e) {
    box.innerHTML = `<div class="err">${esc(e.message)}</div>`;
  }
}

function azQrSvg(text) {
  try {
    const qr = qrcode(0, 'M');
    qr.addData(String(text));
    qr.make();
    return qr.createSvgTag({ cellSize: 4, margin: 0 });
  } catch (e) {
    return `<div class="db-mut">Не удалось построить QR: ${esc(e.message)}</div>`;
  }
}

// helpers
az.backToPlaces = () => { az.rest = null; az.menu = null; azRenderPlaces(); };
az.backToMenu = () => { if (az.rest) azOpenMenu(az.rest); };
az.backToCart = () => azShowCart();

$('azAccount').addEventListener('change', azSelectAccount);
$('azCity').addEventListener('change', azSelectCity);
$('azAddr').addEventListener('change', azSelectAddr);
$('azSearchGo').addEventListener('click', azSearch);
$('azSearch').addEventListener('keydown', (e) => { if (e.key === 'Enter') azSearch(); });
$('azCartShow').addEventListener('click', azShowCart);
$('azCardsBtn').addEventListener('click', azCardsPanel);
$('azClear').addEventListener('click', () => {
  az = { account: az.account, city: '', addr: null, addrs: [], addrLoc: null, restaurants: [], rest: null, menu: null, cart: null, checkout: null, payment: null, addrData: null, promo: '', phone: '', orderNr: '', items: {} };
  if (az.account) azSelectAccount(); else loadAuto();
});

// ================= САМОКАТ =================
let skAccounts = [];

function switchSkTab(name) {
  document.querySelectorAll('#pane-samokat .db-tabs.sub .db-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $('pane-skAccs').classList.toggle('active', name === 'skAccs');
  $('pane-skSess').classList.toggle('active', name === 'skSess');
}
document.querySelectorAll('#pane-samokat .db-tabs.sub .db-tab').forEach(b => b.addEventListener('click', () => switchSkTab(b.dataset.tab)));

async function loadSamokat() {
  await loadSkAccounts();
  await loadSkSessions();
  fillSkAccountSelect();
}

async function loadSkAccounts() {
  try {
    skAccounts = await api('/api/samokat/accounts');
    const tb = $('skAccTable').querySelector('tbody');
    tb.innerHTML = skAccounts.map(a => `
      <tr>
        <td><b>${esc(a.name)}</b></td>
        <td>${esc((a.user && (a.user.name || a.user.email || a.user.phone)) || '—')}</td>
        <td>${a.token_ok ? '<span class="sd-badge ok">есть токен</span>' : '<span class="db-mut">нет</span>'}</td>
        <td class="num">${esc(a.added || '—')}</td>
        <td class="col-actions"><div class="row-actions">
          <button class="btn btn-ghost btn-sm" data-ref="${esc(a.name)}">Обновить</button>
          <button class="btn btn-danger btn-sm" data-del="${esc(a.name)}">Удалить</button>
        </div></td>
      </tr>`).join('') || '<tr><td colspan="5" class="db-empty">Аккаунтов Самоката нет</td></tr>';
    tb.querySelectorAll('[data-ref]').forEach(b => b.addEventListener('click', async () => {
      try {
        await api(`/api/samokat/accounts/${encodeURIComponent(b.dataset.ref)}/refresh`, { method: 'POST' });
        loadSkAccounts();
      } catch (e) { alert(e.message); }
    }));
    tb.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/samokat/accounts/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE' });
      loadSamokat();
    }));
  } catch (e) {
    $('skAccTable').querySelector('tbody').innerHTML = `<tr><td colspan="5" class="db-empty">${esc(e.message)}</td></tr>`;
  }
}

function fillSkAccountSelect() {
  const sel = $('skSessAccount');
  sel.innerHTML = '';
  skAccounts.forEach(a => {
    const o = document.createElement('option');
    o.value = a.name;
    o.textContent = a.name;
    sel.appendChild(o);
  });
}

$('skAccAdd').addEventListener('click', async () => {
  const btn = $('skAccAdd');
  btn.disabled = true;
  try {
    await api('/api/samokat/accounts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('skName').value.trim(),
        cookies: $('skCookies').value.trim(),
      }),
    });
    $('skName').value = '';
    $('skCookies').value = '';
    loadSamokat();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

$('skSmsSend').addEventListener('click', async () => {
  const btn = $('skSmsSend');
  btn.disabled = true;
  try {
    await api('/api/samokat/sms/send', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ phone: $('skPhone').value.trim() }),
    });
    alert('Код отправлен на ' + $('skPhone').value.trim());
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

$('skSmsConfirm').addEventListener('click', async () => {
  const btn = $('skSmsConfirm');
  btn.disabled = true;
  try {
    await api('/api/samokat/sms/confirm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('skName').value.trim() || 'sms',
        phone: $('skPhone').value.trim(),
        code: $('skSmsCode').value.trim(),
      }),
    });
    $('skName').value = '';
    $('skPhone').value = '';
    $('skSmsCode').value = '';
    loadSamokat();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

async function loadSkSessions() {
  try {
    const sess = await api('/api/samokat/sessions');
    const entries = Object.entries(sess).filter(([, v]) => v.active);
    const tb = $('skSessTable').querySelector('tbody');
    tb.innerHTML = entries.map(([token, s]) => `
      <tr>
        <td><b>${esc(s.name)}</b></td>
        <td><b>${esc(s.account)}</b></td>
        <td><span class="mono db-mut">${esc(location.origin + '/s/' + token)}</span></td>
        <td class="num">${esc(s.expires_at || '—')}</td>
        <td class="col-actions">
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" data-copy="${esc(location.origin + '/s/' + token)}">Копировать</button>
            <button class="btn btn-danger btn-sm" data-revoke="${token}">Отозвать</button>
          </div>
        </td>
      </tr>`).join('') || '<tr><td colspan="5" class="db-empty">Активных сессий Самоката нет</td></tr>';
    tb.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => copyText(b.dataset.copy, b)));
    tb.querySelectorAll('[data-revoke]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/samokat/sessions/${b.dataset.revoke}`, { method: 'DELETE' });
      loadSkSessions();
    }));
  } catch (e) {
    $('skSessTable').querySelector('tbody').innerHTML = `<tr><td colspan="5" class="db-empty">${esc(e.message)}</td></tr>`;
  }
}

$('skSessCreate').addEventListener('click', async () => {
  const btn = $('skSessCreate');
  btn.disabled = true;
  try {
    const r = await api('/api/samokat/sessions', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: $('skSessName').value.trim(),
        account: $('skSessAccount').value,
        hours: parseInt($('skSessHours').value, 10) || 24,
      }),
    });
    $('skSessName').value = '';
    copyText(r.link, btn);
    loadSkSessions();
  } catch (e) {
    alert(e.message);
  } finally {
    btn.disabled = false;
  }
});

// ================= logs modal =================
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
    } catch (e) { /* ignore */ }
  }, 1500);
}

$('logsClose').addEventListener('click', () => {
  $('modalLogs').classList.add('hidden');
  clearInterval(logPoller);
  activeLogsName = null;
});

// ================= prizes modal (per account) =================
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
$('prizesClose').addEventListener('click', () => $('modalPrizes').classList.add('hidden'));

function renderPrizes(prizes, box) {
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
          <span class="sd-badge ${p.display_type === 'postcard' ? '' : 'ok'}">${prizeCat(p.display_type)}</span>
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

// ================= session detail modal =================
$('sessClose').addEventListener('click', () => $('modalSess').classList.add('hidden'));
$('modalSess').addEventListener('click', (e) => { if (e.target === $('modalSess')) $('modalSess').classList.add('hidden'); });

const MODE_LABELS = { both: 'Самовывоз + доставка', pickup: 'Самовывоз', delivery: 'Доставка', card: 'Моя карта' };
function modeBadge(mode) {
  const m = (mode || 'both');
  return `<span class="mode-badge">${esc(MODE_LABELS[m] || m)}</span>`;
}

function statusBadge(code) {
  const map = {
    'NEW': 'ok', 'ASSEMBLING': 'ok', 'ON_ASSEMBLE': 'ok', 'READY': 'ok', 'WAITING': 'ok',
    'DELIVERED': 'ok', 'PICKED_UP': 'ok', 'DONE': 'ok',
    'CANCELED': 'bad', 'CANCELED_NO_PAY': 'bad', 'CANCELED_BY_USER': 'bad', 'FAILED': 'bad',
  };
  const cls = map[code] || 'warn';
  return `<span class="sd-badge ${cls}">${esc(code)}</span>`;
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
    <h2>${esc(s.name)} <span class="session-account">${esc(s.account)}</span> ${modeBadge(s.mode)}</h2>
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

// ================= add account modal =================
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
    loadAdminAccounts();
    loadOverview();
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
    loadAdminAccounts();
    loadOverview();
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

// ================= чекер промокодов Я.Еды =================
function promoBadges(codes) {
  if (!codes || !codes.length) return '<span class="db-mut">—</span>';
  return codes.map(c => `<span class="sd-badge ok">${esc(c)}</span>`).join(' ');
}

async function runEdaPromos() {
  const btn = $('edaPromoRun');
  const tb = $('edaPromoTable').querySelector('tbody');
  const prog = $('edaPromoProgress');
  btn.disabled = true;
  tb.innerHTML = '<tr><td colspan="3" class="db-empty">Проверяю все аккаунты Я.Еды…</td></tr>';
  $('edaPromoCount').textContent = '';
  try {
    const { task_id } = await api('/api/eda/promos', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    prog.classList.remove('hidden');
    const render = (st) => {
      $('edaPromoFill').style.width = `${st.progress || 0}%`;
      $('edaPromoMsg').textContent = `${st.progress || 0}% — ${st.message || ''}`;
      tb.innerHTML = `<tr><td colspan="3" class="db-empty">${esc(st.message || '')} (${st.progress || 0}%)</td></tr>`;
    };
    for (;;) {
      const st = await api(`/api/eda/promos/${task_id}`);
      render(st);
      if (st.state === 'done' || st.state === 'error') break;
      await new Promise(r => setTimeout(r, 1500));
    }
    const st = await api(`/api/eda/promos/${task_id}`);
    prog.classList.add('hidden');
    const rows = st.result || [];
    tb.innerHTML = rows.map(r => `
      <tr>
        <td><b>${esc(r.name)}</b></td>
        <td>${promoBadges(r.codes || [])}</td>
        <td class="db-mut">${esc(r.error || '')}</td>
      </tr>`).join('') || '<tr><td colspan="3" class="db-empty">Аккаунтов Я.Еды нет</td></tr>';
    $('edaPromoCount').textContent = `аккаунтов: ${rows.length}`;
  } catch (e) {
    prog.classList.add('hidden');
    tb.innerHTML = `<tr><td colspan="3" class="db-empty">${esc(e.message)}</td></tr>`;
  } finally {
    btn.disabled = false;
  }
}

$('edaPromoRun').addEventListener('click', runEdaPromos);

// ================= «Свои Плюсы»: ежедневные подарки =================
async function runSpDaily() {
  const btn = $('spRun');
  const tb = $('spTable').querySelector('tbody');
  const prog = $('spProgress');
  btn.disabled = true;
  tb.innerHTML = '<tr><td colspan="5" class="db-empty">Собираю подарки «Свои Плюсы»…</td></tr>';
  $('spCount').textContent = '';
  try {
    const { task_id } = await api('/api/sp/daily', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ claim: $('spClaim').checked }),
    });
    prog.classList.remove('hidden');
    const render = (st) => {
      $('spFill').style.width = `${st.progress || 0}%`;
      $('spMsg').textContent = `${st.progress || 0}% — ${st.message || ''}`;
    };
    for (;;) {
      const st = await api(`/api/sp/daily/${task_id}`);
      render(st);
      if (st.state === 'done' || st.state === 'error') break;
      await new Promise(r => setTimeout(r, 1500));
    }
    const st = await api(`/api/sp/daily/${task_id}`);
    prog.classList.add('hidden');
    const rows = st.result || [];
    const cells = [];
    rows.forEach(r => {
      (r.rewards || []).forEach(rw => {
        const opts = (rw.options || []).map(o =>
          `<span class="sd-badge">${esc(o.service_name || o.title || o.id || '')}</span>`).join(' ');
        cells.push(`
          <tr>
            <td><b>${esc(r.name)}</b></td>
            <td>${esc(rw.title || rw.reward_id)}${opts ? `<div class="db-mut" style="margin-top:4px">${opts}</div>` : ''}</td>
            <td>${rw.error ? `<span class="sd-badge bad">${esc(rw.error)}</span>` : (rw.status === 'ACTIVATED' ? '<span class="sd-badge ok">активирован</span>' : esc(rw.status || ''))}</td>
            <td>${rw.promocode ? `<span class="sd-badge ok">${esc(rw.promocode)}</span>` : '<span class="db-mut">—</span>'}</td>
            <td>${fmtDate(rw.expires_at)}</td>
          </tr>`);
      });
      if (!r.rewards || !r.rewards.length) {
        cells.push(`<tr><td><b>${esc(r.name)}</b></td><td colspan="4" class="db-mut">${esc(r.error || 'подарков нет')}</td></tr>`);
      }
    });
    tb.innerHTML = cells.join('') || '<tr><td colspan="5" class="db-empty">Аккаунтов с Session_id нет</td></tr>';
    $('spCount').textContent = `подарков: ${cells.length}`;
    loadSpGifts();
  } catch (e) {
    prog.classList.add('hidden');
    tb.innerHTML = `<tr><td colspan="5" class="db-empty">${esc(e.message)}</td></tr>`;
  } finally {
    btn.disabled = false;
  }
}

async function loadSpGifts() {
  try {
    const gifts = await api('/api/sp/gifts');
    const tb = $('spGiftTable').querySelector('tbody');
    tb.innerHTML = gifts.slice().reverse().map(g => `
      <tr>
        <td><b>${esc(g.account)}</b></td>
        <td>${esc(g.title || g.reward_id)}</td>
        <td>${g.error ? `<span class="sd-badge bad">${esc(g.error)}</span>` : (g.status === 'ACTIVATED' ? '<span class="sd-badge ok">активирован</span>' : esc(g.status || ''))}</td>
        <td>${g.promocode ? `<span class="sd-badge ok">${esc(g.promocode)}</span>` : '<span class="db-mut">—</span>'}</td>
        <td>${fmtDate(g.expires_at)}</td>
        <td class="num">${esc(g.collected_at || '')}</td>
      </tr>`).join('') || '<tr><td colspan="6" class="db-empty">Пока ничего не собрано</td></tr>';
  } catch (e) { /* ignore */ }
}

function spCsv() {
  const rows = [['Аккаунт', 'Подарок', 'Статус', 'Промокод', 'Действует до', 'Получен']];
  $('spGiftTable').querySelectorAll('tbody tr').forEach(tr => {
    rows.push(Array.from(tr.children).map(td => td.textContent.trim().replace(/\s+/g, ' ')));
  });
  const csv = rows.map(r => r.map(c => `"${c.replace(/"/g, '""')}"`).join(';')).join('\r\n');
  const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'sp_gifts.csv';
  a.click();
}

$('spRun').addEventListener('click', runSpDaily);
$('spCsv').addEventListener('click', spCsv);
loadSpGifts();

// ================= «Свои Плюсы»: Колесо Фортуны =================
async function runSpWheel() {
  const btn = $('spWheelRun');
  const tb = $('spWheelTable').querySelector('tbody');
  const prog = $('spWheelProgress');
  btn.disabled = true;
  tb.innerHTML = '<tr><td colspan="5" class="db-empty">Кручу колесо…</td></tr>';
  $('spWheelCount').textContent = '';
  try {
    const { task_id } = await api('/api/sp/wheel', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ spin: $('spWheelSpin').checked }),
    });
    prog.classList.remove('hidden');
    const render = (st) => {
      $('spWheelFill').style.width = `${st.progress || 0}%`;
      $('spWheelMsg').textContent = `${st.progress || 0}% — ${st.message || ''}`;
    };
    for (;;) {
      const st = await api(`/api/sp/wheel/${task_id}`);
      render(st);
      if (st.state === 'done' || st.state === 'error') break;
      await new Promise(r => setTimeout(r, 1500));
    }
    const st = await api(`/api/sp/wheel/${task_id}`);
    prog.classList.add('hidden');
    const rows = st.result || [];
    const cells = [];
    rows.forEach(r => {
      (r.results || []).forEach(rw => {
        const pr = rw.prize || {};
        const prizeText = pr.title ? `${pr.title}${pr.cashback ? ` · ${pr.cashback}` : ''}` : '—';
        const desc = pr.description ? `<div class="db-mut" style="margin-top:4px">${esc(pr.description)}</div>` : '';
        cells.push(`
          <tr>
            <td><b>${esc(r.name)}</b></td>
            <td>${esc(prizeText)}${desc}</td>
            <td>${esc(pr.cashback || '—')}</td>
            <td>${rw.error ? `<span class="sd-badge bad">${esc(rw.error)}</span>`
              : (rw.spun ? '<span class="sd-badge ok">кручено</span>'
                : (rw.prize ? '<span class="sd-badge ok">уже кручено</span>' : esc(rw.status || '')))}</td>
            <td>${fmtDate(rw.endDate)}</td>
          </tr>`);
      });
      if (!r.results || !r.results.length) {
        cells.push(`<tr><td><b>${esc(r.name)}</b></td><td colspan="4" class="db-mut">${esc(r.error || 'нет данных')}</td></tr>`);
      }
    });
    tb.innerHTML = cells.join('') || '<tr><td colspan="5" class="db-empty">Аккаунтов с Session_id нет</td></tr>';
    $('spWheelCount').textContent = `результатов: ${cells.length}`;
  } catch (e) {
    prog.classList.add('hidden');
    tb.innerHTML = `<tr><td colspan="5" class="db-empty">${esc(e.message)}</td></tr>`;
  } finally {
    btn.disabled = false;
  }
}

$('spWheelRun').addEventListener('click', runSpWheel);

// ================= Market =================

function switchMktTab(name) {
  document.querySelectorAll('#pane-market .db-tabs.sub .db-tab').forEach(b => b.classList.toggle('active', b.dataset.tab === name));
  $('pane-mktWow').classList.toggle('active', name === 'mktWow');
}
document.querySelectorAll('#pane-market .db-tabs.sub .db-tab').forEach(b => b.addEventListener('click', () => switchMktTab(b.dataset.tab)));

function renderMktWowResults(r) {
  const tb = $('mktWowTable').querySelector('tbody');
  const available = r.available || {};
  const entries = Object.entries(available);
  tb.innerHTML = entries.map(([name, result]) => {
    const warmupAt = result.warmup_at || result.promo_ready_at;
    const readyIn = result.promo_ready_at ? Math.max(0, result.promo_ready_at - Date.now() / 1000) : null;
    const warmupInfo = readyIn > 0
      ? `<span class="sd-badge warn">Прогрев ${Math.ceil(readyIn / 60)} мин</span>`
      : (warmupAt ? `<span class="sd-badge ok">Прогрет</span>` : `<span class="sd-badge warn">Не прогрет</span>`);
    return `
      <tr>
        <td><b>${esc(name)}</b></td>
        <td><span class="sd-badge ok">✅ Акция за 1₽ доступна</span></td>
        <td>${warmupInfo}</td>
        <td class="col-actions">
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" data-mkt-warmup="${esc(name)}">🔥 Прогреть</button>
          </div>
        </td>
      </tr>`;
  }).join('') || '<tr><td colspan="4" class="db-empty">Нет аккаунтов с доступными акциями</td></tr>';
  $('mktWowCount').textContent = `найдено: ${entries.length} из ${r.total_scanned || 0}`;
  tb.querySelectorAll('[data-mkt-warmup]').forEach(b => b.addEventListener('click', async () => {
    const name = b.dataset.mktWarmup;
    b.disabled = true;
    b.textContent = 'Прогреваем…';
    try {
      await api('/api/eda/warmup', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ names: [name] }) });
      b.textContent = '🔥 Прогрето';
      setTimeout(() => loadMarketWowOffers(), 1500);
    } catch (e) {
      b.textContent = 'Ошибка';
      $('mktWowResults').innerHTML = `<div class="db-empty">${esc(e.message)}</div>`;
    }
  }));
}

function initMarketWow() {
  $('mktWowResults').innerHTML = '<div class="db-empty">Нажмите «Сканировать все аккаунты», чтобы проверить акции за 1₽</div>';
  $('mktWowTable').querySelector('tbody').innerHTML = '<tr><td colspan="4" class="db-empty">Результаты появятся после сканирования</td></tr>';
  $('mktWowCount').textContent = '';
}

async function loadMarketWowOffers() {
  const btn = $('mktWowScan');
  const prog = $('mktWowResults');
  btn.disabled = true;
  prog.innerHTML = '<div class="progress-bar"><div class="progress-fill" style="width:100%"></div></div>';
  try {
    const r = await api('/api/market/wow-offers', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}',
    });
    const taskId = r.task_id;
    const poll = setInterval(async () => {
      try {
        const st = await api(`/api/market/wow-offers/status/${taskId}`);
        const pct = st.progress || 0;
        prog.innerHTML =
          `<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>` +
          `<div class="db-mut" style="margin-top:6px">${esc(st.message || '')}</div>` +
          `<pre class="mkt-log">${(st.log || []).map(l => `[${esc(l.t)}] ${esc(l.msg)}`).join('\n')}</pre>`;
        if (st.state === 'done') {
          clearInterval(poll);
          btn.disabled = false;
          renderMktWowResults(st.result || {});
        } else if (st.state === 'error') {
          clearInterval(poll);
          btn.disabled = false;
          prog.innerHTML = `<div class="db-empty">${esc(st.message || 'Ошибка сканирования')}</div>`;
        }
      } catch (e) {
        clearInterval(poll);
        btn.disabled = false;
        prog.innerHTML = `<div class="db-empty">${esc(e.message)}</div>`;
      }
    }, 1500);
  } catch (e) {
    prog.innerHTML = `<div class="db-empty">${esc(e.message)}</div>`;
    btn.disabled = false;
  }
}

$('mktWowScan').addEventListener('click', loadMarketWowOffers);

async function loadMarketReviews() {
  const btn = $('mktReviewBtn');
  const prog = $('mktWowResults');
  const logEl = $('mktReviewLog');
  const text = $('mktReviewText').value.trim();
  const grade = parseInt($('mktReviewGrade').value, 10) || 5;
  btn.disabled = true;
  logEl.style.display = 'block';
  logEl.textContent = '';
  prog.innerHTML = '<div class="progress-bar"><div class="progress-fill" style="width:100%"></div></div>';
  try {
    const r = await api('/api/market/reviews', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text || undefined, grade }),
    });
    const taskId = r.task_id;
    const poll = setInterval(async () => {
      try {
        const st = await api(`/api/market/reviews/status/${taskId}`);
        const pct = st.progress || 0;
        prog.innerHTML =
          `<div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>` +
          `<div class="db-mut" style="margin-top:6px">${esc(st.message || '')}</div>`;
        logEl.textContent = (st.log || []).map(l => `[${l.t}] ${l.msg}`).join('\n');
        if (st.state === 'done') {
          clearInterval(poll);
          btn.disabled = false;
          renderMktReviewResults(st.result || {});
        } else if (st.state === 'error') {
          clearInterval(poll);
          btn.disabled = false;
          prog.innerHTML = `<div class="db-empty">${esc(st.message || 'Ошибка отправки отзывов')}</div>`;
        }
      } catch (e) {
        clearInterval(poll);
        btn.disabled = false;
        prog.innerHTML = `<div class="db-empty">${esc(e.message)}</div>`;
      }
    }, 1500);
  } catch (e) {
    prog.innerHTML = `<div class="db-empty">${esc(e.message)}</div>`;
    btn.disabled = false;
  }
}

function renderMktReviewResults(r) {
  const results = r.results || {};
  const names = Object.keys(results);
  if (names.length === 0) {
    $('mktWowResults').innerHTML = '<div class="db-empty">Нет результатов</div>';
    return;
  }
  const rows = names.map(name => {
    const res = results[name];
    const revs = res.reviews || [];
    const count = res.reviewed_count || 0;
    const detail = revs.map(rv => {
      if (rv.error) return `<div class="db-error">ошибка: ${esc(rv.error)}</div>`;
      if (rv.dry_run) return `<div class="db-mut">найдено задание (dry run): sku ${esc((rv.data||{}).sku || '')}</div>`;
      return `<div class="db-mut">отзыв ${rv.review_id ? '#' + rv.review_id : 'не сохранён'}: sku ${esc((rv.data||{}).sku || '')}</div>`;
    }).join('');
    const status = count ? `<span class="badge badge-ok">${count} отзыв(ов)</span>` : '<span class="badge badge-mut">нет</span>';
    return `<tr><td>${esc(name)}</td><td>${status}</td><td>${detail}</td></tr>`;
  }).join('');
  $('mktWowTable').querySelector('tbody').innerHTML = rows;
  $('mktWowCount').textContent = `отзывов оставлено: ${r.reviewed_count || 0} из ${r.total || 0} аккаунтов`;
  $('mktWowResults').innerHTML = '';
}

$('mktReviewBtn').addEventListener('click', loadMarketReviews);

$('mktWowScanUrl').addEventListener('click', async () => {
  const btn = $('mktWowScanUrl');
  const url = $('mktWowUrl').value.trim();
  const prog = $('mktWowResults');
  btn.disabled = true;
  prog.innerHTML = '<div class="progress-bar"><div class="progress-fill" style="width:100%"></div></div>';
  try {
    // Получаем список аккаунтов
    const accs = await api('/api/market/accounts');
    const accounts = accs.accounts || [];
    if (accounts.length === 0) {
      prog.innerHTML = '<div class="db-empty">Нет аккаунтов Маркета</div>';
      return;
    }
    // Сканируем каждый аккаунт
    let html = '<h3>Результаты сканирования</h3>';
    for (const acc of accounts) {
      try {
        const r = await api('/api/market/wow-offers/scan', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account: acc.name, url: url || undefined }),
        });
        html += `<div class="card"><h4>${esc(acc.name)}</h4><pre>${JSON.stringify(r.results, null, 2)}</pre></div>`;
      } catch (e) {
        html += `<div class="card"><h4>${esc(acc.name)}</h4><p class="error">${esc(e.message)}</p></div>`;
      }
    }
    prog.innerHTML = html;
  } catch (e) {
    prog.innerHTML = `<div class="db-empty">${esc(e.message)}</div>`;
  } finally {
    btn.disabled = false;
  }
});

// ================= boot =================
async function boot() {
  loadOverview();
  loadAdminAccounts();
  loadEda();
  try {
    accounts = await api('/api/accounts');
  } catch (e) { /* ignore */ }
}
boot();
setInterval(() => {
  loadOverview();
  const active = document.querySelector('#dbTabs .db-tab.active');
  if (active && active.dataset.tab === 'accounts') loadAdminAccounts();
}, 15000);

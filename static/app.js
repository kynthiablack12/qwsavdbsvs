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
    prizes: loadPrizes, sessions: loadSessions, eda: loadEda, samokat: loadSamokat };
  if (loaders[b.dataset.tab]) loaders[b.dataset.tab]();
}));

$('btnRefresh').addEventListener('click', () => {
  const active = document.querySelector('#dbTabs .db-tab.active');
  const loaders = { accounts: loadAdminAccounts, purchases: loadPurchases, coupons: loadCoupons,
    prizes: loadPrizes, sessions: loadSessions, eda: loadEda, samokat: loadSamokat };
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
    const pz = games['wX8CoYBu0OQzsA6DBwqlU'] || {};
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
    const attemptsCell = `${attempts} <span class="db-mut">(П:${pz.attempts ?? '?'} М:${mn.attempts ?? '?'})</span>`;
    return `<tr>
      <td><div class="acc-cell"><b>${esc(a.name)}</b><div class="db-mut mono">${esc(a.device_id || '')}</div>${err}</div></td>
      <td><select class="game-select db-game" data-name="${esc(a.name)}" data-cur="${esc(a.event_id)}">
        <option value="wX8CoYBu0OQzsA6DBwqlU"${a.event_id !== 'At99RuZXsCpnFRhpmEZCK' ? ' selected' : ''}>Призолето</option>
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
  downloadCSV('accounts.csv', adminAccounts.map(a => [a.name, a.event_id === 'At99RuZXsCpnFRhpmEZCK' ? 'Монстро' : 'Призолето', a.device_id, a.error || '', a.balance ?? '', a.prizes ?? 0]));
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
          <div class="session-name">${esc(s.name)} <span class="session-account">${esc(s.account)}</span></div>
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
        <td class="num">${a.orders != null ? esc(String(a.orders)) : '<span class="db-mut">—</span>'}</td>
        <td class="num">${esc(a.added || '—')}</td>
        <td class="col-actions"><button class="btn btn-danger btn-sm" data-del="${esc(a.name)}">Удалить</button></td>
      </tr>`).join('') || '<tr><td colspan="9" class="db-empty">Аккаунтов Я.Еды нет</td></tr>';
    tb.querySelectorAll('[data-del]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/eda/accounts/${encodeURIComponent(b.dataset.del)}`, { method: 'DELETE' });
      loadEda();
    }));
  } catch (e) {
    $('edaAccTable').querySelector('tbody').innerHTML = `<tr><td colspan="9" class="db-empty">${esc(e.message)}</td></tr>`;
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

async function loadEdaSessions() {
  try {
    const sess = await api('/api/eda/sessions');
    const entries = Object.entries(sess).filter(([, v]) => v.active);
    const tb = $('edaSessTable').querySelector('tbody');
    tb.innerHTML = entries.map(([token, s]) => `
      <tr>
        <td><b>${esc(s.name)}</b></td>
        <td><b>${esc(s.account)}</b></td>
        <td><span class="mono db-mut">${esc(location.origin + '/d/' + token)}</span></td>
        <td class="num">${esc(s.expires_at || '—')}</td>
        <td class="col-actions">
          <div class="row-actions">
            <button class="btn btn-ghost btn-sm" data-copy="${esc(location.origin + '/d/' + token)}">Копировать</button>
            <button class="btn btn-danger btn-sm" data-revoke="${token}">Отозвать</button>
          </div>
        </td>
      </tr>`).join('') || '<tr><td colspan="5" class="db-empty">Активных сессий Еды нет</td></tr>';
    tb.querySelectorAll('[data-copy]').forEach(b => b.addEventListener('click', () => copyText(b.dataset.copy, b)));
    tb.querySelectorAll('[data-revoke]').forEach(b => b.addEventListener('click', async () => {
      await api(`/api/eda/sessions/${b.dataset.revoke}`, { method: 'DELETE' });
      loadEdaSessions();
    }));
  } catch (e) {
    $('edaSessTable').querySelector('tbody').innerHTML = `<tr><td colspan="5" class="db-empty">${esc(e.message)}</td></tr>`;
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

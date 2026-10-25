// HTTPS-адрес твоего Render, БЕЗ / в конце.
const API_BASE = 'https://telegram-miniapp-i49m.onrender.com';
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const $ = id => document.getElementById(id);
const fmt = n => Number(n ?? 0).toLocaleString('ru-RU');
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const AVATARS = ['🏠','🔨','👷','🏗️','🦾','👑','🐱','🚀'];
let S = null, tab = 'home', game = null, adm = null, plist = [], busy = false, tapN = 0, tapT = null;

function note(m) { const s = $('status'); s.textContent = m; clearTimeout(note.t); note.t = setTimeout(() => s.textContent = '', 4500); }

async function api(path, body) {
  if (!tg?.initData) throw new Error('Открой приложение кнопкой «Открыть» в Telegram, а не в браузере.');
  let r;
  try {
    r = await fetch(API_BASE + path, { method: body === undefined ? 'GET' : 'POST',
      headers: { 'X-Telegram-Init-Data': tg.initData, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body) });
  } catch (_) { throw new Error('Нет связи с сервером (Render мог уснуть — подожди минуту и повтори).'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `Ошибка сервера ${r.status}`);
  return j;
}
async function run(fn) { try { await fn(); } catch (e) { note('⚠️ ' + e.message); } }

// ---------- дом (SVG растёт с уровнем)
function houseSvg(lv) {
  const hue = [200, 170, 140, 100, 50, 30, 330, 290, 260, 190][lv - 1];
  const floors = Math.min(1 + Math.ceil(lv / 2), 6), fh = 34, w = 120 + lv * 6, x = (260 - w) / 2;
  const top = 250 - floors * fh; let o = '';
  for (let f = 0; f < floors; f++) {
    const y = 250 - (f + 1) * fh;
    o += `<rect x="${x}" y="${y}" width="${w}" height="${fh}" fill="hsl(${hue} 70% ${52 - f * 2}%)" stroke="#0006"/>`;
    for (let k = 0; k < 2 + Math.floor(lv / 3); k++) o += `<rect x="${x + 14 + k * ((w - 28) / (1 + Math.floor(lv / 3) + 1.4))}" y="${y + 8}" width="14" height="18" rx="2" fill="#ffe27a"/>`;
  }
  o += `<polygon points="${x - 10},${top} ${130},${top - 38 - lv * 3} ${x + w + 10},${top}" fill="hsl(${hue + 40} 80% 40%)"/>`;
  o += `<rect x="116" y="${250 - 30}" width="28" height="30" rx="3" fill="#2a1250"/>`;
  if (lv >= 5) o += `<rect x="${x + w - 24}" y="${top - 52 - lv * 2}" width="12" height="30" fill="#8a8aff"/>`;
  if (lv >= 8) o += `<circle cx="130" cy="${top - 56 - lv * 3}" r="8" fill="#ffd400"/>`;
  return `<svg viewBox="0 0 260 270">${o}<rect x="10" y="250" width="240" height="8" rx="4" fill="#48ff9b88"/></svg>`;
}

// ---------- отрисовка
function paint() {
  if (!S) return;
  $('coins').textContent = fmt(S.player.coins); $('gems').textContent = fmt(S.gems);
  const items = [['home','🏠','Дом'], ['games','🎮','Игры'], ['profile','👤','Профиль']];
  if (S.is_admin) items.push(['admin','🛡️','Админ']);
  $('nav').innerHTML = items.map(([k, i, t]) => `<button class="${k === tab ? 'on' : ''}" onclick="go('${k}')"><b>${i}</b>${t}</button>`).join('');
  $('view').innerHTML = { home: homeV, games: gamesV, profile: profileV, admin: adminV }[tab]();
}
function homeV() {
  const h = S.house, pct = h.level * 10;
  return `<div class="panel house">${houseSvg(h.level)}<div><span class="lvl">Уровень ${h.level} / 10</span></div><h2 style="margin-top:8px">${h.name}</h2>
   <div class="prog"><i style="width:${pct}%"></i></div><p class="m">Доход: <b>${fmt(h.income)}</b> 💰/час · копится до ${h.cap_hours} ч</p></div>
  <div class="panel"><h2>💰 Доход дома</h2><p class="m">Накоплено: <b style="color:var(--c)">${fmt(h.pending)}</b> монет</p>
   <button class="gold big" style="padding:16px" onclick="act('claim')" ${h.pending < 1 ? 'disabled' : ''}>Забрать ${fmt(h.pending)} 💰</button></div>
  <div class="panel"><h2>⬆️ Прокачка дома</h2>${h.next_cost ? `<p class="m">Уровень ${h.level + 1}: доход вырастет до <b>${fmt(h.next_income)}</b> 💰/час</p>
   <button class="big alt" style="padding:16px" onclick="act('upgrade')" ${S.player.coins < h.next_cost ? 'disabled' : ''}>Улучшить за ${fmt(h.next_cost)} 💰</button>` : '<p>👑 Максимальный уровень! Твой дом — легенда.</p>'}</div>
  <div class="panel"><h2>🎁 Ежедневный бонус</h2><button onclick="act('daily')" ${S.daily_ready ? '' : 'disabled'}>${S.daily_ready ? `Получить ${100 * h.level} 💰 + 1 💎` : 'Уже получен — приходи завтра'}</button></div>`;
}
function gamesV() {
  const cells = Array.from({length: 25}, (_, i) => { const c = game?.cells[i] || {state: 'closed'};
    return `<button class="cell ${c.state === 'closed' ? '' : c.state}" onclick="openCell(${i})" ${busy || c.state !== 'closed' || game?.status !== 'playing' ? 'disabled' : ''}>${c.state === 'mine' ? '💣' : c.state === 'safe' ? (c.around || '✓') : '◆'}</button>`; }).join('');
  const msg = !game ? 'Нажми «Новая игра»' : game.status === 'playing' ? `Открыто ${game.opened} из 20` : game.status === 'won' ? '🏆 Победа! +50 💰' : '💣 Мина! Попробуй ещё';
  return `<div class="panel"><h2>🔨 Стройка (кликер)</h2><p class="m">Каждый тап = ${1 + S.house.level} 💰. Энергия: ${S.energy}/${S.max_energy} (восстанавливается сама)</p>
   <div class="prog"><i style="width:${S.energy / S.max_energy * 100}%"></i></div><button class="big gold" onclick="tapWork()" ${S.energy < 1 ? 'disabled' : ''}>🔨 РАБОТАТЬ</button></div>
  <div class="panel"><h2>💣 Мины 5×5</h2><p class="m">5 мин. Открой все 20 безопасных клеток — получи +50 💰.</p>
   <button class="alt" onclick="newGame()" ${busy || game?.status === 'playing' ? 'disabled' : ''}>Новая игра</button><div class="grid">${cells}</div><p class="m" style="margin-top:10px">${msg}</p></div>`;
}
function profileV() {
  const p = S.player;
  return `<div class="panel" style="text-align:center"><div style="font-size:60px">${S.avatar}</div><h2>${esc(p.nickname)}</h2><p class="m">Telegram ID: ${p.telegram_id}</p></div>
  <div class="panel"><h2>📊 Статистика</h2><div class="row">${[['🏠 Дом', S.house.level + ' ур.'], ['🎮 Игр', p.games_played], ['🏆 Побед', p.games_won]].map(([a, b]) => `<span class="tag">${a}: <b>${b}</b></span>`).join('')}</div></div>
  <div class="panel"><h2>🎭 Аватар</h2><div class="row">${AVATARS.map(a => `<button class="${a === S.avatar ? '' : 'ghost'}" style="font-size:22px" onclick="setAvatar('${a}')">${a}</button>`).join('')}</div></div>
  <div class="panel"><h2>✏️ Ник</h2><div class="row"><input id="nick" maxlength="24" placeholder="Ник (пусто — имя Telegram)" value="${esc(p.custom_nickname || '')}"><button onclick="saveNick()">Сохранить</button></div></div>`;
}
function adminV() {
  if (!adm) return '<div class="panel m">Загрузка админ-панели...</div>';
  const s = adm.stats, d = adm.diag, i = adm.info;
  const kv = o => Object.entries(o).map(([k, v]) => `<div class="m">${esc(k)}: <b style="color:var(--t)">${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</b></div>`).join('');
  return `<div class="panel"><h2>📈 Статистика</h2><div class="row">${[['Игроков', s.players], ['Онлайн 24ч', s.active_24h], ['Заблок.', s.blocked], ['Монет в игре', fmt(s.coins_total)], ['💎 в игре', fmt(s.gems_total)], ['Игр', s.games_played], ['Побед', s.games_won], ['Тапов', fmt(s.taps)]].map(([a, b]) => `<span class="tag">${a}: <b>${b}</b></span>`).join('')}</div>
   <p class="m">Дома по уровням: ${esc(JSON.stringify(s.levels))}</p></div>
  <div class="panel"><h2>🩺 Диагностика</h2>${Object.entries(d).map(([k, v]) => `<div>${v ? '<span class="ok">✅</span>' : '<span class="bad">❌</span>'} ${esc(k)}</div>`).join('')}<div style="margin-top:8px">${kv(i)}</div><button class="ghost" style="margin-top:8px" onclick="loadAdmin()">🔄 Обновить</button></div>
  <div class="panel"><h2>🛠️ Управление игроком</h2><div class="row"><input id="a_id" type="number" placeholder="Telegram ID"></div>
   <div class="row" style="margin-top:8px"><input id="a_c" type="number" placeholder="Монеты (±)"><input id="a_g" type="number" placeholder="💎 (±)"></div>
   <div class="row" style="margin-top:8px"><button class="gold" onclick="doGrant()">Выдать</button></div>
   <div class="row" style="margin-top:8px"><input id="a_r" placeholder="Причина блокировки"></div>
   <div class="row" style="margin-top:8px"><button class="red" onclick="doBlock(true)">Блок</button><button class="alt" onclick="doBlock(false)">Разблок</button></div></div>
  <div class="panel"><h2>👥 Игроки</h2><div class="row"><input id="a_q" placeholder="Поиск: ID или имя"><button onclick="findPl()">Найти</button></div>
   ${plist.map(p => `<div class="pl ${p.blocked ? 'bl' : ''}" onclick="pick(${p.telegram_id})"><b>${esc(p.nickname || p.telegram_name)}</b> · ID ${p.telegram_id} ${p.blocked ? '🚫 ' + esc(p.reason || '') : ''}<br>💰 ${fmt(p.coins)} · 💎 ${fmt(p.gems)} · 🏠 ур.${p.house ?? 1} · 🎮 ${p.games_played}/${p.games_won} · 👆 ${fmt(p.taps)} · заработано ${fmt(p.earned)}<br>Был: ${p.last_seen ? new Date(p.last_seen * 1000).toLocaleString('ru-RU') : '—'} · Рег: ${new Date(p.created_at * 1000).toLocaleDateString('ru-RU')}</div>`).join('') || '<p class="m">Нет игроков</p>'}</div>`;
}

// ---------- действия
async function go(t) { tab = t; paint(); if (t === 'games') await run(async () => { game = (await api('/api/mines')).game; paint(); }); if (t === 'admin') await loadAdmin(); }
async function load() { await run(async () => { S = await api('/api/bh/state'); paint(); }); if (!S) $('view').innerHTML = `<div class="panel">⚠️ ${esc($('status').textContent)}</div>`; }
function act(k) { return run(async () => { const r = await api('/api/bh/' + k, {}); S = r; if (r.got) note(`+${fmt(r.got)} 💰`); if (k === 'upgrade') note('🎉 Дом улучшен!'); paint(); }); }
function tapWork() { tapN++; S.energy = Math.max(0, S.energy - 1); S.player.coins += 1 + S.house.level; paint(); clearTimeout(tapT);
  tapT = setTimeout(() => run(async () => { const n = tapN; tapN = 0; S = await api('/api/bh/tap', {n}); paint(); }), 350); }
function newGame() { busy = true; return run(async () => { const r = await api('/api/mines/new', {}); game = r.game; }).finally(() => { busy = false; paint(); }); }
function openCell(i) { if (busy) return; busy = true; return run(async () => { const r = await api('/api/mines/open', {cell: i}); game = r.game; S.player = r.player; if (r.game.status === 'won') note('🏆 +50 💰'); }).finally(() => { busy = false; paint(); }); }
function setAvatar(a) { return run(async () => { S = await api('/api/bh/avatar', {avatar: a}); paint(); }); }
function saveNick() { return run(async () => { const r = await api('/api/nickname', {nickname: $('nick').value}); S.player = r.player; note('✅ Ник сохранён'); paint(); }); }
function loadAdmin() { return run(async () => { adm = await api('/api/admin/stats'); plist = (await api('/api/admin/players')).players; paint(); }); }
function findPl() { const q = $('a_q').value; return run(async () => { plist = (await api('/api/admin/players?q=' + encodeURIComponent(q))).players; paint(); $('a_q').value = q; }); }
function pick(id) { $('a_id').value = id; $('a_id').scrollIntoView({behavior: 'smooth', block: 'center'}); }
function doGrant() { return run(async () => { const id = +$('a_id').value; if (!id) throw new Error('Укажи ID'); await api('/api/admin/grant', {telegram_id: id, coins: +$('a_c').value || 0, gems: +$('a_g').value || 0}); note('✅ Выдано'); await loadAdmin(); }); }
function doBlock(b) { return run(async () => { const id = +$('a_id').value; if (!id) throw new Error('Укажи ID'); await api('/api/admin/block', {telegram_id: id, blocked: b, reason: $('a_r').value}); note(b ? '🚫 Заблокирован' : '✅ Разблокирован'); await loadAdmin(); }); }

load();
setInterval(() => { if (S && tab === 'home') { S.house.pending = Math.min(S.house.pending + Math.round(S.house.income / 3600 * 5), S.house.income * S.house.cap_hours); paint(); } }, 5000);
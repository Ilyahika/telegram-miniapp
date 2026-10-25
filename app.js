// HTTPS-адрес твоего Render, БЕЗ / в конце.
const API_BASE = 'https://telegram-miniapp-i49m.onrender.com';
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const $ = id => document.getElementById(id);
const fmt = n => Number(n ?? 0).toLocaleString('ru-RU');
const inf = n => n >= 1e14 ? '∞' : fmt(n);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const AV = ['🏠','🔨','👷','🏗️','🦾','👑','🐱','🚀'], BETS = [200,500,1000,3000,5000,10000,50000];
let S = null, tab = 'home', sub = null, game = null, cfg = {bet: 200, m: 3}, gar = null, drop = null, top = null, topBy = 'house', adm = null, plist = [], busy = false, tapN = 0, tapT;

const note = m => { const s = $('status'); s.textContent = m; clearTimeout(note.t); note.t = setTimeout(() => s.textContent = '', 4500); };
async function api(path, body) {
  if (!tg?.initData) throw new Error('Открой приложение кнопкой «Открыть» в Telegram, а не в браузере.');
  let r;
  try { r = await fetch(API_BASE + path, {method: body === undefined ? 'GET' : 'POST', headers: {'X-Telegram-Init-Data': tg.initData, 'Content-Type': 'application/json'}, body: body === undefined ? undefined : JSON.stringify(body)}); }
  catch (_) { throw new Error('Нет связи с сервером (Render мог уснуть — подожди минуту).'); }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `Ошибка сервера ${r.status}`);
  return j;
}
const run = async fn => { try { return await fn(); } catch (e) { note('⚠️ ' + e.message); } };
const setS = r => { S = r; S.t0 = Date.now(); if (r.game !== undefined) game = r.game; };
const post = (p, b = {}) => run(async () => { const r = await api('/api/bh/' + p, b); setS(r); paint(); return r; });
const mult = (k, m) => { let p = .97; for (let i = 0; i < k; i++) p *= (25 - i) / (25 - m - i); return Math.round(p * 100) / 100; };

// ---------- дома: 5 архитектурных эпох
function houseSvg(lv) {
  const t = Math.ceil(lv / 6), P = [['#c9a26b','#8a3b2a','#ffe9a8'],['#e6dccb','#9b3a3a','#ffe27a'],['#8fa9c9','#2d3e5c','#e8f4ff'],['#7e8aa0','#171c2b','#59d0ff'],['#b48cff','#2a1560','#7ff0ff']][t - 1];
  const fl = Math.min(1 + Math.ceil(lv / 3), 11), fh = fl > 7 ? 20 : 26, w = 96 + Math.min(lv, 14) * 6, x = 150 - w / 2, top = 262 - fl * fh;
  const cols = 2 + Math.min(3, Math.floor(lv / 6)); let o = `<defs><linearGradient id="sk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${t > 3 ? '#0b0630' : '#2a1d6e'}"/><stop offset="1" stop-color="#ff7ad9"/></linearGradient></defs><rect width="300" height="290" rx="22" fill="url(#sk)"/>`;
  for (let i = 0; i < 18; i++) o += `<circle cx="${(i * 97) % 290 + 5}" cy="${(i * 53) % 120 + 8}" r="${i % 3 ? 1 : 1.8}" fill="#fff" opacity=".8"/>`;
  o += `<circle cx="245" cy="48" r="20" fill="${t > 3 ? '#7ff0ff' : '#fff3b0'}" opacity=".9"/>`;
  if (t === 5) o += `<ellipse cx="150" cy="${top - 10}" rx="${w / 2 + 40}" ry="16" fill="none" stroke="#7ff0ff" stroke-width="2" opacity=".7"/>`;
  for (let f = 0; f < fl; f++) {
    const y = 262 - (f + 1) * fh; o += `<rect x="${x}" y="${y}" width="${w}" height="${fh}" fill="${P[0]}" stroke="#0004"/>`;
    for (let c = 0; c < cols; c++) o += `<rect x="${x + 10 + c * (w - 20) / cols + 3}" y="${y + 5}" width="${(w - 20) / cols - 10}" height="${fh - 10}" rx="${t > 2 ? 1 : 3}" fill="${P[2]}" opacity="${(f * 7 + c * 3) % 5 ? 1 : .35}"/>`;
  }
  if (t < 3) o += `<polygon points="${x - 10},${top} 150,${top - 34 - lv * 2} ${x + w + 10},${top}" fill="${P[1]}"/>` + (t === 2 ? `<rect x="${x + w - 28}" y="${top - 40}" width="12" height="30" fill="#6b4a3a"/>` : '');
  else if (t === 3) o += `<rect x="${x - 6}" y="${top - 8}" width="${w + 12}" height="10" fill="${P[1]}"/><rect x="${x + 14}" y="${top - 22}" width="${w - 28}" height="14" fill="${P[0]}" stroke="#0004"/>`;
  else if (t === 4) o += `<rect x="146" y="${top - 46}" width="8" height="46" fill="#aab"/><circle cx="150" cy="${top - 48}" r="5" fill="#ff4d4d"/><rect x="${x}" y="${top - 6}" width="${w}" height="8" fill="${P[1]}"/>`;
  else o += `<path d="M${x},${top} Q150,${top - 70} ${x + w},${top}Z" fill="${P[1]}" opacity=".95"/><circle cx="150" cy="${top - 44}" r="7" fill="#ffd400"/>`;
  o += `<rect x="136" y="${262 - 24}" width="28" height="24" rx="3" fill="#1d0f3f"/><rect x="0" y="262" width="300" height="28" fill="#1b9d62"/><rect x="0" y="262" width="300" height="5" fill="#48ff9b"/>`;
  return `<svg viewBox="0 0 300 290">${o}</svg>`;
}

// ---------- отрисовка
function paint() {
  if (!S) return;
  document.body.classList.toggle('adm', tab === 'admin');
  $('coins').textContent = inf(S.player.coins); $('gems').textContent = inf(S.gems);
  const it = [['home','🏠','Дом'],['games','🎮','Игры'],['cases','📦','Кейсы'],['top','🏆','Топ'],['shop','⭐','Магазин'],['profile','👤','Я']];
  if (S.is_admin) it.push(['admin','🛡️','Админ']);
  $('nav').innerHTML = it.map(([k, i, t]) => `<button class="${k === tab ? 'on' : ''}" onclick="go('${k}')"><b>${i}</b>${t}</button>`).join('');
  $('view').innerHTML = {home: homeV, games: gamesV, cases: casesV, top: topV, shop: shopV, profile: profileV, admin: adminV}[tab]();
}
function homeV() {
  const h = S.house;
  return `<div class="panel house">${houseSvg(h.level)}<div style="margin-top:8px"><span class="lvl">Уровень ${h.level} / ${h.max}</span></div><h2 style="margin:8px 0 4px">${h.name}</h2>
   <div class="prog"><i style="width:${h.level / h.max * 100}%"></i></div><p class="m">Доход: <b>$${fmt(h.income)}</b>/час · копится до ${h.cap_hours} ч</p></div>
  <div class="panel"><h2>💵 Доход (в реальном времени)</h2><p style="font-size:30px;font-weight:900;color:var(--c);margin:4px 0">$<span id="pend">${fmt(h.pending)}</span></p>
   <button id="claim" class="gold big" style="padding:16px" onclick="claim()">Забрать</button></div>
  <div class="panel"><h2>⬆️ Прокачка</h2>${h.next_cost ? `<p class="m">Уровень ${h.level + 1}: доход $${fmt(h.next_income)}/час</p><div class="row"><button class="alt" style="flex:1;padding:15px" onclick="post('upgrade').then(r=>r&&note('🎉 Дом улучшен!'))" ${S.player.coins < h.next_cost ? 'disabled' : ''}>За $${fmt(h.next_cost)}</button><button class="gold" style="flex:1;padding:15px" onclick="go('shop')">За ⭐${h.next_stars}</button></div>` : '<p>👑 Максимальный уровень!</p>'}</div>
  <div class="cards"><div class="card" onclick="go('games')"><i>🎮</i>Играть</div><div class="card" onclick="go('cases')"><i>📦</i>Кейсы</div><div class="card" onclick="daily()"><i>🎁</i>Бонус<small>${S.daily_ready ? `$${100 * h.level} + ⭐1` : 'завтра'}</small></div><div class="card" onclick="go('top')"><i>🏆</i>Рейтинг</div></div>`;
}
function gamesV() {
  if (sub === 'work') return `<button class="ghost" onclick="sub=null;paint()">← Игры</button>` + workV();
  if (sub === 'mines') return `<button class="ghost" onclick="sub=null;paint()">← Игры</button>` + minesV();
  return `<div class="panel"><h2>🎮 Меню игр</h2><div class="cards"><div class="card" onclick="openMines()"><i>💣</i>Мины<small>ставки до $50 000, х до ∞</small></div><div class="card" onclick="sub='work';paint()"><i>🔨</i>Стройка<small>кликер, энергия</small></div><div class="card" onclick="go('cases')"><i>📦</i>Кейсы<small>выбей машину</small></div><div class="card" onclick="daily()"><i>🎁</i>Бонус<small>каждый день</small></div></div></div>`;
}
function workV() {
  return `<div class="panel"><h2>🔨 Стройка</h2><p class="m">Тап = $${1 + S.house.level}. Энергия ${S.energy}/${S.max_energy}</p><div class="prog"><i style="width:${S.energy / S.max_energy * 100}%"></i></div><button class="big gold" onclick="tapWork()" ${S.energy < 1 ? 'disabled' : ''}>🔨 РАБОТАТЬ</button></div>`;
}
function minesV() {
  const pl = game?.status === 'playing', m = cfg.m;
  const cells = game ? game.cells.map((c, i) => `<button class="cell ${c === 'closed' ? '' : c}" onclick="openCell(${i})" ${busy || c !== 'closed' || !pl ? 'disabled' : ''}>${c === 'mine' ? '💣' : c === 'safe' ? '💎' : '◆'}</button>`).join('') : '';
  const setup = pl ? '' : `<div class="panel"><h2>⚙️ Настройка</h2><p class="m">Ставка ($, минимум 200)</p><div class="row">${BETS.map(b => `<button class="chip ${cfg.bet === b ? 'on' : ''}" onclick="cfg.bet=${b};paint()">${fmt(b)}</button>`).join('')}</div>
   <p class="m" style="margin-top:12px">Мин на поле: <b id="mc">${m}</b> · коэффициент за 1-ю клетку: <b id="mm" style="color:var(--c)">x${mult(1, m)}</b></p><input type="range" min="1" max="20" value="${m}" oninput="cfg.m=+this.value;$('mc').textContent=this.value;$('mm').textContent='x'+mult(1,+this.value)" onchange="paint()">
   <button class="big alt" style="padding:16px" onclick="startMines()" ${S.player.coins < cfg.bet ? 'disabled' : ''}>Играть на $${fmt(cfg.bet)}</button><p class="m">Проигрыш — ставка сгорает. Забрать выигрыш можно после любой открытой клетки.</p></div>`;
  const info = !game ? '' : pl ? `<p>Коэф. <b style="color:var(--c)">x${game.mult}</b> · следующий x${game.next ?? '—'} · мин: ${game.mines}</p><button class="gold big" style="padding:16px" onclick="cash()">${game.opened ? `Забрать $${fmt(game.payout)}` : 'Вернуть ставку'}</button>` :
    game.status === 'lost' ? `<p class="bad">💣 Мина! Ставка $${fmt(game.bet)} сгорела.</p>` : `<p class="ok">🏆 Забрано $${fmt(game.payout)} (x${game.mult})</p>`;
  return `${setup}${game ? `<div class="panel"><h2>💣 Мины · ставка $${fmt(game.bet)}</h2>${info}<div class="grid">${cells}</div></div>` : ''}`;
}
function casesV() {
  if (!gar) return '<div class="panel m">Загрузка...</div>';
  const cs = Object.entries(gar.cases).map(([k, c]) => `<div class="panel"><div class="row"><div><h2 style="margin:0">📦 ${c.name}</h2><span class="m">${c.drops.map(d => d.name).join(' · ')}</span></div><button class="gold" style="margin-left:auto" onclick="openCase('${k}')" ${S.player.coins < c.price ? 'disabled' : ''}>$${fmt(c.price)}</button></div></div>`).join('');
  const val = gar.cars.reduce((a, c) => a + c.value, 0);
  return `${drop ? `<div class="drop"><div style="font-size:50px">🚗</div><h2>${esc(drop.name)}</h2><p>Стоит $${fmt(drop.value)}</p></div>` : ''}${cs}
  <div class="panel"><h2>🚘 Гараж (${gar.cars.length}) · $${fmt(val)}</h2>${gar.cars.map(c => `<div class="car">🚗 <b>${esc(c.name)}</b> $${fmt(c.value)}<button class="gold" onclick="sell(${c.id})">Продать</button></div>`).join('') || '<p class="m">Пусто — открой кейс!</p>'}</div>`;
}
function topV() {
  const medal = i => ['🥇', '🥈', '🥉'][i] || (i + 1) + '.';
  return `<div class="panel"><h2>🏆 Рейтинг игроков</h2><div class="row"><button class="chip ${topBy === 'house' ? 'on' : ''}" onclick="loadTop('house')">🏠 По дому</button><button class="chip ${topBy === 'coins' ? 'on' : ''}" onclick="loadTop('coins')">💵 По деньгам</button></div>
  ${top ? top.top.map((p, i) => `<div class="top ${p.id === S.player.telegram_id ? 'me' : ''}"><span>${medal(i)}</span><span>${p.avatar}</span><span>${esc(p.name)}</span><b>${topBy === 'house' ? 'ур. ' + p.house : '$' + fmt(p.coins)}</b></div>`).join('') + `<p class="m">Твоё место: ${top.me ?? '—'}</p>` : '<p class="m">Загрузка...</p>'}</div>`;
}
function shopV() {
  const h = S.house, rate = 500 * h.level;
  return `<div class="panel"><h2>⭐ Магазин</h2><p class="m">У тебя ⭐${inf(S.gems)}. Пополнение звёзд за реальные платежи пока не подключено.</p></div>
  <div class="panel"><h2>🏠 Уровень дома</h2>${h.next_stars ? `<p class="m">Сейчас ${h.level} ур. → ${h.level + 1} ур.</p><button class="gold big" style="padding:16px" onclick="post('buylevel').then(r=>r&&note('🎉 Уровень куплен!'))" ${S.gems < h.next_stars ? 'disabled' : ''}>Купить за ⭐${h.next_stars}</button>` : '<p>Максимум!</p>'}</div>
  <div class="panel"><h2>💱 Обмен ⭐ → $</h2><p class="m">Курс: 1 ⭐ = $${fmt(rate)} (растёт с уровнем дома)</p><div class="row">${[1, 5, 10, 50].map(n => `<button class="alt" onclick="conv(${n})" ${S.gems < n ? 'disabled' : ''}>${n} ⭐ → $${fmt(n * rate)}</button>`).join('')}</div></div>`;
}
function profileV() {
  const p = S.player;
  return `<div class="panel" style="text-align:center"><div style="font-size:60px">${S.avatar}</div><h2>${esc(p.nickname)}</h2><p class="m">ID: ${p.telegram_id}</p></div>
  <div class="panel"><h2>📊 Статистика</h2><div class="row">${[['🏠 Дом', S.house.level + ' ур.'], ['🎮 Игр', p.games_played], ['🏆 Побед', p.games_won]].map(([a, b]) => `<span class="tag">${a}: <b>${b}</b></span>`).join('')}</div></div>
  <div class="panel"><h2>🎭 Аватар</h2><div class="row">${AV.map(a => `<button class="${a === S.avatar ? '' : 'ghost'}" style="font-size:22px" onclick="post('avatar',{avatar:'${a}'})">${a}</button>`).join('')}</div></div>
  <div class="panel"><h2>✏️ Ник</h2><div class="row"><input id="nick" maxlength="24" placeholder="Ник (пусто — имя Telegram)" value="${esc(p.custom_nickname || '')}"><button onclick="saveNick()">Сохранить</button></div></div>`;
}
function adminV() {
  if (!adm) return '<div class="panel m">Загрузка...</div>';
  const s = adm.stats, d = adm.diag, i = adm.info, k = (a, b) => `<div><small>${a}</small><b>${b}</b></div>`;
  const q = (id, a, v, l) => `<button onclick="quick(${id},'${a}',${v})">${l}</button>`;
  return `<div class="panel"><h2>Сводка</h2><div class="kpi">${k('Игроков', s.players) + k('Онлайн 24ч', s.active_24h) + k('Заблокировано', s.blocked) + k('$ в игре', fmt(s.coins_total)) + k('⭐ в игре', fmt(s.gems_total)) + k('Игр', s.games_played) + k('Побед', s.games_won) + k('Тапов', fmt(s.taps))}</div><p class="m">Дома по уровням: ${esc(JSON.stringify(s.levels))}</p></div>
  <div class="cols"><div class="panel"><h2>Диагностика</h2>${Object.entries(d).map(([a, v]) => `<div>${v ? '<span class="ok">● OK</span>' : '<span class="bad">● FAIL</span>'} &nbsp;${esc(a)}</div>`).join('')}<button style="margin-top:10px" onclick="loadAdmin()">Обновить</button></div>
   <div class="panel"><h2>Система</h2>${Object.entries(i).map(([a, v]) => `<div class="m">${esc(a)}: <b style="color:#d6dbe4">${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</b></div>`).join('')}</div>
   <div class="panel"><h2>Ручное управление</h2><div class="row"><input id="a_id" type="number" placeholder="Telegram ID"><input id="a_h" type="number" placeholder="Уровень дома 1–30"></div><div class="row" style="margin-top:8px"><input id="a_c" type="number" placeholder="$ (±)"><input id="a_g" type="number" placeholder="⭐ (±)"></div><div class="row" style="margin-top:8px"><button class="pri" onclick="doGrant()">Применить</button></div><div class="row" style="margin-top:8px"><input id="a_r" placeholder="Причина блокировки"><button class="red" onclick="doBlock(true)">Блок</button><button onclick="doBlock(false)">Разблок</button></div></div></div>
  <div class="panel"><h2>Игроки</h2><div class="row"><input id="a_q" placeholder="Поиск: ID, имя, ник"><button class="pri" onclick="findPl()">Найти</button></div><div class="tw"><table><tr><th>Игрок</th><th>ID</th><th>$</th><th>⭐</th><th>Дом</th><th>Игры/победы</th><th>Заработано</th><th>Был онлайн</th><th>Действия</th></tr>
  ${plist.map(p => `<tr class="${p.blocked ? 'bl' : ''}"><td><a href="#" onclick="pick(${p.telegram_id});return false" style="color:#4c8dff">${esc(p.nickname || p.telegram_name)}</a>${p.blocked ? ' 🚫 ' + esc(p.reason || '') : ''}</td><td>${p.telegram_id}</td><td>${fmt(p.coins)}</td><td>${fmt(p.gems)}</td><td>${p.house ?? 1}</td><td>${p.games_played}/${p.games_won}</td><td>${fmt(p.earned)}</td><td>${p.last_seen ? new Date(p.last_seen * 1000).toLocaleString('ru-RU') : '—'}</td>
  <td>${q(p.telegram_id, 'c', 10000, '+$10k') + q(p.telegram_id, 'c', 1000000, '+$1M') + q(p.telegram_id, 'g', 10, '+⭐10') + q(p.telegram_id, 'g', 100, '+⭐100') + q(p.telegram_id, 'h', (p.house || 1) + 1, 'Дом+1') + (p.blocked ? `<button onclick="quick(${p.telegram_id},'u',0)">Разблок</button>` : `<button class="red" onclick="quick(${p.telegram_id},'b',0)">Блок</button>`)}</td></tr>`).join('')}</table></div></div>`;
}

// ---------- действия
async function go(t) { tab = t; sub = null; drop = null; paint();
  if (t === 'games') run(async () => { game = (await api('/api/bh/mines')).game; paint(); });
  if (t === 'cases') run(async () => { gar = await api('/api/bh/garage'); paint(); });
  if (t === 'top') loadTop(topBy); if (t === 'admin') loadAdmin(); }
const loadTop = by => run(async () => { topBy = by; top = null; paint(); top = await api('/api/bh/top?by=' + by); paint(); });
const claim = () => post('claim').then(r => r && r.got && note(`+$${fmt(r.got)}`));
const daily = () => post('daily').then(r => r && note(`🎁 +$${fmt(r.got)} и ⭐1`));
const conv = n => post('convert', {stars: n}).then(r => r && note(`+$${fmt(r.got)}`));
const openMines = async () => { sub = 'mines'; paint(); };
const startMines = () => { busy = true; return post('mines/start', {bet: cfg.bet, mines: cfg.m}).finally(() => { busy = false; paint(); }); };
const openCell = i => { if (busy) return; busy = true; return post('mines/open', {cell: i}).finally(() => { busy = false; paint(); }); };
const cash = () => post('mines/cash').then(r => r && note('✅ Выигрыш забран'));
const openCase = c => post('case', {case: c}).then(async r => { if (r) { drop = r.car; gar = await api('/api/bh/garage'); paint(); } });
const sell = id => post('sell', {id}).then(async r => { if (r) { gar = await api('/api/bh/garage'); note(`+$${fmt(r.got)}`); paint(); } });
function tapWork() { tapN++; S.energy = Math.max(0, S.energy - 1); S.player.coins += 1 + S.house.level; paint(); clearTimeout(tapT); tapT = setTimeout(() => { const n = tapN; tapN = 0; post('tap', {n}); }, 400); }
const saveNick = () => run(async () => { const r = await api('/api/nickname', {nickname: $('nick').value}); S.player = r.player; note('✅ Ник сохранён'); paint(); });
const loadAdmin = () => run(async () => { adm = await api('/api/admin/stats'); plist = (await api('/api/admin/players')).players; paint(); });
const findPl = () => { const q = $('a_q').value; return run(async () => { plist = (await api('/api/admin/players?q=' + encodeURIComponent(q))).players; paint(); $('a_q').value = q; }); };
const pick = id => { $('a_id').value = id; $('a_id').scrollIntoView({behavior: 'smooth', block: 'center'}); };
const doGrant = () => run(async () => { const id = +$('a_id').value; if (!id) throw new Error('Укажи ID'); await api('/api/admin/grant', {telegram_id: id, coins: +$('a_c').value || 0, gems: +$('a_g').value || 0, house: +$('a_h').value || 0}); note('✅ Применено'); await loadAdmin(); });
const doBlock = b => run(async () => { const id = +$('a_id').value; if (!id) throw new Error('Укажи ID'); await api('/api/admin/block', {telegram_id: id, blocked: b, reason: $('a_r').value}); note(b ? '🚫 Заблокирован' : '✅ Разблокирован'); await loadAdmin(); });
const quick = (id, a, v) => run(async () => {
  if (a === 'b' || a === 'u') await api('/api/admin/block', {telegram_id: id, blocked: a === 'b', reason: a === 'b' ? 'Админ' : ''});
  else await api('/api/admin/grant', {telegram_id: id, coins: a === 'c' ? v : 0, gems: a === 'g' ? v : 0, house: a === 'h' ? Math.min(v, 30) : 0});
  note('✅ Готово'); await loadAdmin(); });

// доход дома тикает каждую секунду
setInterval(() => { if (!S || tab !== 'home') return; const h = S.house, p = Math.min(h.pending + h.income / 3600 * (Date.now() - S.t0) / 1000, h.income * h.cap_hours);
  const e = $('pend'); if (e) e.textContent = fmt(Math.floor(p)); const b = $('claim'); if (b) { b.disabled = p < 1; b.textContent = `Забрать $${fmt(Math.floor(p))}`; } }, 1000);
(async () => { await run(async () => { setS(await api('/api/bh/state')); paint(); }); if (!S) $('view').innerHTML = `<div class="panel">⚠️ ${esc($('status').textContent)}</div>`; })();
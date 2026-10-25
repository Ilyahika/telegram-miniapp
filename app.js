// HTTPS-адрес твоего Render, БЕЗ / в конце.
const API_BASE = 'https://telegram-miniapp-i49m.onrender.com';
const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const $ = id => document.getElementById(id);
const fmt = n => Number(n ?? 0).toLocaleString('ru-RU');
const inf = n => Number(n ?? 0) >= 1e14 ? '∞' : fmt(n);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const AV = ['🏠','🔨','👷','🏗️','🦾','👑','🐱','🚀'];
const BETS = [200,500,1000,3000,5000,10000,50000];
let S = null, tab = 'home', sub = null, game = null, cfg = {bet: 200, m: 3}, gar = null, drop = null, top = null, topBy = 'house', adm = null, plist = [], busy = false, tapN = 0, tapT;

const note = m => { const s = $('status'); s.textContent = m; clearTimeout(note.t); note.t = setTimeout(() => s.textContent = '', 4500); };
async function api(path, body) {
  if (!tg?.initData) throw new Error('Открой приложение кнопкой «Открыть» внутри Telegram.');
  let r;
  try {
    r = await fetch(API_BASE + path, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {'X-Telegram-Init-Data': tg.initData, 'Content-Type': 'application/json'},
      body: body === undefined ? undefined : JSON.stringify(body)
    });
  } catch (e) {
    throw new Error('Нет связи с сервером. Render мог уснуть — подожди 20–60 секунд и попробуй снова.');
  }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `Ошибка сервера ${r.status}`);
  return j;
}
const run = async fn => { try { return await fn(); } catch (e) { note('⚠️ ' + e.message); } };
const setS = r => { S = r; S.t0 = Date.now(); if (r.game !== undefined) game = r.game; };
const post = (p, b = {}) => run(async () => { const r = await api('/api/bh/' + p, b); setS(r); paint(); return r; });
const mult = (k, m) => { let p = .97; for (let i = 0; i < k; i++) p *= (25 - i) / (25 - m - i); return Math.round(p * 100) / 100; };
const ago = ts => !ts ? '—' : new Date(ts * 1000).toLocaleString('ru-RU');
const okFail = v => v ? '<span class="diag-dot ok"></span><b>OK</b>' : '<span class="diag-dot fail"></span><b>FAIL</b>';

function logoHouse(){
  return `<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M10 31 32 11l22 20v22H10V31Z" fill="#FFCC00"/><path d="M18 31h28v22H18V31Z" fill="#fff"/><path d="M28 39h8v14h-8V39Z" fill="#E53935"/><path d="M22 36h4v5h-4Zm16 0h4v5h-4Z" fill="#111"/></svg>`;
}
function logoInfinity(){
  return `<svg viewBox="0 0 64 64" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M17 22c5.4 0 9.2 3.4 15 10 5.8-6.6 9.6-10 15-10 6.1 0 11 4.9 11 11s-4.9 11-11 11c-5.4 0-9.2-3.4-15-10-5.8 6.6-9.6 10-15 10-6.1 0-11-4.9-11-11s4.9-11 11-11Zm0 6a5 5 0 1 0 0 10c2.7 0 4.7-1.7 10.5-8-5.8-6.3-7.8-8-10.5-8Zm30 0c-2.7 0-4.7 1.7-10.5 8 5.8 6.3 7.8 8 10.5 8a5 5 0 1 0 0-10Z" fill="#FFCC00"/><circle cx="32" cy="32" r="31" stroke="#E53935" stroke-opacity=".45"/></svg>`;
}

function updateBrand(){
  const isAdmin = !!S?.is_admin;
  $('brandMark').innerHTML = isAdmin ? logoInfinity() : logoHouse();
  $('brandTitle').textContent = isAdmin ? 'Infinity Control' : 'Infinity Estate';
  $('brandSub').textContent = isAdmin ? 'strict admin panel' : 'business control panel';
  $('adminPill').classList.toggle('show', isAdmin);
}

function houseSvg(lv) {
  const style = Math.min(5, Math.max(1, Math.ceil(lv / 6)));
  const floors = Math.min(2 + Math.ceil(lv / 3), 10);
  const width = 80 + Math.min(lv, 18) * 8;
  const x = 150 - width / 2;
  const floorH = style >= 4 ? 20 : 24;
  const top = 250 - floors * floorH;
  const wall = ['#f5f5f5','#f1f1f1','#dfdfdf','#d0d0d0','#c7c7c7'][style-1];
  const accent = ['#ffcc00','#ffd54f','#ffca28','#ffb300','#ffd84d'][style-1];
  const roof = ['#e53935','#c62828','#b71c1c','#8e1717','#e53935'][style-1];
  let s = `<svg viewBox="0 0 300 280" xmlns="http://www.w3.org/2000/svg">`;
  s += `<defs><linearGradient id="bgH" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0f0f0f"/><stop offset="1" stop-color="#171717"/></linearGradient><linearGradient id="glass" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fff9c4"/><stop offset="1" stop-color="#ffcc00"/></linearGradient></defs>`;
  s += `<rect x="0" y="0" width="300" height="280" rx="28" fill="url(#bgH)"/>`;
  s += `<circle cx="52" cy="56" r="18" fill="#ffcc00" opacity=".95"/><rect x="0" y="240" width="300" height="40" fill="#0d0d0d"/>`;
  for(let i=0;i<12;i++) s += `<circle cx="${20 + (i*23)%260}" cy="${26 + (i*29)%70}" r="${i%3===0?1.5:1}" fill="#fff" opacity=".75"/>`;
  for(let f=0; f<floors; f++){
    const y = 250 - (f+1)*floorH;
    s += `<rect x="${x}" y="${y}" width="${width}" height="${floorH}" rx="4" fill="${wall}" stroke="#3d3d3d"/>`;
    const cols = Math.min(5, 2 + Math.floor(lv/7));
    const winW = (width - 20) / cols - 8;
    for(let c=0;c<cols;c++){
      s += `<rect x="${x+12+c*((width-20)/cols)}" y="${y+5}" width="${winW}" height="${floorH-10}" rx="3" fill="url(#glass)" opacity="${(c+f)%5===0?.5:1}"/>`;
    }
  }
  if(style <= 2){
    s += `<polygon points="${x-8},${top+2} 150,${top-38-lv} ${x+width+8},${top+2}" fill="${roof}"/>`;
    s += `<rect x="${x+width-28}" y="${top-34}" width="12" height="28" fill="#7a2626"/>`;
  } else if(style === 3){
    s += `<rect x="${x-4}" y="${top-10}" width="${width+8}" height="12" rx="2" fill="${accent}"/>`;
  } else if(style === 4){
    s += `<rect x="${x-4}" y="${top-10}" width="${width+8}" height="10" fill="#d5d5d5"/><rect x="145" y="${top-45}" width="10" height="45" fill="#f5f5f5"/><circle cx="150" cy="${top-49}" r="6" fill="#e53935"/>`;
  } else {
    s += `<path d="M${x-2},${top+1} Q150,${top-62} ${x+width+2},${top+1}Z" fill="${roof}"/>`;
    s += `<circle cx="150" cy="${top-42}" r="7" fill="#ffcc00"/>`;
  }
  s += `<rect x="136" y="226" width="28" height="24" rx="4" fill="#212121" stroke="#424242"/><rect x="0" y="236" width="300" height="6" fill="#2e7d32"/><circle cx="65" cy="238" r="8" fill="#2e7d32"/><circle cx="235" cy="238" r="8" fill="#2e7d32"/>`;
  s += `</svg>`;
  return s;
}

function paint() {
  if (!S) return;
  document.body.classList.toggle('adm', tab === 'admin');
  updateBrand();
  $('coins').textContent = inf(S.player.coins);
  $('gems').textContent = inf(S.gems);
  const items = [['home','🏠','Дом'],['games','🎮','Игры'],['cases','📦','Кейсы'],['top','🏆','Топ'],['shop','⭐','Магазин'],['profile','👤','Профиль']];
  if (S.is_admin) items.push(['admin','∞','Админ']);
  $('nav').innerHTML = items.map(([k,i,t]) => `<button class="${k===tab?'on':''}" onclick="go('${k}')"><b>${i}</b>${t}</button>`).join('');
  const views = {home: homeV, games: gamesV, cases: casesV, top: topV, shop: shopV, profile: profileV, admin: adminV};
  $('view').innerHTML = views[tab]();
}

function homeV() {
  const h = S.house;
  return `<section class="hero">
    <div class="panel house-card">
      <div class="section-title"><div><h2>${esc(h.name)}</h2><p class="m">Текущий объект и пассивный доход</p></div><span class="lvl">Уровень ${h.level} / ${h.max}</span></div>
      <div class="house-box">${houseSvg(h.level)}</div>
      <div class="prog"><i style="width:${(h.level/h.max)*100}%"></i></div>
      <div class="metrics">
        <div class="mini"><small>Доход / час</small><b>$${fmt(h.income)}</b></div>
        <div class="mini"><small>Лимит накопления</small><b>${h.cap_hours} ч</b></div>
        <div class="mini"><small>Следующий доход</small><b>${h.next_income ? '$'+fmt(h.next_income) : 'MAX'}</b></div>
      </div>
    </div>
    <div>
      <div class="panel">
        <h2>Доступный доход</h2>
        <div style="font-size:34px;font-weight:900;color:var(--yellow);margin:10px 0">$<span id="pend">${fmt(h.pending)}</span></div>
        <p class="m">Средства накапливаются в реальном времени и ждут выдачи.</p>
        <button class="pri big" id="claim" onclick="claim()">Забрать</button>
      </div>
      <div class="panel">
        <h2>Прокачка дома</h2>
        ${h.next_cost ? `<p class="m">Следующий уровень увеличит доход до <b>$${fmt(h.next_income)}</b> в час.</p>
        <div class="grid2">
          <button class="light" onclick="post('upgrade').then(r=>r&&note('🏠 Дом улучшен'))" ${S.player.coins < h.next_cost ? 'disabled' : ''}>За $${fmt(h.next_cost)}</button>
          <button class="pri" onclick="go('shop')">За ⭐${h.next_stars}</button>
        </div>` : `<div class="empty">Максимальный уровень дома достигнут.</div>`}
      </div>
    </div>
  </section>
  <div class="panel">
    <h2>Быстрые действия</h2>
    <div class="cards">
      <div class="card" onclick="go('games')"><i>💣</i><b>Играть в мины</b><small>Открывай клетки и забирай множитель</small></div>
      <div class="card" onclick="go('cases')"><i>📦</i><b>Открыть кейсы</b><small>Выбей машину и продай её за монеты</small></div>
      <div class="card" onclick="daily()"><i>🎁</i><b>Ежедневный бонус</b><small>${S.daily_ready ? `Готов: $${fmt(100*h.level)} + ⭐1` : 'Будет доступен позже'}</small></div>
      <div class="card" onclick="go('top')"><i>🏆</i><b>Рейтинг игроков</b><small>Сравни дом и баланс с другими</small></div>
    </div>
  </div>`;
}

function gamesV() {
  if (sub === 'work') return `<button class="ghost" onclick="sub=null;paint()">← Назад к играм</button>` + workV();
  if (sub === 'mines') return `<button class="ghost" onclick="sub=null;paint()">← Назад к играм</button>` + minesV();
  return `<div class="panel"><div class="section-title"><div><h2>Игровой центр</h2><p class="m">Выбери режим и зарабатывай внутри Mini App</p></div></div>
    <div class="cards">
      <div class="card" onclick="openMines()"><i>💣</i><b>Мины</b><small>Ставка, множитель, риск и награда</small></div>
      <div class="card" onclick="sub='work';paint()"><i>🔨</i><b>Стройка</b><small>Тапай и обменивай энергию на деньги</small></div>
      <div class="card" onclick="go('cases')"><i>🚗</i><b>Кейсы и гараж</b><small>Собирай коллекцию автомобилей</small></div>
      <div class="card" onclick="go('profile')"><i>👤</i><b>Профиль</b><small>Меняй ник, аватар и смотри статистику</small></div>
    </div></div>`;
}

function workV() {
  return `<div class="panel"><h2>Стройка</h2><p class="m">1 тап = <b>$${1 + S.house.level}</b>. Энергия восстанавливается автоматически.</p>
    <div class="metrics">
      <div class="mini"><small>Энергия</small><b>${S.energy}/${S.max_energy}</b></div>
      <div class="mini"><small>Доход за тап</small><b>$${1 + S.house.level}</b></div>
      <div class="mini"><small>Режим</small><b>Кликер</b></div>
    </div>
    <div class="prog" style="margin-top:12px"><i style="width:${(S.energy/S.max_energy)*100}%"></i></div>
    <button class="pri big" onclick="tapWork()" ${S.energy < 1 ? 'disabled' : ''}>🔨 Работать</button>
  </div>`;
}

function minesCell(c, i, playing) {
  const state = c === 'closed' ? '' : c;
  const icon = c === 'mine' ? '💣' : c === 'safe' ? '💎' : '◆';
  return `<button class="cell ${state}" onclick="openCell(${i})" ${busy || c !== 'closed' || !playing ? 'disabled' : ''}>${icon}</button>`;
}

function minesV() {
  const playing = game?.status === 'playing';
  const m = cfg.m;
  const setup = playing ? '' : `<div class="panel">
      <div class="section-title"><div><h2>Настройка игры</h2><p class="m">Выбери ставку и количество мин перед началом.</p></div></div>
      <h3>Ставка</h3>
      <div class="chips">${BETS.map(b => `<button class="chip ${cfg.bet === b ? 'on' : ''}" onclick="cfg.bet=${b};paint()">$${fmt(b)}</button>`).join('')}</div>
      <div class="rangebox">
        <div class="section-title"><h3 style="margin:0">Количество мин</h3><b id="mc">${m}</b></div>
        <input type="range" min="1" max="20" value="${m}" oninput="cfg.m=+this.value;$('mc').textContent=this.value;$('mm').textContent='x'+mult(1,+this.value)" onchange="paint()">
        <p class="m" style="margin:10px 0 0">Множитель за первую безопасную клетку: <b id="mm" style="color:var(--yellow)">x${mult(1, m)}</b></p>
      </div>
      <button class="red big" onclick="startMines()" ${S.player.coins < cfg.bet ? 'disabled' : ''}>Начать игру на $${fmt(cfg.bet)}</button>
    </div>`;
  const header = game ? `<div class="mines-head">
      <div class="pillbox"><small>Ставка</small><b>$${fmt(game.bet)}</b></div>
      <div class="pillbox"><small>Открыто</small><b>${game.opened}</b></div>
      <div class="pillbox"><small>Мин на поле</small><b>${game.mines}</b></div>
    </div>` : '';
  const status = !game ? '' : playing
    ? `<div class="row" style="justify-content:space-between;margin:12px 0 10px"><div class="tag">Коэффициент: <b>x${game.mult}</b></div><div class="tag">Следующий: <b>${game.next ? 'x'+game.next : '—'}</b></div></div><button class="pri big" onclick="cash()">${game.opened ? `Забрать $${fmt(game.payout)}` : 'Вернуть ставку'}</button>`
    : game.status === 'lost'
      ? `<div class="empty" style="border-color:rgba(229,57,53,.35);color:#fff">💣 Ты попал на мину. Ставка $${fmt(game.bet)} сгорела.</div>`
      : `<div class="empty" style="border-color:rgba(255,204,0,.35);color:#fff">🏆 Игра завершена. Забрано $${fmt(game.payout)} · x${game.mult}</div>`;
  const board = game ? `<div class="panel"><div class="section-title"><div><h2>Поле «Мины»</h2><p class="m">Открывай клетки и не попади на бомбу.</p></div></div>${header}${status}<div class="board" style="margin-top:12px">${game.cells.map((c,i)=>minesCell(c,i,playing)).join('')}</div></div>` : '';
  return `${setup}${board}`;
}

function casesV() {
  if (!gar) return '<div class="panel"><div class="m">Загрузка гаража...</div></div>';
  const cases = Object.entries(gar.cases).map(([k,c]) => `<div class="panel"><div class="section-title"><div><h2>📦 ${esc(c.name)}</h2><p class="m">${c.drops.map(d => d.name).join(' · ')}</p></div><button class="pri" onclick="openCase('${k}')" ${S.player.coins < c.price ? 'disabled' : ''}>$${fmt(c.price)}</button></div></div>`).join('');
  const val = gar.cars.reduce((a,c)=>a+c.value,0);
  return `${drop ? `<div class="case-drop"><h2 style="margin:0 0 8px">Поздравляем!</h2><div style="font-size:42px">🚗</div><b>${esc(drop.name)}</b><p class="m" style="margin:8px 0 0">Рыночная стоимость: $${fmt(drop.value)}</p></div>` : ''}
    ${cases}
    <div class="panel"><div class="section-title"><div><h2>Гараж</h2><p class="m">Всего машин: ${gar.cars.length}</p></div><div class="tag">Сумма: <b>$${fmt(val)}</b></div></div>
      ${gar.cars.length ? gar.cars.map(c => `<div class="car">🚘 <div><b>${esc(c.name)}</b><div class="m">$${fmt(c.value)}</div></div><button class="pri" onclick="sell(${c.id})">Продать</button></div>`).join('') : `<div class="empty">Гараж пуст. Открой первый кейс.</div>`}
    </div>`;
}

function topV() {
  const medal = i => ['🥇','🥈','🥉'][i] || `${i+1}.`;
  return `<div class="panel"><div class="section-title"><div><h2>Рейтинг игроков</h2><p class="m">Сравнивай прогресс, дома и богатство</p></div></div>
    <div class="chips"><button class="chip ${topBy==='house'?'on':''}" onclick="loadTop('house')">🏠 По дому</button><button class="chip ${topBy==='coins'?'on':''}" onclick="loadTop('coins')">💰 По деньгам</button></div>
    <div style="margin-top:12px">${top ? top.top.map((p,i)=>`<div class="top-item ${p.id===S.player.telegram_id?'me':''}"><span>${medal(i)}</span><span>${p.avatar}</span><span>${esc(p.name)}</span><b>${topBy==='house' ? 'ур. '+p.house : '$'+fmt(p.coins)}</b></div>`).join('') : `<div class="empty">Загрузка рейтинга...</div>`}</div>
    <p class="m" style="margin-top:12px">Твоя позиция: <b>${top?.me ?? '—'}</b></p>
  </div>`;
}

function shopV() {
  const h = S.house, rate = 500 * h.level;
  return `<div class="panel"><h2>Магазин ресурсов</h2><p class="m">Здесь можно ускорять развитие дома и обменивать звёзды на монеты.</p></div>
  <div class="grid2">
    <div class="panel"><h2>Уровень дома</h2>${h.next_stars ? `<p class="m">Купить ${h.level+1} уровень за ⭐${h.next_stars}</p><button class="pri big" onclick="post('buylevel').then(r=>r&&note('⭐ Уровень куплен'))" ${S.gems < h.next_stars ? 'disabled' : ''}>Купить улучшение</button>` : `<div class="empty">У тебя уже максимальный уровень дома.</div>`}</div>
    <div class="panel"><h2>Обмен ⭐ → $</h2><p class="m">Текущий курс: <b>1 ⭐ = $${fmt(rate)}</b></p><div class="chips">${[1,5,10,50].map(n=>`<button class="chip" onclick="conv(${n})" ${S.gems < n ? 'disabled' : ''}>${n} ⭐ → $${fmt(n*rate)}</button>`).join('')}</div></div>
  </div>`;
}

function profileV() {
  const p = S.player;
  return `<div class="panel"><div class="profile-head"><div class="profile-avatar">${S.avatar}</div><div><h2 style="margin:0">${esc(p.nickname)}</h2><p class="m">По умолчанию используется имя из Telegram. Ты можешь задать игровой ник вручную.</p><div class="row"><span class="tag">Telegram ID: <b>${p.telegram_id}</b></span><span class="tag">Дом: <b>${S.house.level}</b></span></div></div></div>
    <div class="profile-stats">
      <div class="mini"><small>Сыграно игр</small><b>${fmt(p.games_played)}</b></div>
      <div class="mini"><small>Побед</small><b>${fmt(p.games_won)}</b></div>
      <div class="mini"><small>Баланс</small><b>$${inf(p.coins)}</b></div>
    </div>
  </div>
  <div class="panel"><h2>Изменение аватара</h2><div class="row avatar-row">${AV.map(a => `<button class="${a===S.avatar?'pri':'ghost'}" onclick="post('avatar',{avatar:'${a}'})">${a}</button>`).join('')}</div></div>
  <div class="panel"><h2>Изменение профиля</h2><p class="m">Если поле пустое — будет отображаться имя Telegram.</p><div class="row"><input id="nick" maxlength="24" placeholder="Введи новый ник" value="${esc(p.custom_nickname || '')}"><button class="pri" onclick="saveNick()">Сохранить ник</button></div></div>`;
}

function adminV() {
  if (!adm) return '<div class="panel"><div class="m">Загрузка админ-панели...</div></div>';
  const s = adm.stats, d = adm.diag, i = adm.info;
  const q = (id, a, v, l) => `<button onclick="quick(${id},'${a}',${v})">${l}</button>`;
  return `<div class="panel admin-banner"><div class="inf-logo">${logoInfinity()}</div><div><h2 style="margin:0 0 4px">Infinity Admin</h2><p class="m" style="margin:0">Строгая админ-панель. Для администратора отображаются бесконечные ресурсы и доступно ручное управление игроками.</p></div></div>
  <div class="panel"><h2>Ключевые показатели</h2><div class="kpi">
    <div class="item"><small>Игроков</small><b>${fmt(s.players)}</b></div>
    <div class="item"><small>Онлайн 24ч</small><b>${fmt(s.active_24h)}</b></div>
    <div class="item"><small>Заблокировано</small><b>${fmt(s.blocked)}</b></div>
    <div class="item"><small>Монет в игре</small><b>$${fmt(s.coins_total)}</b></div>
    <div class="item"><small>Звёзд в игре</small><b>${fmt(s.gems_total)}</b></div>
    <div class="item"><small>Сыграно игр</small><b>${fmt(s.games_played)}</b></div>
    <div class="item"><small>Побед</small><b>${fmt(s.games_won)}</b></div>
    <div class="item"><small>Тапов</small><b>${fmt(s.taps)}</b></div>
  </div><p class="m" style="margin-top:10px">Распределение домов по уровням: <b>${esc(JSON.stringify(s.levels))}</b></p></div>
  <div class="cols">
    <div class="panel"><div class="section-title"><div><h2>Диагностика</h2><p class="m">Состояние важных компонентов системы</p></div><button class="pri" onclick="loadAdmin()">Обновить</button></div>
      <div class="diag-grid">${Object.entries(d).map(([k,v])=>`<div class="diag-card ${v?'ok':'fail'}"><div class="diag-line">${okFail(v)}</div><div style="margin-top:8px"><b>${esc(k)}</b></div><div class="m" style="margin-top:4px">${v ? 'Проверка пройдена' : 'Требует внимания'}</div></div>`).join('')}</div>
    </div>
    <div class="panel"><h2>Система</h2><div class="info-list">${Object.entries(i).map(([k,v])=>`<div class="info-row"><small>${esc(k)}</small><b>${esc(typeof v === 'object' ? JSON.stringify(v) : v)}</b></div>`).join('')}</div></div>
  </div>
  <div class="panel"><h2>Ручное управление игроком</h2>
    <div class="grid2"><input id="a_id" type="number" placeholder="Telegram ID"><input id="a_h" type="number" placeholder="Уровень дома 1–30"></div>
    <div class="grid2" style="margin-top:10px"><input id="a_c" type="number" placeholder="Монеты (±)"><input id="a_g" type="number" placeholder="Звёзды (±)"></div>
    <div class="row" style="margin-top:10px"><button class="pri" onclick="doGrant()">Применить ресурсы</button></div>
    <div class="grid2" style="margin-top:10px"><input id="a_r" placeholder="Причина блокировки"><div class="row"><button class="red" onclick="doBlock(true)">Заблокировать</button><button class="ghost" onclick="doBlock(false)">Разблокировать</button></div></div>
  </div>
  <div class="panel"><div class="section-title"><div><h2>Игроки</h2><p class="m">Поиск, выдача ресурсов и модерация</p></div></div>
    <div class="row"><input id="a_q" placeholder="Поиск: ID, имя, ник"><button class="pri" onclick="findPl()">Найти</button></div>
    <div class="tw" style="margin-top:12px"><table><tr><th>Игрок</th><th>ID</th><th>$</th><th>⭐</th><th>Дом</th><th>Игры</th><th>Заработано</th><th>Был онлайн</th><th>Действия</th></tr>
      ${plist.map(p => `<tr class="${p.blocked ? 'bl' : ''}"><td><a href="#" onclick="pick(${p.telegram_id});return false" style="color:#ffcc00;text-decoration:none;font-weight:800">${esc(p.nickname || p.telegram_name)}</a>${p.blocked ? `<div class="m">🚫 ${esc(p.reason || 'Без причины')}</div>` : ''}</td><td>${p.telegram_id}</td><td>${fmt(p.coins)}</td><td>${fmt(p.gems)}</td><td>${p.house ?? 1}</td><td>${p.games_played}/${p.games_won}</td><td>${fmt(p.earned)}</td><td>${ago(p.last_seen)}</td><td><div class="inline-actions">${q(p.telegram_id,'c',10000,'+$10k')}${q(p.telegram_id,'c',1000000,'+$1M')}${q(p.telegram_id,'g',10,'+⭐10')}${q(p.telegram_id,'g',100,'+⭐100')}${q(p.telegram_id,'h',(p.house||1)+1,'Дом+1')}${p.blocked ? `<button onclick="quick(${p.telegram_id},'u',0)">Разблок</button>` : `<button class="red" onclick="quick(${p.telegram_id},'b',0)">Блок</button>`}</div></td></tr>`).join('')}</table></div>
  </div>`;
}

async function go(t) {
  tab = t; sub = null; drop = null; paint();
  if (t === 'games') run(async () => { game = (await api('/api/bh/mines')).game; paint(); });
  if (t === 'cases') run(async () => { gar = await api('/api/bh/garage'); paint(); });
  if (t === 'top') loadTop(topBy);
  if (t === 'admin') loadAdmin();
}
const loadTop = by => run(async () => { topBy = by; top = null; paint(); top = await api('/api/bh/top?by=' + by); paint(); });
const claim = () => post('claim').then(r => r && r.got && note(`+$${fmt(r.got)}`));
const daily = () => post('daily').then(r => r && note(`🎁 +$${fmt(r.got)} и +⭐1`));
const conv = n => post('convert', {stars: n}).then(r => r && note(`+$${fmt(r.got)}`));
const openMines = async () => { sub = 'mines'; paint(); game = (await api('/api/bh/mines')).game; paint(); };
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
const doGrant = () => run(async () => { const id = +$('a_id').value; if (!id) throw new Error('Укажи ID игрока'); await api('/api/admin/grant', {telegram_id: id, coins: +$('a_c').value || 0, gems: +$('a_g').value || 0, house: +$('a_h').value || 0}); note('✅ Изменения применены'); await loadAdmin(); });
const doBlock = b => run(async () => { const id = +$('a_id').value; if (!id) throw new Error('Укажи ID игрока'); await api('/api/admin/block', {telegram_id: id, blocked: b, reason: $('a_r').value}); note(b ? '🚫 Игрок заблокирован' : '✅ Игрок разблокирован'); await loadAdmin(); });
const quick = (id, a, v) => run(async () => {
  if (a === 'b' || a === 'u') await api('/api/admin/block', {telegram_id: id, blocked: a === 'b', reason: a === 'b' ? 'Админ' : ''});
  else await api('/api/admin/grant', {telegram_id: id, coins: a === 'c' ? v : 0, gems: a === 'g' ? v : 0, house: a === 'h' ? Math.min(v, 30) : 0});
  note('✅ Выполнено'); await loadAdmin();
});

setInterval(() => {
  if (!S || tab !== 'home') return;
  const h = S.house;
  const p = Math.min(h.pending + h.income / 3600 * (Date.now() - S.t0) / 1000, h.income * h.cap_hours);
  const e = $('pend');
  if (e) e.textContent = fmt(Math.floor(p));
  const b = $('claim');
  if (b) { b.disabled = p < 1; b.textContent = `Забрать $${fmt(Math.floor(p))}`; }
}, 1000);

(async () => {
  await run(async () => { setS(await api('/api/bh/state')); paint(); });
  if (!S) $('view').innerHTML = `<div class="panel">⚠️ ${esc($('status').textContent)}</div>`;
})();

/* ============================================================ BuildHouse — клиент (Telegram Mini App)
   Разделы: 1 настройки и утилиты · 2 запросы к серверу · 3 загрузка · 4 дом (SVG) · 5 экраны · 6 действия */

/* ---------- 1. Настройки и утилиты ---------- */
// Адрес API берём из <meta name="api-base"> в index.html (пусто = тот же сервер, что отдал страницу)
const API_BASE = (document.querySelector('meta[name="api-base"]')?.content || '').trim().replace(/\/$/, '');
const VER = new URLSearchParams(document.currentScript?.src.split('?')[1] || '').get('v') || '1'; // версия для сброса кэша
const tg = window.Telegram?.WebApp;                       // объект Telegram WebApp (нет, если открыто в обычном браузере)
if (tg) { tg.ready(); tg.expand(); tg.disableVerticalSwipes?.(); }  // ready() — убирает загрузчик Telegram; expand() — на весь экран

const $ = id => document.getElementById(id);              // короткий поиск элемента по id
const sleep = ms => new Promise(r => setTimeout(r, ms));
const fmt = n => Number(n ?? 0).toLocaleString('ru-RU');  // 1234567 -> «1 234 567»
const inf = n => n >= 1e14 ? '∞' : fmt(n);               // огромные балансы админа показываем как ∞
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[c])); // защита от HTML-инъекций
const AVATARS = ['🏠', '🔨', '👷', '🏗️', '🦾', '👑', '🐱', '🚀'];
const BETS = [200, 500, 1000, 3000, 5000, 10000, 50000]; // допустимые ставки в «Минах»

// Состояние приложения
let S = null;                    // состояние игрока с сервера (баланс, дом, энергия…)
let tab = 'home', sub = null;    // текущая вкладка и подэкран («Мины» / «Стройка»)
let game = null;                 // текущая игра в мины
let cfg = {bet: 200, m: 3};      // выбранные ставка и число мин
let gar = null, drop = null;     // гараж/кейсы и последняя выпавшая машина
let top = null, topBy = 'house', topQ = ''; // рейтинг
let busy = false;                // true, пока выполняется запрос (защита от двойных кликов)
let tapN = 0, tapT = null;       // накопленные тапы «Стройки» и таймер их отправки
let lastSync = 0;                // когда последний раз получали состояние с сервера

/** Всплывающее уведомление внизу экрана (исчезает через 4 секунды). */
function note(msg) {
  const el = $('status');
  el.textContent = msg;
  clearTimeout(note.t);
  note.t = setTimeout(() => { el.textContent = ''; }, 4000);
}

/** Подтверждение действия: нативное окно Telegram или обычный confirm. */
const ask = text => new Promise(res => (tg?.showConfirm && tg.isVersionAtLeast?.('6.2')) ? tg.showConfirm(text, res) : res(confirm(text)));

/** Подгружает JS-файл по требованию (админ-панель грузится только админу). */
const loadScript = src => new Promise((ok, fail) => {
  const s = document.createElement('script');
  s.src = src; s.onload = ok; s.onerror = () => fail(new Error('Не удалось загрузить ' + src));
  document.head.appendChild(s);
});

/* ---------- 2. Запросы к серверу ---------- */
class ApiError extends Error {
  constructor(message, status = 0, retry = false) { super(message); this.status = status; this.retry = retry; }
}

/**
 * Запрос к API. body === undefined -> GET, иначе POST (JSON).
 * timeout — через сколько мс прервать; retries — сколько раз повторить GET при сетевой ошибке / 502-504.
 * Именно отсутствие таймаута раньше давало «вечную загрузку»: fetch ждал ответ спящего сервера бесконечно.
 */
async function api(path, body, {timeout = 15000, retries = 0} = {}) {
  if (!tg?.initData) throw new ApiError('Открой приложение кнопкой «Открыть» в Telegram, а не в браузере.');
  const init = {
    method: body === undefined ? 'GET' : 'POST', cache: 'no-store',
    headers: {'X-Telegram-Init-Data': tg.initData, ...(body === undefined ? {} : {'Content-Type': 'application/json'})},
    body: body === undefined ? undefined : JSON.stringify(body)};
  for (let attempt = 0; ; attempt++) {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), timeout);       // прервать запрос по таймеру
    try {
      const r = await fetch(API_BASE + path, {...init, signal: ctl.signal});
      const j = await r.json().catch(() => ({}));
      if (r.ok) return j;
      const msg = typeof j.detail === 'string' ? j.detail : `Ошибка сервера ${r.status}`;
      throw new ApiError(msg, r.status, r.status >= 502 && r.status <= 504); // 502–504 = сервер просыпается
    } catch (e) {
      const err = e instanceof ApiError ? e
        : new ApiError(e.name === 'AbortError' ? 'Сервер долго не отвечает.' : 'Нет связи с сервером (Render мог уснуть — подожди минуту).', 0, true);
      if (!err.retry || attempt >= retries || body !== undefined) throw err; // POST не повторяем: можно потратить деньги дважды
      await sleep(1500 * (attempt + 1));
    } finally { clearTimeout(timer); }
  }
}

/** Выполняет функцию и показывает ошибку уведомлением (вместо падения скрипта). */
const run = async fn => { try { return await fn(); } catch (e) { note('⚠️ ' + e.message); } };

/** Принимает свежее состояние от сервера. */
function setS(r) {
  S = r; S.t0 = Date.now(); lastSync = Date.now();
  if (r.game !== undefined) game = r.game;
}

/** POST к /api/bh/<path>: блокирует повторные клики, обновляет состояние и экран. Возвращает ответ или null. */
async function post(path, body = {}) {
  if (busy) return null;
  busy = true; document.body.classList.add('busy');
  let r = null;
  try { r = await api('/api/bh/' + path, body); setS(r); }
  catch (e) { note('⚠️ ' + e.message); }
  finally { busy = false; document.body.classList.remove('busy'); }
  paint();                                                       // перерисовываем в любом случае — снимает блокировку кнопок
  return r;
}

/** Коэффициент мин (та же формула, что на сервере) — для подсказки до начала игры. */
const mult = (k, m) => { let p = .97; for (let i = 0; i < k; i++) p *= (25 - i) / (25 - m - i); return Math.round(p * 100) / 100; };

/* ---------- 3. Загрузка (без зависаний) ---------- */
const splash = msg => { $('view').innerHTML = `<div class="panel splash"><div class="spin"></div><div>${esc(msg)}</div></div>`; };

/**
 * Запуск приложения:
 *  1) «будим» сервер лёгким запросом /health с таймаутом (бесплатный Render засыпает и просыпается до ~1 минуты);
 *  2) пока ждём — показываем живой счётчик секунд, а не пустую загрузку;
 *  3) грузим состояние игрока; при ошибке — понятное сообщение и кнопка «Повторить».
 */
async function boot() {
  const t0 = Date.now();
  splash('Подключаемся к серверу…');
  let awake = false;
  for (let i = 0; i < 15 && !awake; i++) {
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 8000);
    try { awake = (await fetch(API_BASE + '/health', {signal: ctl.signal, cache: 'no-store'})).ok; } catch (_) { /* ещё спит */ }
    clearTimeout(timer);
    if (!awake) { splash(`Сервер просыпается… ${Math.round((Date.now() - t0) / 1000)} с (обычно до минуты)`); await sleep(2000); }
  }
  try {
    setS(await api('/api/bh/state', undefined, {timeout: 20000, retries: 2}));
    paint();
  } catch (e) {
    $('view').innerHTML = `<div class="panel"><h2>⚠️ Не удалось загрузить</h2><p>${esc(e.message)}</p><button class="full" onclick="boot()">Повторить</button></div>`;
  }
}

/** Когда пользователь возвращается в приложение после долгого отсутствия — обновляем данные. */
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && S && Date.now() - lastSync > 30000 && !['admin'].includes(tab)) {
    run(async () => { setS(await api('/api/bh/state')); paint(); });
  }
});

/* ---------- 4. Дом: SVG по уровню (5 архитектурных эпох) ---------- */
function houseSvg(lv) {
  const era = Math.ceil(lv / 6);                                  // эпоха 1..5: меняется каждые 6 уровней
  // палитра эпохи: [стены, крыша, окна]
  const P = [['#c9a26b', '#8a3b2a', '#ffe9a8'], ['#e6dccb', '#9b3a3a', '#ffe27a'], ['#8fa9c9', '#2d3e5c', '#e8f4ff'],
             ['#7e8aa0', '#171c2b', '#59d0ff'], ['#b48cff', '#2a1560', '#7ff0ff']][era - 1];
  const floors = Math.min(1 + Math.ceil(lv / 3), 11);             // этажей: растёт с уровнем, максимум 11
  const fh = floors > 7 ? 20 : 26;                                // высота этажа
  const w = 96 + Math.min(lv, 14) * 6, x = 150 - w / 2;           // ширина здания и левая граница (по центру)
  const roofY = 262 - floors * fh;                                // Y верхней точки стен
  const cols = 2 + Math.min(3, Math.floor(lv / 6));               // окон в ряду
  let o = `<defs><linearGradient id="sk" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${era > 3 ? '#0b0630' : '#2a1d6e'}"/><stop offset="1" stop-color="#ff7ad9"/></linearGradient></defs>`
        + `<rect width="300" height="290" rx="22" fill="url(#sk)"/>`;                                   // небо
  for (let i = 0; i < 18; i++) o += `<circle cx="${(i * 97) % 290 + 5}" cy="${(i * 53) % 120 + 8}" r="${i % 3 ? 1 : 1.8}" fill="#fff" opacity=".8"/>`; // звёзды
  o += `<circle cx="245" cy="48" r="20" fill="${era > 3 ? '#7ff0ff' : '#fff3b0'}" opacity=".9"/>`;      // луна / солнце
  if (era === 5) o += `<ellipse cx="150" cy="${roofY - 10}" rx="${w / 2 + 40}" ry="16" fill="none" stroke="#7ff0ff" stroke-width="2" opacity=".7"/>`; // орбитальное кольцо
  for (let f = 0; f < floors; f++) {                              // этажи снизу вверх
    const y = 262 - (f + 1) * fh;
    o += `<rect x="${x}" y="${y}" width="${w}" height="${fh}" fill="${P[0]}" stroke="#0004"/>`;
    for (let c = 0; c < cols; c++)                                // окна (часть «не горит» для живости)
      o += `<rect x="${x + 10 + c * (w - 20) / cols + 3}" y="${y + 5}" width="${(w - 20) / cols - 10}" height="${fh - 10}" rx="${era > 2 ? 1 : 3}" fill="${P[2]}" opacity="${(f * 7 + c * 3) % 5 ? 1 : .35}"/>`;
  }
  if (era < 3) {                                                  // эпохи 1–2: двускатная крыша (во 2-й ещё и труба)
    o += `<polygon points="${x - 10},${roofY} 150,${roofY - 34 - lv * 2} ${x + w + 10},${roofY}" fill="${P[1]}"/>`;
    if (era === 2) o += `<rect x="${x + w - 28}" y="${roofY - 40}" width="12" height="30" fill="#6b4a3a"/>`;
  } else if (era === 3) o += `<rect x="${x - 6}" y="${roofY - 8}" width="${w + 12}" height="10" fill="${P[1]}"/><rect x="${x + 14}" y="${roofY - 22}" width="${w - 28}" height="14" fill="${P[0]}" stroke="#0004"/>`; // плоская крыша с надстройкой
  else if (era === 4) o += `<rect x="146" y="${roofY - 46}" width="8" height="46" fill="#aab"/><circle cx="150" cy="${roofY - 48}" r="5" fill="#ff4d4d"/><rect x="${x}" y="${roofY - 6}" width="${w}" height="8" fill="${P[1]}"/>`;  // антенна
  else o += `<path d="M${x},${roofY} Q150,${roofY - 70} ${x + w},${roofY}Z" fill="${P[1]}" opacity=".95"/><circle cx="150" cy="${roofY - 44}" r="7" fill="#ffd400"/>`;                                          // купол
  o += `<rect x="136" y="238" width="28" height="24" rx="3" fill="#1d0f3f"/>`                                // дверь
     + `<rect x="0" y="262" width="300" height="28" fill="#1b9d62"/><rect x="0" y="262" width="300" height="5" fill="#48ff9b"/>`; // земля
  return `<svg viewBox="0 0 300 290">${o}</svg>`;
}

/* ---------- 5. Экраны ---------- */
const NAV = [['home', '🏠', 'Дом'], ['games', '🎮', 'Игры'], ['cases', '📦', 'Кейсы'], ['top', '🏆', 'Топ'], ['shop', '⭐', 'Магазин'], ['profile', '👤', 'Я']];

/** Перерисовывает шапку с балансом, нижнее меню и текущий экран. */
function paint() {
  if (!S) return;
  document.body.classList.toggle('adm', tab === 'admin');
  $('coins').textContent = inf(S.player.coins);
  $('gems').textContent = inf(S.gems);
  const items = S.is_admin ? [...NAV, ['admin', '🛡️', 'Админ']] : NAV;
  $('nav').innerHTML = items.map(([k, i, t]) => `<button class="${k === tab ? 'on' : ''}" onclick="go('${k}')"><b>${i}</b>${t}</button>`).join('');
  const views = {home: homeV, games: gamesV, cases: casesV, top: topV, shop: shopV, profile: profileV, admin: () => window.Admin ? Admin.view() : '<div class="panel splash"><div class="spin"></div>Загрузка панели…</div>'};
  $('view').innerHTML = views[tab]();
}

/** Главная: дом, доход, прокачка, быстрые кнопки. */
function homeV() {
  const h = S.house;
  const upgrade = h.next_cost
    ? `<p class="m">Уровень ${h.level + 1}: доход $${fmt(h.next_income)}/час</p>
       <div class="row"><button class="ghost" style="flex:1;padding:15px" onclick="upgrade()" ${S.player.coins < h.next_cost ? 'disabled' : ''}>За $${fmt(h.next_cost)}</button>
       <button style="flex:1;padding:15px" onclick="go('shop')">За ⭐${h.next_stars}</button></div>`
    : '<p>👑 Максимальный уровень!</p>';
  return `<div class="panel house">${houseSvg(h.level)}
      <h2 style="margin:10px 0 4px">${esc(h.name)} · уровень ${h.level} / ${h.max}</h2>
      <div class="prog"><i style="width:${h.level / h.max * 100}%"></i></div>
      <p class="m">Доход: <b>$${fmt(h.income)}</b>/час${S.car ? ` (🚗 +$${fmt(S.car.bonus)})` : ''} · копится до ${h.cap_hours} ч</p></div>
    <div class="panel"><h2>💵 Доход (в реальном времени)</h2><div class="income">$<span id="pend">${fmt(h.pending)}</span></div>
      <button id="claim" class="full" onclick="claim()">Забрать</button></div>
    <div class="panel"><h2>⬆️ Прокачка</h2>${upgrade}</div>
    <div class="cards">
      <div class="card" onclick="go('games')"><i>🎮</i>Играть</div>
      <div class="card" onclick="go('cases')"><i>📦</i>Кейсы</div>
      <div class="card" onclick="daily()"><i>🎁</i>Бонус<small>${S.daily_ready ? `$${100 * h.level} + ⭐1` : 'завтра'}</small></div>
      <div class="card" onclick="go('top')"><i>🏆</i>Рейтинг</div></div>`;
}

/** Меню игр и подэкраны «Стройка» / «Мины». */
function gamesV() {
  const back = `<button class="ghost sm" onclick="sub=null;paint()">← Игры</button>`;
  if (sub === 'work') return back + workV();
  if (sub === 'mines') return back + minesV();
  return `<div class="panel"><h2>🎮 Меню игр</h2><div class="cards">
    <div class="card" onclick="sub='mines';paint()"><i>💣</i>Мины<small>ставки до $50 000</small></div>
    <div class="card" onclick="sub='work';paint()"><i>🔨</i>Стройка<small>кликер, энергия</small></div>
    <div class="card" onclick="go('cases')"><i>📦</i>Кейсы<small>выбей машину</small></div>
    <div class="card" onclick="daily()"><i>🎁</i>Бонус<small>каждый день</small></div></div></div>`;
}

/** Кликер: тап = (1 + уровень дома) долларов, тратит энергию. */
function workV() {
  return `<div class="panel"><h2>🔨 Стройка</h2><p class="m">Тап = $${1 + S.house.level}. Энергия ${S.energy}/${S.max_energy}</p>
    <div class="prog"><i style="width:${S.energy / S.max_energy * 100}%"></i></div>
    <button class="full" onclick="tapWork()" ${S.energy < 1 ? 'disabled' : ''}>🔨 РАБОТАТЬ</button></div>`;
}

/** «Мины»: настройка ставки, поле 5×5, кнопка «Забрать». */
function minesV() {
  const playing = game?.status === 'playing', m = cfg.m;
  const lastOpened = game?.order?.[game.order.length - 1];        // последняя открытая клетка — подсветим, если на ней мина
  const cells = game ? game.cells.map((c, i) =>
    `<button class="cell ${c === 'closed' ? '' : c} ${game.status === 'lost' && i === lastOpened ? 'hit' : ''}" onclick="openCell(${i})" ${c !== 'closed' || !playing ? 'disabled' : ''}>${c === 'mine' ? '💣' : c === 'safe' ? '💎' : ''}</button>`).join('') : '';
  const setup = playing ? '' : `<div class="panel"><h2>⚙️ Настройка</h2><p class="m">Ставка ($)</p>
    <div class="row">${BETS.map(b => `<button class="chip ${cfg.bet === b ? 'on' : ''}" onclick="cfg.bet=${b};paint()">${fmt(b)}</button>`).join('')}</div>
    <p class="m" style="margin-top:12px">Мин на поле: <b id="mc">${m}</b> · коэффициент за 1-ю клетку: <b id="mm" class="ok">x${mult(1, m)}</b></p>
    <input type="range" min="1" max="20" value="${m}" oninput="cfg.m=+this.value;$('mc').textContent=this.value;$('mm').textContent='x'+mult(1,+this.value)">
    <button class="full" style="margin-top:12px" onclick="startMines()" ${S.player.coins < cfg.bet ? 'disabled' : ''}>Играть на $${fmt(cfg.bet)}</button>
    <p class="m">Проигрыш — ставка сгорает. Забрать выигрыш можно после любой открытой клетки.</p></div>`;
  const info = !game ? '' : playing
    ? `<p>Коэф. <b class="ok">x${game.mult}</b> · следующий x${game.next ?? '—'} · мин: ${game.mines}</p>
       <button class="full" onclick="cash()">${game.opened ? `Забрать $${fmt(game.payout)}` : 'Вернуть ставку'}</button>`
    : game.status === 'lost' ? `<p class="bad">💣 Мина! Ставка $${fmt(game.bet)} сгорела.</p>` : `<p class="ok">🏆 Забрано $${fmt(game.payout)} (x${game.mult})</p>`;
  return `${setup}${game ? `<div class="panel"><h2>💣 Мины · ставка $${fmt(game.bet)}</h2>${info}<div class="grid">${cells}</div></div>` : ''}`;
}

/** Магазин: уровень за звёзды и обмен ⭐ → $. */
function shopV() {
  const h = S.house, rate = 500 * h.level;
  return `<div class="panel"><h2>⭐ Магазин</h2><p class="m">У тебя ⭐${inf(S.gems)}. Звёзды можно получать ежедневным бонусом.</p></div>
    <div class="panel"><h2>🏠 Уровень дома</h2>${h.next_stars
      ? `<p class="m">Сейчас ${h.level} ур. → ${h.level + 1} ур.</p><button class="full" onclick="buyLevel()" ${S.gems < h.next_stars ? 'disabled' : ''}>Купить за ⭐${h.next_stars}</button>`
      : '<p>Максимум!</p>'}</div>
    <div class="panel"><h2>💱 Обмен ⭐ → $</h2><p class="m">Курс: 1 ⭐ = $${fmt(rate)} (растёт с уровнем дома)</p>
      <div class="row">${[1, 5, 10, 50].map(n => `<button class="ghost" onclick="conv(${n})" ${S.gems < n ? 'disabled' : ''}>${n} ⭐ → $${fmt(n * rate)}</button>`).join('')}</div></div>`;
}

/** Профиль: статистика, аватар, ник. */
function profileV() {
  const p = S.player;
  return `<div class="panel" style="text-align:center"><div style="font-size:60px">${esc(S.avatar)}</div><h2>${esc(p.nickname)}</h2><p class="m">ID: ${p.telegram_id}</p></div>
    <div class="panel"><h2>📊 Статистика</h2><div class="row">${[['🏠 Дом', S.house.level + ' ур.'], ['🎮 Игр', p.games_played], ['🏆 Побед', p.games_won]].map(([a, b]) => `<span class="tag">${a}: <b>${b}</b></span>`).join('')}</div></div>
    <div class="panel"><h2>🎭 Аватар</h2><div class="row">${AVATARS.map(a => `<button class="${a === S.avatar ? '' : 'ghost'}" style="font-size:22px" onclick="post('avatar',{avatar:'${a}'})">${a}</button>`).join('')}</div></div>
    <div class="panel"><h2>✏️ Ник</h2><div class="row"><input id="nick" maxlength="24" placeholder="Ник (пусто — имя Telegram)" value="${esc(p.custom_nickname || '')}"><button onclick="saveNick()">Сохранить</button></div></div>`;
}

/* ---------- 6. Действия (вызываются из onclick) ---------- */
/** Переход между вкладками + подгрузка данных нужной вкладки. */
async function go(t) {
  tab = t; sub = null; drop = null; paint();
  if (t === 'games') run(async () => { game = (await api('/api/bh/mines')).game; paint(); });
  if (t === 'cases') run(async () => { gar = await api('/api/bh/garage'); paint(); });
  if (t === 'top') loadTop(topBy);
  if (t === 'admin') run(async () => {
    if (!window.Admin) await loadScript('admin.js?v=' + VER);   // админ-код грузим только админу и только когда он нужен
    await Admin.load();
  });
}
const loadTop = by => run(async () => {
  topBy = by; topQ = $('topq')?.value ?? topQ; top = null; paint();
  top = await api(`/api/bh/top?by=${by}&q=${encodeURIComponent(topQ)}`); paint();
});
const claim = () => post('claim').then(r => r?.got && note(`+$${fmt(r.got)}`));            // забрать доход
const upgrade = () => post('upgrade').then(r => r && note('🎉 Дом улучшен!'));            // улучшить дом за $
const buyLevel = () => post('buylevel').then(r => r && note('🎉 Уровень куплен!'));       // улучшить дом за ⭐
const daily = () => post('daily').then(r => r && note(`🎁 +$${fmt(r.got)} и ⭐1`));        // ежедневный бонус
const conv = n => post('convert', {stars: n}).then(r => r && note(`+$${fmt(r.got)}`));     // обмен звёзд
const startMines = () => post('mines/start', {bet: cfg.bet, mines: cfg.m});                // начать игру в мины
const openCell = i => post('mines/open', {cell: i});                                       // открыть клетку
const cash = () => post('mines/cash').then(r => r && note('✅ Готово'));                   // забрать выигрыш
const refreshGarage = async () => { gar = await api('/api/bh/garage'); paint(); };         // обновить гараж
const openCase = c => post('case', {case: c}).then(r => { if (r) { drop = r.car; run(refreshGarage); } });
const sell = id => post('sell', {id}).then(r => { if (r) { note(`+$${fmt(r.got)}`); run(refreshGarage); } });
const park = id => post('park', {id}).then(r => { if (r) run(refreshGarage); });
const saveNick = () => run(async () => {                                                  // сохранить ник
  setS(await api('/api/nickname', {nickname: $('nick').value})); note('✅ Ник сохранён'); paint();
});

/** Кликер: тапы применяются сразу на экране, а на сервер уходят пачкой раз в 0.4 с. */
function tapWork() {
  if (S.energy < 1) return;
  tapN++; S.energy--; S.player.coins += 1 + S.house.level; paint();
  clearTimeout(tapT);
  tapT = setTimeout(() => {
    const n = tapN; tapN = 0;
    run(async () => { setS(await api('/api/bh/tap', {n})); paint(); });
  }, 400);
}

/** Доход дома «тикает» каждую секунду: пересчитываем сумму и обновляем кнопку «Забрать». */
setInterval(() => {
  if (!S || tab !== 'home') return;
  const h = S.house;
  const p = Math.min(h.pending + h.income / 3600 * (Date.now() - S.t0) / 1000, h.income * h.cap_hours);
  const e = $('pend'); if (e) e.textContent = fmt(Math.floor(p));
  const b = $('claim'); if (b) { b.disabled = p < 1; b.textContent = `Забрать $${fmt(Math.floor(p))}`; }
}, 1000);

boot();   // старт приложения

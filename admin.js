/* ============================================================ BuildHouse — админ-панель (клиент)
   Загружается только администратору (см. go('admin') в app.js). Использует глобальные $, api, esc, fmt, note, ask, run, paint.
   Вкладки: Сводка · Игроки (поиск/фильтры/сортировка/страницы + карточка) · Рассылка · Журнал. */
window.Admin = (() => {
  const PAGE = 25;                                   // игроков на странице
  // Состояние панели
  const A = {sub: 'dash', stats: null, list: null, q: '', flt: 'all', sort: 'last_seen', page: 0,
             card: null, log: null, bc: null, bcText: '', timer: null};

  /* ---------- утилиты ---------- */
  const enc = encodeURIComponent;
  /** «5 мин назад», «3 ч назад»… */
  const ago = ts => {
    if (!ts) return '—';
    const d = Math.floor(Date.now() / 1000) - ts;
    return d < 60 ? 'сейчас' : d < 3600 ? Math.floor(d / 60) + ' мин назад' : d < 86400 ? Math.floor(d / 3600) + ' ч назад' : Math.floor(d / 86400) + ' дн назад';
  };
  const date = ts => ts ? new Date(ts * 1000).toLocaleString('ru-RU') : '—';
  const ACT_NAMES = {coins_add: '± доллары', coins_set: '= доллары', gems_add: '± звёзды', gems_set: '= звёзды', house_add: '± уровень дома',
    house_set: '= уровень дома', give_car: 'подарок: машина', clear_garage: 'очистка гаража', block: 'блокировка', unblock: 'разблокировка',
    refill_energy: 'энергия', daily_reset: 'сброс бонуса', end_game: 'сброс игры', reset: 'СБРОС АККАУНТА', message: 'сообщение', broadcast: 'рассылка'};

  /** Перерисовка с сохранением прокрутки окна игрока и текста рассылки (чтобы не «прыгало»). */
  function repaint() {
    if ($('bc_text')) A.bcText = $('bc_text').value;
    const before = document.querySelector('.modal')?.scrollTop || 0;
    paint();
    const modal = document.querySelector('.modal');
    if (modal) modal.scrollTop = before;
  }
  const syncQ = () => { if ($('a_q')) A.q = $('a_q').value.trim(); };   // запоминаем введённый поиск

  /* ---------- загрузка данных вкладок ---------- */
  const loaders = {
    dash: async deep => { A.stats = await api('/api/admin/stats' + (deep ? '?deep=true' : ''), undefined, {timeout: 30000}); },
    players: async () => { A.list = await api(`/api/admin/players?q=${enc(A.q)}&flt=${A.flt}&sort=${A.sort}&offset=${A.page * PAGE}&limit=${PAGE}`); },
    bc: async () => { A.bc = await api('/api/admin/broadcast'); pollBc(); },
    log: async () => { A.log = (await api('/api/admin/log?limit=60')).log; },
  };
  /** Загружает данные текущей вкладки и перерисовывает панель. */
  async function load(deep = false) {
    repaint();                                                    // сразу показываем «Загрузка…»
    await run(async () => {
      if (!A.stats && A.sub !== 'dash') await loaders.dash();     // каталог машин нужен для карточки игрока
      await loaders[A.sub](deep);
    });
    repaint();
  }
  const setSub = k => { syncQ(); A.sub = k; load(); };

  /* ---------- вкладка «Сводка» ---------- */
  function dashV() {
    if (!A.stats) return '<div class="panel splash"><div class="spin"></div>Загрузка…</div>';
    const {stats: s, checks, info, rows, db_ms} = A.stats;
    const kpi = (a, b) => `<div><small>${a}</small><b>${b}</b></div>`;
    const maxLv = Math.max(1, ...Object.values(s.levels));
    const icon = {ok: 'OK', warn: 'ВНИМАНИЕ', fail: 'ОШИБКА', skip: '—'};
    return `<div class="panel"><h2>Сводка</h2><div class="kpi">
        ${kpi('Игроков', fmt(s.players))}${kpi('Онлайн (15 мин)', fmt(s.online_15m))}${kpi('Активны 24 ч', fmt(s.active_24h))}${kpi('Новые 24 ч', fmt(s.new_24h))}
        ${kpi('Заблокировано', fmt(s.blocked))}${kpi('$ в игре', fmt(s.coins_total))}${kpi('⭐ в игре', fmt(s.gems_total))}
        ${kpi('Игр / побед', fmt(s.games_played) + ' / ' + fmt(s.games_won))}${kpi('Тапов', fmt(s.taps))}${kpi('Машин', fmt(s.cars))}</div></div>
      <div class="panel"><h2>Дома по уровням</h2><div class="bars">${Object.entries(s.levels).map(([lv, n]) =>
        `<div><span>Уровень ${lv}</span><i style="width:${n / maxLv * 60}%"></i><em>${n}</em></div>`).join('') || '<p class="m">Нет данных</p>'}</div></div>
      <div class="panel"><h2>Диагностика · БД ${db_ms} мс</h2><div class="chk-grid">${checks.map(c =>
        `<div class="chk ${c.s}"><b>${esc(c.n)}<span class="m">${icon[c.s] || ''}</span></b><small>${esc(c.d)}</small></div>`).join('')}</div>
        <div class="row" style="margin-top:10px"><button onclick="Admin.load()">Обновить</button><button class="ghost" onclick="Admin.load(true)">Глубокая проверка БД</button></div></div>
      <div class="panel"><h2>Система</h2>${Object.entries(info).map(([k, v]) => `<div class="m">${esc(k)}: <b style="color:var(--t)">${esc(v)}</b></div>`).join('')}
        <div class="m" style="margin-top:6px">Записей: ${Object.entries(rows).map(([k, v]) => `${esc(k)} ${v}`).join(' · ')}</div></div>`;
  }

  /* ---------- вкладка «Игроки» ---------- */
  function playersV() {
    const L = A.list;
    const flts = [['all', 'Все'], ['online', '🟢 Онлайн'], ['blocked', '🚫 Заблок.'], ['new', '🆕 Новые']];
    const sorts = [['last_seen', 'По активности'], ['coins', 'По $'], ['gems', 'По ⭐'], ['house', 'По дому'], ['earned', 'По заработку'], ['created_at', 'По регистрации']];
    const bar = `<div class="panel"><h2>👥 Игроки${L ? ` · ${fmt(L.total)}` : ''}</h2>
      <div class="row"><input id="a_q" placeholder="Поиск: ID, имя, ник" value="${esc(A.q)}" onkeydown="if(event.key==='Enter')Admin.search()"><button onclick="Admin.search()">Найти</button></div>
      <div class="row" style="margin-top:8px">${flts.map(([k, t]) => `<button class="chip sm ${A.flt === k ? 'on' : ''}" onclick="Admin.setFlt('${k}')">${t}</button>`).join('')}
        <select style="width:auto" onchange="Admin.setSort(this.value)">${sorts.map(([k, t]) => `<option value="${k}" ${A.sort === k ? 'selected' : ''}>${t}</option>`).join('')}</select></div>`;
    if (!L) return bar + '<div class="splash"><div class="spin"></div></div></div>';
    const rows = L.players.map(p => `<div class="prow ${p.blocked ? 'bl' : ''}" onclick="Admin.open(${p.telegram_id})">
        <span class="av">${esc(p.avatar || '🏠')}</span>
        <div class="grow"><b>${esc(p.nickname || p.telegram_name)}${p.blocked ? ' 🚫' : ''}${p.telegram_id === L.admin_id ? ' 🛡️' : ''}</b>
          <span class="m">ID ${p.telegram_id} · дом ${p.house ?? 1} · ⭐${fmt(p.gems)}</span></div>
        <div class="r"><b>$${p.coins >= 1e14 ? '∞' : fmt(p.coins)}</b><div class="m">${ago(p.last_seen)}</div></div></div>`).join('')
      || '<p class="m">Никого не нашли</p>';
    const from = L.total ? A.page * PAGE + 1 : 0, to = Math.min(L.total, (A.page + 1) * PAGE);
    return `${bar}${rows}<div class="pager"><button class="ghost sm" onclick="Admin.page(-1)" ${A.page === 0 ? 'disabled' : ''}>← Назад</button>
      <span class="m">${from}–${to} из ${fmt(L.total)}</span><button class="ghost sm" onclick="Admin.page(1)" ${to >= L.total ? 'disabled' : ''}>Далее →</button></div></div>`;
  }
  const search = () => { syncQ(); A.page = 0; load(); };
  const setFlt = f => { syncQ(); A.flt = f; A.page = 0; load(); };
  const setSort = s => { syncQ(); A.sort = s; A.page = 0; load(); };
  const page = d => { syncQ(); A.page = Math.max(0, A.page + d); load(); };

  /* ---------- карточка игрока (всплывающее окно) ---------- */
  async function open(id) { await run(async () => { A.card = await api('/api/admin/player?id=' + id); }); repaint(); }
  const close = () => { A.card = null; repaint(); };
  /** Перечитывает карточку и список после действия. */
  async function refresh() {
    A.card = await api('/api/admin/player?id=' + A.card.telegram_id);
    if (A.sub === 'players') await loaders.players();
  }

  function cardV() {
    const c = A.card, id = c.telegram_id, self = c.is_admin;
    const kv = (k, v) => `<div><small>${k}</small>${v}</div>`;
    const fld = (label, key) => `<div class="fld"><span class="m">${label}</span><input id="ac_${key}" type="number" inputmode="numeric" placeholder="число (минус — списать)">
        <button class="sm" onclick="Admin.actInput(${id},'${key}_add')">＋</button><button class="ghost sm" onclick="Admin.actInput(${id},'${key}_set')">＝</button></div>`;
    const cat = A.stats?.catalog || [];
    return `<div class="modal" onclick="if(event.target===this)Admin.close()"><div>
      <div class="row"><div style="flex:1;min-width:0"><h3>${esc(c.avatar || '🏠')} ${esc(c.nickname || c.telegram_name)}${self ? ' 🛡️' : ''}</h3>
        <span class="m">${esc(c.telegram_name)} · ID ${id}</span></div><button class="ghost sm" onclick="Admin.close()">✕</button></div>
      ${c.blocked ? `<p class="bad">🚫 Заблокирован${c.reason ? ': ' + esc(c.reason) : ''}</p>` : ''}
      <div class="kv">${kv('Доллары', '$' + (c.coins >= 1e14 ? '∞' : fmt(c.coins)))}${kv('Звёзды', '⭐' + (c.gems >= 1e14 ? '∞' : fmt(c.gems)))}
        ${kv('Дом', `${c.house ?? 1} ур. · ${esc(c.house_name)}`)}${kv('Энергия', Math.round(c.energy ?? 0))}${kv('Игр / побед', `${c.games_played} / ${c.games_won}`)}
        ${kv('Тапов', fmt(c.taps))}${kv('Заработано', '$' + fmt(c.earned))}${kv('Машин', c.cars_total)}${kv('Регистрация', date(c.created_at))}
        ${kv('Был онлайн', ago(c.last_seen))}${kv('Бонус дня', Date.now() / 1000 - c.last_daily >= 86400 ? 'доступен' : 'получен')}
        ${kv('Мины', c.game ? `ставка $${fmt(c.game.bet)}, мин ${c.game.mines}, ${esc(c.game.status)}` : '—')}</div>
      <h2>Баланс и дом</h2>${fld('$', 'coins')}${fld('⭐', 'gems')}${fld('Дом', 'house')}
      <div class="acts"><button class="sm" onclick="Admin.act(${id},'coins_add','10000')">+$10k</button><button class="sm" onclick="Admin.act(${id},'coins_add','1000000')">+$1M</button>
        <button class="sm" onclick="Admin.act(${id},'gems_add','10')">+⭐10</button><button class="sm" onclick="Admin.act(${id},'gems_add','100')">+⭐100</button>
        <button class="sm" onclick="Admin.act(${id},'house_add','1')">Дом +1</button>
        <button class="ghost sm" onclick="Admin.act(${id},'refill_energy')">⚡ Энергия</button><button class="ghost sm" onclick="Admin.act(${id},'daily_reset')">🎁 Сброс бонуса</button>
        <button class="ghost sm" onclick="Admin.act(${id},'end_game')">💣 Сброс игры</button></div>
      <h2 style="margin-top:14px">Гараж</h2>
      ${c.cars.map(x => `<div class="m">${x.parked ? '🅿️' : '🚗'} ${esc(x.name)} · $${fmt(x.value)}</div>`).join('') || '<p class="m">Гараж пуст</p>'}
      <div class="row" style="margin-top:8px"><select id="ac_car"><option value="">🎲 Случайная машина</option>${cat.map(x => `<option value="${x.idx}">${esc(x.name)} — $${fmt(x.value)}</option>`).join('')}</select>
        <button class="sm" onclick="Admin.act(${id},'give_car',$('ac_car').value)">Подарить</button></div>
      <h2 style="margin-top:14px">Блокировка</h2>
      <div class="row"><input id="ac_reason" maxlength="100" placeholder="Причина (необязательно)" value="${esc(c.reason || '')}">
        ${c.blocked ? `<button class="sm" onclick="Admin.act(${id},'unblock')">Разблокировать</button>`
                    : `<button class="red sm" onclick="Admin.act(${id},'block',$('ac_reason').value)" ${self ? 'disabled' : ''}>Заблокировать</button>`}</div>
      <h2 style="margin-top:14px">Сообщение от бота</h2>
      <textarea id="ac_msg" maxlength="1000" placeholder="Текст сообщения…"></textarea>
      <button class="sm" style="margin-top:6px" onclick="Admin.sendMsg(${id})">Отправить</button>
      ${self ? '' : `<h2 style="margin-top:14px">Опасная зона</h2><div class="acts"><button class="red sm" onclick="Admin.danger(${id},'clear_garage','Очистить гараж игрока?')">Очистить гараж</button>
        <button class="red sm" onclick="Admin.danger(${id},'reset','Полностью сбросить аккаунт? Это необратимо.')">Сбросить аккаунт</button></div>`}
    </div></div>`;
  }

  /** Выполняет действие над игроком и обновляет карточку. v — значение (число / ID машины / причина). */
  async function act(id, a, v = '') {
    await run(async () => {
      await api('/api/admin/act', {telegram_id: id, act: a, value: String(v ?? '')});
      note('✅ Готово');
      await refresh();
      if (id === S.player.telegram_id) setS(await api('/api/bh/state'));   // если правим себя — обновляем и свой баланс
    });
    repaint();
  }
  /** Действие со значением из поля ввода ac_<имя>. */
  const actInput = (id, a) => {
    const v = $('ac_' + a.split('_')[0]).value.trim();
    if (v === '') return note('Введи число');
    act(id, a, v);
  };
  /** Опасное действие — с подтверждением. */
  const danger = async (id, a, text) => { if (await ask(text)) act(id, a); };
  async function sendMsg(id) {
    const text = $('ac_msg').value.trim();
    if (!text) return note('Введи текст');
    await run(async () => { await api('/api/admin/message', {telegram_id: id, text}); note('✅ Отправлено'); $('ac_msg').value = ''; });
  }

  /* ---------- вкладка «Рассылка» ---------- */
  function bcV() {
    const b = A.bc, pct = b && b.total ? Math.round((b.sent + b.failed) / b.total * 100) : 0;
    return `<div class="panel"><h2>📣 Рассылка всем игрокам</h2>
      <p class="m">Получат все не заблокированные игроки (кто не останавливал бота). Скорость — около 20 сообщений в секунду.</p>
      <textarea id="bc_text" maxlength="1000" placeholder="Текст сообщения…">${esc(A.bcText)}</textarea>
      <button class="full" style="margin-top:8px" onclick="Admin.sendBc()" ${b?.running ? 'disabled' : ''}>${b?.running ? 'Идёт рассылка…' : 'Отправить всем'}</button>
      ${b && b.total ? `<div class="prog"><i style="width:${pct}%"></i></div><p class="m">Доставлено ${b.sent} из ${b.total} · ошибок ${b.failed}${b.running ? '' : ' · завершено'}</p>` : ''}</div>`;
  }
  async function sendBc() {
    const text = $('bc_text').value.trim();
    if (!text) return note('Введи текст');
    if (!await ask('Отправить сообщение ВСЕМ игрокам?')) return;
    await run(async () => {
      const r = await api('/api/admin/broadcast', {text});
      A.bcText = ''; note(`✅ Рассылка запущена: ${r.total} чел.`);
      A.bc = await api('/api/admin/broadcast'); pollBc();
    });
    repaint();
  }
  /** Пока рассылка идёт и открыта её вкладка — раз в 2 с обновляем прогресс. */
  function pollBc() {
    clearTimeout(A.timer);
    if (A.sub !== 'bc' || tab !== 'admin' || !A.bc?.running) return;
    A.timer = setTimeout(async () => {
      await run(async () => { A.bc = await api('/api/admin/broadcast'); });
      repaint(); pollBc();
    }, 2000);
  }

  /* ---------- вкладка «Журнал» ---------- */
  function logV() {
    if (!A.log) return '<div class="panel splash"><div class="spin"></div></div>';
    return `<div class="panel"><h2>📜 Журнал действий</h2>${A.log.length ? `<table class="log">${A.log.map(l =>
      `<tr><td class="m">${date(l.ts)}</td><td>${l.target ? 'ID ' + l.target : 'все'}</td><td><b>${esc(ACT_NAMES[l.action] || l.action)}</b></td><td class="m">${esc(l.value || '')}</td></tr>`).join('')}</table>`
      : '<p class="m">Пока пусто</p>'}<button class="ghost sm" style="margin-top:10px" onclick="Admin.load()">Обновить</button></div>`;
  }

  /* ---------- главный экран панели ---------- */
  function view() {
    const tabs = [['dash', '📊 Сводка'], ['players', '👥 Игроки'], ['bc', '📣 Рассылка'], ['log', '📜 Журнал']];
    const nav = `<div class="sub">${tabs.map(([k, t]) => `<button class="chip ${A.sub === k ? 'on' : ''}" onclick="Admin.setSub('${k}')">${t}</button>`).join('')}</div>`;
    return nav + {dash: dashV, players: playersV, bc: bcV, log: logV}[A.sub]() + (A.card ? cardV() : '');
  }

  return {view, load, setSub, search, setFlt, setSort, page, open, close, act, actInput, danger, sendMsg, sendBc};
})();

// ВПИШИ сюда HTTPS-адрес твоего Render, БЕЗ / в конце.
// Пример: https://my-miniapp.onrender.com
const API_BASE = 'https://telegram-miniapp-i49m.onrender.com';

const tg = window.Telegram?.WebApp;
if (tg) { tg.ready(); tg.expand(); }
const $ = id => document.getElementById(id);
let currentGame = null;
let busy = false;

function status(message) { $('status').textContent = message; }
function showPlayer(p) {
  $('profile').textContent = `${p.nickname} · Telegram ID: ${p.telegram_id}`;
  $('coins').textContent = p.coins;
  $('games').textContent = p.games_played;
  $('wins').textContent = p.games_won;
  if (document.activeElement !== $('nickname')) $('nickname').value = p.custom_nickname || '';
}
async function request(path, options = {}) {
  if (!tg?.initData) throw new Error('Открой приложение через кнопку «Открыть» в Telegram, а не в обычном браузере.');
  if (API_BASE.includes('YOUR-SERVICE')) throw new Error('Укажи настоящий адрес Render в первой строке app.js');
  let response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method: options.method || 'GET',
      headers: { 'X-Telegram-Init-Data': tg.initData, 'Content-Type': 'application/json' },
      body: options.body ? JSON.stringify(options.body) : undefined
    });
  } catch (_) { throw new Error('Нет подключения к API. Проверь адрес Render, WEBAPP_URL и доступность сервера.'); }
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || `Ошибка сервера ${response.status}`);
  return result;
}
function draw(game) {
  currentGame = game;
  const grid = $('grid');
  grid.innerHTML = '';
  for (let index = 0; index < 25; index++) {
    const cell = game?.cells[index] || {state:'closed'};
    const btn = document.createElement('button');
    btn.className = `cell ${cell.state === 'closed' ? '' : cell.state}`;
    btn.textContent = cell.state === 'mine' ? '💣' : cell.state === 'safe' ? (cell.around || '✓') : '◆';
    btn.setAttribute('aria-label', `Клетка ${index + 1}`);
    btn.disabled = busy || cell.state !== 'closed' || game?.status !== 'playing';
    btn.addEventListener('click', () => openCell(index));
    grid.appendChild(btn);
  }
  $('new-game').disabled = busy || game?.status === 'playing';
  if (!game) status('Нажми «Начать новую игру».');
  else if (game.status === 'playing') status(`Открыто ${game.opened} из 20 безопасных клеток`);
  else if (game.status === 'won') status('🏆 Победа! Получено +50 игровых монет.');
  else status('💣 Попалась мина. Монеты не списаны.');
}
async function load() {
  try {
    const [a, b] = await Promise.all([request('/api/profile'), request('/api/mines')]);
    showPlayer(a.player); draw(b.game);
  } catch (e) { $('profile').textContent = 'Не удалось загрузить профиль'; status('⚠️ ' + e.message); }
}
async function openCell(index) {
  if (busy) return;
  busy = true; draw(currentGame);
  try {
    const data = await request('/api/mines/open', {method:'POST', body:{cell:index}});
    showPlayer(data.player); currentGame = data.game;
  } catch(e) { status('⚠️ ' + e.message); }
  finally { busy = false; draw(currentGame); }
}
$('new-game').addEventListener('click', async () => {
  if (busy) return;
  busy = true; draw(currentGame);
  try {
    const data = await request('/api/mines/new', {method:'POST'});
    currentGame = data.game; showPlayer(data.player);
  } catch(e) { status('⚠️ ' + e.message); }
  finally { busy = false; draw(currentGame); }
});
$('nickname-form').addEventListener('submit', async event => {
  event.preventDefault();
  try {
    const data = await request('/api/nickname', {method:'POST',body:{nickname:$('nickname').value}});
    showPlayer(data.player); status('✅ Ник сохранён в SQLite3');
  } catch(e) { status('⚠️ ' + e.message); }
});
load();

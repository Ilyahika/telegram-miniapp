const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();
const $ = id => document.getElementById(id);
const status = text => { $('status').textContent = text; };
const buttons = [$('add'), $('reset')];

async function api(path) {
  const response = await fetch(path, {
    method: path === '/api/me' ? 'GET' : 'POST',
    headers: { Authorization: `tma ${tg?.initData || ''}` }
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || 'Ошибка сервера');
  return data;
}

async function action(path) {
  buttons.forEach(button => button.disabled = true);
  try {
    const data = await api(path);
    $('count').textContent = data.clicks;
    status('Изменения сохранены в SQLite3 ✓');
    tg?.HapticFeedback?.impactOccurred('light');
  } catch (error) { status(error.message); }
  finally { buttons.forEach(button => button.disabled = false); }
}

$('add').onclick = () => action('/api/click');
$('reset').onclick = () => action('/api/reset');
$('hello').onclick = () => tg?.showAlert('🎉 Приложение работает!');
$('close').onclick = () => tg?.close();

(async () => {
  try {
    const user = await api('/api/me');
    $('name').textContent = `Привет, ${user.first_name}!`;
    $('userid').textContent = `Telegram ID: ${user.telegram_id}`;
    $('count').textContent = user.clicks;
    status('Подключено к базе данных ✓');
  } catch (error) { status(error.message); }
})();

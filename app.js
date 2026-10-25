// Если Mini App открывается с Render, ничего не меняй: оставь "".
// Если Mini App открывается с GitHub Pages, вставь сюда Render URL:
// const API_BASE = "https://имя-приложения.onrender.com";
const API_BASE = "";

const tg = window.Telegram?.WebApp;
tg?.ready();
tg?.expand();
const el = id => document.getElementById(id);
const buttons = [el("earn"), el("reset"), el("refresh")];
function status(message) { el("status").textContent = message; }
function render(player) {
  if (player.first_name != null) el("name").textContent = `Привет, ${player.first_name}!`;
  if (player.telegram_id != null) el("userid").textContent = `Telegram ID: ${player.telegram_id}`;
  if (player.clicks != null) el("clicks").textContent = player.clicks;
  if (player.coins != null) el("coins").textContent = player.coins;
}

async function api(path, method = "GET") {
  if (!tg?.initData) throw new Error("Открой Mini App через кнопку бота в Telegram");
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 25000);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      method,
      headers: { "Authorization": `tma ${tg.initData}` },
      signal: controller.signal,
    });
    const body = await response.json();
    if (!response.ok) throw new Error(body.detail || `Ошибка сервера ${response.status}`);
    return body;
  } finally { clearTimeout(timeout); }
}

async function send(path, method = "POST") {
  buttons.forEach(b => b.disabled = true);
  status("Сохранение...");
  try {
    const profile = await api(path, method);
    render(profile);
    status("✅ Данные сохранены в SQLite3");
    tg?.HapticFeedback?.impactOccurred("light");
  } catch (e) {
    status(e.name === "AbortError" ? "Сервер долго отвечает. Попробуй ещё раз." : `⚠️ ${e.message}`);
  } finally {
    buttons.forEach(b => b.disabled = false);
  }
}

el("earn").addEventListener("click", () => send("/api/click"));
el("reset").addEventListener("click", () => send("/api/reset"));
el("refresh").addEventListener("click", () => send("/api/me", "GET"));
el("close").addEventListener("click", () => tg?.close());
send("/api/me", "GET");

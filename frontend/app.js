const API = ""; // same origin

let chart, candleSeries;
let currentSymbol = "EURUSD";
let currentTimeframe = "M15";
let pollTimer, tickTimer, candleTimer;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function api(path, options = {}) {
  const res = await fetch(API + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Request failed");
  }
  return data;
}

function show(el) { el.classList.remove("hidden"); }
function hide(el) { el.classList.add("hidden"); }

// ---------------------------------------------------------------------------
// Login
// ---------------------------------------------------------------------------

const loginScreen = document.getElementById("login-screen");
const dashboard = document.getElementById("dashboard");
const loginError = document.getElementById("login-error");

document.getElementById("login-btn").addEventListener("click", async () => {
  const login = document.getElementById("login-input").value.trim();
  const password = document.getElementById("password-input").value;
  const server = document.getElementById("server-input").value.trim();

  loginError.style.display = "none";

  if (!login || !password || !server) {
    loginError.textContent = "Please fill in login, password and server.";
    loginError.style.display = "block";
    return;
  }

  try {
    const result = await api("/api/connect", {
      method: "POST",
      body: JSON.stringify({ login, password, server }),
    });
    updateAccountSummary(result.account);
    hide(loginScreen);
    show(dashboard);
    await initDashboard();
  } catch (err) {
    loginError.textContent = err.message;
    loginError.style.display = "block";
  }
});

document.getElementById("disconnect-btn").addEventListener("click", async () => {
  await api("/api/disconnect", { method: "POST" });
  clearInterval(pollTimer);
  clearInterval(tickTimer);
  clearInterval(candleTimer);
  hide(dashboard);
  show(loginScreen);
});

// ---------------------------------------------------------------------------
// Account summary
// ---------------------------------------------------------------------------

function updateAccountSummary(acc) {
  const el = document.getElementById("account-summary");
  el.innerHTML = `
    <span>Login: <b>${acc.login}</b></span>
    <span>Balance: <b>${acc.balance.toFixed(2)} ${acc.currency}</b></span>
    <span>Equity: <b>${acc.equity.toFixed(2)}</b></span>
    <span>Margin: <b>${acc.margin.toFixed(2)}</b></span>
    <span>Free margin: <b>${acc.margin_free.toFixed(2)}</b></span>
    <span>Profit: <b class="${acc.profit >= 0 ? 'pos-profit-pos' : 'pos-profit-neg'}">${acc.profit.toFixed(2)}</b></span>
  `;
}

async function refreshAccount() {
  try {
    const acc = await api("/api/account");
    updateAccountSummary(acc);
  } catch (err) {
    console.error(err);
  }
}

// ---------------------------------------------------------------------------
// Symbols + chart
// ---------------------------------------------------------------------------

async function loadSymbols() {
  const select = document.getElementById("symbol-select");
  try {
    const symbols = await api("/api/symbols");
    const common = ["EURUSD", "GBPUSD", "USDJPY", "XAUUSD", "BTCUSD"];
    const ordered = [...common.filter(s => symbols.includes(s)), ...symbols.filter(s => !common.includes(s))];
    select.innerHTML = ordered.map(s => `<option value="${s}">${s}</option>`).join("");
    if (ordered.length) currentSymbol = ordered[0];
  } catch (err) {
    console.error(err);
  }
}

function initChart() {
  const container = document.getElementById("chart");
  chart = LightweightCharts.createChart(container, {
    layout: { background: { color: "#171a21" }, textColor: "#c9cdd6" },
    grid: { vertLines: { color: "#2a2e37" }, horzLines: { color: "#2a2e37" } },
    timeScale: { timeVisible: true, secondsVisible: false },
    width: container.clientWidth,
    height: container.clientHeight,
  });
  candleSeries = chart.addCandlestickSeries({
    upColor: "#16a34a", downColor: "#dc2626",
    borderUpColor: "#16a34a", borderDownColor: "#dc2626",
    wickUpColor: "#16a34a", wickDownColor: "#dc2626",
  });
  window.addEventListener("resize", () => {
    chart.resize(container.clientWidth, container.clientHeight);
  });
}

async function refreshCandles() {
  try {
    const candles = await api(`/api/candles?symbol=${currentSymbol}&timeframe=${currentTimeframe}&count=300`);
    const formatted = candles.map(c => ({
      time: c.time, open: c.open, high: c.high, low: c.low, close: c.close,
    }));
    candleSeries.setData(formatted);
  } catch (err) {
    console.error(err);
  }
}

async function refreshTick() {
  try {
    const t = await api(`/api/tick?symbol=${currentSymbol}`);
    document.getElementById("tick-display").textContent = `bid: ${t.bid} / ask: ${t.ask}`;
  } catch (err) {
    console.error(err);
  }
}

document.getElementById("symbol-select").addEventListener("change", (e) => {
  currentSymbol = e.target.value;
  refreshCandles();
  refreshTick();
});
document.getElementById("timeframe-select").addEventListener("change", (e) => {
  currentTimeframe = e.target.value;
  refreshCandles();
});

// ---------------------------------------------------------------------------
// Positions
// ---------------------------------------------------------------------------

async function refreshPositions() {
  try {
    const positions = await api("/api/positions");
    const tbody = document.getElementById("positions-body");
    tbody.innerHTML = positions.map(p => `
      <tr>
        <td>${p.ticket}</td>
        <td>${p.symbol}</td>
        <td>${p.type_str}</td>
        <td>${p.volume}</td>
        <td>${p.price_open}</td>
        <td>${p.price_current}</td>
        <td class="${p.profit >= 0 ? 'pos-profit-pos' : 'pos-profit-neg'}">${p.profit.toFixed(2)}</td>
        <td><button class="close-btn" data-ticket="${p.ticket}">Close</button></td>
      </tr>
    `).join("");

    tbody.querySelectorAll(".close-btn").forEach(btn => {
      btn.addEventListener("click", () => closePosition(btn.dataset.ticket));
    });
  } catch (err) {
    console.error(err);
  }
}

async function closePosition(ticket) {
  try {
    await api("/api/close", { method: "POST", body: JSON.stringify({ ticket }) });
    await refreshPositions();
    await refreshAccount();
  } catch (err) {
    alert("Close failed: " + err.message);
  }
}

// ---------------------------------------------------------------------------
// Buy / Sell
// ---------------------------------------------------------------------------

function setOrderMessage(text, isError) {
  const el = document.getElementById("order-message");
  el.textContent = text;
  el.className = "order-message " + (isError ? "error" : "success");
}

async function placeOrder(side) {
  const volume = document.getElementById("volume-input").value;
  const sl = document.getElementById("sl-input").value;
  const tp = document.getElementById("tp-input").value;

  try {
    const result = await api("/api/order", {
      method: "POST",
      body: JSON.stringify({ symbol: currentSymbol, side, volume, sl, tp }),
    });
    setOrderMessage(`${side.toUpperCase()} order filled at ${result.price} (ticket ${result.order})`, false);
    await refreshPositions();
    await refreshAccount();
  } catch (err) {
    setOrderMessage(err.message, true);
  }
}

document.getElementById("buy-btn").addEventListener("click", () => placeOrder("buy"));
document.getElementById("sell-btn").addEventListener("click", () => placeOrder("sell"));

// ---------------------------------------------------------------------------
// Init
// ---------------------------------------------------------------------------

async function initDashboard() {
  initChart();
  await loadSymbols();
  document.getElementById("symbol-select").value = currentSymbol;
  await refreshCandles();
  await refreshTick();
  await refreshPositions();

  pollTimer = setInterval(() => { refreshAccount(); refreshPositions(); }, 3000);
  tickTimer = setInterval(refreshTick, 2000);
  candleTimer = setInterval(refreshCandles, 5000);
}

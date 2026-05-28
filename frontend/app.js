/**
 * ORB Dashboard — Frontend Application
 * WebSocket client + UI rendering + chart management
 */

// ─────────────────────────────────────────────────────────────────────────────
// Constants & State
// ─────────────────────────────────────────────────────────────────────────────
// Auto-detect protocol: wss:// on HTTPS (Render), ws:// on HTTP (local)
const WS_PROTOCOL = location.protocol === 'https:' ? 'wss:' : 'ws:';
const WS_URL = `${WS_PROTOCOL}//${location.host}/ws`;
const API_BASE = `${location.protocol}//${location.host}/api`;

const STOCKS = [
  { symbol: "BSE.NS",    name: "BSE Ltd",       short: "BSE"    },
  { symbol: "SUZLON.NS", name: "Suzlon Energy",  short: "SUZLON" },
  { symbol: "IFCI.NS",   name: "IFCI",           short: "IFCI"   },
  { symbol: "HFCL.NS",   name: "HFCL",           short: "HFCL"   },
  { symbol: "TMCV.NS",   name: "TMCV",           short: "TMCV"   },
];

const state = {
  ws: null,
  wsReconnectTimer: null,
  reconnectAttempts: 0,
  soundEnabled: true,
  todayAlerts: [],
  stockStates: {},
  config: { atr_length: 14, atr_multiplier: 1.0, rr_ratio: 2.0 },
  filterSymbol: '',
  filterSignal: '',
  activeTab: 'today',
};

// ─────────────────────────────────────────────────────────────────────────────
// DOM Refs
// ─────────────────────────────────────────────────────────────────────────────
const el = {
  clockTime:         document.getElementById('clockTime'),
  clockDot:          document.getElementById('clockDot'),
  clockLabel:        document.getElementById('clockLabel'),
  wsDot:             document.getElementById('wsDot'),
  wsLabel:           document.getElementById('wsLabel'),
  stockCards:        document.getElementById('stockCards'),
  alertsList:        document.getElementById('alertsList'),
  historyList:       document.getElementById('historyList'),
  emptyAlerts:       document.getElementById('emptyAlerts'),
  todayCount:        document.getElementById('todayCount'),
  marketStatusBadge: document.getElementById('marketStatusBadge'),
  toastContainer:    document.getElementById('toastContainer'),
  tabToday:          document.getElementById('tabToday'),
  tabHistory:        document.getElementById('tabHistory'),
  tabContentToday:   document.getElementById('tabContentToday'),
  tabContentHistory: document.getElementById('tabContentHistory'),
  settingsModal:     document.getElementById('settingsModal'),
  btnRefresh:        document.getElementById('btnRefresh'),
  btnSound:          document.getElementById('btnSound'),
  btnSettings:       document.getElementById('btnSettings'),
  closeSettings:     document.getElementById('closeSettings'),
  cancelSettings:    document.getElementById('cancelSettings'),
  saveSettings:      document.getElementById('saveSettings'),
  filterSymbol:      document.getElementById('filterSymbol'),
  filterSignal:      document.getElementById('filterSignal'),
  btnClearFilters:   document.getElementById('btnClearFilters'),
  historyDate:       document.getElementById('historyDate'),
  historySymbol:     document.getElementById('historySymbol'),
  btnLoadHistory:    document.getElementById('btnLoadHistory'),
  cfgAtrLength:      document.getElementById('cfgAtrLength'),
  cfgAtrMultiplier:  document.getElementById('cfgAtrMultiplier'),
  cfgRrRatio:        document.getElementById('cfgRrRatio'),
  fMultiplier:       document.getElementById('fMultiplier'),
  fRR:               document.getElementById('fRR'),
  fMultiplier2:      document.getElementById('fMultiplier2'),
  fRR2:              document.getElementById('fRR2'),
  soundIcon:         document.getElementById('soundIcon'),
};

// ─────────────────────────────────────────────────────────────────────────────
// Clock
// ─────────────────────────────────────────────────────────────────────────────
function updateClock() {
  const now = new Date();
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  const hh = String(ist.getHours()).padStart(2, '0');
  const mm = String(ist.getMinutes()).padStart(2, '0');
  const ss = String(ist.getSeconds()).padStart(2, '0');
  el.clockTime.textContent = `${hh}:${mm}:${ss}`;

  const h = ist.getHours(), m = ist.getMinutes();
  const mins = h * 60 + m;
  const day  = ist.getDay(); // 0=Sun, 6=Sat
  const isWeekday = day >= 1 && day <= 5;

  if (!isWeekday || mins < 9 * 60 + 15 || mins >= 15 * 60 + 30) {
    el.clockDot.className = 'clock-dot';
    el.clockLabel.textContent = 'Market Closed';
  } else if (mins < 9 * 60 + 45) {
    el.clockDot.className = 'clock-dot building-or';
    el.clockLabel.textContent = 'Building OR';
  } else if (mins < 15 * 60 + 15) {
    el.clockDot.className = 'clock-dot market-open';
    el.clockLabel.textContent = 'Market Open';
  } else {
    el.clockDot.className = 'clock-dot building-or';
    el.clockLabel.textContent = 'Square Off Zone';
  }
}

setInterval(updateClock, 1000);
updateClock();

// ─────────────────────────────────────────────────────────────────────────────
// Market Status Badge
// ─────────────────────────────────────────────────────────────────────────────
function updateMarketStatusBadge() {
  const now = new Date();
  const ist = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Kolkata' }));
  const h = ist.getHours(), m = ist.getMinutes();
  const mins = h * 60 + m;
  const day  = ist.getDay();
  const isWeekday = day >= 1 && day <= 5;

  if (!isWeekday || mins < 9 * 60 + 15 || mins >= 15 * 60 + 30) {
    el.marketStatusBadge.className = 'badge badge-info';
    el.marketStatusBadge.textContent = 'Market Closed';
  } else if (mins < 9 * 60 + 45) {
    el.marketStatusBadge.className = 'badge badge-warning';
    el.marketStatusBadge.textContent = '⏳ Building OR';
  } else if (mins < 15 * 60 + 15) {
    el.marketStatusBadge.className = 'badge badge-success';
    el.marketStatusBadge.textContent = '● Live Trading';
  } else {
    el.marketStatusBadge.className = 'badge badge-warning';
    el.marketStatusBadge.textContent = '⚠ Square Off Zone';
  }
}

setInterval(updateMarketStatusBadge, 10000);
updateMarketStatusBadge();

// ─────────────────────────────────────────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────────────────────────────────────────
function setWsStatus(status) {
  // status: 'connected' | 'connecting' | 'disconnected'
  el.wsDot.className = `ws-dot ${status}`;
  el.wsLabel.textContent =
    status === 'connected'    ? 'Live'         :
    status === 'connecting'   ? 'Connecting...' :
                                 'Disconnected';
}

function connectWS() {
  setWsStatus('connecting');
  const ws = new WebSocket(WS_URL);
  state.ws = ws;

  ws.onopen = () => {
    setWsStatus('connected');
    state.reconnectAttempts = 0;
    clearTimeout(state.wsReconnectTimer);
    showToast('Connected', 'Real-time data feed active', 'info');
  };

  ws.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      handleWSMessage(msg);
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };

  ws.onclose = () => {
    setWsStatus('disconnected');
    scheduleReconnect();
  };

  ws.onerror = () => {
    setWsStatus('disconnected');
  };
}

function scheduleReconnect() {
  clearTimeout(state.wsReconnectTimer);
  const delay = Math.min(2000 * Math.pow(1.5, state.reconnectAttempts), 30000);
  state.reconnectAttempts++;
  state.wsReconnectTimer = setTimeout(() => {
    if (!state.ws || state.ws.readyState === WebSocket.CLOSED) {
      connectWS();
    }
  }, delay);
}

// ─────────────────────────────────────────────────────────────────────────────
// WS Message Handlers
// ─────────────────────────────────────────────────────────────────────────────
function handleWSMessage(msg) {
  switch (msg.type) {
    case 'init':
      handleInit(msg.data);
      break;
    case 'alert':
      handleNewAlert(msg.data);
      break;
    case 'state_update':
      handleStateUpdate(msg.data.stocks);
      break;
    case 'heartbeat':
      // Silently received
      break;
    case 'day_reset':
      handleDayReset(msg.data);
      break;
    case 'day_archived':
      showToast('Day Archived', `Alerts archived for ${msg.data.date}`, 'info');
      break;
    default:
      break;
  }
}

function handleInit(data) {
  // Load today's alerts
  state.todayAlerts = data.today_alerts || [];
  if (data.config) {
    state.config = data.config;
    syncConfigUI();
  }
  // Render stock states
  if (data.stocks) {
    data.stocks.forEach(s => { state.stockStates[s.symbol] = s; });
  }
  initStockCards();
  renderAlerts();

  // Load history dates
  fetchHistoryDates();
}

function handleNewAlert(alert) {
  // Add to top of today's alerts
  state.todayAlerts.unshift(alert);
  renderAlerts();

  // Toast + sound
  const isBuy   = alert.signal_type === 'BUY';
  const isSell  = alert.signal_type === 'SELL';
  const isSL    = alert.signal_type === 'SL_HIT';
  const isTP    = alert.signal_type === 'TP_HIT';
  const isSqOff = alert.signal_type === 'SQUARE_OFF';

  const emoji = isBuy ? '📈' : isSell ? '📉' : isSL ? '🛑' : isTP ? '🎯' : '⏹';
  const title = `${emoji} ${alert.signal_type.replace('_', ' ')} — ${alert.display_name}`;

  let msg;
  if (isBuy || isSell) {
    msg = `Entry: ₹${fmt(alert.entry_price)}  SL: ₹${fmt(alert.stop_loss)}  TP: ₹${fmt(alert.target_price)}`;
  } else if (alert.pnl_points != null) {
    const sign = alert.pnl_points >= 0 ? '+' : '';
    msg = `Exit: ₹${fmt(alert.entry_price)}  P&L: ${sign}${fmt(alert.pnl_points)} pts (${sign}${alert.pnl_percent}%)`;
  } else {
    msg = `@ ₹${fmt(alert.entry_price)}`;
  }

  const toastType = isBuy ? 'buy' : isSell ? 'sell' : (alert.pnl_points >= 0 ? 'profit' : 'loss');
  showToast(title, msg, toastType);

  if (state.soundEnabled) playAlertSound(isBuy, isSell);
}

function handleStateUpdate(stocks) {
  if (!stocks) return;
  stocks.forEach(s => {
    state.stockStates[s.symbol] = s;
    updateStockCard(s);
  });
}

function handleDayReset(data) {
  state.todayAlerts = [];
  renderAlerts();
  showToast('New Day', `Market reset for ${data.date}`, 'info');
  Object.keys(state.stockStates).forEach(sym => {
    state.stockStates[sym] = {
      ...state.stockStates[sym],
      range_high: null,
      range_low: null,
      range_defined: false,
      position: 'FLAT',
      current_price: null,
    };
    updateStockCard(state.stockStates[sym]);
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// Stock Cards
// ─────────────────────────────────────────────────────────────────────────────
function initStockCards() {
  el.stockCards.innerHTML = '';
  STOCKS.forEach(stock => {
    const s = state.stockStates[stock.symbol] || {
      symbol: stock.symbol,
      display_name: stock.name,
      position: 'FLAT',
      market_status: 'CLOSED',
    };
    el.stockCards.appendChild(buildStockCard(s));
  });
}

function buildStockCard(s) {
  const card = document.createElement('div');
  card.className = `stock-card ${posClass(s.position)}`;
  card.id = `card-${s.symbol.replace('.', '-')}`;
  card.innerHTML = stockCardHTML(s);
  return card;
}

function stockCardHTML(s) {
  const priceHTML = s.current_price
    ? `<div class="stock-price">₹${fmt(s.current_price)}</div>`
    : `<div class="stock-price na">No data</div>`;

  const orHTML = `
    <div class="or-levels">
      <div class="or-level high">
        <div class="or-level-label">OR High</div>
        <div class="or-level-val">${s.range_high ? '₹' + fmt(s.range_high) : '—'}</div>
      </div>
      <div class="or-level low">
        <div class="or-level-label">OR Low</div>
        <div class="or-level-val">${s.range_low ? '₹' + fmt(s.range_low) : '—'}</div>
      </div>
    </div>`;

  const rangeBarHTML = s.range_high && s.range_low && s.current_price ? (() => {
    const pct = Math.min(100, Math.max(0,
      ((s.current_price - s.range_low) / (s.range_high - s.range_low)) * 100
    ));
    const color = pct > 50 ? 'var(--green)' : 'var(--red)';
    return `
      <div class="range-bar-wrap">
        <div class="range-bar-label"><span>Low</span><span>Price Position</span><span>High</span></div>
        <div class="range-bar-track">
          <div class="range-bar-fill" style="width:${pct.toFixed(1)}%;background:${color}"></div>
        </div>
      </div>`;
  })() : '';

  const statusClass =
    s.market_status === 'BUILDING_OR' ? 'status-building' :
    s.market_status === 'TRADING'     ? 'status-trading'  : 'status-closed';
  const statusLabel =
    s.market_status === 'BUILDING_OR' ? '⏳ Building OR' :
    s.market_status === 'TRADING'     ? '● Trading'       :
    s.market_status === 'SQUARE_OFF'  ? '⚠ Square Off'   : '○ Closed';

  return `
    <div class="stock-card-header">
      <div>
        <div class="stock-name">${s.display_name}</div>
        <div class="stock-symbol">${s.symbol}</div>
      </div>
      <span class="position-badge ${s.position.toLowerCase()}">${s.position}</span>
    </div>
    ${priceHTML}
    ${orHTML}
    ${rangeBarHTML}
    <div class="stock-meta">
      <span class="meta-pill ${statusClass}">${statusLabel}</span>
      ${s.atr ? `<span class="meta-pill">ATR: ${s.atr.toFixed(2)}</span>` : ''}
      ${s.range_defined ? '<span class="meta-pill status-trading">OR ✓</span>' : ''}
    </div>`;
}

function updateStockCard(s) {
  const card = document.getElementById(`card-${s.symbol.replace('.', '-')}`);
  if (!card) return;
  card.className = `stock-card ${posClass(s.position)}`;
  card.innerHTML = stockCardHTML(s);
}

function posClass(position) {
  if (position === 'LONG')  return 'pos-long';
  if (position === 'SHORT') return 'pos-short';
  return '';
}

// ─────────────────────────────────────────────────────────────────────────────
// Alerts Rendering
// ─────────────────────────────────────────────────────────────────────────────
function renderAlerts() {
  const filtered = state.todayAlerts.filter(a => {
    if (state.filterSymbol && a.symbol !== state.filterSymbol) return false;
    if (state.filterSignal && a.signal_type !== state.filterSignal) return false;
    return true;
  });

  el.todayCount.textContent = state.todayAlerts.length;

  if (filtered.length === 0) {
    el.alertsList.innerHTML = '';
    el.alertsList.appendChild(createEmptyState());
    return;
  }

  el.alertsList.innerHTML = filtered.map(a => alertCardHTML(a)).join('');
}

function createEmptyState() {
  const div = document.createElement('div');
  div.className = 'empty-state';
  div.innerHTML = `
    <div class="empty-icon">
      <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1">
        <path d="M18 20V10M12 20V4M6 20v-6"/>
      </svg>
    </div>
    <p>No alerts yet today</p>
    <span>Signals appear here during trading hours (9:45 AM – 3:15 PM IST)</span>`;
  return div;
}

function alertCardHTML(a) {
  const isEntry  = a.signal_type === 'BUY' || a.signal_type === 'SELL';
  const isExit   = ['SL_HIT', 'TP_HIT', 'SQUARE_OFF'].includes(a.signal_type);
  const isProfit = a.pnl_points != null && a.pnl_points >= 0;
  const isLoss   = a.pnl_points != null && a.pnl_points < 0;

  const typeClass =
    a.signal_type === 'BUY'        ? 'buy'        :
    a.signal_type === 'SELL'       ? 'sell'       :
    a.signal_type === 'SL_HIT'     ? 'sl-hit'     :
    a.signal_type === 'TP_HIT'     ? 'tp-hit'     :
    a.signal_type === 'SQUARE_OFF' ? 'square-off' : '';

  const badgeText =
    a.signal_type === 'BUY'        ? '↑ BUY'        :
    a.signal_type === 'SELL'       ? '↓ SELL'       :
    a.signal_type === 'SL_HIT'     ? '✕ SL Hit'     :
    a.signal_type === 'TP_HIT'     ? '✓ TP Hit'     :
    a.signal_type === 'SQUARE_OFF' ? '⏹ Square Off' : a.signal_type;

  const timeStr = fmtTime(a.timestamp);
  const sign    = a.pnl_points >= 0 ? '+' : '';

  // ── Entry card (BUY / SELL) ────────────────────────────────────
  const pricesHTML = isEntry ? `
    <div class="alert-prices">
      <div class="price-item">
        <span class="price-label">Entry</span>
        <span class="price-val entry">₹${fmt(a.entry_price)}</span>
      </div>
      ${a.stop_loss ? `<div class="price-item">
        <span class="price-label">Stop Loss</span>
        <span class="price-val sl">₹${fmt(a.stop_loss)}</span>
      </div>` : ''}
      ${a.target_price ? `<div class="price-item">
        <span class="price-label">Target</span>
        <span class="price-val tp">₹${fmt(a.target_price)}</span>
      </div>` : ''}
      ${a.risk_reward ? `<div class="price-item">
        <span class="price-label">R:R</span>
        <span class="price-val rr">1:${a.risk_reward}</span>
      </div>` : ''}
    </div>`

  // ── Exit card (SL_HIT / TP_HIT / SQUARE_OFF) ──────────────────
  : isExit ? `
    <div class="alert-prices">
      ${a.original_entry ? `<div class="price-item">
        <span class="price-label">Entry was</span>
        <span class="price-val entry">₹${fmt(a.original_entry)}</span>
      </div>` : ''}
      <div class="price-item">
        <span class="price-label">Exit Price</span>
        <span class="price-val entry">₹${fmt(a.entry_price)}</span>
      </div>
      ${a.direction ? `<div class="price-item">
        <span class="price-label">Direction</span>
        <span class="price-val" style="color:${a.direction==='LONG'?'var(--green)':'var(--red)'}">${a.direction}</span>
      </div>` : ''}
    </div>
    ${a.pnl_points != null ? `
    <div class="pnl-block ${isProfit ? 'profit' : 'loss'}">
      <div class="pnl-main">
        <span class="pnl-label">P&amp;L</span>
        <span class="pnl-points">${sign}₹${fmt(Math.abs(a.pnl_points))} pts</span>
        <span class="pnl-percent">${sign}${a.pnl_percent}%</span>
      </div>
      <div class="pnl-result-badge ${isProfit ? 'profit' : 'loss'}">
        ${isProfit ? '▲ PROFIT' : '▼ LOSS'}
      </div>
    </div>` : ''}`

  // ── Fallback ───────────────────────────────────────────────────
  : `<div class="alert-prices">
      <div class="price-item">
        <span class="price-label">Price</span>
        <span class="price-val entry">₹${fmt(a.entry_price)}</span>
      </div>
    </div>`;

  const orInfo = a.range_high ? `OR: ${fmt(a.range_high)} / ${fmt(a.range_low)}` : '';

  return `
    <div class="alert-card ${typeClass}">
      <span class="signal-badge ${typeClass}">${badgeText}</span>
      <div class="alert-body">
        <div class="alert-stock">${a.display_name} <span style="color:var(--text-muted);font-size:11px;font-weight:400">${a.symbol}</span></div>
        ${pricesHTML}
      </div>
      <div class="alert-meta">
        <div class="alert-time">${timeStr}</div>
        ${a.atr ? `<div class="alert-atr">ATR: ${a.atr.toFixed(2)}</div>` : ''}
        ${orInfo ? `<div class="alert-or">${orInfo}</div>` : ''}
      </div>
    </div>`;
}

// ─────────────────────────────────────────────────────────────────────────────
// History
// ─────────────────────────────────────────────────────────────────────────────
async function fetchHistoryDates() {
  try {
    const r = await fetch(`${API_BASE}/alerts/history`);
    const data = await r.json();
    const dates = data.available_dates || [];
    el.historyDate.innerHTML = '<option value="">Select Date</option>' +
      dates.map(d => `<option value="${d}">${formatDate(d)}</option>`).join('');
  } catch (e) {
    console.error('Failed to load history dates:', e);
  }
}

async function loadHistory() {
  const date   = el.historyDate.value;
  const symbol = el.historySymbol.value;
  if (!date) {
    showToast('Select Date', 'Please choose a date to view history', 'info');
    return;
  }

  el.historyList.innerHTML = '<div class="empty-state"><p>Loading...</p></div>';
  try {
    const params = new URLSearchParams();
    if (date)   params.set('date', date);
    if (symbol) params.set('symbol', symbol);
    const r = await fetch(`${API_BASE}/alerts/history?${params}`);
    const data = await r.json();
    const alerts = data.history || [];

    if (alerts.length === 0) {
      el.historyList.innerHTML = `
        <div class="empty-state">
          <p>No alerts found</p>
          <span>No signals were generated on ${formatDate(date)}${symbol ? ' for ' + symbol : ''}</span>
        </div>`;
    } else {
      el.historyList.innerHTML = alerts.map(a => alertCardHTML(a)).join('');
    }
  } catch (e) {
    el.historyList.innerHTML = '<div class="empty-state"><p>Failed to load history</p></div>';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Toast Notifications
// ─────────────────────────────────────────────────────────────────────────────
function showToast(title, msg, type = 'info') {
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  const emoji = type === 'buy' ? '📈' : type === 'sell' ? '📉' : type === 'info' ? 'ℹ️' : '⚡';
  toast.innerHTML = `
    <span class="toast-icon">${emoji}</span>
    <div class="toast-content">
      <div class="toast-title">${title}</div>
      ${msg ? `<div class="toast-msg">${msg}</div>` : ''}
    </div>`;
  el.toastContainer.prepend(toast);

  // Auto-remove after 4s
  setTimeout(() => {
    toast.classList.add('removing');
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ─────────────────────────────────────────────────────────────────────────────
// Sound
// ─────────────────────────────────────────────────────────────────────────────
function playAlertSound(isBuy, isSell) {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);

    if (isBuy) {
      // Rising tone
      osc.frequency.setValueAtTime(440, ctx.currentTime);
      osc.frequency.linearRampToValueAtTime(660, ctx.currentTime + 0.15);
    } else if (isSell) {
      // Falling tone
      osc.frequency.setValueAtTime(660, ctx.currentTime);
      osc.frequency.linearRampToValueAtTime(440, ctx.currentTime + 0.15);
    } else {
      osc.frequency.setValueAtTime(520, ctx.currentTime);
    }

    gain.gain.setValueAtTime(0.3, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.3);
  } catch (e) {
    // Ignore audio errors
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Settings
// ─────────────────────────────────────────────────────────────────────────────
function syncConfigUI() {
  el.cfgAtrLength.value     = state.config.atr_length    || 14;
  el.cfgAtrMultiplier.value = state.config.atr_multiplier || 1.0;
  el.cfgRrRatio.value       = state.config.rr_ratio       || 2.0;
  updateFormulaPreview();
}

function updateFormulaPreview() {
  const m  = el.cfgAtrMultiplier.value;
  const rr = el.cfgRrRatio.value;
  el.fMultiplier.textContent  = m;
  el.fRR.textContent          = rr;
  el.fMultiplier2.textContent = m;
  el.fRR2.textContent         = rr;
}

async function saveConfig() {
  const body = {
    atr_length:     parseInt(el.cfgAtrLength.value),
    atr_multiplier: parseFloat(el.cfgAtrMultiplier.value),
    rr_ratio:       parseFloat(el.cfgRrRatio.value),
  };
  try {
    const r = await fetch(`${API_BASE}/config`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const data = await r.json();
    state.config = data.config;
    closeModal();
    showToast('Settings Saved', 'Strategy configuration updated', 'info');
  } catch (e) {
    showToast('Error', 'Failed to save settings', 'info');
  }
}

function openModal()  { el.settingsModal.classList.add('open'); syncConfigUI(); }
function closeModal() { el.settingsModal.classList.remove('open'); }

// ─────────────────────────────────────────────────────────────────────────────
// Tab Management
// ─────────────────────────────────────────────────────────────────────────────
function switchTab(tab) {
  state.activeTab = tab;
  el.tabToday.classList.toggle('active', tab === 'today');
  el.tabHistory.classList.toggle('active', tab === 'history');
  el.tabContentToday.classList.toggle('active', tab === 'today');
  el.tabContentHistory.classList.toggle('active', tab === 'history');

  if (tab === 'history') fetchHistoryDates();
}

// ─────────────────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────────────────
function fmt(n) {
  if (n == null) return '—';
  return Number(n).toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function fmtTime(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    return d.toLocaleTimeString('en-IN', {
      timeZone: 'Asia/Kolkata',
      hour: '2-digit', minute: '2-digit', second: '2-digit'
    });
  } catch { return iso; }
}

function formatDate(d) {
  if (!d) return '';
  try {
    return new Date(d + 'T00:00:00').toLocaleDateString('en-IN', {
      year: 'numeric', month: 'short', day: 'numeric'
    });
  } catch { return d; }
}

// ─────────────────────────────────────────────────────────────────────────────
// Force Refresh
// ─────────────────────────────────────────────────────────────────────────────
async function forceRefresh() {
  el.btnRefresh.style.opacity = '0.5';
  el.btnRefresh.style.pointerEvents = 'none';
  try {
    await fetch(`${API_BASE}/refresh`, { method: 'POST' });
    showToast('Refreshing', 'Fetching latest market data...', 'info');
  } catch (e) {
    showToast('Error', 'Refresh failed', 'info');
  }
  setTimeout(() => {
    el.btnRefresh.style.opacity = '';
    el.btnRefresh.style.pointerEvents = '';
  }, 3000);
}

// ─────────────────────────────────────────────────────────────────────────────
// Sound Toggle
// ─────────────────────────────────────────────────────────────────────────────
function toggleSound() {
  state.soundEnabled = !state.soundEnabled;
  el.btnSound.classList.toggle('active', state.soundEnabled);
  const icon = el.soundIcon;
  if (state.soundEnabled) {
    icon.innerHTML = `
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
      <path d="M15.54 8.46a5 5 0 0 1 0 7.07M19.07 4.93a10 10 0 0 1 0 14.14"/>`;
  } else {
    icon.innerHTML = `
      <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
      <line x1="23" y1="9" x2="17" y2="15"/><line x1="17" y1="9" x2="23" y2="15"/>`;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Event Listeners
// ─────────────────────────────────────────────────────────────────────────────
el.btnRefresh.addEventListener('click', forceRefresh);
el.btnSound.addEventListener('click', toggleSound);
el.btnSettings.addEventListener('click', openModal);
el.closeSettings.addEventListener('click', closeModal);
el.cancelSettings.addEventListener('click', closeModal);
el.saveSettings.addEventListener('click', saveConfig);

el.settingsModal.addEventListener('click', (e) => {
  if (e.target === el.settingsModal) closeModal();
});

el.cfgAtrMultiplier.addEventListener('input', updateFormulaPreview);
el.cfgRrRatio.addEventListener('input', updateFormulaPreview);

el.tabToday.addEventListener('click', () => switchTab('today'));
el.tabHistory.addEventListener('click', () => switchTab('history'));

el.filterSymbol.addEventListener('change', () => {
  state.filterSymbol = el.filterSymbol.value;
  renderAlerts();
});
el.filterSignal.addEventListener('change', () => {
  state.filterSignal = el.filterSignal.value;
  renderAlerts();
});
el.btnClearFilters.addEventListener('click', () => {
  el.filterSymbol.value = '';
  el.filterSignal.value = '';
  state.filterSymbol = '';
  state.filterSignal = '';
  renderAlerts();
});

el.btnLoadHistory.addEventListener('click', loadHistory);

// ─────────────────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────────────────
// Initialize stock cards with skeleton state
function initSkeletonCards() {
  el.stockCards.innerHTML = STOCKS.map(s => `
    <div class="stock-card" id="card-${s.symbol.replace('.', '-')}">
      <div class="stock-card-header">
        <div>
          <div class="stock-name">${s.name}</div>
          <div class="stock-symbol">${s.symbol}</div>
        </div>
        <span class="position-badge flat">FLAT</span>
      </div>
      <div class="stock-price na">Loading...</div>
      <div class="or-levels">
        <div class="or-level high"><div class="or-level-label">OR High</div><div class="or-level-val">—</div></div>
        <div class="or-level low"><div class="or-level-label">OR Low</div><div class="or-level-val">—</div></div>
      </div>
      <div class="stock-meta"><span class="meta-pill status-closed">○ Closed</span></div>
    </div>`).join('');
}

initSkeletonCards();
connectWS();

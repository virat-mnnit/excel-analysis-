// === State ===
let apiKeySet = false;
let fileLoaded = false;

// === Theme Toggle ===
function toggleTheme() {
  const html = document.documentElement;
  const next = html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('excel-intel-theme', next);
}
(function() {
  const saved = localStorage.getItem('excel-intel-theme');
  if (saved) document.documentElement.setAttribute('data-theme', saved);
})();

// === Sidebar Toggle (mobile) ===
function toggleSidebar() {
  document.getElementById('sidebar').classList.toggle('mobile-open');
}

// === API Key ===
async function saveApiKey() {
  const key = document.getElementById('apiKey').value.trim();
  const model = document.getElementById('modelSelect').value;
  if (!key) { showToast('Please enter an API key', 'error'); return; }

  const btn = document.getElementById('saveKeyBtn');
  btn.disabled = true; btn.textContent = 'Saving...';

  try {
    const form = new FormData();
    form.append('api_key', key);
    form.append('model', model);
    const res = await fetch('/api/set-key', { method: 'POST', body: form });
    const data = await res.json();
    if (res.ok) {
      apiKeySet = true;
      showToast('API key saved', 'success');
      updateStatus();
    } else {
      showToast(data.detail || 'Failed', 'error');
    }
  } catch (e) {
    showToast('Connection error', 'error');
  }
  btn.disabled = false;
  btn.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/></svg> Save Key';
}

// === File Upload ===
const uploadZone = document.getElementById('uploadZone');
const fileInput = document.getElementById('fileInput');

uploadZone.addEventListener('click', () => fileInput.click());
uploadZone.addEventListener('dragover', e => { e.preventDefault(); uploadZone.classList.add('dragover'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('dragover'));
uploadZone.addEventListener('drop', e => {
  e.preventDefault(); uploadZone.classList.remove('dragover');
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener('change', () => { if (fileInput.files.length) handleFile(fileInput.files[0]); });

async function handleFile(file) {
  const ext = file.name.split('.').pop().toLowerCase();
  if (!['xlsx', 'xls', 'csv'].includes(ext)) { showToast('Unsupported format', 'error'); return; }

  const origHTML = uploadZone.innerHTML;
  uploadZone.innerHTML = '<p class="upload-text">Processing ' + escapeHtml(file.name) + '...</p>';

  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();

    if (res.ok && data.metadata) {
      fileLoaded = true;
      const m = data.metadata;
      document.getElementById('fileInfo').classList.add('active');
      document.getElementById('fileName').textContent = m.file_name;
      document.getElementById('rowCount').textContent = m.row_count.toLocaleString();
      document.getElementById('colCount').textContent = m.col_count;
      document.getElementById('fileSize').textContent = m.file_size_mb + ' MB';
      document.getElementById('tableName').textContent = m.table_name;

      const colsDiv = document.getElementById('schemaCols');
      colsDiv.innerHTML = '';
      for (const [col, type] of Object.entries(m.schema)) {
        colsDiv.innerHTML += `<span class="col-pill">${escapeHtml(col)} · ${type}</span>`;
      }
      showToast('File loaded', 'success');
      updateStatus();
      addBotMessage(`Loaded <strong>${escapeHtml(m.file_name)}</strong> — ${m.row_count.toLocaleString()} rows × ${m.col_count} columns. Ask me anything about your data.`);
    } else {
      showToast(data.detail || 'Upload failed', 'error');
    }
  } catch (e) {
    showToast('Upload error', 'error');
  }
  uploadZone.innerHTML = origHTML;
  const newInput = uploadZone.querySelector('input[type="file"]');
  if (newInput) newInput.addEventListener('change', () => { if (newInput.files.length) handleFile(newInput.files[0]); });
}

// === Chat ===
function quickAsk(text) {
  if (!apiKeySet) { showToast('Set your API key first', 'error'); return; }
  document.getElementById('chatInput').value = text;
  sendMessage();
}

async function sendMessage() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  if (!apiKeySet) { showToast('Set your API key first', 'error'); return; }

  hideWelcome();
  addUserMessage(msg);
  input.value = '';

  const typingId = showTyping();
  document.getElementById('sendBtn').disabled = true;
  input.disabled = true;

  try {
    const form = new FormData();
    form.append('message', msg);
    const res = await fetch('/api/chat', { method: 'POST', body: form });
    const data = await res.json();
    removeTyping(typingId);

    const handlers = {
      data_query: renderDataQuery,
      chart: renderChart,
      chart_followup: renderChartFollowup,
      projection: renderProjection,
      suggestion: renderSuggestion,
      explain: renderExplain,
      correlation: renderCorrelation,
      outlier: renderOutlier,
      timeseries: renderTimeseries,
    };

    if (data.type === 'error') {
      addBotMessageRaw('<span style="color:var(--error)">⚠ ' + escapeHtml(data.content) + '</span>');
    } else if (handlers[data.type]) {
      handlers[data.type](data);
    } else {
      addBotMessageRaw(formatText(data.content || 'Done.'));
    }
  } catch (e) {
    removeTyping(typingId);
    addBotMessageRaw('<span style="color:var(--error)">Connection error: ' + escapeHtml(e.message) + '</span>');
  }

  document.getElementById('sendBtn').disabled = false;
  input.disabled = false;
  input.focus();
}

// === Renderers ===
function renderDataQuery(data) {
  let html = formatText(data.content);
  if (data.sql) html += `<div class="sql-badge">${escapeHtml(data.sql)}</div>`;
  if (data.table && data.table.rows && data.table.rows.length > 0) html += buildTable(data.table.columns, data.table.rows);
  addBotMessageRaw(html);
}

function renderChart(data) {
  let html = formatText(data.content);
  if (data.chart_image) html += `<div class="msg-chart"><img src="data:image/png;base64,${data.chart_image}" alt="Chart"></div>`;
  addBotMessageRaw(html);
}

function renderChartFollowup(data) {
  const opts = data.options;
  let html = formatText(data.content);
  html += '<div class="chart-options">';
  (opts.chart_types || ['bar','line','pie','scatter']).forEach(t => {
    html += `<button class="chart-option-btn" onclick="selectChartType('${t}','${opts.x || ''}','${(opts.y||[]).join(',')}','${opts.title || 'Chart'}')">${t.charAt(0).toUpperCase()+t.slice(1)}</button>`;
  });
  html += '</div>';
  addBotMessageRaw(html);
}

function selectChartType(type, x, y, title) {
  document.getElementById('chatInput').value = `Show me a ${type} chart with x=${x} y=${y} titled "${title}"`;
  sendMessage();
}

function renderProjection(data) {
  let html = formatText(data.content);
  if (data.projected_values) html += `<div class="sql-badge">Forecast: ${data.projected_values.map(v=>v.toLocaleString()).join(' → ')}</div>`;
  if (data.chart_image) html += `<div class="msg-chart"><img src="data:image/png;base64,${data.chart_image}" alt="Projection"></div>`;
  addBotMessageRaw(html);
}

function renderSuggestion(data) {
  let html = formatText(data.content);
  if (data.insights && data.insights.length) {
    html += '<ul class="suggestion-list">';
    data.insights.forEach(s => { html += `<li>${escapeHtml(s)}</li>`; });
    html += '</ul>';
  }
  addBotMessageRaw(html);
}

function renderExplain(data) {
  let html = formatText(data.content);
  if (data.metadata) {
    const m = data.metadata;
    html += '<div class="meta-badges">';
    html += `<span class="meta-badge">${m.rows.toLocaleString()} rows</span>`;
    html += `<span class="meta-badge">${m.columns} cols</span>`;
    if (m.numeric_cols.length) html += `<span class="meta-badge">${m.numeric_cols.length} numeric</span>`;
    if (m.categorical_cols.length) html += `<span class="meta-badge">${m.categorical_cols.length} text</span>`;
    if (m.total_nulls > 0) html += `<span class="meta-badge">${m.total_nulls} nulls</span>`;
    if (m.duplicate_rows > 0) html += `<span class="meta-badge">${m.duplicate_rows} dupes</span>`;
    html += '</div>';
  }
  addBotMessageRaw(html);
}

function renderCorrelation(data) {
  let html = formatText(data.content);
  if (data.top_pairs && data.top_pairs.length) {
    html += '<div class="corr-pairs">';
    data.top_pairs.slice(0,6).forEach(p => {
      const cls = p.correlation >= 0 ? 'positive' : 'negative';
      html += `<div class="corr-pair"><span class="cols">${escapeHtml(p.col_a)} ↔ ${escapeHtml(p.col_b)}</span><span><span class="val ${cls}">${p.correlation.toFixed(3)}</span><span class="strength">${escapeHtml(p.strength)}</span></span></div>`;
    });
    html += '</div>';
  }
  if (data.chart_image) html += `<div class="msg-chart"><img src="data:image/png;base64,${data.chart_image}" alt="Heatmap"></div>`;
  addBotMessageRaw(html);
}

function renderOutlier(data) {
  let html = formatText(data.content);
  if (data.results && data.results.length) {
    html += '<div class="outlier-summary">';
    data.results.forEach(r => {
      html += `<span class="outlier-badge ${r.outlier_count>0?'':'clean'}">${escapeHtml(r.column)}: ${r.outlier_count} (${r.outlier_pct}%)</span>`;
    });
    html += '</div>';
  }
  if (data.chart_image) html += `<div class="msg-chart"><img src="data:image/png;base64,${data.chart_image}" alt="Outliers"></div>`;
  addBotMessageRaw(html);
}

function renderTimeseries(data) {
  let html = formatText(data.content);
  if (data.trend || data.forecast) {
    html += '<div class="ts-stats">';
    if (data.trend) html += `<div class="ts-stat"><div class="label">Trend</div><div class="value">${escapeHtml(data.trend.direction)} (R²=${data.trend.r_squared})</div></div>`;
    if (data.stationarity) html += `<div class="ts-stat"><div class="label">Stationarity</div><div class="value">${data.stationarity.is_stationary?'Yes':'No'} (p=${data.stationarity.p_value})</div></div>`;
    if (data.forecast) {
      html += `<div class="ts-stat"><div class="label">Model</div><div class="value">ARIMA ${escapeHtml(data.forecast.model_params.order||'N/A')}</div></div>`;
      html += `<div class="ts-stat"><div class="label">Periods</div><div class="value">${data.forecast.periods}</div></div>`;
    }
    html += '</div>';
  }
  if (data.chart_image) html += `<div class="msg-chart"><img src="data:image/png;base64,${data.chart_image}" alt="Time Series"></div>`;
  addBotMessageRaw(html);
}

// === UI Helpers ===
function hideWelcome() {
  const w = document.getElementById('welcomeScreen');
  if (w) w.style.display = 'none';
}

function addUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'message user';
  div.innerHTML = `<div class="msg-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg></div><div class="msg-content">${escapeHtml(text)}</div>`;
  document.getElementById('chatMessages').appendChild(div);
  scrollBottom();
}

function addBotMessage(html) { addBotMessageRaw(html); }

function addBotMessageRaw(html) {
  const div = document.createElement('div');
  div.className = 'message bot';
  div.innerHTML = `<div class="msg-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div><div class="msg-content">${html}</div>`;
  document.getElementById('chatMessages').appendChild(div);
  scrollBottom();
}

function buildTable(columns, rows) {
  let html = '<div class="msg-table"><table><thead><tr>';
  columns.forEach(c => { html += `<th>${escapeHtml(c)}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    columns.forEach(c => { html += `<td>${escapeHtml(String(row[c]??''))}</td>`; });
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

let typingCounter = 0;
function showTyping() {
  const id = 'typing-' + (++typingCounter);
  const div = document.createElement('div');
  div.className = 'message bot'; div.id = id;
  div.innerHTML = `<div class="msg-avatar"><svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg></div><div class="msg-content"><div class="typing"><span></span><span></span><span></span></div></div>`;
  document.getElementById('chatMessages').appendChild(div);
  scrollBottom();
  return id;
}

function removeTyping(id) { const el = document.getElementById(id); if (el) el.remove(); }
function scrollBottom() { const c = document.getElementById('chatMessages'); c.scrollTop = c.scrollHeight; }

function clearChat() {
  const msgs = document.getElementById('chatMessages');
  msgs.innerHTML = '';
  const w = document.createElement('div');
  w.className = 'welcome'; w.id = 'welcomeScreen';
  w.innerHTML = '<div class="welcome-badge">AI-Powered Analysis</div><h2>What would you like to know?</h2><p>Upload data and ask questions, or just chat.</p>';
  msgs.appendChild(w);
}

function updateStatus() {
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('headerStatus');
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');

  if (apiKeySet && fileLoaded) {
    dot.className = 'status-dot connected';
    text.textContent = 'Ready';
    input.disabled = false; btn.disabled = false;
    input.placeholder = 'Ask anything about your data...';
  } else if (apiKeySet) {
    dot.className = 'status-dot connected';
    text.textContent = 'Connected — Upload data for analysis';
    input.disabled = false; btn.disabled = false;
    input.placeholder = 'Ask a question or upload data...';
  } else {
    dot.className = 'status-dot';
    text.textContent = 'Set API Key to start';
    input.disabled = true; btn.disabled = true;
    input.placeholder = 'Configure your API key first...';
  }
}

function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 2500);
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

function formatText(text) {
  if (!text) return '';
  let html = escapeHtml(text);
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\n/g, '<br>');
  html = html.replace(/^[-•]\s+(.*)$/gm, '<br>• $1');
  return html;
}

// === State ===
let apiKeySet = false;
let fileLoaded = false;

// === API Key ===
async function saveApiKey() {
  const key = document.getElementById('apiKey').value.trim();
  const model = document.getElementById('modelSelect').value;
  if (!key) { showToast('Please enter an API key', 'error'); return; }

  const btn = document.getElementById('saveKeyBtn');
  btn.disabled = true; btn.innerHTML = '<span>⏳</span> Saving...';

  try {
    const form = new FormData();
    form.append('api_key', key);
    form.append('model', model);
    const res = await fetch('/api/set-key', { method: 'POST', body: form });
    const data = await res.json();
    if (res.ok) {
      apiKeySet = true;
      showToast('API key saved! ✓', 'success');
      updateStatus();
    } else {
      showToast(data.detail || 'Failed to save key', 'error');
    }
  } catch (e) {
    showToast('Connection error: ' + e.message, 'error');
  }
  btn.disabled = false; btn.innerHTML = '<span>🔒</span> Save API Key';
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

  uploadZone.innerHTML = '<div class="icon">⏳</div><p>Processing ' + file.name + '...</p>';

  try {
    const form = new FormData();
    form.append('file', file);
    const res = await fetch('/api/upload', { method: 'POST', body: form });
    const data = await res.json();

    if (res.ok && data.metadata) {
      fileLoaded = true;
      const m = data.metadata;
      document.getElementById('fileInfo').classList.add('active');
      document.getElementById('fileName').innerHTML = '📄 ' + m.file_name;
      document.getElementById('rowCount').textContent = m.row_count.toLocaleString();
      document.getElementById('colCount').textContent = m.col_count;
      document.getElementById('fileSize').textContent = m.file_size_mb + ' MB';
      document.getElementById('tableName').textContent = m.table_name;

      const colsDiv = document.getElementById('schemaCols');
      colsDiv.innerHTML = '';
      for (const [col, type] of Object.entries(m.schema)) {
        colsDiv.innerHTML += `<span class="col-pill">${col} (${type})</span>`;
      }

      showToast('File loaded successfully! ✓', 'success');
      updateStatus();
      addBotMessage(`I've loaded **${m.file_name}** with **${m.row_count.toLocaleString()} rows** and **${m.col_count} columns**. Ask me anything about your data!`);
    } else {
      showToast(data.detail || 'Upload failed', 'error');
    }
  } catch (e) {
    showToast('Upload error: ' + e.message, 'error');
  }

  uploadZone.innerHTML = '<div class="icon">⬆️</div><p>Drop file or click to browse</p><div class="formats">.xlsx, .xls, .csv</div><input type="file" id="fileInput" accept=".xlsx,.xls,.csv">';
  document.getElementById('fileInput').addEventListener('change', () => {
    if (document.getElementById('fileInput').files.length) handleFile(document.getElementById('fileInput').files[0]);
  });
}

// === Chat ===
function quickAsk(text) {
  document.getElementById('chatInput').value = text;
  sendMessage();
}

async function sendMessage() {
  const input = document.getElementById('chatInput');
  const msg = input.value.trim();
  if (!msg) return;
  if (!apiKeySet) { showToast('Set your API key first', 'error'); return; }
  if (!fileLoaded) { showToast('Upload a file first', 'error'); return; }

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

    if (data.type === 'data_query') {
      let html = escapeHtml(data.content);
      if (data.sql) html += `<div class="sql-badge">SQL: ${escapeHtml(data.sql)}</div>`;
      if (data.table && data.table.rows && data.table.rows.length > 0) {
        html += buildTable(data.table.columns, data.table.rows);
      }
      addBotMessageRaw(html);
    } else if (data.type === 'chart') {
      let html = escapeHtml(data.content);
      if (data.chart_image) html += `<div class="msg-chart"><img src="data:image/png;base64,${data.chart_image}" alt="Chart"></div>`;
      addBotMessageRaw(html);
    } else if (data.type === 'projection') {
      let html = escapeHtml(data.content);
      if (data.projected_values) html += `<div class="sql-badge">Projected: ${data.projected_values.map(v => v.toLocaleString()).join(' → ')}</div>`;
      if (data.chart_image) html += `<div class="msg-chart"><img src="data:image/png;base64,${data.chart_image}" alt="Projection"></div>`;
      addBotMessageRaw(html);
    } else if (data.type === 'suggestion') {
      let html = escapeHtml(data.content);
      if (data.insights && data.insights.length) {
        html += '<ul class="suggestion-list">';
        data.insights.forEach(s => { html += `<li>${escapeHtml(s)}</li>`; });
        html += '</ul>';
      }
      addBotMessageRaw(html);
    } else if (data.type === 'error') {
      addBotMessage('⚠️ ' + data.content);
    } else {
      addBotMessage(data.content || 'I received your message but got an unexpected response.');
    }
  } catch (e) {
    removeTyping(typingId);
    addBotMessage('⚠️ Connection error: ' + e.message);
  }

  document.getElementById('sendBtn').disabled = false;
  input.disabled = false;
  input.focus();
}

// === UI Helpers ===
function hideWelcome() {
  const w = document.getElementById('welcomeScreen');
  if (w) w.style.display = 'none';
}

function addUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'message user';
  div.innerHTML = `<div class="msg-avatar">👤</div><div class="msg-content">${escapeHtml(text)}</div>`;
  document.getElementById('chatMessages').appendChild(div);
  scrollBottom();
}

function addBotMessage(text) {
  addBotMessageRaw(escapeHtml(text));
}

function addBotMessageRaw(html) {
  const div = document.createElement('div');
  div.className = 'message bot';
  div.innerHTML = `<div class="msg-avatar">🤖</div><div class="msg-content">${html}</div>`;
  document.getElementById('chatMessages').appendChild(div);
  scrollBottom();
}

function buildTable(columns, rows) {
  let html = '<div class="msg-table"><table><thead><tr>';
  columns.forEach(c => { html += `<th>${escapeHtml(c)}</th>`; });
  html += '</tr></thead><tbody>';
  rows.forEach(row => {
    html += '<tr>';
    columns.forEach(c => { html += `<td>${escapeHtml(String(row[c] ?? ''))}</td>`; });
    html += '</tr>';
  });
  html += '</tbody></table></div>';
  return html;
}

let typingCounter = 0;
function showTyping() {
  const id = 'typing-' + (++typingCounter);
  const div = document.createElement('div');
  div.className = 'message bot';
  div.id = id;
  div.innerHTML = '<div class="msg-avatar">🤖</div><div class="msg-content"><div class="typing"><span></span><span></span><span></span></div></div>';
  document.getElementById('chatMessages').appendChild(div);
  scrollBottom();
  return id;
}

function removeTyping(id) {
  const el = document.getElementById(id);
  if (el) el.remove();
}

function scrollBottom() {
  const c = document.getElementById('chatMessages');
  c.scrollTop = c.scrollHeight;
}

function clearChat() {
  const msgs = document.getElementById('chatMessages');
  msgs.innerHTML = '';
  const welcome = document.createElement('div');
  welcome.className = 'welcome';
  welcome.id = 'welcomeScreen';
  welcome.innerHTML = '<div class="icon-big">🤖</div><h2>Excel Intelligence Chatbot</h2><p>Upload an Excel or CSV file, then ask questions in plain English.</p>';
  msgs.appendChild(welcome);
}

function updateStatus() {
  const dot = document.getElementById('statusDot');
  const text = document.getElementById('headerStatus');
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');

  if (apiKeySet && fileLoaded) {
    dot.className = 'status-dot connected';
    text.textContent = 'Ready — Ask anything';
    input.disabled = false; btn.disabled = false;
  } else if (apiKeySet) {
    dot.className = 'status-dot';
    text.textContent = 'API Connected — Upload a file';
    input.disabled = true; btn.disabled = true;
  } else {
    dot.className = 'status-dot';
    text.textContent = 'Set API Key to start';
    input.disabled = true; btn.disabled = true;
  }
}

function showToast(msg, type) {
  const t = document.createElement('div');
  t.className = 'toast ' + type;
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

function escapeHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

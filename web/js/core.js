let currentPage = 'chat';
let sessionId = '';
let conversationId = '';
let isStreaming = false;
let currentConvId = '';
let splitConvId = '';
let isSplitStreaming = false;
let fbHistory = [];
let currentReader = null;
let debugEvents = [];        // 调试事件缓冲
let debugActiveTab = 'events';

// ── 登录态 / API Key（用户 JWT 优先）──
window.kejiCurrentUser = null;
window.kejiAuthReady = false;

function getKejiToken() {
  return localStorage.getItem('keji_token') || '';
}
function setKejiToken(token) {
  if (token) localStorage.setItem('keji_token', token);
  else localStorage.removeItem('keji_token');
}
function getKejiApiKey() {
  return localStorage.getItem('keji_api_key') || '';
}
function setKejiApiKey(key) {
  if (key) localStorage.setItem('keji_api_key', key);
  else localStorage.removeItem('keji_api_key');
}
function kejiAuthHeaders(extra) {
  var h = {};
  if (extra) {
    if (extra instanceof Headers) {
      extra.forEach(function(v, k) { h[k] = v; });
    } else if (typeof extra === 'object') {
      Object.assign(h, extra);
    }
  }
  var token = getKejiToken();
  if (token) {
    h['Authorization'] = 'Bearer ' + token;
  } else {
    var key = getKejiApiKey();
    // 勿把未替换的环境变量占位符或空串当作 API Key，否则会一直 401
    if (key && key.indexOf('${') < 0 && key.length >= 8) {
      h['Authorization'] = 'Bearer ' + key;
      h['X-API-Key'] = key;
    }
  }
  return h;
}
function kejiFetch(url, options) {
  options = options || {};
  var headers = kejiAuthHeaders(options.headers);
  return fetch(url, Object.assign({}, options, { headers: headers })).then(function(res) {
    if (res.status === 401) {
      var hadSession = !!window.kejiAuthReady && !window.kejiJustLoggedIn;
      var isCoreAuth =
        url.indexOf('/api/auth/me') >= 0 ||
        url.indexOf('/api/admin/') >= 0;
      if (hadSession && isCoreAuth) {
        setKejiToken('');
        window.kejiAuthReady = false;
        window.kejiCurrentUser = null;
        if (typeof showLoginOverlay === 'function') {
          showLoginOverlay('登录已过期，请重新登录');
        }
      } else if (typeof showLoginOverlay === 'function') {
        var overlay = document.getElementById('loginOverlay');
        if (overlay && overlay.classList.contains('open')) {
          var errEl = document.getElementById('loginError');
          if (errEl && errEl.textContent.indexOf('过期') >= 0) errEl.textContent = '';
        }
      }
    }
    return res;
  });
}

let agentMode = localStorage.getItem('keji_agent_mode') || 'react';
let currentPlan = null;

var _emojiFA = {
  '💬': 'fa-comments', '📚': 'fa-book-open', '📁': 'fa-folder', '⚙️': 'fa-gear',
  '🔧': 'fa-wrench', '📋': 'fa-clock', '➕': 'fa-plus', '📥': 'fa-cloud-arrow-down',
  '⏹': 'fa-stop', '🔍': 'fa-magnifying-glass', '🔄': 'fa-rotate', '💾': 'fa-floppy-disk',
  '🗑️': 'fa-trash-can', '🗑': 'fa-trash-can', '✕': 'fa-xmark', '👤': 'fa-user',
  '🤖': 'fa-robot', '🤔': 'fa-brain', '✅': 'fa-circle-check', '❌': 'fa-circle-xmark',
  '📖': 'fa-book-open', '🗣': 'fa-comment', '🏁': 'fa-flag', '💭': 'fa-comment-dots',
  '⏳': 'fa-hourglass-half', '👋': 'fa-hand-wave', '📊': 'fa-chart-simple',
  '⚡': 'fa-bolt', '📂': 'fa-folder-open', '🌐': 'fa-globe', '📝': 'fa-pen',
  '🔗': 'fa-link', '♻️': 'fa-recycle', '✏️': 'fa-pencil', '📦': 'fa-box-archive',
  '📤': 'fa-up-from-bracket', '👁️': 'fa-eye', '📑': 'fa-copy', '✉️': 'fa-envelope',
  '📎': 'fa-paperclip', '📨': 'fa-inbox', '▶️': 'fa-play', '🕐': 'fa-clock',
  '🔢': 'fa-hashtag', '📄': 'fa-file-lines', '🖼️': 'fa-image', '📜': 'fa-scroll',
  '☕': 'fa-mug-saucer', '🔵': 'fa-circle', '🐍': 'fa-code', '🎨': 'fa-palette',
  '📰': 'fa-newspaper', '📕': 'fa-file-pdf', '📘': 'fa-file-word', '📗': 'fa-file-excel',
  '📈': 'fa-chart-line', '🧹': 'fa-broom', '↔️': 'fa-right-left', '💻': 'fa-terminal',
  '🗃️': 'fa-database', '🎯': 'fa-bullseye', '🧠': 'fa-brain', 'ℹ️': 'fa-circle-info',
  '📽️': 'fa-video', '☑': 'fa-square-check', '📭': 'fa-inbox', '💡': 'fa-lightbulb',
  '🔎': 'fa-magnifying-glass', '🛠': 'fa-screwdriver-wrench',
};

// 工具专属 emoji 图标（供 loadTools 使用）
var _toolIcons = {
  get_time: '🕐', calculator: '🔢', read_file: '📄', web_search: '🌐',
  browse_files: '📂', search_files: '🔍', read_document: '📖',
  query_knowledge: '🔎', index_knowledge: '📥', knowledge_stats: '📊',
  remove_from_knowledge: '🗑️',
  create_document: '📝', create_table: '📋', create_presentation: '📽️',
  analyze_data: '📈', format_data: '🔄', clean_data: '🧹',
  etl_pipeline: '🔗', convert_data: '↔️',
  delete_file: '🗑️', create_folder: '📁', rename_files: '✏️',
  organize_files: '📦', deduplicate_files: '♻️',
  exec: '💻', write_file: '📝', edit_file: '✏️', list_dir: '📂',
  glob: '🔍', grep: '🔎', web_fetch: '🌐', run_code: '▶️',
  browse_archive: '📦', extract_archive: '📤', create_archive: '📥',
  ocr_image: '👁️', ocr_pdf: '📄', ocr_batch: '📑',
  parse_email: '✉️', extract_email_attachments: '📎', batch_parse_emails: '📨',
  db_connect: '🔌', db_list_tables: '📋', db_describe_table: '📐',
  db_execute_query: '⚡', db_test_connection: '🔗', db_disconnect: '🔌',
};

// 工具专属 FA 图标
var _toolFA = {
  get_time: 'fa-clock', calculator: 'fa-calculator', read_file: 'fa-file-lines',
  web_search: 'fa-globe', browse_files: 'fa-folder-open', search_files: 'fa-search',
  read_document: 'fa-book-open', query_knowledge: 'fa-magnifying-glass',
  index_knowledge: 'fa-cloud-arrow-down', knowledge_stats: 'fa-chart-simple',
  remove_from_knowledge: 'fa-trash-can',
  create_document: 'fa-file-word', create_table: 'fa-table', create_presentation: 'fa-file-powerpoint',
  analyze_data: 'fa-chart-line', format_data: 'fa-arrows-rotate', clean_data: 'fa-broom',
  etl_pipeline: 'fa-diagram-project', convert_data: 'fa-right-left',
  delete_file: 'fa-trash-can', create_folder: 'fa-folder-plus', rename_files: 'fa-pencil',
  organize_files: 'fa-boxes-stacked', deduplicate_files: 'fa-copy',
  exec: 'fa-terminal', write_file: 'fa-file-pen', edit_file: 'fa-pen', list_dir: 'fa-list',
  glob: 'fa-magnifying-glass', grep: 'fa-filter', web_fetch: 'fa-cloud',
  browse_archive: 'fa-box-archive', extract_archive: 'fa-file-zipper', create_archive: 'fa-box-archive',
  ocr_image: 'fa-eye', ocr_pdf: 'fa-file-pdf', ocr_batch: 'fa-layer-group',
  parse_email: 'fa-envelope', extract_email_attachments: 'fa-paperclip', batch_parse_emails: 'fa-envelope-open-text',
  run_code: 'fa-play',
  db_connect: 'fa-plug', db_list_tables: 'fa-table-list', db_describe_table: 'fa-table-columns',
  db_execute_query: 'fa-bolt', db_test_connection: 'fa-link', db_disconnect: 'fa-plug-circle-xmark',
};

// 输出双版本图标 HTML
function _dualIcon(emoji, faClass) {
  if (!faClass) faClass = _emojiFA[emoji] || 'fa-circle';
  return '<span class="icon-emoji">' + emoji + '</span><i class="icon-fa fa-solid ' + faClass + '"></i>';
}
// 将文本中的已知 emoji 替换为双图标 HTML（用于思考面板等 textContent → innerHTML 迁移）
function _replaceEmoji(text) {
  if (!text) return text;
  var map = { '🔧': 'fa-wrench', '✅': 'fa-circle-check', '❌': 'fa-circle-xmark', '🧠': 'fa-brain', '🤔': 'fa-brain', '🔄': 'fa-rotate' };
  for (var em in map) {
    var re = new RegExp(em.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g');
    text = text.split(em).join(_dualIcon(em, map[em]));
  }
  return text;
}

// 分类中文名
var _catNames = {
  utility: { emoji: '⚡', label: '常用工具', fa: 'fa-bolt' },
  io: { emoji: '📂', label: '文件读写', fa: 'fa-folder-open' },
  web: { emoji: '🌐', label: '网络搜索', fa: 'fa-globe' },
  filesystem: { emoji: '📁', label: '文件管理', fa: 'fa-folder' },
  knowledge: { emoji: '📚', label: '知识库', fa: 'fa-book-open' },
  office: { emoji: '📝', label: '办公文档', fa: 'fa-file-pen' },
  data: { emoji: '📊', label: '数据处理', fa: 'fa-chart-simple' },
  general: { emoji: '🔧', label: '其他', fa: 'fa-wrench' },
};

// 分类配色
var _catColors = {
  utility: { icon: '⚡', bg: '#fff3e0', color: '#e65100', border: '#ffe0b2' },
  io: { icon: '📂', bg: '#e3f2fd', color: '#1565c0', border: '#bbdefb' },
  web: { icon: '🌐', bg: '#e8f5e9', color: '#2e7d32', border: '#c8e6c9' },
  filesystem: { icon: '📁', bg: '#f3e5f5', color: '#6a1b9a', border: '#e1bee7' },
  knowledge: { icon: '📚', bg: '#fce4ec', color: '#c62828', border: '#f8bbd0' },
  office: { icon: '📝', bg: '#e0f7fa', color: '#00695c', border: '#b2ebf2' },
  data: { icon: '📊', bg: '#eceff1', color: '#37474f', border: '#cfd8dc' },
  general: { icon: '🔧', bg: '#f5f5f5', color: '#616161', border: '#e0e0e0' },
};

// 加载并分组渲染工具
function loadTools() {
  Promise.all([
    kejiFetch('/tools').then(function(r){return r.json()}),
    kejiFetch('/api/tools/display').then(function(r){return r.json()})
  ]).then(function(data) {
    var toolsData = data[0];
    var displayData = data[1];
    var nameMap = displayData.tools || {};
    var container = document.getElementById('toolPanelInner');
    if (!container) return;

    if (!toolsData.tools || !toolsData.tools.length) {
      container.innerHTML = '<div style="padding:10px 0;font-size:13px;color:#999">无可用工具</div>';
      return;
    }

    // 按分类分组
    var groups = {};
    toolsData.tools.forEach(function(t) {
      if (!groups[t.category]) groups[t.category] = [];
      groups[t.category].push(t);
    });

    var html = '';
    var catOrder = ['utility','knowledge','office','filesystem','data','io','web','general'];
    catOrder.forEach(function(cat) {
      if (!groups[cat]) return;
      var tools = groups[cat];
      var c = _catColors[cat] || _catColors.general;
      var catInfo = _catNames[cat];
      html += '<div class="tp-category">' + (catInfo ? _dualIcon(catInfo.emoji, catInfo.fa) + ' ' + catInfo.label : cat) + '</div>';
      html += '<div class="tp-tags">';
      tools.forEach(function(t) {
        var label = nameMap[t.name] || t.name;
        var emoji = _toolIcons[t.name] || '⚙️';
        var fa = _toolFA[t.name] || 'fa-wrench';
        html += '<span class="tp-tag" style="background:' + c.bg + ';color:' + c.color + ';border-color:' + c.border + '" title="' + t.name + '">' + _dualIcon(emoji, fa) + ' ' + label + '</span>';
      });
      html += '</div>';
    });

    container.innerHTML = html;
  }).catch(function() {
    var container = document.getElementById('toolPanelInner');
    if (container) container.innerHTML = '<div style="padding:10px 0;font-size:13px;color:#999">加载失败</div>';
  });
}

// 切换工具面板（丝滑动画）
var _toolsLoaded = false;
function toggleToolPanel() {
  var panel = document.getElementById('toolPanel');
  var btn = document.getElementById('toolMenuBtn');
  if (!panel) return;

  if (panel.classList.contains('open')) {
    panel.classList.remove('open');
    btn.classList.remove('active');
  } else {
    if (!_toolsLoaded) { loadTools(); _toolsLoaded = true; }
    panel.classList.add('open');
    btn.classList.add('active');
  }
}

function checkStatus() {
  kejiFetch('/api/status').then(r => r.json()).then(d => {
    const dot = document.getElementById('statusDot');
    const text = document.getElementById('statusText');
    if (d.model) {
      dot.className = 'status-dot online';
      var label = d.model.type === 'openai' ? 'API' : 'Ollama';
      text.textContent = label + ' · ' + d.model.name + ' · ' + d.knowledge.documents + ' 文档';
    } else if (d.ollama && d.ollama.available) {
      dot.className = 'status-dot online';
      text.textContent = 'Ollama 已连接 · ' + d.knowledge.documents + ' 文档';
    } else {
      dot.className = 'status-dot offline';
      text.textContent = '未连接';
    }
  }).catch(() => {
    document.getElementById('statusDot').className = 'status-dot offline';
    document.getElementById('statusText').textContent = '服务器异常';
  });
}

// ================================================================
// 聊天功能
// ================================================================
function escHtml(s) {
  if (!s) return '';
  const div = document.createElement('div');
  div.textContent = s;
  return div.innerHTML;
}

function getFileIcon(ext) {
  var emojiMap = {
    '.pdf': '📕', '.docx': '📘', '.doc': '📘', '.xlsx': '📗', '.xls': '📗',
    '.csv': '📊', '.json': '📋', '.yaml': '📋', '.yml': '📋',
    '.py': '🐍', '.js': '📜', '.ts': '📜', '.java': '☕', '.cpp': '⚙️',
    '.c': '⚙️', '.h': '⚙️', '.rs': '🦀', '.go': '🔵',
    '.html': '🌐', '.htm': '🌐', '.css': '🎨', '.xml': '📰',
    '.md': '📝', '.txt': '📄', '.log': '📋',
    '.sql': '🗃️', '.sh': '💻', '.bat': '💻', '.ps1': '💻',
    '.jpg': '🖼️', '.jpeg': '🖼️', '.png': '🖼️', '.gif': '🖼️',
    '.zip': '📦', '.rar': '📦', '.7z': '📦',
    '.exe': '⚡', '.msi': '⚡',
    '.toml': '⚙️', '.ini': '⚙️', '.cfg': '⚙️', '.conf': '⚙️',
  };
  var faMap = {
    '.pdf': 'fa-file-pdf', '.docx': 'fa-file-word', '.doc': 'fa-file-word',
    '.xlsx': 'fa-file-excel', '.xls': 'fa-file-excel',
    '.csv': 'fa-file-csv', '.json': 'fa-file-code', '.yaml': 'fa-file-code', '.yml': 'fa-file-code',
    '.py': 'fa-code', '.js': 'fa-code', '.ts': 'fa-code', '.java': 'fa-code', '.cpp': 'fa-gear',
    '.c': 'fa-gear', '.h': 'fa-gear', '.go': 'fa-code',
    '.html': 'fa-code', '.htm': 'fa-code', '.css': 'fa-palette', '.xml': 'fa-file-code',
    '.md': 'fa-file-lines', '.txt': 'fa-file-lines', '.log': 'fa-file-lines',
    '.sql': 'fa-database', '.sh': 'fa-terminal', '.bat': 'fa-terminal', '.ps1': 'fa-terminal',
    '.jpg': 'fa-image', '.jpeg': 'fa-image', '.png': 'fa-image', '.gif': 'fa-image',
    '.zip': 'fa-file-zipper', '.rar': 'fa-file-zipper', '.7z': 'fa-file-zipper',
    '.exe': 'fa-gear', '.msi': 'fa-gear',
    '.toml': 'fa-gear', '.ini': 'fa-gear', '.cfg': 'fa-gear', '.conf': 'fa-gear',
  };
  var emoji = emojiMap[ext] || '📄';
  var fa = faMap[ext] || 'fa-file';
  return _dualIcon(emoji, fa);
}

function renderMarkdown(text) {
  if (!text) return '';
  // 代码块
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, '<pre><code>$2</code></pre>');
  // 行内代码
  text = text.replace(/`([^`]+)`/g, '<code>$1</code>');
  // 粗体
  text = text.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  // 换行
  text = text.replace(/\n/g, '<br>');
  return text;
}

function toast(msg, type = 'info') {
  const c = document.getElementById('toastContainer');
  const t = document.createElement('div');
  t.className = 'toast toast-' + type;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3000);
}

// ===== 自定义弹窗（替代系统 confirm/alert） =====
function showConfirm(title, message, onConfirm, onCancel) {
  var overlay = document.createElement('div'); overlay.className = 'modal-overlay';
  var card = document.createElement('div'); card.className = 'modal-card';
  card.innerHTML = '<h3>' + escHtml(title) + '</h3><p>' + escHtml(message) + '</p>' +
    '<div class="modal-btns"><button class="btn-cancel" id="modalCancel">取消</button><button class="btn-primary" id="modalOk">确定</button></div>';
  overlay.appendChild(card);
  document.body.appendChild(overlay);

  var close = function() { overlay.remove(); };
  overlay.addEventListener('click', function(e) { if (e.target === overlay) close(); });
  card.querySelector('#modalCancel').onclick = function() { close(); if (onCancel) onCancel(); };
  card.querySelector('#modalOk').onclick = function() { close(); if (onConfirm) onConfirm(); };
  // ESC 关闭
  var onKey = function(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); } };
  document.addEventListener('keydown', onKey);
}

function showDangerConfirm(title, message, onConfirm, onCancel) {
  var overlay = document.createElement('div'); overlay.className = 'modal-overlay';
  var card = document.createElement('div'); card.className = 'modal-card';
  card.innerHTML = '<h3>' + escHtml(title) + '</h3><p>' + escHtml(message) + '</p>' +
    '<div class="modal-btns"><button class="btn-cancel" id="modalCancel">取消</button><button class="btn-danger" id="modalOk">确定删除</button></div>';
  overlay.appendChild(card);
  document.body.appendChild(overlay);

  var close = function() { overlay.remove(); };
  overlay.addEventListener('click', function(e) { if (e.target === overlay) close(); });
  card.querySelector('#modalCancel').onclick = function() { close(); if (onCancel) onCancel(); };
  card.querySelector('#modalOk').onclick = function() { close(); if (onConfirm) onConfirm(); };
  var onKey = function(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); } };
  document.addEventListener('keydown', onKey);
}

function showAlert(title, message, onOk) {
  var overlay = document.createElement('div'); overlay.className = 'modal-overlay';
  var card = document.createElement('div'); card.className = 'modal-card';
  card.innerHTML = '<h3>' + escHtml(title) + '</h3><p>' + escHtml(message) + '</p>' +
    '<div class="modal-btns"><button class="btn-primary" id="modalOk">知道了</button></div>';
  overlay.appendChild(card);
  document.body.appendChild(overlay);

  var close = function() { overlay.remove(); if (onOk) onOk(); };
  overlay.addEventListener('click', function(e) { if (e.target === overlay) close(); });
  card.querySelector('#modalOk').onclick = close;
  var onKey = function(e) { if (e.key === 'Escape') { close(); document.removeEventListener('keydown', onKey); } };
  document.addEventListener('keydown', onKey);
}

// ===== 双图标系统：Emoji ↔ Font Awesome =====

// 智能滚动：用户不在底部时不强制下拉
function _autoScroll(el, threshold) {
  if (!el) return;
  threshold = threshold || 120;
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - threshold) {
    el.scrollTop = el.scrollHeight;
  }
}
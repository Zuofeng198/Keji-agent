
// ===== 全局状态 =====
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


let agentMode = localStorage.getItem('keji_agent_mode') || 'react';
let currentPlan = null;

// ===== Plan-and-Execute 模式 =====
async function loadAgentMode() {
  try {
    var res = await fetch('/chat/mode?session_id=' + sessionId);
    var data = await res.json();
    if (data.session_id) sessionId = data.session_id;
    agentMode = data.mode || 'react';
    updateModeUI(agentMode);
  } catch(e) {}
}
async function setAgentMode(mode) {
  document.querySelectorAll('.mode-btn').forEach(function(b){b.classList.remove('active')});
  var btn = document.querySelector('.mode-btn[data-mode="' + mode + '"]');
  if (btn) btn.classList.add('active');
  agentMode = mode;
  localStorage.setItem('keji_agent_mode', mode);
  try {
    await fetch('/chat/mode', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({session_id: sessionId, mode: mode})
    });
  } catch(e) {}
}
function updateModeUI(mode) {
  document.querySelectorAll('.mode-btn').forEach(function(b) {
    b.classList.toggle('active', b.dataset.mode === mode);
  });
}

async function sendPlanExecute(q, files) {
  try {
    var res = await fetch('/chat/plan', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({query: q, session_id: sessionId, conversation_id: currentConvId, files: files||[]})
    });
    sessionId = res.headers.get('X-Session-Id') || sessionId;
    var ncid = res.headers.get('X-Conversation-Id') || '';
    if (ncid) { currentConvId = ncid; conversationId = ncid; }
    var reader = res.body.getReader();
    var dec = new TextDecoder();
    var buf = '';
    var thinkingPanel = null, thinkingBody = null, thinkingHtml = '';
    var msgs = document.getElementById('chatMessages');
    while (true) {
      var r = await reader.read(); if (r.done) break;
      buf += dec.decode(r.value, {stream: true});
      var tokens = buf.split('\n'); buf = tokens.pop() || '';
      for (var ti = 0; ti < tokens.length; ti++) {
        var line = tokens[ti]; if (!line.startsWith('data: ')) continue;
        try {
          var evt = JSON.parse(line.slice(6));
          debugEvents.push(Object.assign({_time: Date.now()}, evt));
          switch (evt.phase) {
            case 'think_token':
              if (!thinkingPanel) {
                thinkingPanel = document.createElement('div');
                thinkingPanel.className = 'thinking-panel';
                var hdr = document.createElement('div');
                hdr.className = 'tp-header';
                hdr.innerHTML = '<span>'+_dualIcon('🧠','fa-brain')+' 思考计划</span><span class="tp-toggle">▼</span>';
                hdr.onclick = function() {
                  var body = this.nextElementSibling;
                  body.classList.toggle('collapsed');
                  var tog = this.querySelector('.tp-toggle');
                  tog.textContent = tog.textContent === '▼' ? '▶' : '▼';
                };
                thinkingPanel.appendChild(hdr);
                thinkingBody = document.createElement('div');
                thinkingBody.className = 'tp-body';
                thinkingPanel.appendChild(thinkingBody);
                msgs.appendChild(thinkingPanel);
                msgs.scrollTop = msgs.scrollHeight;
              }
              thinkingHtml += evt.token || '';
              thinkingBody.innerHTML = _replaceEmoji(thinkingHtml.replace(/</g,'&lt;').replace(/\n/g,'<br>'));
              msgs.scrollTop = msgs.scrollHeight;
              break;
            case 'plan':
              // 保留思考面板，标记为已完成
              if (thinkingPanel) {
                var hdr = thinkingPanel.querySelector('.tp-header span');
                if (hdr) hdr.innerHTML = _dualIcon('✅','fa-circle-check')+' 计划已就绪';
                if (thinkingBody) { thinkingBody.style.opacity = '0.5'; }
              }
              currentPlan = evt.plan;
              if (currentPlan) currentPlan._queryText = q;
              showPlanCard(evt.plan);
              break;
          }
        } catch(e) {}
      }
    }
  } catch(e) { toast('计划生成失败: ' + e.message, 'error'); isStreaming = false; document.getElementById('sendBtn').disabled = false; }
}
function showPlanCard(plan) {
  var steps = plan.steps || [];
  var h = '<div class="plan-steps">';
  if (steps.length) {
    for (var i = 0; i < steps.length; i++) {
      var s = steps[i];
      h += '<div class="plan-step"><span class="step-num">' + (i+1) + '</span><span class="step-desc">' + escHtml(s.description||'') + '</span><span class="step-tool">' + escHtml(s.tool||'') + '</span></div>';
    }
  } else { h += '<div class="plan-step" style="color:#999;background:transparent">无需预设计划，将自动调用工具执行</div>'; }
  h += '</div>';
  var card = document.createElement('div');
  card.className = 'plan-card'; card.id = 'planCard';
  card.innerHTML = '<div class="plan-title">'+_dualIcon('📋','fa-clock')+' ' + escHtml(plan.title||'执行计划') + '</div>' + h +
    '<div class="plan-actions"><button class="btn-primary" onclick="approvePlan()">✓ 批准执行</button><button class="btn-outline" onclick="revisePlan()">✏ 修改需求</button></div>';
  document.getElementById('chatMessages').appendChild(card);
  card.scrollIntoView({behavior:'smooth',block:'nearest'});
}
function revisePlan() {
  var card = document.getElementById('planCard'); if (card) card.remove();
  currentPlan = null; isStreaming = false;
  document.getElementById('sendBtn').disabled = false;
  document.getElementById('chatInput').focus();
}
async function approvePlan() {
  if (!currentPlan) return;
  var card = document.getElementById('planCard'); if (card) card.remove();
  isStreaming = true;
  document.getElementById('stopBtn').style.display = '';
  try {
    var q = currentPlan._queryText || document.getElementById('chatInput').value.trim() || '执行';
    var res = await fetch('/chat/execute', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({plan: currentPlan, query: q, session_id: sessionId, conversation_id: currentConvId})
    });
    sessionId = res.headers.get('X-Session-Id') || sessionId;
    var ncid = res.headers.get('X-Conversation-Id') || '';
    if (ncid) { currentConvId = ncid; conversationId = ncid; }
    currentReader = res.body.getReader();
    var reader = currentReader, dec = new TextDecoder(), buf = '', aiDiv = null, phaseDiv = null, fullReply = '', msgs = document.getElementById('chatMessages');
    while (true) {
      var r = await reader.read(); if (r.done) break;
      buf += dec.decode(r.value, {stream: true});
      var tokens = buf.split('\n'); buf = tokens.pop() || '';
      for (var ti = 0; ti < tokens.length; ti++) {
        var line = tokens[ti]; if (!line.startsWith('data: ')) continue;
        try {
          var evt = JSON.parse(line.slice(6));
          debugEvents.push(Object.assign({_time: Date.now()}, evt));
          switch (evt.phase) {
            case 'plan_exec_start': if(phaseDiv)phaseDiv.remove(); phaseDiv=addPhase(_dualIcon('⚡','fa-bolt')+' 执行 '+(evt.total_steps||0)+' 步...','thinking'); break;
            case 'plan_fallback':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('🔄','fa-rotate')+' '+(evt.message||'执行中'),'thinking');
              break;
            case 'thinking':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('🤔','fa-brain')+' 思考中...'+(evt.round?' ('+evt.round+')':''),'thinking');
              document.getElementById('stopBtn').style.display='';
              break;
            case 'think_token':
              if (!window._execThinkPanel) {
                window._execThinkPanel = document.createElement('div');
                window._execThinkPanel.className = 'thinking-panel';
                var hd = document.createElement('div'); hd.className = 'tp-header';
                hd.innerHTML = '<span>'+_dualIcon('🧠','fa-brain')+' 思考过程</span><span class="tp-toggle">▼</span>';
                hd.onclick = function(){this.nextElementSibling.classList.toggle('collapsed');var t=this.querySelector('.tp-toggle');t.textContent=t.textContent=='▼'?'▶':'▼';};
                window._execThinkPanel.appendChild(hd);
                window._execThinkBody = document.createElement('div'); window._execThinkBody.className = 'tp-body';
                window._execThinkPanel.appendChild(window._execThinkBody);
                msgs.appendChild(window._execThinkPanel);
                msgs.scrollTop = msgs.scrollHeight;
              }
              if (window._execThinkBody) {
                window._execThinkBody.innerHTML += _replaceEmoji(escHtml(evt.token || ''));
                msgs.scrollTop = msgs.scrollHeight;
              }
              break;
            case 'tool_call':
              if(phaseDiv)phaseDiv.remove();
              var tools=evt.tools||[];
              var tcCard=document.createElement('div');
              tcCard.className='tool-card tc-running';
              tcCard.innerHTML='<div class="tc-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');var t=this.querySelector(\'.tc-toggle\');t.textContent=t.textContent==\'▼\'?\'▶\':\'▼\'">'+
                '<span class="tc-icon">'+_dualIcon('🔧','fa-wrench')+'</span><span class="tc-name">调用: '+tools.join(', ')+'</span><span class="tc-status">执行中...</span><span class="tc-toggle">▼</span></div>'+
                '<div class="tc-body"><span style="color:#999">等待结果...</span></div>';
              msgs.appendChild(tcCard);
              msgs.scrollTop=msgs.scrollHeight;
              break;
            case 'plan_correction':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('🔧','fa-wrench')+' '+(evt.reason||'自动修正中...'),'thinking');
              var corrCard=document.createElement('div');
              corrCard.className='tool-card tc-running';
              corrCard.innerHTML='<div class="tc-header"><span class="tc-icon">'+_dualIcon('🔧','fa-wrench')+'</span><span class="tc-name">修正步骤'+(evt.step||'')+'：'+(evt.tool||'')+'</span><span class="tc-status">执行中...</span><span class="tc-toggle">▼</span></div><div class="tc-body"><span style="color:#999">等待结果...</span></div>';
              msgs.appendChild(corrCard);
              msgs.scrollTop=msgs.scrollHeight;
              break;
            case 'plan_step':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('⚡','fa-bolt')+' 步骤 '+evt.step+'/'+evt.total+'：'+(evt.description||''),'thinking');
              var stepCard=document.createElement('div');
              stepCard.className='tool-card tc-running';
              stepCard.id='tc_plan_'+evt.step;
              stepCard.innerHTML='<div class="tc-header"><span class="tc-icon">'+_dualIcon('⚡','fa-bolt')+'</span><span class="tc-name">步骤 '+evt.step+': '+(evt.description||'')+'</span><span class="tc-status">执行中...</span><span class="tc-toggle">▼</span></div><div class="tc-body"><span style="color:#999">等待结果...</span></div>';
              msgs.appendChild(stepCard);
              msgs.scrollTop=msgs.scrollHeight;
              break;
            case 'tool_result':
              if(phaseDiv)phaseDiv.remove();
              var tc=msgs.querySelectorAll('.tool-card');
              var lc=null;for(var _ti=tc.length-1;_ti>=0;_ti--){if(!tc[_ti].classList.contains('tc-done')){lc=tc[_ti];break;}}if(!lc)lc=tc[tc.length-1];
              if(lc&&!lc.classList.contains('tc-done')){
                lc.classList.remove('tc-running'); lc.classList.add('tc-done');
                var raw=evt.result||'';
                var clean=raw.split('\n').filter(function(l){return !/^\{"timestamp"/.test(l.trim());}).join('\n').trim();
                if(!clean) clean=raw.replace(/\{"timestamp"[^}]*\}/g,'').trim()||raw;
                var snip=clean.substring(0,250);
                var isErr=/错误|出错|执行超时|不存在|失败/.test(raw);
                if(isErr)lc.classList.add('tc-error');
                lc.querySelector('.tc-status').textContent=isErr?(_dualIcon('❌','fa-circle-xmark')+' 出错'):(_dualIcon('✅','fa-circle-check')+' 完成');
                var bd=lc.querySelector('.tc-body'); if(bd)bd.textContent=snip||'(无输出)';
              }else{phaseDiv=addPhase((evt.result&&/错误|出错/.test(evt.result)?_dualIcon('❌','fa-circle-xmark'):_dualIcon('✅','fa-circle-check'))+' '+evt.tool,'result');}
              break;
            case 'plan_eval':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('🔍','fa-magnifying-glass')+' '+(evt.message||'验证中'),'thinking');
              break;
            case 'plan_eval_done':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase((evt.ok?_dualIcon('✅','fa-circle-check'):_dualIcon('🔧','fa-wrench'))+' '+(evt.message||''), evt.ok?'result':'thinking');
              setTimeout(function(){if(phaseDiv)phaseDiv.remove();}, 2000);
              break;
            case 'plan_answering': if(phaseDiv)phaseDiv.remove(); phaseDiv=addPhase(_dualIcon('🤔','fa-brain')+' '+(evt.message||'思考中'),'thinking'); break;
            case 'answering': if(phaseDiv)phaseDiv.remove(); phaseDiv=addPhase(_dualIcon('🤔','fa-brain')+' 正在生成回答...','thinking'); aiDiv=addMessage('assistant',''); document.getElementById('stopBtn').style.display='none'; break;
            case 'answer':
              if(!aiDiv){if(phaseDiv)phaseDiv.remove();aiDiv=addMessage('assistant','');}
              fullReply+=evt.token||'';
              var display=fullReply;
              // 检测是否整段都是 Python 代码（防幻觉）
              if(fullReply.length>60){
                var trimmed=fullReply.trim();
                var codeLines=trimmed.split('\n').filter(function(l){return /^(import\s|from\s|def\s|class\s|print\(|#|if\s__name__)/.test(l.trim());});
                var totalLines=trimmed.split('\n').filter(function(l){return l.trim();}).length;
                if(codeLines.length>0 && codeLines.length>=totalLines*0.5){
                  display='⚠️ 回答包含大量代码，可能未正确总结。请刷新重试。\n\n<details><summary>原始输出</summary>\n\n```\n'+fullReply+'\n```\n</details>';
                }
              }
              aiDiv.innerHTML=renderMarkdown(escHtml(display));
              msgs.scrollTop=msgs.scrollHeight;
              break;
            case 'done': document.querySelectorAll('.phase-badge').forEach(function(e){e.remove()}); document.getElementById('stopBtn').style.display='none'; break;
          }
        } catch(e) {}
      }
    }
  } catch(e) { toast('执行失败: '+e.message, 'error'); }
  document.querySelectorAll('.phase-badge').forEach(function(e){e.remove()});
  document.getElementById('stopBtn').style.display='none';
  isStreaming = false; document.getElementById('sendBtn').disabled = false;
}
// ===== 页面切换 =====
function switchPage(page) {
  currentPage = page;
  document.querySelectorAll('.page').forEach(function(p){p.classList.remove('active');p.style.display='none';});
  var t = document.getElementById('page-' + page);
  if (t) { t.classList.add('active'); t.style.display='flex'; }
  document.querySelectorAll('.nav-item').forEach(function(n){n.classList.remove('active');});
  var ni = document.querySelector('.nav-item[data-page="' + page + '"]');
  if (ni) ni.classList.add('active');

  if (page === 'knowledge') { loadKnowledgeBase(); }
  if (page === 'files') { loadDrives(); }
  if (page === 'database') { loadDbConfigs(); loadDbConfigSelect(); }
}

// ===== Toast 通知 =====
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
// 通用 emoji → FA 映射
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
    fetch('/tools').then(function(r){return r.json()}),
    fetch('/api/tools/display').then(function(r){return r.json()})
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

// ===== 系统状态 =====
function checkStatus() {
  fetch('/api/status').then(r => r.json()).then(d => {
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

function newChat() {
  conversationId = '';
  currentConvId = '';
  sessionId = '';
  document.getElementById('convTitle').textContent = '新对话';
  document.getElementById('chatMessages').innerHTML =
    '<div class="empty-state">' +
      '<div class="big-icon">' + _dualIcon('👋', 'fa-hand-wave') + '</div>' +
      '<h3>你好！我是科吉</h3>' +
      '<p>你的企业级 AI 助手。我可以帮你整理文件、搜索知识库、分析文档、回答问题。在下方输入框开始对话。</p>' +
    '</div>';
}

function toggleConvPanel() {
  const panel = document.getElementById('convPanel');
  panel.classList.toggle('open');
  if (panel.classList.contains('open')) loadConvList();
}

function loadConvList() {
  fetch('/api/conversations').then(r => r.json()).then(d => {
    const list = document.getElementById('convList');
    if (!d.conversations || d.conversations.length === 0) {
      list.innerHTML = '<div class="empty-list">暂无对话历史</div>';
      return;
    }
    list.innerHTML = d.conversations.map(c => `
      <div class="conv-item" onclick="loadConversation('${c.id}')">
        <div class="conv-title">${escHtml(c.title)}</div>
        <div class="conv-time">${c.updated_at || ''} · ${c.message_count || 0} 条</div>
      </div>
    `).join('');
  }).catch(() => {});
}

function loadConversation(id) {
  fetch('/api/conversations/' + id).then(r => r.json()).then(d => {
    currentConvId = id;
    conversationId = id;
    sessionId = id;  // ← 关键：让后续消息发到同一个会话
    document.getElementById('convTitle').textContent = d.conversation.title;
    document.getElementById('convPanel').classList.remove('open');

    const msgs = document.getElementById('chatMessages');
    msgs.innerHTML = '';
    if (d.messages && d.messages.length) {
      d.messages.forEach(m => {
        addMessage(m.role, escHtml(m.content));
      });
    }
  }).catch(() => toast('加载对话失败', 'error'));
}

function onChatKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
}

/* ═══════════════ 文件上传 ═══════════════ */
let uploadedFiles = [];
var uploadIdCounter = 0;

function handleFileSelect(event) {
  var files = event.target.files;
  if (!files.length) return;
  for (var fi = 0; fi < files.length; fi++) uploadFileItem(files[fi]);
  event.target.value = '';
}

function uploadFileItem(file) {
  var preview = document.getElementById('filePreview');
  var itemId = 'fu_' + (++uploadIdCounter);

  // 显示上传中状态
  preview.insertAdjacentHTML('beforeend',
    '<div class="file-preview" id="' + itemId + '">' +
      '<span class="file-icon">' + getFileIcon('.' + (file.name.split('.').pop() || 'bin')) + '</span>' +
      '<span class="file-name">' + escHtml(file.name) + '</span>' +
      '<span class="upload-progress">⏳ 上传中...</span>' +
    '</div>'
  );

  var formData = new FormData();
  formData.append('file', file);

  fetch('/api/upload', { method: 'POST', body: formData })
    .then(function(r) {
      if (!r.ok) throw new Error('服务器返回: ' + r.status);
      return r.json();
    })
    .then(function(data) {
      if (data.status !== 'ok') throw new Error(data.message || '上传失败');
      uploadedFiles.push({ name: data.file_name, path: data.file_path, size: data.size });
      var el = document.getElementById(itemId);
      if (!el) return;
      // 用 data-path 代替 onclick 内联，避免反斜杠转义问题
      el.setAttribute('data-path', data.file_path);
      el.innerHTML =
        '<span class="file-icon">' + getFileIcon(data.ext) + '</span>' +
        '<span class="file-name">' + escHtml(data.file_name) + '</span>' +
        '<span class="file-size">' + (data.size_str || '') + '</span>' +
        '<span class="file-remove" title="移除">×</span>';
    })
    .catch(function(err) {
      var el = document.getElementById(itemId);
      if (el) {
        el.innerHTML = '<span class="file-icon">❌</span><span class="file-name">' + escHtml(file.name) + ' 上传失败</span>';
        el.title = err.message || '上传出错';
      }
    });
}

// 事件委托：点击 × 移除文件
document.addEventListener('click', function(e) {
  var target = e.target;
  if (!target.classList.contains('file-remove')) return;
  var preview = target.closest('.file-preview');
  if (!preview) return;
  var path = preview.getAttribute('data-path') || '';
  preview.remove();
  if (path) {
    uploadedFiles = uploadedFiles.filter(function(f) { return f.path !== path; });
  }
});

function setupDragDrop() {
  var col = document.querySelector('.chat-col');
  if (!col) return;
  col.addEventListener('dragenter', function(e) { e.preventDefault(); col.classList.add('drag-over'); });
  col.addEventListener('dragover', function(e) { e.preventDefault(); col.classList.add('drag-over'); });
  col.addEventListener('dragleave', function(e) {
    if (!e.currentTarget.contains(e.relatedTarget)) col.classList.remove('drag-over');
  });
  col.addEventListener('drop', function(e) {
    e.preventDefault();
    col.classList.remove('drag-over');
    if (e.dataTransfer.files.length) {
      for (var fi = 0; fi < e.dataTransfer.files.length; fi++) uploadFileItem(e.dataTransfer.files[fi]);
    }
  });
}
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', setupDragDrop);
} else { setupDragDrop(); }

async function sendChat() {
  const input = document.getElementById('chatInput');
  const btn = document.getElementById('sendBtn');
  const msg = input.value.trim();
  if (isStreaming) return;

  isStreaming = true;
  btn.disabled = true;

  // 清除空状态
  const msgs = document.getElementById('chatMessages');
  const empty = msgs.querySelector('.empty-state');
  if (empty) empty.remove();

  // 收集已上传文件路径并清空预览
  const files = uploadedFiles.map(function(f) { return f.path; });
  uploadedFiles = [];
  document.getElementById('filePreview').innerHTML = '';

  // 如果只有文件没有文字，用文件名作为 query
  var queryText = msg;
  if (!queryText && files.length) {
    queryText = '请帮我处理这些文件：' + files.map(function(f) {
      return f.split('/').pop().split('\\').pop();
    }).join(', ');
  }
  if (!queryText) { isStreaming = false; btn.disabled = false; return; }

  addMessage('user', escHtml(queryText));
  input.value = '';
  input.style.height = 'auto';

  try {
    const res = await fetch('/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        query: queryText,
        session_id: sessionId,
        conversation_id: currentConvId,
        files: files
      })
    });

    sessionId = res.headers.get('X-Session-Id') || sessionId;
    const newConvId = res.headers.get('X-Conversation-Id') || '';
    if (newConvId) { currentConvId = newConvId; conversationId = newConvId; }

    currentReader = res.body.getReader();
    const reader = currentReader;
    const dec = new TextDecoder();
    let buf = '';
    let aiDiv = null;
    let phaseDiv = null;
    let fullReply = '';
    let thinkingPanel = null;
    let thinkingBody = null;
    let thinkingHtml = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop() || '';

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        try {
          const evt = JSON.parse(line.slice(6));
          debugEvents.push(Object.assign({_time: Date.now()}, evt));
          switch (evt.phase) {
            case 'knowledge':
              phaseDiv = addPhase('📖 已检索知识库', 'knowledge');
              break;
            case 'think_token':
              if (isShowThinking()) {
                if (!thinkingPanel) {
                  const tp = document.createElement('div');
                  tp.className = 'thinking-panel';
                  tp.innerHTML = '<div class="tp-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');var t=this.querySelector(\'.tp-toggle\');t.textContent=t.textContent==\'▼\'?\'▶\':\'▼\'">' +
                    '<span>' + _dualIcon('🧠', 'fa-brain') + ' 思考过程</span><span class="tp-toggle">▼</span></div><div class="tp-body"></div>';
                  msgs.appendChild(tp);
                  thinkingPanel = tp;
                  thinkingBody = tp.querySelector('.tp-body');
                  msgs.scrollTop = msgs.scrollHeight;
                }
                thinkingHtml += evt.token || '';
                thinkingBody.innerHTML = _replaceEmoji(thinkingHtml);
                msgs.scrollTop = msgs.scrollHeight;
              }
              break;
            case 'thinking':
              if (phaseDiv) phaseDiv.remove();
              phaseDiv = addPhase('🤔 思考中... (' + (evt.round||'') + ')', 'thinking');
              document.getElementById('stopBtn').style.display = '';
              break;
            case 'self_check':
              if (phaseDiv) phaseDiv.remove();
              phaseDiv = addPhase('🔄 科吉二次确认中...', 'thinking');
              document.getElementById('stopBtn').style.display = '';
              break;
            case 'tool_call':
              if (phaseDiv) phaseDiv.remove();
              document.getElementById('stopBtn').style.display = '';
              (evt.tools||[]).forEach(function(tname) {
                var card = document.createElement('div');
                card.className = 'tool-card tc-running';
                card.id = 'tc_' + tname + '_' + Date.now();
                card.innerHTML = '<div class="tc-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');var t=this.querySelector(\'.tc-toggle\');t.textContent=t.textContent==\'▼\'?\'▶\':\'▼\'">' +
                  '<span class="tc-icon">⚡</span>' +
                  '<span class="tc-name">' + escHtml(tname) + '</span>' +
                  '<span class="tc-status">运行中...</span>' +
                  '<span class="tc-toggle">▼</span></div>' +
                  '<div class="tc-body"><span style="color:#999">等待结果...</span></div>';
                msgs.appendChild(card);
                msgs.scrollTop = msgs.scrollHeight;
              });
              if (thinkingBody && isShowThinking()) {
                thinkingHtml += '\n──────────────\n🔧 调用工具: ' + (evt.tools||[]).join(', ') + '\n';
                thinkingBody.innerHTML = _replaceEmoji(thinkingHtml);
                msgs.scrollTop = msgs.scrollHeight;
              }
              break;
            case 'tool_result':
              if (phaseDiv) phaseDiv.remove();
              // 更新对应的 tool card
              var cards = msgs.querySelectorAll('.tool-card');
              var lastCard = cards[cards.length - 1];
              if (lastCard && !lastCard.classList.contains('tc-done')) {
                lastCard.classList.remove('tc-running');
                lastCard.classList.add('tc-done');
                var snippet = (evt.result||'').substring(0, 300);
                var isErr = evt.result && (evt.result.indexOf('错误') >= 0 || evt.result.indexOf('出错') >= 0);
                if (isErr) lastCard.classList.add('tc-error');
                lastCard.querySelector('.tc-status').textContent = isErr ? '❌ 出错' : '✅ 完成';
                var body = lastCard.querySelector('.tc-body');
                body.textContent = snippet;
              } else {
                phaseDiv = addPhase((evt.result && evt.result.indexOf('错误') >= 0 ? '❌ ' : '✅ ') + evt.tool + ' 完成', evt.result && evt.result.indexOf('错误') >= 0 ? 'error' : 'result');
              }
              if (thinkingBody && isShowThinking()) {
                var snippet2 = (evt.result||'').substring(0, 150);
                thinkingHtml += '✅ ' + evt.tool + ' → ' + snippet2 + '\n';
                thinkingBody.innerHTML = _replaceEmoji(thinkingHtml);
                msgs.scrollTop = msgs.scrollHeight;
              }
              break;
            case 'answering':
              if (phaseDiv) phaseDiv.remove();
              aiDiv = addMessage('assistant', '');
              document.getElementById('stopBtn').style.display = 'none';
              break;
            case 'answer':
              if (!aiDiv) { if(phaseDiv)phaseDiv.remove(); aiDiv = addMessage('assistant',''); }
              fullReply += evt.token || '';
              aiDiv.innerHTML = renderMarkdown(escHtml(fullReply));
              msgs.scrollTop = msgs.scrollHeight;
              break;
            case 'error':
              toast('错误: ' + escHtml(evt.message||''), 'error');
              break;
            case 'done':
              document.querySelectorAll('.phase-badge').forEach(e => e.remove());
              document.getElementById('stopBtn').style.display = 'none';
              break;
          }
        } catch(e) {}
      }
    }
    document.querySelectorAll('.phase-badge').forEach(e => e.remove());
  } catch (e) {
    toast('网络错误: ' + e.message, 'error');
  }
  isStreaming = false;
  btn.disabled = false;
  document.getElementById('stopBtn').style.display = 'none';
  input.focus();
}

function addMessage(role, html) {
  const msgs = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'message ' + role;
  var avatarHtml = role === 'user' ? _dualIcon('👤', 'fa-user') : _dualIcon('🤖', 'fa-robot');
  div.innerHTML =
    '<div class="avatar">' + avatarHtml + '</div>' +
    '<div class="bubble">' + html + '</div>' +
    '<button class="copy-btn" onclick="copyMessage(this)" title="复制内容">' + _dualIcon('📋', 'fa-copy') + '</button>';
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div.querySelector('.bubble');
}

function copyMessage(btn) {
  var bubble = btn.parentNode.querySelector('.bubble');
  if (!bubble) return;
  var text = bubble.textContent || '';
  var doneIcon = _dualIcon('✅', 'fa-circle-check');
  var copyIcon = _dualIcon('📋', 'fa-copy');
  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(text).then(function() {
      btn.innerHTML = doneIcon;
      setTimeout(function() { btn.innerHTML = copyIcon; }, 1500);
    });
  } else {
    // fallback
    var ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    btn.innerHTML = doneIcon;
    setTimeout(function() { btn.innerHTML = copyIcon; }, 1500);
  }
}

function addPhase(label, cls) {
  const msgs = document.getElementById('chatMessages');
  const div = document.createElement('div');
  div.className = 'phase-badge phase-' + cls;
  // 如果已通过 _dualIcon() 传入了 HTML，直接使用 innerHTML
  if (label.indexOf('<i class=') === 0) {
    div.innerHTML = label;
  } else {
    var chars = Array.from(label);
    var first = chars[0];
    if (first && _emojiFA[first]) {
      div.innerHTML = _dualIcon(first, _emojiFA[first]) + ' ' + chars.slice(1).join('').trim();
    } else {
      div.textContent = label;
    }
  }
  msgs.appendChild(div);
  msgs.scrollTop = msgs.scrollHeight;
  return div;
}

// ================================================================
// 知识库
// ================================================================

function loadKnowledgeBase() {
  loadKbStats();
  loadKbDocs();
}

function loadKbStats() {
  fetch('/api/knowledge/stats').then(r => r.json()).then(d => {
    document.querySelector('#kbStats .stat-card:nth-child(1) .number').textContent = d.total_documents || 0;
    document.querySelector('#kbStats .stat-card:nth-child(2) .number').textContent = d.total_chunks || 0;
    document.querySelector('#kbStats .stat-card:nth-child(3) .number').textContent = d.vector_count || 0;
  }).catch(() => {});
}

function loadKbDocs() {
  fetch('/api/knowledge/documents').then(r => r.json()).then(d => {
    const list = document.getElementById('kbDocList');
    const countEl = document.getElementById('kbDocCount');
    if (countEl) countEl.textContent = (d.documents ? d.documents.length : 0) + ' 个文档';
    if (!d.documents || d.documents.length === 0) {
      list.innerHTML = '<div class="empty-list">' + _dualIcon('📭', 'fa-inbox') + ' 知识库为空，请输入文件路径进行索引</div>';
      return;
    }
    list.innerHTML = d.documents.map(doc => `
      <div class="doc-item">
        ${kbMultiSelect ? '<input type="checkbox" class="kb-checkbox" value="' + doc.id + '" style="margin-right:10px;width:16px;height:16px;cursor:pointer;flex-shrink:0">' : ''}
        <span class="doc-icon">${getFileIcon(doc.file_type)}</span>
        <div class="doc-info">
          <div class="doc-name">${escHtml(doc.file_name)}</div>
          <div class="doc-meta">${escHtml(doc.file_path)} · ${doc.chunk_count || 0} 块 · ${doc.indexed_at || ''}</div>
        </div>
        <span class="doc-type">${doc.file_type || '未知'}</span>
        ${kbMultiSelect ? '' : '<button class="btn btn-sm btn-danger" onclick="deleteDoc(\'' + doc.id + '\')">删除</button>'}
      </div>
    `).join('');
  }).catch(() => {
    document.getElementById('kbDocList').innerHTML = '<div class="empty-list">加载失败</div>';
  });
}

function indexFromInput() {
  const path = document.getElementById('kbPath').value.trim();
  if (!path) { toast('请输入文件或文件夹路径', 'error'); return; }

  const btn = document.querySelector('#page-knowledge .btn-primary');
  const cancelBtn = document.getElementById('kbCancelBtn');
  btn.disabled = true;
  btn.textContent = '⏳ 索引中...';
  cancelBtn.style.display = 'inline-flex';

  fetch('/api/knowledge/index', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path, recursive: true })
  }).then(r => r.json()).then(d => {
    if (d.status === 'ok') {
      const count = d.result ? (d.result.chunk_count || d.result.success || 0) : 0;
      toast('✅ 索引完成！处理了 ' + count + ' 个文件块', 'success');
      loadKbStats();
      loadKbDocs();
    } else {
      toast('索引失败: ' + JSON.stringify(d), 'error');
    }
  }).catch(e => {
    toast('请求失败: ' + e.message, 'error');
  }).finally(() => {
    btn.disabled = false;
    btn.textContent = '📥 索引到知识库';
    cancelBtn.style.display = 'none';
  });
}

function cancelIndexing() {
  fetch('/api/knowledge/cancel', { method: 'POST' })
    .then(r => r.json()).then(d => {
      toast('⏹ 已终止索引', 'info');
    }).catch(() => toast('取消失败', 'error'));
}

function deleteDoc(docId) {
  showDangerConfirm('删除知识库文档', '确定要从知识库中删除此文档吗？', function() {
    fetch('/api/knowledge/document/' + docId, { method: 'DELETE' })
      .then(r => r.json()).then(d => {
        toast('文档已删除', 'success');
        loadKbDocs();
        loadKbStats();
      }).catch(e => toast('删除失败', 'error'));
  });
}

// === 知识库多选删除 ===
var kbMultiSelect = false;

function toggleKbMultiSelect() {
  kbMultiSelect = !kbMultiSelect;
  document.getElementById('kbToolbar').style.display = kbMultiSelect ? 'flex' : 'none';
  document.getElementById('kbMultiBtn').innerHTML = (kbMultiSelect ? _dualIcon('☑', 'fa-square-check') + ' 取消' : _dualIcon('☑', 'fa-square-check') + ' 多选');
  loadKbDocs();
}

function selectAllKbDocs() {
  var cbs = document.querySelectorAll('.kb-checkbox');
  var allChecked = cbs.length > 0;
  for (var i = 0; i < cbs.length; i++) { if (!cbs[i].checked) { allChecked = false; break; } }
  for (var i = 0; i < cbs.length; i++) { cbs[i].checked = !allChecked; }
}

function getSelectedKbIds() {
  var ids = [];
  var cbs = document.querySelectorAll('.kb-checkbox:checked');
  for (var i = 0; i < cbs.length; i++) { ids.push(cbs[i].value); }
  return ids;
}

function deleteSelectedKbDocs() {
  var ids = getSelectedKbIds();
  if (ids.length === 0) { showAlert('提示', '请先勾选要删除的文档'); return; }
  showDangerConfirm('批量删除文档', '确定删除选中的 ' + ids.length + ' 个文档吗？', function() {
    Promise.all(ids.map(function(id) {
      return fetch('/api/knowledge/document/' + id, { method: 'DELETE' });
    })).then(function() {
      toast('已删除 ' + ids.length + ' 个文档', 'success');
      loadKbDocs();
      loadKbStats();
    }).catch(function(){ showAlert('错误', '删除失败'); });
  });
}

function clearAllKnowledge() {
  showDangerConfirm('清空知识库', '确定要清空整个知识库吗？\n所有已索引的文档和向量数据将被删除。', function() {
    showDangerConfirm('⚠️ 再次确认', '此操作不可恢复！\n确定清空所有知识库数据吗？', function() {
      fetch('/api/knowledge/clear', { method: 'POST' })
        .then(r => r.json()).then(d => {
          toast('知识库已清空（' + (d.count || 0) + ' 个文档）', 'success');
          loadKbDocs();
          loadKbStats();
        }).catch(e => toast('清空失败: ' + e.message, 'error'));
    });
  });
}

function searchKnowledge() {
  const input = document.getElementById('kbSearch');
  const pathInput = document.getElementById('kbPath');

  if (input.style.display === 'none') {
    input.style.display = 'block';
    input.focus();
    return;
  }

  const q = input.value.trim();
  if (!q) { input.style.display = 'none'; return; }

  fetch('/api/knowledge/search?query=' + encodeURIComponent(q) + '&n=10')
    .then(r => r.json()).then(d => {
      const list = document.getElementById('kbDocList');
      if (!d.results || d.results.length === 0) {
        list.innerHTML = '<div class="empty-list">未找到相关内容</div>';
        return;
      }
      list.innerHTML = '<div style="margin-bottom:12px;font-size:14px;color:var(--text-secondary)">🔍 搜索: "' + escHtml(q) + '" · 找到 ' + d.total + ' 条结果</div>';
      list.innerHTML += d.results.map(r => `
        <div class="doc-item" style="flex-direction:column;align-items:stretch">
          <div style="display:flex;align-items:center;gap:8px;width:100%">
            <span>${getFileIcon('.' + (r.source.split('.').pop() || 'txt'))}</span>
            <span style="font-weight:600;font-size:13px">${escHtml(r.source)}</span>
            <span style="font-size:11px;color:var(--text-secondary)">相关度: ${(1 - r.score).toFixed(2)}</span>
          </div>
          <div style="font-size:13px;color:var(--text-secondary);margin-top:4px;line-height:1.5">${escHtml(r.content)}</div>
        </div>
      `).join('');
      input.style.display = 'none';
      input.value = '';
    }).catch(() => toast('搜索失败', 'error'));
}

// ================================================================
// 文件浏览
// ================================================================

function loadDrives() {
  fetch('/api/files/drives').then(r => r.json()).then(d => {
    const div = document.getElementById('fbDrives');
    // 使用 data-path 避免路径中反斜杠破坏 onclick 字符串
    div.innerHTML = (d.drives || []).map(drv =>
      `<button class="drive-btn" data-path="${drv.path}">` + _dualIcon('💾', 'fa-floppy-disk') + ` ${drv.name}</button>`
    ).join('');
    // 事件委托处理盘符点击
    div.onclick = function(e) {
      var btn = e.target.closest('.drive-btn');
      if (btn) listFiles(btn.getAttribute('data-path'));
    };
    // 默认打开 C:
    if (d.drives && d.drives.length) listFiles('C:\\');
  }).catch(() => {});
}

function listFiles(path) {
  document.getElementById('fbPath').textContent = path;
  document.getElementById('fbItems').innerHTML = '<div class="loading"><div class="spinner"></div>加载中...</div>';

  fetch('/api/files/list?path=' + encodeURIComponent(path))
    .then(r => r.json()).then(d => {
      const items = document.getElementById('fbItems');
      items.innerHTML = '';

      if (d.parent) {
        const up = document.createElement('div');
        up.className = 'fb-item';
        up.innerHTML = '<span class="item-icon">' + _dualIcon('📂', 'fa-folder-open') + '</span><span class="item-name" style="font-weight:600">.. 上级目录</span>';
        up.onclick = () => listFiles(d.parent);
        items.appendChild(up);
      }

      (d.items || []).forEach(item => {
        const div = document.createElement('div');
        div.className = 'fb-item';
        div.setAttribute('data-path', item.path);
        div.setAttribute('data-dir', item.is_dir ? '1' : '0');
        if (item.is_supported) div.setAttribute('data-indexable', '1');
        const icon = item.is_dir ? _dualIcon('📁', 'fa-folder') : getFileIcon(item.ext);
        const size = item.is_dir ? '' : item.size_str;

        let html = '<span class="item-icon">' + icon + '</span>';
        if (item.is_dir) {
          html += '<span class="item-name">' + escHtml(item.name) + '</span>';
          html += '<span class="item-meta">' + (item.modified || '') + '</span>';
        } else {
          html += '<span class="item-name">' + escHtml(item.name) + '</span>';
          html += '<span class="item-meta">' + size + ' · ' + (item.modified || '') + '</span>';
          if (item.is_supported) {
            html += '<button class="index-btn">+ 索引</button>';
          }
        }
        div.innerHTML = html;

        // 文件夹单击进入；文件双击打开；索引按钮点击索引
        div.onclick = function(e) {
          var btn = e.target.closest('.index-btn');
          if (btn) {
            e.stopPropagation();
            quickIndex(this.getAttribute('data-path'));
            return;
          }
          if (this.getAttribute('data-dir') === '1') {
            listFiles(this.getAttribute('data-path'));
          }
        };
        div.ondblclick = function(e) {
          if (e.target.closest('.index-btn')) return;
          if (this.getAttribute('data-dir') === '0') {
            var fp = this.getAttribute('data-path');
            var fname = fp.split('\\').pop();
            showConfirm('打开文件', '确定要用系统默认程序打开以下文件吗？\n\n' + fname, function() {
              openLocalFile(fp);
            });
          }
        };
        items.appendChild(div);
      });
    }).catch(e => {
      document.getElementById('fbItems').innerHTML = '<div class="empty-list">❌ 加载失败: ' + e.message + '</div>';
    });
}

function goUpDir() {
  const current = document.getElementById('fbPath').textContent;
  const parent = current.split('\\').filter(Boolean).slice(0, -1).join('\\');
  if (parent.length >= 2) {
    listFiles(parent + '\\');
  } else {
    loadDrives();
  }
}

function refreshFiles() {
  const current = document.getElementById('fbPath').textContent;
  if (current) listFiles(current);
}

function openLocalFile(filePath) {
  fetch('/api/files/open?path=' + encodeURIComponent(filePath), { method: 'POST' })
    .then(r => r.json()).then(d => {
      if (d.status === 'ok') toast('已打开: ' + filePath.split('\\').pop(), 'success');
    }).catch(e => toast('打开失败: ' + e.message, 'error'));
}

function quickIndex(filePath) {
  fetch('/api/knowledge/index', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: filePath, recursive: false })
  }).then(r => r.json()).then(d => {
    if (d.status === 'ok') toast('✅ 已索引到知识库', 'success');
    else toast('索引失败: ' + (d.message || d.detail || ''), 'error');
  }).catch(e => toast('索引失败: ' + e.message, 'error'));
}

// ================================================================
// 设置
// ================================================================

/* 思考过程显示开关 */
function loadThinkingSetting() {
  var enabled = localStorage.getItem('keji_show_thinking');
  if (enabled === null) enabled = 'true';
  document.getElementById('setShowThinking').checked = enabled === 'true';
  updateThinkingToggleUI();
}
function saveThinkingSetting() {
  var checked = document.getElementById('setShowThinking').checked;
  localStorage.setItem('keji_show_thinking', checked ? 'true' : 'false');
  updateThinkingToggleUI();
}
function updateThinkingToggleUI() {
  var on = document.getElementById('setShowThinking').checked;
  document.getElementById('thinkingToggleTrack').style.background = on ? 'var(--primary)' : '#ccc';
  document.getElementById('thinkingToggleThumb').style.transform = on ? 'translateX(20px)' : 'none';
}
function isShowThinking() {
  return localStorage.getItem('keji_show_thinking') !== 'false';
}

/* ===== 图标主题切换 ===== */
function applyIconTheme(theme) {
  if (theme === 'fa') {
    document.body.classList.add('theme-fa');
  } else {
    document.body.classList.remove('theme-fa');
  }
  localStorage.setItem('keji_icon_theme', theme);
}
function loadIconTheme() {
  var theme = localStorage.getItem('keji_icon_theme') || 'emoji';
  document.getElementById('setIconTheme').value = theme;
  applyIconTheme(theme);
}

function toggleModelType() {
  var t = document.getElementById('setModelType').value;
  document.getElementById('ollamaSettings').style.display = t === 'ollama' ? '' : 'none';
  document.getElementById('openaiSettings').style.display = t === 'openai' ? '' : 'none';
}

function loadModelSettings() {
  fetch('/api/settings').then(r => r.json()).then(d => {
    var s = d.db_settings || {};
    if (s.model_type) document.getElementById('setModelType').value = s.model_type;
    if (s.ollama_url) document.getElementById('setOllamaUrl').value = s.ollama_url;
    if (s.chat_model) document.getElementById('setChatModel').value = s.chat_model;
    if (s.openai_base_url) document.getElementById('setOpenaiUrl').value = s.openai_base_url;
    if (s.openai_api_key) document.getElementById('setOpenaiKey').value = s.openai_api_key;
    if (s.openai_model) document.getElementById('setOpenaiModel').value = s.openai_model;
    if (s.embed_model) document.getElementById('setEmbedModel').value = s.embed_model;
    toggleModelType();
  }).catch(function(){});
}

function testModelConn() {
  var btn = document.getElementById('testModelBtn');
  var result = document.getElementById('testModelResult');
  btn.disabled = true;
  btn.textContent = '⏳ 测试中...';
  result.textContent = '';
  result.style.color = '#999';

  var modelType = document.getElementById('setModelType').value;
  var baseUrl, apiKey, model;
  if (modelType === 'ollama') {
    baseUrl = document.getElementById('setOllamaUrl').value;
    model = document.getElementById('setChatModel').value;
    apiKey = '';
  } else {
    baseUrl = document.getElementById('setOpenaiUrl').value;
    apiKey = document.getElementById('setOpenaiKey').value;
    model = document.getElementById('setOpenaiModel').value;
  }

  fetch('/api/models/test', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model_type: modelType, base_url: baseUrl, api_key: apiKey, model: model })
  }).then(function(r){ return r.json(); }).then(function(d){
    result.textContent = d.message || (d.status === 'ok' ? '连接成功' : '连接失败');
    result.style.color = d.status === 'ok' ? '#27ae60' : '#e74c3c';
  }).catch(function(e){
    result.textContent = '❌ 请求失败: ' + e.message;
    result.style.color = '#e74c3c';
  }).finally(function(){
    btn.disabled = false;
    btn.textContent = '🔄 测试模型连接';
  });
}

function saveSettings() {
  const settings = {
    model_type: document.getElementById('setModelType').value,
    ollama_url: document.getElementById('setOllamaUrl').value,
    chat_model: document.getElementById('setChatModel').value,
    openai_base_url: document.getElementById('setOpenaiUrl').value,
    openai_api_key: document.getElementById('setOpenaiKey').value,
    openai_model: document.getElementById('setOpenaiModel').value,
    embed_model: document.getElementById('setEmbedModel').value,
    chunk_size: document.getElementById('setChunkSize').value,
    chunk_overlap: document.getElementById('setOverlap').value,
    top_k: document.getElementById('setTopK').value,
  };

  fetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings })
  }).then(r => r.json()).then(d => {
    toast('设置已保存，新建对话将使用新模型', 'success');
  }).catch(() => toast('保存失败', 'error'));
}

/* ===== 企业微信配置 ===== */
function loadWorkConfig() {
  fetch('/api/settings').then(function(r){return r.json()}).then(function(d){
    var s = d.db_settings || {};
    if (s.work_corp_id) document.getElementById('workCorpId').value = s.work_corp_id;
    if (s.work_agent_id) document.getElementById('workAgentId').value = s.work_agent_id;
    if (s.work_secret) document.getElementById('workSecret').value = s.work_secret;
    var url = window.location.origin + '/api/work/callback';
    var el = document.getElementById('workCallbackUrl');
    if (el) el.textContent = url;
  }).catch(function(){});
}
function saveWorkConfig() {
  var c = document.getElementById('workCorpId').value.trim();
  var a = document.getElementById('workAgentId').value.trim();
  var s = document.getElementById('workSecret').value.trim();
  if (!c || !s) { toast('请填写 CorpID 和 Secret', 'error'); return; }
  fetch('/api/settings', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({settings:{work_corp_id:c, work_agent_id:a, work_secret:s}})
  }).then(function(){toast('企业微信配置已保存','success')}).catch(function(){toast('保存失败','error')});
}
function testWorkConn() {
  var c = document.getElementById('workCorpId').value.trim();
  var a = document.getElementById('workAgentId').value.trim();
  var s = document.getElementById('workSecret').value.trim();
  if (!c || !s) { toast('请先填写 CorpID 和 Secret', 'error'); return; }
  var btn = document.querySelector('#page-settings .btn-primary');
  var r = document.getElementById('workTestResult');
  btn.disabled = true; r.textContent = '测试中...'; r.style.color = '#999';
  fetch('/api/settings', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({settings:{work_corp_id:c, work_agent_id:a, work_secret:s}})
  }).then(function(){return fetch('/api/work/status')})
   .then(function(r){return r.json()}).then(function(d){
    if (d.connected) { r.textContent = '✅ ' + (d.message||'连接成功'); r.style.color = '#27ae60'; }
    else { r.textContent = '❌ ' + (d.message||'连接失败'); r.style.color = '#e74c3c'; }
  }).catch(function(e){ r.textContent = '❌ ' + e.message; r.style.color = '#e74c3c'; })
   .finally(function(){ btn.disabled = false; });
}

// ================================================================
// 工具函数
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

// ===== 初始化 =====
checkStatus();
loadThinkingSetting();
loadIconTheme();
loadModelSettings();
loadAgentMode();
updateModeUI(agentMode);
// 模式按钮图标跟随主题
(function(){
  var rb = document.getElementById('modeBtnReact');
  var pb = document.getElementById('modeBtnPlan');
  if(rb) rb.innerHTML = _dualIcon('⚡','fa-bolt') + ' 急速';
  if(pb) pb.innerHTML = _dualIcon('📋','fa-clock') + ' 计划';
})();
loadWorkConfig();
setInterval(checkStatus, 15000);

// 自动调整输入框高度
document.getElementById('chatInput').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 150) + 'px';
});
document.getElementById('splitInput').addEventListener('input', function() {
  this.style.height = 'auto';
  this.style.height = Math.min(this.scrollHeight, 100) + 'px';
});


// === 历史面板功能（独立脚本，不影响原有代码）===
function openHistory() {
  var o = document.getElementById('historyOverlay');
  if (!o) return;
  o.classList.add('open');
  loadHistory();
}
function closeHistory() {
  var o = document.getElementById('historyOverlay');
  if (o) o.classList.remove('open');
}
function loadHistory() {
  var list = document.getElementById('historyList');
  if (!list) return;
  list.innerHTML = '<div style="text-align:center;padding:20px;color:#999">加载中...</div>';
  fetch('/api/conversations').then(function(r){return r.json()}).then(function(d){
    var arr = d.conversations||[];
    if (!arr.length) { list.innerHTML = '<div style="text-align:center;padding:30px;color:#999">暂无对话</div>'; return; }
    list.innerHTML = arr.map(function(c){
      return '<div class="ht-item" onclick="loadConv(&quot;'+c.id+'&quot;)">' +
        '<div class="ht-name">' + escHtml(c.title||'新对话') + '</div>' +
        '<div class="ht-time">' + (c.message_count||0) + '条 · ' + (c.updated_at||'') + '</div></div>';
    }).join('');
  }).catch(function(){list.innerHTML='<div style="padding:20px;color:#999">加载失败</div>';});
}
function loadConv(convId) {
  closeHistory();
  fetch('/api/conversations/'+convId).then(function(r){return r.json()}).then(function(d){
    var el = document.getElementById('chatMessages');
    if (!el) return;
    currentConvId = convId;
    conversationId = convId;
    el.innerHTML = '';
    if (d.messages && d.messages.length) {
      d.messages.forEach(function(m){ addMessage(m.role, escHtml(m.content)); });
    }
    el.scrollTop = el.scrollHeight;
  });
}

// === 右键菜单 ===
function showCtx(e, convId) {
  e.preventDefault();
  var m = document.getElementById('ctxMenu');
  m.innerHTML =
    '<div class="ctx-item" onclick="closeCtx();loadConv(\'' + convId + '\')">' + _dualIcon('📂', 'fa-folder-open') + ' 在主屏打开</div>' +
    '<div class="ctx-item" onclick="closeCtx();addSplit2(\'' + convId + '\')">' + _dualIcon('➕', 'fa-plus') + ' 添加到分屏</div>' +
    '<div class="ctx-divider"></div>' +
    '<div class="ctx-item danger" onclick="closeCtx();delConv(\'' + convId + '\')">' + _dualIcon('🗑️', 'fa-trash-can') + ' 删除此对话</div>';
  m.style.left = Math.min(e.clientX, window.innerWidth-180)+'px';
  m.style.top = e.clientY+'px';
  m.classList.add('open');
  setTimeout(function(){ document.addEventListener('click', closeCtx, {once:true}); }, 10);
}
function closeCtx() { var m=document.getElementById('ctxMenu'); if(m)m.classList.remove('open'); }
function delConv(id) {
  showDangerConfirm('删除对话', '确定要删除此对话吗？', function() {
    fetch('/api/conversations/'+id,{method:'DELETE'}).then(function(){closeHistory();loadHistory();});
  });
}
function addSplit2(convId) {
  splitConvId = convId;
  var panel = document.getElementById('rightCol');
  var msgs = document.getElementById('splitMessages');
  if (!panel || !msgs) return;
  msgs.innerHTML = '';
  fetch('/api/conversations/' + convId).then(function(r){ return r.json(); }).then(function(d){
    if (d.messages && d.messages.length) {
      d.messages.forEach(function(m){
        var div = document.createElement('div');
        div.className = 'message ' + m.role;
        var avatarHtml2 = m.role === 'user' ? _dualIcon('👤', 'fa-user') : _dualIcon('🤖', 'fa-robot');
        div.innerHTML = '<div class="avatar">' + avatarHtml2 + '</div><div class="bubble">' + escHtml(m.content) + '</div>' +
          '<button class="copy-btn" onclick="copyMessage(this)" title="复制内容">' + _dualIcon('📋', 'fa-copy') + '</button>';
        msgs.appendChild(div);
      });
    }
    panel.classList.add('open');
    document.getElementById('splitInput').focus();
  }).catch(function(){});
}
function closeSplit() {
  var panel = document.getElementById('rightCol');
  if (panel) panel.classList.remove('open');
  splitConvId = '';
  isSplitStreaming = false;
  window._splitThinking = null;
  window._splitThinkingBody = null;
  window._splitThinkingHtml = '';
}
function stopStreaming() {
  if (currentReader) {
    try { currentReader.cancel(); } catch(e) {}
    currentReader = null;
  }
  fetch("/chat/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  }).catch(function(){});
  document.getElementById("stopBtn").style.display = "none";
}
var splitReader = null;
function stopSplitStreaming() {
  if (splitReader) {
    try { splitReader.cancel(); } catch(e) {}
    splitReader = null;
  }
  fetch("/chat/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId })
  }).catch(function(){});
  document.getElementById("splitStopBtn").style.display = "none";
  isSplitStreaming = false;
}

function onSplitKeydown(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendSplitChat();
  }
}
function sendSplitChat() {
  // 重置分屏思考面板（每次新消息独立）
  window._splitThinking = null;
  window._splitThinkingBody = null;
  window._splitThinkingHtml = '';

  var input = document.getElementById('splitInput');
  var btn = document.querySelector('#rightCol .send-btn');
  var msg = input.value.trim();
  if (!msg || isSplitStreaming) return;

  isSplitStreaming = true;
  btn.disabled = true;

  var msgs = document.getElementById('splitMessages');
  // 清空空状态
  var empty = msgs.querySelector('.empty-state');
  if (empty) empty.remove();

  // 显示用户消息
  var userDiv = document.createElement('div');
  userDiv.className = 'message user';
  userDiv.innerHTML = '<div class="avatar">' + _dualIcon('👤', 'fa-user') + '</div><div class="bubble">' + escHtml(msg) + '</div>' +
    '<button class="copy-btn" onclick="copyMessage(this)" title="复制内容">' + _dualIcon('📋', 'fa-copy') + '</button>';
  msgs.appendChild(userDiv);
  msgs.scrollTop = msgs.scrollHeight;
  input.value = '';
  input.style.height = 'auto';

  // 发送流式请求
  var convId = splitConvId || '';
  fetch('/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      query: msg,
      session_id: sessionId,
      conversation_id: convId
    })
  }).then(function(res) {
    sessionId = res.headers.get('X-Session-Id') || sessionId;
    var newConvId = res.headers.get('X-Conversation-Id') || '';
    if (newConvId) { splitConvId = newConvId; }

    splitReader = res.body.getReader();
    var reader = splitReader;
    var dec = new TextDecoder();
    var buf = '';
    var aiBubble = null;
    var fullReply = '';

    function readChunk() {
      reader.read().then(function(result) {
        if (result.done) {
          isSplitStreaming = false;
          btn.disabled = false;
          document.querySelectorAll('#splitMessages .phase-badge').forEach(function(e){ e.remove(); });
          document.getElementById('splitStopBtn').style.display = 'none';
          input.focus();
          return;
        }
        buf += dec.decode(result.value, { stream: true });
        var lines = buf.split('\n');
        buf = lines.pop() || '';

        for (var i = 0; i < lines.length; i++) {
          var line = lines[i];
          if (!line.startsWith('data: ')) continue;
          try {
            var evt = JSON.parse(line.slice(6));
            debugEvents.push(Object.assign({_time: Date.now()}, evt));
            switch (evt.phase) {
              case 'knowledge':
                break;
              case 'think_token':
                if (isShowThinking()) {
                  if (!window._splitThinking) {
                    var tp = document.createElement('div');
                    tp.className = 'thinking-panel';
                    tp.innerHTML = '<div class="tp-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');var t=this.querySelector(\'.tp-toggle\');t.textContent=t.textContent==\'▼\'?\'▶\':\'▼\'">' +
                      '<span>' + _dualIcon('🧠', 'fa-brain') + ' 思考过程</span><span class="tp-toggle">▼</span></div><div class="tp-body"></div>';
                    msgs.appendChild(tp);
                    window._splitThinking = tp;
                    window._splitThinkingBody = tp.querySelector('.tp-body');
                    window._splitThinkingHtml = '';
                    msgs.scrollTop = msgs.scrollHeight;
                  }
                  window._splitThinkingHtml += evt.token || '';
                  window._splitThinkingBody.innerHTML = _replaceEmoji(window._splitThinkingHtml);
                  msgs.scrollTop = msgs.scrollHeight;
                }
                break;
              case 'self_check':
                document.querySelectorAll('#splitMessages .phase-badge').forEach(function(e){ e.remove(); });
                var p = document.createElement('div');
                p.className = 'phase-badge phase-thinking';
                p.innerHTML = _dualIcon('🔄', 'fa-rotate') + ' 科吉二次确认中...';
                msgs.appendChild(p);
                document.getElementById('splitStopBtn').style.display = '';
                break;
              case 'thinking':
                document.querySelectorAll('#splitMessages .phase-badge').forEach(function(e){ e.remove(); });
                var p = document.createElement('div');
                p.className = 'phase-badge phase-thinking';
                p.innerHTML = _dualIcon('🤔', 'fa-brain') + ' 思考中... (' + (evt.round||'') + ')';
                msgs.appendChild(p);
                document.getElementById('splitStopBtn').style.display = '';
                break;
              case 'tool_call':
                document.querySelectorAll('#splitMessages .phase-badge').forEach(function(e){ e.remove(); });
                var p = document.createElement('div');
                p.className = 'phase-badge phase-tool';
                p.innerHTML = _dualIcon('🔧', 'fa-wrench') + ' 调用工具: ' + (evt.tools||[]).join(', ');
                msgs.appendChild(p);
                document.getElementById('splitStopBtn').style.display = '';
                if (window._splitThinkingBody && isShowThinking()) {
                  window._splitThinkingHtml += '\n──────────────\n🔧 调用工具: ' + (evt.tools||[]).join(', ') + '\n';
                  window._splitThinkingBody.innerHTML = _replaceEmoji(window._splitThinkingHtml);
                  msgs.scrollTop = msgs.scrollHeight;
                }
                break;
              case 'tool_result':
                document.querySelectorAll('#splitMessages .phase-badge').forEach(function(e){ e.remove(); });
                var p = document.createElement('div');
                p.className = 'phase-badge phase-result';
                p.innerHTML = _dualIcon('✅', 'fa-circle-check') + ' ' + (evt.tool||'') + ' 完成';
                msgs.appendChild(p);
                if (window._splitThinkingBody && isShowThinking()) {
                  var snippet = (evt.result||'').substring(0, 150);
                  window._splitThinkingHtml += '✅ ' + (evt.tool||'') + ' → ' + snippet + '\n';
                  window._splitThinkingBody.innerHTML = _replaceEmoji(window._splitThinkingHtml);
                  msgs.scrollTop = msgs.scrollHeight;
                }
                break;
              case 'answering':
                document.querySelectorAll('#splitMessages .phase-badge').forEach(function(e){ e.remove(); });
                var aiDiv = document.createElement('div');
                aiDiv.className = 'message assistant';
                aiDiv.innerHTML = '<div class="avatar">' + _dualIcon('🤖', 'fa-robot') + '</div><div class="bubble"></div>' +
    '<button class="copy-btn" onclick="copyMessage(this)" title="复制内容">' + _dualIcon('📋', 'fa-copy') + '</button>';
                msgs.appendChild(aiDiv);
                aiBubble = aiDiv.querySelector('.bubble');
                document.getElementById('splitStopBtn').style.display = 'none';
                break;
              case 'answer':
                if (!aiBubble) {
                  document.querySelectorAll('#splitMessages .phase-badge').forEach(function(e){ e.remove(); });
                  var aiDiv = document.createElement('div');
                  aiDiv.className = 'message assistant';
                  aiDiv.innerHTML = '<div class="avatar">' + _dualIcon('🤖', 'fa-robot') + '</div><div class="bubble"></div>' +
    '<button class="copy-btn" onclick="copyMessage(this)" title="复制内容">' + _dualIcon('📋', 'fa-copy') + '</button>';
                  msgs.appendChild(aiDiv);
                  aiBubble = aiDiv.querySelector('.bubble');
                }
                fullReply += evt.token || '';
                aiBubble.innerHTML = renderMarkdown(escHtml(fullReply));
                break;
              case 'error':
                console.error('Split error:', evt.message);
                break;
            }
            msgs.scrollTop = msgs.scrollHeight;
          } catch(e) {}
        }
        readChunk();
      }).catch(function() {
        isSplitStreaming = false;
        btn.disabled = false;
        document.getElementById('splitStopBtn').style.display = 'none';
      });
    }
    readChunk();
  }).catch(function() {
    isSplitStreaming = false;
    btn.disabled = false;
    document.getElementById('splitStopBtn').style.display = 'none';
  });
}

// === 历史记录多选 & 批量删除 ===
var isMultiSelect = false;

function toggleMultiSelect() {
  isMultiSelect = !isMultiSelect;
  document.getElementById('htToolbar').style.display = isMultiSelect ? 'flex' : 'none';
  document.getElementById('htMultiBtn').innerHTML = (isMultiSelect ? _dualIcon('☑', 'fa-square-check') + ' 取消' : _dualIcon('☑', 'fa-square-check') + ' 多选');
  loadHistory();
}

function selectAllHistory() {
  var cbs = document.querySelectorAll('.ht-checkbox');
  var allChecked = true;
  for (var i = 0; i < cbs.length; i++) { if (!cbs[i].checked) { allChecked = false; break; } }
  for (var i = 0; i < cbs.length; i++) { cbs[i].checked = !allChecked; }
}

function getSelectedIds() {
  var ids = [];
  var cbs = document.querySelectorAll('.ht-checkbox:checked');
  for (var i = 0; i < cbs.length; i++) { ids.push(cbs[i].value); }
  return ids;
}

function deleteSelected() {
  var ids = getSelectedIds();
  if (ids.length === 0) { showAlert('提示', '请先勾选要删除的对话'); return; }
  showDangerConfirm('批量删除对话', '确定删除选中的 ' + ids.length + ' 个对话吗？', function() {
    Promise.all(ids.map(function(id) {
      return fetch('/api/conversations/' + id, { method: 'DELETE' });
    })).then(function() {
      loadHistory();
      if (currentConvId && ids.indexOf(currentConvId) >= 0) newChat();
    }).catch(function(){ showAlert('错误', '删除失败'); });
  });
}

function deleteAllHistory() {
  showDangerConfirm('删除全部对话', '确定删除全部对话吗？此操作不可恢复！', function() {
    fetch('/api/conversations').then(function(r){return r.json()}).then(function(d){
      var arr = d.conversations||[];
      if (!arr.length) { showAlert('提示', '没有可删除的对话'); return; }
      showDangerConfirm('再次确认', '共 ' + arr.length + ' 个对话，确定全部删除？', function() {
        Promise.all(arr.map(function(c) {
          return fetch('/api/conversations/' + c.id, { method: 'DELETE' });
        })).then(function() {
          loadHistory();
          newChat();
        }).catch(function(){ showAlert('错误', '删除失败'); });
      });
    });
  });
}

// === 更新历史列表（带右键 + 多选）===
loadHistory = function() {
  var list = document.getElementById('historyList');
  if (!list) return;
  list.innerHTML = '<div style="text-align:center;padding:20px;color:#999">加载中...</div>';
  fetch('/api/conversations').then(function(r){return r.json()}).then(function(d){
    var arr = d.conversations||[];
    if (!arr.length) { list.innerHTML = '<div style="text-align:center;padding:30px;color:#999">暂无对话</div>'; return; }
    list.innerHTML = arr.map(function(c){
      var cb = '';
      var clickAttr = '';
      if (isMultiSelect) {
        cb = '<input type="checkbox" class="ht-checkbox" value="' + c.id + '">';
        clickAttr = ' onclick="event.stopPropagation();var cb=this.querySelector(\'.ht-checkbox\');if(cb){cb.checked=!cb.checked;}"';
      } else {
        clickAttr = ' onclick="loadConv(\'' + c.id + '\')"';
      }
      return '<div class="ht-item"' + clickAttr + ' oncontextmenu="showCtx(event,\'' + c.id + '\')">' +
        cb + '<div class="ht-info"><div class="ht-name">' + escHtml(c.title||'新对话') + '</div>' +
        '<div class="ht-time">' + (c.message_count||0) + '条 · ' + (c.updated_at||'') + '</div></div></div>';
    }).join('');
  }).catch(function(){list.innerHTML='<div style="padding:20px;color:#999">加载失败</div>';});
};


var _debugLogTimer = null;

function toggleDebug() {
  var d = document.getElementById('debugDrawer');
  var btn = document.getElementById('debugBtn');
  if (d.classList.contains('open')) {
    d.classList.remove('open');
    if (btn) btn.style.background = '';
    if (btn) btn.style.color = '';
    if (_debugLogTimer) { clearInterval(_debugLogTimer); _debugLogTimer = null; }
  } else {
    d.classList.add('open');
    if (btn) btn.style.background = 'var(--primary)';
    if (btn) btn.style.color = '#fff';
    refreshDebugPanel();
    _debugLogTimer = setInterval(function() {
      if (debugActiveTab === 'logs') refreshDebugLogs();
      updateDebugBar();
    }, 3000);
  }
}

function clearDebugEvents() {
  debugEvents = [];
  document.getElementById('ddBody').innerHTML = '<div class="dd-empty">已清空，等待新事件...</div>';
  updateDebugBar();
}

function switchDebugTab(tab) {
  debugActiveTab = tab;
  document.querySelectorAll('.dd-tab').forEach(function(t){ t.classList.remove('active'); });
  var el = document.querySelector('.dd-tab[data-dtab="'+tab+'"]');
  if (el) el.classList.add('active');
  refreshDebugPanel();
}

function refreshDebugPanel() {
  if (debugActiveTab === 'events') renderEventTimeline();
  else if (debugActiveTab === 'tools') renderToolDetails();
  else if (debugActiveTab === 'logs') refreshDebugLogs();
  else if (debugActiveTab === 'raw') renderRawJSON();
}

function updateDebugBar() {
  var toolCount = 0;
  for (var i = 0; i < debugEvents.length; i++) {
    if (debugEvents[i].phase === 'tool_call') toolCount++;
  }
  var lastTime = debugEvents.length ? new Date(debugEvents[debugEvents.length-1]._time).toLocaleTimeString() : '--';
  document.getElementById('ddBar').textContent =
    '事件: ' + debugEvents.length + ' | 工具调用: ' + toolCount + ' | 最后: ' + lastTime;
}

var _phaseLabel = {
  knowledge:       [_dualIcon('📖','fa-book-open')+' 知识库', 'dd-knowledge'],
  thinking:        [_dualIcon('🤔','fa-brain')+' 思考中', 'dd-thinking'],
  self_check:      [_dualIcon('🔄','fa-rotate')+' 二次确认', 'dd-thinking'],
  think_token:     [_dualIcon('💭','fa-comment-dots')+' token', 'dd-thinking'],
  think_done:      [_dualIcon('✅','fa-circle-check')+' 思考完成', 'dd-thinking'],
  tool_call:       [_dualIcon('🔧','fa-wrench')+' 调用工具', 'dd-toolcall'],
  tool_continue:   [_dualIcon('⏳','fa-hourglass-half')+' 自动续传', 'dd-toolcall'],
  tool_result:     [_dualIcon('📤','fa-cloud-arrow-down')+' 工具返回', 'dd-toolresult'],
  plan_exec_start: [_dualIcon('⚡','fa-bolt')+' 计划执行', 'dd-thinking'],
  plan_fallback:   [_dualIcon('🔄','fa-rotate')+' 兜底执行', 'dd-thinking'],
  plan_step:       [_dualIcon('📋','fa-clock')+' 计划步骤', 'dd-toolcall'],
  plan_correction: [_dualIcon('🔧','fa-wrench')+' 步骤修正', 'dd-toolcall'],
  plan_eval:       [_dualIcon('🔍','fa-magnifying-glass')+' 步骤验证', 'dd-thinking'],
  plan_eval_done:  [_dualIcon('✅','fa-circle-check')+' 验证完成', 'dd-thinking'],
  plan_answering:  [_dualIcon('🤔','fa-brain')+' 综合分析', 'dd-answer'],
  answering:       [_dualIcon('🗣','fa-comment')+' 开始回答', 'dd-answer'],
  answer:          [_dualIcon('💬','fa-comments')+' 回答', 'dd-answer'],
  error:           [_dualIcon('❌','fa-circle-xmark')+' 错误', 'dd-error'],
  done:            [_dualIcon('🏁','fa-flag')+' 完成', 'dd-answer']
};

function renderEventTimeline() {
  var body = document.getElementById('ddBody');
  if (!debugEvents.length) { body.innerHTML = '<div class="dd-empty">等待对话事件...</div>'; updateDebugBar(); return; }

  // 将连续同类型事件合并为一条（带计数）
  var groups = [];
  var start = Math.max(0, debugEvents.length - 150);
  for (var i = start; i < debugEvents.length; i++) {
    var e = debugEvents[i];
    var last = groups[groups.length - 1];
    if (last && last.phase === e.phase && e.phase !== 'tool_result' && e.phase !== 'error') {
      last.count++;
      last._time = e._time; // 更新时间戳为最新
    } else {
      groups.push({ phase: e.phase, _time: e._time, tools: e.tools, tool: e.tool, result: e.result, message: e.message, count: 1 });
    }
  }

  var html = '';
  for (var g = 0; g < groups.length; g++) {
    var e = groups[g];
    var lb = _phaseLabel[e.phase] || [_dualIcon('📎','fa-link')+' '+e.phase, ''];
    var d = new Date(e._time);
    var time = d.toLocaleTimeString() + '.' + String(d.getMilliseconds()).padStart(3,'0');
    var countLabel = e.count > 1 ? ' <span style="color:#e8b84b;font-weight:600">×' + e.count + '</span>' : '';

    html += '<div class="dd-entry '+lb[1]+'">';
    html += '<span class="dd-time">'+time+'</span> ';
    html += '<span class="dd-phase">'+lb[0]+'</span>' + countLabel;

    if (e.phase === 'tool_call' && e.tools) {
      html += ' <span style="color:#6bcf7f">'+escHtml(e.tools.join(', '))+'</span>';
    }
    if (e.phase === 'tool_result') {
      html += ' <span style="color:#6bcf7f">'+escHtml(e.tool||'')+'</span>';
      var snippet = (e.result||'').substring(0, 100);
      html += '<div class="dd-detail dd-result">'+escHtml(snippet)+(e.result&&e.result.length>100?' ...':'')+'</div>';
    }
    if (e.phase === 'error') {
      html += '<div class="dd-detail" style="color:#e74c3c">'+escHtml(e.message||'')+'</div>';
    }
    html += '</div>';
  }
  body.innerHTML = html || '<div class="dd-empty">无事件</div>';
  // 只有用户靠近底部才自动滚动
  if (body.scrollTop + body.clientHeight >= body.scrollHeight - 60) {
    body.scrollTop = body.scrollHeight;
  }
  updateDebugBar();
}

function renderToolDetails() {
  var body = document.getElementById('ddBody');
  var pairs = [];
  var pending = null;
  for (var i = 0; i < debugEvents.length; i++) {
    if (debugEvents[i].phase === 'tool_call') {
      pending = { time: debugEvents[i]._time, tools: debugEvents[i].tools || [], result: null };
    }
    if (debugEvents[i].phase === 'tool_result' && pending) {
      pending.result = debugEvents[i];
      pairs.push(pending);
      pending = null;
    }
  }

  if (!pairs.length) { body.innerHTML = '<div class="dd-empty">暂无工具调用记录</div>'; return; }

  var html = '';
  for (var j = 0; j < pairs.length; j++) {
    var p = pairs[j];
    var time = new Date(p.time).toLocaleTimeString();
    html += '<div class="dd-entry dd-toolcall">';
    html += '<span class="dd-time">'+time+'</span> ';
    html += '<span class="dd-phase">🔧 '+escHtml(p.tools.join(', '))+'</span>';
    if (p.result) {
      html += '<div class="dd-detail dd-result" style="max-height:none">';
      html += escHtml((p.result.result||'').substring(0, 800));
      html += '</div>';
    } else {
      html += '<div class="dd-detail" style="color:#e8b84b">等待结果...</div>';
    }
    html += '</div>';
  }
  body.innerHTML = html;
  body.scrollTop = body.scrollHeight;
  updateDebugBar();
}

function renderRawJSON() {
  var body = document.getElementById('ddBody');
  if (!debugEvents.length) { body.innerHTML = '<div class="dd-empty">无数据</div>'; return; }

  var recent = debugEvents.slice(-30);
  var html = '<pre style="font-size:10px;line-height:1.4;white-space:pre-wrap;word-break:break-all">';
  for (var i = 0; i < recent.length; i++) {
    var obj = {};
    for (var k in recent[i]) { if (k !== '_time') obj[k] = recent[i][k]; }
    try {
      html += escHtml(JSON.stringify(obj, null, 2)) + '\n';
    } catch(e) {
      html += escHtml(String(obj)) + '\n';
    }
  }
  html += '</pre>';
  body.innerHTML = html;
  body.scrollTop = body.scrollHeight;
}

function refreshDebugLogs() {
  var body = document.getElementById('ddBody');
  body.innerHTML = '<div style="text-align:center;padding:20px;color:#5a6080"><div class="spinner"></div>加载日志...</div>';

  fetch('/api/debug/logs?limit=100').then(function(r){return r.json()}).then(function(d){
    var logs = d.logs||[];
    if (!logs.length) { body.innerHTML = '<div class="dd-empty">暂无日志</div>'; return; }
    var html = '';
    var start = Math.max(0, logs.length - 80);
    for (var i = start; i < logs.length; i++) {
      var l = logs[i];
      html += '<div class="dd-log-entry">';
      html += '<span class="dd-log-lvl dd-log-'+l.level+'">['+l.level+']</span>';
      html += '<span style="color:#6a7090">'+escHtml(l.logger)+'</span> ';
      html += '<span>'+escHtml(l.message)+'</span>';
      html += '</div>';
    }
    body.innerHTML = html || '<div class="dd-empty">无日志</div>';
    body.scrollTop = body.scrollHeight;
  }).catch(function(e){
    body.innerHTML = '<div class="dd-empty">日志加载失败: '+e.message+'</div>';
  });
}

// 每2秒自动刷新（仅在面板打开时）
setInterval(function() {
  if (!document.getElementById('debugDrawer').classList.contains('open')) return;
  if (debugActiveTab === 'events') renderEventTimeline();
  else if (debugActiveTab === 'tools') renderToolDetails();
  updateDebugBar();
}, 2000);


// ===== 数据库管理 & 智能问数 =====
var _sqAbort = null;

function switchDbTab(tab) {
  document.querySelectorAll('.db-tab').forEach(function(t){t.style.borderBottom='2px solid transparent';t.style.color='var(--text-secondary)';t.style.fontWeight='400';t.classList.remove('active');});
  document.querySelectorAll('.db-panel').forEach(function(p){p.style.display='none';});
  var btn = document.querySelector('.db-tab[data-dbtab="'+tab+'"]');
  if (btn) { btn.style.borderBottom='2px solid var(--primary)'; btn.style.color='var(--primary)'; btn.style.fontWeight='600'; btn.classList.add('active'); }
  var panel = document.getElementById('dbpanel-'+tab);
  if (panel) panel.style.display='block';
  if (tab === 'sources') loadDbConfigs();
  if (tab === 'query') loadDbConfigSelect();
}

function loadDbConfigs() {
  var list = document.getElementById('dbConfigList');
  if (!list) return;
  list.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:40px"><div class="spinner"></div></div>';
  fetch('/api/database/configs').then(function(r){return r.json()}).then(function(data){
    var configs = data.configs || [];
    if (!configs.length) { list.innerHTML = '<div style="grid-column:1/-1;padding:60px 0;text-align:center;color:var(--text-secondary);font-size:14px">暂无数据源，点击上方「新增」按钮添加</div>'; return; }
    var html = '';
    configs.forEach(function(c){
      html += '<div class="db-config-card">';
      html += '<div class="dcc-header"><div><span class="dcc-name">'+escHtml(c.name)+'</span> <span class="dcc-type">'+(c.db_type==='mysql'?'MySQL':'PostgreSQL')+'</span></div>';
      html += '<button class="btn btn-sm btn-outline" onclick="deleteDbConfig('+c.id+')" style="color:var(--danger)">'+_dualIcon('🗑️','fa-trash-can')+'</button></div>';
      html += '<div class="dcc-info">'+escHtml(c.host)+':'+c.port+' / '+escHtml(c.database_name)+'  —  '+escHtml(c.username)+'</div>';
      html += '<div class="dcc-actions">';
      html += '<button class="btn btn-sm btn-outline" onclick="testDbConfig('+c.id+')">'+_dualIcon('🔌','fa-plug')+' 测试连接</button>';
      html += '<button class="btn btn-sm btn-outline" onclick="scanDbConfig('+c.id+')">'+_dualIcon('📡','fa-satellite-dish')+' 扫描表结构</button>';
      html += '<button class="btn btn-sm btn-outline" onclick="showTableMeta('+c.id+')">'+_dualIcon('📋','fa-clipboard-list')+' 表管理</button>';
      html += '</div><div id="dbMsg_'+c.id+'" style="font-size:12px;margin-top:6px"></div></div>';
    });
    list.innerHTML = html;
  }).catch(function(e){ list.innerHTML = '<div style="color:var(--danger);padding:20px">加载失败: '+e.message+'</div>'; });
}

function showDbConfigForm(editId) {
  var body = '<div style="margin-bottom:12px"><label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">名称</label><input id="fld_name" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:14px;box-sizing:border-box"></div>';
  body += '<div style="margin-bottom:12px"><label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">类型</label><select id="fld_db_type" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:14px"><option value="mysql">MySQL</option><option value="postgresql">PostgreSQL</option></select></div>';
  body += '<div style="margin-bottom:12px"><label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">主机地址</label><input id="fld_host" value="localhost" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:14px;box-sizing:border-box"></div>';
  body += '<div style="margin-bottom:12px"><label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">端口</label><input id="fld_port" value="3306" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:14px;box-sizing:border-box"></div>';
  body += '<div style="margin-bottom:12px"><label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">数据库名</label><input id="fld_database_name" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:14px;box-sizing:border-box"></div>';
  body += '<div style="margin-bottom:12px"><label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">用户名</label><input id="fld_username" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:14px;box-sizing:border-box"></div>';
  body += '<div style="margin-bottom:12px"><label style="font-size:13px;font-weight:500;display:block;margin-bottom:4px">密码</label><input id="fld_password" type="password" style="width:100%;padding:10px;border:1px solid var(--border);border-radius:6px;font-size:14px;box-sizing:border-box"></div>';
  showDialog(editId?'编辑数据源':'新增数据源', body+'<div style="display:flex;gap:8px;margin-top:4px"><button class="btn btn-primary" onclick="saveDbConfigFromForm('+(editId||'null')+')">💾 保存</button><button class="btn btn-outline" onclick="closeDialog()">取消</button></div>');
  if (editId) {
    fetch('/api/database/configs/'+editId).then(function(r){return r.json()}).then(function(d){
      var cfg = d.config||{};
      ['name','host','database_name','username'].forEach(function(k){var el=document.getElementById('fld_'+k);if(el&&cfg[k])el.value=cfg[k];});
      var p=document.getElementById('fld_port');if(p&&cfg.port)p.value=cfg.port;
      var t=document.getElementById('fld_db_type');if(t&&cfg.db_type)t.value=cfg.db_type;
    }).catch(function(){});
  }
}

function saveDbConfigFromForm(editId) {
  var data={};['name','db_type','host','port','database_name','username','password'].forEach(function(k){var el=document.getElementById('fld_'+k);if(el)data[k]=el.value;});
  if(!data.name||!data.host||!data.database_name){alert('请填写必填字段');return;}
  var url=editId?'/api/database/configs/'+editId:'/api/database/configs';
  var method=editId?'PUT':'POST';
  fetch(url,{method:method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
  .then(function(r){return r.json()}).then(function(d){if(d.status==='ok'){closeDialog();loadDbConfigs();}else{alert('保存失败: '+(d.detail||'未知错误'));}})
  .catch(function(e){alert('请求失败: '+e.message);});
}

function deleteDbConfig(id){if(!confirm('确定删除此数据源？关联的表元数据也会被删除。'))return;fetch('/api/database/configs/'+id,{method:'DELETE'}).then(function(){loadDbConfigs();}).catch(function(e){alert('删除失败: '+e.message);});}
function testDbConfig(id){var el=document.getElementById('dbMsg_'+id);if(el)el.innerHTML='<span style="color:#888">⏳ 测试中...</span>';fetch('/api/database/configs/'+id+'/test',{method:'POST'}).then(function(r){return r.json()}).then(function(d){if(el)el.innerHTML='<span style="color:'+(d.status==='ok'?'green':'red')+'">'+escHtml(d.message)+'</span>';}).catch(function(e){if(el)el.innerHTML='<span style="color:red">请求失败: '+escHtml(e.message)+'</span>';});}
function scanDbConfig(id){var el=document.getElementById('dbMsg_'+id);if(el)el.innerHTML='<span style="color:#888">⏳ 扫描表结构中...</span>';fetch('/api/database/configs/'+id+'/scan',{method:'POST'}).then(function(r){return r.json()}).then(function(d){if(el)el.innerHTML='<span style="color:green">✅ '+escHtml(d.message)+'</span>';}).catch(function(e){if(el)el.innerHTML='<span style="color:red">❌ 扫描失败: '+escHtml(e.message)+'</span>';});}

function showTableMeta(configId) {
  fetch('/api/database/configs/'+configId+'/metadata').then(function(r){return r.json()}).then(function(d){
    var metas=d.metadata||[];if(!metas.length){alert('暂无表元数据，请先扫描');return;}
    var html='<div style="max-height:400px;overflow-y:auto"><div style="font-size:13px;font-weight:500;margin-bottom:8px;color:var(--text-secondary)">共 '+metas.length+' 个表，勾选「启用问答」即可用于智能问数</div>';
    metas.forEach(function(m){
      var cols=m.columns||[];var cn=cols.map(function(c){return c.column_name}).join(', ');
      html+='<div class="db-table-item"><div><div class="dbt-name">'+escHtml(m.table_name)+'</div><div class="dbt-info">'+(m.table_comment?escHtml(m.table_comment)+' · ':'')+cols.length+' 字段 · '+(m.row_count||'?')+' 行</div><div style="font-size:11px;color:#aaa;margin-top:2px">'+escHtml(cn.slice(0,80))+'</div></div><div class="dbt-actions"><label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" '+(m.qa_enabled?'checked':'')+' onchange="toggleTableQa('+m.id+',this.checked)"> 问答</label></div></div>';
    });
    html+='</div>';showDialog('表管理 — 配置问答',html+'<div style="margin-top:12px"><button class="btn btn-outline" onclick="closeDialog()">关闭</button></div>');
  }).catch(function(e){alert('加载失败: '+e.message);});
}

function toggleTableQa(metaId,enabled){fetch('/api/database/metadata/'+metaId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({qa_enabled:enabled?1:0})}).then(function(r){return r.json()}).catch(function(){});}

function loadDbConfigSelect(){var sel=document.getElementById('sqConfigSelect');if(!sel)return;fetch('/api/database/configs').then(function(r){return r.json()}).then(function(d){var configs=d.configs||[];sel.innerHTML='<option value="">-- 选择数据源 --</option>';configs.forEach(function(c){sel.innerHTML+='<option value="'+c.id+'">'+escHtml(c.name)+' ('+c.db_type+'/'+escHtml(c.database_name)+')</option>';});}).catch(function(){});}

function executeSmartQuery() {
  var configId = document.getElementById('sqConfigSelect').value;
  var input = document.getElementById('sqInput');
  var query = input.value.trim();
  if (!configId) { toast('请先选择数据源', 'error'); return; }
  if (!query) { toast('请输入查询内容', 'error'); return; }

  var msgs = document.getElementById('sqMessages');
  var empty = msgs.querySelector('.db-side-empty');
  if (empty) empty.remove();

  // 用户消息
  msgs.innerHTML += '<div class="sq-msg user">' + escHtml(query) + '</div>';
  input.value = '';
  document.getElementById('sqInput').disabled = true;

  // 创建一个助手气泡，步骤+结果都在里面
  var bubble = document.createElement('div');
  bubble.className = 'sq-msg assistant';
  bubble.innerHTML = '<div class="sq-steps"></div>';
  msgs.appendChild(bubble);
  msgs.scrollTop = msgs.scrollHeight;

  var stepsEl = bubble.querySelector('.sq-steps');
  var resultAppended = false;

  function addStep(msg, status) {
    if (!stepsEl) return;
    var icons = {running:'⏳', completed:'✅', failed:'❌'};
    var icon = icons[status] || '•';
    var color = status === 'failed' ? '#c62828' : (status === 'completed' ? '#2e7d32' : '#f57f17');
    stepsEl.innerHTML += '<div style="font-size:12px;color:'+color+';margin:2px 0">'+icon+' '+escHtml(msg)+'</div>';
    msgs.scrollTop = msgs.scrollHeight;
  }

  // 用 ReadableStream 读取 SSE 流式响应（与主对话一致）
  fetch('/api/smart-query/stream', {method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({query:query, config_id:parseInt(configId)})
  }).then(function(resp){
    if (!resp.ok) { throw new Error('请求失败 (' + resp.status + ')'); }
    var reader = resp.body.getReader();
    var decoder = new TextDecoder();
    var buf = '';

    function read() {
      reader.read().then(function(r){
        if (r.done) {
          document.getElementById('sqInput').disabled = false;
          document.getElementById('sqInput').focus();
          msgs.scrollTop = msgs.scrollHeight;
          return;
        }
        buf += decoder.decode(r.value, {stream:true});
        var lines = buf.split('\n');
        buf = lines.pop() || '';
        for (var i = 0; i < lines.length; i++) {
          var line = lines[i].trim();
          // 跳过非 data: 行（兼容 SSE 格式）
          if (!line || !line.startsWith('data: ')) continue;
          try {
            var ev = JSON.parse(line.slice(6));
            if (ev.type === 'step') {
              addStep(ev.message, ev.status);
            } else if (ev.type === 'result' && !resultAppended) {
              resultAppended = true;
              var resultHtml = buildSqResultHtml(ev.data || {});
              bubble.innerHTML += resultHtml;
              msgs.scrollTop = msgs.scrollHeight;
            } else if (ev.type === 'error') {
              addStep(ev.message || '查询失败', 'failed');
              document.getElementById('sqInput').disabled = false;
            }
          } catch(e) {
            // JSON 解析未完成，等待下一块
          }
        }
        msgs.scrollTop = msgs.scrollHeight;
        read();
      }).catch(function(e){
        addStep('读取流失败: ' + e.message, 'failed');
        document.getElementById('sqInput').disabled = false;
      });
    }
    read();
  }).catch(function(e){
    addStep('请求失败: ' + e.message, 'failed');
    document.getElementById('sqInput').disabled = false;
    console.error('SmartQuery error:', e);
  });
}

function handleSqResult(el, d) {
  var summary = d.summary || '';
  var sql = d.generated_sql || '';
  var cols = d.columns || [];
  var rows = d.data || [];
  var total = d.total || rows.length;

  var html = '';
  if (summary) html += '<div>' + summary + '</div>';
  if (sql) html += '<div class="sq-sql-toggle" onclick="var p=this.nextElementSibling;var d=p.style.display;if(!d||d===\'none\'){p.style.display=\'block\';this.querySelector(\'.sq-sql-arrow\').textContent=\'▼\';}else{p.style.display=\'none\';this.querySelector(\'.sq-sql-arrow\').textContent=\'▶\';}"><span class="sq-sql-arrow">▶</span> 查看 SQL</div><div class="sq-msg-sql" style="display:none;margin-top:4px">' + escHtml(sql) + '</div>';
  if (cols.length) {
    html += '<div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">共 ' + total + ' 行</div>';
    html += '<div style="overflow-x:auto;margin-top:4px"><table style="font-size:11px;border-collapse:collapse;width:100%"><thead><tr>';
    cols.forEach(function(c){ html += '<th style="padding:4px 6px;border:1px solid var(--border-light);text-align:left;white-space:nowrap">' + escHtml(c) + '</th>'; });
    html += '</tr></thead><tbody>';
    var maxR = Math.min(rows.length, 20);
    for (var i=0; i<maxR; i++) {
      html += '<tr>';
      cols.forEach(function(c){ var v = rows[i][c]; html += '<td style="padding:3px 6px;border:1px solid var(--border-light);font-size:11px">' + escHtml(v!==null&&v!==undefined?String(v):'') + '</td>'; });
      html += '</tr>';
    }
    html += '</tbody></table></div>';
  }
  el.innerHTML = html;
}

function buildSqResultHtml(d) {
  var summary = d.summary || '';
  var sql = d.generated_sql || '';
  var cols = d.columns || [];
  var rows = d.data || [];
  var total = d.total || rows.length;
  var html = '';
  if (summary) html += '<div style="margin-top:10px;padding-top:10px;border-top:1px solid var(--border-light)">' + summary + '</div>';
  if (sql) html += '<div class="sq-sql-toggle" onclick="var p=this.nextElementSibling;var d=p.style.display;if(!d||d===\'none\'){p.style.display=\'block\';this.querySelector(\'.sq-sql-arrow\').textContent=\'▼\';}else{p.style.display=\'none\';this.querySelector(\'.sq-sql-arrow\').textContent=\'▶\';}"><span class="sq-sql-arrow">▶</span> 查看 SQL</div><div class="sq-msg-sql" style="display:none;margin-top:6px">' + escHtml(sql) + '</div>';
  if (cols.length) {
    html += '<div style="margin-top:8px;font-size:12px;color:var(--text-secondary)">共 ' + total + ' 行</div>';
    html += '<div style="overflow-x:auto;margin-top:4px"><table style="font-size:11px;border-collapse:collapse;width:100%"><thead><tr>';
    cols.forEach(function(c){ html += '<th style="padding:4px 6px;border:1px solid var(--border-light);text-align:left;white-space:nowrap">' + escHtml(c) + '</th>'; });
    html += '</tr></thead><tbody>';
    var maxR = Math.min(rows.length, 20);
    for (var i=0; i<maxR; i++) {
      html += '<tr>';
      cols.forEach(function(c){ var v = rows[i][c]; html += '<td style="padding:3px 6px;border:1px solid var(--border-light);font-size:11px">' + escHtml(v!==null&&v!==undefined?String(v):'') + '</td>'; });
      html += '</tr>';
    }
    html += '</tbody></table></div>';
  }
  return html;
}

function showDialog(title,bodyHtml){
  closeDialog();
  var o=document.createElement('div');o.style.cssText='position:fixed;inset:0;z-index:1000;background:rgba(0,0,0,0.4);display:flex;align-items:center;justify-content:center';
  var d=document.createElement('div');d.style.cssText='background:var(--bg-card);border-radius:var(--radius-lg);width:700px;max-width:90vw;max-height:85vh;overflow-y:auto;box-shadow:0 20px 60px rgba(0,0,0,0.2)';
  d.innerHTML='<div style="padding:16px 20px;border-bottom:1px solid var(--border);font-size:16px;font-weight:600">'+title+'</div><div style="padding:20px">'+bodyHtml+'</div>';
  o.appendChild(d);o.onclick=function(e){if(e.target===o)closeDialog();};document.body.appendChild(o);window._dlgOverlay=o;
}
function closeDialog(){var o=window._dlgOverlay;if(o){document.body.removeChild(o);window._dlgOverlay=null;}}

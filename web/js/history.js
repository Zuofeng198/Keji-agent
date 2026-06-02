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
    sessionId = convId;
    el.innerHTML = '';
    if (d.messages && d.messages.length) {
      var msgs = el;
      d.messages.forEach(function(m){
        var html = m.role === 'assistant' ? renderMarkdown(escHtml(m.content)) : escHtml(m.content);
        var bubble = addMessage(m.role, html);
        // 助理消息有思考内容 → 在其上方插入思考面板
        if (m.role === 'assistant' && m.thinking && window.isShowThinking && window.isShowThinking()) {
          var panel = document.createElement('div');
          panel.className = 'thinking-panel';
          panel.innerHTML =
            '<div class="tp-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');var t=this.querySelector(\'.tp-toggle\');t.textContent=t.textContent===\'▼\'?\'▶\':\'▼\'">' +
            '<span>' + (window._dualIcon ? window._dualIcon('🧠', 'fa-brain') : '🧠') + ' 思考过程</span><span class="tp-toggle">▼</span></div>' +
            '<div class="tp-body">' + (window._replaceEmoji ? window._replaceEmoji((m.thinking||'').replace(/\n/g, '<br>')) : escHtml(m.thinking||'')) + '</div>';
          var msgDiv = bubble ? bubble.parentNode : null;
          if (msgDiv) msgs.insertBefore(panel, msgDiv);
        }
      });
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


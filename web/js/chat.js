// 智能滚动：用户不在底部时不强制下拉
function _autoScroll(el, threshold) {
  if (!el) return;
  threshold = threshold || 120;
  if (el.scrollTop + el.clientHeight >= el.scrollHeight - threshold) {
    el.scrollTop = el.scrollHeight;
  }
}

// ═══════════════ 斜杠命令处理 ═══════════════

async function execCommand(cmd, args) {
  switch (cmd) {
    case '/new':
      showConfirm('新建对话', '确定新建对话？当前对话将保留在历史中。', function() { newChat(); });
      return true;
    case '/clear':
      showDangerConfirm('删除对话', '确定删除当前对话？此操作不可恢复！', function() {
        if (currentConvId) {
          kejiFetch('/api/conversations/' + currentConvId, { method: 'DELETE' }).catch(function(){});
        }
        conversationId = '';
        currentConvId = '';
        sessionId = '';
        document.getElementById('chatMessages').innerHTML =
          '<div class="empty-state"><div class="big-icon">' + _dualIcon('👋', 'fa-hand-wave') + '</div><h3>你好！我是科吉</h3><p>对话已删除，可以开始新话题。</p></div>';
        document.getElementById('convTitle').textContent = '新对话';
      });
      return true;
    case '/history':
      openHistory();
      return true;
    case '/stop':
      stopStreaming();
      return true;
    default:
      return false; // 不认识的命令，交给后端或 AI
  }
}

async function fetchCommand(cmd, args) {
  var name = cmd.replace('/', '');
  var url = '/api/command/' + name;
  try {
    var res = await kejiFetch(url);
    if (!res.ok) return null;
    var data = await res.json();
    return data.text || '(无输出)';
  } catch(e) {
    return null;
  }
}

/** 在对话区显示命令 + 结果 */
async function showCommandResult(cmdText, resultText) {
  var msgs = document.getElementById('chatMessages');
  var empty = msgs.querySelector('.empty-state');
  if (empty) empty.remove();
  addMessage('user', escHtml(cmdText));
  addMessage('assistant', renderMarkdown(escHtml(resultText || '')));
  _autoScroll(msgs);
}

async function handleSlashInput(msg) {
  var parts = msg.split(' ');
  var cmd = parts[0].toLowerCase();
  var args = parts.slice(1);

  // 纯前端命令（不显示在对话，直接执行）
  if (cmd === '/new' || cmd === '/clear' || cmd === '/history' || cmd === '/stop') {
    execCommand(cmd, args);
    return { handled: true };
  }

  // /compact 特殊处理：POST + 切换 session
  if (cmd === '/compact') {
    var sid = sessionId || currentConvId || conversationId;
    if (!sid) { await showCommandResult(msg, '没有可压缩的对话。请先开始一段对话。'); return { handled: true }; }
    var msgs = document.getElementById('chatMessages');
    addMessage('user', escHtml(msg));
    var statusEl = document.createElement('div');
    statusEl.className = 'phase-badge phase-thinking';
    statusEl.textContent = '📦 压缩对话中...（AI 生成摘要）';
    msgs.appendChild(statusEl);
    _autoScroll(msgs);
    try {
      var res = await kejiFetch('/api/compact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid })
      });
      if (res.ok) {
        var data = await res.json();
        if (statusEl) statusEl.remove();
        addMessage('assistant', renderMarkdown(escHtml(data.text || '')));
        if (data.new_session_id) {
          sessionId = data.new_session_id;
          currentConvId = data.new_session_id;
          conversationId = data.new_session_id;
        }
      } else {
        if (statusEl) statusEl.remove();
        addMessage('assistant', '压缩失败：服务器返回 ' + res.status);
      }
    } catch(e) {
      if (statusEl) statusEl.remove();
      addMessage('assistant', '压缩失败：' + e.message);
    }
    return { handled: true };
  }

  // 技能命令
  if (cmd === '/skills') {
    try {
      var res = await kejiFetch('/api/skills');
      if (!res.ok) { await showCommandResult(msg, '获取技能列表失败'); return { handled: true }; }
      var data = await res.json();
      var skills = data.skills || [];
      if (!skills.length) {
        await showCommandResult(msg, '暂无可用技能。在 skills/ 目录下放置 SKILL.md 即可添加。');
      } else {
        var lines = ['**可用技能：**'];
        skills.forEach(function(s){
          lines.push('  `/use ' + s.name + '`  — ' + s.description);
        });
        lines.push('');
        lines.push('使用 `/use 技能名` 激活技能，`/unload` 卸载');
        await showCommandResult(msg, lines.join('\n'));
      }
    } catch(e) {
      await showCommandResult(msg, '获取技能列表失败: ' + e.message);
    }
    return { handled: true };
  }

  if (cmd === '/use') {
    var skillName = args.join(' ');
    if (!skillName) { await showCommandResult(msg, '请指定技能名，如：`/use excel-analyzer`'); return { handled: true }; }
    var sid_use = sessionId || currentConvId || conversationId;
    if (!sid_use) { await showCommandResult(msg, '请先开始一段对话'); return { handled: true }; }
    try {
      var res = await kejiFetch('/api/skills/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid_use, skill_name: skillName })
      });
      var data = await res.json();
      await showCommandResult(msg, data.message || '操作完成');
    } catch(e) {
      await showCommandResult(msg, '激活失败: ' + e.message);
    }
    return { handled: true };
  }

  if (cmd === '/unload') {
    var sid_unload = sessionId || currentConvId || conversationId;
    if (!sid_unload) { await showCommandResult(msg, '没有激活的技能'); return { handled: true }; }
    try {
      var res = await kejiFetch('/api/skills/deactivate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid_unload })
      });
      var data = await res.json();
      await showCommandResult(msg, data.message || '已卸载所有技能');
    } catch(e) {
      await showCommandResult(msg, '卸载失败: ' + e.message);
    }
    return { handled: true };
  }

  // 后端命令
  var result = await fetchCommand(cmd, args);
  if (result) {
    await showCommandResult(msg, result);
    return { handled: true };
  }

  // 不认识 → 放行给 AI
  return { handled: false };
}

// ═══════════════ 快捷命令栏 ═══════════════

var QUICK_COMMANDS = [
  { cmd: '/new',       desc: '新建对话' },
  { cmd: '/clear',     desc: '删除当前对话' },
  { cmd: '/compact',   desc: '压缩对话历史' },
  { cmd: '/skills',    desc: '技能列表' },
  { cmd: '/use',       desc: '激活技能' },
  { cmd: '/unload',    desc: '卸载技能' },
  { cmd: '/status',    desc: '系统状态' },
  { cmd: '/selfcheck', desc: '运行自检' },
  { cmd: '/tools',     desc: '工具列表' },
  { cmd: '/knowledge', desc: '知识库统计' },
  { cmd: '/cost',      desc: '会话统计' },
  { cmd: '/history',   desc: '历史对话' },
];

function toggleQuickCmds() {
  var panel = document.getElementById('quickCmdBar');
  var btn = document.getElementById('qcToggleBtn');
  if (!panel || !btn) return;
  var isOpen = panel.style.display !== 'none' && panel.classList.contains('open');
  if (isOpen) {
    panel.style.display = 'none';
    panel.classList.remove('open');
    btn.classList.remove('open');
  } else {
    panel.style.display = 'flex';
    panel.classList.add('open');
    btn.classList.add('open');
  }
}

async function onQuickCmdClick(cmd) {
  // 前端命令直接执行
  if (cmd === '/new' || cmd === '/clear' || cmd === '/history' || cmd === '/stop') {
    execCommand(cmd, []);
    return;
  }
  // 命令：显示在对话再执行
  var msgs = document.getElementById('chatMessages');
  var empty = msgs.querySelector('.empty-state');
  if (empty) empty.remove();
  addMessage('user', escHtml(cmd));

  // 技能命令
  if (cmd === '/skills') { onQuickCmdSkills(); return; }
  if (cmd === '/use') { onQuickCmdUse(); return; }
  if (cmd === '/unload') { onQuickCmdUnload(); return; }

  // /compact 特殊处理：POST + 切换 session
  if (cmd === '/compact') {
    var sid = sessionId || currentConvId || conversationId;
    if (!sid) { addMessage('assistant', '没有可压缩的对话。请先开始一段对话。'); _autoScroll(msgs); return; }
    var statusEl = document.createElement('div');
    statusEl.className = 'phase-badge phase-thinking';
    statusEl.textContent = '📦 压缩对话中...（AI 生成摘要）';
    msgs.appendChild(statusEl);
    _autoScroll(msgs);
    try {
      var res = await kejiFetch('/api/compact', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sid })
      });
      if (res.ok) {
        var data = await res.json();
        if (statusEl) statusEl.remove();
        addMessage('assistant', renderMarkdown(escHtml(data.text || '')));
        if (data.new_session_id) {
          sessionId = data.new_session_id;
          currentConvId = data.new_session_id;
          conversationId = data.new_session_id;
        }
      } else {
        if (statusEl) statusEl.remove();
        addMessage('assistant', '压缩失败：服务器返回 ' + res.status);
      }
    } catch(e) {
      if (statusEl) statusEl.remove();
      addMessage('assistant', '压缩失败：' + e.message);
    }
    _autoScroll(msgs);
    return;
  }

  // 普通后端命令
  var result = await fetchCommand(cmd, []);
  addMessage('assistant', renderMarkdown(escHtml(result || '')));
  _autoScroll(msgs);
}

async function onQuickCmdSkills() {
  var msgs = document.getElementById('chatMessages');
  var empty = msgs.querySelector('.empty-state');
  if (empty) empty.remove();
  addMessage('user', escHtml('/skills'));
  try {
    var res = await kejiFetch('/api/skills');
    if (!res.ok) { addMessage('assistant', '获取技能列表失败'); _autoScroll(msgs); return; }
    var data = await res.json();
    var skills = data.skills || [];
    if (!skills.length) {
      addMessage('assistant', '暂无可用技能');
    } else {
      var lines = ['**可用技能：**'];
      skills.forEach(function(s){ lines.push('  `/use ' + s.name + '`  — ' + s.description); });
      lines.push('');
      lines.push('使用 `/use 技能名` 激活技能，`/unload` 卸载');
      addMessage('assistant', renderMarkdown(escHtml(lines.join('\n'))));
    }
  } catch(e) {
    addMessage('assistant', '获取技能列表失败: ' + e.message);
  }
  _autoScroll(msgs);
}

async function onQuickCmdUse() {
  var msgs = document.getElementById('chatMessages');
  var empty = msgs.querySelector('.empty-state');
  if (empty) empty.remove();
  addMessage('user', escHtml('/use'));
  // 先列出可用技能，让用户选
  try {
    var res = await kejiFetch('/api/skills');
    if (!res.ok) { addMessage('assistant', '获取技能列表失败'); _autoScroll(msgs); return; }
    var data = await res.json();
    var sks = data.skills || [];
    if (!sks.length) { addMessage('assistant', '暂无可用技能'); _autoScroll(msgs); return; }
    var lines = ['请使用命令输入完整技能名：', ''];
    sks.forEach(function(s){ lines.push('  `/use ' + s.name + '`  — ' + s.description); });
    addMessage('assistant', renderMarkdown(escHtml(lines.join('\n'))));
  } catch(e) {
    addMessage('assistant', '获取技能列表失败: ' + e.message);
  }
  _autoScroll(msgs);
}

async function onQuickCmdUnload() {
  var msgs = document.getElementById('chatMessages');
  var empty = msgs.querySelector('.empty-state');
  if (empty) empty.remove();
  addMessage('user', escHtml('/unload'));
  var sid = sessionId || currentConvId || conversationId;
  if (!sid) { addMessage('assistant', '没有激活的技能'); _autoScroll(msgs); return; }
  try {
    var res = await kejiFetch('/api/skills/deactivate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: sid })
    });
    var data = await res.json();
    addMessage('assistant', data.message || '已卸载所有技能');
  } catch(e) {
    addMessage('assistant', '卸载失败: ' + e.message);
  }
  _autoScroll(msgs);
}

function renderQuickCommands() {
  var bar = document.getElementById('quickCmdBar');
  if (!bar) return;
  bar.innerHTML = '';
  QUICK_COMMANDS.forEach(function(qc) {
    var btn = document.createElement('button');
    btn.className = 'qc-btn';
    btn.innerHTML = '<span class="qc-cmd">' + qc.cmd + '</span><span class="qc-desc">' + qc.desc + '</span>';
    btn.onclick = function() { onQuickCmdClick(qc.cmd); };
    bar.appendChild(btn);
  });
}
document.addEventListener('DOMContentLoaded', renderQuickCommands);

async function sendPlanExecute(q, files) {
  try {
    var res = await kejiFetch('/chat/plan', {
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
    var thinkingTimer = null;
    var msgs = document.getElementById('chatMessages');
    while (true) {
      var r = await reader.read(); if (r.done) {
        if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
        break;
      }
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
                hdr.innerHTML = '<span>'+_dualIcon('🧠','fa-brain')+' 思考计划 <span class="tp-timer">00:00</span></span><span class="tp-toggle">▼</span>';
                var planTimerStart = Date.now();
                var planTimerEl = hdr.querySelector('.tp-timer');
                thinkingTimer = setInterval(function() {
                  if (!planTimerEl) return;
                  var sec = Math.floor((Date.now() - planTimerStart) / 1000);
                  planTimerEl.textContent = String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
                }, 1000);
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
                _autoScroll(msgs);
              }
              thinkingHtml += evt.token || '';
              thinkingBody.innerHTML = _replaceEmoji(thinkingHtml.replace(/</g,'&lt;').replace(/\n/g,'<br>'));
              _autoScroll(msgs);
              break;
            case 'plan':
              // 保留思考面板，标记为已完成
              if (thinkingPanel) {
                var hdr = thinkingPanel.querySelector('.tp-header span');
                if (hdr) hdr.innerHTML = _dualIcon('✅','fa-circle-check')+' 计划已就绪 <span class="tp-timer plan-done">'+(planTimerEl?planTimerEl.textContent:'00:00')+'</span>';
                if (thinkingBody) { thinkingBody.style.opacity = '0.5'; }
              }
              if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
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
    var res = await kejiFetch('/chat/execute', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({plan: currentPlan, query: q, session_id: sessionId, conversation_id: currentConvId})
    });
    sessionId = res.headers.get('X-Session-Id') || sessionId;
    var ncid = res.headers.get('X-Conversation-Id') || '';
    if (ncid) { currentConvId = ncid; conversationId = ncid; }
    currentReader = res.body.getReader();
    var reader = currentReader, dec = new TextDecoder(), buf = '', aiDiv = null, phaseDiv = null, fullReply = '', msgs = document.getElementById('chatMessages');
    var execTimer = null, execTimerStart = null, execTimerDiv = null;
    while (true) {
      var r = await reader.read(); if (r.done) {
        if (execTimer) { clearInterval(execTimer); execTimer = null; }
        if (execTimerDiv) { execTimerDiv.remove(); execTimerDiv = null; }
        break;
      }
      buf += dec.decode(r.value, {stream: true});
      var tokens = buf.split('\n'); buf = tokens.pop() || '';
      for (var ti = 0; ti < tokens.length; ti++) {
        var line = tokens[ti]; if (!line.startsWith('data: ')) continue;
        try {
          var evt = JSON.parse(line.slice(6));
          debugEvents.push(Object.assign({_time: Date.now()}, evt));
          switch (evt.phase) {
            case 'plan_exec_start': if(phaseDiv)phaseDiv.remove(); phaseDiv=addPhase(_dualIcon('⚡','fa-bolt')+' 执行 '+(evt.total_steps||0)+' 步...','thinking');
              if (!execTimer) {
                execTimerStart = Date.now();
                execTimerDiv = document.createElement('div');
                execTimerDiv.className = 'phase-badge phase-thinking exec-timer';
                execTimerDiv.textContent = '⏱ 00:00';
                msgs.appendChild(execTimerDiv);
                execTimer = setInterval(function() {
                  if (!execTimerDiv) return;
                  var sec = Math.floor((Date.now() - execTimerStart) / 1000);
                  execTimerDiv.textContent = '⏱ ' + String(Math.floor(sec / 60)).padStart(2,'0') + ':' + String(sec % 60).padStart(2,'0');
                }, 1000);
              }
              break;
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
                _autoScroll(msgs);
              }
              if (window._execThinkBody) {
                window._execThinkBody.innerHTML += _replaceEmoji(escHtml(evt.token || ''));
                _autoScroll(msgs);
              }
              break;
            case 'tool_call':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('🔧','fa-wrench')+' '+(evt.tools||[]).join(', '),'thinking');
              var tools=evt.tools||[];
              var tcCard=document.createElement('div');
              tcCard.className='tool-card tc-running';
              tcCard.innerHTML='<div class="tc-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');var t=this.querySelector(\'.tc-toggle\');t.textContent=t.textContent==\'▼\'?\'▶\':\'▼\'">'+
                '<span class="tc-icon">'+_dualIcon('🔧','fa-wrench')+'</span><span class="tc-name">调用: '+tools.join(', ')+'</span><span class="tc-status">执行中...</span><span class="tc-toggle">▼</span></div>'+
                '<div class="tc-body"><span style="color:#999">等待结果...</span></div>';
              msgs.appendChild(tcCard);
              _autoScroll(msgs);
              break;
            case 'plan_correction':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('🔧','fa-wrench')+' '+(evt.reason||'自动修正中...'),'thinking');
              var corrCard=document.createElement('div');
              corrCard.className='tool-card tc-running';
              corrCard.innerHTML='<div class="tc-header"><span class="tc-icon">'+_dualIcon('🔧','fa-wrench')+'</span><span class="tc-name">修正步骤'+(evt.step||'')+'：'+(evt.tool||'')+'</span><span class="tc-status">执行中...</span><span class="tc-toggle">▼</span></div><div class="tc-body"><span style="color:#999">等待结果...</span></div>';
              msgs.appendChild(corrCard);
              _autoScroll(msgs);
              break;
            case 'plan_step':
              if(phaseDiv)phaseDiv.remove();
              phaseDiv=addPhase(_dualIcon('⚡','fa-bolt')+' 步骤 '+evt.step+'/'+evt.total+'：'+(evt.description||''),'thinking');
              var stepCard=document.createElement('div');
              stepCard.className='tool-card tc-running';
              stepCard.id='tc_plan_'+evt.step;
              stepCard.innerHTML='<div class="tc-header"><span class="tc-icon">'+_dualIcon('⚡','fa-bolt')+'</span><span class="tc-name">步骤 '+evt.step+': '+(evt.description||'')+'</span><span class="tc-status">执行中...</span><span class="tc-toggle">▼</span></div><div class="tc-body"><span style="color:#999">等待结果...</span></div>';
              msgs.appendChild(stepCard);
              _autoScroll(msgs);
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
              _autoScroll(msgs);
              break;
            case 'done': document.querySelectorAll('.phase-badge').forEach(function(e){e.remove()}); document.getElementById('stopBtn').style.display='none';
              if (execTimer) { clearInterval(execTimer); execTimer = null; }
              if (execTimerDiv) { execTimerDiv.remove(); execTimerDiv = null; }
              break;
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
  if (page === 'stats') { setTimeout(loadStats, 50); }
  if (page === 'tools') { setTimeout(loadToolPage, 50); }
  if (page === 'settings') { setTimeout(function() {
    if (typeof loadAuditLogs === 'function') loadAuditLogs();
  }, 50); }
}

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

// ===== 技能面板 =====
function toggleSkillPanel() {
  var panel = document.getElementById('skillPanel');
  var isOpen = panel.classList.contains('open');
  panel.classList.toggle('open');
  if (!isOpen) loadSkillPanel();
}

// 技能快捷预设（多选组合，点一下加，再点一下减）
var SKILL_PRESETS = [
  { name: '🗄️ 数据处理', skills: ['iceberg','paimon','flink','fluss','lance','iggy','docker-compose'] },
  { name: '📄 办公文档', skills: ['docx','xlsx','pdf','pptx'] },
  { name: '🎨 内容创作', skills: ['doc-coauthoring','internal-comms','deck'] },
  { name: '💻 前端开发', skills: ['frontend-design','web-artifacts-builder','webapp-testing'] },
  { name: '🎭 设计', skills: ['canvas-design','brand-guidelines','theme-factory','algorithmic-art','slack-gif-creator'] },
];

function toggleSkillPreset(presetName) {
  var preset = null;
  for (var i = 0; i < SKILL_PRESETS.length; i++) {
    if (SKILL_PRESETS[i].name === presetName) { preset = SKILL_PRESETS[i]; break; }
  }
  if (!preset) return;
  var sid = sessionId || currentConvId || conversationId;
  if (!sid) { toast('请先开始一段对话', 'info'); return; }

  kejiFetch('/api/skills/active', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sid})
  }).then(function(r){return r.json()}).then(function(d){
    var current = d.active_skills || [];
    var currentSet = {};
    current.forEach(function(n){ currentSet[n] = true; });

    var allActive = true;
    for (var i = 0; i < preset.skills.length; i++) {
      if (!currentSet[preset.skills[i]]) { allActive = false; break; }
    }

    var newSkills;
    if (allActive) {
      var removeSet = {};
      preset.skills.forEach(function(n){ removeSet[n] = true; });
      newSkills = current.filter(function(n){ return !removeSet[n]; });
    } else {
      newSkills = current.slice();
      preset.skills.forEach(function(n){
        if (newSkills.indexOf(n) < 0) newSkills.push(n);
      });
    }

    return kejiFetch('/api/skills/set', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({session_id: sid, skills: newSkills})
    });
  }).then(function(r){return r.json()}).then(function(d){
    if (d.status === 'ok') { loadSkillPanel(); }
    else { toast(d.message || '操作失败', 'error'); }
  }).catch(function(e){ toast('请求失败: ' + e.message, 'error'); });
}

function loadSkillPanel() {
  var body = document.getElementById('skillPanelBody');
  body.innerHTML = '<div style="text-align:center;padding:20px;color:var(--text-secondary)"><div class="spinner"></div>加载中...</div>';

  var sid = sessionId || currentConvId || conversationId;
  // 没有活跃会话时生成临时 ID，让新会话能直接看到默认技能
  if (!sid) {
    sid = 'tmp_' + Date.now().toString(36);
    sessionId = sid;
  }
  Promise.all([
    kejiFetch('/api/skills').then(function(r){return r.json()}).then(function(d){return d.skills || [];}),
    sid ? kejiFetch('/api/skills/active', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({session_id:sid})}).then(function(r){return r.json()}).then(function(d){return d.active_skills || []}).catch(function(){return [];}) : Promise.resolve([])
  ]).then(function(results){
    var skills = results[0];
    var activeSkills = results[1] || [];
    if (!skills.length) {
      body.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-secondary)">暂无可用技能</div>';
      return;
    }

    // 按分类分组
    var groups = {};
    skills.forEach(function(s){
      var cat = s.category || '其他';
      if (!groups[cat]) groups[cat] = {active: [], inactive: []};
      if (activeSkills.indexOf(s.name) >= 0) groups[cat].active.push(s);
      else groups[cat].inactive.push(s);
    });

    // 检测当前激活匹配哪个预设
    var activeSet = {};
    activeSkills.forEach(function(n){ activeSet[n] = true; });
    var matchedPreset = null;
    for (var pi = 0; pi < SKILL_PRESETS.length; pi++) {
      var p = SKILL_PRESETS[pi];
      if (p.name === '🧰 全部技能') continue;
      var match = true;
      if (p.skills.length !== Object.keys(activeSet).length) { match = false; continue; }
      for (var si = 0; si < p.skills.length; si++) {
        if (!activeSet[p.skills[si]]) { match = false; break; }
      }
      if (match) { matchedPreset = p; break; }
    }
    // 如果激活的是默认技能（docx+xlsx+pdf）也算"办公文档"预设
    if (!matchedPreset && Object.keys(activeSet).length === 3 &&
        activeSet['docx'] && activeSet['xlsx'] && activeSet['pdf'] &&
        !activeSet['pptx']) {
      matchedPreset = SKILL_PRESETS[1]; // 办公文档
    }

    // 预设栏（多选组合）
    var html = '<div class="skill-presets">';
    for (var pi = 0; pi < SKILL_PRESETS.length; pi++) {
      var p = SKILL_PRESETS[pi];
      var allIn = 0;
      for (var si = 0; si < p.skills.length; si++) {
        if (activeSet[p.skills[si]]) allIn++;
      }
      var cls = 'skill-preset-btn';
      if (allIn === p.skills.length) cls += ' active';
      else if (allIn > 0) cls += ' partial';
      html += '<button class="' + cls + '" onclick="toggleSkillPreset(\'' + p.name.replace(/'/g, "\\'") + '\')">' + p.name + '</button>';
    }
    html += '</div>';

    // 分类显示顺序
    var catOrder = ['数据处理','文档处理','内容创作','设计','开发工具','系统管理','其他'];
    catOrder.forEach(function(cat){
      var g = groups[cat];
      if (!g || (!g.active.length && !g.inactive.length)) return;
      html += '<div class="skill-section-title">' + escHtml(cat) + '</div>';
      g.active.forEach(function(s){ html += renderSkillCard(s, true); });
      g.inactive.forEach(function(s){ html += renderSkillCard(s, false); });
    });
    body.innerHTML = html;
  }).catch(function(){
    body.innerHTML = '<div style="text-align:center;padding:30px;color:var(--text-secondary)">加载失败</div>';
  });
}

function renderSkillCard(skill, isActive) {
  var name = skill.name;
  var desc = skill.description || '';
  var activeClass = isActive ? 'active' : '';
  var activeStyle = isActive ? ' style="background:#e8f5e9;border-color:#27ae60"' : '';
  var btnHtml = isActive
    ? '<button class="btn btn-sm btn-outline" style="color:var(--danger);border-color:var(--danger)" onclick="deactivateSkill(\'' + name + '\')"><span class="icon-emoji">✕</span><i class="icon-fa fa-solid fa-xmark"></i> 卸载</button>'
    : '<button class="btn btn-sm btn-primary" onclick="activateSkill(\'' + name + '\')"><span class="icon-emoji">✓</span><i class="icon-fa fa-solid fa-check"></i> 激活</button>';
  return '<div class="skill-card ' + activeClass + '"' + activeStyle + ' data-skill-name="' + escHtml(name) + '">'
    + '<div class="skill-card-name">' + escHtml(name) + '<span class="active-badge">已激活</span></div>'
    + '<div class="skill-card-toggle" onmouseenter="hoverSkillDesc(event, this, \'' + escHtml(desc) + '\')" onmouseleave="hideSkillDesc(event, this)"><span class="toggle-arrow">▸</span> 详细信息</div>'
    + '<div class="skill-card-actions">' + btnHtml + '</div>'
    + '</div>';
}

var _skillPopupTimer = null;
var _skillPopupEl = null;

function hoverSkillDesc(event, el, desc) {
  if (_skillPopupTimer) clearTimeout(_skillPopupTimer);
  _skillPopupTimer = setTimeout(function() {
    // 移除旧的浮层
    var old = document.getElementById('skillPopup');
    if (old) old.remove();

    var popup = document.createElement('div');
    popup.id = 'skillPopup';
    popup.className = 'skill-popup';
    popup.textContent = desc;

    var rect = el.getBoundingClientRect();
    // 先挂载到 body 测量实际高度
    popup.style.left = '-9999px';
    popup.style.top = '-9999px';
    document.body.appendChild(popup);
    var actualH = popup.offsetHeight;
    var spaceBelow = window.innerHeight - rect.bottom - 6;
    if (spaceBelow < actualH && rect.top > actualH + 6) {
      popup.style.top = (rect.top - actualH - 4) + 'px';
    } else {
      popup.style.top = (rect.bottom + 4) + 'px';
    }
    popup.style.left = Math.min(Math.max(rect.left, 4), window.innerWidth - 360) + 'px';

    document.body.appendChild(popup);
    _skillPopupEl = popup;

    // 浮层本身也监听 hover，避免移上去看的时候消失
    popup.onmouseenter = function() {
      if (_skillPopupTimer) clearTimeout(_skillPopupTimer);
    };
    popup.onmouseleave = function() {
      popup.remove();
      _skillPopupEl = null;
    };
  }, 500);
}

function hideSkillDesc(event, el) {
  if (_skillPopupTimer) {
    clearTimeout(_skillPopupTimer);
    _skillPopupTimer = null;
  }
  // 延迟一点点再移除，防止移回到浮层时闪动
  setTimeout(function() {
    if (_skillPopupEl && !_skillPopupEl.matches(':hover')) {
      _skillPopupEl.remove();
      _skillPopupEl = null;
    }
  }, 100);
}

function activateSkill(name) {
  var sid = sessionId || currentConvId || conversationId;
  if (!sid) { toast('请先开始一段对话', 'error'); return; }
  kejiFetch('/api/skills/activate', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sid, skill_name: name})
  }).then(function(r){return r.json()}).then(function(d){
    if (d.status === 'ok') { toast(d.message, 'success'); loadSkillPanel(); }
    else { toast(d.message || '激活失败', 'error'); }
  }).catch(function(e){ toast('激活失败: ' + e.message, 'error'); });
}

function deactivateSkill(name) {
  var sid = sessionId || currentConvId || conversationId;
  if (!sid) return;
  kejiFetch('/api/skills/deactivate', {
    method: 'POST',
    headers: {'Content-Type':'application/json'},
    body: JSON.stringify({session_id: sid, skill_name: name})
  }).then(function(r){return r.json()}).then(function(d){
    if (d.status === 'ok') { toast(d.message, 'success'); loadSkillPanel(); }
    else { toast(d.message || '卸载失败', 'error'); }
  }).catch(function(e){ toast('卸载失败: ' + e.message, 'error'); });
}

function toggleConvPanel() {
  const panel = document.getElementById('convPanel');
  panel.classList.toggle('open');
  if (panel.classList.contains('open')) loadConvList();
}

function loadConvList() {
  kejiFetch('/api/conversations').then(r => r.json()).then(d => {
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
  kejiFetch('/api/conversations/' + id).then(r => r.json()).then(d => {
    currentConvId = id;
    conversationId = id;
    sessionId = id;  // ← 关键：让后续消息发到同一个会话
    document.getElementById('convTitle').textContent = d.conversation.title;
    document.getElementById('convPanel').classList.remove('open');

    const msgs = document.getElementById('chatMessages');
    msgs.innerHTML = '';
    if (d.messages && d.messages.length) {
      d.messages.forEach(function(m) {
        var html = m.role === 'assistant' ? renderMarkdown(escHtml(m.content)) : escHtml(m.content);
        var bubble = addMessage(m.role, html);
        // 助理消息有思考内容 → 在其上方插入思考面板
        if (m.role === 'assistant' && m.thinking && isShowThinking()) {
          var panel = document.createElement('div');
          panel.className = 'thinking-panel';
          panel.innerHTML =
            '<div class="tp-header" onclick="this.nextElementSibling.classList.toggle(\'collapsed\');var t=this.querySelector(\'.tp-toggle\');t.textContent=t.textContent===\'▼\'?\'▶\':\'▼\'">' +
            '<span>' + _dualIcon('🧠', 'fa-brain') + ' 思考过程</span><span class="tp-toggle">▼</span></div>' +
            '<div class="tp-body">' + _replaceEmoji(escHtml(m.thinking).replace(/\n/g, '<br>')) + '</div>';
          var msgDiv = bubble ? bubble.closest('.message') : null;
          if (msgDiv) msgs.insertBefore(panel, msgDiv);
        }
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

  kejiFetch('/api/upload', { method: 'POST', body: formData })
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

  // 斜杠命令拦截
  if (queryText.startsWith('/')) {
    var cmdResult = await handleSlashInput(queryText);
    if (cmdResult.handled) {
      isStreaming = false;
      btn.disabled = false;
      input.focus();
      return;
    }
    // 不认识的命令继续走 AI
  }

  addMessage('user', escHtml(queryText));
  input.value = '';
  input.style.height = 'auto';

  try {
    const res = await kejiFetch('/chat/stream', {
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
    let thinkingTimer = null;
    let toolTimers = {};
    let statusBar = document.createElement('div');
    statusBar.className = 'phase-badge phase-thinking status-bar';
    statusBar.textContent = '⏳ 处理中';
    msgs.appendChild(statusBar);

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
                    '<span>' + _dualIcon('🧠', 'fa-brain') + ' 思考过程 <span class="tp-timer">00:00</span></span><span class="tp-toggle">▼</span></div><div class="tp-body"></div>';
                  msgs.appendChild(tp);
                  thinkingPanel = tp;
                  thinkingBody = tp.querySelector('.tp-body');
                  var tpHdr = tp.querySelector('.tp-header');
                  var tpTimerEl = tpHdr ? tpHdr.querySelector('.tp-timer') : null;
                  var tpTimerStart = Date.now();
                  if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
                  thinkingTimer = setInterval(function() {
                    if (!tpTimerEl) return;
                    var sec = Math.floor((Date.now() - tpTimerStart) / 1000);
                    tpTimerEl.textContent = String(Math.floor(sec / 60)).padStart(2, '0') + ':' + String(sec % 60).padStart(2, '0');
                  }, 1000);
                  _autoScroll(msgs);
                }
                thinkingHtml += evt.token || '';
                thinkingBody.innerHTML = _replaceEmoji(thinkingHtml);
                _autoScroll(msgs);
              }
              if (statusBar) {
                var tok = evt.token || '';
                if (tok.indexOf('🔧') >= 0 || tok.indexOf('调用工具') >= 0) {
                  statusBar.textContent = '🔧 运行工具...';
                } else if (tok.indexOf('验证') >= 0 || tok.indexOf('检查') >= 0) {
                  statusBar.textContent = '🔍 验证中...';
                } else if (statusBar.textContent === '🔧 运行工具...' && !tok.indexOf('[') === 0) {
                  // keep tool status visible
                } else {
                  statusBar.textContent = '🤔 思考...';
                }
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
                _autoScroll(msgs);
                // 启动耗时计时器
                var startTime = Date.now();
                toolTimers[card.id] = setInterval(function() {
                  var elapsed = Math.floor((Date.now() - startTime) / 1000);
                  var s = card.querySelector('.tc-status');
                  if (s) s.textContent = '运行中... ' + elapsed + 's';
                }, 1000);
              });
              if (thinkingBody && isShowThinking()) {
                thinkingHtml += '\n──────────────\n🔧 调用工具: ' + (evt.tools||[]).join(', ') + '\n';
                thinkingBody.innerHTML = _replaceEmoji(thinkingHtml);
                _autoScroll(msgs);
              }
              break;
            case 'tool_result':
              if (phaseDiv) phaseDiv.remove();
              // 更新对应的 tool card
              var cards = msgs.querySelectorAll('.tool-card');
              var lastCard = cards[cards.length - 1];
              if (lastCard && !lastCard.classList.contains('tc-done')) {
                // 清除耗时计时器
                if (toolTimers[lastCard.id]) {
                  clearInterval(toolTimers[lastCard.id]);
                  delete toolTimers[lastCard.id];
                }
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
                _autoScroll(msgs);
              }
              break;
            case 'answering':
              if (phaseDiv) phaseDiv.remove();
              if (statusBar) { statusBar.textContent = '💬 回答中'; }
              aiDiv = addMessage('assistant', '');
              document.getElementById('stopBtn').style.display = 'none';
              break;
            case 'answer':
              if (!aiDiv) { if(phaseDiv)phaseDiv.remove(); aiDiv = addMessage('assistant',''); }
              fullReply += evt.token || '';
              aiDiv.innerHTML = renderMarkdown(escHtml(fullReply));
              _autoScroll(msgs);
              break;
            case 'error':
              toast('错误: ' + escHtml(evt.message||''), 'error');
              break;
            case 'done':
              document.querySelectorAll('.phase-badge').forEach(e => e.remove());
              document.getElementById('stopBtn').style.display = 'none';
              if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
              if (statusBar) { statusBar.textContent = '✅ 完成'; setTimeout(function(){statusBar.remove();statusBar=null;}, 2000); }
              break;
          }
        } catch(e) {}
      }
    }
    document.querySelectorAll('.phase-badge').forEach(e => e.remove());
    if (thinkingTimer) { clearInterval(thinkingTimer); thinkingTimer = null; }
    if (statusBar) { statusBar.remove(); statusBar = null; }
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
  _autoScroll(msgs);
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
  _autoScroll(msgs);
  return div;
}

// ================================================================


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

  kejiFetch('/api/debug/logs?limit=100').then(function(r){return r.json()}).then(function(d){
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

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


// ===== Plan-and-Execute 模式 =====
async function loadAgentMode() {
  try {
    var res = await kejiFetch('/chat/mode?session_id=' + sessionId);
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
    await kejiFetch('/chat/mode', {
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

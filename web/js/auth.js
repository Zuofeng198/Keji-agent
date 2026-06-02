/** 登录与管理页入口 */

function formatApiDetail(data) {
  if (!data) return '请求失败';
  var d = data.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) {
    return d.map(function(x) {
      if (typeof x === 'string') return x;
      var loc = (x.loc && x.loc.length) ? x.loc.join('.') + ': ' : '';
      return loc + (x.msg || JSON.stringify(x));
    }).join('\n');
  }
  return String(d || data.message || '请求失败');
}

function showLoginOverlay(msg) {
  var el = document.getElementById('loginOverlay');
  if (!el) return;
  el.classList.add('open');
  document.body.classList.add('login-lock');
  var err = document.getElementById('loginError');
  if (err) err.textContent = msg || '';
}

function hideLoginOverlay() {
  var el = document.getElementById('loginOverlay');
  if (el) el.classList.remove('open');
  document.body.classList.remove('login-lock');
  var err = document.getElementById('loginError');
  if (err) err.textContent = '';
}

function updateUserChrome() {
  var u = window.kejiCurrentUser;
  var bar = document.getElementById('userBar');
  var adminNav = document.getElementById('navAdmin');
  if (bar) {
    bar.style.display = u ? 'flex' : 'none';
    var nameEl = document.getElementById('userDisplayName');
    if (nameEl) nameEl.textContent = u ? (u.display_name || u.username) : '';
    var roleEl = document.getElementById('userRoleBadge');
    if (roleEl) {
      roleEl.textContent = u && u.role === 'admin' ? '管理员' : (u && u.role === 'readonly' ? '只读' : '成员');
      roleEl.className = 'user-role-badge role-' + (u ? u.role : 'member');
    }
  }
  if (adminNav) adminNav.style.display = u && u.role === 'admin' ? '' : 'none';
  var setNav = document.querySelector('.nav-item[data-page="settings"]');
  if (setNav) setNav.style.display = u && u.role === 'admin' ? '' : 'none';
}

function logoutKeji() {
  setKejiToken('');
  window.kejiCurrentUser = null;
  window.kejiAuthReady = false;
  showLoginOverlay();
}

function clearKejiLocalAuth() {
  setKejiToken('');
  setKejiApiKey('');
  window.kejiCurrentUser = null;
  window.kejiAuthReady = false;
  var err = document.getElementById('loginError');
  if (err) err.textContent = '';
  if (typeof toast === 'function') toast('已清除本地登录信息，请重新输入账号密码', 'success');
  else alert('已清除本地登录信息，请重新登录');
}

async function initAuth() {
  try {
    var res = await fetch('/api/security/status');
    var data = await res.json();
    if (!data.auth_enabled) {
      window.kejiAuthReady = true;
      hideLoginOverlay();
      return;
    }
    if (data.authenticated && data.user) {
      window.kejiCurrentUser = data.user;
      window.kejiAuthReady = true;
      hideLoginOverlay();
      updateUserChrome();
      if (typeof loadModelSettings === 'function') loadModelSettings();
      return;
    }
    var token = getKejiToken();
    if (token) {
      var meRes = await fetch('/api/auth/me', {
        headers: { Authorization: 'Bearer ' + token },
      });
      if (meRes.ok) {
        var me = await meRes.json();
        window.kejiCurrentUser = me.user;
        window.kejiAuthReady = true;
        hideLoginOverlay();
        updateUserChrome();
        if (typeof loadModelSettings === 'function') loadModelSettings();
        return;
      }
      setKejiToken('');
    }
    var err0 = document.getElementById('loginError');
    if (err0) err0.textContent = '';
    showLoginOverlay();
  } catch (e) {
    showLoginOverlay('无法连接服务，请确认科吉已启动');
  }
}

function bindLoginForm() {
  var form = document.getElementById('loginForm');
  if (!form || form._bound) return;
  form._bound = true;
  form.addEventListener('submit', async function(ev) {
    ev.preventDefault();
    var user = document.getElementById('loginUsername').value.trim();
    var pass = document.getElementById('loginPassword').value;
    var err = document.getElementById('loginError');
    if (!user || !pass) {
      if (err) err.textContent = '请输入用户名和密码';
      return;
    }
    if (err) err.textContent = '';
    setKejiToken('');
    try {
      var res = await fetch('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: user, password: pass }),
      });
      var data = {};
      try { data = await res.json(); } catch (e) { /* ignore */ }
      if (!res.ok) {
        if (err) err.textContent = formatApiDetail(data) || ('登录失败 (HTTP ' + res.status + ')');
        return;
      }
      if (!data.token) {
        if (err) err.textContent = '登录响应异常（无 token），请重启服务后重试';
        return;
      }
      setKejiToken(data.token);
      window.kejiCurrentUser = data.user;
      window.kejiAuthReady = true;
      window.kejiJustLoggedIn = true;
      setTimeout(function() { window.kejiJustLoggedIn = false; }, 3000);
      hideLoginOverlay();
      updateUserChrome();
      if (typeof loadModelSettings === 'function') loadModelSettings();
      if (typeof checkStatus === 'function') checkStatus();
    } catch (e) {
      if (err) err.textContent = '网络错误';
    }
  });
}

// ---- 管理页 ----

var _adminUsersCache = [];
var _adminConvCount = 0;

function adminRoleLabel(role) {
  return { admin: '管理员', member: '成员', readonly: '只读' }[role] || role;
}

function adminRoleIcon(role) {
  if (role === 'admin') return '<span class="icon-emoji">🛡️</span><i class="icon-fa fa-solid fa-user-shield"></i>';
  if (role === 'readonly') return '<span class="icon-emoji">👁️</span><i class="icon-fa fa-solid fa-eye"></i>';
  return '<span class="icon-emoji">👤</span><i class="icon-fa fa-solid fa-user"></i>';
}

function updateAdminStats() {
  var users = _adminUsersCache || [];
  var elU = document.getElementById('adminStatUsers');
  var elA = document.getElementById('adminStatActive');
  var elC = document.getElementById('adminStatConvs');
  if (elU) elU.textContent = String(users.length);
  if (elA) elA.textContent = String(users.filter(function(u) { return u.is_active; }).length);
  if (elC) elC.textContent = String(_adminConvCount);
}

function renderAdminUserCard(u) {
  var active = u.is_active;
  var canDelete = u.id !== (window.kejiCurrentUser && window.kejiCurrentUser.id);
  return '<div class="admin-user-card">' +
    '<div class="admin-user-card-main">' +
    '<div class="admin-user-avatar">' + adminRoleIcon(u.role) + '</div>' +
    '<div class="admin-user-info">' +
    '<div class="admin-user-name">' + escHtml(u.display_name || u.username) + '</div>' +
    '<div class="admin-user-sub">' +
    '<span class="text-muted">@' + escHtml(u.username) + '</span>' +
    '<span class="admin-role-badge role-' + escHtml(u.role) + '">' + adminRoleLabel(u.role) + '</span>' +
    '<span><span class="admin-status-dot ' + (active ? 'on' : 'off') + '"></span>' +
    (active ? '已启用' : '已禁用') + '</span>' +
    '</div></div></div>' +
    '<div class="admin-user-actions">' +
    '<select data-uid="' + u.id + '" class="admin-role-select" onchange="adminChangeRole(this)" title="角色">' +
    ['admin', 'member', 'readonly'].map(function(r) {
      return '<option value="' + r + '"' + (u.role === r ? ' selected' : '') + '>' + adminRoleLabel(r) + '</option>';
    }).join('') +
    '</select>' +
    '<button class="btn btn-sm btn-outline" onclick="adminToggleActive(\'' + u.id + '\',' + (active ? 'false' : 'true') + ')">' +
    (active ? '禁用' : '启用') + '</button>' +
    '<button class="btn btn-sm btn-outline" onclick="adminResetPassword(\'' + u.id + '\')">重置密码</button>' +
    (canDelete ?
      '<button class="btn btn-sm btn-danger" onclick="adminDeleteUser(\'' + u.id + '\')">删除</button>' : '') +
    '</div></div>';
}

function _adminApiError(res, data) {
  if (res.status === 401) return '未登录或登录已失效，请重新登录后再打开管理页';
  if (res.status === 403) return '需要管理员权限';
  return formatApiDetail(data) || ('加载失败 (HTTP ' + res.status + ')');
}

async function loadAdminUsers() {
  var box = document.getElementById('adminUserList');
  if (!box) return;
  if (!getKejiToken()) {
    box.innerHTML = '<div class="admin-empty">请先登录管理员账号</div>';
    return;
  }
  box.innerHTML = '<div class="loading"><div class="spinner"></div>加载中...</div>';
  try {
    var res = await kejiFetch('/api/admin/users');
    var data = {};
    try { data = await res.json(); } catch (e) { /* ignore */ }
    if (!res.ok) throw new Error(_adminApiError(res, data));
    var users = data.users || [];
    _adminUsersCache = users;
    updateAdminStats();
    var countEl = document.getElementById('adminUserCount');
    if (countEl) countEl.textContent = users.length ? '共 ' + users.length + ' 人' : '';
    if (!users.length) {
      box.innerHTML = '<div class="admin-empty">暂无用户，请在上方创建</div>';
      return;
    }
    box.innerHTML = users.map(renderAdminUserCard).join('');
  } catch (e) {
    box.innerHTML = '<div class="admin-empty">' + escHtml(e.message || '加载失败') + '</div>';
  }
}

async function adminChangeRole(sel) {
  var uid = sel.getAttribute('data-uid');
  await kejiFetch('/api/admin/users/' + uid, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ role: sel.value }),
  });
}

async function adminToggleActive(uid, active) {
  await kejiFetch('/api/admin/users/' + uid, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ is_active: active }),
  });
  loadAdminUsers();
}

async function adminDeleteUser(uid) {
  var u = _adminUsersCache.find(function(x) { return x.id === uid; });
  var name = u ? (u.display_name || u.username) : uid;
  if (!confirm('确定删除用户「' + name + '」？其对话记录也会一并删除。')) return;
  var res = await kejiFetch('/api/admin/users/' + uid, { method: 'DELETE' });
  var data = {};
  try { data = await res.json(); } catch (e) { /* ignore */ }
  if (!res.ok) {
    alert(formatApiDetail(data) || '删除失败');
    return;
  }
  if (typeof toast === 'function') toast(data.message || '已删除', 'success');
  loadAdminUsers();
  loadAdminConversations();
}

async function adminResetPassword(uid) {
  var pw = prompt('输入新密码（至少 6 位）');
  if (!pw || pw.length < 6) return;
  await kejiFetch('/api/admin/users/' + uid, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password: pw }),
  });
  alert('密码已更新');
}

async function adminCreateUser() {
  var u = document.getElementById('adminNewUsername').value.trim();
  var p = document.getElementById('adminNewPassword').value;
  var r = document.getElementById('adminNewRole').value;
  var d = document.getElementById('adminNewDisplay').value.trim();
  if (!u || !p) {
    alert('请填写用户名和密码');
    return;
  }
  if (u.length < 2) {
    alert('用户名至少 2 个字符');
    return;
  }
  if (p.length < 6) {
    alert('密码至少 6 位（后端校验要求）');
    return;
  }
  try {
    var res = await kejiFetch('/api/admin/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: u, password: p, role: r, display_name: d || u }),
    });
    var data = {};
    try { data = await res.json(); } catch (e) { /* ignore */ }
    if (!res.ok) {
      if (res.status === 403) {
        alert('需要管理员账号登录后才能创建用户（侧栏应有「管理」菜单）');
        return;
      }
      alert(formatApiDetail(data) || ('创建失败 (HTTP ' + res.status + ')'));
      return;
    }
    document.getElementById('adminNewUsername').value = '';
    document.getElementById('adminNewPassword').value = '';
    document.getElementById('adminNewDisplay').value = '';
    if (typeof toast === 'function') {
      toast('用户「' + u + '」已创建', 'success');
    } else {
      alert('用户「' + u + '」已创建');
    }
    loadAdminUsers();
  } catch (e) {
    alert('创建失败：' + (e.message || '网络错误'));
  }
}

async function loadAdminConversations() {
  var box = document.getElementById('adminConvList');
  if (!box) return;
  if (!getKejiToken()) {
    box.innerHTML = '<div class="admin-empty">请先登录</div>';
    return;
  }
  box.innerHTML = '<div class="loading"><div class="spinner"></div>加载中...</div>';
  var filter = document.getElementById('adminConvUserFilter');
  var q = filter && filter.value ? '?user_id=' + encodeURIComponent(filter.value) : '';
  try {
    var res = await kejiFetch('/api/admin/conversations' + q);
    var data = {};
    try { data = await res.json(); } catch (e) { /* ignore */ }
    if (!res.ok) throw new Error(_adminApiError(res, data));
    var arr = data.conversations || [];
    if (!filter || !filter.value) {
      _adminConvCount = arr.length;
      updateAdminStats();
    }
    if (!arr.length) {
      box.innerHTML = '<div class="admin-empty">暂无对话记录</div>';
      return;
    }
    box.innerHTML = arr.map(function(c) {
      var owner = escHtml(c.owner_display_name || c.owner_username || '未知用户');
      var time = escHtml(c.updated_at || c.created_at || '');
      return '<div class="admin-conv-row" data-cid="' + escHtml(c.id) + '" onclick="adminOpenConv(\'' + c.id + '\')">' +
        '<div class="admin-conv-title">' + escHtml(c.title || '新对话') + '</div>' +
        '<div class="admin-conv-meta">' + owner + ' · ' + (c.message_count || 0) + ' 条消息' +
        (time ? '<br>' + time : '') + '</div></div>';
    }).join('');
  } catch (e) {
    box.innerHTML = '<div class="admin-empty">' + escHtml(e.message || '加载失败') + '</div>';
  }
}

function adminPreviewEmptyHtml() {
  return '<div class="admin-preview-scroll"><div class="admin-preview-empty">' +
    '<div class="big-icon"><span class="icon-emoji">💬</span><i class="icon-fa fa-solid fa-message"></i></div>' +
    '<p>从左侧选择一条对话查看最近消息</p></div></div>';
}

function adminPreviewRoleLabel(role) {
  return role === 'user' ? '用户' : role === 'assistant' ? '助手' : role;
}

async function adminOpenConv(convId) {
  var panel = document.getElementById('adminConvPreview');
  if (!panel) return;
  document.querySelectorAll('.admin-conv-row').forEach(function(el) {
    el.classList.toggle('active', el.getAttribute('data-cid') === convId);
  });
  panel.innerHTML = '<div class="admin-preview-scroll"><div class="loading"><div class="spinner"></div>加载中...</div></div>';
  try {
    var res = await kejiFetch('/api/admin/conversations/' + convId);
    var data = await res.json();
    if (!res.ok) throw new Error(data.detail || '加载失败');
    var msgs = (data.messages || []).slice(-30);
    if (!msgs.length) {
      panel.innerHTML = '<div class="admin-preview-head">' + escHtml(data.title || convId) + '</div>' +
        '<div class="admin-preview-scroll"><div class="admin-empty">该对话暂无消息</div></div>';
      return;
    }
    var msgHtml = msgs.map(function(m) {
      var role = m.role || 'assistant';
      return '<div class="admin-preview-msg role-' + escHtml(role) + '">' +
        '<div class="msg-role">' + adminPreviewRoleLabel(role) + '</div>' +
        '<div class="msg-body">' + escHtml(String(m.content || '').slice(0, 2000)) + '</div></div>';
    }).join('');
    panel.innerHTML = '<div class="admin-preview-head">' + escHtml(data.title || convId) +
      ' <span class="text-muted">（最近 ' + msgs.length + ' 条，可向下滚动）</span></div>' +
      '<div class="admin-preview-scroll" id="adminPreviewScroll">' + msgHtml + '</div>';
    var scrollEl = document.getElementById('adminPreviewScroll');
    if (scrollEl) scrollEl.scrollTop = scrollEl.scrollHeight;
  } catch (e) {
    panel.innerHTML = '<div class="admin-preview-scroll"><div class="admin-empty">加载失败</div></div>';
  }
}

function loadAdminPage() {
  loadAdminUsers();
  loadAdminConversations();
  kejiFetch('/api/admin/conversations').then(function(r) { return r.json(); }).then(function(d) {
    _adminConvCount = (d.conversations || []).length;
    updateAdminStats();
  }).catch(function() {});
  kejiFetch('/api/admin/users').then(function(r) { return r.json(); }).then(function(d) {
    var sel = document.getElementById('adminConvUserFilter');
    if (!sel) return;
    var users = d.users || [];
    var cur = sel.value;
    sel.innerHTML = '<option value="">全部用户</option>' +
      users.map(function(u) {
        return '<option value="' + u.id + '">' + escHtml(u.display_name || u.username) + '</option>';
      }).join('');
    if (cur) sel.value = cur;
  });
  var preview = document.getElementById('adminConvPreview');
  if (preview && !preview.querySelector('.admin-preview-msg') && !preview.querySelector('.admin-preview-head')) {
    preview.innerHTML = adminPreviewEmptyHtml();
  }
}

document.addEventListener('DOMContentLoaded', bindLoginForm);

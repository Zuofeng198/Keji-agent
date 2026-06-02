function loadKnowledgeBase() {
  loadKbStats();
  loadKbDocs();
}

function loadKbStats() {
  kejiFetch('/api/knowledge/stats').then(r => r.json()).then(d => {
    document.querySelector('#kbStats .stat-card:nth-child(1) .number').textContent = d.total_documents || 0;
    document.querySelector('#kbStats .stat-card:nth-child(2) .number').textContent = d.total_chunks || 0;
    document.querySelector('#kbStats .stat-card:nth-child(3) .number').textContent = d.vector_count || 0;
  }).catch(() => {});
}

function loadKbDocs() {
  kejiFetch('/api/knowledge/documents').then(r => r.json()).then(d => {
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

  kejiFetch('/api/knowledge/index', {
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
  kejiFetch('/api/knowledge/cancel', { method: 'POST' })
    .then(r => r.json()).then(d => {
      toast('⏹ 已终止索引', 'info');
    }).catch(() => toast('取消失败', 'error'));
}

function deleteDoc(docId) {
  showDangerConfirm('删除知识库文档', '确定要从知识库中删除此文档吗？', function() {
    kejiFetch('/api/knowledge/document/' + docId, { method: 'DELETE' })
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
      return kejiFetch('/api/knowledge/document/' + id, { method: 'DELETE' });
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
      kejiFetch('/api/knowledge/clear', { method: 'POST' })
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

  kejiFetch('/api/knowledge/search?query=' + encodeURIComponent(q) + '&n=10')
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
  kejiFetch('/api/files/drives').then(r => r.json()).then(d => {
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

  kejiFetch('/api/files/list?path=' + encodeURIComponent(path))
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
  kejiFetch('/api/files/open?path=' + encodeURIComponent(filePath), { method: 'POST' })
    .then(r => r.json()).then(d => {
      if (d.status === 'ok') toast('已打开: ' + filePath.split('\\').pop(), 'success');
    }).catch(e => toast('打开失败: ' + e.message, 'error'));
}

function quickIndex(filePath) {
  kejiFetch('/api/knowledge/index', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path: filePath, recursive: false })
  }).then(r => r.json()).then(d => {
    if (d.status === 'ok') toast('✅ 已索引到知识库', 'success');
    else toast('索引失败: ' + (d.message || d.detail || ''), 'error');
  }).catch(e => toast('索引失败: ' + e.message, 'error'));
}
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

function saveKejiApiKey() {
  var el = document.getElementById('setKejiApiKey');
  if (!el) return;
  setKejiApiKey(el.value.trim());
  toast('访问密钥已保存到浏览器', 'success');
  loadSecurityStatus();
}

function loadSecurityStatus() {
  var hint = document.getElementById('securityStatusHint');
  if (!hint) return;
  fetch('/api/security/status').then(function(r) { return r.json(); }).then(function(d) {
    if (!d.auth_enabled) {
      hint.textContent = '服务端未启用鉴权';
      return;
    }
    hint.textContent = d.authenticated ? '已认证' : '未认证（请填写 API Key）';
    hint.style.color = d.authenticated ? '#27ae60' : '#e67e22';
  }).catch(function() { hint.textContent = ''; });
}

var _AUDIT_TYPE_LABELS = { tool_call: '工具调用', file_access: '文件访问' };

function loadAuditLogs() {
  var tbody = document.getElementById('auditLogBody');
  var hint = document.getElementById('auditLoadHint');
  var typeEl = document.getElementById('auditEventType');
  var limitEl = document.getElementById('auditLimit');
  if (!tbody) return;

  var eventType = typeEl ? typeEl.value : '';
  var limit = limitEl ? parseInt(limitEl.value, 10) || 100 : 100;
  var url = '/api/security/audit/logs?limit=' + limit + '&offset=0';
  if (eventType) url += '&event_type=' + encodeURIComponent(eventType);

  if (hint) hint.textContent = '加载中…';
  tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary);padding:20px">加载中…</td></tr>';

  kejiFetch(url)
    .then(function(r) {
      if (!r.ok) {
        return r.json().then(function(d) {
          throw new Error(d.detail || ('HTTP ' + r.status));
        }).catch(function() {
          throw new Error('HTTP ' + r.status);
        });
      }
      return r.json();
    })
    .then(function(d) {
      var events = d.events || [];
      if (hint) hint.textContent = '共 ' + events.length + ' 条（最近）';
      if (!events.length) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--text-secondary);padding:24px">暂无审计记录</td></tr>';
        return;
      }
      tbody.innerHTML = events.map(function(ev) {
        var typeLabel = _AUDIT_TYPE_LABELS[ev.event_type] || ev.event_type || '—';
        var toolOrAction = ev.tool_name || ev.action || '—';
        var detailParts = [];
        if (ev.path) detailParts.push(ev.path);
        else if (ev.detail) detailParts.push(String(ev.detail).slice(0, 200));
        if (ev.session_id) {
          var sid = String(ev.session_id);
          if (sid.length > 12) sid = sid.slice(0, 12) + '…';
          detailParts.push('会话:' + sid);
        }
        var detailPlain = detailParts.join(' · ') || '—';
        var detail = escHtml(detailPlain);
        var statusCls = (ev.status === 'ok') ? 'audit-status-ok' : 'audit-status-error';
        var statusText = ev.status === 'ok' ? '成功' : (ev.status || '—');
        return '<tr>' +
          '<td>' + escHtml(ev.created_at || '—') + '</td>' +
          '<td><span class="audit-type-badge">' + escHtml(typeLabel) + '</span></td>' +
          '<td title="' + escHtml(toolOrAction) + '">' + escHtml(toolOrAction) + '</td>' +
          '<td class="audit-detail-cell" title="' + escHtml(detailPlain) + '">' + detail + '</td>' +
          '<td class="' + statusCls + '">' + escHtml(statusText) + '</td>' +
          '</tr>';
      }).join('');
    })
    .catch(function(e) {
      if (hint) hint.textContent = '';
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;color:var(--danger);padding:20px">加载失败: ' + escHtml(e.message || '') + '</td></tr>';
    });
}

function loadModelSettings() {
  var keyEl = document.getElementById('setKejiApiKey');
  if (keyEl) keyEl.value = getKejiApiKey();
  loadSecurityStatus();
  loadAuditLogs();
  kejiFetch('/api/settings').then(r => r.json()).then(d => {
    var s = d.db_settings || {};
    if (s.model_type) document.getElementById('setModelType').value = s.model_type;
    if (s.ollama_url) document.getElementById('setOllamaUrl').value = s.ollama_url;
    if (s.chat_model) document.getElementById('setChatModel').value = s.chat_model;
    if (s.openai_base_url) document.getElementById('setOpenaiUrl').value = s.openai_base_url;
    var keyInput = document.getElementById('setOpenaiKey');
    if (keyInput) {
      if (s.openai_api_key) keyInput.value = s.openai_api_key;
      keyInput.placeholder = s.openai_api_key_configured
        ? '已配置（留空不修改，填写则写入 .env）'
        : 'sk-...';
    }
    if (s.openai_model) document.getElementById('setOpenaiModel').value = s.openai_model;
    if (s.embed_model) document.getElementById('setEmbedModel').value = s.embed_model;
    if (s.chunk_size) document.getElementById('setChunkSize').value = s.chunk_size;
    if (s.chunk_overlap) document.getElementById('setOverlap').value = s.chunk_overlap;
    if (s.top_k) document.getElementById('setTopK').value = s.top_k;
    var ac = document.getElementById('setAutoCompact');
    if (ac) ac.checked = s.context_auto_compact_enabled !== false && s.context_auto_compact_enabled !== 'false';
    var pt = document.getElementById('setPruneTools');
    if (pt) pt.checked = s.context_prune_tool_results !== false && s.context_prune_tool_results !== 'false';
    var th = document.getElementById('setCompactThreshold');
    if (th && s.context_auto_compact_threshold) th.value = s.context_auto_compact_threshold;
    var mcpTa = document.getElementById('setMcpDirs');
    if (mcpTa && s.mcp_filesystem_dirs) mcpTa.value = s.mcp_filesystem_dirs;
    var mik = document.getElementById('setMcpIncludeKnowledge');
    if (mik) mik.checked = s.mcp_include_knowledge !== false && s.mcp_include_knowledge !== 'false';
    var mid = document.getElementById('setMcpIncludeData');
    if (mid) mid.checked = s.mcp_include_data !== false && s.mcp_include_data !== 'false';
    var mcpHint = document.getElementById('setMcpResolvedHint');
    if (mcpHint && s.mcp_resolved_dirs && s.mcp_resolved_dirs.length) {
      mcpHint.textContent = s.mcp_resolved_dirs.join(' · ');
    }
    toggleModelType();
  }).catch(function(){});
}

function _applyMcpReloadResponse(d) {
  var hint = document.getElementById('setMcpResolvedHint');
  if (hint && d.filesystem_dirs && d.filesystem_dirs.length) {
    hint.textContent = d.filesystem_dirs.join(' · ');
  }
  toast(d.message || 'MCP 已重新连接', 'success');
}

function reloadMcpFilesystem() {
  var btn = document.querySelector('button[onclick="reloadMcpFilesystem()"]');
  var prevText = btn ? btn.textContent : '';
  if (btn) {
    btn.disabled = true;
    btn.textContent = '连接文件 MCP…';
  }
  function tryReload(url) {
    return kejiFetch(url, { method: 'POST' }).then(function(r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    });
  }
  tryReload('/api/mcp/reload')
    .catch(function() { return tryReload('/api/mcp/servers'); })
    .then(_applyMcpReloadResponse)
    .catch(function(e) {
      var msg = String(e.message || e);
      if (msg.indexOf('404') >= 0) {
        toast('应用失败：请先完全退出并重新启动科吉（运行 启动科吉.bat），再点「应用 MCP 目录」', 'error');
      } else {
        toast('应用失败: ' + msg, 'error');
      }
    })
    .finally(function() {
      if (btn) {
        btn.disabled = false;
        btn.textContent = prevText || '应用 MCP 目录（无需重启）';
      }
    });
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

  kejiFetch('/api/models/test', {
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
    context_auto_compact_enabled: document.getElementById('setAutoCompact') ? document.getElementById('setAutoCompact').checked : true,
    context_auto_compact_threshold: document.getElementById('setCompactThreshold') ? document.getElementById('setCompactThreshold').value : '60000',
    context_prune_tool_results: document.getElementById('setPruneTools') ? document.getElementById('setPruneTools').checked : true,
    mcp_filesystem_dirs: document.getElementById('setMcpDirs') ? document.getElementById('setMcpDirs').value : '',
    mcp_include_knowledge: document.getElementById('setMcpIncludeKnowledge') ? document.getElementById('setMcpIncludeKnowledge').checked : true,
    mcp_include_data: document.getElementById('setMcpIncludeData') ? document.getElementById('setMcpIncludeData').checked : true,
  };

  kejiFetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings })
  }).then(function(r) {
    if (!r.ok) {
      return r.json().then(function(d) {
        throw new Error(d.detail || ('HTTP ' + r.status));
      }).catch(function() {
        throw new Error('HTTP ' + r.status);
      });
    }
    return r.json();
  }).then(function(d) {
    toast(d.message || '设置已保存，请重启服务后对话生效', 'success');
  }).catch(function(e) {
    toast('保存失败: ' + (e.message || '未知错误'), 'error');
  });
}

/* ===== 企业微信配置 ===== */
function loadWorkConfig() {
  kejiFetch('/api/settings').then(function(r){return r.json()}).then(function(d){
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
  kejiFetch('/api/settings', {
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
  kejiFetch('/api/settings', {
    method: 'POST', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({settings:{work_corp_id:c, work_agent_id:a, work_secret:s}})
  }).then(function(){return kejiFetch('/api/work/status')})
   .then(function(r){return r.json()}).then(function(d){
    if (d.connected) { r.textContent = '✅ ' + (d.message||'连接成功'); r.style.color = '#27ae60'; }
    else { r.textContent = '❌ ' + (d.message||'连接失败'); r.style.color = '#e74c3c'; }
  }).catch(function(e){ r.textContent = '❌ ' + e.message; r.style.color = '#e74c3c'; })
   .finally(function(){ btn.disabled = false; });
}

// ================================================================
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
  kejiFetch('/api/database/configs').then(function(r){return r.json()}).then(function(data){
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
    kejiFetch('/api/database/configs/'+editId).then(function(r){return r.json()}).then(function(d){
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
  kejiFetch(url,{method:method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
  .then(function(r){return r.json()}).then(function(d){if(d.status==='ok'){closeDialog();loadDbConfigs();}else{alert('保存失败: '+(d.detail||'未知错误'));}})
  .catch(function(e){alert('请求失败: '+e.message);});
}

function deleteDbConfig(id){if(!confirm('确定删除此数据源？关联的表元数据也会被删除。'))return;kejiFetch('/api/database/configs/'+id,{method:'DELETE'}).then(function(){loadDbConfigs();}).catch(function(e){alert('删除失败: '+e.message);});}
function testDbConfig(id){var el=document.getElementById('dbMsg_'+id);if(el)el.innerHTML='<span style="color:#888">⏳ 测试中...</span>';kejiFetch('/api/database/configs/'+id+'/test',{method:'POST'}).then(function(r){return r.json()}).then(function(d){if(el)el.innerHTML='<span style="color:'+(d.status==='ok'?'green':'red')+'">'+escHtml(d.message)+'</span>';}).catch(function(e){if(el)el.innerHTML='<span style="color:red">请求失败: '+escHtml(e.message)+'</span>';});}
function scanDbConfig(id){var el=document.getElementById('dbMsg_'+id);if(el)el.innerHTML='<span style="color:#888">⏳ 扫描表结构中...</span>';kejiFetch('/api/database/configs/'+id+'/scan',{method:'POST'}).then(function(r){return r.json()}).then(function(d){if(el)el.innerHTML='<span style="color:green">✅ '+escHtml(d.message)+'</span>';}).catch(function(e){if(el)el.innerHTML='<span style="color:red">❌ 扫描失败: '+escHtml(e.message)+'</span>';});}

function showTableMeta(configId) {
  kejiFetch('/api/database/configs/'+configId+'/metadata').then(function(r){return r.json()}).then(function(d){
    var metas=d.metadata||[];if(!metas.length){alert('暂无表元数据，请先扫描');return;}
    var html='<div style="max-height:400px;overflow-y:auto"><div style="font-size:13px;font-weight:500;margin-bottom:8px;color:var(--text-secondary)">共 '+metas.length+' 个表，勾选「启用问答」即可用于智能问数</div>';
    metas.forEach(function(m){
      var cols=m.columns||[];var cn=cols.map(function(c){return c.column_name}).join(', ');
      html+='<div class="db-table-item"><div><div class="dbt-name">'+escHtml(m.table_name)+'</div><div class="dbt-info">'+(m.table_comment?escHtml(m.table_comment)+' · ':'')+cols.length+' 字段 · '+(m.row_count||'?')+' 行</div><div style="font-size:11px;color:#aaa;margin-top:2px">'+escHtml(cn.slice(0,80))+'</div></div><div class="dbt-actions"><label style="font-size:12px;display:flex;align-items:center;gap:4px;cursor:pointer"><input type="checkbox" '+(m.qa_enabled?'checked':'')+' onchange="toggleTableQa('+m.id+',this.checked)"> 问答</label></div></div>';
    });
    html+='</div>';showDialog('表管理 — 配置问答',html+'<div style="margin-top:12px"><button class="btn btn-outline" onclick="closeDialog()">关闭</button></div>');
  }).catch(function(e){alert('加载失败: '+e.message);});
}

function toggleTableQa(metaId,enabled){kejiFetch('/api/database/metadata/'+metaId,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({qa_enabled:enabled?1:0})}).then(function(r){return r.json()}).catch(function(){});}

function loadDbConfigSelect(){var sel=document.getElementById('sqConfigSelect');if(!sel)return;kejiFetch('/api/database/configs').then(function(r){return r.json()}).then(function(d){var configs=d.configs||[];sel.innerHTML='<option value="">-- 选择数据源 --</option>';configs.forEach(function(c){sel.innerHTML+='<option value="'+c.id+'">'+escHtml(c.name)+' ('+c.db_type+'/'+escHtml(c.database_name)+')</option>';});}).catch(function(){});}

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
  kejiFetch('/api/smart-query/stream', {method:'POST', headers:{'Content-Type':'application/json'},
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

// ===== Token 统计页面 =====
var _statsData = null;
var _statsSort = 'date';
var _statsFilter = 'all';
var _legendState = { prompt: true, completion: true, cached: true };

function formatNumber(n) {
  if (n === null || n === undefined) return '0';
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return n.toString();
}

function formatNumberFull(n) {
  return (n || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// ---- 时间筛选 ----
function getDateRange(range) {
  var now = new Date();
  var start = new Date(now);
  start.setHours(0,0,0,0);
  if (range === 'today') {
    return { start: start, end: now };
  } else if (range === 'week') {
    var day = now.getDay() || 7;
    start.setDate(now.getDate() - day + 1);
    return { start: start, end: now };
  } else if (range === 'month') {
    start.setDate(1);
    return { start: start, end: now };
  }
  return { start: new Date(0), end: now };
}

function filterByRange(convs, range) {
  if (range === 'all' || !convs) return convs || [];
  var r = getDateRange(range);
  return convs.filter(function(c){
    if (!c.date) return false;
    var d = new Date(c.date);
    return d >= r.start && d <= r.end;
  });
}

function setStatsFilter(range) {
  _statsFilter = range;
  document.querySelectorAll('#statsFilter .filter-btn').forEach(function(b){
    b.classList.toggle('active', b.dataset.range === range);
  });
  if (_statsData) renderAll();
}

// ---- 加载与渲染 ----
function loadStats() {
  kejiFetch('/api/stats/tokens').then(function(r){return r.json()}).then(function(d){
    _statsData = d;
    renderAll();
  }).catch(function(){
    document.getElementById('statsTableBody').innerHTML = '';
    document.getElementById('statsEmpty').style.display = 'block';
  });
}

function loadToolPage() {
  kejiFetch('/api/stats/tools?days=30').then(function(r){return r.json()}).then(function(d){
    renderToolPage(d);
  }).catch(function(){});
}

function renderToolPage(data) {
  if (!data || !data.totals) return;
  var t = data.totals;
  var g = function(id){ return document.getElementById(id); };

  g('tsNumCalls').textContent = formatNumber(t.total_calls || 0);
  g('tsNumSuccess').textContent = formatNumber(t.success_count || 0);
  g('tsNumErrors').textContent = formatNumber(t.error_count || 0);

  var totalTokens = (t.total_prompt || 0) + (t.total_completion || 0);
  g('tsNumTokens').textContent = formatNumber(totalTokens);

  var cost = t.total_cost || 0;
  g('tsNumTotalCost').textContent = cost < 0.01 && cost > 0 ? '< \u00a50.01' : '\u00a5' + cost.toFixed(4);

  var tbody = document.getElementById('toolsTableBody');
  var empty = document.getElementById('toolsEmpty');
  var tools = data.by_tool || [];
  if (!tools.length) { tbody.innerHTML = ''; if (empty) empty.style.display = 'block'; return; }
  if (empty) empty.style.display = 'none';

  var html = '';
  for (var i = 0; i < tools.length; i++) {
    var t2 = tools[i];
    var tc = t2.total_cost || 0;
    var costStr = tc < 0.01 && tc > 0 ? '<\u00a50.01' : '\u00a5' + tc.toFixed(4);
    html += '<tr><td>' + (i + 1) + '</td>' +
      '<td>' + (t2.tool_name || '-') + '</td>' +
      '<td class="num">' + formatNumber(t2.call_count || 0) + '</td>' +
      '<td class="num" style="color:var(--success)">' + formatNumber(t2.success_count || 0) + '</td>' +
      '<td class="num" style="color:var(--danger)">' + formatNumber(t2.error_count || 0) + '</td>' +
      '<td class="num">' + formatNumber(t2.avg_duration_ms || 0) + '</td>' +
      '<td class="num">' + formatNumber(t2.total_prompt || 0) + '</td>' +
      '<td class="num">' + formatNumber(t2.total_completion || 0) + '</td>' +
      '<td class="num">' + formatNumber(t2.total_cached || 0) + '</td>' +
      '<td class="num">' + costStr + '</td></tr>';
  }
  tbody.innerHTML = html;
  var p = document.getElementById('toolsStatsPeriod');
  if (p) p.textContent = '(近30天)';
}

function renderAll() {
  if (!_statsData) return;
  var filtered = filterByRange(_statsData.conversations, _statsFilter);
  var total = { conversations: filtered.length, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, cached_tokens: 0, cost: 0 };
  for (var i = 0; i < filtered.length; i++) {
    var c = filtered[i];
    total.prompt_tokens += c.prompt_tokens || 0;
    total.completion_tokens += c.completion_tokens || 0;
    total.total_tokens += c.total_tokens || 0;
    total.cached_tokens += c.cached_tokens || 0;
    total.cost += c.cost || 0;
  }
  renderStatsSummary(total);
  drawDonutChart(total);
  renderStatsTable(filtered);
}

// ---- 统计卡片 ----
function renderStatsSummary(total) {
  var idMap = { convs: 'sNumConvs', total: 'sNumTotal', prompt: 'sNumPrompt', completion: 'sNumCompletion', cached: 'sNumCached', cost: 'sNumCost' };
  var valMap = { convs: total.conversations, total: total.total_tokens, prompt: total.prompt_tokens, completion: total.completion_tokens, cached: total.cached_tokens, cost: total.cost };
  var cards = document.querySelectorAll('#statsSummary .s-card');
  var isLocal = _statsData && _statsData.is_local;
  var modelName = (_statsData && _statsData.model) || '';

  for (var i = 0; i < cards.length; i++) {
    var key = cards[i].dataset.key;
    var el = document.getElementById(idMap[key]);
    if (!el) continue;
    if (key === 'cost') {
      if (isLocal) {
        el.textContent = '免费';
      } else if (valMap[key] < 0.01 && valMap[key] > 0) {
        el.textContent = '< \u00a50.01';
      } else {
        el.textContent = '\u00a5' + valMap[key].toFixed(2);
      }
    } else {
      el.textContent = formatNumber(valMap[key]);
    }
    if (key === 'cached') cards[i].style.display = valMap[key] > 0 ? '' : 'none';
  }

  var hint = document.getElementById('sCostModelHint');
  if (hint) {
    hint.textContent = isLocal ? '(本地免费)' : '(' + modelName + ')';
  }
}

// ---- Canvas 3D 扇形图 + Hover 交互 ----
var _donutColors = { prompt: '#7c4dff', completion: '#00c853', cached: '#00bcd4' };

function drawDonutChart(total, hoverIdx) {
  var canvas = document.getElementById('donutChart');
  if (!canvas) return;
  // 未传 hoverIdx 时从 canvas 缓存读取（兼容 renderAll 无参调用）
  if (hoverIdx === undefined) hoverIdx = canvas._hoverIdx != null ? canvas._hoverIdx : -1;
  var ctx = canvas.getContext('2d');
  var W = canvas.width, H = canvas.height;
  var cx = W / 2, cy = H / 2;

  // 首次绘制：固定尺寸 + 绑定鼠标事件
  if (!canvas._sized) {
    canvas._sized = true;
    canvas.width = 280;
    canvas.height = 280;
    canvas.addEventListener('mousemove', onDonutHover);
    canvas.addEventListener('mouseleave', onDonutLeave);
  }

  var outerR = 110, innerR = 70;

  // 根据图例状态构建可见扇区
  var segs = [];
  if (_legendState.prompt && total.prompt_tokens > 0)
    segs.push({ key:'prompt', val:total.prompt_tokens, color:_donutColors.prompt, label:'输入令牌' });
  if (_legendState.completion && total.completion_tokens > 0)
    segs.push({ key:'completion', val:total.completion_tokens, color:_donutColors.completion, label:'输出令牌' });
  if (_legendState.cached && total.cached_tokens > 0)
    segs.push({ key:'cached', val:total.cached_tokens, color:_donutColors.cached, label:'缓存命中' });

  var totalVal = segs.reduce(function(s, s2){ return s + s2.val; }, 0);
  ctx.clearRect(0, 0, W, H);

  if (totalVal === 0) {
    ctx.beginPath();
    ctx.arc(cx, cy, outerR, 0, Math.PI * 2);
    ctx.arc(cx, cy, innerR, 0, Math.PI * 2, true);
    ctx.closePath();
    ctx.fillStyle = '#eee';
    ctx.fill();
    document.getElementById('donutTotal').textContent = '0';
    canvas._segData = [];
    return;
  }

  // ── 1. 整环投影（浮空效果） ──
  ctx.save();
  ctx.shadowColor = 'rgba(0,0,0,0.10)';
  ctx.shadowBlur = 14;
  ctx.shadowOffsetX = 0;
  ctx.shadowOffsetY = 5;
  ctx.beginPath();
  ctx.arc(cx, cy + 2, outerR, 0, Math.PI * 2);
  ctx.arc(cx, cy + 2, innerR, 0, Math.PI * 2, true);
  ctx.closePath();
  ctx.fillStyle = 'rgba(0,0,0,0.25)';
  ctx.fill();
  ctx.restore();

  // ── 2. 绘制各个扇区（hover 放大 + 丝滑动画） ──
  var segData = [];
  var startAngle = -Math.PI / 2;

  // 单值展开量：_currentExpand 由动画引擎驱动，始终平滑过渡
  var expandAmt = canvas._currentExpand || 0;
  var actualHover = canvas._hoverIdx != null ? canvas._hoverIdx : hoverIdx;

  for (var i = 0; i < segs.length; i++) {
    var angle = (segs[i].val / totalVal) * Math.PI * 2;
    var isHover = (i === actualHover);
    var expand = isHover ? expandAmt : 0;
    var segOuter = outerR + expand;
    var segInner = innerR - expand * 0.6;   // 内圈缩得少一点，视觉更平衡

    ctx.beginPath();
    ctx.arc(cx, cy, segOuter, startAngle, startAngle + angle);
    ctx.arc(cx, cy, segInner, startAngle + angle, startAngle, true);
    ctx.closePath();
    ctx.fillStyle = segs[i].color;
    ctx.fill();

    // 记录扇区数据（标准化角度，0 = 正上方顺时针）
    var normStart = startAngle + Math.PI / 2;
    if (normStart < 0) normStart += Math.PI * 2;
    var normEnd = startAngle + angle + Math.PI / 2;
    if (normEnd < 0) normEnd += Math.PI * 2;
    segData.push({
      start: normStart, end: normEnd,
      key: segs[i].key, label: segs[i].label,
      val: segs[i].val, color: segs[i].color
    });

    startAngle += angle;
  }

  // 缓存供 hover 检测
  canvas._segData = segData;
  canvas._totalVal = totalVal;
  canvas._cx = cx; canvas._cy = cy;
  canvas._outerR = outerR; canvas._innerR = innerR;
  canvas._hoverIdx = hoverIdx != null ? hoverIdx : -1;

  // 更新中心文字 & 图例
  document.getElementById('donutTotal').textContent = formatNumber(totalVal);
  document.getElementById('legendPrompt').textContent = formatNumberFull(total.prompt_tokens);
  document.getElementById('legendCompletion').textContent = formatNumberFull(total.completion_tokens);
  document.getElementById('legendCached').textContent = formatNumberFull(total.cached_tokens);
}

// ── 放大动画引擎（lerp 到目标值，极其简单） ──
var _donutAnimId = null;

function _startDonutAnim(canvas, targetIdx) {
  if (_donutAnimId) { cancelAnimationFrame(_donutAnimId); _donutAnimId = null; }
  if (canvas._animTarget === targetIdx) return;
  if (canvas._currentExpand == null) canvas._currentExpand = 0;

  canvas._animTarget = targetIdx;
  canvas._animStart = performance.now();
  _donutTick(canvas);
}

function _donutTick(canvas) {
  var elapsed = performance.now() - canvas._animStart;
  var t = Math.min(1, elapsed / 180);
  var e = 1 - Math.pow(1 - t, 3); // ease-out cubic

  var targetVal = canvas._animTarget >= 0 ? 6 : 0;
  canvas._currentExpand += (targetVal - canvas._currentExpand) * e;

  // hoverIdx 在出口动画期间保留指向退出的扇区，动画结束后才清
  if (canvas._animTarget >= 0) {
    canvas._hoverIdx = canvas._animTarget;
  } else if (t >= 1) {
    canvas._hoverIdx = -1;
  }
  // 出口动画中(t<1)：保留 canvas._hoverIdx 不变（指向退出前的扇区）

  renderAll();

  if (t < 1) {
    _donutAnimId = requestAnimationFrame(function(){ _donutTick(canvas); });
  } else {
    _donutAnimId = null;
    canvas._currentExpand = targetVal;
  }
}

// ── hover 检测 ──
function onDonutHover(e) {
  var c = e.target;
  var rect = c.getBoundingClientRect();
  var mx = e.clientX - rect.left;
  var my = e.clientY - rect.top;

  var cx = c._cx || 140, cy = c._cy || 140;
  var outerR = c._outerR || 110, innerR = c._innerR || 70;
  var segData = c._segData || [];

  var dx = mx - cx, dy = my - cy;
  var dist = Math.sqrt(dx * dx + dy * dy);

  // 不在圆环内 → 启动出口动画（不碰 _hoverIdx，动画引擎自己会管）
  if (dist < innerR || dist > outerR || !segData.length) {
    if (c._animTarget === -1) return;
    _hideDonutTip();
    _startDonutAnim(c, -1);
    return;
  }

  // 计算标准化角度（0 = 正上方，顺时针）
  var angle = Math.atan2(dy, dx) + Math.PI / 2;
  if (angle < 0) angle += Math.PI * 2;

  // 查找命中的扇区
  var found = -1;
  for (var i = 0; i < segData.length; i++) {
    var s = segData[i], st = s.start, en = s.end;
    if (st <= en) { if (angle >= st && angle < en) found = i; }
    else { if (angle >= st || angle < en) found = i; }
  }

  if (found === -1) {
    if (c._animTarget !== -1) { _hideDonutTip(); _startDonutAnim(c, -1); }
    return;
  }

  // 扇区切换 → 启动动画
  if (c._animTarget !== found) {
    _startDonutAnim(c, found);
  }

  // ── 显示 tooltip ──（同上）
  var seg = segData[found];
  var tip = document.getElementById('donutTooltip');
  if (!tip) {
    tip = document.createElement('div');
    tip.id = 'donutTooltip';
    tip.style.cssText =
      'position:fixed;z-index:999;background:#1a1f2e;color:#fff;' +
      'padding:12px 16px;border-radius:10px;font-size:13px;' +
      'line-height:1.6;box-shadow:0 6px 24px rgba(0,0,0,0.3);' +
      'pointer-events:none;font-family:-apple-system,"Microsoft YaHei",sans-serif;' +
      'min-width:140px;border:1px solid rgba(255,255,255,0.08)';
    document.body.appendChild(tip);
  }
  var pct = ((seg.val / c._totalVal) * 100).toFixed(1);
  tip.innerHTML =
    '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">' +
      '<span style="width:10px;height:10px;border-radius:50%;background:' + seg.color + ';flex-shrink:0"></span>' +
      '<span style="font-weight:600;font-size:14px">' + seg.label + '</span>' +
    '</div>' +
    '<div style="display:flex;justify-content:space-between;gap:24px;padding-left:18px">' +
      '<span style="color:rgba(255,255,255,0.5)">Tokens</span>' +
      '<span style="font-weight:700;font-variant-numeric:tabular-nums">' + _formatNumberFull(seg.val) + '</span>' +
    '</div>' +
    '<div style="display:flex;justify-content:space-between;gap:24px;padding-left:18px">' +
      '<span style="color:rgba(255,255,255,0.5)">占比</span>' +
      '<span style="font-weight:600">' + pct + '%</span>' +
    '</div>';
  tip.style.display = 'block';

  // tooltip 定位（不超出视口）
  var tx = e.clientX + 16, ty = e.clientY - 12;
  var tw = 160, th = 90;
  if (tx + tw > window.innerWidth) tx = e.clientX - tw - 10;
  if (ty < 8) ty = 8;
  if (ty + th > window.innerHeight - 8) ty = window.innerHeight - th - 8;
  tip.style.left = tx + 'px';
  tip.style.top = ty + 'px';
}

function onDonutLeave(e) {
  var c = e.target;
  if (c._animTarget === -1) return;
  _hideDonutTip();
  _startDonutAnim(c, -1);
}

function _hideDonutTip() {
  var tip = document.getElementById('donutTooltip');
  if (tip) tip.style.display = 'none';
}

// 带千分位的数字格式化（避免与全局 formatNumberFull 冲突）
function _formatNumberFull(n) {
  return (n || 0).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',');
}

// ---- 图例点击切换 ----
function toggleLegend(key) {
  _legendState[key] = !_legendState[key];
  var item = document.querySelector('.legend-item[data-key="'+key+'"]');
  if (item) item.classList.toggle('hidden', !_legendState[key]);
  if (_statsData) renderAll();
}

document.addEventListener('click', function(e){
  var item = e.target.closest('.legend-item');
  if (item) {
    var key = item.dataset.key;
    if (key) toggleLegend(key);
  }
});

// ---- 统计表格 ----
function renderStatsTable(convs) {
  var tbody = document.getElementById('statsTableBody');
  var empty = document.getElementById('statsEmpty');
  if (!convs || !convs.length) {
    tbody.innerHTML = '';
    empty.style.display = 'block';
    return;
  }
  empty.style.display = 'none';

  var sorted = convs.slice();
  if (_statsSort === 'date') {
    sorted.sort(function(a, b){ return (b.date || '') > (a.date || '') ? 1 : -1; });
  } else if (_statsSort === 'tokens') {
    sorted.sort(function(a, b){ return (b.total_tokens || 0) - (a.total_tokens || 0); });
  } else if (_statsSort === 'cost') {
    sorted.sort(function(a, b){ return (b.cost || 0) - (a.cost || 0); });
  }

  var isLocal = _statsData && _statsData.is_local;

  var html = '';
  for (var i = 0; i < sorted.length; i++) {
    var c = sorted[i];
    var title = (c.title || '新对话').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    var dateStr = (c.date || '').slice(0, 16).replace('T', ' ');
    var costStr = '';
    if (isLocal) {
      costStr = '免费';
    } else if (c.cost == null || c.cost === 0) {
      costStr = '¥0';
    } else if (c.cost < 0.01) {
      costStr = '< ¥0.01';
    } else {
      costStr = '¥' + c.cost.toFixed(2);
    }
    html += '<tr onclick="loadConversation(\'' + c.id + '\')">'
      + '<td>' + (i + 1) + '</td>'
      + '<td class="conv-title" title="' + title + '">' + title + '</td>'
      + '<td>' + dateStr + '</td>'
      + '<td class="num">' + formatNumberFull(c.prompt_tokens) + '</td>'
      + '<td class="num">' + formatNumberFull(c.completion_tokens) + '</td>'
      + '<td class="num">' + (c.cached_tokens ? formatNumberFull(c.cached_tokens) : '-') + '</td>'
      + '<td class="num"><strong>' + formatNumberFull(c.total_tokens) + '</strong></td>'
      + '<td class="num">' + costStr + '</td>'
      + '<td class="num">' + c.message_count + '</td>'
      + '</tr>';
  }
  tbody.innerHTML = html;
}

function sortStatsTable(by) {
  _statsSort = by;
  document.querySelectorAll('.stats-sort-btn').forEach(function(b){
    b.classList.toggle('active', b.dataset.sort === by);
  });
  if (_statsData) renderAll();
}
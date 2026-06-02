// MCP 外部工具管理
function refreshMCPStatus() {
  fetch('/api/mcp/status').then(function(r){return r.json()}).then(function(d){
    var el = document.getElementById('mcpServerList');
    if (!el) return;
    var a = d.connected || [];
    if (a.length === 0) {
      el.innerHTML = '<span style="color:#999">未连接 MCP 服务器</span>';
    } else {
      var h = '';
      a.forEach(function(n){ h += '<div style="padding:4px 0;font-size:13px">✅ ' + n + '</div>'; });
      el.innerHTML = h;
    }
  });
}
function showMCPHelp() {
  var t = 'MCP - Model Context Protocol\n\n';
  t += '配置方式：编辑 config.yaml 的 mcp_servers 一节\n';
  t += '或在项目根目录的 config.yaml 中添加\n\n';
  t += '示例：\nmcp_servers:\n  filesystem:\n    command: npx\n    args: ["-y", "@modelcontextprotocol/server-filesystem", "D:/"]\n\n';
  t += '配置后重启服务生效。';
  alert(t);
}
setTimeout(refreshMCPStatus, 2000);

# 技能面板 Bug 排查与修复记录

## 现象
技能面板打开后存在三个问题：
1. **激活/卸载按钮点了没反应** — 点击"激活"或"卸载"按钮无任何 Toast 提示，视觉上像没点一样
2. **技能激活后在对话中无效** — 面板显示"已激活"，但模型行为完全没变化
3. **技能描述全英文** — 卡片展示的说明文字全部是 Claude Code 英文原版，不符合中文企业工具定位

---

## Bug 1：toast() 函数被空函数覆盖（前端 → 致命）

### 定位
- **文件**：[web/js/chat.js:632](web/js/chat.js#L632)
- **根因**：chat.js 中残留了一个空的 `toast()` 函数：
  ```js
  function toast(msg, type = 'info') {
    const c = document.getElementById('toastContainer');
  }
  ```
  由于 chat.js 在 core.js **之后**加载，后定义的函数覆盖了 [web/js/core.js:263](web/js/core.js#L263) 中完整的 toast 实现。

### 影响
所有通过 toast 反馈的操作全部静默失效：
- 技能激活/卸载 → 无反馈
- 上传文件失败 → 无提示
- 知识库操作 → 无通知
- 设置保存 → 无确认

### 修复
删除了 chat.js 中的空函数，让 core.js 的实现生效。

---

## Bug 2：双 KejiAdapter 实例（后端 → 致命）

### 定位
系统存在**两个独立的 KejiAdapter 实例**：

| 位置 | 全局变量 | 负责接口 |
|---|---|---|
| [main.py:22](main.py#L22) `get_adapter()` | `main._adapter_instance` | `/chat/stream` 等对话接口 |
| [nanobot/adapter.py:598](nanobot/adapter.py#L598) `get_adapter()` | `nanobot.adapter.adapter` | 被 [core/routes.py:1182](core/routes.py#L1182) 调用 |

### 调用链路
```
技能激活 → POST /api/skills/activate → routes.py._get_adapter()
  → nanobot.adapter.get_adapter() → 实例 B._active_skills += skill  ✅

用户发送消息 → POST /chat/stream → main.py.get_adapter()
  → main._adapter_instance（实例 A）→ _build_msgs() 读实例 A._active_skills
  → 空列表 → 技能不生效 ❌
```

### 影响
技能面板的"激活/卸载"操作保存到了实例 B，但对话使用实例 A。技能看似激活成功（API 返回 `status: ok`），实际对话中模型完全没有收到技能指令。

### 修复
[main.py:19](main.py#L19) 的 `get_adapter()` 改为委托 `nanobot.adapter.get_adapter()`，全系统共用单例。

---

## Bug 3：技能描述全英文（内容）

### 定位
`skills/` 目录下 18 个 SKILL.md 全部从 Claude Code 复制，name 和 description 均为英文。

### 影响
技能面板卡片展示英文名称和说明，与软件的中文定位不匹配。

### 修复
翻译全部 18 个 SKILL.md 的 description 字段为中文。name 保持英文 ID 不变（兼容 `/use 技能名` 命令）。

### 变更的技能列表
algorithmic-art、brand-guidelines、canvas-design、claude-api、deck、doc-coauthoring、docx、frontend-design、internal-comms、mcp-builder、pdf、pptx、skill-creator、slack-gif-creator、theme-factory、web-artifacts-builder、webapp-testing、xlsx

---

## 附加改进：技能变更通知模型

### 问题
技能激活/卸载后，模型对此一无所知。

### 修复
在 [nanobot/adapter.py:512](nanobot/adapter.py#L512) `_build_msgs()` 中增加技能状态变更检测：

1. 每次构建消息时，对比当前激活的技能集合 `skill_set` 与上次已通知的集合 `_skill_notified`
2. 检测到差异后，注入一条 system 消息告知模型变更内容：
   - `用户已激活技能：「docx」、「pdf」`
   - `用户已卸载技能：「algorithmic-art」`
3. 更新 `_skill_notified` 记录，避免重复通知
4. 通知仅在技能状态变化后的**第一次对话**触发

---

## 变更文件清单

| 文件 | 变更类型 | 说明 |
|---|---|---|
| [web/js/chat.js](web/js/chat.js) | 删除 | 移除空 `toast()` 函数 |
| [main.py](main.py) | 修改 | `get_adapter()` 委托 nanobot 单例 |
| [nanobot/adapter.py](nanobot/adapter.py) | 修改 | 增加 `_skill_notified` 和装袋-检测逻辑 |
| [skills/*/SKILL.md](skills/) | 修改 | 18 个技能描述翻译为中文 |

# 第三方组件与致谢

本仓库在 [MIT License](../LICENSE) 下发布**科吉（Keji）自有部分**（如 `core/`、`web/`、`main.py`、多用户与工作区等）。

以下组件为独立开源项目或附带单独许可，使用时请遵守各自条款。科吉对上游项目表示感谢。

---

## 1. nanobot（Agent 引擎，核心依赖）

| 项目 | 说明 |
|------|------|
| **上游仓库** | https://github.com/HKUDS/nanobot |
| **许可** | [MIT License](../nanobot/LICENSE) |
| **版权** | Copyright (c) 2025 nanobot contributors |
| **本仓库位置** | `nanobot/` 目录（含 Agent 运行时、工具、Provider、会话等） |

科吉在 nanobot 之上增加了 Web 界面、多用户鉴权、团队工作区、权限控制与企业部署脚本等。**Agent 核心能力来自 HKUDS 团队的 nanobot 项目**，并非科吉原创。

本仓库内 `nanobot/` 基于上游代码集成并做了适配（如 `nanobot/adapter.py`）。若你分发本仓库，请保留 `nanobot/LICENSE` 及本文件中的署名说明。

---

## 2. quack-mcp（MCP 服务，可选）

| 项目 | 说明 |
|------|------|
| **上游** | `mcp/quack-mcp-main/` |
| **许可** | [MIT License](../mcp/quack-mcp-main/LICENSE.md) |
| **本仓库位置** | `mcp/quack-mcp-main/` |

用于 DuckDB 等 MCP 能力，按需启用。

---

## 3. skills/（技能模板，可选）

`skills/` 下各子目录为 bundled 技能示例/模板，**各自目录内可能有独立 `LICENSE.txt`**，常见来源包括 Anthropic 官方 Skills 等。

- 使用前请阅读对应子目录下的许可证文件。
- Anthropic Skills 通常受 Anthropic 服务条款约束，**不得用于训练竞争模型等**（详见各 `LICENSE.txt`）。

---

## 4. Python / Node 运行时依赖

通过 `requirements.txt` 及部署脚本安装的包（如 FastAPI、uvicorn、chromadb、torch 等）由 PyPI / npm 上游各自许可。

完整依赖列表见 `requirements.txt` 与 `offline_packages/`。分发商用产品时，请自行核对各依赖许可证是否满足你的场景。

---

## 5. 模型与 API 服务

科吉通过配置连接 **DeepSeek、OpenAI、Anthropic** 等第三方 API。这些服务的使用受各平台**服务条款与计费政策**约束，与本仓库 MIT 许可无关。

---

## 致谢摘要

- **[HKUDS/nanobot](https://github.com/HKUDS/nanobot)** — 轻量级 Agent 框架，科吉的对话与工具引擎建立在其之上。
- 其他开源依赖与技能作者 — 见各目录 LICENSE 文件。

如有遗漏或需更正，欢迎提 Issue。

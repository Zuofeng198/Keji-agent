# 科吉 Agent

基于 FastAPI + nanobot 的本地/局域网 AI 助手：Web 对话、多用户登录、团队文件工作区、工具与 MCP 扩展。

## 功能概览

- **对话**：流式聊天，按用户隔离会话与历史
- **账号**：JWT 登录；角色 `admin` / `member` / `readonly`（工具与路径权限不同）
- **团队文件**：`data/workspace/shared/` 共享目录，`data/workspace/users/<用户ID>/` 个人目录
- **管理**：管理员可管理用户、查看会话
- **工具**：文档、表格、知识库、代码执行、MCP（DuckDB/文件系统等，需 Node）

## 环境要求

| 组件 | 要求 |
|------|------|
| 系统 | Windows 10/11（64 位） |
| Python | **3.10 或 3.11、3.12**（64 位）均可运行源码 |
| 离线 wheel | **必须与打 wheel 时的 Python 主版本一致**（见下） |
| Node.js | 可选 18+，完整 MCP 建议安装 |

### 关于 Python 3.10 / 3.12

- 从 GitHub **在线部署**：`setup_deploy.bat` 会用你本机已装的 Python（3.10～3.12 均可）联网安装依赖。
- **离线 wheel 包**（`offline_packages/pip_wheels`）是按 **打包容器的 Python 版本**编译的。当前若用开发机 `venv` 为 **3.10** 打的包，在 **3.12** 上不能混用，需在 **3.12** 下重新执行 `package_wheels.bat`，或目标机不用离线包、改在线安装。

## 快速开始（Windows）

### 1. 获取代码

```powershell
git clone <你的仓库地址>
cd 科吉agent
```

### 2. 一键部署

双击 **`setup_deploy.bat`**（或 `一键部署.bat`）。

或在 PowerShell 中：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
```

### 3. 配置密钥

```powershell
copy config.example.yaml config.yaml
copy .env.example .env
```

编辑 **`.env`**，至少填写：

```env
DEEPSEEK_API_KEY=你的DeepSeek密钥
KEJI_ADMIN_PASSWORD=首次管理员密码
```

（`KEJI_JWT_SECRET` 部署脚本可自动生成。）

### 4. 启动

| 脚本 | 说明 |
|------|------|
| `launch_keji.bat` | 后台启动 + 打开 http://127.0.0.1:8000/ |
| `run_server.bat` | 黑窗运行，便于看日志 |

局域网访问：`http://<服务器IP>:8000/`（服务默认 `0.0.0.0:8000`）。

### 5. 停止服务

- 黑窗模式：`Ctrl+C`
- 后台模式：任务管理器结束 `pythonw.exe`，或见 `docs/新机部署.md`

## 离线部署（可选）

在**能正常跑起来的一台机器**上：

```text
package_wheels.bat   → 生成 offline_packages/pip_wheels
```

将整个项目（含 `offline_packages`）拷到目标机，再运行 `setup_deploy.bat`。  
详见 [docs/离线部署.md](docs/离线部署.md)。

> 离线包体积大（约 400MB），**未纳入 Git 仓库**；请本地打包或 U 盘拷贝。

## 配置说明

- **`config.yaml`**：模型、MCP、安全策略（勿提交到 Git）
- **`.env`**：API Key、JWT、管理员密码（勿提交到 Git）
- **`config.example.yaml` / `.env.example`**：模板

首次启动会用 `bootstrap_admin` 创建管理员（见 `config.yaml` 中 `security.bootstrap_admin`）。

## 项目结构（简要）

```text
core/           业务 API、用户、工作区、权限
nanobot/        Agent 引擎适配
web/            前端静态页
main.py         服务入口
scripts/        deploy.ps1、package_offline.ps1
docs/           部署与排错文档
```

## 文档

- [新机部署](docs/新机部署.md)
- [离线部署](docs/离线部署.md)
- [项目目录说明](docs/项目目录说明.md)

## 仓库未包含（需本地生成）

- `venv/`、`node_modules/`
- `config.yaml`、`.env`
- `data/`、`logs/`、`offline_packages/`

## 许可证

请根据你方实际情况补充 LICENSE。

"""科吉 AI 助手 - 基于 nanobot 引擎的 FastAPI 服务"""

from __future__ import annotations

import os
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger
from pydantic import BaseModel, Field

from core.routes import router as api_router
from core.routes_auth import router as auth_router
from core.routes_admin import router as admin_router
from core.routes_security import router as security_router
from core.security.auth import APIKeyMiddleware, get_security_settings
from core.security.context import clear_request_context, set_request_context
from core.security.users import bootstrap_admin_if_needed
from core.security.chat_session import resolve_chat_ids
from core.wechat.work_bridge import router as work_router

async def get_adapter():
    """全系统共享同一个 KejiAdapter 实例（委托给 nanobot.adapter 模块的单例）"""
    from nanobot.adapter import get_adapter as _get_nanobot_adapter
    return await _get_nanobot_adapter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    sec = get_security_settings(reload=True)
    bootstrap_admin_if_needed()
    try:
        from core.workspace import ensure_layout

        from core.database.db import get_db
        from core.workspace import ensure_user_dir

        ws = ensure_layout()
        for row in get_db().list_users():
            ensure_user_dir(row["id"])
        logger.info("团队文件工作区: {}", ws)
    except Exception as e:
        logger.warning("初始化文件工作区失败: {}", e)
    if sec.enabled:
        logger.info(
            "鉴权已启用 mode={} localhost_skip={}",
            sec.auth_mode,
            sec.allow_localhost_without_auth,
        )
    else:
        logger.warning("API 鉴权未启用：请在 config.yaml 的 security 段配置")
    adapter = await get_adapter()
    # 启动飞书桥接层（如果配置了飞书渠道）
    await adapter.start_feishu_bridge()
    logger.info("科吉 AI 助手启动完成（nanobot 引擎）")
    yield
    # 关闭飞书桥接层
    await adapter.stop_feishu_bridge()


app = FastAPI(title="科吉 AI 助手", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(APIKeyMiddleware)
app.include_router(api_router)
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(security_router)
app.include_router(work_router)


static_dir = os.path.join(os.path.dirname(__file__), "web")
if os.path.isdir(static_dir):
    from fastapi.staticfiles import StaticFiles
    app.mount("/static", StaticFiles(directory=static_dir, check_dir=False), name="static")


# ── 请求模型 ──

class ChatRequest(BaseModel):
    query: str = Field(..., min_length=1, description="用户输入")
    session_id: str = Field(default="", description="会话ID")
    conversation_id: str = Field(default="", description="对话ID")
    files: list[str] = Field(default=[], description="已上传文件路径")


class ResetRequest(BaseModel):
    session_id: str = Field(default="", description="会话ID")


# ── 前端页面 ──

_cache_buster: str = ""

def _get_cache_buster() -> str:
    global _cache_buster
    if not _cache_buster:
        import time
        _cache_buster = str(int(time.time() * 1000))
    return _cache_buster


def get_html() -> str:
    html_path = os.path.join(os.path.dirname(__file__), "web", "index.html")
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "<h1>前端页面未找到</h1>"


@app.get("/", response_class=HTMLResponse)
def home():
    from starlette.responses import Response
    content = get_html().replace("v=VERSION", "v=" + _get_cache_buster())
    return Response(content=content, media_type="text/html",
                    headers={"Cache-Control": "no-cache, no-store, must-revalidate",
                             "Pragma": "no-cache", "Expires": "0"})


# ── 对话接口 ──

@app.post("/chat")
async def chat(req: ChatRequest, request: Request):
    adapter = await get_adapter()
    sid, conv_id, user = resolve_chat_ids(
        request, session_id=req.session_id, conversation_id=req.conversation_id
    )
    set_request_context(
        session_id=sid,
        client_ip=request.client.host if request.client else "",
        actor=user.username if user else "api",
        user_id=user.id if user else "",
        role=user.role if user else "",
    )
    reply = await adapter.chat(query=req.query, sid=sid, files=req.files or None)
    return {"reply": reply, "session_id": sid, "conversation_id": conv_id}


@app.post("/chat/stream")
async def chat_stream(req: ChatRequest, request: Request):
    adapter = await get_adapter()
    sid, conv_id, user = resolve_chat_ids(
        request, session_id=req.session_id, conversation_id=req.conversation_id
    )
    set_request_context(
        session_id=sid,
        client_ip=request.client.host if request.client else "",
        actor=user.username if user else "api",
        user_id=user.id if user else "",
        role=user.role if user else "",
    )

    async def generate():
        async for event_str in adapter.chat_stream(query=req.query, sid=sid, files=req.files or None):
            yield f"data: {event_str}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"X-Session-Id": sid, "X-Conversation-Id": conv_id},
    )


@app.post("/chat/stop")
async def stop_chat(session_id: str = "", conversation_id: str = ""):
    adapter = await get_adapter()
    sid = conversation_id or session_id
    triggered = adapter.cancel_chat(sid)
    if triggered:
        return {"status": "ok", "message": "已中断对话", "session_id": sid}
    return {"status": "warning", "message": "未找到正在执行的对话", "session_id": sid}


@app.post("/chat/reset")
async def reset_chat(req: ResetRequest):
    adapter = await get_adapter()
    await adapter.reset_session(req.session_id)
    return {"status": "ok", "message": "会话已重置"}


# ── 工具列表 ──

@app.get("/tools")
async def list_tools(session_id: str = ""):
    _TOOL_CATS = {
        "exec": "utility", "read_file": "io", "write_file": "io", "edit_file": "io",
        "list_dir": "filesystem", "glob": "filesystem", "grep": "filesystem",
        "web_search": "web", "web_fetch": "web",
        "get_time": "utility", "calculator": "utility", "web_search": "web",
        "create_document": "office", "create_table": "office", "create_presentation": "office",
        "delete_file": "filesystem", "read_document": "filesystem",
        "analyze_data": "data", "knowledge_stats": "knowledge",
        "query_knowledge": "knowledge", "index_knowledge": "knowledge",
        "ocr_image": "utility", "ocr_pdf": "utility",
        "parse_email": "utility",
        "organize_files": "filesystem", "rename_files": "filesystem", "deduplicate_files": "filesystem",
        "run_code": "utility",
        "db_connect": "data", "db_list_tables": "data", "db_describe_table": "data",
        "db_execute_query": "data", "db_test_connection": "data", "db_disconnect": "data",
    }
    adapter = await get_adapter()
    tools_info = []
    # 显示全量工具（含懒加载隐藏的）
    full = adapter.tools._tools
    for name, tool in full.items():
        tools_info.append({
            "name": name,
            "description": tool.description,
            "parameters": tool.parameters,
            "category": _TOOL_CATS.get(name, "general"),
        })
    return {"tools": tools_info}


# ── 会话统计 ──

@app.get("/sessions")
async def get_sessions():
    adapter = await get_adapter()
    sessions_info = []
    for key, session in adapter.session_manager._cache.items():
        sessions_info.append({
            "id": key,
            "messages": len(session.messages),
            "created_at": str(session.created_at),
            "updated_at": str(session.updated_at),
        })
    return {"total_sessions": len(sessions_info), "sessions": sessions_info}


# ── 健康检查 ──

@app.get("/favicon.ico")
async def favicon():
    from fastapi.responses import Response
    return Response(status_code=204)


@app.get("/chat/mode")
async def chat_mode(session_id: str = ""):
    return {"session_id": session_id, "mode": "react"}


@app.get("/health")
async def health():
    return {"status": "healthy", "engine": "nanobot"}


if __name__ == "__main__":
    import uvicorn
    try:
        print("🚀 科吉 AI 助手启动中...")
        print("🌐 访问地址: http://127.0.0.1:8000 （局域网请用本机 IP）")
    except UnicodeEncodeError:
        print("科吉 AI 助手启动中...")
        print("访问地址: http://127.0.0.1:8000")
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    host = os.environ.get("KEJI_HOST", "0.0.0.0")
    port = int(os.environ.get("KEJI_PORT", "8000"))
    try:
        print(f"🌐 本机: http://127.0.0.1:{port}  局域网: http://<本机IP>:{port}")
    except UnicodeEncodeError:
        print(f"本机: http://127.0.0.1:{port}  局域网: http://<本机IP>:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")

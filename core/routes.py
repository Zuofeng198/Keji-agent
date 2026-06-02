"""知识库、文件浏览、设置的 API 路由"""

import os
import json
import datetime
import time
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, UploadFile, File, Depends, Request

from core.security.deps import get_current_user, get_current_user_optional
from core.security.users import CurrentUser, user_session_key, parse_session_conversation_id
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from core.database.db import get_db
from core.rag.vector_store import get_vector_store
from core.document.parser import is_supported, get_file_metadata, get_doc_category
from core.document.indexer import get_indexer

router = APIRouter(prefix="/api")


# ──────────── 请求/响应模型 ────────────


class IndexRequest(BaseModel):
    path: str
    recursive: bool = True


class SettingsUpdate(BaseModel):
    settings: dict


# ──────────── 知识库接口 ────────────


@router.get("/knowledge/documents")
def list_documents():
    """列出所有已索引文档"""
    db = get_db()
    docs = db.list_documents()
    # 格式化时间
    for d in docs:
        if d.get("indexed_at"):
            d["indexed_at"] = datetime.datetime.fromtimestamp(
                d["indexed_at"]
            ).strftime("%Y-%m-%d %H:%M")
    return {"documents": docs}


@router.post("/knowledge/index")
def index_document(req: IndexRequest):
    """索引文件或文件夹到知识库"""
    from core.path_policy import check_path
    path, err = check_path(req.path, must_exist=True)
    if err:
        raise HTTPException(403, err.replace("错误：", ""))
    if not os.path.exists(path):
        raise HTTPException(404, f"路径不存在: {path}")
    try:
        from core.security.audit import audit_file_access
        audit_file_access(path, "index", tool_name="api_knowledge_index")
    except Exception:
        pass

    indexer = get_indexer()

    if os.path.isfile(path):
        if not is_supported(path):
            raise HTTPException(400, f"不支持的文件类型: {os.path.splitext(path)[1]}")
        result = indexer.index_file(path)
        if result:
            return {"status": "ok", "type": "file", "result": result}
        raise HTTPException(500, "文件索引失败")

    elif os.path.isdir(path):
        result = indexer.index_directory(path, recursive=req.recursive)
        return {"status": "ok", "type": "directory", "result": result}

    raise HTTPException(400, "路径无效")


@router.post("/knowledge/cancel")
def cancel_indexing():
    """取消当前正在进行的索引任务"""
    indexer = get_indexer()
    indexer.cancel_indexing()
    return {"status": "ok", "message": "索引任务已取消"}


@router.get("/knowledge/is_indexing")
def check_indexing():
    """检查是否有正在进行的索引任务"""
    indexer = get_indexer()
    return {"is_indexing": indexer.is_indexing()}


@router.post("/knowledge/clear")
def clear_knowledge():
    """清空整个知识库（删除并重建向量集合 + 清除数据库记录）"""
    db = get_db()
    vs = get_vector_store()

    docs = db.list_documents()
    count = len(docs)

    # 直接删除整个 collection，避免逐条删除导致索引错误
    try:
        vs.client.delete_collection("keji_documents")
    except Exception:
        pass

    # 重建空 collection
    from core.rag.embeddings import EmbeddingManager
    embedding_fn = EmbeddingManager.get_instance().get_ollama()
    vs.collection = vs.client.create_collection(
        name="keji_documents",
        embedding_function=embedding_fn,
        metadata={"hnsw:space": "cosine"},
    )

    # 清除数据库记录
    conn = db._get_conn()
    conn.execute("DELETE FROM documents")
    conn.commit()

    return {"status": "ok", "message": f"已清空 {count} 个文档", "count": count}


@router.delete("/knowledge/document/{doc_id:str}")
def delete_document(doc_id: str):
    """删除已索引文档"""
    db = get_db()
    vs = get_vector_store()
    vs.delete_document(doc_id)
    db.remove_document(doc_id)
    return {"status": "ok", "message": "文档已删除"}


@router.get("/knowledge/search")
def search_knowledge(
    query: str = Query(..., description="搜索关键词"),
    n: int = Query(5, description="返回结果数"),
):
    """搜索知识库"""
    vs = get_vector_store()
    if vs.count() == 0:
        return {"results": [], "total": 0}

    results = vs.search(query, n_results=n)
    items = []
    for r in results:
        items.append({
            "id": r["id"],
            "content": r["content"][:500],
            "score": round(r["score"], 4),
            "source": r["metadata"].get("file_name", "未知"),
            "file_path": r["metadata"].get("file_path", ""),
        })
    return {"results": items, "total": len(items)}


@router.get("/knowledge/stats")
def knowledge_stats():
    """知识库统计"""
    db = get_db()
    vs = get_vector_store()
    doc_stats = db.get_document_stats()
    return {
        "total_documents": doc_stats["total_documents"],
        "total_chunks": doc_stats["total_chunks"],
        "vector_count": vs.count(),
        "by_type": doc_stats["by_type"],
    }


# ──────────── 文件浏览接口（团队工作区） ────────────


def _format_size(size: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f}{unit}"
        size /= 1024
    return f"{size:.1f}TB"


def _files_check_path(
    request: Request,
    path: str,
    user: CurrentUser | None,
    **kwargs,
) -> str:
    from core.workspace import (
        use_workspace_for_user,
        check_workspace_path,
        default_list_path,
    )
    from core.path_policy import check_path, default_browse_path

    u = user or get_current_user_optional(request)
    if use_workspace_for_user(u):
        if not path:
            path = default_list_path(u)
        resolved, err = check_workspace_path(path, u, **kwargs)
    else:
        if not path:
            path = default_browse_path()
        resolved, err = check_path(path, **kwargs)
    if err:
        raise HTTPException(403, err.replace("错误：", ""))
    return resolved


def _enrich_dir_item(name: str, full: str, is_dir: bool) -> dict:
    extra: dict = {}
    if is_dir:
        from core.workspace import users_root

        try:
            if Path(full).resolve().parent.resolve() == users_root().resolve():
                row = get_db().get_user_by_id(name)
                if row:
                    extra["owner_username"] = row.get("username")
                    extra["owner_display"] = row.get("display_name") or row.get("username")
                    extra["label"] = extra["owner_display"]
        except Exception:
            pass
    return extra


@router.get("/files/roots")
def file_workspace_roots(
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """工作区入口：共享 / 我的 /（管理员）全部用户。"""
    from core.workspace import list_roots, use_workspace_for_user, path_display

    if not use_workspace_for_user(user):
        from core.path_policy import get_allowed_roots, is_sandbox_enabled
        import string

        if is_sandbox_enabled():
            roots = get_allowed_roots()
            return {
                "mode": "legacy",
                "roots": [
                    {"id": "root", "name": p.name or str(p), "path": str(p), "can_write": True}
                    for p in roots
                ],
            }
        drives = []
        for letter in string.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append({"id": drive, "name": drive, "path": drive, "can_write": True})
        return {"mode": "legacy", "roots": drives}

    return {"mode": "workspace", "roots": list_roots(user)}


@router.get("/files/list")
def list_files(
    request: Request,
    path: str = Query("", description="文件夹路径"),
    user: CurrentUser | None = Depends(get_current_user_optional),
):
    """列出目录内容"""
    from core.workspace import use_workspace_for_user, path_display, can_write

    path = _files_check_path(
        request, path, user, must_exist=True, must_be_dir=True
    )
    try:
        from core.security.audit import audit_file_access
        audit_file_access(path, "list", tool_name="api_files_list")
    except Exception:
        pass

    if not os.path.exists(path):
        raise HTTPException(404, f"路径不存在: {path}")
    if not os.path.isdir(path):
        raise HTTPException(400, "不是文件夹")

    try:
        items = []
        for name in sorted(os.listdir(path)):
            full = os.path.join(path, name)
            try:
                stat = os.stat(full)
                is_dir = os.path.isdir(full)
                ext = os.path.splitext(name)[1].lower() if not is_dir else ""
                row = {
                    "name": name,
                    "path": full,
                    "is_dir": is_dir,
                    "size": stat.st_size,
                    "size_str": _format_size(stat.st_size) if not is_dir else "",
                    "modified": datetime.datetime.fromtimestamp(
                        stat.st_mtime
                    ).strftime("%Y-%m-%d %H:%M"),
                    "ext": ext,
                    "is_supported": is_supported(full) if not is_dir else False,
                }
                row.update(_enrich_dir_item(name, full, is_dir))
                if row.get("label"):
                    row["name"] = row["label"]
                items.append(row)
            except Exception:
                items.append({
                    "name": name,
                    "path": full,
                    "is_dir": False,
                    "size": 0,
                    "size_str": "",
                    "modified": "",
                    "ext": "",
                    "is_supported": False,
                })

        parent = os.path.dirname(path) if path != os.path.dirname(path) else ""
        u = user or get_current_user_optional(request)
        if u and use_workspace_for_user(u):
            from core.workspace import (
                shared_dir,
                users_root,
                user_dir as ws_user_dir,
                workspace_root,
            )

            if path.rstrip("\\/") == str(shared_dir()).rstrip("\\/"):
                parent = ""
            elif path.rstrip("\\/") == str(ws_user_dir(u.id)).rstrip("\\/"):
                parent = ""
            elif not u.is_admin:
                wr = str(workspace_root())
                ur = str(users_root())
                if parent.rstrip("\\/") in (wr, ur):
                    parent = ""
        payload = {
            "path": path,
            "parent": parent,
            "items": items,
            "total": len(items),
        }
        if use_workspace_for_user(u):
            payload["mode"] = "workspace"
            payload["display_path"] = path_display(path, u)
            payload["can_write"] = can_write(Path(path), u)
            payload["can_upload"] = payload["can_write"] and os.path.isdir(path)
        return payload
    except PermissionError:
        raise HTTPException(403, f"无权限访问: {path}")


@router.get("/files/drives")
def list_drives(request: Request, user: CurrentUser | None = Depends(get_current_user_optional)):
    """兼容旧前端：返回工作区 roots 或盘符。"""
    from core.workspace import use_workspace_for_user, list_roots

    u = user or get_current_user_optional(request)
    if use_workspace_for_user(u):
        roots = list_roots(u)
        return {
            "mode": "workspace",
            "drives": [
                {"name": r["name"], "path": r["path"], "label": r["name"], "id": r["id"]}
                for r in roots
            ],
        }
    from core.path_policy import get_allowed_roots, is_sandbox_enabled
    if is_sandbox_enabled():
        roots = get_allowed_roots()
        return {
            "mode": "legacy",
            "drives": [
                {"name": p.name or str(p), "path": str(p), "label": str(p)}
                for p in roots
            ],
        }
    import string
    drives = []
    for letter in string.ascii_uppercase:
        drive = f"{letter}:\\"
        if os.path.exists(drive):
            drives.append({"name": drive, "path": drive, "label": drive})
    return {"mode": "legacy", "drives": drives}


@router.get("/files/info")
def file_info(
    request: Request,
    path: str = Query(...),
    user: CurrentUser | None = Depends(get_current_user_optional),
):
    """获取文件信息"""
    path = _files_check_path(request, path, user, must_exist=True)
    if not os.path.exists(path):
        raise HTTPException(404, "文件不存在")

    stat = os.stat(path)
    is_dir = os.path.isdir(path)
    ext = os.path.splitext(path)[1].lower() if not is_dir else ""
    meta = get_file_metadata(path) if not is_dir else {}

    return {
        "name": os.path.basename(path),
        "path": path,
        "is_dir": is_dir,
        "size": stat.st_size,
        "size_str": _format_size(stat.st_size),
        "modified": datetime.datetime.fromtimestamp(stat.st_mtime).strftime(
            "%Y-%m-%d %H:%M"
        ),
        "created": datetime.datetime.fromtimestamp(
            getattr(stat, "st_ctime", 0)
        ).strftime("%Y-%m-%d %H:%M"),
        "ext": ext,
        "is_supported": is_supported(path) if not is_dir else False,
        "category": meta.get("category", "") if not is_dir else "",
    }


@router.post("/files/open")
def open_file(
    request: Request,
    path: str = Query(...),
    user: CurrentUser | None = Depends(get_current_user_optional),
):
    """用系统默认程序打开文件（在服务器 A 上打开）"""
    import subprocess
    import platform
    path = _files_check_path(request, path, user, must_exist=True, must_be_file=True)
    try:
        from core.security.audit import audit_file_access
        audit_file_access(path, "open", tool_name="api_files_open")
    except Exception:
        pass
    if not os.path.exists(path):
        raise HTTPException(404, f"文件不存在: {path}")
    if os.path.isdir(path):
        raise HTTPException(400, "不支持打开文件夹，请使用浏览功能")
    try:
        pf = platform.system()
        if pf == "Windows":
            os.startfile(path)
        elif pf == "Darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
        return {"status": "ok", "message": f"已打开: {os.path.basename(path)}"}
    except Exception as e:
        raise HTTPException(500, f"打开文件失败: {str(e)[:200]}")


class FilesMkdirRequest(BaseModel):
    path: str = Field(..., description="父目录绝对路径")
    name: str = Field(..., min_length=1, max_length=128)


@router.post("/files/mkdir")
def files_mkdir(
    req: FilesMkdirRequest,
    request: Request,
    user: CurrentUser = Depends(get_current_user),
):
    """在工作区当前目录下新建文件夹。"""
    parent = _files_check_path(
        request, req.path, user, must_exist=True, must_be_dir=True, write=True
    )
    safe = "".join(c for c in req.name.strip() if c not in '\\/:*?"<>|').strip()
    if not safe:
        raise HTTPException(400, "文件夹名称无效")
    new_path = os.path.join(parent, safe)
    if os.path.exists(new_path):
        raise HTTPException(400, "文件夹已存在")
    os.makedirs(new_path, exist_ok=False)
    return {"status": "ok", "path": new_path, "name": safe}


@router.post("/files/upload")
async def files_upload(
    request: Request,
    path: str = Query(..., description="目标目录"),
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    """上传文件到工作区目录（共享或自己的文件夹；管理员可上传到任意工作区路径）。"""
    target_dir = _files_check_path(
        request, path, user, must_exist=True, must_be_dir=True, write=True
    )
    original_name = file.filename or "upload"
    safe_name = "".join(
        c for c in os.path.basename(original_name) if c not in '\\/:*?"<>|'
    ).strip() or "upload"
    save_path = os.path.join(target_dir, safe_name)
    if os.path.exists(save_path):
        base, ext = os.path.splitext(safe_name)
        save_path = os.path.join(target_dir, f"{base}_{uuid.uuid4().hex[:6]}{ext}")

    try:
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)
        try:
            from core.security.audit import audit_file_access
            audit_file_access(save_path, "upload", tool_name="api_files_upload")
        except Exception:
            pass
        size = len(content)
        ext = os.path.splitext(safe_name)[1].lower()
        return {
            "status": "ok",
            "file_name": original_name,
            "file_path": save_path,
            "size": size,
            "size_str": _format_size(size),
            "ext": ext,
            "is_supported": is_supported(save_path),
        }
    except Exception as e:
        raise HTTPException(500, f"上传失败: {str(e)[:200]}")


# ──────────── 对话管理接口 ────────────


def _format_conv_timestamps(convs: list[dict]) -> None:
    for c in convs:
        if isinstance(c.get("created_at"), (int, float)):
            c["created_at"] = datetime.datetime.fromtimestamp(c["created_at"]).strftime(
                "%Y-%m-%d %H:%M"
            )
        if isinstance(c.get("updated_at"), (int, float)):
            c["updated_at"] = datetime.datetime.fromtimestamp(c["updated_at"]).strftime(
                "%Y-%m-%d %H:%M"
            )


def _merge_all_nanobot_conversations_for_admin(
    convs: list[dict],
    owner_filter: str | None = None,
) -> None:
    """管理员：合并所有 user:{uid}:{conv} 的 nanobot 会话。"""
    try:
        from nanobot.session.manager import SessionManager
        from pathlib import Path

        sm = SessionManager(Path(__file__).resolve().parent.parent)
        users_by_id = {u["id"]: u for u in get_db().list_users()}
        for info in sm.list_sessions():
            key = info.get("key", "")
            if not key.startswith("user:"):
                continue
            parts = key.split(":", 2)
            if len(parts) < 3:
                continue
            uid, conv_id = parts[1], parts[2]
            if owner_filter and uid != owner_filter:
                continue
            if any(c.get("id") == conv_id and c.get("owner_user_id") == uid for c in convs):
                continue
            data = sm.read_session_file(key)
            msgs = data.get("messages", []) if data else []
            first = msgs[0].get("content", "")[:30] if msgs else conv_id
            owner = users_by_id.get(uid)
            convs.append({
                "id": conv_id,
                "title": first[:50],
                "created_at": info.get("created_at", ""),
                "updated_at": info.get("updated_at", ""),
                "message_count": len(msgs),
                "owner_user_id": uid,
                "owner_username": owner["username"] if owner else "",
                "owner_display_name": (owner.get("display_name") or owner["username"]) if owner else "",
            })
    except Exception:
        pass


def _merge_user_nanobot_sessions(convs: list[dict], user: CurrentUser) -> None:
    if user.id in ("anonymous", "localhost", "service"):
        return
    prefix = f"user:{user.id}:"
    try:
        from nanobot.session.manager import SessionManager
        from pathlib import Path

        sm = SessionManager(Path(__file__).resolve().parent.parent)
        for info in sm.list_sessions():
            key = info.get("key", "")
            if not key.startswith(prefix):
                continue
            conv_id = parse_session_conversation_id(key, user.id) or key
            if any(c.get("id") == conv_id for c in convs):
                continue
            data = sm.read_session_file(key)
            msgs = data.get("messages", []) if data else []
            first_content = msgs[0].get("content", "")[:30] if msgs else conv_id
            convs.append({
                "id": conv_id,
                "title": first_content[:50],
                "created_at": info.get("created_at", ""),
                "updated_at": info.get("updated_at", ""),
                "message_count": len(msgs),
                "owner_user_id": user.id,
            })
    except Exception:
        pass


def _assert_conv_access(conv_id: str, user: CurrentUser) -> None:
    if user.is_admin:
        return
    db = get_db()
    conv = db.get_conversation(conv_id)
    if conv:
        owner = conv.get("owner_user_id")
        if owner and owner != user.id and not user.is_admin:
            raise HTTPException(403, "无权访问该对话")
        if owner is None and user.id not in ("service", "localhost", "anonymous"):
            raise HTTPException(403, "无权访问该对话")
        return
    if user.id in ("anonymous", "localhost", "service"):
        return
    sk = user_session_key(user.id, conv_id)
    try:
        from nanobot.session.manager import SessionManager
        from pathlib import Path

        sm = SessionManager(Path(__file__).resolve().parent.parent)
        if sm.read_session_file(sk) or sm.read_session_file(conv_id):
            return
    except Exception:
        pass
    raise HTTPException(404, "对话不存在")


@router.get("/conversations")
def list_conversations(user: CurrentUser = Depends(get_current_user)):
    """列出当前用户自己的对话。"""
    db = get_db()
    if user.id in ("anonymous", "localhost", "service"):
        convs = db.list_conversations(limit=50)
    else:
        convs = db.list_conversations(limit=50, owner_user_id=user.id)
    _format_conv_timestamps(convs)
    _merge_user_nanobot_sessions(convs, user)
    return {"conversations": convs}


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: str, user: CurrentUser = Depends(get_current_user)):
    """获取对话消息（仅本人；管理员请用 /api/admin/conversations）"""
    _assert_conv_access(conv_id, user)
    db = get_db()
    conv = db.get_conversation(conv_id)
    if conv:
        messages = db.get_messages(conv_id)
        return {"conversation": conv, "messages": messages}
    sk = user_session_key(user.id, conv_id)
    try:
        from nanobot.session.manager import SessionManager
        from pathlib import Path

        sm = SessionManager(Path(__file__).resolve().parent.parent)
        for key in (sk, conv_id):
            data = sm.read_session_file(key)
            if data:
                msgs = data.get("messages", [])
                return {
                    "conversation": {"id": conv_id, "title": conv_id, "messages": len(msgs)},
                    "messages": msgs,
                }
    except Exception:
        pass
    raise HTTPException(404, "对话不存在")


@router.post("/chat/load")
def load_conversation(conv_id: str, session_id: str = ""):
    """将已有对话的消息加载到记忆（由前端session_id控制，nanobot自动读取session文件）"""
    return {"status": "ok", "message": "会话切换完成"}


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: str, user: CurrentUser = Depends(get_current_user)):
    """删除对话（数据库 + nanobot session文件）"""
    _assert_conv_access(conv_id, user)
    db = get_db()
    db.delete_conversation(conv_id)
    try:
        from nanobot.session.manager import SessionManager
        from pathlib import Path

        sm = SessionManager(Path(__file__).resolve().parent.parent)
        sm.delete_session(conv_id)
        if user.id not in ("anonymous", "localhost", "service"):
            sm.delete_session(user_session_key(user.id, conv_id))
    except Exception:
        pass
    return {"status": "ok", "message": "对话已删除"}


# ──────────── 设置接口 ────────────


def _user_pref_key(user_id: str, name: str) -> str:
    return f"user:{user_id}:{name}"


@router.get("/settings")
def get_settings(request: Request):
    """从 config.yaml + DB 读取所有设置"""
    from ruamel.yaml import YAML

    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    yaml = YAML()
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.load(f)

    # 从 config.yaml 映射到前端需要的键值格式
    models = config.get("models", {})
    default_provider = models.get("default", "ollama")
    provider_cfg = models.get(default_provider, {})
    ollama_cfg = models.get("ollama", {})
    openai_cfg = models.get("openai", {})
    know = config.get("knowledge", {})

    # 前端只认 ollama/openai，deepseek 用 openai 表单显示（同一个模板）
    display_type = default_provider
    if display_type not in ("ollama", "openai"):
        display_type = "openai"

    from core.security.secrets import mask_api_key_for_settings
    from core.mcp_paths import dirs_for_display, get_mcp_config

    raw_api_key = str(provider_cfg.get("api_key", "") or "")
    _, api_configured = mask_api_key_for_settings(raw_api_key)

    agent_cfg = config.get("agent") or {}
    mcp_cfg = get_mcp_config(config)
    mcp_dirs = mcp_cfg.get("filesystem_allowed_dirs") or []
    if isinstance(mcp_dirs, list):
        mcp_dirs_text = "\n".join(str(x) for x in mcp_dirs)
    else:
        mcp_dirs_text = str(mcp_dirs)

    mapped = {
        "model_type": display_type,
        "ollama_url": ollama_cfg.get("base_url", ""),
        "chat_model": ollama_cfg.get("model", ""),
        "openai_base_url": provider_cfg.get("base_url", ""),
        "openai_api_key": "",
        "openai_api_key_configured": api_configured,
        "openai_model": provider_cfg.get("model", ""),
        "embed_model": know.get("embedding_model", ""),
        "chunk_size": str(know.get("chunk_size", "")),
        "chunk_overlap": str(know.get("chunk_overlap", "")),
        "top_k": str(know.get("retrieval_count", "")),
        "context_auto_compact_enabled": agent_cfg.get("context_auto_compact_enabled", True),
        "context_auto_compact_threshold": str(agent_cfg.get("context_auto_compact_threshold", 60000)),
        "context_prune_tool_results": agent_cfg.get("context_prune_tool_results", True),
        "mcp_filesystem_dirs": mcp_dirs_text,
        "mcp_include_knowledge": mcp_cfg.get("include_knowledge", True),
        "mcp_include_data": mcp_cfg.get("include_data", True),
        "mcp_resolved_dirs": dirs_for_display(config),
    }

    # 企业微信等设置仍从 DB 读取
    db = get_db()
    db_settings = db.get_all_settings()
    for k in ("work_corp_id", "work_agent_id", "work_secret"):
        if k in db_settings:
            mapped[k] = db_settings[k]

    user = getattr(request.state, "user", None)
    if user and user.id not in ("anonymous", "localhost", "service"):
        pref = db_settings.get(_user_pref_key(user.id, "icon_theme"))
        if pref:
            mapped["icon_theme"] = pref

    return {"config": config, "db_settings": mapped}


# config.yaml 键 ← 前端 setting key（实际目标 provider 由 runtime 决定）
def _get_config_path(settings_key: str, default_provider: str) -> list[str]:
    """将前端设置 key 映射到 config.yaml 的实际路径"""
    _ollama_keys = {
        "ollama_url":  ["models", "ollama", "base_url"],
        "chat_model":  ["models", "ollama", "model"],
    }
    if settings_key in _ollama_keys:
        return _ollama_keys[settings_key]
    # OpenAI 兼容的 key → 写入实际使用的 provider 下
    _openai_keys = {
        "openai_base_url": ["models", default_provider, "base_url"],
        "openai_api_key":  ["models", default_provider, "api_key"],
        "openai_model":    ["models", default_provider, "model"],
    }
    if settings_key in _openai_keys:
        return _openai_keys[settings_key]
    _common_keys = {
        "embed_model":   ["knowledge", "embedding_model"],
        "chunk_size":    ["knowledge", "chunk_size"],
        "chunk_overlap": ["knowledge", "chunk_overlap"],
        "top_k":         ["knowledge", "retrieval_count"],
        "context_auto_compact_enabled": ["agent", "context_auto_compact_enabled"],
        "context_auto_compact_threshold": ["agent", "context_auto_compact_threshold"],
        "context_prune_tool_results": ["agent", "context_prune_tool_results"],
    }
    return _common_keys.get(settings_key, [])


# 写入 config.yaml 的前端设置项（其余进 SQLite settings 表）
_CONFIG_KEY_MAP = frozenset({
    "model_type",
    "ollama_url",
    "chat_model",
    "openai_base_url",
    "openai_api_key",
    "openai_model",
    "embed_model",
    "chunk_size",
    "chunk_overlap",
    "top_k",
    "context_auto_compact_enabled",
    "context_auto_compact_threshold",
    "context_prune_tool_results",
    "mcp_filesystem_dirs",
    "mcp_include_knowledge",
    "mcp_include_data",
})


def _apply_model_type(config: dict, model_type: str) -> None:
    """前端 model_type → config.models.default"""
    models = config.setdefault("models", {})
    if model_type == "ollama":
        models["default"] = "ollama"
    elif model_type == "openai":
        if "deepseek" in models:
            models["default"] = "deepseek"
        elif "openai" in models:
            models["default"] = "openai"
        else:
            models["default"] = "openai"


def _set_nested(d: dict, keys: list[str], value) -> None:
    """在嵌套字典中按 key 路径设值"""
    for k in keys[:-1]:
        d = d.setdefault(k, {})
    # 类型还原
    if keys[-1] in ("chunk_size", "chunk_overlap", "top_k", "retrieval_count"):
        try:
            value = int(value)
        except (ValueError, TypeError):
            pass
    d[keys[-1]] = value


@router.post("/settings")
def update_settings(req: SettingsUpdate, request: Request):
    """保存设置：模型/知识库配置写入 config.yaml，企业微信写入 DB"""
    from ruamel.yaml import YAML

    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")

    # 分离 Config 类设置和 DB 类设置
    config_updates = {}
    db_updates = {}

    user = getattr(request.state, "user", None)
    for key, value in req.settings.items():
        if key in _CONFIG_KEY_MAP:
            config_updates[key] = value
        elif key == "icon_theme" and user and user.id not in (
            "anonymous",
            "localhost",
            "service",
        ):
            db_updates[_user_pref_key(user.id, "icon_theme")] = str(value)
        else:
            db_updates[key] = value

    mcp_dirs_raw = None
    mcp_changed = False

    # 写入 config.yaml
    if config_updates:
        yaml = YAML()
        yaml.preserve_quotes = True
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.load(f) or {}

        if "model_type" in config_updates:
            mt = config_updates.pop("model_type")
            if mt:
                _apply_model_type(config, str(mt))

        default_provider = config.get("models", {}).get("default", "openai")

        from core.security.secrets import persist_provider_api_key

        api_key_val = config_updates.pop("openai_api_key", None)
        if api_key_val:
            persist_provider_api_key(config, default_provider, str(api_key_val))

        mcp_dirs_raw = config_updates.pop("mcp_filesystem_dirs", None)
        mcp_inc_k = config_updates.pop("mcp_include_knowledge", None)
        mcp_inc_d = config_updates.pop("mcp_include_data", None)
        if mcp_dirs_raw is not None or mcp_inc_k is not None or mcp_inc_d is not None:
            mcp_changed = True
            mcp = config.setdefault("mcp", {})
            if mcp_dirs_raw is not None:
                lines = [
                    ln.strip() for ln in str(mcp_dirs_raw).replace("\r", "").split("\n")
                    if ln.strip()
                ]
                mcp["filesystem_allowed_dirs"] = lines
            if mcp_inc_k is not None:
                mcp["include_knowledge"] = str(mcp_inc_k).lower() in ("1", "true", "yes", "on")
            if mcp_inc_d is not None:
                mcp["include_data"] = str(mcp_inc_d).lower() in ("1", "true", "yes", "on")

        for key, value in config_updates.items():
            if key in ("context_auto_compact_enabled", "context_prune_tool_results"):
                if isinstance(value, bool):
                    bool_val = value
                else:
                    bool_val = str(value).lower() in ("1", "true", "yes", "on")
                path = _get_config_path(key, default_provider)
                if path:
                    _set_nested(config, path, bool_val)
                continue
            if value is None or value == "":
                continue
            if key == "context_auto_compact_threshold":
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    continue
            path = _get_config_path(key, default_provider)
            if path:
                _set_nested(config, path, value)

        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)

        try:
            from nanobot import adapter as _adapter_mod
            if _adapter_mod.adapter is not None:
                with open(config_path, "r", encoding="utf-8") as f:
                    _adapter_mod.adapter.config = yaml.load(f) or {}
        except Exception:
            pass

    # 写入 DB（企业微信等）
    if db_updates:
        db = get_db()
        for key, value in db_updates.items():
            if value is not None:
                db.set_setting(key, str(value))

    msg = "设置已保存"
    if mcp_changed:
        msg += "；MCP 文件目录已写入配置，请点击「应用 MCP 目录」或重启服务"
    else:
        msg += "；对话压缩等新参数已生效（MCP 变更需应用或重启）"
    return {"status": "ok", "message": msg}


@router.post("/mcp/reload")
async def reload_mcp_servers():
    """重新连接 MCP（应用 filesystem 允许目录变更）。"""
    adapter = await _get_adapter()
    # 重载磁盘上的 config.yaml
    from core.security.secrets import load_app_config
    from pathlib import Path
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    adapter.config = load_app_config(config_path)
    dirs = await adapter.reload_filesystem_mcp()
    return {"status": "ok", "message": "MCP 文件目录已应用", "filesystem_dirs": dirs}


@router.get("/mcp/filesystem-dirs")
def get_mcp_filesystem_dirs():
    """当前生效的 MCP 文件系统允许目录。"""
    from core.security.secrets import load_app_config
    from core.mcp_paths import dirs_for_display
    from pathlib import Path
    config_path = Path(__file__).resolve().parent.parent / "config.yaml"
    config = load_app_config(config_path)
    return {"directories": dirs_for_display(config)}


class TestModelRequest(BaseModel):
    model_type: str = "ollama"
    base_url: str = ""
    api_key: str = ""
    model: str = ""


@router.post("/models/test")
def test_model_connection(req: TestModelRequest):
    """测试模型连接是否可用"""
    import requests as http_req

    try:
        if req.model_type == "ollama":
            url = req.base_url.rstrip("/") + "/api/chat"
            payload = {
                "model": req.model or "qwen2.5:7b",
                "messages": [{"role": "user", "content": "hi"}],
                "stream": False,
                "options": {"temperature": 0.1},
            }
            resp = http_req.post(url, json=payload, timeout=15)
            resp.raise_for_status()
            return {"status": "ok", "message": f"Ollama 连接成功，模型 [{req.model}] 可用"}

        elif req.model_type == "openai":
            url = req.base_url.rstrip("/") + "/chat/completions"
            if not req.api_key:
                return {"status": "error", "message": "API Key 不能为空"}
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {req.api_key}",
            }
            payload = {
                "model": req.model or "gpt-4o-mini",
                "messages": [{"role": "user", "content": "hi"}],
                "temperature": 0.1,
                "max_tokens": 10,
            }
            resp = http_req.post(url, json=payload, headers=headers, timeout=15)
            resp.raise_for_status()
            return {"status": "ok", "message": f"API 连接成功，模型 [{req.model}] 可用"}

        return {"status": "error", "message": "未知的模型类型"}

    except http_req.ConnectionError:
        return {"status": "error", "message": "无法连接到服务器，请检查地址是否正确"}
    except http_req.Timeout:
        return {"status": "error", "message": "连接超时，请检查网络或地址"}
    except http_req.HTTPError as e:
        code = e.response.status_code if e.response else "?"
        # 尝试获取 API 返回的具体错误信息
        detail = ""
        if e.response is not None:
            try:
                body = e.response.json()
                err = body.get("error", {})
                if isinstance(err, dict):
                    detail = err.get("message", str(body)[:200])
                else:
                    detail = str(body)[:200]
            except Exception:
                detail = e.response.text[:200]
        if code == 401:
            return {"status": "error", "message": f"API Key 无效 (401)，{detail}"}
        elif code == 404:
            return {"status": "error", "message": f"模型不存在 (404)，{detail}"}
        return {"status": "error", "message": f"HTTP {code}: {detail}"}
    except Exception as e:
        return {"status": "error", "message": f"连接失败: {str(e)[:200]}"}


# ──────────── Ollama 管理 ────────────


@router.get("/ollama/check")
def ollama_check():
    """检查 Ollama 服务和模型状态"""
    import requests
    result = {
        "ollama_running": False,
        "models": [],
        "default_model_ready": False,
        "message": "",
    }
    try:
        r = requests.get("http://localhost:11434/api/tags", timeout=5)
        if r.status_code == 200:
            result["ollama_running"] = True
            models = [m["name"] for m in r.json().get("models", [])]
            result["models"] = models
            result["default_model_ready"] = any(
                "qwen2.5:7b" in m or "qwen2.5" in m for m in models
            )
            if not result["default_model_ready"]:
                result["message"] = "未检测到 qwen2.5:7b 模型"
        else:
            result["message"] = "Ollama 服务响应异常"
    except requests.ConnectionError:
        result["message"] = "Ollama 服务未启动，请先启动 Ollama"
    except Exception as e:
        result["message"] = f"检查失败: {str(e)}"

    return result


class PullRequest(BaseModel):
    model: str = "qwen2.5:7b"


@router.post("/ollama/pull")
def ollama_pull(req: PullRequest):
    """拉取 Ollama 模型"""
    import requests
    try:
        resp = requests.post(
            "http://localhost:11434/api/pull",
            json={"model": req.model},
            timeout=600,
            stream=True,
        )
        if resp.status_code == 200:
            # 等待拉取完成
            last_line = ""
            for line in resp.iter_lines():
                if line:
                    last_line = line.decode()
            return {"status": "ok", "model": req.model, "detail": last_line}
        else:
            return {"status": "error", "message": f"Ollama 返回: {resp.status_code}"}
    except requests.ConnectionError:
        return {"status": "error", "message": "无法连接到 Ollama 服务"}
    except Exception as e:
        return {"status": "error", "message": str(e)}


# ──────────── 工具名映射 ────────────


@router.get("/tools/display")
def get_tools_display():
    """返回工具中文名对照表"""
    display_names = {
        "get_time": "获取时间", "calculator": "计算器",
        "read_file": "读取文件", "write_file": "写入文件", "edit_file": "编辑文件",
        "list_dir": "列出目录", "glob": "搜索文件", "grep": "搜索内容",
        "exec": "执行命令", "web_search": "网页搜索", "web_fetch": "获取网页",
        "read_document": "读取文档",
        "query_knowledge": "知识库检索", "index_knowledge": "索引到知识库",
        "knowledge_stats": "知识库统计", "remove_from_knowledge": "知识库删档",
        "create_document": "创建文档", "create_table": "创建表格", "create_presentation": "创建演示",
        "analyze_data": "数据分析", "format_data": "数据整理",
        "delete_file": "删除文件", "create_folder": "创建文件夹",
        "browse_archive": "浏览压缩包", "extract_archive": "解压压缩包", "create_archive": "创建压缩包",
        "ocr_image": "图片文字识别", "ocr_pdf": "PDF文字识别", "ocr_batch": "批量OCR",
        "parse_email": "解析邮件", "extract_email_attachments": "提取附件", "batch_parse_emails": "批量解析",
        "organize_files": "文件分类整理", "rename_files": "批量重命名", "deduplicate_files": "文件去重",
        "clean_data": "数据清洗", "convert_data": "格式转换", "etl_pipeline": "ETL处理",
        "run_code": "执行代码",
        "db_connect": "连接数据库", "db_list_tables": "列出表", "db_describe_table": "查看表结构",
        "db_execute_query": "执行SQL", "db_test_connection": "测试连接", "db_disconnect": "断开连接",
        "mcp_quack_load_csv": "加载CSV", "mcp_quack_query_csv": "查询CSV", "mcp_quack_list_tables": "列出CSV表",
        "mcp_quack_describe_table": "描述表结构", "mcp_quack_analyze_csv": "数据统计分析",
        "mcp_quack_load_excel": "加载Excel", "mcp_quack_load_multiple_csvs": "加载多个CSV",
        "mcp_quack_load_multiple_excels": "加载多个Excel", "mcp_quack_discover_csv_files": "搜索CSV文件",
        "mcp_quack_discover_excel_files": "搜索Excel文件", "mcp_quack_detect_anomalies": "异常检测",
        "mcp_quack_optimize_expenses": "费用优化分析",
        "mcp_quack_export_csv": "导出CSV", "mcp_quack_export_json": "导出JSON",
        "mcp_quack_attach_database": "挂载数据库",
        "mcp_filesystem_read_file": "读取文件", "mcp_filesystem_read_text_file": "读取文本",
        "mcp_filesystem_read_media_file": "读取媒体", "mcp_filesystem_read_multiple_files": "读取多个文件",
        "mcp_filesystem_write_file": "写入文件", "mcp_filesystem_edit_file": "编辑文件",
        "mcp_filesystem_create_directory": "创建目录", "mcp_filesystem_list_directory": "列出目录",
        "mcp_filesystem_list_directory_with_sizes": "列出目录大小", "mcp_filesystem_directory_tree": "目录树",
        "mcp_filesystem_move_file": "移动文件", "mcp_filesystem_search_files": "搜索文件",
        "mcp_filesystem_get_file_info": "获取文件信息", "mcp_filesystem_list_allowed_directories": "允许的目录",
        "mcp_memdb_store_memory": "存储记忆", "mcp_memdb_store_memories": "批量存储",
        "mcp_memdb_get_memory": "获取记忆", "mcp_memdb_delete_memory": "删除记忆",
        "mcp_memdb_delete_memories": "批量删除", "mcp_memdb_update_memory": "更新记忆",
        "mcp_memdb_search_memories": "搜索记忆", "mcp_memdb_recall": "回忆",
        "mcp_memdb_create_relationship": "创建关系", "mcp_memdb_get_relationships": "获取关系",
        "mcp_memdb_delete_relationship": "删除关系", "mcp_memdb_memory_stats": "记忆统计",
        "mcp_doc-tools_create_document": "创建Word", "mcp_doc-tools_open_document": "打开Word",
        "mcp_doc-tools_add_paragraph": "添加段落", "mcp_doc-tools_add_table": "添加表格",
        "mcp_doc-tools_search_and_replace": "查找替换", "mcp_doc-tools_set_page_margins": "设置页边距",
        "mcp_doc-tools_get_document_info": "文档信息",
        "mcp_excel_excel_copy_sheet": "复制Sheet", "mcp_excel_excel_create_table": "创建Excel表",
        "mcp_excel_excel_describe_sheets": "描述Sheet", "mcp_excel_excel_format_range": "格式化范围",
        "mcp_excel_excel_read_sheet": "读取Sheet", "mcp_excel_excel_screen_capture": "截图",
        "mcp_excel_excel_write_to_sheet": "写入Sheet",
        "mcp_image-gen_generateImageUrl": "生成图片URL", "mcp_image-gen_generateImage": "生成图片",
        "mcp_image-gen_listImageModels": "图片模型列表", "mcp_image-gen_generateText": "生成文本",
        "mcp_image-gen_listTextModels": "文本模型列表", "mcp_image-gen_respondAudio": "生成音频",
        "mcp_image-gen_sayText": "语音合成", "mcp_image-gen_listAudioVoices": "语音列表",
        "mcp_image-gen_startAuth": "开始认证", "mcp_image-gen_checkAuthStatus": "检查认证",
        "mcp_image-gen_getDomains": "获取域名", "mcp_image-gen_updateDomains": "更新域名",
        "mcp_charts_generate_echarts": "生成图表", "mcp_charts_generate_area_chart": "面积图",
        "mcp_charts_generate_line_chart": "折线图", "mcp_charts_generate_bar_chart": "柱状图",
        "mcp_charts_generate_pie_chart": "饼图", "mcp_charts_generate_radar_chart": "雷达图",
        "mcp_charts_generate_scatter_chart": "散点图", "mcp_charts_generate_sankey_chart": "桑基图",
        "mcp_charts_generate_funnel_chart": "漏斗图", "mcp_charts_generate_gauge_chart": "仪表盘",
        "mcp_charts_generate_treemap_chart": "矩形树图", "mcp_charts_generate_sunburst_chart": "旭日图",
        "mcp_charts_generate_heatmap_chart": "热力图", "mcp_charts_generate_candlestick_chart": "K线图",
        "mcp_charts_generate_boxplot_chart": "箱线图", "mcp_charts_generate_graph_chart": "关系图",
        "mcp_charts_generate_parallel_chart": "平行坐标", "mcp_charts_generate_tree_chart": "树图",
        # engineer-your-data 数据处理工具
        "mcp_engineer-your-data_read_file": "读取数据文件",
        "mcp_engineer-your-data_write_file": "写入数据文件",
        "mcp_engineer-your-data_list_files": "列出数据文件",
        "mcp_engineer-your-data_file_info": "文件信息",
        "mcp_engineer-your-data_validate_schema": "验证数据模式",
        "mcp_engineer-your-data_check_nulls": "空值检测",
        "mcp_engineer-your-data_data_quality_report": "数据质量报告",
        "mcp_engineer-your-data_detect_duplicates": "重复数据检测",
        "mcp_engineer-your-data_filter_data": "数据过滤",
        "mcp_engineer-your-data_aggregate_data": "数据聚合",
        "mcp_engineer-your-data_join_data": "数据关联",
        "mcp_engineer-your-data_pivot_data": "数据透视",
        "mcp_engineer-your-data_clean_data": "数据清洗",
        "mcp_engineer-your-data_execute_tool_chain": "工具链执行",
        "mcp_engineer-your-data_analyze_data_schema": "数据模式分析",
        "mcp_engineer-your-data_fetch_api_data": "获取API数据",
        "mcp_engineer-your-data_monitor_api": "监控API",
        "mcp_engineer-your-data_batch_api_calls": "批量API调用",
        "mcp_engineer-your-data_api_auth": "API认证",
        "mcp_engineer-your-data_create_chart": "生成图表",
        "mcp_engineer-your-data_data_summary": "数据摘要",
        "mcp_engineer-your-data_export_visualization": "导出可视化",
    }
    return {"tools": display_names}


# ──────────── 文件上传接口 ────────────

import shutil

_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "uploads")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传文件（图片/文档等），保存到临时目录，返回文件信息"""
    os.makedirs(_UPLOAD_DIR, exist_ok=True)

    # 安全化文件名
    original_name = file.filename or "upload"
    safe_name = f"{uuid.uuid4().hex[:8]}_{original_name}"
    save_path = os.path.join(_UPLOAD_DIR, safe_name)

    try:
        content = await file.read()
        with open(save_path, "wb") as f:
            f.write(content)
        try:
            from core.security.audit import audit_file_access
            audit_file_access(save_path, "upload", tool_name="api_upload")
        except Exception:
            pass

        size = len(content)
        ext = os.path.splitext(original_name)[1].lower()
        from core.document.parser import is_supported
        supported = is_supported(save_path)

        return {
            "status": "ok",
            "file_name": original_name,
            "file_path": save_path,
            "size": size,
            "size_str": _format_size(size),
            "ext": ext,
            "is_supported": supported,
        }
    except Exception as e:
        raise HTTPException(500, f"文件上传失败: {str(e)[:200]}")


@router.get("/upload/cleanup")
def cleanup_uploads(hours: int = 24):
    """清理超过指定小时数的临时上传文件"""
    now = time.time()
    count = 0
    if not os.path.isdir(_UPLOAD_DIR):
        return {"status": "ok", "deleted": 0}
    for fn in os.listdir(_UPLOAD_DIR):
        fp = os.path.join(_UPLOAD_DIR, fn)
        if os.path.isfile(fp) and now - os.path.getmtime(fp) > hours * 3600:
            try:
                os.remove(fp)
                count += 1
            except Exception:
                pass
    return {"status": "ok", "deleted": count}


# ──────────── 系统状态 ────────────


@router.get("/status")
def system_status():
    """系统状态信息"""
    db = get_db()
    vs = get_vector_store()
    doc_stats = db.get_document_stats()

    # Ollama 状态
    from core.rag.embeddings import EmbeddingManager
    em = EmbeddingManager.get_instance()
    ollama_ok = em.check_ollama_available()

    # Ollama 模型列表
    models = []
    try:
        import requests
        r = requests.get("http://localhost:11434/api/tags", timeout=3)
        if r.status_code == 200:
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception:
        pass

    # 当前模型连接信息
    model_type = db.get_setting("model_type", "")
    chat_model = db.get_setting("chat_model", "")

    # 如果数据库没有 model_type，回退到 config.yaml 的默认配置
    if not model_type:
        try:
            import yaml
            cfg_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            default_key = cfg.get("models", {}).get("default", "")
            provider_cfg = cfg.get("models", {}).get(default_key, {})
            model_name = provider_cfg.get("model", "deepseek-v4-flash")
            base_url = provider_cfg.get("base_url", "")
            # deepseek 走 OpenAI 兼容协议，归类为 API
            provider_label = base_url.replace("https://", "").split(".")[0] if base_url else "API"
            model_type = "openai"  # 前端显示为 API 模式
        except Exception:
            model_name = "unknown"
            provider_label = "config"
    elif model_type == "openai":
        api_base = db.get_setting("openai_base_url", "")
        api_model = db.get_setting("openai_model", "")
        model_name = api_model or chat_model or "unknown"
        provider_label = api_base.replace("https://", "").split(".")[0] if api_base else "API"
    else:
        model_name = chat_model or "unknown"
        provider_label = "Ollama"

    return {
        "ollama": {"available": ollama_ok, "models": models},
        "model": {
            "type": model_type,
            "name": model_name,
            "provider": provider_label,
        },
        "knowledge": {
            "documents": doc_stats["total_documents"],
            "chunks": doc_stats["total_chunks"],
            "vectors": vs.count(),
        },
        "sessions": 0,  # 已迁移至 nanobot.session
        "version": "1.0.0.1-Beta",
    }


# ──────────── 调试接口 ────────────


@router.get("/debug/logs")
def debug_logs(since: float = 0, limit: int = 100):
    """获取最近的应用日志（环形缓冲）"""
    from core.debug_logs import get_memory_handler
    handler = get_memory_handler()
    return {"logs": handler.get_logs(since=since, limit=limit)}


@router.get("/debug/agent-state")
def debug_agent_state(session_id: str = ""):
    """获取指定会话的消息历史（nanobot）"""
    try:
        from nanobot.session.manager import SessionManager
        from pathlib import Path
        sm = SessionManager(Path(__file__).resolve().parent.parent)
        data = sm.read_session_file(session_id) if session_id else None
        if data:
            msgs = [{"role": m["role"], "content": str(m.get("content", ""))[:500]} for m in data.get("messages", [])]
            return {"session_id": session_id, "memory_size": len(msgs), "messages": msgs}
    except Exception:
        pass
    return {"session_id": session_id or "auto", "memory_size": 0, "messages": []}


# ──────────── MCP 管理接口 ────────────


@router.get("/mcp/servers")
def list_mcp_servers():
    """列出已配置的 MCP 服务器"""
    try:
        from nanobot.adapter import get_adapter
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        adapter = loop.run_until_complete(get_adapter())
        loop.close()
        return {"servers": adapter.get_mcp_servers_config()}
    except Exception as e:
        return {"servers": [], "error": str(e)[:200]}


@router.get("/mcp/status")
def mcp_status():
    """获取 MCP 连接状态"""
    try:
        from nanobot.adapter import get_adapter
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        adapter = loop.run_until_complete(get_adapter())
        loop.close()
        stacks = adapter._mcp_stacks if hasattr(adapter, '_mcp_stacks') else {}
        return {"connected": list(stacks.keys()) if stacks else []}
    except Exception as e:
        return {"connected": [], "error": str(e)[:200]}


@router.post("/mcp/servers")
async def reload_mcp_servers_alias():
    """与 POST /api/mcp/reload 相同（兼容旧前端或代理路径）。"""
    return await reload_mcp_servers()


# ──────────── 数据库管理接口 ────────────

import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

def _get_cipher() -> Fernet:
    """获取密码加密器（基于机器级密钥）"""
    import hashlib
    machine_id = hashlib.md5(os.environ.get("COMPUTERNAME", "keji").encode()).hexdigest()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"keji-db-pwd", iterations=100000)
    key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
    return Fernet(key)

def _encrypt_pwd(password: str) -> str:
    try:
        return _get_cipher().encrypt(password.encode()).decode()
    except Exception:
        return ""

def _decrypt_pwd(encrypted: str) -> str:
    try:
        return _get_cipher().decrypt(encrypted.encode()).decode()
    except Exception:
        return encrypted


@router.get("/database/configs")
def list_db_configs():
    """列出所有数据库配置"""
    db = get_db()
    configs = db.list_db_configs()
    return {"configs": configs}

@router.post("/database/configs")
def create_db_config(data: dict):
    """创建数据库配置"""
    required = ["name", "db_type", "host", "port", "database_name", "username"]
    for k in required:
        if k not in data:
            raise HTTPException(400, f"缺少必填字段: {k}")
    db = get_db()
    pwd_enc = _encrypt_pwd(data.get("password", ""))
    result = db.create_db_config(
        name=data["name"], db_type=data["db_type"],
        host=data["host"], port=int(data["port"]),
        database_name=data["database_name"],
        username=data["username"],
        password_encrypted=pwd_enc,
    )
    return {"status": "ok", "config": result}

@router.get("/database/configs/{config_id}")
def get_db_config(config_id: int):
    """获取单个数据库配置"""
    db = get_db()
    config = db.get_db_config(config_id)
    if not config:
        raise HTTPException(404, "数据库配置不存在")
    # 不返回加密密码
    config.pop("password_encrypted", None)
    return {"config": config}

@router.put("/database/configs/{config_id}")
def update_db_config(config_id: int, data: dict):
    """更新数据库配置"""
    db = get_db()
    existing = db.get_db_config(config_id)
    if not existing:
        raise HTTPException(404, "数据库配置不存在")
    updates = {}
    for k in ("name", "host", "port", "database_name", "username"):
        if k in data:
            updates[k] = data[k]
    if "password" in data and data["password"]:
        updates["password_encrypted"] = _encrypt_pwd(data["password"])
    db.update_db_config(config_id, **updates)
    return {"status": "ok"}

@router.delete("/database/configs/{config_id}")
def delete_db_config(config_id: int):
    """删除数据库配置"""
    db = get_db()
    db.delete_db_config(config_id)
    return {"status": "ok"}

@router.post("/database/configs/{config_id}/test")
def test_db_config(config_id: int):
    """测试数据库连接"""
    db = get_db()
    config = db.get_db_config(config_id)
    if not config:
        raise HTTPException(404, "数据库配置不存在")
    from core.db_tools import db_test_connection
    pwd = _decrypt_pwd(config.get("password_encrypted", ""))
    result = db_test_connection(
        db_type=config["db_type"],
        host=config["host"],
        port=config["port"],
        database=config["database_name"],
        username=config["username"],
        password=pwd,
    )
    ok = "✅" in result or "成功" in result
    return {"status": "ok" if ok else "error", "message": result}


@router.post("/database/configs/{config_id}/scan")
def scan_table_metadata(config_id: int):
    """扫描数据库并保存/更新所有表元数据"""
    db = get_db()
    config = db.get_db_config(config_id)
    if not config:
        raise HTTPException(404, "数据库配置不存在")
    pwd = _decrypt_pwd(config.get("password_encrypted", ""))
    conn_config = {
        "db_type": config["db_type"],
        "host": config["host"],
        "port": config["port"],
        "database": config["database_name"],
        "username": config["username"],
        "password": pwd,
    }
    try:
        from core.db_tools import _create_connection, _mysql_describe_table, _pg_describe_table
        conn = _create_connection(conn_config)
        cursor = conn.cursor()
        db_type = config["db_type"]
        try:
            if db_type == "mysql":
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = DATABASE()")
            else:
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
            all_tables = [r[0] for r in cursor.fetchall()]
        finally:
            cursor.close()
        conn.close()

        saved = 0
        for tn in all_tables:
            conn2 = _create_connection(conn_config)
            try:
                if db_type == "mysql":
                    schema = _mysql_describe_table(conn2, tn)
                else:
                    schema = _pg_describe_table(conn2, tn)
            finally:
                conn2.close()

            # 获取行数
            row_count = 0
            try:
                conn3 = _create_connection(conn_config)
                c3 = conn3.cursor()
                c3.execute(f"SELECT COUNT(*) FROM {tn}")
                row_count = c3.fetchone()[0]
                c3.close()
                conn3.close()
            except Exception:
                pass

            db.save_table_metadata(
                config_id=config_id, table_name=tn,
                columns=schema.get("columns", []),
                primary_keys=schema.get("primary_keys", []),
                foreign_keys=schema.get("foreign_keys", []),
                row_count=row_count,
                table_comment=schema.get("table_comment", ""),
            )
            saved += 1

        return {"status": "ok", "message": f"已扫描 {saved} 个表", "count": saved}
    except Exception as e:
        raise HTTPException(500, f"扫描失败: {str(e)[:200]}")

@router.get("/database/configs/{config_id}/metadata")
def get_table_metadata(config_id: int):
    """获取表元数据列表"""
    db = get_db()
    metas = db.get_table_metadata(config_id, qa_enabled_only=False)
    return {"metadata": metas}

@router.put("/database/metadata/{meta_id}")
def update_table_qa(meta_id: int, data: dict):
    """更新表问答设置"""
    db = get_db()
    qa_enabled = data.get("qa_enabled", 1)
    business_context = data.get("business_context", "")
    db.update_table_qa(meta_id, qa_enabled, business_context)
    return {"status": "ok"}


# ──────────── 智能问数接口 ────────────

class SmartQueryRequest(BaseModel):
    query: str
    config_id: int

@router.post("/smart-query")
def smart_query(req: SmartQueryRequest):
    """执行智能 NL2SQL 查询"""
    from core.smart_query import get_smart_query_service
    if not req.query:
        raise HTTPException(400, "请提供查询内容")
    if not req.config_id:
        raise HTTPException(400, "请选择数据库配置")
    svc = get_smart_query_service()
    result = svc.full_query(req.query, req.config_id)
    return result

@router.post("/smart-query/with-steps")
def smart_query_with_steps(req: SmartQueryRequest):
    """非流式智能问数，返回所有中间步骤 + 最终结果"""
    from core.smart_query import get_smart_query_service
    if not req.query or not req.config_id:
        raise HTTPException(400, "缺少参数")
    svc = get_smart_query_service()
    steps = []
    result = None
    error = None
    for event in svc.full_query_stream(req.query, req.config_id):
        if event["type"] == "result":
            result = event["data"]
        elif event["type"] == "error":
            error = event["message"]
        else:
            steps.append(event)
    return {"steps": steps, "result": result, "error": error}


@router.post("/smart-query/stream")
async def smart_query_stream(req: SmartQueryRequest):
    """流式智能问数（SSE 格式，与主对话一致）"""
    from core.smart_query import get_smart_query_service
    if not req.query or not req.config_id:
        raise HTTPException(400, "缺少参数")

    svc = get_smart_query_service()

    async def generate():
        import asyncio
        queue = asyncio.Queue()

        def run():
            try:
                for event in svc.full_query_stream(req.query, req.config_id):
                    queue.put_nowait(event)
            except Exception as e:
                queue.put_nowait({"type": "error", "message": str(e)})
            finally:
                queue.put_nowait(None)  # 结束信号

        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, run)

        while True:
            event = await queue.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
    )


# ═══════════════════════════════════════════════════════
# 斜杠命令 API
# ═══════════════════════════════════════════════════════


async def _get_adapter():
    from nanobot.adapter import get_adapter
    return await get_adapter()


@router.get("/command/status")
async def cmd_status():
    """系统状态概览"""
    try:
        adapter = await _get_adapter()
        all_names = adapter.tools.tool_names
        mcp_count = sum(1 for n in all_names if n.startswith("mcp_"))
        direct_count = len([n for n in ["create_document", "create_table", "read_document",
                                         "query_knowledge", "analyze_data", "web_search"] if adapter.tools.has(n)])
        lines = [
            "━━━ 科吉系统状态 ━━━━━━━━━━━━━━━━━━━━",
            f"模型: {adapter.model}",
            f"工具总数: {len(all_names)}（直接: {direct_count}, MCP: {mcp_count}）",
            f"最大工具轮次: {adapter.max_iterations}",
        ]
        return {"text": "\n".join(lines)}
    except Exception as e:
        return {"text": f"获取状态失败: {e}"}


@router.get("/command/selfcheck")
async def cmd_selfcheck():
    """运行系统自检"""
    try:
        adapter = await _get_adapter()
        from nanobot.selfcheck.runner import SelfCheckRunner
        runner = SelfCheckRunner(adapter.tools, adapter.project_root, adapter.config)
        report = runner.run()
        return {"text": report.format_text()}
    except Exception as e:
        return {"text": f"自检失败: {e}"}


@router.get("/command/cost")
async def cmd_cost():
    """当前会话 token / 工具使用统计"""
    try:
        adapter = await _get_adapter()
        lines = ["━━━ 会话统计 ━━━━━━━━━━━━━━━━━━━━"]
        sm = adapter.session_manager
        sessions = sm.list_sessions()
        lines.append(f"总会话数: {len(sessions)}")
        lines.append(f"max_tool_rounds: {adapter.max_iterations}")
        lines.append(f"Provider: {type(adapter.provider).__name__} ({adapter.model})")
        return {"text": "\n".join(lines)}
    except Exception as e:
        return {"text": f"获取统计失败: {e}"}


@router.get("/command/tools")
async def cmd_tools():
    """列出所有可用工具（分类）"""
    try:
        adapter = await _get_adapter()
        all_names = sorted(adapter.tools.tool_names)
        groups = {}
        for n in all_names:
            if n.startswith("mcp_quack_"):
                groups.setdefault("DuckDB(SQL)", []).append(n.removeprefix("mcp_quack_"))
            elif n.startswith("mcp_filesystem_"):
                groups.setdefault("文件系统", []).append(n.removeprefix("mcp_filesystem_"))
            elif n.startswith("mcp_"):
                prefix = n.split("_")[1] if len(n.split("_")) > 1 else "other"
                groups.setdefault(f"MCP-{prefix}", []).append("_".join(n.split("_")[2:]) or n)
            elif n == "__tool__":
                continue
            else:
                groups.setdefault("内置工具", []).append(n)
        lines = [f"━━━ 可用工具 ({len(all_names)}) ━━━━━━━━━━━"]
        for cat, tools in groups.items():
            lines.append(f"\n{cat}:")
            for t in tools[:10]:
                lines.append(f"  - {t}")
            if len(tools) > 10:
                lines.append(f"  ... 还有 {len(tools)-10} 个")
        return {"text": "\n".join(lines)}
    except Exception as e:
        return {"text": f"获取工具列表失败: {e}"}


@router.get("/command/knowledge")
async def cmd_knowledge():
    """知识库统计"""
    try:
        from core.database.db import get_db
        from core.rag.vector_store import get_vector_store
        db = get_db()
        docs = db.list_documents()
        vs = get_vector_store()
        count = vs.count()
        lines = [
            "━━━ 知识库统计 ━━━━━━━━━━━━━━━━━━━━",
            f"已索引文档: {len(docs)}",
            f"向量块数: {count}",
        ]
        if docs:
            lines.append("\n最近文档:")
            for d in docs[-5:]:
                lines.append(f"  - {d.get('file_name', d.get('path','?'))}")
        return {"text": "\n".join(lines)}
    except Exception as e:
        return {"text": f"获取知识库统计失败: {e}"}


@router.post("/compact")
async def cmd_compact(req: dict):
    """压缩会话：LLM 总结历史 → 创建新会话"""
    session_id = req.get("session_id", "")
    if not session_id:
        return {"text": "错误: 缺少 session_id", "new_session_id": ""}

    from pathlib import Path
    from nanobot.session.manager import SessionManager
    from core.context_compact import compact_session_new

    sm = SessionManager(Path(__file__).resolve().parent.parent)
    adapter = await _get_adapter()
    return await compact_session_new(sm, session_id, adapter.provider)


# ──────────── Token 统计接口 ────────────

# 模型价格表（人民币 元/百万 tokens）
# 数据来源：各厂商官网 2025年中公开定价
# 缓存命中通常按输入价格的 10% 计费
_MODEL_PRICES: dict[str, dict[str, float]] = {
    # DeepSeek 系列
    "deepseek-v4-flash":  {"input": 1.00, "output": 2.00, "cache_discount": 0.10},
    "deepseek-chat":      {"input": 1.00, "output": 4.00, "cache_discount": 0.10},
    "deepseek-reasoner":  {"input": 4.00, "output": 16.00, "cache_discount": 0.10},
    "deepseek-r1":        {"input": 4.00, "output": 16.00, "cache_discount": 0.10},
    # OpenAI 系列（按 ~7.2 汇率折算）
    "gpt-4o":             {"input": 18.00, "output": 72.00, "cache_discount": 0.50},
    "gpt-4o-mini":        {"input": 1.10, "output": 4.40, "cache_discount": 0.50},
    "gpt-4-turbo":        {"input": 72.00, "output": 216.00, "cache_discount": 0.50},
    "gpt-3.5-turbo":      {"input": 3.60, "output": 10.80, "cache_discount": 0.50},
    # Ollama 本地模型 — 零成本
    # （任何未在表中匹配的模型也默认免费）
}

# 利用 base_url 特征自动判定为本地部署的模型
_LOCAL_PROVIDER_INDICATORS = ("localhost", "127.0.0.1", "0.0.0.0", "[::1]")


def _get_model_pricing() -> tuple[str, dict[str, float] | None]:
    """从 config.yaml 读取当前模型，返回 (model_name, price_dict_or_None)"""
    import yaml
    try:
        config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except Exception:
        return ("unknown", None)

    models_cfg = cfg.get("models", {})
    default_key = models_cfg.get("default", "")
    provider_cfg = models_cfg.get(default_key, {})

    # 本地 ollama 或 base_url 指向本机 → 免费
    base_url = (provider_cfg.get("base_url") or "").lower()
    if default_key == "ollama" or any(ind in base_url for ind in _LOCAL_PROVIDER_INDICATORS):
        return (provider_cfg.get("model", "ollama-local"), None)  # None = 免费

    model_name = provider_cfg.get("model", default_key)
    # 精确匹配优先，否则模糊匹配（模型名包含 key）
    if model_name in _MODEL_PRICES:
        return (model_name, _MODEL_PRICES[model_name])
    for key, prices in _MODEL_PRICES.items():
        if key in model_name:
            return (model_name, prices)
    return (model_name, None)  # 未匹配 → 免费


def _calc_cost(
    prompt_tokens: int, completion_tokens: int, cached_tokens: int, pricing: dict | None
) -> float:
    """根据 token 数量和定价计算花费（人民币 元）"""
    if pricing is None:
        return 0.0
    # 缓存部分 input 打折
    cache_discount = pricing.get("cache_discount", 0.10)
    uncached_input = max(0, prompt_tokens - cached_tokens)
    cached_input = min(prompt_tokens, cached_tokens)
    cost = (
        uncached_input / 1_000_000 * pricing["input"]
        + cached_input / 1_000_000 * pricing["input"] * cache_discount
        + completion_tokens / 1_000_000 * pricing["output"]
    )
    return round(cost, 6)


@router.get("/stats/tokens")
def get_token_stats():
    """聚合所有对话的 token 消耗统计（含费用估算）"""
    from nanobot.session.manager import SessionManager
    from pathlib import Path
    sm = SessionManager(Path(__file__).resolve().parent.parent)

    model_name, pricing = _get_model_pricing()

    total = {"conversations": 0, "prompt_tokens": 0, "completion_tokens": 0,
             "total_tokens": 0, "cached_tokens": 0, "cost": 0.0}
    convs = []

    for info in sm.list_sessions():
        key = info.get("key", "")
        if not key:
            continue
        try:
            data = sm.read_session_file(key)
            if not data:
                continue
        except Exception:
            continue

        msgs = data.get("messages", [])
        if not msgs:
            continue

        # 取第一条 user 消息前 50 字作标题
        title = "新对话"
        for m in msgs:
            if m.get("role") == "user":
                t = m.get("content", "")
                if t:
                    title = t[:50]
                    break

        # 从 assistant 消息中提取 usage（含 cached_tokens）
        c_prompt = 0
        c_completion = 0
        c_total = 0
        c_cached = 0
        for m in msgs:
            if m.get("role") == "assistant" and "usage" in m:
                u = m["usage"]
                if isinstance(u, dict):
                    c_prompt += u.get("prompt_tokens", 0) or 0
                    c_completion += u.get("completion_tokens", 0) or 0
                    c_total += u.get("total_tokens", 0) or 0
                    c_cached += u.get("cached_tokens", 0) or 0

        conv_cost = _calc_cost(c_prompt, c_completion, c_cached, pricing)

        convs.append({
            "id": key,
            "title": title,
            "date": data.get("updated_at") or data.get("created_at") or "",
            "prompt_tokens": c_prompt,
            "completion_tokens": c_completion,
            "total_tokens": c_total,
            "cached_tokens": c_cached,
            "cost": conv_cost,
            "message_count": len(msgs),
        })

        total["conversations"] += 1
        total["prompt_tokens"] += c_prompt
        total["completion_tokens"] += c_completion
        total["total_tokens"] += c_total
        total["cached_tokens"] += c_cached
        total["cost"] += conv_cost

    total["cost"] = round(total["cost"], 4)

    # 按日期倒序
    convs.sort(key=lambda c: c.get("date", ""), reverse=True)

    return {
        "total": total,
        "conversations": convs,
        "model": model_name,
        "is_local": pricing is None,
    }


# ──────────── 技能系统接口 ────────────

# 技能分类映射
SKILL_CATEGORIES = {
    "docx": "文档处理", "pdf": "文档处理", "xlsx": "文档处理", "pptx": "文档处理",
    "doc-coauthoring": "内容创作", "internal-comms": "内容创作", "deck": "内容创作",
    "canvas-design": "设计", "brand-guidelines": "设计", "theme-factory": "设计",
    "algorithmic-art": "设计", "slack-gif-creator": "设计",
    "claude-api": "开发工具", "mcp-builder": "开发工具", "frontend-design": "开发工具",
    "web-artifacts-builder": "开发工具", "webapp-testing": "开发工具",
    "skill-creator": "系统管理",
    # 数据工程技能
    "iceberg": "数据处理", "paimon": "数据处理", "flink": "数据处理",
    "fluss": "数据处理", "lance": "数据处理", "iggy": "数据处理",
    "docker-compose": "数据处理",
}


@router.get("/skills")
def list_skills():
    """列出所有可用技能（含分类和完整指令）"""
    from core.skills import get_registry
    registry = get_registry()
    skills = []
    for s in registry._skills.values():
        skills.append({
            "name": s.name,
            "description": s.description,
            "version": s.version,
            "category": SKILL_CATEGORIES.get(s.name, "其他"),
            "instructions": s.instructions,
            "active": False,
        })
    return {"skills": skills}


@router.get("/skills/{name}")
def get_skill(name: str):
    """获取单个技能详情"""
    from core.skills import get_registry
    skill = get_registry().get_skill(name)
    if not skill:
        raise HTTPException(404, f"技能不存在: {name}")
    return {
        "name": skill.name,
        "description": skill.description,
        "version": skill.version,
        "category": SKILL_CATEGORIES.get(skill.name, "其他"),
        "instructions": skill.instructions,
    }


@router.post("/skills/activate")
async def activate_skill(req: dict):
    """激活一个技能"""
    session_id = req.get("session_id", "")
    skill_name = req.get("skill_name", "")
    if not session_id or not skill_name:
        return {"status": "error", "message": "缺少 session_id 或 skill_name"}

    from core.skills import get_registry
    registry = get_registry()
    if not registry.has_skill(skill_name):
        return {"status": "error", "message": f"技能不存在: {skill_name}"}

    adapter = await _get_adapter()
    if session_id not in adapter._active_skills:
        adapter._active_skills[session_id] = []
    if skill_name not in adapter._active_skills[session_id]:
        adapter._active_skills[session_id].append(skill_name)

    return {"status": "ok", "message": f"已激活技能: {skill_name}", "active_skills": adapter._active_skills[session_id]}


@router.post("/skills/active")
async def get_active_skills(req: dict):
    """查询当前会话已激活的技能（新会话自动填充默认技能）"""
    session_id = req.get("session_id", "")
    if not session_id:
        return {"active_skills": []}
    adapter = await _get_adapter()
    adapter._ensure_default_skills(session_id)
    return {"active_skills": adapter._active_skills.get(session_id, [])}


@router.post("/skills/deactivate")
async def deactivate_skill(req: dict):
    """卸载技能（可指定 skill_name 卸载单个，不指定则卸载全部）"""
    session_id = req.get("session_id", "")
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}
    skill_name = req.get("skill_name", "")

    adapter = await _get_adapter()
    if skill_name:
        skills = adapter._active_skills.get(session_id, [])
        if skill_name in skills:
            skills.remove(skill_name)
            msg = f"已卸载技能: {skill_name}"
        else:
            msg = f"技能未激活: {skill_name}"
    else:
        adapter._active_skills.pop(session_id, None)
        msg = "已卸载所有技能"

    return {"status": "ok", "message": msg}


@router.post("/skills/set")
async def set_active_skills(req: dict):
    """批量设置当前会话的技能（替换全部）"""
    session_id = req.get("session_id", "")
    skills = req.get("skills", [])
    if not session_id:
        return {"status": "error", "message": "缺少 session_id"}
    from core.skills import get_registry
    registry = get_registry()
    valid = [s for s in skills if registry.has_skill(s)]
    adapter = await _get_adapter()
    adapter._active_skills[session_id] = valid
    adapter._skill_notified.pop(session_id, None)  # 清除通知缓存，下次聊天会通知变更
    return {"status": "ok", "active_skills": valid}


# ═══════════════════════════════════════════════════════
# 工具调用统计
# ═══════════════════════════════════════════════════════


@router.get("/stats/tokens")
def token_stats():
    """获取会话 token 消耗概览（按天聚合）"""
    import json as _json
    from nanobot.adapter import load_config
    config = load_config()
    default_model = config.get("models", {}).get("default", "deepseek")
    model_name = config.get("models", {}).get(default_model, {}).get("model", "deepseek-v4-flash")
    is_local = default_model == "ollama"

    sessions_dir = os.path.join(os.path.dirname(__file__), "..", "sessions")
    convs = []
    if os.path.isdir(sessions_dir):
        for fn in sorted(os.listdir(sessions_dir)):
            if not fn.endswith(".jsonl"):
                continue
            fp = os.path.join(sessions_dir, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        msg = _json.loads(line)
                        usage = msg.get("usage") or {}
                        timestamp = msg.get("timestamp", "")
                        date = timestamp[:10] if len(timestamp) >= 10 else ""
                        convs.append({
                            "date": date,
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "total_tokens": usage.get("total_tokens", usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0)),
                            "cached_tokens": usage.get("cached_tokens", 0),
                            "cost": usage.get("cost", 0),
                        })
            except Exception:
                pass

    # 从 database 补充 cost 数据
    try:
        from core.database.db import get_db
        db = get_db()
        cost_sum = db.get_cost_summary()
    except Exception:
        cost_sum = {"all": {"cost": 0}}

    return {
        "conversations": convs,
        "is_local": is_local,
        "model": model_name,
        "total_cost": cost_sum.get("all", {}).get("cost", 0),
    }


@router.get("/stats/tools")
def tool_stats(days: int = Query(7, description="统计天数", ge=1, le=365)):
    """获取工具调用统计（按工具名汇总）"""
    from core.database.db import get_db
    db = get_db()
    stats = db.get_tool_stats(days=days)
    return stats


@router.get("/stats/cost")
def cost_summary():
    """获取今日、本月、全部的成本汇总"""
    from core.database.db import get_db
    db = get_db()
    summary = db.get_cost_summary()
    return summary


@router.get("/stats/session/{session_id}")
def session_cost(session_id: str):
    """获取单个会话的成本"""
    from core.database.db import get_db
    db = get_db()
    cost = db.get_session_cost(session_id)
    return cost

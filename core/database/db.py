import sqlite3
import json
import os
import threading
import time
import uuid
from typing import Optional


# ── 模型计价表（美元 / 1M tokens） ──
MODEL_PRICING = {
    "deepseek-chat":     {"input": 0.27,   "output": 1.10,  "cached_input": 0.07},
    "deepseek-reasoner": {"input": 0.55,   "output": 2.19,  "cached_input": 0.07},
    "deepseek-v4-flash": {"input": 0.14,   "output": 0.55,  "cached_input": 0.014},
    "gpt-4o-mini":       {"input": 0.15,   "output": 0.60,  "cached_input": 0.075},
    "gpt-4o":            {"input": 2.50,   "output": 10.00, "cached_input": 1.25},
    "qwen2.5:7b":        {"input": 0.0,    "output": 0.0,   "cached_input": 0.0},
}


def estimate_tool_cost(
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cached_tokens: int = 0,
) -> float:
    """根据模型单价估算美元费用。未知模型按 deepseek-v4-flash 计。"""
    pricing = MODEL_PRICING.get(model, MODEL_PRICING["deepseek-v4-flash"])
    actual_input = max(0, prompt_tokens - cached_tokens)
    input_cost = actual_input * pricing["input"] / 1_000_000
    cached_cost = cached_tokens * pricing["cached_input"] / 1_000_000
    output_cost = completion_tokens * pricing["output"] / 1_000_000
    return round(input_cost + cached_cost + output_cost, 8)


_db_instance = None
_db_lock = threading.Lock()


def get_db() -> "Database":
    global _db_instance
    if _db_instance is None:
        with _db_lock:
            if _db_instance is None:
                db_path = os.path.join(
                    os.path.dirname(__file__), "..", "..", "data", "keji.db"
                )
                _db_instance = Database(db_path)
    return _db_instance


class Database:
    """SQLite 数据库 —— 持久化存储对话、文档、设置"""

    def __init__(self, db_path: str):
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.db_path = db_path
        self._local = threading.local()
        self._init_tables()

    def _get_conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA foreign_keys=ON")
        return self._local.conn

    def _init_tables(self):
        conn = self._get_conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY,
                title TEXT DEFAULT '新对话',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                message_count INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at REAL NOT NULL,
                FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY,
                file_path TEXT UNIQUE NOT NULL,
                file_name TEXT NOT NULL,
                file_type TEXT NOT NULL,
                file_size INTEGER DEFAULT 0,
                doc_category TEXT DEFAULT 'other',
                content_hash TEXT,
                chunk_count INTEGER DEFAULT 0,
                indexed_at REAL,
                created_at REAL NOT NULL,
                last_accessed_at REAL
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS database_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                db_type TEXT NOT NULL CHECK(db_type IN ('mysql','postgresql')),
                host TEXT NOT NULL,
                port INTEGER NOT NULL,
                database_name TEXT NOT NULL,
                username TEXT NOT NULL,
                password_encrypted TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS table_metadata (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                config_id INTEGER NOT NULL,
                table_name TEXT NOT NULL,
                columns_json TEXT NOT NULL DEFAULT '[]',
                primary_keys_json TEXT NOT NULL DEFAULT '[]',
                foreign_keys_json TEXT NOT NULL DEFAULT '[]',
                row_count INTEGER DEFAULT 0,
                table_comment TEXT DEFAULT '',
                qa_enabled INTEGER DEFAULT 1,
                business_context TEXT DEFAULT '',
                sample_data TEXT DEFAULT '[]',
                created_at REAL NOT NULL,
                updated_at REAL NOT NULL,
                FOREIGN KEY (config_id) REFERENCES database_configs(id) ON DELETE CASCADE,
                UNIQUE(config_id, table_name)
            );

            CREATE INDEX IF NOT EXISTS idx_messages_conv ON messages(conversation_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_documents_path ON documents(file_path);
            CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(file_type);

            -- 工具调用统计
            CREATE TABLE IF NOT EXISTS tool_usage_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL DEFAULT '',
                tool_name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'ok',
                duration_ms INTEGER NOT NULL DEFAULT 0,
                prompt_tokens INTEGER NOT NULL DEFAULT 0,
                completion_tokens INTEGER NOT NULL DEFAULT 0,
                cached_tokens INTEGER NOT NULL DEFAULT 0,
                estimated_cost REAL NOT NULL DEFAULT 0.0,
                model TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_tool_usage_session ON tool_usage_log(session_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_tool_usage_name ON tool_usage_log(tool_name);

            CREATE TABLE IF NOT EXISTS audit_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT NOT NULL,
                actor TEXT NOT NULL DEFAULT 'api',
                session_id TEXT NOT NULL DEFAULT '',
                tool_name TEXT NOT NULL DEFAULT '',
                path TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'ok',
                detail TEXT NOT NULL DEFAULT '',
                client_ip TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_events(created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_type ON audit_events(event_type, created_at);
            CREATE INDEX IF NOT EXISTS idx_audit_path ON audit_events(path);

            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                role TEXT NOT NULL DEFAULT 'member'
                    CHECK(role IN ('admin', 'member', 'readonly')),
                is_active INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                last_login_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
        """)
        conn.commit()
        self._migrate_schema()

    def _migrate_schema(self) -> None:
        conn = self._get_conn()
        cols = {r[1] for r in conn.execute("PRAGMA table_info(conversations)").fetchall()}
        if "owner_user_id" not in cols:
            conn.execute(
                "ALTER TABLE conversations ADD COLUMN owner_user_id TEXT"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_conv_owner "
                "ON conversations(owner_user_id, updated_at)"
            )
            conn.commit()

    # ---- 用户管理 ----

    def count_users(self) -> int:
        row = self._get_conn().execute("SELECT COUNT(*) AS c FROM users").fetchone()
        return int(row["c"]) if row else 0

    def get_user_by_username(self, username: str) -> Optional[dict]:
        row = self._get_conn().execute(
            "SELECT id, username, password_hash, display_name, role, is_active, "
            "created_at, last_login_at FROM users WHERE username = ?",
            (username.strip(),),
        ).fetchone()
        return dict(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        row = self._get_conn().execute(
            "SELECT id, username, password_hash, display_name, role, is_active, "
            "created_at, last_login_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        rows = self._get_conn().execute(
            "SELECT id, username, display_name, role, is_active, created_at, last_login_at "
            "FROM users ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def create_user(
        self,
        username: str,
        password_hash: str,
        role: str = "member",
        display_name: str = "",
    ) -> str:
        uid = uuid.uuid4().hex[:16]
        now = time.time()
        self._get_conn().execute(
            "INSERT INTO users (id, username, password_hash, display_name, role, "
            "is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (uid, username.strip(), password_hash, display_name or username, role, now),
        )
        self._get_conn().commit()
        return uid

    def update_user(
        self,
        user_id: str,
        *,
        display_name: str | None = None,
        role: str | None = None,
        is_active: int | None = None,
        password_hash: str | None = None,
    ) -> bool:
        user = self.get_user_by_id(user_id)
        if not user:
            return False
        fields: list[str] = []
        values: list = []
        if display_name is not None:
            fields.append("display_name = ?")
            values.append(display_name)
        if role is not None:
            fields.append("role = ?")
            values.append(role)
        if is_active is not None:
            fields.append("is_active = ?")
            values.append(int(is_active))
        if password_hash is not None:
            fields.append("password_hash = ?")
            values.append(password_hash)
        if not fields:
            return True
        values.append(user_id)
        self._get_conn().execute(
            f"UPDATE users SET {', '.join(fields)} WHERE id = ?",
            values,
        )
        self._get_conn().commit()
        return True

    def touch_user_login(self, user_id: str) -> None:
        self._get_conn().execute(
            "UPDATE users SET last_login_at = ? WHERE id = ?",
            (time.time(), user_id),
        )
        self._get_conn().commit()

    def user_to_public(self, row: dict) -> dict:
        return {
            "id": row["id"],
            "username": row["username"],
            "display_name": row.get("display_name") or row["username"],
            "role": row["role"],
            "is_active": bool(row.get("is_active", 1)),
            "created_at": row.get("created_at"),
            "last_login_at": row.get("last_login_at"),
        }

    # ---- 对话管理 ----

    def create_conversation(
        self,
        conv_id: str,
        title: str = "新对话",
        owner_user_id: str | None = None,
    ) -> dict:
        now = time.time()
        conn = self._get_conn()
        conn.execute(
            "INSERT OR IGNORE INTO conversations "
            "(id, title, created_at, updated_at, owner_user_id) VALUES (?, ?, ?, ?, ?)",
            (conv_id, title, now, now, owner_user_id),
        )
        if owner_user_id:
            conn.execute(
                "UPDATE conversations SET owner_user_id = ? WHERE id = ? AND owner_user_id IS NULL",
                (owner_user_id, conv_id),
            )
        conn.commit()
        return {"id": conv_id, "title": title, "created_at": now, "owner_user_id": owner_user_id}

    def ensure_conversation_owned(
        self, conv_id: str, owner_user_id: str, title: str = "新对话"
    ) -> dict:
        self.create_conversation(conv_id, title=title, owner_user_id=owner_user_id)
        conv = self.get_conversation(conv_id)
        if conv and title and conv.get("title") in ("新对话", conv_id) and title != "新对话":
            self.rename_conversation(conv_id, title)
        return conv or {"id": conv_id}

    def delete_user(self, user_id: str) -> bool:
        conn = self._get_conn()
        convs = conn.execute(
            "SELECT id FROM conversations WHERE owner_user_id = ?",
            (user_id,),
        ).fetchall()
        for row in convs:
            cid = row["id"]
            conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
            conn.execute("DELETE FROM conversations WHERE id = ?", (cid,))
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True

    def list_conversations(
        self,
        limit: int = 50,
        owner_user_id: str | None = None,
    ) -> list[dict]:
        conn = self._get_conn()
        if owner_user_id is not None:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at, message_count, owner_user_id "
                "FROM conversations WHERE owner_user_id = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (owner_user_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT id, title, created_at, updated_at, message_count, owner_user_id "
                "FROM conversations ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_conversation(self, conv_id: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT id, title, created_at, updated_at, message_count, owner_user_id "
            "FROM conversations WHERE id = ?",
            (conv_id,),
        ).fetchone()
        return dict(row) if row else None

    def conversation_owned_by(self, conv_id: str, user_id: str) -> bool:
        conv = self.get_conversation(conv_id)
        if not conv:
            return True
        owner = conv.get("owner_user_id")
        if not owner:
            return False
        return owner == user_id

    def delete_conversation(self, conv_id: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM messages WHERE conversation_id = ?", (conv_id,))
        conn.execute("DELETE FROM conversations WHERE id = ?", (conv_id,))
        conn.commit()

    def rename_conversation(self, conv_id: str, title: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title, time.time(), conv_id),
        )
        conn.commit()

    def add_message(self, conv_id: str, role: str, content: str):
        now = time.time()
        conn = self._get_conn()
        conn.execute(
            "INSERT INTO messages (conversation_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (conv_id, role, content, now),
        )
        conn.execute(
            "UPDATE conversations SET updated_at = ?, message_count = message_count + 1 WHERE id = ?",
            (now, conv_id),
        )
        conn.commit()

    def get_messages(self, conv_id: str, limit: int = 100) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at ASC LIMIT ?",
            (conv_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ---- 文档管理 ----

    def add_document(
        self,
        doc_id: str,
        file_path: str,
        file_name: str,
        file_type: str,
        file_size: int = 0,
        doc_category: str = "other",
        content_hash: str = "",
        chunk_count: int = 0,
    ) -> bool:
        now = time.time()
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO documents
                   (id, file_path, file_name, file_type, file_size, doc_category,
                    content_hash, chunk_count, indexed_at, created_at, last_accessed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    doc_id, file_path, file_name, file_type, file_size,
                    doc_category, content_hash, chunk_count, now, now, now,
                ),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def remove_document(self, doc_id: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
        conn.commit()

    def remove_document_by_path(self, file_path: str):
        conn = self._get_conn()
        conn.execute("DELETE FROM documents WHERE file_path = ?", (file_path,))
        conn.commit()

    def list_documents(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, file_path, file_name, file_type, file_size, doc_category, chunk_count, indexed_at FROM documents ORDER BY indexed_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_document_by_path(self, file_path: str) -> Optional[dict]:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM documents WHERE file_path = ?", (file_path,)
        ).fetchone()
        return dict(row) if row else None

    def update_document_access(self, doc_id: str):
        conn = self._get_conn()
        conn.execute(
            "UPDATE documents SET last_accessed_at = ? WHERE id = ?",
            (time.time(), doc_id),
        )
        conn.commit()

    def get_document_stats(self) -> dict:
        conn = self._get_conn()
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        chunks = conn.execute("SELECT COALESCE(SUM(chunk_count), 0) FROM documents").fetchone()[
            0
        ]
        by_type = conn.execute(
            "SELECT file_type, COUNT(*) as cnt FROM documents GROUP BY file_type ORDER BY cnt DESC"
        ).fetchall()
        return {
            "total_documents": total,
            "total_chunks": chunks,
            "by_type": [dict(r) for r in by_type],
        }

    # ---- 数据库配置管理 ----

    def create_db_config(self, name: str, db_type: str, host: str, port: int,
                         database_name: str, username: str, password_encrypted: str = "") -> dict:
        now = time.time()
        conn = self._get_conn()
        cur = conn.execute(
            "INSERT INTO database_configs (name, db_type, host, port, database_name, username, password_encrypted, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (name, db_type, host, port, database_name, username, password_encrypted, now, now),
        )
        conn.commit()
        return {"id": cur.lastrowid, "name": name, "db_type": db_type}

    def list_db_configs(self) -> list[dict]:
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT id, name, db_type, host, port, database_name, username, created_at, updated_at FROM database_configs ORDER BY updated_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_db_config(self, config_id: int) -> dict | None:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT * FROM database_configs WHERE id = ?", (config_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_decrypted_db_config(self, config_id: int) -> dict | None:
        """获取数据库配置并解密密码"""
        config = self.get_db_config(config_id)
        if not config:
            return None
        pwd_enc = config.get("password_encrypted", "")
        if pwd_enc:
            try:
                import base64
                from cryptography.fernet import Fernet
                from cryptography.hazmat.primitives import hashes
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                machine_id = __import__("hashlib").md5(__import__("os").environ.get("COMPUTERNAME", "keji").encode()).hexdigest()
                kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=b"keji-db-pwd", iterations=100000)
                key = base64.urlsafe_b64encode(kdf.derive(machine_id.encode()))
                config["password"] = Fernet(key).decrypt(pwd_enc.encode()).decode()
            except Exception:
                config["password"] = pwd_enc
        else:
            config["password"] = ""
        config.pop("password_encrypted", None)
        return config

    def update_db_config(self, config_id: int, **kwargs):
        fields = {k: v for k, v in kwargs.items() if k in ("name", "host", "port", "database_name", "username", "password_encrypted")}
        if not fields:
            return
        fields["updated_at"] = time.time()
        sets = ", ".join(f"{k} = ?" for k in fields)
        conn = self._get_conn()
        conn.execute(f"UPDATE database_configs SET {sets} WHERE id = ?", (*fields.values(), config_id))
        conn.commit()

    def delete_db_config(self, config_id: int):
        conn = self._get_conn()
        conn.execute("DELETE FROM table_metadata WHERE config_id = ?", (config_id,))
        conn.execute("DELETE FROM database_configs WHERE id = ?", (config_id,))
        conn.commit()

    # ---- 表元数据管理 ----

    def save_table_metadata(self, config_id: int, table_name: str, columns: list,
                            primary_keys: list, foreign_keys: list, row_count: int = 0,
                            table_comment: str = "", sample_data: list = None) -> bool:
        now = time.time()
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO table_metadata
                   (config_id, table_name, columns_json, primary_keys_json, foreign_keys_json,
                    row_count, table_comment, sample_data, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (config_id, table_name,
                 json.dumps(columns, ensure_ascii=False),
                 json.dumps(primary_keys, ensure_ascii=False),
                 json.dumps(foreign_keys, ensure_ascii=False),
                 row_count, table_comment,
                 json.dumps(sample_data or [], ensure_ascii=False),
                 now, now),
            )
            conn.commit()
            return True
        except Exception:
            return False

    def get_table_metadata(self, config_id: int, qa_enabled_only: bool = True) -> list[dict]:
        conn = self._get_conn()
        if qa_enabled_only:
            rows = conn.execute(
                "SELECT * FROM table_metadata WHERE config_id = ? AND qa_enabled = 1 ORDER BY table_name",
                (config_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM table_metadata WHERE config_id = ? ORDER BY table_name",
                (config_id,),
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["columns"] = json.loads(d.pop("columns_json", "[]"))
            except Exception:
                d["columns"] = []
            try:
                d["primary_keys"] = json.loads(d.pop("primary_keys_json", "[]"))
            except Exception:
                d["primary_keys"] = []
            try:
                d["foreign_keys"] = json.loads(d.pop("foreign_keys_json", "[]"))
            except Exception:
                d["foreign_keys"] = []
            try:
                d["sample_data"] = json.loads(d.pop("sample_data", "[]"))
            except Exception:
                d["sample_data"] = []
            result.append(d)
        return result

    def update_table_qa(self, meta_id: int, qa_enabled: int, business_context: str = ""):
        conn = self._get_conn()
        conn.execute(
            "UPDATE table_metadata SET qa_enabled = ?, business_context = ?, updated_at = ? WHERE id = ?",
            (qa_enabled, business_context, time.time(), meta_id),
        )
        conn.commit()

    def delete_table_metadata(self, config_id: int):
        conn = self._get_conn()
        conn.execute("DELETE FROM table_metadata WHERE config_id = ?", (config_id,))
        conn.commit()

    # ---- 设置管理 ----

    def get_setting(self, key: str, default: str = "") -> str:
        conn = self._get_conn()
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return row[0] if row else default

    def set_setting(self, key: str, value: str):
        conn = self._get_conn()
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (key, value, time.time()),
        )
        conn.commit()

    def get_all_settings(self) -> dict:
        conn = self._get_conn()
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
        return {r["key"]: r["value"] for r in rows}

    # ═══════════════════════════════════════════════════════
    # 工具调用统计
    # ═══════════════════════════════════════════════════════

    def log_tool_usage(
        self,
        session_id: str,
        turn_id: str,
        tool_name: str,
        status: str = "ok",
        duration_ms: int = 0,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cached_tokens: int = 0,
        estimated_cost: float = 0.0,
        model: str = "",
    ):
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO tool_usage_log
               (session_id, turn_id, tool_name, status, duration_ms,
                prompt_tokens, completion_tokens, cached_tokens,
                estimated_cost, model, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, turn_id, tool_name, status, duration_ms,
             prompt_tokens, completion_tokens, cached_tokens,
             estimated_cost, model, time.time()),
        )
        conn.commit()

    def get_tool_stats(self, days: int = 7) -> dict:
        """获取指定天数内的工具调用统计"""
        cutoff = time.time() - days * 86400
        conn = self._get_conn()

        # 按工具名汇总
        by_tool = conn.execute(
            """SELECT tool_name,
                      COUNT(*) as call_count,
                      SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as success_count,
                      SUM(CASE WHEN status!='ok' THEN 1 ELSE 0 END) as error_count,
                      ROUND(AVG(duration_ms)) as avg_duration_ms,
                      SUM(estimated_cost) as total_cost,
                      SUM(prompt_tokens) as total_prompt,
                      SUM(completion_tokens) as total_completion,
                      SUM(cached_tokens) as total_cached
               FROM tool_usage_log
               WHERE created_at >= ?
               GROUP BY tool_name
               ORDER BY call_count DESC""",
            (cutoff,),
        ).fetchall()

        # 总体
        totals = conn.execute(
            """SELECT COUNT(*) as total_calls,
                      SUM(CASE WHEN status='ok' THEN 1 ELSE 0 END) as success_count,
                      SUM(CASE WHEN status!='ok' THEN 1 ELSE 0 END) as error_count,
                      ROUND(AVG(duration_ms)) as avg_duration_ms,
                      SUM(estimated_cost) as total_cost,
                      SUM(prompt_tokens) as total_prompt,
                      SUM(completion_tokens) as total_completion,
                      SUM(cached_tokens) as total_cached
               FROM tool_usage_log
               WHERE created_at >= ?""",
            (cutoff,),
        ).fetchone()

        return {
            "by_tool": [dict(r) for r in by_tool],
            "totals": dict(totals) if totals else {},
        }

    def get_cost_summary(self) -> dict:
        """获取今日、本月、全部的成本汇总"""
        conn = self._get_conn()
        now = time.time()
        today_start = int(time.mktime(time.strptime(time.strftime("%Y-%m-%d 00:00:00"), "%Y-%m-%d %H:%M:%S")))
        month_start = int(time.mktime(time.strptime(time.strftime("%Y-%m-01 00:00:00"), "%Y-%m-%d %H:%M:%S")))

        def _sum_cost(since: float) -> dict:
            row = conn.execute(
                """SELECT COUNT(*) as calls,
                          COALESCE(SUM(estimated_cost), 0) as cost,
                          COALESCE(SUM(prompt_tokens), 0) as prompt,
                          COALESCE(SUM(completion_tokens), 0) as completion,
                          COALESCE(SUM(cached_tokens), 0) as cached
                   FROM tool_usage_log WHERE created_at >= ?""",
                (since,),
            ).fetchone()
            return dict(row) if row else {"calls": 0, "cost": 0.0, "prompt": 0, "completion": 0, "cached": 0}

        return {
            "today": _sum_cost(today_start),
            "month": _sum_cost(month_start),
            "all": _sum_cost(0),
        }

    def get_session_cost(self, session_id: str) -> dict:
        """获取单个会话的成本"""
        conn = self._get_conn()
        row = conn.execute(
            """SELECT COUNT(*) as calls,
                      COALESCE(SUM(estimated_cost), 0) as cost,
                      COALESCE(SUM(prompt_tokens), 0) as prompt,
                      COALESCE(SUM(completion_tokens), 0) as completion
               FROM tool_usage_log WHERE session_id = ?""",
            (session_id,),
        ).fetchone()
        return dict(row) if row else {"calls": 0, "cost": 0.0, "prompt": 0, "completion": 0}

    # ═══════════════════════════════════════════════════════
    # 审计日志
    # ═══════════════════════════════════════════════════════

    def log_audit_event(
        self,
        event_type: str,
        actor: str = "api",
        session_id: str = "",
        tool_name: str = "",
        path: str = "",
        action: str = "",
        status: str = "ok",
        detail: str = "",
        client_ip: str = "",
    ) -> None:
        conn = self._get_conn()
        conn.execute(
            """INSERT INTO audit_events
               (event_type, actor, session_id, tool_name, path, action,
                status, detail, client_ip, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (event_type, actor, session_id, tool_name, path, action,
             status, detail[:2000], client_ip, time.time()),
        )
        conn.commit()

    def list_audit_events(
        self,
        *,
        event_type: str = "",
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict]:
        conn = self._get_conn()
        sql = "SELECT * FROM audit_events WHERE 1=1"
        params: list = []
        if event_type:
            sql += " AND event_type = ?"
            params.append(event_type)
        sql += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = conn.execute(sql, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            if d.get("created_at"):
                d["created_at"] = time.strftime(
                    "%Y-%m-%d %H:%M:%S", time.localtime(d["created_at"])
                )
            result.append(d)
        return result

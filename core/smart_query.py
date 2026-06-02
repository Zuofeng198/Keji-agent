"""智能问数服务 — NL2SQL 全流程编排

管线：
1. 读取数据库配置 → 连接数据库
2. 读取保存的表元数据（仅启用问答的表）
3. LLM 智能选择相关表
4. LLM 根据表结构生成 SQL
5. 执行 SQL 查询
6. LLM 生成数据总结
7. 返回结构化结果
"""

import json
import logging
import os
import sys
from typing import Optional

from core.logger import setup_logger

logger = setup_logger("keji.smart_query")


def _get_model():
    """获取模型适配器"""
    from core.models import ModelRouter
    import yaml
    config_path = os.path.join(os.path.dirname(__file__), "..", "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    # 从数据库读取动态模型配置
    try:
        from core.database.db import get_db
        db = get_db()
        model_type = db.get_setting("model_type", "")
        if model_type in ("ollama", "openai"):
            config.setdefault("models", {})["default"] = model_type
            if model_type == "ollama":
                oc = config.setdefault("models", {}).setdefault("ollama", {})
                url = db.get_setting("ollama_url", "")
                if url:
                    oc["base_url"] = url
                m = db.get_setting("chat_model", "")
                if m:
                    oc["model"] = m
            elif model_type == "openai":
                oc = config.setdefault("models", {}).setdefault("openai", {})
                url = db.get_setting("openai_base_url", "")
                if url:
                    oc["base_url"] = url
                key = db.get_setting("openai_api_key", "")
                if key:
                    oc["api_key"] = key
                m = db.get_setting("openai_model", "")
                if m:
                    oc["model"] = m
    except Exception:
        pass
    router = ModelRouter(config)
    return router.get()


def _build_schema_text(table_metas: list[dict]) -> str:
    """将表元数据列表构建为结构化的 schema 文本"""
    parts = []
    for meta in table_metas:
        lines = [f"表名: {meta['table_name']}"]
        if meta.get("table_comment"):
            lines.append(f"  表描述: {meta['table_comment']}")
        if meta.get("business_context"):
            lines.append(f"  业务说明: {meta['business_context']}")
        lines.append("  字段:")
        for col in meta.get("columns", []):
            nullable = "NULL" if col.get("is_nullable") else "NOT NULL"
            comment = f" — {col.get('comment', '')}" if col.get('comment') else ""
            lines.append(f"    {col['column_name']} ({col['data_type']}) {nullable}{comment}")
        if meta.get("primary_keys"):
            lines.append(f"  主键: {', '.join(meta['primary_keys'])}")
        if meta.get("foreign_keys"):
            lines.append("  外键:")
            for fk in meta["foreign_keys"]:
                lines.append(f"    {fk.get('column', '')} → {fk.get('ref_table', '')}.{fk.get('ref_column', '')}")
        if meta.get("row_count", 0) > 0:
            lines.append(f"  数据量: 约 {meta['row_count']} 行")
        parts.append("\n".join(lines))
    return "\n\n---\n\n".join(parts)


class SmartQueryService:
    """智能问数服务"""

    def __init__(self):
        self.model = None

    def _ensure_model(self):
        if self.model is None:
            self.model = _get_model()

    def select_tables(self, user_query: str, table_metas: list[dict]) -> list[str]:
        """LLM 根据用户问题选择相关表"""
        self._ensure_model()
        if len(table_metas) == 1:
            return [table_metas[0]["table_name"]]

        schema_text = _build_schema_text(table_metas)

        prompt = f"""你是一个数据库分析师。请根据用户的问题和可用的表结构，选择查询所需的表。

用户问题: {user_query}

可用的表信息:
{schema_text}

请分析用户问题，选择相关的表。如果涉及多表关联查询，选择所有需要的表。
只返回表名，多个用逗号分隔，不要任何其他文字。
例如: users
例如: orders,users,products"""

        try:
            resp = self.model.chat([{"role": "user", "content": prompt}], temperature=0.1)
            selected = [t.strip() for t in resp.strip().split(",") if t.strip()]
            valid_names = {m["table_name"] for m in table_metas}
            valid = [t for t in selected if t in valid_names]
            if valid:
                return valid
            # 回退：返回第一个表
            return [table_metas[0]["table_name"]]
        except Exception as e:
            logger.warning(f"Select tables failed: {e}")
            return [table_metas[0]["table_name"]]

    def generate_sql(self, user_query: str, table_metas: list[dict]) -> str:
        """LLM 根据表结构生成 SQL"""
        self._ensure_model()
        schema_text = _build_schema_text(table_metas)

        prompt = f"""你是一个 SQL 专家。请根据表结构和用户问题，生成对应的 SQL 查询语句。

表结构:
{schema_text}

用户问题: {user_query}

要求:
1. 只输出 SQL 语句，不要任何解释
2. 如果需要关联多表，使用合适的 JOIN
3. 字段来源明确，必要时使用表名前缀
4. 使用标准的 SQL 语法（兼容 MySQL 和 PostgreSQL 通用语法）
5. 不要包含 ```sql 代码块标记"""

        try:
            resp = self.model.chat([{"role": "user", "content": prompt}], temperature=0.1)
            sql = resp.strip()
            # 清理可能的代码块标记
            if sql.startswith("```"):
                sql = sql.split("\n", 1)[-1] if "\n" in sql else sql[3:]
            if sql.endswith("```"):
                sql = sql[:-3]
            # 去掉可能的 sql 前缀
            if sql.upper().startswith("SQL"):
                sql = sql[3:].strip()
            return sql.strip()
        except Exception as e:
            logger.error(f"Generate SQL failed: {e}")
            return f"SELECT * FROM {table_metas[0]['table_name']} LIMIT 10"

    def generate_summary(self, user_query: str, query_result: dict) -> str:
        """LLM 对查询结果生成自然语言总结"""
        self._ensure_model()
        rows = query_result.get("data", [])
        columns = query_result.get("columns", [])
        sql = query_result.get("sql", "")

        # 截取前几行作为示例
        sample = str(rows[:5]) if rows else "无数据"

        prompt = f"""你是一个数据分析师。请根据用户问题、SQL 和查询结果，用一段简洁的中文总结回答用户。

用户问题: {user_query}
查询 SQL: {sql}
返回列: {', '.join(columns)}
返回行数: {len(rows)}
数据示例: {sample[:1000]}

请基于以上真实数据，用 3-5 句中文给用户一个清晰的数据分析总结。"""

        try:
            resp = self.model.chat([{"role": "user", "content": prompt}], temperature=0.3)
            return resp.strip()
        except Exception as e:
            return f"查询完成，共返回 {len(rows)} 条记录。"

    def full_query(self, user_query: str, config_id: int) -> dict:
        """执行完整 NL2SQL 查询"""
        from core.database.db import get_db
        from core.db_tools import db_get_tables_list, db_get_schema_full
        import uuid

        db = get_db()
        config = db.get_decrypted_db_config(config_id)
        if not config:
            return {"success": False, "error": "数据库配置不存在"}

        conn_config = {
            "db_type": config["db_type"],
            "host": config["host"],
            "port": config["port"],
            "database": config["database_name"],
            "username": config["username"],
            "password": config.get("password", ""),
        }

        # 1. 读取已保存的表元数据（仅启用问答的表）
        table_metas = db.get_table_metadata(config_id, qa_enabled_only=True)

        # 如果还没有元数据，从数据库抓取
        if not table_metas:
            # 从数据库实时抓取表结构
            try:
                from core.db_tools import _create_connection
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

                for tn in all_tables:
                    conn2 = _create_connection(conn_config)
                    try:
                        if db_type == "mysql":
                            from core.db_tools import _mysql_describe_table
                            schema = _mysql_describe_table(conn2, tn)
                        else:
                            from core.db_tools import _pg_describe_table
                            schema = _pg_describe_table(conn2, tn)
                    finally:
                        conn2.close()

                    db.save_table_metadata(
                        config_id=config_id,
                        table_name=tn,
                        columns=schema.get("columns", []),
                        primary_keys=schema.get("primary_keys", []),
                        foreign_keys=schema.get("foreign_keys", []),
                        table_comment=schema.get("table_comment", ""),
                    )
                table_metas = db.get_table_metadata(config_id, qa_enabled_only=True)
            except Exception as e:
                return {"success": False, "error": f"读取表结构失败: {str(e)}"}

        if not table_metas:
            return {"success": False, "error": "没有可用表，请先在数据库管理中收集表元数据"}

        # 2. LLM 选择相关表
        target_tables = self.select_tables(user_query, table_metas)
        target_metas = [m for m in table_metas if m["table_name"] in target_tables]

        # 3. LLM 生成 SQL
        sql = self.generate_sql(user_query, target_metas)

        # 4. 执行 SQL
        try:
            from core.db_tools import _create_connection
            conn = _create_connection(conn_config)
            cursor = conn.cursor()
            try:
                # 自动加 LIMIT 保护
                final_sql = sql
                if "LIMIT" not in final_sql.upper() and final_sql.strip().upper().startswith("SELECT"):
                    final_sql = final_sql.rstrip(";") + " LIMIT 200"

                cursor.execute(final_sql)
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows_data = cursor.fetchall()
                    data = []
                    for row in rows_data:
                        row_dict = {}
                        for i, v in enumerate(row):
                            if i < len(columns):
                                if isinstance(v, (int, float, str, bool)):
                                    row_dict[columns[i]] = v
                                elif v is None:
                                    row_dict[columns[i]] = None
                                else:
                                    row_dict[columns[i]] = str(v)
                        data.append(row_dict)
                else:
                    columns = []
                    data = []
                    rows_data = []
            finally:
                cursor.close()
                conn.close()

            query_result = {
                "success": True,
                "data": data,
                "columns": columns,
                "row_count": len(data),
                "sql": final_sql,
            }
        except Exception as e:
            return {"success": False, "error": f"SQL 执行失败: {str(e)}", "generated_sql": sql}

        # 5. LLM 生成总结
        summary = self.generate_summary(user_query, query_result)

        return {
            "success": True,
            "data": {
                "data": query_result["data"],
                "columns": query_result["columns"],
                "total": query_result["row_count"],
                "generated_sql": query_result["sql"],
                "summary": summary,
                "table_names": target_tables,
            },
        }

    def full_query_stream(self, user_query: str, config_id: int):
        """流式推送完整 NL2SQL 查询的每一步"""
        events = []

        def emit(step: str, status: str, message: str, details: dict = None):
            ev = {"type": "step", "step": step, "status": status, "message": message}
            if details:
                ev["details"] = details
            events.append(ev)
            return ev

        try:
            from core.database.db import get_db
            db = get_db()
            config = db.get_decrypted_db_config(config_id)
            if not config:
                yield emit("error", "failed", "数据库配置不存在")
                return

            conn_config = {
                "db_type": config["db_type"],
                "host": config["host"],
                "port": config["port"],
                "database": config["database_name"],
                "username": config["username"],
                "password": config.get("password", ""),
            }

            yield emit("connect", "running", "正在连接数据库...")

            try:
                from core.db_tools import _create_connection
                conn = _create_connection(conn_config)
                conn.close()
            except Exception as e:
                yield emit("connect", "failed", f"数据库连接失败: {str(e)}")
                yield {"type": "error", "message": str(e)}
                return

            yield emit("connect", "completed", f"已连接到 {config['database_name']}")

            yield emit("metadata", "running", "正在读取表元数据...")
            table_metas = db.get_table_metadata(config_id, qa_enabled_only=True)

            if not table_metas:
                yield emit("metadata", "failed", "没有启用问答的表，请先在数据库管理中启用")
                yield {"type": "error", "message": "无可用表，请先收集表元数据"}
                return

            yield emit("metadata", "completed", f"已读取 {len(table_metas)} 个启用问答的表")

            # LLM 选表
            yield emit("select_tables", "running", "正在分析需要查询的表...")
            target_tables = self.select_tables(user_query, table_metas)
            yield emit("select_tables", "completed", f"已选择相关表: {', '.join(target_tables)}")

            # LLM 生成SQL
            target_metas = [m for m in table_metas if m["table_name"] in target_tables]
            yield emit("generate_sql", "running", "正在根据表结构生成 SQL...")
            sql = self.generate_sql(user_query, target_metas)
            yield emit("generate_sql", "completed", "SQL 生成成功", {"sql": sql})

            # 执行SQL
            yield emit("execute", "running", "正在执行 SQL 查询...")
            conn = _create_connection(conn_config)
            cursor = conn.cursor()
            try:
                final_sql = sql
                if "LIMIT" not in final_sql.upper() and final_sql.strip().upper().startswith("SELECT"):
                    final_sql = final_sql.rstrip(";") + " LIMIT 200"
                cursor.execute(final_sql)
                if cursor.description:
                    columns = [desc[0] for desc in cursor.description]
                    rows_data = cursor.fetchall()
                    data = []
                    for row in rows_data:
                        row_dict = {}
                        for i, v in enumerate(row):
                            if i < len(columns):
                                if isinstance(v, (int, float, str, bool)):
                                    row_dict[columns[i]] = v
                                elif v is None:
                                    row_dict[columns[i]] = None
                                else:
                                    row_dict[columns[i]] = str(v)
                        data.append(row_dict)
                else:
                    columns, data = [], []
            finally:
                cursor.close()
                conn.close()

            yield emit("execute", "completed", f"查询成功，返回 {len(data)} 条记录")

            query_result = {
                "data": data, "columns": columns,
                "row_count": len(data), "sql": final_sql,
            }

            # AI 总结
            yield emit("summary", "running", "正在生成数据总结...")
            summary = self.generate_summary(user_query, query_result)
            yield emit("summary", "completed", "总结完成")

            # 最终结果
            yield {"type": "result", "data": {
                "data": data, "columns": columns, "total": len(data),
                "generated_sql": final_sql, "summary": summary,
                "table_names": target_tables,
            }}

        except Exception as e:
            logger.error(f"Smart query error: {e}")
            yield {"type": "error", "message": str(e)}


# 全局单例
_smart_query_service: Optional[SmartQueryService] = None


def get_smart_query_service() -> SmartQueryService:
    global _smart_query_service
    if _smart_query_service is None:
        _smart_query_service = SmartQueryService()
    return _smart_query_service

import hashlib
import os
import time
import uuid
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable

from core.document.parser import (
    parse_document, get_file_type, get_doc_category,
    chunk_text, is_supported, get_file_metadata,
)
from core.database.db import get_db
from core.rag.vector_store import get_vector_store
from core.logger import setup_logger

logger = setup_logger("keji.indexer")

_index_executor = ThreadPoolExecutor(max_workers=4)


class FileIndexer:
    """文件索引器 —— 扫描文件并索引到知识库"""

    def __init__(self):
        self._indexing = set()
        self._cancel_flags = {}
        self._lock = threading.Lock()

    def is_indexing(self, path: str = "") -> bool:
        if path:
            return path in self._indexing
        return len(self._indexing) > 0

    def cancel_indexing(self, path: str = ""):
        with self._lock:
            if path:
                self._cancel_flags[path] = True
            else:
                for p in list(self._indexing):
                    self._cancel_flags[p] = True

    def index_file(
        self,
        file_path: str,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        progress_callback: Optional[Callable] = None,
    ) -> Optional[dict]:
        """索引单个文件"""
        abs_path = os.path.abspath(file_path)

        if not os.path.isfile(abs_path):
            logger.warning("File not found: %s", abs_path)
            return None

        if not is_supported(abs_path):
            return None

        try:
            # 计算文件哈希
            hasher = hashlib.md5()
            with open(abs_path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    hasher.update(chunk)
            content_hash = hasher.hexdigest()

            # 检查是否已索引（内容未变）
            db = get_db()
            existing = db.get_document_by_path(abs_path)
            if existing and existing.get("content_hash") == content_hash:
                logger.debug("Skipping unchanged: %s", abs_path)
                return existing

            # 解析文档
            content = parse_document(abs_path)
            if not content:
                logger.warning("Could not parse: %s", abs_path)
                return None

            # 分块
            chunks = chunk_text(content, chunk_size, chunk_overlap)
            if not chunks:
                return None

            # 生成文档 ID
            doc_id = uuid.uuid5(uuid.NAMESPACE_URL, abs_path).hex[:16]
            file_name = os.path.basename(abs_path)
            file_type = get_file_type(abs_path)
            doc_category = get_doc_category(abs_path)
            file_size = os.path.getsize(abs_path)

            # 先删除旧的向量
            vs = get_vector_store()
            vs.delete_document(doc_id)

            # 添加新向量
            metadatas = [
                {
                    "doc_id": doc_id,
                    "file_path": abs_path,
                    "file_name": file_name,
                    "chunk_index": i,
                    "file_type": file_type,
                    "category": doc_category,
                }
                for i in range(len(chunks))
            ]
            vs.add_document(doc_id, chunks, metadatas)

            # 保存到数据库
            db.add_document(
                doc_id=doc_id,
                file_path=abs_path,
                file_name=file_name,
                file_type=file_type,
                file_size=file_size,
                doc_category=doc_category,
                content_hash=content_hash,
                chunk_count=len(chunks),
            )

            logger.info("Indexed: %s (%d chunks)", file_name, len(chunks))

            if progress_callback:
                progress_callback(abs_path, "ok")

            return {
                "doc_id": doc_id,
                "file_path": abs_path,
                "file_name": file_name,
                "chunk_count": len(chunks),
            }

        except Exception as e:
            logger.error("Index error: %s -> %s", abs_path, e)
            return None

    def index_directory(
        self,
        dir_path: str,
        recursive: bool = True,
        chunk_size: int = 500,
        chunk_overlap: int = 100,
        progress_callback: Optional[Callable] = None,
    ) -> dict:
        """扫描并索引整个目录"""
        abs_path = os.path.abspath(dir_path)
        if not os.path.isdir(abs_path):
            return {"total": 0, "success": 0, "failed": 0, "files": []}

        with self._lock:
            self._indexing.add(abs_path)
            self._cancel_flags[abs_path] = False

        results = {"total": 0, "success": 0, "failed": 0, "files": []}
        files_to_index = []

        # 收集所有文件
        if recursive:
            for root, _, files in os.walk(abs_path):
                for f in files:
                    file_path = os.path.join(root, f)
                    if is_supported(file_path):
                        files_to_index.append(file_path)
        else:
            for f in os.listdir(abs_path):
                file_path = os.path.join(abs_path, f)
                if os.path.isfile(file_path) and is_supported(file_path):
                    files_to_index.append(file_path)

        results["total"] = len(files_to_index)

        # 并行索引
        futures = {}
        for file_path in files_to_index:
            future = _index_executor.submit(
                self._index_single,
                file_path, chunk_size, chunk_overlap, abs_path,
            )
            futures[future] = file_path

        for future in as_completed(futures):
            # 检查取消
            with self._lock:
                if self._cancel_flags.get(abs_path):
                    break

            file_path = futures[future]
            try:
                result = future.result()
                if result:
                    results["success"] += 1
                    results["files"].append(result)
                else:
                    results["failed"] += 1
            except Exception as e:
                logger.error("Index worker error: %s", e)
                results["failed"] += 1

            if progress_callback:
                progress_callback(file_path, "done")

        with self._lock:
            self._indexing.discard(abs_path)
            self._cancel_flags.pop(abs_path, None)

        return results

    def _index_single(
        self, file_path: str, chunk_size: int, chunk_overlap: int, task_id: str
    ) -> Optional[dict]:
        with self._lock:
            if self._cancel_flags.get(task_id):
                return None
        return self.index_file(file_path, chunk_size, chunk_overlap)

    def remove_from_index(self, file_path: str):
        """从索引中移除文件"""
        db = get_db()
        doc = db.get_document_by_path(file_path)
        if doc:
            vs = get_vector_store()
            vs.delete_document(doc["id"])
            db.remove_document(doc["id"])
            logger.info("Removed from index: %s", file_path)

    def get_stats(self) -> dict:
        """获取索引统计"""
        db = get_db()
        vs = get_vector_store()
        doc_stats = db.get_document_stats()
        return {
            **doc_stats,
            "vector_count": vs.count(),
        }


_indexer_instance: Optional[FileIndexer] = None


def get_indexer() -> FileIndexer:
    global _indexer_instance
    if _indexer_instance is None:
        _indexer_instance = FileIndexer()
    return _indexer_instance

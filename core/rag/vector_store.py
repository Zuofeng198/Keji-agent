import os
import threading
from typing import Optional

import chromadb
from chromadb.config import Settings as ChromaSettings

from core.rag.embeddings import EmbeddingManager


_vector_store_instance: Optional["VectorStore"] = None
_vs_lock = threading.Lock()


def get_vector_store() -> "VectorStore":
    global _vector_store_instance
    if _vector_store_instance is None:
        with _vs_lock:
            if _vector_store_instance is None:
                persist_dir = os.path.join(
                    os.path.dirname(__file__), "..", "..", "data", "vector_db"
                )
                _vector_store_instance = VectorStore(persist_dir)
    return _vector_store_instance


class VectorStore:
    """向量存储 —— 基于 ChromaDB 的文档向量检索"""

    def __init__(self, persist_dir: str):
        os.makedirs(persist_dir, exist_ok=True)
        self.persist_dir = persist_dir

        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )

        self._embedding_fn = EmbeddingManager.get_instance().get_ollama()
        self.collection = self.client.get_or_create_collection(
            name="keji_documents",
            embedding_function=self._embedding_fn,
            metadata={"hnsw:space": "cosine"},
        )

    def add_document(
        self,
        doc_id: str,
        chunks: list[str],
        metadatas: Optional[list[dict]] = None,
        chunk_ids: Optional[list[str]] = None,
    ):
        if not chunks:
            return

        if chunk_ids is None:
            chunk_ids = [f"{doc_id}_{i}" for i in range(len(chunks))]

        if metadatas is None:
            metadatas = [{"doc_id": doc_id} for _ in chunks]
        else:
            for m in metadatas:
                m.setdefault("doc_id", doc_id)

        self.collection.add(
            documents=chunks,
            metadatas=metadatas,
            ids=chunk_ids,
        )

    def search(
        self, query: str, n_results: int = 5, filter_doc_id: Optional[str] = None
    ) -> list[dict]:
        # 手动计算查询向量，避免 ChromaDB query_texts 的兼容问题
        query_emb = self._embedding_fn.embed_query(query)
        kwargs = {
            "query_embeddings": [query_emb],
            "n_results": n_results,
        }
        if filter_doc_id:
            kwargs["where"] = {"doc_id": filter_doc_id}

        results = self.collection.query(**kwargs)

        items = []
        if results["ids"] and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "score": results["distances"][0][i] if results.get("distances") else 0,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                })
        return items

    def delete_document(self, doc_id: str):
        self.collection.delete(where={"doc_id": doc_id})

    def delete_by_ids(self, ids: list[str]):
        self.collection.delete(ids=ids)

    def count(self) -> int:
        return self.collection.count()

    def get_document_chunks(self, doc_id: str) -> list[dict]:
        results = self.collection.get(where={"doc_id": doc_id})
        if not results["ids"]:
            return []
        items = []
        for i in range(len(results["ids"])):
            items.append({
                "id": results["ids"][i],
                "content": results["documents"][i],
                "metadata": results["metadatas"][i] if results.get("metadatas") else {},
            })
        return items

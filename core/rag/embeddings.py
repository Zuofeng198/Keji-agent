import requests
import json
from typing import Optional


class OllamaEmbedding:
    """通过 Ollama API 生成文本嵌入向量"""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: int = 3,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def name(self) -> str:
        return f"ollama_{self.model}"

    def __call__(self, input: list[str]) -> list[list[float]]:
        if isinstance(input, str):
            texts = [input]
        else:
            texts = input
        return self.embed_documents(texts)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        results = []
        for text in texts:
            try:
                resp = requests.post(
                    f"{self.base_url}/api/embeddings",
                    json={"model": self.model, "prompt": text},
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                embedding = resp.json().get("embedding", [])
                results.append(embedding)
            except Exception as e:
                print(f"Embedding error: {e}")
                results.append([0.0] * 768)
        return results

    def embed_query(self, input: str) -> list[float]:
        try:
            resp = requests.post(
                f"{self.base_url}/api/embeddings",
                json={"model": self.model, "prompt": input},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            return resp.json().get("embedding", [])
        except Exception as e:
            print(f"Query embedding error: {e}")
            return [0.0] * 768


class EmbeddingManager:
    """嵌入管理器 —— 支持多种嵌入方式"""

    _instance: Optional["EmbeddingManager"] = None

    @classmethod
    def get_instance(cls) -> "EmbeddingManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._ollama: Optional[OllamaEmbedding] = None

    def get_ollama(
        self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text"
    ) -> OllamaEmbedding:
        if self._ollama is None:
            self._ollama = OllamaEmbedding(base_url, model)
        return self._ollama

    def check_ollama_available(self, base_url: str = "http://localhost:11434") -> bool:
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def ensure_embedding_model(
        self, base_url: str = "http://localhost:11434", model: str = "nomic-embed-text"
    ) -> bool:
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                models = resp.json().get("models", [])
                for m in models:
                    if model in m.get("name", ""):
                        return True
            resp = requests.post(
                f"{base_url}/api/pull",
                json={"model": model},
                timeout=300,
                stream=True,
            )
            return resp.status_code == 200
        except Exception:
            return False

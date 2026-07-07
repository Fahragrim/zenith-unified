"""RAG Engine — Retrieval-Augmented Generation using ChromaDB + local embeddings."""

from __future__ import annotations

from typing import Any

from loguru import logger


class RAGEngine:
    """Retrieval-Augmented Generation over DEEP_ATLAS knowledge."""

    def __init__(self, chroma_path: str = "data/chroma_db", collection_name: str = "zenith_knowledge") -> None:
        self.chroma_path = chroma_path
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    def _get_client(self):
        if self._client is None:
            try:
                import chromadb  # type: ignore[import-not-found]
                self._client = chromadb.PersistentClient(path=self.chroma_path)
            except ImportError:
                logger.warning("chromadb not installed — RAG will use keyword fallback")
                return None
            except Exception as e:
                logger.error(f"ChromaDB init failed: {e}")
                return None
        return self._client

    def _get_collection(self):
        if self._collection is None:
            client = self._get_client()
            if client is None:
                return None
            try:
                self._collection = client.get_or_create_collection(
                    name=self.collection_name,
                    metadata={"hnsw:space": "cosine"},
                )
            except Exception as e:
                logger.error(f"Collection error: {e}")
                return None
        return self._collection

    def is_available(self) -> bool:
        return self._get_collection() is not None

    def index_knowledge(self, kb_data: list[dict[str, Any]]) -> int:
        """Index knowledge chunks into ChromaDB."""
        collection = self._get_collection()
        if collection is None:
            return 0
        if not kb_data:
            return 0

        ids = []
        documents = []
        metadatas = []
        for i, chunk in enumerate(kb_data):
            ids.append(f"chunk_{i}")
            documents.append(chunk.get("text", ""))
            metadatas.append({k: str(v) for k, v in chunk.items() if k != "text"})

        collection.add(documents=documents, metadatas=metadatas, ids=ids)
        logger.info(f"Indexed {len(ids)} knowledge chunks")
        return len(ids)

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Search knowledge base. Falls back to keyword matching if ChromaDB unavailable."""
        collection = self._get_collection()
        if collection is None:
            return []

        try:
            results = collection.query(query_texts=[query], n_results=k)
            if not results or not results.get("documents") or not results["documents"][0]:
                return []
            return [
                {"text": doc, "metadata": meta, "score": dist}
                    for doc, meta, dist in zip(
                        results["documents"][0], results["metadatas"][0], results["distances"][0], strict=False
                )
            ]
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def clear(self) -> None:
        client = self._get_client()
        if client:
            try:
                client.delete_collection(self.collection_name)
                self._collection = None
                logger.info("Collection cleared")
            except Exception:
                pass

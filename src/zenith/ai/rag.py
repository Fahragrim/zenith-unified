"""RAG Engine — Retrieval-Augmented Generation using ChromaDB + sentence-transformers.

Supports indexing DEEP_ATLAS knowledge and semantic search with keyword fallback.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from loguru import logger


class RAGEngine:
    """RAG over DEEP_ATLAS knowledge using ChromaDB + embeddings."""

    def __init__(self, chroma_path: str = "data/chroma_db", collection_name: str = "zenith_knowledge") -> None:
        self.chroma_path = Path(chroma_path)
        self.collection_name = collection_name
        self._client = None
        self._collection = None
        self._embed_fn = None

    def _init_embed(self) -> bool:
        try:
            from sentence_transformers import SentenceTransformer
            self._embed_fn = SentenceTransformer("all-MiniLM-L6-v2")
            return True
        except ImportError:
            logger.warning("sentence-transformers not installed — RAG will use keyword fallback")
            return False

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                import chromadb
                self.chroma_path.mkdir(parents=True, exist_ok=True)
                self._client = chromadb.PersistentClient(path=str(self.chroma_path))
            except ImportError:
                logger.warning("chromadb not installed")
                return None
        return self._client

    def _get_collection(self) -> Any:
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
        """Index knowledge chunks (from DEEP_ATLAS parser) into ChromaDB."""
        collection = self._get_collection()
        if collection is None:
            logger.warning("ChromaDB not available — indexing skipped")
            return 0
        if not kb_data:
            return 0

        ids, docs, metadatas = [], [], []
        for i, chunk in enumerate(kb_data):
            text = chunk.get("text", "")
            if not text:
                continue
            ids.append(f"chunk_{i}")
            docs.append(text)
            metadatas.append({k: str(v) for k, v in chunk.items() if k != "text"})

        if not docs:
            return 0

        # Embed if available
        if self._embed_fn is None:
            self._init_embed()

        if self._embed_fn:
            try:
                embeddings = self._embed_fn.encode(docs).tolist()
                collection.add(documents=docs, embeddings=embeddings, metadatas=metadatas, ids=ids)
            except Exception as e:
                logger.error(f"Embedding failed, adding without embeddings: {e}")
                collection.add(documents=docs, metadatas=metadatas, ids=ids)
        else:
            collection.add(documents=docs, metadatas=metadatas, ids=ids)

        logger.info(f"Indexed {len(ids)} chunks into {self.collection_name}")
        return len(ids)

    def index_atlas(self, atlas_parser: Any) -> int:
        """Convenience: index the full DEEP_ATLAS into ChromaDB."""
        from zenith.knowledge.atlas_parser import AtlasData
        data: AtlasData = atlas_parser.data
        chunks: list[dict[str, str]] = []

        for key, soc in data.socs.items():
            chunks.append({"text": f"SoC: {soc.name} ({soc.manufacturer}). Boot chain: {' → '.join(soc.boot_chain)}. "
                                   f"Recovery modes: {', '.join(soc.recovery_modes)}.",
                          "category": "soc", "id": key})
            for mode in soc.recovery_modes:
                chunks.append({"text": f"Recovery mode {mode} for {soc.name}.", "category": "soc_mode", "soc": key})
        for key, proto in data.protocols.items():
            chunks.append({"text": f"Protocol: {proto.name}. {proto.description}. USB: {proto.usb_vid or 'N/A'}:{proto.usb_pid or 'N/A'}. "
                                   f"SoC families: {', '.join(proto.soc_families)}. Commands: {', '.join(proto.commands)}",
                          "category": "protocol", "id": key, "risk": proto.risk_level})
        for key, pb in data.playbooks.items():
            chunks.append({"text": f"Playbook: {pb.title}. Symptom: {pb.symptom}. SoC: {pb.soc or 'any'}. "
                                   f"Risk: {pb.risk_level}. {len(pb.steps)} steps.",
                          "category": "playbook", "id": key, "symptom": pb.symptom})
        for key, tool in data.tools.items():
            chunks.append({"text": f"Tool: {tool.name}. Category: {tool.category}. Function: {tool.function}. "
                                   f"Open source: {tool.open_source}.",
                          "category": "tool", "id": key})

        return self.index_knowledge(chunks)

    def search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Semantic search. Falls back to keyword matching if ChromaDB unavailable."""
        collection = self._get_collection()
        if collection is None:
            return self._keyword_search(query, k)

        try:
            if self._embed_fn:
                q_emb = self._embed_fn.encode([query]).tolist()
                results = collection.query(query_embeddings=q_emb, n_results=k)
            else:
                results = collection.query(query_texts=[query], n_results=k)

            if not results or not results.get("documents") or not results["documents"][0]:
                return self._keyword_search(query, k)
            return [
                {"text": doc, "metadata": meta, "score": dist}
                for doc, meta, dist in zip(
                    results["documents"][0], results["metadatas"][0], results["distances"][0], strict=False
                )
            ]
        except Exception as e:
            logger.error(f"Vector search failed: {e}")
            return self._keyword_search(query, k)

    def _keyword_search(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        q = query.lower()
        results: list[dict[str, Any]] = []
        try:
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            for _key, s in kb.data.socs.items():
                if q in s.name.lower() or q in s.manufacturer.lower():
                    results.append({"text": f"SoC: {s.name} ({s.manufacturer})", "category": "soc"})
            for _key, p in kb.data.protocols.items():
                if q in p.name.lower() or q in p.description.lower():
                    results.append({"text": f"Protocol: {p.name}. {p.description[:100]}", "category": "protocol"})
            for _key, pb in kb.data.playbooks.items():
                if q in pb.title.lower() or q in pb.symptom.lower():
                    results.append({"text": f"Playbook: {pb.title} ({pb.symptom})", "category": "playbook"})
        except Exception:
            pass
        return results[:k]

    def clear(self) -> None:
        client = self._get_client()
        if client:
            try:
                client.delete_collection(self.collection_name)
                self._collection = None
                logger.info(f"Collection {self.collection_name} cleared")
            except Exception:
                pass

    def count(self) -> int:
        collection = self._get_collection()
        if collection is None:
            return 0
        try:
            return collection.count()
        except Exception:
            return 0

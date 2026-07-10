"""Tests for RAG Engine — ChromaDB vector search + keyword fallback."""

from __future__ import annotations

import pytest

from zenith.ai.rag import RAGEngine


class TestRAGEngine:
    def test_create(self) -> None:
        engine = RAGEngine()
        assert engine.collection_name == "zenith_knowledge"
        assert engine.chroma_path.name == "chroma_db"

    def test_is_available_returns_bool(self) -> None:
        engine = RAGEngine()
        available = engine.is_available()
        assert isinstance(available, bool)

    def test_count_returns_int(self) -> None:
        engine = RAGEngine()
        count = engine.count()
        assert isinstance(count, int)
        assert count >= 0

    def test_search_keyword_fallback(self) -> None:
        """Keyword search should work without ChromaDB."""
        engine = RAGEngine()
        results = engine.search("qualcomm")
        assert isinstance(results, list)
        # May be empty if knowledge base isn't loaded, but shouldn't crash

    def test_search_no_results(self) -> None:
        engine = RAGEngine()
        results = engine.search("zzzznonexistent_xyz")
        assert isinstance(results, list)

    def test_index_knowledge_empty(self) -> None:
        engine = RAGEngine()
        count = engine.index_knowledge([])
        assert count == 0

    def test_index_knowledge_no_chromadb(self) -> None:
        """Should not crash when ChromaDB is unavailable."""
        engine = RAGEngine()
        # Use a path that won't conflict with real data
        from pathlib import Path
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            engine.chroma_path = Path(td) / "nope"
            count = engine.index_knowledge([{"text": "test", "category": "test"}])
            # Either succeeds (if chromadb installed) or returns 0
            assert isinstance(count, int)

    def test_clear(self) -> None:
        engine = RAGEngine()
        # Should not raise
        engine.clear()

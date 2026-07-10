"""Unit tests for zenith/ai/rag.py — RAG engine (ChromaDB + sentence-transformers)."""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from zenith.ai.rag import RAGEngine


class TestRAGEngineInit:
    """Tests for RAGEngine.__init__()."""

    def test_stores_path_and_collection(self, temp_dir) -> None:
        engine = RAGEngine(chroma_path=str(temp_dir / "chroma"), collection_name="test_coll")
        assert str(engine.chroma_path) == str(temp_dir / "chroma")
        assert engine.collection_name == "test_coll"
        assert engine._client is None
        assert engine._collection is None
        assert engine._embed_fn is None

    def test_defaults(self) -> None:
        engine = RAGEngine()
        assert engine.collection_name == "zenith_knowledge"


class TestRAGEngineInitEmbed:
    """Tests for _init_embed()."""

    def test_import_success(self) -> None:
        mock_transformer = MagicMock()
        with patch.dict("sys.modules", {"sentence_transformers": MagicMock()}):
            import sentence_transformers  # type: ignore[import-untyped]

            sentence_transformers.SentenceTransformer = MagicMock(return_value=mock_transformer)

            engine = RAGEngine()
            result = engine._init_embed()

        assert result is True
        assert engine._embed_fn is mock_transformer

    def test_import_failure(self) -> None:
        engine = RAGEngine()
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with patch("zenith.ai.rag.logger.warning") as mock_warn:
                result = engine._init_embed()

        assert result is False
        assert engine._embed_fn is None
        mock_warn.assert_called_once_with(
            "sentence-transformers not installed — RAG will use keyword fallback"
        )


class TestRAGEngineGetClient:
    """Tests for _get_client()."""

    def test_import_success(self) -> None:
        mock_client = MagicMock()
        mock_persistent = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"chromadb": MagicMock()}):
            import chromadb  # type: ignore[import-untyped]

            chromadb.PersistentClient = mock_persistent

            engine = RAGEngine()
            result = engine._get_client()

        assert result is mock_client
        mock_persistent.assert_called_once()

    def test_import_failure(self, temp_dir) -> None:
        engine = RAGEngine(chroma_path=str(temp_dir / "nope"))
        with patch.dict("sys.modules", {"chromadb": None}):
            with patch("zenith.ai.rag.logger.warning") as mock_warn:
                result = engine._get_client()

        assert result is None
        mock_warn.assert_called_once_with("chromadb not installed")

    def test_client_cached(self) -> None:
        mock_client = MagicMock()
        persistent = MagicMock(return_value=mock_client)

        with patch.dict("sys.modules", {"chromadb": MagicMock()}):
            import chromadb  # type: ignore[import-untyped]

            chromadb.PersistentClient = persistent

            engine = RAGEngine()
            c1 = engine._get_client()
            c2 = engine._get_client()

            assert c1 is c2
            assert persistent.call_count == 1


class TestRAGEngineGetCollection:
    """Tests for _get_collection()."""

    def test_returns_none_when_db_fails(self, temp_dir) -> None:
        engine = RAGEngine(chroma_path=str(temp_dir / "x"))
        engine._get_client = MagicMock(return_value=None)  # type: ignore[assignment]
        result = engine._get_collection()
        assert result is None

    def test_returns_collection_on_success(self, temp_dir) -> None:
        mock_collection = MagicMock()
        mock_client = MagicMock()
        mock_client.get_or_create_collection.return_value = mock_collection

        engine = RAGEngine(chroma_path=str(temp_dir / "x"))
        engine._get_client = MagicMock(return_value=mock_client)  # type: ignore[assignment]
        result = engine._get_collection()

        assert result is mock_collection
        mock_client.get_or_create_collection.assert_called_once_with(
            name="zenith_knowledge",
            metadata={"hnsw:space": "cosine"},
        )

    def test_handles_exception(self, temp_dir) -> None:
        mock_client = MagicMock()
        mock_client.get_or_create_collection.side_effect = RuntimeError("db error")

        engine = RAGEngine(chroma_path=str(temp_dir / "x"))
        engine._get_client = MagicMock(return_value=mock_client)  # type: ignore[assignment]
        with patch("zenith.ai.rag.logger.error") as mock_err:
            result = engine._get_collection()

        assert result is None
        mock_err.assert_called_once()
        assert "db error" in str(mock_err.call_args[0][0])


class TestRAGEngineIsAvailable:
    """Tests for is_available()."""

    def test_false_when_collection_none(self) -> None:
        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=None)  # type: ignore[assignment]
        assert engine.is_available() is False

    def test_true_when_collection_exists(self) -> None:
        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=MagicMock())  # type: ignore[assignment]
        assert engine.is_available() is True


class TestRAGEngineIndexKnowledge:
    """Tests for index_knowledge()."""

    def test_empty_data_returns_zero(self) -> None:
        engine = RAGEngine()
        result = engine.index_knowledge([])
        assert result == 0

    def test_no_collection_returns_zero(self) -> None:
        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=None)  # type: ignore[assignment]

        with patch("zenith.ai.rag.logger.warning") as mock_warn:
            result = engine.index_knowledge([{"text": "some content"}])

        assert result == 0
        mock_warn.assert_called_once_with("ChromaDB not available — indexing skipped")

    def test_skips_empty_text_chunks(self) -> None:
        mock_collection = MagicMock()
        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = None
        engine._init_embed = MagicMock(return_value=False)  # type: ignore[assignment]

        result = engine.index_knowledge([{"text": ""}, {"text": "valid"}])

        assert result == 1
        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args[1]
        assert call_args["documents"] == ["valid"]
        # embeddings should not be passed when no embed_fn

    def test_index_with_embeddings(self) -> None:
        mock_collection = MagicMock()
        mock_embed_fn = MagicMock()
        mock_embed_fn.encode.return_value.tolist.return_value = [[0.1, 0.2]]

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = mock_embed_fn

        result = engine.index_knowledge([{"text": "hello world", "source": "atlas"}])

        assert result == 1
        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args[1]
        assert call_args["documents"] == ["hello world"]
        assert call_args["embeddings"] == [[0.1, 0.2]]
        assert call_args["metadatas"] == [{"source": "atlas"}]

    def test_index_with_embedding_exception(self) -> None:
        mock_collection = MagicMock()
        mock_embed_fn = MagicMock()
        mock_embed_fn.encode.side_effect = RuntimeError("encode failed")

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = mock_embed_fn

        with patch("zenith.ai.rag.logger.error") as mock_err:
            result = engine.index_knowledge([{"text": "hello"}])

        assert result == 1
        mock_err.assert_called_once()
        assert "failed" in str(mock_err.call_args[0][0])
        # Should have fallen back to adding without embeddings
        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args[1]
        assert "embeddings" not in call_args

    def test_index_without_embeddings(self) -> None:
        mock_collection = MagicMock()

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = None
        engine._init_embed = MagicMock(return_value=False)  # type: ignore[assignment]

        result = engine.index_knowledge([{"text": "hello without embeddings"}])

        assert result == 1
        mock_collection.add.assert_called_once()
        call_args = mock_collection.add.call_args[1]
        assert call_args["documents"] == ["hello without embeddings"]
        assert "embeddings" not in call_args

    def test_index_when_chromadb_unavailable(self) -> None:
        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=None)  # type: ignore[assignment]

        result = engine.index_knowledge([{"text": "test"}])

        assert result == 0


class TestRAGEngineIndexAtlas:
    """Tests for index_atlas()."""

    def test_index_atlas_calls_index_knowledge(self) -> None:
        mock_soc = MagicMock()
        mock_soc.name = "T810"
        mock_soc.manufacturer = "Unisoc"
        mock_soc.boot_chain = ["boot1", "boot2"]
        mock_soc.recovery_modes = ["edl", "fastboot"]

        mock_proto = MagicMock()
        mock_proto.name = "USB 3.0"
        mock_proto.description = "USB Protocol"
        mock_proto.usb_vid = "0x123"
        mock_proto.usb_pid = "0x456"
        mock_proto.soc_families = ["unisoc"]
        mock_proto.commands = ["cmd1"]
        mock_proto.risk_level = "low"

        mock_pb = MagicMock()
        mock_pb.title = "FRP Bypass"
        mock_pb.symptom = "frp-lock"
        mock_pb.soc = "unisoc"
        mock_pb.risk_level = "high"
        mock_pb.steps = ["step1"]

        mock_tool = MagicMock()
        mock_tool.name = "SPD Flash"
        mock_tool.category = "flashing"
        mock_tool.function = "flash firmware"
        mock_tool.open_source = True

        mock_data = MagicMock()
        mock_data.socs = {"t810": mock_soc}
        mock_data.protocols = {"usb30": mock_proto}
        mock_data.playbooks = {"frp1": mock_pb}
        mock_data.tools = {"spd": mock_tool}

        mock_parser = MagicMock()
        mock_parser.data = mock_data

        engine = RAGEngine()
        engine.index_knowledge = MagicMock(return_value=42)  # type: ignore[assignment]
        result = engine.index_atlas(mock_parser)

        assert result == 42
        engine.index_knowledge.assert_called_once()
        chunks = engine.index_knowledge.call_args[0][0]
        assert len(chunks) == 6  # 1 soc + 2 modes + 1 protocol + 1 playbook + 1 tool
        categories = {c["category"] for c in chunks}
        assert categories == {"soc", "soc_mode", "protocol", "playbook", "tool"}


class TestRAGEngineSearch:
    """Tests for search()."""

    def test_falls_back_to_keyword_when_no_collection(self) -> None:
        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=None)  # type: ignore[assignment]
        engine._keyword_search = MagicMock(return_value=[{"text": "fallback"}])  # type: ignore[assignment]

        result = engine.search("frp")

        assert result == [{"text": "fallback"}]
        engine._keyword_search.assert_called_once_with("frp", 5)

    def test_vector_search_success(self) -> None:
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["doc1", "doc2"]],
            "metadatas": [[{"cat": "soc"}, {"cat": "tool"}]],
            "distances": [[0.1, 0.2]],
        }

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = MagicMock()
        engine._embed_fn.encode.return_value.tolist.return_value = [[0.5, 0.6]]

        result = engine.search("test query")

        assert len(result) == 2
        assert result[0]["text"] == "doc1"
        assert result[0]["metadata"] == {"cat": "soc"}
        assert result[0]["score"] == 0.1

    def test_vector_search_empty_results_falls_back(self) -> None:
        mock_collection = MagicMock()
        mock_collection.query.return_value = {"documents": [[]], "metadatas": [[]], "distances": [[]]}

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = MagicMock()
        engine._keyword_search = MagicMock(return_value=[{"text": "keyword"}])  # type: ignore[assignment]

        result = engine.search("test")

        assert result == [{"text": "keyword"}]

    def test_vector_search_exception_falls_back(self) -> None:
        mock_collection = MagicMock()
        mock_collection.query.side_effect = RuntimeError("query failed")

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = MagicMock()
        engine._keyword_search = MagicMock(return_value=[{"text": "fallback"}])  # type: ignore[assignment]

        with patch("zenith.ai.rag.logger.error") as mock_err:
            result = engine.search("test")

        assert result == [{"text": "fallback"}]
        mock_err.assert_called_once()

    def test_vector_search_no_embed_fn_uses_query_texts(self) -> None:
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{}]],
            "distances": [[0.3]],
        }

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        engine._embed_fn = None

        result = engine.search("test query")

        assert len(result) == 1
        mock_collection.query.assert_called_once_with(query_texts=["test query"], n_results=5)


class TestRAGEngineKeywordSearch:
    """Tests for _keyword_search()."""

    def test_searches_socs_protocols_playbooks(self) -> None:
        mock_soc = MagicMock()
        mock_soc.name = "Snapdragon 888"
        mock_soc.manufacturer = "Qualcomm"

        mock_proto = MagicMock()
        mock_proto.name = "EDL"
        mock_proto.description = "Qualcomm Emergency Download"

        mock_pb = MagicMock()
        mock_pb.title = "FRP Bypass"
        mock_pb.symptom = "frp-lock"

        mock_data = MagicMock()
        mock_data.socs = {"sm8350": mock_soc}
        mock_data.protocols = {"edl": mock_proto}
        mock_data.playbooks = {"frp1": mock_pb}

        mock_kb = MagicMock()
        mock_kb.data = mock_data

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            engine = RAGEngine()
            results = engine._keyword_search("qualcomm", k=5)

        assert len(results) >= 1
        assert any("Snapdragon" in r["text"] for r in results)

    def test_returns_empty_on_exception(self) -> None:
        engine = RAGEngine()
        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", side_effect=ImportError("no kb")):
            results = engine._keyword_search("anything")
        assert results == []

    def test_results_limited_by_k(self) -> None:
        mock_soc1 = MagicMock()
        mock_soc1.name = "Snapdragon 888"
        mock_soc1.manufacturer = "Qualcomm"
        mock_soc2 = MagicMock()
        mock_soc2.name = "Snapdragon 8 Gen 1"
        mock_soc2.manufacturer = "Qualcomm"

        mock_data = MagicMock()
        mock_data.socs = {"sm8350": mock_soc1, "sm8450": mock_soc2}
        mock_data.protocols = {}
        mock_data.playbooks = {}

        mock_kb = MagicMock()
        mock_kb.data = mock_data

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            engine = RAGEngine()
            results = engine._keyword_search("qualcomm", k=1)

        assert len(results) == 1


class TestRAGEngineClear:
    """Tests for clear()."""

    def test_calls_delete_collection(self, temp_dir) -> None:
        mock_client = MagicMock()

        engine = RAGEngine(chroma_path=str(temp_dir / "x"))
        engine._get_client = MagicMock(return_value=mock_client)  # type: ignore[assignment]

        engine.clear()

        mock_client.delete_collection.assert_called_once_with("zenith_knowledge")
        assert engine._collection is None

    def test_noop_when_no_client(self) -> None:
        engine = RAGEngine()
        engine._get_client = MagicMock(return_value=None)  # type: ignore[assignment]

        # Should not raise
        engine.clear()

    def test_handles_exception_gracefully(self, temp_dir) -> None:
        mock_client = MagicMock()
        mock_client.delete_collection.side_effect = RuntimeError("delete failed")

        engine = RAGEngine(chroma_path=str(temp_dir / "x"))
        engine._get_client = MagicMock(return_value=mock_client)  # type: ignore[assignment]

        # Should not raise
        engine.clear()


class TestRAGEngineCount:
    """Tests for count()."""

    def test_returns_zero_when_no_collection(self) -> None:
        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=None)  # type: ignore[assignment]
        assert engine.count() == 0

    def test_returns_collection_count(self) -> None:
        mock_collection = MagicMock()
        mock_collection.count.return_value = 5

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        assert engine.count() == 5

    def test_handles_exception(self) -> None:
        mock_collection = MagicMock()
        mock_collection.count.side_effect = RuntimeError("count failed")

        engine = RAGEngine()
        engine._get_collection = MagicMock(return_value=mock_collection)  # type: ignore[assignment]
        assert engine.count() == 0

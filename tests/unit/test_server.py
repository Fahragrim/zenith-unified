"""Unit tests for zenith.server.app — FastAPI server endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from zenith.server.app import app

client = TestClient(app)


class TestRoot:
    def test_root_returns_name_version_status(self) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "Zenith Unified API"
        assert data["version"] == "0.1.0"
        assert data["status"] == "online"


class TestHealth:
    def test_health_returns_healthy(self) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "healthy"}


class TestListDevices:
    def test_list_devices_returns_devices_dict(self) -> None:
        mock_result = MagicMock()
        mock_result.to_display_text.return_value = "MOCK DEVICES"

        with patch("zenith.core.discovery.run_discovery", return_value=mock_result):
            resp = client.get("/devices")

        assert resp.status_code == 200
        assert resp.json() == {"devices": "MOCK DEVICES"}

    def test_list_devices_calls_run_discovery(self) -> None:
        mock_result = MagicMock()
        mock_result.to_display_text.return_value = ""

        with patch("zenith.core.discovery.run_discovery", return_value=mock_result) as m:
            client.get("/devices")

        m.assert_called_once_with()


class TestDiagnose:
    def test_diagnose_default_symptom(self) -> None:
        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"diagnosis": "mock", "risk_level": "high"}
        mock_engine.diagnose.return_value = mock_result

        with patch("zenith.engines.diagnostics.DiagnosticsEngine", return_value=mock_engine):
            resp = client.get("/diagnose")

        assert resp.status_code == 200
        assert resp.json() == {"diagnosis": "mock", "risk_level": "high"}

    def test_diagnose_with_custom_symptom(self) -> None:
        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {"diagnosis": "frp result"}
        mock_engine.diagnose.return_value = mock_result

        with patch("zenith.engines.diagnostics.DiagnosticsEngine", return_value=mock_engine):
            resp = client.get("/diagnose?symptom=frp-lock")

        assert resp.status_code == 200

    def test_diagnose_passes_symptom_to_engine(self) -> None:
        mock_engine = MagicMock()
        mock_result = MagicMock()
        mock_result.to_dict.return_value = {}
        mock_engine.diagnose.return_value = mock_result

        with patch("zenith.engines.diagnostics.DiagnosticsEngine", return_value=mock_engine) as m_cls:
            client.get("/diagnose?symptom=hard-brick")

        m_cls.assert_called_once_with()
        mock_engine.diagnose.assert_called_once_with(["hard-brick"])


class TestListPlaybooks:
    def test_list_playbooks_returns_list(self) -> None:
        mock_kb = MagicMock()
        pb1 = MagicMock(id="pb-1", title="Playbook 1", symptom="bootloop")
        pb2 = MagicMock(id="pb-2", title="Playbook 2", symptom="frp-lock")
        mock_kb.list_playbooks.return_value = [pb1, pb2]

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.get("/playbooks")

        assert resp.status_code == 200
        data = resp.json()
        assert len(data["playbooks"]) == 2
        assert data["playbooks"][0] == {"id": "pb-1", "title": "Playbook 1", "symptom": "bootloop"}
        assert data["playbooks"][1] == {"id": "pb-2", "title": "Playbook 2", "symptom": "frp-lock"}

    def test_list_playbooks_empty(self) -> None:
        mock_kb = MagicMock()
        mock_kb.list_playbooks.return_value = []

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.get("/playbooks")

        assert resp.status_code == 200
        assert resp.json() == {"playbooks": []}


class TestArsenal:
    def test_arsenal_without_query_returns_counts(self) -> None:
        mock_kb = MagicMock()
        mock_kb.data.socs = {"qcom": MagicMock(), "mtk": MagicMock()}
        mock_kb.data.protocols = {"adb": MagicMock(), "fastboot": MagicMock(), "edl": MagicMock()}
        mock_kb.data.playbooks = {"pb1": MagicMock()}
        mock_kb.data.tools = {"t1": MagicMock(), "t2": MagicMock(), "t3": MagicMock()}

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.get("/arsenal")

        assert resp.status_code == 200
        data = resp.json()
        assert data == {"soc_count": 2, "protocol_count": 3, "playbook_count": 1, "tool_count": 3}

    def test_arsenal_empty_counts(self) -> None:
        mock_kb = MagicMock()
        mock_kb.data.socs = {}
        mock_kb.data.protocols = {}
        mock_kb.data.playbooks = {}
        mock_kb.data.tools = {}

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.get("/arsenal")

        assert resp.status_code == 200
        assert resp.json() == {"soc_count": 0, "protocol_count": 0, "playbook_count": 0, "tool_count": 0}

    def test_arsenal_with_query_calls_search(self) -> None:
        mock_kb = MagicMock()
        mock_kb.search.return_value = {
            "socs": ["qcom"], "protocols": [], "playbooks": [], "tools": [],
        }

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.get("/arsenal?query=qualcomm")

        assert resp.status_code == 200
        mock_kb.search.assert_called_once_with("qualcomm")
        assert resp.json() == {"socs": ["qcom"], "protocols": [], "playbooks": [], "tools": []}

    def test_arsenal_with_empty_query_returns_counts(self) -> None:
        mock_kb = MagicMock()
        mock_kb.data.socs = {}
        mock_kb.data.protocols = {}
        mock_kb.data.playbooks = {}
        mock_kb.data.tools = {}

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.get("/arsenal?query=")

        assert resp.status_code == 200
        assert "soc_count" in resp.json()


class TestMain:
    def test_main_calls_uvicorn_run(self) -> None:
        with patch("zenith.server.app.uvicorn.run") as m:
            from zenith.server.app import main
            main()

        m.assert_called_once_with(app, host="127.0.0.1", port=8089)


class TestDiagnosePost:
    def test_diagnose_post_accepts_body(self) -> None:
        mock_diag_result = MagicMock()
        mock_diag_result.to_dict.return_value = {"diagnosis": "bootloop"}

        mock_engine = MagicMock()
        mock_engine.diagnose.return_value = mock_diag_result

        with patch("zenith.engines.diagnostics.DiagnosticsEngine", return_value=mock_engine):
            resp = client.post("/diagnose", json={"symptom": "bootloop"})

        assert resp.status_code == 200
        assert resp.json()["diagnosis"] == "bootloop"
        mock_engine.diagnose.assert_called_once_with(["bootloop"])

    def test_diagnose_post_default_symptom(self) -> None:
        mock_diag_result = MagicMock()
        mock_diag_result.to_dict.return_value = {"diagnosis": "bootloop"}

        mock_engine = MagicMock()
        mock_engine.diagnose.return_value = mock_diag_result

        with patch("zenith.engines.diagnostics.DiagnosticsEngine", return_value=mock_engine):
            resp = client.post("/diagnose", json={})

        assert resp.status_code == 200
        mock_engine.diagnose.assert_called_once_with(["bootloop"])


class TestExecutePlaybook:
    def test_playbook_not_found(self) -> None:
        mock_kb = MagicMock()
        mock_kb.get_playbook.return_value = None

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.post("/execute-playbook", json={"playbook_id": "missing"})

        assert resp.status_code == 200
        assert "not found" in resp.json()["error"]

    def test_high_risk_requires_consent(self) -> None:
        """High-risk playbooks with force=True must return consent_required, not execute."""
        mock_pb = MagicMock()
        mock_pb.id = "pb1"
        mock_pb.title = "FRP Bypass"
        mock_pb.symptom = "frp-lock"
        mock_pb.steps = []
        mock_pb.risk_level = "high"

        mock_kb = MagicMock()
        mock_kb.get_playbook.return_value = mock_pb

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.post("/execute-playbook", json={"playbook_id": "pb1", "device_serial": "123", "force": True})

        assert resp.status_code == 200
        data = resp.json()
        # With force=True the legal ack gate is passed, but consent is still required for high-risk
        assert data.get("consent_required") is True
        assert "operation" in data

    def test_high_risk_denied_without_legal_ack(self) -> None:
        """High-risk playbooks without force must be denied by policy."""
        mock_pb = MagicMock()
        mock_pb.id = "pb1"
        mock_pb.title = "FRP Bypass"
        mock_pb.symptom = "frp-lock"
        mock_pb.steps = []
        mock_pb.risk_level = "high"

        mock_kb = MagicMock()
        mock_kb.get_playbook.return_value = mock_pb

        with patch("zenith.knowledge.knowledge_base.get_knowledge_base", return_value=mock_kb):
            resp = client.post("/execute-playbook", json={"playbook_id": "pb1", "device_serial": "123"})

        assert resp.status_code == 200
        data = resp.json()
        # Policy denies destructive ops without legal acknowledgment (rule R004)
        assert "error" in data
        assert "Policy denied" in data["error"]


class TestConsentEndpoints:
    def test_consent_grant_requires_operation(self) -> None:
        resp = client.post("/consent/grant", json={})
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_consent_deny_requires_operation(self) -> None:
        resp = client.post("/consent/deny", json={})
        assert resp.status_code == 200
        assert "error" in resp.json()

    def test_consent_grant_unknown_operation(self) -> None:
        resp = client.post("/consent/grant", json={"operation": "nonexistent"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_required"


class TestCorsConfig:
    def test_cors_not_wildcard(self) -> None:
        """CORS must not allow wildcard origins with credentials (insecure)."""
        from zenith.server.app import app

        middleware = next(
            (m for m in app.user_middleware if "CORSMiddleware" in str(m.cls)), None
        )
        assert middleware is not None
        origins = middleware.kwargs.get("allow_origins", [])
        assert "*" not in origins, "CORS must not use wildcard origin with credentials"

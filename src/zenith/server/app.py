"""FastAPI server — REST API for Zenith Unified."""

from __future__ import annotations

import os
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Zenith Unified API",
    description="API for Android diagnostic and repair operations",
    version="0.1.0",
)

# CORS: restrict to localhost origins only. The server binds to 127.0.0.1, so
# cross-origin browser access should be limited to local development frontends.
# ZENITH_CORS_ORIGINS can override (comma-separated) for specific trusted origins.
# Note: allow_credentials=True with a wildcard origin is rejected by browsers and
# is insecure for a tool that can flash/erase devices — never use ["*"] here.
_default_origins = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:8089,http://127.0.0.1:8089"
_allowed_origins = [o.strip() for o in os.environ.get("ZENITH_CORS_ORIGINS", _default_origins).split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
def root() -> dict[str, Any]:
    return {"name": "Zenith Unified API", "version": "0.1.0", "status": "online"}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "healthy"}


@app.get("/devices")
def list_devices() -> dict[str, Any]:
    from zenith.core.discovery import run_discovery
    return {"devices": run_discovery().to_display_text()}


@app.get("/diagnose")
def diagnose(symptom: str = "bootloop") -> dict[str, Any]:
    from zenith.engines.diagnostics import DiagnosticsEngine
    engine = DiagnosticsEngine()
    result = engine.diagnose([symptom])
    return result.to_dict()


@app.post("/diagnose")
def diagnose_post(body: dict[str, Any]) -> dict[str, Any]:
    """POST variant of /diagnose — accepts a JSON body with 'symptom'."""
    from zenith.engines.diagnostics import DiagnosticsEngine
    engine = DiagnosticsEngine()
    symptom = str(body.get("symptom", "bootloop"))
    result = engine.diagnose([symptom])
    return result.to_dict()


@app.get("/playbooks")
def list_playbooks() -> dict[str, Any]:
    from zenith.knowledge.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    return {"playbooks": [{"id": p.id, "title": p.title, "symptom": p.symptom} for p in kb.list_playbooks()]}


@app.post("/execute-playbook")
def execute_playbook(body: dict[str, Any]) -> dict[str, Any]:
    """Execute a repair playbook. Enforces PolicyEngine + ConsentGate (safety-by-design).

    Destructive operations require explicit consent. If consent is required, the
    response includes a 'consent_required' key with the operation ID — the client
    must call POST /consent/grant to approve before retrying.
    """
    from zenith.core.consent import ConsentGate
    from zenith.core.exceptions import ConsentRequiredError
    from zenith.core.policy import ActionLevel, PolicyContext, PolicyEngine, Verdict
    from zenith.engines.playbook_executor import PlaybookExecutor
    from zenith.knowledge.knowledge_base import get_knowledge_base

    playbook_id = str(body.get("playbook_id", ""))
    device_serial = str(body.get("device_serial", ""))
    force = bool(body.get("force", False))

    kb = get_knowledge_base()
    pb = kb.get_playbook(playbook_id)
    if pb is None:
        return {"error": f"Playbook not found: {playbook_id}"}

    risk_level = getattr(pb, "risk_level", "medium")
    action_level = ActionLevel.DESTRUCTIVE if risk_level in ("high", "critical") else ActionLevel.WRITE
    policy = PolicyEngine()
    ctx = PolicyContext(device_serial=device_serial, operator_acknowledged_legal=force)
    decision = policy.evaluate(action_level, ctx)
    if decision.verdict == Verdict.DENY:
        return {"error": f"Policy denied: {decision.reason} (rule {decision.rule_id})"}

    consent = ConsentGate(policy_engine=policy)
    operation = f"execute_playbook:{pb.id}"
    try:
        consent.check_and_require(
            operation=operation,
            title=pb.title,
            description=f"Execute repair playbook '{pb.title}' on device {device_serial or '(none)'}.",
            risk_level=risk_level,
            device_serial=device_serial,
        )
    except ConsentRequiredError as e:
        return {"consent_required": True, "operation": operation, "message": str(e),
                "risk_level": risk_level, "title": pb.title}

    pbd = {"id": pb.id, "title": pb.title, "symptom": pb.symptom, "steps": pb.steps, "risk_level": pb.risk_level}
    executor = PlaybookExecutor()
    result = executor.execute(pbd, device_serial)
    return result.to_dict()


@app.post("/consent/grant")
def consent_grant(body: dict[str, Any]) -> dict[str, Any]:
    """Grant consent for a pending operation (human-in-the-loop approval)."""
    from zenith.core.consent import ConsentGate
    from zenith.core.policy import PolicyEngine
    operation = str(body.get("operation", ""))
    if not operation:
        return {"error": "operation is required"}
    consent = ConsentGate(policy_engine=PolicyEngine())
    status = consent.grant(operation, reason=str(body.get("reason", "granted via API")))
    return {"operation": operation, "status": status.value}


@app.post("/consent/deny")
def consent_deny(body: dict[str, Any]) -> dict[str, Any]:
    """Deny consent for a pending operation."""
    from zenith.core.consent import ConsentGate
    from zenith.core.policy import PolicyEngine
    operation = str(body.get("operation", ""))
    if not operation:
        return {"error": "operation is required"}
    consent = ConsentGate(policy_engine=PolicyEngine())
    status = consent.deny(operation, reason=str(body.get("reason", "denied via API")))
    return {"operation": operation, "status": status.value}


@app.get("/arsenal")
def arsenal(query: str = "") -> dict[str, Any]:
    from zenith.knowledge.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    if query:
        return kb.search(query)
    return {"soc_count": len(kb.data.socs), "protocol_count": len(kb.data.protocols),
            "playbook_count": len(kb.data.playbooks), "tool_count": len(kb.data.tools)}


def main() -> None:
    uvicorn.run(app, host="127.0.0.1", port=8089)


if __name__ == "__main__":
    main()

"""FastAPI server — REST API for Zenith Unified."""

from __future__ import annotations

import uvicorn  # type: ignore[import-untyped]
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="Zenith Unified API",
    description="API for Android diagnostic and repair operations",
    version="0.1.0",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])


@app.get("/")
def root() -> dict:
    return {"name": "Zenith Unified API", "version": "0.1.0", "status": "online"}


@app.get("/health")
def health() -> dict:
    return {"status": "healthy"}


@app.get("/devices")
def list_devices() -> dict:
    from zenith.core.discovery import run_discovery
    return {"devices": run_discovery().to_display_text()}


@app.get("/diagnose")
def diagnose(symptom: str = "bootloop") -> dict:
    from zenith.engines.diagnostics import DiagnosticsEngine
    engine = DiagnosticsEngine()
    result = engine.diagnose([symptom])
    return result.to_dict()


@app.get("/playbooks")
def list_playbooks() -> dict:
    from zenith.knowledge.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    return {"playbooks": [{"id": p.id, "title": p.title, "symptom": p.symptom} for p in kb.list_playbooks()]}


@app.get("/arsenal")
def arsenal(query: str = "") -> dict:
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

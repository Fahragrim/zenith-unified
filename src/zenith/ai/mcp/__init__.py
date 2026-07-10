"""MCP (Model Context Protocol) Server — tool-calling interface for AI agents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any


@dataclass
class MCPTool:
    name: str
    description: str
    schema: dict[str, Any]


MCP_TOOLS: list[MCPTool] = [
    MCPTool("discover_devices", "Discover connected Android devices via ADB, Fastboot, USB, and serial",
            {"type": "object", "properties": {}, "required": []}),
    MCPTool("diagnose", "Run Bayesian diagnostics on device symptoms",
            {"type": "object", "properties": {"symptom": {"type": "string"}}, "required": ["symptom"]}),
    MCPTool("search_knowledge", "Search the DEEP_ATLAS knowledge base",
            {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}),
    MCPTool("list_playbooks", "List available repair playbooks",
            {"type": "object", "properties": {}, "required": []}),
    MCPTool("execute_playbook", "Execute a repair playbook on a device",
            {"type": "object", "properties": {"playbook_id": {"type": "string"}, "device_serial": {"type": "string"}},
             "required": ["playbook_id"]}),
    MCPTool("run_adb", "Run an ADB command on a device",
            {"type": "object", "properties": {"command": {"type": "string"}, "serial": {"type": "string"}},
             "required": ["command"]}),
    MCPTool("run_fastboot", "Run a Fastboot command",
            {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}),
    MCPTool("sahara_ping", "Scan COM ports for Qualcomm EDL devices",
            {"type": "object", "properties": {}, "required": []}),
    MCPTool("fastboot_fuzz", "Fuzz fastboot OEM commands for hidden features",
            {"type": "object", "properties": {}, "required": []}),
]


def list_tools() -> list[dict[str, Any]]:
    return [{"name": t.name, "description": t.description, "inputSchema": t.schema} for t in MCP_TOOLS]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    args = arguments or {}
    if name == "discover_devices":
        from zenith.core.discovery import run_discovery
        r = run_discovery()
        return {"content": [{"type": "text", "text": r.to_display_text()}]}
    elif name == "diagnose":
        from zenith.engines.diagnostics import DiagnosticsEngine
        engine = DiagnosticsEngine()
        r2 = engine.diagnose([args.get("symptom", "bootloop")])
        return {"content": [{"type": "text", "text": json.dumps(r2.to_dict(), ensure_ascii=False)}]}
    elif name == "search_knowledge":
        from zenith.knowledge.knowledge_base import get_knowledge_base
        kb = get_knowledge_base()
        r3 = kb.search(args.get("query", ""))
        return {"content": [{"type": "text", "text": json.dumps(r3, ensure_ascii=False)}]}
    elif name == "list_playbooks":
        from zenith.knowledge.knowledge_base import get_knowledge_base
        kb = get_knowledge_base()
        r4 = [{"id": p.id, "title": p.title, "symptom": p.symptom, "risk": p.risk_level} for p in kb.list_playbooks()]
        return {"content": [{"type": "text", "text": json.dumps(r4, ensure_ascii=False)}]}
    elif name == "execute_playbook":
        from zenith.core.consent import ConsentGate
        from zenith.core.exceptions import ConsentRequiredError
        from zenith.core.policy import ActionLevel, PolicyContext, PolicyEngine, Verdict
        from zenith.engines.playbook_executor import PlaybookExecutor
        from zenith.knowledge.knowledge_base import get_knowledge_base
        kb = get_knowledge_base()
        pb = kb.get_playbook(args.get("playbook_id", ""))
        if pb is None:
            return {"content": [{"type": "text", "text": f"Playbook not found: {args.get('playbook_id')}"}]}
        pbd = {"id": pb.id, "title": pb.title, "symptom": pb.symptom, "steps": pb.steps, "risk_level": pb.risk_level}

        # Safety-by-design: route through PolicyEngine + ConsentGate before execution.
        # Playbooks are write/destructive operations — they must not bypass consent.
        device_serial = args.get("device_serial", "")
        risk_level = getattr(pb, "risk_level", "medium")
        action_level = ActionLevel.DESTRUCTIVE if risk_level in ("high", "critical") else ActionLevel.WRITE
        policy = PolicyEngine()
        ctx = PolicyContext(device_serial=device_serial, operator_acknowledged_legal=False)
        decision = policy.evaluate(action_level, ctx)
        if decision.verdict == Verdict.DENY:
            return {"content": [{"type": "text", "text": f"Policy denied: {decision.reason} (rule {decision.rule_id})"}]}

        consent = ConsentGate(policy_engine=policy)
        try:
            consent.check_and_require(
                operation=f"execute_playbook:{pb.id}",
                title=pb.title,
                description=f"Execute repair playbook '{pb.title}' on device {device_serial or '(none)'}.",
                risk_level=risk_level,
                device_serial=device_serial,
            )
        except ConsentRequiredError as e:
            return {"content": [{"type": "text", "text": f"Consent required: {e}"}]}

        executor = PlaybookExecutor()
        r5 = executor.execute(pbd, device_serial)
        return {"content": [{"type": "text", "text": json.dumps(r5.to_dict(), ensure_ascii=False)}]}
    elif name == "run_adb":
        import shlex
        import subprocess
        serial = args.get("serial", "")
        command_str = str(args.get("command", "")).strip()
        if not command_str:
            return {"content": [{"type": "text", "text": "Error: 'command' is required for run_adb"}]}
        # Build arg list — NEVER shell=True. shlex.split safely tokenizes the command string
        # so the AI/client cannot inject shell metacharacters (pipes, &&, $(), etc.).
        try:
            cmd_args = shlex.split(command_str)
        except ValueError as e:
            return {"content": [{"type": "text", "text": f"Error: invalid command syntax: {e}"}]}
        full_args = ["adb"] + (["-s", serial] if serial else []) + cmd_args
        proc = subprocess.run(full_args, capture_output=True, text=True, timeout=30)
        return {"content": [{"type": "text", "text": proc.stdout or proc.stderr}]}
    elif name == "run_fastboot":
        import shlex
        import subprocess
        command_str = str(args.get("command", "")).strip()
        if not command_str:
            return {"content": [{"type": "text", "text": "Error: 'command' is required for run_fastboot"}]}
        try:
            cmd_args = shlex.split(command_str)
        except ValueError as e:
            return {"content": [{"type": "text", "text": f"Error: invalid command syntax: {e}"}]}
        full_args = ["fastboot"] + cmd_args
        proc = subprocess.run(full_args, capture_output=True, text=True, timeout=30)
        return {"content": [{"type": "text", "text": proc.stdout or proc.stderr}]}
    elif name == "sahara_ping":
        from zenith.tools.sahara_ping import sahara_ping_scan
        results = sahara_ping_scan()
        return {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False)}]}
    elif name == "fastboot_fuzz":
        from zenith.tools.fastboot_fuzz import fuzz_oem_commands
        results = fuzz_oem_commands()
        return {"content": [{"type": "text", "text": json.dumps(results, ensure_ascii=False)}]}
    return {"content": [{"type": "text", "text": f"Unknown tool: {name}"}]}

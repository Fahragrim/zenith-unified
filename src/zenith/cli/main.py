"""CLI entry point for Zenith Unified."""

from __future__ import annotations

import json

import click

from zenith import __version__


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(__version__, "-V", "--version", prog_name="zenith")
def main() -> None:
    """Zenith Unified — AI-powered Android diagnostics, repair, and recovery toolkit."""


@main.command()
def discover() -> None:
    """Discover connected devices across ADB, Fastboot, USB, and serial."""
    from zenith.core.discovery import run_discovery
    click.echo(run_discovery().to_display_text())


@main.group(invoke_without_command=True)
@click.pass_context
@click.argument("query", required=False)
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def ai(ctx: click.Context, query: str | None = None, as_json: bool = False) -> None:
    """AI diagnostics assistant. Use 'ai ask <query>' or 'ai index'."""
    if ctx.invoked_subcommand is None:
        if query:
            from zenith.ai.intent import parse_intent
            from zenith.engines.diagnostics import DiagnosticsEngine
            from zenith.knowledge.knowledge_base import get_knowledge_base
            kb = get_knowledge_base()
            engine = DiagnosticsEngine(kb)
            intent = parse_intent(query)
            click.echo(f"Intent: {intent.type.value} (confidence: {intent.confidence:.0%})")
            if intent.target_symptom:
                click.echo(f"Symptom: {intent.target_symptom}")
            if intent.target_soc:
                click.echo(f"SoC: {intent.target_soc}")
            result = engine.diagnose([intent.target_symptom or query])
            if as_json:
                import json as _json
                click.echo(_json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
            else:
                click.echo(f"\nDiagnosis: {result.diagnosis}")
                click.echo(f"Risk: {result.risk_level}")
                if result.tests:
                    click.echo("\nTests:" + "\n  - " + "\n  - ".join(result.tests))
                if result.fixes:
                    click.echo("\nFixes:" + "\n  - " + "\n  - ".join(result.fixes))
        else:
            click.echo("Usage: zenith ai <query> or zenith ai ask <query> or zenith ai index")


@main.command()
@click.option("--soc", type=str, help="Filter by SoC family (qualcomm, mediatek, etc.).")
@click.option("--symptom", type=str, help="Filter by symptom (bootloop, hard-brick, etc.).")
def playbooks(soc: str | None = None, symptom: str | None = None) -> None:
    """List available repair playbooks."""
    from zenith.knowledge.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    playbooks = kb.find_playbook(symptom or "", soc)
    for pb in playbooks:
        steps = len(pb.steps)
        click.echo(f"  [{pb.risk_level:8s}] {pb.title}  (soc={pb.soc or 'any'}, {steps} steps)  id={pb.id}")


@main.command()
@click.argument("playbook_id")
@click.option("--serial", type=str, help="Device serial for ADB/Fastboot targeting.")
@click.option("--dry-run", is_flag=True, help="Simulate without executing commands.")
def repair(playbook_id: str, serial: str | None = None, dry_run: bool = False) -> None:
    """Execute a repair playbook."""
    from zenith.engines.playbook_executor import PlaybookExecutor
    from zenith.knowledge.knowledge_base import get_knowledge_base

    kb = get_knowledge_base()
    pb = kb.get_playbook(playbook_id)
    if pb is None:
        click.echo(f"Playbook not found: {playbook_id}")
        click.echo("Use 'zenith playbooks' to list available playbooks.")
        return

    pbd = {"id": pb.id, "title": pb.title, "symptom": pb.symptom, "steps": pb.steps, "risk_level": pb.risk_level}
    executor = PlaybookExecutor()
    executor.dry_run = dry_run
    click.echo(f"Executing: {pb.title} (risk: {pb.risk_level})")
    if dry_run:
        click.echo("*** DRY RUN MODE — no commands will be executed ***")
    result = executor.execute(pbd, serial or "")
    status = "SUCCESS" if result.success else "FAILED"
    click.echo(f"\nResult: {status} ({result.steps_completed}/{result.total_steps} steps)")
    for r in result.results:
        icon = "OK" if r.success else "FAIL"
        click.echo(f"  [{icon}] Step {r.step_number}: {r.description}")
        if not r.success and r.error:
            click.echo(f"         Error: {r.error}")


@main.command()
@click.argument("symptom")
def diagnose(symptom: str) -> None:
    """Run Bayesian diagnostics on device symptoms."""
    from zenith.engines.diagnostics import DiagnosticsEngine
    engine = DiagnosticsEngine()
    result = engine.diagnose([symptom])
    click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


@main.command()
@click.option("--protocol", type=str, help="Auto-detect from protocol (edl, brom, fastboot).")
def triage(protocol: str | None = None) -> None:
    """Interactive diagnostic triage tree."""
    from zenith.engines.triage import TriageEngine
    engine = TriageEngine()
    if protocol:
        result = engine.auto_detect(protocol)
    else:
        result = engine.traverse(["Bootloop / restarting", "No, only Fastboot"])
    click.echo(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


@main.command()
@click.option("--json", "as_json", is_flag=True, help="Output as JSON.")
def arsenal(as_json: bool = False) -> None:
    """Browse the DEEP_ATLAS knowledge base."""
    from zenith.knowledge.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    if as_json:
        click.echo(kb.to_json())
    else:
        click.echo(f"SoCs: {len(kb.data.socs)}   Protocols: {len(kb.data.protocols)}   "
                    f"Playbooks: {len(kb.data.playbooks)}   Tools: {len(kb.data.tools)}")
        click.echo(f"\nSoCs: {', '.join(kb.data.socs.keys())}")
        click.echo(f"Protocols: {', '.join(kb.data.protocols.keys())}")


@main.command()
@click.argument("firmware_dir")
@click.option("--device", type=str, default="auto", help="Device ID.")
@click.option("--dry-run", is_flag=True, help="Plan only, no execution.")
@click.option("--partition", multiple=True, help="Target partitions.")
def flash(firmware_dir: str, device: str = "auto", dry_run: bool = False, partition: list[str] | None = None) -> None:
    """Flash firmware partitions via EDL/BROM/Fastboot."""
    from zenith.engines.flash import FlashEngine
    engine = FlashEngine()
    plan = engine.plan(device, firmware_dir, list(partition) if partition else None)
    plan.dry_run = dry_run
    click.echo(f"Flash plan: {len(plan.target_partitions)} partitions")
    for s in plan.steps:
        click.echo(f"  [{s.kind.value}] {s.partition}")
    if dry_run:
        click.echo("DRY-RUN — no commands executed")
    else:
        result = engine.execute(plan)
        if result.success:
            click.echo("Flash completed successfully")
        else:
            click.echo(f"Flash failed: {result.error}")


@ai.command("index")
def ai_index() -> None:
    """Index DEEP_ATLAS into ChromaDB vector database."""
    from zenith.knowledge.knowledge_base import get_knowledge_base
    kb = get_knowledge_base()
    from zenith.ai.rag import RAGEngine
    rag = RAGEngine()
    if not rag.is_available():
        click.echo("ChromaDB not available. Install: pip install chromadb sentence-transformers")
        return
    n = rag.index_atlas(kb.parser)
    click.echo(f"Indexed {n} chunks into ChromaDB ({rag.collection_name})")


@ai.command("ask")
@click.argument("query")
def ai_ask(query: str) -> None:
    """Search the knowledge base using semantic search."""
    from zenith.ai.rag import RAGEngine
    rag = RAGEngine()
    results = rag.search(query)
    if not results:
        click.echo("No results found.")
    for r in results:
        click.echo(f"[score={r.get('score', '?'):.3f}] {r.get('text', '')[:200]}")
        meta = r.get('metadata', {})
        if meta:
            click.echo(f"       {', '.join(f'{k}={v}' for k, v in meta.items())}")


@main.command()
def repairs() -> None:
    """List available repair actions."""
    """List available repair actions."""
    from zenith.engines.repair import RepairEngine, RepairType
    engine = RepairEngine()
    for rt in RepairType:
        click.echo(f"\n[{rt.value}]")
        for a in engine.list_actions(rt):
            click.echo(f"  {a.id:20s} {a.name:40s} [{a.protocol or 'manual':10s}] {a.soc_target.value}")


@main.group()
def tool() -> None:
    """Standalone hardware diagnostic tools."""


@tool.command()
def sahara_ping() -> None:
    """Scan COM ports for Qualcomm EDL devices."""
    from zenith.tools.sahara_ping import sahara_ping_scan
    results = sahara_ping_scan()
    if not results:
        click.echo("No EDL devices found.")
    for r in results:
        if "error" in r:
            click.echo(f"Error: {r['error']}")
        else:
            click.echo(f"Found: {r['port']} (response: {r['response_hex']})")


@tool.command()
@click.option("--duration", type=int, default=30, help="Scan duration in seconds.")
def token_hunt(duration: int = 30) -> None:
    """Scan logcat for leaked credentials."""
    from zenith.tools.token_hunter import token_hunt_logcat
    click.echo(f"Scanning logcat for {duration}s...")
    findings = token_hunt_logcat(duration=duration)
    if not findings:
        click.echo("No tokens found.")
    for f in findings:
        if "error" in f:
            click.echo(f"Error: {f['error']}")
        else:
            click.echo(f"Found: {f['match']}")


@main.group()
def audit() -> None:
    """Audit log management."""


@audit.command()
@click.option("--tail", type=int, default=20, help="Show last N entries.")
@click.option("--device", type=str, help="Filter by device serial.")
def show(tail: int = 20, device: str | None = None) -> None:
    """Show audit log entries."""
    from zenith.core.audit import AuditLog
    log = AuditLog()
    entries = log.query(device_serial=device, limit=tail) if device else log.tail(tail)
    if not entries:
        click.echo("No audit entries found.")
    for e in entries:
        click.echo(f"[{e.seq}] {e.timestamp[:19]} | {e.action_level:12s} | {e.topic:25s} | {e.summary}")


@audit.command()
def verify() -> None:
    """Verify audit log integrity."""
    from zenith.core.audit import AuditLog
    log = AuditLog()
    ok = log.verify_chain()
    click.echo(f"Audit chain integrity: {'OK' if ok else 'BROKEN — tampering detected!'}")


@main.command()
@click.option("--host", type=str, default="127.0.0.1", help="Bind host.")
@click.option("--port", type=int, default=8089, help="Bind port.")
def server(host: str = "127.0.0.1", port: int = 8089) -> None:
    """Start the FastAPI server."""
    import uvicorn  # type: ignore[import-untyped]

    from zenith.server.app import app
    click.echo(f"Starting Zenith API server on {host}:{port}")
    uvicorn.run(app, host=host, port=port)


@main.command()
def mcp() -> None:
    """Start the MCP server for AI tool integration."""
    click.echo("Zenith MCP Server ready (stdout implementation)")
    click.echo(f"Available tools: {len(__import__('zenith.ai.mcp.__init__', fromlist=['list_tools']).list_tools())}")
    click.echo("Use 'zenith mcp' to integrate with Claude Desktop or other MCP clients.")


@main.command()
def gui() -> None:
    """Launch the PySide6 desktop GUI."""
    from zenith.gui import launch_gui
    launch_gui()


@main.command()
def version() -> None:
    """Show version information."""
    click.echo(f"Zenith Unified v{__version__}")


if __name__ == "__main__":
    main()

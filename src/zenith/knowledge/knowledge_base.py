"""Knowledge Base — unified query interface for DEEP_ATLAS structured data.

Provides high-level queries: SoC info, protocols, playbooks, tools, secret codes.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from zenith.knowledge.atlas_parser import AtlasData, AtlasParser, Playbook, Protocol, SOCInfo, Tool


class KnowledgeBase:
    """Query interface for structured ATLAS knowledge."""

    def __init__(self, atlas_path: Path | str | None = None) -> None:
        if atlas_path is None:
            atlas_path = self._find_atlas()
        self.parser = AtlasParser(Path(atlas_path))
        self._data: AtlasData | None = None
        logger.info(f"KnowledgeBase: {self.parser.atlas_path}")

    @staticmethod
    def _find_atlas() -> Path:
        candidates = [
            Path("data/DEEP_ATLAS.md"),
            Path(__file__).resolve().parents[3] / "data" / "DEEP_ATLAS.md",
        ]
        for c in candidates:
            if c.exists():
                return c
        return Path("data/DEEP_ATLAS.md")

    @property
    def data(self) -> AtlasData:
        if self._data is None:
            self._data = self.parser.parse()
        return self._data

    def reload(self) -> None:
        self._data = None
        logger.info("KnowledgeBase reloaded")

    # ─── Queries ───────────────────────────────

    def get_soc(self, key: str) -> SOCInfo | None:
        return self.data.socs.get(key.lower())

    def get_protocol(self, name: str) -> Protocol | None:
        return self.data.protocols.get(name.lower())

    def get_protocols_for_soc(self, soc_key: str) -> list[Protocol]:
        return [p for p in self.data.protocols.values() if soc_key in p.soc_families]

    def get_playbook(self, playbook_id: str) -> Playbook | None:
        return self.data.playbooks.get(playbook_id)

    def find_playbook(self, symptom: str, soc: str | None = None) -> list[Playbook]:
        results = []
        for pb in self.data.playbooks.values():
            if (symptom.lower() in pb.symptom.lower() or symptom.lower() in pb.id.lower()) and (soc is None or pb.soc is None or pb.soc == soc):
                    results.append(pb)
        return results

    def list_playbooks(self) -> list[Playbook]:
        return list(self.data.playbooks.values())

    def get_tool(self, name: str) -> Tool | None:
        return self.data.tools.get(name)

    def list_tools(self) -> list[Tool]:
        return list(self.data.tools.values())

    def get_secret_codes(self, manufacturer: str) -> dict[str, str]:
        return self.data.secret_codes.get(manufacturer.lower(), {})

    def search(self, query: str) -> dict[str, list]:
        query_lower = query.lower()
        return {
            "socs": [k for k, v in self.data.socs.items() if query_lower in v.name.lower() or query_lower in v.manufacturer.lower()],
            "protocols": [k for k, v in self.data.protocols.items() if query_lower in v.name.lower() or query_lower in v.description.lower()],
            "playbooks": [k for k, v in self.data.playbooks.items() if query_lower in v.title.lower() or query_lower in v.symptom.lower()],
            "tools": [k for k, v in self.data.tools.items() if query_lower in v.name.lower() or query_lower in v.function.lower()],
        }

    def to_json(self) -> str:
        return self.parser.to_json()


_kb_instance: KnowledgeBase | None = None


def get_knowledge_base() -> KnowledgeBase:
    global _kb_instance
    if _kb_instance is None:
        _kb_instance = KnowledgeBase()
    return _kb_instance

"""Unit tests for zenith knowledge.atlas_parser module."""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest

from zenith.knowledge.atlas_parser import (
    AtlasData,
    AtlasParser,
    Playbook,
    Protocol,
    SOCInfo,
    Tool,
)


SAMPLE_ATLAS = """# Tier 1 — Silicon Atlases

## Qualcomm Snapdragon

- **Primary BootROM —** PBL (Primary Boot Loader)
- **Secondary Bootloader —** SBL (Secondary Boot Loader)
- **EDL (Emergency Download Mode) —** USB VID:05C6 PID:9008
- **Fastboot** — Standard Android Fastboot
- **Recovery** — Stock recovery
- **Diag Mode** — QDSS trace

## MediaTek Dimensity/Helio

- **BROM Mode** — USB VID:0E8D
- **Preloader Mode** — Preloader USB
- **Fastboot** — Standard Fastboot
- **Meta Mode** — Factory test mode

# Tier 8 — Real-World Playbooks

## hard-brick-qualcomm

- **Symptom:** hard-brick
- **SoC:** qualcomm
- **Risk:** high
- **Step 1:** Identify 9008 in Device Manager
- **Step 2:** Force EDL via test point
- **Step 3:** Flash firmware via edl
"""


class TestAtlasData:
    def test_empty_data(self) -> None:
        data = AtlasData()
        assert len(data.socs) == 0
        assert len(data.protocols) == 0
        assert len(data.playbooks) == 0
        assert len(data.tools) == 0

    def test_add_soc(self) -> None:
        data = AtlasData()
        soc = SOCInfo(name="Test SoC", manufacturer="TestCorp")
        data.socs["test"] = soc
        assert data.socs["test"].name == "Test SoC"
        assert data.socs["test"].manufacturer == "TestCorp"

    def test_add_playbook(self) -> None:
        data = AtlasData()
        pb = Playbook(id="test-1", title="Test Playbook", symptom="bootloop", risk_level="high")
        data.playbooks[pb.id] = pb
        assert data.playbooks["test-1"].risk_level == "high"


class TestAtlasParser:
    def test_init_with_path(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        assert parser.atlas_path == atlas_path
        assert parser._content is None

    def test_content_lazy_load(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        content = parser.content
        assert "Qualcomm Snapdragon" in content
        assert parser._content is not None

    def test_content_mtime_cache(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        c1 = parser.content
        atlas_path.write_text("new content", encoding="utf-8")
        c2 = parser.content
        assert c1 == c2

    def test_content_mtime_cache_invalidated_by_reload(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        c1 = parser.content
        atlas_path.write_text("new content", encoding="utf-8")
        parser.reload()
        c2 = parser.content
        assert c1 != c2
        assert "new content" in c2

    def test_content_missing_file(self, temp_dir: Path) -> None:
        parser = AtlasParser(temp_dir / "nonexistent.md")
        assert parser.content == ""

    def test_data_lazy_parse(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        assert parser._data is None
        data = parser.data
        assert parser._data is not None
        assert data is parser.data

    def test_parse_socs(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        assert "qualcomm" in data.socs
        assert "mediatek" in data.socs
        assert data.socs["qualcomm"].manufacturer == "Qualcomm"

    def test_parse_socs_has_recovery_modes(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        qualcomm = data.socs["qualcomm"]
        assert len(qualcomm.recovery_modes) >= 1

    def test_parse_protocols_has_defaults(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        assert "adb" in data.protocols
        assert "fastboot" in data.protocols
        assert "edl" in data.protocols
        assert "brom" in data.protocols
        assert data.protocols["edl"].usb_vid == "05C6"

    def test_parse_playbooks_has_defaults(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        assert "hard-brick-qualcomm" in data.playbooks
        assert data.playbooks["hard-brick-qualcomm"].risk_level == "high"

    def test_parse_tools_has_defaults(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        assert "edl" in data.tools
        assert data.tools["edl"].category == "Qualcomm EDL"

    def test_parse_secret_codes(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        assert "samsung" in data.secret_codes
        assert "xiaomi" in data.secret_codes
        assert "*#0*#" in data.secret_codes["samsung"]

    def test_reload(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        d1 = parser.data
        atlas_path.write_text("# New content\n", encoding="utf-8")
        d2 = parser.reload()
        assert d1 is not d2

    def test_to_json(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        j = parser.to_json()
        result = json.loads(j)
        assert "socs" in result
        assert "protocols" in result
        assert "playbooks" in result
        assert "tools" in result

    def test_validate_risk_levels(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        for pb in data.playbooks.values():
            assert pb.risk_level in {"low", "medium", "high", "critical"}

    def test_extract_section(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        section = parser._extract_section(parser.content, "Qualcomm")
        assert section is not None
        assert "Snapdragon" in section

    def test_extract_section_nonexistent(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text(SAMPLE_ATLAS, encoding="utf-8")
        parser = AtlasParser(atlas_path)
        section = parser._extract_section(parser.content, "NonexistentSection")
        assert section is None

    def test_empty_file(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text("", encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        assert len(data.socs) >= 2

    def test_apply_defaults_fallback(self, temp_dir: Path) -> None:
        atlas_path = temp_dir / "DEEP_ATLAS.md"
        atlas_path.write_text("# Nothing useful\n", encoding="utf-8")
        parser = AtlasParser(atlas_path)
        data = parser.parse()
        assert len(data.socs) >= 2
        assert len(data.protocols) >= 5
        assert len(data.playbooks) >= 5


class TestSOCInfo:
    def test_creation(self) -> None:
        soc = SOCInfo(name="Test", manufacturer="TestCorp")
        assert soc.name == "Test"
        assert soc.manufacturer == "TestCorp"
        assert soc.boot_chain == []
        assert soc.recovery_modes == []

    def test_with_data(self) -> None:
        soc = SOCInfo(
            name="Qualcomm Snapdragon",
            manufacturer="Qualcomm",
            boot_chain=["PBL", "SBL"],
            recovery_modes=["EDL", "Fastboot"],
        )
        assert len(soc.boot_chain) == 2
        assert "EDL" in soc.recovery_modes


class TestPlaybook:
    def test_creation(self) -> None:
        pb = Playbook(id="test-1", title="Test", symptom="bootloop", risk_level="medium")
        assert pb.id == "test-1"
        assert pb.risk_level == "medium"
        assert pb.steps == []

    def test_with_steps(self) -> None:
        steps = [{"step": 1, "desc": "Do A"}, {"step": 2, "desc": "Do B"}]
        pb = Playbook(id="pb-1", title="Firmware Rescue", symptom="hard-brick", steps=steps)
        assert len(pb.steps) == 2
        assert pb.steps[0]["desc"] == "Do A"


class TestProtocol:
    def test_creation(self) -> None:
        p = Protocol(name="EDL", description="Qualcomm EDL mode", soc_families=["qualcomm"])
        assert p.name == "EDL"
        assert "qualcomm" in p.soc_families

    def test_with_usb_ids(self) -> None:
        p = Protocol(name="EDL", description="EDL", usb_vid="05C6", usb_pid="9008")
        assert p.usb_vid == "05C6"
        assert p.usb_pid == "9008"


class TestTool:
    def test_creation(self) -> None:
        t = Tool(name="edl", category="Qualcomm EDL", platform=["Python"])
        assert t.name == "edl"
        assert t.category == "Qualcomm EDL"
        assert "Python" in t.platform

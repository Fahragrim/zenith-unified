"""Unit tests for zenith package foundation."""

from __future__ import annotations

import pytest

from zenith import __version__, __author__, __description__


class TestPackage:
    """Tests for the zenith package metadata."""

    def test_version_is_string(self) -> None:
        assert isinstance(__version__, str)

    def test_version_format(self) -> None:
        parts = __version__.split(".")
        assert len(parts) == 3
        assert all(p.isdigit() for p in parts)

    def test_author_is_string(self) -> None:
        assert isinstance(__author__, str)
        assert len(__author__) > 0

    def test_description_is_string(self) -> None:
        assert isinstance(__description__, str)
        assert len(__description__) > 0


class TestConfig:
    """Tests for the configuration module."""

    def test_settings_singleton(self) -> None:
        from zenith.config import get_settings, ZenithSettings

        s1 = get_settings()
        s2 = get_settings()
        assert s1 is s2
        assert isinstance(s1, ZenithSettings)

    def test_settings_defaults(self) -> None:
        from zenith.config import get_settings

        settings = get_settings()
        assert settings.dry_run is False
        assert settings.require_consent is True
        assert settings.auto_backup is True
        assert settings.ai_provider == "local"
        assert settings.log_level == "INFO"
        assert settings.gui_framework == "pyside6"

    def test_config_dir_default(self) -> None:
        from zenith.config import get_settings

        settings = get_settings()
        assert settings.config_dir.name == ".zenith"

    def test_temp_dir_fixture(self, temp_dir) -> None:
        assert temp_dir.exists()
        assert temp_dir.is_dir()

    def test_sample_device_info_fixture(self, sample_device_info) -> None:
        assert sample_device_info["serial"] == "emulator-5554"
        assert sample_device_info["model"] == "Pixel 7"
        assert sample_device_info["soc"] == "Google Tensor G2"

    def test_sample_adb_output_fixture(self, sample_adb_devices_output) -> None:
        assert "emulator-5554" in sample_adb_devices_output
        assert "R5CT1234ABCD" in sample_adb_devices_output
        assert "device" in sample_adb_devices_output


class TestCLI:
    """Tests for the CLI entry point."""

    def test_cli_main_imports(self) -> None:
        from zenith.cli.main import main
        assert callable(main)

    def test_cli_help(self) -> None:
        from click.testing import CliRunner
        from zenith.cli.main import main

        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Zenith Unified" in result.output

    def test_cli_version(self) -> None:
        from click.testing import CliRunner
        from zenith.cli.main import main

        runner = CliRunner()
        result = runner.invoke(main, ["version"])
        assert result.exit_code == 0
        assert __version__ in result.output

    def test_cli_discover_stub(self) -> None:
        from click.testing import CliRunner
        from zenith.cli.main import main

        runner = CliRunner()
        result = runner.invoke(main, ["discover"])
        assert result.exit_code == 0
        assert "ZENITH DEVICE DISCOVERY" in result.output

    def test_cli_ai(self) -> None:
        from click.testing import CliRunner
        from zenith.cli.main import main

        runner = CliRunner()
        result = runner.invoke(main, ["ai"])
        assert result.exit_code == 0
        assert "Usage" in result.output or "zenith ai" in result.output

    def test_cli_arsenal(self) -> None:
        from click.testing import CliRunner
        from zenith.cli.main import main

        runner = CliRunner()
        result = runner.invoke(main, ["arsenal"])
        assert result.exit_code == 0
        assert "SoCs" in result.output or "arsenal" in result.output.lower()

"""Unit tests for zenith.adapters._runner — CommandResult and run_command."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from zenith.adapters._runner import CommandResult, run_command


class TestCommandResult:
    def test_creation_with_all_fields(self) -> None:
        r = CommandResult(
            success=True,
            command="adb devices",
            stdout="device",
            stderr="",
            returncode=0,
            data={"serial": "123"},
        )
        assert r.success is True
        assert r.command == "adb devices"
        assert r.stdout == "device"
        assert r.stderr == ""
        assert r.returncode == 0
        assert r.data == {"serial": "123"}

    def test_creation_with_defaults(self) -> None:
        r = CommandResult(success=False, command="test")
        assert r.success is False
        assert r.command == "test"
        assert r.stdout == ""
        assert r.stderr == ""
        assert r.returncode == -1
        assert r.data == {}

    def test_bool_true_when_success_true(self) -> None:
        r = CommandResult(success=True, command="echo hello")
        assert bool(r) is True

    def test_bool_false_when_success_false(self) -> None:
        r = CommandResult(success=False, command="bad_command")
        assert bool(r) is False

    def test_data_field_mutable(self) -> None:
        r = CommandResult(success=True, command="test", data={"key": "val"})
        r.data["extra"] = 42
        assert r.data == {"key": "val", "extra": 42}

    def test_data_field_default_empty_dict(self) -> None:
        r = CommandResult(success=True, command="test")
        assert r.data == {}
        r.data["a"] = 1
        assert r.data == {"a": 1}


class TestRunCommand:
    def test_success_path(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "hello\n"
        mock_proc.stderr = ""

        with patch("zenith.adapters._runner.subprocess.run", return_value=mock_proc) as m:
            result = run_command("echo", ["hello"])

        assert result.success is True
        assert result.command == "echo hello"
        assert result.stdout == "hello"
        assert result.stderr == ""
        assert result.returncode == 0
        m.assert_called_once_with(
            ["echo", "hello"], capture_output=True, text=True, timeout=60
        )

    def test_failure_path_nonzero_returncode(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "error occurred"

        with patch("zenith.adapters._runner.subprocess.run", return_value=mock_proc):
            result = run_command("adb", ["devices"])

        assert result.success is False
        assert result.returncode == 1
        assert result.stderr == "error occurred"

    def test_timeout_expired(self) -> None:
        with patch("zenith.adapters._runner.subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="test", timeout=5)):
            result = run_command("sleep", ["10"])

        assert result.success is False
        assert result.command == "sleep 10"
        assert result.stderr == "Timed out"
        assert result.returncode == -1

    def test_file_not_found(self) -> None:
        with patch("zenith.adapters._runner.subprocess.run", side_effect=FileNotFoundError()):
            result = run_command("nonexistent_binary", ["--help"])

        assert result.success is False
        assert result.command == "nonexistent_binary --help"
        assert result.stderr == "Binary not found: nonexistent_binary"
        assert result.returncode == -1

    def test_generic_exception(self) -> None:
        with patch("zenith.adapters._runner.subprocess.run", side_effect=PermissionError("Access denied")):
            result = run_command("adb", ["shell"])

        assert result.success is False
        assert result.command == "adb shell"
        assert result.stderr == "Access denied"
        assert result.returncode == -1

    def test_timeout_parameter_passed_through(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        with patch("zenith.adapters._runner.subprocess.run", return_value=mock_proc) as m:
            run_command("fastboot", ["devices"], timeout=120)

        m.assert_called_once_with(
            ["fastboot", "devices"], capture_output=True, text=True, timeout=120
        )

    def test_strips_stdout(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "  hello world  \n"
        mock_proc.stderr = ""

        with patch("zenith.adapters._runner.subprocess.run", return_value=mock_proc):
            result = run_command("echo", ["hello"])

        assert result.stdout == "hello world"

    def test_strips_stderr(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "  warning  \n"

        with patch("zenith.adapters._runner.subprocess.run", return_value=mock_proc):
            result = run_command("bad", ["cmd"])

        assert result.stderr == "warning"

    def test_empty_stdout_is_empty_string(self) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = ""
        mock_proc.stderr = ""

        with patch("zenith.adapters._runner.subprocess.run", return_value=mock_proc):
            result = run_command("true", [])

        assert result.stdout == ""
        assert result.success is True

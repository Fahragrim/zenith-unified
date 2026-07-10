"""Unit tests for zenith.tools package — VCC Matrix, Fastboot Fuzz, Sahara Ping,
Token Hunter, Panic Inject, Arsenal Shell."""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from zenith.tools.arsenal_shell import (
    ARSENAL_ACTIONS,
    ArsenalResult,
    list_actions,
    run_action,
    run_all,
)
from zenith.tools.fastboot_fuzz import OEM_COMMANDS, fuzz_oem_commands
from zenith.tools.panic_inject import CRASH_PAYLOADS, RISK_WARNING, scan_and_inject
from zenith.tools.sahara_ping import sahara_ping_scan
from zenith.tools.token_hunter import TOKEN_PATTERN, token_hunt_logcat
from zenith.tools.vcc_matrix import calculate, matrix

# ─── VCC Matrix ───────────────────────────────────────────────────────────


class TestVccMatrixCalculate:
    def test_default_values(self) -> None:
        r = calculate()
        assert isinstance(r, dict)
        assert r["cpu_mhz"] == 200.0
        assert r["cycle_ns"] == 5.0  # 1000/200
        assert r["glitch_width_ns"] == 5.0  # 5.0 * 1
        assert r["brown_out_reset_ns"] == 15.0  # 5.0 * 3
        assert "recommendation" in r
        assert "hardware" in r
        assert "risks" in r

    def test_custom_values(self) -> None:
        r = calculate(cpu_mhz=50.0, target_instructions=4)
        assert r["cpu_mhz"] == 50.0
        assert r["cycle_ns"] == 20.0  # 1000/50
        assert r["glitch_width_ns"] == 80.0  # 20.0 * 4
        assert r["brown_out_reset_ns"] == 60.0  # 20.0 * 3

    def test_warning_when_glitch_exceeds_bor(self) -> None:
        r = calculate(cpu_mhz=100.0, target_instructions=4)
        # cycle_ns=10, glitch=40, bor=30
        assert r["warning"] is True
        assert "exceeds BOR" in r["warning_text"]
        assert "Brown-out Reset will trigger" in r["warning_text"]

    def test_no_warning_when_safe(self) -> None:
        r = calculate(cpu_mhz=400.0, target_instructions=1)
        # cycle_ns=2.5, glitch=2.5, bor=7.5
        assert r["warning"] is False
        assert r["warning_text"] == ""

    def test_hardware_section_structure(self) -> None:
        r = calculate()
        hw = r["hardware"]
        assert isinstance(hw, dict)
        assert "emfi" in hw
        assert "serial" in hw
        assert "reference" in hw

    def test_risks_section_structure(self) -> None:
        r = calculate()
        risks = r["risks"]
        assert isinstance(risks, dict)
        assert "efuse" in risks
        assert "brick" in risks
        assert "mitigation" in risks

    def test_recommendation_includes_values(self) -> None:
        r = calculate(cpu_mhz=150.0, target_instructions=2)
        assert "150" in r["recommendation"]
        assert "2" in r["recommendation"]
        assert "150.0 MHz" in r["recommendation"]


class TestVccMatrixMatrix:
    def test_default_matrix(self) -> None:
        rows = matrix()
        # cpu_min=100, cpu_max=400, step=50 → 7 frequencies
        # 7 * 3 instructions = 21 rows
        assert len(rows) == 21

    def test_row_structure(self) -> None:
        rows = matrix(cpu_min=100, cpu_max=100, step=50)
        assert len(rows) == 3  # 1 freq × 3 instructions
        row = rows[0]
        assert "cpu_mhz" in row
        assert "instructions" in row
        assert "glitch_width_ns" in row
        assert "brown_out" in row

    def test_edge_case_min_equals_max(self) -> None:
        rows = matrix(cpu_min=250, cpu_max=250, step=50)
        assert len(rows) == 3
        for row in rows:
            assert row["cpu_mhz"] == 250

    def test_edge_case_step_larger_than_range(self) -> None:
        rows = matrix(cpu_min=100, cpu_max=150, step=200)
        # Only one iteration: range(100, 151, 200) → [100]
        assert len(rows) == 3
        assert rows[0]["cpu_mhz"] == 100

    def test_glitch_width_calculation(self) -> None:
        rows = matrix(cpu_min=200, cpu_max=200, step=50)
        # cycle_ns = 1000/200 = 5
        # instr=1 → glitch=5, instr=2 → glitch=10, instr=4 → glitch=20
        assert rows[0]["glitch_width_ns"] == 5.0
        assert rows[1]["glitch_width_ns"] == 10.0
        assert rows[2]["glitch_width_ns"] == 20.0

    def test_brown_out_flag(self) -> None:
        rows = matrix(cpu_min=100, cpu_max=100, step=50)
        # cycle_ns=10, bor=30
        # instr=1 → glitch=10 → not warning
        # instr=2 → glitch=20 → not warning
        # instr=4 → glitch=40 → warning
        assert rows[0]["brown_out"] is False
        assert rows[1]["brown_out"] is False
        assert rows[2]["brown_out"] is True


# ─── Fastboot Fuzz ────────────────────────────────────────────────────────


class TestFastbootFuzzOemCommands:
    def test_oem_commands_list_not_empty(self) -> None:
        assert len(OEM_COMMANDS) > 0
        assert "unlock" in OEM_COMMANDS

    def test_returns_list_on_subprocess_error(self) -> None:
        results = fuzz_oem_commands(fastboot_path="nonexistent_fastboot", delay=0)
        assert isinstance(results, list)
        assert len(results) == len(OEM_COMMANDS)

    def test_each_result_has_expected_keys(self) -> None:
        results = fuzz_oem_commands(fastboot_path="nonexistent_fastboot", delay=0)
        for entry in results:
            assert "command" in entry
            assert "response" in entry
            assert "interesting" in entry
            assert entry["command"].startswith("fastboot oem ")

    def test_interesting_false_on_exception(self) -> None:
        results = fuzz_oem_commands(fastboot_path="nonexistent_fastboot", delay=0)
        for entry in results:
            assert entry["interesting"] is False

    @patch("zenith.tools.fastboot_fuzz.subprocess.run")
    def test_interesting_when_response_unknown(self, mock_run: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.stderr = "unknown command\n"
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        results = fuzz_oem_commands(fastboot_path="fastboot", delay=0)
        for entry in results:
            assert entry["interesting"] is False

    @patch("zenith.tools.fastboot_fuzz.subprocess.run")
    def test_interesting_when_not_allowed(self, mock_run: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.stderr = "not allowed\n"
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        results = fuzz_oem_commands(fastboot_path="fastboot", delay=0)
        for entry in results:
            assert entry["interesting"] is False

    @patch("zenith.tools.fastboot_fuzz.subprocess.run")
    def test_interesting_flagged(self, mock_run: MagicMock) -> None:
        mock_proc = MagicMock()
        mock_proc.stderr = "OKAY\n"
        mock_proc.stdout = ""
        mock_run.return_value = mock_proc

        results = fuzz_oem_commands(fastboot_path="fastboot", delay=0)
        interesting = [e for e in results if e["interesting"]]
        assert len(interesting) == len(OEM_COMMANDS)

    @patch("zenith.tools.fastboot_fuzz.subprocess.run")
    def test_exception_handled_gracefully(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = RuntimeError("boom")

        results = fuzz_oem_commands(fastboot_path="fastboot", delay=0)
        assert len(results) == len(OEM_COMMANDS)
        for entry in results:
            assert "boom" in entry["response"]
            assert entry["interesting"] is False


# ─── Sahara Ping ──────────────────────────────────────────────────────────


class TestSaharaPing:
    def test_returns_error_when_pyserial_not_installed(self) -> None:
        import builtins
        original_import = builtins.__import__

        def _mock_import(name: str, *args: object, **kw: object) -> object:
            if name == "serial":
                raise ImportError("No module named serial")
            return original_import(name, *args, **kw)

        with patch.dict("sys.modules", {"serial": None}):
            with patch("builtins.__import__", side_effect=_mock_import):
                result = sahara_ping_scan(max_port=1)
                assert result == [{"error": "pyserial not installed"}]

    @patch("serial.Serial")
    def test_scan_scans_ports(self, mock_serial: MagicMock) -> None:
        results = sahara_ping_scan(max_port=3)
        assert isinstance(results, list)
        assert mock_serial.call_count <= 3

    @patch("serial.Serial")
    def test_found_device_added(self, mock_serial: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.read.return_value = b"\x01\x02\x03\x04" + b"\x00" * 44
        mock_serial.return_value = mock_instance

        results = sahara_ping_scan(max_port=2)
        assert len(results) > 0
        for r in results:
            assert "port" in r
            assert "response_hex" in r
            assert "response_len" in r
            assert r["response_len"] == 48

    @patch("serial.Serial")
    def test_no_device_returns_empty(self, mock_serial: MagicMock) -> None:
        mock_instance = MagicMock()
        mock_instance.read.return_value = b""
        mock_serial.return_value = mock_instance

        results = sahara_ping_scan(max_port=3)
        assert len(results) == 0

    @patch("serial.Serial")
    def test_serial_exception_skipped(self, mock_serial: MagicMock) -> None:
        mock_serial.side_effect = OSError("port not found")

        results = sahara_ping_scan(max_port=3)
        assert len(results) == 0


# ─── Token Hunter ─────────────────────────────────────────────────────────


class TestTokenHunterPattern:
    def test_matches_jwt(self) -> None:
        text = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8"
        assert TOKEN_PATTERN.search(text) is not None

    def test_matches_bearer_token(self) -> None:
        text = "Bearer ya29.a0AfH6SMC8a8b9c0d1e2f3g4h5i6j7k8l9m0n1o2p3"
        assert TOKEN_PATTERN.search(text) is not None

    def test_matches_password(self) -> None:
        text = "password=My$ecureP@ss1"
        assert TOKEN_PATTERN.search(text) is not None

    def test_matches_rsa_private_key(self) -> None:
        text = "-----BEGIN RSA PRIVATE KEY-----"
        assert TOKEN_PATTERN.search(text) is not None

    def test_matches_generic_private_key(self) -> None:
        text = "-----BEGIN PRIVATE KEY-----"
        assert TOKEN_PATTERN.search(text) is not None

    def test_no_match_normal_text(self) -> None:
        text = "This is a normal log line with no secrets"
        assert TOKEN_PATTERN.search(text) is None

    def test_no_match_partial_jwt(self) -> None:
        text = "eyJhbGciOiJIUzI1NiJ9.not-a-full-jwt"
        assert TOKEN_PATTERN.search(text) is None


class TestTokenHunterLogcat:
    def test_returns_empty_list_no_tokens(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "normal log line\n",
            "",
        ]
        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            lambda *a, **kw: mock_proc,
        )

        # Ensure it terminates quickly by patching time
        monkeypatch.setattr("time.time", lambda: 0)

        results = token_hunt_logcat(duration=1)
        assert results == []

    def test_finds_tokens_in_logcat(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.signature_part\n",
            "",
        ]
        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            lambda *a, **kw: mock_proc,
        )

        monkeypatch.setattr("time.time", lambda: 0)

        results = token_hunt_logcat(duration=1)
        assert len(results) == 1
        assert results[0]["match"].startswith("eyJ")
        assert "eyJ" in results[0]["line"]

    def test_finds_bearer_token(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "Authorization: Bearer abc.def.ghi\n",
            "",
        ]
        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            lambda *a, **kw: mock_proc,
        )

        monkeypatch.setattr("time.time", lambda: 0)

        results = token_hunt_logcat(duration=1)
        assert len(results) == 1
        assert results[0]["match"] == "Bearer abc.def.ghi"

    def test_temp_file_cleanup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = ["", ""]
        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            lambda *a, **kw: mock_proc,
        )
        monkeypatch.setattr("time.time", lambda: 0)

        # Patch TemporaryDirectory to verify cleanup
        mock_tmp = MagicMock()
        mock_tmp.name = "C:\\tmp\\zenith_token_xxx"
        monkeypatch.setattr(
            "zenith.tools.token_hunter.tempfile.TemporaryDirectory",
            lambda **kw: mock_tmp,
        )

        results = token_hunt_logcat(duration=1)
        mock_tmp.cleanup.assert_called_once()

    def test_custom_output_file(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "password=My$ecureP@ss1\n",
            "",
        ]
        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            lambda *a, **kw: mock_proc,
        )
        monkeypatch.setattr("time.time", lambda: 0)

        out_file = tmp_path / "custom_findings.txt"
        results = token_hunt_logcat(duration=1, output_file=str(out_file))
        assert len(results) == 1
        assert out_file.exists()
        content = out_file.read_text()
        assert "My$ecureP@ss1" in content

    def test_exception_returns_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise RuntimeError("adb not found")

        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            _raise,
        )

        results = token_hunt_logcat(duration=1)
        assert results == [{"error": "adb not found"}]

    def test_findings_written_to_temp_file(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "Bearer secret123\n",
            "",
        ]
        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            lambda *a, **kw: mock_proc,
        )
        monkeypatch.setattr("time.time", lambda: 0)

        # Use a real temp dir so we can inspect file writing
        with tempfile.TemporaryDirectory(prefix="zenith_token_test_") as tmpdir:
            real_tmp = MagicMock()
            real_tmp.name = tmpdir
            monkeypatch.setattr(
                "zenith.tools.token_hunter.tempfile.TemporaryDirectory",
                lambda **kw: real_tmp,
            )
            results = token_hunt_logcat(duration=1)

        assert len(results) == 1
        assert "Bearer secret123" in results[0]["match"]

    def test_readline_trigger_match(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only lines matching the pattern trigger findings."""
        mock_proc = MagicMock()
        mock_proc.stdout.readline.side_effect = [
            "safe line\n",
            "password=hunter2\n",
            "also safe\n",
            "",
        ]
        monkeypatch.setattr(
            "zenith.tools.token_hunter.subprocess.Popen",
            lambda *a, **kw: mock_proc,
        )
        monkeypatch.setattr("time.time", lambda: 0)

        results = token_hunt_logcat(duration=1)
        assert len(results) == 1
        assert results[0]["match"] == "password=hunter2"


# ─── Panic Inject ─────────────────────────────────────────────────────────


class TestPanicInjectCrashPayloads:
    def test_crash_payloads_not_empty(self) -> None:
        assert len(CRASH_PAYLOADS) > 0

    def test_risk_warning_not_empty(self) -> None:
        assert len(RISK_WARNING) > 0
        assert "WARNING" in RISK_WARNING
        assert "NVRAM" in RISK_WARNING

    def test_contains_all_expected_payloads(self) -> None:
        expected = ["AT+CFUN=0", "AT+SYSDUMP=1,0", "AT$QCPWRDN", "AT+KDEAD", "AT^RESET"]
        for payload in expected:
            assert payload in CRASH_PAYLOADS


class TestPanicInjectScan:
    def test_returns_error_when_pyserial_not_installed(self) -> None:
        import builtins
        original_import = builtins.__import__

        def _mock_import(name: str, *args: object, **kw: object) -> object:
            if name == "serial":
                raise ImportError("No module named serial")
            return original_import(name, *args, **kw)

        with patch.dict("sys.modules", {"serial": None}):
            with patch("builtins.__import__", side_effect=_mock_import):
                result = scan_and_inject()
                assert result == [{"error": "pyserial not installed"}]

    @patch("serial.tools.list_ports.comports")
    def test_no_vulnerable_ports(self, mock_comports: MagicMock) -> None:
        mock_port = MagicMock()
        mock_port.description = "USB to UART Bridge"
        mock_port.device = "COM1"
        mock_comports.return_value = [mock_port]

        results = scan_and_inject()
        assert results == [{"error": "No vulnerable ports found. Dial *#0808# on device?"}]

    @patch("serial.tools.list_ports.comports")
    def test_dry_run_mode(self, mock_comports: MagicMock) -> None:
        mock_port = MagicMock()
        mock_port.description = "Qualcomm HS-USB Diag"
        mock_port.device = "COM4"
        mock_comports.return_value = [mock_port]

        results = scan_and_inject(dry_run=True)
        assert len(results) == 1
        assert results[0]["port"] == "COM4"
        assert results[0]["status"] == "dry-run"
        assert results[0]["description"] == "Qualcomm HS-USB Diag"

    @patch("serial.tools.list_ports.comports")
    def test_dry_run_skips_injection(self, mock_comports: MagicMock) -> None:
        """In dry_run mode, no serial connection is attempted."""
        mock_port = MagicMock()
        mock_port.description = "modem"
        mock_port.device = "COM5"
        mock_comports.return_value = [mock_port]

        with patch("serial.Serial") as mock_ser:
            results = scan_and_inject(dry_run=True)
            mock_ser.assert_not_called()

    @patch("serial.Serial")
    @patch("serial.tools.list_ports.comports")
    def test_injection_on_vulnerable_port(
        self, mock_comports: MagicMock, mock_serial: MagicMock
    ) -> None:
        mock_port = MagicMock()
        mock_port.description = "Qualcomm Diag Port"
        mock_port.device = "COM3"
        mock_comports.return_value = [mock_port]

        mock_ser_instance = MagicMock()
        mock_ser_instance.read.return_value = b"OK\r\n"
        mock_ser_instance.__enter__.return_value = mock_ser_instance
        mock_serial.return_value = mock_ser_instance

        results = scan_and_inject(dry_run=False)
        assert len(results) > 1  # payload results + completion
        last_entry = results[-1]
        assert last_entry["status"] == "complete"
        assert "Check device screen" in last_entry["note"]

    @patch("serial.Serial")
    @patch("serial.tools.list_ports.comports")
    def test_port_closed_on_exception(
        self, mock_comports: MagicMock, mock_serial: MagicMock
    ) -> None:
        mock_port = MagicMock()
        mock_port.description = "sprd diag"
        mock_port.device = "COM7"
        mock_comports.return_value = [mock_port]

        mock_ser_instance = MagicMock()
        mock_ser_instance.write.side_effect = OSError("port died")
        mock_ser_instance.__enter__.return_value = mock_ser_instance
        mock_serial.return_value = mock_ser_instance

        results = scan_and_inject(dry_run=False)
        assert any(r.get("status") == "port_closed" for r in results)

    @patch("serial.Serial")
    @patch("serial.tools.list_ports.comports")
    def test_injection_exception_handled(
        self, mock_comports: MagicMock, mock_serial: MagicMock
    ) -> None:
        mock_port = MagicMock()
        mock_port.description = "modem"
        mock_port.device = "COM8"
        mock_comports.return_value = [mock_port]

        mock_ser_instance = MagicMock()
        mock_ser_instance.write.side_effect = OSError("modem died")
        mock_ser_instance.__enter__.return_value = mock_ser_instance
        mock_serial.return_value = mock_ser_instance

        results = scan_and_inject(dry_run=False)
        assert any(r.get("status") == "port_closed" for r in results)

    @patch("serial.Serial")
    @patch("serial.tools.list_ports.comports")
    def test_crash_payloads_sent_in_order(
        self, mock_comports: MagicMock, mock_serial: MagicMock
    ) -> None:
        mock_port = MagicMock()
        mock_port.description = "diag"
        mock_port.device = "COM9"
        mock_comports.return_value = [mock_port]

        mock_ser_instance = MagicMock()
        mock_ser_instance.read.return_value = b"OK\r\n"
        mock_ser_instance.__enter__.return_value = mock_ser_instance
        mock_serial.return_value = mock_ser_instance

        results = scan_and_inject(dry_run=False)
        payload_results = [r for r in results if "payload" in r]
        sent_payloads = [r["payload"] for r in payload_results]
        for pl in CRASH_PAYLOADS:
            if pl == "AT^RESET":
                continue
            assert pl in sent_payloads


# ─── Arsenal Shell ────────────────────────────────────────────────────────


class TestArsenalShellResult:
    def test_dataclass_defaults(self) -> None:
        r = ArsenalResult(action="test")
        assert r.action == "test"
        assert r.success is False
        assert r.output == ""
        assert r.data == {}

    def test_dataclass_custom_values(self) -> None:
        r = ArsenalResult(
            action="fingerprint",
            success=True,
            output="some output",
            data={"key": "val"},
        )
        assert r.action == "fingerprint"
        assert r.success is True
        assert r.output == "some output"
        assert r.data == {"key": "val"}


class TestArsenalShellListActions:
    def test_returns_all_actions(self) -> None:
        actions = list_actions()
        assert len(actions) == len(ARSENAL_ACTIONS)

    def test_structure_has_required_keys(self) -> None:
        actions = list_actions()
        for a in actions:
            assert "id" in a
            assert "title" in a
            assert "desc" in a
            assert "requires_fastboot" in a

    def test_distinct_ids(self) -> None:
        actions = list_actions()
        ids = [a["id"] for a in actions]
        assert len(ids) == len(set(ids))

    def test_fastboot_actions_marked(self) -> None:
        actions = list_actions()
        fb_actions = [a for a in actions if a["requires_fastboot"]]
        assert len(fb_actions) == 2
        assert fb_actions[0]["id"] == "fastboot_getvar"
        assert fb_actions[1]["id"] == "fastboot_unlock"


class TestArsenalShellRunAction:
    def test_unknown_action_returns_error(self) -> None:
        r = run_action("nonexistent")
        assert r.success is False
        assert "Unknown action" in r.output
        assert r.action == "nonexistent"

    def test_successful_execution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Some device info\n"
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            lambda *a, **kw: mock_proc,
        )

        r = run_action("fingerprint")
        assert r.success is True
        assert r.action == "fingerprint"
        assert "Some device info" in r.output

    def test_failed_execution(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 1
        mock_proc.stdout = ""
        mock_proc.stderr = "error: no device\n"
        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            lambda *a, **kw: mock_proc,
        )

        r = run_action("logcat")
        assert r.success is False
        assert "error: no device" in r.output

    def test_extract_data_from_getprop(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = (
            "[ro.product.model]: [Pixel 7]\n"
            "[ro.board.platform]: [gs201]\n"
            "[ro.build.version.release]: [14]\n"
            "[ro.boot.verifiedbootstate]: [green]\n"
            "[ro.product.manufacturer]: [Google]\n"
        )
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            lambda *a, **kw: mock_proc,
        )

        r = run_action("fingerprint")
        assert r.data["ro.product.model"] == "Pixel 7"
        assert r.data["ro.board.platform"] == "gs201"
        assert r.data["ro.build.version.release"] == "14"
        assert r.data["ro.boot.verifiedbootstate"] == "green"
        assert r.data["ro.product.manufacturer"] == "Google"

    def test_partial_extract_data(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "[ro.product.model]: [Pixel 8]\n[other.prop]: [value]\n"
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            lambda *a, **kw: mock_proc,
        )

        r = run_action("fingerprint")
        assert r.data["ro.product.model"] == "Pixel 8"
        assert len(r.data) == 1  # Only matched keys

    def test_no_extract_for_non_extract_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "some log output\n"
        mock_proc.stderr = ""
        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            lambda *a, **kw: mock_proc,
        )

        r = run_action("logcat")
        assert r.data == {}  # logcat has no extract key

    def test_timeout_handling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _timeout(*a: object, **kw: object) -> object:
            raise subprocess.TimeoutExpired(cmd=["adb"], timeout=60, output="")

        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            _timeout,
        )

        r = run_action("battery")
        assert r.success is False
        assert "Timed out" in r.output

    def test_generic_exception_handling(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*a: object, **kw: object) -> object:
            raise FileNotFoundError("adb not found")

        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            _raise,
        )

        r = run_action("battery")
        assert r.success is False
        assert "adb not found" in r.output


class TestArsenalShellRunAll:
    def test_returns_list_of_results(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "output\n"
        mock_proc.stderr = ""

        def mock_run(*a: object, **kw: object) -> MagicMock:
            return mock_proc

        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            mock_run,
        )

        results = run_all()
        assert len(results) == len(ARSENAL_ACTIONS)
        for r in results:
            assert isinstance(r, ArsenalResult)

    def test_includes_all_action_ids(self, monkeypatch: pytest.MonkeyPatch) -> None:
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "output\n"
        mock_proc.stderr = ""

        def mock_run(*a: object, **kw: object) -> MagicMock:
            return mock_proc

        monkeypatch.setattr(
            "zenith.tools.arsenal_shell.subprocess.run",
            mock_run,
        )

        results = run_all()
        result_ids = {r.action for r in results}
        expected_ids = {a["id"] for a in ARSENAL_ACTIONS}
        assert result_ids == expected_ids

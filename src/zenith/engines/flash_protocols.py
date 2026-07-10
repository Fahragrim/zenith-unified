"""Flash Protocol Constants & Helpers — Sahara, Firehose, and BROM protocols.

Pure functions and constants with no side effects. Every packet builder
returns bytes; every parser takes bytes. All USB I/O lives in adapters/.
"""

from __future__ import annotations

import struct
from abc import ABC, abstractmethod
from typing import Any

# ─── Sahara Protocol Constants ────────────────────────────────────────────────

class SaharaCommand:
    HELLO_REQ = 0x01
    HELLO_RESP = 0x02
    READ_DATA = 0x03
    READ_DATA_RESP = 0x04
    DONE = 0x05
    DONE_RESP = 0x06
    EXECUTE = 0x07
    EXECUTE_RESP = 0x08
    RESET = 0x09
    RESET_RESP = 0x0A
    LOG = 0x0B


class SaharaMode:
    IMAGE_MODE = 0
    MEMORY_DEBUG = 1
    STREAM_MODE = 2
    COMMAND_MODE = 3


SAHARA_HEADER_FMT = "<II"
SAHARA_HEADER_SIZE = struct.calcsize(SAHARA_HEADER_FMT)

SAHARA_DEFAULT_VERSION = 2
SAHARA_DEFAULT_MIN_VERSION = 1

# Sahara HELLO_REQ: header(8) + version(4) + min_version(4) + reserved(16) + mode(4) = 36
SAHARA_HELLO_REQ_SIZE = SAHARA_HEADER_SIZE + 28
# Sahara HELLO_RESP: header(8) + version(4) + min_version(4) + reserved(16) + mode(4) + status(4) = 40
SAHARA_HELLO_RESP_SIZE = SAHARA_HEADER_SIZE + 32

# Sahara READ_DATA packet size (header + seq + size)
SAHARA_READ_DATA_SIZE = SAHARA_HEADER_SIZE + 8  # 8 + 8 = 16

# Sahara DONE packet size (header + image_type + total_size)
SAHARA_DONE_SIZE = SAHARA_HEADER_SIZE + 8  # 8 + 8 = 16

# Sahara EXECUTE packet min size (header + cmd_id)
SAHARA_EXECUTE_MIN_SIZE = SAHARA_HEADER_SIZE + 4  # 8 + 4 = 12

# Sahara RESET packet size
SAHARA_RESET_SIZE = SAHARA_HEADER_SIZE + 4  # 8 + 4 = 12

# Firehose USB VID/PID
QUALCOMM_EDL_VID = 0x05C6
QUALCOMM_EDL_PID = 0x9008

# MediaTek BROM USB VID/PID
MTK_BROM_VID = 0x0E8D
MTK_BROM_PIDS = (0x0003, 0x2000, 0x3000)


# ─── Sahara Packet Builders ───────────────────────────────────────────────────


def build_sahara_hello_req(
    version: int = SAHARA_DEFAULT_VERSION,
    min_version: int = SAHARA_DEFAULT_MIN_VERSION,
    mode: int = SaharaMode.IMAGE_MODE,
) -> bytes:
    """Build a Sahara HELLO_REQ packet (command 0x01).

    Layout: header | version | min_version | reserved[4] | mode
    """
    length = SAHARA_HELLO_REQ_SIZE
    header = struct.pack(SAHARA_HEADER_FMT, SaharaCommand.HELLO_REQ, length)
    body = struct.pack("<II", version, min_version)
    reserved = struct.pack("<IIII", 0, 0, 0, 0)
    mode_field = struct.pack("<I", mode)
    return header + body + reserved + mode_field


def parse_sahara_hello_resp(data: bytes) -> dict[str, Any]:
    """Parse a Sahara HELLO_RESP (command 0x02) packet.

    Returns dict with cmd, length, version, min_version, mode, status.
    Raises ValueError if data is too short or cmd is wrong.
    """
    if len(data) < SAHARA_HELLO_RESP_SIZE:
        raise ValueError(
            f"Sahara HELLO_RESP too short: {len(data)} < {SAHARA_HELLO_RESP_SIZE}"
        )
    cmd, length = struct.unpack_from(SAHARA_HEADER_FMT, data, 0)
    if cmd != SaharaCommand.HELLO_RESP:
        raise ValueError(f"Unexpected Sahara cmd: 0x{cmd:02X}, expected 0x{SaharaCommand.HELLO_RESP:02X}")
    version, min_version = struct.unpack_from("<II", data, SAHARA_HEADER_SIZE)
    # reserved[4] occupies SAHARA_HEADER_SIZE + 8 to SAHARA_HEADER_SIZE + 24
    mode = struct.unpack_from("<I", data, SAHARA_HEADER_SIZE + 24)[0]
    status = struct.unpack_from("<I", data, SAHARA_HEADER_SIZE + 28)[0]
    return {
        "cmd": cmd,
        "length": length,
        "version": version,
        "min_version": min_version,
        "mode": mode,
        "status": status,
    }


def build_sahara_read_data(seq: int = 0) -> bytes:
    """Build a Sahara READ_DATA request (command 0x03).

    Request the programmer loader from the device.
    """
    length = SAHARA_READ_DATA_SIZE
    header = struct.pack(SAHARA_HEADER_FMT, SaharaCommand.READ_DATA, length)
    body = struct.pack("<II", seq, 0)
    return header + body


def parse_sahara_read_data_resp(data: bytes) -> dict[str, Any]:
    """Parse Sahara READ_DATA response (command 0x04)."""
    if len(data) < SAHARA_READ_DATA_SIZE:
        raise ValueError(f"Sahara READ_DATA_RESP too short: {len(data)}")
    cmd, length = struct.unpack_from(SAHARA_HEADER_FMT, data, 0)
    if cmd != SaharaCommand.READ_DATA_RESP:
        raise ValueError(f"Unexpected cmd: 0x{cmd:02X}, expected 0x{SaharaCommand.READ_DATA_RESP:02X}")
    seq, size = struct.unpack_from("<II", data, SAHARA_HEADER_SIZE)
    payload = data[SAHARA_READ_DATA_SIZE:] if len(data) > SAHARA_READ_DATA_SIZE else b""
    return {"cmd": cmd, "length": length, "seq": seq, "size": size, "payload": payload}


def build_sahara_done(image_type: int = 0, total_size: int = 0) -> bytes:
    """Build a Sahara DONE packet (command 0x05)."""
    length = SAHARA_DONE_SIZE
    header = struct.pack(SAHARA_HEADER_FMT, SaharaCommand.DONE, length)
    body = struct.pack("<II", image_type, total_size)
    return header + body


def parse_sahara_done_resp(data: bytes) -> dict[str, Any]:
    """Parse Sahara DONE_RESP (command 0x06)."""
    if len(data) < SAHARA_HEADER_SIZE + 4:
        raise ValueError(f"Sahara DONE_RESP too short: {len(data)}")
    cmd, length = struct.unpack_from(SAHARA_HEADER_FMT, data, 0)
    if cmd != SaharaCommand.DONE_RESP:
        raise ValueError(f"Unexpected cmd: 0x{cmd:02X}, expected 0x{SaharaCommand.DONE_RESP:02X}")
    seq = struct.unpack_from("<I", data, SAHARA_HEADER_SIZE)[0]
    return {"cmd": cmd, "length": length, "seq": seq}


def build_sahara_reset(seq: int = 0) -> bytes:
    """Build a Sahara RESET packet (command 0x09)."""
    length = SAHARA_RESET_SIZE
    header = struct.pack(SAHARA_HEADER_FMT, SaharaCommand.RESET, length)
    body = struct.pack("<I", seq)
    return header + body


def parse_sahara_reset_resp(data: bytes) -> dict[str, Any]:
    """Parse Sahara RESET_RESP (command 0x0A)."""
    if len(data) < SAHARA_HEADER_SIZE + 4:
        raise ValueError(f"Sahara RESET_RESP too short: {len(data)}")
    cmd, length = struct.unpack_from(SAHARA_HEADER_FMT, data, 0)
    if cmd != SaharaCommand.RESET_RESP:
        raise ValueError(f"Unexpected cmd: 0x{cmd:02X}, expected 0x{SaharaCommand.RESET_RESP:02X}")
    seq = struct.unpack_from("<I", data, SAHARA_HEADER_SIZE)[0]
    return {"cmd": cmd, "length": length, "seq": seq}


# ─── Firehose XML Builders ────────────────────────────────────────────────────


def build_firehose_configure_xml(
    memory_name: str = "emmc",
    zlp_aware_host: int = 1,
    max_payload_size: int = 1048576,
    skip_storage_init: int = 0,
) -> str:
    """Build Firehose <configure> XML command."""
    return (
        f"<configure MemoryName=\"{memory_name}\" "
        f"ZLPAwareHost=\"{zlp_aware_host}\" "
        f"MaxPayloadSizeToTargetInBytes=\"{max_payload_size}\" "
        f"SkipStorageInit=\"{skip_storage_init}\"/>"
    )


def build_firehose_program_xml(
    partition: str,
    filename: str,
    num_sectors: int = 0,
    start_sector: int = 0,
    physical_partition: int = 0,
    sector_size: int = 512,
) -> str:
    """Build Firehose <program> XML command for flashing a partition."""
    attrs = (
        f"SECTOR_SIZE_IN_BYTES=\"{sector_size}\" "
        f"num_partition_sectors=\"{num_sectors}\" "
        f"physical_partition_number=\"{physical_partition}\" "
        f"start_sector=\"{start_sector}\" "
        f"filename=\"{filename}\" "
        f"label=\"{partition}\""
    )
    return f"<program {attrs}/>"


def build_firehose_read_xml(
    partition: str,
    filename: str,
    num_sectors: int = 0,
    start_sector: int = 0,
    physical_partition: int = 0,
    sector_size: int = 512,
) -> str:
    """Build Firehose <read> XML command for reading a partition."""
    attrs = (
        f"SECTOR_SIZE_IN_BYTES=\"{sector_size}\" "
        f"num_partition_sectors=\"{num_sectors}\" "
        f"physical_partition_number=\"{physical_partition}\" "
        f"start_sector=\"{start_sector}\" "
        f"filename=\"{filename}\" "
        f"label=\"{partition}\""
    )
    return f"<read {attrs}/>"


def build_firehose_reset_xml() -> str:
    """Build Firehose <reset> XML command."""
    return "<reset/>"


def build_firehose_packet(xml_command: str) -> bytes:
    """Wrap an XML command in a Firehose data packet and frame it.

    Firehose expects raw XML between <data> tags, terminated with a
    ʻ\nʼ, prefixed with a 4-byte length.
    """
    xml = f"<?xml version=\"1.0\" encoding=\"utf-8\"?>\n<data>\n{xml_command}\n</data>\n"
    data = xml.encode("utf-8")
    length_prefix = struct.pack("<I", len(data))
    return length_prefix + data


def parse_firehose_response(data: bytes) -> dict[str, Any]:
    """Parse a Firehose response.

    Returns dict with success (bool), raw (str), and parsed XML tag info.
    """
    raw = data.decode("utf-8", errors="replace")
    success = "<response value=\"ACK\"" in raw or "OK" in raw
    error = ""
    if not success:
        if "<response value=\"NAK\"" in raw:
            import re
            m = re.search(r"rawmode=\"([^\"]*)\"", raw)
            error = m.group(1) if m else "NAK received"
        else:
            error = raw[:200]
    return {"success": success, "raw": raw, "error": error}


# ─── BROM Protocol Constants ──────────────────────────────────────────────────


class BromCommand:
    BROM_HANDSHAKE = 0x01
    BROM_HANDSHAKE_RESP = 0x02
    BROM_SEND_DA = 0x03
    BROM_SEND_DA_RESP = 0x04
    BROM_JUMP_DA = 0x05
    BROM_JUMP_DA_RESP = 0x06
    BROM_FLASH = 0x07
    BROM_FLASH_RESP = 0x08
    BROM_RESET = 0x09
    BROM_RESET_RESP = 0x0A


BROM_HANDSHAKE_MAGIC = b"\xAA\x55\xAA\x55"
BROM_DA_HEADER_SIZE = 16


def build_brom_handshake() -> bytes:
    """Build BROM handshake packet: magic + command."""
    return BROM_HANDSHAKE_MAGIC + struct.pack("<I", BromCommand.BROM_HANDSHAKE)


def parse_brom_handshake_resp(data: bytes) -> dict[str, Any]:
    """Parse BROM handshake response."""
    if len(data) < 8:
        raise ValueError(f"BROM handshake response too short: {len(data)}")
    magic = data[:4]
    cmd = struct.unpack_from("<I", data, 4)[0]
    status = struct.unpack_from("<I", data, 8)[0] if len(data) >= 12 else 0
    return {"magic": magic.hex(), "cmd": cmd, "status": status}


def build_brom_da_header(da_size: int, entry_point: int = 0x1000) -> bytes:
    """Build BROM DA (Download Agent) header.

    The DA binary is sent in chunks after this header.
    """
    return struct.pack("<IIII", BromCommand.BROM_SEND_DA, da_size, entry_point, 0)


def build_brom_flash_command(partition: str, offset: int = 0, size: int = 0) -> bytes:
    """Build BROM flash partition command."""
    part_bytes = partition.encode("utf-8").ljust(32, b"\x00")[:32]
    return struct.pack("<I", BromCommand.BROM_FLASH) + part_bytes + struct.pack("<II", offset, size)


def build_brom_reset() -> bytes:
    """Build BROM reset command."""
    return struct.pack("<I", BromCommand.BROM_RESET)


# ─── Transport ABCs (protocol abstraction interfaces) ─────────────────────────


class EdlTransport(ABC):
    """Low-level USB transport for Qualcomm EDL (Sahara + Firehose).

    Implementations can use pyusb, pyserial, or wrap the edl tool.
    """

    @abstractmethod
    def detect(self) -> str | None:
        """Detect a Qualcomm EDL device. Returns serial/port or None."""
        ...

    @abstractmethod
    def sahara_hello(self) -> dict[str, Any]:
        """Send Sahara HELLO_REQ and return parsed HELLO_RESP."""
        ...

    @abstractmethod
    def sahara_upload_loader(self, loader_path: str) -> bool:
        """Upload a .mbn or .elf programmer loader via Sahara READ_DATA handshake."""
        ...

    @abstractmethod
    def firehose_connect(self, max_payload_size: int = 1048576) -> bool:
        """Configure and connect via Firehose protocol after Sahara uploads loader."""
        ...

    @abstractmethod
    def firehose_command(self, xml: str) -> dict[str, Any]:
        """Send a Firehose XML command and return parsed response."""
        ...

    @abstractmethod
    def firehose_reset(self) -> bool:
        """Send Firehose reset command to reboot device."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release USB device handle."""
        ...


class BromTransport(ABC):
    """Low-level USB transport for MediaTek BROM.

    Implementations can use pyusb or wrap the mtkclient tool.
    """

    @abstractmethod
    def detect(self) -> str | None:
        """Detect a MediaTek BROM device. Returns serial/port or None."""
        ...

    @abstractmethod
    def handshake(self) -> dict[str, Any]:
        """Perform BROM handshake."""
        ...

    @abstractmethod
    def send_da(self, da_path: str) -> bool:
        """Send Download Agent (DA) binary to BROM device."""
        ...

    @abstractmethod
    def jump_da(self) -> bool:
        """Jump to the uploaded DA."""
        ...

    @abstractmethod
    def flash_partition(self, partition: str, file_path: str) -> bool:
        """Flash a partition via DA protocol."""
        ...

    @abstractmethod
    def reset(self) -> bool:
        """Send reset command to reboot device."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release USB device handle."""
        ...

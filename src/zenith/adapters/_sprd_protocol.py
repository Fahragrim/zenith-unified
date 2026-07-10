"""SPRD BootROM + Socrates native protocol — ported from OpencodeDeviceTool.

HDLC BootROM framing, Socrates command protocol, .pac parser.
USB VID: 1782, PID: 4D00.
"""

from __future__ import annotations

import contextlib
import struct
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any, cast

from loguru import logger

HDLC_FLAG = 0x7E
HDLC_ESCAPE = 0x7D
HDLC_ESCAPE_MASK = 0x20
HDLC_DATA_MAX_SIZE = 512
HDLC_FRAME_MAX_SIZE = 520
SPRD_VID = 0x1782
SPRD_PID = 0x4D00
PAC_MAGIC = b"BP"
PAC_HEADER_SIZE = 4000
PAC_ENTRY_SIZE = 400


class BootROMCmd(IntEnum):
    REQ_CONNECT = 0x00
    REQ_START_DATA = 0x01
    REQ_MIDST_DATA = 0x02
    REQ_END_DATA = 0x03
    REQ_EXEC_DATA = 0x04
    REP_ACK = 0x80
    REP_VER = 0x81


class SocratesCmd(IntEnum):
    REQ_VERSION = 0x0000
    REQ_READ_32 = 0x0005
    REQ_WRITE_32 = 0x0006
    REQ_MMC_INIT = 0x0009
    REQ_MMC_GET_SEC_COUNT = 0x000B
    REQ_MMC_READ_SINGLE_BLOCK = 0x000C
    REQ_MMC_WRITE_BLOCK = 0x000D
    RSP_OK = 0x8000
    RSP_READ_32 = 0x8005
    RSP_MMC_GET_SEC_COUNT = 0x8007
    RSP_MMC_READ_SINGLE_BLOCK = 0x8008


@dataclass
class PacFileEntry:
    filename: str
    size: int = 0
    data_offset: int = 0
    attribute: int = 0
    data: bytes = b""
    start_lba: int = 0
    partition_size: int = 0

    @property
    def is_fdl1(self) -> bool:
        return any(k in self.filename.lower() for k in ("fdl1", "fdl_test1"))

    @property
    def is_fdl2(self) -> bool:
        return any(k in self.filename.lower() for k in ("fdl2", "fdl2_test"))


@dataclass
class PacFile:
    version: int = 0
    file_count: int = 0
    entries: list[PacFileEntry] = field(default_factory=list)
    source_path: str = ""

    @property
    def fdl1(self) -> PacFileEntry | None:
        for e in self.entries:
            if e.is_fdl1:
                return e
        return None

    @property
    def fdl2(self) -> PacFileEntry | None:
        for e in self.entries:
            if e.is_fdl2:
                return e
        return None


class SPRDDevice:
    def __init__(self) -> None:
        self._dev: Any = None
        self._ep_in: int = -1
        self._ep_out: int = -1

    async def open(self) -> bool:
        import usb.core
        import usb.util
        dev = usb.core.find(idVendor=SPRD_VID, idProduct=SPRD_PID)
        if dev is None:
            return False
        if dev.is_kernel_driver_active(0):
            with contextlib.suppress(Exception):
                dev.detach_kernel_driver(0)
        dev.set_configuration()
        cfg = dev.get_active_configuration()
        iface = cfg[(0, 0)]
        ep_in = ep_out = None
        for ep in iface.endpoints():
            if ep.bEndpointAddress & 0x80:
                ep_in = ep.bEndpointAddress
            else:
                ep_out = ep.bEndpointAddress
        if ep_in is None or ep_out is None:
            return False
        self._dev = dev
        self._ep_in = ep_in
        self._ep_out = ep_out
        with contextlib.suppress(Exception):
            dev.ctrl_transfer(0x21, 34, 0x601, 0, None, 100)
        return True

    async def transfer_in(self, length: int, timeout: int = 1000) -> bytes:
        return bytes(self._dev.read(self._ep_in, length, timeout))

    async def transfer_out(self, data: bytes, timeout: int = 1000) -> None:
        result = self._dev.write(self._ep_out, data, timeout)
        if result != len(data):
            raise RuntimeError(f"Short write: {result} vs {len(data)}")

    async def close(self) -> None:
        if self._dev is not None:
            try:
                import usb.util
                usb.util.dispose_resources(self._dev)
            except Exception:
                pass
            self._dev = None


class HDLCBootROM:
    def __init__(self, device: SPRDDevice) -> None:
        self.device = device
        self._fifo = bytearray()

    async def send_hello(self) -> str:
        await self.device.transfer_out(bytes([HDLC_FLAG]))
        resp = await self._receive_packet()
        if resp["type"] != BootROMCmd.REP_VER:
            raise RuntimeError(f"Expected REP_VER, got {resp['type']}")
        data = resp.get("data")
        if data is None:
            raise RuntimeError("No version data")
        return cast(str, data[:-1].decode("utf-8", errors="replace"))

    async def send_payload(self, address: int, data: bytes) -> None:
        header = struct.pack("<II", address, len(data))
        await self._send_packet(BootROMCmd.REQ_START_DATA, header)
        await self._receive_ack()
        for i in range(0, len(data), HDLC_DATA_MAX_SIZE):
            await self._send_packet(BootROMCmd.REQ_MIDST_DATA, data[i : i + HDLC_DATA_MAX_SIZE])
            await self._receive_ack()
        await self._send_packet(BootROMCmd.REQ_END_DATA)
        await self._receive_ack()

    async def send_jump_to_payload(self, address: int) -> None:
        lr = struct.pack("<I", address) + b"\x00\x00\x00\x00"
        await self._send_packet(BootROMCmd.REQ_START_DATA, struct.pack("<II", 0x3F58, 8))
        await self._receive_ack()
        await self._send_packet(BootROMCmd.REQ_MIDST_DATA, lr)
        await self._receive_ack()

    async def _receive_ack(self) -> None:
        resp = await self._receive_packet()
        if resp["type"] != BootROMCmd.REP_ACK:
            raise RuntimeError(f"Expected REP_ACK, got {resp['type']}")

    async def _receive_packet(self) -> dict[str, Any]:
        state = 0  # 0=START, 1=UNESCAPED, 2=ESCAPED, 3=END
        buf = bytearray(HDLC_FRAME_MAX_SIZE)
        pos = 0
        while state != 3:
            if len(self._fifo) == 0:
                self._fifo.extend(await self.device.transfer_in(HDLC_FRAME_MAX_SIZE))
            i = 0
            while i < len(self._fifo) and state != 3:
                b = self._fifo[i]
                i += 1
                if state == 0:
                    if b == HDLC_FLAG:
                        state = 1
                elif state == 2:
                    buf[pos] = b ^ HDLC_ESCAPE_MASK
                    pos += 1
                    state = 1
                elif state == 1:
                    if b == HDLC_FLAG:
                        state = 3
                    elif b == HDLC_ESCAPE:
                        state = 2
                    else:
                        buf[pos] = b
                    pos += 1
            self._fifo = self._fifo[i:]
        pkt_type = int.from_bytes(buf[0:2], "little")
        data_length = int.from_bytes(buf[2:4], "little")
        data = bytes(buf[4 : 4 + data_length]) if data_length > 0 else None
        return {"type": pkt_type, "data": data}

    async def _send_packet(self, cmd: BootROMCmd, data: bytes | None = None) -> None:
        data_len = len(data) if data else 0
        raw = cmd.to_bytes(2, "little") + data_len.to_bytes(2, "little")
        if data:
            raw += data
        crc = self._crc16(raw)
        raw += crc.to_bytes(2, "little")
        buf = bytearray([HDLC_FLAG])
        for b in raw:
            if b in (HDLC_FLAG, HDLC_ESCAPE):
                buf.append(HDLC_ESCAPE)
                buf.append(b ^ HDLC_ESCAPE_MASK)
            else:
                buf.append(b)
        buf.append(HDLC_FLAG)
        await self.device.transfer_out(bytes(buf))

    @staticmethod
    def _crc16(data: bytes) -> int:
        crc = 0
        for byte in data:
            for _ in range(8):
                if crc & 0x8000:
                    crc = ((crc << 1) ^ 0x1021) & 0xFFFF
                else:
                    crc = (crc << 1) & 0xFFFF
                if byte & 0x80:
                    crc ^= 0x1021
                byte = (byte << 1) & 0xFF
        return crc


class Socrates:
    def __init__(self, device: SPRDDevice) -> None:
        self.device = device
        self._fifo = bytearray()

    async def get_version(self) -> str:
        await self._send(SocratesCmd.REQ_VERSION)
        resp = await self._receive()
        if resp["type"] != SocratesCmd.RSP_OK:
            raise RuntimeError(f"Version failed: {resp['type']}")
        data = resp.get("data")
        if data is None:
            return "unknown"
        return cast(str, data.decode("utf-8", errors="replace").rstrip("\x00"))

    async def read32(self, address: int) -> int:
        await self._send(SocratesCmd.REQ_READ_32, struct.pack("<Q", address))
        resp = await self._receive()
        if resp["type"] != SocratesCmd.RSP_READ_32:
            raise RuntimeError(f"read32 failed: {resp['type']}")
        data = resp.get("data")
        if data is None or len(data) < 4:
            raise RuntimeError("Invalid read32 response")
        return cast(int, struct.unpack("<I", data[:4])[0])

    async def write32(self, address: int, value: int) -> None:
        await self._send(SocratesCmd.REQ_WRITE_32, struct.pack("<QI", address, value))
        resp = await self._receive()
        if resp["type"] != SocratesCmd.RSP_OK:
            raise RuntimeError(f"write32 failed: {resp['type']}")

    async def mmc_init(self) -> None:
        await self._send(SocratesCmd.REQ_MMC_INIT)
        resp = await self._receive()
        if resp["type"] != SocratesCmd.RSP_OK:
            raise RuntimeError(f"mmc_init failed: {resp['type']}")

    async def mmc_get_sec_count(self) -> int:
        await self._send(SocratesCmd.REQ_MMC_GET_SEC_COUNT)
        resp = await self._receive()
        if resp["type"] != SocratesCmd.RSP_MMC_GET_SEC_COUNT:
            raise RuntimeError(f"mmc_get_sec_count: {resp['type']}")
        data = resp.get("data")
        if data is None or len(data) < 4:
            raise RuntimeError("Invalid sec_count")
        return cast(int, struct.unpack("<I", data[:4])[0])

    async def mmc_read_block(self, lba: int) -> bytes:
        await self._send(SocratesCmd.REQ_MMC_READ_SINGLE_BLOCK, struct.pack("<I", lba))
        resp = await self._receive()
        if resp["type"] != SocratesCmd.RSP_MMC_READ_SINGLE_BLOCK:
            raise RuntimeError(f"mmc_read_block: {resp['type']}")
        return cast(bytes, resp.get("data", b""))

    async def mmc_write_block(self, lba: int, data: bytes) -> None:
        await self._send(SocratesCmd.REQ_MMC_WRITE_BLOCK, struct.pack("<I", lba) + data)
        resp = await self._receive()
        if resp["type"] != SocratesCmd.RSP_OK:
            raise RuntimeError(f"mmc_write_block: {resp['type']}")

    async def _receive(self) -> dict[str, Any]:
        while len(self._fifo) < 4:
            self._fifo.extend(await self.device.transfer_in(1024))
        pkt_type = int.from_bytes(self._fifo[0:2], "little")
        data_length = int.from_bytes(self._fifo[2:4], "little")
        while len(self._fifo) < 4 + data_length:
            self._fifo.extend(await self.device.transfer_in(1024))
        data = bytes(self._fifo[4 : 4 + data_length]) if data_length > 0 else None
        self._fifo = self._fifo[4 + data_length :]
        return {"type": pkt_type, "data": data}

    async def _send(self, cmd: SocratesCmd, data: bytes | None = None) -> None:
        data_len = len(data) if data else 0
        buf = cmd.to_bytes(2, "little") + data_len.to_bytes(2, "little")
        if data:
            buf += data
        await self.device.transfer_out(bytes(buf))


# ─── .pac Parser ────────────────────────────────────────────


def parse_pac(path: str) -> PacFile:
    with open(path, "rb") as f:
        header = f.read(PAC_HEADER_SIZE)
    if header[0:2] != PAC_MAGIC:
        raise ValueError(f"Not a PAC file: {path}")
    version = struct.unpack_from("<I", header, 4)[0]
    file_count = 0
    for offset in (8, 12, 16, 20, 24, 28, 32, 36, 40):
        if offset + 4 <= len(header):
            count = struct.unpack_from("<I", header, offset)[0]
            if 0 < count < 200:
                file_count = count
                break
    entries: list[PacFileEntry] = []
    for i in range(file_count):
        entry_start = PAC_HEADER_SIZE + i * PAC_ENTRY_SIZE
        with open(path, "rb") as f2:
            f2.seek(entry_start)
            entry_bytes = f2.read(PAC_ENTRY_SIZE)
        filename_raw = entry_bytes[0:256]
        null_pos = filename_raw.find(b"\x00")
        filename = filename_raw[:null_pos].decode("utf-8", errors="replace") if null_pos >= 0 else filename_raw.decode("utf-8", errors="replace")
        size = struct.unpack_from("<I", entry_bytes, 0x100)[0]
        data_offset = struct.unpack_from("<I", entry_bytes, 0x104)[0]
        attribute = struct.unpack_from("<I", entry_bytes, 0x108)[0]
        start_lba = struct.unpack_from("<I", entry_bytes, 0x10C)[0]
        partition_size = struct.unpack_from("<I", entry_bytes, 0x110)[0]
        with open(path, "rb") as f3:
            f3.seek(data_offset)
            data = f3.read(size)
        entries.append(PacFileEntry(filename=filename.strip(), size=size, data_offset=data_offset,
                                    attribute=attribute, start_lba=start_lba, partition_size=partition_size, data=data))
    logger.info(f"PAC: {path} ({version=}, {file_count} files)")
    return PacFile(version=version, file_count=file_count, entries=entries, source_path=path)


def extract_fdl1(pac: PacFile) -> bytes:
    entry = pac.fdl1
    if entry is None:
        raise ValueError("No FDL1 found in PAC")
    return entry.data


def extract_fdl2(pac: PacFile) -> bytes:
    entry = pac.fdl2
    if entry is None:
        raise ValueError("No FDL2 found in PAC")
    return entry.data


def extract_partitions(pac: PacFile) -> list[PacFileEntry]:
    return [e for e in pac.entries if not e.is_fdl1 and not e.is_fdl2]


async def flash_pac_file(socrates: Socrates, pac_path: str) -> dict[str, bool]:
    pac = parse_pac(pac_path)
    entries = extract_partitions(pac)
    await socrates.mmc_init()
    results: dict[str, bool] = {}
    for entry in entries:
        if entry.size == 0 or not entry.data:
            results[entry.filename] = False
            continue
        try:
            block_size = 512
            for offset in range(0, len(entry.data), block_size):
                chunk = entry.data[offset : offset + block_size]
                if len(chunk) < block_size:
                    chunk += b"\x00" * (block_size - len(chunk))
                await socrates.mmc_write_block(entry.start_lba + offset // block_size, chunk)
            results[entry.filename] = True
        except Exception as e:
            logger.warning(f"flash_pac: {entry.filename}: {e}")
            results[entry.filename] = False
    return results

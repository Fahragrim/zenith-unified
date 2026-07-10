"""USB Transport — PyUSB-based EDL and BROM transport implementations.

These classes implement the EdlTransport and BromTransport ABCs using
pyusb (usb.core) for direct USB communication. All operations are
wrapped to be mockable in unit tests.
"""

from __future__ import annotations

import contextlib
import importlib.util
from pathlib import Path
from typing import Any

from loguru import logger

from zenith.engines.flash_protocols import (
    MTK_BROM_PIDS,
    MTK_BROM_VID,
    QUALCOMM_EDL_PID,
    QUALCOMM_EDL_VID,
    BromTransport,
    EdlTransport,
    build_firehose_configure_xml,
    build_firehose_packet,
    build_sahara_done,
    build_sahara_hello_req,
    parse_firehose_response,
    parse_sahara_done_resp,
    parse_sahara_hello_resp,
)

# ─── Constants ────────────────────────────────────────────────────────────────

EDL_BULK_EP_OUT = 0x01
EDL_BULK_EP_IN = 0x82
EDL_TIMEOUT_MS = 5000
EDL_LOADER_TIMEOUT_MS = 30000

BROM_BULK_EP_OUT = 0x01
BROM_BULK_EP_IN = 0x82
BROM_TIMEOUT_MS = 5000
BROM_DA_TIMEOUT_MS = 60000


# ─── EDL Transport (PyUSB) ────────────────────────────────────────────────────


class EdlUsbTransport(EdlTransport):
    """Qualcomm EDL transport via pyusb.

    Opens the USB device (VID 05C6, PID 9008), claims interface 0,
    and communicates via bulk endpoints.
    """

    def __init__(self) -> None:
        self._dev: Any = None
        self._handle: Any = None

    def detect(self) -> str | None:
        try:
            import usb.core
            import usb.util
        except ImportError:
            logger.warning("pyusb not installed")
            return None
        try:
            dev = usb.core.find(idVendor=QUALCOMM_EDL_VID, idProduct=QUALCOMM_EDL_PID)
            if dev is None:
                return None
            serial = None
            with contextlib.suppress(Exception):
                serial = usb.util.get_string(dev, dev.iSerialNumber)
            self._dev = dev
            return serial or f"{QUALCOMM_EDL_VID:04X}:{QUALCOMM_EDL_PID:04X}"
        except Exception as e:
            logger.debug(f"EDL detect failed: {e}")
            return None

    def _ensure_claimed(self) -> None:
        if self._handle is not None:
            return
        if self._dev is None:
            raise RuntimeError("No EDL device. Call detect() first.")
        if importlib.util.find_spec("usb") is None:
            raise RuntimeError("pyusb not installed")
        if self._dev.is_kernel_driver_active(0):
            self._dev.detach_kernel_driver(0)
        self._dev.set_configuration()
        self._handle = self._dev
        logger.debug("EDL USB interface claimed")

    def sahara_hello(self) -> dict[str, Any]:
        self._ensure_claimed()
        try:
            packet = build_sahara_hello_req()
            self._dev.write(EDL_BULK_EP_OUT, packet, EDL_TIMEOUT_MS)
            resp = self._dev.read(EDL_BULK_EP_IN, 64, EDL_TIMEOUT_MS)
            parsed = parse_sahara_hello_resp(bytes(resp))
            logger.info(f"Sahara HELLO_RESP: mode={parsed['mode']}, status={parsed['status']}")
            return parsed
        except Exception as e:
            logger.error(f"Sahara hello failed: {e}")
            return {"error": str(e)}

    def sahara_upload_loader(self, loader_path: str) -> bool:
        self._ensure_claimed()
        loader = Path(loader_path)
        if not loader.exists():
            logger.error(f"Loader not found: {loader_path}")
            return False
        try:
            loader_data = loader.read_bytes()
            chunk_size = 1024 * 16
            seq = 0
            offset = 0
            while offset < len(loader_data):
                chunk = loader_data[offset:offset + chunk_size]
                chunk_packet = chunk
                self._dev.write(EDL_BULK_EP_OUT, chunk_packet, EDL_LOADER_TIMEOUT_MS)
                ack = self._dev.read(EDL_BULK_EP_IN, 64, EDL_TIMEOUT_MS)
                if not ack:
                    logger.warning(f"No ACK for seq {seq}")
                    return False
                offset += len(chunk)
                seq += 1
            done = build_sahara_done(image_type=0, total_size=len(loader_data))
            self._dev.write(EDL_BULK_EP_OUT, done, EDL_LOADER_TIMEOUT_MS)
            done_resp = self._dev.read(EDL_BULK_EP_IN, 64, EDL_TIMEOUT_MS)
            parse_sahara_done_resp(bytes(done_resp))
            logger.info(f"Sahara loader uploaded: {loader_path} ({len(loader_data)} bytes)")
            return True
        except Exception as e:
            logger.error(f"Sahara upload loader failed: {e}")
            return False

    def firehose_connect(self, max_payload_size: int = 1048576) -> bool:
        self._ensure_claimed()
        try:
            xml = build_firehose_configure_xml(
                memory_name="emmc",
                zlp_aware_host=1,
                max_payload_size=max_payload_size,
            )
            result = self.firehose_command(xml)
            return bool(result.get("success", False))
        except Exception as e:
            logger.error(f"Firehose connect failed: {e}")
            return False

    def firehose_command(self, xml: str) -> dict[str, Any]:
        self._ensure_claimed()
        try:
            packet = build_firehose_packet(xml)
            self._dev.write(EDL_BULK_EP_OUT, packet, EDL_TIMEOUT_MS)
            resp = self._dev.read(EDL_BULK_EP_IN, 4096, EDL_TIMEOUT_MS)
            return parse_firehose_response(bytes(resp))
        except Exception as e:
            logger.error(f"Firehose command failed: {e}")
            return {"success": False, "error": str(e)}

    def firehose_reset(self) -> bool:
        result = self.firehose_command("<reset/>")
        return bool(result.get("success", False))

    def close(self) -> None:
        try:
            import usb.util
        except ImportError:
            return
        if self._dev is not None:
            with contextlib.suppress(Exception):
                usb.util.dispose_resources(self._dev)
            self._dev = None
            self._handle = None
            logger.debug("EDL USB resources released")


# ─── BROM Transport (PyUSB) ───────────────────────────────────────────────────


class BromUsbTransport(BromTransport):
    """MediaTek BROM transport via pyusb.

    Opens the USB device (VID 0E8D, PID varies), claims interface 0,
    and communicates via bulk endpoints.
    """

    def __init__(self) -> None:
        self._dev: Any = None
        self._handle: Any = None

    def detect(self) -> str | None:
        try:
            import usb.core
            import usb.util
        except ImportError:
            logger.warning("pyusb not installed")
            return None
        try:
            for pid in MTK_BROM_PIDS:
                dev = usb.core.find(idVendor=MTK_BROM_VID, idProduct=pid)
                if dev is not None:
                    serial = None
                    with contextlib.suppress(Exception):
                        serial = usb.util.get_string(dev, dev.iSerialNumber)
                    self._dev = dev
                    return serial or f"{MTK_BROM_VID:04X}:{pid:04X}"
            return None
        except Exception as e:
            logger.debug(f"BROM detect failed: {e}")
            return None

    def _ensure_claimed(self) -> None:
        if self._handle is not None:
            return
        if self._dev is None:
            raise RuntimeError("No BROM device. Call detect() first.")
        if importlib.util.find_spec("usb") is None:
            raise RuntimeError("pyusb not installed")
        try:
            if self._dev.is_kernel_driver_active(0):
                self._dev.detach_kernel_driver(0)
        except (NotImplementedError, AttributeError):
            pass
        self._dev.set_configuration()
        self._handle = self._dev
        logger.debug("BROM USB interface claimed")

    def handshake(self) -> dict[str, Any]:
        self._ensure_claimed()
        try:
            from zenith.engines.flash_protocols import build_brom_handshake, parse_brom_handshake_resp
            packet = build_brom_handshake()
            self._dev.write(BROM_BULK_EP_OUT, packet, BROM_TIMEOUT_MS)
            resp = self._dev.read(BROM_BULK_EP_IN, 64, BROM_TIMEOUT_MS)
            return parse_brom_handshake_resp(bytes(resp))
        except Exception as e:
            logger.error(f"BROM handshake failed: {e}")
            return {"error": str(e)}

    def send_da(self, da_path: str) -> bool:
        self._ensure_claimed()
        da = Path(da_path)
        if not da.exists():
            logger.error(f"DA not found: {da_path}")
            return False
        try:
            from zenith.engines.flash_protocols import build_brom_da_header
            da_data = da.read_bytes()
            header = build_brom_da_header(len(da_data))
            self._dev.write(BROM_BULK_EP_OUT, header, BROM_DA_TIMEOUT_MS)
            ack = self._dev.read(BROM_BULK_EP_IN, 64, BROM_TIMEOUT_MS)
            if not ack:
                logger.warning("No DA header ACK from BROM")
                return False
            chunk_size = 1024 * 64
            offset = 0
            while offset < len(da_data):
                chunk = da_data[offset:offset + chunk_size]
                self._dev.write(BROM_BULK_EP_OUT, chunk, BROM_DA_TIMEOUT_MS)
                ack = self._dev.read(BROM_BULK_EP_IN, 64, BROM_TIMEOUT_MS)
                if not ack:
                    logger.warning(f"No DA chunk ACK at offset {offset}")
                    return False
                offset += len(chunk)
            logger.info(f"BROM DA sent: {da_path} ({len(da_data)} bytes)")
            return True
        except Exception as e:
            logger.error(f"BROM send DA failed: {e}")
            return False

    def jump_da(self) -> bool:
        self._ensure_claimed()
        try:
            import struct

            from zenith.engines.flash_protocols import BromCommand
            packet = struct.pack("<I", BromCommand.BROM_JUMP_DA)
            self._dev.write(BROM_BULK_EP_OUT, packet, BROM_TIMEOUT_MS)
            resp = self._dev.read(BROM_BULK_EP_IN, 64, BROM_TIMEOUT_MS)
            ack = len(resp) > 0
            if ack:
                logger.info("BROM jump to DA successful")
            else:
                logger.warning("BROM jump to DA returned no response")
            return ack
        except Exception as e:
            logger.error(f"BROM jump DA failed: {e}")
            return False

    def flash_partition(self, partition: str, file_path: str) -> bool:
        self._ensure_claimed()
        img = Path(file_path)
        if not img.exists():
            logger.error(f"Image not found: {file_path}")
            return False
        try:
            from zenith.engines.flash_protocols import build_brom_flash_command
            img_data = img.read_bytes()
            cmd = build_brom_flash_command(partition, size=len(img_data))
            self._dev.write(BROM_BULK_EP_OUT, cmd, BROM_DA_TIMEOUT_MS)
            ack = self._dev.read(BROM_BULK_EP_IN, 64, BROM_TIMEOUT_MS)
            if not ack:
                logger.warning(f"No ACK for flash command: {partition}")
                return False
            chunk_size = 1024 * 64
            offset = 0
            while offset < len(img_data):
                chunk = img_data[offset:offset + chunk_size]
                self._dev.write(BROM_BULK_EP_OUT, chunk, BROM_DA_TIMEOUT_MS)
                ack = self._dev.read(BROM_BULK_EP_IN, 64, BROM_TIMEOUT_MS)
                if not ack:
                    logger.warning(f"No ACK at offset {offset} for {partition}")
                    return False
                offset += len(chunk)
            logger.info(f"BROM flashed {partition}: {file_path} ({len(img_data)} bytes)")
            return True
        except Exception as e:
            logger.error(f"BROM flash {partition} failed: {e}")
            return False

    def reset(self) -> bool:
        self._ensure_claimed()
        try:
            from zenith.engines.flash_protocols import build_brom_reset
            packet = build_brom_reset()
            self._dev.write(BROM_BULK_EP_OUT, packet, BROM_TIMEOUT_MS)
            self._dev.read(BROM_BULK_EP_IN, 64, BROM_TIMEOUT_MS)
            logger.info("BROM reset command sent")
            return True
        except Exception as e:
            logger.error(f"BROM reset failed: {e}")
            return False

    def close(self) -> None:
        try:
            import usb.util
        except ImportError:
            return
        if self._dev is not None:
            with contextlib.suppress(Exception):
                usb.util.dispose_resources(self._dev)
            self._dev = None
            self._handle = None
            logger.debug("BROM USB resources released")

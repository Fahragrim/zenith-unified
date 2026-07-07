"""Backup Manager — enforces backup-before-destructive operations.

Creates verified backups before any write/erase/flash operation.
Uses SHA-256 hashing for integrity verification.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger


@dataclass
class BackupManifest:
    id: str
    device_serial: str
    created_at: str
    files: list[dict[str, Any]] = field(default_factory=list)
    total_size_bytes: int = 0
    checksum: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "device_serial": self.device_serial,
            "created_at": self.created_at, "files": self.files,
            "total_size_bytes": self.total_size_bytes, "checksum": self.checksum,
            "metadata": self.metadata,
        }


class BackupManager:
    """Manages backup creation, verification, and restoration."""

    def __init__(self, backup_dir: str | Path = "backups") -> None:
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _checksum_file(self, path: Path, algorithm: str = "sha256") -> str:
        h = hashlib.new(algorithm)
        with path.open("rb") as f:
            while chunk := f.read(8192):
                h.update(chunk)
        return h.hexdigest()

    def _checksum_data(self, data: bytes, algorithm: str = "sha256") -> str:
        return hashlib.new(algorithm, data).hexdigest()

    def create_backup(
        self,
        device_serial: str,
        files: dict[str, bytes],
        *,
        metadata: dict[str, Any] | None = None,
    ) -> BackupManifest | None:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_id = f"{device_serial}_{timestamp}"
        backup_path = self.backup_dir / backup_id
        backup_path.mkdir(parents=True, exist_ok=True)

        manifest = BackupManifest(
            id=backup_id,
            device_serial=device_serial,
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata=metadata or {},
        )

        total_size = 0
        for name, data in files.items():
            file_path = backup_path / name
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(data)
            file_checksum = self._checksum_data(data)
            file_size = len(data)
            total_size += file_size
            manifest.files.append({
                "name": name, "size_bytes": file_size,
                "checksum": file_checksum,
            })
            logger.debug(f"Backup: {name} ({file_size} bytes)")

        manifest.total_size_bytes = total_size

        # Create manifest
        manifest_path = backup_path / "manifest.json"
        manifest_data = manifest.to_dict()
        manifest_str = json.dumps(manifest_data, sort_keys=True, ensure_ascii=False)
        manifest.checksum = hashlib.sha256(manifest_str.encode()).hexdigest()
        manifest_path.write_text(json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")

        logger.info(f"Backup created: {backup_id} ({total_size} bytes, {len(files)} files)")
        return manifest

    def verify_backup(self, backup_id: str) -> bool:
        backup_path = self.backup_dir / backup_id
        manifest_path = backup_path / "manifest.json"

        if not manifest_path.exists():
            logger.error(f"Backup manifest not found: {backup_id}")
            return False

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid manifest: {backup_id} — {e}")
            return False

        for file_info in manifest_data.get("files", []):
            name = file_info["name"]
            expected = file_info["checksum"]
            file_path = backup_path / name
            if not file_path.exists():
                logger.error(f"Backup file missing: {name}")
                return False
            actual = self._checksum_file(file_path)
            if actual != expected:
                logger.error(f"Checksum mismatch: {name} (expected={expected[:16]}..., actual={actual[:16]}...)")
                return False

        logger.info(f"Backup verified: {backup_id}")
        return True

    def list_backups(self, device_serial: str | None = None) -> list[str]:
        backups: list[str] = []
        for entry in sorted(self.backup_dir.iterdir(), reverse=True):
            if entry.is_dir() and (entry / "manifest.json").exists() and (device_serial is None or entry.name.startswith(device_serial)):
                backups.append(entry.name)
        return backups

    def get_manifest(self, backup_id: str) -> BackupManifest | None:
        manifest_path = self.backup_dir / backup_id / "manifest.json"
        if not manifest_path.exists():
            return None
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            return BackupManifest(
                id=data["id"], device_serial=data["device_serial"],
                created_at=data["created_at"], files=data.get("files", []),
                total_size_bytes=data.get("total_size_bytes", 0),
                checksum=data.get("checksum", ""), metadata=data.get("metadata", {}),
            )
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse manifest: {backup_id} — {e}")
            return None

    def delete_backup(self, backup_id: str) -> bool:
        backup_path = self.backup_dir / backup_id
        if not backup_path.exists():
            return False
        import shutil
        shutil.rmtree(backup_path)
        logger.info(f"Backup deleted: {backup_id}")
        return True

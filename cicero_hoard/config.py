"""Process-level configuration read from the environment (never from the DB)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .guard import parse_allowed_hosts

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 5194
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def _int(raw: str, default: int, low: int, high: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if low <= value <= high else default


@dataclass
class Config:
    """Everything the process needs before the database exists."""

    data_dir: Path = field(default_factory=lambda: REPO_ROOT / "data")
    port: int = DEFAULT_PORT
    port_strict: bool = False
    allowed_hosts: tuple[str, ...] = ()
    data_dir_configured: bool = False
    file_roots: tuple[Path, ...] = ()  # CICERO_FILE_ROOTS: when set, local-file sources must live under one of them
    image_studio_url: str = ""  # CICERO_IMAGE_STUDIO_URL: skip discovery and use this studio
    image_timeout: float = 600.0  # CICERO_IMAGE_TIMEOUT: seconds to wait for a render in the studio
    max_upload_bytes: int = MAX_UPLOAD_BYTES
    max_image_bytes: int = MAX_IMAGE_BYTES

    @property
    def db_path(self) -> Path:
        return self.data_dir / "cicero.db"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "mcp-token"

    @property
    def url_path(self) -> Path:
        return self.data_dir / "url"

    @property
    def backend_json_path(self) -> Path:
        return self.data_dir / "backend.json"

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @classmethod
    def from_env(cls) -> "Config":
        raw_dir = _env("CICERO_DATA_DIR")
        port = _int(_env("CICERO_PORT") or _env("PORT") or str(DEFAULT_PORT), DEFAULT_PORT, 1, 65535)
        roots = tuple(Path(p).expanduser() for p in _env("CICERO_FILE_ROOTS").split(os.pathsep) if p.strip())
        return cls(
            data_dir=Path(raw_dir).expanduser() if raw_dir else REPO_ROOT / "data",
            port=port,
            port_strict=_env("PORT_STRICT") == "1",
            allowed_hosts=parse_allowed_hosts(_env("CICERO_ALLOWED_HOSTS")),
            data_dir_configured=bool(raw_dir),
            file_roots=roots,
            image_studio_url=_env("CICERO_IMAGE_STUDIO_URL").rstrip("/"),
            image_timeout=float(_int(_env("CICERO_IMAGE_TIMEOUT") or "600", 600, 10, 86400)),
        )

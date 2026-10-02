"""Process-level configuration read from the environment (never from the DB)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .hoard_link.appconfig import AppPaths, env_flag, env_float, env_int, env_str
from .hoard_link.guard import parse_allowed_hosts

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PORT = 5194
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_IMAGE_BYTES = 15 * 1024 * 1024


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
    def paths(self) -> AppPaths:
        """The shared data-folder layout (``cicero.db``, ``mcp-token``, ``url``, ``logs/``, ``backend.json``)."""
        return AppPaths("cicero", REPO_ROOT, self.data_dir, self.data_dir_configured)

    @property
    def db_path(self) -> Path:
        return self.paths.db_path

    @property
    def token_path(self) -> Path:
        return self.paths.token_path

    @property
    def url_path(self) -> Path:
        return self.paths.url_path

    @property
    def backend_json_path(self) -> Path:
        return self.paths.backend_json_path

    @property
    def logs_dir(self) -> Path:
        return self.paths.logs_dir

    @property
    def assets_dir(self) -> Path:
        return self.data_dir / "assets"

    @property
    def exports_dir(self) -> Path:
        return self.data_dir / "exports"

    @classmethod
    def from_env(cls) -> "Config":
        raw_dir = env_str("CICERO_DATA_DIR") or ""
        port = env_int("CICERO_PORT", "PORT", default=DEFAULT_PORT)
        if not 1 <= port <= 65535:
            port = DEFAULT_PORT
        roots = tuple(Path(p).expanduser() for p in (env_str("CICERO_FILE_ROOTS") or "").split(os.pathsep) if p.strip())
        return cls(
            data_dir=Path(raw_dir).expanduser() if raw_dir else REPO_ROOT / "data",
            port=port,
            port_strict=env_flag("PORT_STRICT"),
            allowed_hosts=parse_allowed_hosts(env_str("CICERO_ALLOWED_HOSTS")),
            data_dir_configured=bool(raw_dir),
            file_roots=roots,
            image_studio_url=(env_str("CICERO_IMAGE_STUDIO_URL") or "").rstrip("/"),
            image_timeout=env_float("CICERO_IMAGE_TIMEOUT", default=600.0, minimum=10.0, maximum=86400.0),
        )

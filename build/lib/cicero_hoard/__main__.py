"""`python -m cicero_hoard` — run the app with uvicorn on 127.0.0.1 (the shared Hoard Link launcher)."""

from __future__ import annotations

from .hoard_link.service import run_main


def main() -> int:
    return run_main(service="cicero-hoard", package="cicero_hoard", default_port=5194, app_factory="cicero_hoard.main:create_app",
                    data_dir_env="CICERO_DATA_DIR", port_env="CICERO_PORT", open_browser_default=False, title="Cicero's Hoard")


if __name__ == "__main__":
    raise SystemExit(main())

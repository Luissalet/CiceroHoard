"""Stdio MCP bridge for Cicero's Hoard.

It never opens the database: every tool call is proxied to the running app (`POST /api/agent/call`) with the
Bearer token from `<DATA_DIR>/mcp-token`. The tool list is fetched from `GET /api/agent/tools` (refreshed while the
bridge runs), so the bridge and the app can never disagree. When nothing answers, the bridge starts the app itself
(`python -m cicero_hoard`, detached, on the port of CICERO_URL) and waits for it; CICERO_BRIDGE_AUTOSTART=0 turns
that off. The bridge itself is the shared catalogue bridge of Hoard Link; the slow tools (generation, export,
pictures) publish their own waiting time in the catalogue.
"""

from __future__ import annotations

import sys

from cicero_hoard.hoard_link.bridge import CatalogBridge


def main() -> int:
    CatalogBridge(app="cicero", service="cicero-hoard", package="cicero_hoard", default_port=5194,
                  data_dir_env="CICERO_DATA_DIR", title="Cicero's Hoard", root=__file__).run_bridge()
    return 0


if __name__ == "__main__":
    sys.exit(main())

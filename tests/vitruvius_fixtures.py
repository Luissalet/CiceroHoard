"""Recorded answers of Vitruvius's Hoard through the hub proxy (tests/fixtures/vitruvius/*.json), served by a fake hub.

Recorded on 03-11-2026 from the running studio (design_slop_audit of a four-slide stacked deck, design_preset_list,
design_pick_themes with use_model=false, software_modules); the tests never reach a live app."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Optional

from conftest import FakeHub

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "vitruvius"


def recorded(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


DOWN = {"ok": False, "status": None, "contract": "shared", "error": "URLError: "}
MODULE_OFF = {"ok": False, "status": 400, "contract": "shared", "error": "Enable module explicitly first: design"}


class StudioHub(FakeHub):
    """The fake hub of conftest plus the studio's recorded tools. ``state``: up, down (until started) or off (module off until set)."""

    def __init__(self, state: str = "up", audit: Optional[dict] = None, **kw):
        super().__init__(**kw)
        self.state = state
        self.audit = audit
        self.starts = 0

    def call(self, app, tool, arguments=None, *, timeout=120.0):
        if app != "vitruvius" or tool in ("tokens_list", "tokens_get") or self.error:
            return super().call(app, tool, arguments, timeout=timeout)
        self.calls.append((app, tool, dict(arguments or {})))
        if self.state == "down":
            return {"app": app, "tool": tool, **DOWN}
        if tool == "software_modules":
            answer = recorded("software_modules")
            answer["result"]["modules"][0]["state"] = "off" if self.state == "off" else "on"
            return answer
        if tool == "software_module_set":
            self.state = "up"
            return {"ok": True, "app": app, "tool": tool, "status": 200, "result": {"module": "design", "state": "on"}}
        if self.state == "off":
            return {"app": app, "tool": tool, **MODULE_OFF}
        if tool == "design_slop_audit":
            return copy.deepcopy(self.audit) if self.audit else recorded("design_slop_audit")
        if tool == "design_preset_list":
            if (arguments or {}).get("name") == "ledger-ink":
                return recorded("design_preset_ledger_ink")
            if (arguments or {}).get("name"):
                return {"ok": False, "app": app, "tool": tool, "status": 404, "error": "Unknown preset"}
            return recorded("design_preset_list")
        if tool == "design_pick_themes":
            return recorded("design_pick_themes")
        return {"ok": False, "app": app, "tool": tool, "status": 400, "error": "Unknown tool"}

    def start(self, path, body, timeout):
        """Stands in for design_audit.hub_post: the Hub starting the studio."""
        self.starts += 1
        if self.state == "down":
            self.state = "up"
        return 200, {"ok": True, "app": "vitruvius", "ready": True}

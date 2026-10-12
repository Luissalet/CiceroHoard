"""Themes made from another app's design system, stored beside the built-in ones.

A deck's ``theme`` column holds either a built-in id or the id of a row here; ``decks.deck_view`` attaches the definition as
``theme_def`` so the renderers never touch the database.
"""

from __future__ import annotations

import json
from typing import Any

from .errors import CiceroError
from .themes import clean_custom_theme, contrast_issues, get_theme, list_themes, require_theme as require_builtin
from .util import jload

BUILTIN_IDS = {t["id"] for t in list_themes()}


def _row_theme(row: Any) -> dict[str, Any]:
    theme = jload(row["definition"], {})
    return {**theme, "id": row["id"], "name": row["name"], "custom": True, "source_ref": row["source_ref"],
            "source_revision": row["source_revision"], "warnings": jload(row["warnings"], [])}


def list_custom(svc: Any) -> list[dict[str, Any]]:
    return [_row_theme(r) for r in svc.db.query("SELECT * FROM custom_themes ORDER BY created_ts, id")]


def get_custom(svc: Any, theme_id: str) -> dict[str, Any] | None:
    row = svc.db.one("SELECT * FROM custom_themes WHERE id = ?", (theme_id,))
    return _row_theme(row) if row else None


def find_by_source(svc: Any, source_ref: str, revision: str) -> dict[str, Any] | None:
    row = svc.db.one("SELECT * FROM custom_themes WHERE source_ref = ? AND source_revision = ? ORDER BY created_ts LIMIT 1", (source_ref, revision))
    return _row_theme(row) if row else None


def save_custom(svc: Any, theme: dict[str, Any], *, source_ref: str, revision: str, warnings: list[str]) -> dict[str, Any]:
    clean = clean_custom_theme(theme)
    if clean["id"] in BUILTIN_IDS:
        raise CiceroError(f"{clean['id']!r} is a built-in theme id.")
    definition = {k: clean[k] for k in ("colors", "fonts", "radius")}
    svc.db.execute("INSERT INTO custom_themes(id, name, definition, source_ref, source_revision, warnings, created_ts) VALUES (?,?,?,?,?,?,?)",
                   (clean["id"], clean["name"], json.dumps(definition), source_ref, revision, json.dumps(warnings), svc.clock()))
    return get_custom(svc, clean["id"]) or clean


def all_themes(svc: Any) -> list[dict[str, Any]]:
    return [*list_themes(), *list_custom(svc)]


def resolve(svc: Any, theme_id: str | None) -> dict[str, Any]:
    """The full theme for an id: a built-in one, or a saved custom one."""
    custom = get_custom(svc, theme_id) if theme_id else None
    return custom if custom else get_theme(theme_id)


def require(svc: Any, theme_id: str) -> str:
    if get_custom(svc, theme_id):
        return theme_id
    try:
        return require_builtin(theme_id)
    except CiceroError:
        names = ", ".join(t["id"] for t in all_themes(svc))
        raise CiceroError(f"Unknown theme {theme_id!r}. Available: {names}.") from None


# ---------------- from a design system ----------------

VITRUVIUS_APP = "vitruvius"


def theme_ref(theme_id: str) -> str:
    return f"hoard://cicero/theme/{theme_id}"


def tokens_ref(tokens_id: str) -> str:
    return f"hoard://{VITRUVIUS_APP}/tokens/{tokens_id}"


def _hub_result(answer: dict[str, Any], what: str) -> dict[str, Any]:
    """The tool result inside a hub proxy answer, or a CiceroError that says what went wrong."""
    if not answer.get("ok"):
        reason = answer.get("error") or f"status {answer.get('status')}"
        if answer.get("status") in (404, 502, 503) or "not reachable" in str(reason) or "unreachable" in str(reason):
            reason = f"{reason}. Is the design-system app running and linked to the hub?"
        raise CiceroError(f"Could not {what}: {reason}", code="family_unavailable")
    result = answer.get("result")
    if not isinstance(result, dict):
        raise CiceroError(f"Could not {what}: unexpected answer from the design-system app.", code="family_unavailable")
    return result


def list_design_systems(svc: Any) -> list[dict[str, Any]]:
    """The design systems the family offers, with their colour roles, newest first."""
    result = _hub_result(svc.family_call(VITRUVIUS_APP, "tokens_list", {"compact": True, "limit": 50}), "list design systems")
    items = result.get("design_systems") or []
    return [{"id": d["id"], "name": d.get("name") or d["id"], "created_ts": d.get("created_ts"), "roles": d.get("roles") or {}}
            for d in items if isinstance(d, dict) and d.get("id")]


def from_tokens(svc: Any, tokens_id: str, mode: str = "light") -> dict[str, Any]:
    """Save a design system as a Cicero theme. Idempotent: the same system in the same state gives back the theme it made before."""
    from .hoard_link import artifacts
    from .themes import theme_from_roles

    if not (tokens_id or "").strip():
        raise CiceroError("tokens_id is required.")
    system = _hub_result(svc.family_call(VITRUVIUS_APP, "tokens_get", {"id": tokens_id}), f"read design system {tokens_id!r}")
    roles = system.get("roles")
    if not isinstance(roles, dict):
        raise CiceroError("That design system did not send its colour roles; update the design-system app.", code="family_unavailable")
    source_ref = tokens_ref(tokens_id)
    revision = artifacts.revision_for(json.dumps({"mode": mode, "roles": roles}, sort_keys=True))
    existing = find_by_source(svc, source_ref, revision)
    if existing:
        return {"theme": existing, "created": False, "warnings": existing.get("warnings", []), "contrast_issues": contrast_issues(existing)}
    name = f"{roles.get('name') or system.get('name') or tokens_id} ({'oscuro' if mode == 'dark' else 'claro'})"
    theme_id = f"ds-{tokens_id}-{mode}-{revision.split(':')[-1][:8]}"
    theme, warnings = theme_from_roles(roles, theme_id=theme_id, name=name, mode=mode)
    saved = save_custom(svc, theme, source_ref=source_ref, revision=revision, warnings=warnings)
    svc.emit("cicero.theme.created", {"id": theme_id, "name": name, "ref": theme_ref(theme_id), "from": source_ref})
    svc.refs_link(theme_ref(theme_id), source_ref, "derived_from", from_label=name, to_label=str(system.get("name") or tokens_id))
    return {"theme": saved, "created": True, "warnings": warnings, "contrast_issues": contrast_issues(saved)}

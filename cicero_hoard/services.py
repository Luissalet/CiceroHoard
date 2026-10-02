"""Wiring: database, Hoard Link, the image studio, exporters and settings.

Every provider is injectable so the whole app runs offline in tests; the domain modules (decks, generate, check, ...)
take this object as their first argument.
"""

from __future__ import annotations

import dataclasses
import logging
import time
from typing import Any, Callable, Optional

from . import APP_ID, SERVICE, __version__
from . import decks as store
from .check import check_deck
from .config import Config
from .db import Database
from .errors import CiceroError
from .hoard_link import fam_refs, family, tokens
from .hoard_link.config import LinkConfig
from .images import ImageStudio
from .render import render_document
from . import custom_themes
from .util import clip

log = logging.getLogger("cicero")

EXPORT_FORMATS = ("pptx", "pdf", "html", "md")


class Services:
    def __init__(self, config: Config, *, link: Any = None, image_studio: Any = None, emit_fn: Optional[Callable[[str, dict], None]] = None,
                 clock_fn: Callable[[], float] = time.time, pdf_fn: Optional[Callable[..., bytes]] = None,
                 family_call_fn: Optional[Callable[..., dict]] = None, refs_link_fn: Optional[Callable[..., dict]] = None):
        self.config = config
        self.clock = clock_fn
        self.started_at = time.time()
        config.data_dir.mkdir(parents=True, exist_ok=True)
        self.token = tokens.read_or_create_token(config.token_path)  # stable across restarts: the bridge keeps working
        try:
            tokens.write_url(config.url_path, f"http://127.0.0.1:{config.port}")
        except OSError:
            pass
        self.db = Database(config.db_path)
        self._injected_link = link
        self._link: Any = None
        self.link_sync: Any = link if link is not None else self._build_link()
        self.image_studio = image_studio or ImageStudio(configured_url=config.image_studio_url, timeout=config.image_timeout)
        self._emit = emit_fn
        self._pdf_fn = pdf_fn
        self._family_call_fn = family_call_fn
        self._refs_link_fn = refs_link_fn

    # ---------------- lifecycle ----------------
    def start(self) -> None:
        pass

    def stop(self) -> None:
        self._close_link()
        self.db.close()

    def _close_link(self) -> None:
        if self._link is not None:
            try:
                self.link_sync.close()
            except Exception:  # noqa: BLE001
                pass

    def _build_link(self) -> Any:
        from .hoard_link.link import Link

        link_config = LinkConfig.load(self.config.backend_json_path if self.config.backend_json_path.is_file() else None, app=APP_ID)
        preferred = str(self.db.get_setting("model", "") or "").strip()
        if preferred:  # the person's choice in Settings wins over backend.json and the environment
            llm = dataclasses.replace(link_config.capability("llm"), model=preferred)
            link_config = dataclasses.replace(link_config, capabilities={**link_config.capabilities, "llm": llm})
        self._link = Link(link_config)
        return self._link.sync

    # ---------------- events ----------------
    def emit(self, type_: str, data: dict[str, Any]) -> None:
        """Announce something on the hub bus (ids and short titles only); never raises."""
        try:
            if self._emit is not None:
                self._emit(type_, data)
            else:
                family.emit(type_, data)
        except Exception:  # noqa: BLE001
            pass

    # ---------------- settings ----------------
    def default_language(self) -> str:
        value = self.db.get_setting("default_language", "es")
        return value if value in ("es", "en") else "es"

    def pdf_available(self) -> bool:
        if self._pdf_fn is not None:
            return True
        from .export_pdf import pdf_available

        return pdf_available()

    def get_settings(self) -> dict[str, Any]:
        return {
            "model": str(self.db.get_setting("model", "") or ""),
            "default_language": self.default_language(),
            "pdf_available": self.pdf_available(),
            "image_studio": {"configured_url": self.config.image_studio_url or None, "timeout_s": self.config.image_timeout},
            "file_roots": [str(p) for p in self.config.file_roots],
            "max_upload_mb": self.config.max_upload_bytes // (1024 * 1024),
        }

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        if "default_language" in patch:
            if patch["default_language"] not in ("es", "en"):
                raise CiceroError("default_language must be 'es' or 'en'.")
            self.db.set_setting("default_language", patch["default_language"])
        if "model" in patch:
            model = (patch["model"] or "").strip()
            self.db.set_setting("model", model)
            if self._injected_link is None:  # rebuild the link so the preference applies to the next call
                self._close_link()
                self.link_sync = self._build_link()
        return self.get_settings()

    # ---------------- status ----------------
    def counts(self) -> dict[str, int]:
        one = lambda sql: self.db.one(sql)["c"]  # noqa: E731
        return {"decks": one("SELECT COUNT(*) c FROM decks"), "sources": one("SELECT COUNT(*) c FROM sources"),
                "slides": one("SELECT COUNT(*) c FROM slides"), "exports": one("SELECT COUNT(*) c FROM exports")}

    def status(self) -> dict[str, Any]:
        try:
            model = self.link_sync.status()
        except Exception as error:  # noqa: BLE001
            model = {"error": f"{type(error).__name__}: {error}"}
        return {"service": SERVICE, "version": __version__, "counts": self.counts(), "model": model, "pdf_available": self.pdf_available(),
                "family": family.status(), "uptime_s": int(time.time() - self.started_at),
                "db": str(self.config.db_path) if self.config.data_dir_configured else "data/cicero.db", "schema": self.db.schema_version}

    # ---------------- rendering and export ----------------
    def assets_lookup(self) -> Callable[[str], Optional[dict[str, Any]]]:
        return lambda asset_id: store.asset_info(self, asset_id)

    def themes(self) -> list[dict[str, Any]]:
        return custom_themes.all_themes(self)

    # ---------------- other apps ----------------
    def family_call(self, app: str, tool: str, arguments: Optional[dict[str, Any]] = None, timeout: float = 30.0) -> dict[str, Any]:
        """Call a tool of another app through the hub; the answer is the hub's ``{ok, result|error, status}``. Never raises."""
        try:
            return (self._family_call_fn or family.call)(app, tool, arguments or {}, timeout=timeout)
        except Exception as error:  # noqa: BLE001
            return {"ok": False, "app": app, "tool": tool, "error": f"{type(error).__name__}: {error}"}

    def refs_link(self, from_uri: str, to_uri: str, rel: str, **labels: str) -> None:
        """Tell the hub two records are connected (a hint: never raises, never blocks the work)."""
        try:
            (self._refs_link_fn or fam_refs.link)(from_uri, to_uri, rel, **labels)
        except Exception:  # noqa: BLE001
            pass

    def design_systems(self) -> list[dict[str, Any]]:
        return custom_themes.list_design_systems(self)

    def theme_from_tokens(self, tokens_id: str, mode: str = "light") -> dict[str, Any]:
        return custom_themes.from_tokens(self, tokens_id, mode)

    def preview_html(self, deck_id: str, slide_id: Optional[str] = None) -> str:
        deck = store.deck_view(self, deck_id)
        if slide_id is not None:
            store.get_slide(self, deck_id, slide_id)  # NotFound when it is not in this deck
        document, _ = render_document(deck, assets=self.assets_lookup(), inline=False, mode="single" if slide_id else "stacked", only_slide=slide_id)
        return document

    def check(self, deck_id: str) -> dict[str, Any]:
        deck = store.deck_view(self, deck_id)
        sources = store.source_texts(self, deck_id)
        return {"issues": check_deck(deck, sources, self.assets_lookup())}

    def export(self, deck_id: str, fmt: str) -> dict[str, Any]:
        if fmt not in EXPORT_FORMATS:
            raise CiceroError(f"Unknown export format {fmt!r}. Use one of: {', '.join(EXPORT_FORMATS)}.")
        deck = store.deck_view(self, deck_id)
        if not deck["slides"]:
            raise CiceroError("The presentation has no slides to export.", code="no_slides")
        assets = self.assets_lookup()
        if fmt == "pptx":
            from .export_pptx import build_pptx

            data = build_pptx(deck, assets=assets)
        elif fmt == "html":
            from .export_html import build_html

            data = build_html(deck, assets=assets)
        elif fmt == "md":
            from .export_md import build_markdown

            data = build_markdown(deck)
        else:
            if self._pdf_fn is not None:
                data = self._pdf_fn(deck, assets=assets)
            else:
                from .export_pdf import build_pdf

                data = build_pdf(deck, assets=assets)
        export = store.add_export(self, deck_id, fmt, data, deck["title"])
        self.emit("cicero.deck.exported", {"id": deck_id, "format": fmt, "title": clip(deck["title"], 80)})
        return export

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.config.port}" if self.config.port else ""

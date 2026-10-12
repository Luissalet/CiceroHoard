"""Wiring: database, Hoard Link, the image studio, exporters and settings.

Every provider is injectable so the whole app runs offline in tests; the domain modules (decks, generate, check, ...)
take this object as their first argument.
"""

from __future__ import annotations

import dataclasses
import logging
import time
import threading
from pathlib import Path
from typing import Any, Callable, Optional

from . import APP_ID, SERVICE, __version__
from . import decks as store
from .check import check_deck
from .config import Config
from .db import Database
from .errors import CiceroError, NotFound, RevisionConflict
from .hoard_link import fam_refs, family, tokens
from .hoard_link.config import LinkConfig
from .images import ImageStudio
from .render import render_document
from . import custom_themes
from . import native_slides
from .util import clip

log = logging.getLogger("cicero")

EXPORT_FORMATS = ("pptx", "pdf", "html", "md")


class Services:
    def __init__(self, config: Config, *, link: Any = None, image_studio: Any = None, emit_fn: Optional[Callable[[str, dict], None]] = None,
                 clock_fn: Callable[[], float] = time.time, pdf_fn: Optional[Callable[..., bytes]] = None,
                 family_call_fn: Optional[Callable[..., dict]] = None, refs_link_fn: Optional[Callable[..., dict]] = None,
                 native_render_fn: Optional[Callable[..., dict]] = None):
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
        self._native_render_fn = native_render_fn
        self._visual_measure_fn = None  # tests replace the browser measurement
        from .presentation import Sessions
        self.presentations=Sessions(clock_fn)
        from .data_links import Worker
        self.data_link_lock = threading.RLock()
        self.data_link_worker = Worker(self)

    # ---------------- lifecycle ----------------
    def start(self) -> None:
        self.data_link_worker.start()

    def stop(self) -> None:
        self.data_link_worker.stop()
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

    def preview_html(self, deck_id: str, slide_id: Optional[str] = None, mode: str = 'stacked',layout: Optional[str] = None) -> str:
        deck = store.deck_view(self, deck_id)
        from .advanced import hydrate
        deck=hydrate(self,deck)
        if slide_id is not None:
            store.get_slide(self, deck_id, slide_id)  # NotFound when it is not in this deck
        if layout:
            from .models import LAYOUTS
            if not slide_id or layout not in LAYOUTS:raise CiceroError('Choose a slide and a supported composition.')
            for slide in deck['slides']:
                if slide['id']==slide_id:slide['layout']=layout
        if deck.get('template'):
            from .template_live import document
            return document(self,deck,slide_id=slide_id,mode='single' if slide_id else mode,inline=False)
        document, _ = render_document(deck, assets=self.assets_lookup(), inline=False, mode="single" if slide_id else "stacked", only_slide=slide_id)
        if mode=='present':
            from .render import present_document
            return present_document(document)
        return document

    def check(self, deck_id: str) -> dict[str, Any]:
        deck = store.deck_view(self, deck_id)
        sources = store.source_texts(self, deck_id)
        issues=check_deck(deck, sources, self.assets_lookup())
        result={"issues":issues}
        if deck.get('template'):
            folder=native_slides.cache_folder(self.config.data_dir,deck)
            report_path=folder/'report.json'
            if report_path.is_file():
                import json
                report=json.loads(report_path.read_text(encoding='utf-8-sig'))
                extra=native_slides.layout_findings(report)
                by_position={s['position']:s['id'] for s in deck['slides']}
                issues.extend({**item,'slide_id':by_position.get(item['position'])} for item in extra)
                result['native_review']={'status':'rendered','renderer':report['renderer'],'findings':len(extra)}
            else:
                result['native_review']={'status':'not_rendered','next':'Export PDF or open the template preview before assessing the actual layout.'}
        return result

    def _native_snapshot(self, deck: dict) -> tuple:
        from .export_pptx import build_pptx
        folder=native_slides.cache_folder(self.config.data_dir,deck)
        report=(self._native_render_fn or native_slides.render)(build_pptx(deck,assets=self.assets_lookup()),folder)
        return folder,report

    def export(self, deck_id: str, fmt: str) -> dict[str, Any]:
        with self.data_link_lock:
            return self._export(deck_id,fmt)

    def _export(self, deck_id: str, fmt: str) -> dict[str, Any]:
        warnings=[]
        if fmt not in EXPORT_FORMATS:
            raise CiceroError(f"Unknown export format {fmt!r}. Use one of: {', '.join(EXPORT_FORMATS)}.")
        deck = store.deck_view(self, deck_id)
        if not deck["slides"]:
            raise CiceroError("The presentation has no slides to export.", code="no_slides")
        from .advanced import hydrate,static_deck
        if fmt in ('pptx','pdf'):
            kinds={b['type'] for s in deck['slides'] for b in s['blocks']}
            if 'scene3d' in kinds:warnings.append('3D scenes and camera paths are interactive in HTML; this file uses rendered scene posters.')
            if 'poll' in kinds:warnings.append('Live audience voting is available on the local web audience; this file contains vote snapshots.')
            if any(b.get('animation','none')!='none' for s in deck['slides'] for b in s['blocks'] if b['type']=='chart'):
                warnings.append('Series, point and data-state animations run in HTML; this file retains the base chart data.')
        deck=static_deck(self,deck) if fmt in ('pptx','pdf') else hydrate(self,deck)
        assets = self.assets_lookup()
        if deck.get('template') and fmt=='html':
            from .template_live import document
            data=document(self,deck,mode='present').encode('utf-8')
        elif deck.get('template') and fmt=='pdf':
            folder,report=self._native_snapshot(deck)
            data=(folder/'slides.pdf').read_bytes()
        elif fmt == "pptx":
            from .export_pptx import build_pptx

            data = build_pptx(deck, assets=assets)
            # click stages, auto/mixed/effect animations and slide transitions, written as native OOXML (animations.json)
            from . import animations as motion
            data, motion_report = motion.apply(data, self.animations_get(deck_id), [s['id'] for s in deck['slides']],
                                               transitions={s['id']:s['transition'] for s in deck['slides'] if s.get('transition')})
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
        cache_review=None
        if fmt=='pptx':
            from .chart_cache import refresh_numeric_caches
            data,cache_review=refresh_numeric_caches(data)
        export = store.add_export(self, deck_id, fmt, data, deck["title"])
        from .data_links import inspect,RefArgs
        linked=inspect(self,RefArgs(deck_id=deck_id))['items']
        if linked:
            export['data_snapshot']=[{k:r[k] for k in ('id','source_id','checked_ts','refreshed_ts','error')} for r in linked]
            warnings.extend('Linked data retained its last good snapshot: '+r['error'] for r in linked if r['error'])
        if fmt=='pptx' and any(b.get('subtitles') and b['type']=='audio' for s in deck['slides'] for b in s['blocks']):
            warnings.append('Timed audio captions are available in HTML only; native audio retains its caption label.')
        if cache_review is not None:export['cache_review']=cache_review
        if warnings:export['warnings']=warnings
        if fmt=='pptx':export['animations']={k:motion_report[k] for k in ('animated','transitions')}
        self.emit("cicero.deck.exported", {"id": deck_id, "format": fmt, "title": clip(deck["title"], 80)})
        return export

    # ---------------- animations ----------------
    def animations_get(self, deck_id: str) -> dict[str, Any]:
        from .animations import AnimationStore
        store.deck_view(self, deck_id)                       # 404 for an unknown deck
        return AnimationStore(self.config.data_dir).get(deck_id)

    def animations_set(self, deck_id: str, settings: dict[str, Any], *, merge: bool = True) -> dict[str, Any]:
        from .animations import AnimationStore
        deck = store.deck_view(self, deck_id)
        try:
            saved = AnimationStore(self.config.data_dir).set(deck_id, settings, {s['id'] for s in deck['slides']}, merge=merge)
        except ValueError as exc:
            raise CiceroError(str(exc), code='bad_animation') from exc
        self.emit("cicero.deck.animations", {"id": deck_id, "mode": saved["mode"], "transition": saved["transition"]})
        return saved

    def animations_reset(self, deck_id: str) -> dict[str, Any]:
        from .animations import AnimationStore
        store.deck_view(self, deck_id)
        return AnimationStore(self.config.data_dir).reset(deck_id)

    def animations_preview(self, deck_id: str) -> dict[str, Any]:
        """What the next .pptx export would carry, per slide, without storing an export."""
        from . import animations as motion
        from .export_pptx import build_pptx
        deck = store.deck_view(self, deck_id)
        if not deck['slides']:
            raise CiceroError("The presentation has no slides to export.", code="no_slides")
        _, report = motion.apply(build_pptx(deck, assets=self.assets_lookup()), self.animations_get(deck_id), [s['id'] for s in deck['slides']],
                                  transitions={s['id']:s['transition'] for s in deck['slides'] if s.get('transition')})
        return report

    # ---------------- visual review ----------------
    def visual_review_dir(self, deck_id: str) -> Path:
        return self.config.data_dir / "visual_review" / deck_id

    def _review_scene(self, deck: dict[str, Any]) -> dict[str, Any]:
        """For a template deck, the same scene the preview shows (template furniture, its own slide size); the standard
        rendering otherwise (empty: the review builds it)."""
        if not deck.get("template"):
            return {}
        from .template_live import document, scenes
        _, width, height = scenes(deck, self.assets_lookup())
        return {"document": document(self, deck, mode="stacked", inline=True), "size": (int(width), int(height))}

    def visual_review(self, deck_id: str, *, fix: bool = False) -> dict[str, Any]:
        """Render every slide in the browser, keep a PNG of each and apply the hard rules; with ``fix`` apply the
        allowed automatic fix (minimum font size on slides whose text overflows) and review again."""
        from . import visual_review as vr
        deck = store.deck_view(self, deck_id)
        if not deck["slides"]:
            raise CiceroError("The presentation has no slides to export.", code="no_slides")
        folder = self.visual_review_dir(deck_id)
        result = vr.review(deck, assets=self.assets_lookup(), png_dir=folder, measure_fn=self._visual_measure_fn,
                           **self._review_scene(deck))
        if fix:
            fixed, skipped = [], []
            for entry in result["slides"]:
                if any(f["rule"] == "text_overflow" for f in entry["findings"]):
                    slide = next(s for s in deck["slides"] if s["id"] == entry["slide_id"])
                    blocks = vr.shrink_patch(slide)
                    if blocks is None:
                        continue
                    try:
                        # only over the revision that was measured: an edit made meanwhile is kept, never overwritten
                        store.patch_slide(self, deck_id, slide["id"], {"blocks": blocks, "expected_revision": slide["revision"]},
                                          reason="visual review: minimum font size")
                    except (RevisionConflict, NotFound):
                        skipped.append({"slide_id": slide["id"], "position": entry["position"],
                                        "reason": "the slide changed while it was being measured; it is reviewed again as it is now"})
                        continue
                    fixed.append({"slide_id": slide["id"], "position": entry["position"], "fix": f"font_size {vr.MIN_FONT} on text and bullets"})
            if fixed or skipped:
                before = {"errors": result["errors"], "warnings": result["warnings"]}
                current = store.deck_view(self, deck_id)
                result = vr.review(current, assets=self.assets_lookup(), png_dir=folder, measure_fn=self._visual_measure_fn,
                                   **self._review_scene(current))
                result["before"] = before
            result["fixed"] = fixed
            if skipped:
                result["skipped"] = skipped
        for entry in result["slides"]:
            if entry.get("png"):
                entry["png_url"] = f"/api/decks/{deck_id}/visual-review/{Path(entry['png']).name}"
        self.emit("cicero.deck.reviewed", {"id": deck_id, "errors": result["errors"], "warnings": result["warnings"]})
        return result

    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.config.port}" if self.config.port else ""

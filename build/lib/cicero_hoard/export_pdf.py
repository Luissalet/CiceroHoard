"""PDF export: a headless Chromium prints the same HTML the preview shows (13.333 x 7.5 in, one slide per page).

The browser is found and started by the shared Hoard Link launcher (``hoard_link.web.browser``): the installed Edge or
Chrome, Playwright's Chromium (``PLAYWRIGHT_BROWSERS_PATH`` or the default install location) or a system Chromium. Without any browser the export fails
with ``pdf_unavailable`` and a message that says what to install; nothing else in the app is affected.
"""

from __future__ import annotations

import tempfile
from typing import Any, Callable, Optional

from .errors import PdfUnavailable
from .hoard_link.web import browser
from .render import render_document

AssetLookup = Callable[[str], Optional[dict[str, Any]]]
INSTALL_HINT = "Install a browser for the PDF export with `python -m playwright install chromium`, or export PPTX/HTML instead."

find_chromium = browser.find_chromium  # the shared discovery (Playwright's folders), kept under its old name


def pdf_available() -> bool:
    """Cheap check (no browser is started): a Playwright package plus a browser on disk or a system Edge/Chrome/Chromium."""
    return browser.playwright_installed() and bool(browser.find_chromium() or browser.system_browsers())


def _launch(p: Any, profile_dir: str) -> Any:
    """The first browser that starts, through the shared launcher (installed Edge/Chrome first on Windows, then Playwright's Chromium)."""
    try:
        context, _name = browser.launch_context(p, profile_dir, headless=True)
    except browser.BrowserUnavailable as error:
        raise PdfUnavailable(f"No Chromium is available for the PDF export ({error}). {INSTALL_HINT}") from error
    return context


def build_pdf(deck: dict[str, Any], *, assets: AssetLookup) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PdfUnavailable(f"The playwright package is not installed. {INSTALL_HINT}") from error
    document, _ = render_document(deck, assets=assets, inline=True, mode="stacked")
    try:
        # a throwaway profile folder per export: two exports at once (or a stale one) never fight over a profile lock
        with sync_playwright() as p, tempfile.TemporaryDirectory(prefix="cicero-pdf-") as profile:
            context = _launch(p, profile)
            try:
                page = context.new_page()
                page.set_content(document, wait_until="load")
                page.emulate_media(media="print")
                return page.pdf(width="13.333in", height="7.5in", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                                prefer_css_page_size=True)
            finally:
                context.close()
    except PdfUnavailable:
        raise
    except Exception as error:  # noqa: BLE001
        raise PdfUnavailable(f"The PDF could not be produced ({str(error).splitlines()[0] if str(error) else type(error).__name__}). {INSTALL_HINT}") from error

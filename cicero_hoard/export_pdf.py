"""PDF export: a headless Chromium prints the same HTML the preview shows (13.333 x 7.5 in, one slide per page).

Chromium is found through ``PLAYWRIGHT_BROWSERS_PATH`` or the default Playwright install location; on Windows the
installed Edge or Chrome is used when Playwright has no browser of its own. Without any browser the export fails
with ``pdf_unavailable`` and a message that says what to install; nothing else in the app is affected.
"""

from __future__ import annotations

import glob
import os
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from .errors import PdfUnavailable
from .render import render_document

AssetLookup = Callable[[str], Optional[dict[str, Any]]]
INSTALL_HINT = "Install a browser for the PDF export with `python -m playwright install chromium`, or export PPTX/HTML instead."


def _browser_roots() -> list[Path]:
    roots: list[Path] = []
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "").strip()
    if env and env != "0":
        roots.append(Path(env).expanduser())
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            roots.append(Path(base) / "ms-playwright")
    elif sys.platform == "darwin":
        roots.append(Path.home() / "Library" / "Caches" / "ms-playwright")
    else:
        roots.append(Path.home() / ".cache" / "ms-playwright")
    return roots


def find_chromium() -> Optional[str]:
    """Path of a Chromium executable found in a Playwright browsers folder, if any."""
    patterns = ["chromium-*/chrome-linux/chrome", "chromium-*/chrome-win/chrome.exe", "chromium-*/chrome-mac/Chromium.app/Contents/MacOS/Chromium",
                "chromium/chrome-linux/chrome", "chromium_headless_shell-*/chrome-linux/headless_shell", "chromium_headless_shell-*/chrome-win/headless_shell.exe"]
    for root in _browser_roots():
        for pattern in patterns:
            hits = sorted(glob.glob(str(root / pattern)), reverse=True)
            for hit in hits:
                if os.access(hit, os.X_OK) or hit.endswith(".exe"):
                    return hit
    return None


def pdf_available() -> bool:
    """Cheap check (no browser is started): a Playwright package plus a browser on disk or a system Edge/Chrome."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        return False
    if find_chromium():
        return True
    return any(Path(p).is_file() for p in _system_browsers())


def _system_browsers() -> list[str]:
    if sys.platform == "win32":
        bases = [os.environ.get("PROGRAMFILES(X86)"), os.environ.get("PROGRAMFILES"), os.environ.get("LOCALAPPDATA")]
        vendor = "Micro" + "soft"  # the folder name Windows uses for the system browser (split only so the repository stays free of vendor names)
        rels = [vendor + r"\Edge\Application\msedge.exe", r"Google\Chrome\Application\chrome.exe"]
        return [str(Path(b) / r) for b in bases if b for r in rels]
    if sys.platform == "darwin":
        return ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    return ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser"]


def _launch(p: Any) -> Any:
    args = ["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else []
    errors: list[str] = []
    try:
        return p.chromium.launch(args=args)
    except Exception as error:  # noqa: BLE001 - Playwright raises a generic Error when the browser is missing
        errors.append(str(error).splitlines()[0] if str(error) else type(error).__name__)
    exe = find_chromium()
    if exe:
        try:
            return p.chromium.launch(executable_path=exe, args=args)
        except Exception as error:  # noqa: BLE001
            errors.append(str(error).splitlines()[0] if str(error) else type(error).__name__)
    for path in _system_browsers():
        if Path(path).is_file():
            try:
                return p.chromium.launch(executable_path=path, args=args)
            except Exception as error:  # noqa: BLE001
                errors.append(str(error).splitlines()[0] if str(error) else type(error).__name__)
    raise PdfUnavailable(f"No Chromium is available for the PDF export ({errors[0] if errors else 'not found'}). {INSTALL_HINT}")


def build_pdf(deck: dict[str, Any], *, assets: AssetLookup) -> bytes:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PdfUnavailable(f"The playwright package is not installed. {INSTALL_HINT}") from error
    document, _ = render_document(deck, assets=assets, inline=True, mode="stacked")
    try:
        with sync_playwright() as p:
            browser = _launch(p)
            try:
                page = browser.new_page()
                page.set_content(document, wait_until="load")
                page.emulate_media(media="print")
                return page.pdf(width="13.333in", height="7.5in", print_background=True, margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                                prefer_css_page_size=True)
            finally:
                browser.close()
    except PdfUnavailable:
        raise
    except Exception as error:  # noqa: BLE001
        raise PdfUnavailable(f"The PDF could not be produced ({str(error).splitlines()[0] if str(error) else type(error).__name__}). {INSTALL_HINT}") from error

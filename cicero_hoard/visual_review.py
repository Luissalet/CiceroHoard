"""Visual review before export: render every slide in a real browser, keep a PNG of each, and apply hard rules to what
the browser actually laid out (not to estimates).

Rules, each with what may be done about it:

* ``off_slide`` (error): an object crosses the slide edge (1280x720, or the template's own size). Fix: move or shrink it (frame).
* ``text_overflow`` (error): the text needs more room than its box even at the smallest fitted size. Auto-fix: set the
  slide's text and bullet blocks to the minimum font size (14), then review again; otherwise shorten the text.
* ``overlap`` (warning): two content objects (text, picture, chart, table) cover each other by more than 4 % of the
  smaller one. Fix: another layout or frames.
* ``contrast`` (error): text against what is really behind it below 4.5:1 (3:1 for large text). Fix: another theme or
  colour.
* ``broken_image`` (error): a picture that does not load. Fix: re-import the asset.
* ``missing_title`` / ``missing_chart`` / ``missing_image`` (warning): the layout's key element is absent.

The method follows the visual-review step of PPT Master (MIT): render, measure, fix with the allowed move, render again.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any, Callable, Optional

from .errors import PdfUnavailable
from .hoard_link.web import browser
from .render import render_document

AssetLookup = Callable[[str], Optional[dict[str, Any]]]
MIN_FONT = 14
OVERLAP_SHARE = 0.04

FIXES = {
    "off_slide": "Move or shrink the object (block frame) so it stays inside the slide.",
    "text_overflow": "Shorten the text, split the slide, or let the review set the minimum font size (fix=true).",
    "overlap": "Choose another layout or give the blocks frames that do not cover each other.",
    "contrast": "Pick a theme or colour with more contrast for this text.",
    "broken_image": "Re-import the picture; the asset is missing or unreadable.",
    "missing_title": "Give the slide a title.",
    "missing_chart": "Add the chart block this layout is for.",
    "missing_image": "Add the picture this layout is for.",
}
SEVERITY = {"off_slide": "error", "text_overflow": "error", "contrast": "error", "broken_image": "error",
            "overlap": "warning", "missing_title": "warning", "missing_chart": "warning", "missing_image": "warning"}

# Runs in the page: one record per slide with the measured findings.
_PROBE = r"""
() => {
  const lum = (c) => { const m = (c || '').match(/rgba?\(([^)]+)\)/); if (!m) return null;
    const p = m[1].split(',').map(Number); if (p.length > 3 && p[3] < 0.5) return null;
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(p[0]) + 0.7152 * f(p[1]) + 0.0722 * f(p[2]); };
  const ratio = (a, b) => (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
  const out = [];
  for (const section of document.querySelectorAll('section.slide')) {
    const stage = section.querySelector('.stage'); const sr = stage.getBoundingClientRect();
    const W = stage.offsetWidth || 1280, H = stage.offsetHeight || 720;  // the scene's own size (a template may differ)
    const sx = W / sr.width, sy = H / sr.height;
    const rel = (r) => ({x: (r.left - sr.left) * sx, y: (r.top - sr.top) * sy, w: r.width * sx, h: r.height * sy});
    const found = []; const content = [];
    const boxes = Array.from(stage.querySelectorAll('.b'));
    for (const el of boxes) {
      const r = rel(el.getBoundingClientRect()); if (r.w < 1 || r.h < 1) continue;
      const isText = el.classList.contains('t'); const isImg = el.tagName === 'IMG';
      const isChart = !!el.querySelector(':scope > svg') && !el.classList.contains('diagram-node');
      const isTable = !!el.querySelector('table');
      const isScene = el.classList.contains('scene3d'), isPoll = el.classList.contains('poll');
      const label = isText ? (el.innerText || '').trim().slice(0, 60) : isImg ? 'picture' : isChart ? 'chart' : isTable ? 'table' : 'shape';
      // a text box that starts inside the slide and only runs past the bottom grew with its text: that is overflow
      // (and the minimum-font fix applies), not an object placed off the slide
      const grewDown = isText && r.x >= -2 && r.y >= -2 && r.x + r.w <= W + 2 && r.y < H && r.y + r.h > H + 2;
      if (grewDown) found.push({rule: 'text_overflow', where: label,
        detail: `needs ${Math.round(r.h)}px, the slide leaves ${Math.round(H - r.y)}px`, need: Math.round(r.h), have: Math.round(H - r.y)});
      else if (r.x < -2 || r.y < -2 || r.x + r.w > W + 2 || r.y + r.h > H + 2) found.push({rule: 'off_slide', where: label,
        detail: `${Math.round(r.x)},${Math.round(r.y)} ${Math.round(r.w)}x${Math.round(r.h)}`});
      if (isText && !grewDown) {
        // the ink of the text, not scrollHeight: a trailing paragraph margin is space, not overflow
        // line boxes of the text nodes only: element boxes carry paragraph margins that are space, not text
        const box = el.getBoundingClientRect(); const ink = {top: Infinity, bottom: -Infinity, right: -Infinity, height: 0};
        const walker = document.createTreeWalker(el, NodeFilter.SHOW_TEXT); let tn; const range = document.createRange();
        while ((tn = walker.nextNode())) { if (!tn.textContent.trim()) continue; range.selectNodeContents(tn);
          for (const q of range.getClientRects()) { ink.top = Math.min(ink.top, q.top); ink.bottom = Math.max(ink.bottom, q.bottom); ink.right = Math.max(ink.right, q.right); } }
        ink.height = ink.bottom > ink.top ? ink.bottom - ink.top : 0;
        const tol = Math.max(4, 0.12 * parseFloat(getComputedStyle(el.querySelector('h2,p,li') || el).fontSize));
        const over = Math.max(ink.bottom - box.bottom, box.top - ink.top, 0) * sy;
        const wide = Math.max(ink.right - box.right, 0) * sx;
        if (ink.height > 0 && (over > tol || wide > tol)) found.push({rule: 'text_overflow', where: label,
          detail: `needs ${Math.round(ink.height * sy)}px, has ${Math.round(box.height * sy)}px`, need: Math.round(ink.height * sy), have: Math.round(box.height * sy)});
      }
      if (isImg && (!el.complete || el.naturalWidth === 0)) found.push({rule: 'broken_image', where: el.getAttribute('alt') || 'picture', detail: 'did not load'});
      if (isScene && (el.dataset.error || !el.querySelector('canvas'))) found.push({rule:'broken_image',where:'3D scene',detail:el.dataset.error || 'scene did not render'});
      if (isText || isImg || isChart || isTable || isScene || isPoll) content.push({r, label, el});
      if (isText) {
        for (const node of el.querySelectorAll('h2,p,li')) {
          const txt = (node.innerText || '').trim(); if (!txt) continue;
          const cs = getComputedStyle(node); const fg = lum(cs.color); if (fg === null) continue;
          const nr = node.getBoundingClientRect(); const cx = nr.left + Math.min(nr.width / 2, 12), cy = nr.top + nr.height / 2;
          let bg = null;
          for (const under of document.elementsFromPoint(cx, cy)) {
            if (under === node || node.contains(under)) continue;
            const b = lum(getComputedStyle(under).backgroundColor); if (b !== null) { bg = b; break; }
          }
          if (bg === null) bg = lum(getComputedStyle(stage).backgroundColor);
          if (bg === null) continue;
          const size = parseFloat(cs.fontSize) * sx; const bold = parseInt(cs.fontWeight, 10) >= 700;
          const need = (size >= 24 || (bold && size >= 18.66)) ? 3.0 : 4.5; const got = ratio(fg, bg);
          if (got < need) { found.push({rule: 'contrast', where: txt.slice(0, 60), detail: `${got.toFixed(2)}:1 < ${need}:1`}); break; }
        }
      }
    }
    for (let i = 0; i < content.length; i++) for (let j = i + 1; j < content.length; j++) {
      const a = content[i].r, b = content[j].r;
      if (content[i].el.contains(content[j].el) || content[j].el.contains(content[i].el)) continue;
      const ix = Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)), iy = Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
      const share = (ix * iy) / Math.max(1, Math.min(a.w * a.h, b.w * b.h));
      if (share > %OVERLAP%) found.push({rule: 'overlap', where: `${content[i].label} / ${content[j].label}`, detail: `${Math.round(share * 100)}% of the smaller one`});
    }
    const hasTitle = !!stage.querySelector('.t h2'); const hasChart = content.some(c => c.label === 'chart');
    const hasImage = !!stage.querySelector('img.b');
    const fonts=Array.from(stage.querySelectorAll('.t h2,.t p,.t li,svg text,td,th'))
      .filter(node=>node.textContent.trim()&&node.closest('[data-role]')?.dataset.role!=='footer')
      .map(node=>({text:node.textContent.trim().slice(0,80),size:parseFloat(getComputedStyle(node).fontSize)}))
      .filter(item=>Number.isFinite(item.size));
    out.push({id: section.id.replace(/^s-/, ''), found, hasTitle, hasChart, hasImage, fonts});
  }
  return out;
}
""".replace("%OVERLAP%", str(OVERLAP_SHARE))

def _force_layout(width: int, height: int) -> str:
    """Every slide at its own scene size, unscaled, with every build step shown."""
    return (f".slide{{width:{width}px!important;height:{height}px!important;aspect-ratio:auto!important;margin:0 0 8px 0!important}}"
            ".stage{transform:none!important}.fragment{opacity:1!important;visibility:visible!important;clip-path:none!important}")


def _launch(p: Any, profile_dir: str, size: tuple[int, int] = (1280, 720)) -> Any:
    try:
        context, _ = browser.launch_context(p, profile_dir, headless=True,
                                            viewport={"width": int(size[0]) + 20, "height": int(size[1]) + 40})
    except browser.BrowserUnavailable as error:
        raise PdfUnavailable(f"No Chromium is available for the visual review ({error}).") from error
    return context


def measure(deck: dict[str, Any], *, assets: AssetLookup, png_dir: Optional[Path] = None, document: Optional[str] = None,
            size: Optional[tuple[int, int]] = None) -> list[dict[str, Any]]:
    """Render the deck and return the raw per-slide measurements (and a PNG per slide when ``png_dir`` is given).
    ``document`` is the HTML to measure when the caller has the real preview scene (a template deck: its furniture and
    its own slide size, ``size``); otherwise the standard 1280x720 rendering is built here."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise PdfUnavailable("The playwright package is not installed.") from error
    width, height = (int(size[0]), int(size[1])) if size else (1280, 720)
    if document is None:
        document, _ = render_document(deck, assets=assets, inline=True, mode="stacked")
    document = document.replace("</head>", f"<style>{_force_layout(width, height)}</style></head>", 1)
    with sync_playwright() as p, tempfile.TemporaryDirectory(prefix="cicero-review-") as profile:
        context = _launch(p, profile, (width, height))
        try:
            page = context.new_page()
            page.emulate_media(reduced_motion='reduce')
            page.set_content(document, wait_until="load")
            page.wait_for_timeout(150)
            if page.locator('.scene3d').count():
                page.wait_for_function("Array.from(document.querySelectorAll('.scene3d')).every(el=>el.dataset.ready==='true'||el.dataset.error)",timeout=15000)
            rows = page.evaluate(_PROBE)
            if png_dir is not None:
                png_dir.mkdir(parents=True, exist_ok=True)
                for old in png_dir.glob("slide-*.png"):
                    old.unlink()
                for i, row in enumerate(rows):
                    page.locator("section.slide").nth(i).screenshot(path=str(png_dir / f"slide-{i + 1:02d}.png"))
                    row["png"] = str(png_dir / f"slide-{i + 1:02d}.png")
            return rows
        finally:
            context.close()


def review(deck: dict[str, Any], *, assets: AssetLookup, png_dir: Optional[Path] = None,
           measure_fn: Optional[Callable[..., list[dict[str, Any]]]] = None, document: Optional[str] = None,
           size: Optional[tuple[int, int]] = None) -> dict[str, Any]:
    scene = {"document": document, "size": size} if document is not None else {}
    rows = (measure_fn or measure)(deck, assets=assets, png_dir=png_dir, **scene)
    by_id = {s["id"]: s for s in deck.get("slides", [])}
    slides, counts = [], {"error": 0, "warning": 0}
    for position, row in enumerate(rows, 1):
        slide = by_id.get(row["id"], {})
        findings = [dict(f) for f in row.get("found", [])]
        layout = slide.get("layout", "")
        if (slide.get("title") or "").strip() and not row.get("hasTitle") and layout != "image_full":
            findings.append({"rule": "missing_title", "where": slide.get("title", "")[:60], "detail": "the title is not on the slide"})
        if layout == "chart" and not row.get("hasChart"):
            findings.append({"rule": "missing_chart", "where": layout, "detail": "a chart layout without a chart"})
        if layout == "image_text" and not row.get("hasImage"):
            findings.append({"rule": "missing_image", "where": layout, "detail": "a picture layout without a picture"})
        for f in findings:
            f["severity"] = SEVERITY[f["rule"]]
            f["fix"] = FIXES[f["rule"]]
            f["auto_fix"] = f["rule"] == "text_overflow"
            f.pop("need", None)
            f.pop("have", None)
            counts[f["severity"]] += 1
        entry = {"slide_id": row["id"], "position": position, "title": slide.get("title", ""), "findings": findings}
        if 'fonts' in row:entry['fonts']=row['fonts']
        if row.get("png"):
            entry["png"] = row["png"]
        slides.append(entry)
    return {"ok": counts["error"] == 0, "errors": counts["error"], "warnings": counts["warning"], "slides": slides,
            "rules": sorted(SEVERITY), "measured_in": "browser"}


def shrink_patch(slide: dict[str, Any]) -> Optional[list[dict[str, Any]]]:
    """The slide's blocks with the minimum font size on every text and bullet block that has none (the allowed fix for
    ``text_overflow``); ``None`` when there is nothing left to shrink."""
    changed = False
    blocks = []
    for b in slide.get("blocks") or []:
        b = dict(b)
        if b.get("type") in ("text", "bullets") and (b.get("font_size") or 99) > MIN_FONT:
            b["font_size"] = MIN_FONT
            changed = True
        blocks.append(b)
    return blocks if changed else None


def png_data_uri(path: str) -> str:
    return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")

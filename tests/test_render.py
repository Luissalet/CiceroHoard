"""One geometry engine: layouts, fit, escaping, themes."""
from __future__ import annotations

import re

import pytest

from cicero_hoard import layouts, themes
from cicero_hoard.layouts import build_plan
from cicero_hoard.render import esc, nice_ticks, render_document
from conftest import png_bytes
from sample_deck import S, sample_deck

NO_ASSETS = lambda _id: None  # noqa: E731


def plan_for(slide, theme="claro", lang="es", assets=NO_ASSETS):
    return build_plan(slide, deck_title="Deck", theme=themes.get_theme(theme), number=1, total=3, lang=lang, assets=assets)


@pytest.mark.parametrize("theme", [t["id"] for t in themes.THEMES])
def test_theme_contrast(theme):
    c = themes.get_theme(theme)["colors"]
    for fg in ("text", "muted", "accent", "accent2"):
        assert themes.contrast(c[fg], c["background"]) >= 4.5, (theme, fg)
    for fg in ("text", "muted"):
        assert themes.contrast(c[fg], c["surface"]) >= 4.5, (theme, fg, "surface")


def test_seven_themes_and_unknown_theme():
    assert len(themes.list_themes()) == 7
    assert themes.get_theme("nope")["id"] == "claro"
    with pytest.raises(Exception):
        themes.require_theme("nope")


@pytest.mark.parametrize("theme", [t["id"] for t in themes.THEMES])
def test_every_layout_renders_in_every_theme(theme):
    deck = sample_deck(theme)
    html, plans = render_document(deck, assets=NO_ASSETS)
    assert len(plans) == 11 and html.count("<section") == 11
    assert not [i for i, p in enumerate(plans, 1) if p.overflow], "the sample deck must fit"


def test_no_external_urls_and_no_scripts_injected():
    html, _ = render_document(sample_deck(), assets=NO_ASSETS, mode="present")
    assert not re.search(r"(src|href)\s*=\s*[\"']https?://", html)
    assert "url(http" not in html and "@import" not in html
    assert html.count("<script") == 1


def test_html_is_escaped():
    deck = sample_deck()
    deck["slides"][2]["title"] = "<script>alert(1)</script>"
    deck["slides"][2]["blocks"] = [{"type": "bullets", "items": ["<img src=x onerror=alert(1)>", "a & b"]}]
    deck["slides"][8]["blocks"] = [{"type": "quote", "text": "<b>x</b>", "attribution": "\"><svg onload=1>"}]
    deck["slides"][5]["blocks"][0]["categories"] = ["<i>a</i>", "b", "c"]
    html, _ = render_document(deck, assets=NO_ASSETS)
    assert "<script>alert" not in html and "<img src=x" not in html and "<svg onload" not in html and "<b>x</b>" not in html and "<i>a</i>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html and "a &amp; b" in html
    assert "&lt;trimestral&gt;" in html  # the deck title in <title>


def test_esc():
    assert esc('<a href="x">&\'') == "&lt;a href=&quot;x&quot;&gt;&amp;&#x27;" or "&lt;a" in esc('<a href="x">')
    assert esc(None) == "" and esc(5) == "5"


def test_fit_steps_the_font_down_and_flags_overflow():
    short = S(1, "bullets", "Corto", [{"type": "bullets", "items": ["Uno", "Dos"]}])
    dense = S(2, "bullets", "Denso", [{"type": "bullets", "items": layouts_items(6)}])
    huge = S(3, "bullets", "Enorme", [{"type": "text", "text": "palabra " * 2500}])

    def body_size(plan):
        sizes = [p.size for b in plan.boxes if b.kind == "text" and b.role != "title" for p in b.paras]
        return max(sizes)

    p_short, p_dense, p_huge = plan_for(short), plan_for(dense), plan_for(huge)
    assert body_size(p_short) > body_size(p_dense) >= 16
    assert not p_short.overflow and not p_dense.overflow
    assert p_huge.overflow and p_huge.overflow_where


def layouts_items(n):
    return [f"Esta es la viñeta número {i} con un texto bastante más largo de lo normal para forzar varias líneas de texto" for i in range(n)]


def test_long_title_is_downscaled_not_clipped():
    slide = S(1, "bullets", "Un título extremadamente largo " * 6, [{"type": "bullets", "items": ["a"]}])
    plan = plan_for(slide)
    title = next(b for b in plan.boxes if b.role == "title")
    assert 20 <= title.paras[0].size < 44


def test_boxes_stay_on_the_canvas():
    for slide in sample_deck()["slides"]:
        plan = plan_for(slide)
        for b in plan.boxes:
            assert b.x >= -0.5 and b.y >= -0.5 and b.x + b.w <= 1280.5 and b.y + b.h <= 720.5, (slide["layout"], b.kind, b.x, b.y, b.w, b.h)


def test_number_format_by_language():
    assert layouts.fmt_num(1250000, "es") == "1.250.000"
    assert layouts.fmt_num(4.3, "es") == "4,3" and layouts.fmt_num(4.3, "en") == "4.3"
    assert layouts.fmt_num(1500, "en") == "1500" and layouts.fmt_num(125000, "en") == "125,000"
    assert layouts.fmt_num(38.0, "es") == "38"


def test_nice_ticks():
    ticks = nice_ticks(0, 475)
    assert ticks[0] == 0 and ticks[-1] >= 475 and len(ticks) <= 8
    assert nice_ticks(5, 5)[0] <= 5 <= nice_ticks(5, 5)[-1]


def test_chart_svg_for_each_kind():
    html, _ = render_document(sample_deck(), assets=NO_ASSETS)
    assert html.count("<svg") >= 3 and "Hogar" in html and "Ventas (miles de euros)" in html


def test_single_and_present_modes():
    deck = sample_deck()
    one, plans = render_document(deck, assets=NO_ASSETS, mode="single", only_slide="s3")
    assert one.count("<section") == 1 and len(plans) == 1 and "1.250.000" in one or "1 250 000" in one or "1250000" in one
    present, _ = render_document(deck, assets=NO_ASSETS, mode="present")
    assert 'data-mode="present"' in present and "keydown" in present


def test_images_inline_as_data_uri_or_link(tmp_path):
    deck = sample_deck(image_asset="a1")
    tmp = tmp_path / "a1.png"
    tmp.write_bytes(png_bytes())
    lookup = lambda aid: ({"id": "a1", "mime": "image/png", "path": str(tmp), "width": 64, "height": 48, "filename": "a1.png"} if aid == "a1" else None)  # noqa: E731
    inline, _ = render_document(deck, assets=lookup, inline=True)
    assert "data:image/png;base64," in inline
    linked, _ = render_document(deck, assets=lookup, inline=False)
    assert "data:image" not in linked and "/api/assets/a1" in linked


def test_empty_deck_renders_a_message():
    html, plans = render_document({"id": "d", "title": "Vacío", "language": "es", "theme": "claro", "slides": []}, assets=NO_ASSETS)
    assert plans == [] and "empty" in html


def test_text_estimator_is_monotonic():
    assert layouts.text_width("hola mundo", 20) < layouts.text_width("hola mundo largo", 20) < layouts.text_width("hola mundo largo", 30)
    assert layouts.count_lines("palabra " * 50, 300, 20, "sans", False) > layouts.count_lines("palabra " * 5, 300, 20, "sans", False)

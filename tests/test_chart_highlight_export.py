"""Exported native charts keep what the preview shows."""
from __future__ import annotations

from cicero_hoard import themes


def test_exported_bar_chart_keeps_its_highlight():
    from pptx import Presentation
    from cicero_hoard.layouts import Box
    from cicero_hoard.rich_pptx import add_chart
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    block = {"type": "chart", "chart": "bar", "unit": "M€", "categories": ["A", "B", "C"], "series": [{"name": "S", "values": [4.1, 1.9, 1.4]}], "highlight": [1]}
    add_chart(slide, Box("chart", 10, 10, 600, 300, chart=block), themes.get_theme("claro"), "es")
    chart = next(s for s in slide.shapes if s.has_chart).chart
    fills = [str(p.format.fill.fore_color.rgb) for p in (chart.plots[0].series[0].points[i] for i in range(3))]
    assert fills[0] == fills[2] == "CFD9E0" and fills[1] != "CFD9E0"

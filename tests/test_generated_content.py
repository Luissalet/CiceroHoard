"""What the model writes is repaired into slides that say something: figure-less metrics, rule-made titles."""
from __future__ import annotations

from cicero_hoard import generate, titles
from cicero_hoard.models import GeneratedSlide


def test_metrics_without_figures_become_a_list():
    draft = GeneratedSlide(layout="metrics", title="Métricas para decidir", notes="n", blocks=[{"type": "metrics", "items": [
        {"value": "Entrega", "label": "Productividad y entrega", "detail": "Hitos"}, {"value": "Calidad", "label": "Calidad", "detail": "Incidencias"}]}])
    warnings: list[str] = []
    slide = generate.finish_slide(draft, strict=False, source_ids=set(), reference=set(), warnings=warnings)
    assert slide["blocks"] == [{"type": "bullets", "items": ["Entrega · Productividad y entrega: Hitos", "Calidad: Incidencias"]}]
    assert any("became a list" in w for w in warnings)


def test_rule_titles_skip_wordy_metrics_and_keep_chart_units():
    wordy = {"id": "m", "title": "Métricas", "blocks": [{"type": "metrics", "items": [{"value": "Calidad", "label": "Calidad"}]}]}
    assert titles.rule_proposal(wordy, "es") is None or "Calidad se sitúa" not in titles.rule_proposal(wordy, "es")
    chart = {"id": "c", "title": "Inversión", "blocks": [{"type": "chart", "chart": "bar", "unit": "M€", "categories": ["Aperturas", "Energía"],
                                                          "series": [{"name": "Inversión 2026", "values": [4.1, 1.9]}]}]}
    assert titles.rule_proposal(chart, "es") == "Aperturas tiene el valor más alto de inversión 2026: 4,1 M€"

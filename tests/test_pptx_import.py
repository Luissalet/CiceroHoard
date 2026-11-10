"""An existing PPTX becomes an editable deck: titles, text, tables, native charts, pictures and notes."""
from __future__ import annotations

import io

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

from cicero_hoard.agent_tools import call_tool
from conftest import png_bytes


def sample_pptx(path=None) -> bytes:
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[0])
    s.shapes.title.text = "Plan comercial 2027"
    s.placeholders[1].text = "Comité de dirección"
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Prioridades"
    body = s.placeholders[1].text_frame
    body.text = "Abrir dos tiendas"
    body.add_paragraph().text = "Reducir costes de transporte un 6 %"
    s.notes_slide.notes_text_frame.text = "Empezamos por las prioridades."
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Ventas por región"
    table = s.shapes.add_table(3, 2, Inches(1), Inches(2), Inches(6), Inches(2)).table
    for r, row in enumerate([["Región", "Ventas"], ["Norte", "15,2"], ["Sur", "8,2"]]):
        for c, v in enumerate(row):
            table.cell(r, c).text = v
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Evolución trimestral"
    data = CategoryChartData()
    data.categories = ["T1", "T2", "T3"]
    data.add_series("2026", (10.9, 11.7, 12.4))
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(2), Inches(6), Inches(4), data)
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "La tienda"
    s.shapes.add_picture(io.BytesIO(png_bytes(64, 40)), Inches(1), Inches(2))
    s = prs.slides.add_slide(prs.slide_layouts[1])
    s.shapes.title.text = "Gracias"
    out = io.BytesIO()
    prs.save(out)
    if path:
        path.write_bytes(out.getvalue())
    return out.getvalue()


def test_import_reads_every_kind_of_content(services, tmp_path):
    f = tmp_path / "plan.pptx"
    sample_pptx(f)
    res = call_tool(services, "deck_import_pptx", {"path": str(f), "theme": "oscuro"})
    assert res["imported_slides"] == 6 and res["charts"] == 1 and res["tables"] == 1 and res["images"] == 1
    assert res["title"] == "Plan comercial 2027" and res["theme"] == "oscuro"
    deck = call_tool(services, "deck_get", {"deck_id": res["deck_id"], "detail": "full"})
    slides = deck["slides"] if "slides" in deck else deck["deck"]["slides"]
    layouts = [s["layout"] for s in slides]
    assert layouts == ["title", "bullets", "table", "evidence", "image_full", "closing"]
    assert slides[0]["subtitle"] == "Comité de dirección"
    assert slides[1]["blocks"] == [{"type": "bullets", "items": ["Abrir dos tiendas", "Reducir costes de transporte un 6 %"]}]
    assert slides[1]["notes"] == "Empezamos por las prioridades."
    table = slides[2]["blocks"][0]
    assert table["headers"] == ["Región", "Ventas"] and table["rows"] == [["Norte", "15,2"], ["Sur", "8,2"]]
    chart = slides[3]["blocks"][0]
    assert chart["chart"] == "bar" and chart["categories"] == ["T1", "T2", "T3"] and chart["series"][0]["values"] == [10.9, 11.7, 12.4]
    assert slides[4]["blocks"][0]["type"] == "image"
    check = call_tool(services, "deck_check", {"deck_id": res["deck_id"]})
    issues = check["issues"] if isinstance(check, dict) else check
    assert not [i for i in issues if i["kind"] in ("unsourced_numbers", "unsourced_chart")], issues


def test_import_over_http_and_export_again(client):
    r = client.post("/api/import/pptx", files={"file": ("plan.pptx", sample_pptx(), "application/vnd.openxmlformats-officedocument.presentationml.presentation")},
                    data={"theme": "editorial", "title": "Plan rehecho"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Plan rehecho" and body["deck"]["theme"] == "editorial"
    exported = client.post(f"/api/decks/{body['deck_id']}/export", json={"format": "pptx"})
    assert exported.status_code == 201
    again = Presentation(io.BytesIO(client.get(exported.json()["url"]).content))
    assert len(again.slides) == 6
    assert any(sh.has_chart for sh in again.slides[3].shapes)
    bad = client.post("/api/import/pptx", files={"file": ("x.pptx", b"not a zip", "application/octet-stream")})
    assert bad.status_code == 400 and bad.json()["code"] == "invalid_pptx"


def test_footer_text_boxes_are_not_content(services, tmp_path):
    from pptx.util import Pt
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Ventas"
    s.shapes.add_textbox(Inches(1), Inches(2), Inches(6), Inches(1)).text_frame.text = "Crecen un 9 %"
    for text, left in (("Informe anual", 0.5), ("3 / 10", 8.5)):
        box = s.shapes.add_textbox(Inches(left), prs.slide_height - Inches(0.4), Inches(2), Inches(0.3))
        box.text_frame.text = text
        box.text_frame.paragraphs[0].runs[0].font.size = Pt(10)
    f = tmp_path / "pie.pptx"
    prs.save(f)
    res = call_tool(services, "deck_import_pptx", {"path": str(f)})
    assert res["slides"][0]["blocks"] == ["text"] or res["slides"][0]["blocks"] == ["bullets"]
    deck = call_tool(services, "deck_get", {"deck_id": res["deck_id"], "detail": "full"})
    slide = (deck["slides"] if "slides" in deck else deck["deck"]["slides"])[0]
    assert slide["blocks"][0].get("items", [slide["blocks"][0].get("text")]) == ["Crecen un 9 %"]

"""A deck dict (as the API returns it) with one slide of every layout, used by the render and export tests."""
from __future__ import annotations

from typing import Any

LONG = ["Las ventas del tercer trimestre alcanzaron 1.250.000 euros, un 12% más que el año anterior", "La categoría de hogar aportó el 38% del total de ingresos del periodo",
        "El número de clientes activos llegó a 8.400 y la satisfacción media fue de 4,3 sobre 5", "Se resolvieron 310 incidencias con un tiempo medio de respuesta de dos días",
        "La rotación subió al 9%", "Los costes de transporte aumentaron un 6%"]


def S(i: int, layout: str, title: str, blocks: list | None = None, subtitle: str | None = None, notes: str = "Notas del orador número %d.") -> dict[str, Any]:
    return {"id": f"s{i}", "position": i, "layout": layout, "title": title, "subtitle": subtitle, "blocks": blocks or [], "notes": notes % i if "%d" in notes else notes,
            "status": "draft", "revision": 1, "sources": [], "image_prompt": None, "outline_id": None}


def sample_deck(theme: str = "claro", language: str = "es", image_asset: str | None = None) -> dict[str, Any]:
    image_blocks: list[dict[str, Any]] = [{"type": "bullets", "items": ["Abierta en 2021", "45 empleados", "Tres plantas"]}]
    if image_asset:
        image_blocks.append({"type": "image", "asset_id": image_asset, "caption": "Fachada"})
    slides = [
        S(1, "title", "Revisión trimestral de resultados", [{"type": "text", "text": "Para: Comité de dirección"}], "Tercer trimestre"),
        S(2, "section", "Ventas y clientes", [], "Dónde crecemos"),
        S(3, "bullets", "Las ventas crecieron un 12%", [{"type": "bullets", "items": LONG}]),
        S(4, "bullets", "Título muy largo para comprobar el ajuste automático de la tipografía cuando el texto no cabe en dos líneas de tamaño normal en la diapositiva",
          [{"type": "bullets", "items": LONG}, {"type": "text", "text": "Nota final con un texto corrido que acompaña a las viñetas."}]),
        S(5, "two_column", "Antes y después", [{"type": "columns", "left_title": "Antes", "left": ["Pedidos manuales", "Tres hojas de cálculo"],
                                                "right_title": "Después", "right": ["Pedidos en línea", "Una sola base"]}]),
        S(6, "chart", "Ventas por categoría", [{"type": "chart", "chart": "bar", "title": "Ventas (miles de euros)", "categories": ["Hogar", "Moda", "Deporte"],
                                                "series": [{"name": "2025", "values": [380, 310, 150]}, {"name": "2026", "values": [475, 340, 160]}]},
                                               {"type": "bullets", "items": ["Hogar lidera", "Deporte estable"]}]),
        S(7, "chart", "Evolución mensual", [{"type": "chart", "chart": "line", "title": "Clientes activos", "categories": ["Jul", "Ago", "Sep"],
                                             "series": [{"name": "Clientes", "values": [7900, 8100, 8400]}]}]),
        S(8, "chart", "Reparto de ventas", [{"type": "chart", "chart": "pie", "categories": ["Hogar", "Moda", "Otros"], "series": [{"name": "Ventas", "values": [38, 27, 35]}]}]),
        S(9, "quote", "Voz del cliente", [{"type": "quote", "text": "Encuentro lo que busco sin llamar por teléfono.", "attribution": "Cliente de ejemplo"}]),
        S(10, "image_text", "Tienda Norte", image_blocks),
        S(11, "closing", "Siguientes pasos", [{"type": "bullets", "items": ["Contratar dos personas", "Renegociar el transporte"]}], "Gracias"),
    ]
    return {"id": "deck1", "title": "Revisión <trimestral> & \"cifras\"", "language": language, "theme": theme, "slides": slides}

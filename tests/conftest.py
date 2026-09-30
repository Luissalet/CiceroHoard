from __future__ import annotations

import io
import json
import re
import sys
import threading
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

import pytest

ROOT = Path(__file__).resolve().parent.parent
for entry in (str(ROOT), str(ROOT / "tests")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

warnings.filterwarnings("ignore", category=DeprecationWarning)

from cicero_hoard.config import Config  # noqa: E402
from cicero_hoard.main import create_app  # noqa: E402
from cicero_hoard.services import Services  # noqa: E402

# Words that must never appear in the product, its manifest or its docs (built from fragments so this file does not contain them).
BANNED_WORDS = ("chat" + "gpt", "open" + "ai", "anthro" + "pic", "lm " + "studio", "odys" + "seus", "vitru" + "vius", "gem" + "ini", "co" + "pilot",
                "clau" + "de", "power" + "point", "key" + "note", "can" + "va", "pre" + "zi", "google " + "slides", "micro" + "soft")

T0 = 1_790_000_000.0  # a fixed clock for the tests

SOURCE_TEXT = """# Contexto
La tienda Norte, una empresa ficticia, abrió en 2021 y tiene 45 empleados. Las ventas crecieron un 12% en el tercer trimestre.

# Ventas
Las ventas del trimestre fueron de 1.250.000 euros. Septiembre fue el mejor mes del año. La categoría de hogar aportó el 38% del total.

# Clientes
Los clientes activos llegaron a 8.400. La satisfacción media fue de 4,3 sobre 5. Se resolvieron 310 incidencias.

# Riesgos
La rotación de personal subió al 9%. Los costes de transporte aumentaron un 6%.

# Próximos pasos
Contratar a dos personas. Renegociar el contrato de transporte. Abrir un canal de venta en línea.
"""


@dataclass
class FakeChatResult:
    text: str = "{}"
    model: str = "fake-model"


def outline_json(n: int, title: str = "Tema") -> str:
    items = [{"title": f"{title} inicial", "purpose": "Presentar el tema", "points": ["Quiénes somos", "Qué veremos"], "layout_hint": "title"}]
    for i in range(1, n - 1):
        items.append({"title": f"Sección {i}", "purpose": f"Explicar la sección {i}", "points": [f"Punto {i}.1", f"Punto {i}.2", f"Punto {i}.3"], "layout_hint": None})
    items.append({"title": "Cierre", "purpose": "Recapitular", "points": ["Resumen", "Siguientes pasos"], "layout_hint": "closing"})
    return json.dumps({"items": items}, ensure_ascii=False)


def slide_json(title: str, *, layout: str = "bullets", blocks: Optional[list] = None, sources: Optional[list] = None, notes: str = "Primera frase. Segunda frase. Tercera frase.") -> str:
    return json.dumps({"layout": layout, "title": title, "subtitle": None, "blocks": blocks if blocks is not None else [{"type": "bullets", "items": ["Uno", "Dos", "Tres"]}],
                       "notes": notes, "sources": sources or [], "image_prompt": None}, ensure_ascii=False)


def default_responder(messages: list[dict[str, str]]) -> str:
    user = messages[-1]["content"]
    m = re.search(r"Number of slides: exactly (\d+)", user)
    if m:
        return outline_json(int(m.group(1)))
    t = re.search(r'"title":"([^"]+)"', user)
    return slide_json(t.group(1) if t else "Diapositiva", sources=[1])


class FakeLink:
    """A sync-shaped stand-in for hoard_link.Link.sync: no network. ``responder`` gets the messages and returns the answer text
    (or a list of texts served in order)."""

    def __init__(self, responder: Any = None, available: bool = True):
        self.responder = responder or default_responder
        self.available = available
        self.calls: list[list[dict[str, str]]] = []
        self._i = 0
        self._lock = threading.Lock()

    def chat(self, messages, images=None, **kwargs):
        with self._lock:
            self.calls.append(messages)
            if not self.available:
                raise RuntimeError("no model configured")
            if isinstance(self.responder, list):
                text = self.responder[min(self._i, len(self.responder) - 1)]
                self._i += 1
                return FakeChatResult(text=text)
        text = self.responder(messages)
        return FakeChatResult(text=text)

    def status(self):
        return {"llm": {"state": "resolved" if self.available else "unavailable", "provider": "fake", "model": "fake-model"}}

    def close(self):
        pass


class Recorder:
    """Collects events that would go to the hub bus."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def __call__(self, type_, data):
        self.events.append((type_, data))

    def types(self):
        return [t for t, _ in self.events]


class FakeStudio:
    """Stands in for ImageStudio: returns the given PNG bytes or raises."""

    def __init__(self, data: Optional[bytes] = None, error: Optional[Exception] = None):
        self.data, self.error, self.calls = data, error, []

    def generate(self, prompt, **kw):
        self.calls.append(prompt)
        if self.error:
            raise self.error
        return self.data


def png_bytes(width: int = 64, height: int = 48, color=(200, 30, 60), fmt: str = "PNG") -> bytes:
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buf, format=fmt)
    return buf.getvalue()


def minimal_pdf(text: str) -> bytes:
    """A valid one-page PDF with one line of text (Helvetica), built by hand."""
    esc = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content = f"BT /F1 12 Tf 72 720 Td ({esc}) Tj ET"
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
            f"<< /Length {len(content)} >>\nstream\n{content}\nendstream", "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = b"%PDF-1.4\n"
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{body}\nendobj\n".encode("latin-1")
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    return out


def make_config(tmp_path: Path, **overrides) -> Config:
    base = dict(data_dir=tmp_path / "data", port=0, data_dir_configured=True)
    base.update(overrides)
    return Config(**base)


def make_services(tmp_path: Path, *, link: Any = None, studio: Any = None, pdf_fn: Optional[Callable] = None, **config_overrides) -> Services:
    svc = Services(make_config(tmp_path, **config_overrides), link=link if link is not None else FakeLink(), image_studio=studio or FakeStudio(png_bytes()),
                   emit_fn=Recorder(), clock_fn=lambda: T0, pdf_fn=pdf_fn)
    return svc


@pytest.fixture
def services(tmp_path):
    svc = make_services(tmp_path)
    svc.start()
    yield svc
    svc.stop()


@pytest.fixture
def fallback_services(tmp_path):
    svc = make_services(tmp_path, link=FakeLink(available=False))
    svc.start()
    yield svc
    svc.stop()


@pytest.fixture
def client(tmp_path):
    from fastapi.testclient import TestClient

    svc = make_services(tmp_path)
    app = create_app(svc.config, svc)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.svc = svc
        yield test_client


@pytest.fixture
def fallback_client(tmp_path):
    from fastapi.testclient import TestClient

    svc = make_services(tmp_path, link=FakeLink(available=False))
    app = create_app(svc.config, svc)
    with TestClient(app, base_url="http://127.0.0.1") as test_client:
        test_client.svc = svc
        yield test_client


def new_deck(svc: Services, **kw) -> dict:
    from cicero_hoard import decks
    from cicero_hoard.models import DeckCreate

    data = dict(title="Revisión trimestral", brief="Resultados del tercer trimestre para el comité.", audience="Comité de dirección", slide_count=6)
    data.update(kw)
    return decks.create_deck(svc, DeckCreate(**data))


@pytest.fixture
def deck(services):
    """A deck with one source, an outline (from the fake model) and generated slides."""
    from cicero_hoard import decks, generate

    d = new_deck(services)
    decks.add_source_text(services, d["id"], "Informe interno", SOURCE_TEXT)
    generate.generate_outline(services, d["id"])
    generate.generate_slides(services, d["id"])
    return decks.deck_view(services, d["id"])


@pytest.fixture(autouse=True)
def _one_slide_at_a_time(monkeypatch):
    """Canned answer lists are served in order, so slides are written one by one unless a test asks otherwise."""
    monkeypatch.setenv("CICERO_PARALLEL_SLIDES", "1")

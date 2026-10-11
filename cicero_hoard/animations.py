"""Native slide animations and transitions in the exported .pptx.

The deck keeps an ``animations.json`` beside it (``AnimationStore``); the export applies it to the finished file, so
nothing is regenerated and the HTML/PDF exports are untouched. The OOXML (``<p:timing>`` trees with the format's own
presets, ``<p:transition>`` including Morph) comes from the vendored PPT Master modules.

Settings (deck level, with per-slide overrides under ``slides[<slide id>]``)::

    mode        builds | auto | mixed | none | <effect>      default builds
    trigger     after-previous | on-click                    how the non-staged elements start (default after-previous)
    duration    seconds per element animation                default 0.45
    transition  none | <transition>                          default none
    transition_duration  seconds                             default 0.5

* ``builds``: only the click stages the author gave blocks (``build``/``effect``) become animations, one click per stage.
* ``auto``: every content element animates on entry by what it is -- cover slide zoom, title fade, chart and table wipe,
  picture zoom, cards and text fly in -- and the click stages follow.
* ``mixed``: the title fades, the rest cycle through the native entrance pool.
* ``<effect>``: that effect for every content element (``entrance_*``, ``emphasis_*``, ``exit_*``, ``path_*``).
* ``none``: no animation at all.

Footers and background decorations never animate.
"""

from __future__ import annotations

import io
import json
import re
import tempfile
import zipfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

from lxml import etree

from .vendor.ppt_master import pptx_animations as A
from .vendor.ppt_master import pptx_transitions as T

NS = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
MODES = ("builds", "auto", "mixed", "none")
TRIGGERS = ("after-previous", "on-click")
DEFAULTS: dict[str, Any] = {"mode": "builds", "trigger": "after-previous", "duration": 0.45, "transition": "none",
                            "transition_duration": 0.5, "slides": {}}
BUILD_EFFECTS = {"fade": "entrance_fade", "wipe": "entrance_wipe", "draw": "entrance_wipe", "stages": "entrance_fade"}
AUTO_BY_KIND = {"title": "entrance_fade", "chart": "entrance_wipe", "table": "entrance_wipe", "picture": "entrance_zoom",
                "text": "entrance_fly", "shape": "entrance_fade"}
_STEP = re.compile(r"^Cicero-step:(\d+):(\w+):(\d+)$")


# ------------------------------------------------------------------------------------------------ settings
def catalogue() -> dict[str, Any]:
    effects: dict[str, list[str]] = {}
    for key in A.NATIVE_ANIMATION_KEYS:
        effects.setdefault(key.split("_", 1)[0], []).append(key)
    transitions = list(T.NATIVE_TRANSITION_KEYS)
    return {"modes": list(MODES), "triggers": list(TRIGGERS), "effects": effects, "transitions": ["none", *transitions],
            "defaults": {k: v for k, v in DEFAULTS.items() if k != "slides"}}


def _effect(name: str) -> str:
    try:
        return A.normalize_animation_effect(name)
    except Exception as exc:  # noqa: BLE001 - the vendored module raises plain ValueErrors with good text
        raise ValueError(f"unknown animation effect '{name}': use builds, auto, mixed, none or one of the {len(A.NATIVE_ANIMATION_KEYS)} native effects (see deck_animations action=list)") from exc


def _layer(raw: dict[str, Any], *, top: bool) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if "mode" in raw and raw["mode"] is not None:
        mode = str(raw["mode"]).strip()
        out["mode"] = mode if mode in MODES else _effect(mode)
    if "trigger" in raw and raw["trigger"] is not None:
        if raw["trigger"] not in TRIGGERS:
            raise ValueError(f"trigger must be one of {', '.join(TRIGGERS)}")
        out["trigger"] = raw["trigger"]
    for key, lo, hi in (("duration", 0.05, 10.0), ("transition_duration", 0.05, 10.0)):
        if key in raw and raw[key] is not None:
            value = float(raw[key])
            if not lo <= value <= hi:
                raise ValueError(f"{key} must be between {lo} and {hi} seconds")
            out[key] = value
    if "transition" in raw and raw["transition"] is not None:
        name = str(raw["transition"]).strip()
        if name != "none":
            try:
                name = T.normalize_transition_effect(name, allow_none=False)
            except Exception as exc:  # noqa: BLE001
                raise ValueError(f"unknown transition '{raw['transition']}' (see deck_animations action=list)") from exc
        out["transition"] = name
    unknown = set(raw) - {"mode", "trigger", "duration", "transition", "transition_duration"} - ({"slides"} if top else set())
    if unknown:
        raise ValueError(f"unknown animation setting(s): {', '.join(sorted(unknown))}")
    return out


def normalize(raw: dict[str, Any], slide_ids: Optional[set[str]] = None) -> dict[str, Any]:
    out = {**DEFAULTS, **_layer(raw or {}, top=True), "slides": {}}
    for sid, layer in ((raw or {}).get("slides") or {}).items():
        if slide_ids is not None and sid not in slide_ids:
            raise ValueError(f"slide '{sid}' is not in this deck")
        clean = _layer(layer or {}, top=False)
        if clean:                                            # an all-null layer (every field inherited) is no override
            out["slides"][sid] = clean
    return out


class AnimationStore:
    def __init__(self, data_dir: Path):
        self.dir = Path(data_dir) / "animations"

    def _path(self, deck_id: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", deck_id or ""):
            raise ValueError("bad deck id")
        return self.dir / f"{deck_id}.json"

    def get(self, deck_id: str) -> dict[str, Any]:
        path = self._path(deck_id)
        if path.exists():
            return normalize(json.loads(path.read_text(encoding="utf-8")))
        return normalize({})

    def set(self, deck_id: str, settings: dict[str, Any], slide_ids: Optional[set[str]] = None, *, merge: bool = True) -> dict[str, Any]:
        base = self.get(deck_id) if merge else {}
        raw = {**{k: v for k, v in base.items() if k != "slides"}, **{k: v for k, v in settings.items() if k != "slides"}}
        slides = dict(base.get("slides") or {}) if merge else {}
        for sid, layer in (settings.get("slides") or {}).items():
            if layer:
                slides[sid] = {**slides.get(sid, {}), **layer}
            else:
                slides.pop(sid, None)                       # an empty override removes it
        raw["slides"] = slides
        clean = normalize(raw, slide_ids)
        self.dir.mkdir(parents=True, exist_ok=True)
        self._path(deck_id).write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")
        return clean

    def reset(self, deck_id: str) -> dict[str, Any]:
        path = self._path(deck_id)
        if path.exists():
            path.unlink()
        return normalize({})


# ------------------------------------------------------------------------------------------------ applying
def _kind(el) -> str:
    tag = etree.QName(el).localname
    if tag == "pic":
        return "picture"
    if tag == "graphicFrame":
        uri = (el.xpath(".//a:graphicData/@uri", namespaces=NS) or [""])[0]
        return "chart" if uri.endswith("/chart") else "table" if uri.endswith("/table") else "shape"
    if el.xpath("./p:nvSpPr/p:nvPr/p:ph[@type='title' or @type='ctrTitle']", namespaces=NS):
        return "title"
    if tag == "sp" and el.xpath("./p:txBody//a:t", namespaces=NS):
        return "text"
    return "shape"


def _shapes(root) -> list[dict[str, Any]]:
    out = []
    for el in root.xpath("/p:sld/p:cSld/p:spTree/*[self::p:sp or self::p:pic or self::p:graphicFrame or self::p:grpSp or self::p:cxnSp]",
                         namespaces=NS):
        c = el.xpath("./*[1]/p:cNvPr", namespaces=NS)
        if not c:
            continue
        name = c[0].get("name") or ""
        step = _STEP.match(name) or _STEP.match((c[0].get('descr') or '').split('|')[0])
        kind = _kind(el)
        skip = name in ("Decoration", "Footer") or etree.QName(el).localname == "cxnSp" and not step
        out.append({"id": int(c[0].get("id")), "name": name, "kind": kind, "skip": skip,
                    "stage": int(step.group(1)) if step else None, "build_effect": step.group(2) if step else None,
                    "build_ms": int(step.group(3)) if step else None})
    return out


def plan_slide(shapes: list[dict[str, Any]], cfg: dict[str, Any], *, index: int, offset: int = 0) -> list[dict[str, Any]]:
    """The animation targets of one slide in play order (mapping targets for ``create_sequence_timing_xml``)."""
    mode = cfg["mode"]
    if mode == "none":
        return []
    targets: list[dict[str, Any]] = []
    if mode != "builds":
        free = [s for s in shapes if not s["skip"] and s["stage"] is None]
        free.sort(key=lambda s: 0 if s["kind"] == "title" else 1)   # the title first, then the page in z-order
        for i, s in enumerate(free):
            if mode == "auto":
                effect = "entrance_zoom" if index == 0 else AUTO_BY_KIND.get(s["kind"], "entrance_fade")
            elif mode == "mixed":
                effect = A.pick_animation_effect("mixed", i, offset)
            else:
                effect = mode
            targets.append({"shape_id": s["id"], "delay_ms": 0, "effect": effect, "duration": cfg["duration"],
                            "trigger": cfg["trigger"] if i == 0 or cfg["trigger"] == "on-click" else "after-previous"})
    stages: dict[int, list[dict[str, Any]]] = {}
    for s in shapes:
        if s["stage"] is not None and s["build_effect"] != "none":
            stages.setdefault(s["stage"], []).append(s)
    for stage in sorted(stages):
        for j, s in enumerate(stages[stage]):
            targets.append({"shape_id": s["id"], "delay_ms": 0, "effect": BUILD_EFFECTS.get(s["build_effect"], "entrance_fade"),
                            "duration": max(0.05, (s["build_ms"] or 400) / 1000), "trigger": "on-click" if j == 0 else "with-previous"})
    return targets


def _slide_parts(names: list[str]) -> list[str]:
    parts = [n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
    return sorted(parts, key=lambda n: int(re.search(r"(\d+)\.xml$", n).group(1)))


def _insert_timing(xml: str, timing: str) -> str:
    root = etree.fromstring(xml.encode('utf-8'))
    existing = root.find('p:timing', NS)
    media = [] if existing is None else [deepcopy(n) for n in existing.xpath('.//p:video|.//p:audio', namespaces=NS)]
    if not timing:
        if media:
            return xml
        if existing is not None:
            root.remove(existing)
        return etree.tostring(root,encoding='unicode')
    wrapper = etree.fromstring(('<root xmlns:p="'+NS['p']+'" xmlns:a="'+NS['a']+'" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'+timing+'</root>').encode('utf-8'))
    replacement = wrapper[0]
    target = replacement.find('p:tnLst/p:par/p:cTn/p:childTnLst', NS)
    if media and target is None:
        raise ValueError('Animation timing is missing its root child list.')
    next_id = max([int(v) for v in replacement.xpath('.//p:cTn/@id', namespaces=NS)] or [0]) + 1
    for node in media:
        ids = {}
        for ctn in node.xpath('.//p:cTn', namespaces=NS):
            ids[ctn.get('id')] = str(next_id)
            ctn.set('id', str(next_id)); next_id += 1
        for ref in node.xpath('.//p:tn', namespaces=NS):
            if ref.get('val') in ids:
                ref.set('val',ids[ref.get('val')])
        target.append(node)
    if existing is not None:
        root.replace(existing,replacement)
    else:
        extension=root.find('p:extLst',NS)
        root.insert(list(root).index(extension) if extension is not None else len(root),replacement)
    return etree.tostring(root,encoding='unicode')


def apply(pptx: bytes, settings: dict[str, Any], slide_ids: list[str], *, transitions=None) -> tuple[bytes, dict[str, Any]]:
    """The .pptx with timing and transitions written into every slide, and a per-slide report."""
    cfg = normalize(settings or {})
    src = zipfile.ZipFile(io.BytesIO(pptx))
    parts = _slide_parts(src.namelist())
    report: list[dict[str, Any]] = []
    changed: dict[str, bytes] = {}
    offset = 0
    for index, part in enumerate(parts):
        sid = slide_ids[index] if index < len(slide_ids) else None
        slide_cfg = {**cfg, **(cfg["slides"].get(sid) or {})} if sid else cfg
        xml = src.read(part).decode("utf-8")
        root = etree.fromstring(xml.encode("utf-8"))
        targets = plan_slide(_shapes(root), slide_cfg, index=index, offset=offset)
        offset += len(targets)
        timing = A.create_sequence_timing_xml(targets, duration=slide_cfg["duration"]) if targets else ""
        xml = _insert_timing(xml, timing)
        transition = slide_cfg["transition"]
        explicit = (transitions or {}).get(sid)
        if explicit or transition != "none":
            from .transitions import native_effect
            effect = native_effect(explicit.get('native_effect') or explicit['effect']) if explicit else transition
            duration = explicit['duration_ms']/1000 if explicit else slide_cfg['transition_duration']
            transition = explicit['effect'] if explicit else transition
            xml, _ = T.apply_slide_motion_xml(xml, enter=T.EnterUpdate(policy="replace", effect=effect,duration=duration),
                                              advance=T.AdvanceUpdate(mode="preserve"))
        changed[part] = xml.encode("utf-8")
        report.append({"slide": index + 1, "slide_id": sid, "mode": slide_cfg["mode"], "transition": transition,
                       "animated": len(targets), "clicks": sum(1 for t in targets if t["trigger"] == "on-click"),
                       "effects": sorted({t["effect"] for t in targets})})
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = changed.get(info.filename)
            dst.writestr(info, data if data is not None else src.read(info.filename))
    result = out.getvalue()
    validate(result)
    return result, {"slides": report, "animated": sum(r["animated"] for r in report),
                    "transitions": sum(1 for r in report if r["transition"] != "none")}


def validate(pptx: bytes) -> None:
    """PPT Master's own read-back of every timing tree and transition; raises ValueError with the problems."""
    with tempfile.TemporaryDirectory(prefix="cicero-anim-") as tmp:
        path = Path(tmp) / "deck.pptx"
        path.write_bytes(pptx)
        A.validate_pptx_animation_package(path, require_supported_effects=True)
        T.validate_pptx_transition_package(path)


def read_back(pptx: bytes) -> list[dict[str, Any]]:
    """What a .pptx carries per slide: transition and animation rows (for tests and the tool's dry run)."""
    out = []
    with zipfile.ZipFile(io.BytesIO(pptx)) as z:
        for part in _slide_parts(z.namelist()):
            xml = z.read(part)
            tr = T.read_slide_transition_xml(xml)
            seq = A.read_slide_animation_sequence(xml)
            out.append({"part": part, "transition": getattr(tr, "effect", None),
                        "animations": [getattr(r, "effect", None) for r in getattr(seq, "rows", [])]})
    return out

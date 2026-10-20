"""HTML/CSS/SVG renderer shared by the preview, the standalone HTML export and the PDF export.

Every slide is a 1280 x 720 px stage built from the boxes of :mod:`layouts`; all text is escaped; no external fonts,
scripts or styles are loaded. Charts are drawn here as inline SVG from the block data (nothing is invented: axes
only show the given values on a rounded scale).
"""

from __future__ import annotations

import base64
import html
import json
import math
import re
from pathlib import Path
from typing import Any, Callable, Optional

from .layouts import Box, Para, Plan, W, H, build_plan, fmt_num, is_card
from .themes import COLOR_KEYS, css_font_stack, series_colors, theme_of

AssetLookup = Callable[[str], Optional[dict[str, Any]]]
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")

UI_TEXT = {
    "es": {"slide": "Diapositiva", "of": "de", "empty": "Esta presentación no tiene diapositivas."},
    "en": {"slide": "Slide", "of": "of", "empty": "This presentation has no slides."},
}


def esc(text: Any) -> str:
    return html.escape("" if text is None else str(text), quote=True)


def _hex(value: str) -> str:
    return value if _HEX.match(value or "") else "#000000"


# ---------------- charts ----------------

def nice_ticks(lo: float, hi: float, target: int = 5) -> list[float]:
    if hi <= lo:
        hi = lo + 1
    raw = (hi - lo) / max(1, target)
    mag = 10 ** math.floor(math.log10(raw))
    step = mag
    for m in (1, 2, 2.5, 5, 10):
        step = m * mag
        if raw <= step:
            break
    start = math.floor(lo / step) * step
    end = math.ceil(hi / step) * step
    count = int(round((end - start) / step))
    return [round(start + i * step, 10) for i in range(count + 1)]


def _trunc(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[: max(1, max_chars - 1)] + "…"


def chart_svg(block: dict[str, Any], w: float, h: float, theme: dict[str, Any], lang: str, font: str) -> str:
    rich={'unit','annotations','references','highlight','stacked','zero_baseline','show_values','show_legend'}
    if block.get('chart') not in ('bar','line','pie') or rich.intersection(block) or any(s.get('x_values') for s in block.get('series',[])):
        from .visuals import chart_svg as render_visual
        return render_visual(block,w,h,theme,lang)
    kind = block.get("chart", "bar")
    cats: list[str] = list(block.get("categories") or [])
    series: list[dict[str, Any]] = list(block.get("series") or [])
    colors = series_colors(theme)
    text_c, muted_c = _hex(theme["colors"]["text"]), _hex(theme["colors"]["muted"])
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w:.0f} {h:.0f}" width="{w:.0f}" height="{h:.0f}" role="img" '
             f'aria-label="{esc(block.get("title") or "chart")}" style="font-family:{esc(font)}">']
    if not cats or not series:
        return "".join(parts) + "</svg>"
    n = len(cats)
    values = [[(s.get("values") or [])[i] if i < len(s.get("values") or []) else None for i in range(n)] for s in series]

    if kind == "pie":
        vals = [max(0.0, float(v)) if v is not None else 0.0 for v in values[0]]
        total = sum(vals)
        legend_w = min(w * 0.5, 420)
        r = max(20.0, min(h - 20, w - legend_w - 40) / 2)
        cx, cy = 10 + r, h / 2
        if total > 0:
            ang = -math.pi / 2
            for i, v in enumerate(vals):
                if v <= 0:
                    continue
                frac = v / total
                nxt = ang + frac * 2 * math.pi
                col = colors[i % len(colors)]
                if frac >= 0.9999:
                    parts.append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{col}"/>')
                else:
                    x1, y1 = cx + r * math.cos(ang), cy + r * math.sin(ang)
                    x2, y2 = cx + r * math.cos(nxt), cy + r * math.sin(nxt)
                    large = 1 if frac > 0.5 else 0
                    parts.append(f'<path d="M{cx:.1f},{cy:.1f} L{x1:.1f},{y1:.1f} A{r:.1f},{r:.1f} 0 {large} 1 {x2:.1f},{y2:.1f} Z" '
                                 f'fill="{col}" stroke="{_hex(theme["colors"]["background"])}" stroke-width="2"/>')
                ang = nxt
        lx = 2 * r + 40
        row = min(34.0, (h - 20) / max(1, n))
        fs = 16 if row >= 24 else 13
        for i, c in enumerate(cats):
            y = 14 + i * row
            v = values[0][i]
            label = _trunc(c, int((w - lx - 40) / (fs * 0.5)) - 8)
            parts.append(f'<rect x="{lx:.1f}" y="{y + 2:.1f}" width="{fs}" height="{fs}" rx="2" fill="{colors[i % len(colors)]}"/>')
            parts.append(f'<text x="{lx + fs + 8:.1f}" y="{y + fs:.1f}" font-size="{fs}" fill="{text_c}">{esc(label)}'
                         f'<tspan fill="{muted_c}"> — {esc(fmt_num(v, lang)) if v is not None else "?"}</tspan></text>')
        return "".join(parts) + "</svg>"

    flat = [float(v) for row in values for v in row if v is not None]
    lo, hi = min(flat + [0.0]), max(flat + [0.0])
    ticks = nice_ticks(lo, hi)
    lo, hi = ticks[0], ticks[-1]
    tick_labels = [fmt_num(t, lang) for t in ticks]
    left = max(len(t) for t in tick_labels) * 9 + 18
    legend_h = 30 if len(series) > 1 else 0
    top, bottom, right = 12 + legend_h, 36, 12
    pw, ph = w - left - right, h - top - bottom
    if pw < 40 or ph < 40:
        return "".join(parts) + "</svg>"

    def ypos(v: float) -> float:
        return top + ph - (v - lo) / (hi - lo) * ph

    for t, label in zip(ticks, tick_labels):
        y = ypos(t)
        parts.append(f'<line x1="{left:.1f}" y1="{y:.1f}" x2="{w - right:.1f}" y2="{y:.1f}" stroke="{muted_c}" stroke-opacity="{0.55 if t == 0 else 0.22}" stroke-width="1"/>')
        parts.append(f'<text x="{left - 8:.1f}" y="{y + 5:.1f}" font-size="15" text-anchor="end" fill="{muted_c}">{esc(label)}</text>')
    gw = pw / n
    label_size = 15 if gw >= 70 else 13
    max_chars = max(3, int(gw / (label_size * 0.52)))
    for i, c in enumerate(cats):
        parts.append(f'<text x="{left + gw * (i + 0.5):.1f}" y="{h - 12:.1f}" font-size="{label_size}" text-anchor="middle" fill="{text_c}">{esc(_trunc(c, max_chars))}</text>')
    show_values = n * len(series) <= 14
    m = len(series)
    if kind == "bar":
        bw = gw * 0.72 / m
        for si, row in enumerate(values):
            col = colors[si % len(colors)]
            for i, v in enumerate(row):
                if v is None:
                    continue
                x = left + gw * i + gw * 0.14 + si * bw
                y0, y1 = ypos(0), ypos(float(v))
                parts.append(f'<rect x="{x:.1f}" y="{min(y0, y1):.1f}" width="{bw - 2:.1f}" height="{max(1.0, abs(y1 - y0)):.1f}" rx="2" fill="{col}"/>')
                if show_values:
                    ty = (y1 - 6) if v >= 0 else (y1 + 16)
                    parts.append(f'<text x="{x + (bw - 2) / 2:.1f}" y="{ty:.1f}" font-size="14" text-anchor="middle" fill="{text_c}">{esc(fmt_num(float(v), lang))}</text>')
    else:  # line
        for si, row in enumerate(values):
            col = colors[si % len(colors)]
            pts = [(left + gw * (i + 0.5), ypos(float(v))) for i, v in enumerate(row) if v is not None]
            if len(pts) > 1:
                parts.append(f'<polyline points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="none" stroke="{col}" stroke-width="3" stroke-linejoin="round"/>')
            for i, v in enumerate(row):
                if v is None:
                    continue
                x, y = left + gw * (i + 0.5), ypos(float(v))
                parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="5" fill="{col}"/>')
                if show_values:
                    parts.append(f'<text x="{x:.1f}" y="{y - 10:.1f}" font-size="14" text-anchor="middle" fill="{text_c}">{esc(fmt_num(float(v), lang))}</text>')
    if len(series) > 1:
        lx = left
        for si, s in enumerate(series):
            name = _trunc(s.get("name") or f"#{si + 1}", 24)
            parts.append(f'<rect x="{lx:.1f}" y="8" width="14" height="14" rx="2" fill="{colors[si % len(colors)]}"/>')
            parts.append(f'<text x="{lx + 20:.1f}" y="20" font-size="15" fill="{text_c}">{esc(name)}</text>')
            lx += 20 + len(name) * 8.5 + 22
    return "".join(parts) + "</svg>"


# ---------------- boxes ----------------

def _px(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".") + "px"


def _para_style(p: Para, lang_fonts: dict[str, str]) -> str:
    return (f"font-family:var(--f-{'h' if p.font == 'heading' else 'b'});font-size:{_px(p.size)};line-height:{p.line};"
            f"font-weight:{700 if p.bold else 400};font-style:{'italic' if p.italic else 'normal'};color:var(--{p.color});"
            f"text-align:{p.align};margin:0 0 {_px(p.space_after)}")


def box_html(box: Box, theme: dict[str, Any], lang: str, assets: AssetLookup, src: Callable[[str], str]) -> str:
    geo = f"left:{_px(box.x)};top:{_px(box.y)};width:{_px(box.w)};height:{_px(box.h)}"
    if box.kind=='scene3d':
        from .scene3d import render_data
        return f'<div class="b scene3d" style="{geo}" data-scene="{esc(json.dumps(render_data(box.data,assets)))}" role="img" aria-label="{esc(box.data.get("caption") or "3D scene")}"></div>'
    if box.kind=='poll':
        b=box.data
        choices=''.join(f'<button type="button" aria-pressed="false">{esc(label)} <span>{b.get("results",[])[i] if i<len(b.get("results",[])) else 0}</span></button>' for i,label in enumerate(b.get('options',[])))
        return f'<div class="b poll" style="{geo}" data-poll="{esc(json.dumps(b))}"><h3>{esc(b.get("question", ""))}</h3><div class="poll-options" style="grid-template-columns:repeat({2 if len(b.get("options",[]))>6 else 1},minmax(0,1fr))">{choices}</div><p role="status"></p></div>'
    if box.kind == 'media':
        data = box.data
        kind = data['type']
        attrs = ''.join(' '+name for name in ('controls', 'loop', 'muted') if data.get(name))
        if data.get('autoplay'):
            attrs += ' data-autoplay'
        poster = f' poster="{esc(src(data["poster_id"]))}"' if kind == 'video' and data.get('poster_id') else ''
        track = ''
        if data.get('subtitles'):
            content = base64.b64encode(data['subtitles'].encode('utf-8')).decode('ascii')
            track = f'<track default kind="captions" srclang="{esc(lang)}" src="data:text/vtt;base64,{content}">'
        fallback = f'<img class="b media-poster" style="{geo};object-fit:contain" alt="{esc(data.get("caption") or kind)}" src="{esc(src(data["poster_id"]))}">' if data.get('poster_id') else ''
        return (f'<{kind} class="b slide-media" style="{geo};object-fit:{data.get("fit", "contain")}" '
                f'src="{esc(src(data["asset_id"]))}" preload="metadata" playsinline{attrs}{poster} '
                f'data-start="{data.get("start",0)}" data-end="{data.get("end", "")}" '
                f'data-volume="{data.get("volume",1)}" data-rate="{data.get("playback_rate",1)}" '
                f'aria-label="{esc(data.get("caption") or kind)}">{track}</{kind}>'+fallback)
    if box.kind=='marker':
        return f'<div class="b" style="{geo};background:var(--{box.fill});border-radius:50%"></div>'
    if box.kind=='node':
        return f'<div class="b diagram-node" style="{geo};background:var(--{box.fill});border:1.5px solid var(--accent);border-radius:6px"></div>'
    if box.kind=='connector':
        cw,ch=box.data['canvas'];points=' '.join(f"{p['x']:.2f},{p['y']:.2f}" for p in box.data['points'])
        end=box.data['points'][-1];before=box.data['points'][-2]
        angle=math.atan2(end['y']-before['y'],end['x']-before['x'])
        a=(end['x']-10*math.cos(angle-.45),end['y']-10*math.sin(angle-.45));z=(end['x']-10*math.cos(angle+.45),end['y']-10*math.sin(angle+.45))
        tip=f"{a[0]:.2f},{a[1]:.2f} {end['x']:.2f},{end['y']:.2f} {z[0]:.2f},{z[1]:.2f}"
        return f'<svg class="b" style="{geo};overflow:visible" viewBox="0 0 {cw} {ch}" aria-hidden="true"><polyline points="{points}" fill="none" stroke="{_hex(theme["colors"]["accent"])}" stroke-width="2"/><polygon points="{tip}" fill="{_hex(theme["colors"]["accent"])}"/></svg>'
    if box.kind=='table':
        rows=[box.data['headers'],*box.data['rows']];head=rows[0]
        body=''.join(('<tr style="background:var(--surface)" >' if i in (box.data.get('highlight_rows') or []) else '<tr>')+''.join(f'<td>{esc(cell)}</td>' for cell in row)+'</tr>' for i,row in enumerate(rows[1:]))
        size=max(13,min(box.data.get('font_size') or 24,box.h/len(rows)*.46))
        return f'<div class="b" style="{geo}"><table class="visual-table" style="font-size:{size}px"><thead><tr>'+''.join(f'<th>{esc(cell)}</th>' for cell in head)+f'</tr></thead><tbody>{body}</tbody></table></div>'
    if box.kind in ("rect","rule"):
        radius = f";border-radius:{int(theme['radius'])}px" if theme.get("radius") and is_card(box) else ""
        return f'<div class="b" style="{geo};background:var(--{box.fill or "surface"}){radius}"></div>'
    if box.kind == "image" and box.image:
        position=box.image.get('position',[.5,.5]);fit=box.image.get('fit','contain')
        return f'<img class="b" style="{geo};object-fit:{fit};object-position:{position[0]*100}% {position[1]*100}%" src="{esc(src(box.image["asset_id"]))}" alt="{esc(box.image.get("alt", ""))}">'
    if box.kind == "chart" and box.chart:
        svg = chart_svg(box.chart, box.w, box.h, theme, lang, css_font_stack(theme["fonts"]["body"]))
        scale=box.chart['font_size']/18 if box.chart.get('font_size') else theme.get('chart_font_points',13.5)/13.5
        return f'<div class="b" style="{geo}" data-chart="{esc(json.dumps(box.chart))}" data-chart-id="{esc(box.object_id or "chart")}" data-font-scale="{scale}" data-palette="{esc(json.dumps(theme["colors"]))}">{svg}</div>'
    if box.kind == "text":
        justify = {"top": "flex-start", "middle": "center", "bottom": "flex-end"}.get(box.anchor, "flex-start")
        inner: list[str] = []
        i = 0
        paras = box.paras
        while i < len(paras):
            p = paras[i]
            if p.bullet:
                items = []
                while i < len(paras) and paras[i].bullet:
                    q = paras[i]
                    items.append(f'<li style="{_para_style(q, {})}">{esc(q.text)}</li>')
                    i += 1
                inner.append(f'<ul style="margin:0;padding:0 0 0 {_px(p.indent)}">{"".join(items)}</ul>')
            else:
                tag = "h2" if box.role == "title" else "p"
                inner.append(f'<{tag} style="{_para_style(p, {})}">{esc(p.text)}</{tag}>')
                i += 1
        return f'<div class="b t" data-role="{esc(box.role or "content")}" style="{geo};justify-content:{justify}">{"".join(inner)}</div>'
    return ""


def _theme_vars(theme: dict[str, Any]) -> str:
    colors = "".join(f"--{k}:{_hex(theme['colors'][k])};" for k in COLOR_KEYS)
    return colors + f"--f-h:{css_font_stack(theme['fonts']['heading'])};--f-b:{css_font_stack(theme['fonts']['body'])};"


def slide_section(slide: dict[str, Any], *, deck: dict[str, Any], theme: dict[str, Any], number: int, total: int,
                  assets: AssetLookup, src: Callable[[str], str], index: int) -> tuple[str, Plan]:
    lang = deck.get("language", "es")
    plan = build_plan(slide, deck_title=deck["title"], theme=theme, number=number, total=total, lang=lang, assets=assets, chrome=deck.get("chrome"))
    body = "".join(motion_box_html(b,theme,lang,assets,src) for b in plan.boxes)
    ui = UI_TEXT.get(lang, UI_TEXT["es"])
    label = f'{ui["slide"]} {number} {ui["of"]} {total}: {slide.get("title") or ""}'
    from .transitions import attributes
    return (f'<section class="slide" id="s-{esc(slide["id"])}" data-index="{index}"{attributes(slide)} aria-label="{esc(label.strip())}">'
            f'<div class="stage" style="{esc(_theme_vars(theme))}">{body}</div></section>'), plan


def motion_box_html(box,theme,lang,assets,src):
    content=box_html(box,theme,lang,assets,src)
    if box.object_id:content=content.replace('class="b',f'data-id="{esc(box.object_id)}" class="b',1)
    if box.action:
        action=box.action
        href=action.get('url') if action['kind']=='url' else '#s-'+action['slide_id'] if action['kind']=='slide' else '#'
        label=action.get('label') or ''
        geo=f'position:absolute;left:{_px(box.x)};top:{_px(box.y)};width:{_px(box.w)};height:{_px(box.h)}'
        content=f'<a class="slide-action" style="{geo}" href="{esc(href)}" data-action="{esc(json.dumps(action))}" title="{esc(label)}"'+(' target="_blank" rel="noopener noreferrer"' if action['kind']=='url' else '')+(' aria-label="'+esc(label)+'"' if label else '')+'>'+content+'</a>'
    if box.build is not None and box.build>0 and box.effect!='none':
        effect=box.effect or 'fade'
        return f'<div class="fragment visual-{effect}" data-fragment-index="{box.build-1}" style="position:absolute;inset:0;--motion-duration:{box.duration_ms}ms">{content}</div>'
    return content


CSS = """
*{box-sizing:border-box;margin:0;padding:0}
html{background:#1c1f26;color-scheme:dark}
body{font-family:"Segoe UI",Arial,sans-serif;background:#1c1f26;min-height:100vh}
.deck{padding:24px 16px}
.slide{position:relative;width:min(100%,1280px);aspect-ratio:16/9;margin:0 auto 28px;overflow:hidden;background:#000;box-shadow:0 6px 28px rgba(0,0,0,.45)}
.stage{position:absolute;left:0;top:0;width:1280px;height:720px;transform-origin:0 0;transform:scale(var(--s,1));background:var(--background);color:var(--text);overflow:hidden}
.b{position:absolute}
.scene3d canvas{width:100%;height:100%;display:block;touch-action:none}
.poll{display:flex;flex-direction:column;gap:12px;font-family:var(--f-b);font-size:24px}
.poll h3{font-size:28px}.poll-options{display:grid;gap:8px;flex:1;min-height:0}
.poll button{display:flex;align-items:center;justify-content:space-between;padding:8px 16px;background:var(--surface);color:var(--text);font:inherit;border:1px solid var(--muted);border-radius:4px;cursor:pointer;text-align:left}
.poll button:hover,.poll button[aria-pressed=true]{outline:3px solid var(--accent)}.poll [role=status]{font-size:18px;min-height:24px}
.slide-action{display:block;color:inherit;text-decoration:none}
.slide-action>.b{left:0!important;top:0!important;width:100%!important;height:100%!important;cursor:pointer}
.slide-action:focus-visible{outline:3px solid var(--accent);outline-offset:3px}
.slide-action:hover>.t{text-decoration:underline}
.t{display:flex;flex-direction:column;overflow-wrap:break-word}
.t ul{list-style:disc}
.t li::marker{color:var(--accent)}
.t h2{font-weight:inherit}
.t p,.t h2,.t li{white-space:pre-wrap}
.visual-table{border-collapse:collapse;width:100%;height:100%;font-family:var(--f-b);color:var(--text);table-layout:fixed}
.visual-table th{text-align:left;background:var(--accent);color:white;padding:12px}
.visual-table td{padding:12px;border-bottom:1px solid var(--muted);overflow-wrap:anywhere}
.fragment{opacity:1;visibility:visible}
.media-poster{display:none}
@media(prefers-reduced-motion:reduce){.fragment{transition:none!important;animation:none!important}}
.mode-present{overflow:hidden}
.mode-present .deck{padding:0;height:100vh;display:grid;place-items:center}
.mode-present .slide{display:none;margin:0;width:min(100vw,calc(100vh*16/9));box-shadow:none}
.mode-present .slide.active{display:block}
.mode-single{overflow:hidden}
.mode-single .deck{padding:0;height:100vh;display:grid;place-items:center}
.mode-single .slide{margin:0;width:min(100vw,calc(100vh*16/9));box-shadow:none}
.hud{position:fixed;right:12px;bottom:10px;font:13px "Segoe UI",Arial,sans-serif;color:#c9ced8;background:rgba(0,0,0,.55);padding:3px 9px;border-radius:12px}
.empty{color:#dfe3ea;text-align:center;padding:80px 16px;font:18px "Segoe UI",Arial,sans-serif}
@page{size:13.333in 7.5in;margin:0}
@media print{
html,body{background:#fff!important;margin:0!important;padding:0!important;min-height:0!important}
*{-webkit-print-color-adjust:exact;print-color-adjust:exact}
.deck,.mode-present .deck,.mode-single .deck{display:block!important;padding:0!important;height:auto!important}
.slide,.mode-present .slide,.mode-single .slide{display:block!important;width:13.333in!important;height:7.5in!important;aspect-ratio:auto!important;margin:0!important;box-shadow:none!important;break-after:page;page-break-after:always;overflow:hidden}
.slide:last-child{break-after:auto;page-break-after:auto}
.stage{transform:none!important}
.hud{display:none!important}
.slide-media{display:none!important}.media-poster{display:block!important}
}
"""

SCRIPT = """
(function(){
var mode=document.body.getAttribute('data-mode');
var frames=[].slice.call(document.querySelectorAll('.slide'));
function fit(){frames.forEach(function(f){f.style.setProperty('--s',f.clientWidth/1280);});}
var cur=0,hud=document.getElementById('hud');
function show(i){
  if(!frames.length)return;
  cur=Math.max(0,Math.min(frames.length-1,i));
  if(mode==='present'){frames.forEach(function(f,k){f.classList.toggle('active',k===cur);});fit();}
  else{frames[cur].scrollIntoView({block:'center',behavior:'smooth'});}
  if(hud)hud.textContent=(cur+1)+' / '+frames.length;
  try{history.replaceState(null,'','#'+(cur+1));}catch(e){}
}
function nearest(){var best=0,d=1e9;frames.forEach(function(f,k){var r=f.getBoundingClientRect();var c=Math.abs(r.top+r.height/2-innerHeight/2);if(c<d){d=c;best=k;}});return best;}
addEventListener('resize',fit);
if(mode!=='single'){
addEventListener('keydown',function(e){
  if(e.altKey||e.ctrlKey||e.metaKey)return;
  if(mode!=='present')cur=nearest();
  var k=e.key;
  if(k==='ArrowRight'||k==='ArrowDown'||k==='PageDown'||k===' '||k==='Enter'){e.preventDefault();show(cur+1);}
  else if(k==='ArrowLeft'||k==='ArrowUp'||k==='PageUp'||k==='Backspace'){e.preventDefault();show(cur-1);}
  else if(k==='Home'){e.preventDefault();show(0);}
  else if(k==='End'){e.preventDefault();show(frames.length-1);}
});
if(mode==='present'){addEventListener('click',function(e){show(cur+(e.clientX<innerWidth/3?-1:1));});}
}
var start=parseInt((location.hash||'').slice(1),10);
fit();
if(mode==='present')show(isNaN(start)?0:start-1);
else if(hud)hud.textContent='';
})();
"""

MEDIA_SCRIPT = """
<script>
document.querySelectorAll('.slide-media').forEach(media=>{
  const start=Number(media.dataset.start)||0,end=Number(media.dataset.end)||Infinity;
  const setup=()=>{media.volume=Number(media.dataset.volume);media.playbackRate=Number(media.dataset.rate)||1;
    if(start&&Math.abs(media.currentTime-start)>.05)media.currentTime=start;};
  media.addEventListener('loadedmetadata',setup);
  if(media.readyState>=1)setup();
  media.addEventListener('play',()=>{if(media.currentTime<start||media.currentTime>=end)media.currentTime=start;});
  media.addEventListener('timeupdate',()=>{if(media.currentTime>=end){
    if(media.loop){media.currentTime=start;media.play().catch(()=>{});}else{media.pause();media.currentTime=end;}}});
});
</script>
"""


def _asset_src(assets: AssetLookup, inline: bool) -> Callable[[str], str]:
    def src(asset_id: str) -> str:
        if not inline:
            return f"/api/assets/{asset_id}"
        info = assets(asset_id)
        if not info or not info.get("path"):
            return ""
        try:
            data = Path(info["path"]).read_bytes()
        except OSError:
            return ""
        return f"data:{info['mime']};base64,{base64.b64encode(data).decode('ascii')}"

    return src


def render_document(deck: dict[str, Any], *, assets: AssetLookup, inline: bool = False, mode: str = "stacked",
                    only_slide: Optional[str] = None) -> tuple[str, list[Plan]]:
    """A complete HTML document. ``mode``: ``stacked`` (preview), ``present`` (one slide at a time, keyboard) or ``single``."""
    theme = theme_of(deck)
    lang = deck.get("language", "es")
    slides = deck.get("slides", [])
    if only_slide is not None:
        slides = [s for s in slides if s["id"] == only_slide]
    total_all = len(deck.get("slides", []))
    src = _asset_src(assets, inline)
    sections: list[str] = []
    plans: list[Plan] = []
    for i, slide in enumerate(slides):
        number = deck["slides"].index(slide) + 1 if only_slide is not None else i + 1
        section, plan = slide_section(slide, deck=deck, theme=theme, number=number, total=total_all, assets=assets, src=src, index=i)
        sections.append(section)
        plans.append(plan)
    if not sections:
        sections.append(f'<p class="empty">{esc(UI_TEXT.get(lang, UI_TEXT["es"])["empty"])}</p>')
    hud = '<div class="hud" id="hud" aria-live="polite"></div>' if mode == "present" else ""
    doc = (f'<!doctype html><html lang="{esc(lang)}"><head><meta charset="utf-8">'
           '<meta name="viewport" content="width=device-width, initial-scale=1">'
           f'<title>{esc(deck["title"])}</title><style>{CSS}</style></head>'
           f'<body class="mode-{mode}" data-mode="{mode}"{linked_attributes(deck,inline)}><main class="deck">{"".join(sections)}</main>{hud}'
           f'<script>{SCRIPT}{MEDIA_SCRIPT.removeprefix("\n<script>\n").removesuffix("</script>\n")}</script></body></html>')
    return doc.replace('</body>',advanced_runtime(doc)+'</body>'), plans


def present_document(document: str,width=1280,height=720) -> str:
    """A local, self-contained presentation runtime with staged navigation and reduced motion."""
    root=Path(__file__).resolve().parent/'static/visual-runtime'
    css=(root/'reveal.css').read_text(encoding='utf-8')
    js=(root/'reveal.js').read_text(encoding='utf-8').replace('</script','<\\/script')
    # The renderer's stage coordinates remain the source of truth.
    document=re.sub(r'<script>.*?</script>','',document,flags=re.S)
    document=document.replace('<main class="deck">','<div class="reveal"><div class="slides">').replace('</main>','</div></div>')
    document=document.replace('class="slide"','class="slide"')
    overrides=f'''.reveal .slides{{text-align:left}}.reveal .slides>section{{padding:0;width:{width}px;height:{height}px;margin:0;box-shadow:none;overflow:hidden;aspect-ratio:auto}}
    .reveal .stage{{width:{width}px;height:{height}px;transform:none!important}}
    .reveal .fragment{{transition-duration:var(--motion-duration,400ms)}}
    .reveal .visual-wipe,.reveal .visual-draw{{clip-path:inset(0 100% 0 0)}}
    .reveal .visual-wipe.visible,.reveal .visual-draw.visible{{clip-path:inset(0)}}
    .reveal .progress{{color:#219BC3}}.reveal .controls{{color:#219BC3}}
    .elapsed{{position:fixed;left:12px;bottom:10px;font:14px Arial;color:#657681;z-index:20}}
    @media print{{.fragment{{opacity:1!important;visibility:visible!important;clip-path:none!important}}}}
    @media(prefers-reduced-motion:reduce){{.reveal .fragment{{clip-path:none!important;transition:none!important}}}}
    '''
    start=f'''<script>{js}</script><script>
    const reduced=matchMedia('(prefers-reduced-motion: reduce)').matches;
    const started=Date.now();
    const deck=new Reveal({{width:{width},height:{height},margin:0,center:false,controls:true,progress:true,hash:false,
      transition:reduced?'none':'fade',transitionSpeed:'fast',autoAnimate:!reduced,
      keyboard:{{66:()=>document.body.classList.toggle('blackout')}}}});
    deck.initialize();
    const routeHistory=[];
    async function routeAction(action){{
      const origin=deck.getIndices();
      if(deck.isOverview())deck.toggleOverview(false);
      if(document.body.dataset.sessionControl){{
        const response=await fetch(document.body.dataset.sessionControl,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify(action.kind==='slide'?{{action:'branch',slide_id:action.slide_id}}:{{action:action.kind}})}});
        if(!response.ok)throw Error((await response.json()).error||'Navigation failed');return;
      }}
      if(action.kind==='return'){{const previous=routeHistory.pop();if(previous)deck.slide(previous.h,previous.v,previous.f);return;}}
      if(action.kind==='next'){{deck.next();return;}}if(action.kind==='previous'){{deck.prev();return;}}
      const target=document.getElementById('s-'+action.slide_id);
      if(!target)throw Error(document.documentElement.lang==='es'?'La diapositiva de destino ya no existe.':'The destination slide no longer exists.');
      const index=Array.from(document.querySelectorAll('.reveal .slides>section')).indexOf(target);
      routeHistory.push(origin);deck.slide(index,0,-1);
    }}
    const routeStatus=document.createElement('div');routeStatus.setAttribute('role','alert');routeStatus.style.cssText='position:fixed;top:0;left:0;right:0;padding:12px;background:#a22;color:white;z-index:112;display:none';document.body.append(routeStatus);
    // Capture internal actions before the presentation engine's own hash-link listener.
    document.addEventListener('click',event=>{{const link=event.target.closest('.slide-action');if(!link)return;const action=JSON.parse(link.dataset.action);event.stopImmediatePropagation();if(action.kind==='url')return;event.preventDefault();routeStatus.style.display='none';routeAction(action).catch(error=>{{routeStatus.textContent=error.message;routeStatus.style.display='block';}});}},true);
    deck.on('ready',()=>{{
      try{{const saved=sessionStorage.getItem('cicero-resume:'+location.pathname);
      if(saved){{sessionStorage.removeItem('cicero-resume:'+location.pathname);const p=JSON.parse(saved);deck.slide(p.h,p.v,p.f)}}}}catch{{}}
    }});
    const liveUrl=document.body.dataset.liveUrl;
    if(liveUrl)setInterval(async()=>{{try{{const r=await fetch(liveUrl);if(!r.ok)return;const s=await r.json();
      if(s.content_version!==document.body.dataset.contentVersion){{const i=deck.getIndices();sessionStorage.setItem('cicero-resume:'+location.pathname,JSON.stringify(i));location.reload();}}
    }}catch{{}}}},2000);
    deck.on('slidechanged',event=>{{
      document.querySelectorAll('.slide-media').forEach(media=>{{
        if(!event.currentSlide.contains(media))media.pause();
      }});
      if(!reduced&&event.currentSlide.dataset.transitionDuration){{
        event.currentSlide.style.transitionDuration=Number(event.currentSlide.dataset.transitionDuration)+'ms';
      }}
    }});
    const timer=document.createElement('div');timer.className='elapsed';document.body.append(timer);
    setInterval(()=>{{const s=Math.floor((Date.now()-started)/1000);timer.textContent=String(Math.floor(s/60)).padStart(2,'0')+':'+String(s%60).padStart(2,'0')}},1000);
    </script>'''
    document=document.replace('</head>',f'<style>{css}\n{overrides}\nbody.blackout::after{{content:"";position:fixed;inset:0;background:#000;z-index:100}}</style></head>')
    return document.replace('</body>',start+MEDIA_SCRIPT+advanced_runtime(document)+'</body>')

def advanced_runtime(document):
    if not ('data-scene=' in document or 'data-poll=' in document or re.search(r'&quot;animation&quot;:\s*&quot;(series|points|update)',document)):
        return ''
    file=Path(__file__).resolve().parent/'static/visual-runtime/advanced.js'
    if not file.exists():return ''
    licenses=file.parent/'LICENSES.txt'
    notice='<!-- Bundled runtime licenses\n'+licenses.read_text(encoding='utf-8').replace('--','- -')+'\n-->' if licenses.is_file() else ''
    return notice+'<script>'+file.read_text(encoding='utf-8').replace('</','<\\/')+'</script>'


def linked_attributes(deck, inline):
    if inline or not deck.get('linked_data'):
        return ''
    return (f' data-live-url="/api/decks/{esc(deck["id"])}/data-links/version"'
            f' data-content-version="{esc(deck["content_version"])}"')

"""Optional local office rendering of the exported file, including its actual template."""
from __future__ import annotations

import base64
import hashlib
import html
import json
import os
import shutil
import tempfile
import threading
from functools import lru_cache
from pathlib import Path

from .errors import PdfUnavailable
from .hoard_link import proc

_OFFICE_CLSID = '{91493441-5A91-11CF-8700-00AA0060263B}'
_LOCK = threading.Lock()


def available() -> bool:
    if os.name != 'nt' or not shutil.which('powershell.exe'):
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 'CLSID\\' + _OFFICE_CLSID + '\\LocalServer32'):
            return True
    except OSError:
        return False


@lru_cache(maxsize=1)
def renderer_fingerprint() -> str:
    root=Path(__file__).parent
    paths=[root/name for name in ('native_slides.py','export_pptx.py','rich_pptx.py','template_pptx.py','layouts.py','visual_layout.py','visuals.py','themes.py')]
    paths += [root/'static/visual-runtime/engine.mjs']
    digest=hashlib.sha256()
    for path in paths:
        if path.is_file():digest.update(path.read_bytes())
    return digest.hexdigest()


def cache_key(deck: dict) -> str:
    payload=renderer_fingerprint()+json.dumps(deck, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def cache_folder(data_dir: Path, deck: dict) -> Path:
    return data_dir / 'native-previews' / cache_key(deck)


def layout_findings(report: dict) -> list[dict]:
    """Use native text bounds, not estimates; furniture is excluded from body-size warnings."""
    issues = []
    for slide in report.get('slides', []):
        position = slide['position']
        for shape in slide.get('shapes', []):
            if not shape.get('text'):
                continue
            x, y, w, h = shape['frame']
            bx, by, bw, bh = shape['text_bounds']
            # A point of tolerance allows harmless font overhangs and renderer rounding.
            if bx < x - 2 or by < y - 2 or bx + bw > x + w + 2 or by + bh > y + h + 2:
                issues.append({'position': position, 'kind': 'native_text_overflow', 'severity': 'warning',
                               'message': f"Native text exceeds its frame: {shape['name']}.",
                               'evidence': {'text': shape['text'][:120], 'frame': shape['frame'],
                                            'text_bounds': shape['text_bounds']}})
    return issues


# Paths are process arguments, never interpolated into shell code. Opened documents have no window.
_SCRIPT = r'''
param([string]$InputFile, [string]$OutputFolder)
$ErrorActionPreference = 'Stop'
$nativeType = [Type]::GetTypeFromCLSID([Guid]'{91493441-5A91-11CF-8700-00AA0060263B}')
$nativeApp = [Activator]::CreateInstance($nativeType)
$nativeDeck = $null
try {
    $nativeDeck = $nativeApp.Presentations.Open($InputFile, -1, 0, 0)
    $effectTotal = 0
    $createdEffects = 0
    foreach ($slide in $nativeDeck.Slides) {
        $entries = @()
        foreach ($shape in $slide.Shapes) {
            if ($shape.Name -match '^Cicero-step:(\d+):(fade|wipe|draw|stages):(\d+)$') {
                $entries += @{shape=$shape;step=[int]$Matches[1];effect=$Matches[2];duration=[int]$Matches[3]}
            }
        }
        $previous = -1
        if ($slide.TimeLine.MainSequence.Count -eq 0) {
            foreach ($entry in ($entries | Sort-Object {[int]$_.step})) {
                $trigger = if ($entry.step -eq $previous) {2} else {1}
                $effectId = if ($entry.effect -in @('wipe','draw')) {22} else {10}
                $effect = $slide.TimeLine.MainSequence.AddEffect($entry.shape, $effectId, 0, $trigger)
                $effect.Timing.Duration = $entry.duration / 1000.0
                $previous = $entry.step
                $createdEffects++
            }
        }
        $effectTotal += $slide.TimeLine.MainSequence.Count
    }
    if ($createdEffects -gt 0) {$nativeDeck.SaveAs((Join-Path $OutputFolder 'animated.pptx'),24)}
    $nativeDeck.SaveAs((Join-Path $OutputFolder 'slides.pdf'), 32)
    $records = @()
    foreach ($slide in $nativeDeck.Slides) {
        $slide.Export((Join-Path $OutputFolder ('slide-' + $slide.SlideIndex + '.png')), 'PNG', 1600, [int](1600 * $nativeDeck.PageSetup.SlideHeight / $nativeDeck.PageSetup.SlideWidth))
        $shapes = @()
        foreach ($shape in $slide.Shapes) {
            if ($shape.HasTextFrame -eq -1 -and $shape.TextFrame.HasText -eq -1) {
                $range = $shape.TextFrame.TextRange
                $shapes += @{
                    name = $shape.Name
                    text = $range.Text
                    font_points = $range.Font.Size
                    frame = @($shape.Left, $shape.Top, $shape.Width, $shape.Height)
                    text_bounds = @($range.BoundLeft, $range.BoundTop, $range.BoundWidth, $range.BoundHeight)
                }
            }
        }
        $records += @{position=$slide.SlideIndex; shapes=@($shapes)}
    }
    $report = @{renderer='native_office'; slide_count=$nativeDeck.Slides.Count; slides=@($records); animation_count=$effectTotal; created_animation_count=$createdEffects}
    $report | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $OutputFolder 'report.json') -Encoding UTF8
} finally {
    if ($nativeDeck -ne $null) {$nativeDeck.Close()}
    if ($nativeApp.Presentations.Count -eq 0) {$nativeApp.Quit()}
    [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($nativeApp)
}
'''


def render(pptx: bytes, folder: Path) -> dict:
    if not available():
        raise PdfUnavailable('Template rendering needs an installed local office slide engine on Windows. PPTX export remains available.')
    with _LOCK:
        report_path = folder / 'report.json'
        if report_path.is_file() and (folder / 'slides.pdf').is_file():
            return json.loads(report_path.read_text(encoding='utf-8-sig'))
        folder.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='cicero-native-') as raw:
            stage = Path(raw)
            (stage / 'input.pptx').write_bytes(pptx)
            script = stage / 'render.ps1'
            script.write_text(_SCRIPT, encoding='utf-8-sig')
            try:
                result = proc.run([shutil.which('powershell.exe'), '-NoProfile', '-NonInteractive',
                                   '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                   '-InputFile', str(stage / 'input.pptx'), '-OutputFolder', str(stage)], timeout=120)
            except Exception as error:
                raise PdfUnavailable(f'Native slide rendering failed: {type(error).__name__}.') from error
            if result.returncode or not (stage / 'report.json').is_file() or not (stage / 'slides.pdf').is_file():
                raise PdfUnavailable('The native engine could not open and render the exported presentation. Review the PPTX package.')
            report = json.loads((stage / 'report.json').read_text(encoding='utf-8-sig'))
            count = report.get('slide_count', 0)
            if count < 1 or any(not (stage / f'slide-{n}.png').is_file() for n in range(1, count + 1)):
                raise PdfUnavailable('The native engine returned an incomplete slide preview.')
            folder.mkdir(parents=True, exist_ok=True)
            for path in [stage / 'slides.pdf', *stage.glob('slide-*.png'),*stage.glob('animated.pptx')]:
                shutil.copyfile(path, folder / path.name)
            report_path.write_text(json.dumps(report, ensure_ascii=False), encoding='utf-8')
            return report


def snapshot_html(folder: Path, report: dict, *, title: str, positions: list[int] | None = None,
                  mode: str = 'stacked') -> bytes:
    chosen = positions or list(range(1, report['slide_count'] + 1))
    sections = []
    for index, number in enumerate(chosen):
        raw = base64.b64encode((folder / f'slide-{number}.png').read_bytes()).decode('ascii')
        hidden = ' hidden' if mode == 'present' and index else ''
        sections.append(f'<section{hidden}><img alt="Diapositiva {number}" src="data:image/png;base64,{raw}"></section>')
    script = ''
    if mode == 'present':
        script = """<script>const slides=[...document.querySelectorAll('section')];let current=0;
        document.addEventListener('keydown',event=>{let step=event.key==='ArrowRight'?1:event.key==='ArrowLeft'?-1:0;
        if(!step)return;current=Math.max(0,Math.min(slides.length-1,current+step));
        slides.forEach((slide,i)=>slide.hidden=i!==current);});</script>"""
    document = f'''<!doctype html><html lang="es"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
    <style>body{{margin:0;background:#eceef0}}section{{max-width:1600px;margin:0 auto 16px}}
    section[hidden]{{display:none}}img{{display:block;width:100%;height:auto}}
    @media print{{section{{margin:0;break-after:page}}}}</style></head><body>{''.join(sections)}{script}</body></html>'''
    return document.encode('utf-8')

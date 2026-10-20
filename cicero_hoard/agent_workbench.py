"""Shared tools for object morph, multimedia and durable linked datasets."""
from .hoard_link.agentkit import Tool, ann
from . import transitions, media, data_links, presentation, chrome

TOOLS = [
    Tool('deck_media_control', 'Play/pause, seek, mute or set volume on audio/video in the current live slide.\nZero-based media_index; audience browser applies the command. Unmuted playback may require a browser click.', presentation.MediaControlArgs, ann(False, False, False), presentation.media_control),
    Tool('deck_transitions', 'Get, set or reset default/per-slide transitions, including matched-object morph.\ninspect lists stable block IDs between adjacent slides. HTML and native PPTX; PDF remains static.', transitions.Args, ann(False, False, True), transitions.run),
    Tool('deck_chrome', 'Get, set or reset slide numbering (n, n / total, none) and a progress bar or segments.\nmain_slides excludes an appendix from the total and the progress. Preview, HTML, PPTX and templates.', chrome.Args, ann(False, False, True), chrome.run),
    Tool('media_import', 'Import a local or HTTP(S) audio/video file with duration, stream metadata and automatic video poster.\nReturns asset_id for typed audio/video blocks; originals are preserved.', media.ImportArgs, ann(False, False, True), media.import_media, timeout_s=180),
    Tool('media_get', 'Inspect imported audio/video, duration, codec, poster, provenance and playback URL. No content is changed.', media.GetArgs, ann(True), media.inspect),
    Tool('dataset_link', 'Link local CSV/TSV/XLSX or HTTP(S) tabular data and start periodic refresh.\nKeeps immutable snapshots and the last good version on failure. Returns link_id and source_id.', data_links.LinkArgs, ann(False, False, True), data_links.create, timeout_s=120),
    Tool('dataset_links', 'Inspect linked data, refresh schedule, snapshot, recipe mappings and errors. No content is changed.', data_links.RefArgs, ann(True), data_links.inspect),
    Tool('dataset_link_control', 'Refresh, pause, resume or unlink one/all linked datasets in a deck.\nUnlink preserves sources and rendered visuals; refresh updates bound blocks without replacing notes or layout.', data_links.ControlArgs, ann(False, False, True), data_links.control, timeout_s=180),
    Tool('dataset_bind', 'Bind linked data to a chart/table using a typed mapping and optional transform recipe.\nUpdates by stable block ID; preserves notes/layout; reports manual data edits as conflicts.', data_links.BindArgs, ann(False, False, True), data_links.bind, timeout_s=120),
]

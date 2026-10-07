"""Local, headless MCP access to VectorCraft and DesignCraft.

The raw bridge deliberately returns the complete tool catalogue and tool results;
it does not maintain a second, lossy allow-list of an installed app's MCP API.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any
from concurrent.futures import ThreadPoolExecutor

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError


def _run(coroutine):
    """Sync API callers and direct async MCP callbacks share the same bridge."""
    try:asyncio.get_running_loop()
    except RuntimeError:return asyncio.run(coroutine)
    with ThreadPoolExecutor(max_workers=1) as worker:
        return worker.submit(asyncio.run,coroutine).result()


def _exe(svc: Any, app: str) -> tuple[Path, list[str]]:
    if app not in {"vectorcraft", "designcraft"}:
        raise ValueError("app must be vectorcraft or designcraft")
    configured = getattr(svc.config, f"{app}_cli", "") or os.environ.get(f"CICERO_{app.upper()}_CLI", "")
    if not configured:
        settings=Path(svc.config.data_dir)/'craft-engines.json'
        if settings.is_file():configured=json.loads(settings.read_text(encoding='utf-8')).get(app,{}).get('executable','')
    if not configured:
        raise RuntimeError(f"Configure CICERO_{app.upper()}_CLI with the local executable path.")
    path = Path(configured).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"{app} executable is not available at {path}")
    return path, (["mcp", "--headless"] if app == "vectorcraft" else ["mcp"])


async def _request(svc: Any, app: str, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    executable, args = _exe(svc, app)
    run_root = Path(svc.config.data_dir) / "craft-runs" / app
    appdata, localdata = run_root / "appdata", run_root / "localappdata"
    appdata.mkdir(parents=True, exist_ok=True)
    localdata.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env.update({"APPDATA": str(appdata), "LOCALAPPDATA": str(localdata)})
    params = StdioServerParameters(command=str(executable), args=args, env=env,cwd=str(run_root))
    results: list[dict[str, Any]] = []
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for call in calls:
                name = str(call.get("name", ""))
                arguments = call.get("arguments", {})
                if not name or not isinstance(arguments, dict):
                    raise ValueError("Each call needs a tool name and an arguments object.")
                kind = call.get("kind", "tool")
                if kind == "tool":
                    result = await session.call_tool(name, arguments)
                    results.append({"kind": kind, "name": name, "is_error": bool(result.isError),
                                    "result": _serialize(result)})
                elif kind == "prompt":
                    results.append({"kind": kind, "name": name, "result": _serialize(await session.get_prompt(name, arguments))})
                elif kind == "resource":
                    uri = str(arguments.get("uri", name))
                    results.append({"kind": kind, "name": uri, "result": _serialize(await session.read_resource(uri))})
                else:
                    raise ValueError("MCP call kind must be tool, prompt, or resource.")
    return results


def discover(svc: Any, app: str) -> dict[str, Any]:
    async def run() -> dict[str, Any]:
        executable, args = _exe(svc, app)
        root = Path(svc.config.data_dir) / "craft-runs" / app
        root.mkdir(parents=True, exist_ok=True)
        env = dict(os.environ, APPDATA=str(root / "appdata"), LOCALAPPDATA=str(root / "localappdata"))
        params = StdioServerParameters(command=str(executable), args=args, env=env,cwd=str(root))
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                prompts = await _optional_list(session.list_prompts, "prompts")
                resources = await _optional_list(session.list_resources, "resources")
                templates = await _optional_list(session.list_resource_templates, "resourceTemplates")
                return {"app": app, "executable": str(executable), "tools": _serialize(tools.tools),
                        "prompts": _serialize(prompts), "resources": _serialize(resources),
                        "resource_templates": _serialize(templates)}
    return _run(run())


def call(svc: Any, app: str, calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {"app": app, "results": _run(_request(svc, app, calls))}


def _serialize(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None: return value
    if isinstance(value, bytes): return value.hex()
    if isinstance(value, (list, tuple)): return [_serialize(item) for item in value]
    if isinstance(value, dict): return {str(key): _serialize(item) for key, item in value.items()}
    if getattr(value, "type", "") == "image":
        return {"type": "image", "mimeType": value.mimeType, "data": value.data}
    if hasattr(value, "model_dump"): return _serialize(value.model_dump(mode="json"))
    if hasattr(value, "__dict__"): return _serialize(vars(value))
    return str(value)


async def _optional_list(request: Any, member: str) -> list[Any]:
    try:
        result = await request()
        return list(getattr(result, member, []) or [])
    except McpError as error:
        if error.error.code == -32601: return []  # the server implements tools only
        raise


def create_handout(svc: Any, deck: dict[str, Any]) -> dict[str, Any]:
    """Create a deterministic, editable A4 DesignCraft handout and page previews."""
    export_dir = Path(svc.config.data_dir) / "craft-runs" / "designcraft"
    export_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{re.sub(r'[^A-Za-z0-9_-]+', '-', deck['title']).strip('-')[:40] or 'presentation'}-{deck['id']}-{uuid.uuid4().hex[:8]}"
    native = export_dir / f"{stem}.designcraft"
    slides = sorted(deck.get("slides", []), key=lambda s: s.get("position", 0))
    if not slides:
        raise ValueError("Add slides before creating a DesignCraft handout.")
    pages = max(1, len(slides))
    calls: list[dict[str, Any]] = [{"name": "new_document", "arguments": {"title": deck["title"], "preset": "A4", "pages": pages, "margins": 36, "facingPages": False}}]
    for index, slide in enumerate(slides):
        body = _slide_text(slide, include_title=False)
        # Separate editable heading and body frames create a clear hierarchy;
        # the command targets each spread directly and works headless.
        calls.extend([
            {"name": "execute", "arguments": {"command": "frame.create", "params": {
                "spread": index, "rect": [48, 48, 547, 132], "content": "text", "text": slide.get("title", "")[:1000]}}},
            {"name": "execute", "arguments": {"command": "frame.create", "params": {
                "spread": index, "rect": [48, 150, 547, 794], "content": "text", "text": body[:12000]}}},
        ])
    previews = [export_dir / f"{stem}-page-{index + 1}.png" for index in range(pages)]
    calls.append({"name": "save_document", "arguments": {"path": str(native)}})
    calls.extend({"name": "render_page", "arguments": {"page": index, "path": str(path), "scale": 1}}
                 for index, path in enumerate(previews))
    calls.append({"name": "inspect_document", "arguments": {}})
    result = call(svc, "designcraft", calls)
    failed = [r for r in result["results"] if r["is_error"]]
    if failed:
        raise RuntimeError(f"DesignCraft failed at {failed[0]['name']}: {failed[0]['result']}")
    if not native.is_file() or not all(path.is_file() and path.stat().st_size > 1000 for path in previews):
        raise RuntimeError("DesignCraft did not produce the editable document and rendered previews for every page.")
    inspection = next((r.get("result", {}).get("content", [{}])[0].get("text", "{}") for r in reversed(result["results"])
                       if r["name"] == "inspect_document" and r.get("result", {}).get("content")
                       and r["result"]["content"][0].get("type") == "text"), "{}")
    try: inspected = json.loads(inspection)
    except (TypeError, ValueError): inspected = {}
    if inspected.get("pageCount") != pages:
        raise RuntimeError(f"DesignCraft produced {inspected.get('pageCount')} pages, expected {pages}.")
    compact = {"pageCount": inspected.get("pageCount"),
               "stories": [{"id": story.get("id"), "preview": story.get("preview"), "overset": story.get("overset")}
                           for story in inspected.get("stories", [])]}
    from . import decks as store
    editable_export = store.add_export(svc, deck["id"], "designcraft", native.read_bytes(), deck["title"] + " handout")
    editable_path, _ = store.export_file(svc, editable_export["id"])
    image_exports = [store.add_export(svc, deck["id"], "png", path.read_bytes(), f"{deck['title']} handout page {index + 1}")
                     for index, path in enumerate(previews)]
    image_files = [store.export_file(svc, item["id"])[0] for item in image_exports]
    return {"path": str(editable_path), "url": editable_export["url"],
            "preview_path": str(image_files[0]), "preview_url": image_exports[0]["url"],
            "preview_paths": [str(path) for path in image_files], "preview_urls": [item["url"] for item in image_exports],
            "pages": pages, "editable": True, "preview_format": "png", "inspection": compact,
            "overset_text_frames": sum(bool(story.get("overset")) for story in compact["stories"])}


def create_vector_figure(svc: Any, deck_id: str, slide_id: str, *, shape: str = "star", title: str = "Vector figure",
                         fill: str = "#d59b32", stroke: str = "#162f43",replace_block_index: int | None=None) -> dict[str, Any]:
    """Use VectorCraft to create SVG/native/PNG files, then add the SVG to a slide."""
    if shape not in {"star", "rectangle", "ellipse", "triangle", "polygon"}:
        raise ValueError("shape must be one of: star, rectangle, ellipse, triangle, polygon")
    from . import decks
    existing_slide = decks.get_slide(svc, deck_id, slide_id)
    if replace_block_index is None and len(existing_slide["blocks"]) >= 8:
        raise ValueError("The slide already has the maximum number of content blocks.")
    if replace_block_index is not None and (not 0<=replace_block_index<len(existing_slide['blocks']) or existing_slide['blocks'][replace_block_index].get('type')!='image'):
        raise ValueError('replace_block_index must select an existing image block.')
    root = Path(svc.config.data_dir) / "craft-runs" / "vectorcraft"
    root.mkdir(parents=True, exist_ok=True)
    stem = re.sub(r"[^A-Za-z0-9_-]+", "-", title).strip("-")[:40] or "figure"
    native, svg, png = root / f"{stem}-{deck_id}-{slide_id}.vectorcraft", root / f"{stem}-{deck_id}-{slide_id}.svg", root / f"{stem}-{deck_id}-{slide_id}.png"
    if shape == "star":
        draw = {"shape": shape, "cx": 256, "cy": 192, "radius1": 130, "radius2": 65, "points": 7, "fill": fill, "stroke": stroke, "strokeWidth": 5}
    elif shape in {'triangle','polygon'}:
        draw={'shape':'polygon','cx':256,'cy':192,'radius':130,'sides':3 if shape=='triangle' else 6,'fill':fill,'stroke':stroke,'strokeWidth':5}
    else:
        draw = {"shape": shape, "x":136,"y":102,"width":240,"height":180,"fill":fill,"stroke":stroke,"strokeWidth":5}
    calls = [
        {"name": "run_command", "arguments": {"command": "file.new", "params": {"width": 512, "height": 384}}},
        {"name": "draw_shape", "arguments": draw},
        {"name": "export", "arguments": {"path": str(native), "format": "vectorcraft"}},
        {"name": "export", "arguments": {"path": str(svg), "format": "svg"}},
        {"name": "export", "arguments": {"path": str(png), "format": "png"}},
    ]
    result = call(svc, "vectorcraft", calls)
    failed = [r for r in result["results"] if r["is_error"]]
    if failed: raise RuntimeError(f"VectorCraft failed at {failed[0]['name']}: {failed[0]['result']}")
    if not all(path.is_file() and path.stat().st_size > 100 for path in (native, svg, png)):
        raise RuntimeError("VectorCraft did not produce a complete editable graphic and its previews.")
    asset = decks.add_svg_asset(svc, deck_id, svg.read_bytes(), native.name,
                                fallback_png=png.read_bytes(), native_data=native.read_bytes())
    asset_path = Path(svc.config.assets_dir) / f"{asset['asset_id']}.svg"
    slide = decks.get_slide(svc, deck_id, slide_id)
    blocks = list(slide["blocks"])
    figure={"type":"image","asset_id":asset['asset_id'],"caption":title}
    if replace_block_index is None:blocks.append(figure)
    else:blocks[replace_block_index]={**blocks[replace_block_index],**figure}
    decks.patch_slide(svc, deck_id, slide_id, {"blocks": blocks}, reason="vectorcraft figure added")
    return {"asset_id": asset["asset_id"], "slide_id": slide_id, "block_index":len(blocks)-1 if replace_block_index is None else replace_block_index,
            "replaced":replace_block_index is not None,"native_path": str(asset_path.with_suffix(".vectorcraft")),
            "native_url": f"/api/assets/{asset['asset_id']}/native", "svg_path": str(asset_path),
            "svg_url": f"/api/assets/{asset['asset_id']}", "preview_path": str(asset_path.with_suffix(".png")),
            "preview_url": f"/api/assets/{asset['asset_id']}/preview", "editable": True,
            "pptx_contains_svg": True}


def _slide_text(slide: dict[str, Any], *, include_title: bool = True) -> str:
    lines = [slide.get("title", "")] if include_title else []
    if slide.get("subtitle"):
        lines.append(slide["subtitle"])
    for block in slide.get("blocks", []):
        kind = block.get("type")
        if kind == "bullets": lines.extend(f"• {x}" for x in block.get("items", []))
        elif kind == "text": lines.append(block.get("text", ""))
        elif kind == "quote": lines.append(f"“{block.get('text', '')}”" + (f" — {block['attribution']}" if block.get("attribution") else ""))
        elif kind == "columns": lines.extend([block.get("left_title") or "", *block.get("left", []), block.get("right_title") or "", *block.get("right", [])])
        elif kind == "chart":
            lines.append(block.get("title") or "")
            for series in block.get("series", []): lines.append(f"{series.get('name', '')}: " + ", ".join(map(str, series.get("values", []))))
        elif kind == "image": lines.append(block.get("caption") or "[Figure]")
    if slide.get("notes"): lines.extend(["", "Speaker notes", slide["notes"]])
    return "\n".join(x for x in lines if x)

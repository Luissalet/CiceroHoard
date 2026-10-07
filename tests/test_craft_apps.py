"""Real local craft-app integration tests; they never start a model or touch user libraries."""
from __future__ import annotations

import zipfile
import os
from pathlib import Path

import pytest

from cicero_hoard import decks
from cicero_hoard.agent_tools import call_tool, tool_catalog
from cicero_hoard.models import DeckCreate


VECTOR = Path(os.environ.get("CICERO_VECTORCRAFT_CLI", ""))
DESIGN = Path(os.environ.get("CICERO_DESIGNCRAFT_CLI", ""))


@pytest.mark.skipif(not VECTOR.is_file(), reason="set CICERO_VECTORCRAFT_CLI for actual async MCP callback")
def test_sync_native_bridge_is_usable_from_an_async_mcp_callback(services):
    import asyncio
    services.config.vectorcraft_cli=str(VECTOR)
    async def callback():
        result=call_tool(services,'craft_discover',{'app':'vectorcraft'})
        assert len(result['tools'])==25
    asyncio.run(callback())


@pytest.mark.skipif(not VECTOR.is_file(), reason="set CICERO_VECTORCRAFT_CLI to run the local VectorCraft integration test")
def test_real_vectorcraft_svg_becomes_slide_figure_and_pptx_svg(client):
    services = client.svc
    services.config.vectorcraft_cli = str(VECTOR)
    deck = decks.create_deck(services, DeckCreate(title="Local vector integration", slide_count=3))
    slide = decks.add_slide(services, deck["id"], title="Native vector")
    catalog = {tool["name"] for tool in tool_catalog()}
    assert {"craft_discover", "craft_call", "vector_figure_create", "deck_handout_designcraft"} <= catalog
    discovery = call_tool(services, "craft_discover", {"app": "vectorcraft"})
    assert {"draw_shape", "export", "inspect_document"} <= {item["name"] for item in discovery["tools"]}
    assert {"prompts", "resources", "resource_templates"} <= discovery.keys()
    raw = call_tool(services, "craft_call", {"app": "vectorcraft", "calls": [
        {"name": "run_command", "arguments": {"command": "file.new", "params": {"width": 100, "height": 100}}},
        {"name": "draw_shape", "arguments": {"shape": "star", "cx": 50, "cy": 50, "radius1": 30, "radius2": 14, "points": 5}},
    ]})
    assert [item["name"] for item in raw["results"]] == ["run_command", "draw_shape"]
    assert all(not item["is_error"] for item in raw["results"])
    result = call_tool(services, "vector_figure_create", {"deck_id": deck["id"], "slide_id": slide["id"], "title": "Editable star"})
    assert Path(result["native_path"]).is_file() and Path(result["svg_path"]).is_file() and Path(result["preview_path"]).is_file()
    assert result['native_editable'] and not result['pptx_native_shapes']
    assert result['pptx_embedding']=='svg_picture_with_png_fallback'
    assert client.get(result["native_url"]).status_code == 200
    assert client.get(result["svg_url"]).headers["content-type"].startswith("image/svg+xml")
    assert client.get(result["preview_url"]).headers["content-type"].startswith("image/png")
    assert decks.get_slide(services, deck["id"], slide["id"])["blocks"][-1]["asset_id"] == result["asset_id"]
    exported = services.export(deck["id"], "pptx")
    export_path, _ = decks.export_file(services, exported["id"])
    with zipfile.ZipFile(export_path) as package:
        names = package.namelist()
        svg_name = next(name for name in names if name.startswith("ppt/media/") and name.endswith(".svg"))
        assert b"svgBlip" in package.read("ppt/slides/slide1.xml")
        assert b"<svg" in package.read(svg_name)


@pytest.mark.skipif(not VECTOR.is_file(), reason="set CICERO_VECTORCRAFT_CLI for native geometry tests")
@pytest.mark.parametrize('shape',['rectangle','ellipse','triangle','polygon'])
def test_native_vector_shapes_replace_one_block_and_preserve_slide_context(services,shape):
    from PIL import Image
    services.config.vectorcraft_cli=str(VECTOR)
    deck=decks.create_deck(services,DeckCreate(title='Geometry proof',slide_count=3))
    slide=decks.add_slide(services,deck['id'],title='Heading retained',blocks=[{'type':'text','text':'Body retained'}],notes='Speaker note retained')
    original=call_tool(services,'vector_figure_create',{'deck_id':deck['id'],'slide_id':slide['id'],'title':'Original star'})
    changed=call_tool(services,'vector_figure_create',{'deck_id':deck['id'],'slide_id':slide['id'],'title':shape,'shape':shape,'fill':'#0077bb','replace_block_index':original['block_index']})
    after=decks.get_slide(services,deck['id'],slide['id'])
    assert len(after['blocks'])==2 and after['blocks'][0]['text']=='Body retained'
    assert after['title']=='Heading retained' and after['notes']=='Speaker note retained'
    assert changed['replaced'] and after['blocks'][1]['asset_id']==changed['asset_id']
    with Image.open(changed['preview_path']) as png:
        assert png.size==(512,384)
        box=png.convert('RGBA').getchannel('A').getbbox()
        assert box and box[0]>100 and box[1]>30 and box[2]<410 and box[3]<350
    assert Path(original['native_path']).is_file() and Path(changed['native_path']).is_file()


@pytest.mark.skipif(not DESIGN.is_file(), reason="set CICERO_DESIGNCRAFT_CLI to run the local DesignCraft integration test")
def test_real_designcraft_handout_contains_deck_text_and_rendered_preview(services):
    services.config.designcraft_cli = str(DESIGN)
    deck = decks.create_deck(services, DeckCreate(title="Handout source title", slide_count=3))
    slide = decks.add_slide(services, deck["id"], title="Distinctive slide heading",
                            blocks=[{"type": "bullets", "items": ["First retained point", "Second retained point"]}],
                            notes="Speaker note carried into the handout")
    decks.add_slide(services, deck["id"], title="Second page proof", blocks=[{"type": "text", "text": "Second page body copy"}])
    result = call_tool(services, "deck_handout_designcraft", {"deck_id": deck["id"]})
    native, preview = Path(result["path"]), Path(result["preview_path"])
    assert native.suffix == ".designcraft" and native.is_file()
    assert preview.suffix == ".png" and preview.is_file() and preview.stat().st_size > 1000
    assert result["editable"] is True and result["pages"] == 2 and len(result["preview_paths"]) == 2
    assert result['image_transfer']=='embedded_raster_frames' and result['images_transferred']==[]
    assert result['portable_copy_verified'] and result['chart_transfer']=='text_values'
    assert result["url"].startswith("/api/exports/") and len(result["preview_urls"]) == 2
    assert result["overset_text_frames"] == 0
    rendered_content = " ".join(story["preview"] or "" for story in result["inspection"]["stories"])
    assert "Distinctive slide heading" in rendered_content and "First retained point" in rendered_content
    assert "Second page proof" in rendered_content and "Second page body copy" in rendered_content


@pytest.mark.skipif(not DESIGN.is_file(), reason="set CICERO_DESIGNCRAFT_CLI to run the local DesignCraft image integration test")
def test_designcraft_handout_embeds_raster_and_svg_fallback_in_reopenable_project(services):
    import io
    from PIL import Image

    services.config.designcraft_cli = str(DESIGN)
    deck = decks.create_deck(services, DeckCreate(title="Image handout proof", slide_count=3))
    raster = Image.new("RGB", (240, 120), "#da3f2b")
    raster_buf = io.BytesIO(); raster.save(raster_buf, format="PNG")
    raster_asset = decks.add_asset(services, deck["id"], raster_buf.getvalue(), "real-photo.png")
    fallback = Image.new("RGB", (120, 180), "#235eb5")
    fallback_buf = io.BytesIO(); fallback.save(fallback_buf, format="PNG")
    vector = b'<svg xmlns="http://www.w3.org/2000/svg" width="120" height="180" viewBox="0 0 120 180"><rect width="120" height="180" fill="#235eb5"/></svg>'
    svg_asset = decks.add_svg_asset(services, deck["id"], vector, "figure.svg", fallback_png=fallback_buf.getvalue())
    slide = decks.add_slide(services, deck["id"], title="Raster and vector source",
                            blocks=[{"type": "text", "text": "Text remains editable alongside the figures."},
                                    {"type": "image", "asset_id": raster_asset["asset_id"], "caption": "Original raster photo"},
                                    {"type": "image", "asset_id": svg_asset["asset_id"], "caption": "SVG source with PNG fallback"}],
                            notes="Speaker notes remain in the editable handout.")
    result = call_tool(services, "deck_handout_designcraft", {"deck_id": deck["id"]})
    native, preview = Path(result["path"]), Path(result["preview_path"])
    assert native.is_file() and native.suffix == ".designcraft"
    assert result["portable_copy_verified"] is True
    assert result["image_transfer"] == "embedded_raster_frames"
    assert [item["source"] for item in result["images_transferred"]] == ["raster", "svg_png_fallback"]
    assert [item["caption"] for item in result["images_transferred"]] == ["Original raster photo", "SVG source with PNG fallback"]
    assert result["overset_text_frames"] == 0
    text = " ".join(story["preview"] or "" for story in result["inspection"]["stories"])
    assert "Text remains editable" in text
    with zipfile.ZipFile(native) as package:
        document = __import__("json").loads(package.read("document.json"))
        stories = list(document["stories"].values())
        assert any("Speaker notes remain in the editable handout." in story["text"] for story in stories)
        graphics = [item for spread in document["spreads"] for item in spread["items"]
                    if item.get("content", {}).get("type") == "graphic"]
        assert len(graphics) == 2 and len(document["assets"]) >= 2
    with Image.open(preview) as rendered:
        colors = rendered.convert("RGB").getcolors(maxcolors=rendered.width * rendered.height)
        assert colors and any(count > 500 and color[0] > color[1] * 1.5 for count, color in colors)
        assert any(count > 500 and color[2] > color[0] * 1.5 for count, color in colors)
    slide_after = decks.get_slide(services, deck["id"], slide["id"])
    assert slide_after["notes"] == "Speaker notes remain in the editable handout."
    assert [block["caption"] for block in slide_after["blocks"] if block["type"] == "image"] == [
        "Original raster photo", "SVG source with PNG fallback"]

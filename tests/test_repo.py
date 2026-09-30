"""Repository hygiene: manifest, docs, neutral wording, vendored code, defaults."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from cicero_hoard import APP_ID, SERVICE, agent_tools
from cicero_hoard.config import DEFAULT_PORT, Config
from conftest import BANNED_WORDS

ROOT = Path(__file__).resolve().parent.parent
# static/ is the minified build of client/src, which is scanned instead.
SKIP_DIRS = {"node_modules", "public", "static", "hoard_link", "dist-icons", ".git", "__pycache__", "venv", ".pytest_cache", "data", "dist"}
TEXT_SUFFIXES = {".py", ".md", ".json", ".toml", ".txt", ".yml", ".yaml", ".jsx", ".js", ".css", ".html"}


def repo_files():
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_SUFFIXES:
            continue
        rel = path.relative_to(ROOT)
        if set(rel.parts) & SKIP_DIRS or rel.name == "package-lock.json" or rel.parts[0] == "tests":
            continue
        yield path


def test_manifest_matches_the_app():
    manifest = json.loads((ROOT / "faustus-plugin.json").read_text(encoding="utf-8"))
    assert manifest["id"] == APP_ID == "cicero"
    assert manifest["app"]["health"]["expect"]["service"] == SERVICE == "cicero-hoard"
    assert str(DEFAULT_PORT) in manifest["app"]["url_default"] and DEFAULT_PORT == 5194
    assert manifest["app"]["launch_hint"]["argv"] == ["-m", "cicero_hoard"]
    assert manifest["mcp"]["transport"] == "stdio" and manifest["mcp"]["env"]["CICERO_URL"] == "{APP_URL}"
    for placeholder in re.findall(r"\{([A-Z_]+)\}", json.dumps(manifest)):
        assert placeholder in manifest["placeholders"], placeholder
    for name in re.findall(r"\b([a-z]+_[a-z_]+)\b(?=[,: ( ])", manifest["notes"].split("Tools that change or delete something:")[1].split(".")[0]):
        assert name in agent_tools.TOOLS_BY_NAME or name in ("confirm",), name


@pytest.mark.parametrize("readme", ["README.md", "README.es.md"])
def test_readmes_list_every_tool_and_have_the_responsible_use_section(readme):
    text = (ROOT / readme).read_text(encoding="utf-8")
    for tool in agent_tools.TOOLS_BY_NAME:
        assert f"`{tool}`" in text, (readme, tool)
    assert ("## Responsible use" if readme == "README.md" else "## Uso responsable") in text
    for var in ("CICERO_PORT", "CICERO_DATA_DIR", "CICERO_FILE_ROOTS", "CICERO_IMAGE_STUDIO_URL", "CICERO_IMAGE_TIMEOUT", "CICERO_ALLOWED_HOSTS"):
        assert f"`{var}`" in text, (readme, var)
    assert "pdf_unavailable" in text and "5194" in text


def test_api_doc_covers_every_route():
    from cicero_hoard.main import create_app
    from conftest import make_config

    doc = (ROOT / "docs" / "API.md").read_text(encoding="utf-8")
    import tempfile

    app = create_app(make_config(Path(tempfile.mkdtemp())))
    routes = {r.path for r in app.routes if getattr(r, "path", "").startswith("/api/") and "{path" not in r.path}
    for route in routes:
        normalized = re.sub(r"\{[a-z_]+\}", "{}", route)
        assert any(normalized == re.sub(r"\{[a-z_0-9]+\}", "{}", m.split("?")[0]) for m in re.findall(r"`(?:GET|POST|PUT|PATCH|DELETE)[^`]*?(/api/[^`\s]*)", doc)), route


def test_no_competitor_or_product_names_anywhere():
    offenders = []
    for path in repo_files():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for word in BANNED_WORDS:
            if re.search(rf"\b{re.escape(word)}\b", text):
                offenders.append((str(path.relative_to(ROOT)), word))
    assert not offenders, offenders


def test_vendored_hoard_link_is_untouched():
    vendored = ROOT / "cicero_hoard" / "hoard_link"
    assert (vendored / "VENDORED.txt").is_file()
    for name in ("__init__.py", "link.py", "family.py", "config.py"):
        assert (vendored / name).is_file(), name
    ref = Path("/home/claude/atlas-ref/atlas_hoard/hoard_link")
    if ref.is_dir():
        for path in vendored.glob("*.py"):
            assert path.read_bytes() == (ref / path.name).read_bytes(), path.name


def test_defaults():
    cfg = Config.from_env()
    assert cfg.port == 5194 and cfg.image_timeout == 600.0 and cfg.max_upload_bytes == 20 * 1024 * 1024
    assert (ROOT / "LICENSE").is_file() and (ROOT / ".gitignore").is_file() and (ROOT / ".github" / "workflows" / "ci.yml").is_file()


def test_requirements_are_pinned():
    for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            assert "==" in line, line
    assert "playwright" in (ROOT / "requirements.txt").read_text(encoding="utf-8")


def test_gitignore_keeps_data_and_secrets_out():
    text = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("data/", "venv", "node_modules", "__pycache__"):
        assert entry in text, entry

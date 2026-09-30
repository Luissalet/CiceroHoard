"""/api/decks/{id}/sources: pasted text (JSON) or a document (multipart)."""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile

from .. import decks as store
from ..errors import CiceroError
from ..models import SourceText
from .deps import services, tool

router = APIRouter(prefix="/api")


async def read_upload(request: Request, limit: int) -> tuple[bytes, str, dict]:
    """The ``file`` part of a multipart request, read within ``limit`` bytes (a bigger body is refused early)."""
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit + 1024 * 1024:
        raise CiceroError(f"The upload is larger than {limit // (1024 * 1024)} MB.")
    form = await request.form()
    upload = form.get("file")
    if not isinstance(upload, UploadFile):
        raise CiceroError("Send the document as a multipart field named 'file'.")
    data = await upload.read(limit + 1)
    if len(data) > limit:
        raise CiceroError(f"The file is larger than {limit // (1024 * 1024)} MB.")
    return data, upload.filename or "", {k: v for k, v in form.items() if isinstance(v, str)}


@router.post("/decks/{deck_id}/sources", status_code=201)
async def sources_add(request: Request, deck_id: str):
    svc = services(request)
    if request.headers.get("content-type", "").lower().startswith("multipart/"):
        data, filename, fields = await read_upload(request, svc.config.max_upload_bytes)
        source = await run_in_threadpool(store.add_source_file, svc, deck_id, data, filename)
        if fields.get("title", "").strip():  # a title typed in the form wins over the one found in the file
            svc.db.execute("UPDATE sources SET title = ? WHERE id = ?", (fields["title"].strip()[:300], source["id"]))
            source["title"] = fields["title"].strip()[:300]
        return source
    try:
        payload = await request.json()
    except ValueError as error:
        raise CiceroError("Send JSON {title, text} or a multipart file.") from error
    body = SourceText.model_validate(payload)
    return await run_in_threadpool(store.add_source_text, svc, deck_id, body.title or "Text", body.text, body.kind)


@router.get("/decks/{deck_id}/sources")
def sources_list(request: Request, deck_id: str):
    return tool(request, "source_list", deck_id=deck_id)


@router.get("/decks/{deck_id}/sources/{source_id}")
def sources_get(request: Request, deck_id: str, source_id: int, offset: int = 0, max_chars: int = 12000):
    return tool(request, "source_get", deck_id=deck_id, source_id=source_id, offset=offset, max_chars=max_chars)


@router.delete("/decks/{deck_id}/sources/{source_id}")
def sources_delete(request: Request, deck_id: str, source_id: int):
    return store.remove_source(services(request), deck_id, source_id)

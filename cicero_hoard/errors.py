"""Domain errors. The API and the agent route map them to HTTP codes (400 / 404 / 403)."""

from __future__ import annotations


class CiceroError(ValueError):
    """Invalid input or a violated rule (HTTP 400). ``code`` is an optional machine-readable reason."""

    code: str | None = None

    def __init__(self, message: str = "", code: str | None = None):
        super().__init__(message)
        if code is not None:
            self.code = code


class NotFound(LookupError):
    """The record does not exist (HTTP 404)."""


class Refused(CiceroError):
    """Blocked by a safety rule (HTTP 403)."""


class PdfUnavailable(CiceroError):
    """No Chromium could be started for the PDF export."""

    code = "pdf_unavailable"


class ImageStudioUnavailable(CiceroError):
    """The family image studio cannot be reached or did not return an image."""

    code = "image_studio_unavailable"


class GenerationFailed(CiceroError):
    """The model answered but not with usable JSON, even after one repair attempt."""

    code = "generation_failed"


class ModelUnavailable(CiceroError):
    """The operation needs a model and none is reachable."""

    code = "model_unavailable"

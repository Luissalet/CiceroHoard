"""Domain errors. The API and the agent route map them to HTTP codes (400 / 404 / 403)."""

from __future__ import annotations

from .hoard_link.agentkit import AppError


class CiceroError(AppError, ValueError):
    """Invalid input or a violated rule (HTTP 400). ``code`` is a machine-readable reason (``invalid`` when none is given).

    An :class:`~hoard_link.agentkit.AppError`: the shared error handlers and the agent router answer it with its own
    status and ``{"error", "code"}`` body."""

    code: str | None = None  # a subclass can fix its own code
    default_status = 400

    def __init__(self, message: str = "", code: str | None = None):
        super().__init__(code or type(self).code or "invalid", message, status=self.default_status)


class NotFound(AppError, LookupError):
    """The record does not exist (HTTP 404)."""

    def __init__(self, message: str = ""):
        super().__init__("not_found", message)


class RevisionConflict(CiceroError):
    code = "conflict"
    default_status = 409


class Refused(CiceroError):
    """Blocked by a safety rule (HTTP 403)."""

    code = "refused"
    default_status = 403


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

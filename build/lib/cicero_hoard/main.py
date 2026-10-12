"""FastAPI application factory: request guard, API routers, static SPA."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from . import APP_ID, SERVICE, __version__
from .api import ROUTERS
from .config import Config
from .hoard_link import family
from .hoard_link.agentkit import format_issues, issues_of
from .hoard_link.guard import install_guard
from .hoard_link.service import health_router, install_error_handlers, install_pwa, install_spa
from .services import Services

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(config: Config | None = None, services: Services | None = None) -> FastAPI:
    """``services`` lets tests inject a pre-built instance (fake link, fake image studio)."""
    config = config or (services.config if services else Config.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        svc = services or Services(config)
        app.state.services = svc
        svc.start()
        logging.getLogger("cicero").info("Cicero's Hoard %s — data in %s", __version__, config.data_dir)
        try:
            yield
        finally:
            svc.stop()

    app = FastAPI(title="Cicero's Hoard", version=__version__, lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.config = config
    family.configure(APP_ID, str(config.data_dir), token_file=str(config.token_path))

    install_guard(app, port_getter=lambda: config.port, allowed_env="CICERO_ALLOWED_HOSTS", allowed_hosts=config.allowed_hosts)
    install_error_handlers(app)  # one {"error", "code"} envelope: HTTP errors, validation, CiceroError/NotFound/Refused (AppError), 500

    @app.exception_handler(ValidationError)
    async def model_error(_, exc: ValidationError):  # a pydantic model that failed inside a handler (not a request body)
        return JSONResponse({"error": format_issues(exc), "code": "invalid_arguments", "issues": issues_of(exc)}, status_code=400)

    @app.exception_handler(KeyError)
    async def unknown(_, exc: KeyError):
        return JSONResponse({"error": str(exc.args[0]) if exc.args else "Not found.", "code": "not_found"}, status_code=404)

    app.include_router(health_router(SERVICE, __version__, extra=lambda: {
        "dataDirConfigured": config.data_dir_configured,
        "counts": getattr(app.state, "services").counts() if getattr(app.state, "services", None) else {}}))
    for router in ROUTERS:
        app.include_router(router)

    install_pwa(app, name="Cicero's Hoard", short_name="Cicero", theme="#4a1520", background="#2a0c13", cache="cicero-hoard-assets",
                lang="es", static_dir=STATIC_DIR, version=__version__)
    install_spa(app, STATIC_DIR)  # last: everything that is not an API route or a real file is the single page app
    return app

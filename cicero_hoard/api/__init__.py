"""API routers: one per area and the agent contract (health, PWA and the SPA come from Hoard Link in main.py)."""

from .agent import router as agent_router
from .assets import router as assets_router
from .decks import router as decks_router
from .exports import router as exports_router
from .outline import router as outline_router
from .settings import router as settings_router
from .slides import router as slides_router
from .sources import router as sources_router
from .status import router as status_router
from .themes import router as themes_router
from .templates import router as templates_router

ROUTERS = [status_router, decks_router, sources_router, outline_router, slides_router, assets_router, exports_router, themes_router,
           settings_router, agent_router, templates_router]

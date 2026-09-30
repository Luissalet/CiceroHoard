"""API routers: one per area, the agent contract and the PWA files."""

from .agent import router as agent_router
from .assets import router as assets_router
from .decks import router as decks_router
from .exports import router as exports_router
from .health import router as health_router
from .outline import router as outline_router
from .pwa import router as pwa_router
from .settings import router as settings_router
from .slides import router as slides_router
from .sources import router as sources_router
from .themes import router as themes_router

ROUTERS = [health_router, decks_router, sources_router, outline_router, slides_router, assets_router, exports_router, themes_router,
           settings_router, agent_router, pwa_router]

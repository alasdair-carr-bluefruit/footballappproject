from backend.api.routers.admin import router as admin_router
from backend.api.routers.auth import router as auth_router
from backend.api.routers.feedback import router as feedback_router
from backend.api.routers.matches import router as match_router
from backend.api.routers.public import router as public_router
from backend.api.routers.squad import router as squad_router
from backend.api.routers.teams import router as teams_router
from backend.api.routers.tournaments import router as tournament_router

__all__ = [
    "squad_router",
    "teams_router",
    "match_router",
    "tournament_router",
    "feedback_router",
    "auth_router",
    "admin_router",
    "public_router",
]

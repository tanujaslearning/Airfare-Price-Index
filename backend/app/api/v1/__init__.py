"""API v1 router configuration."""

from fastapi import APIRouter
from backend.app.api.v1.endpoints.index import router as index_router
from backend.app.api.v1.endpoints.routes import router as routes_router
from backend.app.api.v1.endpoints.pipeline import router as pipeline_router
from backend.app.api.v1.endpoints.provenance import router as provenance_router
from backend.app.api.v1.endpoints.filters import router as filters_router

v1_router = APIRouter(prefix="/v1")
v1_router.include_router(index_router)
v1_router.include_router(routes_router)
v1_router.include_router(pipeline_router)
v1_router.include_router(provenance_router)
v1_router.include_router(filters_router)

__all__ = ["v1_router"]

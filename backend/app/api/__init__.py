"""API routing module."""

from fastapi import APIRouter
from backend.app.api.health import router as health_router
from backend.app.api.v1 import v1_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(v1_router)

__all__ = ["api_router", "v1_router"]

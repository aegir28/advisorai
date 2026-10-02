"""The /api/v1 router. New resource routers (cases, documents, analysis, ...) are included here."""

from fastapi import APIRouter

from app.core.config import API_PREFIX

from . import health

api_v1 = APIRouter(prefix=API_PREFIX)
api_v1.include_router(health.router)

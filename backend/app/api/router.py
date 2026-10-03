"""The /api/v1 router. New resource routers (cases, documents, analysis, ...) are included here."""

from fastapi import APIRouter

from app.core.config import API_PREFIX

from . import cases, documents, health, me

api_v1 = APIRouter(prefix=API_PREFIX)
api_v1.include_router(health.router)
api_v1.include_router(me.router)
api_v1.include_router(cases.router)
api_v1.include_router(documents.router)

"""The /api/v1 router. New resource routers (cases, documents, analysis, ...) are included here."""

from fastapi import APIRouter

from app.core.config import API_PREFIX

from . import analysis, cases, documents, health, me, orchestration

api_v1 = APIRouter(prefix=API_PREFIX)
api_v1.include_router(health.router)
api_v1.include_router(me.router)
api_v1.include_router(analysis.router)
api_v1.include_router(cases.router)
api_v1.include_router(documents.router)
api_v1.include_router(orchestration.router)

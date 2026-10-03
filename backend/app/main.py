"""FastAPI application factory.

Middleware order, outermost first:

    RequestIdMiddleware  ->  CORSMiddleware  ->  ErrorBoundaryMiddleware  ->  routes

* the request ID wraps everything, so every response (including CORS preflights) carries it;
* CORS wraps the error boundary, so a 500 envelope still gets CORS headers and the browser can read it.

Starlette runs the middleware added LAST first, hence the reversed `add_middleware` calls below.

Services (database, JWT verifier, audit writer, storage) are built from settings and kept on
`app.state`. Anything not configured is simply absent and the routes that need it answer
`503 SERVICE_UNAVAILABLE`, so the app still starts in a bare environment (and in unit tests).
"""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_v1
from app.audit.writer import AuditWriter
from app.auth.jwks import JwksKeyProvider, KeyProvider
from app.auth.verifier import JwtVerifier
from app.core.config import API_PREFIX, Settings, get_settings
from app.core.errors import ErrorBoundaryMiddleware, register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.core.security import BodyLimitMiddleware, SecurityHeadersMiddleware
from app.db.database import Database, create_engine
from app.openapi import DESCRIPTION, install_openapi
from app.schemas import ErrorEnvelope
from app.services.cases import CaseService
from app.services.documents import DocumentService
from app.services.workflows import WorkflowService
from app.storage.gateway import StorageGateway, SupabaseStorageGateway
from app.storage.service import DocumentUrlService
from app.workflow.definitions import DefinitionRegistry
from app.workflow.engine import Engine, NodeRegistry
from app.workflow.repository import WorkflowRepository
from app.workflow.worker import Worker


def create_app(
    settings: Settings | None = None,
    *,
    database: Database | None = None,
    key_provider: KeyProvider | None = None,
    storage: StorageGateway | None = None,
) -> FastAPI:
    """Build the app. The keyword arguments let tests (and later phases) inject services."""
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    http = httpx.AsyncClient()
    owns_database = database is None and settings.database_url is not None
    if database is None and settings.database_url is not None:
        # Two logins, two pools: the user path (app_backend) and the system path (app_system).
        database = Database(
            create_engine(settings.database_url),
            create_engine(settings.system_database_url) if settings.system_database_url is not None else None,
        )

    if key_provider is None and settings.supabase_jwks_url is not None:
        key_provider = JwksKeyProvider(settings.supabase_jwks_url, http)
    verifier = (
        JwtVerifier(key_provider, settings.supabase_jwt_issuer)
        if key_provider is not None and settings.supabase_jwt_issuer is not None
        else None
    )

    if (
        storage is None
        and settings.supabase_url is not None
        and settings.supabase_service_role_key is not None
    ):
        storage = SupabaseStorageGateway(settings, http)
    audit = AuditWriter(database, settings.audit_ip_hmac_secret) if database is not None else None
    document_urls = (
        DocumentUrlService(database, audit, storage)
        if database is not None and audit is not None and storage is not None
        else None
    )

    cases = CaseService(database, audit, storage) if database is not None and audit is not None else None
    documents = (
        DocumentService(database, audit, storage, settings)
        if database is not None and audit is not None and storage is not None
        else None
    )

    definitions = DefinitionRegistry.from_directory(settings.workflows_dir)
    node_registry = NodeRegistry()  # empty until the AI phase registers node types
    workflow_repo = WorkflowRepository(database) if database is not None else None
    workflows = (
        WorkflowService(database, workflow_repo, definitions)
        if database is not None and workflow_repo is not None
        else None
    )
    worker = (
        Worker(
            workflow_repo,
            Engine(workflow_repo, definitions, node_registry, audit=audit),
            lease_seconds=settings.worker_lease_seconds,
            poll_interval=settings.worker_poll_interval_seconds,
        )
        if settings.worker_enabled and workflow_repo is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        stop = asyncio.Event()
        task = asyncio.create_task(worker.run_forever(stop)) if worker is not None else None
        yield
        if task is not None:
            stop.set()
            task.cancel()  # a run in progress is handed back by the worker's cancellation path
            await asyncio.gather(task, return_exceptions=True)
        await http.aclose()
        if owns_database and database is not None:
            await database.dispose()

    docs = settings.docs_enabled
    app = FastAPI(
        title="AdvisorAI API",
        version=__version__,
        description=DESCRIPTION,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=f"{API_PREFIX}/redoc" if docs else None,
        lifespan=lifespan,
        responses={
            422: {"model": ErrorEnvelope, "description": "Request did not match the expected format."},
            500: {"model": ErrorEnvelope, "description": "Unexpected server error."},
        },
    )

    app.add_middleware(ErrorBoundaryMiddleware)
    app.add_middleware(BodyLimitMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, hsts=settings.environment == "production")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.add_middleware(RequestIdMiddleware)

    app.state.settings = settings
    app.state.database = database
    app.state.jwt_verifier = verifier
    app.state.audit = audit
    app.state.storage = storage
    app.state.document_urls = document_urls
    app.state.cases = cases
    app.state.documents = documents
    app.state.workflows = workflows
    app.state.node_registry = node_registry
    app.state.definitions = definitions
    register_exception_handlers(app)
    app.include_router(api_v1)
    install_openapi(app)
    return app


app = create_app()

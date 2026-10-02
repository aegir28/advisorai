"""FastAPI application factory.

Middleware order, outermost first:

    RequestIdMiddleware  ->  CORSMiddleware  ->  ErrorBoundaryMiddleware  ->  routes

* the request ID wraps everything, so every response (including CORS preflights) carries it;
* CORS wraps the error boundary, so a 500 envelope still gets CORS headers and the browser can read it.

Starlette runs the middleware added LAST first, hence the reversed `add_middleware` calls below.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.router import api_v1
from app.core.config import API_PREFIX, Settings, get_settings
from app.core.errors import ErrorBoundaryMiddleware, register_exception_handlers
from app.core.logging import configure_logging
from app.core.request_id import REQUEST_ID_HEADER, RequestIdMiddleware
from app.openapi import DESCRIPTION, install_openapi
from app.schemas import ErrorEnvelope


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    docs = settings.docs_enabled
    app = FastAPI(
        title="AdvisorAI API",
        version=__version__,
        description=DESCRIPTION,
        openapi_url=f"{API_PREFIX}/openapi.json" if docs else None,
        docs_url=f"{API_PREFIX}/docs" if docs else None,
        redoc_url=f"{API_PREFIX}/redoc" if docs else None,
        responses={
            422: {"model": ErrorEnvelope, "description": "Request did not match the expected format."},
            500: {"model": ErrorEnvelope, "description": "Unexpected server error."},
        },
    )

    app.add_middleware(ErrorBoundaryMiddleware)
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
    register_exception_handlers(app)
    app.include_router(api_v1)
    install_openapi(app)
    return app


app = create_app()

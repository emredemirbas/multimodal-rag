from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Query, Request, Response, Security
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.exceptions import HTTPException as StarletteHTTPException

from .auth import (
    AuthenticationError,
    Authenticator,
    DevelopmentAuthenticator,
    TrustedProxyAuthenticator,
)
from .config import Settings
from .metrics import Metrics
from .models import (
    AuthenticatedPrincipal,
    Project,
    ProjectCreate,
    ProjectList,
    ProjectListStatus,
    ProjectUpdate,
    QuestionRequest,
    QuestionResponse,
    Source,
    SourceIngested,
    TranscriptIngestRequest,
)
from .postgres import DatabaseUnavailableError, PostgresStore
from .providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from .service import TutorialService
from .store import InMemoryStore, ProjectNotFoundError, Store
from .transcripts import TranscriptParseError


LOGGER = logging.getLogger("tutorial_workspace")
API_VERSION = "0.2.0"
bearer_scheme = HTTPBearer(auto_error=False)


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")


def build_store(settings: Settings) -> Store:
    if settings.store_backend == "postgres":
        if settings.embedding_dimensions != 64:
            raise ValueError("PostgreSQL schema requires 64 embedding dimensions")
        store = PostgresStore(settings.database_url)
        if settings.auto_migrate:
            store.run_migrations()
        return store
    if settings.store_backend == "memory":
        return InMemoryStore()
    raise ValueError(f"unsupported APP_STORE: {settings.store_backend}")


def build_authenticator(settings: Settings) -> Authenticator:
    auth_mode = settings.auth_mode.strip().lower()
    if auth_mode == "development":
        return DevelopmentAuthenticator(
            token=settings.development_auth_token,
            subject=settings.development_auth_subject,
            tenant_id=settings.development_auth_tenant,
        )
    if auth_mode == "trusted_proxy":
        return TrustedProxyAuthenticator(shared_secret=settings.trusted_proxy_secret)
    raise ValueError(f"unsupported AUTH_MODE: {settings.auth_mode}")


async def require_principal(
    request: Request,
    _: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ] = None,
) -> AuthenticatedPrincipal:
    return request.app.state.authenticator.authenticate(request.headers)


CurrentPrincipal = Annotated[AuthenticatedPrincipal, Depends(require_principal)]


def create_app(
    *,
    settings: Settings | None = None,
    store: Store | None = None,
    authenticator: Authenticator | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    configure_logging(active_settings.log_level)
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_store = store or build_store(active_settings)
        application.state.store = active_store
        application.state.authenticator = authenticator or build_authenticator(
            active_settings
        )
        application.state.service = TutorialService(
            active_store,
            DeterministicHashEmbeddingProvider(active_settings.embedding_dimensions),
            EvidenceExtractiveAnswerProvider(),
            retrieval_limit=active_settings.retrieval_limit,
        )
        application.state.metrics = metrics
        yield

    app = FastAPI(
        title="Multimodal Tutorial Workspace",
        version=API_VERSION,
        description="Sprint 1 authenticated project foundation API",
        lifespan=lifespan,
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.exception(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "method": request.method,
                        "path": request.url.path,
                    }
                )
            )
            raise
        route = request.scope.get("route")
        route_path = getattr(route, "path", request.url.path)
        metrics.observe_request(request.method, route_path, response.status_code)
        response.headers["X-Request-ID"] = request_id
        LOGGER.info(
            json.dumps(
                {
                    "event": "request_complete",
                    "request_id": request_id,
                    "method": request.method,
                    "route": route_path,
                    "status": response.status_code,
                    "latency_ms": round((perf_counter() - started) * 1_000),
                }
            )
        )
        return response

    @app.exception_handler(AuthenticationError)
    async def authentication_handler(_: Request, exc: AuthenticationError):
        return JSONResponse(
            status_code=401,
            content={"code": exc.code, "detail": exc.detail},
            headers={"WWW-Authenticate": "Bearer"},
        )

    @app.exception_handler(ProjectNotFoundError)
    async def not_found_handler(_: Request, exc: ProjectNotFoundError):
        return JSONResponse(
            status_code=404,
            content={"code": "not_found", "detail": str(exc)},
        )

    @app.exception_handler(DatabaseUnavailableError)
    async def database_unavailable_handler(_: Request, __: DatabaseUnavailableError):
        return JSONResponse(
            status_code=503,
            content={
                "code": "database_unavailable",
                "detail": "The database is temporarily unavailable.",
            },
        )

    @app.exception_handler(TranscriptParseError)
    async def transcript_handler(_: Request, exc: TranscriptParseError):
        return JSONResponse(
            status_code=422,
            content={"code": "invalid_transcript", "detail": str(exc)},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(_: Request, __: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "code": "validation_error",
                "detail": "Request validation failed.",
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(_: Request, exc: StarletteHTTPException):
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": code, "detail": str(exc.detail)},
            headers=exc.headers,
        )

    def service(request: Request) -> TutorialService:
        return request.app.state.service

    @app.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "ok", "version": API_VERSION}

    @app.get("/health/ready")
    def health_ready(request: Request) -> dict[str, str]:
        request.app.state.store.healthcheck()
        return {"status": "ok", "version": API_VERSION}

    @app.get("/health")
    def health_compatibility_alias(request: Request) -> dict[str, str]:
        request.app.state.store.healthcheck()
        return {"status": "ok", "version": API_VERSION}

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics(request: Request) -> Response:
        return Response(
            request.app.state.metrics.render(),
            media_type="text/plain; version=0.0.4",
        )

    @app.post("/api/v1/projects", response_model=Project, status_code=201)
    def create_project(
        body: ProjectCreate,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Project:
        return service(request).create_project(principal, body)

    @app.get("/api/v1/projects", response_model=ProjectList)
    def list_projects(
        request: Request,
        principal: CurrentPrincipal,
        status: Annotated[ProjectListStatus, Query()] = ProjectListStatus.ACTIVE,
    ) -> ProjectList:
        return service(request).list_projects(principal, status)

    @app.get("/api/v1/projects/{project_id}", response_model=Project)
    def get_project(
        project_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Project:
        return service(request).get_project(principal, project_id)

    @app.patch("/api/v1/projects/{project_id}", response_model=Project)
    def update_project(
        project_id: UUID,
        body: ProjectUpdate,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Project:
        return service(request).update_project(principal, project_id, body)

    @app.post("/api/v1/projects/{project_id}/archive", response_model=Project)
    def archive_project(
        project_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Project:
        return service(request).archive_project(principal, project_id)

    @app.post("/api/v1/projects/{project_id}/restore", response_model=Project)
    def restore_project(
        project_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Project:
        return service(request).restore_project(principal, project_id)

    @app.delete("/api/v1/projects/{project_id}", status_code=204)
    def delete_project(
        project_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Response:
        service(request).delete_project(principal, project_id)
        return Response(status_code=204)

    @app.post(
        "/api/v1/projects/{project_id}/sources/transcripts",
        response_model=SourceIngested,
        status_code=201,
    )
    def ingest_transcript(
        project_id: UUID,
        body: TranscriptIngestRequest,
        request: Request,
        principal: CurrentPrincipal,
    ) -> SourceIngested:
        return service(request).ingest_transcript(principal, project_id, body)

    @app.get(
        "/api/v1/projects/{project_id}/sources/{source_id}",
        response_model=Source,
    )
    def get_source(
        project_id: UUID,
        source_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Source:
        return service(request).get_source(principal, project_id, source_id)

    @app.post(
        "/api/v1/projects/{project_id}/questions",
        response_model=QuestionResponse,
    )
    def ask_question(
        project_id: UUID,
        body: QuestionRequest,
        request: Request,
        principal: CurrentPrincipal,
    ) -> QuestionResponse:
        return service(request).ask(principal, project_id, body.question)

    return app


app = create_app()

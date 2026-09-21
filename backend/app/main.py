from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
from time import perf_counter
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, Request, Response
from fastapi.responses import JSONResponse

from .config import Settings
from .metrics import Metrics
from .models import (
    Project,
    ProjectCreate,
    QuestionRequest,
    QuestionResponse,
    Source,
    SourceIngested,
    TenantId,
    TranscriptIngestRequest,
)
from .postgres import PostgresStore
from .providers import DeterministicHashEmbeddingProvider, EvidenceExtractiveAnswerProvider
from .service import TutorialService
from .store import InMemoryStore, ProjectNotFoundError, Store
from .transcripts import TranscriptParseError


LOGGER = logging.getLogger("tutorial_workspace")
TenantHeader = Annotated[TenantId, Header(alias="X-Tenant-ID")]


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")


def build_store(settings: Settings) -> Store:
    if settings.store_backend == "postgres":
        if settings.embedding_dimensions != 64:
            raise ValueError("PostgreSQL Sprint 0 schema requires 64 embedding dimensions")
        store = PostgresStore(settings.database_url)
        store.run_migrations()
        return store
    if settings.store_backend == "memory":
        return InMemoryStore()
    raise ValueError(f"unsupported APP_STORE: {settings.store_backend}")


def create_app(*, settings: Settings | None = None, store: Store | None = None) -> FastAPI:
    active_settings = settings or Settings.from_env()
    configure_logging(active_settings.log_level)
    metrics = Metrics()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_store = store or build_store(active_settings)
        application.state.store = active_store
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
        version="0.1.0",
        description="Sprint 0 transcript-to-cited-answer validation API",
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

    @app.exception_handler(ProjectNotFoundError)
    async def not_found_handler(_: Request, exc: ProjectNotFoundError):
        return JSONResponse(status_code=404, content={"code": "not_found", "detail": str(exc)})

    @app.exception_handler(TranscriptParseError)
    async def transcript_handler(_: Request, exc: TranscriptParseError):
        return JSONResponse(
            status_code=422,
            content={"code": "invalid_transcript", "detail": str(exc)},
        )

    def service(request: Request) -> TutorialService:
        return request.app.state.service

    @app.get("/health")
    async def health(request: Request) -> dict[str, str]:
        request.app.state.store.healthcheck()
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics(request: Request) -> Response:
        return Response(
            request.app.state.metrics.render(),
            media_type="text/plain; version=0.0.4",
        )

    @app.post("/api/v1/projects", response_model=Project, status_code=201)
    async def create_project(
        body: ProjectCreate,
        request: Request,
        tenant_id: TenantHeader = "local",
    ) -> Project:
        return service(request).create_project(tenant_id, body)

    @app.post(
        "/api/v1/projects/{project_id}/sources/transcripts",
        response_model=SourceIngested,
        status_code=201,
    )
    async def ingest_transcript(
        project_id: UUID,
        body: TranscriptIngestRequest,
        request: Request,
        tenant_id: TenantHeader = "local",
    ) -> SourceIngested:
        return service(request).ingest_transcript(tenant_id, project_id, body)

    @app.get(
        "/api/v1/projects/{project_id}/sources/{source_id}",
        response_model=Source,
    )
    async def get_source(
        project_id: UUID,
        source_id: UUID,
        request: Request,
        tenant_id: TenantHeader = "local",
    ) -> Source:
        return request.app.state.store.get_source(tenant_id, project_id, source_id)

    @app.post(
        "/api/v1/projects/{project_id}/questions",
        response_model=QuestionResponse,
    )
    async def ask_question(
        project_id: UUID,
        body: QuestionRequest,
        request: Request,
        tenant_id: TenantHeader = "local",
    ) -> QuestionResponse:
        return service(request).ask(tenant_id, project_id, body.question)

    return app


app = create_app()

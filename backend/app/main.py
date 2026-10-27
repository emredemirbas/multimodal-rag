from __future__ import annotations

from contextlib import asynccontextmanager
import json
import logging
from time import perf_counter
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, File, Form, Query, Request, Response, Security, UploadFile
from starlette.concurrency import run_in_threadpool
import psycopg
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
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
    AuthorizationMode,
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
from .providers import EvidenceExtractiveAnswerProvider
from .local_embeddings import build_embedding_provider
from .embedding_profiles import configured_space
from .service import TutorialService
from .store import InMemoryStore, ProjectNotFoundError, Store
from .transcripts import TranscriptParseError
from .artifacts.storage import ArtifactStore, S3ArtifactStore
from .sources.contracts import Cleanup, Job, ManagedSource, MetadataRegistration, Registration, SourceCommand, SourceError, SourceList
from .sources.repository import SourceRepository
from .sources.transcript import MAX_PAGES, TranscriptPage, TranscriptRepository
from .sources.alignment import AlignmentRepository, TimelineAlignment, MAX_OFFSET
from .sources.upload_limit import UploadLimitMiddleware
from .sources.audio_upload import AUDIO_FORM_FIELDS, AUDIO_OPTIONAL_FIELDS, AudioCapability
from .sources.video_upload import VIDEO_FORM_FIELDS, VideoCapability
from .sources.video import VideoRepository
from .vision.media import MAX_VIDEO_BYTES
from .sources.media import MediaRepository
from .asr.contracts import Language
from .asr.wav import MAX_WAV_BYTES
from .local_model import OllamaAnswerProvider
from .chat.contracts import Conversation, ConversationCreate, ConversationList, EvidenceView, History, MessageRequest
from .chat.repository import ChatRepository
from .chat.delivery import deliver
from .vision.gallery import VisualGalleryRepository
from .vision.gallery_contracts import VisualGallery
from .vision.descriptions import DescriptionRepository, DescriptionView


LOGGER = logging.getLogger("tutorial_workspace")
API_VERSION = "0.9.0"
bearer_scheme = HTTPBearer(auto_error=False)


def configure_logging(level: str) -> None:
    logging.basicConfig(level=level, format="%(message)s")


def build_store(settings: Settings) -> Store:
    if settings.store_backend == "postgres":
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
    artifacts: ArtifactStore | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_env()
    configure_logging(active_settings.log_level)
    metrics = Metrics()
    active_authenticator = authenticator or build_authenticator(active_settings)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        active_store = store or build_store(active_settings)
        application.state.store = active_store
        application.state.authenticator = active_authenticator
        application.state.service = TutorialService(
            active_store,
            build_embedding_provider(active_settings),
            (OllamaAnswerProvider(active_settings.ollama_base_url, active_settings.ollama_model,
                                 active_settings.local_model_timeout,
                                 embedding_space=configured_space(active_settings.embedding_provider))
             if active_settings.answer_provider == 'ollama' else EvidenceExtractiveAnswerProvider()),
            retrieval_limit=active_settings.retrieval_limit,
        )
        application.state.metrics = metrics
        application.state.sources = None
        application.state.chat = ChatRepository(active_store, metrics) if isinstance(active_store, PostgresStore) else None
        if isinstance(active_store, PostgresStore) and (artifacts is not None or active_settings.s3_access_key):
            application.state.sources = SourceRepository(active_store, artifacts or S3ArtifactStore(active_settings), active_settings)
        yield

    app = FastAPI(
        title="Multimodal Tutorial Workspace",
        version=API_VERSION,
        description="Authenticated project and asynchronous transcript ingestion API",
        lifespan=lifespan,
    )
    app.add_middleware(UploadLimitMiddleware, limit=active_settings.upload_limit_bytes + 16_384,
                       audio_upload_enabled=active_settings.audio_upload_enabled,
                       video_upload_enabled=active_settings.video_upload_enabled, authenticator=active_authenticator)

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid4()))[:128]
        started = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            LOGGER.error(
                json.dumps(
                    {
                        "event": "request_failed",
                        "request_id": request_id,
                        "method": request.method,
                        "code": "request_unavailable",
                    }
                )
            )
            raise
        route = request.scope.get("route")
        route_path = getattr(route, "path", "unmatched")
        if route_path in {'/api/v1/projects/{project_id}/sources/{source_id}/frames', '/api/v1/projects/{project_id}/frames/{frame_id}/image', '/api/v1/projects/{project_id}/evidence/{segment_id}', '/api/v1/projects/{project_id}/sources/{source_id}/alignment', '/api/v1/projects/{project_id}/sources/{source_id}/descriptions'}:
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['X-Content-Type-Options'] = 'nosniff'
            response.headers['Cross-Origin-Resource-Policy'] = 'same-origin'
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

    @app.exception_handler(SourceError)
    async def source_error_handler(_: Request, exc: SourceError):
        return JSONResponse(status_code=exc.status, content={"code": exc.code, "detail": exc.detail})

    @app.exception_handler(psycopg.Error)
    async def database_query_error_handler(_: Request, __: psycopg.Error):
        return JSONResponse(status_code=503, content={"code": "database_unavailable", "detail": "The database is temporarily unavailable."})

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

    def sources(request: Request) -> SourceRepository:
        repository = request.app.state.sources
        if repository is None:
            raise SourceError("ingestion_not_configured", "Transcript ingestion requires PostgreSQL and configured object storage.", 503)
        return repository

    def actor(request: Request, principal: AuthenticatedPrincipal) -> UUID:
        return request.app.state.store.bootstrap_principal(principal)

    def chat(request: Request) -> ChatRepository:
        if request.app.state.chat is None:
            raise SourceError("chat_not_configured", "Persisted conversations require PostgreSQL.", 503)
        return request.app.state.chat

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
    def prometheus_metrics(request: Request) -> Response:
        processing = request.app.state.sources.render_metrics() if request.app.state.sources is not None else ""
        return Response(
            request.app.state.metrics.render() + processing,
            media_type="text/plain; version=0.0.4",
        )

    @app.get("/api/v1/runtime")
    def runtime_configuration(request: Request, principal: CurrentPrincipal) -> dict[str, str]:
        actor(request, principal)
        provider = service(request).answer_provider
        return {'mode': active_settings.answer_provider, 'provider': provider.name, 'model': provider.model,
                'retrieval': 'local-semantic-and-lexical' if active_settings.embedding_provider == 'ollama' else 'deterministic-hash-and-lexical',
                'embedding_space': configured_space(active_settings.embedding_provider), 'spend_policy': 'no-paid-provider'}

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
        cleanup_id = service(request).delete_project(principal, project_id)
        headers = {} if cleanup_id is None else {"X-Cleanup-ID": str(cleanup_id), "Location": f"/api/v1/projects/{project_id}/cleanup/{cleanup_id}"}
        return Response(status_code=204, headers=headers)

    @app.post("/api/v1/projects/{project_id}/sources/uploads", response_model=Registration, status_code=202)
    async def upload_transcript(
        project_id: UUID, request: Request, principal: CurrentPrincipal,
        file: Annotated[UploadFile, File()],
        authorization_mode: Annotated[AuthorizationMode, Form()],
        idempotency_key: Annotated[str, Form(min_length=8, max_length=128, pattern=r"^[a-zA-Z0-9_-]+$")],
        playlist_item_id: Annotated[UUID | None, Form()] = None,
    ) -> Registration:
        repository = sources(request)
        allowed_types = {"text/plain", "text/vtt", "application/x-subrip", "application/octet-stream"}
        if file.content_type not in allowed_types:
            raise SourceError("unsupported_file", "Upload a text SRT/VTT transcript.")
        try:
            content = await file.read(active_settings.upload_limit_bytes + 1)
            actor_id = await run_in_threadpool(actor, request, principal)
            return await run_in_threadpool(repository.register, principal.tenant_id, project_id, actor_id,
                                          filename=file.filename or "", content=content, rights=authorization_mode,
                                          idempotency_key=idempotency_key, playlist_item_id=playlist_item_id)
        finally:
            await file.close()

    @app.get('/api/v1/ingestion/capabilities', response_model=AudioCapability)
    def ingestion_capabilities(request: Request, response: Response, principal: CurrentPrincipal) -> AudioCapability:
        actor(request, principal)
        response.headers['Cache-Control'] = 'no-store'
        return AudioCapability(enabled=active_settings.audio_upload_enabled and request.app.state.sources is not None)

    @app.get('/api/v1/ingestion/video-capabilities', response_model=VideoCapability)
    def video_capabilities(request: Request, response: Response, principal: CurrentPrincipal) -> VideoCapability:
        actor(request, principal)
        response.headers['Cache-Control'] = 'no-store'
        return VideoCapability(enabled=active_settings.video_upload_enabled and request.app.state.sources is not None)

    @app.post('/api/v1/projects/{project_id}/sources/video', response_model=Registration, status_code=202)
    async def upload_video(
        project_id: UUID, request: Request, response: Response, principal: CurrentPrincipal,
        file: Annotated[UploadFile, File()],
        authorization_mode: Annotated[AuthorizationMode, Form()],
        language: Annotated[Literal['en', 'tr', 'en+tr'], Form()],
        idempotency_key: Annotated[str, Form(min_length=8, max_length=128, pattern=r'^[a-zA-Z0-9_-]+$')],
        retention_acknowledged: Annotated[Literal['accepted'], Form()],
    ) -> Registration:
        try:
            if not active_settings.video_upload_enabled:
                raise SourceError('video_upload_disabled', 'Local MP4 upload is not enabled.', 503)
            form = await request.form()
            if set(form) != VIDEO_FORM_FIELDS or len(form.multi_items()) != len(VIDEO_FORM_FIELDS):
                raise SourceError('invalid_video_form', 'Send one MP4, rights, OCR language, request key and retention acknowledgement.')
            if file.content_type not in {'video/mp4', 'application/octet-stream'}:
                raise SourceError('invalid_video_type', 'Use an authorized supported MP4 file.')
            repository = sources(request)
            content = await file.read(MAX_VIDEO_BYTES + 1)
            if not content or len(content) > MAX_VIDEO_BYTES:
                raise SourceError('video_too_large', 'Upload a non-empty MP4 file of at most 100 MB.', 413)
            actor_id = await run_in_threadpool(actor, request, principal)
            response.headers['Cache-Control'] = 'no-store'
            return await run_in_threadpool(VideoRepository(repository).register, principal.tenant_id, project_id, actor_id,
                filename=file.filename or '', content=content, rights=authorization_mode, language=language,
                idempotency_key=idempotency_key, auto_process=True)
        finally:
            await file.close()

    @app.post('/api/v1/projects/{project_id}/sources/audio', response_model=Registration, status_code=202)
    async def upload_audio(
        project_id: UUID, request: Request, response: Response, principal: CurrentPrincipal,
        file: Annotated[UploadFile, File()],
        authorization_mode: Annotated[AuthorizationMode, Form()],
        language: Annotated[Language, Form()],
        idempotency_key: Annotated[str, Form(min_length=8, max_length=128, pattern=r'^[a-zA-Z0-9_-]+$')],
        retention_acknowledged: Annotated[Literal['accepted'], Form()],
        playlist_item_id: Annotated[UUID | None, Form()] = None,
    ) -> Registration:
        try:
            if not active_settings.audio_upload_enabled:
                raise SourceError('audio_upload_disabled', 'Local audio upload is not enabled.', 503)
            form = await request.form()
            if (not AUDIO_FORM_FIELDS <= set(form) or set(form) - AUDIO_FORM_FIELDS - AUDIO_OPTIONAL_FIELDS
                    or len(form.multi_items()) != len(set(form))):
                raise SourceError('validation_error', 'Send one WAV file, rights, language, request key and retention acknowledgement.')
            if file.content_type not in {'audio/wav', 'audio/x-wav', 'audio/wave', 'application/octet-stream'}:
                raise SourceError('invalid_audio_type', 'Upload a supported WAV file, not video or compressed media.')
            repository = sources(request)
            content = await file.read(MAX_WAV_BYTES + 1)
            actor_id = await run_in_threadpool(actor, request, principal)
            response.headers['Cache-Control'] = 'no-store'
            return await run_in_threadpool(MediaRepository(repository).register, principal.tenant_id, project_id, actor_id,
                filename=file.filename or '', content=content, rights=authorization_mode, language=language, idempotency_key=idempotency_key,
                playlist_item_id=playlist_item_id)
        finally:
            await file.close()

    @app.get("/api/v1/projects/{project_id}/sources", response_model=SourceList)
    def list_sources(project_id: UUID, request: Request, principal: CurrentPrincipal) -> SourceList:
        actor(request, principal)
        return sources(request).list_sources(principal.tenant_id, project_id)

    @app.post("/api/v1/projects/{project_id}/sources", response_model=Registration, status_code=202)
    def register_metadata(project_id: UUID, body: MetadataRegistration, request: Request, principal: CurrentPrincipal) -> Registration:
        return sources(request).register_metadata(principal.tenant_id, project_id, actor(request, principal),
                                                 url=body.url, rights=body.authorization_mode, idempotency_key=body.idempotency_key)

    @app.get("/api/v1/projects/{project_id}/jobs/{job_id}", response_model=Job)
    def get_job(project_id: UUID, job_id: UUID, request: Request, principal: CurrentPrincipal) -> Job:
        actor(request, principal)
        return sources(request).get_job(principal.tenant_id, project_id, job_id)

    # Specific derived-input commands must precede the generic command route.
    @app.post('/api/v1/projects/{project_id}/sources/{source_id}/descriptions',response_model=Registration,status_code=202)
    def describe_selected_frames(project_id:UUID,source_id:UUID,body:SourceCommand,request:Request,principal:CurrentPrincipal):
        return DescriptionRepository(sources(request)).enqueue(principal.tenant_id,project_id,source_id,actor(request,principal),body.idempotency_key)

    @app.post("/api/v1/projects/{project_id}/sources/{source_id}/{command}", response_model=Registration, status_code=202)
    def source_command(project_id: UUID, source_id: UUID, command: str, body: SourceCommand, request: Request, principal: CurrentPrincipal) -> Registration:
        if command not in {"retry", "cancel", "reprocess"}:
            raise ProjectNotFoundError("command not found")
        return sources(request).command(principal.tenant_id, project_id, source_id, actor(request, principal), command, body.idempotency_key)

    @app.delete("/api/v1/projects/{project_id}/sources/{source_id}", response_model=Cleanup, status_code=202)
    def delete_source(project_id: UUID, source_id: UUID, request: Request, principal: CurrentPrincipal) -> Cleanup:
        return sources(request).delete_source(principal.tenant_id, project_id, source_id, actor(request, principal))

    @app.get("/api/v1/projects/{project_id}/cleanup/{cleanup_id}", response_model=Cleanup)
    def cleanup_status(project_id: UUID, cleanup_id: UUID, request: Request, principal: CurrentPrincipal) -> Cleanup:
        return sources(request).get_cleanup(principal.tenant_id, project_id, cleanup_id, actor(request, principal))

    @app.post("/api/v1/projects/{project_id}/cleanup/{cleanup_id}/retry", response_model=Cleanup)
    def retry_cleanup(project_id: UUID, cleanup_id: UUID, request: Request, principal: CurrentPrincipal) -> Cleanup:
        repository = sources(request)
        actor_id = actor(request, principal)
        current = repository.get_cleanup(principal.tenant_id, project_id, cleanup_id, actor_id)
        if current.status == "failed":
            with repository.store._connect() as connection:
                connection.execute("UPDATE artifact_cleanup SET status='pending',attempt_count=0,available_at=now(),failure_code=NULL WHERE tenant_id=%s AND project_id=%s AND id=%s AND actor_user_id=%s AND status='failed'", (principal.tenant_id, project_id, cleanup_id, actor_id))
        return repository.get_cleanup(principal.tenant_id, project_id, cleanup_id, actor_id)

    @app.post(
        "/api/v1/projects/{project_id}/sources/transcripts",
        response_model=SourceIngested,
        status_code=201,
        deprecated=True,
    )
    def ingest_transcript(
        project_id: UUID,
        body: TranscriptIngestRequest,
        request: Request,
        principal: CurrentPrincipal,
    ) -> SourceIngested:
        if active_settings.environment.strip().lower() not in {"development", "test"} or active_settings.embedding_provider != 'hash':
            raise SourceError("validation_endpoint_unavailable", "Use the asynchronous transcript upload endpoint.", 503)
        return service(request).ingest_transcript(principal, project_id, body)

    @app.get(
        "/api/v1/projects/{project_id}/sources/{source_id}",
        response_model=ManagedSource,
    )
    def get_source(
        project_id: UUID,
        source_id: UUID,
        request: Request,
        principal: CurrentPrincipal,
    ) -> Source:
        if request.app.state.sources is not None:
            actor(request, principal)
            return sources(request).get_source(principal.tenant_id, project_id, source_id)
        return service(request).get_source(principal, project_id, source_id)

    @app.get("/api/v1/projects/{project_id}/sources/{source_id}/transcript", response_model=TranscriptPage)
    def read_transcript(project_id: UUID, source_id: UUID, request: Request, response: Response, principal: CurrentPrincipal,
                        generation: int | None = Query(default=None, ge=1, le=2_147_483_647),
                        page: int = Query(default=1, ge=1, le=MAX_PAGES)):
        store = request.app.state.store
        if not isinstance(store, PostgresStore):
            raise SourceError("transcript_not_configured", "Transcript browsing requires PostgreSQL.", 503)
        response.headers["Cache-Control"] = "no-store"
        return TranscriptRepository(store).read(principal.tenant_id, project_id, actor(request, principal),
                                               source_id, generation=generation, page=page)

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
        return service(request).ask(principal, project_id, body.question, body.source_ids)

    @app.post("/api/v1/projects/{project_id}/conversations", response_model=Conversation, status_code=201)
    def create_conversation(project_id: UUID, body: ConversationCreate, request: Request, principal: CurrentPrincipal):
        return chat(request).create(principal.tenant_id, project_id, actor(request, principal), body)

    @app.get("/api/v1/projects/{project_id}/conversations", response_model=ConversationList)
    def list_conversations(project_id: UUID, request: Request, principal: CurrentPrincipal):
        return chat(request).list(principal.tenant_id, project_id, actor(request, principal))

    @app.get("/api/v1/projects/{project_id}/conversations/{conversation_id}", response_model=History)
    def conversation_history(project_id: UUID, conversation_id: UUID, request: Request, principal: CurrentPrincipal):
        return chat(request).history(principal.tenant_id, project_id, actor(request, principal), conversation_id)

    @app.post("/api/v1/projects/{project_id}/conversations/{conversation_id}/messages", response_class=StreamingResponse,
              responses={200: {"content": {"text/event-stream": {}}}})
    def post_message(project_id: UUID, conversation_id: UUID, body: MessageRequest, request: Request, principal: CurrentPrincipal):
        repository = chat(request)
        actor_id = actor(request, principal)
        turn = repository.replay(principal.tenant_id, project_id, actor_id, conversation_id, body)
        if turn is None:
            response, run = service(request).prepare_answer(principal, project_id, body.question, body.source_ids)
            turn = repository.record(principal.tenant_id, project_id, actor_id, conversation_id, body, response, run)
        return StreamingResponse(deliver(repository, principal.tenant_id, project_id, actor_id, conversation_id, turn),
                                 media_type="text/event-stream", headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @app.get('/api/v1/projects/{project_id}/sources/{source_id}/frames', response_model=VisualGallery)
    def selected_frames(project_id: UUID, source_id: UUID, request: Request, principal: CurrentPrincipal, response: Response):
        response.headers['Cache-Control'] = 'private, no-store'
        return VisualGalleryRepository(sources(request)).gallery(principal.tenant_id, project_id, source_id, actor(request, principal))

    @app.get('/api/v1/projects/{project_id}/frames/{frame_id}/image')
    def selected_frame_image(project_id: UUID, frame_id: UUID, request: Request, principal: CurrentPrincipal):
        data = VisualGalleryRepository(sources(request)).image(principal.tenant_id, project_id, frame_id, actor(request, principal))
        return Response(content=data, media_type='image/png', headers={'Cache-Control': 'private, no-store',
            'X-Content-Type-Options': 'nosniff', 'Cross-Origin-Resource-Policy': 'same-origin'})

    @app.get('/api/v1/projects/{project_id}/sources/{source_id}/descriptions',response_model=DescriptionView)
    def frame_descriptions(project_id:UUID,source_id:UUID,request:Request,principal:CurrentPrincipal):
        return DescriptionRepository(sources(request)).read(principal.tenant_id,project_id,source_id,actor(request,principal))

    @app.get('/api/v1/projects/{project_id}/sources/{source_id}/alignment', response_model=TimelineAlignment)
    def align_evidence(project_id: UUID, source_id: UUID, transcript_source_id: UUID,
                       assert_same_recording: Literal['true'], request: Request, principal: CurrentPrincipal,
                       response: Response, offset_ms: int = Query(default=0, ge=-MAX_OFFSET, le=MAX_OFFSET),
                       visual_generation: int | None = Query(default=None, ge=1, le=2_147_483_647),
                       transcript_generation: int | None = Query(default=None, ge=1, le=2_147_483_647)):
        allowed = {'transcript_source_id', 'assert_same_recording', 'offset_ms', 'visual_generation', 'transcript_generation'}
        if any(key not in allowed or len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise SourceError('invalid_alignment', 'Use one value for each supported comparison field.', 422)
        response.headers['Cache-Control'] = 'private, no-store'
        return AlignmentRepository(sources(request)).read(principal.tenant_id, project_id, actor(request, principal),
            source_id, transcript_source_id, assert_same_recording=assert_same_recording == 'true',
            offset_ms=offset_ms, visual_generation=visual_generation, transcript_generation=transcript_generation)

    @app.get("/api/v1/projects/{project_id}/evidence/{segment_id}", response_model=EvidenceView)
    def inspect_evidence(project_id: UUID, segment_id: UUID, request: Request, principal: CurrentPrincipal):
        return chat(request).evidence(principal.tenant_id, project_id, actor(request, principal), segment_id)

    return app


app = create_app()

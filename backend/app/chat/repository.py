from __future__ import annotations

import hashlib
import json
import logging
from uuid import UUID, uuid4

from ..models import Citation, QuestionResponse, RetrievalRun
from ..metrics import Metrics
from ..postgres import PostgresStore
from ..sources.contracts import SourceError
from ..store import ProjectNotFoundError
from .contracts import ChatTurn, Conversation, ConversationCreate, ConversationList, EvidenceView, History, MessageRequest

LOGGER = logging.getLogger("tutorial_workspace")


class ChatRepository:
    def __init__(self, store: PostgresStore, metrics: Metrics | None = None):
        self.store = store
        self.metrics = metrics

    def _scope(self, connection, tenant: str, project: UUID, actor: UUID, *, write=False):
        self.store._require_membership(connection, tenant, actor)
        lock = " FOR UPDATE" if write else ""
        row = connection.execute(
            "SELECT status FROM projects WHERE tenant_id=%s AND id=%s AND deleted_at IS NULL" + lock,
            (tenant, project),
        ).fetchone()
        if not row:
            raise ProjectNotFoundError("project not found")
        return row

    @staticmethod
    def _conversation(connection, tenant: str, project: UUID, conversation: UUID) -> Conversation:
        row = connection.execute(
            "SELECT * FROM conversations WHERE tenant_id=%s AND project_id=%s AND id=%s",
            (tenant, project, conversation),
        ).fetchone()
        if not row:
            raise ProjectNotFoundError("conversation not found")
        return Conversation.model_validate(row)

    def create(self, tenant: str, project: UUID, actor: UUID, body: ConversationCreate) -> Conversation:
        with self.store._connect() as connection:
            state = self._scope(connection, tenant, project, actor, write=True)
            row = connection.execute(
                "SELECT * FROM conversations WHERE tenant_id=%s AND project_id=%s AND idempotency_key=%s",
                (tenant, project, body.idempotency_key),
            ).fetchone()
            if row:
                if row["title"] != body.title:
                    raise SourceError("idempotency_conflict", "This conversation key was used for different input.", 409)
                return Conversation.model_validate(row)
            if state["status"] != "active":
                raise SourceError("project_archived", "Restore the project before starting a conversation.", 409)
            count = connection.execute("SELECT count(*) AS count FROM conversations WHERE tenant_id=%s AND project_id=%s", (tenant, project)).fetchone()["count"]
            if count >= 100:
                raise SourceError("conversation_limit", "This project supports at most 100 conversations.", 429)
            row = connection.execute(
                """INSERT INTO conversations (tenant_id,project_id,id,actor_user_id,title,idempotency_key)
                   VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                (tenant, project, uuid4(), actor, body.title, body.idempotency_key),
            ).fetchone()
            return Conversation.model_validate(row)

    def list(self, tenant: str, project: UUID, actor: UUID) -> ConversationList:
        with self.store._connect() as connection:
            self._scope(connection, tenant, project, actor)
            rows = connection.execute("SELECT * FROM conversations WHERE tenant_id=%s AND project_id=%s ORDER BY updated_at DESC,id LIMIT 100", (tenant, project)).fetchall()
        return ConversationList(items=[Conversation.model_validate(row) for row in rows])

    @staticmethod
    def _turn(connection, tenant: str, project: UUID, row) -> ChatTurn:
        evidence = connection.execute(
            """SELECT c.score,s.filename,cs.* FROM message_citations c
               JOIN content_segments cs ON cs.tenant_id=c.tenant_id AND cs.project_id=c.project_id AND cs.id=c.segment_id
               JOIN sources s ON s.tenant_id=cs.tenant_id AND s.project_id=cs.project_id AND s.id=cs.source_id
               WHERE c.tenant_id=%s AND c.project_id=%s AND c.turn_id=%s ORDER BY c.ordinal""",
            (tenant, project, row["id"]),
        ).fetchall()
        citations = [Citation(segment_id=item["id"], source_id=item["source_id"], source_filename=item["filename"],
                              start_ms=item["start_ms"], end_ms=item["end_ms"], modality=item["modality"],
                              frame_id=item["frame_id"], score=item["score"], processing_version=item["processing_version"],
                              generation=item["generation"]) for item in evidence]
        response = QuestionResponse(answer=row["answer"], abstained=row["abstained"], citations=citations,
                                    retrieval_run_id=row["retrieval_run_id"], provider=row["provider"], model=row["model"],
                                    processing_version=row["retrieval_version"], latency_ms=row["duration_ms"])
        return ChatTurn(id=row["id"], sequence=row["sequence"], question=row["question"], source_ids=row["source_ids"],
                        response=response, created_at=row["created_at"])

    @staticmethod
    def request_hash(body: MessageRequest) -> str:
        return hashlib.sha256(json.dumps([body.question, [str(value) for value in body.source_ids]]).encode()).hexdigest()

    def replay(self, tenant: str, project: UUID, actor: UUID, conversation: UUID, body: MessageRequest) -> ChatTurn | None:
        with self.store._connect() as connection:
            self._scope(connection, tenant, project, actor)
            self._conversation(connection, tenant, project, conversation)
            row = connection.execute(
                "SELECT * FROM chat_turns WHERE tenant_id=%s AND project_id=%s AND conversation_id=%s AND idempotency_key=%s",
                (tenant, project, conversation, body.idempotency_key),
            ).fetchone()
            if row:
                if row["request_sha256"] != self.request_hash(body):
                    raise SourceError("idempotency_conflict", "This message key was used for different input.", 409)
                return self._turn(connection, tenant, project, row)
        return None

    def record(self, tenant: str, project: UUID, actor: UUID, conversation: UUID, body: MessageRequest,
               response: QuestionResponse, run: RetrievalRun) -> ChatTurn:
        if (run.tenant_id != tenant or run.project_id != project or response.retrieval_run_id != run.id
                or run.cited_segment_ids != [item.segment_id for item in response.citations]):
            raise SourceError("invalid_citation", "The answer evidence could not be validated.", 503)
        with self.store._connect() as connection:
            state = self._scope(connection, tenant, project, actor, write=True)
            self._conversation(connection, tenant, project, conversation)
            existing = connection.execute(
                "SELECT * FROM chat_turns WHERE tenant_id=%s AND project_id=%s AND conversation_id=%s AND idempotency_key=%s",
                (tenant, project, conversation, body.idempotency_key),
            ).fetchone()
            if existing:
                if existing["request_sha256"] != self.request_hash(body):
                    raise SourceError("idempotency_conflict", "This message key was used for different input.", 409)
                return self._turn(connection, tenant, project, existing)
            if state["status"] != "active":
                raise SourceError("project_archived", "Restore the project before asking a question.", 409)
            latest = connection.execute("SELECT coalesce(max(sequence),0) AS sequence FROM chat_turns WHERE tenant_id=%s AND project_id=%s AND conversation_id=%s", (tenant, project, conversation)).fetchone()["sequence"]
            if latest >= 200:
                raise SourceError("message_limit", "Start a new conversation after 200 turns.", 429)
            # Deletion uses this same project lock; no citation can race source removal.
            for citation in response.citations:
                segment = connection.execute(
                    "SELECT * FROM content_segments WHERE tenant_id=%s AND project_id=%s AND id=%s AND source_id=%s",
                    (tenant, project, citation.segment_id, citation.source_id),
                ).fetchone()
                if (not segment or segment["generation"] != citation.generation or
                        segment["processing_version"] != citation.processing_version or
                        segment["start_ms"] != citation.start_ms or segment["end_ms"] != citation.end_ms):
                    raise SourceError("evidence_changed", "The source evidence changed; ask the question again.", 409)
            self.store.insert_retrieval_run(connection, run)
            row = connection.execute(
                """INSERT INTO chat_turns (tenant_id,project_id,conversation_id,id,sequence,actor_user_id,
                   idempotency_key,request_sha256,question,source_ids,answer,abstained,retrieval_run_id,provider,model,
                   prompt_version,retrieval_version,reranker_version,duration_ms,input_characters,output_characters)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                (tenant, project, conversation, uuid4(), latest+1, actor, body.idempotency_key, self.request_hash(body),
                 body.question, body.source_ids, response.answer, response.abstained, run.id, response.provider, response.model,
                 run.prompt_version, run.retrieval_version, run.reranker_version, response.latency_ms,
                 len(body.question), len(response.answer)),
            ).fetchone()
            for index, citation in enumerate(response.citations, 1):
                connection.execute(
                    "INSERT INTO message_citations (tenant_id,project_id,turn_id,ordinal,segment_id,source_id,score) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (tenant, project, row["id"], index, citation.segment_id, citation.source_id, citation.score),
                )
            connection.execute("UPDATE conversations SET updated_at=now() WHERE tenant_id=%s AND project_id=%s AND id=%s", (tenant, project, conversation))
            turn = self._turn(connection, tenant, project, row)
        LOGGER.info(json.dumps({"event": "chat_turn_committed", "tenant_id": tenant, "project_id": str(project),
                                "turn_id": str(turn.id), "outcome": "abstained" if response.abstained else "answered",
                                "latency_ms": response.latency_ms}))
        if self.metrics is not None:
            self.metrics.observe_chat(response.abstained, response.latency_ms)
        return turn

    def history(self, tenant: str, project: UUID, actor: UUID, conversation: UUID) -> History:
        with self.store._connect() as connection:
            self._scope(connection, tenant, project, actor)
            current = self._conversation(connection, tenant, project, conversation)
            rows = connection.execute("SELECT * FROM chat_turns WHERE tenant_id=%s AND project_id=%s AND conversation_id=%s ORDER BY sequence LIMIT 200", (tenant, project, conversation)).fetchall()
            return History(conversation=current, turns=[self._turn(connection, tenant, project, row) for row in rows])

    def readable(self, tenant: str, project: UUID, actor: UUID, conversation: UUID, turn: UUID) -> bool:
        with self.store._connect() as connection:
            row = connection.execute(
                """SELECT 1 FROM chat_turns t JOIN projects p ON p.tenant_id=t.tenant_id AND p.id=t.project_id
                   JOIN memberships m ON m.tenant_id=t.tenant_id AND m.user_id=%s
                   WHERE t.tenant_id=%s AND t.project_id=%s AND t.conversation_id=%s AND t.id=%s
                     AND p.deleted_at IS NULL""", (actor, tenant, project, conversation, turn),
            ).fetchone()
            return row is not None

    def evidence(self, tenant: str, project: UUID, actor: UUID, segment: UUID) -> EvidenceView:
        with self.store._connect() as connection:
            self._scope(connection, tenant, project, actor)
            row = connection.execute(
                """SELECT cs.*, s.filename AS source_filename FROM content_segments cs
                   JOIN sources s ON s.tenant_id=cs.tenant_id AND s.project_id=cs.project_id AND s.id=cs.source_id
                   WHERE cs.tenant_id=%s AND cs.project_id=%s AND cs.id=%s AND s.deleted_at IS NULL""",
                (tenant, project, segment),
            ).fetchone()
            if not row:
                raise ProjectNotFoundError("evidence not found")
            return EvidenceView(segment_id=row["id"], **{key: row[key] for key in EvidenceView.model_fields if key != "segment_id"})

ALTER TABLE retrieval_runs
    ADD COLUMN retrieval_version text NOT NULL DEFAULT 'sprint0-weighted-v1',
    ADD COLUMN reranker_version text NOT NULL DEFAULT 'none',
    ADD COLUMN prompt_version text NOT NULL DEFAULT 'evidence-extractive-v1';

CREATE TABLE conversations (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES users(id),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE CASCADE
);

-- One immutable turn owns both user and assistant messages and model attribution.
CREATE TABLE chat_turns (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    conversation_id uuid NOT NULL,
    id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence BETWEEN 1 AND 200),
    actor_user_id uuid NOT NULL REFERENCES users(id),
    idempotency_key text NOT NULL,
    request_sha256 text NOT NULL,
    question text NOT NULL CHECK (length(question) BETWEEN 2 AND 2000),
    source_ids uuid[] NOT NULL,
    answer text NOT NULL CHECK (length(answer) BETWEEN 1 AND 12000),
    abstained boolean NOT NULL,
    retrieval_run_id uuid NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    prompt_version text NOT NULL,
    retrieval_version text NOT NULL,
    reranker_version text NOT NULL,
    duration_ms integer NOT NULL CHECK (duration_ms >= 0),
    input_characters integer NOT NULL,
    output_characters integer NOT NULL,
    input_tokens integer,
    output_tokens integer,
    billed_usd numeric(12,6) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, conversation_id, sequence),
    UNIQUE (tenant_id, project_id, conversation_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, conversation_id)
        REFERENCES conversations(tenant_id, project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, retrieval_run_id)
        REFERENCES retrieval_runs(tenant_id, project_id, id) ON DELETE CASCADE
);

ALTER TABLE content_segments ADD CONSTRAINT content_segments_source_identity
    UNIQUE (tenant_id, project_id, source_id, id);

CREATE TABLE message_citations (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    turn_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 1 AND 4),
    segment_id uuid NOT NULL,
    source_id uuid NOT NULL,
    score double precision NOT NULL,
    PRIMARY KEY (tenant_id, project_id, turn_id, ordinal),
    FOREIGN KEY (tenant_id, project_id, turn_id)
        REFERENCES chat_turns(tenant_id, project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, source_id, segment_id)
        REFERENCES content_segments(tenant_id, project_id, source_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, source_id)
        REFERENCES sources(tenant_id, project_id, id) ON DELETE CASCADE
);
CREATE INDEX message_citations_source_idx ON message_citations (tenant_id, project_id, source_id);
CREATE INDEX chat_turns_history_idx ON chat_turns (tenant_id, project_id, conversation_id, sequence);

-- Remove quoted derived source text too, not merely the citation relationships.
CREATE FUNCTION remove_source_chat_turns() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM chat_turns t USING message_citations c
    WHERE t.tenant_id=OLD.tenant_id AND t.project_id=OLD.project_id
      AND c.tenant_id=t.tenant_id AND c.project_id=t.project_id AND c.turn_id=t.id
      AND c.source_id=OLD.id;
    RETURN OLD;
END;
$$;
CREATE TRIGGER source_chat_cleanup BEFORE DELETE ON sources
    FOR EACH ROW EXECUTE FUNCTION remove_source_chat_turns();

ALTER TABLE sources
    ADD COLUMN content_sha256 text,
    ADD COLUMN request_sha256 text,
    ADD COLUMN generation integer NOT NULL DEFAULT 1 CHECK (generation > 0),
    ADD COLUMN active_generation integer;
UPDATE sources SET active_generation = 1 WHERE status = 'ready';

ALTER TABLE content_segments
    ADD COLUMN generation integer NOT NULL DEFAULT 1,
    ADD COLUMN cue_start integer,
    ADD COLUMN cue_end integer;

ALTER TABLE processing_jobs
    ADD COLUMN generation integer NOT NULL DEFAULT 1,
    ADD COLUMN actor_user_id uuid REFERENCES users(id),
    ADD COLUMN lease_token uuid,
    ADD COLUMN lease_expires_at timestamptz;
ALTER TABLE processing_attempts ADD COLUMN duration_ms bigint;

CREATE TABLE source_artifacts (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    object_key text NOT NULL,
    content_sha256 text NOT NULL,
    byte_count bigint NOT NULL CHECK (byte_count BETWEEN 1 AND 2000000),
    retention_class text NOT NULL CHECK (retention_class = 'permitted_transcript'),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, source_id),
    FOREIGN KEY (tenant_id, project_id, source_id)
        REFERENCES sources(tenant_id, project_id, id) ON DELETE CASCADE
);

CREATE TABLE processing_versions (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL CHECK (generation > 0),
    processing_version text NOT NULL,
    embedding_provider text NOT NULL,
    embedding_model text NOT NULL,
    embedding_dimensions integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, source_id, generation),
    FOREIGN KEY (tenant_id, project_id, source_id)
        REFERENCES sources(tenant_id, project_id, id) ON DELETE CASCADE
);

CREATE TABLE outbox_events (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL,
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_token uuid,
    lease_expires_at timestamptz,
    sent_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0,
    PRIMARY KEY (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, job_id),
    FOREIGN KEY (tenant_id, project_id, job_id)
        REFERENCES processing_jobs(tenant_id, project_id, id) ON DELETE CASCADE
);
CREATE INDEX outbox_due_idx ON outbox_events (available_at) WHERE sent_at IS NULL;

CREATE TABLE source_commands (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    idempotency_key text NOT NULL,
    command text NOT NULL CHECK (command IN ('retry', 'cancel', 'reprocess')),
    job_id uuid NOT NULL,
    PRIMARY KEY (tenant_id, project_id, source_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id, source_id)
        REFERENCES sources(tenant_id, project_id, id) ON DELETE CASCADE
);

-- Deliberately no project/source FK: this work must survive destructive cascades.
-- No user content, filenames, provider payloads or credentials are retained here.
CREATE TABLE artifact_cleanup (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    actor_user_id uuid NOT NULL,
    object_prefix text NOT NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    available_at timestamptz NOT NULL DEFAULT now(),
    lease_token uuid,
    lease_expires_at timestamptz,
    attempt_count integer NOT NULL DEFAULT 0,
    failure_code text,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz
);
CREATE INDEX cleanup_due_idx ON artifact_cleanup (status, available_at);
CREATE INDEX cleanup_scope_idx ON artifact_cleanup (tenant_id, project_id, id);

CREATE TABLE usage_events (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    job_id uuid NOT NULL,
    generation integer NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    input_characters bigint NOT NULL,
    segment_count integer NOT NULL,
    duration_ms bigint NOT NULL,
    billed_usd numeric(12,6) NOT NULL DEFAULT 0,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, job_id),
    FOREIGN KEY (tenant_id, project_id, job_id)
        REFERENCES processing_jobs(tenant_id, project_id, id) ON DELETE CASCADE
);

ALTER TABLE audit_events DROP CONSTRAINT audit_events_action_check;
ALTER TABLE audit_events ADD CONSTRAINT audit_events_action_check CHECK (
    action IN ('project.created', 'project.renamed', 'project.archived',
              'project.restored', 'project.deleted', 'source.created',
              'source.retry', 'source.cancel', 'source.reprocess', 'source.deleted')
);

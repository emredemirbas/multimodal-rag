CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE tenants (
    id text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE projects (
    id uuid NOT NULL,
    tenant_id text NOT NULL REFERENCES tenants(id),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 120),
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz,
    PRIMARY KEY (tenant_id, id)
);

CREATE TABLE sources (
    id uuid NOT NULL,
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    filename text NOT NULL,
    authorization_mode text NOT NULL CHECK (
        authorization_mode IN ('owner_upload', 'authorized_upload', 'licensed_content')
    ),
    status text NOT NULL,
    processing_version text NOT NULL,
    segment_count integer NOT NULL DEFAULT 0,
    frame_count integer NOT NULL DEFAULT 0,
    idempotency_key text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE CASCADE
);

CREATE TABLE content_segments (
    id uuid NOT NULL,
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    modality text NOT NULL CHECK (modality IN ('transcript', 'frame')),
    start_ms integer NOT NULL CHECK (start_ms >= 0),
    end_ms integer NOT NULL CHECK (end_ms > start_ms),
    text text NOT NULL,
    search_document tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED,
    embedding vector(64) NOT NULL,
    processing_version text NOT NULL,
    frame_id uuid,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, id),
    FOREIGN KEY (tenant_id, project_id, source_id)
        REFERENCES sources(tenant_id, project_id, id) ON DELETE CASCADE
);

CREATE INDEX content_segments_scope_idx
    ON content_segments (tenant_id, project_id, source_id);
CREATE INDEX content_segments_fts_idx
    ON content_segments USING gin (search_document);

CREATE TABLE retrieval_runs (
    id uuid NOT NULL,
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    embedding_provider text NOT NULL,
    embedding_model text NOT NULL,
    answer_provider text NOT NULL,
    answer_model text NOT NULL,
    query_sha256 text NOT NULL CHECK (query_sha256 ~ '^[0-9a-f]{64}$'),
    retrieved_segment_ids uuid[] NOT NULL,
    cited_segment_ids uuid[] NOT NULL,
    candidate_count integer NOT NULL,
    latency_ms integer NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, id),
    FOREIGN KEY (tenant_id, project_id) REFERENCES projects(tenant_id, id) ON DELETE CASCADE
);

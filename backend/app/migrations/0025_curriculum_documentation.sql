-- Explicit per-context approval; a separate fenced command captures one immutable copy.
CREATE TABLE curriculum_document_approvals (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    context_id uuid NOT NULL,
    approved_by uuid NOT NULL REFERENCES users(id),
    consent text NOT NULL CHECK (consent='retrieve_and_retain'),
    approved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-zA-Z0-9_-]{8,128}$'),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    policy jsonb NOT NULL CHECK (jsonb_typeof(policy)='object' AND octet_length(policy::text)<=16000),
    PRIMARY KEY (tenant_id,project_id,id),
    UNIQUE (tenant_id,project_id,idempotency_key),
    FOREIGN KEY (tenant_id,project_id,context_id)
        REFERENCES curriculum_contexts(tenant_id,project_id,id) ON DELETE CASCADE
);
CREATE INDEX curriculum_document_context_idx ON curriculum_document_approvals (tenant_id,project_id,context_id);

CREATE TABLE curriculum_document_commands (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    document_id uuid NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES users(id),
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-zA-Z0-9_-]{8,128}$'),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    command_no integer NOT NULL CHECK (command_no>0),
    status text NOT NULL CHECK (status IN ('capturing','failed','succeeded')),
    lease_token uuid NOT NULL,
    lease_expires_at timestamptz NOT NULL,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    failure_code text CHECK (failure_code IN ('documentation_fetch_timeout','documentation_fetch_unavailable',
        'documentation_fetch_invalid','documentation_fetch_not_allowed','documentation_fetch_busy','documentation_capture_lost')),
    retryable boolean,
    CHECK ((status='capturing' AND finished_at IS NULL AND failure_code IS NULL AND retryable IS NULL)
        OR (status='failed' AND finished_at IS NOT NULL AND failure_code IS NOT NULL AND retryable IS NOT NULL)
        OR (status='succeeded' AND finished_at IS NOT NULL AND failure_code IS NULL AND retryable IS NULL)),
    PRIMARY KEY (tenant_id,project_id,id),
    UNIQUE (tenant_id,project_id,idempotency_key),
    UNIQUE (tenant_id,project_id,document_id,command_no),
    FOREIGN KEY (tenant_id,project_id,document_id)
        REFERENCES curriculum_document_approvals(tenant_id,project_id,id) ON DELETE CASCADE
);
CREATE UNIQUE INDEX curriculum_document_active_idx ON curriculum_document_commands (tenant_id,project_id,document_id)
    WHERE status='capturing';

CREATE TABLE curriculum_document_snapshots (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    document_id uuid NOT NULL,
    snapshot jsonb NOT NULL CHECK (jsonb_typeof(snapshot)='object' AND octet_length(snapshot::text)<=900000),
    raw_sha256 text NOT NULL CHECK (raw_sha256 ~ '^[a-f0-9]{64}$'),
    raw_bytes integer NOT NULL CHECK (raw_bytes BETWEEN 1 AND 512000),
    PRIMARY KEY (tenant_id,project_id,document_id),
    FOREIGN KEY (tenant_id,project_id,document_id)
        REFERENCES curriculum_document_approvals(tenant_id,project_id,id) ON DELETE CASCADE
);

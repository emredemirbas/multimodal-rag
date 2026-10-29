-- Internal project-owned execution state. No ingestion source or live producer.
CREATE TABLE curriculum_runs (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    context_id uuid NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES users(id),
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-zA-Z0-9_-]{8,128}$'),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    workflow_version text NOT NULL CHECK (workflow_version ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$'),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','running','retrying','failed','cancelled')),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count>=0),
    failure_count integer NOT NULL DEFAULT 0 CHECK (failure_count BETWEEN 0 AND 3),
    checkpoint_seq integer NOT NULL DEFAULT 0 CHECK (checkpoint_seq BETWEEN 0 AND 64),
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_token uuid,
    lease_expires_at timestamptz,
    failure_code text CHECK (failure_code IS NULL OR failure_code IN
        ('provider_unavailable','provider_timeout','invalid_output','worker_lost',
         'authorization_revoked','project_archived','cancelled','processing_unavailable')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    PRIMARY KEY (tenant_id,project_id,id),
    UNIQUE (tenant_id,project_id,idempotency_key),
    FOREIGN KEY (tenant_id,project_id,context_id)
        REFERENCES curriculum_contexts(tenant_id,project_id,id) ON DELETE CASCADE,
    CHECK ((lease_token IS NULL)=(lease_expires_at IS NULL)),
    CHECK ((status='running')=(lease_token IS NOT NULL AND lease_expires_at IS NOT NULL)),
    CHECK ((status IN ('failed','cancelled'))=(finished_at IS NOT NULL))
);
CREATE INDEX curriculum_runs_context_idx ON curriculum_runs (tenant_id,project_id,context_id);
CREATE INDEX curriculum_runs_due_idx ON curriculum_runs (status,available_at)
    WHERE status IN ('pending','retrying');
CREATE INDEX curriculum_runs_expired_idx ON curriculum_runs (lease_expires_at) WHERE status='running';

CREATE TABLE curriculum_run_attempts (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    run_id uuid NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number>0),
    lease_token uuid NOT NULL,
    status text NOT NULL DEFAULT 'running' CHECK (status IN ('running','failed','cancelled')),
    failure_code text CHECK (failure_code IS NULL OR failure_code IN
        ('provider_unavailable','provider_timeout','invalid_output','worker_lost',
         'authorization_revoked','project_archived','cancelled','processing_unavailable')),
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    PRIMARY KEY (tenant_id,project_id,run_id,attempt_number),
    UNIQUE (tenant_id,project_id,run_id,lease_token),
    FOREIGN KEY (tenant_id,project_id,run_id)
        REFERENCES curriculum_runs(tenant_id,project_id,id) ON DELETE CASCADE,
    CHECK ((status='running')=(finished_at IS NULL))
);

CREATE TABLE curriculum_run_outbox (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    run_id uuid NOT NULL,
    available_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    lease_token uuid,
    lease_expires_at timestamptz,
    sent_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0 CHECK (publish_attempts>=0),
    PRIMARY KEY (tenant_id,project_id,id),
    UNIQUE (tenant_id,project_id,run_id),
    FOREIGN KEY (tenant_id,project_id,run_id)
        REFERENCES curriculum_runs(tenant_id,project_id,id) ON DELETE CASCADE,
    CHECK ((lease_token IS NULL)=(lease_expires_at IS NULL))
);
CREATE INDEX curriculum_run_outbox_due_idx ON curriculum_run_outbox (available_at) WHERE sent_at IS NULL;

-- Persist the accepted command result; replay never reads a mutable run head.
CREATE TABLE curriculum_run_commands (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    run_id uuid NOT NULL,
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-zA-Z0-9_-]{8,128}$'),
    operation text NOT NULL CHECK (operation IN ('cancel','retry')),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    actor_user_id uuid NOT NULL REFERENCES users(id),
    response jsonb NOT NULL CHECK (jsonb_typeof(response)='object' AND octet_length(response::text)<=16384),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,project_id,run_id,idempotency_key),
    FOREIGN KEY (tenant_id,project_id,run_id)
        REFERENCES curriculum_runs(tenant_id,project_id,id) ON DELETE CASCADE
);

CREATE TABLE curriculum_run_checkpoints (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    run_id uuid NOT NULL,
    sequence integer NOT NULL CHECK (sequence BETWEEN 1 AND 64),
    attempt_number integer NOT NULL,
    stage text NOT NULL CHECK (stage ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$'),
    workflow_version text NOT NULL CHECK (workflow_version ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$'),
    payload jsonb NOT NULL CHECK (jsonb_typeof(payload)='object' AND octet_length(payload::text)<=327680),
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,project_id,run_id,sequence),
    FOREIGN KEY (tenant_id,project_id,run_id,attempt_number)
        REFERENCES curriculum_run_attempts(tenant_id,project_id,run_id,attempt_number) ON DELETE CASCADE
);

CREATE TABLE curriculum_model_calls (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    run_id uuid NOT NULL,
    call_id uuid NOT NULL,
    attempt_number integer NOT NULL,
    purpose text NOT NULL CHECK (purpose ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$'),
    provider text NOT NULL CHECK (provider='ollama-local'),
    model text NOT NULL CHECK (length(model) BETWEEN 1 AND 200),
    model_digest text NOT NULL CHECK (model_digest ~ '^[a-f0-9]{64}$'),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    engine text NOT NULL CHECK (length(engine) BETWEEN 1 AND 200),
    prompt_version text NOT NULL CHECK (prompt_version ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$'),
    input_characters bigint NOT NULL CHECK (input_characters>=0),
    input_tokens bigint CHECK (input_tokens>=0),
    output_tokens bigint CHECK (output_tokens>=0),
    output_characters bigint CHECK (output_characters>=0),
    duration_ms bigint CHECK (duration_ms>=0),
    billed_usd numeric(12,6) NOT NULL DEFAULT 0 CHECK (billed_usd=0),
    status text NOT NULL DEFAULT 'started' CHECK (status IN ('started','succeeded','failed','interrupted')),
    failure_code text CHECK (failure_code IS NULL OR failure_code IN
        ('provider_unavailable','provider_timeout','invalid_output','worker_lost',
         'authorization_revoked','project_archived','cancelled','processing_unavailable')),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    PRIMARY KEY (tenant_id,project_id,run_id,call_id),
    FOREIGN KEY (tenant_id,project_id,run_id,attempt_number)
        REFERENCES curriculum_run_attempts(tenant_id,project_id,run_id,attempt_number) ON DELETE CASCADE,
    CHECK ((status='started')=(finished_at IS NULL))
);

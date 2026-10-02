CREATE TABLE users (
    id uuid PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE auth_identities (
    provider text NOT NULL CHECK (length(provider) BETWEEN 1 AND 64),
    subject text NOT NULL CHECK (length(subject) BETWEEN 1 AND 255),
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (provider, subject)
);

CREATE INDEX auth_identities_user_idx ON auth_identities (user_id);

CREATE TABLE memberships (
    tenant_id text NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role text NOT NULL CHECK (role IN ('owner')),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, user_id)
);

ALTER TABLE projects
    ADD COLUMN status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'archived')),
    ADD COLUMN updated_at timestamptz,
    ADD COLUMN archived_at timestamptz;

UPDATE projects SET updated_at = created_at WHERE updated_at IS NULL;

ALTER TABLE projects
    ALTER COLUMN updated_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL,
    ADD CONSTRAINT projects_archive_state_check CHECK (
        (status = 'active' AND archived_at IS NULL)
        OR (status = 'archived' AND archived_at IS NOT NULL)
    );

CREATE INDEX projects_tenant_status_idx
    ON projects (tenant_id, status, updated_at DESC)
    WHERE deleted_at IS NULL;

ALTER TABLE sources
    ADD COLUMN kind text NOT NULL DEFAULT 'transcript',
    ADD COLUMN provider text NOT NULL DEFAULT 'upload',
    ADD COLUMN canonical_external_id text,
    ADD COLUMN license_mode text NOT NULL DEFAULT 'unspecified',
    ADD COLUMN retention_class text NOT NULL DEFAULT 'derived_only',
    ADD COLUMN failure_code text,
    ADD COLUMN failure_detail text,
    ADD COLUMN metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN updated_at timestamptz,
    ADD COLUMN deleted_at timestamptz;

UPDATE sources SET updated_at = created_at WHERE updated_at IS NULL;

ALTER TABLE sources
    ALTER COLUMN updated_at SET DEFAULT now(),
    ALTER COLUMN updated_at SET NOT NULL,
    ADD CONSTRAINT sources_status_check CHECK (
        status IN (
            'created', 'validating', 'metadata_ready', 'processing', 'indexing',
            'ready', 'failed', 'cancelled', 'reprocessing'
        )
    );

CREATE INDEX sources_scope_status_idx
    ON sources (tenant_id, project_id, status, created_at)
    WHERE deleted_at IS NULL;

CREATE TABLE processing_jobs (
    id uuid NOT NULL,
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid,
    job_type text NOT NULL CHECK (length(job_type) BETWEEN 1 AND 64),
    stage text NOT NULL CHECK (length(stage) BETWEEN 1 AND 64),
    status text NOT NULL CHECK (
        status IN ('pending', 'running', 'retrying', 'succeeded', 'failed', 'cancelled')
    ),
    idempotency_key text NOT NULL CHECK (length(idempotency_key) BETWEEN 8 AND 128),
    progress_percent integer NOT NULL DEFAULT 0
        CHECK (progress_percent BETWEEN 0 AND 100),
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    max_attempts integer NOT NULL DEFAULT 3 CHECK (max_attempts >= 1),
    cancellation_requested_at timestamptz,
    available_at timestamptz NOT NULL DEFAULT now(),
    started_at timestamptz,
    finished_at timestamptz,
    failure_code text,
    failure_detail text,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, idempotency_key),
    FOREIGN KEY (tenant_id, project_id)
        REFERENCES projects(tenant_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, source_id)
        REFERENCES sources(tenant_id, project_id, id) ON DELETE CASCADE
);

CREATE INDEX processing_jobs_claim_idx
    ON processing_jobs (status, available_at, created_at)
    WHERE status IN ('pending', 'retrying');
CREATE INDEX processing_jobs_scope_idx
    ON processing_jobs (tenant_id, project_id, source_id, status);

CREATE TABLE processing_attempts (
    id uuid NOT NULL,
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    attempt_number integer NOT NULL CHECK (attempt_number >= 1),
    status text NOT NULL CHECK (
        status IN ('running', 'succeeded', 'failed', 'cancelled')
    ),
    failure_code text,
    failure_detail text,
    started_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz,
    PRIMARY KEY (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, job_id, attempt_number),
    FOREIGN KEY (tenant_id, project_id, job_id)
        REFERENCES processing_jobs(tenant_id, project_id, id) ON DELETE CASCADE
);

CREATE INDEX processing_attempts_job_idx
    ON processing_attempts (tenant_id, project_id, job_id, attempt_number);

CREATE TABLE audit_events (
    id uuid PRIMARY KEY,
    tenant_id text NOT NULL REFERENCES tenants(id),
    project_id uuid NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES users(id),
    action text NOT NULL CHECK (
        action IN (
            'project.created', 'project.renamed', 'project.archived',
            'project.restored', 'project.deleted'
        )
    ),
    details jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX audit_events_project_idx
    ON audit_events (tenant_id, project_id, created_at DESC);

-- Private ASR staging only. No registration route, raw audio retention or index
-- activation is enabled by this migration. Scope/generation cannot be reassigned.
ALTER TABLE processing_jobs ADD CONSTRAINT asr_job_identity
    UNIQUE (tenant_id, project_id, id, source_id, generation);

CREATE TABLE asr_runs (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL CHECK (generation > 0),
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[a-f0-9]{64}$'),
    input_frames integer NOT NULL CHECK (input_frames BETWEEN 1 AND 9600000),
    requested_language text NOT NULL CHECK (requested_language IN ('auto', 'en', 'tr')),
    provider text NOT NULL,
    model text NOT NULL,
    revision text NOT NULL,
    profile text NOT NULL,
    engine text NOT NULL,
    network_policy text NOT NULL,
    assembly_version text NOT NULL,
    window_count integer GENERATED ALWAYS AS ((input_frames + 479999) / 480000) STORED,
    next_window integer NOT NULL DEFAULT 0 CHECK (next_window >= 0),
    completed_frames integer NOT NULL DEFAULT 0 CHECK (completed_frames >= 0),
    model_duration_ms bigint NOT NULL DEFAULT 0 CHECK (model_duration_ms >= 0),
    segment_count integer NOT NULL DEFAULT 0 CHECK (segment_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (next_window <= window_count AND completed_frames <= input_frames),
    PRIMARY KEY (tenant_id, project_id, job_id),
    UNIQUE (tenant_id, project_id, job_id, source_id, generation),
    FOREIGN KEY (tenant_id, project_id, job_id, source_id, generation)
        REFERENCES processing_jobs (tenant_id, project_id, id, source_id, generation) ON DELETE CASCADE
);

CREATE TABLE asr_windows (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 19),
    input_frames integer NOT NULL CHECK (input_frames BETWEEN 1 AND 480000),
    result jsonb NOT NULL CHECK (jsonb_typeof(result) = 'object' AND octet_length(result::text) <= 65536),
    result_sha256 text NOT NULL CHECK (result_sha256 ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (tenant_id, project_id, job_id, ordinal),
    FOREIGN KEY (tenant_id, project_id, job_id, source_id, generation)
        REFERENCES asr_runs (tenant_id, project_id, job_id, source_id, generation) ON DELETE CASCADE
);

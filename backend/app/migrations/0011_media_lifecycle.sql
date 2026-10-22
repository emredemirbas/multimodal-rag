CREATE TABLE audio_inputs (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL,
    actor_user_id uuid NOT NULL,
    object_key text NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
    byte_count integer NOT NULL CHECK (byte_count BETWEEN 1 AND 20000000),
    input_frames integer NOT NULL CHECK (input_frames BETWEEN 1 AND 9600000),
    requested_language text NOT NULL CHECK (requested_language IN ('auto', 'en', 'tr')),
    expires_at timestamptz NOT NULL DEFAULT now() + interval '1 hour',
    cleanup_id uuid REFERENCES artifact_cleanup(id),
    deleted_at timestamptz,
    PRIMARY KEY (tenant_id, project_id, job_id),
    FOREIGN KEY (tenant_id, project_id, job_id, source_id, generation)
        REFERENCES processing_jobs (tenant_id, project_id, id, source_id, generation) ON DELETE CASCADE
);
CREATE INDEX audio_inputs_expiry_idx ON audio_inputs (expires_at) WHERE cleanup_id IS NULL;

ALTER TABLE asr_runs ADD CONSTRAINT asr_source_identity UNIQUE (tenant_id, project_id, job_id, source_id);
ALTER TABLE asr_runs
    ADD COLUMN transcript_job_id uuid,
    ADD COLUMN adopted_sha256 text CHECK (adopted_sha256 ~ '^[a-f0-9]{64}$'),
    ADD COLUMN completed_at timestamptz,
    ADD CONSTRAINT asr_transcript_job FOREIGN KEY (tenant_id, project_id, transcript_job_id, source_id, generation)
        REFERENCES processing_jobs (tenant_id, project_id, id, source_id, generation) ON DELETE CASCADE;

ALTER TABLE source_artifacts
    ADD COLUMN asr_job_id uuid,
    ADD CONSTRAINT artifact_asr_origin FOREIGN KEY (tenant_id, project_id, asr_job_id, source_id)
        REFERENCES asr_runs (tenant_id, project_id, job_id, source_id);
ALTER TABLE processing_versions
    ADD COLUMN asr_job_id uuid,
    ADD CONSTRAINT version_asr_origin FOREIGN KEY (tenant_id, project_id, asr_job_id, source_id)
        REFERENCES asr_runs (tenant_id, project_id, job_id, source_id);

ALTER TABLE usage_events ADD COLUMN input_audio_frames integer CHECK (input_audio_frames BETWEEN 1 AND 9600000);

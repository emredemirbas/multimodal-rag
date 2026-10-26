-- Private raw input lifecycle only; no public MP4 upload or published evidence.
CREATE TABLE video_inputs (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL,
    actor_user_id uuid NOT NULL,
    object_key text NOT NULL,
    content_sha256 text NOT NULL CHECK (content_sha256 ~ '^[a-f0-9]{64}$'),
    byte_count integer NOT NULL CHECK (byte_count BETWEEN 24 AND 100000000),
    requested_language text NOT NULL CHECK (requested_language IN ('en', 'tr', 'en+tr')),
    expires_at timestamptz NOT NULL,
    cleanup_id uuid,
    deleted_at timestamptz,
    PRIMARY KEY (tenant_id, project_id, job_id),
    FOREIGN KEY (tenant_id, project_id, job_id, source_id, generation)
        REFERENCES processing_jobs (tenant_id, project_id, id, source_id, generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, cleanup_id)
        REFERENCES artifact_cleanup (tenant_id, project_id, id),
    CHECK (deleted_at IS NULL OR cleanup_id IS NOT NULL)
);
CREATE INDEX video_inputs_expiry_idx ON video_inputs (expires_at) WHERE cleanup_id IS NULL;
ALTER TABLE visual_runs ADD COLUMN prepared_at timestamptz,
    ADD CONSTRAINT visual_prepared_snapshot CHECK (prepared_at IS NULL OR saved_at IS NOT NULL);
ALTER TABLE usage_events
    ADD COLUMN input_video_bytes integer CHECK (input_video_bytes BETWEEN 24 AND 100000000),
    ADD COLUMN selected_frame_count integer CHECK (selected_frame_count BETWEEN 1 AND 20);

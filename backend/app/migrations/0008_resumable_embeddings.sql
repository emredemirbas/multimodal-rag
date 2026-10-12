ALTER TABLE processing_jobs
    ADD COLUMN target_embedding_space text CHECK (target_embedding_space IN (
        'signed-hash-v1:64',
        'qwen3-0.6b:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d:1024:query-v1'
    )),
    ADD COLUMN delivery_count integer NOT NULL DEFAULT 0 CHECK (delivery_count >= 0),
    ADD COLUMN continuation_pending boolean NOT NULL DEFAULT false,
    ADD COLUMN processed_segments integer NOT NULL DEFAULT 0 CHECK (processed_segments >= 0),
    ADD COLUMN total_segments integer NOT NULL DEFAULT 0 CHECK (total_segments BETWEEN 0 AND 10000),
    ADD COLUMN chunk_manifest_sha256 text CHECK (chunk_manifest_sha256 ~ '^[a-f0-9]{64}$'),
    ADD COLUMN checkpoint_input_tokens bigint DEFAULT 0 CHECK (checkpoint_input_tokens >= 0),
    ADD CONSTRAINT checkpoint_cursor_bounds CHECK (processed_segments <= total_segments),
    ADD CONSTRAINT checkpoint_job_identity UNIQUE (tenant_id, project_id, id, source_id, generation, target_embedding_space);
UPDATE processing_jobs SET delivery_count = attempt_count;

-- Historical attempt_number remains the execution/delivery sequence; retry
-- attempt_count is now separate so normal bounded continuations are not failures.
ALTER TABLE processing_attempts DROP CONSTRAINT processing_attempts_status_check;
ALTER TABLE processing_attempts ADD CONSTRAINT processing_attempts_status_check
    CHECK (status IN ('running', 'succeeded', 'failed', 'cancelled', 'checkpointed'));

CREATE TABLE embedding_checkpoints (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 9999),
    segment_id uuid NOT NULL,
    start_ms integer NOT NULL CHECK (start_ms >= 0),
    end_ms integer NOT NULL CHECK (end_ms > start_ms),
    text text NOT NULL CHECK (length(text) BETWEEN 1 AND 1200),
    cue_start integer NOT NULL CHECK (cue_start >= 0),
    cue_end integer NOT NULL CHECK (cue_end >= cue_start),
    processing_version text NOT NULL,
    embedding_space text NOT NULL CHECK (embedding_space =
        'qwen3-0.6b:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d:1024:query-v1'),
    embedding vector(1024) NOT NULL,
    PRIMARY KEY (tenant_id, project_id, job_id, ordinal),
    UNIQUE (tenant_id, project_id, job_id, segment_id),
    FOREIGN KEY (tenant_id, project_id, job_id, source_id, generation, embedding_space)
        REFERENCES processing_jobs (tenant_id, project_id, id, source_id, generation, target_embedding_space) ON DELETE CASCADE
);
-- No retrieval or evidence view reads this private table. Promotion is atomic.

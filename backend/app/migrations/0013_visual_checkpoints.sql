-- Private bounded staging only: no public video registration or evidence.
CREATE TABLE visual_runs (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL CHECK (generation > 0),
    actor_user_id uuid NOT NULL,
    authorization_mode text NOT NULL CHECK (authorization_mode IN ('owner_upload', 'authorized_upload', 'licensed_content')),
    input_sha256 text NOT NULL CHECK (input_sha256 ~ '^[a-f0-9]{64}$'),
    input_bytes integer NOT NULL CHECK (input_bytes BETWEEN 24 AND 100000000),
    identity jsonb NOT NULL CHECK (jsonb_typeof(identity) = 'object' AND octet_length(identity::text) <= 4096),
    profile text NOT NULL CHECK (profile ~ '^local-visual-v1:[a-f0-9]{64}$'),
    checkpoint_version text NOT NULL,
    processing_expires_at timestamptz NOT NULL,
    video_metadata jsonb CHECK (jsonb_typeof(video_metadata) = 'object' AND octet_length(video_metadata::text) <= 2048),
    candidates integer CHECK (candidates BETWEEN 1 AND 20),
    saved_frames integer NOT NULL DEFAULT 0 CHECK (saved_frames BETWEEN 0 AND 20),
    image_bytes integer NOT NULL DEFAULT 0 CHECK (image_bytes BETWEEN 0 AND 12000000),
    ocr_characters integer NOT NULL DEFAULT 0 CHECK (ocr_characters BETWEEN 0 AND 320000),
    result_sha256 text CHECK (result_sha256 ~ '^[a-f0-9]{64}$'),
    saved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (processing_expires_at > created_at AND processing_expires_at <= created_at + interval '1 hour'),
    CHECK ((saved_at IS NULL AND result_sha256 IS NULL AND video_metadata IS NULL AND candidates IS NULL
            AND saved_frames = 0 AND image_bytes = 0 AND ocr_characters = 0)
        OR (saved_at IS NOT NULL AND result_sha256 IS NOT NULL AND video_metadata IS NOT NULL
            AND candidates IS NOT NULL AND saved_frames BETWEEN 1 AND candidates AND image_bytes > 0)),
    PRIMARY KEY (tenant_id, project_id, job_id),
    UNIQUE (tenant_id, project_id, job_id, source_id, generation),
    FOREIGN KEY (tenant_id, project_id, job_id, source_id, generation)
        REFERENCES processing_jobs (tenant_id, project_id, id, source_id, generation) ON DELETE CASCADE
);

CREATE TABLE visual_checkpoint_frames (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    job_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 19),
    sample_target_ms integer NOT NULL CHECK (sample_target_ms BETWEEN 0 AND 599999),
    timestamp_ms integer NOT NULL CHECK (timestamp_ms BETWEEN sample_target_ms AND least(sample_target_ms + 1000, 599999)),
    width integer NOT NULL CHECK (width BETWEEN 1 AND 960),
    height integer NOT NULL CHECK (height BETWEEN 1 AND 540),
    image bytea NOT NULL CHECK (octet_length(image) BETWEEN 1 AND 600000),
    image_sha256 text NOT NULL CHECK (image_sha256 ~ '^[a-f0-9]{64}$'),
    ocr_text text NOT NULL CHECK (length(ocr_text) <= 16000 AND octet_length(ocr_text) <= 64000),
    text_sha256 text NOT NULL CHECK (text_sha256 ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (tenant_id, project_id, job_id, ordinal),
    FOREIGN KEY (tenant_id, project_id, job_id, source_id, generation)
        REFERENCES visual_runs (tenant_id, project_id, job_id, source_id, generation) ON DELETE CASCADE
);

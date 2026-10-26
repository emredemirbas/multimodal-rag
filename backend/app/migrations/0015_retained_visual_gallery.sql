CREATE TABLE visual_publications (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    job_id uuid NOT NULL,
    generation integer NOT NULL,
    visual_job_id uuid NOT NULL,
    visual_generation integer NOT NULL,
    result_sha256 text NOT NULL CHECK (result_sha256 ~ '^[a-f0-9]{64}$'),
    processing_version text NOT NULL CHECK (processing_version = 'retained-frames-v1'),
    published_at timestamptz,
    PRIMARY KEY (tenant_id,project_id,job_id),
    UNIQUE (tenant_id,project_id,job_id,source_id,generation),
    UNIQUE (tenant_id,project_id,source_id,visual_job_id),
    FOREIGN KEY (tenant_id,project_id,job_id,source_id,generation)
        REFERENCES processing_jobs(tenant_id,project_id,id,source_id,generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,visual_job_id,source_id,visual_generation)
        REFERENCES visual_runs(tenant_id,project_id,job_id,source_id,generation) ON DELETE CASCADE
);

CREATE TABLE retained_visual_frames (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    job_id uuid NOT NULL,
    generation integer NOT NULL,
    id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 19),
    timestamp_ms integer NOT NULL CHECK (timestamp_ms BETWEEN 0 AND 599999),
    sample_target_ms integer NOT NULL CHECK (sample_target_ms BETWEEN 0 AND timestamp_ms),
    width integer NOT NULL CHECK (width BETWEEN 1 AND 960),
    height integer NOT NULL CHECK (height BETWEEN 1 AND 540),
    object_key text NOT NULL,
    byte_count integer NOT NULL CHECK (byte_count BETWEEN 1 AND 600000),
    image_sha256 text NOT NULL CHECK (image_sha256 ~ '^[a-f0-9]{64}$'),
    ocr_text text NOT NULL CHECK (length(ocr_text)<=16000 AND octet_length(ocr_text)<=64000),
    text_sha256 text NOT NULL CHECK (text_sha256 ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (tenant_id,project_id,id),
    UNIQUE (tenant_id,project_id,job_id,ordinal),
    FOREIGN KEY (tenant_id,project_id,job_id,source_id,generation)
        REFERENCES visual_publications(tenant_id,project_id,job_id,source_id,generation) ON DELETE CASCADE
);

ALTER TABLE source_commands DROP CONSTRAINT source_commands_command_check;
ALTER TABLE source_commands ADD CONSTRAINT source_commands_command_check
    CHECK (command IN ('retry','cancel','reprocess','publish_visual'));

-- Opt-in orchestration only; existing private/manual registrations are unchanged.
ALTER TABLE video_inputs ADD UNIQUE (tenant_id,project_id,source_id,job_id,generation,actor_user_id);

CREATE TABLE video_workflows (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    visual_job_id uuid NOT NULL,
    visual_generation integer NOT NULL,
    actor_user_id uuid NOT NULL,
    workflow_version text NOT NULL CHECK (workflow_version='selected-ocr-v1'),
    target_embedding_space text NOT NULL CHECK (target_embedding_space IN (
        'signed-hash-v1:64',
        'qwen3-0.6b:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d:1024:query-v1'
    )),
    publication_job_id uuid,
    publication_generation integer,
    index_job_id uuid,
    index_generation integer,
    PRIMARY KEY (tenant_id,project_id,source_id),
    FOREIGN KEY (tenant_id,project_id,source_id,visual_job_id,visual_generation,actor_user_id)
        REFERENCES video_inputs(tenant_id,project_id,source_id,job_id,generation,actor_user_id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id,publication_job_id,publication_generation)
        REFERENCES visual_publications(tenant_id,project_id,source_id,job_id,generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id,index_job_id,index_generation)
        REFERENCES visual_index_runs(tenant_id,project_id,source_id,job_id,generation) ON DELETE CASCADE,
    CHECK ((publication_job_id IS NULL) = (publication_generation IS NULL)),
    CHECK ((index_job_id IS NULL) = (index_generation IS NULL)),
    CHECK (publication_generation IS NULL OR publication_generation>visual_generation),
    CHECK (index_generation IS NULL OR (publication_generation IS NOT NULL AND index_generation>publication_generation))
);

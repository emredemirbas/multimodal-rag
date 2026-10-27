CREATE TABLE visual_description_runs (
    tenant_id text NOT NULL, project_id uuid NOT NULL, source_id uuid NOT NULL,
    job_id uuid NOT NULL, generation integer NOT NULL, actor_user_id uuid NOT NULL REFERENCES users(id),
    publication_job_id uuid NOT NULL, publication_generation integer NOT NULL,
    model_digest text NOT NULL CHECK (model_digest ~ '^[a-f0-9]{64}$'),
    prompt_version text NOT NULL CHECK (prompt_version='retained-frame-description-v1'),
    target_embedding_space text NOT NULL,
    identity jsonb, identity_sha256 text CHECK (identity_sha256 ~ '^[a-f0-9]{64}$'), completed_at timestamptz,
    index_job_id uuid, index_generation integer,
    PRIMARY KEY (tenant_id,project_id,job_id),
    UNIQUE (tenant_id,project_id,source_id,job_id,generation),
    UNIQUE (tenant_id,project_id,source_id,job_id),
    FOREIGN KEY (tenant_id,project_id,job_id,source_id,generation)
        REFERENCES processing_jobs(tenant_id,project_id,id,source_id,generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id,publication_job_id,publication_generation)
        REFERENCES visual_publications(tenant_id,project_id,source_id,job_id,generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id,index_job_id,index_generation)
        REFERENCES visual_index_runs(tenant_id,project_id,source_id,job_id,generation) ON DELETE CASCADE,
    CHECK ((index_job_id IS NULL)=(index_generation IS NULL)),
    CHECK (completed_at IS NULL OR identity IS NOT NULL),
    CHECK ((identity IS NULL)=(identity_sha256 IS NULL)),
    CHECK (identity IS NULL OR (jsonb_typeof(identity)='object' AND identity->>'model_digest'=model_digest))
);
CREATE TABLE visual_descriptions (
    tenant_id text NOT NULL, project_id uuid NOT NULL, source_id uuid NOT NULL,
    job_id uuid NOT NULL, generation integer NOT NULL,
    frame_id uuid NOT NULL, publication_job_id uuid NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 19),
    image_sha256 text NOT NULL CHECK (image_sha256 ~ '^[a-f0-9]{64}$'),
    description jsonb NOT NULL CHECK (jsonb_typeof(description)='object' AND octet_length(description::text)<=8192),
    description_sha256 text NOT NULL CHECK (description_sha256 ~ '^[a-f0-9]{64}$'),
    input_tokens integer CHECK (input_tokens BETWEEN 0 AND 100000),
    output_tokens integer CHECK (output_tokens BETWEEN 0 AND 100000),
    duration_ms integer NOT NULL CHECK (duration_ms BETWEEN 0 AND 210000),
    PRIMARY KEY (tenant_id,project_id,job_id,ordinal),
    UNIQUE (tenant_id,project_id,job_id,frame_id),
    FOREIGN KEY (tenant_id,project_id,source_id,job_id,generation)
        REFERENCES visual_description_runs(tenant_id,project_id,source_id,job_id,generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id,frame_id,publication_job_id)
        REFERENCES retained_visual_frames(tenant_id,project_id,source_id,id,job_id) ON DELETE CASCADE
);
ALTER TABLE visual_index_runs ADD COLUMN description_job_id uuid;
ALTER TABLE visual_index_runs ADD FOREIGN KEY (tenant_id,project_id,source_id,description_job_id)
    REFERENCES visual_description_runs(tenant_id,project_id,source_id,job_id) ON DELETE CASCADE;
ALTER TABLE visual_index_runs DROP CONSTRAINT visual_index_runs_processing_version_check;
ALTER TABLE visual_index_runs ADD CHECK (
    (processing_version='visual-ocr-chunks-v1' AND description_job_id IS NULL) OR
    (processing_version='visual-evidence-chunks-v2' AND description_job_id IS NOT NULL));
ALTER TABLE visual_index_chunks DROP CONSTRAINT visual_index_chunks_ordinal_check;
ALTER TABLE visual_index_chunks ADD CHECK (ordinal BETWEEN 0 AND 299);
ALTER TABLE processing_versions ADD COLUMN visual_description_job_id uuid;
ALTER TABLE processing_versions ADD FOREIGN KEY (tenant_id,project_id,source_id,visual_description_job_id)
    REFERENCES visual_description_runs(tenant_id,project_id,source_id,job_id) ON DELETE CASCADE;
ALTER TABLE usage_events
    ADD COLUMN prompt_version text,
    ADD COLUMN output_tokens integer CHECK (output_tokens>=0),
    ADD COLUMN input_image_count integer CHECK (input_image_count BETWEEN 1 AND 20),
    ADD COLUMN input_image_bytes integer CHECK (input_image_bytes BETWEEN 1 AND 12000000);
ALTER TABLE source_commands DROP CONSTRAINT source_commands_command_check;
ALTER TABLE source_commands ADD CHECK (command IN ('retry','cancel','reprocess','publish_visual','index_visual','describe_visual'));
ALTER TABLE audit_events DROP CONSTRAINT audit_events_action_check;
ALTER TABLE audit_events ADD CHECK (action IN ('project.created','project.renamed','project.archived','project.restored','project.deleted',
    'source.created','source.retry','source.cancel','source.reprocess','source.deleted','source.index_visual','source.describe_visual'));
CREATE OR REPLACE VIEW visual_index_origins AS
SELECT v.tenant_id,v.project_id,v.source_id,v.generation,
       jsonb_build_object('machine_generated',true,'human_reviewed',false,
         'job_id',r.job_id,'generation',r.generation,'profile',r.profile,
         'language',r.identity->'language','engines',r.identity->'engines',
         'checkpoint_version',r.checkpoint_version,'prepared_at',r.prepared_at) ||
       CASE WHEN d.job_id IS NULL THEN '{}'::jsonb ELSE jsonb_build_object('description',jsonb_build_object(
         'job_id',d.job_id,'generation',d.generation,'provider',d.identity->>'provider',
         'model',d.identity->>'model','model_digest',d.model_digest,'engine',d.identity->>'engine',
         'prompt_version',d.prompt_version,'completed_at',d.completed_at)) END AS origin
FROM processing_versions v
JOIN visual_publications p ON p.tenant_id=v.tenant_id AND p.project_id=v.project_id
  AND p.source_id=v.source_id AND p.job_id=v.visual_publication_job_id AND p.published_at IS NOT NULL
JOIN visual_runs r ON r.tenant_id=p.tenant_id AND r.project_id=p.project_id
  AND r.source_id=p.source_id AND r.job_id=p.visual_job_id AND r.generation=p.visual_generation AND r.prepared_at IS NOT NULL
LEFT JOIN visual_description_runs d ON d.tenant_id=v.tenant_id AND d.project_id=v.project_id
  AND d.source_id=v.source_id AND d.job_id=v.visual_description_job_id AND d.completed_at IS NOT NULL;

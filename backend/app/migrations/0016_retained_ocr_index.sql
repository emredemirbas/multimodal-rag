ALTER TABLE visual_publications ADD UNIQUE (tenant_id,project_id,source_id,job_id,generation);
ALTER TABLE visual_publications ADD UNIQUE (tenant_id,project_id,source_id,job_id);
ALTER TABLE retained_visual_frames ADD UNIQUE (tenant_id,project_id,source_id,id,job_id);

CREATE TABLE visual_index_runs (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    job_id uuid NOT NULL,
    generation integer NOT NULL,
    publication_job_id uuid NOT NULL,
    publication_generation integer NOT NULL,
    processing_version text NOT NULL CHECK (processing_version='visual-ocr-chunks-v1'),
    PRIMARY KEY (tenant_id,project_id,job_id),
    UNIQUE (tenant_id,project_id,source_id,job_id,generation),
    FOREIGN KEY (tenant_id,project_id,job_id,source_id,generation)
        REFERENCES processing_jobs(tenant_id,project_id,id,source_id,generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id,publication_job_id,publication_generation)
        REFERENCES visual_publications(tenant_id,project_id,source_id,job_id,generation) ON DELETE CASCADE
);

CREATE TABLE visual_index_chunks (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    source_id uuid NOT NULL,
    job_id uuid NOT NULL,
    generation integer NOT NULL,
    ordinal integer NOT NULL CHECK (ordinal BETWEEN 0 AND 279),
    segment_id uuid NOT NULL,
    frame_id uuid NOT NULL,
    publication_job_id uuid NOT NULL,
    start_ms integer NOT NULL CHECK (start_ms BETWEEN 0 AND 599999),
    text_offset integer NOT NULL CHECK (text_offset BETWEEN 0 AND 15999),
    text text NOT NULL CHECK (length(text) BETWEEN 1 AND 1200),
    embedding_space text NOT NULL,
    embedding vector NOT NULL,
    embedding_sha256 text NOT NULL CHECK (embedding_sha256 ~ '^[a-f0-9]{64}$'),
    PRIMARY KEY (tenant_id,project_id,job_id,ordinal),
    FOREIGN KEY (tenant_id,project_id,source_id,job_id,generation)
        REFERENCES visual_index_runs(tenant_id,project_id,source_id,job_id,generation) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id,frame_id,publication_job_id)
        REFERENCES retained_visual_frames(tenant_id,project_id,source_id,id,job_id) ON DELETE CASCADE,
    CHECK ((embedding_space='signed-hash-v1:64' AND vector_dims(embedding)=64) OR
           (embedding_space='qwen3-0.6b:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d:1024:query-v1'
            AND vector_dims(embedding)=1024))
);

ALTER TABLE processing_versions ADD COLUMN visual_publication_job_id uuid;
ALTER TABLE processing_versions ADD UNIQUE (tenant_id,project_id,source_id,generation,visual_publication_job_id);
ALTER TABLE processing_versions ADD FOREIGN KEY (tenant_id,project_id,source_id,visual_publication_job_id)
    REFERENCES visual_publications(tenant_id,project_id,source_id,job_id) ON DELETE CASCADE;
ALTER TABLE content_segments ADD COLUMN visual_publication_job_id uuid;
-- Replace only the historical strict interval check; frames are point observations.
DO $$ DECLARE timeline_check text; BEGIN
    SELECT conname INTO STRICT timeline_check FROM pg_constraint
    WHERE conrelid='content_segments'::regclass AND contype='c'
      AND pg_get_constraintdef(oid)='CHECK ((end_ms > start_ms))';
    EXECUTE format('ALTER TABLE content_segments DROP CONSTRAINT %I',timeline_check);
END $$;
ALTER TABLE content_segments ADD CONSTRAINT content_evidence_timeline_check
    CHECK (end_ms>start_ms OR (modality='frame' AND end_ms=start_ms));
ALTER TABLE content_segments ADD FOREIGN KEY (tenant_id,project_id,source_id,generation,visual_publication_job_id)
    REFERENCES processing_versions(tenant_id,project_id,source_id,generation,visual_publication_job_id) ON DELETE CASCADE;
ALTER TABLE content_segments ADD FOREIGN KEY (tenant_id,project_id,source_id,frame_id,visual_publication_job_id)
    REFERENCES retained_visual_frames(tenant_id,project_id,source_id,id,job_id) ON DELETE CASCADE;
ALTER TABLE content_segments ADD CHECK (visual_publication_job_id IS NULL OR (modality='frame' AND frame_id IS NOT NULL AND end_ms=start_ms));

ALTER TABLE source_commands DROP CONSTRAINT source_commands_command_check;
ALTER TABLE source_commands ADD CONSTRAINT source_commands_command_check
    CHECK (command IN ('retry','cancel','reprocess','publish_visual','index_visual'));
ALTER TABLE audit_events DROP CONSTRAINT audit_events_action_check;
ALTER TABLE audit_events ADD CONSTRAINT audit_events_action_check CHECK (
    action IN ('project.created','project.renamed','project.archived','project.restored','project.deleted',
              'source.created','source.retry','source.cancel','source.reprocess','source.deleted','source.index_visual')
);

-- Public projection only; the callers still authorize and filter both scopes.
CREATE VIEW visual_index_origins AS
SELECT v.tenant_id,v.project_id,v.source_id,v.generation,
       jsonb_build_object('machine_generated',true,'human_reviewed',false,
         'job_id',r.job_id,'generation',r.generation,'profile',r.profile,
         'language',r.identity->'language','engines',r.identity->'engines',
         'checkpoint_version',r.checkpoint_version,'prepared_at',r.prepared_at) AS origin
FROM processing_versions v
JOIN visual_publications p ON p.tenant_id=v.tenant_id AND p.project_id=v.project_id
  AND p.source_id=v.source_id AND p.job_id=v.visual_publication_job_id AND p.published_at IS NOT NULL
JOIN visual_runs r ON r.tenant_id=p.tenant_id AND r.project_id=p.project_id
  AND r.source_id=p.source_id AND r.job_id=p.visual_job_id AND r.generation=p.visual_generation AND r.prepared_at IS NOT NULL;

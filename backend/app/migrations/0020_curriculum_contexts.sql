-- Immutable copied tutorial context; generation/coverage/model work comes later.
CREATE TABLE curriculum_contexts (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES users(id),
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-zA-Z0-9_-]{8,128}$'),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    request jsonb NOT NULL CHECK (jsonb_typeof(request)='object' AND octet_length(request::text)<=20000),
    tutorial_snapshots jsonb NOT NULL CHECK (jsonb_typeof(tutorial_snapshots)='array'
        AND jsonb_array_length(tutorial_snapshots) BETWEEN 1 AND 20
        AND octet_length(tutorial_snapshots::text)<=4000000),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,project_id,id),
    UNIQUE (tenant_id,project_id,idempotency_key),
    FOREIGN KEY (tenant_id,project_id) REFERENCES projects(tenant_id,id) ON DELETE CASCADE
);

CREATE TABLE curriculum_context_sources (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    context_id uuid NOT NULL,
    source_id uuid NOT NULL,
    generation integer NOT NULL CHECK (generation>0),
    processing_version text NOT NULL CHECK (length(processing_version) BETWEEN 1 AND 200),
    PRIMARY KEY (tenant_id,project_id,context_id,source_id),
    FOREIGN KEY (tenant_id,project_id,context_id)
        REFERENCES curriculum_contexts(tenant_id,project_id,id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,source_id)
        REFERENCES sources(tenant_id,project_id,id) ON DELETE CASCADE
);
CREATE INDEX curriculum_context_sources_source_idx
    ON curriculum_context_sources (tenant_id,project_id,source_id);

-- Remove copied source text, not merely the dependency rows. A multi-source
-- context is deleted in full when any dependency is deleted.
CREATE FUNCTION remove_source_curriculum_contexts() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM curriculum_contexts c USING curriculum_context_sources d
    WHERE c.tenant_id=OLD.tenant_id AND c.project_id=OLD.project_id
      AND d.tenant_id=c.tenant_id AND d.project_id=c.project_id AND d.context_id=c.id
      AND d.source_id=OLD.id;
    RETURN OLD;
END;
$$;
CREATE TRIGGER source_curriculum_cleanup BEFORE DELETE ON sources
    FOR EACH ROW EXECUTE FUNCTION remove_source_curriculum_contexts();

-- Editable heads point at append-only revisions of an immutable saved context.
CREATE TABLE curriculum_drafts (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    context_id uuid NOT NULL,
    actor_user_id uuid NOT NULL REFERENCES users(id),
    current_revision integer NOT NULL CHECK (current_revision > 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,project_id,id),
    FOREIGN KEY (tenant_id,project_id,context_id)
        REFERENCES curriculum_contexts(tenant_id,project_id,id) ON DELETE CASCADE
);
CREATE INDEX curriculum_drafts_context_idx
    ON curriculum_drafts (tenant_id,project_id,context_id);

CREATE TABLE curriculum_draft_revisions (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    draft_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    actor_user_id uuid NOT NULL REFERENCES users(id),
    content jsonb NOT NULL CHECK (jsonb_typeof(content)='object'
        AND octet_length(content::text)<=300000),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,project_id,draft_id,revision),
    FOREIGN KEY (tenant_id,project_id,draft_id)
        REFERENCES curriculum_drafts(tenant_id,project_id,id) ON DELETE CASCADE
);

-- Keep each accepted result, rather than making retry depend on the current head.
-- The hash includes operation, target, expected revision and exact content.
CREATE TABLE curriculum_draft_commands (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    idempotency_key text NOT NULL CHECK (idempotency_key ~ '^[a-zA-Z0-9_-]{8,128}$'),
    operation text NOT NULL CHECK (operation IN ('create','replace')),
    request_sha256 text NOT NULL CHECK (request_sha256 ~ '^[a-f0-9]{64}$'),
    draft_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    actor_user_id uuid NOT NULL REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,project_id,idempotency_key),
    FOREIGN KEY (tenant_id,project_id,draft_id,revision)
        REFERENCES curriculum_draft_revisions(tenant_id,project_id,draft_id,revision) ON DELETE CASCADE
);
CREATE INDEX curriculum_draft_commands_revision_idx
    ON curriculum_draft_commands (tenant_id,project_id,draft_id,revision);

-- Explicit learner acceptance pins an existing immutable draft revision.
CREATE TABLE curriculum_assignment_versions (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    context_id uuid NOT NULL,
    draft_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision > 0),
    activated_by uuid NOT NULL REFERENCES users(id),
    activated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (tenant_id,project_id,id),
    UNIQUE (tenant_id,project_id,draft_id,revision),
    FOREIGN KEY (tenant_id,project_id,context_id,draft_id)
        REFERENCES curriculum_drafts(tenant_id,project_id,context_id,id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,draft_id,revision)
        REFERENCES curriculum_draft_revisions(tenant_id,project_id,draft_id,revision) ON DELETE CASCADE
);

-- Retain the existing project-wide draft command-key namespace. Direct version
-- removal also removes activation receipts; old create/replace rows stay valid.
ALTER TABLE curriculum_draft_commands
    DROP CONSTRAINT curriculum_draft_commands_operation_check,
    ADD COLUMN assignment_version_id uuid,
    ADD CONSTRAINT curriculum_draft_commands_operation_check
        CHECK (operation IN ('create','replace','activate')),
    ADD CONSTRAINT curriculum_activation_command_link
        CHECK ((operation='activate')=(assignment_version_id IS NOT NULL)),
    ADD FOREIGN KEY (tenant_id,project_id,assignment_version_id)
        REFERENCES curriculum_assignment_versions(tenant_id,project_id,id) ON DELETE CASCADE;
CREATE INDEX curriculum_activation_commands_version_idx
    ON curriculum_draft_commands (tenant_id,project_id,assignment_version_id)
    WHERE assignment_version_id IS NOT NULL;

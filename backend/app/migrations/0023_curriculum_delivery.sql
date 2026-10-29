-- Separate bounded curriculum deliveries and atomic generated draft results.
ALTER TABLE curriculum_runs DROP CONSTRAINT curriculum_runs_status_check;
ALTER TABLE curriculum_runs ADD CONSTRAINT curriculum_runs_status_check
    CHECK (status IN ('pending','running','retrying','failed','cancelled','succeeded'));
ALTER TABLE curriculum_runs DROP CONSTRAINT curriculum_runs_check2;
ALTER TABLE curriculum_runs ADD CONSTRAINT curriculum_runs_finished_state_check
    CHECK ((status IN ('failed','cancelled','succeeded'))=(finished_at IS NOT NULL));

ALTER TABLE curriculum_run_attempts DROP CONSTRAINT curriculum_run_attempts_status_check;
ALTER TABLE curriculum_run_attempts ADD CONSTRAINT curriculum_run_attempts_status_check
    CHECK (status IN ('running','failed','cancelled','checkpointed','succeeded'));

-- The pointer is to the original immutable revision, not an editable draft head.
-- Deleting a result removes its pointer but does not resurrect or erase its run.
CREATE TABLE curriculum_run_results (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    run_id uuid NOT NULL,
    draft_id uuid NOT NULL,
    revision integer NOT NULL CHECK (revision>0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (tenant_id,project_id,run_id),
    UNIQUE (tenant_id,project_id,draft_id,revision),
    FOREIGN KEY (tenant_id,project_id,run_id)
        REFERENCES curriculum_runs(tenant_id,project_id,id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,draft_id,revision)
        REFERENCES curriculum_draft_revisions(tenant_id,project_id,draft_id,revision) ON DELETE CASCADE
);

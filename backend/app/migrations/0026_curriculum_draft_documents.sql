-- Every selected retained document is a dependency, even when this revision
-- cites none of its excerpts. Removal deletes the entire logical draft/history.
ALTER TABLE curriculum_draft_revisions
    ADD COLUMN documentation_ids jsonb NOT NULL DEFAULT '[]'::jsonb
        CHECK (jsonb_typeof(documentation_ids)='array' AND jsonb_array_length(documentation_ids)<=20);

ALTER TABLE curriculum_drafts
    ADD CONSTRAINT curriculum_draft_context_identity UNIQUE (tenant_id,project_id,context_id,id);
ALTER TABLE curriculum_document_approvals
    ADD CONSTRAINT curriculum_document_context_identity UNIQUE (tenant_id,project_id,context_id,id);

CREATE TABLE curriculum_draft_documents (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    context_id uuid NOT NULL,
    draft_id uuid NOT NULL,
    revision integer NOT NULL,
    document_id uuid NOT NULL,
    PRIMARY KEY (tenant_id,project_id,draft_id,revision,document_id),
    FOREIGN KEY (tenant_id,project_id,draft_id,revision)
        REFERENCES curriculum_draft_revisions(tenant_id,project_id,draft_id,revision) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,context_id,draft_id)
        REFERENCES curriculum_drafts(tenant_id,project_id,context_id,id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,context_id,document_id)
        REFERENCES curriculum_document_approvals(tenant_id,project_id,context_id,id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id,project_id,document_id)
        REFERENCES curriculum_document_snapshots(tenant_id,project_id,document_id) ON DELETE CASCADE
);
CREATE INDEX curriculum_draft_documents_document_idx
    ON curriculum_draft_documents (tenant_id,project_id,document_id,draft_id);

CREATE FUNCTION delete_document_dependent_curriculum_drafts() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    removed_id uuid;
    affected record;
BEGIN
    IF TG_TABLE_NAME='curriculum_document_approvals' THEN
        removed_id := OLD.id;
    ELSE
        removed_id := OLD.document_id;
    END IF;
    FOR affected IN
        SELECT DISTINCT draft_id FROM curriculum_draft_documents
        WHERE tenant_id=OLD.tenant_id AND project_id=OLD.project_id AND document_id=removed_id
        ORDER BY draft_id
    LOOP
        DELETE FROM curriculum_drafts
        WHERE tenant_id=OLD.tenant_id AND project_id=OLD.project_id AND id=affected.draft_id;
    END LOOP;
    RETURN OLD;
END;
$$;

CREATE TRIGGER curriculum_document_draft_cleanup
    BEFORE DELETE ON curriculum_document_approvals
    FOR EACH ROW EXECUTE FUNCTION delete_document_dependent_curriculum_drafts();
CREATE TRIGGER curriculum_snapshot_draft_cleanup
    BEFORE DELETE ON curriculum_document_snapshots
    FOR EACH ROW EXECUTE FUNCTION delete_document_dependent_curriculum_drafts();

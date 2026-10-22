-- Keep already-applied 0011 immutable; strengthen cleanup ownership additively.
ALTER TABLE artifact_cleanup ADD CONSTRAINT cleanup_scoped_identity UNIQUE (tenant_id, project_id, id);
ALTER TABLE audio_inputs
    DROP CONSTRAINT audio_inputs_cleanup_id_fkey,
    ADD CONSTRAINT audio_cleanup_scope FOREIGN KEY (tenant_id, project_id, cleanup_id)
        REFERENCES artifact_cleanup (tenant_id, project_id, id),
    ADD CONSTRAINT audio_deleted_state CHECK (deleted_at IS NULL OR cleanup_id IS NOT NULL);

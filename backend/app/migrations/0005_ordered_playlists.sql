ALTER TABLE sources
    ADD COLUMN playlist_snapshot_generation integer CHECK (playlist_snapshot_generation > 0),
    ADD COLUMN parent_playlist_source_id uuid,
    ADD CONSTRAINT sources_parent_playlist_fk
        FOREIGN KEY (tenant_id, project_id, parent_playlist_source_id)
        REFERENCES sources(tenant_id, project_id, id)
        ON DELETE SET NULL (parent_playlist_source_id),
    ADD CONSTRAINT sources_not_own_playlist CHECK (parent_playlist_source_id IS DISTINCT FROM id);

CREATE TABLE playlist_items (
    tenant_id text NOT NULL,
    project_id uuid NOT NULL,
    id uuid NOT NULL,
    playlist_source_id uuid NOT NULL,
    generation integer NOT NULL CHECK (generation > 0),
    position integer NOT NULL CHECK (position BETWEEN 0 AND 1000000),
    external_item_id text NOT NULL CHECK (length(external_item_id) BETWEEN 1 AND 512),
    video_id text NOT NULL CHECK (video_id ~ '^[a-zA-Z0-9_-]{11}$'),
    title text NOT NULL CHECK (length(title) BETWEEN 1 AND 255),
    transcript_source_id uuid,
    PRIMARY KEY (tenant_id, project_id, id),
    UNIQUE (tenant_id, project_id, playlist_source_id, generation, position),
    UNIQUE (tenant_id, project_id, playlist_source_id, generation, external_item_id),
    FOREIGN KEY (tenant_id, project_id, playlist_source_id)
        REFERENCES sources(tenant_id, project_id, id) ON DELETE CASCADE,
    FOREIGN KEY (tenant_id, project_id, transcript_source_id)
        REFERENCES sources(tenant_id, project_id, id)
        ON DELETE SET NULL (transcript_source_id)
);
CREATE INDEX sources_playlist_jobs_idx ON sources (tenant_id, project_id, parent_playlist_source_id)
    WHERE parent_playlist_source_id IS NOT NULL;

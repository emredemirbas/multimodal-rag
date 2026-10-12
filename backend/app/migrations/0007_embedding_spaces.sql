-- Preserve immutable evidence while allowing separately filtered 64/1024-D spaces.
ALTER TABLE content_segments ALTER COLUMN embedding TYPE vector;
ALTER TABLE content_segments ADD COLUMN embedding_space text NOT NULL DEFAULT 'signed-hash-v1:64';
ALTER TABLE content_segments ADD CONSTRAINT segment_embedding_space_dimensions CHECK (
    (embedding_space = 'signed-hash-v1:64' AND vector_dims(embedding) = 64) OR
    (embedding_space = 'qwen3-0.6b:ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d:1024:query-v1'
     AND vector_dims(embedding) = 1024)
);
CREATE INDEX segment_space_scope_idx ON content_segments (tenant_id, project_id, embedding_space, source_id, generation);

ALTER TABLE sources ADD COLUMN active_embedding_space text;
UPDATE sources SET active_embedding_space = 'signed-hash-v1:64' WHERE active_generation IS NOT NULL AND kind = 'transcript';

ALTER TABLE processing_versions
    ADD COLUMN embedding_space text DEFAULT 'signed-hash-v1:64',
    ADD COLUMN embedding_model_digest text CHECK (embedding_model_digest ~ '^[a-f0-9]{64}$');
UPDATE processing_versions SET embedding_space = NULL WHERE embedding_dimensions = 0;

ALTER TABLE usage_events
    ADD COLUMN embedding_space text DEFAULT 'signed-hash-v1:64',
    ADD COLUMN model_digest text CHECK (model_digest ~ '^[a-f0-9]{64}$'),
    ADD COLUMN input_tokens integer CHECK (input_tokens >= 0);
UPDATE usage_events SET embedding_space = NULL WHERE segment_count = 0;

ALTER TABLE retrieval_runs
    ADD COLUMN embedding_space text NOT NULL DEFAULT 'signed-hash-v1:64',
    ADD COLUMN embedding_dimensions integer NOT NULL DEFAULT 64 CHECK (embedding_dimensions IN (64, 1024)),
    ADD COLUMN embedding_model_digest text CHECK (embedding_model_digest ~ '^[a-f0-9]{64}$'),
    ADD COLUMN embedding_input_tokens integer CHECK (embedding_input_tokens >= 0);

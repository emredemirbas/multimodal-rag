-- Exact prepared-request attribution. Historical metadata-only calls stay NULL.
ALTER TABLE curriculum_model_calls
    ADD COLUMN input_sha256 text CHECK (input_sha256 IS NULL OR input_sha256 ~ '^[a-f0-9]{64}$'),
    ADD COLUMN schema_version text CHECK (schema_version IS NULL OR schema_version ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$'),
    ADD COLUMN request_version text CHECK (request_version IS NULL OR request_version ~ '^[a-zA-Z0-9][a-zA-Z0-9._:/+@-]{0,127}$'),
    ADD CONSTRAINT curriculum_model_calls_request_identity_check CHECK (
        (input_sha256 IS NULL)=(schema_version IS NULL) AND (input_sha256 IS NULL)=(request_version IS NULL)
    );

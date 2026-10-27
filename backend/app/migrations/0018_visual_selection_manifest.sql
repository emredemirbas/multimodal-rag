-- Additive: no legacy identities, digests, frames or citations are rewritten.
ALTER TABLE visual_runs DROP CONSTRAINT visual_runs_profile_check;
ALTER TABLE visual_runs ADD CONSTRAINT visual_runs_profile_check
    CHECK (profile ~ '^local-visual-v[12]:[a-f0-9]{64}$');

-- Inherits the run's complete scope, fences, retention and ON DELETE CASCADE.
ALTER TABLE visual_runs ADD COLUMN selection_manifest jsonb
    CHECK (jsonb_typeof(selection_manifest) = 'object'
           AND octet_length(selection_manifest::text) <= 196608);
ALTER TABLE visual_runs ADD CONSTRAINT visual_runs_selection_version_check CHECK (
    (profile LIKE 'local-visual-v1:%' AND selection_manifest IS NULL)
    OR (profile LIKE 'local-visual-v2:%'
        AND ((saved_at IS NULL AND selection_manifest IS NULL)
             OR (saved_at IS NOT NULL AND selection_manifest IS NOT NULL)))
);

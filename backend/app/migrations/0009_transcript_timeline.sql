-- Published evidence only; private staging has no role in transcript browsing.
CREATE INDEX content_segments_transcript_timeline_idx
    ON content_segments (tenant_id, project_id, source_id, generation, start_ms, end_ms, id)
    WHERE modality = 'transcript';

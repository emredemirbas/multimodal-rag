"""Scoped snapshot helpers; callers hold the project lock for all writes."""
from uuid import UUID, uuid5

from pydantic import ValidationError

from ..store import ProjectNotFoundError
from .contracts import PlaylistItem, PlaylistMetadataItem, SourceError


def read_items(connection, tenant: str, project: UUID) -> list[PlaylistItem]:
    rows = connection.execute(
        '''SELECT i.* FROM playlist_items i JOIN sources s
           ON s.tenant_id=i.tenant_id AND s.project_id=i.project_id AND s.id=i.playlist_source_id
           AND s.playlist_snapshot_generation=i.generation
           WHERE i.tenant_id=%s AND i.project_id=%s AND s.deleted_at IS NULL
           ORDER BY s.created_at DESC,s.id,i.position,i.id''', (tenant, project),
    ).fetchall()
    return [PlaylistItem.model_validate(row) for row in rows]


def current_item(connection, tenant: str, project: UUID, item: UUID):
    row = connection.execute(
        '''SELECT i.* FROM playlist_items i JOIN sources s
           ON s.tenant_id=i.tenant_id AND s.project_id=i.project_id AND s.id=i.playlist_source_id
           AND s.playlist_snapshot_generation=i.generation
           WHERE i.tenant_id=%s AND i.project_id=%s AND i.id=%s AND s.deleted_at IS NULL''',
        (tenant, project, item),
    ).fetchone()
    if row is None:
        raise ProjectNotFoundError('playlist item not found; refresh the source list')
    if row['transcript_source_id']:
        running = connection.execute(
            '''SELECT status FROM processing_jobs WHERE tenant_id=%s AND project_id=%s AND source_id=%s
               ORDER BY generation DESC,created_at DESC LIMIT 1''',
            (tenant, project, row['transcript_source_id']),
        ).fetchone()
        if running and running['status'] in {'pending', 'running', 'retrying'}:
            raise SourceError('playlist_item_busy', 'Wait for or cancel this video’s transcript job before replacing its upload.', 409)
    return row


def store_snapshot(connection, tenant: str, project: UUID, source: UUID, generation: int, metadata: dict):
    raw = metadata.get('items')
    try:
        if not isinstance(raw, list) or len(raw) > 100:
            raise ValueError()
        items = [PlaylistMetadataItem.model_validate(item) for item in raw]
        if len({item.position for item in items}) != len(items) or len({item.item_id for item in items}) != len(items):
            raise ValueError()
    except (ValidationError, ValueError, TypeError):
        raise SourceError('invalid_provider_response', 'Playlist metadata contains invalid or duplicated items.') from None
    previous = connection.execute(
        '''SELECT i.external_item_id,i.video_id,i.transcript_source_id FROM playlist_items i JOIN sources s
           ON s.tenant_id=i.tenant_id AND s.project_id=i.project_id AND s.id=i.playlist_source_id
           AND s.playlist_snapshot_generation=i.generation
           WHERE i.tenant_id=%s AND i.project_id=%s AND i.playlist_source_id=%s''',
        (tenant, project, source),
    ).fetchall()
    bindings = {(row['external_item_id'], row['video_id']): row['transcript_source_id'] for row in previous}
    for item in sorted(items, key=lambda value: value.position):
        connection.execute(
            '''INSERT INTO playlist_items (tenant_id,project_id,id,playlist_source_id,generation,position,
               external_item_id,video_id,title,transcript_source_id) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (tenant, project, uuid5(source, f'playlist:{generation}:{item.item_id}'), source, generation,
             item.position, item.item_id, item.video_id, item.title, bindings.get((item.item_id, item.video_id))),
        )
    connection.execute(
        'UPDATE sources SET playlist_snapshot_generation=%s WHERE tenant_id=%s AND project_id=%s AND id=%s',
        (generation, tenant, project, source),
    )

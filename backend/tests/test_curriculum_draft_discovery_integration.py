"""Bounded scoped discovery exposes current heads, never draft bodies or receipts."""

from uuid import uuid4

import pytest

from app.models import ProjectCreate
from app.curriculum.drafts import DraftRepository
from app.store import ProjectNotFoundError
from uuid import UUID
from conftest import auth_headers
from test_curriculum_api_integration import context_api, context_body, create_context, assert_private
from test_curriculum_draft_api_integration import create_draft, create_path, draft_path, draft_body, replacement
from test_postgres_integration import isolated_postgres_url

pytestmark = [pytest.mark.integration, pytest.mark.anyio]


async def test_discovery_empty_and_current_heads_with_bounded_metadata(context_api):
    client, state = context_api
    context = await create_context(client, state)
    path = create_path(state, context)
    empty = await client.get(path, headers=auth_headers())
    assert empty.status_code == 200 and empty.json() == {"items": [], "next_after": None}
    assert_private(empty)
    body = draft_body(context)
    saved = await create_draft(client, state, context, body)
    updated = await client.put(draft_path(state, saved['id']), headers=auth_headers(), json=replacement(body))
    assert updated.status_code == 200
    result = await client.get(path, headers=auth_headers())
    assert_private(result)
    assert result.json() == {"items": [{key: updated.json()[key] for key in ('id', 'tenant_id', 'project_id', 'context_id', 'revision', 'created_at')} | {"title": replacement(body)['content']['title']}], "next_after": None}
    assert 'scenario' not in result.text and 'tutorial_evidence' not in result.text


async def test_discovery_keyset_pages_survive_edit_and_deleted_cursor(context_api):
    client, state = context_api
    context = await create_context(client, state)
    saved = [await create_draft(client, state, context, draft_body(context, f'discovery-draft-{i}')) for i in range(3)]
    saved.sort(key=lambda item: item['id'])
    path = create_path(state, context)
    first = await client.get(path + '?limit=1', headers=auth_headers())
    assert first.json()['items'][0]['id'] == saved[0]['id']
    assert first.json()['next_after'] == saved[0]['id']
    assert (await client.delete(draft_path(state, saved[0]['id']), headers=auth_headers())).status_code == 204
    edit = replacement(draft_body(context), key='discovery-page-edit')
    assert (await client.put(draft_path(state, saved[1]['id']), headers=auth_headers(), json=edit)).status_code == 200
    second = await client.get(path + '?limit=1&after=' + first.json()['next_after'], headers=auth_headers())
    assert second.json()['items'][0]['id'] == saved[1]['id'] and second.json()['items'][0]['revision'] == 2
    last = await client.get(path + '?limit=1&after=' + second.json()['next_after'], headers=auth_headers())
    assert last.json()['items'][0]['id'] == saved[2]['id'] and last.json()['next_after'] is None


async def test_discovery_context_tenant_project_membership_and_dependency_scope(context_api):
    client, state = context_api
    context = await create_context(client, state)
    await create_draft(client, state, context)
    path = create_path(state, context)
    assert (await client.get(path)).status_code == 401
    foreign = await client.get(path, headers=auth_headers('tenant-b'))
    assert foreign.status_code == 404
    assert_private(foreign)
    other = await create_context(client, state, context_body(state, 'other-discovery-context'))
    assert (await client.get(create_path(state, other), headers=auth_headers())).json()['items'] == []
    project = state['service'].create_project(state['principal'], ProjectCreate(title='Other discovery project'))
    wrong = path.replace(str(state['project'].id), str(project.id))
    assert (await client.get(wrong, headers=auth_headers())).status_code == 404
    with state['store']._connect() as connection:
        actor = connection.execute('SELECT user_id FROM memberships WHERE tenant_id=%s', ('tenant-a',)).fetchone()['user_id']
        connection.execute('DELETE FROM memberships WHERE tenant_id=%s', ('tenant-a',))
    # The development identity adapter reestablishes membership at HTTP entry.
    # Verify revocation at the same repository boundary as existing draft tests.
    with pytest.raises(ProjectNotFoundError):
        DraftRepository(state['store']).list_for_context('tenant-a', state['project'].id, actor, UUID(context['id']))


async def test_discovery_archive_read_and_complete_context_deletion(context_api):
    client, state = context_api
    context = await create_context(client, state)
    await create_draft(client, state, context)
    project_path = f"/api/v1/projects/{state['project'].id}"
    assert (await client.post(project_path + '/archive', headers=auth_headers())).status_code == 200
    path = create_path(state, context)
    assert len((await client.get(path, headers=auth_headers())).json()['items']) == 1
    assert (await client.delete(state['path'] + '/' + context['id'], headers=auth_headers())).status_code == 204
    assert (await client.get(path, headers=auth_headers())).status_code == 404


@pytest.mark.parametrize('query', ['limit=0', 'limit=51', 'limit=x', 'after=../private', 'after='])
async def test_discovery_invalid_page_bounds_fail_without_exposure(context_api, query):
    client, state = context_api
    context = await create_context(client, state)
    response = await client.get(create_path(state, context) + '?' + query, headers=auth_headers())
    assert response.status_code == 422
    assert_private(response)


async def test_discovery_missing_context_is_not_empty_success(context_api):
    client, state = context_api
    response = await client.get(state['path'] + f'/{uuid4()}/drafts', headers=auth_headers())
    assert response.status_code == 404
    assert_private(response)

import hashlib
import json
import logging
from pathlib import Path

import pytest
import yaml

from app.config import Settings
from app.vision.client import VisualError
from app.vision.contracts import VisualIdentity, WireResult
from test_visual_selection import change_result
from test_visual_service import content, identity, provider, request, service


def change_identity(language='en'):
    row = change_result().identity.model_dump(exclude={'profile'})
    row['language'] = language
    row['profile'] = 'local-visual-v2:' + hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    return VisualIdentity.model_validate(row)


@pytest.fixture
def changes(service):
    calls = []
    service.change_identities = {language: change_identity(language) for language in ['en', 'tr', 'en+tr']}
    def run(data, language):
        calls.append(language)
        row = change_result().model_dump()
        row['input_sha256'] = hashlib.sha256(data).hexdigest()
        row['identity'] = change_identity(language).model_dump()
        return WireResult.model_validate(row).result()
    service.change_runner = run
    return service, calls


@pytest.mark.parametrize('language', ['en', 'tr', 'en+tr'])
def test_real_http_routes_both_policies_without_changing_default_or_logging_payloads(changes, language, caplog):
    server, calls = changes
    caplog.set_level(logging.INFO, logger='tutorial_workspace.visual')
    client = provider(server)
    pin = client.ready(language, selection='change')
    result = client.extract(content(), expected_identity=pin)
    assert pin == change_identity(language) and len(result.frames) == 6 and calls == [language]
    assert client.ready(language) == identity(language)
    assert not server.observed
    assert 'PRIVATE_OCR' not in caplog.text and result.selection['samples'][0]['thumbnail_sha256'] not in caplog.text


@pytest.mark.parametrize('query', ['selection=change', 'language=en&selection=change&selection=uniform',
    'language=en&selection=custom', 'language=en&selection=', 'language=en&selection=change&url=PRIVATE',
    'language=en&selection=%63hange', 'language=en&selection=change&language=tr'])
def test_invalid_policy_queries_never_start_native_work(changes, query):
    server, calls = changes
    status, body = request(server, path='/extract?' + query)
    assert status == 422 and body == {'code': 'invalid_visual_request'}
    assert not calls and not server.observed


def test_policy_profile_mismatch_and_unavailable_change_mode_do_not_fall_back(changes):
    server, calls = changes
    assert request(server, path='/extract?language=en&selection=change')[0] == 409
    assert request(server, headers={'X-Visual-Profile': change_identity().profile})[0] == 409
    server.change_identities.clear()
    with pytest.raises(VisualError): provider(server).ready(selection='change')
    assert provider(server).ready() == identity()
    assert not calls and not server.observed


def test_wrong_native_policy_and_tampered_scan_do_not_cross_http_boundary(changes):
    server, _ = changes
    from test_visual_service import result
    server.change_runner = lambda data, language: result(data, language)
    with pytest.raises(VisualError): provider(server).extract(content(), expected_identity=change_identity())
    corrupt = change_result().result()
    corrupt.selection['samples'].clear()
    server.change_runner = lambda data, language: corrupt
    with pytest.raises(VisualError): provider(server).extract(content(), expected_identity=change_identity())


def test_client_rejects_wrong_ready_policy_before_upload(changes, monkeypatch):
    client = provider(changes[0])
    monkeypatch.setattr(client, '_request', lambda *args, **kwargs: identity().model_dump())
    with pytest.raises(VisualError) as failure: client.ready(selection='change')
    assert failure.value.code == 'invalid_visual_response'
    with pytest.raises(VisualError): client.ready(selection='custom')


def test_setting_is_explicit_default_uniform_and_only_reaches_the_trusted_worker(monkeypatch):
    monkeypatch.setenv('DEVELOPMENT_AUTH_TOKEN', 'test-development-token')
    monkeypatch.delenv('VISUAL_SELECTION', raising=False)
    assert Settings.from_env().visual_selection == 'uniform'
    monkeypatch.setenv('VISUAL_SELECTION', 'change')
    assert Settings.from_env().visual_selection == 'change'
    root = Path(__file__).resolve().parents[2]
    config = yaml.safe_load((root / 'compose.yaml').read_text())
    assert config['services']['visual-worker']['environment']['VISUAL_SELECTION'] == '${VISUAL_SELECTION:-uniform}'
    assert not config['services']['visual'].get('environment')
    assert 'VISUAL_SELECTION' not in config['x-api-environment']


@pytest.mark.parametrize('bad', ['', 'Change', 'scene', None, False, []])
def test_unknown_selection_configuration_is_rejected(bad):
    with pytest.raises(ValueError, match='VISUAL_SELECTION'):
        Settings(environment='test', development_auth_token='test-development-token', visual_selection=bad)

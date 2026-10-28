"""No actual Docker, home configuration, credentials, network or app data needed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest


spec = importlib.util.spec_from_file_location('local_setup', Path(__file__).resolve().parents[2] / 'scripts/check_local_setup.py')
setup = importlib.util.module_from_spec(spec)
spec.loader.exec_module(setup)


@pytest.fixture
def environment(tmp_path):
    env_file = tmp_path / '.env'
    env_file.write_text('PRIVATE_SENTINEL=not-a-shell-script\n', encoding='utf-8')
    env_file.chmod(0o600)
    config = {'services': {
        'api': {'environment': {'DEVELOPMENT_AUTH_TOKEN': 'private-token-for-test-only'}},
        'postgres': {'environment': {'POSTGRES_PASSWORD': 'private-db-password'}},
        'minio': {'environment': {'MINIO_ROOT_PASSWORD': 'private-object-password'}},
    }}
    return tmp_path, env_file, config


def check_environment(environment, *, responses=None, present=lambda name: '/test/bin/' + name):
    root, env_file, config = environment
    calls = []
    def run(arguments, directory):
        assert directory == root
        calls.append(arguments)
        key = 'config' if 'config' in arguments else 'daemon' if 'info' in arguments else 'compose'
        if responses and key in responses:
            return responses[key]
        return SimpleNamespace(returncode=0, stdout=json.dumps(config) if key == 'config' else 'version', stderr='')
    checks = setup.run_checks(root, env_file, run=run, which=present, docker_config=root / 'docker-config')
    return checks, calls


def test_default_check_is_read_only_and_uses_effective_compose_values(environment):
    checks, calls = check_environment(environment)
    assert all(check.level == 'PASS' for check in checks)
    root, env_file, _ = environment
    assert calls == [
        ['docker', 'compose', 'version', '--short'],
        ['docker', 'compose', '--project-directory', str(root), '--env-file', str(env_file),
         '--file', str(root / 'compose.yaml'), 'config', '--format', 'json'],
        ['docker', 'info', '--format', '{{.ServerVersion}}'],
    ]
    assert env_file.read_text() == 'PRIVATE_SENTINEL=not-a-shell-script\n'


def test_missing_docker_never_executes_a_command(environment):
    checks, calls = check_environment(environment, present=lambda name: None)
    assert not calls
    assert any(check.code == 'docker_cli' and check.level == 'FAIL' for check in checks)


@pytest.mark.parametrize('response', [None, SimpleNamespace(returncode=1, stdout='', stderr='private raw plugin failure')])
def test_missing_or_timed_out_compose_does_not_render_configuration(environment, response):
    checks, calls = check_environment(environment, responses={'compose': response})
    assert any(check.code == 'compose_plugin' and check.level == 'FAIL' for check in checks)
    assert not any('config' in call for call in calls)
    assert 'private raw' not in str(checks)


@pytest.mark.parametrize('error,expected', [('permission denied SECRET', 'access is denied'),
                                           ('connection refused SECRET', 'unavailable')])
def test_daemon_failures_have_safe_actionable_messages(environment, error, expected):
    checks, _ = check_environment(environment, responses={'daemon': SimpleNamespace(returncode=1, stdout='', stderr=error)})
    check = next(check for check in checks if check.code == 'docker_daemon')
    assert check.level == 'FAIL' and expected in check.message
    assert 'SECRET' not in str(checks)


def test_missing_env_skips_config_without_creating_or_overwriting_it(environment):
    environment[1].unlink()
    checks, calls = check_environment(environment)
    assert any(check.code == 'env_file' and check.level == 'FAIL' for check in checks)
    assert not any('config' in call for call in calls)
    assert not environment[1].exists()


@pytest.mark.skipif(setup.os.name != 'posix', reason='POSIX permission bits')
def test_permissions_are_reported_not_changed(environment):
    environment[1].chmod(0o644)
    checks, _ = check_environment(environment)
    assert any(check.code == 'env_permissions' and check.level == 'WARN' for check in checks)
    assert environment[1].stat().st_mode & 0o777 == 0o644


@pytest.mark.parametrize('service,key,value,code', [
    ('api', 'DEVELOPMENT_AUTH_TOKEN', 'replace-me', 'auth_token'),
    ('api', 'DEVELOPMENT_AUTH_TOKEN', 'TINYKEY', 'auth_token'),
    ('postgres', 'POSTGRES_PASSWORD', 'change-me-local-only', 'postgres_password'),
    ('minio', 'MINIO_ROOT_PASSWORD', 'TINYKEY', 'minio_password'),
    ('minio', 'MINIO_ROOT_PASSWORD', 'change-me-local-only', 'minio_password'),
])
def test_placeholders_and_invalid_lengths_fail_without_displaying_values(environment, service, key, value, code):
    environment[2]['services'][service]['environment'][key] = value
    checks, _ = check_environment(environment)
    assert any(check.code == code and check.level == 'FAIL' for check in checks)
    assert value not in str(checks)


@pytest.mark.parametrize('response', [None,
    SimpleNamespace(returncode=1, stdout='secret stdout', stderr='secret stderr'),
    SimpleNamespace(returncode=0, stdout='{"secret":"raw-value"}', stderr=''),
    SimpleNamespace(returncode=0, stdout='not JSON secret', stderr=''),
])
def test_bad_configuration_output_is_never_forwarded(environment, response):
    checks, _ = check_environment(environment, responses={'config': response})
    assert any(check.code == 'compose_config' and check.level == 'FAIL' for check in checks)
    assert 'secret' not in str(checks).replace('secrets', '')


@pytest.mark.parametrize('value,level', [('', 'FAIL'), ('a' * 12, 'FAIL'), ('a' * 64, 'PASS')])
def test_opted_in_vision_requires_full_digest_but_never_calls_models(environment, value, level):
    environment[2]['services']['api']['environment'].update(FRAME_DESCRIPTIONS_ENABLED='true', VISION_MODEL_DIGEST=value)
    checks, calls = check_environment(environment)
    assert any(check.code == 'vision_digest' and check.level == level for check in checks)
    assert any(check.code == 'optional_services' and check.level == 'WARN' for check in checks)
    assert len(calls) == 3


@pytest.mark.parametrize('flag', ['1', 'true', 'yes', 'on', ' TRUE '])
@pytest.mark.parametrize('name', ['AUDIO_UPLOAD_ENABLED', 'VIDEO_UPLOAD_ENABLED', 'FRAME_DESCRIPTIONS_ENABLED'])
def test_all_app_enabled_flag_forms_require_optional_setup(environment, flag, name):
    environment[2]['services']['api']['environment'][name] = flag
    checks, _ = check_environment(environment)
    assert any(check.code == 'optional_services' and check.level == 'WARN' for check in checks)
    if name == 'FRAME_DESCRIPTIONS_ENABLED':
        assert any(check.code == 'vision_digest' and check.level == 'FAIL' for check in checks)


@pytest.mark.parametrize('flag', ['0', 'false', 'no', 'off', ' FALSE '])
def test_all_app_disabled_flag_forms_remain_keyless(environment, flag):
    environment[2]['services']['api']['environment']['FRAME_DESCRIPTIONS_ENABLED'] = flag
    checks, _ = check_environment(environment)
    assert all(check.level == 'PASS' for check in checks)


@pytest.mark.parametrize('value', ['SECRET_INVALID_FLAG', 1, None])
def test_invalid_flag_values_fail_safely(environment, value):
    environment[2]['services']['api']['environment']['VIDEO_UPLOAD_ENABLED'] = value
    checks, _ = check_environment(environment)
    assert any(check.code == 'feature_flag' and check.level == 'FAIL' for check in checks)
    assert 'SECRET_INVALID_FLAG' not in str(checks)


def test_disabled_vision_still_rejects_nonempty_malformed_digest(environment):
    environment[2]['services']['api']['environment']['VISION_MODEL_DIGEST'] = 'SECRET_BAD_DIGEST'
    checks, _ = check_environment(environment)
    assert any(check.code == 'vision_digest' and check.level == 'FAIL' for check in checks)
    assert 'SECRET_BAD_DIGEST' not in str(checks)


@pytest.mark.parametrize('payload', [{'credsStore': 'pass'}, {'credHelpers': {'registry.example': 'pass'}}])
def test_missing_credential_helpers_are_reported_without_displaying_auths_or_changing_config(tmp_path, payload):
    payload['auths'] = {'private-registry': {'auth': 'SECRET_AUTH_BLOB'}}
    path = tmp_path / 'config.json'
    raw = json.dumps(payload)
    path.write_text(raw)
    seen = []
    check = setup.credential_check(tmp_path, lambda name: seen.append(name))
    assert check.level == 'WARN' and seen == ['docker-credential-pass']
    assert 'SECRET' not in str(check) and path.read_text() == raw


@pytest.mark.parametrize('raw', ['[]', '{', '{"credsStore": "../../SECRET"}', '{"credHelpers": null}', 'x' * 65_537])
def test_malformed_or_oversized_docker_config_is_safe(tmp_path, raw):
    (tmp_path / 'config.json').write_text(raw)
    check = setup.credential_check(tmp_path, lambda name: pytest.fail('Invalid helper must not be resolved'))
    assert check.level == 'WARN' and 'SECRET' not in str(check)


@pytest.mark.parametrize('error', [OSError('SECRET_EXCEPTION'), subprocess.TimeoutExpired(['docker'], 15, output='SECRET_OUTPUT')])
def test_subprocess_failures_are_bounded_and_not_forwarded(monkeypatch, tmp_path, error):
    def fail(arguments, **kwargs):
        assert kwargs['timeout'] == 15 and kwargs['stdin'] == subprocess.DEVNULL
        assert kwargs['capture_output'] and not kwargs.get('shell')
        raise error
    monkeypatch.setattr(setup.subprocess, 'run', fail)
    assert setup.run_command(['docker', 'compose', 'version', '--short'], tmp_path) is None


@pytest.mark.parametrize('level,expected', [('PASS', 0), ('WARN', 0), ('FAIL', 1)])
def test_cli_exit_and_redacted_output(monkeypatch, capsys, level, expected):
    monkeypatch.setattr(setup, 'run_checks', lambda *args: [setup.Check(level, 'fixture', 'Safe result.')])
    assert setup.main([]) == expected
    output = capsys.readouterr().out
    assert 'Safe result.' in output and 'no containers started' in output
    assert 'model-quality approval' in output


@pytest.mark.parametrize('invalid', [False, True])
def test_actual_cli_with_fake_docker_never_exposes_output_or_changes_inputs(environment, invalid):
    root, env_file, config = environment
    binary = root / 'docker'
    calls_file = root / 'calls'
    source = (f'#!{sys.executable}\nimport json,sys\n'
        f'with open({str(calls_file)!r}, "a") as handle: handle.write(json.dumps(sys.argv[1:])+"\\n")\n'
        'if "config" in sys.argv:\n'
        f'    print({json.dumps(config)!r})\n'
        '    print("SECRET_STDERR", file=sys.stderr)\n'
        f'    sys.exit({int(invalid)})\n'
        'print("SECRET_UNUSED_VERSION")\n')
    binary.write_text(source)
    binary.chmod(0o700)
    result = subprocess.run([sys.executable, str(Path(setup.__file__)), '--env-file', str(env_file)],
        env={'PATH': str(root), 'DOCKER_CONFIG': str(root / 'unused-config')},
        capture_output=True, text=True, timeout=10)
    assert result.returncode == int(invalid) and not result.stderr
    assert not any(value in result.stdout for value in
        ('private-token-for-test-only', 'private-db-password', 'private-object-password',
         'SECRET_STDERR', 'SECRET_UNUSED_VERSION'))
    assert env_file.read_text() == 'PRIVATE_SENTINEL=not-a-shell-script\n'
    calls = [json.loads(line) for line in calls_file.read_text().splitlines()]
    assert [call[:2] for call in calls] == [['compose', 'version'], ['compose', '--project-directory'], ['info', '--format']]
    assert 'config' in calls[1] and not any('up' in call or 'pull' in call for call in calls)

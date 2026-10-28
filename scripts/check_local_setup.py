#!/usr/bin/env python3
"""Read-only base compose.yaml prerequisites; standard library only, no startup.

Compose resolves configuration privately so its real dotenv/override rules apply.
Never echo its rendered config, command output, Docker auth data or exceptions.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import NamedTuple


ROOT = Path(__file__).resolve().parents[1]
TIMEOUT = 15


class Check(NamedTuple):
    level: str
    code: str
    message: str


def run_command(arguments, root):
    try:
        return subprocess.run(arguments, cwd=root, stdin=subprocess.DEVNULL,
                              capture_output=True, text=True, encoding='utf-8',
                              errors='replace', timeout=TIMEOUT, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return None


def credential_check(directory, which):
    """Inspect helper names, never auths; do not invoke or repair any helper."""
    try:
        with (directory / 'config.json').open('rb') as handle:
            raw = handle.read(65_537)
        if len(raw) > 65_536:
            raise ValueError()
        config = json.loads(raw)
        if not isinstance(config, dict):
            raise ValueError()
        helpers = config.get('credHelpers', {})
        if not isinstance(helpers, dict):
            raise ValueError()
        names = [config.get('credsStore'), *helpers.values()]
        for name in names:
            if name in (None, ''):
                continue
            if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]{1,100}', name):
                raise ValueError()
            if which('docker-credential-' + name) is None:
                return Check('WARN', 'credential_helper',
                    'A configured Docker credential helper is missing from PATH. '
                    'Restore it or review Docker credential settings before pulling images; '
                    'this check does not edit them.')
    except FileNotFoundError:
        return Check('PASS', 'credential_helper', 'No Docker credential-helper configuration file is present.')
    except (OSError, ValueError, TypeError, RecursionError):
        return Check('WARN', 'credential_helper', 'Docker credential-helper configuration could not be checked safely.')
    return Check('PASS', 'credential_helper', 'Configured Docker credential helpers are available on PATH (not invoked).')


def configuration_checks(config):
    """Check effective Compose values, not a second approximation of dotenv."""
    services = config['services']
    api = services['api']['environment']
    values = [
        ('auth_token', 'DEVELOPMENT_AUTH_TOKEN', api.get('DEVELOPMENT_AUTH_TOKEN'), 16),
        ('postgres_password', 'POSTGRES_PASSWORD', services['postgres']['environment'].get('POSTGRES_PASSWORD'), 1),
        ('minio_password', 'MINIO_ROOT_PASSWORD', services['minio']['environment'].get('MINIO_ROOT_PASSWORD'), 8),
    ]
    checks = []
    for code, label, value, minimum in values:
        valid = (isinstance(value, str) and len(value) >= minimum
                 and value not in {'replace-me', 'change-me-local-only'})
        checks.append(Check('PASS' if valid else 'FAIL', code,
            f'{label} is set and is not the example placeholder.' if valid else
            f'Set a private, non-placeholder {label} (at least {minimum} characters). '
            'Do not reset existing database credentials or volumes as a shortcut.'))
    flags = {}
    for name in ('AUDIO_UPLOAD_ENABLED', 'VIDEO_UPLOAD_ENABLED', 'FRAME_DESCRIPTIONS_ENABLED'):
        value = api.get(name, 'false')
        normalized = value.strip().lower() if isinstance(value, str) else None
        if normalized not in {'1', 'true', 'yes', 'on', '0', 'false', 'no', 'off'}:
            checks.append(Check('FAIL', 'feature_flag', f'{name} must be a boolean value; its current value is withheld.'))
            flags[name] = None
        else:
            flags[name] = normalized in {'1', 'true', 'yes', 'on'}
    digest = api.get('VISION_MODEL_DIGEST', '')
    if not isinstance(digest, str) or digest or flags['FRAME_DESCRIPTIONS_ENABLED']:
        valid = isinstance(digest, str) and re.fullmatch(r'[a-f0-9]{64}', digest) is not None
        checks.append(Check('PASS' if valid else 'FAIL', 'vision_digest',
            'A full vision-model digest is configured; weights/readiness are not checked.' if valid else
            'VISION_MODEL_DIGEST must be empty while disabled or a full 64-character lowercase hex digest; '
            'it is required when FRAME_DESCRIPTIONS_ENABLED is enabled.'))
    optional = (api.get('ANSWER_PROVIDER', 'extractive') != 'extractive'
                or api.get('EMBEDDING_PROVIDER', 'hash') != 'hash'
                or any(flag is not False for flag in flags.values()))
    checks.append(Check('WARN' if optional else 'PASS', 'optional_services',
        'Optional local features are configured or their flags need correction. Start their documented profiles and install weights explicitly '
        'where needed; this check does not verify model readiness or enable anything.' if optional else
        'Default keyless mode: no optional media/model service is required.'))
    return checks


def run_checks(root, env_file, *, run=run_command, which=shutil.which, docker_config=None):
    checks = []
    try:
        if not env_file.is_file():
            raise FileNotFoundError()
        checks.append(Check('PASS', 'env_file', 'The selected local environment file exists (values are never displayed).'))
        if os.name == 'posix' and env_file.stat().st_mode & 0o077:
            checks.append(Check('WARN', 'env_permissions',
                'The environment file is accessible beyond its owner. Review its permissions; no permissions were changed.'))
    except OSError:
        checks.append(Check('FAIL', 'env_file',
            'The selected environment file is missing or inaccessible. For a first setup only, '
            'copy .env.example to .env and replace placeholders; never overwrite an existing .env.'))
    if which('docker') is None:
        checks.append(Check('FAIL', 'docker_cli', 'Docker CLI is unavailable on PATH. Install Docker and the Compose plugin.'))
        return checks
    checks.append(Check('PASS', 'docker_cli', 'Docker CLI is available.'))
    checks.append(credential_check(docker_config if docker_config is not None else
        Path(os.environ.get('DOCKER_CONFIG') or Path.home() / '.docker'), which))
    compose = run(['docker', 'compose', 'version', '--short'], root)
    if compose is None or compose.returncode:
        checks.append(Check('FAIL', 'compose_plugin',
            'The docker compose plugin is unavailable or timed out. Check it in this same terminal/user account.'))
    else:
        checks.append(Check('PASS', 'compose_plugin', 'The docker compose plugin responds.'))
        if not any(item.code == 'env_file' and item.level == 'FAIL' for item in checks):
            result = run(['docker', 'compose', '--project-directory', str(root), '--env-file', str(env_file),
                          '--file', str(root / 'compose.yaml'), 'config', '--format', 'json'], root)
            if result is None or result.returncode:
                checks.append(Check('FAIL', 'compose_config',
                    'Compose configuration is invalid or timed out. Check required variables and Compose syntax locally; '
                    'raw output is withheld because it may contain secrets.'))
            else:
                try:
                    checked = configuration_checks(json.loads(result.stdout))
                except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
                    checks.append(Check('FAIL', 'compose_config', 'The effective Compose configuration could not be checked safely.'))
                else:
                    checks.append(Check('PASS', 'compose_config', 'Compose configuration resolves (rendered values are withheld).'))
                    checks.extend(checked)
    daemon = run(['docker', 'info', '--format', '{{.ServerVersion}}'], root)
    if daemon is None or daemon.returncode:
        denied = daemon is not None and 'permission denied' in daemon.stderr.lower()
        checks.append(Check('FAIL', 'docker_daemon',
            'Docker daemon access is denied for this terminal/user. Review rootless Docker or daemon access policy; '
            'do not make the socket world-writable. No permissions were changed.' if denied else
            'Docker daemon is unavailable or timed out. Check that it is running and your Docker context is correct.'))
    else:
        checks.append(Check('PASS', 'docker_daemon', 'Docker daemon responds in the current Docker context.'))
    return checks


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env',
                        help='Compose environment file (default: repository .env); never sourced or modified')
    args = parser.parse_args(argv)
    checks = run_checks(ROOT, args.env_file.resolve())
    for check in checks:
        print(f'{check.level} [{check.code}] {check.message}')
    failed = any(check.level == 'FAIL' for check in checks)
    print('Setup checks found blockers.' if failed else 'Setup prerequisites checked; review any warnings before building.')
    print('Read-only check: no containers started, images/models pulled, files changed or application data inspected. '
          'This is not application health, credential-login validation or model-quality approval.')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())

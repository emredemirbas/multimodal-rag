import os
from pathlib import Path
import subprocess
import sys

import pytest

from app.config import Settings
from app.jobs.queue import delivery_route


def test_delivery_routes_are_fixed_and_remote_models_are_rejected():
    assert delivery_route('asr') == ('tutorial.process_audio', 'media')
    assert delivery_route('visual') == ('tutorial.process_video', 'visual')
    for job_type in ['transcript', 'metadata']:
        assert delivery_route(job_type) == ('tutorial.process_transcript', 'ingestion')
    with pytest.raises(ValueError): delivery_route('arbitrary.task')
    with pytest.raises(ValueError): Settings(development_auth_token='test-development-token', asr_base_url='https://remote.invalid')
    with pytest.raises(ValueError): Settings(development_auth_token='test-development-token', visual_base_url='https://remote.invalid')


def test_workers_do_not_share_their_registered_application_tasks():
    code = '''
from app.jobs.worker import celery_app as ingestion
from app.jobs.media_worker import celery_app as media
from app.jobs.visual_worker import celery_app as visual
assert 'tutorial.process_transcript' in ingestion.tasks
assert 'tutorial.process_audio' not in ingestion.tasks
assert 'tutorial.process_audio' in media.tasks
assert 'tutorial.process_transcript' not in media.tasks
assert 'tutorial.process_video' in visual.tasks
assert 'tutorial.process_video' not in ingestion.tasks and 'tutorial.process_video' not in media.tasks
assert 'tutorial.process_audio' not in visual.tasks and 'tutorial.process_transcript' not in visual.tasks
assert visual.conf.task_soft_time_limit == 180 and visual.conf.task_time_limit == 210
assert visual.conf.broker_transport_options['visibility_timeout'] == 300
assert visual.conf.visibility_timeout == 300
for app in (media,ingestion):
    assert app.conf.task_soft_time_limit == 90 and app.conf.task_time_limit == 120
    assert app.conf.broker_transport_options['visibility_timeout'] == 240
print('PASS: application task registries are separate')
'''
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).parents[1]), 'APP_ENV': 'test',
           'DEVELOPMENT_AUTH_TOKEN': 'fixture-development-token', 'AUTH_MODE': 'development',
           'EMBEDDING_PROVIDER': 'hash', 'ANSWER_PROVIDER': 'extractive', 'ASR_BASE_URL': 'http://asr:8090'}
    result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, 'Application worker task registries are not isolated'
    assert 'PASS:' in result.stdout

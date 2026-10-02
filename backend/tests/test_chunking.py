from uuid import uuid4

import pytest

from app.sources.chunking import chunk_transcript, decode_transcript, segment_id
from app.sources.contracts import SourceError
from app.sources.upload_limit import UploadLimitMiddleware


def test_bom_chunking_preserves_code_timing_and_stable_cues():
    content = b'\xef\xbb\xbfWEBVTT\n\n00:00.000 --> 00:02.000\nCall create_app() and GET /health.\n\n00:03.000 --> 00:05.000\nUse snake_case identifiers.\n\n00:20.000 --> 00:25.000\nA new topic.\n'
    chunks = chunk_transcript(content)
    assert len(chunks) == 2
    assert chunks[0].start_ms == 0 and chunks[0].end_ms == 5000
    assert (chunks[0].cue_start, chunks[0].cue_end) == (0, 1)
    assert 'create_app()' in chunks[0].text and 'snake_case' in chunks[0].text
    source = uuid4()
    assert segment_id(source, 1, chunks[0]) == segment_id(source, 1, chunk_transcript(content)[0])
    assert segment_id(source, 1, chunks[0]) != segment_id(source, 2, chunks[0])
    assert segment_id(source, 1, chunks[0], 1) != segment_id(source, 1, chunks[0], 2)


@pytest.mark.parametrize('content,code', [
    (b'\xff', 'invalid_encoding'), (b'\x00media', 'invalid_encoding'),
    (b'not a transcript', 'invalid_transcript'),
    (b'00:10.000 --> 00:12.000\nB\n\n00:02.000 --> 00:04.000\nA', 'invalid_timeline'),
    (b'00:00.000 --> 00:61.000\nA', 'invalid_transcript'),
    (b'00:00.000 --> 00:02:00.000\nA', 'invalid_timeline'),
])
def test_invalid_transcript_errors_are_safe(content, code):
    with pytest.raises(SourceError) as error:
        chunk_transcript(content)
    assert error.value.code == code


def test_long_cue_chunks_are_bounded_without_losing_identifiers():
    text = ('snake_case create_app() ' * 100).strip()
    chunks = chunk_transcript(f'00:00.000 --> 00:05.000\n{text}'.encode())
    assert all(len(chunk.text) <= 1200 for chunk in chunks)
    assert ' '.join(chunk.text for chunk in chunks) == text


def test_code_generics_and_comparisons_are_not_mistaken_for_html_tags():
    chunks = chunk_transcript(b'WEBVTT\n\n00:00.000 --> 00:05.000\n<b>Use Foo<T>, Foo<B>, list[str] and x < y > z.</b>')
    assert chunks[0].text == 'Use Foo<T>, Foo<B>, list[str] and x < y > z.'


@pytest.mark.anyio
async def test_streamed_upload_is_rejected_before_parser_receives_body():
    called = False
    messages = iter([{'type': 'http.request', 'body': b'1234', 'more_body': True},
                     {'type': 'http.request', 'body': b'5678', 'more_body': False}])
    sent = []

    async def app(*_):
        nonlocal called
        called = True

    async def receive():
        return next(messages)

    async def send(message):
        sent.append(message)

    await UploadLimitMiddleware(app, 6)({'type': 'http', 'method': 'POST', 'path': '/api/v1/projects/x/sources/uploads'}, receive, send)
    assert not called and sent[0]['status'] == 413

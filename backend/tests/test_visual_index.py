from uuid import uuid4

import pytest

from app.models import EvidenceSegment
from app.vision.index import chunks, VisualIndexRepository


def test_literal_unicode_chunks_stable_offsets_frame_ids_and_no_blank_evidence():
    tenant, project, source = 'fixture', uuid4(), uuid4()
    frames = [dict(id=uuid4(), timestamp_ms=0, ocr_text='😀'*1200+'\nuser_id <script>data</script>'),
              dict(id=uuid4(), timestamp_ms=5000, ocr_text=' \n\t')]
    result = chunks(tenant, project, source, 3, frames)
    assert len(result) == 2 and [r['text_offset'] for r in result] == [0,1200]
    assert ''.join(r['text'] for r in result) == frames[0]['ocr_text']
    assert all(r['frame_id'] == frames[0]['id'] and r['start_ms'] == 0 for r in result)
    assert result == chunks(tenant, project, source, 3, frames)
    assert result[0]['segment_id'] != chunks(tenant, project, source, 4, frames)[0]['segment_id']
    assert result[0]['segment_id'] != chunks('foreign', project, source, 3, frames)[0]['segment_id']


def test_maximum_chunks_and_point_timeline_do_not_invent_visibility_duration():
    result = chunks('fixture', uuid4(), uuid4(), 3,
                    [dict(id=uuid4(), timestamp_ms=i*5000, ocr_text='x'*16000) for i in range(20)])
    assert len(result) == 280 and all(1 <= len(item['text']) <= 1200 for item in result)
    base = dict(tenant_id='fixture',project_id=uuid4(),source_id=uuid4(),modality='frame',start_ms=0,end_ms=0,text='code',embedding=[])
    assert EvidenceSegment(**base).end_ms == 0
    with pytest.raises(ValueError): EvidenceSegment(**{**base,'modality':'transcript'})
    with pytest.raises(ValueError): EvidenceSegment(**{**base,'start_ms':1})
    assert VisualIndexRepository._vector_digest([-0.,1.]) == VisualIndexRepository._vector_digest([0.,1.])

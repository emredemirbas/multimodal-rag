from urllib.error import HTTPError

import pytest

from app.sources.adapters import NoRedirects, TranscriptAdapter, YouTubeAdapter, YouTubeMetadataProvider
from app.sources.contracts import SourceError


@pytest.mark.parametrize('url', [
    'http://www.youtube.com/watch?v=abcdefghijk',
    'https://youtube.com.evil.test/watch?v=abcdefghijk',
    'https://evil.test/?url=https://youtube.com/watch?v=abcdefghijk',
    'https://user:pass@youtube.com/watch?v=abcdefghijk',
    'https://youtube.com:443/watch?v=abcdefghijk',
    'https://127.0.0.1/watch?v=abcdefghijk',
    'https://youtube.com/watch?v=abcdefghijk&v=ABCDEFGHIJK',
    'https://youtu.be/abcdefghijk/extra',
    'https://youtube.com/watch?v=../private',
    'https://youtube.com/watch?v=abcdefghijk#fragment',
])
def test_arbitrary_url_fetches_are_rejected(url):
    with pytest.raises(SourceError) as error:
        YouTubeAdapter().normalize(url)
    assert error.value.code == 'unsupported_url'


def test_normalized_upload_and_youtube_contracts():
    assert TranscriptAdapter().normalize('../nested/tutorial.vtt').title == 'tutorial.vtt'
    video = YouTubeAdapter().normalize('https://youtu.be/abcdefghijk')
    assert video.kind == 'youtube_video' and video.canonical_id == 'abcdefghijk'
    playlist = YouTubeAdapter().normalize('https://www.youtube.com/playlist?list=PLabcdefghijk')
    assert playlist.kind == 'youtube_playlist'
    assert NoRedirects().redirect_request(None, None, 302, '', {}, 'https://private.test') is None


def test_metadata_video_is_evidence_free_and_missing_key_is_honest():
    video = YouTubeAdapter().normalize('https://youtu.be/abcdefghijk')
    with pytest.raises(SourceError) as error:
        YouTubeMetadataProvider('').metadata(video)
    assert error.value.code == 'provider_not_configured'
    provider = YouTubeMetadataProvider('fixture-only', fetch=lambda resource, params: {'items': [{'id': 'abcdefghijk', 'snippet': {'title': 'FastAPI tutorial'}}]})
    metadata = provider.metadata(video)
    assert metadata['needs_authorized_transcript'] is True
    assert metadata['items'][0]['video_id'] == video.canonical_id
    assert metadata['retrieved_at'] and metadata['provider_version'] == 'youtube-data-api-v3'
    assert 'fixture-only' not in str(metadata)


def test_playlist_pagination_is_bounded_ordered_and_explicitly_truncated():
    pages = []
    def fetch(resource, params):
        assert resource == 'playlistItems'
        assert params['playlistId'] == 'PLabcdefghijk'
        pages.append(params)
        return {'items': [{'id': f'playlist-item-{len(pages)}', 'contentDetails': {'videoId': 'abcdefghijk'}, 'snippet': {'title': 'Fixture', 'position': 3-len(pages)}}], 'nextPageToken': f'page-{len(pages)}'}
    source = YouTubeAdapter().normalize('https://www.youtube.com/playlist?list=PLabcdefghijk')
    result = YouTubeMetadataProvider('fixture-only', fetch=fetch, playlist_limit=2).metadata(source)
    assert len(pages) == 2 and len(result['items']) == 2 and result['truncated']
    assert [item['position'] for item in result['items']] == [1, 2]


def test_malformed_and_cyclic_provider_response_is_safe():
    source = YouTubeAdapter().normalize('https://www.youtube.com/playlist?list=PLabcdefghijk')
    provider = YouTubeMetadataProvider('fixture-only', fetch=lambda *_: {'items': [], 'nextPageToken': 'same-token'})
    with pytest.raises(SourceError) as error:
        provider.metadata(source)
    assert error.value.code == 'invalid_provider_response'


@pytest.mark.parametrize('change', [{'id': None}, {'id': 'duplicate'}, {'snippet': {'title': 'Fixture', 'position': True}}])
def test_playlist_item_identity_and_position_are_validated(change):
    source = YouTubeAdapter().normalize('https://www.youtube.com/playlist?list=PLabcdefghijk')
    first = {'id': 'duplicate', 'contentDetails': {'videoId': 'abcdefghijk'}, 'snippet': {'title': 'First', 'position': 0}}
    second = {'id': 'second', 'contentDetails': {'videoId': 'abcdefghijk'}, 'snippet': {'title': 'Second', 'position': 1}, **change}
    with pytest.raises(SourceError) as error:
        YouTubeMetadataProvider('fixture-only', fetch=lambda *_: {'items': [first, second]}).metadata(source)
    assert error.value.code == 'invalid_provider_response'

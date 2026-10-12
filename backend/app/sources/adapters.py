from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import re
from typing import Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .contracts import SourceError


@dataclass(frozen=True)
class NormalizedSource:
    kind: str
    provider: str
    canonical_id: str | None
    title: str
    metadata: dict = field(default_factory=dict)


class SourceAdapter(Protocol):
    def normalize(self, value: str) -> NormalizedSource: ...


class TranscriptAdapter:
    def normalize(self, value: str) -> NormalizedSource:
        filename = value.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
        if not 1 <= len(filename) <= 255 or not filename.lower().endswith(('.srt', '.vtt')):
            raise SourceError('unsupported_file', 'Only text SRT/VTT uploads are available; binary media processing is not configured.')
        return NormalizedSource('transcript', 'upload', None, filename)


class YouTubeAdapter:
    def normalize(self, value: str) -> NormalizedSource:
        try:
            url = urlsplit(value)
            if url.scheme != 'https' or url.hostname not in {'youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be'}:
                raise ValueError()
            if url.username or url.password or url.port is not None or url.fragment:
                raise ValueError()
            # Reject ambiguous duplicate IDs, escaped hostnames and unsupported paths.
            query = parse_qs(url.query)
            if any(len(query.get(key, [])) > 1 for key in ('v', 'list')):
                raise ValueError()
            if url.hostname == 'youtu.be':
                kind, identifier = 'youtube_video', url.path.strip('/')
            elif url.path == '/watch':
                kind, identifier = 'youtube_video', query.get('v', [''])[0]
            elif url.path.startswith(('/shorts/', '/embed/')):
                kind, identifier = 'youtube_video', url.path.split('/')[-1]
            elif url.path == '/playlist':
                kind, identifier = 'youtube_playlist', query.get('list', [''])[0]
            else:
                raise ValueError()
            pattern = r'[a-zA-Z0-9_-]{11}' if kind == 'youtube_video' else r'[a-zA-Z0-9_-]{10,120}'
            if not re.fullmatch(pattern, identifier):
                raise ValueError()
        except ValueError:
            raise SourceError('unsupported_url', 'Use an HTTPS YouTube video or playlist URL without credentials, custom ports or redirects.') from None
        canonical = f'https://www.youtube.com/watch?v={identifier}' if kind == 'youtube_video' else f'https://www.youtube.com/playlist?list={identifier}'
        return NormalizedSource(kind, 'youtube', identifier, identifier, {'canonical_url': canonical})


class NoRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class YouTubeMetadataProvider:
    """Only fixed official endpoints, bounded responses, no download/caption fallback."""

    def __init__(self, api_key: str, *, fetch=None, playlist_limit: int = 100):
        self.api_key = api_key
        self.fetch = fetch or self._fetch
        self.playlist_limit = min(100, max(1, playlist_limit))

    def _fetch(self, resource: str, parameters: dict) -> dict:
        if resource not in {'videos', 'playlistItems'}:
            raise ValueError('unsupported metadata resource')
        request = Request(f'https://www.googleapis.com/youtube/v3/{resource}?{urlencode({**parameters, "key": self.api_key})}', headers={'Accept': 'application/json'})
        try:
            with build_opener(NoRedirects).open(request, timeout=5) as response:
                body = response.read(1_000_001)
            if len(body) > 1_000_000:
                raise ValueError('oversized response')
            payload = json.loads(body)
            if not isinstance(payload, dict):
                raise ValueError()
            return payload
        except HTTPError as exc:
            if 300 <= exc.code < 400:
                raise SourceError('provider_redirect_rejected', 'The metadata provider returned an unsupported redirect.') from None
            raise SourceError('metadata_unavailable', 'YouTube metadata is unavailable; check API configuration or retry later.', 503, transient=exc.code == 429 or exc.code >= 500) from None
        except (URLError, TimeoutError, OSError):
            raise SourceError('metadata_unavailable', 'YouTube metadata is temporarily unavailable; retry later.', 503, transient=True) from None
        except (ValueError, KeyError, TypeError):
            raise SourceError('invalid_provider_response', 'The metadata provider returned an unsupported response.') from None

    @staticmethod
    def _title(value) -> str:
        if not isinstance(value, str):
            raise SourceError('invalid_provider_response', 'The metadata provider returned an unsupported title.')
        return ''.join(char for char in value if ord(char) >= 32)[:255] or 'Untitled video'

    def metadata(self, source: NormalizedSource) -> dict:
        if not self.api_key:
            raise SourceError('provider_not_configured', 'Set a server-side YouTube Data API key to import metadata. Uploading transcripts does not require a key.', 503)
        if source.kind not in {'youtube_video', 'youtube_playlist'} or not source.canonical_id:
            raise ValueError('unsupported metadata source')
        items = []
        truncated = False
        try:
            if source.kind == 'youtube_video':
                payload = self.fetch('videos', {'part': 'snippet', 'id': source.canonical_id})
                matches = [item for item in payload.get('items', []) if item.get('id') == source.canonical_id]
                if not matches:
                    raise SourceError('metadata_not_found', 'The video was not found or is not available.', 404)
                title = self._title(matches[0]['snippet']['title'])
                items = [{'video_id': source.canonical_id, 'title': title, 'position': 0}]
            else:
                page = None
                seen_pages = set()
                for _ in range(3):
                    params = {'part': 'snippet,contentDetails', 'playlistId': source.canonical_id, 'maxResults': min(50, self.playlist_limit-len(items))}
                    if page:
                        params['pageToken'] = page
                    payload = self.fetch('playlistItems', params)
                    for item in payload.get('items', []):
                        video_id = item['contentDetails']['videoId']
                        if not isinstance(video_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{11}', video_id):
                            raise ValueError()
                        position = item['snippet']['position']
                        item_id = item['id']
                        if not isinstance(item_id, str) or not re.fullmatch(r'[a-zA-Z0-9_+=./-]{1,512}', item_id):
                            raise ValueError()
                        if type(position) is not int or not 0 <= position <= 1_000_000:
                            raise ValueError()
                        items.append({'item_id': item_id, 'video_id': video_id, 'title': self._title(item['snippet']['title']), 'position': position})
                        if len(items) == self.playlist_limit:
                            break
                    page = payload.get('nextPageToken')
                    if not page:
                        break
                    if not isinstance(page, str) or len(page) > 512 or page in seen_pages:
                        raise ValueError()
                    seen_pages.add(page)
                    if len(items) >= self.playlist_limit:
                        truncated = True
                        break
                else:
                    truncated = bool(page)
                items.sort(key=lambda item: item['position'])
                if len({item['position'] for item in items}) != len(items) or len({item['item_id'] for item in items}) != len(items):
                    raise ValueError()
                title = f'Playlist {source.canonical_id}'
            return {**source.metadata, 'title': title, 'items': items, 'truncated': truncated,
                    'retrieved_at': datetime.now(timezone.utc).isoformat(), 'provider_version': 'youtube-data-api-v3',
                    'needs_authorized_transcript': True}
        except (ValueError, KeyError, TypeError, AttributeError):
            raise SourceError('invalid_provider_response', 'The metadata provider returned an unsupported response.') from None

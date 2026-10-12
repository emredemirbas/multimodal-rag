"""Bounded local Qwen embeddings, with no downloads or provider fallback."""
import json
import math
from threading import BoundedSemaphore
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from .embedding_profiles import QWEN_DIGEST, QWEN_MODEL, QWEN_SPACE, QUERY_PREFIX
from .local_model import NoRedirects, checked_local_url
from .providers import DeterministicHashEmbeddingProvider, EmbeddingBatch
from .sources.contracts import SourceError

BATCH_SIZE = 8


class OllamaEmbeddingProvider:
    name = 'ollama-local'
    model = QWEN_MODEL
    model_digest = QWEN_DIGEST
    dimensions = 1024
    space_id = QWEN_SPACE

    def __init__(self, base_url: str):
        self.base_url = checked_local_url(base_url)
        self.opener = build_opener(ProxyHandler({}), NoRedirects())
        self.capacity = BoundedSemaphore(1)

    def _request(self, path: str, payload=None, *, timeout: float = 1) -> dict:
        data = json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None
        request = Request(self.base_url + path, data=data, headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=timeout) as response:
                body = response.read(400_001)
            if len(body) > 400_000:
                raise ValueError()
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except HTTPError as error:
            if error.code == 400:
                raise SourceError('embedding_input_limit', 'The local model rejected the input. Shorten the question or split the transcript.', 422) from None
            raise SourceError('local_embeddings_unavailable', 'Start local-ai, install its embedding model, free resources or retry shortly.', 503, transient=True) from None
        except (URLError, TimeoutError, OSError):
            raise SourceError('local_embeddings_unavailable', 'Start local-ai, install its embedding model, free resources or retry shortly.', 503, transient=True) from None
        except (ValueError, UnicodeError):
            raise SourceError('invalid_embeddings', 'The local embedding response could not be validated.', 503) from None

    def _check_manifest(self):
        models = self._request('/api/tags').get('models')
        if not isinstance(models, list) or len(models) > 100:
            raise SourceError('invalid_embeddings', 'The embedding manifest could not be validated.', 503)
        matches = [item for item in models if isinstance(item, dict) and item.get('name') == self.model]
        if not matches:
            raise SourceError('local_embeddings_not_installed', 'Explicitly install qwen3-embedding:0.6b in local-ai.', 503)
        if len(matches) != 1 or matches[0].get('digest') != self.model_digest:
            raise SourceError('embedding_model_changed', 'The embedding manifest changed. Restore the approved model; a new model requires a new index version.', 503)

    def _embed(self, texts: Sequence[str], *, timeout: float) -> EmbeddingBatch:
        if not 1 <= len(texts) <= BATCH_SIZE or any(not isinstance(text, str) or not text.strip() or len(text) > 2200 for text in texts):
            raise SourceError('embedding_input_limit', 'Split the transcript into smaller inputs.', 422)
        if not self.capacity.acquire(blocking=False):
            raise SourceError('local_embeddings_busy', 'Local embedding capacity is busy. Retry shortly.', 503, transient=True)
        try:
            self._check_manifest()
            result = self._request('/api/embed', {'model': self.model, 'input': list(texts), 'truncate': False,
                'keep_alive': 0, 'options': {'num_ctx': 2048}}, timeout=timeout)
            vectors, tokens = result.get('embeddings'), result.get('prompt_eval_count')
            if (result.get('model') != self.model or not isinstance(vectors, list) or len(vectors) != len(texts)
                    or (tokens is not None and (type(tokens) is not int or not 0 <= tokens <= 100_000))):
                raise SourceError('invalid_embeddings', 'The local embedding response could not be validated.', 503)
            normalized = []
            for vector in vectors:
                if (not isinstance(vector, list) or len(vector) != self.dimensions
                        or any(type(value) not in {float, int} or not -1.001 <= value <= 1.001 or not math.isfinite(value) for value in vector)):
                    raise SourceError('invalid_embeddings', 'The local embedding vector could not be validated.', 503)
                norm = math.sqrt(sum(value * value for value in vector))
                if not math.isfinite(norm) or norm < 1e-12:
                    raise SourceError('invalid_embeddings', 'The local embedding vector could not be validated.', 503)
                normalized.append([value / norm for value in vector])
            self._check_manifest()  # Never label a response with a cached mutable tag.
            return EmbeddingBatch(normalized, tokens)
        finally:
            self.capacity.release()

    def embed(self, text: str) -> list[float]:
        return self.embed_documents([text]).vectors[0]

    def embed_query(self, text: str) -> EmbeddingBatch:
        return self._embed([QUERY_PREFIX + text], timeout=6)

    def embed_documents(self, texts: Sequence[str]) -> EmbeddingBatch:
        if any(not isinstance(text, str) or len(text) > 1200 for text in texts):
            raise SourceError('embedding_input_limit', 'Split the transcript into smaller inputs.', 422)
        return self._embed(texts, timeout=20)


def build_embedding_provider(settings):
    return OllamaEmbeddingProvider(settings.ollama_base_url) if settings.embedding_provider == 'ollama' else DeterministicHashEmbeddingProvider()

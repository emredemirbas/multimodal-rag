"""Immutable vector spaces; a model tag alone is not an index identity."""
HASH_SPACE = 'signed-hash-v1:64'
QWEN_MODEL = 'qwen3-embedding:0.6b'
QWEN_DIGEST = 'ac6da0dfba84a81fdbfbaf330198c33cd77c4cdfc53e8bc50eb581914a15621d'
QWEN_SPACE = f'qwen3-0.6b:{QWEN_DIGEST}:1024:query-v1'
QUERY_PREFIX = 'Instruct: Given a question about a programming tutorial, retrieve passages that answer the question.\nQuery: '
SEMANTIC_FLOOR = 0.40  # Experimental fixture-measured relevance guard, not confidence.


def configured_space(provider: str) -> str:
    return QWEN_SPACE if provider == 'ollama' else HASH_SPACE

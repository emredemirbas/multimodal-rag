"""Pinned local JSON inference for curriculum stages; no workflow is enabled."""

from dataclasses import dataclass, field
from hashlib import sha256
from http.client import HTTPException
import json
import math
from threading import BoundedSemaphore
from time import perf_counter
from typing import Callable, Literal, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from pydantic import ConfigDict, Field, JsonValue

from ..local_model import NoRedirects, checked_local_url
from .contracts import Contract, Digest
from .run_contracts import Identifier


REQUEST_VERSION = "curriculum-json-call-v1"
MAX_INPUT_BYTES = 12_000
MAX_SCHEMA_BYTES = 16_000
MAX_REQUEST_BYTES = 65_536
MAX_RESPONSE_BYTES = 262_144
MAX_OUTPUT_BYTES = 128_000
CALL_SECONDS = 60
METADATA_SECONDS = 2
INFERENCE_SECONDS = 42
OPTIONS = {"temperature": 0, "num_ctx": 16_384, "num_predict": 2048, "num_thread": 4}


class CurriculumProviderError(Exception):
    def __init__(self, code: Literal["provider_unavailable", "provider_timeout", "invalid_output"], *, retryable: bool):
        self.code, self.retryable = code, retryable
        self.input_tokens = self.output_tokens = self.duration_ms = None
        super().__init__("The local curriculum model request could not be completed.")


class LocalModelIdentity(Contract):
    model_config = ConfigDict(frozen=True)
    provider: Literal["ollama-local"] = "ollama-local"
    model: Literal["qwen3:4b"] = "qwen3:4b"
    model_digest: Digest
    engine: str = Field(min_length=1, max_length=64,
                        pattern=r"^[0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?$")


class JsonCallSpec(Contract):
    purpose: Identifier
    prompt_version: Identifier
    schema_version: Identifier
    system: str = Field(min_length=1, max_length=12_000, repr=False)
    user: str = Field(min_length=1, max_length=12_000, repr=False)
    output_schema: dict[str, JsonValue] = Field(repr=False)


@dataclass(frozen=True)
class PreparedCall:
    identity: LocalModelIdentity
    spec: JsonCallSpec
    input_sha256: str
    input_characters: int
    payload: bytes = field(repr=False)


class JsonModelResponse(Contract):
    identity: LocalModelIdentity
    input_sha256: Digest
    content: str = Field(min_length=1, repr=False)
    input_tokens: int | None = Field(ge=0, le=100_000)
    output_tokens: int | None = Field(ge=0, le=2048)
    duration_ms: int = Field(ge=0, le=60_000)


class CurriculumJsonProvider(Protocol):
    def prepare(self, spec: JsonCallSpec) -> PreparedCall: ...

    def complete(self, prepared: PreparedCall, *, before_inference: Callable[[], bool]) -> JsonModelResponse | None: ...


def _invalid():
    return CurriculumProviderError("invalid_output", retryable=False)


def _json_bytes(value) -> bytes:
    def compatible(item):
        if isinstance(item, str):
            return "\x00" not in item
        if isinstance(item, list):
            return all(compatible(child) for child in item)
        if isinstance(item, dict):
            return all(type(key) is str and compatible(key) and compatible(child) for key, child in item.items())
        return item is None or type(item) in {bool, int} or type(item) is float and math.isfinite(item)

    try:
        if not compatible(value):
            raise ValueError()
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise _invalid() from None


def _json_object(raw: bytes | str):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError()
            result[key] = value
        return result

    def invalid_constant(_):
        raise ValueError()

    try:
        value = json.loads(raw.decode("utf-8") if type(raw) is bytes else raw,
                           object_pairs_hook=unique, parse_constant=invalid_constant)
        if type(value) is not dict:
            raise ValueError()
        _json_bytes(value)
        return value
    except (ValueError, TypeError, RecursionError, UnicodeError):
        raise _invalid() from None


class LocalCurriculumProvider:
    def __init__(self, base_url: str, identity: LocalModelIdentity):
        self.base_url = checked_local_url(base_url)
        try:
            if not isinstance(identity, LocalModelIdentity):
                raise ValueError()
            self.identity = LocalModelIdentity.model_validate(identity.model_dump(warnings=False), strict=True)
        except (ValueError, TypeError, AttributeError):
            raise ValueError("An explicit local model digest and engine pin are required.") from None
        self.opener = build_opener(ProxyHandler({}), NoRedirects())
        self.capacity = BoundedSemaphore(1)

    @staticmethod
    def _remaining(deadline, limit):
        remaining = min(limit, deadline - perf_counter())
        if remaining <= 0:
            raise CurriculumProviderError("provider_timeout", retryable=True)
        return remaining

    def _request(self, path, data=None, *, deadline, timeout):
        request = Request(self.base_url + path, data=data,
                          headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.opener.open(request, timeout=self._remaining(deadline, timeout)) as response:
                if response.status != 200 or response.headers.get_content_type() != "application/json":
                    raise _invalid()
                if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                    raise _invalid()
                declared = response.headers.get("Content-Length")
                if (len(response.headers.get_all("Content-Length", [])) > 1
                        or declared is not None and response.headers.get("Transfer-Encoding") is not None):
                    raise _invalid()
                if declared is not None and (len(declared) > 6 or not declared.isascii() or not declared.isdecimal()
                                              or int(declared) > MAX_RESPONSE_BYTES):
                    raise _invalid()
                body = bytearray()
                while True:
                    self._remaining(deadline, timeout)
                    chunk = response.read1(min(8192, MAX_RESPONSE_BYTES + 1 - len(body)))
                    self._remaining(deadline, timeout)
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > MAX_RESPONSE_BYTES:
                        raise _invalid()
                if declared is not None and len(body) != int(declared):
                    raise _invalid()
            return _json_object(bytes(body))
        except HTTPError as error:
            retryable = error.code in {408, 429, 500, 502, 503, 504}
            error.close()
            raise CurriculumProviderError("provider_unavailable", retryable=retryable) from None
        except (TimeoutError, URLError, OSError) as error:
            timed_out = isinstance(error, TimeoutError) or isinstance(getattr(error, "reason", None), TimeoutError)
            raise CurriculumProviderError("provider_timeout" if timed_out else "provider_unavailable", retryable=True) from None
        except HTTPException:
            raise _invalid() from None

    def _ready(self, deadline):
        tags = self._request("/api/tags", deadline=deadline, timeout=METADATA_SECONDS).get("models")
        if type(tags) is not list or len(tags) > 100:
            raise _invalid()
        matches = [item for item in tags if type(item) is dict and item.get("name") == self.identity.model]
        if (len(matches) != 1 or matches[0].get("digest") != self.identity.model_digest
                or matches[0].get("remote_model") not in (None, "") or matches[0].get("remote_host") not in (None, "")):
            raise CurriculumProviderError("provider_unavailable", retryable=False)
        info = self._request("/api/show", _json_bytes({"model": self.identity.model}),
                             deadline=deadline, timeout=METADATA_SECONDS)
        version = self._request("/api/version", deadline=deadline, timeout=METADATA_SECONDS).get("version")
        if (info.get("remote_host") not in (None, "") or info.get("remote_model") not in (None, "")
                or type(info.get("capabilities")) is not list
                or "completion" not in info["capabilities"] or type(info.get("details")) is not dict
                or info["details"].get("family") != "qwen3" or version != self.identity.engine):
            raise CurriculumProviderError("provider_unavailable", retryable=False)

    def prepare(self, spec: JsonCallSpec) -> PreparedCall:
        try:
            if not isinstance(spec, JsonCallSpec):
                raise ValueError()
            spec = JsonCallSpec.model_validate(spec.model_dump(warnings=False), strict=True)
            size = len(spec.system.encode("utf-8")) + len(spec.user.encode("utf-8"))
            if (size > MAX_INPUT_BYTES or not spec.system.strip() or not spec.user.strip()
                    or spec.output_schema.get("type") != "object"
                    or len(_json_bytes(spec.output_schema)) > MAX_SCHEMA_BYTES):
                raise ValueError()

            def local_references(value):
                if isinstance(value, dict):
                    if "$ref" in value and (type(value["$ref"]) is not str or not value["$ref"].startswith("#/")):
                        raise ValueError()
                    for nested in value.values():
                        local_references(nested)
                elif isinstance(value, list):
                    for nested in value:
                        local_references(nested)

            local_references(spec.output_schema)
            payload = _json_bytes({"model": self.identity.model, "stream": False, "think": False, "keep_alive": 0,
                                   "format": spec.output_schema, "options": OPTIONS,
                                   "messages": [{"role": "system", "content": spec.system},
                                                {"role": "user", "content": spec.user}]})
            if len(payload) > MAX_REQUEST_BYTES:
                raise ValueError()
            return PreparedCall(self.identity, spec, sha256(payload).hexdigest(), len(spec.system) + len(spec.user), payload)
        except (ValueError, TypeError, AttributeError, RecursionError, UnicodeError):
            raise _invalid() from None

    def complete(self, prepared: PreparedCall, *, before_inference: Callable[[], bool]) -> JsonModelResponse | None:
        if not isinstance(prepared, PreparedCall) or self.prepare(prepared.spec) != prepared:
            raise _invalid()
        if not self.capacity.acquire(blocking=False):
            raise CurriculumProviderError("provider_unavailable", retryable=True)
        deadline = perf_counter() + CALL_SECONDS
        try:
            self._ready(deadline)
            if before_inference() is not True:
                return None
            started = perf_counter()
            counts = [None, None]
            duration = None
            try:
                payload = self._request("/api/chat", prepared.payload, deadline=deadline, timeout=INFERENCE_SECONDS)
                duration = round((perf_counter() - started) * 1000)
                message = payload.get("message")
                values = [payload.get("prompt_eval_count"), payload.get("eval_count")]
                if any(value is not None and (type(value) is not int or not 0 <= value <= bound)
                       for value, bound in zip(values, (100_000, OPTIONS["num_predict"]))):
                    raise _invalid()
                counts = values
                if (payload.get("done") is not True or payload.get("done_reason") != "stop"
                        or payload.get("model") != self.identity.model or type(message) is not dict
                        or message.get("role") != "assistant" or message.get("tool_calls")
                        or message.get("thinking") or type(message.get("content")) is not str
                        or not message["content"].strip() or len(message["content"].encode("utf-8")) > MAX_OUTPUT_BYTES):
                    raise _invalid()
                _json_object(message["content"])
                self._ready(deadline)
                self._remaining(deadline, CALL_SECONDS)
                return JsonModelResponse(identity=self.identity, input_sha256=prepared.input_sha256,
                                         content=message["content"], input_tokens=counts[0], output_tokens=counts[1],
                                         duration_ms=duration)
            except (ValueError, TypeError, UnicodeError, AttributeError, RecursionError):
                error = _invalid()
                error.input_tokens, error.output_tokens = counts
                error.duration_ms = duration if duration is not None else round((perf_counter() - started) * 1000)
                raise error from None
            except CurriculumProviderError as error:
                error.input_tokens, error.output_tokens = counts
                error.duration_ms = duration if duration is not None else round((perf_counter() - started) * 1000)
                raise
        finally:
            self.capacity.release()

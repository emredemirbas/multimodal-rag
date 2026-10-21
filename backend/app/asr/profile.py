"""Immutable approved public model, input encoding and decoding policy."""
import hashlib
import json
from pathlib import Path

PROVIDER = "faster-whisper-local"
MODEL = "whisper-base"
REVISION = "a80717a3a48b1b28aa687bca146cb7301feae1b1"
REPOSITORY = "Systran/faster-whisper-base"
FILES = {
    "config.json": (2309, "56a6d8110d311f19c8f0471e562832c7527f146b567275bfca59fcf7c184da9a"),
    "model.bin": (145217532, "d01c3014881c9c6f3133c182f3d2887eb6ca1c789a7538c5c007196857a0a6a9"),
    "tokenizer.json": (2203239, "fb7b63191e9bb045082c79fd742a3106a12c99513ab30df4a0d47fa6cb6fd0ab"),
    "vocabulary.txt": (459861, "34ce3fe1c5041027b3f8d42912270993f986dbc4bb34cf27f951e34a1e453913"),
}
ENGINE = "faster-whisper:1.2.1/ctranslate2:4.8.2"
PROFILE = "local-whisper-base-v1:" + hashlib.sha256(json.dumps(
    [REVISION, ENGINE, FILES, "pcm16-16k-mono", "beam1-temp0-tokens256-no-history-no-vad-v1"],
    sort_keys=True, separators=(",", ":"),
).encode()).hexdigest()
MODEL_DIRECTORY = Path("/models") / f"whisper-base-{REVISION}"
MAX_RESPONSE_BYTES = 32_768
INFERENCE_SECONDS = 35


def verify_model(directory: Path = MODEL_DIRECTORY) -> None:
    """Verify bytes, not a mutable Hub name or self-reported manifest."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Approved local ASR weights are not installed")
    for name, (size, expected) in FILES.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or path.stat().st_size != size:
            raise ValueError("Approved local ASR weights are incomplete")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != expected:
            raise ValueError("Approved local ASR weights changed")


def identity() -> dict:
    return {"provider": PROVIDER, "model": MODEL, "revision": REVISION, "profile": PROFILE, "engine": ENGINE,
            "network_policy": "outbound-denied"}


def encode_result(result: dict) -> bytes:
    data = json.dumps(result, ensure_ascii=False, allow_nan=False).encode("utf-8")
    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("ASR output exceeds its byte limit")
    return data

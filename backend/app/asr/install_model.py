"""Explicit public-weight setup only; never imported by a user request."""
import fcntl
import hashlib
from pathlib import Path
import tempfile
from time import monotonic
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

from . import profile


def checked_download_url(value: str) -> str:
    url = urlsplit(value)
    host = url.hostname or ""
    if (url.scheme != "https" or url.username is not None or url.password is not None
            or url.port not in {None, 443} or url.fragment
            or not (host == "huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co"))):
        raise ValueError("Model download redirect is not an approved public weights host")
    return value


class PublicWeightsRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, checked_download_url(newurl))


def install(root: Path = Path("/models")) -> None:
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Use the dedicated local model volume")
    target = root / profile.MODEL_DIRECTORY.name
    opener = build_opener(ProxyHandler({}), PublicWeightsRedirect())
    # Concurrent setup commands cannot replace a verified immutable installation.
    with (root / ".whisper-base-install.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if target.exists() or target.is_symlink():
            profile.verify_model(target)
            return
        with tempfile.TemporaryDirectory(prefix=".whisper-base-", dir=root) as temporary:
            staging = Path(temporary)
            for name, (size, digest) in profile.FILES.items():
                url = checked_download_url(f"https://huggingface.co/{profile.REPOSITORY}/resolve/{profile.REVISION}/{name}")
                count, checksum, deadline = 0, hashlib.sha256(), monotonic() + 300
                with opener.open(url, timeout=30) as response, (staging / name).open("xb") as output:
                    while True:
                        if monotonic() > deadline:
                            raise TimeoutError("Public model download exceeded its setup deadline")
                        block = response.read1(min(1024 * 1024, size - count + 1))
                        if not block:
                            break
                        count += len(block)
                        if count > size:
                            raise ValueError("Public model download exceeds its pinned size")
                        checksum.update(block)
                        output.write(block)
                if count != size or checksum.hexdigest() != digest:
                    raise ValueError("Public model download checksum mismatch")
            profile.verify_model(staging)
            staging.rename(target)


if __name__ == "__main__":
    try:
        install()
        print("Approved local Whisper base weights installed and verified. No audio was sent.")
    except Exception:
        raise SystemExit("Local ASR setup failed; check connectivity, disk space and the pinned model checksums. Existing weights were not overwritten.") from None

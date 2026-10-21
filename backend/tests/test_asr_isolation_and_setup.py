import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

from app.asr import profile
from app.asr.install_model import checked_download_url, install
from app.asr.server import infer
from app.asr.smoke import synthetic_health_terms
from test_local_asr import result


def test_synthetic_probe_accepts_equivalent_words_not_identifier_substrings():
    assert synthetic_health_terms("The HEALTH endpoint works.")
    assert synthetic_health_terms("The health end point works.")
    assert not synthetic_health_terms("A healthy sendpoint.")
    assert not synthetic_health_terms("Health alone does not identify the route.")


def test_actual_kernel_filter_is_inherited_and_preserves_inbound_http():
    source = textwrap.dedent("""
        import errno,json,socket,subprocess,sys,threading
        from app.asr.isolation import block_outbound_sockets
        listener=socket.socket()
        listener.bind(('127.0.0.1',0)); listener.listen(1)
        block_outbound_sockets()
        print(listener.getsockname()[1],flush=True)
        blocked=[]
        def inspect():
            for family in [socket.AF_INET,socket.AF_INET6,socket.AF_UNIX]:
                try: socket.socket(family,socket.SOCK_STREAM)
                except OSError as error: blocked.append(error.errno==errno.EPERM)
        thread=threading.Thread(target=inspect); thread.start(); thread.join()
        try: socket.socketpair()
        except OSError as error: blocked.append(error.errno==errno.EPERM)
        code='import socket,sys; socket.socket()'
        child=subprocess.run([sys.executable,'-c',code],capture_output=True)
        blocked.append(child.returncode!=0 and b'Operation not permitted' in child.stderr)
        connection,_=listener.accept()
        assert connection.recv(2)==b'ok'
        connection.sendall(b'yes'); connection.close(); listener.close()
        print(json.dumps(blocked),flush=True)
    """)
    # No filter is installed in pytest/the user's application process.
    with subprocess.Popen([sys.executable, "-c", source], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          text=True, env={"PYTHONPATH": str(Path(__file__).parents[1])}) as child:
        import select
        assert select.select([child.stdout], [], [], 10)[0], "Owned seccomp probe did not start"
        port = child.stdout.readline().strip()
        assert port.isdigit(), "Owned seccomp probe failed to initialize"
        import socket
        with socket.create_connection(("127.0.0.1", int(port)), timeout=2) as connection:
            connection.sendall(b"ok")
            assert connection.recv(3) == b"yes"
        stdout, stderr = child.communicate(timeout=10)
        assert child.returncode == 0 and not stderr
        assert json.loads(stdout) == [True] * 5


def test_setup_checksums_atomicity_existing_weights_and_no_proxy(tmp_path, monkeypatch):
    data = b"owned tiny model fixture"
    monkeypatch.setattr(profile, "FILES", {"model.bin": (len(data), hashlib.sha256(data).hexdigest())})
    requests = []
    class Opener:
        def open(self, url, timeout):
            requests.append(url)
            return io.BytesIO(data)
    monkeypatch.setattr("app.asr.install_model.build_opener", lambda *args: Opener())
    monkeypatch.setenv("HF_TOKEN", "not-to-be-used")
    monkeypatch.setenv("HTTP_PROXY", "http://unreachable.invalid")
    install(tmp_path)
    target = tmp_path / profile.MODEL_DIRECTORY.name
    profile.verify_model(target)
    assert requests == [f"https://huggingface.co/{profile.REPOSITORY}/resolve/{profile.REVISION}/model.bin"]
    assert not any(path.is_dir() and path.name.startswith(".whisper-base-") for path in tmp_path.iterdir())
    install(tmp_path)
    assert len(requests) == 1
    # A changed existing installation is not overwritten or silently accepted.
    (target / "model.bin").write_bytes(b"changed")
    with pytest.raises(ValueError): install(tmp_path)
    assert (target / "model.bin").read_bytes() == b"changed" and len(requests) == 1


def test_corrupt_download_and_symlinks_fail_without_activating(tmp_path, monkeypatch):
    monkeypatch.setattr(profile, "FILES", {"model.bin": (3, hashlib.sha256(b"yes").hexdigest())})
    class Opener:
        def open(self, *args, **kwargs): return io.BytesIO(b"bad and oversized")
    monkeypatch.setattr("app.asr.install_model.build_opener", lambda *args: Opener())
    with pytest.raises(ValueError): install(tmp_path)
    target = tmp_path / profile.MODEL_DIRECTORY.name
    assert not target.exists() and len(list(tmp_path.iterdir())) == 1  # Only the public setup lock.
    target.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError): install(tmp_path)
    for value in ["http://huggingface.co/file", "https://evil-huggingface.co/file", "https://huggingface.co.evil.invalid/file", "https://127.0.0.1/file", "https://user:secret@huggingface.co/file", "https://huggingface.co:444/file"]:
        with pytest.raises(ValueError): checked_download_url(value)


def test_child_receives_only_pcm_and_safe_environment_and_has_wall_deadline(monkeypatch):
    pcm = b"\x00\x00" * 16000
    observed = {}
    class Child:
        pid = 999_999_999  # Not a real OS process; killpg is intercepted below.
        returncode = 0
        def __init__(self, args, **kwargs):
            observed.update({"args": args, **kwargs})
            self.output = kwargs["stdout"]
            self.timeout_once = observed.get("fail", False)
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def communicate(self, data=None, timeout=None):
            observed["timeout"] = timeout
            if self.timeout_once:
                self.timeout_once = False
                raise subprocess.TimeoutExpired("owned-child", timeout)
            if data is not None:
                assert data == pcm
                self.output.write(profile.encode_result(result(pcm, "en")))
    monkeypatch.setenv("DATABASE_URL", "private-database")
    monkeypatch.setenv("DEVELOPMENT_AUTH_TOKEN", "private-token")
    monkeypatch.setattr("app.asr.server.subprocess.Popen", Child)
    assert infer(pcm, "en")["segments"]
    assert observed["timeout"] == profile.INFERENCE_SECONDS
    assert "DATABASE_URL" not in observed["env"] and "DEVELOPMENT_AUTH_TOKEN" not in observed["env"]
    assert observed["start_new_session"] and observed["stderr"] == subprocess.DEVNULL
    observed["fail"] = True
    killed = []
    monkeypatch.setattr("app.asr.server.os.killpg", lambda pid, signal: killed.append(pid))
    with pytest.raises(RuntimeError, match="deadline"):
        infer(pcm, "en")
    assert killed == [Child.pid]

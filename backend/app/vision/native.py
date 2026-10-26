"""Fixed executable wrapper; only called from the already isolated visual tool."""
import os
import resource
import sys


def main():
    arguments = sys.argv[1:]
    if not arguments or arguments[0] not in {"/usr/bin/ffprobe", "/usr/bin/ffmpeg", "/usr/bin/tesseract"}:
        raise ValueError("Unsupported native tool")
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (10, 11))
    resource.setrlimit(resource.RLIMIT_AS, (1024 ** 3, 1024 ** 3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (2_000_000, 2_000_000))
    resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
    os.execve(arguments[0], arguments, {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
        "OMP_THREAD_LIMIT": "1", "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1"})


if __name__ == "__main__":
    try:
        main()
    except Exception:
        raise SystemExit("Visual native tool unavailable") from None

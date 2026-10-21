"""Inherited fail-closed network restriction layered on Docker's default seccomp."""
import ctypes
import errno
import resource
import socket


def block_outbound_sockets() -> None:
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    library = ctypes.CDLL("libseccomp.so.2", use_errno=True)
    library.seccomp_init.argtypes = [ctypes.c_uint32]
    library.seccomp_init.restype = ctypes.c_void_p
    library.seccomp_syscall_resolve_name.argtypes = [ctypes.c_char_p]
    library.seccomp_syscall_resolve_name.restype = ctypes.c_int
    library.seccomp_attr_set.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint32]
    library.seccomp_attr_set.restype = ctypes.c_int
    library.seccomp_rule_add.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_int, ctypes.c_uint]
    library.seccomp_rule_add.restype = ctypes.c_int
    library.seccomp_load.argtypes = [ctypes.c_void_p]
    library.seccomp_load.restype = ctypes.c_int
    library.seccomp_release.argtypes = [ctypes.c_void_p]
    context = library.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW; retains the outer Docker filter.
    if not context:
        raise RuntimeError("ASR network isolation is unavailable")
    try:
        # SCMP_FLTATR_CTL_TSYNC: cover existing threads and inherited children.
        if library.seccomp_attr_set(context, 4, 1) != 0:
            raise RuntimeError("ASR network isolation is unavailable")
        for name in (b"socket", b"socketpair", b"connect"):
            number = library.seccomp_syscall_resolve_name(name)
            if number < 0 or library.seccomp_rule_add(context, 0x00050000 | errno.EPERM, number, 0) != 0:
                raise RuntimeError("ASR network isolation is unavailable")
        if library.seccomp_load(context) != 0:
            raise RuntimeError("ASR network isolation is unavailable")
    finally:
        library.seccomp_release(context)
    # Fail startup unless the kernel actually enforces the restriction.
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    except OSError as error:
        if error.errno != errno.EPERM:
            raise RuntimeError("ASR network isolation is unavailable") from None
    else:
        probe.close()
        raise RuntimeError("ASR network isolation is unavailable")

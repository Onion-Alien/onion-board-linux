"""Linux support. The Windows modules (winkeys, midi, appaudio…) stay as they are
upstream apart from two small hooks, so new upstream releases merge cleanly:

  at the top     a Windows DLL becomes `NoDLL(...)` off Windows, so the module
                 still imports (its portable parts: tables, parsing, pure helpers)
  at the bottom  `from soundboard.linux.<name> import *` replaces the Windows-only
                 functions and classes with the Linux ones

`NoDLL` accepts the `.argtypes` / `.restype` set-up a module does at import time;
calling anything on it raises, so a Windows path that wasn't overridden fails loudly
instead of silently doing nothing.
"""
from __future__ import annotations

import sys

WIN = sys.platform == "win32"
LINUX = sys.platform.startswith("linux")


class _NoFunc:
    def __init__(self, name: str):
        self.__name__ = name

    def __call__(self, *_a, **_k):
        raise OSError(f"{self.__name__} is Windows-only")


class NoDLL:
    """Stands in for ctypes.WinDLL(name) off Windows."""

    def __init__(self, name: str, *_a, **_k):
        self._name = name
        self._funcs: dict[str, _NoFunc] = {}

    def __getattr__(self, attr: str) -> _NoFunc:
        if attr.startswith("__"):
            raise AttributeError(attr)
        f = self._funcs.get(attr)
        if f is None:
            f = self._funcs[attr] = _NoFunc(f"{self._name}.{attr}")
        return f


def win_dll(name: str, **kw):
    """ctypes.WinDLL(name, **kw) on Windows, a NoDLL elsewhere."""
    if WIN:
        import ctypes
        return ctypes.WinDLL(name, **kw)
    return NoDLL(name)


def winfunctype(*args):
    """ctypes.WINFUNCTYPE on Windows; CFUNCTYPE elsewhere (never called by Windows)."""
    import ctypes
    return (ctypes.WINFUNCTYPE if WIN else ctypes.CFUNCTYPE)(*args)


def data_home() -> str:
    """$XDG_DATA_HOME, or ~/.local/share."""
    import os
    from pathlib import Path
    return os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")


def config_home() -> str:
    """$XDG_CONFIG_HOME, or ~/.config."""
    import os
    from pathlib import Path
    return os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")


def use_bundled_portaudio() -> str | None:
    """In a built copy, make sounddevice load the PortAudio the build ships
    (build-linux.sh: ALSA only, no JACK) instead of searching the system for one.

    sounddevice asks ctypes.util.find_library("portaudio"), which only knows the
    system's libraries: without the distribution's libportaudio2 (most desktops)
    the app stopped at start with "PortAudio library not found", and with it the
    app ran on that copy, not its own. Returns the path used, or None (from source,
    or no bundled copy). Must run before sounddevice is imported."""
    import os
    if not getattr(sys, "frozen", False):
        return None
    path = os.path.join(getattr(sys, "_MEIPASS", ""), "libportaudio.so.2")
    if not os.path.isfile(path):
        return None
    import ctypes.util
    find = ctypes.util.find_library
    if getattr(find, "_bundled", None) == path:
        return path

    def find_library(name):
        return path if name == "portaudio" else find(name)
    find_library._bundled = path
    ctypes.util.find_library = find_library
    return path


# Where distributions keep the certificate authorities, as one file or a hashed folder
CA_FILES = (
    "/etc/ssl/certs/ca-certificates.crt",                  # Debian, Ubuntu, Arch, Gentoo
    "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem",   # Fedora, RHEL
    "/etc/pki/tls/certs/ca-bundle.crt",                    # older Fedora, RHEL
    "/etc/ssl/ca-bundle.pem",                              # openSUSE
    "/etc/ssl/cert.pem",                                   # Alpine, Arch
)
CA_DIRS = ("/etc/ssl/certs", "/etc/pki/tls/certs")


def use_system_certificates(files=CA_FILES, dirs=CA_DIRS) -> str | None:
    """Point OpenSSL at this distribution's certificate authorities when its built-in
    place has none.

    A built copy carries the build machine's OpenSSL (Ubuntu's), which looks in
    /usr/lib/ssl; Fedora keeps them under /etc/pki, so every secure connection
    (update check, radio, voice downloads) failed with "certificate verify failed".
    Sets SSL_CERT_FILE (or SSL_CERT_DIR), which Python, Qt and FFmpeg's OpenSSL all
    read, and returns what it set; leaves a user's own setting and a working
    default alone."""
    import os
    import ssl
    if os.environ.get("SSL_CERT_FILE") or os.environ.get("SSL_CERT_DIR"):
        return None
    paths = ssl.get_default_verify_paths()
    if os.path.isfile(paths.openssl_cafile or ""):
        return None
    capath = paths.openssl_capath or ""
    if os.path.isdir(capath) and any(n.endswith(".0") for n in os.listdir(capath)):
        return None
    for f in files:
        if os.path.isfile(f):
            os.environ["SSL_CERT_FILE"] = f
            return f
    for d in dirs:
        if os.path.isdir(d) and any(n.endswith(".0") for n in os.listdir(d)):
            os.environ["SSL_CERT_DIR"] = d
            return d
    return None


def selftest_problems() -> list[str]:
    """What `--selftest` checks on top of upstream's on Linux (a built copy)."""
    problems = []
    if LINUX and getattr(sys, "frozen", False):
        import os
        import sounddevice
        here = os.path.realpath(getattr(sys, "_MEIPASS", ""))
        lib = os.path.realpath(sounddevice._libname)
        if os.path.dirname(lib) != here:
            problems.append(f"PortAudio came from {lib}, not the build's own")
    return problems


if not WIN:
    use_bundled_portaudio()
    use_system_certificates()
    # Every "%APPDATA%\OnionBoard" in the app (library, splash, tor, ytdl…) reads the
    # APPDATA variable: pointing it at the XDG data folder puts all of it in
    # ~/.local/share/OnionBoard without touching those modules. app.py imports this
    # package before anything reads it.
    import os as _os
    _os.environ.setdefault("APPDATA", data_home())
    # the app's Windows wording, reworded for Linux as it reaches the screen
    # (soundboard/linux/wording.py: one table, no edits in the upstream modules)
    from soundboard.linux import wording as _wording
    _wording.install()

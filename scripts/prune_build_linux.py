"""Trim the PyInstaller output on Linux before it's packaged (build-linux.sh runs
this): the Linux counterpart of scripts/prune_build.py, whose rules it follows.

PySide6's wheel brings the whole Qt (QML, Quick 3D, Charts, Pdf, Wayland
compositor, Chromium's developer tools, 53 MB of translations…): 522 of the
build's 704 MB. This removes what the app never loads:

- Qt Python modules (`Qt*.abi3.so`) other than the ones the app imports
- `PySide6/Qt/lib/*.so*` that nothing left behind needs, found by walking each kept
  file's ELF `DT_NEEDED` entries (Qt's libraries, ICU, FFmpeg and its stubs)
- the QML folder, the QML / positioning / input-device plugins, platform plugins
  other than X11, Wayland and offscreen (`--selftest`), eglfs's integrations, the
  touch-screen keyboard and the PDF image reader
- Chromium's developer-tools resources
- Qt's translations and every WebEngine locale except en-US
- PyInstaller's links to removed libraries in `_internal/`
- ALSA's and Mesa's libraries (`HOST_LIBS`): those must be the user's own

Every kept file's libraries must then be in the build or be ones every desktop has
(`FROM_SYSTEM`).

Usage: python scripts/prune_build_linux.py dist/OnionBoard [--dry-run]
Exit 1 if a kept file needs a library that would be missing afterwards, so a change
in Qt's layout fails the build instead of shipping an app that can't start.
"""
from __future__ import annotations

import os
import shutil
import struct
import sys
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prune_build import KEEP_LOCALES, KEEP_MODULES, closure  # noqa: E402

# QtDBus: the desktop portal (Wayland hotkeys, file dialogs) talks D-Bus
KEEP_MODULES_LINUX = KEEP_MODULES | {"QtDBus"}
# X11 (and XWayland), native Wayland, and offscreen for `OnionBoard --selftest`
KEEP_PLATFORMS = frozenset({"libqxcb.so", "libqwayland.so", "libqoffscreen.so"})
DROP_PLUGIN_DIRS = ("qmltooling", "position", "generic", "egldeviceintegrations")
# the touch-screen keyboard (QML) and PDFs as images: Qt Pdf, Virtual Keyboard go too
DROP_PLUGINS = ("platforminputcontexts/libqtvirtualkeyboardplugin.so", "imageformats/libqpdf.so")

# Libraries that must be the user's own, never the build machine's: each loads
# parts of the user's system from a folder compiled into it. libasound: ALSA's
# plugins (the "pulse" device the app plays through), in
# /usr/lib/x86_64-linux-gnu/alsa-lib on the Ubuntu that builds the app but
# /usr/lib64/alsa-lib on Fedora and /usr/lib/alsa-lib on Arch. libgbm: Mesa's
# graphics driver, which must match it (and it needs libwayland-server, which the
# build didn't carry: the app didn't start without it). libstdc++ and libgcc_s:
# the user's graphics driver (Mesa) is built against the user's C++ runtime, newer
# than the build machine's (Ubuntu 22.04): with the build's one loaded first, Fedora
# 44's Mesa couldn't load (GLIBCXX_3.4.32 not found), Qt got no OpenGL and the
# window never drew. Every desktop has all four, and every one the app runs on
# (glibc 2.35 or newer) has a C++ runtime at least as new as the build's.
HOST_LIBS = ("libasound.so", "libgbm.so", "libstdc++.so", "libgcc_s.so")
# what the app may take from the user's system: the C library, the graphics stack
# (drivers' own libraries), the display server's client libraries and HOST_LIBS.
# A kept file needing anything else that isn't in the build is a problem: the
# AppImage would start only where the user happens to have it.
FROM_SYSTEM = ("libc.so", "libm.so", "libdl.so", "libpthread.so", "librt.so", "libresolv.so",
               "ld-linux", "libGL.so", "libEGL.so", "libGLX.so", "libOpenGL.so", "libdrm.so",
               "libxcb.so", "libxcb-dri3.so", "libwayland-client.so", "libwayland-cursor.so",
               "libwayland-egl.so") + HOST_LIBS

DT_NEEDED, DT_STRTAB_SECTION = 1, 3   # d_tag of a needed library; SHT_STRTAB
SHT_DYNAMIC = 6


def elf_needed(path: Path) -> list[str]:
    """The libraries `path` links against (its DT_NEEDED names), or [] for a file
    that isn't a 64-bit little-endian ELF. Reads the section table, no tools."""
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError:
        return []
    if data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
        return []
    try:
        shoff, = struct.unpack_from("<Q", data, 0x28)
        shentsize, shnum = struct.unpack_from("<HH", data, 0x3A)
        sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * shentsize)
                    for i in range(shnum)]
        names = []
        for _name, kind, _flags, _addr, off, size, link, _info, _align, entsize in sections:
            if kind != SHT_DYNAMIC:
                continue
            str_off = sections[link][4]
            for pos in range(off, off + size, entsize or 16):
                tag, val = struct.unpack_from("<qQ", data, pos)
                if tag == 0:
                    break
                if tag == DT_NEEDED:
                    end = data.index(b"\0", str_off + val)
                    names.append(data[str_off + val:end].decode("ascii", "replace"))
        return names
    except (struct.error, IndexError, ValueError):
        return []


def plan(app_dir: Path, needed_of: Callable[[Path], list[str]] = elf_needed
         ) -> tuple[list[Path], list[str]]:
    """(paths to delete, problems). A problem is a kept file needing a library that
    would be gone."""
    internal = app_dir / "_internal"
    pyside = internal / "PySide6"
    qt = pyside / "Qt"
    if not (qt / "lib").is_dir():
        return [], [f"no PySide6/Qt/lib folder under {app_dir}"]
    drop: list[Path] = []

    # 1. Python modules
    for so in pyside.glob("Qt*.abi3.so"):
        if so.name.split(".")[0] not in KEEP_MODULES_LINUX:
            drop.append(so)

    # 2. folders and files the app never opens
    for d in (qt / "qml", *(qt / "plugins" / n for n in DROP_PLUGIN_DIRS)):
        if d.is_dir():
            drop.append(d)
    drop += [qt / "plugins" / n for n in DROP_PLUGINS if (qt / "plugins" / n).exists()]
    for p in (qt / "plugins" / "platforms").glob("*.so"):
        if p.name not in KEEP_PLATFORMS:
            drop.append(p)
    for p in (qt / "resources").glob("*"):
        if ".debug." in p.name or "devtools" in p.name:
            drop.append(p)
    drop += list((qt / "translations").glob("*.qm"))
    for p in (qt / "translations" / "qtwebengine_locales").glob("*.pak"):
        if p.name not in KEEP_LOCALES:
            drop.append(p)
    for folder in (internal, qt / "lib"):
        drop += [p for p in folder.glob("*.so*") if p.name.startswith(HOST_LIBS)]

    # 3. libraries nothing left behind needs. Roots: every kept ELF file in the
    # PySide6 tree (modules, plugins, the WebEngine helper) and shiboken6
    dropped = {p.resolve() for p in drop}

    def kept(p: Path) -> bool:
        r = p.resolve()
        return not any(r == d or d in r.parents for d in dropped)

    # libpyside6qml and friends: PySide6's own libraries, kept if a kept file needs them
    side = {p.name: p for p in pyside.glob("libpyside6*.so*")}
    roots = [p for p in pyside.rglob("*") if p.is_file() and not p.is_symlink() and kept(p)
             and p.parent != qt / "lib" and p.name not in side
             and (".so" in p.name or p.parent.name == "libexec")]
    roots += list((internal / "shiboken6").glob("*.so*"))
    side_needed = closure(roots, side, needed_of)
    drop += [p for n, p in side.items() if n not in side_needed]
    roots += [side[n] for n in side_needed]
    pool = {p.name: p for p in (qt / "lib").iterdir() if p.is_file() and ".so" in p.name}
    needed = closure(roots, pool, needed_of)
    for name in sorted(set(pool) - needed):
        drop.append(pool[name])

    # 4. PyInstaller's links in _internal/ to what's going
    dropped = {p.resolve() for p in drop}
    for link in internal.iterdir():
        if link.is_symlink() and not kept(link):
            drop.append(link)

    # 5. sanity: nothing kept needs a file that's going
    gone = {p.name for p in drop}
    left = {p.name for p in internal.rglob("*") if kept(p)}
    problems = []
    for f in roots + [pool[n] for n in needed]:
        for name in needed_of(f):
            if name in gone and name not in left and not name.startswith(HOST_LIBS):
                problems.append(f"{f.relative_to(app_dir)} needs {name}, which would be removed")
    # 6. nothing kept needs a library that's neither in the build nor the system's own
    elf = [p for p in [app_dir / "OnionBoard", *internal.rglob("*")]
           if p.is_file() and not p.is_symlink() and kept(p)
           and (".so" in p.name or p.parent.name == "libexec" or p.parent == app_dir)]
    for f in elf:
        for name in needed_of(f):
            if name not in left and name not in gone and not name.startswith(FROM_SYSTEM):
                problems.append(f"{f.relative_to(app_dir)} needs {name}, which isn't in the "
                                "build (a user's system may not have it)")
    return drop, problems


def _size(p: Path) -> int:
    """Bytes under `p`, links not followed (PyInstaller links libraries into
    _internal/: folder_size would count them twice)."""
    if p.is_symlink():
        return 0
    if p.is_file():
        return p.stat().st_size
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file() and not f.is_symlink())


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    app_dir = Path(args[0])
    drop, problems = plan(app_dir)
    for msg in problems:
        print("ERROR:", msg)
    if problems:
        return 1
    before = _size(app_dir)
    freed = sum(_size(p) for p in drop)
    for p in sorted(drop):
        print(("would remove " if dry else "removing ") + str(p.relative_to(app_dir)))
        if not dry:
            if p.is_dir() and not p.is_symlink():
                shutil.rmtree(p)
            else:
                os.unlink(p)
    print(f"{'would free' if dry else 'freed'} {freed / 2**20:.0f} MB of {before / 2**20:.0f} MB "
          f"({len(drop)} items)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

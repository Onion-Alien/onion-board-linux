"""Put the app's own PortAudio (scripts/build_portaudio.sh: ALSA only) in place of
the distribution's copy PyInstaller collected, and remove the system libraries only
that copy needed (libjack, and Berkeley DB through it). build-linux.sh runs this.

Usage: python scripts/swap_portaudio.py dist/OnionBoard build/portaudio/libportaudio.so.2
Exit 1 if a library the new PortAudio needs isn't there, or one that's removed is
still needed by something else.
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from prune_build_linux import elf_needed  # noqa: E402

NAME = "libportaudio.so.2"
SYSTEM = ("libc.so", "libm.so", "libdl.so", "libpthread.so", "librt.so", "ld-linux")


def _elf_files(internal: Path) -> list[Path]:
    return [p for p in internal.rglob("*") if p.is_file() and not p.is_symlink()
            and (".so" in p.name or p.suffix == "")]


def swap(app_dir: Path, new_lib: Path, needed_of=elf_needed) -> list[str]:
    """Replace PortAudio; the removed libraries' names."""
    internal = app_dir / "_internal"
    target = internal / NAME
    loose = {p.name: p for p in internal.iterdir()
             if p.is_file() and not p.is_symlink() and ".so" in p.name}
    # what the old copy brought along: its NEEDED libraries, and theirs, in _internal/
    old_deps: set[str] = set()
    todo = list(needed_of(target)) if target.exists() else []
    while todo:
        n = todo.pop()
        if n in loose and n not in old_deps:
            old_deps.add(n)
            todo += needed_of(loose[n])
    shutil.copyfile(new_lib, target)
    target.chmod(0o755)
    missing = [n for n in needed_of(target) if n not in loose and not n.startswith(SYSTEM)]
    if missing:
        raise SystemExit(f"ERROR: the new PortAudio needs {', '.join(missing)}, not in the build")
    # drop what nothing else needs any more, until nothing changes
    removed: list[str] = []
    while True:
        users = set()
        for f in _elf_files(internal):
            users.update(needed_of(f))
        gone = [n for n in sorted(old_deps - set(removed)) if n not in users]
        if not gone:
            return removed
        for n in gone:
            loose[n].unlink()
            removed.append(n)


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    removed = swap(Path(argv[0]), Path(argv[1]))
    print(f"PortAudio swapped; removed {', '.join(removed) or 'nothing'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

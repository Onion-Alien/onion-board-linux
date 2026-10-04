"""THIRD-PARTY-NOTICES.txt for the Linux build (build-linux.sh runs this).

scripts/make_notices.py's list (the Python packages and their licences), plus what
only the Linux build carries:

- jeepney (D-Bus, for Wayland hotkeys: soundboard/linux/portal.py)
- PortAudio, built for the app (scripts/build_portaudio.sh)
- the system libraries PyInstaller copied from the build machine (libpulse,
  libsndfile, libxcb-*, …): each one's package and its copyright file, found with
  dpkg on the Debian / Ubuntu machine that builds the AppImage

Usage: python scripts/linux_notices.py dist/OnionBoard
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import make_notices  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
LINUX_ROOTS = ["jeepney"]
RULE = "=" * 78


def bundled_libraries(app_dir: Path) -> list[str]:
    """Names of the shared libraries PyInstaller put loose in _internal/ (the ones it
    took from the system; Python packages' own libraries sit in their folders)."""
    internal = app_dir / "_internal"
    return sorted(p.name for p in internal.iterdir()
                  if ".so" in p.name and p.is_file() and not p.is_symlink()
                  and not p.name.startswith(("libpython", "libpyside6", "libshiboken6",
                                             "libportaudio")))   # ours: below


def packages_of(names: list[str]) -> dict[str, list[str]]:
    """Debian package -> the libraries it provided, from dpkg's file lists."""
    owners: dict[str, list[str]] = {}
    for name in names:
        try:
            out = subprocess.run(["dpkg", "-S", f"*/{name}"], capture_output=True, text=True,
                                 timeout=30).stdout
        except (OSError, subprocess.SubprocessError):
            return {}
        # "libpulse0:amd64: /usr/lib/x86_64-linux-gnu/libpulse.so.0"; skip
        # "diversion by … from: …" lines
        line = next((x for x in out.splitlines() if ": /" in x and not
                     x.startswith("diversion")), "")
        pkg = line.split(":", 1)[0].strip()
        owners.setdefault(pkg or "(not from a package)", []).append(name)
    return owners


def system_section(app_dir: Path) -> str:
    owners = packages_of(bundled_libraries(app_dir))
    if not owners:
        return ""
    parts = [f"{RULE}\nSystem libraries in the Linux build\n{RULE}\n",
             "Copied from the Ubuntu machine that built it; each package's copyright "
             "file follows.\n"]
    for pkg, libs in sorted(owners.items()):
        parts.append(f"{RULE}\n{pkg}: {', '.join(libs)}\n{RULE}\n")
        doc = Path("/usr/share/doc") / pkg.split(":")[0] / "copyright"
        parts.append(doc.read_text("utf-8", errors="replace") if doc.is_file()
                     else "(no copyright file found)\n")
    return "\n".join(parts)


def portaudio_section() -> str:
    """PortAudio, built for the app by scripts/build_portaudio.sh."""
    lic = ROOT / "build" / "portaudio" / "LICENSE.txt"
    if not lic.is_file():
        return ""
    return (f"{RULE}\nPortAudio 19.7.0 (libportaudio.so.2, built from "
            f"github.com/PortAudio/portaudio with ALSA only)  --  MIT\n{RULE}\n"
            + lic.read_text("utf-8", errors="replace"))


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    app_dir = Path(argv[0])
    make_notices.ROOTS = make_notices.ROOTS + LINUX_ROOTS
    dest = app_dir / "THIRD-PARTY-NOTICES.txt"
    sys.argv = [sys.argv[0], str(dest)]
    make_notices.main()
    extra = "\n".join(x for x in (portaudio_section(), system_section(app_dir)) if x)
    if extra:
        with open(dest, "a", encoding="utf-8") as f:
            f.write("\n" + extra)
        print(f"added the system libraries ({dest.stat().st_size // 1024} KB)")
    else:
        print("no dpkg here: the system libraries' notices are missing", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

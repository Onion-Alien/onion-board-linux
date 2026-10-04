"""Linux side of soundboard.modules: where an add-on's own environment is, and the
Python it's made from.

- The environment's Python is `.venv/bin/python` (Windows: `.venv\\Scripts\\python.exe`).
- Inside the AppImage the shipped add-ons are read-only (and at a new mount point
  each run), so an add-on whose folder can't be written keeps its environment in
  ~/.local/share/OnionBoard/envs/<add-on>: its code always comes from the running
  version, its installed packages stay put across updates.
- The Python it's made from is a python3 new enough for the pinned packages (the
  distribution's, found on PATH, when the app runs from its AppImage)."""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

__all__ = ["base_python", "env_dir", "venv_python"]

MIN_PYTHON = (3, 11)   # live voice's pinned numpy needs it
CANDIDATES = ("python3.14", "python3.13", "python3.12", "python3.11", "python3", "python")


def env_dir(folder: Path) -> Path:
    """The environment of the add-on in `folder`: its .venv, or in the data folder
    when `folder` can't be written (the AppImage)."""
    if os.access(folder, os.W_OK):
        return folder / ".venv"
    from soundboard import library
    return library.APP_DIR / "envs" / folder.name


def venv_python(folder: Path) -> Path:
    """The Python of the environment an add-on's install made for `folder`."""
    return env_dir(folder) / "bin" / "python"


def _version(exe: str) -> tuple[int, ...]:
    try:
        out = subprocess.run([exe, "-c", "import sys; print(*sys.version_info[:2])"],
                             capture_output=True, text=True, timeout=10).stdout
        return tuple(int(x) for x in out.split())
    except (OSError, ValueError, subprocess.SubprocessError):
        return ()


def base_python() -> str | None:
    """A Python to build a module's own environment from: the one running the app
    from source; for the AppImage, the newest python3 on PATH that's new enough."""
    if not getattr(sys, "frozen", False):
        return sys.executable
    seen = set()
    for name in CANDIDATES:
        found = shutil.which(name)
        if not found or Path(found).resolve() in seen:
            continue
        seen.add(Path(found).resolve())
        if _version(found) >= MIN_PYTHON:
            return found
    return None


def _patch(cls) -> None:
    """ModuleInfo's two places that know where the environment's Python is."""
    def _fill(self, arg: str, base_python: str = "python3") -> str:
        venv_py = venv_python(self.path)
        py = str(venv_py) if venv_py.exists() else "python3"
        return (arg.replace("{dir}/.venv", str(env_dir(self.path)))
                .replace("{base_python}", base_python).replace("{python}", py)
                .replace("{dir}", str(self.path)))

    def installed(self) -> bool:
        if self.kind == "translation":
            from soundboard.speech import translation
            return translation.is_downloaded(self)
        if self.kind != "service" or not any("{python}" in a for a in self.command):
            return True
        return venv_python(self.path).exists()

    cls._fill = _fill
    cls.installed = property(installed, doc=cls.installed.__doc__)


# this module is imported by the last line of soundboard.modules (import that one),
# which has defined ModuleInfo by then
_patch(sys.modules["soundboard.modules"].ModuleInfo)

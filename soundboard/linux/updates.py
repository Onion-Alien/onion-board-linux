"""Linux side of soundboard.updates: the AppImage updates itself.

The release check is the same (the project's latest GitHub release, once a day or on
"Check now"); the file is the release's OnionBoard-x86_64.AppImage, downloaded and
checked against the SHA-256 GitHub lists for it exactly as Windows' installer is.
"Restart to update" then puts it in place of the running AppImage file (one rename
in the same folder: the running copy keeps its already-open file, so nothing breaks
mid-way), and a tiny shell waits for this process to end before starting the new
one, so the single-instance lock doesn't send it back to the old window.

Only a copy started from an AppImage in a folder the user can write to updates
itself; a folder build or a source checkout only says what's new."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

log = logging.getLogger(__name__)

__all__ = ["ASSET", "UPDATE_ASSET", "appimage", "can_install", "cleanup", "installer_env",
           "installer_path", "start_install"]

ASSET = "OnionBoard-x86_64.AppImage"
# *Update now* takes this copy when a release has it (counted apart from downloads
# off the website, as Windows' OnionBoardSetup-update.exe), else ASSET; never the .exe
UPDATE_ASSET = "OnionBoard-x86_64-update.AppImage"
# waits (at most a minute) for the old app's process to be gone, then becomes the new one
WAIT_THEN_RUN = ('i=0; while kill -0 "$1" 2>/dev/null && [ "$i" -lt 600 ]; do sleep 0.1; '
                 'i=$((i+1)); done; exec "$2"')
# the AppImage runtime's own variables: the new one sets them afresh
APPIMAGE_VARS = ("APPDIR", "APPIMAGE", "ARGV0", "OWD")


def _u():
    from soundboard import updates
    return updates


# Windows' version, kept for installer_env() below: this module is imported by the last
# line of soundboard.updates (import that one, never this directly), which has defined
# it by then and replaces it with this module's names right after
_upstream_installer_env = sys.modules["soundboard.updates"].installer_env


def appimage() -> Path | None:
    """The AppImage file this copy was started from, or None."""
    p = os.environ.get("APPIMAGE", "")
    if not p or not getattr(sys, "frozen", False):
        return None
    path = Path(p)
    return path if path.is_file() else None


def can_install() -> bool:
    """Started from an AppImage the user may replace (its folder is writable)."""
    a = appimage()
    return a is not None and os.access(a.parent, os.W_OK | os.X_OK)


def installer_path(rel) -> Path:
    return _u().UPDATES_DIR / f"OnionBoard-{rel.version}-x86_64.AppImage"


def installer_env(env: dict[str, str] | None = None,
                  bundle: str | None = None) -> dict[str, str]:
    """The environment for the new copy: the Windows clean-up (PyInstaller's
    bookkeeping, Qt paths into this bundle), plus the library path PyInstaller's
    loader set for this copy put back as it was, and the AppImage runtime's
    variables dropped."""
    from soundboard.linux import host_env
    env = host_env(_upstream_installer_env(env, bundle), bundle)
    for k in APPIMAGE_VARS:
        env.pop(k, None)
    return env


def start_install(path: Path, pid: int | None = None) -> None:
    """Put the downloaded AppImage in place of this one and start it once process
    `pid` (this one) has ended; the caller then quits. Raises OSError if the file
    couldn't be replaced or the new copy started."""
    target = appimage()
    if target is None:
        raise OSError("this copy wasn't started from an AppImage")
    tmp = target.with_name(f".{target.name}.update")
    try:
        shutil.copyfile(path, tmp)   # the download may be on another file system
        tmp.chmod(0o755)
        os.replace(tmp, target)
    except OSError:
        tmp.unlink(missing_ok=True)
        raise
    subprocess.Popen(["/bin/sh", "-c", WAIT_THEN_RUN, "sh", str(pid or os.getpid()),
                      str(target)],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True,
                     cwd=str(Path.home()), env=installer_env())
    log.info("replaced %s with the update; it starts when this copy has closed", target.name)


def cleanup() -> None:
    """Remove downloaded updates (and half-downloads)."""
    d = _u().UPDATES_DIR
    for p in (*d.glob("OnionBoard-*.AppImage*"), *d.glob("OnionBoardSetup-*")):
        try:
            p.unlink()
        except OSError:
            pass

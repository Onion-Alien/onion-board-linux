"""soundboard/linux/modules.py: an add-on's own environment on Linux (.venv/bin, or
the data folder when the add-on's folder is read-only, as inside the AppImage), and
the python3 it's made from; modules/live-voice/install.sh."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from soundboard import library, modules

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux add-on environments")

ROOT = Path(__file__).resolve().parent.parent


def _service(folder: Path) -> Path:
    folder.mkdir(parents=True)
    (folder / "module.json").write_text(json.dumps({
        "id": "s", "kind": "service", "command": ["{python}", "{dir}/run.py"],
        "install": [["{base_python}", "-m", "venv", "{dir}/.venv"]]}), encoding="utf-8")
    return folder


def _python(env: Path) -> Path:
    py = env / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_bytes(b"")
    return py


def test_the_environment_is_the_folders_own_venv_when_it_can_be_written(tmp_path):
    m = _service(tmp_path / "s")
    (info,) = modules.discover([tmp_path])
    assert info.resolved_command()[0] == "python3" and not info.installed
    py = _python(m / ".venv")
    assert info.resolved_command() == [str(py), f"{m}/run.py"] and info.installed
    assert info._fill("{dir}/.venv", "/usr/bin/python3") == str(m / ".venv")


def test_a_read_only_add_on_keeps_its_environment_in_the_data_folder(tmp_path, monkeypatch):
    """Inside the AppImage the add-on's folder is read-only, and somewhere new each run."""
    m = _service(tmp_path / "mount" / "s")
    real_access = os.access
    monkeypatch.setattr(os, "access", lambda p, mode: False if Path(p) == m
                        else real_access(p, mode))
    (info,) = modules.discover([tmp_path / "mount"])
    env = library.APP_DIR / "envs" / "s"
    assert modules.env_dir(m) == env
    assert info._fill("{dir}/.venv", "/usr/bin/python3") == str(env)   # the venv step
    assert not info.installed
    py = _python(env)
    assert info.installed and info.resolved_command() == [str(py), f"{m}/run.py"]


def test_the_appimage_builds_environments_from_a_new_enough_python3(monkeypatch):
    found = {"python3.12": "/usr/bin/python3.12", "python3": "/usr/bin/python3"}
    versions = {"/usr/bin/python3.12": (3, 12), "/usr/bin/python3": (3, 10)}
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(modules.shutil, "which", found.get)
    import soundboard.linux.modules as lm
    monkeypatch.setattr(lm, "_version", versions.get)
    assert modules.base_python() == "/usr/bin/python3.12"
    found.pop("python3.12")
    assert modules.base_python() is None              # only a 3.10: too old
    monkeypatch.delattr(sys, "frozen")
    assert modules.base_python() == sys.executable   # from source: the app's own


def test_install_sh_makes_the_environment_where_the_app_looks(tmp_path):
    """install.sh with a stand-in python3 that records what it was asked to do."""
    addon = tmp_path / "live-voice"
    addon.mkdir()
    for name in ("install.sh", "requirements.txt"):
        (addon / name).write_bytes((ROOT / "modules" / "live-voice" / name).read_bytes())
    (addon / "install.sh").chmod(0o755)
    calls = tmp_path / "calls.txt"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    # "python3 -m venv DIR" makes DIR/bin/python, a copy of this same stand-in
    fake = fake_bin / "python3"
    fake.write_text(f"""#!/bin/sh
echo "$0 $*" >> "{calls}"
case "$1" in
  -c) exit 0 ;;
  -m) [ "$2" = venv ] && mkdir -p "$3/bin" && cp "$0" "$3/bin/python" ;;
esac
exit 0
""")
    fake.chmod(0o755)
    import shutil
    for tool in ("mkdir", "cp", "dirname", "basename"):   # and no other python on PATH
        (fake_bin / tool).symlink_to(shutil.which(tool))
    env = {"PATH": str(fake_bin), "HOME": str(tmp_path)}
    r = subprocess.run(["/bin/sh", str(addon / "install.sh"), "--quiet"], env=env,
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    lines = calls.read_text().splitlines()
    assert any(" -m venv .venv" in x for x in lines)
    assert any(x.startswith(".venv/bin/python -m pip install") for x in lines)
    assert any(x.startswith(".venv/bin/python helper.py --download base.en") for x in lines)

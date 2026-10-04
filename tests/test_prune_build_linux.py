"""scripts/prune_build_linux.py: what's cut from the Linux PyInstaller output, on a
fake tree with a fake DT_NEEDED table, and its ELF reader on real libraries."""
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32",
                                reason="the Linux build (its tree has symlinks)")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import prune_build_linux as pbl  # noqa: E402

# who needs whom, by file name, standing in for the ELF dynamic section
NEEDED = {
    "QtWidgets.abi3.so": ["libQt6Widgets.so.6", "libQt6Core.so.6", "libpyside6.abi3.so.6.11"],
    "QtWebEngineCore.abi3.so": ["libQt6WebEngineCore.so.6"],
    "QtQuick.abi3.so": ["libQt6Quick.so.6", "libpyside6qml.abi3.so.6.11"],
    "libQt6WebEngineCore.so.6": ["libQt6Quick.so.6", "libQt6Core.so.6"],
    "libQt6Quick.so.6": ["libQt6Qml.so.6"],
    "libQt6Widgets.so.6": ["libQt6Core.so.6"],
    "libQt6Core.so.6": ["libicuuc.so.73", "libc.so.6"],
    "QtWebEngineProcess": ["libQt6WebEngineCore.so.6"],
    "libffmpegmediaplugin.so": ["libavcodec.so.61"],
    "libavcodec.so.61": ["libavutil.so.59"],
    "libqxcb.so": ["libQt6XcbQpa.so.6"],
    "libqtvirtualkeyboardplugin.so": ["libQt6VirtualKeyboard.so.6"],
    "libqpdf.so": ["libQt6Pdf.so.6"],
}


def fake_needed(path: Path) -> list[str]:
    return NEEDED.get(path.name, [])


def make_tree(tmp_path: Path) -> Path:
    app = tmp_path / "OnionBoard"
    pyside = app / "_internal" / "PySide6"
    files = [
        "QtCore.abi3.so", "QtWidgets.abi3.so", "QtWebEngineCore.abi3.so", "QtQuick.abi3.so",
        "QtOpenGL.abi3.so", "QtDBus.abi3.so", "libpyside6.abi3.so.6.11",
        "libpyside6qml.abi3.so.6.11",
        "Qt/lib/libQt6Core.so.6", "Qt/lib/libQt6Widgets.so.6", "Qt/lib/libQt6WebEngineCore.so.6",
        "Qt/lib/libQt6Quick.so.6", "Qt/lib/libQt6Qml.so.6", "Qt/lib/libQt6Charts.so.6",
        "Qt/lib/libQt63DRender.so.6", "Qt/lib/libicuuc.so.73", "Qt/lib/libavcodec.so.61",
        "Qt/lib/libavutil.so.59", "Qt/lib/libswscale.so.8", "Qt/lib/libQt6XcbQpa.so.6",
        "Qt/lib/libQt6VirtualKeyboard.so.6", "Qt/lib/libQt6Pdf.so.6",
        "Qt/libexec/QtWebEngineProcess", "Qt/libexec/qt.conf",
        "Qt/plugins/multimedia/libffmpegmediaplugin.so",
        "Qt/plugins/platforms/libqxcb.so", "Qt/plugins/platforms/libqwayland.so",
        "Qt/plugins/platforms/libqoffscreen.so", "Qt/plugins/platforms/libqeglfs.so",
        "Qt/plugins/platforms/libqvnc.so",
        "Qt/plugins/platforminputcontexts/libcomposeplatforminputcontextplugin.so",
        "Qt/plugins/platforminputcontexts/libqtvirtualkeyboardplugin.so",
        "Qt/plugins/imageformats/libqjpeg.so", "Qt/plugins/imageformats/libqpdf.so",
        "Qt/plugins/qmltooling/libqmldbg_debugger.so", "Qt/plugins/generic/libqevdevmouseplugin.so",
        "Qt/qml/QtQuick/qmldir",
        "Qt/resources/qtwebengine_resources.pak", "Qt/resources/qtwebengine_devtools_resources.pak",
        "Qt/resources/icudtl.dat",
        "Qt/translations/qt_de.qm", "Qt/translations/qtwebengine_locales/en-US.pak",
        "Qt/translations/qtwebengine_locales/de.pak",
    ]
    for f in files:
        p = pyside / f
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    internal = app / "_internal"
    (internal / "shiboken6").mkdir()
    # PyInstaller links the libraries into _internal/
    for name in ("libQt6Core.so.6", "libQt6Charts.so.6"):
        os.symlink(f"PySide6/Qt/lib/{name}", internal / name)
    os.symlink("PySide6/libpyside6qml.abi3.so.6.11", internal / "libpyside6qml.abi3.so.6.11")
    return app


def test_plan_keeps_what_is_reachable_and_drops_the_rest(tmp_path):
    app = make_tree(tmp_path)
    drop, problems = pbl.plan(app, needed_of=fake_needed)
    assert problems == []
    rel = {str(p.relative_to(app / "_internal")) for p in drop}
    names = {p.name for p in drop}
    # cut: unused Python modules, unreachable libraries, QML, dev tools, locales, extras
    assert {"QtQuick.abi3.so", "QtOpenGL.abi3.so", "libQt6Charts.so.6", "libQt63DRender.so.6",
            "libswscale.so.8", "libpyside6qml.abi3.so.6.11", "qml", "qmltooling", "generic",
            "libqeglfs.so", "libqvnc.so", "libqtvirtualkeyboardplugin.so", "libqpdf.so",
            "libQt6VirtualKeyboard.so.6", "libQt6Pdf.so.6",
            "qtwebengine_devtools_resources.pak", "qt_de.qm", "de.pak"} <= names
    # PyInstaller's links to removed files go with them; links to kept ones stay
    assert {"libQt6Charts.so.6", "libpyside6qml.abi3.so.6.11"} <= rel
    assert "libQt6Core.so.6" not in rel
    # kept: what the app imports and what that needs (Quick via WebEngineCore), the
    # desktop's platforms, the WebEngine helper
    for keep in ("QtCore.abi3.so", "QtWidgets.abi3.so", "QtDBus.abi3.so",
                 "libpyside6.abi3.so.6.11", "libQt6Quick.so.6", "libQt6Qml.so.6",
                 "libQt6Core.so.6", "libicuuc.so.73", "libavcodec.so.61", "libavutil.so.59",
                 "libqxcb.so", "libQt6XcbQpa.so.6", "libqwayland.so", "libqoffscreen.so",
                 "libffmpegmediaplugin.so", "libqjpeg.so",
                 "libcomposeplatforminputcontextplugin.so", "qtwebengine_resources.pak",
                 "icudtl.dat", "en-US.pak", "QtWebEngineProcess"):
        assert keep not in names, keep


def test_plan_reports_a_kept_file_that_would_lose_a_library(tmp_path):
    app = make_tree(tmp_path)
    # the X11 plugin suddenly needs the VNC one, a platform that's cut by name
    bad = dict(NEEDED, **{"libqxcb.so": ["libQt6XcbQpa.so.6", "libqvnc.so"]})
    _drop, problems = pbl.plan(app, needed_of=lambda p: bad.get(p.name, []))
    assert problems and "libqvnc.so" in problems[0]


def test_main_dry_run_deletes_nothing(tmp_path, monkeypatch, capsys):
    app = make_tree(tmp_path)
    monkeypatch.setattr(pbl, "elf_needed", fake_needed)
    monkeypatch.setattr(pbl.plan, "__defaults__", (fake_needed,))
    assert pbl.main([str(app), "--dry-run"]) == 0
    assert (app / "_internal" / "PySide6" / "Qt" / "qml").exists()
    assert "would free" in capsys.readouterr().out
    assert pbl.main([str(app)]) == 0
    internal = app / "_internal"
    assert not (internal / "PySide6" / "Qt" / "qml").exists()
    assert not (internal / "libQt6Charts.so.6").is_symlink()
    assert (internal / "PySide6" / "Qt" / "lib" / "libQt6Quick.so.6").exists()
    assert (internal / "libQt6Core.so.6").exists()


def test_elf_needed_reads_a_real_library():
    import ctypes.util
    libm = ctypes.util.find_library("m")
    path = next((Path(d) / libm for d in ("/lib/x86_64-linux-gnu", "/usr/lib/x86_64-linux-gnu",
                                          "/lib64", "/usr/lib64", "/lib", "/usr/lib")
                 if libm and (Path(d) / libm).exists()), None)
    if path is None:
        pytest.skip("no libm found here")
    assert any(n.startswith("libc.so") for n in pbl.elf_needed(path))
    assert pbl.elf_needed(Path(__file__)) == []           # not ELF
    assert pbl.elf_needed(Path("/nonexistent/lib.so")) == []


def test_every_qt_module_the_app_imports_is_kept():
    import re
    used = set()
    for f in (ROOT / "soundboard").rglob("*.py"):
        used |= set(re.findall(r"PySide6\.(Qt\w+)", f.read_text(encoding="utf-8")))
    assert used - pbl.KEEP_MODULES_LINUX == set()


# ---------------------------------------------------------------- our own PortAudio

def _pa_tree(tmp_path, jack_user=False):
    import swap_portaudio  # noqa: F401 - scripts/ is on sys.path above
    internal = tmp_path / "OnionBoard" / "_internal"
    (internal / "_sounddevice").mkdir(parents=True)
    for name, body in (("libportaudio.so.2", b"old"), ("libjack.so.0", b"jack"),
                       ("libdb-5.3.so", b"db"), ("libasound.so.2", b"asound"),
                       ("libother.so.1", b"other")):
        (internal / name).write_bytes(body)
    new = tmp_path / "libportaudio.so.2"
    new.write_bytes(b"new")
    table = {b"old": ["libasound.so.2", "libjack.so.0", "libc.so.6"],
             b"jack": ["libdb-5.3.so"], b"new": ["libasound.so.2", "libm.so.6"],
             b"other": ["libjack.so.0"] if jack_user else ["libasound.so.2"]}

    def needed(p):
        return table.get(p.read_bytes(), []) if p.is_file() else []
    return internal, new, needed


def test_our_portaudio_replaces_the_distributions_and_jack_goes_with_it(tmp_path):
    import swap_portaudio
    internal, new, needed = _pa_tree(tmp_path)
    removed = swap_portaudio.swap(internal.parent, new, needed)
    assert sorted(removed) == ["libdb-5.3.so", "libjack.so.0"]
    assert (internal / "libportaudio.so.2").read_bytes() == b"new"
    assert (internal / "libasound.so.2").exists()          # the new one needs it too


def test_a_library_something_else_still_needs_is_kept(tmp_path):
    import swap_portaudio
    internal, new, needed = _pa_tree(tmp_path, jack_user=True)
    assert swap_portaudio.swap(internal.parent, new, needed) == []
    assert (internal / "libjack.so.0").exists() and (internal / "libdb-5.3.so").exists()


def test_a_portaudio_needing_what_isnt_bundled_stops_the_build(tmp_path):
    import swap_portaudio
    internal, new, needed = _pa_tree(tmp_path)
    (internal / "libasound.so.2").unlink()
    with pytest.raises(SystemExit, match="libasound"):
        swap_portaudio.swap(internal.parent, new, needed)

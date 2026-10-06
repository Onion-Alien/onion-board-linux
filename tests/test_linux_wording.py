"""soundboard/linux/wording.py: the app's Windows wording, reworded on Linux as it
reaches the screen; and every "Windows" string in the source is either reworded or
never shown on Linux."""
import ast
import html
import re
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux wording")

ROOT = Path(__file__).resolve().parent.parent


def test_phrases_are_reworded_anywhere_in_a_text_and_html_escaped():
    from soundboard.linux.wording import linux
    assert linux("Sounds kept in it go to the Windows Recycle Bin.") == \
        "Sounds kept in it go to the Trash."
    shown = html.escape("You hear your sounds on X now: it's Windows' default output.")
    assert "the system&#x27;s default output" in linux(shown)
    assert linux(r"see the log in %APPDATA%\OnionBoard.").endswith("/OnionBoard.")
    assert "%APPDATA%" not in linux(r"see the log in %APPDATA%\OnionBoard.")
    assert linux("Nothing Windows-ish here") == "Nothing Windows-ish here"
    assert linux("In Discord, pick CABLE Output as the mic.") == \
        "In Discord, pick Onion Board Cable Output as the mic."
    assert linux(None) is None and linux(3) == 3


def test_short_texts_are_reworded_only_when_whole():
    from soundboard.linux.wording import linux
    assert linux("Windows default") == "Default voice"
    assert linux("Windows default output") == "Windows default output"


def test_hotkeys_name_the_super_key():
    from soundboard.linux.wording import linux
    from soundboard.settings import pretty_key
    assert linux(pretty_key("ctrl+windows+x")) == "Ctrl+Super+X"
    assert linux(pretty_key("left windows")) == "Left Super"


def test_qt_calls_put_linux_wording_on_screen(qapp):
    from PySide6.QtWidgets import QComboBox, QLabel, QPushButton
    assert QLabel("Gone to the Windows Recycle Bin.").text() == "Gone to the Trash."
    label = QLabel()
    label.setText("Couldn't change Windows startup — x")
    assert label.text() == "Couldn't change starting at sign-in — x"
    b = QPushButton("Windows default")
    b.setToolTip("Restart the speech engine to pick up new Windows voices")
    assert b.text() == "Default voice" and "new voices" in b.toolTip()
    combo = QComboBox()
    combo.addItem("Windows default", "Windows default")   # the item's data stays as it is
    assert (combo.itemText(0), combo.itemData(0)) == ("Default voice", "Windows default")


def test_static_message_boxes_are_reworded():
    """QMessageBox.information(parent, title, text): conftest stubs the real ones in
    every test, so the wrapper is checked on a stand-in."""
    from soundboard.linux import wording
    seen = []

    class Box:
        @staticmethod
        def information(parent, title, text, *rest):
            seen.append((title, text))
            return 1
    wording._wrap_static(Box, "information", (1, 2))
    assert Box.information(None, "Windows default", "Windows denied access (x).") == 1
    Box.information(None, title="t", text="Windows reported a problem.")
    assert seen == [("Default voice", "Access was denied (x)."),
                    ("t", "The system reported a problem.")]


# ---------------------------------------------------------------- the source

WORDS = re.compile(r"\bWindows\b|Task Manager|Recycle Bin|%APPDATA%|taskbar|VB-Cable|vb-audio"
                   r"|CABLE (Input|Output)|Voicemeeter")

# strings that say Windows but never reach the screen on Linux: (file, start) → why
NOT_ON_LINUX = {
    ("soundboard/appaudio.py", ""): "Windows' capture (Linux: soundboard/linux/appaudio.py)",
    ("soundboard/autostart.py", "Software\\Microsoft"): "registry keys",
    ("soundboard/ui/setupwizard.py", "Software\\Microsoft"): "registry keys",
    ("soundboard/applog.py", "Windows:  "): "the log's header (the value says Linux)",
    ("soundboard/ytdl.py", "Mozilla/5.0"): "the web user agent",
    ("soundboard/speech/tts.py", ""): "Windows speech (Linux: eSpeak, soundboard/linux/tts.py)",
    ("soundboard/speech/winvoices.py", ""): "Windows' voice installs",
    ("soundboard/ui/voicepanel.py", ""): "Windows' voice installs (hidden: linux/ui.py)",
    ("soundboard/engine.py", "vb-audio"): "a device-name hint for spotting cables",
    ("soundboard/net.py", " Install VB-Cable yourself"):
        "the cable download's switch, hidden on Linux (linux/ui.py): nothing downloads",
    ("soundboard/settings.py", "The setup guide's Install button downloads VB-Cable"):
        "the cable download switch's hint, hidden on Linux (linux/ui.py)",
    # the setup guide's VB-Cable installer: its steps and outcomes (Linux makes its
    # cable: linux/ui.py's install_cable); the rest of the guide does show
    ("soundboard/ui/setupwizard.py", "Click <b>Yes</b> when Windows asks"): "installer step",
    ("soundboard/ui/setupwizard.py", "'>The cable installer is missing"): "installer outcome",
    ("soundboard/ui/setupwizard.py", ").</span> Restart your PC and try again"):
        "installer outcome",
    ("soundboard/ui/setupwizard.py", "'>✓ Installed.</b> Windows needs"): "installer outcome",
    ("soundboard/ui/setupwizard.py", "'>That didn't work.</b> If Windows asked"):
        "installer outcome",
    ("soundboard/ui/setupwizard.py", "'>It still isn't showing up after the restart"):
        "installer outcome (no restart on Linux)",
    ("soundboard/ui/mainwindow.py", "A window opened that downloads VB-Cable"):
        "the VB-Cable installer (linux/ui.py)",
    ("soundboard/ui/mainwindow.py", "Some games just use Windows' main mic"):
        "the mic control panel (Linux sets the default mic: linux/ui.py)",
    # "Straight into my mic" (1.9.0): Windows' mic effect (linux/directmic.py is the
    # Linux one); its failures that can't happen here, and its update
    ("soundboard/directmic.py", ""): "the mic effect (linux/directmic.py answers instead)",
    ("soundboard/ui/mainwindow.py", "'>✗ Windows isn't running Onion Board"):
        "the effect not running on the mic (no effect: installed_on() is [])",
    ("soundboard/ui/mainwindow.py", "Another app may have your mic to itself"):
        "the effect not running on the mic (no effect)",
    ("soundboard/ui/mainwindow.py", " A newer version of the mic part is ready"):
        "the effect's update (never 'outdated' here)",
    ("soundboard/ui/mainwindow.py", "  →  Set as Default Device"):
        "the mic control panel (Linux sets the default mic: linux/ui.py)",
}


def _shown_strings():
    """(file, line, text) of every string constant in the app that isn't a docstring
    or a log message, with Linux wording applied."""
    from soundboard.linux.wording import linux
    for f in sorted((ROOT / "soundboard").rglob("*.py")):
        if "linux" in f.parts:
            continue
        rel = f.relative_to(ROOT).as_posix()
        tree = ast.parse(f.read_text(encoding="utf-8"))
        skip = set()
        for n in ast.walk(tree):
            body = getattr(n, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) and \
                    isinstance(body[0].value, ast.Constant):
                skip.add(id(body[0].value))
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and \
                    n.func.attr in ("debug", "info", "warning", "error", "exception"):
                skip.update(id(a) for a in ast.walk(n))
        for n in ast.walk(tree):
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in skip:
                yield rel, n.lineno, linux(n.value)


def test_every_windows_string_is_reworded_or_never_shown_on_linux():
    left = []
    for rel, line, text in _shown_strings():
        if not WORDS.search(text):
            continue
        if any(rel == f and text.startswith(start) for f, start in NOT_ON_LINUX):
            continue
        left.append(f"{rel}:{line}: {text[:90]!r}")
    assert left == [], ("say these the Linux way in soundboard/linux/wording.py, or list "
                        "them in NOT_ON_LINUX with the reason they never show:\n"
                        + "\n".join(left))


# ---------------------------------------------------------------- the Voice tab

def test_a_missing_voice_points_at_espeak_not_windows_update(qapp, monkeypatch):
    from test_voicepanel import FakeEngine, _chinese_without_a_voice

    import soundboard.ui.mainwindow  # noqa: F401 - its Linux hook patches the Voice tab
    from soundboard.ui.voicepanel import VoicePanel
    p = VoicePanel(FakeEngine(), {"enabled": False, "effects": {}}, {"voice": "", "rate": 0})
    try:
        s = p.speech
        _chinese_without_a_voice(s, qapp)
        assert s.b_voice_install.isHidden() and s.b_voices.isHidden()
        assert not s.b_voices_check.isHidden()            # Reload voices stays
        assert "espeak-ng" in s.lbl_tr.text() and "Windows" not in s.lbl_tr.text()
    finally:
        p.shutdown()
        p.deleteLater()


# ---------------------------------------------------------------- custom voices

def test_piper_from_its_linux_download_is_found(tmp_path, monkeypatch):
    from soundboard.speech import customvoices
    monkeypatch.setattr(customvoices.shutil, "which", lambda name: None)
    assert customvoices._piper_exe(tmp_path) == ""
    exe = tmp_path / "piper" / "piper"   # piper_linux_x86_64.tar.gz unpacks to piper/piper
    exe.parent.mkdir()
    exe.write_bytes(b"\x7fELF")
    exe.chmod(0o644)                      # lost its exec bit on the way: given back
    assert customvoices._piper_exe(tmp_path) == str(exe)
    assert exe.stat().st_mode & 0o100


def test_voices_folder_readme_is_in_linux_terms():
    from soundboard.speech import customvoices
    assert "piper.exe" not in customvoices.README and "C:/" not in customvoices.README
    assert "piper_linux_x86_64" in customvoices.README


# built at run time, not literals: settings.pretty_key title-cases "windows" key names
_BUILT = {"Windows+", "Windows", "Left Windows", "Right Windows"}


def test_every_rewording_still_matches_upstreams_text():
    """An upstream merge that rewords a text leaves its entry here matching nothing,
    and the Windows wording back on screen: each entry must still be in the source."""
    from soundboard.linux import wording
    consts = []
    for f in ROOT.joinpath("soundboard").rglob("*.py"):
        if "linux" in f.relative_to(ROOT).parts:
            continue
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Constant) and isinstance(n.value, str):
                consts.append(n.value)
            elif isinstance(n, ast.JoinedStr):   # an f-string: its fixed parts
                consts.append("".join(v.value if isinstance(v, ast.Constant) else "\0"
                                      for v in n.values))
    text = "\n".join(consts)
    stale = [old for old, _ in wording.PHRASES if old not in text and old not in _BUILT]
    stale += [w for w in wording.WHOLE if w not in consts and w not in _BUILT]
    assert not stale, f"reworded upstream, update soundboard/linux/wording.py: {stale}"

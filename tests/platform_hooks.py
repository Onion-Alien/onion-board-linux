"""Platform hooks, star-imported at the end of conftest.py:

- tests that check Windows itself (its memory layouts, drive-letter paths, its
  case-insensitive environment) are skipped off Windows, each with its reason; what
  those modules do on Linux is tested in tests/test_linux_*.py
- upstream's tests see upstream's text: soundboard/linux/wording.py is off for
  them (tests/test_linux_wording.py checks it)
- the Linux versions of conftest's "never touch the real thing" guards: real MIDI
  devices, the real autostart folder, the real sound server (a stand-in with
  speakers, a mic and the cable answers instead), and the desktop's own display"""
import os
import sys

import pytest

__all__ = ["pytest_collection_modifyitems", "_linux_never_touches_the_real_desktop", "REAL"]

REAL: dict = {}   # what the guards replace, for the tests of those very functions
if sys.platform != "win32":
    # Run from a desktop, every test that made the app grabbed its hotkeys on the
    # desktop's own X server (or asked its portal, on Wayland), and the hotkey
    # threads they left behind kept signalling objects later tests had deleted
    # (segfaults in Qt's event loop). A test that needs an X server starts
    # its own Xvfb (tests/xvfb.py) and sets DISPLAY itself.
    for _var in ("DISPLAY", "WAYLAND_DISPLAY"):
        os.environ.pop(_var, None)
    from soundboard.linux.tts import EspeakTTS
    REAL["tts_warm_up"] = EspeakTTS.warm_up   # conftest stubs it outside test_speech.py
    from soundboard import updates as _updates
    REAL["start_install"] = _updates.start_install   # conftest's guard replaces it

WINDOWS_ONLY = {
    "tests/test_settings.py::test_onion_watch_can_be_removed_from_settings":
        "the Onion Watch card: no Triggers tab on Linux yet (tests/test_linux_ui.py)",
    "tests/test_appaudio.py::test_guid_bytes_keep_zero_bytes":
        "Windows COM GUID layout (appaudio is replaced on Linux)",
    "tests/test_appaudio.py::test_struct_sizes_match_the_windows_layouts":
        "Windows struct sizes (a C long is 8 bytes on Linux)",
    "tests/test_appaudio.py::test_supported_reports_windows_and_build":
        "Windows' build number (Linux: tests/test_linux_appaudio.py)",
    "tests/test_appaudio.py::test_root_pid_walks_up_same_exe_only":
        "the Windows process snapshot (Linux walks /proc: tests/test_linux_appaudio.py)",
    "tests/test_chatguide.py::test_with_rate_rewrites_rate_and_byte_rate":
        "WAVEFORMATEX in VB-Cable's registry format (no VB-Cable on Linux)",
    "tests/test_library.py::test_config_round_trip":
        "D:\\ drive paths are only absolute on Windows",
    "tests/test_net.py::test_every_mode_points_ffmpeg_at_the_relay_as_the_radio":
        "expects HTTP_PROXY and http_proxy to be one variable (Windows' environment)",
    "tests/test_shellicon.py::test_is_ours_matches_only_this_copy":
        "Windows paths compare without case (shell icons are Windows-only)",
    "tests/test_audit_audio.py::test_co_init_owns_s_false_but_not_changed_mode":
        "Windows COM initialisation (appaudio is replaced on Linux)",
    "tests/test_audit_main.py::test_refresh_keeps_task_managers_off":
        "the registry Run key and Task Manager's startup switch (Linux: "
        "tests/test_linux_platform.py)",
    "tests/test_trim_updates_autostart.py::test_autostart_adds_updates_and_removes_the_run_value":
        "the registry Run key (Linux: tests/test_linux_platform.py)",
    "tests/test_trim_updates_autostart.py::test_autostart_follows_task_managers_switch":
        "Task Manager's startup switch (Linux: tests/test_linux_platform.py)",
    "tests/test_trim_updates_autostart.py::test_installer_starts_without_the_frozen_apps_variables":
        "the Windows installer's PATH (; separated, C:\\ paths)",
    "tests/test_tor.py::test_job_object_kills_its_process_when_closed":
        "Windows job objects (Linux: __OwningControllerProcess)",
    "tests/test_tor.py::test_tor_dies_when_the_app_crashes":
        "Windows job objects (Linux: __OwningControllerProcess)",
    "tests/test_tor.py::test_torrc_bridges_come_from_pt_config":
        "the transport's path with \\ (Linux: tests/test_linux_platform.py)",
    "tests/test_winkeys.py::test_hotkey_thread_survives_a_failing_message_and_reports_its_end":
        "the Win32 message loop (Linux: tests/test_linux_keys.py)",
    "tests/test_winkeys.py::test_key_input_record_flags":
        "SendInput's INPUT records (Linux: XTest)",
    "tests/test_winkeys.py::test_register_reports_combos_another_thread_owns":
        "RegisterHotKey (Linux: tests/test_linux_keys.py)",
    "tests/test_torget.py::test_get_unpacks_only_the_kept_files_where_tor_looks":
        "the Windows bundle's tor.exe (Linux: tests/test_linux_platform.py)",
    "tests/test_torget.py::test_a_tarball_missing_a_kept_file_leaves_nothing_behind":
        "the Windows bundle's lyrebird.exe",
    "tests/test_torget.py::test_an_update_replaces_an_older_copy":
        "the Windows bundle's tor.exe",
    "tests/test_speech.py::test_windows_speech_that_stops_answering_is_restarted":
        "the PowerShell speech process (Linux: eSpeak, tests/test_linux_platform.py)",
    "tests/test_speech.py::test_windows_speech_output_that_isnt_utf8_cant_kill_the_reader":
        "the PowerShell speech process's output pipe",
    # the VB-Cable installer; Linux makes its own virtual cable (soundboard/linux/vcable.py)
    "tests/test_setupwizard.py::test_restart_marker_counts_only_until_the_pc_restarts":
        "VB-Cable's restart marker",
    "tests/test_setupwizard.py::test_install_shows_bun_building_and_each_step":
        "the VB-Cable installer",
    "tests/test_setupwizard.py::test_install_that_still_needs_a_restart_stops_bun":
        "the VB-Cable installer",
    "tests/test_setupwizard.py::test_mid_install_the_guide_stays_put_and_a_reopened_one_picks_it_up":
        "the VB-Cable installer",
    "tests/test_setupwizard.py::test_installer_that_cant_start_says_what_to_do":
        "the VB-Cable installer",
    "tests/test_setupwizard.py::test_installer_needing_a_restart_offers_restart_not_reinstall":
        "the VB-Cable installer's restart (Linux: tests/test_linux_ui.py)",
    "tests/test_setupwizard.py::test_resume_after_restart_writes_and_removes_the_runonce_entry":
        "the RunOnce registry entry",
    "tests/test_setupwizard.py::test_resumed_guide_with_the_cable_still_missing_offers_to_install_again":
        "reopening after VB-Cable's restart",
    "tests/test_net_switches.py::test_setup_downloads_off_never_starts_the_cable_installer":
        "VB-Cable's download (Linux makes the cable with none: tests/test_linux_ui.py)",
    # Windows' voice installs (Windows Update); Linux says to install eSpeak's package
    "tests/test_voicepanel.py::test_downloaded_language_needs_a_windows_voice_and_uses_it":
        "Windows' voice install (Linux: tests/test_linux_wording.py)",
    "tests/test_voicepanel.py::test_voice_installed_in_windows_settings_is_found_on_return":
        "Windows' speech settings",
    "tests/test_voicepanel.py::test_one_click_voice_install_then_its_picked_up":
        "Windows' voice install",
    "tests/test_voicepanel.py::test_voice_install_cancelled_or_failed_says_so":
        "Windows' voice install",
    "tests/test_customvoices.py::test_folder_gets_a_readme_and_load_reads_every_kind":
        "piper.exe in the voices folder (Linux: tests/test_linux_wording.py)",
    # the release's Windows installer; Linux takes its AppImage (tests/test_linux_updates.py)
    "tests/test_trim_updates_autostart.py::test_latest_finds_the_installer_and_its_checksum":
        "OnionBoardSetup.exe (Linux: tests/test_linux_updates.py)",
    "tests/test_trim_updates_autostart.py::test_an_installer_under_the_old_repo_name_is_still_trusted":
        "OnionBoardSetup.exe under the old repo name",
    "tests/test_trim_updates_autostart.py::test_latest_takes_the_checksum_from_the_notes_without_a_digest":
        "OnionBoardSetup.exe (Linux: tests/test_linux_updates.py)",
    "tests/test_speech.py::test_service_command_uses_the_modules_own_python":
        ".venv\\Scripts\\python.exe (Linux: tests/test_linux_modules.py)",
    "tests/test_voicesdk.py::test_is_system_never_touches_the_disk":
        "C:\\Windows paths (the voice engine watcher is off on Linux)",
}


def _alive(pid: int) -> bool:
    """tests/test_tor.py's Windows _alive(), for Linux: running and not a zombie."""
    import os
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    try:
        with open(f"/proc/{pid}/stat", encoding="ascii", errors="replace") as f:
            return f.read().rsplit(")", 1)[1].split()[0] != "Z"
    except OSError:
        return False


STAND_IN_SINKS = """Sink #1
\tName: test_speakers
\tDescription: Speakers
\tSample Specification: float32le 2ch 48000Hz
Sink #4
\tName: onionboard_cable
\tDescription: Onion Board Cable Input
\tSample Specification: float32le 2ch 48000Hz
"""
STAND_IN_SOURCES = """Source #2
\tName: test_speakers.monitor
\tDescription: Monitor of Speakers
\tSample Specification: float32le 2ch 48000Hz
\tMonitor of Sink: test_speakers
Source #3
\tName: test_mic
\tDescription: Microphone
\tSample Specification: float32le 1ch 48000Hz
\tMonitor of Sink: n/a
Source #5
\tName: onionboard_cable_out
\tDescription: Onion Board Cable Output
\tSample Specification: float32le 2ch 48000Hz
\tMonitor of Sink: n/a
"""
STAND_IN_INFO = "Default Sink: test_speakers\nDefault Source: test_mic\n"


@pytest.fixture(autouse=True)
def _linux_never_touches_the_real_desktop(request, monkeypatch, tmp_path):
    if sys.platform == "win32":
        yield
        return
    # upstream's tests check upstream's text; the Linux wording has its own tests
    if not request.node.module.__name__.rsplit(".", 1)[-1].startswith("test_linux_"):
        from soundboard.linux import wording
        monkeypatch.setattr(wording, "active", False)
    # XDG autostart, the PipeWire / PulseAudio drop-ins and the Trash live under these
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "guard" / "xdg-config"))
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "guard" / "xdg-data"))
    from soundboard import midi
    from soundboard.linux import vcable

    class NoMidi:
        slow = False

        def __init__(self):
            self.on_message = lambda key, msg: None
            self.on_closed = lambda key: None

        def devices(self):
            return []

        def open(self, index, key):
            raise OSError("no MIDI in tests")

        def close(self, handle):
            pass
    REAL.setdefault("midi_backend", midi._linux_backend)
    REAL.setdefault("pactl", vcable._pactl)
    monkeypatch.setattr(midi, "_linux_backend", NoMidi)
    # the real sound server (its cable, its device list): tests that want one use a
    # stand-in pactl, so results don't depend on the machine's devices
    from soundboard.linux import audio
    REAL.setdefault("audio_pactl", audio._pactl)
    monkeypatch.setattr(vcable, "_pactl", lambda *a: None)
    # a set-up machine's sound server: speakers, a mic and the Onion Board cable;
    # streams on them reach conftest's silent stream, PortAudio's index 0
    answers = {("list", "sinks"): STAND_IN_SINKS, ("list", "sources"): STAND_IN_SOURCES,
               ("info",): STAND_IN_INFO}
    monkeypatch.setattr(audio, "_pactl", lambda *a: answers.get(a, ""))
    monkeypatch.setattr(audio, "_pcm_index", lambda: 0)
    monkeypatch.setattr(audio, "_devices", None)
    yield


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        return
    patched = set()
    for item in items:
        reason = WINDOWS_ONLY.get(item.nodeid) or WINDOWS_ONLY.get(item.nodeid.split("[")[0])
        if reason:
            item.add_marker(pytest.mark.skip(reason=f"Windows only: {reason}"))
        mod = getattr(item, "module", None)
        if mod is not None and mod.__name__.endswith("test_tor") and mod not in patched:
            mod._alive = _alive   # the Windows helper uses OpenProcess
            patched.add(mod)

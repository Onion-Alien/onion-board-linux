"""Tests that check Windows itself (its memory layouts, drive-letter paths, its
case-insensitive environment), skipped off Windows. Each has its reason; what
these modules do on Linux is tested in tests/test_linux_*.py. Hooked in from the
end of conftest.py."""
import sys

import pytest

WINDOWS_ONLY = {
    "tests/test_appaudio.py::test_guid_bytes_keep_zero_bytes":
        "Windows COM GUID layout (appaudio is replaced on Linux)",
    "tests/test_appaudio.py::test_struct_sizes_match_the_windows_layouts":
        "Windows struct sizes (a C long is 8 bytes on Linux)",
    "tests/test_chatguide.py::test_with_rate_rewrites_rate_and_byte_rate":
        "WAVEFORMATEX in VB-Cable's registry format (no VB-Cable on Linux)",
    "tests/test_library.py::test_config_round_trip":
        "D:\\ drive paths are only absolute on Windows",
    "tests/test_net.py::test_every_mode_points_ffmpeg_at_the_relay_as_the_radio":
        "expects HTTP_PROXY and http_proxy to be one variable (Windows' environment)",
    "tests/test_shellicon.py::test_is_ours_matches_only_this_copy":
        "Windows paths compare without case (shell icons are Windows-only)",
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

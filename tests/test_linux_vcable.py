"""The Linux virtual cable (soundboard.linux.vcable) against a stand-in pactl: a
small script on PATH that keeps the sound server's sinks, sources and modules in a
JSON file, so no real sound server is touched."""
import json
import os
import stat
import sys
import textwrap

import pytest

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="Linux only")

FAKE = textwrap.dedent(r'''
    #!{python}
    import json, sys
    path = {state!r}
    st = json.load(open(path))
    a = sys.argv[1:]
    def save():
        json.dump(st, open(path, "w"))
    if a == ["info"]:
        print("Server String: x\nServer Name: " + st["server"])
    elif a[:2] == ["list", "short"]:
        kind = a[2]
        if kind == "modules":
            for m in st["modules"]:
                print(f"{{m['id']}}\t{{m['name']}}\t{{m['args']}}\t")
        else:
            for i, n in enumerate(st[kind]):
                print(f"{{i}}\t{{n}}\tPipeWire\ts16le 2ch 48000Hz\tSUSPENDED")
    elif a[0] == "load-module":
        args = " ".join(a[2:])
        st["calls"].append(a)
        if st.get("refuse"):
            print("Failure: Module initialization failed", file=sys.stderr); sys.exit(1)
        kv = dict(x.split("=", 1) for x in a[2:] if "=" in x)
        if a[1] == "module-null-sink":
            st["sinks"].append(kv["sink_name"]); st["sources"].append(kv["sink_name"] + ".monitor")
        elif a[1] == "module-remap-source":
            st["sources"].append(kv["source_name"])
        st["next"] += 1
        st["modules"].append({{"id": str(st["next"]), "name": a[1], "args": args}})
        save(); print(st["next"])
    elif a[0] == "unload-module":
        m = next(m for m in st["modules"] if m["id"] == a[1])
        st["modules"].remove(m)
        kv = dict(x.split("=", 1) for x in m["args"].split() if "=" in x)
        if m["name"] == "module-null-sink":
            st["sinks"].remove(kv["sink_name"]); st["sources"].remove(kv["sink_name"] + ".monitor")
        else:
            st["sources"].remove(kv["source_name"])
        save()
    else:
        sys.exit(2)
''')


@pytest.fixture
def pactl(tmp_path, monkeypatch):
    from platform_hooks import REAL
    from soundboard.linux import vcable
    monkeypatch.setattr(vcable, "_pactl", REAL["pactl"])   # conftest's guard stubs it

    def make(server="PulseAudio (on PipeWire 1.0.5)"):
        state = tmp_path / "state.json"
        state.write_text(json.dumps({"server": server, "sinks": ["speakers"],
                                     "sources": ["speakers.monitor", "mic"],
                                     "modules": [], "next": 10, "calls": []}))
        bindir = tmp_path / "bin"
        bindir.mkdir(exist_ok=True)
        exe = bindir / "pactl"
        exe.write_text(FAKE.format(python=sys.executable, state=str(state)).lstrip())
        exe.chmod(exe.stat().st_mode | stat.S_IXUSR)
        monkeypatch.setenv("PATH", f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}")
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
        return lambda: json.loads(state.read_text())
    return make


def test_no_sound_server(monkeypatch, tmp_path):
    from platform_hooks import REAL
    from soundboard.linux import vcable
    monkeypatch.setattr(vcable, "_pactl", REAL["pactl"])
    monkeypatch.setenv("PATH", str(tmp_path))   # no pactl at all
    assert vcable.server() == "" and not vcable.exists() and not vcable.create()


def test_create_makes_both_ends_once(pactl):
    from soundboard.linux import vcable
    state = pactl()
    assert vcable.server() == "pipewire" and not vcable.exists()
    assert vcable.create() and vcable.exists()
    st = state()
    assert vcable.SINK in st["sinks"] and vcable.SOURCE in st["sources"]
    assert any(f'device.description="{vcable.SINK_DESC}"' in " ".join(c) for c in st["calls"])
    n = len(st["calls"])
    assert vcable.create() and len(state()["calls"]) == n   # already there: nothing loaded


def test_the_names_are_what_the_app_calls_a_cable():
    from soundboard import engine
    from soundboard.linux import vcable
    assert engine.is_virtual(vcable.SINK_DESC) and engine.is_virtual(vcable.SOURCE_DESC)
    assert vcable.SINK_DESC.replace("Input", "Output") == vcable.SOURCE_DESC


def test_a_refusing_server_is_reported(pactl):
    from soundboard.linux import vcable
    state = pactl()
    st = state()
    st["refuse"] = True
    (__import__("pathlib").Path(os.environ["XDG_CONFIG_HOME"]).parent / "state.json").write_text(
        json.dumps(st))
    assert not vcable.create() and not vcable.exists()


def test_install_on_pipewire_writes_the_dropin_and_remove_undoes_it(pactl):
    from soundboard.linux import vcable
    state = pactl()
    assert vcable.install() and vcable.installed() and vcable.exists()
    conf = vcable.pipewire_conf().read_text()
    assert "libpipewire-module-loopback" in conf and vcable.SOURCE_DESC in conf
    assert conf.count("{") == conf.count("}") and conf.count("[") == conf.count("]")
    assert vcable.remove()
    assert not vcable.installed() and not vcable.exists() and state()["modules"] == []


def test_install_on_pulseaudio_keeps_the_system_setup(pactl):
    from soundboard.linux import vcable
    pactl(server="pulseaudio")
    assert vcable.install() and vcable.installed()
    text = vcable.pulse_default_pa().read_text()
    assert text.startswith(".include /etc/pulse/default.pa")
    assert text.count(vcable.PA_MARK) == 1
    vcable.install()
    assert vcable.pulse_default_pa().read_text().count(vcable.PA_MARK) == 1   # not twice
    assert vcable.remove() and not vcable.installed()
    assert not vcable.pulse_default_pa().exists()   # it made the file: it goes again
    # a default.pa of the user's own keeps everything of theirs
    own = ".include /etc/pulse/default.pa\nload-module module-echo-cancel\n"
    vcable.pulse_default_pa().write_text(own)
    assert vcable.install() and vcable.remove()
    assert vcable.pulse_default_pa().read_text() == own

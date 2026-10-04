"""Linux: check the virtual cable end to end on this PC's own sound server.

Makes the Onion Board cable (for this session only, unless it's already installed),
plays a quiet 660 Hz beep through the real engine into "Onion Board Cable Input" and
records "Onion Board Cable Output" (what Discord would hear) with parec. Nothing goes
to your speakers. Prints PASS or FAIL.

    python scripts/linux_audio_check.py            # keeps the cable afterwards
    python scripts/linux_audio_check.py --remove   # takes a cable it made away again
"""
import subprocess
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from soundboard.linux import audio, vcable  # noqa: E402

SR = 48000


def main() -> int:
    if not vcable.server():
        print("FAIL: no PipeWire / PulseAudio reachable with pactl")
        return 1
    had = vcable.exists()
    if not vcable.create():
        print("FAIL: couldn't make the cable (see the log lines above)")
        return 1
    audio.refresh()
    from soundboard import engine
    eng = engine.Engine()
    eng.set_main_device(vcable.SINK_DESC)
    if eng.errors:
        print(f"FAIL: the engine couldn't open the cable: {eng.errors}")
        return 1
    rec = subprocess.Popen(["parec", f"--device={vcable.SOURCE}", "--format=float32le",
                            "--channels=1", f"--rate={SR}", "--raw", "--latency-msec=20"],
                           stdout=subprocess.PIPE, bufsize=0)
    chunks: list[bytes] = []

    def read():   # as it comes: parec drops what it buffered when it's stopped
        while b := rec.stdout.read(4096):
            chunks.append(b)
    threading.Thread(target=read, daemon=True).start()
    time.sleep(0.4)
    beep = (0.1 * np.sin(2 * np.pi * 660 * np.arange(SR * 2) / SR)).astype(np.float32)
    beep = np.repeat(beep[:, None], 2, axis=1)
    eng.prepare("check", beep)
    eng.play("check", beep, 1.0, only="main")
    time.sleep(1.6)
    rec.terminate()
    rec.wait(2)
    eng.shutdown()
    data = b"".join(chunks)
    x = np.frombuffer(data[: len(data) // 4 * 4], np.float32)
    if "--remove" in sys.argv and not had:
        vcable.remove()
    if len(x) < SR // 2:
        print(f"FAIL: recorded only {len(x)} samples from {vcable.SOURCE_DESC}")
        return 1
    x = x[SR // 4:]
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    peak = float(np.fft.rfftfreq(len(x), 1 / SR)[spec.argmax()])
    ok = abs(peak - 660) < 10 and float(np.sqrt(np.mean(x ** 2))) > 0.01
    print(f"{'PASS' if ok else 'FAIL'}: {vcable.SOURCE_DESC} carried {peak:.0f} Hz "
          f"(sent 660 Hz)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

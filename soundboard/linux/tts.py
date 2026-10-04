"""Linux side of soundboard.speech.tts: the built-in voices are eSpeak NG's (every
distro packages it: `espeak-ng`). Same interface as the Windows SapiTTS (voices,
voice_langs, voice_for, warm_up, refresh, synth, close), so customvoices.VoiceSet
(Piper packs, voice servers, voice programs) builds on it unchanged.

eSpeak has a voice for 100+ languages; the list keeps the ones the app has
translations for, English's accents and the desktop's own language, so the voice
picker stays short. Any eSpeak voice still works when named in config.
"""
from __future__ import annotations

import locale
import logging
import os
import re
import shutil
import subprocess
import threading

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["SapiTTS", "EspeakTTS"]

PREFIX = "eSpeak "
WANTED = ("en", "de", "es", "fr", "ru", "cmn", "zh")   # the translation add-ons' languages
TIMEOUT_S = 30.0
BASE_WPM = 170


def _exe() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


def _desktop_lang() -> str:
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = os.environ.get(var, "")
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            return v.split(".")[0].replace("_", "-").lower()
    try:
        code = locale.getlocale()[0] or ""
    except ValueError:
        code = ""
    code = code.replace("_", "-").lower()
    return "" if code in ("c", "posix") else code


def parse_voice_list(text: str) -> list[tuple[str, str]]:
    """`espeak-ng --voices` into [(language code, voice name)]."""
    out = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 4 and re.fullmatch(r"\d+", parts[0]):
            out.append((parts[1], parts[3].replace("_", " ")))
    return out


def _bcp47(code: str) -> str:
    """eSpeak's code as the app's language tags: 'en-us' -> 'en-US', 'cmn' -> 'zh'."""
    if code.startswith("cmn"):
        return "zh-CN"
    head, _, tail = code.partition("-")
    return f"{head}-{tail.upper()}" if tail and len(tail) == 2 else head


class EspeakTTS:
    def __init__(self):
        self._lock = threading.Lock()
        self.voices: list[str] = []
        self.voice_langs: dict[str, str] = {}
        self._codes: dict[str, str] = {}      # display name -> eSpeak voice code
        self.error = ""
        self._loaded = False

    # -- voices
    def _load(self):
        exe = _exe()
        if exe is None:
            raise RuntimeError("no speech engine: install espeak-ng from your distribution")
        p = subprocess.run([exe, "--voices"], capture_output=True, text=True,
                           timeout=TIMEOUT_S, errors="replace")
        if p.returncode != 0:
            raise RuntimeError(f"espeak-ng --voices failed: {p.stderr.strip()[:200]}")
        mine = _desktop_lang()
        voices, langs, codes = [], {}, {}
        for code, name in parse_voice_list(p.stdout):
            base = code.split("-")[0]
            if base not in WANTED and code != mine and base != mine.split("-")[0]:
                continue
            label = PREFIX + name
            if label in langs:
                continue
            voices.append(label)
            langs[label] = _bcp47(code)
            codes[label] = code
        # the desktop's own voice first, then American and British English, then the
        # rest as listed
        first = mine.split("-")[0]
        top = ("en-us", "en-gb")

        def rank(v: str):
            code = codes[v]
            return (code != mine, code.split("-")[0] != first,
                    top.index(code) if code in top else len(top),
                    not code.startswith("en"))
        voices.sort(key=rank)
        self.voices, self.voice_langs, self._codes = voices, langs, codes
        self._loaded = True
        log.info("eSpeak ready: %d voices", len(voices))

    def voice_for(self, lang: str, prefer: str = "") -> str:
        def speaks(name: str) -> bool:
            return self.voice_langs.get(name, "").lower().split("-")[0] == lang.lower()
        if prefer and speaks(prefer):
            return prefer
        return next((v for v in self.voices if speaks(v)), "")

    def warm_up(self) -> list[str]:
        with self._lock:
            if not self._loaded:
                try:
                    self._load()
                    self.error = ""
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as e:
                    from soundboard import errors
                    self.error = errors.plain(e)
                    log.warning("text-to-speech unavailable: %s", e)
            return self.voices

    def refresh(self) -> list[str]:
        with self._lock:
            self._loaded = False
        return self.warm_up()

    def _code(self, voice: str) -> str:
        if voice in self._codes:
            return self._codes[voice]
        if voice.startswith(PREFIX):   # saved on another PC: find it by name
            name = voice[len(PREFIX):]
            for label, code in self._codes.items():
                if label[len(PREFIX):] == name:
                    return code
        mine = _desktop_lang()
        return mine if mine else "en-us"

    def synth(self, text: str, voice: str = "", rate: int = 0) -> tuple[np.ndarray, int]:
        """Speak `text` into memory: (float32 mono samples, sample rate)."""
        import io

        import soundfile as sf
        text = " ".join(text.split())
        if not text:
            from soundboard.speech.tts import TTS_RATE
            return np.zeros(0, np.float32), TTS_RATE
        self.warm_up()
        exe = _exe()
        if exe is None:
            raise RuntimeError(self.error or "no speech engine: install espeak-ng")
        wpm = int(BASE_WPM * 1.08 ** max(-10, min(10, int(rate))))
        # the text goes on stdin: never parsed as an option, whatever it starts with
        p = subprocess.run([exe, "-v", self._code(voice), "-s", str(wpm), "--stdout",
                            "--stdin"], input=text.encode("utf-8"), capture_output=True,
                           timeout=TIMEOUT_S)
        if p.returncode != 0 or not p.stdout:
            raise RuntimeError(f"eSpeak failed: {p.stderr.decode(errors='replace')[:200]}")
        data, sr = sf.read(io.BytesIO(p.stdout), dtype="float32", always_2d=False)
        if data.ndim > 1:
            data = data.mean(axis=1)
        return np.ascontiguousarray(data, np.float32), int(sr)

    def close(self):
        pass


SapiTTS = EspeakTTS

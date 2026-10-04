# Linux audio: choosing devices (findings)

The engine opens up to four streams in one process, each on a device the user picked
by name: mic in, cable out, headphones out, the optional OBS out.

## What PortAudio offers

PortAudio as the `sounddevice` wheel loads it (the system's `libportaudio2`, ALSA host
API) lists only `pipewire`, `pulse` and `default` on a PipeWire or PulseAudio desktop,
never the devices behind them. So the device lists can't come from PortAudio.

## What works (tested on a headless PipeWire 1.x with pipewire-pulse)

**PortAudio's `pulse` device, aimed per stream.** The pulse ALSA plugin reads
`PULSE_SINK` (`PULSE_SOURCE` for capture) when a stream opens, so setting it just
before each `OutputStream` / `InputStream` sends each stream to its own device:
two tones opened this way in one process landed on two different sinks and nothing
on a third (FFT-checked). It needs nothing beyond what every desktop has (PulseAudio,
or PipeWire with pipewire-pulse, plus the ALSA pulse plugin), latency ~9 ms at
"low". The app name in volume mixers comes from `PULSE_PROP_OVERRIDE` (the plugin's
own name beats plain `PULSE_PROP`).

The device lists come from `pactl list sinks / sources` (descriptions, rates,
channels; monitors left out) and the defaults from `pactl info`.

End to end with the real engine: a sound plus a mic's voice played into "Onion Board
Cable Input" came out of "Onion Board Cable Output" together, and the headphones
got the sound only.

## Also seen

- The `pipewire` ALSA device with `PIPEWIRE_NODE` routed correctly too; the pulse
  route was kept because it also covers plain PulseAudio.
- Module arguments to the sound server are split at spaces unless the whole value
  is quoted: `sink_properties='device.description="Onion Board Cable Input"'`,
  else the device is called "Onion".

## Not tried yet

- A PortAudio built with its PulseAudio host API (would list devices itself; would
  mean bundling our own libportaudio).
- Per-program capture for the Apps tab (`pw-record --target <node>` is the plan).

"""Linux side of soundboard.net. Windows' environment ignores case, so setting
http_proxy there also sets HTTP_PROXY; on Linux they are two variables, and a
user's own HTTPS_PROXY or NO_PROXY left beside the relay's lowercase ones could
send a child program around the relay. Both spellings are set (and both saved for
own_env), and neither no_proxy is: FFmpeg would connect straight to what it lists,
so a radio station redirecting to 127.0.0.1 would step around the relay (upstream
took no_proxy out in 1.6.8; on Linux NO_PROXY has to go too)."""
from __future__ import annotations

import os

__all__ = ["_set_env"]


def _set_env():
    from soundboard import net
    if net._env_saved is None:
        keys = list(net.ENV_KEYS) + [k.upper() for k in net.ENV_KEYS]
        net._env_saved = {k: os.environ.get(k) for k in keys}
    url = net.relay_url("radio")
    for k in ("http_proxy", "https_proxy", "all_proxy"):
        os.environ[k] = url
        os.environ[k.upper()] = url
    os.environ.pop("no_proxy", None)
    os.environ.pop("NO_PROXY", None)

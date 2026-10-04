"""Linux side of soundboard.net. Windows' environment ignores case, so setting
http_proxy there also sets HTTP_PROXY; on Linux they are two variables, and a
user's own HTTPS_PROXY or NO_PROXY left beside the relay's lowercase ones could
send a child program around the relay. Both spellings are set (and both saved for
own_env)."""
from __future__ import annotations

import os

__all__ = ["_set_env"]


def _set_env():
    from soundboard import net
    if net._env_saved is None:
        keys = list(net.ENV_KEYS) + [k.upper() for k in net.ENV_KEYS]
        net._env_saved = {k: os.environ.get(k) for k in keys}
    url = net.relay_url("radio")
    values = {"http_proxy": url, "https_proxy": url, "all_proxy": url,
              "no_proxy": "localhost,127.0.0.1,::1"}
    for k, v in values.items():
        os.environ[k] = v
        os.environ[k.upper()] = v

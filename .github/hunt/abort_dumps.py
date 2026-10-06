"""pytest plugin for win-crash-hunt (faulthandler: on): the fault handler stays on (it
may be part of the abort), but SIGABRT is ignored after it is set up. abort() then
goes on to fail fast, and Windows saves a crash dump with every thread's native stack;
with the fault handler's own SIGABRT handler the process exits inside it, no dump."""
import signal

import pytest


@pytest.hookimpl(trylast=True)
def pytest_configure(config):
    signal.signal(signal.SIGABRT, signal.SIG_IGN)

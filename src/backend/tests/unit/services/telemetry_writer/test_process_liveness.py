"""Process probes must recognize dead workers without signaling live workers."""

import subprocess
import sys

import pytest
from langflow.services.telemetry_writer.service import _pid_alive


@pytest.mark.parametrize("pid", [-1, 0])
def test_pid_alive_rejects_nonpositive_pids(pid: int) -> None:
    assert _pid_alive(pid) is False


def test_pid_alive_recognizes_exited_process() -> None:
    with subprocess.Popen([sys.executable, "-c", "pass"]) as process:  # noqa: S603
        process.wait(timeout=10)
        assert _pid_alive(process.pid) is False


def test_pid_alive_leaves_running_process_responsive() -> None:
    # Only probe a disposable child: os.kill(pid, 0) terminates Windows
    # processes instead of performing the harmless existence check on POSIX.
    with subprocess.Popen(  # noqa: S603
        [sys.executable, "-c", "import sys; print(sys.stdin.readline().strip(), flush=True)"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    ) as process:
        try:
            assert _pid_alive(process.pid) is True
            stdout, _ = process.communicate("still-alive\n", timeout=10)
            assert process.returncode == 0
            assert stdout.strip() == "still-alive"
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)

"""Terminal engine: a real interactive shell in a PTY whose output is tapped for errors.
The shell itself is untouched - the tap only reads a copy of the output stream."""
from __future__ import annotations

import os
import subprocess
import sys
from typing import Callable, List, Optional


def run_command(
    cmd: List[str],
    feed: Callable[[str], None],
    cwd: Optional[str] = None,
    result_feed: Optional[Callable[[str, int, List[str]], None]] = None,
) -> int:
    """`aiterm run -- <cmd>`: run a command, stream its output, and analyse it afterwards."""
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    buf = []
    assert p.stdout is not None
    for line in p.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        buf.append(line)
    rc = p.wait()
    output = "".join(buf)
    feed(output)
    if result_feed:
        result_feed(output, rc, cmd)
    return rc


def run_shell(feed: Callable[[str], None], shell: Optional[str] = None) -> int:
    import fcntl
    import pty
    import select
    import signal
    import struct
    import termios
    import tty

    shell = shell or os.environ.get("SHELL", "/bin/bash")
    pid, fd = pty.fork()
    if pid == 0:
        os.environ["AITERM_ACTIVE"] = "1"
        os.execvp(shell, [shell])

    def sync_size(*_):
        try:
            sz = fcntl.ioctl(sys.stdin.fileno(), termios.TIOCGWINSZ, struct.pack("HHHH", 0, 0, 0, 0))
            fcntl.ioctl(fd, termios.TIOCSWINSZ, sz)
        except OSError:
            pass

    old_handler = signal.signal(signal.SIGWINCH, sync_size)
    sync_size()
    stdin_fd = sys.stdin.fileno()
    saved = termios.tcgetattr(stdin_fd)
    status = 0
    try:
        tty.setraw(stdin_fd)
        while True:
            try:
                r, _, _ = select.select([stdin_fd, fd], [], [])
            except InterruptedError:
                continue
            if stdin_fd in r:
                data = os.read(stdin_fd, 4096)
                if not data:
                    break
                os.write(fd, data)
            if fd in r:
                try:
                    data = os.read(fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                os.write(sys.stdout.fileno(), data)
                try:
                    feed(data.decode("utf-8", errors="replace"))
                except Exception:
                    pass
    finally:
        termios.tcsetattr(stdin_fd, termios.TCSADRAIN, saved)
        signal.signal(signal.SIGWINCH, old_handler)
        try:
            _, status = os.waitpid(pid, 0)
        except ChildProcessError:
            pass
    return os.waitstatus_to_exitcode(status) if status else 0

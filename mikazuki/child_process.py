"""Linux child launcher that terminates when its creating parent disappears."""

from __future__ import annotations

import ctypes
import os
import signal
import sys


def main() -> None:
    parent_pid = int(sys.argv[1])
    command = sys.argv[2:]
    if not command:
        raise SystemExit("missing child command")

    signal.pthread_sigmask(signal.SIG_UNBLOCK, {signal.SIGTERM})
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGTERM) != 0:  # PR_SET_PDEATHSIG
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error))

    # The parent can disappear between Popen() and prctl().
    if os.getppid() != parent_pid:
        os.kill(os.getpid(), signal.SIGTERM)

    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    main()

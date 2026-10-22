"""Shared host precondition; not a sandbox or proof of complete containment."""
import os
from pathlib import Path


def become_subreaper() -> bool:
    try:
        import ctypes
        if int(Path('/proc/self/stat').read_text().split(' ', 1)[0]) != os.getpid():
            return False
        return ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) == 0
    except (OSError, AttributeError, ValueError):
        return False


if __name__ == '__main__':
    # The adapter probes in a separate process so its own process-wide child
    # adoption behavior is not changed. The dispatcher rechecks on actual use.
    raise SystemExit(0 if become_subreaper() else 1)

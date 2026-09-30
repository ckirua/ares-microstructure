"""Line-oriented logging for ``tail -f`` (stdout + file)."""

from __future__ import annotations

import logging
import sys
import time
from pathlib import Path


class FlushFileHandler(logging.FileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def setup_logging(log_path: Path, *, quiet: bool = False) -> logging.Logger:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        except Exception:
            pass

    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("tick_shadow")
    for h in list(root.handlers):
        root.removeHandler(h)
        try:
            h.close()
        except Exception:
            pass

    root.setLevel(logging.INFO)
    root.propagate = False
    fmt = logging.Formatter(
        fmt="%(asctime)sZ %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    fmt.converter = time.gmtime  # type: ignore[attr-defined]

    fh = FlushFileHandler(log_path)
    fh.setFormatter(fmt)
    root.addHandler(fh)
    if not quiet:
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        root.addHandler(sh)
    return root

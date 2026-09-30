"""Line-oriented logging for ``tail -f`` (stdout + file, flush each record)."""

from __future__ import annotations

import logging
import sys
import time
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path

LOG = logging.getLogger("paper_live")
_SETUP_KEY = "_paper_live_logging"


class FlushFileHandler(logging.FileHandler):
    """FileHandler that flushes after every emit (tail -f friendly)."""

    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


class FlushRotatingFileHandler(RotatingFileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


class FlushTimedRotatingFileHandler(TimedRotatingFileHandler):
    def emit(self, record: logging.LogRecord) -> None:
        super().emit(record)
        self.flush()


def _line_buffer_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(line_buffering=True)  # type: ignore[attr-defined]
        except Exception:
            pass


def setup_logging(
    log_path: Path,
    *,
    rotate: str = "daily",
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 14,
    quiet: bool = False,
    force: bool = False,
) -> logging.Logger:
    """Configure root ``paper_live`` logger → file (+ stdout unless quiet).

    File handlers flush each record so ``tail -f logs/paper_live.log`` shows
    events live even under fully-buffered redirects.
    """
    _line_buffer_stdio()
    log_path = Path(log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger("paper_live")
    already = getattr(root, _SETUP_KEY, None)
    if already == str(log_path) and root.handlers and not force:
        return root
    if force or (already and already != str(log_path)):
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

    rotate_l = str(rotate or "daily").lower()
    if rotate_l == "daily":
        fh: logging.Handler = FlushTimedRotatingFileHandler(
            log_path,
            when="midnight",
            interval=1,
            backupCount=int(backup_count),
            encoding="utf-8",
            utc=True,
        )
    elif rotate_l == "size":
        fh = FlushRotatingFileHandler(
            log_path,
            maxBytes=int(max_bytes),
            backupCount=int(backup_count),
            encoding="utf-8",
        )
    else:
        fh = FlushFileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.INFO)
    fh.setFormatter(fmt)
    root.addHandler(fh)

    if not quiet:
        sh = logging.StreamHandler(sys.stdout)
        sh.setLevel(logging.INFO)
        sh.setFormatter(fmt)
        root.addHandler(sh)

    setattr(root, _SETUP_KEY, str(log_path))
    root.info("logging → %s (rotate=%s) live_orders=False", log_path, rotate_l)
    return root

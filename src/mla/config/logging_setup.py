from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def configure_logging(log_dir: Path, level: int = logging.INFO) -> Path:
    """Rotating file log (5 x 1 MB) plus stderr. Returns the log file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "mla.log"
    root = logging.getLogger()
    root.setLevel(level)
    for handler in list(root.handlers):
        if getattr(handler, "_mla", False):
            root.removeHandler(handler)
            handler.close()
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    file_handler.setFormatter(logging.Formatter(FORMAT, "%Y-%m-%d %H:%M:%S"))
    file_handler._mla = True  # type: ignore[attr-defined]
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(FORMAT, "%H:%M:%S"))
    stream_handler.setLevel(logging.WARNING)
    stream_handler._mla = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)
    root.addHandler(stream_handler)
    return log_file

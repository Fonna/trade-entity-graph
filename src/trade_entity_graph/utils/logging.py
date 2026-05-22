"""Logging setup helpers."""

from __future__ import annotations

import logging


def configure_logging(level: int = logging.INFO) -> None:
    """Configure simple console logging for local MVP runs."""

    logging.basicConfig(level=level, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

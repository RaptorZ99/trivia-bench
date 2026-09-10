"""Configuration des journaux (loguru)."""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

_CONSOLE_FORMAT = (
    "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | <level>{message}</level>"
)


def setup_logging(name: str, *, level: str = "INFO", log_dir: Path | None = None) -> None:
    """Configure la sortie console et, si demande, un fichier de journal par commande."""
    logger.remove()
    logger.add(sys.stderr, level=level, format=_CONSOLE_FORMAT, colorize=True)
    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        logger.add(
            log_dir / f"{name}_{{time:YYYYMMDD-HHmmss}}.log",
            level="DEBUG",
            rotation="10 MB",
            retention="14 days",
            encoding="utf-8",
        )


__all__ = ["logger", "setup_logging"]

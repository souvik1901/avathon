"""
Structured, human-readable logging for the allocation engine.

Uvicorn only prints one access line per request (``POST /allocate/compare 200``).
That tells you *that* a request happened, not *what* the engine did. This module
gives the engine its own named logger (``rae``) with a compact formatter, so every
solve prints the scenario shape, the cost-matrix feasibility, each strategy's
result, and the optimality gap — the story behind the request.

The logger uses its own handler and does not propagate, so it renders
independently of (and alongside) uvicorn's access log.
"""
from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def _configure() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logger = logging.getLogger("rae")
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(
        fmt="%(asctime)s | %(levelname)-5s | rae | %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(handler)
    logger.propagate = False   # render alongside uvicorn, not through it
    _CONFIGURED = True


def get_logger() -> logging.Logger:
    _configure()
    return logging.getLogger("rae")

"""Structured logging configuration."""

import logging

import structlog

from slate.config import Settings


def configure_logging(settings: Settings | None = None) -> None:
    """Configure structlog for the application."""
    settings = settings or Settings()
    renderer = (
        structlog.dev.ConsoleRenderer()
        if settings.log_format == "console"
        else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping()[settings.log_level.upper()]
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

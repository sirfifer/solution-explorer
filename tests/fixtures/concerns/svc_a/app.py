"""Service A: structured logging via structlog."""
import structlog

log = structlog.get_logger()


def handle(event):
    log.info("handling", event=event)
    return event

"""Service B: logging via loguru."""
from loguru import logger


def handle(event):
    logger.info("handling {}", event)
    return event

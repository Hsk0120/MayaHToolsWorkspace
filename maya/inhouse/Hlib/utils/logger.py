"""Standard logging integration for Hlib and Maya's user feedback surfaces."""

import html
import logging


LOGGER_NAME = "Hlib"
_VIEWPORT_COLORS = {
    logging.WARNING: "#ffcc00",
    logging.ERROR: "#ff4d4d",
    logging.CRITICAL: "#ff4d4d",
}


def _message_from(record):
    """Return the fully formatted text without exposing exception objects to Maya."""
    return record.getMessage()


class MayaHandler(logging.Handler):
    """Route Hlib log records to Maya's Script Editor and viewport."""

    def emit(self, record):
        message = _message_from(record)
        try:
            import maya.api.OpenMaya as om2
        except ImportError:
            return

        try:
            if record.levelno >= logging.ERROR:
                om2.MGlobal.displayError(message)
            elif record.levelno >= logging.WARNING:
                om2.MGlobal.displayWarning(message)
            else:
                om2.MGlobal.displayInfo(message)
        except RuntimeError:
            pass

        if record.levelno < logging.WARNING:
            return

        try:
            import maya.cmds as cmds
            color = _VIEWPORT_COLORS.get(record.levelno, "#ff4d4d")
            cmds.inViewMessage(
                amg=f'<font color="{color}">{html.escape(message)}</font>',
                pos="midCenter",
                fade=True,
            )
        except (ImportError, RuntimeError):
            pass


def get_logger():
    """Return the shared Hlib logger, installing the Maya handler once."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    if not any(isinstance(handler, MayaHandler) for handler in logger.handlers):
        logger.addHandler(MayaHandler())
    return logger


def debug(message, *args, **kwargs):
    """Write a diagnostic record without showing a viewport notification."""
    get_logger().debug(message, *args, **kwargs)


def warning(message, *args, **kwargs):
    """Write a warning record and show a fading viewport notification."""
    get_logger().warning(message, *args, **kwargs)


def error(message, *args, **kwargs):
    """Write an error record and show a red fading viewport notification."""
    get_logger().error(message, *args, **kwargs)


def raise_with_notify(exception_type, message, *args, **kwargs):
    """Log an error, then raise the requested exception with the same message."""
    error(message)
    raise exception_type(message, *args, **kwargs)


__all__ = [
    "MayaHandler",
    "debug",
    "error",
    "get_logger",
    "raise_with_notify",
    "warning",
]
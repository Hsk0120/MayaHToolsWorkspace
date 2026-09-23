"""hlib.utils.logger のロギングヘルパーを検証するMaya内テスト。"""

import logging
import sys
import unittest

import hlib
hlib.reload()
from hlib.utils.logger import LOGGER_NAME, MayaHandler, debug, error, get_logger, raise_with_notify, warning


class LoggerTest(unittest.TestCase):
    """get_logger/debug/warning/error/raise_with_notify/MayaHandler を検証する。"""

    def test_get_logger_is_idempotent_and_configured(self):
        logger = get_logger()
        self.assertEqual(logger.name, LOGGER_NAME)
        self.assertEqual(logger.level, logging.DEBUG)
        self.assertFalse(logger.propagate)
        handlers = [h for h in logger.handlers if isinstance(h, MayaHandler)]
        self.assertEqual(len(handlers), 1)

        get_logger()
        handlers_after = [h for h in logging.getLogger(LOGGER_NAME).handlers if isinstance(h, MayaHandler)]
        self.assertEqual(len(handlers_after), 1, "get_logger() should not add a duplicate MayaHandler")

    def test_debug_warning_error_emit_expected_log_records(self):
        with self.assertLogs(LOGGER_NAME, level="DEBUG") as captured:
            debug("hlib debug message")
            warning("hlib warning message")
            error("hlib error message")

        messages = [record.getMessage() for record in captured.records]
        self.assertIn("hlib debug message", messages)
        self.assertIn("hlib warning message", messages)
        self.assertIn("hlib error message", messages)
        levels = [record.levelname for record in captured.records]
        self.assertEqual(levels, ["DEBUG", "WARNING", "ERROR"])

    def test_debug_warning_error_support_format_args(self):
        with self.assertLogs(LOGGER_NAME, level="DEBUG") as captured:
            debug("value=%s", 42)
        self.assertEqual(captured.records[0].getMessage(), "value=42")

    def test_maya_handler_emit_does_not_raise_for_each_level(self):
        handler = MayaHandler()
        logger = logging.getLogger("hlibHandlerTest")
        for level, message in (
            (logging.DEBUG, "hlib handler debug"),
            (logging.WARNING, "hlib handler warning"),
            (logging.ERROR, "hlib handler error"),
        ):
            record = logger.makeRecord("hlibHandlerTest", level, __file__, 0, message, None, None)
            handler.emit(record)  # Maya へ表示するだけで例外を送出しないことを確認する

    def test_raise_with_notify_raises_specified_exception(self):
        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            with self.assertRaises(ValueError) as context:
                raise_with_notify(ValueError, "boom")
        self.assertEqual(str(context.exception), "boom")

    def test_raise_with_notify_passes_extra_constructor_args(self):
        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            with self.assertRaises(OSError) as context:
                raise_with_notify(OSError, "boom", 2)
        self.assertEqual(context.exception.args, ("boom", 2))

    def test_raise_with_notify_chains_from_exception(self):
        original = RuntimeError("original")
        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            with self.assertRaises(ValueError) as context:
                raise_with_notify(ValueError, "boom", from_exception=original)
        self.assertIs(context.exception.__cause__, original)

    def test_raise_with_notify_suppresses_chain_when_from_exception_is_none(self):
        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            with self.assertRaises(ValueError) as context:
                raise_with_notify(ValueError, "boom", from_exception=None)
        self.assertIsNone(context.exception.__cause__)
        self.assertTrue(context.exception.__suppress_context__)

    def test_raise_with_notify_preserves_implicit_chain_when_omitted(self):
        with self.assertLogs(LOGGER_NAME, level="ERROR"):
            try:
                try:
                    raise KeyError("inner")
                except KeyError as inner:
                    raise_with_notify(ValueError, "boom")
            except ValueError as outer:
                self.assertIsInstance(outer.__context__, KeyError)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

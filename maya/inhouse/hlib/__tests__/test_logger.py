"""hlib.utils.logger のロギングヘルパーを検証するMaya内テスト。"""

import logging
import io
import contextlib
from pathlib import Path
import sys
import unittest

import hlib
hlib.reload()
from hlib.utils.logger import LOGGER_NAME, MayaHandler, debug, error, get_logger, raise_with_notify, warning
from hlib.utils import logger as output


class LoggerTest(unittest.TestCase):
    """get_logger/debug/warning/error/raise_with_notify/MayaHandler を検証する。"""

    def test_info_supports_logging_format(self):
        with self.assertLogs(LOGGER_NAME, level="INFO") as captured:
            output.info("count=%s", 3)
        self.assertEqual(captured.records[0].levelno, logging.INFO)
        self.assertEqual(captured.records[0].getMessage(), "count=3")

    def test_print_preserves_stream_separator_and_end(self):
        stream = io.StringIO()
        self.assertIsNone(output.print("腕", 3, sep=":", end="!", file=stream, flush=True))
        self.assertEqual(stream.getvalue(), "腕:3!")
        with contextlib.redirect_stdout(stream):
            output.print("next")
        self.assertEqual(stream.getvalue(), "腕:3!next\n")
        with self.assertRaises(TypeError):
            output.print("invalid", sep=1, file=stream)

    def test_old_warning_command_is_removed(self):
        self.assertFalse((Path(hlib.__file__).parent / "cmds" / "warning.py").exists())
        self.assertFalse(hasattr(hlib.cmds, "warning"))
        self.assertFalse(hasattr(hlib, "warning"))
        self.assertIs(hlib.utils.warning, output.warning)

    def test_old_handler_is_replaced_without_removing_external_handlers(self):
        logger = get_logger()
        old_type = type("MayaHandler", (logging.Handler,), {"__module__": output.__name__})
        old_handler = old_type()
        external = logging.NullHandler()
        logger.addHandler(old_handler)
        logger.addHandler(external)
        try:
            get_logger()
            self.assertNotIn(old_handler, logger.handlers)
            self.assertIn(external, logger.handlers)
            self.assertEqual(sum(isinstance(h, output.MayaHandler) for h in logger.handlers), 1)
        finally:
            logger.removeHandler(external)
            external.close()
            logger.removeHandler(old_handler)

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

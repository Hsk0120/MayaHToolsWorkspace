"""5.0.0で変えたエラー表示の約束を固定する。

対象: Script Editor の書式関数(``maya.utils.formatGuiException``)が mlib 内部のフレームを省き、
利用者が mlib を呼んだ行を示すこと、``MLIB_FULL_TRACEBACK`` で省略しないこと、例外の
トレースバック自体は変えないこと、再読み込みで包みを重ねないこと。
"""

import os
import sys
import traceback
import unittest

import maya.utils

import mlib
mlib.reload()
from mlib import logger


def _raise_from_mlib():
    """mlib の中で例外を送出させ、(型, 例外, トレースバック, 呼出し行) を返す。"""
    try:
        line = sys._getframe().f_lineno + 1
        mlib.getNode("mlibSpecErrorDisplay_missing_node")
    except RuntimeError:
        kind, error, trace = sys.exc_info()
        return kind, error, trace, line
    raise AssertionError("getNode did not raise")


class FormatterTest(unittest.TestCase):
    """Script Editor の表示。"""

    def setUp(self):
        self.saved = os.environ.pop(logger.FULL_TRACEBACK_ENV, None)

    def tearDown(self):
        os.environ.pop(logger.FULL_TRACEBACK_ENV, None)
        if self.saved is not None:
            os.environ[logger.FULL_TRACEBACK_ENV] = self.saved

    def test_last_frame_is_the_callers_line(self):
        kind, error, trace, line = _raise_from_mlib()
        self.assertTrue(any(logger._internal_file(frame.filename) for frame in traceback.extract_tb(trace)))
        trimmed = traceback.extract_tb(logger._trimmed_traceback(trace))
        self.assertEqual(os.path.basename(trimmed[-1].filename), os.path.basename(__file__))
        self.assertEqual(trimmed[-1].lineno, line)
        self.assertFalse(any(logger._internal_file(frame.filename) for frame in trimmed))
        # 例外のトレースバック自体は変更しない。
        self.assertTrue(any(logger._internal_file(frame.filename) for frame in traceback.extract_tb(trace)))
        text = maya.utils.formatGuiException(kind, error, trace, 1)
        self.assertIn("RuntimeError: file", text)
        self.assertIn("{} line {}".format(os.path.basename(__file__), line), text)
        self.assertIn("Node not found", text)
        full = maya.utils.formatGuiException(kind, error, trace, 2)
        self.assertNotIn("getNode.py", full)

    def test_environment_variable_keeps_internal_frames(self):
        os.environ[logger.FULL_TRACEBACK_ENV] = "1"
        kind, error, trace, _line = _raise_from_mlib()
        text = maya.utils.formatGuiException(kind, error, trace, 1)
        self.assertNotIn(os.path.basename(__file__), text)
        full = maya.utils.formatGuiException(kind, error, trace, 2)
        self.assertIn("getNode.py", full)

    def test_user_code_errors_are_unchanged(self):
        try:
            {}["missing"]
        except KeyError:
            kind, error, trace = sys.exc_info()
        self.assertIs(logger._trimmed_traceback(trace), trace)
        self.assertIsNone(logger._trimmed_traceback(None))

    def test_reload_does_not_stack_wrappers(self):
        original = maya.utils.formatGuiException._mlib_previous
        mlib.reload()
        from mlib import logger as reloaded
        self.assertIs(maya.utils.formatGuiException._mlib_previous, original)
        self.assertTrue(reloaded._install_exception_formatter())
        self.assertIs(maya.utils.formatGuiException._mlib_previous, original)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

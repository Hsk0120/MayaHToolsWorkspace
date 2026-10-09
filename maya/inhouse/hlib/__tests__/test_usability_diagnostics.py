"""通知の詳細とスキン保護の失敗診断をMaya内で検証する。"""

import logging
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import hlib
hlib.reload()
from hlib import logger
from hlib.decorator import preservedSkinShape
from hlib.nodes import joint as joint_module


class DetailedNotificationTest(unittest.TestCase):
    """詳細はScript Editor、本文はViewportへ表示する。"""

    def test_formatter_and_exception_are_only_in_script_editor(self):
        try:
            raise ValueError("exception detail")
        except ValueError:
            record = logging.LogRecord("hlib", logging.ERROR, __file__, 0,
                                       "operation %s <failed>", ("A",), sys.exc_info())
        handler = logger.MayaHandler()
        handler.setFormatter(logging.Formatter("CUSTOM %(levelname)s %(message)s"))
        display = mock.Mock()
        with mock.patch.object(om2, "MGlobal", SimpleNamespace(displayError=display)), \
                mock.patch.object(cmds, "inViewMessage") as viewport:
            handler.emit(record)
        details = display.call_args[0][0]
        self.assertIn("CUSTOM ERROR operation A <failed>", details)
        self.assertIn("Traceback", details)
        self.assertIn("ValueError: exception detail", details)
        summary = viewport.call_args[1]["amg"]
        self.assertIn("operation A &lt;failed&gt;", summary)
        self.assertNotIn("exception detail", summary)
        self.assertNotIn("CUSTOM", summary)

    def test_stack_info_and_info_level_do_not_create_viewport_notification(self):
        record = logging.LogRecord("hlib", logging.INFO, __file__, 0,
                                   "value=%s", (3,), None, sinfo="stack detail")
        display = mock.Mock()
        with mock.patch.object(om2, "MGlobal", SimpleNamespace(displayInfo=display)), \
                mock.patch.object(cmds, "inViewMessage") as viewport:
            logger.MayaHandler().emit(record)
        self.assertEqual(display.call_args[0][0], "value=3\nstack detail")
        viewport.assert_not_called()

    def test_missing_formatter_field_falls_back_to_exception_details(self):
        try:
            raise ValueError("original detail")
        except ValueError:
            record = logging.LogRecord("hlib", logging.WARNING, __file__, 0,
                                       "operation failed", (), sys.exc_info())
        handler = logger.MayaHandler()
        handler.setFormatter(logging.Formatter("%(tool)s %(message)s"))
        display = mock.Mock()
        with mock.patch.object(om2, "MGlobal", SimpleNamespace(displayWarning=display)), \
                mock.patch.object(cmds, "inViewMessage") as viewport:
            handler.emit(record)
        details = display.call_args[0][0]
        self.assertIn("operation failed", details)
        self.assertIn("ValueError: original detail", details)
        self.assertIn("ログ書式の適用に失敗", details)
        self.assertNotIn("original detail", viewport.call_args[1]["amg"])


class SkinProtectionDiagnosticsTest(unittest.TestCase):
    """失敗した段階を通知し、従来の継続・復元・例外を維持する。"""

    def _exercise(self, stage, body_error=None):
        """指定段階だけ失敗させ、命令順と警告を収集する。

        Args:
            stage (str): query/switch/recache/restoreのいずれか。
            body_error (Exception | None): with本体で送出する例外。
        Returns:
            tuple: skins・命令呼出・警告・本体通過の記録。
        """
        skins = [SimpleNamespace(getFullName=lambda: "skinA"),
                 SimpleNamespace(getFullName=lambda: "skinB")]
        collection = SimpleNamespace(getSkinClusters=lambda: skins)
        entered = []
        calls = []

        def command(name, **kwargs):
            """照会・更新の段階を識別して障害を注入する。"""
            if kwargs.get("query"):
                actual = "query"
            elif kwargs.get("recacheBindMatrices"):
                actual = "recache"
            elif kwargs.get("moveJointsMode") is True:
                actual = "switch"
            else:
                actual = "restore"
            calls.append((name, actual))
            if name == "skinA" and actual == stage:
                raise RuntimeError("injected failure")
            return False if actual == "query" else None

        with mock.patch.object(joint_module, "Joints", return_value=collection), \
                mock.patch.object(cmds, "skinCluster", side_effect=command), \
                mock.patch.object(logger, "warning") as warning:
            if body_error is None:
                with preservedSkinShape(["joint"]) as result:
                    self.assertIs(result, skins)
                    entered.append(True)
            else:
                with self.assertRaises(type(body_error)) as raised:
                    with preservedSkinShape(["joint"]):
                        entered.append(True)
                        raise body_error
                self.assertIs(raised.exception, body_error)
            messages = [call[0][0] for call in warning.call_args_list]
        return skins, calls, messages, entered

    def test_query_failure_is_reported_without_stopping_other_skin(self):
        _, calls, messages, entered = self._exercise("query")
        self.assertEqual(entered, [True])
        self.assertNotIn(("skinA", "switch"), calls)
        self.assertIn(("skinB", "switch"), calls)
        self.assertIn(("skinA", "recache"), calls)
        self.assertNotIn(("skinA", "restore"), calls)
        self.assertEqual(len(messages), 1)
        self.assertIn("モード照会", messages[0])

    def test_switch_failure_still_restores_known_previous_mode(self):
        _, calls, messages, _ = self._exercise("switch")
        self.assertIn(("skinA", "restore"), calls)
        self.assertIn(("skinB", "restore"), calls)
        self.assertEqual(len(messages), 1)
        self.assertIn("モード切替", messages[0])

    def test_recache_failure_does_not_skip_mode_restore(self):
        _, calls, messages, _ = self._exercise("recache")
        self.assertIn(("skinA", "restore"), calls)
        self.assertIn(("skinB", "recache"), calls)
        self.assertIn("再キャッシュ", messages[0])

    def test_restore_failure_keeps_original_body_exception_and_other_cleanup(self):
        _, calls, messages, entered = self._exercise("restore", ValueError("body"))
        self.assertEqual(entered, [True])
        self.assertIn(("skinB", "restore"), calls)
        self.assertEqual(len(messages), 1)
        self.assertIn("モード復元", messages[0])

    def test_bad_formatter_does_not_interrupt_cleanup_or_replace_body_exception(self):
        skins = [SimpleNamespace(getFullName=lambda: "skinA"),
                 SimpleNamespace(getFullName=lambda: "skinB")]
        collection = SimpleNamespace(getSkinClusters=lambda: skins)
        handler = next(item for item in logger.get_logger().handlers
                       if isinstance(item, logger.MayaHandler))
        formatter = handler.formatter
        handler.setFormatter(logging.Formatter("%(tool)s %(message)s"))
        restores = []

        def command(name, **kwargs):
            """片方の復元だけ失敗し、残りの復元が実行されるか記録する。"""
            if kwargs.get("query"):
                return False
            if kwargs.get("moveJointsMode") is False:
                restores.append(name)
                if name == "skinA":
                    raise RuntimeError("restore failure")

        original = ValueError("original body")
        try:
            with mock.patch.object(joint_module, "Joints", return_value=collection), \
                    mock.patch.object(cmds, "skinCluster", side_effect=command), \
                    mock.patch.object(om2, "MGlobal", SimpleNamespace(displayWarning=mock.Mock())), \
                    mock.patch.object(cmds, "inViewMessage"):
                with self.assertRaises(ValueError) as raised:
                    with preservedSkinShape(["joint"]):
                        raise original
            self.assertIs(raised.exception, original)
            self.assertEqual(restores, ["skinA", "skinB"])
        finally:
            handler.setFormatter(formatter)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

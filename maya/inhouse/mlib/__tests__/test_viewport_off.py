"""画面停止のバッチ動作とベイクのUndoを検証する。"""
import sys
import unittest
from unittest.mock import patch
import maya.cmds as cmds
import mlib
from mlib.decorator import viewportOff


class ViewportOffTest(unittest.TestCase):
    def test_batch_context_and_decorator(self):
        calls = []

        @viewportOff()
        def operation(value):
            calls.append(value)
            return value

        with patch.object(cmds, 'about', return_value=True), patch.object(
                cmds, 'paneLayout', side_effect=AssertionError('Unexpected UI call')):
            with viewportOff():
                self.assertEqual(operation(1), 1)
                self.assertEqual(operation(2), 2)
            with self.assertRaisesRegex(RuntimeError, 'original'):
                with viewportOff():
                    raise RuntimeError('original')
        self.assertEqual(calls, [1, 2])

    def test_bake_results_undo(self):
        node = cmds.createNode('transform')
        try:
            cmds.setKeyframe(node, attribute='tx', time=1, value=0)
            cmds.setKeyframe(node, attribute='tx', time=4, value=3)
            before = cmds.keyframe(node, attribute='tx', query=True, timeChange=True)
            with viewportOff():
                cmds.bakeResults(node, time=(1, 4), attribute='tx', simulation=True)
            self.assertEqual(cmds.keyframe(node, attribute='tx', query=True, timeChange=True), [1, 2, 3, 4])
            cmds.undo()
            self.assertEqual(cmds.keyframe(node, attribute='tx', query=True, timeChange=True), before)
        finally:
            cmds.delete(node)

    def test_gui_nested_exception_and_hidden_start(self):
        """メインペインの元値を入れ子でも保持し、本体例外を変更しない。"""
        state = {"manage": True, "exists": True}

        def pane(name, exists=False, query=False, edit=False, manage=None):
            """表示状態だけを保持するpaneLayoutの代役。"""
            if exists:
                return state["exists"]
            if query:
                return state["manage"]
            if edit:
                state["manage"] = manage

        with patch.object(cmds, "about", return_value=False), patch("maya.mel.eval", return_value="mainPane"), \
                patch.object(cmds, "paneLayout", side_effect=pane):
            for previous in (True, False):
                state["manage"] = previous
                with self.assertRaisesRegex(ValueError, "body"):
                    with viewportOff():
                        self.assertFalse(state["manage"])
                        with viewportOff():
                            self.assertFalse(state["manage"])
                        self.assertFalse(state["manage"])
                        raise ValueError("body")
                self.assertEqual(state["manage"], previous)

    def test_gui_missing_or_deleted_pane(self):
        """開始時にないペインは拒否し、実行中に消えたペインへ復帰要求を出さない。"""
        with patch.object(cmds, "about", return_value=False), patch("maya.mel.eval", return_value="mainPane"), \
                patch.object(cmds, "paneLayout", return_value=False) as layout:
            with self.assertRaises(RuntimeError):
                with viewportOff():
                    self.fail("Missing pane was accepted")
            layout.assert_called_once_with("mainPane", exists=True)
        with patch.object(cmds, "about", return_value=False), patch("maya.mel.eval", return_value="mainPane"), \
                patch.object(cmds, "paneLayout", side_effect=[True, True, None, False]) as layout:
            with viewportOff():
                pass
            self.assertEqual(layout.call_count, 4)
            layout.assert_any_call("mainPane", edit=True, manage=False)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])

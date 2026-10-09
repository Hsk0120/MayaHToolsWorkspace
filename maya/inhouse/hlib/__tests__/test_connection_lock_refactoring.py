"""接続編集の例外境界と親子ロックの解除・復元順を実Mayaで検証する。"""

import sys
import unittest
from unittest import mock

import hlib
import maya.cmds as cmds


class ConnectionLockRefactoringTest(unittest.TestCase):
    """一時アンロックの共有後も成功・失敗・Undoの契約を維持する。"""

    def setUp(self):
        """各テストを独立した空シーンとUndoキューで実行する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_connect_failure_restores_parent_and_child_in_reverse_order(self):
        """入力接続の失敗後も子から親へ復元し、元の例外をそのまま返す。"""
        source, target, parent = self._locked_pair()
        events = []
        error = RuntimeError("Injected connect failure")
        with mock.patch.object(hlib.plugs.Plug, "setFlags", autospec=True,
                               side_effect=self._record_flags(events)):
            with mock.patch("maya.cmds.connectAttr", side_effect=error):
                with self.assertRaises(RuntimeError) as caught:
                    target.connect(source, force=True)
        self.assertIs(caught.exception, error)
        self.assertEqual(events, [("payload", False), ("value", False),
                                  ("value", True), ("payload", True)])
        self.assertTrue(target.isLocked())
        self.assertTrue(parent.isLocked())
        self.assertIsNone(target.getSourceWithConversion())

    def test_disconnect_failure_restores_parent_and_child_in_reverse_order(self):
        """入力切断の失敗時も同じ順序でロックを復元し、接続を保つ。"""
        source, target, parent = self._locked_pair(connected=True)
        events = []
        error = RuntimeError("Injected disconnect failure")
        with mock.patch.object(hlib.plugs.Plug, "setFlags", autospec=True,
                               side_effect=self._record_flags(events)):
            with mock.patch("maya.cmds.disconnectAttr", side_effect=error):
                with self.assertRaises(RuntimeError) as caught:
                    target.disconnect(source, force=True)
        self.assertIs(caught.exception, error)
        self.assertEqual(events, [("payload", False), ("value", False),
                                  ("value", True), ("payload", True)])
        self.assertTrue(target.isLocked())
        self.assertTrue(parent.isLocked())
        self.assertTrue(cmds.isConnected(str(source), str(target)))

    def test_unlock_failure_restores_only_completed_unlocks_before_edit(self):
        """子の解除が失敗した場合、解除済みの親を戻し接続編集へ進まない。"""
        for disconnect in (False, True):
            with self.subTest(disconnect=disconnect):
                cmds.file(new=True, force=True)
                source, target, parent = self._locked_pair(connected=disconnect)
                events = []
                error = RuntimeError("Injected unlock failure")

                def fail_child(plug, locked):
                    """子のロック解除を失敗させる。"""
                    if plug.getLongName() == "value" and not locked:
                        raise error

                command = "disconnectAttr" if disconnect else "connectAttr"
                with mock.patch.object(hlib.plugs.Plug, "setFlags", autospec=True,
                                       side_effect=self._record_flags(events, fail_child)):
                    with mock.patch("maya.cmds." + command) as edit:
                        with self.assertRaises(RuntimeError) as caught:
                            if disconnect:
                                target.disconnect(source, force=True)
                            else:
                                target.connect(source, force=True)
                        edit.assert_not_called()
                self.assertIs(caught.exception, error)
                self.assertEqual(events, [("payload", False), ("value", False), ("payload", True)])
                self.assertTrue(target.isLocked())
                self.assertTrue(parent.isLocked())
                self.assertEqual(cmds.isConnected(str(source), str(target)), disconnect)

    def test_restore_failure_keeps_edit_error_as_context_and_stops_restoring(self):
        """復元失敗を送出し、そのcontextと復元途中の状態を従来通り保つ。"""
        for disconnect in (False, True):
            with self.subTest(disconnect=disconnect):
                cmds.file(new=True, force=True)
                source, target, parent = self._locked_pair(connected=disconnect)
                events = []
                edit_error = RuntimeError("Injected edit failure")
                restore_error = RuntimeError("Injected restore failure")

                def fail_restore(plug, locked):
                    """子のロック復元を失敗させる。"""
                    if plug.getLongName() == "value" and locked:
                        raise restore_error

                command = "disconnectAttr" if disconnect else "connectAttr"
                with mock.patch.object(hlib.plugs.Plug, "setFlags", autospec=True,
                                       side_effect=self._record_flags(events, fail_restore)):
                    with mock.patch("maya.cmds." + command, side_effect=edit_error):
                        with self.assertRaises(RuntimeError) as caught:
                            if disconnect:
                                target.disconnect(source, force=True)
                            else:
                                target.connect(source, force=True)
                self.assertIs(caught.exception, restore_error)
                self.assertIs(caught.exception.__context__, edit_error)
                self.assertEqual(events, [("payload", False), ("value", False), ("value", True)])
                self.assertFalse(target.isLocked())
                self.assertFalse(parent.isLocked())
                self.assertEqual(cmds.isConnected(str(source), str(target)), disconnect)

    def test_forced_connect_keeps_return_lock_order_and_one_undo_redo(self):
        """成功したforce接続の返却とロックを保ち、一回のUndo/Redoで接続を戻す。"""
        source, target, parent = self._locked_pair()
        events = []
        with mock.patch.object(hlib.plugs.Plug, "setFlags", autospec=True,
                               side_effect=self._record_flags(events)):
            result = target.connect(source, f=True)
        self.assertIs(result, target)
        self.assertEqual(events, [("payload", False), ("value", False),
                                  ("value", True), ("payload", True)])
        self.assertTrue(cmds.isConnected(str(source), str(target)))
        self.assertTrue(target.isLocked())
        self.assertTrue(parent.isLocked())
        cmds.undo()
        self.assertFalse(cmds.isConnected(str(source), str(target)))
        self.assertTrue(target.isLocked())
        self.assertTrue(parent.isLocked())
        cmds.redo()
        self.assertTrue(cmds.isConnected(str(source), str(target)))
        self.assertTrue(target.isLocked())
        self.assertTrue(parent.isLocked())

    def _locked_pair(self, connected=False):
        """親と子を個別にロックしたdouble接続先を用意する。

        Args:
            connected (bool): ロック前に入力を接続するか。

        Returns:
            tuple: 入力元、接続先の子、接続先の親。
        """
        source = hlib.nodes.Node(cmds.createNode("network")).addAttr("value")
        owner = hlib.nodes.Node(cmds.createNode("network"))
        cmds.addAttr(str(owner), longName="payload", attributeType="compound", numberOfChildren=1)
        cmds.addAttr(str(owner), longName="value", attributeType="double", parent="payload")
        target = owner.getPlug("value")
        parent = owner.getPlug("payload")
        if connected:
            target.connect(source)
        target.setFlags(locked=True)
        parent.setFlags(locked=True)
        cmds.flushUndo()
        return source, target, parent

    def _record_flags(self, events, failure=None):
        """実際のフラグ変更を行いながら操作順と指定した失敗境界を記録する。

        Args:
            events (list): 記録先。
            failure (callable | None): Plugとロック状態を受け取り、必要時に例外を送出する。

        Returns:
            callable: setFlagsへ渡すside_effect。
        """
        original = hlib.plugs.Plug.setFlags

        def record(plug, **flags):
            """フラグ変更の試行を記録して元のsetterへ委譲する。"""
            events.append((plug.getLongName(), flags["locked"]))
            if failure is not None:
                failure(plug, flags["locked"])
            return original(plug, **flags)

        return record


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

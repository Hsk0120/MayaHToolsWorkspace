"""ウィンドウAPIの検証。GUI項目は使い捨てMaya専用の環境変数で有効化する。"""
import os
import sys
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import maya.cmds as cmds
from hlib.general import Window, WorkspaceControl, WorkspaceLayout


class WindowApiTest(unittest.TestCase):
    """Maya UIを変更せず入力・復元・コマンドの意味を検証する。"""

    def setUp(self):
        """GUIコマンドを隔離する。保存先へ書き込まない。"""
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(cmds, "about", return_value=False))
        self.window = self.stack.enter_context(patch.object(cmds, "window", create=True, return_value=True))
        self.control = self.stack.enter_context(patch.object(cmds, "workspaceControl", create=True, return_value=True))
        self.manager = self.stack.enter_context(patch.object(cmds, "workspaceLayoutManager", create=True))
        self.manager.side_effect = lambda **kw: ["Main", "Other"] if kw.get("listLayouts") else "Main"
        self.mel = self.stack.enter_context(patch("hlib.general.workspaceLayout.mel.eval"))

    def test_batch_rejected(self):
        """batchではUI参照を生成しない。"""
        with patch.object(cmds, "about", return_value=True):
            for cls in (Window, WorkspaceControl, WorkspaceLayout):
                with self.assertRaises(RuntimeError):
                    cls("anything")

    def test_position_order_and_validation(self):
        """公開x/yをMayaのtop/leftへ変換する。"""
        window = Window("test")
        window.set_position(-20, 40)
        self.window.assert_called_with("test", edit=True, topLeftCorner=(40, -20))
        with self.assertRaises(TypeError):
            window.set_size(True, 10)
        with self.assertRaises(ValueError):
            window.set_size(0, 10)
        with self.assertRaises(TypeError):
            window.set_resizable(1)

    def test_snapshot_rejected_before_edit(self):
        """他のUIの退避データを誤適用しない。"""
        window = Window("test")
        self.window.reset_mock()
        with self.assertRaises(ValueError):
            window.restore({"kind": "window", "name": "other"})
        self.assertFalse(any(call[1].get("edit") for call in self.window.call_args_list))

    def test_context_restores_on_exception(self):
        """利用側例外でも復元する。"""
        window = Window("test")
        with patch.object(window, "capture", return_value={"state": "saved"}), patch.object(window, "restore") as restore:
            with self.assertRaisesRegex(RuntimeError, "body"):
                with window.temporary_state():
                    raise RuntimeError("body")
            restore.assert_called_once_with({"state": "saved"})

    def test_deleted_window_fails_restore(self):
        """削除済みUIを再作成しない。"""
        window = Window("test")
        self.window.return_value = False
        with self.assertRaises(RuntimeError):
            window.restore({"kind": "window", "name": "test"})
        self.assertFalse(any(call[1].get("edit") for call in self.window.call_args_list))

    def test_dock_lock_and_arguments(self):
        """ロックを迂回せず、配置先フラグを正しく選ぶ。"""
        control = WorkspaceControl("tool")
        with patch.object(WorkspaceLayout, "get_locked", return_value=True):
            with self.assertRaises(RuntimeError):
                control.undock()
        with patch.object(WorkspaceLayout, "get_locked", return_value=False):
            control.dock("left")
            self.control.assert_called_with("tool", edit=True, dockToMainWindow=("left", False))
            control.dock("right", "target")
            self.control.assert_called_with("tool", edit=True, dockToControl=("target", "right"))
            with self.assertRaises(ValueError):
                control.tab_to("tool")

    def test_floating_resize_only(self):
        """ドッキング中のresizeWidth/Height適用を防ぐ。"""
        control = WorkspaceControl("tool")
        with patch.object(control, "get_floating", return_value=False):
            with self.assertRaises(RuntimeError):
                control.set_size(200, 150)
        with patch.object(control, "get_floating", return_value=True):
            control.set_size(200, 150)
            self.control.assert_called_with("tool", edit=True, resizeWidth=200, resizeHeight=150)

    def test_layout_save_current_guard_and_collision(self):
        """別の配置や同名配置を暗黙に上書きしない。"""
        other = WorkspaceLayout("Other")
        with self.assertRaises(RuntimeError):
            other.save()
        current = WorkspaceLayout.current()
        with self.assertRaises(ValueError):
            current.save_as("Other")
        with self.assertRaises(ValueError):
            current.save_as("C:/somewhere")
        current.save()
        self.manager.assert_called_with(save=True)

    def test_lock_standard_procedure(self):
        """標準手続きで鍵アイコンも同期する。"""
        WorkspaceLayout.lock()
        self.assertIn("updateWorkspaceDocking 1", self.mel.call_args[0][0])
        with self.assertRaises(TypeError):
            WorkspaceLayout.set_locked("false")

    def test_layout_restore_failure_restores_lock(self):
        """配置復元失敗でも元のロックに戻す。"""
        layout = WorkspaceLayout()
        snapshot = {"kind": "workspaceLayout", "name": "Main", "main_window": "MayaWindow", "docking": "abc", "controls": [], "locked": False}
        def window(name, **kw):
            if kw.get("edit"):
                raise RuntimeError("restore failed")
            return True
        self.window.side_effect = window
        with patch("hlib.general.workspaceLayout.MainWindow.name", return_value="MayaWindow"), patch.object(WorkspaceLayout, "get_locked", return_value=True), patch.object(WorkspaceLayout, "set_locked") as lock:
            with self.assertRaisesRegex(RuntimeError, "restore failed"):
                layout.restore(snapshot)
            self.assertEqual([call[0] for call in lock.call_args_list], [(False,), (True,)])


@unittest.skipUnless(os.environ.get("HLIB_WINDOW_LAYOUT_TEST") == "1" and not cmds.about(batch=True), "Requires disposable Maya GUI")
class WindowGuiTest(unittest.TestCase):
    """隔離プロファイル内でUIと保存を検証する。"""

    def test_window_state(self):
        """windowのサイズ固定・メモリ復元を確認する。"""
        name = cmds.window(title="hlib window test", widthHeight=(300, 180))
        try:
            cmds.columnLayout(parent=name)
            window = Window(name)
            window.show()
            window.set_resizable(False)
            self.assertFalse(window.get_resizable())
            snapshot = window.capture()
            window.hide()
            window.set_resizable(True)
            window.restore(snapshot)
            self.assertTrue(window.get_visible())
            self.assertFalse(window.get_resizable())
            window.set_position(200, 180)
            self.assertEqual(window.get_position(), (200, 180))
        finally:
            cmds.deleteUI(name, window=True)

    def test_dock_and_layout(self):
        """独立プロファイルでドッキング・ロック・名前付き保存を確認する。"""
        import uuid
        name = "hlibWindowTest" + uuid.uuid4().hex[:8]
        layout_name = "hlibLayoutTest" + uuid.uuid4().hex[:8]
        original = WorkspaceLayout.current()
        locked = WorkspaceLayout.get_locked()
        tool = cmds.workspaceControl(name, uiScript="", retain=False, floating=True)
        try:
            control = WorkspaceControl(tool)
            WorkspaceLayout.unlock()
            control.dock("right")
            self.assertFalse(control.get_floating())
            snapshot = original.capture()
            control.undock()
            self.assertTrue(control.get_floating())
            original.restore(snapshot)
            self.assertFalse(control.get_floating())
            WorkspaceLayout.lock()
            self.assertTrue(WorkspaceLayout.get_locked())
            WorkspaceLayout.unlock()
            saved = original.save_as(layout_name)
            self.assertTrue(saved.is_current())
            saved.save()
            original.activate()
        finally:
            if cmds.workspaceControl(tool, exists=True):
                cmds.deleteUI(tool)
            if layout_name in (cmds.workspaceLayoutManager(listLayouts=True) or []):
                original.activate()
                cmds.workspaceLayoutManager(delete=layout_name)
            WorkspaceLayout.set_locked(locked)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

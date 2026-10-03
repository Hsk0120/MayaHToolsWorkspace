"""ウィンドウAPIの検証。GUI項目は使い捨てMaya専用の環境変数で有効化する。"""
import os
import sys
import unittest
from unittest.mock import patch
from contextlib import ExitStack
import maya.cmds as cmds
from hlib.ui import Window
from hlib.ui import WorkspaceControl
from hlib.ui import WorkspaceLayout
from hlib.ui._windowReference import _WindowReference
from hlib.ui._uiLifetime import _UiLifetime
from maya.api import OpenMayaUI
import weakref


class WindowApiTest(unittest.TestCase):
    """Maya UIを変更せず入力・復元・コマンドの意味を検証する。"""

    def setUp(self):
        """GUIコマンドを隔離する。保存先へ書き込まない。"""
        self.stack = ExitStack()
        self.callbacks = {}
        def register(name, callback):
            """削除通知を記録し、テストから明示的に発火できるようにする。"""
            self.callbacks[name] = callback
            return len(self.callbacks)
        self.stack.enter_context(patch.object(_UiLifetime, "_instances", weakref.WeakValueDictionary()))
        self.stack.enter_context(patch.object(_UiLifetime, "_remove_callback"))
        message = self.stack.enter_context(patch.object(OpenMayaUI, "MUiMessage"))
        message.addUiDeletedCallback.side_effect = register
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(cmds, "about", return_value=False))
        self.window = self.stack.enter_context(patch.object(cmds, "window", create=True, return_value=True))
        self.control = self.stack.enter_context(patch.object(cmds, "workspaceControl", create=True, return_value=True))
        self.manager = self.stack.enter_context(patch.object(cmds, "workspaceLayoutManager", create=True))
        self.manager.side_effect = lambda **kw: ["Main", "Other"] if kw.get("listLayouts") else "Main"
        self.mel = self.stack.enter_context(patch("hlib.ui.workspaceLayout.mel.eval"))

    def test_batch_rejected(self):
        """batchではUI参照を生成しない。"""
        with patch.object(cmds, "about", return_value=True):
            for cls in (Window, WorkspaceControl, WorkspaceLayout):
                with self.assertRaises(RuntimeError):
                    cls("anything")

    def test_position_order_and_validation(self):
        """公開x/yをMayaのtop/leftへ変換する。"""
        window = Window("test")
        window.setPosition(-20, 40)
        self.window.assert_called_with("test", edit=True, topLeftCorner=(40, -20))
        with self.assertRaises(TypeError):
            window.setSize(True, 10)
        with self.assertRaises(ValueError):
            window.setSize(0, 10)
        with self.assertRaises(TypeError):
            window.setResizable(1)

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
                with window.temporaryState():
                    raise RuntimeError("body")
            restore.assert_called_once_with({"state": "saved"})

    def test_deleted_window_fails_restore(self):
        """削除済みUIを再作成しない。"""
        window = Window("test")
        self.window.return_value = False
        with self.assertRaises(RuntimeError):
            window.restore({"kind": "window", "name": "test"})
        self.assertFalse(any(call[1].get("edit") for call in self.window.call_args_list))

    def test_recreated_ui_and_immutable_snapshot(self):
        """同名UI再生成で古い参照を無効にし、退避値の書換えを防ぐ。"""
        original = Window("test")
        snapshot = original._capture({"state": "saved", "visible": True, "resizable": True})
        with self.assertRaises(TypeError):
            snapshot.data["state"] = "changed"
        self.callbacks["test"]()
        self.assertFalse(original.exists())
        replacement = Window("test")
        self.window.reset_mock()
        with self.assertRaises(RuntimeError):
            replacement.restore(snapshot)
        self.assertFalse(any(call[1].get("edit") for call in self.window.call_args_list))

    def test_dock_lock_and_arguments(self):
        """ロックを迂回せず、配置先フラグを正しく選ぶ。"""
        control = WorkspaceControl("tool")
        with patch.object(WorkspaceLayout, "getLocked", return_value=True):
            with self.assertRaises(RuntimeError):
                control.undock()
        with patch.object(WorkspaceLayout, "getLocked", return_value=False):
            control.dock("left")
            self.control.assert_called_with("tool", edit=True, dockToMainWindow=("left", False))
            control.dock("right", "target")
            self.control.assert_called_with("tool", edit=True, dockToControl=("target", "right"))
            with self.assertRaises(ValueError):
                control.tabTo("tool")

    def test_floating_resize_only(self):
        """ドッキング中のresizeWidth/Height適用を防ぐ。"""
        control = WorkspaceControl("tool")
        with patch.object(control, "getFloating", return_value=False):
            with self.assertRaises(RuntimeError):
                control.setSize(200, 150)
        with patch.object(control, "getFloating", return_value=True):
            control.setSize(200, 150)
            self.control.assert_called_with("tool", edit=True, resizeWidth=200, resizeHeight=150)

    def test_layout_save_current_guard_and_collision(self):
        """別の配置や同名配置を暗黙に上書きしない。"""
        other = WorkspaceLayout("Other")
        with self.assertRaises(RuntimeError):
            other.save()
        current = WorkspaceLayout.current()
        with self.assertRaises(ValueError):
            current.saveAs("Other")
        with self.assertRaises(ValueError):
            current.saveAs("C:/somewhere")
        current.save()
        self.manager.assert_called_with(save=True)

    def test_lock_standard_procedure(self):
        """標準手続きで鍵アイコンも同期する。"""
        WorkspaceLayout.lock()
        self.assertIn("updateWorkspaceDocking 1", self.mel.call_args[0][0])
        with self.assertRaises(TypeError):
            WorkspaceLayout.setLocked("false")

    def test_docking_snapshot_api_is_not_provided(self):
        """workspaceControlのドッキングを復元できないメモリ退避APIは提供しない。"""
        for name in ("captureDockingLayout", "restoreDockingLayout", "temporaryDockingLayout"):
            self.assertFalse(hasattr(WorkspaceLayout, name), name)


class WindowLifetimeTest(unittest.TestCase):
    """Mayaの削除callbackの共有・解放・同名再生成を検証する。"""

    def test_callback_shared_and_released(self):
        """最終参照解放で監視を解除し、Mayaから強参照が残らない。"""
        import gc
        with patch.object(_UiLifetime, "_instances", weakref.WeakValueDictionary()), patch.object(_UiLifetime, "_remove_callback") as remove, patch.object(OpenMayaUI, "MUiMessage") as message:
            register = message.addUiDeletedCallback
            register.return_value = 123
            first = _UiLifetime.acquire("window", "shared")
            second = _UiLifetime.acquire("window", "shared")
            self.assertIs(first, second)
            register.assert_called_once()
            callback = register.call_args[0][1]
            reference = weakref.ref(first)
            del first
            gc.collect()
            remove.assert_not_called()
            del second
            gc.collect()
            self.assertIsNone(reference())
            remove.assert_called_once_with(123)
            callback()  # 解放後の通知も安全。

    def test_deleted_ui_gets_new_lifetime(self):
        """同じ名前でも削除通知後は新しい寿命を割り当てる。"""
        with patch.object(_UiLifetime, "_instances", weakref.WeakValueDictionary()), patch.object(_UiLifetime, "_remove_callback"), patch.object(OpenMayaUI, "MUiMessage") as message:
            register = message.addUiDeletedCallback
            register.return_value = 123
            first = _UiLifetime.acquire("window", "recreated")
            register.call_args[0][1](None)
            second = _UiLifetime.acquire("window", "recreated")
            self.assertFalse(first.alive)
            self.assertTrue(second.alive)
            self.assertIsNot(first, second)


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
            window.setResizable(False)
            self.assertFalse(window.getResizable())
            snapshot = window.capture()
            window.hide()
            window.setResizable(True)
            window.restore(snapshot)
            self.assertTrue(window.getVisible())
            self.assertFalse(window.getResizable())
            window.setPosition(200, 180)
            self.assertEqual(window.getPosition(), (200, 180))
        finally:
            cmds.deleteUI(name, window=True)

    def test_same_name_recreation_invalidates_reference(self):
        """Maya標準UIの削除・同名再生成を検出する。"""
        name = cmds.window(title="hlib lifetime test")
        original = Window(name)
        snapshot = original.capture()
        cmds.deleteUI(name, window=True)
        cmds.window(name, title="replacement")
        try:
            self.assertFalse(original.exists())
            with self.assertRaises(RuntimeError):
                original.show()
            with self.assertRaises(RuntimeError):
                Window(name).restore(snapshot)
        finally:
            cmds.deleteUI(name, window=True)

    def test_dock_and_layout(self):
        """独立プロファイルでドッキング・切り離し・ロック・名前付き保存を確認する。"""
        import uuid
        name = "hlibWindowTest" + uuid.uuid4().hex[:8]
        layout_name = "hlibLayoutTest" + uuid.uuid4().hex[:8]
        original = WorkspaceLayout.current()
        locked = WorkspaceLayout.getLocked()
        tool = cmds.workspaceControl(name, uiScript="", retain=False, floating=True)
        try:
            control = WorkspaceControl(tool)
            WorkspaceLayout.unlock()
            control.dock("right")
            self.assertFalse(control.getFloating())
            control.undock()
            self.assertTrue(control.getFloating())
            control.dock("left")
            self.assertFalse(control.getFloating())
            WorkspaceLayout.lock()
            self.assertTrue(WorkspaceLayout.getLocked())
            WorkspaceLayout.unlock()
            saved = original.saveAs(layout_name)
            self.assertTrue(saved.isCurrent())
            saved.save()
            original.activate()
        finally:
            if cmds.workspaceControl(tool, exists=True):
                cmds.deleteUI(tool)
            if layout_name in (cmds.workspaceLayoutManager(listLayouts=True) or []):
                original.activate()
                cmds.workspaceLayoutManager(delete=layout_name)
            WorkspaceLayout.setLocked(locked)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

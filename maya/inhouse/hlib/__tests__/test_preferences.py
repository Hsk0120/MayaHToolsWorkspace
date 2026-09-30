"""Preferencesの状態変更と復元をMayaで検証する。"""
import sys
import tempfile
import unittest
from pathlib import Path
import maya.cmds as cmds
from hlib.general import Preferences


class PreferencesTest(unittest.TestCase):
    """ユーザー設定を保存し、変更後に必ず元へ戻す。"""

    def test_axis_and_selection(self):
        """Up軸と選択順の設定がMayaへ反映される。"""
        axis = cmds.upAxis(query=True, axis=True)
        order = cmds.selectPref(query=True, trackSelectionOrder=True)
        try:
            Preferences.set_up_axis("z" if axis == "y" else "y")
            self.assertNotEqual(Preferences.get_up_axis(), axis)
            Preferences.set_track_selection_order(not order)
            self.assertEqual(Preferences.get_track_selection_order(), not order)
        finally:
            cmds.upAxis(axis=axis)
            cmds.selectPref(trackSelectionOrder=order)

    def test_autosave(self):
        """自動保存設定だけを編集し、ファイルは作成しない。"""
        if not cmds.about(batch=True):
            self.skipTest("Auto-save toggling is tested in isolated standalone Maya")
        previous = {f: cmds.autoSave(query=True, **{f: True})
                    for f in ("enable", "interval", "folder", "destination")}
        try:
            Preferences.set_autosave_enabled(False)
            Preferences.set_autosave_interval(999999)
            self.assertEqual(Preferences.get_autosave_interval(), 999999)
            folder = Path(tempfile.gettempdir()) / "hlibPreferenceTest"
            Preferences.set_autosave_directory(folder)
            self.assertEqual(Preferences.get_autosave_directory(), folder)
            self.assertEqual(cmds.autoSave(query=True, destination=True), 1)
            Preferences.set_autosave_enabled(True)
            self.assertTrue(Preferences.get_autosave_enabled())
        finally:
            cmds.autoSave(enable=False)
            cmds.autoSave(interval=previous["interval"], folder=previous["folder"], destination=previous["destination"])
            cmds.autoSave(enable=previous["enable"])

    def test_undo_settings(self):
        """既定の履歴消去と、明示した履歴保持を区別する。"""
        if not cmds.about(batch=True):
            self.skipTest("Undo queue test requires isolated standalone Maya")
        previous = {f: cmds.undoInfo(query=True, **{f: True}) for f in ("state", "infinity", "length")}
        node = None
        try:
            Preferences.set_undo_enabled(True)
            Preferences.set_undo_limit(100)
            self.assertFalse(Preferences.get_undo_infinite())
            self.assertEqual(Preferences.get_undo_limit(), 100)
            Preferences.set_undo_infinite(True)
            self.assertTrue(Preferences.get_undo_infinite())
            node = cmds.createNode("transform")
            last = cmds.undoInfo(query=True, undoName=True)
            Preferences.set_undo_enabled(False, flush=False)
            self.assertFalse(Preferences.get_undo_enabled())
            Preferences.set_undo_enabled(True, flush=False)
            self.assertEqual(cmds.undoInfo(query=True, undoName=True), last)
            Preferences.set_undo_enabled(False)
            Preferences.set_undo_enabled(True)
            self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        finally:
            if node and cmds.objExists(node):
                cmds.delete(node)
            cmds.undoInfo(infinity=previous["infinity"], length=previous["length"])
            cmds.undoInfo(stateWithoutFlush=previous["state"])

    def test_validation(self):
        """不正な値は設定を変更する前に拒否する。"""
        with self.assertRaises(TypeError):
            Preferences.set_autosave_enabled(1)
        for value in (0, -1, float("inf"), float("nan")):
            with self.assertRaises(ValueError):
                Preferences.set_autosave_interval(value)
        for value in (0, -1, True):
            with self.assertRaises(ValueError):
                Preferences.set_undo_limit(value)
        with self.assertRaises(ValueError):
            Preferences.set_up_axis("x")
        with self.assertRaises(ValueError):
            Preferences.set_autosave_directory("")


class PreferencesSaveTest(unittest.TestCase):
    """実ユーザーの設定ファイルを変更せず保存経路を確認する。"""

    def test_explicit_save_and_default(self):
        from unittest.mock import patch
        with patch.object(Preferences, "save") as save:
            original = Preferences.get_linear_unit()
            Preferences.set_linear_unit(original)
            save.assert_not_called()
            Preferences.set_linear_unit(original, save=True)
            save.assert_called_once_with()
            with self.assertRaises(TypeError):
                Preferences.set_linear_unit(original, save=1)

    def test_save_sync_and_error(self):
        from unittest.mock import patch
        import maya.cmds as cmds
        with patch.object(cmds, "about", return_value=False), patch.object(cmds, "optionVar") as option, patch("hlib.general.preferences.mel.eval") as save:
            Preferences.save()
            save.assert_called_once_with("savePrefs -general;")
            option.assert_any_call(intValue=("TrackSelectionOrder", int(Preferences.get_track_selection_order())))
            option.assert_any_call(floatValue=("autoSaveInterval", Preferences.get_autosave_interval() / 60.0))
            self.assertFalse(any("workingUnit" in str(call) for call in option.call_args_list))
            save.side_effect = RuntimeError("save failed")
            with self.assertRaises(RuntimeError):
                Preferences.save()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

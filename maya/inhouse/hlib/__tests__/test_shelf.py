"""専用ウィンドウ内のシェルフで操作と保存を確認する。既存タブは変更しない。"""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import maya.cmds as cmds
from hlib.ui import Shelf
from hlib.ui import ShelfButton


class ShelfValidationTest(unittest.TestCase):
    def test_invalid_commands(self):
        """保存できないcallableと言語を拒否する。"""
        with self.assertRaises(TypeError):
            ShelfButton._validate_command(lambda: None, "python")
        with self.assertRaises(ValueError):
            ShelfButton._validate_command("", "javascript")

    def test_save_path_and_failure(self):
        """保存先の拡張子処理と保存失敗の伝播を確認する。"""
        shelf = object.__new__(Shelf)
        shelf._name = "TestShelf"
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "shelf_TestShelf.mel"
            with patch.object(Shelf, "_load"), patch.object(Shelf, "name", return_value="TestShelf"), patch.object(cmds, "saveShelf", create=True, return_value=True) as save:
                self.assertEqual(shelf.save(path), path.resolve())
                save.assert_called_once_with("TestShelf", str(path.resolve().with_suffix("")).replace("\\", "/"))
                with self.assertRaises(ValueError):
                    shelf.save(Path(folder) / "bad.txt")
                save.return_value = False
                with self.assertRaises(RuntimeError):
                    shelf.save(path)

    def test_buttons_filter(self):
        """区切り線を除外し、ボタン参照の順序を維持する。"""
        shelf = object.__new__(Shelf)
        shelf._name = "tab"
        with patch.object(Shelf, "_load"), patch.object(Shelf, "name", return_value="tab"), patch.object(cmds, "about", return_value=False), patch.object(cmds, "shelfLayout", create=True, return_value=["first", "separator", "second"]), patch.object(cmds, "shelfButton", create=True, side_effect=lambda name, **kw: not name.endswith("separator")):
            self.assertEqual([str(b) for b in shelf.buttons()], ["tab|first", "tab|second"])

    def test_batch_guard(self):
        """GUIなしを明示的に拒否する。"""
        with patch.object(cmds, "about", return_value=True):
            with self.assertRaises(RuntimeError):
                Shelf()
            with self.assertRaises(RuntimeError):
                ShelfButton("missing")


@unittest.skipIf(cmds.about(batch=True), "Requires Maya GUI")
class ShelfGuiTest(unittest.TestCase):
    def test_buttons_and_save(self):
        """独立UIでラベル・言語・保存・削除を確認する。"""
        window = cmds.window()
        try:
            tabs = cmds.shelfTabLayout(parent=window)
            name = cmds.shelfLayout(parent=tabs)
            shelf = Shelf(name)
            button = shelf.addButton("Test", 'print("shelf test")', annotation="tip")
            self.assertIsInstance(button, ShelfButton)
            self.assertEqual(button.getLabel(), "Test")
            self.assertEqual(button.getAnnotation(), "tip")
            button.setLabel("Changed")
            button.setIcon("commandButton.png")
            button.setCommand('print "test";', language="mel")
            self.assertEqual(button.getLanguage(), "mel")
            self.assertEqual(len(shelf.buttons()), 1)
            with tempfile.TemporaryDirectory() as folder:
                path = shelf.save(Path(folder) / "shelf_hlibTest.mel")
                self.assertTrue(path.is_file())
                self.assertIn("Changed", path.read_text(encoding="utf-8"))
            button.delete()
            self.assertFalse(button.exists())
            shelf.addButton("Clear", "pass")
            shelf.clear()
            self.assertEqual(shelf.buttons(), [])
        finally:
            cmds.deleteUI(window, window=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

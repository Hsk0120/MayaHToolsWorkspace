"""mlrig画面の表示と終了を、検証専用Maya GUIで確認する。"""
import unittest
import maya.cmds as cmds

@unittest.skipIf(cmds.about(batch=True), "Requires Maya GUI")
class MlrigEditorGuiTest(unittest.TestCase):
    def test_mlrig_editor_starts_and_closes(self):
        try:
            from PySide6 import QtWidgets
        except ImportError:
            from PySide2 import QtWidgets
        from mlrig.layerEditor import LayerEditor
        widget = LayerEditor()
        try:
            widget.show()
            QtWidgets.QApplication.processEvents()
            self.assertTrue(widget.isVisible())
        finally:
            widget.close()
            widget.deleteLater()
            QtWidgets.QApplication.processEvents()

if __name__ == "__main__":
    unittest.main()

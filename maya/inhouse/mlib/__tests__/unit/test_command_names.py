"""正式コマンド・取得の省略入口と生成専用の契約を検証する。"""

from pathlib import Path
import unittest
import uuid
import maya.cmds as cmds
import mlib


class CommandNamesTest(unittest.TestCase):
    """生成の旧名は除去し、取得の省略入口とオブジェクト側の編集を確認する。"""

    def test_exports_and_files(self):
        """基礎コマンドと作成関数だけを、同名のファイルとルートから公開する。"""
        expected = {"getNode", "getPlug", "createNode", "ls", "delete", "duplicate", "select", "objExists", "bindSkin",
                    "createContainer", "createDagContainer", "createDagPose", "createIkHandle", "createBlendShape",
                    "createCurve", "createCircle", "createLocator", "createPolyCube", "createPolySphere",
                    "createPolyCylinder", "createPolyPlane"}
        mlib.reload()
        self.assertEqual(set(mlib.cmds.__all__), expected)
        folder = Path(mlib.__file__).parent / "cmds"
        self.assertEqual({path.stem for path in folder.glob("*.py") if path.stem != "__init__"}, expected)
        for name in expected:
            self.assertIs(getattr(mlib, name), getattr(mlib.cmds, name))
            self.assertTrue(callable(getattr(mlib, name)))
        for name in ("node", "plug", "attr", "constraint", "curve", "ikHandle", "sets", "group", "listNodes"):
            self.assertFalse(hasattr(mlib, name), name)
            self.assertNotIn(name, mlib.cmds.__all__)

    def test_enum_edit_and_undo(self):
        """既存Nodeの追加アトリビュートとenum編集はUndoを保つ。"""
        node = mlib.createNode("transform", name="commandNames_" + uuid.uuid4().hex, skipSelect=True)
        try:
            enum = node.addAttr("mode", attributeType="enum", enumName="one:two")
            enum.setEnumNames(["local", "world", "foot"])
            self.assertEqual(enum.getEnumValue("foot"), 2)
            cmds.undo()
            self.assertEqual(enum.getEnumValue("two"), 1)
            cmds.redo()
            self.assertEqual(enum.getEnumValue("world"), 1)
        finally:
            node.delete()


if __name__ == "__main__":
    unittest.main()

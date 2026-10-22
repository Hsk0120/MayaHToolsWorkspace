"""get取得入口の統合と保持プロパティ・Maya標準APIを検証する。"""
import ast
import importlib
import inspect
from pathlib import Path
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib


class CanonicalGettersTest(unittest.TestCase):
    """独自取得をgetへ集約し、既存の値型・フラグを維持する。"""

    def setUp(self):
        """独立した空シーンを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.node = mlib.createNode("transform", name="canonicalGetterTarget")

    def test_no_getter_forwarding_definitions_remain(self):
        """製品と拡張に取得専用の重複defを残さない。"""
        root = Path(mlib.__file__).parent
        for path in root.rglob("*.py"):
            if any(p in ("__tests__", "_docs") for p in path.parts):
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    self.assertFalse(any(isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
                                         and d.func.id == "_getter_alias" for d in node.decorator_list), str(path))

    def test_canonical_commands_have_one_public_entry(self):
        """取得コマンドはget付きファイルと公開関数を同じ名前にする。"""
        for name in ("getNode", "getPlug", "getAttr", "getScene", "getChannelBox", "getShelf",
                     "getTimeSlider", "getViewport", "getWindow", "getWorkspaceControl", "getWorkspaceLayout", "getOutliner", "getDrivenKey"):
            module = importlib.import_module("mlib.cmds." + name)
            self.assertIs(getattr(mlib, name), getattr(module, name))
            self.assertIs(getattr(mlib.cmds, name), getattr(module, name))
        for name in ("node", "plug", "attr", "scene", "window", "viewport"):
            self.assertNotIn(name, mlib.__all__)
            self.assertNotIn(name, mlib.cmds.__all__)

    def test_queries_keep_flags_and_value_types(self):
        """内部単位と型を保ち、getの追加フラグでUI数値を選択する。"""
        import math
        self.node.setTranslate((4, 5, 6), ws=True)
        self.assertEqual(tuple(self.node.getTranslate(ws=True)), (4, 5, 6))
        angle = self.node.getPlug("rotateX")
        angle.set(math.pi / 2)
        self.assertIs(mlib.getAttr(angle), angle)
        self.assertAlmostEqual(angle.get(), math.pi / 2)
        self.assertAlmostEqual(angle.get(uiUnits=True), 90)
        self.assertIsInstance(self.node.getPlug("matrix").get(), mlib.maths.Matrix)

    def test_getter_removal_frees_attribute_names(self):
        """省略名がMayaのアトリビュートを隠さず明示getも使える。"""
        self.assertNotIn("matrix", mlib.nodes.Transform.__dict__)
        self.assertIsInstance(self.node.matrix, mlib.plugs.MatrixPlug)
        self.assertEqual(self.node.getPlug("matrix"), self.node.matrix)
        self.assertIsInstance(self.node.getMatrix(), mlib.maths.Matrix)

    def test_stored_properties_and_native_methods_remain(self):
        """保持プロパティとOpenMaya継承APIは取得統合の対象外にする。"""
        shape = mlib.getNode(cmds.polyCube(constructionHistory=False)[0]).getShape()
        vertices = shape.getVertices([0, 2])
        self.assertEqual(vertices.indices, (0, 2))
        self.assertIsInstance(inspect.getattr_static(type(vertices), "indices"), property)
        matrix = mlib.maths.Matrix(translate=(4, 5, 6))
        self.assertIs(inspect.getattr_static(mlib.maths.Matrix, "getElement"),
                      inspect.getattr_static(om2.MMatrix, "getElement"))
        self.assertEqual(matrix.getElement(3, 0), 4)


if __name__ == "__main__":
    unittest.main()

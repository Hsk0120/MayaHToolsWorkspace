"""ポリゴン生成の型付き戻り値・フラグ・Undoを実Mayaで検証する。"""

from pathlib import Path
import unittest
import uuid

import maya.cmds as cmds
import hlib


class CreatePolygonTest(unittest.TestCase):
    """各プリミティブと履歴の有無でMeshを返すことを確認する。"""

    def setUp(self):
        self.selection = cmds.ls(selection=True, long=True) or []
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.namespace = ":createPolygonTest_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)

    def test_all_primitives_with_and_without_history(self):
        for kind in (
            "cube",
            "sphere",
            "cylinder",
            "cone",
            "plane",
            "torus",
            "pipe",
            "pyramid",
            "prism",
            "helix",
            "platonicSolid",
        ):
            command = "poly" + kind[0].upper() + kind[1:]
            for history in (True, False):
                with self.subTest(kind=kind, history=history):
                    mesh = hlib.createPolygon(type=kind, constructionHistory=history)
                    self.assertIsInstance(mesh, hlib.nodes.Mesh)
                    self.assertIsInstance(mesh.transform(), hlib.nodes.Transform)
                    self.assertGreater(cmds.polyEvaluate(mesh.fullName(), vertex=True), 0)
                    nodes = [hlib.getNode(value) for value in (cmds.listHistory(mesh) or [])]
                    self.assertEqual(any(node.type() == command for node in nodes), history)

    def test_flags_dimensions_and_rename(self):
        mesh = hlib.createPolygon(typ="polyCube", n="box", w=2, h=4, d=6, sx=2, ch=False)
        self.assertEqual(mesh.transform().name().split(":")[-1], "box")
        self.assertEqual(cmds.exactWorldBoundingBox(mesh.fullName()), [-1, -2, -3, 1, 2, 3])
        self.assertEqual(cmds.polyEvaluate(mesh.fullName(), vertex=True), 12)
        identity = mesh.uuid()
        mesh.transform().rename("renamedBox")
        self.assertEqual(mesh.uuid(), identity)
        self.assertIn("renamedBox", mesh.fullName())

    def test_default_type_and_undo_redo(self):
        mesh = hlib.createPolygon()
        shape = mesh.fullName()
        parent = mesh.transform().fullName()
        history = [
            node.fullName()
            for node in [hlib.getNode(value) for value in (cmds.listHistory(mesh) or [])]
            if node.type() == "polyCube"
        ]
        self.assertEqual(len(history), 1)
        cmds.undo()
        self.assertTrue(all(not cmds.objExists(name) for name in [shape, parent] + history))
        cmds.redo()
        self.assertTrue(all(cmds.objExists(name) for name in [shape, parent] + history))

    def test_invalid_requests_leave_scene_unchanged(self):
        before = set(cmds.ls(long=True))
        for options, error in (
            ({"type": "extrudeFacet"}, ValueError),
            ({"type": None}, TypeError),
            ({"q": True}, ValueError),
            ({"e": True}, ValueError),
            ({"o": False}, ValueError),
            ({"w": 1, "width": 2}, TypeError),
            ({"type": "cube", "typ": "sphere"}, TypeError),
        ):
            with self.subTest(options=options), self.assertRaises(error):
                hlib.createPolygon(**options)
        self.assertEqual(set(cmds.ls(long=True)), before)

    def test_exports(self):
        self.assertIs(hlib.createPolygon, hlib.cmds.createPolygon)
        self.assertFalse(hasattr(hlib, "polyCube"))
        self.assertFalse(hasattr(hlib.cmds, "polyCube"))
        self.assertFalse((Path(hlib.__file__).parent / "cmds" / "polyCube.py").exists())

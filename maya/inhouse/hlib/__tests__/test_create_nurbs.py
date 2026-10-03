"""NURBS生成の型付き戻り値・フラグ・Undoを実Mayaで検証する。"""

from pathlib import Path
import unittest
import uuid

import maya.cmds as cmds
import hlib


class CreateNurbsTest(unittest.TestCase):
    """全プリミティブのシェイプ型と構成数を確認する。"""

    def setUp(self):
        self.selection = cmds.ls(selection=True, long=True) or []
        self.previous = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        self.namespace = ":createNurbsTest_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.previous)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        if self.selection:
            cmds.select(self.selection, replace=True)
        else:
            cmds.select(clear=True)

    def test_all_primitives(self):
        for kind, count, curve in (
            ("circle", 1, True),
            ("square", 4, True),
            ("sphere", 1, False),
            ("cube", 6, False),
            ("cylinder", 1, False),
            ("cone", 1, False),
            ("plane", 1, False),
            ("torus", 1, False),
        ):
            for history in (True, False):
                with self.subTest(kind=kind, history=history):
                    result = hlib.createNurbs(type=kind, ch=history)
                    shapes = result if isinstance(result, list) else [result]
                    self.assertEqual(isinstance(result, list), count > 1)
                    self.assertEqual(len(shapes), count)
                    for shape in shapes:
                        self.assertIsInstance(
                            shape, hlib.nodes.NurbsCurve if curve else hlib.nodes.NurbsSurface
                        )
                        self.assertIsInstance(shape.transform(), hlib.nodes.Transform)
                        self.assertEqual(
                            bool(
                                cmds.listConnections(shape.fullName() + ".create", s=True, d=False)
                            ),
                            history,
                        )

    def test_radius_aliases_and_undo(self):
        shape = hlib.createNurbs(typ="circle", r=2.5, n="testCircle", ch=True)
        history = next(
            n
            for n in [hlib.getNode(value) for value in (cmds.listHistory(shape) or [])]
            if n.type() == "makeNurbCircle"
        )
        self.assertAlmostEqual(history.plug("radius").get(), 2.5)
        names = [shape.fullName(), shape.transform().fullName(), history.fullName()]
        cmds.undo()
        self.assertTrue(all(not cmds.objExists(n) for n in names))
        cmds.redo()
        self.assertTrue(all(cmds.objExists(n) for n in names))

    def test_cube_undo_and_command_aliases(self):
        for kind in ("nurbsCube", "nurbsSquare", "nurbsPlane"):
            before = set(cmds.ls(long=True))
            hlib.createNurbs(type=kind)
            created = set(cmds.ls(long=True)) - before
            self.assertTrue(created)
            cmds.undo()
            self.assertEqual(set(cmds.ls(long=True)), before)
            cmds.redo()
            self.assertTrue(all(cmds.objExists(n) for n in created))

    def test_invalid_requests(self):
        before = set(cmds.ls(long=True))
        for options, error in (
            ({"type": "invalid"}, ValueError),
            ({"type": None}, TypeError),
            ({"q": True}, ValueError),
            ({"e": True}, ValueError),
            ({"o": False}, ValueError),
            ({"type": "sphere", "po": 1}, ValueError),
            ({"r": 1, "radius": 2}, TypeError),
            ({"type": "circle", "typ": "sphere"}, TypeError),
        ):
            with self.subTest(options=options), self.assertRaises(error):
                hlib.createNurbs(**options)
        self.assertEqual(set(cmds.ls(long=True)), before)

    def test_exports(self):
        self.assertIs(hlib.createNurbs, hlib.cmds.createNurbs)
        self.assertFalse(hasattr(hlib, "circle"))
        self.assertFalse((Path(hlib.__file__).parent / "cmds" / "circle.py").exists())

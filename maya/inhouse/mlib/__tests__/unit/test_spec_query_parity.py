"""テストの少なかった照会系(Version・点の座標・Locator・デフォーマ・コンストレイント)を cmds と突き合わせる。"""

import math
import random
import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Version
from support.specCase import NamespaceCase


class VersionTest(unittest.TestCase):
    """Versionの各桁・接尾辞・比較・置き換え。"""

    def test_parts_suffix_and_ordering(self):
        """桁・接尾辞の取得、ゼロ埋めに依らない等価、順序、replaceを確かめる。"""
        version = Version("2027.1.2-beta")
        self.assertEqual(version.parts, (2027, 1, 2))
        self.assertEqual((version.major, version.minor, version.patch, version.build), (2027, 1, 2, 0))
        self.assertEqual(version.suffix, "-beta")
        self.assertEqual(Version("2027"), Version("2027.0.0"))
        self.assertEqual(hash(Version("2027")), hash(Version((2027, 0))))
        self.assertEqual((Version(2027).minor, Version(2027).patch), (0, 0))
        ordered = sorted(Version(value) for value in ("2025.3", "2022", "2027.0.1", "2024.2", "2027"))
        self.assertEqual([str(value) for value in ordered][0], str(Version("2022")))
        self.assertTrue(Version("2027.0.1") > Version("2027"))
        self.assertTrue(Version("2027.1").isAtLeast("2027"))
        self.assertFalse(Version("2026.9").isAtLeast(Version("2027")))
        replaced = version.replace(minor=5, build=7)
        self.assertEqual(replaced.parts, (2027, 5, 2, 7))
        self.assertEqual(version.parts, (2027, 1, 2))
        self.assertIsNone(Version.parse(None))
        self.assertIsNone(Version.parse(""))
        self.assertEqual(Version.parse("2026 Update 2"), Version("2026"))
        self.assertEqual(Version([2027, "1"]).parts, (2027, 1))
        for value, error in ((True, TypeError), ("", ValueError), (-1, ValueError), ("abc", ValueError),
                             ([1, 2.5], TypeError), ([1, -2], ValueError)):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    Version(value)


class PointPositionParityTest(NamespaceCase):
    """頂点・CVの座標はcmds.pointPosition / xformと同じ値をcmで返す。"""

    PREFIX = "mlibQueryParity_"

    def setUp(self):
        """UI単位を保存する。"""
        super().setUp()
        self.linear = cmds.currentUnit(query=True, linear=True)

    def tearDown(self):
        """UI単位を戻す。"""
        cmds.currentUnit(linear=self.linear)
        super().tearDown()

    def test_vertices_and_cvs(self):
        """移動・回転・スケールした形状の頂点とCVを、ローカル・ワールドとも比べる。UI単位がmでもcm。"""
        rng = random.Random(21)
        cube = cmds.polyCube(name=self.name("cube"), subdivisionsX=2, constructionHistory=False)[0]
        curve = cmds.curve(name=self.name("curve"), degree=3, point=[(i, math.sin(i), 0) for i in range(6)])
        for name in (cube, curve):
            cmds.setAttr(name + ".translate", *[rng.uniform(-5, 5) for _ in range(3)])
            cmds.setAttr(name + ".rotate", *[rng.uniform(-90, 90) for _ in range(3)])
            cmds.setAttr(name + ".scale", *[rng.uniform(0.5, 2) for _ in range(3)])
        mesh, nurbs = mlib.getNode(cube).getShape(), mlib.getNode(curve).getShape()
        cmds.currentUnit(linear="m")
        for shape, component, count in ((mesh, "vtx", mesh.mfn().numVertices), (nurbs, "cv", nurbs.mfn().numCVs)):
            for index in range(count):
                item = shape.getVertex(index) if component == "vtx" else shape.getCV(index)
                name = "{}.{}[{}]".format(shape.getFullName(), component, index)
                with self.subTest(component=component, index=index):
                    world = [v * 100 for v in cmds.xform(name, query=True, worldSpace=True, translation=True)]
                    local = [v * 100 for v in cmds.xform(name, query=True, objectSpace=True, translation=True)]
                    for actual, expected in zip(item.getPosition(worldSpace=True), world):
                        self.assertAlmostEqual(actual, expected, places=5)
                    for actual, expected in zip(item.getPosition(), local):
                        self.assertAlmostEqual(actual, expected, places=5)
                    self.assertAlmostEqual(item.getPositionX(worldSpace=True), world[0], places=5)
                    self.assertAlmostEqual(item.getPositionY(worldSpace=True), world[1], places=5)
                    self.assertAlmostEqual(item.getPositionZ(), local[2], places=5)
        vertices = mesh.getVertices([0, 3, 5])
        for actual, index in zip(vertices.getPositionY(worldSpace=True), (0, 3, 5)):
            self.assertAlmostEqual(actual, mesh.getVertex(index).getPositionY(worldSpace=True), places=9)
        self.assertEqual(vertices.shape, mesh)
        with self.assertRaises(IndexError):
            mesh.getVertex(mesh.mfn().numVertices).getPosition()


class DeformerAndConstraintParityTest(NamespaceCase):
    """デフォーマ・コンストレイント・Locatorの照会をcmdsと比べる。"""

    PREFIX = "mlibQueryParity_"

    def test_locator_cluster_and_blend_shape(self):
        """Locatorの位置(通常・fast)、clusterとblendShapeの変形対象、weightのPlug。"""
        locator = mlib.createLocator(name=self.name("loc"))
        cmds.flushUndo()
        locator.setPosition((1, 2, 3))
        self.assertEqual(cmds.getAttr(locator.getFullName() + ".localPosition")[0], (1.0, 2.0, 3.0))
        cmds.undo()
        self.assertEqual(tuple(locator.getPosition()), (0.0, 0.0, 0.0))
        cmds.flushUndo()
        locator.setPosition((4, 5, 6), fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual(tuple(locator.getPosition()), (4.0, 5.0, 6.0))
        cube = cmds.polyCube(name=self.name("deformed"), constructionHistory=False)[0]
        cluster, handle = cmds.cluster(cube + ".vtx[0:3]", name=self.name("cluster"))
        node = mlib.getNode(cluster)
        self.assertEqual([shape.getFullName() for shape in node.getGeometry()],
                         cmds.ls(cmds.cluster(cluster, query=True, geometry=True), long=True))
        self.assertEqual(node.getWeightedNode().getFullName(), cmds.ls(handle, long=True)[0])
        target = cmds.polyCube(name=self.name("target"), constructionHistory=False)[0]
        blend = mlib.createBlendShape(cube, [target], name=self.name("blend"))
        self.assertEqual([shape.getFullName() for shape in blend.getBaseGeometry()],
                         cmds.ls(cmds.blendShape(blend.getFullName(), query=True, geometry=True), long=True))
        plug = blend.getWeightPlug(blend.getTargetNames()[0])
        plug.set(0.25)
        self.assertAlmostEqual(cmds.getAttr(blend.getFullName() + ".weight[0]"), 0.25)
        with self.assertRaises(ValueError):
            blend.getWeightPlug("missing")

    def test_constraint_weights_and_aim_output(self):
        """コンストレイントのターゲット・ウェイトとaimの評価出力をcmdsと比べる。"""
        a = cmds.createNode("transform", name=self.name("a"), skipSelect=True)
        b = cmds.createNode("transform", name=self.name("b"), skipSelect=True)
        driven = cmds.createNode("transform", name=self.name("driven"), skipSelect=True)
        cmds.setAttr(a + ".translate", 5, 0, 0)
        cmds.setAttr(b + ".translate", 0, 5, 3)
        constraint = mlib.getNode(cmds.parentConstraint(a, b, driven, name=self.name("parent"))[0])
        self.assertEqual([node.getName() for node in constraint.getTargets()],
                         cmds.parentConstraint(constraint.getFullName(), query=True, targetList=True))
        self.assertEqual(constraint.getWeightAliases(),
                         cmds.parentConstraint(constraint.getFullName(), query=True, weightAliasList=True))
        constraint.setWeight(0.3, a)
        self.assertAlmostEqual(constraint.getWeight(a), 0.3)
        self.assertAlmostEqual(cmds.parentConstraint(a, constraint.getFullName(), query=True, weight=True), 0.3)
        self.assertEqual(len(constraint.getWeights()), 2)
        with self.assertRaises(ValueError):
            constraint.getWeight(driven)
        aimed = cmds.createNode("transform", name=self.name("aimed"), skipSelect=True)
        cmds.setAttr(aimed + ".rotateOrder", 3)
        aim = mlib.getNode(cmds.aimConstraint(b, aimed, aimVector=(1, 0, 0), name=self.name("aim"))[0])
        output = aim.getOutputRotate()
        self.assertEqual(output.order, 3)
        for actual, axis in zip(output, "XYZ"):
            self.assertAlmostEqual(math.degrees(actual), cmds.getAttr(aim.getFullName() + ".constraintRotate" + axis), places=6)
        for actual, expected in zip(output, mlib.getNode(aimed).getRotate()):
            self.assertAlmostEqual(actual, expected, places=6)


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)

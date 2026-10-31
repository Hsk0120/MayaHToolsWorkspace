"""Transform/Jointの位置・回転・マトリクスの取得と設定を、乱数で作った階層で cmds と突き合わせる。

回転順序・rotateAxis・jointOrient・ピボットのずれ・親の回転とスケール・offsetParentMatrix を
シード固定の乱数で組み合わせ、mlib の照会が ``cmds.xform`` / ``getAttr`` と一致すること、
設定(通常・fast)の後に cmds で読んだ値が目標と一致することを確かめる。
"""

import math
import random
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import Matrix
from support.specCase import NamespaceCase

#: 1テストあたりの試行回数。
TRIALS = 40

#: 位置・マトリクスの比較の許容誤差(cm)。
TOLERANCE = 1e-6


def _angles(rng):
    """ジンバル付近を避けた回転角(度)の3成分を返す。"""
    while True:
        values = [rng.uniform(-170, 170) for _ in range(3)]
        if abs(abs(values[1]) - 90) > 5:
            return values


def _vector(rng, scale=10.0):
    """各成分が -scale〜scale の3成分を返す。"""
    return [rng.uniform(-scale, scale) for _ in range(3)]


class _ParityCase(NamespaceCase):
    """乱数の階層を作る補助と比較の補助。"""

    PREFIX = "mlibRandomParity_"

    def setUp(self):
        """UI単位を保存してcmに揃える。"""
        super().setUp()
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        cmds.currentUnit(linear="cm", angle="deg")

    def tearDown(self):
        """UI単位を戻す。"""
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        super().tearDown()

    def assert_close(self, actual, expected, tolerance=TOLERANCE, msg=None):
        """数値の列が成分ごとに近いことを確かめる。"""
        actual, expected = list(actual), list(expected)
        self.assertEqual(len(actual), len(expected), msg)
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertLessEqual(abs(a - b), tolerance * max(1.0, abs(b)), "{}: [{}] {} != {}".format(msg, index, a, b))

    def build(self, rng, index, joint):
        """親(回転・スケール)の下に、乱数の設定の Transform または Joint を作って返す。

        Args:
            rng (random.Random): 乱数。
            index (int): 名前の番号。
            joint (bool): TrueならJoint、FalseならTransform。

        Returns:
            Transform | Joint: 作った子のラッパー。
        """
        parent = cmds.createNode("transform", name=self.name("parent%d" % index), skipSelect=True)
        cmds.setAttr(parent + ".translate", *_vector(rng))
        cmds.setAttr(parent + ".rotate", *_angles(rng))
        cmds.setAttr(parent + ".scale", *[rng.uniform(0.5, 2.0) for _ in range(3)])
        kind = "joint" if joint else "transform"
        child = cmds.createNode(kind, name=self.name("child%d" % index), parent=parent, skipSelect=True)
        child = cmds.ls(child, long=True)[0]
        cmds.setAttr(child + ".rotateOrder", rng.randrange(6))
        cmds.setAttr(child + ".translate", *_vector(rng))
        cmds.setAttr(child + ".rotate", *_angles(rng))
        cmds.setAttr(child + ".rotateAxis", *_angles(rng))
        if joint:
            cmds.setAttr(child + ".jointOrient", *_angles(rng))
        else:
            cmds.setAttr(child + ".scale", *[rng.uniform(0.5, 2.0) for _ in range(3)])
            cmds.setAttr(child + ".rotatePivot", *_vector(rng, 2.0))
            cmds.setAttr(child + ".scalePivot", *_vector(rng, 2.0))
        if rng.random() < 0.5:
            offset = om2.MTransformationMatrix()
            offset.setTranslation(om2.MVector(*_vector(rng, 3.0)), om2.MSpace.kTransform)
            offset.setRotation(om2.MEulerRotation(*[math.radians(v) for v in _angles(rng)]))
            cmds.setAttr(child + ".offsetParentMatrix", list(offset.asMatrix()), type="matrix")
        return mlib.getNode(child)


class QueryParityTest(_ParityCase):
    """照会はcmdsの値と一致する。"""

    def test_matrix_translation_rotation_queries(self):
        """getMatrix(ローカル・ワールド・親・逆)・getTranslation(at)・getRotate・getQuaternion。"""
        rng = random.Random(11)
        for trial in range(TRIALS):
            node = self.build(rng, trial, joint=trial % 2 == 1)
            name = node.getFullName()
            with self.subTest(trial=trial, type=node.getType()):
                world = cmds.xform(name, query=True, worldSpace=True, matrix=True)
                self.assert_close(node.getMatrix(worldSpace=True), world, msg="world matrix")
                self.assert_close(node.getMatrix(), cmds.getAttr(name + ".matrix"), msg="local matrix")
                self.assert_close(node.getMatrix(worldSpace=True, inv=True), cmds.getAttr(name + ".worldInverseMatrix[0]"),
                                  msg="world inverse")
                self.assert_close(node.getMatrix(worldSpace=True, p=True), cmds.getAttr(name + ".parentMatrix[0]"),
                                  msg="parent matrix")
                self.assert_close(node.getTranslation(worldSpace=True),
                                  cmds.xform(name, query=True, worldSpace=True, rotatePivot=True), msg="world pivot")
                self.assert_close(node.getTranslation(worldSpace=True, at=4), world[12:15], msg="world origin")
                self.assert_close(node.getTranslation(at=1), cmds.getAttr(name + ".translate")[0], msg="translate")
                local = om2.MTransformationMatrix(om2.MMatrix(cmds.getAttr(name + ".matrix")))
                expected = local.rotation(asQuaternion=True)
                actual = node.getQuaternion(ra=True)
                dot = abs(sum(a * b for a, b in zip(actual, expected)))
                self.assertAlmostEqual(dot, 1.0, places=7, msg="local quaternion")
                rotation = node.getRotate()
                self.assertEqual(rotation.order, cmds.getAttr(name + ".rotateOrder"))
                dot = abs(sum(a * b for a, b in zip(rotation.asQuaternion(), expected)))
                self.assertAlmostEqual(dot, 1.0, places=7, msg="local rotate")

    def test_translation_in_other_linear_units(self):
        """UI単位がmでも、getTranslationはcmで返す。"""
        rng = random.Random(12)
        node = self.build(rng, 0, joint=False)
        cmds.currentUnit(linear="m")
        meters = cmds.xform(node.getFullName(), query=True, worldSpace=True, rotatePivot=True)
        self.assert_close(node.getTranslation(worldSpace=True), [v * 100 for v in meters], msg="m to cm")


class SetterParityTest(_ParityCase):
    """設定の後にcmdsで読んだ値が目標と一致し、fastと通常の結果は同じになる。"""

    def test_set_world_matrix_translation_and_rotation(self):
        """setMatrix・setTranslation・setRotate(ワールド)は、通常とfastで同じ結果になる。"""
        rng = random.Random(13)
        for trial in range(TRIALS):
            joint = trial % 2 == 1
            target = om2.MTransformationMatrix()
            target.setTranslation(om2.MVector(*_vector(rng)), om2.MSpace.kTransform)
            target.setRotation(om2.MEulerRotation(*[math.radians(v) for v in _angles(rng)]))
            target_matrix = Matrix(target.asMatrix())
            position = _vector(rng)
            rotation = _angles(rng)
            results = []
            for fast in (False, True):
                state = rng.getstate()
                node = self.build(random.Random(trial), trial * 2 + int(fast), joint)
                rng.setstate(state)
                name = node.getFullName()
                with self.subTest(trial=trial, fast=fast, type=node.getType()):
                    # 親のスケールが不均一でも届く値にするため、ワールド位置・回転は個別に確かめる。
                    node.setTranslation(position, worldSpace=True, fast=fast)
                    self.assert_close(cmds.xform(name, query=True, worldSpace=True, rotatePivot=True), position, 1e-5,
                                      "world position")
                    node.setRotate(rotation, worldSpace=True, fast=fast)
                    world = om2.MTransformationMatrix(om2.MMatrix(cmds.xform(name, query=True, worldSpace=True, matrix=True)))
                    # 3成分はノードのrotateOrderで解釈する(setRotateの仕様)。
                    order = cmds.getAttr(name + ".rotateOrder")
                    expected = om2.MEulerRotation(*[math.radians(v) for v in rotation], order).asQuaternion()
                    # 親の不均一なスケールで回転は厳密には届かないことがあるため、親のスケールを1にして確かめる。
                    parent = node.getParent().getFullName()
                    cmds.setAttr(parent + ".scale", 1, 1, 1)
                    node.setRotate(rotation, worldSpace=True, fast=fast)
                    world = om2.MTransformationMatrix(om2.MMatrix(cmds.xform(name, query=True, worldSpace=True, matrix=True)))
                    dot = abs(sum(a * b for a, b in zip(world.rotation(asQuaternion=True), expected)))
                    self.assertAlmostEqual(dot, 1.0, places=6, msg="world rotation")
                    if not joint:
                        cmds.setAttr(name + ".scale", 1, 1, 1)
                        cmds.setAttr(name + ".shear", 0, 0, 0)
                    node.setMatrix(target_matrix, worldSpace=True, fast=fast)
                    actual = Matrix(cmds.xform(name, query=True, worldSpace=True, matrix=True))
                    self.assertTrue(actual.isEquivalent(target_matrix, 1e-5),
                                    "world matrix {} != {}".format(list(actual), list(target_matrix)))
                    results.append([round(v, 6) for v in cmds.xform(name, query=True, worldSpace=True, matrix=True)])
            self.assert_close(results[0], results[1], 1e-6, "fast and normal")


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)

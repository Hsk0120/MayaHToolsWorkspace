"""SlidingFkの回転の割り振りを、OpenMayaで独立に求めた三角形の重み・球面補間・積と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import SlidingFk

#: 節の間の長さ(cm)。均等でない長さで、チェーン上の位置が長さの割合になることを確かめる。
_LENGTHS = (1.0, 2.0, 1.5, 2.5, 1.0)


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMVectorで返す。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _chain(prefix, parent, orient=True):
    """parentの下に、+Xへ_LENGTHSの長さで並ぶjointの列を作る。orientならjointOrientを持たせる。"""
    joints, current = [], parent
    for index, length in enumerate((0.0,) + _LENGTHS):
        joint = cmds.createNode("joint", name="{}{}".format(prefix, index), parent=current)
        cmds.setAttr(joint + ".translateX", length)
        if orient:
            cmds.setAttr(joint + ".jointOrient", 4 * index, -6 * index, 10)
        joints.append(cmds.ls(joint, long=True)[0])
        current = joint
    return joints


class SlidingFkTest(unittest.TestCase):
    """作成時の一致・位置の割合・重み・行列・一点への集中・曲がりの合計・重みが0・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・移動した親の下のjointOrient付き6節と、2つのコントロールを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="base")
        cmds.setAttr(self.base + ".translate", 2, 6, -1)
        cmds.setAttr(self.base + ".rotate", 15, 20, -10)
        self.joints = _chain("tail", self.base)
        self.controls = []
        for index in range(2):
            control = cmds.createNode("transform", name="ctrl" + str(index))
            cmds.setAttr(control + ".rotateOrder", index * 2)
            self.controls.append(control)
        self.rest = [_matrix(joint + ".worldMatrix[0]") for joint in self.joints]
        self.setup = SlidingFk.create(self.joints, self.controls, name="slide")
        self.owner = str(self.setup.container)
        self.params = [0.0]
        for length in _LENGTHS:
            self.params.append(self.params[-1] + length)
        self.params = [value / self.params[-1] for value in self.params]

    def _set(self, rotations=None, positions=None, falloffs=None):
        for index, rotate in enumerate(rotations or ()):
            cmds.setAttr(self.controls[index] + ".rotate", *rotate)
        for index, value in enumerate(positions or ()):
            cmds.setAttr("{}.position{}".format(self.owner, index), value)
        for index, value in enumerate(falloffs or ()):
            cmds.setAttr("{}.falloff{}".format(self.owner, index), value)

    def _weights(self):
        """独立に求めた正規化した重み weights[j][k]。"""
        result = [[0.0] * len(self.controls) for _ in range(len(self.joints) - 1)]
        for k in range(len(self.controls)):
            center = cmds.getAttr("{}.position{}".format(self.owner, k))
            falloff = cmds.getAttr("{}.falloff{}".format(self.owner, k))
            triangles = [min(max(1 - abs(t - center) / falloff, 0.0), 1.0) for t in self.params[:-1]]
            total = sum(triangles)
            for j, value in enumerate(triangles):
                result[j][k] = value / total if total > 1e-6 else 0.0
        return result

    def _expected(self, parent=None):
        """独立に求めた各節のワールド行列。"""
        weights = self._weights()
        quats = []
        for control in self.controls:
            rotate = [om.MAngle(v, om.MAngle.kDegrees).asRadians() for v in cmds.getAttr(control + ".rotate")[0]]
            quats.append(om.MEulerRotation(rotate, cmds.getAttr(control + ".rotateOrder")).asQuaternion())
        parent = _matrix(self.base + ".worldMatrix[0]") if parent is None else parent
        restParent = self._restParent
        result, previous = [], parent
        for j in range(len(self.joints)):
            rotation = om.MMatrix()
            if j < len(self.joints) - 1:
                for k, quat in enumerate(quats):
                    rotation = rotation * om.MQuaternion.slerp(om.MQuaternion(), quat, weights[j][k]).asMatrix()
            local = self.rest[j] * (self.rest[j - 1].inverse() if j else restParent.inverse())
            previous = rotation * local * previous
            result.append(previous)
        return result

    @property
    def _restParent(self):
        """生成時の親のワールド行列(setUpの値)。"""
        matrix = om.MTransformationMatrix()
        matrix.setRotation(om.MEulerRotation([om.MAngle(v, om.MAngle.kDegrees).asRadians() for v in (15, 20, -10)]))
        matrix.setTranslation(om.MVector(2, 6, -1), om.MSpace.kTransform)
        return matrix.asMatrix()

    def _outputs(self, owner=None, count=None):
        owner = owner or self.owner
        return [_matrix("{}.matrix{}".format(owner, j)) for j in range(count or len(self.joints))]

    def _assertMatrices(self, actual, expected, tolerance=1e-5):
        for index, (a, b) in enumerate(zip(actual, expected)):
            for element, (x, y) in enumerate(zip(a, b)):
                self.assertAlmostEqual(x, y, delta=tolerance, msg="matrix{} element {}".format(index, element))

    def test_rest(self):
        """コントロールの回転が0なら、位置・falloffによらず各節の生成時のワールド行列と一致し、親に付いていく。"""
        self._assertMatrices(self._outputs(), self.rest)
        self._set(positions=(0.1, 0.9), falloffs=(0.05, 2.0))
        self._assertMatrices(self._outputs(), self.rest)
        cmds.setAttr(self.base + ".translate", -1, 0, 3)
        cmds.setAttr(self.base + ".rotateY", 70)
        self._assertMatrices(self._outputs(), self._expected())

    def test_parameters_and_weights(self):
        """節の位置は長さの累積の割合で、weight<j>[k] は独立計算と一致し、コントロールごとの合計は1。"""
        self.assertEqual(len(SlidingFk.parameters([(0, 0, 0), (1, 0, 0), (3, 0, 0)])), 3)
        self.assertAlmostEqual(SlidingFk.parameters([(0, 0, 0), (1, 0, 0), (3, 0, 0)])[1], 1 / 3.0)
        self.assertEqual([cmds.getAttr("{}.position{}".format(self.owner, k)) for k in range(2)], [0.25, 0.75])
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".falloff0"), 1.5 / 5)
        for positions, falloffs in (((0.25, 0.75), (0.3, 0.3)), ((0.0, 0.5), (0.2, 0.6)), ((0.42, 0.9), (1.0, 0.1))):
            with self.subTest(positions=positions, falloffs=falloffs):
                self._set(positions=positions, falloffs=falloffs)
                expected = self._weights()
                for j in range(len(self.joints) - 1):
                    for k in range(2):
                        self.assertAlmostEqual(cmds.getAttr("{}.weight{}[{}]".format(self.owner, j, k)),
                                               expected[j][k], delta=1e-5)
                for k in range(2):
                    self.assertAlmostEqual(sum(row[k] for row in expected), 1.0, delta=1e-9)

    def test_matrices(self):
        """回転・位置・falloffを変えた各状態で、各節のワールド行列が独立計算と一致する。"""
        for rotations, positions, falloffs in (
                (((0, 0, 40), (0, 0, 0)), (0.25, 0.75), (0.3, 0.3)),
                (((10, -30, 50), (-20, 15, 35)), (0.3, 0.6), (0.4, 0.25)),
                (((0, 80, 0), (60, 0, -45)), (0.05, 0.95), (1.0, 0.15)),
                (((-35, 25, 120), (0, -90, 10)), (0.5, 0.5), (0.2, 0.5))):
            with self.subTest(rotations=rotations, positions=positions):
                self._set(rotations, positions, falloffs)
                self._assertMatrices(self._outputs(), self._expected())

    def test_single_joint(self):
        """falloffを節の間より小さくして位置を節に合わせると、その節だけがコントロールの回転を全て受ける。"""
        self._set(rotations=((20, 30, 40), (0, 0, 0)), positions=(self.params[2], 0.0), falloffs=(0.01, 0.01))
        weights = self._weights()
        self.assertEqual([round(row[0], 6) for row in weights], [0, 0, 1, 0, 0])
        outputs = self._outputs()
        self._assertMatrices(outputs[:2], self.rest[:2])
        expected = om.MEulerRotation([om.MAngle(v, om.MAngle.kDegrees).asRadians() for v in (20, 30, 40)]).asMatrix()
        # 節2の回転は、節2の生成時の向きの空間でのコントロールの回転: out_2 = R · rest_2
        self._assertMatrices([outputs[2]], [expected * self.rest[2]])

    def test_total_bend(self):
        """jointOrientの無い平面のチェーンで、1つのコントロールのZ回転は節へ分かれ、先端の向きの変化の合計に等しい。"""
        flat = _chain("flat", None, orient=False)
        control = cmds.createNode("transform", name="flatCtrl")
        setup = SlidingFk.create(flat, [control], name="flatSlide", positions=(0.4,), falloff=0.5)
        cmds.setAttr(control + ".rotateZ", 60)
        outputs = self._outputs(str(setup.container), len(flat))
        direction = _position(outputs[-1]) - _position(outputs[-2])
        angle = om.MAngle(om.MVector(1, 0, 0).angle(direction)).asDegrees()
        self.assertAlmostEqual(angle, 60.0, delta=1e-4)
        self.assertGreater(direction.y, 0)

    def test_no_weight(self):
        """どの節にもfalloffが届かない位置では回転は0になり、値が壊れない。"""
        between = (self.params[1] + self.params[2]) / 2
        self._set(rotations=((30, 0, 0), (0, 0, 0)), positions=(between, 0.0), falloffs=(0.01, 0.01))
        weights = self._weights()
        self.assertEqual([row[0] for row in weights], [0.0] * 5)
        self._assertMatrices(self._outputs(), self.rest)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = []
        for j in range(len(self.joints)):
            upstream += cmds.listHistory("{}.matrix{}".format(self.owner, j), pruneDagObjects=True) or []
        outside = [node for node in set(upstream) if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "joint", "hyperLayout")]
        self.assertEqual(outside, [])
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        SlidingFk.create(self.joints, self.controls, name="undoSlide")
        self.assertTrue(cmds.objExists("undoSlide"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoSlide"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoSlide.matrix5"))

    def test_arguments(self):
        """節の数・コントロール無し・重複・transform以外・positions・falloff・長さ0・名前の重複を拒否する。"""
        node = cmds.createNode("multiplyDivide")
        same = [cmds.createNode("transform", name="same" + str(i)) for i in range(3)]
        cases = (
            ((self.joints[:2], self.controls), {}),
            ((self.joints, []), {}),
            ((self.joints, [self.joints[1]]), {}),
            ((self.joints, [self.controls[0], self.controls[0]]), {}),
            ((self.joints, [node]), {}),
            ((self.joints, self.controls), {"positions": (0.5,)}),
            ((self.joints, self.controls), {"positions": (0.5, 1.5)}),
            ((self.joints, self.controls), {"falloff": 0.0}),
            ((self.joints, self.controls), {"falloff": float("inf")}),
            ((same, self.controls), {}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                SlidingFk.create(*args, name="bad", **kwargs)
        with self.assertRaises(ValueError):
            SlidingFk.create(self.joints, self.controls, name="slide")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()

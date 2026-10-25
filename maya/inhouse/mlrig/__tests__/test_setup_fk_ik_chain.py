"""FkIkChainの切り替えを、OpenMayaで独立に求めた相対行列・球面補間・積と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import FkIkChain

#: 節の数と、節の間の長さ(cm)。
_COUNT = 5
_LENGTH = 2.0


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMVectorで返す。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _blend(first, second, weight):
    """blendMatrixと同じ考え方(scale・移動は線形、回転は球面補間)で2つの行列を混ぜる(独立計算)。"""
    a, b = om.MTransformationMatrix(first), om.MTransformationMatrix(second)
    scale = [x + (y - x) * weight for x, y in zip(a.scale(om.MSpace.kTransform), b.scale(om.MSpace.kTransform))]
    rotation = om.MQuaternion.slerp(a.rotation(asQuaternion=True), b.rotation(asQuaternion=True), weight)
    translate = a.translation(om.MSpace.kTransform) * (1 - weight) + b.translation(om.MSpace.kTransform) * weight
    result = om.MTransformationMatrix()
    result.setScale(scale, om.MSpace.kTransform)
    result.setRotation(rotation)
    result.setTranslation(translate, om.MSpace.kTransform)
    return result.asMatrix()


def _chain(prefix, kind, parent, rotations):
    """parentの下に、+Xへ_LENGTHずつ並ぶ節の親子の列を作る。"""
    nodes, current = [], parent
    for index, rotate in enumerate(rotations):
        node = cmds.createNode(kind, name="{}{}".format(prefix, index), parent=current)
        cmds.setAttr(node + ".translateX", _LENGTH if index else 0.0)
        cmds.setAttr(node + ".rotate", *rotate)
        nodes.append(cmds.ls(node, long=True)[0])
        current = node
    return nodes


class FkIkChainTest(unittest.TestCase):
    """両端の割合・途中の割合(local/world)・節の間の長さ・追従・表示・FKの合わせ込み・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転した親の下に、姿勢の違うFK(transform)とIK(joint)の5節のチェーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.base = cmds.createNode("transform", name="base")
        cmds.setAttr(self.base + ".translate", 1, 5, -2)
        cmds.setAttr(self.base + ".rotate", 10, 30, 0)
        self.fk = _chain("fk", "transform", self.base, [(0, 0, 10)] * _COUNT)
        self.ik = _chain("ik", "joint", self.base, [(0, 15, -20), (5, 0, -25), (0, -10, 30), (0, 20, 0), (10, 0, 0)])
        self.setup = FkIkChain.create(self.fk, self.ik, name="chain")
        self.owner = str(self.setup.container)

    def _outputs(self, owner=None):
        owner = owner or self.owner
        return [_matrix("{}.matrix{}".format(owner, index)) for index in range(_COUNT)]

    def _worlds(self, chain):
        return [_matrix(node + ".worldMatrix[0]") for node in chain]

    def _expectedLocal(self, weight):
        """親の節に対する相対行列を混ぜて根元から積んだ、期待するワールド行列。"""
        fk, ik = self._worlds(self.fk), self._worlds(self.ik)
        result = [_blend(fk[0], ik[0], weight)]
        for index in range(1, _COUNT):
            local = _blend(fk[index] * fk[index - 1].inverse(), ik[index] * ik[index - 1].inverse(), weight)
            result.append(local * result[-1])
        return result

    def _assertMatrices(self, actual, expected, tolerance=1e-5):
        for index, (a, b) in enumerate(zip(actual, expected)):
            for element, (x, y) in enumerate(zip(a, b)):
                self.assertAlmostEqual(x, y, delta=tolerance, msg="matrix{} element {}".format(index, element))

    def _blendTo(self, weight, owner=None):
        cmds.setAttr((owner or self.owner) + ".blend", weight)

    def test_ends(self):
        """blend=0ならFK、blend=1ならIKの各節のワールド行列と一致する(local・worldとも)。"""
        world = str(FkIkChain.create(self.fk, self.ik, name="worldChain", space="world").container)
        for owner in (self.owner, world):
            with self.subTest(owner=owner):
                self._blendTo(0.0, owner)
                self._assertMatrices(self._outputs(owner), self._worlds(self.fk))
                self._blendTo(1.0, owner)
                self._assertMatrices(self._outputs(owner), self._worlds(self.ik))

    def test_local_blend(self):
        """途中の割合では、相対行列を混ぜて根元から積んだ独立計算と一致し、節の間の長さが保たれる。"""
        for weight in (0.2, 0.5, 0.85):
            with self.subTest(weight=weight):
                self._blendTo(weight)
                outputs = self._outputs()
                self._assertMatrices(outputs, self._expectedLocal(weight))
                for index in range(1, _COUNT):
                    length = (_position(outputs[index]) - _position(outputs[index - 1])).length()
                    self.assertAlmostEqual(length, _LENGTH, delta=1e-5)

    def test_world_blend(self):
        """space="world"では節ごとにワールド行列を混ぜ、途中の割合では節の間が縮む(localとの違い)。"""
        world = str(FkIkChain.create(self.fk, self.ik, name="worldChain", space="world").container)
        self._blendTo(0.5, world)
        fk, ik = self._worlds(self.fk), self._worlds(self.ik)
        outputs = self._outputs(world)
        self._assertMatrices(outputs, [_blend(a, b, 0.5) for a, b in zip(fk, ik)])
        tip = (_position(outputs[-1]) - _position(outputs[-2])).length()
        self.assertLess(tip, _LENGTH - 0.05)

    def test_follow(self):
        """FK・IKの節や共通の親を動かしても、出力は独立計算に追従する。"""
        cmds.setAttr(self.fk[1] + ".rotateY", 40)
        cmds.setAttr(self.ik[0] + ".rotateX", -30)
        cmds.setAttr(self.ik[3] + ".rotateZ", 60)
        cmds.setAttr(self.base + ".translate", -3, 2, 4)
        cmds.setAttr(self.base + ".rotateZ", 45)
        for weight in (0.0, 0.4, 1.0):
            with self.subTest(weight=weight):
                self._blendTo(weight)
                self._assertMatrices(self._outputs(), self._expectedLocal(weight))

    def test_visibility(self):
        """fkVisibilityは blend<1、ikVisibilityは blend>0 の間だけ真になる。"""
        for weight, expected in ((0.0, (True, False)), (0.001, (True, True)), (0.5, (True, True)),
                                 (0.999, (True, True)), (1.0, (False, True))):
            with self.subTest(weight=weight):
                self._blendTo(weight)
                self.assertEqual((cmds.getAttr(self.owner + ".fkVisibility"),
                                  cmds.getAttr(self.owner + ".ikVisibility")), expected)

    def test_match_fk_to_ik(self):
        """matchFkToIkでFKの各節がIKと同じワールド行列になり、切り替えても跳ねない。Undoで戻る。"""
        self.assertEqual([node.getFullName() for node in self.setup.getChain("fk")], self.fk)
        self.assertEqual([node.getFullName() for node in self.setup.getChain("ik")], self.ik)
        before = self._worlds(self.fk)
        cmds.undoInfo(state=True)
        FkIkChain(self.owner).matchFkToIk()
        self._assertMatrices(self._worlds(self.fk), self._worlds(self.ik))
        cmds.undo()
        self._assertMatrices(self._worlds(self.fk), before)
        cmds.redo()
        self._assertMatrices(self._worlds(self.fk), self._worlds(self.ik))
        self._blendTo(0.0)
        atFk = self._outputs()
        self._blendTo(1.0)
        self._assertMatrices(self._outputs(), atFk)

    def test_match_joint_fk(self):
        """FKがjointOrientを持つjointの列でも、matchFkToIkでIKのワールド行列に一致する。"""
        fk = _chain("jointFk", "joint", self.base, [(0, 0, 0)] * _COUNT)
        for index, node in enumerate(fk):
            cmds.setAttr(node + ".jointOrient", 5 * index, -10, 20)
        setup = FkIkChain.create(fk, self.ik, name="jointChain", blend=0.3)
        setup.matchFkToIk()
        self._assertMatrices(self._worlds(fk), self._worlds(self.ik))
        self.assertEqual(cmds.getAttr("jointChain.blend"), 0.3)

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = []
        for index in range(_COUNT):
            upstream += cmds.listHistory("{}.matrix{}".format(self.owner, index), pruneDagObjects=True) or []
        outside = [node for node in set(upstream) if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "joint", "hyperLayout")]
        self.assertEqual(outside, [])
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        FkIkChain.create(self.fk, self.ik, name="undoChain")
        self.assertTrue(cmds.objExists("undoChain"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoChain"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoChain.matrix4"))

    def test_arguments(self):
        """節の数・数の不一致・重複・transform以外・blend・space・名前の重複を拒否する。"""
        node = cmds.createNode("multiplyDivide")
        cases = (
            ((self.fk[:1], self.ik[:1]), {}),
            ((self.fk, self.ik[:-1]), {}),
            ((self.fk, self.fk), {}),
            ((self.fk[:2], [self.ik[0], self.fk[0]]), {}),
            (([self.fk[0], node], self.ik[:2]), {}),
            ((self.fk, self.ik), {"blend": 1.5}),
            ((self.fk, self.ik), {"blend": -0.1}),
            ((self.fk, self.ik), {"space": "parent"}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                FkIkChain.create(*args, name="bad", **kwargs)
        with self.assertRaises(ValueError):
            FkIkChain.create(self.fk, self.ik, name="chain")
        with self.assertRaises(ValueError):
            self.setup.getChain("other")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()

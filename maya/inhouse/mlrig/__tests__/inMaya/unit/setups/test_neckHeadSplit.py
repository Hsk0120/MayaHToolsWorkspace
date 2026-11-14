"""NeckHeadSplitの首への回転の分配と頭の向きを、独立に書いたクォータニオンの式で確かめる。"""

import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import NeckHeadSplit

#: 位置(cm)と行列の成分の許容。multMatrix・pickMatrix・blendMatrix は倍精度なので丸めの範囲で確かめる。
TOLERANCE = 1e-6


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _output(owner, index):
    return om2.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))


def _close(test, first, second, message=None):
    for a, b in zip(first, second):
        test.assertLess(abs(a - b), TOLERANCE, message)


def _rotation(matrix):
    """行列の回転だけの行列を返す。"""
    return om2.MTransformationMatrix(matrix).rotation(asQuaternion=True).asMatrix()


def _translate(vector):
    matrix = om2.MTransformationMatrix()
    matrix.setTranslation(om2.MVector(vector), om2.MSpace.kTransform)
    return matrix.asMatrix()


def _power(quaternion, ratio):
    """最短の向きの回転を ratio 乗した回転行列(軸と角度から直接作る)。"""
    q = om2.MQuaternion(quaternion)
    if q.w < 0:
        q = q.negateIt()
    axis, angle = q.asAxisAngle()
    return om2.MQuaternion(angle * ratio, axis).asMatrix()


class NeckHeadSplitTest(unittest.TestCase):
    """作成時の不変、式との一致、頭の向き、割合の端、胸への追従、所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動した胸の下に、向きを持つ首の3関節と頭、別の階層の頭のコントロールを作る。"""
        cmds.file(new=True, force=True)
        self.chest = cmds.createNode("transform", name="chest")
        cmds.setAttr(self.chest + ".translate", 1, 10, -2)
        cmds.setAttr(self.chest + ".rotate", 15, -20, 10)
        self.joints, parent = [], self.chest
        for index, role in enumerate(("neck0", "neck1", "neck2", "head")):
            cmds.select(clear=True)
            joint = cmds.joint(name=role)
            joint = cmds.parent(joint, parent)[0]
            cmds.setAttr(joint + ".translate", 0.1 * index, 1.0 + 0.2 * index, 0.3)
            cmds.setAttr(joint + ".jointOrient", 5 * index, -10, 7)
            self.joints.append(cmds.ls(joint, long=True)[0])
            parent = joint
        self.space = cmds.createNode("transform", name="ctrlSpace")
        cmds.setAttr(self.space + ".rotate", 0, 30, 0)
        self.control = cmds.createNode("transform", name="ctrl", parent=self.space)
        cmds.setAttr(self.control + ".translate", 1, 14, 2)
        cmds.setAttr(self.control + ".rotate", 10, 0, -5)
        self.rest_world = [_world(node) for node in self.joints]
        self.rest_chest = _world(self.chest)
        self.rest_control = _world(self.control)
        self.setup = NeckHeadSplit.create(self.chest, self.joints, self.control, name="split")
        self.owner = str(self.setup.container)

    def _expected(self, weights):
        """胸の空間での D の累乗と骨の向きの積み重ねで、各関節のワールド行列を独立に求める。"""
        chest = _world(self.chest)
        rest_in_chest = [world * self.rest_chest.inverse() for world in self.rest_world]
        control_rest = self.rest_control * self.rest_chest.inverse()
        control_now = _world(self.control) * chest.inverse()
        delta = om2.MTransformationMatrix(control_rest.inverse() * control_now).rotation(asQuaternion=True)
        result, total = [], 0.0
        position = om2.MVector()
        previous = om2.MVector()
        for index, rest in enumerate(rest_in_chest):
            point = om2.MVector(rest[12], rest[13], rest[14])
            bone = point - previous
            # 骨の向きは一つ前までの割合の合計で回る(行ベクトル規約)。
            moved = om2.MVector(bone) * _power(delta, total) if index else om2.MVector(bone)
            position = position + moved
            previous = point
            if index < len(rest_in_chest) - 1:
                total += weights[index]
                rotation = _power(delta, total)
            else:
                rotation = _power(delta, 1.0)
            orient = om2.MMatrix(rest)
            orient.setElement(3, 0, 0.0)
            orient.setElement(3, 1, 0.0)
            orient.setElement(3, 2, 0.0)
            result.append(orient * rotation * _translate(position) * chest)
        return result

    def _weights(self):
        return [cmds.getAttr("{}.weight{}".format(self.owner, index)) for index in range(3)]

    def test_rest_unchanged(self):
        """作成直後の出力は各関節のワールド行列と一致し、weight は keyable で既定 1/4。"""
        for index, rest in enumerate(self.rest_world):
            _close(self, _output(self.owner, index), rest, self.joints[index])
        for index in range(3):
            plug = "{}.weight{}".format(self.owner, index)
            self.assertAlmostEqual(cmds.getAttr(plug), 0.25)
            self.assertTrue(cmds.getAttr(plug, keyable=True))
        self.assertFalse(cmds.objExists(self.owner + ".weight3"))
        self.assertEqual(len(self.setup.getOutputs()), 4)

    def test_formula(self):
        """乱数のコントロールの回転と割合の30組で、出力が独立に書いた式と一致する。"""
        generator = random.Random(7)
        for _ in range(30):
            cmds.setAttr(self.control + ".rotate", *[generator.uniform(-80, 80) for _ in range(3)])
            cmds.setAttr(self.control + ".translate", *[generator.uniform(-3, 3) for _ in range(3)])
            for index in range(3):
                cmds.setAttr("{}.weight{}".format(self.owner, index), generator.uniform(0, 1))
            for index, expected in enumerate(self._expected(self._weights())):
                _close(self, _output(self.owner, index), expected, index)

    def test_head_follows_control_and_bones_keep_length(self):
        """頭の回転の変化はコントロールのワールドの回転の変化と一致し、骨の長さは変わらない。"""
        generator = random.Random(11)
        rest_points = [om2.MPoint(world[12], world[13], world[14]) for world in self.rest_world]
        for _ in range(20):
            cmds.setAttr(self.control + ".rotate", *[generator.uniform(-80, 80) for _ in range(3)])
            for index in range(3):
                cmds.setAttr("{}.weight{}".format(self.owner, index), generator.uniform(0, 0.6))
            head = _output(self.owner, 3)
            expected = _rotation(self.rest_world[3]) * _rotation(self.rest_control).inverse() \
                * _rotation(_world(self.control))
            _close(self, _rotation(head), expected)
            points = [om2.MPoint(m[12], m[13], m[14]) for m in (_output(self.owner, i) for i in range(4))]
            _close(self, points[0], rest_points[0])
            for index in range(1, 4):
                self.assertAlmostEqual(points[index].distanceTo(points[index - 1]),
                                       rest_points[index].distanceTo(rest_points[index - 1]), delta=TOLERANCE)

    def test_weight_extremes(self):
        """割合が0なら首は生成時のまま頭だけ回り、合計1なら首の先がDまで回って頭は首との関係を保つ。"""
        cmds.setAttr(self.control + ".rotate", 30, 20, -40)
        for index in range(3):
            cmds.setAttr("{}.weight{}".format(self.owner, index), 0.0)
        for index in range(3):
            _close(self, _output(self.owner, index), self.rest_world[index], index)
        head = _output(self.owner, 3)
        _close(self, (head[12], head[13], head[14]), [self.rest_world[3][12 + i] for i in range(3)])
        for index, value in enumerate((0.2, 0.3, 0.5)):
            cmds.setAttr("{}.weight{}".format(self.owner, index), value)
        relative = _output(self.owner, 3) * _output(self.owner, 2).inverse()
        _close(self, relative, self.rest_world[3] * self.rest_world[2].inverse())

    def test_chest_follow(self):
        """コントロールが胸と一緒に動けば D は単位行列のままで、首と頭は胸に付いていく。"""
        cmds.parent(self.space, self.chest)
        cmds.setAttr(self.chest + ".translate", -3, 5, 4)
        cmds.setAttr(self.chest + ".rotate", 40, 10, -60)
        chest = _world(self.chest)
        for index, rest in enumerate(self.rest_world):
            _close(self, _output(self.owner, index), rest * self.rest_chest.inverse() * chest, index)

    def test_container_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消えRedoで戻る。"""
        nodes = cmds.container(self.owner, query=True, nodeList=True) or []
        self.assertTrue(any(cmds.nodeType(node) == "blendMatrix" for node in nodes))
        self.assertTrue(all(cmds.nodeType(node) in ("multMatrix", "pickMatrix", "blendMatrix") for node in nodes))
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        NeckHeadSplit.create(self.chest, self.joints, self.control, name="split2")
        self.assertTrue(cmds.objExists("split2"))
        cmds.undo()
        self.assertFalse(cmds.objExists("split2"))
        cmds.redo()
        self.assertTrue(cmds.objExists("split2.matrix3"))

    def test_arguments(self):
        """不正な引数は ValueError。"""
        cases = [
            dict(chest="missing", joints=self.joints, control=self.control),
            dict(chest=self.chest, joints=self.joints[:1], control=self.control),
            dict(chest=self.chest, joints=self.joints, control=self.joints[0]),
            dict(chest=self.chest, joints=self.joints, control=self.control, weights=[0.5, 0.5]),
            dict(chest=self.chest, joints=self.joints, control=self.control, weights=[0.5, 0.5, 1.5]),
            dict(chest=self.chest, joints=self.joints, control=self.control, weights=[0.5, 0.5, float("nan")]),
            dict(chest=self.chest, joints=self.joints, control=self.control, name="split"),
        ]
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                NeckHeadSplit.create(**case)


if __name__ == "__main__":
    unittest.main(argv=["neck_head_split"], exit=False, verbosity=2)

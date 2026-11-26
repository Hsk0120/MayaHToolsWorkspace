"""RollUpChainの各関節の巻き取りの回転を、Pythonの式とOpenMayaで求めた期待値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import RollUpChain

_AXES = {"x": 0, "y": 1, "z": 2}


def _local(node):
    """matrix * offsetParentMatrix。"""
    return om.MMatrix(cmds.getAttr(node + ".matrix")) * om.MMatrix(cmds.getAttr(node + ".offsetParentMatrix"))


class RollUpChainTest(unittest.TestCase):
    """標準ノードの数値評価・生成時の姿勢・巻く順・範囲の端・引数検査を確認する。"""

    def setUp(self):
        """回転した親の下に、jointOrientを持つ6関節の尻尾を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.root = cmds.createNode("transform", name="hip")
        cmds.setAttr(self.root + ".rotate", 0, 30, 10)
        self.joints = []
        parent = self.root
        for index in range(6):
            joint = cmds.createNode("joint", name="tail{}".format(index), parent=parent)
            cmds.setAttr(joint + ".translate", 3 if index else 0, 0, 0)
            cmds.setAttr(joint + ".jointOrient", 0, 5 * index, -8)
            cmds.setAttr(joint + ".rotate", 2, 0, index)
            self.joints.append(joint)
            parent = joint

    def build(self, joints=None, **kwargs):
        """セットアップと、出力をoffsetParentMatrixで受ける同じ親子の結果transformを作る。"""
        joints = joints or self.joints
        owner = RollUpChain.create(joints, **kwargs).container
        results = []
        parent = cmds.listRelatives(joints[0], parent=True, fullPath=True)[0]
        for index in range(len(joints)):
            result = cmds.createNode("transform", name="result{}".format(index), parent=parent)
            cmds.connectAttr("{}.matrix{}".format(owner, index), result + ".offsetParentMatrix")
            results.append(result)
            parent = result
        return owner, results

    def check(self, owner, results, axis="z", **parameters):
        """角度・rolled・excess・totalAngleと、出力行列(ローカルの軸まわりの回転 * 入力のローカル行列)を確認する。"""
        expected, rolled, excess = RollUpChain.rollAngles(len(self.joints), **parameters)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".rolled"), rolled, places=6)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".excess"), excess, places=6)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".totalAngle"), sum(expected), places=4)
        for index, (joint, result) in enumerate(zip(self.joints, results)):
            self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), expected[index], places=4)
            values = [0.0, 0.0, 0.0]
            values[_AXES[axis]] = math.radians(expected[index])
            curl = om.MEulerRotation(*values).asMatrix()
            actual = om.MMatrix(cmds.getAttr(result + ".offsetParentMatrix"))
            self.assertTrue(actual.isEquivalent(curl * _local(joint), 1e-5), index)
        return expected

    def test_rest_pose_does_not_jump(self):
        """既定のroll=0では、生成直後の出力の各関節が入力と同じワールド行列になる。"""
        owner, results = self.build()
        for joint, result in zip(self.joints, results):
            world = om.MMatrix(cmds.getAttr(result + ".worldMatrix[0]"))
            self.assertTrue(world.isEquivalent(om.MMatrix(cmds.getAttr(joint + ".worldMatrix[0]")), 1e-5))
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".totalAngle"), 0.0, places=6)

    def test_rolls_from_tip_in_order(self):
        """rollを増やすと、先端から1関節ずつ順に曲がり、式どおりの角度になる。"""
        owner, results = self.build(angle=60, decay=0.8, width=1.0)
        parameters = {"angle": 60, "decay": 0.8, "width": 1.0}
        for roll in (0.0, 0.25, 1.0, 1.5, 2.75, 4.0, 5.3, 6.0):
            with self.subTest(roll=roll):
                cmds.setAttr(str(owner) + ".roll", roll)
                self.check(owner, results, roll=roll, **parameters)
        # roll=1.5: 先端(順0)は巻き終え、次(順1)は半分、根元側はまだ動かない。
        cmds.setAttr(str(owner) + ".roll", 1.5)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".angle5"), 60.0, places=4)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".angle4"), 60.0 * 0.8 * 0.5, places=4)
        for index in range(4):
            self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), 0.0, places=6)

    def test_limits_and_excess(self):
        """届く範囲 0〜N-1+width の外は端で止まり、超えた量がexcessに出て、範囲へ戻すと元の値へ戻る。"""
        owner, results = self.build(angle=45, decay=1.0, width=2.0)
        parameters = {"angle": 45, "decay": 1.0, "width": 2.0}
        for roll, rolled, excess in ((-1.5, 0.0, -1.5), (7.0, 7.0, 0.0), (9.25, 7.0, 2.25), (3.0, 3.0, 0.0)):
            with self.subTest(roll=roll):
                cmds.setAttr(str(owner) + ".roll", roll)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".rolled"), rolled, places=6)
                self.assertAlmostEqual(cmds.getAttr(str(owner) + ".excess"), excess, places=6)
                self.check(owner, results, roll=roll, **parameters)
        # 端では全関節が巻き終え、合計は angle * N(decay=1)。
        cmds.setAttr(str(owner) + ".roll", 100)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".totalAngle"), 45.0 * 6, places=4)

    def test_circle_closes(self):
        """まっすぐな等しい長さの鎖を decay=1・angle=360/N で全部巻くと、正N角形になって先端が根元へ戻る。"""
        base = cmds.createNode("transform", name="flat")
        joints, parent = [], base
        for index in range(6):
            joint = cmds.createNode("joint", name="flat{}".format(index), parent=parent)
            cmds.setAttr(joint + ".translateX", 2 if index else 0)
            joints.append(joint)
            parent = joint
        owner, results = self.build(joints=joints, name="circle", angle=60, decay=1.0)
        end = cmds.createNode("transform", name="end", parent=results[-1])
        cmds.setAttr(end + ".translateX", 2)
        cmds.setAttr(str(owner) + ".roll", 6)
        tip = om.MVector(cmds.xform(end, q=True, worldSpace=True, translation=True))
        self.assertLess(tip.length(), 1e-5)
        # 半分だけ巻くと、根元側の3区間はまっすぐなまま。
        cmds.setAttr(str(owner) + ".roll", 3)
        third = om.MVector(cmds.xform(results[3], q=True, worldSpace=True, translation=True))
        self.assertTrue(third.isEquivalent(om.MVector(6, 0, 0), 1e-5))

    def test_from_root_axis_and_attributes(self):
        """根元から巻く指定・軸の指定と、生成後のアトリビュート変更に追従する。"""
        owner, results = self.build(name="rootRoll", axis="y", fromRoot=True)
        parameters = {"angle": -35, "decay": 0.6, "width": 2.5}
        for attr, value in parameters.items():
            cmds.setAttr(str(owner) + "." + attr, value)
        for roll in (0.5, 2.0, 4.4, 7.5, 9.0):
            with self.subTest(roll=roll):
                cmds.setAttr(str(owner) + ".roll", roll)
                self.check(owner, results, axis="y", roll=roll, fromRoot=True, **parameters)
        # 根元から巻くので、rollが小さいうちは根元だけが曲がる。
        cmds.setAttr(str(owner) + ".roll", 0.5)
        self.assertNotAlmostEqual(cmds.getAttr(str(owner) + ".angle0"), 0.0, places=3)
        self.assertAlmostEqual(cmds.getAttr(str(owner) + ".angle5"), 0.0, places=6)

    def test_radian_ui_unit(self):
        """UIの角度単位がradianでも、角度の出力は度のまま一致する。"""
        owner, results = self.build(angle=50, decay=0.9)
        cmds.setAttr(str(owner) + ".roll", 3.5)
        expected = [cmds.getAttr("{}.angle{}".format(owner, i)) for i in range(6)]
        cmds.currentUnit(angle="rad")
        try:
            for index in range(6):
                self.assertAlmostEqual(cmds.getAttr("{}.angle{}".format(owner, index)), expected[index], places=5)
            self.check(owner, results, roll=3.5, angle=50, decay=0.9, width=1.0)
        finally:
            cmds.currentUnit(angle="deg")

    def test_invalid_arguments(self):
        """範囲外の値・軸・親子でない並び・既存の名前を拒否する。"""
        for kwargs in ({"axis": "w"}, {"angle": 200}, {"decay": 0}, {"decay": 1.5}, {"width": 0},
                       {"width": float("nan")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RollUpChain.create(self.joints, **kwargs)
        with self.assertRaises(ValueError):
            RollUpChain.create(self.joints[:1])
        with self.assertRaises(ValueError):
            RollUpChain.create([self.joints[0], self.joints[2]])
        RollUpChain.create(self.joints, name="taken")
        with self.assertRaises(ValueError):
            RollUpChain.create(self.joints, name="taken")
        # 拒否した呼び出しはノードを残さない。
        self.assertFalse(cmds.objExists("rollUpChain"))

    def test_undo_removes_graph(self):
        """生成を1回のUndoで取り消せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        before = set(cmds.ls())
        RollUpChain.create(self.joints, name="undoRoll", angle=30)
        self.assertTrue(cmds.objExists("undoRoll"))
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main()

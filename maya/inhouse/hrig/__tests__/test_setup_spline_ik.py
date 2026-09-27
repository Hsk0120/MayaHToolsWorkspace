"""Spline IK共通ビルダーの所有と入力検査を検証する。"""

import unittest
from maya import cmds
import hlib
from hrig.setups import SplineIK


class SplineIKTest(unittest.TestCase):
    """既存の骨とcontrolを所有しないことを確認する。"""

    def setUp(self):
        """隔離シーンに汎用入力を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")
        self.parent = hlib.createNode("transform", name="setup")
        self.joints = []
        parent = self.parent
        for i in range(5):
            joint = hlib.createNode("joint", name="bone" + str(i), parent=parent)
            joint.plug("tx").set(2 if i else 0)
            self.joints.append(joint)
            parent = joint
        self.controls = [hlib.createNode("transform", name="control" + str(i)) for i in range(4)]
        for i, control in enumerate(self.controls):
            control.plug("tx").set(i * 8 / 3)

    def test_ownership_enable(self):
        """所有graphの停止・再開・削除で入力骨を保持する。"""
        graph = SplineIK.create(self.joints, self.controls, self.parent)
        self.controls[1].plug("ty").set(2)
        self.assertGreater(
            abs(
                cmds.xform(
                    self.joints[2].full_name(), query=True, worldSpace=True, translation=True
                )[1]
            ),
            0.1,
        )
        graph.set_enabled(False)
        self.assertIsNone(graph.member("handle").plug("inCurve").source())
        graph.set_enabled(True)
        self.assertIsNotNone(graph.member("handle").plug("inCurve").source())
        hlib.delete(graph.container)
        self.assertTrue(all(cmds.objExists(n.full_name()) for n in self.joints + self.controls))
        self.assertFalse(cmds.ls("splineGraph*"))

    def test_invalid_inputs(self):
        """不連続骨列、重複control、循環DAG入力を拒否する。"""
        for joints, controls, parent in (
            (self.joints[::2], self.controls, self.parent),
            (self.joints, [self.controls[0]] * 4, self.parent),
            (self.joints, self.controls, self.joints[-1]),
        ):
            with self.assertRaises(ValueError):
                SplineIK.create(joints, controls, parent)
            self.assertFalse(cmds.objExists("splineGraph"))

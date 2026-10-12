"""全身骨格のサンプル(mlrig.examples.humanoid)の関節・左右対称・向き・プロキシ・Undoを検証する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.examples import humanoid


def _position(node):
    return om.MVector(*cmds.xform(node, query=True, worldSpace=True, translation=True))


def _axisX(node):
    m = cmds.xform(node, query=True, worldSpace=True, matrix=True)
    return om.MVector(*m[0:3]).normal()


class HumanoidTest(unittest.TestCase):
    """作った骨格を実際の行列で確かめる。"""

    def setUp(self):
        """空のシーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_joints_and_symmetry(self):
        """全関節があり、左右の関節が鏡像の位置にある。"""
        result = humanoid.build()
        names = humanoid.jointNames()
        self.assertEqual(sorted(result["joints"]), sorted(names))
        self.assertEqual(len(cmds.ls(type="joint")), len(names))
        for name in names:
            self.assertEqual(cmds.objectType(result["joints"][name]), "joint")
            if name.endswith("_l"):
                left, right = _position(result["joints"][name]), _position(result["joints"][name[:-2]+"_r"])
                for a, b in zip((left.x, left.y, left.z), (-right.x, right.y, right.z)):
                    self.assertAlmostEqual(a, b, places=2, msg=name)
        self.assertAlmostEqual(_position(result["joints"]["head"]).y, 157, places=4)

    def test_bone_axis_points_to_child(self):
        """子が1つの骨は、ローカル X 軸が子の方向を向く(左右とも)。"""
        result = humanoid.build()
        joints = result["joints"]
        for parent, child in (("upperarm", "lowerarm"), ("lowerarm", "hand"), ("thigh", "calf"),
                              ("calf", "foot"), ("foot", "ball"), ("index_01", "index_02")):
            for side in ("_l", "_r"):
                direction = (_position(joints[child+side])-_position(joints[parent+side])).normal()
                axis = _axisX(joints[parent+side])
                # 右は mirrorBehavior なので X 軸が逆向きになる。
                dot = axis*direction
                self.assertAlmostEqual(abs(dot), 1, places=4, msg=parent+side)
        for parent, child in (("spine_01", "spine_02"), ("neck_01", "head")):
            direction = (_position(joints[child])-_position(joints[parent])).normal()
            self.assertAlmostEqual(_axisX(joints[parent])*direction, 1, places=4)

    def test_mirror_behavior(self):
        """左右に同じ回転を入れると、動きが鏡像になる。"""
        joints = humanoid.build(fingers=False)["joints"]
        for name in ("upperarm", "lowerarm", "thigh"):
            cmds.setAttr(joints[name+"_l"]+".rotate", 10, 25, 40)
            cmds.setAttr(joints[name+"_r"]+".rotate", 10, 25, 40)
        for name in ("hand", "foot"):
            left, right = _position(joints[name+"_l"]), _position(joints[name+"_r"])
            for a, b in zip((left.x, left.y, left.z), (-right.x, right.y, right.z)):
                self.assertAlmostEqual(a, b, places=3, msg=name)

    def test_proxy_meshes(self):
        """プロキシは関節の子で、リファレンス表示。関節を回すと一緒に動く。"""
        result = humanoid.build()
        self.assertGreaterEqual(len(result["meshes"]), 40)
        for mesh in result["meshes"]:
            parent = cmds.listRelatives(mesh, parent=True)[0]
            self.assertEqual(cmds.objectType(parent), "joint")
            shape = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0]
            self.assertEqual(cmds.getAttr(shape+".overrideDisplayType"), 2)
        mesh = result["joints"]["lowerarm_l"].split("|")[-1]+"_proxy"
        before = _position(mesh)
        cmds.setAttr(result["joints"]["upperarm_l"]+".rz", -60)
        self.assertGreater((_position(mesh)-before).length(), 5)
        self.assertEqual(humanoid.build(prefix="b_", proxy=False)["meshes"], [])
        # 胸(spine_03)は子が複数あっても、首までの円柱を置く。
        self.assertTrue(cmds.objExists("spine_03_proxy"))

    def test_a_pose(self):
        """Aポーズは腕が肩から45度下がり、回転0のまま。左右対称で、骨の X 軸が子を向く。"""
        joints = humanoid.build(pose="A")["joints"]
        for side, sign in (("_l", 1), ("_r", -1)):
            direction = (_position(joints["lowerarm"+side])-_position(joints["upperarm"+side])).normal()
            self.assertAlmostEqual(direction.x, sign*0.70711, places=4)
            self.assertAlmostEqual(direction.y, -0.70711, places=4)
            self.assertAlmostEqual(abs(_axisX(joints["upperarm"+side])*direction), 1, places=4)
            for attr in ("rx", "ry", "rz"):
                self.assertAlmostEqual(cmds.getAttr(joints["upperarm"+side]+"."+attr), 0, places=6)
        hand_l, hand_r = _position(joints["middle_03_l"]), _position(joints["middle_03_r"])
        self.assertAlmostEqual(hand_l.x, -hand_r.x, places=2)
        self.assertLess(hand_l.y, 125)
        with self.assertRaises(ValueError):
            humanoid.build(prefix="bad_", pose="B")

    def test_validation_and_undo(self):
        """重複・不正な接頭辞を拒否し、作成を一回のUndoで戻せる。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        humanoid.build()
        with self.assertRaises(ValueError):
            humanoid.build()
        # "_l" を含む接頭辞でも、左右の名前が崩れない。
        second = humanoid.build(prefix="second_l_")
        self.assertTrue(cmds.objExists("second_l_lowerarm_r"))
        cmds.undo()
        second = humanoid.build(prefix="second_")
        self.assertTrue(cmds.objExists("second_hand_r"))
        self.assertEqual(second["root"].split("|")[-1], "second_root")
        cmds.undo()
        self.assertFalse(cmds.objExists("second_root"))
        self.assertTrue(cmds.objExists("root"))


if __name__ == "__main__":
    unittest.main(argv=["humanoid"], exit=False, verbosity=2)

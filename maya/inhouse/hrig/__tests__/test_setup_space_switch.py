"""汎用空間切替をMaya標準ノードの実評価で検証する。"""

import unittest

from maya import cmds

import hlib
from hrig.setups import SpaceSwitch


class SpaceSwitchTest(unittest.TestCase):
    """hrigに依存しない参照空間の操作を検証する。"""

    def setUp(self):
        """専用の空シーンを用意する。"""
        cmds.file(new=True, force=True)
        self.root = hlib.createNode("transform", name="parent", skipSelect=True)
        self.buffer = hlib.createNode("transform", name="buffer", parent=self.root, skipSelect=True)
        self.child = hlib.createNode(
            "transform", name="control", parent=self.buffer, skipSelect=True
        )
        self.child.set_translate((2, 0, 0))
        self.switch = SpaceSwitch.create(self.buffer)
        self.switch.add("local", self.root)
        self.switch.add("world")

    def test_world_local_and_undo(self):
        """子のチャンネルを維持してワールド固定とローカル追従を切り替える。"""
        self.root.set_translate((3, 0, 0))
        self.switch.switch("world")
        self.root.set_translate((5, 0, 0))
        self.assertAlmostEqual(self.child.get_translate(ws=True)[0], 5)
        self.assertAlmostEqual(self.child.get_translate()[0], 2)
        self.switch.switch("local")
        self.root.set_translate((6, 0, 0))
        self.assertAlmostEqual(self.child.get_translate(ws=True)[0], 6)
        cmds.undo()
        cmds.undo()
        self.assertEqual(SpaceSwitch(self.buffer).current(), "world")
        self.assertAlmostEqual(self.child.get_translate(ws=True)[0], 5)

    def test_reject_descendant_and_singular(self):
        """自己依存と逆行列のない空間をシーン変更なしで拒否する。"""
        with self.assertRaises(ValueError):
            self.switch.add("child", self.child)
        self.assertEqual(self.switch.labels(), ("local", "world"))
        target = hlib.createNode("transform", name="singular", skipSelect=True)
        target.plug("scaleX").set(0)
        with self.assertRaises(ValueError):
            self.switch.add("singular", target)
        self.assertEqual(self.switch.labels(), ("local", "world"))

    def test_external_target_not_owned(self):
        """所有ノード一覧に外部の参照先を含めない。"""
        external = hlib.createNode("transform", name="external", skipSelect=True)
        self.switch.add("external", external)
        self.switch.switch("external")
        self.assertNotIn(external.full_name(), [node.full_name() for node in self.switch.nodes()])
        external.set_translate((0, 3, 0))
        self.assertAlmostEqual(self.child.get_translate(ws=True)[1], 3)


if __name__ == "__main__":
    unittest.main()

"""行列追従バッファの評価・保存・Undo・入力制限を検証する。"""
from hlib.maths import MSpace

from pathlib import Path
import tempfile
import unittest

from maya import cmds

import hlib
from hrig.setups import MatrixFollow


class MatrixFollowTest(unittest.TestCase):
    """全成分追従の契約とシーン変更前の拒否を検証する。"""

    def setUp(self):
        """独立した入力と親付きバッファを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        self.source = hlib.createNode("transform", name="source", skipSelect=True)
        self.parent = hlib.createNode("transform", name="parent", skipSelect=True)
        self.target = hlib.createNode(
            "transform", name="target", parent=self.parent, skipSelect=True
        )

    def assertMatrix(self, a, b):
        """行列を許容誤差1e-7で比較する。"""
        for x, y in zip(a, b):
            self.assertAlmostEqual(x, y, places=7)

    def test_full_affine_and_parent_motion(self):
        """親の動きとscale/shearを含む入力に全成分が一致する。"""
        MatrixFollow.create(self.source, self.target, maintain_offset=False)
        for mode in ("off", "serial", "parallel"):
            cmds.evaluationManager(mode=mode)
            self.source.setTranslation((3, -2, 7), at=4)
            self.source.setRotation((17, 31, -49))
            self.source.setScaling((2, 3, 1.5))
            self.source.plug("shear").set((0.2, 0.1, -0.3))
            self.parent.setTranslation((8, -3, 2), at=4)
            self.parent.setRotation((-31, 12, 50))
            self.parent.setScaling((1.5, 0.8, 2))
            self.assertMatrix(
                self.target.plug("worldMatrix[0]").get(), self.source.plug("worldMatrix[0]").get()
            )

    def test_offset_save_and_reload(self):
        """初期姿勢とオフセットを保持し、再読込後も標準ノードだけで評価する。"""
        self.source.setTranslation((4, 0, 0), at=4)
        self.parent.setTranslation((0, 3, 0), at=4)
        MatrixFollow.create(self.source, self.target)
        self.assertAlmostEqual(self.target.getTranslation(ws=True, at=4)[0], 0)
        self.source.setTranslation((6, 0, 0), at=4)
        expected = tuple(self.target.plug("worldMatrix[0]").get())
        source_name, target_name = self.source.fullName(), self.target.fullName()
        self.assertAlmostEqual(expected[12], 2)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "matrix_follow.ma"
            cmds.file(rename=str(path))
            cmds.file(save=True, type="mayaAscii", force=True)
            cmds.file(new=True, force=True)
            cmds.file(str(path), open=True, force=True)
            self.assertMatrix(hlib.getNode(target_name).plug("worldMatrix[0]").get(), expected)
            hlib.getNode(source_name).setTranslation((7, 0, 0), at=4)
            self.assertAlmostEqual(hlib.getNode(target_name).getTranslation(ws=True, at=4)[0], 3)

    def test_undo_redo(self):
        """構築を1回のUndo/Redoで元へ戻せる。"""
        graph = MatrixFollow.create(self.source, self.target)
        name = graph.name()
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        self.assertIsNone(self.target.plug("offsetParentMatrix").sourceWithConversion())
        cmds.redo()
        self.assertTrue(cmds.objExists(name))
        self.source.setTranslation((2, 1, 3), at=4)
        self.assertMatrix(
            self.source.plug("worldMatrix[0]").get(), self.target.plug("worldMatrix[0]").get()
        )

    def test_reject_invalid_buffers(self):
        """ローカル編集・pivot・ロック・無効継承をノード追加前に拒否する。"""
        for attr, value, reset in (
            ("translateX", 2, 0),
            ("rotatePivotX", 2, 0),
            ("rotateAxisX", 5, 0),
            ("inheritsTransform", False, True),
        ):
            with self.subTest(attr=attr):
                self.target.plug(attr).set(value)
                before = set(cmds.ls())
                with self.assertRaises(ValueError):
                    MatrixFollow.create(self.source, self.target)
                self.assertEqual(set(cmds.ls()), before)
                self.target.plug(attr).set(reset)
        self.target.plug("offsetParentMatrix").setFlags(locked=True)
        with self.assertRaises(ValueError):
            MatrixFollow.create(self.source, self.target)

    def test_reject_connected_channels(self):
        """ゼロ値でも接続された出力チャンネルを上書きしない。"""
        self.source.plug("translateX").connectTo(self.target.plug("translateX"))
        with self.assertRaises(ValueError):
            MatrixFollow.create(self.source, self.target)
        self.assertEqual(len(cmds.ls(type="multMatrix")), 0)

    def test_reject_cycle_and_instancing(self):
        """DAGの子孫・DG依存・インスタンス化された親を拒否する。"""
        child = hlib.createNode("transform", parent=self.target, skipSelect=True)
        with self.assertRaises(ValueError):
            MatrixFollow.create(child, self.target)
        self.target.plug("translateX").connectTo(self.source.plug("translateX"))
        with self.assertRaises(ValueError):
            MatrixFollow.create(self.source, self.target)
        cmds.disconnectAttr(
            self.target.fullName() + ".translateX", self.source.fullName() + ".translateX"
        )
        first = cmds.createNode("transform", name="first")
        cmds.parent(self.parent.fullName(), first)
        other = cmds.createNode("transform", name="other")
        cmds.parent(self.parent.fullName(), other, addObject=True)
        with self.assertRaises(ValueError):
            MatrixFollow.create(self.source, self.target)
        self.assertEqual(len(cmds.ls(type="multMatrix")), 0)

    def test_reject_joint_and_singular(self):
        """jointOrientを持つ骨と逆行列のない入力を拒否する。"""
        joint = hlib.createNode("joint", skipSelect=True)
        with self.assertRaises(ValueError):
            MatrixFollow.create(self.source, joint)
        self.source.plug("scaleX").set(0)
        with self.assertRaises(ValueError):
            MatrixFollow.create(self.source, self.target)
        self.source.plug("scaleX").set(1)
        self.parent.plug("scaleX").set(0)
        with self.assertRaises(ValueError):
            MatrixFollow.create(self.source, self.target)

    def test_world_buffer_and_message_reference(self):
        """親なしのバッファと評価依存しないmessage参照を使用できる。"""
        cmds.parent(self.target.fullName(), world=True)
        self.source.addAttr(longName="owner", attributeType="message")
        self.target.plug("message").connectTo(self.source.plug("owner"))
        MatrixFollow.create(self.source, self.target, maintain_offset=False)
        self.source.setRotation((20, -30, 65))
        self.source.setScaling((-2, 1, 3))
        self.assertMatrix(
            self.source.plug("worldMatrix[0]").get(), self.target.plug("worldMatrix[0]").get()
        )


if __name__ == "__main__":
    unittest.main()

"""公開引数の意味を参照実装と比較する。専用Mayaで実行する。"""

import math
from pathlib import Path
import sys
import unittest

import maya.cmds as cmds
import maya.api.OpenMaya as om2

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "external" / "cymel" / "python"))
from cymel import core as cy
from hlib.nodes import Node
from hlib.maths import Quaternion, Matrix


class ApiArgumentsTest(unittest.TestCase):
    """型の同一性ではなく、引数の解釈・値・シーン更新を比較する。"""

    def setUp(self):
        """専用プロセスのシーンを初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)

    def assertValues(self, actual, expected):
        """数値列を浮動小数誤差の範囲で比較する。"""
        self.assertEqual(len(actual), len(expected))
        for a, b in zip(actual, expected):
            self.assertAlmostEqual(a, b, places=7)

    def pair(self, joint=False):
        """ピボット・回転軸・親の非一様スケールを含む比較対象を作る。"""
        parent = cmds.createNode("transform")
        name = cmds.createNode("joint" if joint else "transform", parent=parent)
        cmds.setAttr(parent + ".translate", 8, -3, 2)
        cmds.setAttr(parent + ".rotate", 20, 15, -10)
        cmds.setAttr(parent + ".scale", 1.2, 2, .7)
        for attr, values in (("translate", (2, 3, 4)), ("rotate", (17, 31, -8)),
                             ("rotateAxis", (11, -7, 4)), ("rotatePivot", (1, 2, -1)),
                             ("scalePivot", (-2, 1, 3)), ("rotatePivotTranslate", (.1, .2, .3)),
                             ("scalePivotTranslate", (.3, .1, .2))):
            cmds.setAttr(name + "." + attr, *values)
        if joint:
            cmds.setAttr(name + ".jointOrient", 9, 23, -13)
            cmds.connectAttr(parent + ".scale", name + ".inverseScale", force=True)
        return Node(name), cy.Transform(name)

    def test_translation(self):
        """atとwsの全組合せで取得・計算・移動結果を比較する。"""
        for joint in (False, True):
            node, ref = self.pair(joint)
            for ws in (False, True):
                for at in range(5):
                    with self.subTest(joint=joint, ws=ws, at=at):
                        self.assertValues(tuple(node.getTranslation(ws=ws, at=at)), tuple(ref.getTranslation(ws=ws, at=at)))
                        values = (6, -2, 8)
                        before = cmds.getAttr(node.getFullName() + ".translate")[0]
                        expected = ref.setTranslation(values, ws=ws, at=at, get=True)[:3]  # 参照値のMPoint由来w成分は座標比較から除外。
                        self.assertValues(node.setTranslation(values, ws=ws, at=at, get=True), expected)
                        self.assertEqual(cmds.getAttr(node.getFullName() + ".translate")[0], before)
                        node.setTranslation(values, ws=ws, at=at)
                        self.assertValues(tuple(node.getPlug("translate").get()), expected)
                        cmds.undo()

    def test_rotation_components(self):
        """回転合成と計算だけのsetterを参照実装と比較する。"""
        for joint in (False, True):
            node, ref = self.pair(joint)
            for ws in (False, True):
                for ra in (False, True):
                    for r in (False, True):
                        for jo in (False, True):
                            flags = dict(ws=ws, ra=ra, r=r, jo=jo)
                            with self.subTest(joint=joint, **flags):
                                try:
                                    expected = ref.getQuaternion(**flags)
                                except ValueError:
                                    with self.assertRaises(ValueError):
                                        node.getQuaternion(**flags)
                                else:
                                    self.assertTrue(node.getQuaternion(**flags).isEquivalent(om2.MQuaternion(*expected), 1e-7))
                                q = cy.Quaternion(.1, .2, .3, .9).normal()
                                try:
                                    expected = ref.setQuaternion(q, get=True, **flags)
                                except ValueError:
                                    with self.assertRaises(ValueError):
                                        node.setQuaternion(Quaternion(*q), get=True, **flags)
                                else:
                                    self.assertValues(node.setQuaternion(Quaternion(*q), get=True, **flags), expected)

    def test_scaling_shearing_matrix(self):
        """チャンネルとワールドの分解・行列オプションを比較する。"""
        for joint in (False, True):
            node, ref = self.pair(joint)
            for ws in (False, True):
                for suffix, values in (("Scaling", (2, 3, 4)), ("Shearing", (.1, .2, .3))):
                    self.assertValues(tuple(getattr(node, "get" + suffix)(ws=ws)), tuple(getattr(ref, "get" + suffix)(ws=ws)))
                    self.assertValues(getattr(node, "set" + suffix)(values, ws=ws, get=True), getattr(ref, "set" + suffix)(values, ws=ws, get=True))
                for p in (False, True):
                    for inv in (False, True):
                        self.assertValues(tuple(node.getMatrix(ws=ws, p=p, inv=inv)), tuple(ref.getMatrix(ws=ws, p=p, inv=inv)))
            original = node.getMatrix()
            values = node.setMatrix(original, get=True)
            self.assertEqual(set(values), {"translate", "rotate", "scale", "shear"})
            node.setMatrix(original)
            self.assertTrue(node.getMatrix().isEquivalent(original, 1e-7))

    def test_connections(self):
        """接続方向・短縮指定・ロック・配列・Undoを確認する。"""
        a, b, c = [Node(cmds.createNode("transform")) for _ in range(3)]
        src, dst, out = a.getPlug("tx"), b.getPlug("tx"), c.getPlug("tx")
        self.assertEqual(dst.connect(src, f=True, force=False, l=True), dst)
        self.assertTrue(dst.isLocked())
        with self.assertRaises(RuntimeError):
            dst.connect(src, f=True)
        self.assertTrue(dst.isLocked())
        dst.setFlags(locked=False)
        dst.connectTo(out)
        self.assertEqual(dst.disconnect(), src)
        self.assertEqual(out.getSourceWithConversion(), dst)
        cmds.undo()
        self.assertEqual(dst.getSourceWithConversion(), src)
        multi = b.addAttr("inputs", attributeType="double", multi=True)
        first = multi.connect(src, na=True)
        second = multi.connect(src, nextAvailable=True)
        self.assertEqual(first.mplug().logicalIndex(), 0)
        self.assertEqual(second.mplug().logicalIndex(), 1)
        self.assertEqual(multi.disconnect(src, na=True), [first, second])
        multi.setFlags(locked=True)
        with self.assertRaises(RuntimeError):
            multi.connect(src, na=True)
        multi.connect(src, na=True, f=True)
        self.assertTrue(multi.isLocked())

    def test_units_safe(self):
        """UI単位・safeの部分更新と失敗数を確認する。"""
        node, ref = self.pair()
        for linear, angle in (("cm", "deg"), ("m", "rad")):
            cmds.currentUnit(linear=linear, angle=angle)
            for name in ("translate", "rotate", "tx", "ry"):
                self.assertValues(tuple(node.getPlug(name).getu()) if name in ("translate", "rotate") else (node.getPlug(name).getu(),),
                                  tuple(ref.plug_(name).getu()) if name in ("translate", "rotate") else (ref.plug_(name).getu(),))
            node.getPlug("rotate").setu((.1, .2, .3))
            self.assertValues(node.getPlug("rotate").getu(), (.1, .2, .3))
        node.getPlug("tx").setFlags(locked=True)
        old = node.getPlug("tx").get()
        self.assertEqual(node.getPlug("translate").set((20, 30, 40), safe=True), 1)
        self.assertValues(tuple(node.getPlug("translate").get()), (old, 30, 40))
        self.assertEqual(node.getPlug("tx").set(8, True), 1)
        self.assertEqual(node.getPlug("ty").set(8, True), 0)

    def test_attribute_arguments(self):
        """型の自動選択・子名・既定値・戻り値・プロキシを確認する。"""
        node = Node(cmds.createNode("transform"))
        weight = node.addAttr("weight", dv=.5)
        self.assertEqual(weight, node.getPlug("weight"))
        self.assertEqual(weight.get(), .5)
        self.assertIsNone(node.addAttr("noReturn", getPlug=False))
        self.assertEqual(node.getPlug("weight").get(), .5)
        text = node.addAttr("label", "string", dv="control")
        self.assertEqual(text.get(), "control")
        vector = node.addAttr("offset", "double3", subType="doubleLinear",
                              childNames=("offsetA", "offsetB", "offsetC"),
                              dv=(1, 2, 3))
        self.assertValues(tuple(vector.get()), (1, 2, 3))
        self.assertEqual([p.getLongName() for p in vector.getChildren()], ["offsetA", "offsetB", "offsetC"])
        angle = node.addAttr(ln="angle", type="doubleAngle", dv=math.pi / 2)
        self.assertAlmostEqual(angle.getu(), 90)
        proxy = node.addAttr("angleProxy", proxy=angle)
        self.assertEqual(proxy.getSourceWithConversion(), angle)
        self.assertAlmostEqual(proxy.get(), angle.get())
        cmds.undo()
        self.assertFalse(node.hasAttr("angleProxy"))

    def test_safe_undo_and_get_collection(self):
        """部分更新も一回のUndoで戻し、get指定はコレクションでも計算値を返す。"""
        from hlib.nodes import Transforms
        node = Node(cmds.createNode("transform"))
        node.getPlug("ty").setFlags(locked=True)
        before = tuple(node.getPlug("translate").get())
        self.assertEqual(node.getPlug("translate").set((1, 2, 3), safe=True), 1)
        cmds.undo()
        self.assertEqual(tuple(node.getPlug("translate").get()), before)
        values = Transforms([node]).setTranslation((4, 5, 6), False, 1, False, True)
        self.assertEqual(values, [[4, 5, 6]])
        self.assertEqual(tuple(node.getPlug("translate").get()), before)


if __name__ == "__main__":
    unittest.main()

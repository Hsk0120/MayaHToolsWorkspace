"""8.0.0 で足した入口(作成関数・objExists・Time・キーの追加/削除・Shapeの親変更・setPreferredAngle)の約束を固定する。

作成関数は Shape を返し、大きさは cm(UI単位に依存しない)、選択を変えず、1回の Undo で戻ること、
不正な引数は作る前に拒否することを確かめる。接続照会の既定が直結になったことも確かめる。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Time
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、UI単位・選択の補助。"""

    PREFIX = "mlibSpecV8_"

    def setUp(self):
        """UI単位・時刻を保存して名前空間を用意する。"""
        super().setUp()
        self.linear = cmds.currentUnit(query=True, linear=True)
        self.time = cmds.currentTime(query=True)
        self.range = (cmds.playbackOptions(query=True, minTime=True), cmds.playbackOptions(query=True, maxTime=True))

    def tearDown(self):
        """UI単位・時刻を戻す。"""
        cmds.currentUnit(linear=self.linear)
        cmds.playbackOptions(minTime=self.range[0], maxTime=self.range[1])
        cmds.currentTime(self.time)
        super().tearDown()

    def assert_one_undo(self, action):
        """actionを1回のUndoで戻せ、作ったノードが消えることを確かめる。"""
        before = set(cmds.ls(long=True))
        cmds.flushUndo()
        result = action()
        self.assertTrue(set(cmds.ls(long=True)) - before)
        cmds.undo()
        self.assertEqual(set(cmds.ls(long=True)), before)
        cmds.redo()
        return result


class CreateShapeFunctionsTest(_SpecCase):
    """形状を作る関数はShapeを返し、cmで作り、選択を変えず、1回のUndoで戻る。"""

    def test_returns_named_shapes_in_centimeters(self):
        """UI単位をmにしても大きさはcmで、Transform名とShape名がそろう。"""
        cmds.currentUnit(linear="m")
        group = mlib.createNode("transform", name=self.name("grp"), skipSelect=True)
        cmds.select(clear=True)
        cases = (
            ("nurbsCurve", lambda name: mlib.createCurve([(0, 0, 0), (100, 0, 0)], name=name, parent=group)),
            ("nurbsCurve", lambda name: mlib.createCircle(radius=50, name=name)),
            ("locator", lambda name: mlib.createLocator(name=name, localScale=(2, 2, 2))),
            ("mesh", lambda name: mlib.createPolyCube(width=200, name=name)),
            ("mesh", lambda name: mlib.createPolySphere(radius=10, subdivisions=(8, 6), name=name)),
            ("mesh", lambda name: mlib.createPolyCylinder(axis=(1, 0, 0), name=name, parent=group)),
            ("mesh", lambda name: mlib.createPolyPlane(subdivisions=(2, 2), name=name)),
        )
        for index, (kind, create) in enumerate(cases):
            name = self.name("shape%d" % index)
            with self.subTest(kind=kind, index=index):
                shape = self.assert_one_undo(lambda: create(name))
                shape = mlib.getNode(name).getShape()
                self.assertEqual(shape.getType(), kind)
                self.assertEqual(shape.getNodeName(), name + "Shape")
                self.assertEqual(cmds.ls(selection=True), [])
        cmds.currentUnit(linear="cm")
        line = mlib.getNode(self.name("shape0")).getShape()
        self.assertAlmostEqual(cmds.xform(line.getFullName() + ".cv[1]", query=True, translation=True,
                                          objectSpace=True)[0], 100.0)
        self.assertEqual(line.getParent().getParent(), group)
        box = cmds.exactWorldBoundingBox(self.name("shape3"))
        self.assertAlmostEqual(box[3] - box[0], 200.0)
        self.assertEqual(tuple(mlib.getNode(self.name("shape2")).getShape().getPlug("localScale").get()), (2, 2, 2))

    def test_curve_knots_and_invalid_arguments(self):
        """knotsを受け付け、個数・次数・closedとの併用の誤りは作る前に拒否する。"""
        before = set(cmds.ls())
        points = [(0, 0, 0), (1, 0, 0), (2, 1, 0), (3, 0, 0)]
        shape = mlib.createCurve(points, degree=3, knots=[0, 0, 0, 2, 2, 2], name=self.name("knots"))
        self.assertEqual(list(shape.mfn().knots()), [0.0, 0.0, 0.0, 2.0, 2.0, 2.0])
        after = set(cmds.ls())
        for call, error in ((lambda: mlib.createCurve(points, degree=3, knots=[0, 1]), ValueError),
                            (lambda: mlib.createCurve(points, degree=3, knots=[0, 0, 0, 2, 1, 2]), ValueError),
                            (lambda: mlib.createCurve(points, degree=3, closed=True, knots=[0] * 6), ValueError),
                            (lambda: mlib.createCircle(radius=0), ValueError),
                            (lambda: mlib.createCircle(normal=(0, 0, 0)), ValueError),
                            (lambda: mlib.createPolyCube(subdivisions=(1, 1)), ValueError),
                            (lambda: mlib.createPolyCube(width=-1), ValueError),
                            (lambda: mlib.createPolySphere(subdivisions=(8, 1.5)), TypeError),
                            (lambda: mlib.createLocator(name="a|b"), ValueError)):
            with self.subTest(call=call):
                with self.assertRaises(error):
                    call()
        self.assertEqual(set(cmds.ls()), after)
        self.assertTrue(after - before)


class CreateNodeFunctionsTest(_SpecCase):
    """クラスメソッドから移した作成関数は型付きのラッパーを返し、旧入口は無い。"""

    def test_functions_and_removed_classmethods(self):
        """container・IK・blendShape・dagPose・bindSkinを作り、旧createとbindは無い。"""
        cmds.select(clear=True)
        j0 = cmds.joint(name=self.name("j0"), position=(0, 0, 0))
        j1 = cmds.joint(name=self.name("j1"), position=(5, 0, 1))
        j2 = cmds.joint(name=self.name("j2"), position=(10, 0, 0))
        self.assertIsInstance(mlib.createContainer(self.name("own")), mlib.nodes.Container)
        self.assertIsInstance(mlib.createDagContainer(self.name("dag")), mlib.nodes.DagContainer)
        handle = mlib.createIkHandle(j0, j2, name=self.name("ikh"))
        self.assertIsInstance(handle, mlib.nodes.IkHandle)
        self.assertIsInstance(mlib.createDagPose(j0, name=self.name("pose")), mlib.nodes.DagPose)
        mesh = mlib.createPolyCube(name=self.name("skinned")).getParent()
        skin = mlib.bindSkin([j0, j1], mesh, maximumInfluences=2)
        self.assertIsInstance(skin, mlib.nodes.SkinCluster)
        self.assertEqual(skin.getMaxInfluences(), 2)
        with self.assertRaises(ValueError):
            mlib.bindSkin([j0], mesh)
        with self.assertRaises(TypeError):
            mlib.bindSkin([j0], mlib.createPolyCube().getParent(), mi=2)
        base = mlib.createPolyCube(name=self.name("base")).getParent()
        target = mlib.createPolyCube(name=self.name("target")).getParent()
        self.assertEqual(mlib.createBlendShape(base, [target]).getTargetNames(), [target.getNodeName(removeNamespace=True)])
        for wrapper in (mlib.nodes.Container, mlib.nodes.DagContainer, mlib.nodes.DagPose, mlib.nodes.IkHandle,
                        mlib.nodes.BlendShape, mlib.nodes.NurbsCurve):
            with self.subTest(wrapper=wrapper.__name__):
                self.assertNotIn("create", vars(wrapper))
        self.assertFalse(hasattr(mlib.nodes.SkinCluster, "bind"))


class ObjExistsTest(_SpecCase):
    """objExistsはcmds.objExistsと同じ判定で、参照はisValidで判定する。"""

    def test_names_and_references(self):
        """ノード名・アトリビュート・Node・Plugを判定し、列はTypeError。"""
        node = mlib.createNode("transform", name=self.name("exists"), skipSelect=True)
        name = node.getFullName()
        for target in (name, name + ".tx", self.name("missing"), name + ".missingAttr"):
            with self.subTest(target=target):
                self.assertIs(mlib.objExists(target), bool(cmds.objExists(target)))
        plug = node.getPlug("tx")
        self.assertTrue(mlib.objExists(node))
        self.assertTrue(mlib.objExists(plug))
        cmds.delete(name)
        self.assertFalse(mlib.objExists(node))
        with self.assertRaises(TypeError):
            mlib.objExists([name])


class TimeTest(_SpecCase):
    """Timeは静的メソッドだけで、フレームと秒の両方で時刻・範囲を扱う。"""

    def test_current_ranges_and_preserved(self):
        """時刻・範囲の取得と変更、preservedで元の時刻へ戻ることを確かめる。"""
        cmds.currentUnit(time="film")
        self.assertEqual(Time.setCurrent(12), 12.0)
        self.assertEqual(cmds.currentTime(query=True), 12.0)
        self.assertAlmostEqual(Time.getCurrent(timeUnit="sec"), 0.5)
        Time.setCurrent(1.0, timeUnit="sec")
        self.assertEqual(Time.getCurrent(), 24.0)
        self.assertEqual(Time.setPlaybackRange(5, 48), (5.0, 48.0))
        self.assertEqual(Time.getPlaybackRange(timeUnit="sec"), (5 / 24, 2.0))
        self.assertEqual(Time.getAnimationRange(), (cmds.playbackOptions(query=True, animationStartTime=True),
                                                    cmds.playbackOptions(query=True, animationEndTime=True)))
        with self.assertRaises(ValueError):
            Time.setPlaybackRange(10, 5)
        with self.assertRaises(TypeError):
            Time.setCurrent("1")
        with self.assertRaises(TypeError):
            Time()
        with Time.preserved() as original:
            self.assertEqual(original, 24.0)
            Time.setCurrent(30)
        self.assertEqual(Time.getCurrent(), 24.0)


class KeyMethodsTest(_SpecCase):
    """Node.setKey・removeKey、Plug.removeKey、AnimCurve.removeKey(time=)。"""

    def test_set_and_remove_keys(self):
        """複数アトリビュートへのキー、範囲の削除、秒での指定、1回のUndoを確かめる。"""
        cmds.currentUnit(time="film")
        node = mlib.createNode("transform", name=self.name("keyed"), skipSelect=True)
        name = node.getFullName()
        cmds.flushUndo()
        node.setKey(["tx", "ry"], time=1)
        node.setKey(["tx", "ry"], time=1.0, timeUnit="sec", value=3)
        self.assertEqual(cmds.keyframe(name + ".tx", query=True, timeChange=True), [1.0, 24.0])
        cmds.undo()
        self.assertEqual(cmds.keyframe(name + ".tx", query=True, timeChange=True), [1.0])
        node.setKey(time=10)
        self.assertEqual(len(cmds.keyframe(name, query=True, name=True)), 10)
        node.setKey(["tx"], time=20)
        node.getPlug("tx").removeKey(time=(5, 15))
        self.assertEqual(cmds.keyframe(name + ".tx", query=True, timeChange=True), [1.0, 20.0])
        node.removeKey(["ry"], time=10)
        self.assertEqual(cmds.keyframe(name + ".ry", query=True, timeChange=True), [1.0])
        with self.assertRaises(TypeError):
            node.setKey(["tx"], attribute="ty")
        with self.assertRaises(ValueError):
            node.removeKey([], time=1)
        with self.assertRaises(ValueError):
            node.getPlug("tx").removeKey(time=(5, 1))
        curve = mlib.getNode(cmds.listConnections(name + ".tz", source=True)[0])
        curve.setKey(30, 1).setKey(40, 2)
        curve.removeKey(time=(25, 35), fast=True)
        self.assertEqual(curve.getKeyInputs(), [10.0, 40.0])
        curve.removeKey(time=(0.0, 1.0), timeUnit="sec")
        self.assertEqual(curve.getKeyInputs(), [40.0])
        with self.assertRaises(TypeError):
            curve.removeKey(0, time=40)
        with self.assertRaises(TypeError):
            curve.removeKey()


class ShapeSetParentTest(_SpecCase):
    """Shape.setParent・Transform.addShapeはローカルの形を保ってシェイプを移す。"""

    def test_normal_and_fast(self):
        """通常は1回のUndoで戻り、fastはUndoに記録しない。同名の子があればfastは拒否する。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                target = mlib.createNode("transform", name=self.name("target%d" % fast), skipSelect=True)
                target.getPlug("tx").set(5)
                shape = mlib.createCircle(radius=1, name=self.name("circle%d" % fast))
                old = shape.getParent()
                cmds.flushUndo()
                self.assertIs(shape.setParent(target, fast=fast), shape)
                self.assertEqual(shape.getParent(), target)
                self.assertEqual(old.getShapes(), [])
                self.assertTrue(old.isValid())
                if fast:
                    self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
                else:
                    cmds.undo()
                    self.assertEqual(shape.getParent(), old)
        target = mlib.createNode("transform", name=self.name("dup"), skipSelect=True)
        first = mlib.createLocator(name=self.name("loc"))
        target.addShape(first)
        self.assertEqual(target.getShapes(), [first])
        other = mlib.createNode("transform", name=self.name("other"), skipSelect=True)
        twin = mlib.createNode("locator", name=first.getNodeName(), parent=other, skipSelect=True)
        with self.assertRaises(NotImplementedError):
            twin.setParent(target, fast=True)
        with self.assertRaises(TypeError):
            target.addShape(other)


class SetPreferredAngleTest(_SpecCase):
    """Joint.setPreferredAngleは今のrotate、または指定値をpreferredAngleへ書く。"""

    def test_current_rotate_and_value(self):
        """省略時は今のrotate、値の指定は度・ラジアンで、1回のUndoで戻る。"""
        joint = mlib.createNode("joint", name=self.name("joint"), skipSelect=True)
        joint.getPlug("rotate").set((10, 20, 30))
        cmds.flushUndo()
        joint.setPreferredAngle()
        for actual, expected in zip(joint.getPlug("preferredAngle").get(), (10, 20, 30)):
            self.assertAlmostEqual(actual, expected)
        cmds.undo()
        self.assertEqual(tuple(joint.getPlug("preferredAngle").get()), (0, 0, 0))
        joint.setPreferredAngle((0, 0, 3.14159265358979 / 2), unit="rad")
        self.assertAlmostEqual(joint.getPlug("preferredAngle").get()[2], 90.0)
        with self.assertRaises(ValueError):
            joint.setPreferredAngle((1, 2))


class ConnectionDefaultTest(_SpecCase):
    """接続照会の既定は直結で、skipConversionNodes=Trueで変換ノードを飛ばす。"""

    def test_direct_by_default(self):
        """unitConversionを挟む接続で、既定は変換ノード、Trueは先のノードを返す。"""
        source = mlib.createNode("transform", name=self.name("drv"), skipSelect=True)
        target = mlib.createNode("transform", name=self.name("dst"), skipSelect=True)
        cmds.connectAttr(source.getFullName() + ".tx", target.getFullName() + ".rx")
        plug = target.getPlug("rx")
        self.assertEqual(plug.getSource().getNode().getType(), "unitConversion")
        self.assertEqual(plug.getSource(skipConversionNodes=True).getNode(), source)
        self.assertEqual(plug.getConnections(destination=False, asNode=True)[0].getType(), "unitConversion")
        self.assertEqual(plug.getConnections(destination=False, asNode=True, scn=True), [source])
        self.assertEqual(source.getPlug("tx").getDestinations(skipConversionNodes=True), [plug])


if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=2).result
    sys.exit(0 if result.wasSuccessful() else 1)

"""6.1.0 で fast を足した書込みメソッドの約束を固定する。

対象は ``Mesh.setPoints``・``NurbsCurve.setCvPositions``(周期カーブを含む)・``Shape.scaleGeometry`` の
周期カーブ・``DagNode.setColor``・``Nodes.setColor``・``BoolPlug.toggle``・``SkinCluster.pruneWeights``・
``DrivenKey.setKey``。各メソッドで、fast=True が通常経路と同じ結果になること、Undo キューへ何も
記録しないこと、fast が bool 以外なら TypeError、未対応・書込み不可は変更前に拒否することを確かめる。
"""

import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.drivenKey import DrivenKey
from mlib.nodes import Nodes
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、比較・Undo確認の補助。"""

    PREFIX = "mlibSpecFastWriters_"

    def assert_points(self, actual, expected, places=6):
        """点列が成分ごとに一致することを確かめる。"""
        self.assertEqual(len(actual), len(expected))
        for left, right in zip(actual, expected):
            for a, b in zip(left, right):
                self.assertAlmostEqual(a, b, places=places)

    def assert_no_undo(self, action):
        """flush後にactionを実行し、Undoキューが空のままであることを確かめる。"""
        cmds.flushUndo()
        result = action()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True),
                        cmds.undoInfo(query=True, undoName=True))
        return result

    def cube(self, name, history=False):
        """名前空間内に立方体を作り、そのMeshを返す。"""
        transform = cmds.polyCube(name=self.ns + ":" + name, constructionHistory=history)[0]
        return mlib.getNode(transform).getShape()

    def circle(self, name):
        """名前空間内に履歴なしの周期カーブを作り、そのNurbsCurveを返す。"""
        transform = cmds.circle(name=self.ns + ":" + name, constructionHistory=False, sections=8)[0]
        return mlib.getNode(transform).getShape()


class MeshSetPointsFastTest(_SpecCase):
    """Mesh.setPointsのfastは通常と同じ位置を書き、Undoに記録しない。"""

    def test_matches_normal(self):
        """ローカル・ワールドの両方で、通常とfastの結果が一致する。"""
        for worldSpace in (False, True):
            with self.subTest(worldSpace=worldSpace):
                normal, fast = self.cube("normal"), self.cube("fast")
                for shape in (normal, fast):
                    cmds.xform(shape.getParent().getFullName(), translation=(1, 2, 3), rotation=(10, 20, 30))
                points = [(i * 0.5, i * 0.25, -i) for i in range(8)]
                normal.setPoints(points, worldSpace=worldSpace)
                self.assert_no_undo(lambda: fast.setPoints(points, worldSpace=worldSpace, fast=True))
                self.assert_points(fast.getPoints(worldSpace=worldSpace), normal.getPoints(worldSpace=worldSpace))
                cmds.delete(normal.getParent().getFullName(), fast.getParent().getFullName())

    def test_rejections_before_change(self):
        """履歴のあるMeshはNotImplementedError、fastがbool以外はTypeErrorで、位置を変えない。"""
        shape = self.cube("history", history=True)
        before = shape.getPoints()
        moved = [point * 2 for point in before]
        with self.assertRaises(NotImplementedError):
            shape.setPoints(moved, fast=True)
        self.assert_points(shape.getPoints(), before)
        with self.assertRaises(TypeError):
            shape.setPoints(moved, fast=1)
        self.assert_points(shape.getPoints(), before)


class NurbsCurveSetCvPositionsFastTest(_SpecCase):
    """NurbsCurve.setCvPositionsのfastは周期カーブでも通常と同じ位置を書く。"""

    def test_periodic_matches_normal(self):
        """独立CVだけの点列・重複CVを含む点列のどちらも、通常とfastが一致し、重複CVが揃う。"""
        for overlap in (False, True):
            with self.subTest(overlap=overlap):
                normal, fast = self.circle("normal"), self.circle("fast")
                count = len(normal.getCvPositions()) - normal.getDegree()
                points = [(i, i * 0.5, 1.0) for i in range(count)]
                if overlap:
                    points += points[:normal.getDegree()]
                normal.setCvPositions(points)
                self.assert_no_undo(lambda: fast.setCvPositions(points, fast=True))
                self.assert_points(fast.getCvPositions(), normal.getCvPositions())
                cmds.delete(normal.getParent().getFullName(), fast.getParent().getFullName())

    def test_open_curve_world_space(self):
        """開いたカーブのワールド空間指定も通常と一致する。"""
        names = [cmds.curve(name=self.ns + ":" + name, degree=1, point=[(0, 0, 0), (1, 0, 0), (2, 1, 0)])
                 for name in ("normal", "fast")]
        normal, fast = (mlib.getNode(name).getShape() for name in names)
        for name in names:
            cmds.xform(name, translation=(0, 3, 0), scale=(2, 2, 2))
        points = [(0, 1, 0), (1, 1, 0), (2, 2, 0)]
        normal.setCvPositions(points, worldSpace=True)
        self.assert_no_undo(lambda: fast.setCvPositions(points, worldSpace=True, fast=True))
        self.assert_points(fast.getCvPositions(worldSpace=True), normal.getCvPositions(worldSpace=True))


class DagNodeSetColorFastTest(_SpecCase):
    """DagNode.setColor・Nodes.setColorのfastは通常と同じアトリビュートを書く。"""

    ATTRIBUTES = ("overrideEnabled", "overrideRGBColors", "overrideColor", "overrideColorRGB")

    def colors(self, shape):
        """表示色のアトリビュートの値を返す。"""
        return [cmds.getAttr(shape + "." + name) for name in self.ATTRIBUTES]

    def test_matches_normal(self):
        """インデックス・RGBの両方で、Transform配下のShapeと、Shapeの無いTransformが通常と一致する。"""
        for color in (13, (1.0, 0.5, 0.0)):
            with self.subTest(color=color):
                normal = mlib.getNode(cmds.circle(name=self.ns + ":normal", constructionHistory=False)[0])
                fast = mlib.getNode(cmds.circle(name=self.ns + ":fast", constructionHistory=False)[0])
                group = mlib.getNode(cmds.createNode("transform", name=self.ns + ":group"))
                normal.setColor(color)
                self.assert_no_undo(lambda: fast.setColor(color, fast=True))
                self.assertEqual(self.colors(fast.getShape().getFullName()),
                                 self.colors(normal.getShape().getFullName()))
                self.assert_no_undo(lambda: Nodes([group]).setColor(color, fast=True))
                self.assertTrue(cmds.getAttr(group.getFullName() + ".overrideEnabled"))
                cmds.delete(normal.getFullName(), fast.getFullName(), group.getFullName())

    def test_locked_attribute_rejects_before_change(self):
        """ロックされたアトリビュートがあれば、他のアトリビュートも書かずにRuntimeError。"""
        node = mlib.getNode(cmds.circle(name=self.ns + ":locked", constructionHistory=False)[0])
        shape = node.getShape().getFullName()
        cmds.setAttr(shape + ".overrideColor", lock=True)
        with self.assertRaises(RuntimeError):
            node.setColor(13, fast=True)
        self.assertFalse(cmds.getAttr(shape + ".overrideEnabled"))
        with self.assertRaises(TypeError):
            node.setColor(13, fast="yes")


class BoolPlugToggleFastTest(_SpecCase):
    """BoolPlug.toggleのfastは値を反転し、Undoに記録しない。"""

    def test_toggle(self):
        """fastでも反転し、fastがbool以外ならTypeError。"""
        node = cmds.createNode("transform", name=self.ns + ":node")
        plug = mlib.getPlug(node + ".visibility")
        self.assert_no_undo(lambda: plug.toggle(fast=True))
        self.assertFalse(cmds.getAttr(node + ".visibility"))
        plug.toggle()
        self.assertTrue(cmds.getAttr(node + ".visibility"))
        with self.assertRaises(TypeError):
            plug.toggle(fast=1)


class SkinClusterPruneWeightsFastTest(_SpecCase):
    """SkinCluster.pruneWeightsのfastは通常と同じウェイトを書き、Undoに記録しない。"""

    def skin(self, name):
        """名前空間内にジョイント3本でバインドした球を作り、SkinClusterを返す。"""
        mesh = cmds.polySphere(name=self.ns + ":" + name, subdivisionsX=12, subdivisionsY=8,
                               constructionHistory=False)[0]
        cmds.select(clear=True)
        joints = [cmds.joint(name=self.ns + ":" + name + "J%d" % i, position=(0, i - 1, 0)) for i in range(3)]
        return mlib.getNode(cmds.skinCluster(joints, mesh, toSelectedBones=True, maximumInfluences=3)[0])

    def test_matches_normal(self):
        """normalizeの有無とも、通常とfastで全頂点のウェイトが一致する。"""
        for normalize in (True, False):
            with self.subTest(normalize=normalize):
                normal, fast = self.skin("normal"), self.skin("fast")
                normal.pruneWeights(0.3, normalize=normalize)
                self.assert_no_undo(lambda: fast.pruneWeights(0.3, normalize=normalize, fast=True))
                self.assertEqual(len(fast.getWeights(fast.getInfluences())), len(normal.getWeights(normal.getInfluences())))
                for a, b in zip(fast.getWeights(fast.getInfluences()), normal.getWeights(normal.getInfluences())):
                    self.assertAlmostEqual(a, b, places=9)
        with self.assertRaises(TypeError):
            fast.pruneWeights(0.3, fast=None)


class DrivenKeySetKeyFastTest(_SpecCase):
    """DrivenKey.setKeyのfastは、setDrivenKeyframeと同じカーブ・キー・接続を作る。"""

    def setUp(self):
        super().setUp()
        self.namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        # 作るカーブを名前空間に入れ、tearDownで一緒に消す。
        cmds.namespace(setNamespace=":" + self.ns)

    def tearDown(self):
        cmds.namespace(setNamespace=self.namespace)
        super().tearDown()

    def build(self, fast, pairs):
        """ドライバー・駆動先の組ごとに4回キーを打ち、カーブの情報と評価値を返す。

        キーを打つ部分だけをUndoの確認対象にする(ノードの作成・評価値の確認は通常経路)。
        """
        driver = cmds.createNode("transform", name="driver")
        driven = cmds.createNode("transform", name="driven")
        cmds.addAttr(driver, longName="amount", attributeType="double", keyable=True)
        keys = [DrivenKey(driver + "." + source, driven + "." + target) for source, target in pairs]

        def set_keys():
            for key in keys:
                for driverValue, value in ((0, 0), (10, 5), (-4, 2), (10, 7)):
                    key.setKey(driverValue, value, fast=fast)

        if fast:
            self.assert_no_undo(set_keys)
        else:
            set_keys()
        results = []
        for key, (source, target) in zip(keys, pairs):
            curve = key.getCurves()[0]
            values = []
            for driverValue in (-6, 0, 3, 10, 20):
                mlib.getPlug(driver + "." + source).set(driverValue)
                values.append(round(mlib.getPlug(driven + "." + target).get(), 6))
            results.append((curve.getType(), curve.getName().rpartition(":")[2],
                            cmds.keyframe(curve.getFullName(), query=True, floatChange=True),
                            cmds.keyframe(curve.getFullName(), query=True, valueChange=True),
                            cmds.keyTangent(curve.getFullName(), query=True, inTangentType=True), values))
        cmds.delete(driver, driven, [key.getCurves()[0].getFullName() for key in keys])
        return results

    def test_matches_normal(self):
        """距離・角度・無次元の組合せと、UI単位がmmの場合で、通常とfastが一致する。"""
        pairs = (("rotateX", "translateY"), ("translateX", "rotateZ"), ("amount", "scaleX"), ("amount", "translateX"))
        for linear in ("cm", "mm"):
            with self.subTest(linear=linear):
                cmds.currentUnit(linear=linear)
                normal = self.build(False, pairs)
                fast = self.build(True, pairs)
                self.assertEqual(fast, normal)

    def test_second_driver_is_rejected_before_change(self):
        """別のドライバーのカーブがある駆動先はNotImplementedErrorで、ノードを作らない。"""
        driver = cmds.createNode("transform", name="driver")
        driven = cmds.createNode("transform", name="driven")
        DrivenKey(driver + ".translateX", driven + ".translateY").setKey(0, 0)
        before = set(cmds.ls(type="animCurve"))
        with self.assertRaises(NotImplementedError):
            DrivenKey(driver + ".translateZ", driven + ".translateY").setKey(0, 0, fast=True)
        self.assertEqual(set(cmds.ls(type="animCurve")), before)
        with self.assertRaises(ValueError):
            DrivenKey(driver + ".translateZ", driven + ".translateX").setKey(0, 0, "fixed", fast=True)
        self.assertEqual(set(cmds.ls(type="animCurve")), before)
        with self.assertRaises(TypeError):
            DrivenKey(driver + ".translateZ", driven + ".translateX").setKey(0, 0, fast=0)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

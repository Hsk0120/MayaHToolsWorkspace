"""nodes のメソッド(aimConstraint〜mesh)の docstring の Raises に書かれた例外を確かめる。

各メソッドについて、Raises の各例外が実際に起きる入力を作って ``assertRaises`` で確かめ、
書込み系は例外の後にシーン(値・接続・メンバー・ファイル)が変わっていないことも確かめる。
docstring と実際の挙動が食い違う項目はここでは固定しない(本体または docstring の修正待ち)。
"""

import os
import shutil
import sys
import tempfile
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


class _ErrorCase(NamespaceCase):
    """削除済みノードの作成など、各テストで共通の補助を持つ。"""

    PREFIX = "mlibSpecErrNodesA_"
    CLEAR_SELECTION = True

    def dead(self, kind):
        """名前空間に作ってすぐ削除したノードのラッパーを返す(無効なノードの確認用)。"""
        node = mlib.getNode(self.make(kind))
        cmds.delete(node.getFullName())
        self.assertFalse(node.isValid())
        return node

    def cube(self, text):
        """履歴なしの polyCube を作り、transform の名前を返す。"""
        return cmds.polyCube(name=self.name(text), constructionHistory=False)[0]

    def joints(self, *names):
        """名前の順に親子にした joint を作り、名前を返す。"""
        cmds.select(clear=True)
        result = [cmds.joint(name=self.name(name), position=(0, i, 0)) for i, name in enumerate(names)]
        cmds.select(clear=True)
        return result


class AngleUnitArgumentTest(_ErrorCase):
    """AimConstraint.getRestRotate・getOffset の unit の検証。"""

    def test_unit_type_and_name(self):
        aim = mlib.getNode(self.make("aimConstraint"))
        for method in ("getRestRotate", "getOffset"):
            with self.subTest(method=method):
                self.assertEqual(len(getattr(aim, method)(unit="rad")), 3)
                for unit in (1, 1.0, ["deg"]):
                    with self.assertRaises(TypeError):
                        getattr(aim, method)(unit=unit)
                for unit in ("grad", "", "DEG?"):
                    with self.assertRaises(ValueError):
                        getattr(aim, method)(unit=unit)


class EnumSetterTest(_ErrorCase):
    """AimMatrix.setPrimaryMode/setSecondaryMode と ComposeMatrix/DecomposeMatrix.setRotateOrder。"""

    CASES = (
        ("aimMatrix", "setPrimaryMode", "primaryMode", 3),
        ("aimMatrix", "setSecondaryMode", "secondaryMode", 3),
        ("composeMatrix", "setRotateOrder", "inputRotateOrder", 6),
        ("decomposeMatrix", "setRotateOrder", "inputRotateOrder", 6),
    )

    def test_invalid_values_do_not_change_the_attribute(self):
        for kind, method, attribute, count in self.CASES:
            node = mlib.getNode(self.make(kind))
            plug = node.getFullName() + "." + attribute
            before = cmds.getAttr(plug)
            for value in (1.5, True, None, [0]):
                with self.subTest(kind=kind, method=method, value=value):
                    with self.assertRaises(TypeError):
                        getattr(node, method)(value)
                    self.assertEqual(cmds.getAttr(plug), before)
            for value in ("bad", "", count, -1, 99):
                with self.subTest(kind=kind, method=method, value=value):
                    with self.assertRaises(ValueError):
                        getattr(node, method)(value)
                    self.assertEqual(cmds.getAttr(plug), before)

    def test_invalid_node_and_locked_attribute(self):
        for kind, method, attribute, count in self.CASES:
            with self.subTest(kind=kind, method=method, case="dead"):
                with self.assertRaises(RuntimeError):
                    getattr(self.dead(kind), method)(1)
            with self.subTest(kind=kind, method=method, case="locked"):
                node = mlib.getNode(self.make(kind))
                plug = node.getFullName() + "." + attribute
                before = cmds.getAttr(plug)
                cmds.setAttr(plug, lock=True)
                with self.assertRaises(RuntimeError):
                    getattr(node, method)(count - 1)
                self.assertEqual(cmds.getAttr(plug), before)
                cmds.setAttr(plug, lock=False)

    def test_name_and_index_set_the_same_value(self):
        node = mlib.getNode(self.make("aimMatrix"))
        self.assertIs(node.setPrimaryMode("align"), node)
        self.assertEqual(cmds.getAttr(node.getFullName() + ".primaryMode"), 2)
        node.setSecondaryMode(1)
        self.assertEqual(cmds.getAttr(node.getFullName() + ".secondaryMode"), 1)


class OutputPlugKindTest(_ErrorCase):
    """AngleBetween/DecomposeMatrix.getOutputPlug の kind の検証。"""

    def test_unknown_kind(self):
        for kind, valid in (("angleBetween", ("angle", "axis", "euler")),
                            ("decomposeMatrix", ("translate", "rotate", "scale", "shear", "quaternion"))):
            node = mlib.getNode(self.make(kind))
            for name in valid:
                with self.subTest(kind=kind, name=name):
                    plug = node.getOutputPlug(name)
                    self.assertTrue(cmds.objExists(str(plug)))
            for name in ("bad", "", "Angle", 1):
                with self.subTest(kind=kind, name=name):
                    with self.assertRaises(ValueError):
                        node.getOutputPlug(name)


class AnimCurveErrorTest(_ErrorCase):
    """AnimCurve.getKeyValues・evaluate・getTangent・getDrivenPlugs。"""

    def setUp(self):
        super().setUp()
        self.target = self.make("transform", "animated")
        cmds.setKeyframe(self.target, attribute="rx", time=1, value=10)
        cmds.setKeyframe(self.target, attribute="rx", time=10, value=20)
        self.curve = mlib.getNode(cmds.listConnections(self.target + ".rx", source=True, destination=False)[0])
        self.assertEqual(self.curve.getKeyCount(), 2)

    def test_unit_arguments(self):
        calls = (("getKeyValues", lambda **kw: self.curve.getKeyValues(**kw)),
                 ("evaluate", lambda **kw: self.curve.evaluate(5, **kw)),
                 ("getTangent", lambda **kw: self.curve.getTangent(0, **kw)))
        for name, call in calls:
            with self.subTest(method=name, flag="unit"):
                with self.assertRaises(TypeError):
                    call(unit=1)
                with self.assertRaises(ValueError):
                    call(unit="grad")
            if name == "getTangent":
                continue  # getTangent は timeUnit を持たない
            with self.subTest(method=name, flag="timeUnit"):
                with self.assertRaises(TypeError):
                    call(timeUnit=1)
                with self.assertRaises(ValueError):
                    call(timeUnit="minute")

    def test_evaluate_input(self):
        time = cmds.currentTime(query=True)
        for value in (object(), None, [1]):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    self.curve.evaluate(value)
        for value in ("abc", float("inf"), float("-inf"), float("nan")):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.curve.evaluate(value)
        self.assertAlmostEqual(self.curve.evaluate(1), 10.0)
        self.assertAlmostEqual(self.curve.evaluate("10"), 20.0)
        # 評価しても現在時刻は変わらない。
        self.assertEqual(cmds.currentTime(query=True), time)

    def test_evaluate_empty_curve_rejected_before_input_conversion(self):
        empty = mlib.createNode("animCurveTL", name=self.name("empty"))
        with self.assertRaises(RuntimeError):
            empty.evaluate(1)
        # 空カーブは入力変換より先に拒否する(変換できない入力でも RuntimeError)。
        with self.assertRaises(RuntimeError):
            empty.evaluate(object())

    def test_get_tangent_index(self):
        for index in (True, False, 1.0, "0", -1, 2, 99):
            with self.subTest(index=index):
                with self.assertRaises(IndexError):
                    self.curve.getTangent(index)
        info = self.curve.getTangent(1)
        self.assertEqual(info["inTangentType"], cmds.keyTangent(self.curve.getFullName(), query=True,
                                                                 index=(1, 1), inTangentType=True)[0])

    def test_get_driven_plugs(self):
        plugs = self.curve.getDrivenPlugs()
        self.assertEqual([plug.getFullName() for plug in plugs],
                         [mlib.getPlug(self.target + ".rx").getFullName()])
        self.assertEqual(mlib.createNode("animCurveTL", name=self.name("free")).getDrivenPlugs(), [])
        with self.assertRaises(RuntimeError):
            self.dead("animCurveTL").getDrivenPlugs()


class BlendShapeErrorTest(_ErrorCase):
    """BlendShape.getBaseGeometry・getInBetweenWeights・reduceTargetDeltas・getTargetsData・exportTargets。"""

    def setUp(self):
        super().setUp()
        self.base = self.cube("base")
        self.target = self.cube("target")
        cmds.move(0, 1, 0, self.target + ".vtx[0]", relative=True)
        self.bs = mlib.getNode(cmds.blendShape(self.target, self.base, name=self.name("bs"))[0])
        self.item = self.bs.getFullName() + ".inputTarget[0].inputTargetGroup[0].inputTargetItem[6000]"
        self.directory = tempfile.mkdtemp(prefix="mlibSpecErrNodesA_")

    def tearDown(self):
        shutil.rmtree(self.directory, ignore_errors=True)
        super().tearDown()

    def curve_blend_shape(self):
        """カーブをベースにした blendShape(メッシュでないベース)を作る。"""
        points = [(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)]
        base = cmds.curve(point=points, name=self.name("curveBase"))
        target = cmds.curve(point=[(0, 1, 0)] + points[1:], name=self.name("curveTarget"))
        return mlib.getNode(cmds.blendShape(target, base, name=self.name("curveBs"))[0])

    def item_state(self):
        """項目のデルタと、ターゲット形状の接続をまとめる。"""
        deltas = {vertex: tuple(round(v, 6) for v in delta)
                  for vertex, delta in self.bs.getTargetDeltas(0).items()}
        source = cmds.listConnections(self.item + ".inputGeomTarget", source=True, destination=False)
        return deltas, source

    def test_get_base_geometry(self):
        shape = cmds.listRelatives(self.base, shapes=True, fullPath=True)[0]
        self.assertEqual([node.getFullName() for node in self.bs.getBaseGeometry()], [shape])
        with self.assertRaises(RuntimeError):
            self.dead_blend_shape().getBaseGeometry()

    def dead_blend_shape(self):
        node = mlib.getNode(cmds.blendShape(self.cube("deadBase"), name=self.name("deadBs"))[0])
        cmds.delete(node.getFullName())
        return node

    def test_get_in_between_weights(self):
        between = self.cube("between")
        cmds.blendShape(self.bs.getFullName(), edit=True, inBetween=True, target=(self.base, 0, between, 0.5))
        self.assertEqual(self.bs.getInBetweenWeights(0), [0.5])
        for target in (1.5, None, True, [0]):
            with self.subTest(target=target):
                with self.assertRaises(TypeError):
                    self.bs.getInBetweenWeights(target)
        with self.subTest(base=1):
            with self.assertRaises(TypeError):
                self.bs.getInBetweenWeights(0, base=1)
        for target in ("missing", 9):
            with self.subTest(target=target):
                with self.assertRaises(ValueError):
                    self.bs.getInBetweenWeights(target)
        with self.subTest(base="other"):
            with self.assertRaises(ValueError):
                self.bs.getInBetweenWeights(0, base=self.cube("other"))

    def test_reduce_target_deltas_invalid_arguments(self):
        before = self.item_state()
        type_errors = (dict(tolerance="a"), dict(disconnect=1), dict(fast=1), dict(target=1.5))
        value_errors = (dict(tolerance=-1), dict(tolerance=float("inf")), dict(tolerance=float("nan")),
                        dict(target="missing"), dict(fullWeight=0.5))
        for flags, error in [(f, TypeError) for f in type_errors] + [(f, ValueError) for f in value_errors]:
            flags = dict(flags)
            target = flags.pop("target", 0)
            with self.subTest(flags=flags, target=target):
                with self.assertRaises(error):
                    self.bs.reduceTargetDeltas(target, **flags)
                self.assertEqual(self.item_state(), before)

    def test_reduce_target_deltas_connected_target(self):
        before = self.item_state()
        self.assertEqual(before[0].keys(), {0})
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(RuntimeError):
                    self.bs.reduceTargetDeltas(0, tolerance=10.0, fast=fast)
                self.assertEqual(self.item_state(), before)
        # disconnect=True なら接続を切ってから取り除く。
        self.bs.reduceTargetDeltas(0, tolerance=10.0, disconnect=True)
        self.assertEqual(self.item_state(), ({}, None))

    def test_targets_data_requires_mesh_bases(self):
        data = self.bs.getTargetsData()
        self.assertEqual(sorted(data), ["bases", "blendShape", "folders", "targets"])
        curve_bs = self.curve_blend_shape()
        with self.assertRaises(TypeError):
            curve_bs.getTargetsData()
        with self.assertRaises(RuntimeError):
            self.dead_blend_shape().getTargetsData()

    def test_export_targets_errors(self):
        path = os.path.join(self.directory, "targets.json")
        with self.assertRaises(TypeError):
            self.curve_blend_shape().exportTargets(path)
        self.assertFalse(os.path.exists(path))
        missing = os.path.join(self.directory, "no_such_dir", "targets.json")
        with self.assertRaises(OSError):
            self.bs.exportTargets(missing)
        self.assertFalse(os.path.exists(os.path.dirname(missing)))
        written = self.bs.exportTargets(path)
        self.assertTrue(written.is_file())


class DagNodeInvalidTest(_ErrorCase):
    """DagNode の照会メソッドが、削除済みのノード・取り除いたインスタンスで RuntimeError になること。"""

    DELETED = ("getBindPoses", "mpath", "getRoot", "isIntermediateObject", "getInstances", "getParents",
               "isVisible", "getOverrideColor", "getOutlinerVisibility", "getDisplayType",
               "isShadingOverridden", "getSkinClusters")
    REMOVED_INSTANCE = ("getBindPoses", "mpath", "getRoot", "getSiblings", "isIntermediateObject",
                        "getInstances", "getParents", "isVisible", "getSkinClusters")

    def test_deleted_node(self):
        node = self.dead("transform")
        for method in self.DELETED:
            with self.subTest(method=method):
                with self.assertRaises(RuntimeError):
                    getattr(node, method)()
        # getSiblings は無効なノードでは空リストを返す(docstring の記載どおり)。
        self.assertEqual(node.getSiblings(), [])

    def test_removed_instance_path(self):
        first, second = self.make("transform", "first"), self.make("transform", "second")
        child = self.make("transform", "child", parent=first)
        cmds.parent(child, second, addObject=True)
        instance = [node for node in mlib.getNode(child).getInstances()
                    if node.getFullName().startswith(cmds.ls(second, long=True)[0] + "|")][0]
        cmds.parent(instance.getFullName(), removeObject=True)
        # ノード自体は残り、保持するパスだけが無効になる。
        self.assertTrue(instance.isValid())
        for method in self.REMOVED_INSTANCE:
            with self.subTest(method=method):
                with self.assertRaises(RuntimeError):
                    getattr(instance, method)()

    def test_get_override_color_shape_flag(self):
        node = mlib.getNode(self.make("transform"))
        for value in (1, 0, None, "true"):
            with self.subTest(shape=value):
                with self.assertRaises(TypeError):
                    node.getOverrideColor(shape=value)
        self.assertIsNone(node.getOverrideColor(shape=True))

    def test_get_bind_poses_with_invalid_connection(self):
        joint, = self.joints("bindJoint")
        cube = self.cube("skinned")
        skin = mlib.getNode(cmds.skinCluster(joint, cube, name=self.name("skin"))[0])
        pose = skin.getBindPose()
        self.assertEqual(mlib.getNode(cube).getBindPoses(), [pose])
        cmds.disconnectAttr(pose.getFullName() + ".message", skin.getFullName() + ".bindPose")
        cmds.connectAttr(self.make("network", "fakePose") + ".message", skin.getFullName() + ".bindPose")
        for name in (cube, joint):
            with self.subTest(node=name):
                with self.assertRaises(RuntimeError):
                    mlib.getNode(name).getBindPoses()


class DagPoseErrorTest(_ErrorCase):
    """DagPose の照会と addMembers。"""

    def setUp(self):
        super().setUp()
        self.root, self.tip = self.joints("root", "tip")
        cmds.select(clear=True)
        self.free, = self.joints("free")
        pose = cmds.dagPose(self.root, self.tip, save=True, selection=True)
        self.pose = mlib.getNode(cmds.rename(pose, self.name("pose")))

    def members(self):
        return [node.getFullName() for node in self.pose.getMembers()]

    def test_queries_on_deleted_pose(self):
        pose = mlib.getNode(cmds.rename(cmds.dagPose(self.root, save=True, selection=True), self.name("gone")))
        cmds.delete(pose.getFullName())
        for method in ("getNotAtPose", "isAtPose", "getSkinClusters", "isBindPose", "getMemberIndices",
                       "getMembers"):
            with self.subTest(method=method):
                with self.assertRaises(RuntimeError):
                    getattr(pose, method)()
        with self.assertRaises(RuntimeError):
            pose.addMembers(self.free)

    def test_add_members_invalid_input_keeps_members(self):
        before = self.members()
        shape = cmds.listRelatives(self.cube("mesh"), shapes=True, fullPath=True)[0]
        cases = ((TypeError, (1,)), (TypeError, (None,)), (TypeError, ([self.free, 1.5],)),
                 (ValueError, ()), (ValueError, ([],)), (ValueError, (shape,)),
                 (ValueError, (self.free, "time1")),
                 (RuntimeError, (self.name("missing"),)))
        for error, members in cases:
            with self.subTest(error=error.__name__, members=members):
                with self.assertRaises(error):
                    self.pose.addMembers(*members)
                self.assertEqual(self.members(), before)
        self.pose.addMembers(self.free)
        self.assertEqual(self.members(), before + [cmds.ls(self.free, long=True)[0]])


class GeometryFilterWeightTest(_ErrorCase):
    """GeometryFilter.getDeformerWeights・setDeformerWeights。"""

    def setUp(self):
        super().setUp()
        self.mesh = self.cube("mesh")
        self.cluster = mlib.getNode(cmds.cluster(self.mesh, name=self.name("cluster"))[0])
        self.cluster.setDeformerWeights([0.5] * 8)

    def test_get_errors(self):
        self.assertEqual(self.cluster.getDeformerWeights(), [0.5] * 8)
        for value in (1.0, True, "0", None):
            with self.subTest(geometryIndex=value):
                with self.assertRaises(TypeError):
                    self.cluster.getDeformerWeights(value)
        for value in (1, 5, -1):
            with self.subTest(geometryIndex=value):
                with self.assertRaises(IndexError):
                    self.cluster.getDeformerWeights(value)

    def test_skin_cluster_has_no_deformer_weights(self):
        joint, = self.joints("joint")
        skin = mlib.getNode(cmds.skinCluster(joint, self.cube("skinned"), name=self.name("skin"))[0])
        with self.assertRaises(TypeError):
            skin.getDeformerWeights()
        with self.assertRaises(TypeError):
            skin.setDeformerWeights([1.0] * 8)

    def test_set_invalid_arguments_keep_weights(self):
        cases = (
            (TypeError, dict(weights=[1.0] * 8, fast=1)),
            (TypeError, dict(weights=[1.0] * 8, geometryIndex=1.0)),
            (TypeError, dict(weights=["a"] * 8)),
            (TypeError, dict(weights=[True] * 8)),
            (TypeError, dict(weights=[1.0], vertices=[1.0])),
            (ValueError, dict(weights=[1.0] * 3)),
            (ValueError, dict(weights=[float("nan")] * 8)),
            (ValueError, dict(weights=[1.0, 1.0], vertices=[1, 1])),
            (IndexError, dict(weights=[1.0] * 8, geometryIndex=5)),
            (IndexError, dict(weights=[1.0], vertices=[99])),
            (IndexError, dict(weights=[1.0], vertices=[-1])),
        )
        for fast in (False, True):
            for error, flags in cases:
                flags = dict(flags)
                flags.setdefault("fast", fast)
                with self.subTest(error=error.__name__, flags=flags):
                    with self.assertRaises(error):
                        self.cluster.setDeformerWeights(**flags)
                    self.assertEqual(self.cluster.getDeformerWeights(), [0.5] * 8)

    def test_set_locked_or_connected_attribute(self):
        weights = self.cluster.getFullName() + ".weightList[0].weights"
        cmds.setAttr(weights, lock=True)
        for fast in (False, True):
            with self.subTest(case="locked", fast=fast):
                with self.assertRaises(RuntimeError):
                    self.cluster.setDeformerWeights([0.2], vertices=[0], fast=fast)
                self.assertEqual(self.cluster.getDeformerWeights(), [0.5] * 8)
        cmds.setAttr(weights, lock=False)
        cmds.connectAttr(self.make("transform", "driver") + ".visibility", weights + "[1]")
        for fast in (False, True):
            with self.subTest(case="connected", fast=fast):
                with self.assertRaises(RuntimeError):
                    self.cluster.setDeformerWeights([0.2], vertices=[1], fast=fast)
                self.assertAlmostEqual(cmds.getAttr(weights + "[0]"), 0.5)


class IkHandleErrorTest(_ErrorCase):
    """IkHandle.getEffector・getCurve。"""

    def test_effector_and_curve(self):
        start, _, end = self.joints("a", "b", "c")
        cmds.setAttr(end + ".tz", 1)
        handle, effector = cmds.ikHandle(startJoint=start, endEffector=end, name=self.name("ik"))
        ik = mlib.getNode(handle)
        self.assertEqual(ik.getEffector().getFullName(), cmds.ls(effector, long=True)[0])
        self.assertIsNone(ik.getCurve())
        cmds.delete(handle)
        for method in ("getEffector", "getCurve"):
            with self.subTest(method=method):
                with self.assertRaises(RuntimeError):
                    getattr(ik, method)()


class JointDisconnectInverseScaleTest(_ErrorCase):
    """Joint.disconnectInverseScale。"""

    def setUp(self):
        super().setUp()
        self.parent, self.child = self.joints("parent", "child")
        self.joint = mlib.getNode(self.child)

    def source(self):
        return cmds.listConnections(self.child + ".inverseScale", source=True, destination=False)

    def test_errors_keep_connection(self):
        before = self.source()
        self.assertTrue(before)
        with self.assertRaises(TypeError):
            self.joint.disconnectInverseScale(fast=1)
        self.assertEqual(self.source(), before)
        cmds.setAttr(self.child + ".inverseScale", lock=True)
        for fast in (False, True):
            with self.subTest(case="locked", fast=fast):
                with self.assertRaises(RuntimeError):
                    self.joint.disconnectInverseScale(fast=fast)
                self.assertEqual(self.source(), before)
        cmds.setAttr(self.child + ".inverseScale", lock=False)
        dead = mlib.getNode(self.joints("gone")[0])
        cmds.delete(dead.getFullName())
        with self.assertRaises(RuntimeError):
            dead.disconnectInverseScale()
        self.assertIs(self.joint.disconnectInverseScale(), self.joint)
        self.assertIsNone(self.source())


class MeshClosestVertexTest(_ErrorCase):
    """Mesh.getClosestVertex。docstring と食い違う成分数の誤り・データの無いメッシュは扱わない。"""

    def setUp(self):
        super().setUp()
        self.mesh = mlib.getNode(cmds.listRelatives(self.cube("mesh"), shapes=True, fullPath=True)[0])

    def test_errors(self):
        self.assertEqual(self.mesh.getClosestVertex((0.5, 0.5, 0.5)).index, 3)
        for point in ("abc", object(), ("a", 0, 0)):
            with self.subTest(point=point):
                with self.assertRaises(TypeError):
                    self.mesh.getClosestVertex(point)
        for flags in (dict(worldSpace=1), dict(ws="yes"), dict(worldSpace=True, ws=True)):
            with self.subTest(flags=flags):
                with self.assertRaises(TypeError):
                    self.mesh.getClosestVertex((0, 0, 0), **flags)
        for point in ((float("nan"), 0, 0), (0, float("inf"), 0)):
            with self.subTest(point=point):
                with self.assertRaises(ValueError):
                    self.mesh.getClosestVertex(point)

    def test_mesh_without_vertices(self):
        parent = om2.MSelectionList().add(self.make("transform", "emptyMesh")).getDependNode(0)
        shape = om2.MFnMesh().create([], [], [], parent=parent)
        empty = mlib.getNode(om2.MFnDagNode(shape).fullPathName())
        with self.assertRaises(ValueError):
            empty.getClosestVertex((0, 0, 0))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

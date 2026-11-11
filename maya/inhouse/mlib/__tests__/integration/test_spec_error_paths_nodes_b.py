"""ノードのクラス(Mesh・Node・Nodes・NurbsCurve・ObjectSet・計算ノード・Reference・ShadingEngine・
SkinCluster・Transform)の公開メソッドについて、docstring の Raises に書かれた例外を確かめる。

各テストは Raises に書かれた入力を作って ``assertRaises`` で例外の型を確かめ、可能なものは例外の後に
シーンが変わっていないこと(ノードが増えない・値や接続が戻る・ファイルが残らない)も確かめる。
docstring と実際の挙動が食い違う項目はここでは確かめず、別途の記録に回している。
"""

import math
import os
import shutil
import tempfile
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    """名前空間にノードを作る補助。"""

    PREFIX = "mlibErrNodesB_"
    CLEAR_SELECTION = True

    def node(self, node_type, text=None, **flags):
        """mlib.createNode で名前空間にノードを作る。"""
        return mlib.createNode(node_type, name=self.name(text or node_type + "#"), **flags)

    def deleted(self, node_type="transform", flush=False):
        """作ってすぐ削除したノードのラッパーを返す。flush=True なら Undo の記録も消す。"""
        node = self.node(node_type)
        cmds.delete(node.getFullName())
        if flush:
            cmds.flushUndo()
        return node

    def namespace_nodes(self):
        """名前空間にあるノードの名前の集合。"""
        return set(cmds.ls(self.ns + ":*", long=True) or [])

    def temp_dir(self):
        """テスト終了時に消える一時フォルダーを返す。"""
        path = tempfile.mkdtemp(prefix="mlibErrNodesB_")
        self.addCleanup(shutil.rmtree, path, True)
        return path

    def track_outside_nodes(self):
        """以後に名前空間の外へできたノード(bindPose 等)を、テスト終了時に削除する。"""
        before = set(cmds.ls(long=True))

        def cleanup():
            created = [name for name in set(cmds.ls(long=True)) - before
                       if cmds.objExists(name) and not cmds.ls(name, readOnly=True)]
            for name in created:
                if cmds.objExists(name):
                    cmds.delete(name)

        self.addCleanup(cleanup)


class MeshErrorTest(_Case):
    """Mesh の最近点・法線と UV セットの操作。"""

    def cube(self):
        transform = cmds.polyCube(name=self.name("cube#"), constructionHistory=False)[0]
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def faceless(self):
        """頂点だけで面の無いメッシュを om2 で作る。"""
        parent = om2.MFnDagNode().create("transform", self.name("noFace"))
        points = [om2.MPoint(0, 0, 0), om2.MPoint(1, 0, 0), om2.MPoint(0, 1, 0)]
        shape = om2.MFnMesh().create(points, [], [], parent=parent)
        return mlib.getNode(om2.MFnDagNode(shape).fullPathName())

    def test_closest_point_and_normal_reject_invalid_input(self):
        """点が文字列・非シーケンスは TypeError、成分が有限でない・面の無いメッシュは ValueError、worldSpace が bool 以外は TypeError。"""
        mesh = self.cube()
        faceless = self.faceless()
        for method in ("getClosestPoint", "getClosestNormal"):
            call = getattr(mesh, method)
            with self.subTest(method=method, case="str"):
                self.assertRaises(TypeError, call, "abc")
            with self.subTest(method=method, case="object"):
                self.assertRaises(TypeError, call, object())
            with self.subTest(method=method, case="nan"):
                self.assertRaises(ValueError, call, (float("nan"), 0, 0))
            with self.subTest(method=method, case="inf"):
                self.assertRaises(ValueError, call, (0, float("inf"), 0))
            with self.subTest(method=method, case="worldSpace"):
                self.assertRaises(TypeError, call, (0, 0, 0), worldSpace=1)
                self.assertRaises(TypeError, call, (0, 0, 0), ws="yes")
            with self.subTest(method=method, case="both aliases"):
                self.assertRaises(TypeError, call, (0, 0, 0), worldSpace=True, ws=True)
            with self.subTest(method=method, case="no faces"):
                self.assertRaises(ValueError, getattr(faceless, method), (0, 0, 0))

    def test_closest_point_and_normal_component_count_and_empty_shape(self):
        """成分の数が3でない点は ValueError、形状データを持たない空のシェイプは RuntimeError。"""
        mesh = self.cube()
        empty = self.node("mesh")
        for method in ("getClosestPoint", "getClosestNormal"):
            call = getattr(mesh, method)
            for point in ((1, 2), (1, 2, 3, 4)):
                with self.subTest(method=method, point=point):
                    self.assertRaises(ValueError, call, point)
            with self.subTest(method=method, case="empty shape"):
                self.assertRaises(RuntimeError, getattr(empty, method), (0, 0, 0))

    def test_closest_normal_on_cube_face(self):
        """正常系: 立方体の +X 面の外の点では、+X 方向の法線になる。"""
        normal = self.cube().getClosestNormal((2, 0.1, 0.1))
        self.assertSequenceAlmostEqual(normal, (1, 0, 0), places=6)

    def assertUVSets(self, mesh, expected, current="map1"):
        self.assertEqual(cmds.polyUVSet(mesh.getFullName(), query=True, allUVSets=True), expected)
        self.assertEqual(cmds.polyUVSet(mesh.getFullName(), query=True, currentUVSet=True), [current])

    def test_set_current_uv_set_errors(self):
        """name が文字列以外は TypeError、空・存在しない名前は ValueError。UV セットは変わらない。"""
        mesh = self.cube()
        cases = ((TypeError, 5), (TypeError, None), (ValueError, ""), (ValueError, "missing"))
        for error, name in cases:
            with self.subTest(name=name):
                self.assertRaises(error, mesh.setCurrentUVSet, name)
                self.assertUVSets(mesh, ["map1"])

    def test_create_uv_set_errors(self):
        """name が文字列以外は TypeError、空・既にある名前は ValueError。UV セットは増えない。"""
        mesh = self.cube()
        for error, name in ((TypeError, 5), (TypeError, b"bytes"), (ValueError, ""), (ValueError, "map1")):
            with self.subTest(name=name):
                self.assertRaises(error, mesh.createUVSet, name)
                self.assertUVSets(mesh, ["map1"])

    def test_copy_uv_set_errors(self):
        """source・target が文字列以外は TypeError、空・source が無い・target が既にあるは ValueError。"""
        mesh = self.cube()
        mesh.createUVSet("second")
        cases = (
            (TypeError, 5, "copy"),
            (TypeError, "map1", 5),
            (ValueError, "", "copy"),
            (ValueError, "map1", ""),
            (ValueError, "missing", "copy"),
            (ValueError, "map1", "second"),
            (ValueError, "map1", "map1"),
        )
        for error, source, target in cases:
            with self.subTest(source=source, target=target):
                self.assertRaises(error, mesh.copyUVSet, source, target)
                self.assertUVSets(mesh, ["map1", "second"])

    def test_rename_uv_set_errors(self):
        """name・newName が文字列以外は TypeError、空・name が無い・newName が既にあるは ValueError。"""
        mesh = self.cube()
        mesh.createUVSet("second")
        cases = (
            (TypeError, None, "renamed"),
            (TypeError, "second", 5),
            (ValueError, "", "renamed"),
            (ValueError, "second", ""),
            (ValueError, "missing", "renamed"),
            (ValueError, "second", "map1"),
        )
        for error, name, new_name in cases:
            with self.subTest(name=name, newName=new_name):
                self.assertRaises(error, mesh.renameUVSet, name, new_name)
                self.assertUVSets(mesh, ["map1", "second"])


class NodeErrorTest(_Case):
    """Node の照会で、無効なノード・不正な入力の例外。"""

    def test_invalid_node_queries_raise_runtime_error(self):
        """削除したノードの findCycles・getAliases は RuntimeError。"""
        for method in ("findCycles", "getAliases"):
            for flush in (False, True):
                with self.subTest(method=method, flush=flush):
                    self.assertRaises(RuntimeError, getattr(self.deleted(flush=flush), method))

    def test_destroyed_node_queries_raise_runtime_error(self):
        """削除して Undo の記録も消えたノードの getTypeId・getPluginName・isFromReferencedFile は RuntimeError。"""
        for method in ("getTypeId", "getPluginName", "isFromReferencedFile"):
            with self.subTest(method=method):
                self.assertRaises(RuntimeError, getattr(self.deleted(flush=True), method))

    def test_destroyed_node_queries_valid_counterpart(self):
        """正常系: 有効なノードでは typeId は MTypeId と同じ整数、組み込み型のプラグイン名は空。"""
        node = self.node("transform")
        self.assertEqual(node.getTypeId(), om2.MFnDependencyNode(node.mnode()).typeId.id())
        self.assertEqual(node.getPluginName(), "")
        self.assertFalse(node.isFromReferencedFile())

    def test_find_cycles_and_aliases_on_valid_node(self):
        """正常系: 循環の無いノードは空リスト、エイリアスは (名前, Plug) の組。"""
        node = self.node("transform")
        cmds.aliasAttr("moveX", node.getFullName() + ".translateX")
        self.assertEqual(node.findCycles(), [])
        aliases = node.getAliases()
        self.assertEqual([alias for alias, _ in aliases], ["moveX"])
        self.assertEqual(aliases[0][1].getLongName(), "translateX")

    def test_is_ancestor_of_rejects_unresolvable_input(self):
        """other が未対応型は TypeError、解決できない名前・null の MObject・MPlug は RuntimeError。"""
        parent = self.node("transform")
        child = self.node("transform", parent=parent)
        for error, other in ((TypeError, 5), (TypeError, None), (TypeError, 1.5),
                             (RuntimeError, self.name("missing")),
                             (RuntimeError, om2.MObject()), (RuntimeError, om2.MPlug())):
            with self.subTest(other=other):
                self.assertRaises(error, parent.isAncestorOf, other)
        self.assertTrue(parent.isAncestorOf(child))
        self.assertFalse(child.isAncestorOf(parent))

    def test_is_ancestor_of_rejects_invalid_self(self):
        """自身を削除した後(Undo の記録の有無によらない)の isAncestorOf は RuntimeError。"""
        for flush in (False, True):
            with self.subTest(flush=flush):
                other = self.node("transform")
                self.assertRaises(RuntimeError, self.deleted(flush=flush).isAncestorOf, other)


class NodesErrorTest(_Case):
    """Nodes の一括照会。"""

    def test_get_override_color_rejects_non_dag(self):
        """DAG ノード以外を含む Nodes の getOverrideColor は TypeError。"""
        dag = self.node("transform")
        for items in ([self.node("multiplyDivide")], [dag, self.node("multiplyDivide")]):
            with self.subTest(items=len(items)):
                self.assertRaises(TypeError, mlib.Nodes(items).getOverrideColor)

    def test_invalid_items_raise_runtime_error(self):
        """保持中のノードを削除した後の getOverrideColor・getNames は RuntimeError。"""
        for method in ("getOverrideColor", "getNames"):
            with self.subTest(method=method):
                first, second = self.node("transform"), self.node("transform")
                nodes = mlib.Nodes([first, second])
                cmds.delete(second.getFullName())
                self.assertRaises(RuntimeError, getattr(nodes, method))

    def test_valid_items(self):
        """正常系: getNames は保持順の名前、getOverrideColor は各ノードの表示色。"""
        first, second = self.node("transform"), self.node("transform")
        nodes = mlib.Nodes([first, second])
        self.assertEqual(nodes.getNames(), [first.getName(), second.getName()])
        self.assertEqual(nodes.getOverrideColor(), [first.getOverrideColor(), second.getOverrideColor()])


class NurbsCurveErrorTest(_Case):
    """NurbsCurve のパラメーター・弧長の照会。"""

    def curve(self, points=((0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0)), degree=3):
        transform = cmds.curve(name=self.name("curve#"), degree=degree, point=points)
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def test_empty_shape_raises_runtime_error(self):
        """形状データを持たない空の nurbsCurve では各照会が RuntimeError。"""
        empty = mlib.getNode(self.make("nurbsCurve", "emptyCurve#", parent=self.make("transform", "emptyParent#")))
        calls = (
            ("getParamRange", ()),
            ("getClosestPoint", ((0, 0, 0),)),
            ("getPointAtParam", (0.0,)),
            ("getTangentAtParam", (0.0,)),
            ("getLengthAtParam", (0.0,)),
            ("getParamAtLength", (0.0,)),
            ("getParamsAlong", (2,)),
        )
        for method, args in calls:
            with self.subTest(method=method):
                self.assertRaises(RuntimeError, getattr(empty, method), *args)

    def test_world_space_must_be_bool(self):
        """worldSpace・ws が bool 以外、または両方の指定は TypeError。"""
        curve = self.curve()
        calls = (
            ("getClosestPoint", ((0, 0, 0),)),
            ("getPointAtParam", (0.5,)),
            ("getTangentAtParam", (0.5,)),
            ("getLengthAtParam", (0.5,)),
            ("getParamAtLength", (1.0,)),
            ("getParamsAlong", (2,)),
        )
        for method, args in calls:
            call = getattr(curve, method)
            with self.subTest(method=method):
                self.assertRaises(TypeError, call, *args, worldSpace=1)
                self.assertRaises(TypeError, call, *args, ws="yes")
                self.assertRaises(TypeError, call, *args, worldSpace=None)
                self.assertRaises(TypeError, call, *args, worldSpace=True, ws=True)

    def test_get_closest_point_errors(self):
        """点が文字列・非シーケンスは TypeError、成分が有限でない場合は ValueError。"""
        curve = self.curve()
        self.assertRaises(TypeError, curve.getClosestPoint, "abc")
        self.assertRaises(TypeError, curve.getClosestPoint, object())
        self.assertRaises(ValueError, curve.getClosestPoint, (float("nan"), 0, 0))
        self.assertRaises(ValueError, curve.getClosestPoint, (1, 2))
        self.assertRaises(ValueError, curve.getClosestPoint, (1, 2, 3, 4))
        position, param = curve.getClosestPoint((1.5, 2, 0))
        self.assertSequenceAlmostEqual(position, (1.5, 0, 0), places=5)
        self.assertAlmostEqual(param, 0.5, places=5)

    def test_param_errors(self):
        """param が数値でない(bool を含む)は TypeError、有限でない・範囲外は ValueError。"""
        curve = self.curve()
        for method in ("getPointAtParam", "getTangentAtParam", "getLengthAtParam"):
            call = getattr(curve, method)
            for error, param in ((TypeError, "a"), (TypeError, None), (TypeError, True),
                                 (ValueError, float("nan")), (ValueError, float("inf")),
                                 (ValueError, -0.5), (ValueError, 1.5)):
                with self.subTest(method=method, param=param):
                    self.assertRaises(error, call, param)

    def test_tangent_undefined_at_coincident_cvs(self):
        """重なった CV で接線が 0 になる位置の getTangentAtParam は ValueError。"""
        curve = self.curve(points=((0, 0, 0), (0, 0, 0), (1, 0, 0)), degree=1)
        for param in (0.0, 0.5):
            with self.subTest(param=param):
                self.assertRaises(ValueError, curve.getTangentAtParam, param)
        self.assertSequenceAlmostEqual(curve.getTangentAtParam(1.5), (1, 0, 0), places=6)

    def test_unit_errors(self):
        """unit が文字列・None 以外は TypeError、未対応の単位名は ValueError。"""
        curve = self.curve()
        for method, value in (("getLengthAtParam", 0.5), ("getParamAtLength", 1.0)):
            call = getattr(curve, method)
            with self.subTest(method=method):
                self.assertRaises(TypeError, call, value, unit=5)
                self.assertRaises(ValueError, call, value, unit="furlong")
        self.assertAlmostEqual(curve.getLengthAtParam(1.0, unit="m"), 0.03, places=6)
        self.assertAlmostEqual(curve.getParamAtLength(0.015, unit="m"), 0.5, places=5)

    def test_get_param_at_length_errors(self):
        """length が数値でないは TypeError、有限でない・負・全長超えは ValueError。"""
        curve = self.curve()
        for error, length in ((TypeError, "a"), (TypeError, None), (ValueError, float("inf")),
                              (ValueError, float("nan")), (ValueError, -1.0), (ValueError, 3.5)):
            with self.subTest(length=length):
                self.assertRaises(error, curve.getParamAtLength, length)

    def test_get_params_along_errors(self):
        """count が int 以外(bool を含む)は TypeError、1 未満は ValueError。"""
        curve = self.curve()
        for error, count in ((TypeError, True), (TypeError, 2.0), (TypeError, "3"),
                             (ValueError, 0), (ValueError, -1)):
            with self.subTest(count=count):
                self.assertRaises(error, curve.getParamsAlong, count)
        self.assertSequenceAlmostEqual(curve.getParamsAlong(3), (0.0, 0.5, 1.0), places=5)


class ObjectSetErrorTest(_Case):
    """ObjectSet.addMembers で Maya が追加を拒否する場合。"""

    def object_set(self):
        return mlib.getNode(cmds.sets(name=self.name("set#"), empty=True))

    def members(self, object_set):
        return sorted(cmds.sets(object_set.getFullName(), query=True) or [])

    def test_cycle_is_rejected(self):
        """セット自身の追加は循環になるため RuntimeError で、メンバーは変わらない。"""
        object_set = self.object_set()
        member = self.node("transform")
        object_set.addMembers(member)
        before = self.members(object_set)
        self.assertRaises(RuntimeError, object_set.addMembers, object_set)
        self.assertEqual(self.members(object_set), before)

    def test_partition_exclusivity_is_rejected(self):
        """同じ partition の別のセットに入っているノードの追加は RuntimeError で、どちらも加わらない。"""
        partition = cmds.partition(name=self.name("partition#"))
        first, second = self.object_set(), self.object_set()
        cmds.partition(first.getFullName(), add=partition)
        cmds.partition(second.getFullName(), add=partition)
        taken, free = self.node("transform"), self.node("transform")
        first.addMembers(taken)
        self.assertRaises(RuntimeError, second.addMembers, free, taken)
        self.assertEqual(self.members(second), [])
        self.assertEqual(self.members(first), [taken.getName()])

    def test_input_errors(self):
        """未対応型・名前とノードの混在は TypeError、一致しない名前は ValueError で、メンバーは変わらない。"""
        object_set = self.object_set()
        member = self.node("transform")
        for error, members in ((TypeError, (5,)), (TypeError, (None,)),
                               (TypeError, (member, self.name("other"))),
                               (ValueError, (self.name("missing"),))):
            with self.subTest(members=members):
                self.assertRaises(error, object_set.addMembers, *members)
                self.assertEqual(self.members(object_set), [])


class CalculationNodeErrorTest(_Case):
    """PairBlend・PlusMinusAverage・PointOnCurveInfo・PointOnSurfaceInfo・RemapValue。"""

    def test_pair_blend_set_rotate_interpolation_errors(self):
        """名前・int 以外(bool を含む)は TypeError、未対応の名前・範囲外の番号は ValueError。値は変わらない。"""
        node = self.node("pairBlend")
        node.setRotateInterpolation("quaternion")
        plug = node.getFullName() + ".rotInterpolation"
        for error, value in ((TypeError, 1.5), (TypeError, None), (TypeError, True),
                             (ValueError, "slerp"), (ValueError, 2), (ValueError, -1)):
            with self.subTest(value=value):
                self.assertRaises(error, node.setRotateInterpolation, value)
                self.assertEqual(cmds.getAttr(plug), 1)

    def test_pair_blend_invalid_node(self):
        """削除した pairBlend の setRotateInterpolation は RuntimeError。"""
        self.assertRaises(RuntimeError, self.deleted("pairBlend").setRotateInterpolation, "euler")

    def test_get_output_plug_rejects_unknown_kind(self):
        """各計算ノードの getOutputPlug は未対応の kind で ValueError。"""
        cases = (
            ("pairBlend", "translate"),
            ("pointOnCurveInfo", "position"),
            ("pointOnSurfaceInfo", "position"),
            ("remapValue", "value"),
        )
        for node_type, valid in cases:
            node = self.node(node_type)
            for kind in ("missing", "", 5, None):
                with self.subTest(node_type=node_type, kind=kind):
                    self.assertRaises(ValueError, node.getOutputPlug, kind)
            self.assertEqual(node.getOutputPlug(valid).getNode(), node)

    def test_plus_minus_average_dimension_errors(self):
        """getOutputPlug・getInputIndices の dimension が 1・2・3 以外(bool・文字列を含む)は ValueError、ハッシュできない型は TypeError。"""
        node = self.node("plusMinusAverage")
        for method in ("getOutputPlug", "getInputIndices"):
            for dimension in (0, 4, True, "1", None):
                with self.subTest(method=method, dimension=dimension):
                    self.assertRaises(ValueError, getattr(node, method), dimension)
            for dimension in ([1], {1: 1}, {1}):
                with self.subTest(method=method, dimension=dimension):
                    self.assertRaises(TypeError, getattr(node, method), dimension)
        cmds.setAttr(node.getFullName() + ".input3D[2].input3Dx", 1.0)
        self.assertEqual(node.getInputIndices(3), [2])
        self.assertEqual(node.getOutputPlug(2).getLongName(), "output2D")

    def entries(self, node, kind="value"):
        return node.getPlug(kind).getEntries()

    def test_remap_value_set_ramp_points_errors(self):
        """点の形・型の不正は TypeError、kind 未対応・空・有限でない・補間名の未対応は ValueError。ランプは変わらない。"""
        node = self.node("remapValue")
        before = self.entries(node)
        cases = (
            (TypeError, ([(0, 1)],), {}),
            (TypeError, ([("a", 1, "linear")],), {}),
            (TypeError, (5,), {}),
            (TypeError, ([(0, 1, 5)],), {}),
            (TypeError, ([(0, 1, "linear")],), {"kind": "color"}),
            (ValueError, ([(0, 1, "linear")],), {"kind": "alpha"}),
            (ValueError, ([],), {}),
            (ValueError, ([(float("nan"), 1, "linear")],), {}),
            (ValueError, ([(0, float("inf"), "linear")],), {}),
            (ValueError, ([(0, 1, "cubic")],), {}),
        )
        for error, args, flags in cases:
            with self.subTest(args=args, flags=flags):
                self.assertRaises(error, node.setRampPoints, *args, **flags)
                self.assertEqual(self.entries(node), before)

    def test_remap_value_add_ramp_point_errors(self):
        """位置・値・補間の型の不正は TypeError、kind・補間の未対応・有限でない数値は ValueError。ランプは変わらない。"""
        node = self.node("remapValue")
        before = self.entries(node)
        cases = (
            (TypeError, ("a", 1), {}),
            (TypeError, (0.5, "a"), {}),
            (TypeError, (0.5, 0.5, 5), {}),
            (TypeError, (0.5, 0.5), {"kind": "color"}),
            (ValueError, (0.5, 0.5, "cubic"), {}),
            (ValueError, (0.5, 0.5), {"kind": "alpha"}),
            (ValueError, (0.5, float("nan")), {}),
            (ValueError, (float("inf"), 0.5), {}),
        )
        for error, args, flags in cases:
            with self.subTest(args=args, flags=flags):
                self.assertRaises(error, node.addRampPoint, *args, **flags)
                self.assertEqual(self.entries(node), before)
        node.addRampPoint(0.5, 0.25, "smooth")
        self.assertIn((0.5, 0.25, "smooth"), self.entries(node))

    def test_remap_value_invalid_node(self):
        """削除した remapValue の setRampPoints・addRampPoint は RuntimeError。"""
        node = self.deleted("remapValue")
        self.assertRaises(RuntimeError, node.setRampPoints, [(0, 0, "linear")])
        self.assertRaises(RuntimeError, node.addRampPoint, 0.5, 0.5)


class ReferenceErrorTest(_Case):
    """Reference.unload で Maya がアンロードを拒否する場合。"""

    def test_unload_without_file_raises(self):
        """ファイルに結び付いていない reference ノードの unload は RuntimeError。"""
        reference = mlib.getNode(self.make("reference", "unboundRN#"))
        self.assertRaises(RuntimeError, reference.unload)
        self.assertTrue(cmds.objExists(reference.getFullName()))


class ShadingEngineErrorTest(_Case):
    """ShadingEngine.setShader。"""

    def engine(self):
        return mlib.getNode(cmds.sets(name=self.name("SG#"), renderable=True, noSurfaceShader=True, empty=True))

    def sources(self, engine, attribute="surfaceShader"):
        return cmds.listConnections(engine.getFullName() + "." + attribute, source=True,
                                    destination=False, plugs=True) or []

    def test_unknown_kind_raises_value_error(self):
        """kind が surface・volume・displacement 以外は ValueError で、接続は変わらない(fast も同じ)。"""
        engine = self.engine()
        shader = self.node("lambert")
        for fast in (False, True):
            for kind in ("missing", "Surface", ""):
                with self.subTest(fast=fast, kind=kind):
                    self.assertRaises(ValueError, engine.setShader, shader, kind=kind, fast=fast)
                    self.assertEqual(self.sources(engine), [])

    def test_maya_rejects_connection(self):
        """自身のアトリビュートへの接続を Maya が拒否すると RuntimeError で、接続は変わらない。"""
        engine = self.engine()
        shader = self.node("lambert")
        engine.setShader(shader)
        before = self.sources(engine)
        self.assertRaises(RuntimeError, engine.setShader, engine.getPlug("surfaceShader"))
        self.assertEqual(self.sources(engine), before)

    def test_replaces_existing_connection(self):
        """正常系: 別のシェーダーを指定すると既存の接続を置き換える。"""
        engine = self.engine()
        first, second = self.node("lambert"), self.node("lambert")
        engine.setShader(first)
        engine.setShader(second)
        self.assertEqual(self.sources(engine), [second.getName() + ".outColor"])

    def test_same_shader_again_is_no_op(self):
        """接続済みの同じシェーダーの再指定は例外にせず、接続も変わらない(fast も同じ)。"""
        engine = self.engine()
        shader = self.node("lambert")
        engine.setShader(shader)
        for fast in (False, True):
            with self.subTest(fast=fast):
                self.assertIs(engine.setShader(shader, fast=fast), engine)
                self.assertEqual(self.sources(engine), [shader.getName() + ".outColor"])

    def test_self_connection_rejected_with_fast(self):
        """fast=True でも自身の surfaceShader への接続は RuntimeError で、接続は変わらない。"""
        engine = self.engine()
        shader = self.node("lambert")
        engine.setShader(shader)
        before = self.sources(engine)
        self.assertRaises(RuntimeError, engine.setShader, engine.getPlug("surfaceShader"), fast=True)
        self.assertEqual(self.sources(engine), before)


class SkinClusterErrorTest(_Case):
    """SkinCluster の保存ポーズ・ウェイトの照会と書き出し。"""

    def skin(self):
        self.track_outside_nodes()
        cmds.select(clear=True)
        root = cmds.joint(name=self.name("root"), position=(0, 0, 0))
        cmds.joint(name=self.name("tip"), position=(0, 1, 0))
        cmds.select(clear=True)
        cmds.joint(name=self.name("unused"), position=(5, 5, 5))
        cmds.select(clear=True)
        mesh = cmds.polyCylinder(name=self.name("body"), constructionHistory=False)[0]
        skin = cmds.skinCluster(root, self.name("tip"), self.name("unused"), mesh,
                                toSelectedBones=True, name=self.name("skin"))[0]
        return mlib.getNode(skin)

    def test_get_bind_pose_errors(self):
        """bindPose が dagPose 以外へつながる・skinCluster が無効な場合は RuntimeError。"""
        skin = self.skin()
        plug = skin.getFullName() + ".bindPose"
        pose = cmds.listConnections(plug, source=True, destination=False, plugs=True)[0]
        self.assertEqual(skin.getBindPose().getFullName(), cmds.ls(pose.split(".")[0], long=True)[0])
        cmds.disconnectAttr(pose, plug)
        self.assertIsNone(skin.getBindPose())
        cmds.connectAttr(self.make("transform", "notPose#") + ".message", plug)
        self.assertRaises(RuntimeError, skin.getBindPose)
        cmds.delete(skin.getFullName())
        self.assertRaises(RuntimeError, skin.getBindPose)

    def test_get_unused_influences(self):
        """正常系: 頂点にウェイトを持たない influence だけを返す。"""
        skin = self.skin()
        self.assertEqual([node.getName() for node in skin.getUnusedInfluences()], [self.name("unused")])

    def test_get_unused_influences_invalid(self):
        """削除した skinCluster の getUnusedInfluences は RuntimeError(Undo の記録の有無によらない)。"""
        skin = self.skin()
        cmds.delete(skin.getFullName())
        self.assertRaises(RuntimeError, skin.getUnusedInfluences)
        cmds.flushUndo()
        self.assertRaises(RuntimeError, skin.getUnusedInfluences)

    def test_export_weights_invalid(self):
        """削除した skinCluster の exportWeights は RuntimeError で、ファイルを作らない。"""
        skin = self.skin()
        root = self.temp_dir()
        cmds.delete(skin.getFullName())
        self.assertRaises(RuntimeError, skin.exportWeights, os.path.join(root, "weights.json"))
        self.assertEqual(os.listdir(root), [])

    def test_get_weights_data_invalid(self):
        """削除した skinCluster の getWeightsData は RuntimeError。"""
        skin = self.skin()
        self.assertEqual(skin.getWeightsData()["vertexCount"], cmds.polyEvaluate(self.name("body"), vertex=True))
        cmds.delete(skin.getFullName())
        self.assertRaises(RuntimeError, skin.getWeightsData)

    def test_export_weights_to_missing_folder(self):
        """存在しないフォルダーへの exportWeights は OSError で、フォルダーもファイルも作らない。"""
        skin = self.skin()
        root = self.temp_dir()
        target = os.path.join(root, "missing", "weights.json")
        self.assertRaises(OSError, skin.exportWeights, target)
        self.assertEqual(os.listdir(root), [])


class TransformErrorTest(_Case):
    """Transform の照会・回転の設定・カーブ形状の書き出し。"""

    def test_invalid_transform_raises_runtime_error(self):
        """削除した Transform の各照会は RuntimeError(Undo の記録の有無によらない)。"""
        calls = (
            ("getOffsetParentMatrix", ()),
            ("getUnusedIntermediateShapes", ()),
            ("getCurveShapesData", ()),
            ("getClosestAxisToVector", ((1, 0, 0),)),
        )
        for method, args in calls:
            for flush in (False, True):
                with self.subTest(method=method, flush=flush):
                    self.assertRaises(RuntimeError, getattr(self.deleted(flush=flush), method), *args)

    def test_export_curve_shapes_errors(self):
        """無効な Transform は RuntimeError、存在しないフォルダーは OSError。ファイルは作らない。"""
        root = self.temp_dir()
        self.assertRaises(RuntimeError, self.deleted().exportCurveShapes, os.path.join(root, "shapes.json"))
        transform = mlib.getNode(cmds.circle(name=self.name("ctrl#"), constructionHistory=False)[0])
        self.assertRaises(OSError, transform.exportCurveShapes, os.path.join(root, "missing", "shapes.json"))
        self.assertEqual(os.listdir(root), [])
        path = transform.exportCurveShapes(os.path.join(root, "shapes.json"))
        self.assertTrue(path.is_file())

    def test_get_pivot_errors(self):
        """kind が rotate・scale 以外は ValueError。"""
        transform = self.node("transform")
        for kind in ("translate", "", "Rotate"):
            with self.subTest(kind=kind):
                self.assertRaises(ValueError, transform.getPivot, kind=kind)
        cmds.xform(transform.getFullName(), scalePivot=(1, 2, 3))
        self.assertSequenceAlmostEqual(transform.getPivot(kind="scale"), (1, 2, 3))

    def test_get_closest_axis_to_vector_zero_vectors(self):
        """refVector がゼロ、またはローカル軸がワールド変換でゼロになる場合は ValueError。"""
        transform = self.node("transform")
        self.assertRaises(ValueError, transform.getClosestAxisToVector, (0, 0, 0))
        flat = self.node("transform")
        cmds.setAttr(flat.getFullName() + ".offsetParentMatrix",
                     [0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1], type="matrix")
        for include_negative in (True, False):
            with self.subTest(includeNegative=include_negative):
                self.assertRaises(ValueError, flat.getClosestAxisToVector, (0, 1, 0), include_negative)
        cmds.setAttr(transform.getFullName() + ".rotateZ", 90)
        self.assertEqual(transform.getClosestAxisToVector((0, 1, 0)), "x")
        self.assertEqual(transform.getClosestAxisToVector((1, 0, 0)), "-y")

    def test_set_quaternion_errors(self):
        """unit が文字列以外は TypeError、未対応の単位名・未対応の成分と空間の組合せは ValueError。rotate は変わらない。"""
        transform = self.node("transform")
        cmds.setAttr(transform.getFullName() + ".rotate", 10, 20, 30)
        half = math.sqrt(0.5)
        value = (0.0, 0.0, half, half)
        cases = (
            (TypeError, {"unit": 5}),
            (TypeError, {"unit": 5, "get": True}),
            (ValueError, {"unit": "turn"}),
            (ValueError, {"unit": "turn", "fast": True}),
            (ValueError, {"worldSpace": True, "jo": False}),
            (ValueError, {"worldSpace": True, "r": False}),
            (ValueError, {"ws": True, "r": False, "ra": True}),
        )
        for error, flags in cases:
            with self.subTest(flags=flags):
                self.assertRaises(error, transform.setQuaternion, value, **flags)
                self.assertSequenceAlmostEqual(cmds.getAttr(transform.getFullName() + ".rotate")[0],
                                               (10, 20, 30), places=6)
        transform.setQuaternion(value)
        self.assertSequenceAlmostEqual(cmds.getAttr(transform.getFullName() + ".rotate")[0], (0, 0, 90), places=6)


if __name__ == "__main__":
    unittest.main()

"""cmds・common・components・json・maths の公開APIが docstring の Raises に書いた例外を固定する。

各メソッドの Raises に書かれた例外が実際に起きる入力を作り、``assertRaises`` で型を確かめる。
可能なものは、例外の後にノードが残らない・値が変わっていないこと(シーンが変わらないこと)も確かめる。
実装と docstring が食い違うものはここでは扱わない(別に記録する)。
"""

import math
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import DrivenKey, Plugin, ScalarGraph, Time
from mlib.common.callbacks import Callbacks
from mlib.common.environment import Environment
from mlib.components import CVs, Edges, UV, UVs, Vertex, Vertices
from mlib.json import ComponentRef, NameMapping, NodeRef, PlugRef, PoseSnapshot
from mlib.maths import EulerRotate, Quaternion
from support.specCase import NamespaceCase

_MISSING_PLUGIN = "mlibSpecNoSuchPlugin_errorPaths"


class _ErrorCase(NamespaceCase):
    """シーン全体のノード一覧の比較と、テスト用の形状の作成を共通にする。"""

    PREFIX = "mlibSpecErr_"

    def nodes(self):
        """シーン全体のノードの完全名の集合を返す。"""
        return set(cmds.ls(long=True) or [])

    def assertSceneUnchanged(self, before):
        """シーンのノードが増減していないことを確かめる。

        Args:
            before (set[str]): 操作前の :meth:`nodes` の結果。
        """
        self.assertEqual(self.nodes(), before)

    def transform(self, text="grp"):
        """この名前空間に transform を作り、名前を返す。"""
        return self.make("transform", text)

    def plane(self, text="plane", history=False):
        """2x2 分割の平面(頂点9・辺12・面4・UV9)を作り、(transform, Mesh) を返す。"""
        transform = cmds.polyPlane(name=self.name(text), width=2, height=2, subdivisionsX=2, subdivisionsY=2,
                                   constructionHistory=history)[0]
        shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
        return transform, mlib.getNode(shape)

    def shrinkPlane(self, transform):
        """角の面(3番)を消し、頂点8番・UV8番・辺10/11番を範囲外にする。"""
        cmds.delete(transform + ".f[3]")


class CreateShapeErrorTest(_ErrorCase):
    """形状を作る関数(createCircle・createLocator・createPoly*)の入力の拒否。"""

    def _check(self, function, cases):
        """各 (例外型, 引数) で例外になり、ノードが増えないことを確かめる。"""
        before = self.nodes()
        for error, kwargs in cases:
            with self.subTest(function=function.__name__, kwargs=kwargs):
                with self.assertRaises(error):
                    function(**kwargs)
                self.assertSceneUnchanged(before)

    def _parent_cases(self):
        """親の不正(存在しない名前・削除済み・transform 以外)の (例外型, 引数) を返す。"""
        deleted = mlib.getNode(self.transform("deleted"))
        cmds.delete(deleted.getFullName())
        mesh = self.plane("parentMesh")[1]
        return [
            (RuntimeError, {"parent": self.name("noSuchParent")}),
            (RuntimeError, {"parent": deleted}),
            (TypeError, {"parent": mesh}),
            (TypeError, {"name": 5}),
            (ValueError, {"name": ""}),
            (ValueError, {"name": "a|b"}),
        ]

    def test_create_circle(self):
        """半径・法線・区間数・次数・名前・親の不正。"""
        cases = [
            (TypeError, {"radius": "1"}),
            (TypeError, {"normal": 5}),
            (TypeError, {"sections": 8.0}),
            (ValueError, {"radius": 0}),
            (ValueError, {"radius": float("inf")}),
            (ValueError, {"normal": (0, 0, 0)}),
            (ValueError, {"normal": (0, 1)}),
            (ValueError, {"degree": 2}),
            (ValueError, {"degree": 3, "sections": 3}),
            (ValueError, {"degree": 1, "sections": 2}),
        ] + self._parent_cases()
        self._check(mlib.createCircle, cases)
        shape = mlib.createCircle(name=self.name("circle"), degree=1, sections=3)
        self.assertEqual(shape.getType(), "nurbsCurve")

    def test_create_locator(self):
        """localPosition・localScale の成分数・有限・型と、名前・親の不正。"""
        cases = [
            (TypeError, {"localPosition": 1}),
            (TypeError, {"localScale": ("a", 1, 1)}),
            (ValueError, {"localPosition": (0, 0)}),
            (ValueError, {"localScale": (1, float("nan"), 1)}),
        ] + self._parent_cases()
        self._check(mlib.createLocator, cases)

    def _poly_cases(self, size_names, subdivision_count):
        """ポリゴンのプリミティブ共通の (例外型, 引数) を返す。"""
        cases = []
        for size in size_names:
            cases += [(TypeError, {size: "1"}), (ValueError, {size: 0}), (ValueError, {size: -1.0}),
                      (ValueError, {size: float("inf")})]
        cases += [
            (TypeError, {"subdivisions": 5}),
            (TypeError, {"subdivisions": (1.5,) + (1,) * (subdivision_count - 1)}),
            (ValueError, {"subdivisions": (1,) * (subdivision_count + 1)}),
            (ValueError, {"subdivisions": (0,) + (1,) * (subdivision_count - 1)}),
            (TypeError, {"axis": 1}),
            (ValueError, {"axis": (0, 0, 0)}),
            (ValueError, {"axis": (0, 1)}),
        ]
        return cases + self._parent_cases()

    def test_create_poly_cylinder(self):
        """円柱の大きさ・分割数・軸・名前・親の不正。"""
        self._check(mlib.createPolyCylinder, self._poly_cases(("radius", "height"), 3))

    def test_create_poly_plane(self):
        """平面の大きさ・分割数・軸・名前・親の不正。"""
        self._check(mlib.createPolyPlane, self._poly_cases(("width", "height"), 2))

    def test_create_poly_sphere(self):
        """球の大きさ・分割数・軸・名前・親の不正。"""
        self._check(mlib.createPolySphere, self._poly_cases(("radius",), 2))


class CreateJointChainErrorTest(_ErrorCase):
    """createJointChain の入力の拒否。拒否時は joint を作らない。"""

    def test_rejections(self):
        """Raises の各項目に当たる入力で例外になり、ノードが増えない。"""
        points = [(0, 0, 0), (1, 0, 0), (2, 0, 0)]
        mesh = self.plane("mesh")[1]
        cases = [
            (TypeError, ("x",), {}),
            (TypeError, (5,), {}),
            (TypeError, ([(0, 0, "a"), (1, 0, 0)],), {}),
            (TypeError, (points,), {"up": (0, "a", 0)}),
            (TypeError, (points,), {"aimAxis": 0}),
            (TypeError, (points,), {"upAxis": None}),
            (TypeError, (points,), {"names": "abc"}),
            (TypeError, (points,), {"names": ["a", 1, "c"]}),
            (TypeError, (points,), {"parent": mesh}),
            (ValueError, ([(0, 0, 0)],), {}),
            (ValueError, ([(0, 0, 0), (0, 0, 0)],), {}),
            (ValueError, (points,), {"aimAxis": "w"}),
            (ValueError, (points,), {"aimAxis": "x", "upAxis": "-x"}),
            (ValueError, (points,), {"names": [self.name("a"), self.name("b")]}),
            (ValueError, (points,), {"names": [self.name("a"), "", self.name("c")]}),
            (ValueError, (points,), {"up": (0, 0, 0)}),
            (ValueError, (points,), {"up": (1, 0, 0)}),
            (RuntimeError, (points,), {"parent": self.name("noSuchParent")}),
        ]
        before = self.nodes()
        for error, args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    mlib.createJointChain(*args, **kwargs)
                self.assertSceneUnchanged(before)
        joints = mlib.createJointChain(points, names=[self.name("j0"), self.name("j1"), self.name("j2")])
        self.assertEqual([joint.getName() for joint in joints],
                         [self.name("j0"), self.name("j1"), self.name("j2")])


class CreateContainerErrorTest(_ErrorCase):
    """createContainer・createDagContainer は、Mayaが所属を拒否した場合 RuntimeError で何も残さない。"""

    def test_missing_member(self):
        """存在しないノードを所属させようとすると RuntimeError で、作りかけの container を残さない。"""
        before = self.nodes()
        for function in (mlib.createContainer, mlib.createDagContainer):
            with self.subTest(function=function.__name__):
                with self.assertRaises(RuntimeError):
                    function(self.name("box"), members=[self.name("noSuchMember")])
                self.assertSceneUnchanged(before)


class CallbacksErrorTest(_ErrorCase):
    """Callbacks の登録の入力の拒否。拒否時は何も登録しない。"""

    def setUp(self):
        super().setUp()
        self.callbacks = Callbacks()

    def tearDown(self):
        self.callbacks.remove()
        super().tearDown()

    def test_scene_callback(self):
        """イベント名の型・関数・未知のイベント名。"""
        for error, args in ((TypeError, (5, lambda: None)), (TypeError, ("afterOpen", 5)),
                            (ValueError, ("noSuchSceneEvent", lambda: None)),
                            (ValueError, ("AfterOpen", lambda: None))):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    self.callbacks.addSceneCallback(*args)
        self.assertFalse(self.callbacks._ids)

    def test_event_callback(self):
        """イベント名の型・関数・Mayaに無いイベント名(大文字小文字を区別)。"""
        for error, args in ((TypeError, (None, lambda: None)), (TypeError, ("timeChanged", "f")),
                            (ValueError, ("noSuchMayaEvent", lambda: None)),
                            (ValueError, ("TimeChanged", lambda: None))):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    self.callbacks.addEventCallback(*args)
        self.assertFalse(self.callbacks._ids)

    def test_attribute_changed_callback(self):
        """ノードの型・関数・存在しないノード名。"""
        node = self.transform()
        for error, args in ((TypeError, (5, lambda message, plug: None)), (TypeError, (node, 5)),
                            (RuntimeError, (self.name("noSuchNode"), lambda message, plug: None))):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    self.callbacks.addAttributeChangedCallback(*args)
        self.assertFalse(self.callbacks._ids)


class DrivenKeyErrorTest(_ErrorCase):
    """DrivenKey.find・getDrivenPlug の入力の拒否。"""

    def setUp(self):
        super().setUp()
        self.driver = self.transform("driver")
        self.driven = self.transform("driven")

    def test_find(self):
        """型・非スカラー/非数値・存在しないアトリビュート。"""
        cmds.addAttr(self.driven, longName="label", dataType="string")
        for error, value in ((TypeError, 5), (TypeError, self.driven),
                             (ValueError, self.driven + ".translate"),
                             (ValueError, self.driven + ".label"),
                             (RuntimeError, self.driven + ".noSuchAttr")):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    DrivenKey.find(value)
        self.assertEqual(DrivenKey.find(self.driven + ".tx"), [])

    def test_get_driven_plug_after_delete_attr(self):
        """駆動先の動的アトリビュートを削除すると RuntimeError。"""
        cmds.addAttr(self.driven, longName="amount", attributeType="double")
        relation = DrivenKey(self.driver + ".tx", self.driven + ".amount")
        self.assertEqual(relation.getDrivenPlug().getFullName(), self.driven + ".amount")
        cmds.deleteAttr(self.driven + ".amount")
        with self.assertRaises(RuntimeError):
            relation.getDrivenPlug()

    def test_get_driven_plug_after_delete_node(self):
        """駆動先のノードを削除すると RuntimeError。"""
        relation = DrivenKey(self.driver + ".tx", self.driven + ".ty")
        cmds.delete(self.driven)
        with self.assertRaises(RuntimeError):
            relation.getDrivenPlug()


class EnvironmentErrorTest(_ErrorCase):
    """Environment.getMayaVersion は版として解釈できない文字列で RuntimeError。"""

    def test_unparsable_version(self):
        """cmds.about が版でない文字列を返した場合を差し替えで再現する。"""
        self.assertEqual(Environment.getMayaVersion().major, int(cmds.about(apiVersion=True)) // 10000)
        with mock.patch.object(cmds, "about", return_value="not a version"):
            with self.assertRaises(RuntimeError):
                Environment.getMayaVersion()


class KeyframeErrorTest(_ErrorCase):
    """Keyframe.getTime・getValue・setValue の拒否。拒否時はキーの値を変えない。"""

    def setUp(self):
        super().setUp()
        self.node = self.transform("keyed")
        cmds.setKeyframe(self.node, attribute="tx", time=1, value=2.0)
        cmds.setKeyframe(self.node, attribute="tx", time=10, value=5.0)
        self.curve = mlib.getNode(cmds.listConnections(self.node + ".tx", source=True, destination=False)[0])

    def values(self):
        return cmds.keyframe(self.curve.getFullName(), query=True, valueChange=True)

    def test_index_out_of_range(self):
        """キーを消して番号が範囲外になると IndexError。"""
        key = self.curve.getKeyframe(1)
        self.assertEqual(key.getTime(), 10.0)
        cmds.cutKey(self.curve.getFullName(), time=(10, 10))
        before = self.values()
        for name, call in (("getTime", key.getTime), ("getValue", key.getValue),
                           ("setValue", lambda: key.setValue(1.0)),
                           ("setValue fast", lambda: key.setValue(1.0, fast=True))):
            with self.subTest(name=name):
                with self.assertRaises(IndexError):
                    call()
        self.assertEqual(self.values(), before)

    def test_deleted_curve(self):
        """カーブを削除すると RuntimeError。"""
        key = self.curve.getKeyframe(0)
        cmds.delete(self.curve.getFullName())
        for name, call in (("getTime", key.getTime), ("getValue", key.getValue),
                           ("setValue", lambda: key.setValue(1.0))):
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):
                    call()

    def test_set_value_rejections(self):
        """値の型・fast の型・非有限値・未対応の単位名。値は変わらない。"""
        key = self.curve.getKeyframe(0)
        before = self.values()
        for error, args, kwargs in ((TypeError, (object(),), {}), (TypeError, (1.0,), {"fast": "yes"}),
                                    (ValueError, (float("nan"),), {}), (ValueError, (float("inf"),), {}),
                                    (ValueError, (1.0,), {"unit": "grad"}),
                                    (ValueError, (1.0,), {"timeUnit": "minute"})):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    key.setValue(*args, **kwargs)
                self.assertEqual(self.values(), before)
        key.setValue(7.0)
        self.assertAlmostEqual(key.getValue(), 7.0)


class PluginErrorTest(_ErrorCase):
    """Plugin のロード・アンロードの拒否。"""

    def test_missing_plugin(self):
        """見つからないプラグインの ensureLoaded は RuntimeError。"""
        plugin = Plugin(_MISSING_PLUGIN)
        self.assertFalse(plugin.isLoaded())
        with self.assertRaises(RuntimeError):
            plugin.ensureLoaded()
        self.assertFalse(plugin.isLoaded())

    def test_unload_in_use(self):
        """使用中のプラグインの unload(force=False) は Maya が拒否して RuntimeError で、ロードされたまま。"""
        plugin = Plugin("quatNodes")
        was_loaded = plugin.isLoaded()
        plugin.ensureLoaded()
        node = self.make("quatToEuler", "quat")
        try:
            with self.assertRaises(RuntimeError):
                plugin.unload()
            self.assertTrue(plugin.isLoaded())
        finally:
            cmds.delete(node)
            if not was_loaded:
                # Undo の履歴がノードを参照していると使用中のままになるため、空にしてから戻す。
                cmds.flushUndo()
                cmds.unloadPlugin("quatNodes", force=True)

    def test_ensure_node_plugin(self):
        """HumanIK 以外は何もせず、ロードが拒否されると RuntimeError を伝える(拒否は差し替えで再現する)。"""
        self.assertIsNone(Plugin.ensureNodePlugin("transform"))
        with mock.patch.object(Plugin, "isLoaded", return_value=False), \
                mock.patch.object(Plugin, "load", side_effect=RuntimeError("refused")):
            with self.assertRaises(RuntimeError):
                Plugin.ensureNodePlugin("HIKCharacterNode")
            self.assertIsNone(Plugin.ensureNodePlugin("joint"))


class ScalarGraphErrorTest(_ErrorCase):
    """ScalarGraph の構築メソッドの fast の拒否。拒否時はノードを作らない。"""

    def _calls(self, graph):
        return (
            ("sum", lambda fast: graph.sum(self.name("sum"), 1.0, 2.0, fast=fast)),
            ("multiply", lambda fast: graph.multiply(self.name("mul"), 1.0, 2.0, fast=fast)),
            ("condition", lambda fast: graph.condition(self.name("cond"), 1.0, 2.0, 3.0, 4.0, fast=fast)),
        )

    def test_fast_not_bool(self):
        """fast が bool 以外なら TypeError。"""
        graph = ScalarGraph(createNode=mlib.createNode)
        before = self.nodes()
        for name, call in self._calls(graph):
            for value in ("yes", 1, None):
                with self.subTest(method=name, fast=value):
                    with self.assertRaises(TypeError):
                        call(value)
                    self.assertSceneUnchanged(before)

    def test_container_fast(self):
        """container を所有先にして fast=True なら NotImplementedError。"""
        container = mlib.createContainer(self.name("graph"))
        graph = ScalarGraph(container)
        before = self.nodes()
        for name, call in self._calls(graph):
            with self.subTest(method=name):
                with self.assertRaises(NotImplementedError):
                    call(True)
                self.assertSceneUnchanged(before)
        self.assertEqual(list(container.getMembers()), [])


class TimeErrorTest(_ErrorCase):
    """Time.setAnimationRange の拒否。拒否時は範囲を変えない。"""

    def setUp(self):
        super().setUp()
        self.original = (cmds.playbackOptions(query=True, animationStartTime=True),
                         cmds.playbackOptions(query=True, animationEndTime=True))

    def tearDown(self):
        cmds.playbackOptions(animationStartTime=self.original[0], animationEndTime=self.original[1])
        super().tearDown()

    def test_rejections(self):
        """数値以外・非有限・開始>終了・未対応の単位名。"""
        for error, args, kwargs in ((TypeError, ("1", 10), {}), (TypeError, (1, None), {}),
                                    (ValueError, (float("nan"), 10), {}), (ValueError, (1, float("inf")), {}),
                                    (ValueError, (20, 10), {}), (ValueError, (1, 10), {"timeUnit": "minute"})):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    Time.setAnimationRange(*args, **kwargs)
                self.assertEqual(Time.getAnimationRange(), self.original)


class ComponentNameErrorTest(_ErrorCase):
    """Components.getCompactNames・CVs.getCompactNames の拒否。"""

    def test_components_out_of_range_and_deleted(self):
        """トポロジー変更で範囲外なら IndexError、シェイプ削除後は RuntimeError。"""
        transform, mesh = self.plane()
        vertices = Vertices(mesh, [0, 1, 2, 8])
        self.assertEqual(vertices.getCompactNames(),
                         [mesh.getFullName() + ".vtx[0:2]", mesh.getFullName() + ".vtx[8]"])
        self.shrinkPlane(transform)
        with self.assertRaises(IndexError):
            vertices.getCompactNames()
        cmds.delete(transform)
        with self.assertRaises(RuntimeError):
            vertices.getCompactNames()

    def test_cvs_out_of_range_and_deleted(self):
        """CV数を減らすと IndexError、カーブ削除後は RuntimeError。"""
        transform = cmds.curve(name=self.name("curve"), degree=1,
                               point=[(0, 0, 0), (1, 0, 0), (2, 0, 0), (3, 0, 0), (4, 0, 0)])
        shape = mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])
        cvs = CVs(shape, [3, 4])
        self.assertEqual(len(cvs.getCompactNames()), 2)
        cmds.rebuildCurve(transform, constructionHistory=False, replaceOriginal=True, rebuildType=0,
                          spans=1, degree=1, keepRange=0)
        with self.assertRaises(IndexError):
            cvs.getCompactNames()
        cmds.delete(transform)
        with self.assertRaises(RuntimeError):
            cvs.getCompactNames()


class TopologyQueryErrorTest(_ErrorCase):
    """Edges.getLoop・getRing と Vertices.grow・shrink の拒否。"""

    def test_out_of_range_and_deleted(self):
        """トポロジー変更で範囲外なら IndexError、シェイプ削除後は RuntimeError。"""
        transform, mesh = self.plane()
        edges = Edges(mesh, [11])
        vertices = Vertices(mesh, [4, 8])
        calls = (("getLoop", edges.getLoop), ("getRing", edges.getRing),
                 ("grow", vertices.grow), ("shrink", vertices.shrink))
        for name, call in calls:
            with self.subTest(method=name, state="valid"):
                call()
        self.assertEqual(list(vertices.grow().indices)[:2], [4, 8])
        self.shrinkPlane(transform)
        for name, call in calls:
            with self.subTest(method=name, state="shrunk"):
                with self.assertRaises(IndexError):
                    call()
        cmds.delete(transform)
        for name, call in calls:
            with self.subTest(method=name, state="deleted"):
                with self.assertRaises(RuntimeError):
                    call()


class PointComponentSetterErrorTest(_ErrorCase):
    """PointComponent・PointComponents の座標の書込みの拒否。拒否時は座標を変えない。"""

    def _singles(self, mesh, index):
        vertex = Vertex(mesh, index)
        return (("Vertex.setPositionX", vertex.setPositionX), ("Vertex.setPositionY", vertex.setPositionY),
                ("Vertex.setPositionZ", vertex.setPositionZ))

    def _multis(self, mesh, indices):
        vertices = Vertices(mesh, indices)
        return (("Vertices.setPositionX", vertices.setPositionX), ("Vertices.setPositionY", vertices.setPositionY),
                ("Vertices.setPositionZ", vertices.setPositionZ),
                ("Vertices.setPositions", lambda value, *args, **kwargs: vertices.setPositions(
                    [(value, value, value)] * len(indices) if isinstance(value, (int, float)) else value,
                    *args, **kwargs)))

    def points(self, mesh):
        return cmds.xform(mesh.getFullName() + ".vtx[*]", query=True, translation=True, objectSpace=True)

    def _all(self, mesh, index):
        return self._singles(mesh, index) + self._multis(mesh, [0, index])

    def test_argument_rejections(self):
        """worldSpace・fast・値の型と非有限値。"""
        _, mesh = self.plane()
        before = self.points(mesh)
        for name, call in self._all(mesh, 4):
            for error, args, kwargs in ((TypeError, (1.0,), {"fast": "yes"}),
                                        (TypeError, (1.0,), {"worldSpace": "yes"}),
                                        (TypeError, (1.0,), {"ws": 1}),
                                        (TypeError, (1.0, True), {"ws": True}),
                                        (ValueError, (float("nan"),), {})):
                with self.subTest(method=name, args=args, kwargs=kwargs):
                    with self.assertRaises(error):
                        call(*args, **kwargs)
                    self.assertEqual(self.points(mesh), before)
        for name, call in self._singles(mesh, 4) + self._multis(mesh, [0, 4])[:3]:
            with self.subTest(method=name, value="text"):
                with self.assertRaises(TypeError):
                    call("a")
        vertices = Vertices(mesh, [0, 4])
        for error, value in ((ValueError, [1.0]), (TypeError, ["a", 1.0])):
            with self.subTest(method="Vertices.setPositionX", value=value):
                with self.assertRaises(error):
                    vertices.setPositionX(value)
        for error, values in ((ValueError, [(0, 0, 0)]), (ValueError, [(0, 0), (0, 0)]),
                              (TypeError, [(0, 0, "a"), (0, 0, 0)]), (TypeError, 5)):
            with self.subTest(method="Vertices.setPositions", values=values):
                with self.assertRaises(error):
                    vertices.setPositions(values)
        self.assertEqual(self.points(mesh), before)

    def test_singular_world_matrix(self):
        """worldSpace=True で変換マトリクスがほぼ特異なら ValueError。"""
        transform, mesh = self.plane()
        cmds.setAttr(transform + ".scaleX", 0)
        before = self.points(mesh)
        for name, call in self._all(mesh, 4):
            with self.subTest(method=name):
                with self.assertRaises(ValueError):
                    call(1.0, worldSpace=True)
                self.assertEqual(self.points(mesh), before)

    def test_fast_with_history(self):
        """fast=True で入力履歴のあるシェイプなら NotImplementedError。"""
        _, mesh = self.plane(history=True)
        before = self.points(mesh)
        for name, call in self._all(mesh, 4):
            with self.subTest(method=name):
                with self.assertRaises(NotImplementedError):
                    call(1.0, fast=True)
                self.assertEqual(self.points(mesh), before)

    def test_out_of_range_and_deleted(self):
        """トポロジー変更で範囲外なら IndexError、シェイプ削除後は RuntimeError。"""
        transform, mesh = self.plane()
        calls = self._all(mesh, 8)
        self.shrinkPlane(transform)
        before = self.points(mesh)
        for name, call in calls:
            with self.subTest(method=name, state="shrunk"):
                with self.assertRaises(IndexError):
                    call(1.0)
                self.assertEqual(self.points(mesh), before)
        cmds.delete(transform)
        for name, call in calls:
            with self.subTest(method=name, state="deleted"):
                with self.assertRaises(RuntimeError):
                    call(1.0)

    def test_valid_write(self):
        """正常系: 1成分だけを変え、他の成分を保つ。"""
        _, mesh = self.plane()
        vertex = Vertex(mesh, 4)
        y, z = vertex.getPositionY(), vertex.getPositionZ()
        vertex.setPositionX(3.0)
        self.assertSequenceAlmostEqual(vertex.getPosition(), (3.0, y, z))
        Vertices(mesh, [0, 1]).setPositionZ([5.0, 6.0])
        self.assertSequenceAlmostEqual(Vertices(mesh, [0, 1]).getPositionZ(), [5.0, 6.0])


class UVSetterErrorTest(_ErrorCase):
    """UV・UVs の書込みの拒否。拒否時は UV を変えない。"""

    def uvs(self, mesh):
        return cmds.polyEditUV(mesh.getFullName() + ".map[*]", query=True)

    def _calls(self, mesh, index):
        uv = UV(mesh, index)
        uvs = UVs(mesh, [0, index])
        return (("UV.setU", uv.setU), ("UV.setV", uv.setV), ("UVs.setU", uvs.setU), ("UVs.setV", uvs.setV),
                ("UVs.setPositions", lambda value, **kwargs: uvs.setPositions(
                    [(value, value)] * 2 if isinstance(value, (int, float)) else value, **kwargs)))

    def test_argument_rejections(self):
        """fast・値の型、非有限値、件数違い。"""
        _, mesh = self.plane()
        before = self.uvs(mesh)
        for name, call in self._calls(mesh, 4):
            for error, args, kwargs in ((TypeError, (0.5,), {"fast": "yes"}), (TypeError, ("a",), {}),
                                        (ValueError, (float("nan"),), {})):
                with self.subTest(method=name, args=args, kwargs=kwargs):
                    with self.assertRaises(error):
                        call(*args, **kwargs)
                    self.assertEqual(self.uvs(mesh), before)
        uvs = UVs(mesh, [0, 4])
        for name, call, error, value in (("UVs.setU", uvs.setU, ValueError, [0.5]),
                                         ("UVs.setV", uvs.setV, ValueError, [0.5, 0.5, 0.5]),
                                         ("UVs.setPositions", uvs.setPositions, ValueError, [(0.5, 0.5)]),
                                         ("UVs.setPositions", uvs.setPositions, ValueError, [(0.5,), (0.5,)]),
                                         ("UVs.setPositions", uvs.setPositions, TypeError, "uv"),
                                         ("UVs.setPositions", uvs.setPositions, TypeError, 5)):
            with self.subTest(method=name, value=value):
                with self.assertRaises(error):
                    call(value)
        self.assertEqual(self.uvs(mesh), before)

    def test_fast_with_history(self):
        """fast=True で inMesh への入力があれば NotImplementedError。"""
        _, mesh = self.plane(history=True)
        before = self.uvs(mesh)
        for name, call in self._calls(mesh, 4):
            with self.subTest(method=name):
                with self.assertRaises(NotImplementedError):
                    call(0.5, fast=True)
                self.assertEqual(self.uvs(mesh), before)

    def test_out_of_range_and_deleted(self):
        """UV数が減って範囲外なら IndexError、メッシュ削除後は RuntimeError。"""
        transform, mesh = self.plane()
        last = cmds.polyEvaluate(mesh.getFullName(), uvcoord=True) - 1
        calls = self._calls(mesh, last)
        self.shrinkPlane(transform)
        self.assertLessEqual(cmds.polyEvaluate(mesh.getFullName(), uvcoord=True), last)
        before = self.uvs(mesh)
        for name, call in calls:
            with self.subTest(method=name, state="shrunk"):
                with self.assertRaises(IndexError):
                    call(0.5)
                self.assertEqual(self.uvs(mesh), before)
        cmds.delete(transform)
        for name, call in calls:
            with self.subTest(method=name, state="deleted"):
                with self.assertRaises(RuntimeError):
                    call(0.5)

    def test_valid_write(self):
        """正常系: U だけを変え、V を保つ。"""
        _, mesh = self.plane()
        uv = UV(mesh, 4)
        v = uv.getV()
        uv.setU(0.25)
        self.assertSequenceAlmostEqual(uv.getPosition(), (0.25, v), places=6)


class JsonRefErrorTest(_ErrorCase):
    """NodeRef・PlugRef・ComponentRef.resolve の mapping の型の拒否と、見つからない場合の None。"""

    def test_resolve_mapping_type(self):
        """mapping が NameMapping・None 以外なら TypeError。"""
        node = self.transform()
        mesh = self.plane()[1]
        refs = (("NodeRef", NodeRef.capture(node)),
                ("PlugRef", PlugRef.capture(node + ".tx")),
                ("ComponentRef", ComponentRef.capture(Vertices(mesh, [0, 1]))))
        for name, ref in refs:
            for mapping in ({}, "a", 5):
                with self.subTest(ref=name, mapping=mapping):
                    with self.assertRaises(TypeError):
                        ref.resolve(mapping)
            with self.subTest(ref=name, mapping="NameMapping"):
                self.assertIsNotNone(ref.resolve(NameMapping()))
                self.assertIsNotNone(ref.resolve())

    def test_resolve_missing(self):
        """対象が無い・範囲外なら例外にせず None。"""
        missing = NodeRef(self.name("noSuchNode"))
        self.assertIsNone(missing.resolve())
        self.assertIsNone(PlugRef(missing, "tx").resolve())
        self.assertIsNone(PlugRef(NodeRef.capture(self.transform()), "noSuchAttr").resolve())
        mesh = self.plane()[1]
        self.assertIsNone(ComponentRef(NodeRef.capture(mesh), "vtx", [100]).resolve())


class SnapshotSaveErrorTest(_ErrorCase):
    """Snapshot.save は書き出せない場合 OSError で、ファイルを残さない。"""

    def setUp(self):
        super().setUp()
        self.folder = tempfile.mkdtemp(prefix="mlibSpecErrSave")

    def tearDown(self):
        shutil.rmtree(self.folder, ignore_errors=True)
        super().tearDown()

    def test_unwritable_destination(self):
        """存在しないフォルダ・既存のフォルダへの書き出し。"""
        snapshot = PoseSnapshot.capture([self.transform()])
        existing_dir = os.path.join(self.folder, "dir")
        os.mkdir(existing_dir)
        for label, path in (("missing folder", os.path.join(self.folder, "missing", "pose.json")),
                            ("directory", existing_dir)):
            with self.subTest(case=label):
                with self.assertRaises(OSError):
                    snapshot.save(path)
                self.assertEqual(sorted(os.listdir(self.folder)), ["dir"])
                self.assertEqual(os.listdir(existing_dir), [])
        path = snapshot.save(os.path.join(self.folder, "pose.json"))
        self.assertTrue(path.is_file())


class MathsErrorTest(unittest.TestCase):
    """EulerRotate.fromDegrees・Quaternion.asCanonicalAxisAngle・asUnitMatrix の拒否。"""

    def test_from_degrees_order(self):
        """未対応の回転順序は ValueError。"""
        for order in ("abc", "xxy", 6, -1):
            with self.subTest(order=order):
                with self.assertRaises(ValueError):
                    EulerRotate.fromDegrees(10, 20, 30, order)
        rotation = EulerRotate.fromDegrees(90, 0, 0, "zyx")
        self.assertAlmostEqual(rotation.x, math.pi / 2)
        self.assertEqual(rotation.orderName, "zyx")

    def test_zero_quaternion(self):
        """ゼロクォータニオンは ValueError で、自身を変えない。"""
        zero = Quaternion(0.0, 0.0, 0.0, 0.0)
        for name in ("asCanonicalAxisAngle", "asUnitMatrix"):
            with self.subTest(method=name):
                with self.assertRaises(ValueError):
                    getattr(zero, name)()
                self.assertEqual([zero.x, zero.y, zero.z, zero.w], [0.0, 0.0, 0.0, 0.0])
        scaled = Quaternion(0.0, 0.0, 0.0, -2.0)
        axis, angle = scaled.asCanonicalAxisAngle()
        self.assertEqual([axis.x, axis.y, axis.z], [1.0, 0.0, 0.0])
        self.assertAlmostEqual(angle, 0.0)
        self.assertEqual([scaled.x, scaled.y, scaled.z, scaled.w], [0.0, 0.0, 0.0, -2.0])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

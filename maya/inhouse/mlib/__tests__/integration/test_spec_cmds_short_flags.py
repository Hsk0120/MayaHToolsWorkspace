"""mlib.cmds の作成関数が受ける Maya コマンドの短縮名の仕様テスト(12.2.0)。

createIkHandle(sj・ee・sol・n・c)・bindSkin(mi)・bakeResults(at・t・sb)・bakeDeformer(mi)と、
createCurve・createCircle・createLocator・createPoly*・createBlendShape・createContainer・
createDagContainer・createDagPose の n 等について、短縮名が長名と同じ結果になること、
長名と短縮名の同時指定が TypeError でノードを残さないことを subTest で確かめる。
"""

import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


def _rounded(values, places=4):
    """数値の列を丸めたリストにする(cmds の照会結果の比較用)。"""
    return [round(value, places) for value in values or []]


def _points(shape):
    """メッシュの頂点またはカーブのCVのオブジェクト空間の座標を返す。"""
    component = ".vtx[*]" if cmds.nodeType(str(shape)) == "mesh" else ".cv[*]"
    return _rounded(cmds.xform(str(shape) + component, query=True, objectSpace=True, translation=True))


def _leaf(node):
    """ノードの、DAGパスを除いた名前(名前空間を含む)を返す。"""
    return node.getFullName().split("|")[-1] if hasattr(node, "getFullName") else str(node)


class _ShortFlagCase(NamespaceCase):
    """一時名前空間を現在の名前空間にして、名前を省略した作成も名前空間内に作る。"""

    PREFIX = "mlibSpecShortFlags_"
    CLEAR_SELECTION = True

    def setUp(self):
        super().setUp()
        self.previous_namespace = cmds.namespaceInfo(currentNamespace=True, absoluteName=True)
        cmds.namespace(set=":" + self.ns)

    def tearDown(self):
        cmds.namespace(set=self.previous_namespace)
        super().tearDown()

    def nodes(self):
        """一時名前空間内のノードの数を返す。"""
        return len(cmds.ls(self.ns + ":*") or [])

    def chain(self, prefix, count=3):
        """Y方向に並ぶjointのチェーンを作り、名前のリストを返す。"""
        cmds.select(clear=True)
        joints = [cmds.joint(name=f"{prefix}{index}", position=(0, index * 2.0, 0)) for index in range(count)]
        cmds.select(clear=True)
        return [cmds.ls(joint, long=True)[0] for joint in joints]

    def assertSameResult(self, function, longFlags, shortFlags, probe, args=()):
        """長名と短縮名で作った結果を probe で比べる。"""
        expected = probe(function(*args(), **longFlags) if callable(args) else function(*args, **longFlags))
        actual = probe(function(*args(), **shortFlags) if callable(args) else function(*args, **shortFlags))
        self.assertEqual(actual, expected)

    def assertConflict(self, function, args, flags):
        """長名と短縮名の同時指定は TypeError で、ノードを残さない。"""
        before = self.nodes()
        with self.assertRaises(TypeError):
            function(*args, **flags)
        self.assertEqual(self.nodes(), before)


class ShapeCreatorShortFlagsTest(_ShortFlagCase):
    """形状の作成関数の短縮名。"""

    def test_curve_and_circle(self):
        """createCurve の d・n、createCircle の r・nr・s・d・n。"""
        points = [(0, 0, 0), (1, 0, 0), (2, 1, 0), (3, 0, 0)]

        def curve_probe(shape):
            return cmds.getAttr(str(shape) + ".degree"), _points(shape)

        with self.subTest(function="createCurve", flag="d"):
            self.assertSameResult(mlib.createCurve, {"degree": 3}, {"d": 3}, curve_probe, args=(points,))
        with self.subTest(function="createCircle", flags="r nr s d"):
            self.assertSameResult(mlib.createCircle,
                                  {"radius": 2.5, "normal": (0, 1, 0), "sections": 6, "degree": 1},
                                  {"r": 2.5, "nr": (0, 1, 0), "s": 6, "d": 1}, curve_probe)
        for function, args in ((mlib.createCurve, (points,)), (mlib.createCircle, ())):
            with self.subTest(function=function.__name__, flag="n"):
                shape = function(*args, n=function.__name__ + "Short")
                self.assertEqual(_leaf(shape.getTransform()), self.name(function.__name__ + "Short"))

    def test_locator_name(self):
        """createLocator の n。parent の短縮名 p は無い(spaceLocator の p は position)。"""
        shape = mlib.createLocator(n="shortLocator")
        self.assertEqual(_leaf(shape.getTransform()), self.name("shortLocator"))
        with self.assertRaises(TypeError):
            mlib.createLocator(p=None)

    def test_poly_shapes(self):
        """createPolyCube の w・h・d・n、createPolySphere の r・ax・n、createPolyCylinder の r・h・ax・n、
        createPolyPlane の w・h・ax・n。"""
        cases = (
            (mlib.createPolyCube, {"width": 2.0, "height": 3.0, "depth": 4.0}, {"w": 2.0, "h": 3.0, "d": 4.0}),
            (mlib.createPolySphere, {"radius": 2.0, "axis": (1, 0, 0)}, {"r": 2.0, "ax": (1, 0, 0)}),
            (mlib.createPolyCylinder, {"radius": 0.5, "height": 3.0, "axis": (0, 0, 1)},
             {"r": 0.5, "h": 3.0, "ax": (0, 0, 1)}),
            (mlib.createPolyPlane, {"width": 2.0, "height": 5.0, "axis": (1, 0, 0)},
             {"w": 2.0, "h": 5.0, "ax": (1, 0, 0)}),
        )
        for function, longFlags, shortFlags in cases:
            with self.subTest(function=function.__name__):
                self.assertSameResult(function, longFlags, shortFlags, _points)
                shape = function(n=function.__name__ + "Short")
                self.assertEqual(_leaf(shape.getTransform()), self.name(function.__name__ + "Short"))

    def test_conflicts(self):
        """形状の作成関数で長名と短縮名を同時に指定すると TypeError(False・None の重複も含む)。"""
        points = [(0, 0, 0), (1, 0, 0)]
        cases = (
            (mlib.createCurve, (points,), {"degree": 1, "d": 1}),
            (mlib.createCurve, (points,), {"name": None, "n": "a"}),
            (mlib.createCircle, (), {"radius": 1.0, "r": 1.0}),
            (mlib.createCircle, (), {"normal": (0, 1, 0), "nr": (0, 1, 0)}),
            (mlib.createCircle, (), {"sections": 8, "s": 8}),
            (mlib.createCircle, (), {"degree": 3, "d": 3}),
            (mlib.createCircle, (), {"name": "a", "n": "a"}),
            (mlib.createLocator, (), {"name": "a", "n": "a"}),
            (mlib.createPolyCube, (), {"width": 1.0, "w": 1.0}),
            (mlib.createPolyCube, (), {"height": 1.0, "h": 1.0}),
            (mlib.createPolyCube, (), {"depth": 1.0, "d": 1.0}),
            (mlib.createPolyCube, (), {"name": "a", "n": "a"}),
            (mlib.createPolySphere, (), {"radius": 1.0, "r": 1.0}),
            (mlib.createPolySphere, (), {"axis": (0, 1, 0), "ax": (0, 1, 0)}),
            (mlib.createPolySphere, (), {"name": "a", "n": "a"}),
            (mlib.createPolyCylinder, (), {"radius": 1.0, "r": 1.0}),
            (mlib.createPolyCylinder, (), {"height": 1.0, "h": 1.0}),
            (mlib.createPolyCylinder, (), {"axis": (0, 1, 0), "ax": (0, 1, 0)}),
            (mlib.createPolyCylinder, (), {"name": "a", "n": "a"}),
            (mlib.createPolyPlane, (), {"width": 1.0, "w": 1.0}),
            (mlib.createPolyPlane, (), {"height": 1.0, "h": 1.0}),
            (mlib.createPolyPlane, (), {"axis": (0, 1, 0), "ax": (0, 1, 0)}),
            (mlib.createPolyPlane, (), {"name": "a", "n": "a"}),
        )
        for function, args, flags in cases:
            with self.subTest(function=function.__name__, flags=sorted(flags)):
                self.assertConflict(function, args, flags)


class NodeCreatorShortFlagsTest(_ShortFlagCase):
    """コンテナ・dagPose・blendShape の作成関数の短縮名。"""

    def test_containers_and_dag_pose(self):
        """createContainer・createDagContainer の n、createDagPose の n・bp。"""
        for function in (mlib.createContainer, mlib.createDagContainer):
            with self.subTest(function=function.__name__):
                node = function(n=function.__name__ + "Short")
                self.assertEqual(_leaf(node), self.name(function.__name__ + "Short"))
                self.assertConflict(function, (), {"name": "a", "n": "a"})
        joints = self.chain("pose")
        with self.subTest(function="createDagPose"):
            self.assertSameResult(mlib.createDagPose, {"bindPose": True}, {"bp": True},
                                  lambda pose: cmds.getAttr(str(pose) + ".bindPose"), args=(joints[0],))
            pose = mlib.createDagPose(joints[0], n="poseShort")
            self.assertEqual(_leaf(pose), self.name("poseShort"))
            self.assertConflict(mlib.createDagPose, (joints[0],), {"name": "a", "n": "a"})
            self.assertConflict(mlib.createDagPose, (joints[0],), {"bindPose": False, "bp": False})

    def test_blend_shape(self):
        """createBlendShape の n・foc。foc=False は frontOfChain=False と同じくデフォーマーの最後に置く。"""

        def base_with_cluster():
            base = cmds.polyCube(name="base#")[0]
            cmds.cluster(base)
            return base, [cmds.polyCube(name="target#")[0]]

        def order(blend):
            geometry = cmds.blendShape(str(blend), query=True, geometry=True)[0]
            history = cmds.ls(cmds.listHistory(geometry), type="geometryFilter")
            return [cmds.nodeType(node) for node in history]

        self.assertSameResult(mlib.createBlendShape, {"frontOfChain": False}, {"foc": False}, order,
                              args=base_with_cluster)
        blend = mlib.createBlendShape(*base_with_cluster(), n="blendShort")
        self.assertEqual(_leaf(blend), self.name("blendShort"))
        base, targets = base_with_cluster()
        self.assertConflict(mlib.createBlendShape, (base, targets), {"name": "a", "n": "a"})
        self.assertConflict(mlib.createBlendShape, (base, targets), {"frontOfChain": True, "foc": True})


class RigCreatorShortFlagsTest(_ShortFlagCase):
    """createIkHandle・bindSkin・bakeResults・bakeDeformer の短縮名(以前は TypeError で拒否していたもの)。"""

    def test_ik_handle(self):
        """createIkHandle の sj・ee・sol・n・c は長名と同じハンドルを作る。"""
        def probe(handle):
            name = str(handle)
            solver = cmds.listConnections(name + ".ikSolver") or []
            joints = cmds.ikHandle(name, query=True, jointList=True)
            return [cmds.nodeType(solver[0]) if solver else None, len(joints)]

        first, second = self.chain("ikLong"), self.chain("ikShort")
        long_handle = mlib.createIkHandle(startJoint=first[0], endJoint=first[2], solver="ikSCsolver", name="ikL")
        short_handle = mlib.createIkHandle(sj=second[0], ee=second[2], sol="ikSCsolver", n="ikS")
        self.assertEqual(_leaf(short_handle), self.name("ikS"))
        self.assertEqual(probe(short_handle), probe(long_handle))
        self.assertEqual(probe(short_handle)[0], "ikSCsolver")
        self.assertEqual(cmds.ls(cmds.ikHandle(str(short_handle), query=True, startJoint=True), long=True),
                         [second[0]])

        spline = self.chain("ikSpline", 4)
        curve = cmds.curve(degree=3, point=[(0, 0, 0), (0, 2, 0), (0, 4, 0), (0, 6, 0)], name="ikCurve")
        handle = mlib.createIkHandle(spline[0], spline[3], solver="ikSplineSolver", c=curve)
        self.assertEqual(handle.getCurve().getFullName(), cmds.ls(curve, long=True)[0])

        third = self.chain("ikConflict")
        for flags in ({"startJoint": third[0], "sj": third[0], "endJoint": third[2]},
                      {"startJoint": third[0], "endJoint": third[2], "ee": third[2]},
                      {"startJoint": third[0], "endJoint": third[2], "solver": "ikSCsolver", "sol": "ikSCsolver"},
                      {"startJoint": third[0], "endJoint": third[2], "name": None, "n": "a"},
                      {"startJoint": third[0], "endJoint": third[2], "curve": None, "c": None}):
            with self.subTest(flags=sorted(flags)):
                self.assertConflict(mlib.createIkHandle, (), flags)
        with self.subTest(flags="endEffector"):
            # Mayaの長名 endEffector は endJoint(短縮名 ee)で指定するため、kwargs では受け付けない。
            self.assertConflict(mlib.createIkHandle, (third[0], third[2]), {"endEffector": third[2]})

    def test_bind_skin(self):
        """bindSkin の mi は maximumInfluences と同じ最大インフルエンス数でバインドする。"""
        joints = self.chain("bind")

        def mesh():
            return cmds.polyCylinder(height=4, subdivisionsHeight=4)[0]

        self.assertSameResult(mlib.bindSkin, {"maximumInfluences": 2}, {"mi": 2},
                              lambda skin: skin.getMaxInfluences(), args=lambda: (joints, mesh()))
        self.assertEqual(mlib.bindSkin(joints, mesh(), mi=1).getMaxInfluences(), 1)
        self.assertConflict(mlib.bindSkin, (joints, mesh()), {"maximumInfluences": 2, "mi": 2})

    def test_bake_results(self):
        """bakeResults の at・t・sb は attributes・time・sampleBy と同じキーを作る。"""

        def driven():
            node = cmds.createNode("transform", name="baked#")
            cmds.expression(string=f"{node}.translateX = frame; {node}.translateY = frame * 2;")
            return (node,)

        def probe(curves):
            plugs = sorted(plug.getLongName() for curve in curves for plug in curve.getDrivenPlugs())
            times = [_rounded(cmds.keyframe(str(curve), query=True, timeChange=True)) for curve in curves]
            return plugs, times

        self.assertSameResult(mlib.bakeResults, {"attributes": ["tx"], "time": (1, 5), "sampleBy": 2},
                              {"at": ["tx"], "t": (1, 5), "sb": 2}, probe, args=driven)
        node = driven()[0]
        for flags in ({"attributes": "tx", "at": "tx"}, {"time": (1, 2), "t": (1, 2)},
                      {"sampleBy": 1, "sb": 1}, {"attribute": "tx"}):
            with self.subTest(flags=sorted(flags)):
                with self.assertRaises(TypeError):
                    mlib.bakeResults(node, **flags)
                self.assertFalse(cmds.listConnections(node + ".translateX", source=True, destination=False,
                                                      type="animCurve"))

    def test_bake_deformer(self):
        """bakeDeformer の mi は maxInfluences と同じウェイトを焼き込む。"""
        joints = self.chain("bake")
        mesh = cmds.polyCylinder(name="bakeGeo", height=4, subdivisionsHeight=8)[0]
        cmds.move(0, 2, 0, mesh)
        cmds.skinCluster(joints, mesh, toSelectedBones=True, maximumInfluences=3)
        cmds.deltaMush(mesh)

        def target():
            return (mesh, joints[0], cmds.duplicate(mesh, name="bakeTarget#")[0])

        def probe(skin):
            return _rounded(skin.getWeights(joints), 3)

        self.assertSameResult(mlib.bakeDeformer, {"maxInfluences": 2}, {"mi": 2}, probe, args=target)
        self.assertConflict(mlib.bakeDeformer, target(), {"maxInfluences": 2, "mi": 2})


if __name__ == "__main__":
    unittest.main()

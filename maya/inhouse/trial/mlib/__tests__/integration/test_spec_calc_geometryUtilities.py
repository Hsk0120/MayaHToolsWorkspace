"""形状を参照する計算ノードと、テクスチャ配置のユーティリティノードの仕様を固定する。

担当A。distanceBetween・pointOnCurveInfo・pointOnSurfaceInfo・curveInfo の評価を
MFnNurbsCurve・MFnNurbsSurface・MMatrixで独立に求めた値と突き合わせ、
file・texture2d・place2dTexture のパス・色空間・接続の約束を確かめる。
"""

import math
import unittest
from unittest import mock

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib.util import _ArgumentError


def _dag(name):
    """名前からMDagPathを返す。"""
    selection = om2.MSelectionList()
    selection.add(name)
    return selection.getDagPath(0)


class _GeometryCase(unittest.TestCase):
    """専用名前空間・cm/rad・Undo有効で実行し、終了時に戻す。"""

    def setUp(self):
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="rad")
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibSpecAGeometry")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.undoInfo(state=self.undo_state)

    def assertClose(self, actual, expected, places=5):
        """成分列を許容誤差付きで比較する。"""
        actual, expected = tuple(actual), tuple(expected)
        self.assertEqual(len(actual), len(expected), (actual, expected))
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places, msg=(actual, expected))

    def make_curve(self):
        """移動・回転・スケールしたTransformの下の3次カーブ(パラメーター0〜2)を作る。"""
        curve = cmds.curve(d=3, p=[(0, 0, 0), (1, 2, 0), (3, 2, 1), (4, 0, 0), (6, 1, 0)])
        cmds.xform(curve, translation=(1, 2, 3), rotation=(10, 20, 30), scale=(2, 2, 2))
        return curve

    def sentinel(self):
        """fastがUndoに残らないことを確かめる目印のUndo対象操作。"""
        name = cmds.createNode("transform")
        cmds.setAttr(name + ".tx", 5)
        return name


class DistanceBetweenTest(_GeometryCase):
    """distanceBetweenの点・Transform接続・距離。"""

    def test_set_points_distance(self):
        """setPointsは各点をそのまま書き、getDistanceはユークリッド距離を返す。"""
        node = mlib.createNode("distanceBetween")
        self.assertEqual(node.getDistance(), 0.0)
        self.assertIs(node.setPoints((0, 0, 0), (3, 4, 0)), node)
        self.assertAlmostEqual(node.getDistance(), 5.0)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDistanceBetweenSetPoints")
        cmds.undo()
        self.assertClose(node.getPlug("point1").get(), (0, 0, 0))
        self.assertClose(node.getPlug("point2").get(), (0, 0, 0))
        cmds.redo()
        self.assertAlmostEqual(node.getDistance(), 5.0)

    def test_set_points_validation(self):
        """両方の点を検証してから書く。不正値では何も変えない。"""
        node = mlib.createNode("distanceBetween").setPoints((1, 2, 3), (4, 5, 6))
        cases = ((((0, 0), (1, 1, 1)), ValueError), (((0, 0, 0), (1, 1, float("nan"))), ValueError),
                 ((("abc"), (1, 1, 1)), ValueError), (((0, 0, 0), None), TypeError),
                 (((0, 0, 0, 0), (1, 1, 1)), ValueError))
        for args, error in cases:
            for fast in (False, True):
                with self.subTest(args=args, fast=fast):
                    with self.assertRaises(error):
                        node.setPoints(*args, fast=fast)
                    self.assertClose(node.getPlug("point1").get(), (1, 2, 3))
                    self.assertClose(node.getPlug("point2").get(), (4, 5, 6))
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.setPoints((0, 0, 0), (0, 0, 0), fast=1)

    def test_set_points_fast_and_units(self):
        """fastはUndoに残らない。UI単位をmmにしても、setPoints・getDistanceはcmのまま。"""
        node = mlib.createNode("distanceBetween")
        sentinel = self.sentinel()
        with mock.patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")):
            node.setPoints((1, 0, 0), (1, 0, 2), fast=True)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + ".tx"), 0)
        self.assertAlmostEqual(node.getDistance(), 2.0)
        cmds.currentUnit(linear="mm")
        node.setPoints((0, 0, 0), (3, 4, 0))
        # mlibは常にcm。distanceの型はMaya 2027でdouble(単位なし)、それ以前はdoubleLinear(距離)で、
        # cmds.getAttrの値だけが版により変わる。
        self.assertAlmostEqual(node.getDistance(), 5.0)
        linear = cmds.attributeQuery("distance", node=node.getFullName(), attributeType=True) == "doubleLinear"
        factor = 10.0 if linear else 1.0
        self.assertAlmostEqual(cmds.getAttr(node.getFullName() + ".distance"), 5.0 * factor)
        self.assertClose(cmds.getAttr(node.getFullName() + ".point2")[0], (3 * factor, 4 * factor, 0))
        node.setPoints((0, 0, 0), (0, 0, 2), fast=True)
        self.assertAlmostEqual(node.getDistance(), 2.0)
        self.assertClose(cmds.getAttr(node.getFullName() + ".point2")[0], (0, 0, 2 * factor))

    def test_connect_transforms(self):
        """ワールドマトリクスを接続し、点をリセットして原点間の距離を測る。点は各空間で変換される。"""
        first = cmds.createNode("transform")
        second = cmds.createNode("transform")
        cmds.xform(first, translation=(1, 2, 3), rotation=(0.3, 0.2, 0.1))
        cmds.xform(second, translation=(4, -2, 3), scale=(2, 2, 2))
        node = mlib.createNode("distanceBetween").setPoints((9, 9, 9), (8, 8, 8))
        self.assertIs(node.connectTransforms(first, mlib.getNode(second)), node)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDistanceBetweenConnectTransforms")
        self.assertClose(node.getPlug("point1").get(), (0, 0, 0))
        self.assertClose(node.getPlug("point2").get(), (0, 0, 0))
        self.assertAlmostEqual(node.getDistance(), 5.0)
        for number, name in ((1, first), (2, second)):
            self.assertEqual(cmds.listConnections("%s.inMatrix%d" % (node.getFullName(), number),
                                                  source=True, plugs=True), [name + ".worldMatrix"])
        node.setPoints((1, 0, 0), (0, 1, 0))
        p1 = om2.MPoint(1, 0, 0) * _dag(first).inclusiveMatrix()
        p2 = om2.MPoint(0, 1, 0) * _dag(second).inclusiveMatrix()
        self.assertAlmostEqual(node.getDistance(), p1.distanceTo(p2), places=5)
        cmds.undo()
        cmds.undo()
        self.assertIsNone(cmds.listConnections(node.getFullName() + ".inMatrix1", source=True))
        self.assertClose(node.getPlug("point1").get(), (9, 9, 9))

    def test_connect_transforms_errors(self):
        """型の不一致は変更前に拒否し、既存接続による失敗では先行した点のリセットが残る。"""
        first = cmds.createNode("transform")
        locator = cmds.spaceLocator()[0]
        shape = cmds.listRelatives(locator, shapes=True, fullPath=True)[0]
        node = mlib.createNode("distanceBetween").setPoints((1, 1, 1), (2, 2, 2))
        for bad in (shape, mlib.createNode("composeMatrix")):
            with self.assertRaisesRegex(TypeError, "Both inputs must be transforms"):
                node.connectTransforms(first, bad)
        self.assertClose(node.getPlug("point1").get(), (1, 1, 1))
        node.connectTransforms(first, locator)
        node.setPoints((1, 1, 1), (2, 2, 2))
        with self.assertRaises(RuntimeError):
            node.connectTransforms(locator, first)
        # 点のリセットは戻さない(docstringの「失敗時の先行変更は戻さない」)。
        self.assertClose(node.getPlug("point1").get(), (0, 0, 0))
        self.assertIs(node.connectTransforms(locator, first, f=True), node)
        self.assertEqual(cmds.listConnections(node.getFullName() + ".inMatrix1", source=True), [locator])
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'force' and 'f'"):
            node.connectTransforms(first, locator, force=True, f=True)

    def test_connect_transforms_instance(self):
        """インスタンスのDAGパスでは、そのインスタンス番号のworldMatrixを接続する。"""
        parent = cmds.createNode("transform")
        child = cmds.createNode("transform", parent=parent)
        copy = cmds.instance(parent)[0]
        paths = cmds.ls(child, allPaths=True, long=True)
        self.assertEqual(len(paths), 2)
        second = [path for path in paths if path.startswith("|" + copy)][0]
        node = mlib.createNode("distanceBetween")
        node.connectTransforms(parent, second)
        self.assertTrue(cmds.connectionInfo(node.getFullName() + ".inMatrix2", sourceFromDestination=True)
                        .endswith(".worldMatrix[1]"))
        self.assertTrue(cmds.connectionInfo(node.getFullName() + ".inMatrix1", sourceFromDestination=True)
                        .endswith(".worldMatrix[0]"))


class PointOnCurveInfoTest(_GeometryCase):
    """pointOnCurveInfoとMFnNurbsCurve。"""

    def test_connect_and_evaluate(self):
        """ワールド空間の位置・接線・法線がMFnNurbsCurveの値と一致する。"""
        curve = self.make_curve()
        fn = om2.MFnNurbsCurve(_dag(curve).extendToShape())
        node = mlib.createNode("pointOnCurveInfo")
        self.assertIs(node.connectCurve(curve), node)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibCalculationEdit")
        for parameter in (0.0, 0.3, 1.0, 1.7, 2.0):
            with self.subTest(parameter=parameter):
                self.assertIs(node.setParameter(parameter), node)
                point = fn.getPointAtParam(parameter, om2.MSpace.kWorld)
                self.assertClose(node.getPosition(), (point.x, point.y, point.z))
                self.assertIsInstance(node.getPosition(), mlib.maths.Vector)
                tangent = fn.tangent(parameter, om2.MSpace.kWorld)
                self.assertClose(node.getTangent(), tuple(tangent))
                self.assertClose(om2.MVector(*node.getTangent(False)).normal(), tuple(tangent))
                normal = node.getNormal()
                self.assertAlmostEqual(om2.MVector(*normal).length(), 1.0, places=5)
                self.assertAlmostEqual(om2.MVector(*normal) * tangent, 0.0, places=5)
                self.assertClose(om2.MVector(*node.getNormal(False)).normal(), normal)

    def test_percentage_and_local_space(self):
        """percentageは0〜1をパラメーター範囲へ写す。worldSpace=Falseはlocalを接続する。"""
        curve = self.make_curve()
        fn = om2.MFnNurbsCurve(_dag(curve).extendToShape())
        start, end = fn.knotDomain
        node = mlib.createNode("pointOnCurveInfo").connectCurve(curve, ws=False)
        self.assertTrue(cmds.listConnections(node.getFullName() + ".inputCurve", source=True, plugs=True)[0]
                        .endswith(".local"))
        node.setParameter(0.25, True)
        self.assertTrue(node.getPlug("turnOnPercentage").get())
        point = fn.getPointAtParam(start + 0.25 * (end - start), om2.MSpace.kObject)
        self.assertClose(node.getPosition(), (point.x, point.y, point.z))
        node.setParameter(1.5, percentage=False)
        self.assertFalse(node.getPlug("turnOnPercentage").get())
        self.assertAlmostEqual(node.getPlug("parameter").get(), 1.5)

    def test_parameter_validation_undo_fast(self):
        """値・percentageを検証してから書き、通常は1回のUndoで戻り、fastはUndoに残らない。"""
        node = mlib.createNode("pointOnCurveInfo")
        node.setParameter(0.5, True)
        cases = ((("x",), ValueError), ((float("inf"),), ValueError), ((1.5, True), ValueError),
                 ((-0.1, True), ValueError), ((0.5, 1), TypeError), ((None,), TypeError))
        for args, error in cases:
            for fast in (False, True):
                with self.subTest(args=args, fast=fast):
                    with self.assertRaises(error):
                        node.setParameter(*args, fast=fast)
                    self.assertAlmostEqual(node.getPlug("parameter").get(), 0.5)
                    self.assertTrue(node.getPlug("turnOnPercentage").get())
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.setParameter(0.2, fast=None)
        node.setParameter(1.25)
        cmds.undo()
        self.assertAlmostEqual(node.getPlug("parameter").get(), 0.5)
        self.assertTrue(node.getPlug("turnOnPercentage").get())
        sentinel = self.sentinel()
        with mock.patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")):
            node.setParameter(1.0, fast=True)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + ".tx"), 0)
        self.assertAlmostEqual(node.getPlug("parameter").get(), 1.0)
        for value in (1, None, "True"):
            with self.assertRaisesRegex(TypeError, "Expected bool"):
                node.getNormal(value)
            with self.assertRaisesRegex(TypeError, "Expected bool"):
                node.getTangent(value)

    def test_connect_curve_rules(self):
        """シェイプ・Transformを受け付け、既存接続はforceでだけ置換し、型違いは拒否する。"""
        curve = self.make_curve()
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        node = mlib.createNode("pointOnCurveInfo").connectCurve(shape)
        path = node.getFullName() + ".inputCurve"
        with self.assertRaises(RuntimeError):
            node.connectCurve(curve, worldSpace=False)
        self.assertIs(node.connectCurve(curve, worldSpace=False, f=True), node)
        self.assertTrue(cmds.listConnections(path, source=True, plugs=True)[0].endswith(".local"))
        cmds.undo()
        self.assertTrue(cmds.listConnections(path, source=True, plugs=True)[0].endswith(".worldSpace"))
        cube = cmds.polyCube()[0]
        fresh = mlib.createNode("pointOnCurveInfo")
        with self.assertRaisesRegex(ValueError, "exactly one matching shape"):
            fresh.connectCurve(cube)
        with self.assertRaisesRegex(TypeError, "Expected a nurbsCurve"):
            fresh.connectCurve(cmds.listRelatives(cube, shapes=True, fullPath=True)[0])
        with self.assertRaisesRegex(TypeError, "Expected bool"):
            fresh.connectCurve(curve, worldSpace=1)
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'worldSpace' and 'ws'"):
            fresh.connectCurve(curve, True, ws=True)
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'force' and 'f'"):
            fresh.connectCurve(curve, force=True, f=True)
        self.assertIsNone(cmds.listConnections(fresh.getFullName() + ".inputCurve", source=True))
        self.assertFalse(hasattr(fresh, "getParameter"))


class PointOnSurfaceInfoTest(_GeometryCase):
    """pointOnSurfaceInfoとMFnNurbsSurface。"""

    def make_surface(self):
        """変形したTransformの下のNURBS平面(パラメーター0〜1)を作る。"""
        surface = cmds.nurbsPlane(axis=(0, 1, 0), width=4, lengthRatio=1, degree=3, u=2, v=2)[0]
        cmds.move(0, 1, 0, surface + ".cv[1][1]", relative=True)
        cmds.xform(surface, translation=(1, 2, 3), rotation=(0.2, 0.4, 0.1))
        return surface

    def test_connect_and_evaluate(self):
        """位置・法線・U/V接線がMFnNurbsSurfaceのワールド空間の値と一致する。"""
        surface = self.make_surface()
        fn = om2.MFnNurbsSurface(_dag(surface).extendToShape())
        node = mlib.createNode("pointOnSurfaceInfo")
        self.assertIs(node.connectSurface(surface), node)
        for u, v in ((0.2, 0.3), (0.5, 0.5), (0.9, 0.1)):
            with self.subTest(u=u, v=v):
                self.assertIs(node.setParameters(u, v), node)
                self.assertEqual(node.getParameters(), (u, v))
                point = fn.getPointAtParam(u, v, om2.MSpace.kWorld)
                self.assertClose(node.getPosition(), (point.x, point.y, point.z))
                normal = fn.normal(u, v, om2.MSpace.kWorld).normal()
                self.assertClose(node.getNormal(), tuple(normal))
                self.assertClose(om2.MVector(*node.getNormal(False)).normal(), tuple(normal))
                tangent_u, tangent_v = fn.tangents(u, v, om2.MSpace.kWorld)
                self.assertClose(node.getTangent("u"), tuple(tangent_u.normal()))
                self.assertClose(node.getTangent(direction="v"), tuple(tangent_v.normal()))
                self.assertClose(om2.MVector(*node.getTangent("u", False)).normal(), tuple(tangent_u.normal()))

    def test_parameters_validation_undo(self):
        """U/V・percentageを検証してから書き、1回のUndoで3つとも戻る。"""
        surface = self.make_surface()
        node = mlib.createNode("pointOnSurfaceInfo").connectSurface(surface, False)
        self.assertTrue(cmds.listConnections(node.getFullName() + ".inputSurface", source=True, plugs=True)[0]
                        .endswith(".local"))
        node.setParameters(0.5, 0.5, True)
        cases = (((0.5, -0.1, True), ValueError), ((1.1, 0.5, True), ValueError), (("x", 0.5), ValueError),
                 ((0.5, float("nan")), ValueError), ((0.5, 0.5, 0), TypeError))
        for args, error in cases:
            for fast in (False, True):
                with self.subTest(args=args, fast=fast):
                    with self.assertRaises(error):
                        node.setParameters(*args, fast=fast)
                    self.assertEqual(node.getParameters(), (0.5, 0.5))
        node.setParameters(0.25, 0.75)
        self.assertFalse(node.getPlug("turnOnPercentage").get())
        cmds.undo()
        self.assertEqual(node.getParameters(), (0.5, 0.5))
        self.assertTrue(node.getPlug("turnOnPercentage").get())
        sentinel = self.sentinel()
        with mock.patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")):
            node.setParameters(0.0, 1.0, True, fast=True)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + ".tx"), 0)
        self.assertEqual(node.getParameters(), (0.0, 1.0))
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.setParameters(0.1, 0.1, fast="no")
        for bad in ("U", "w", None):
            with self.assertRaisesRegex(ValueError, "direction must be u or v"):
                node.getTangent(bad)
        with self.assertRaisesRegex(TypeError, "Expected bool"):
            node.getTangent("u", 1)
        with self.assertRaisesRegex(TypeError, "Expected bool"):
            node.getNormal(0)

    def test_connect_surface_rules(self):
        """型違い・既存接続の扱い。"""
        surface = self.make_surface()
        curve = self.make_curve()
        node = mlib.createNode("pointOnSurfaceInfo")
        with self.assertRaisesRegex(ValueError, "exactly one matching shape"):
            node.connectSurface(curve)
        with self.assertRaisesRegex(TypeError, "Expected a nurbsSurface"):
            node.connectSurface(cmds.listRelatives(curve, shapes=True, fullPath=True)[0])
        node.connectSurface(surface)
        with self.assertRaises(RuntimeError):
            node.connectSurface(surface, ws=False)
        node.connectSurface(surface, ws=False, force=True)
        self.assertTrue(cmds.listConnections(node.getFullName() + ".inputSurface", source=True, plugs=True)[0]
                        .endswith(".local"))
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'worldSpace' and 'ws'"):
            node.connectSurface(surface, worldSpace=True, ws=True)


class CurveInfoTest(_GeometryCase):
    """curveInfoとMFnNurbsCurve.length。"""

    def test_arc_length(self):
        """worldSpaceはTransformのスケールを含む長さ、localはオブジェクト空間の長さ。"""
        curve = self.make_curve()
        fn = om2.MFnNurbsCurve(_dag(curve).extendToShape())
        world = mlib.createNode("curveInfo")
        self.assertIs(world.connectCurve(curve), world)
        length = fn.length(1e-7)
        self.assertAlmostEqual(world.getPlug("arcLength").get(), length * 2, places=2)
        local = mlib.createNode("curveInfo").connectCurve(curve, worldSpace=False)
        self.assertAlmostEqual(local.getPlug("arcLength").get(), length, places=2)
        local_length = local.getPlug("arcLength").get()
        cmds.currentUnit(linear="mm")
        # Plug.getは内部単位cm、cmds.getAttrはUI単位mm。
        self.assertAlmostEqual(local.getPlug("arcLength").get(), local_length, places=6)
        self.assertAlmostEqual(cmds.getAttr(local.getFullName() + ".arcLength"), local_length * 10, places=5)

    def test_connect_rules(self):
        """既存接続の置換・Undo・別名の同時指定。"""
        curve = self.make_curve()
        node = mlib.createNode("curveInfo").connectCurve(curve)
        path = node.getFullName() + ".inputCurve"
        with self.assertRaises(RuntimeError):
            node.connectCurve(curve, False)
        node.connectCurve(curve, ws=False, f=True)
        self.assertTrue(cmds.listConnections(path, source=True, plugs=True)[0].endswith(".local"))
        cmds.undo()
        self.assertTrue(cmds.listConnections(path, source=True, plugs=True)[0].endswith(".worldSpace"))
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'force' and 'f'"):
            node.connectCurve(curve, force=False, f=False)
        with self.assertRaisesRegex(TypeError, "Expected a nurbsCurve"):
            mlib.createNode("curveInfo").connectCurve(cmds.listRelatives(cmds.polyCube()[0], shapes=True)[0])


class TextureNodesTest(_GeometryCase):
    """file・texture2d・place2dTexture。"""

    def test_file_path(self):
        """パスはトークンを展開せずそのまま保持し、str以外はTypeError。Undoで戻る。"""
        node = mlib.createNode("file")
        self.assertEqual(node.getFilePath(), "")
        for path in ("C:/tex/a.<UDIM>.png", "relative/b_<f>.exr", "", "no_such_file_specA.tif"):
            with self.subTest(path=path):
                self.assertIs(node.setFilePath(path), node)
                self.assertEqual(node.getFilePath(), path)
                self.assertEqual(cmds.getAttr(node.getFullName() + ".fileTextureName"), path)
        node.setFilePath("first.png")
        node.setFilePath("second.png")
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibFileSetPath")
        cmds.undo()
        self.assertEqual(node.getFilePath(), "first.png")
        for bad in (None, b"x.png", 5):
            with self.assertRaisesRegex(TypeError, "path must be a string"):
                node.setFilePath(bad)
        self.assertEqual(node.getFilePath(), "first.png")

    def test_file_color_space(self):
        """利用可能な色空間名を往復し、Undoで戻る。

        名前は検証せずに保持する(色管理の設定で変わるため)。str以外は値を変えずにTypeError
        (setFilePathと同じ)。
        """
        node = mlib.createNode("file")
        names = cmds.colorManagementPrefs(query=True, inputSpaceNames=True)
        before = node.getColorSpace()
        self.assertIn(before, names)
        target = [name for name in names if name != before][0]
        self.assertIs(node.setColorSpace(target), node)
        self.assertEqual(node.getColorSpace(), target)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibFileSetColorSpace")
        cmds.undo()
        self.assertEqual(node.getColorSpace(), before)
        node.setColorSpace("NoSuchColorSpace_specA")
        self.assertEqual(node.getColorSpace(), "NoSuchColorSpace_specA")
        for bad in (3, None, b"sRGB", ("sRGB",)):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(TypeError, "name must be a string"):
                    node.setColorSpace(bad)
                self.assertEqual(node.getColorSpace(), "NoSuchColorSpace_specA")

    def test_place2d_connect_texture(self):
        """標準の配置アトリビュートをすべて接続し、getPlacementで取得できる。再実行は何もしない。"""
        texture = mlib.createNode("file")
        self.assertIsNone(texture.getPlacement())
        place = mlib.createNode("place2dTexture")
        self.assertIs(place.connectTexture(texture), place)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibPlace2dConnect")
        names = ("coverage", "translateFrame", "rotateFrame", "mirrorU", "mirrorV", "stagger", "wrapU", "wrapV",
                 "repeatUV", "offset", "rotateUV", "noiseUV", "vertexUvOne", "vertexUvTwo", "vertexUvThree",
                 "vertexCameraOne")
        pairs = [(n, n) for n in names] + [("outUV", "uvCoord"), ("outUvFilterSize", "uvFilterSize")]
        expected = [(o, d) for o, d in pairs if cmds.attributeQuery(d, node=texture.getFullName(), exists=True)]
        for origin, destination in expected:
            with self.subTest(attr=destination):
                source = cmds.listConnections("%s.%s" % (texture.getFullName(), destination),
                                              source=True, destination=False)
                self.assertEqual(source, [place.getName()])
        connections = cmds.listConnections(place.getFullName(), source=False, destination=True, connections=True)
        self.assertEqual(len(connections) // 2, len(expected))
        placement = texture.getPlacement()
        self.assertIsInstance(placement, mlib.nodes.Place2dTexture)
        self.assertTrue(placement.sameNode(place))
        # 接続済みの再実行は何も変えず、Undoの記録も残さない。
        undo_name = cmds.undoInfo(query=True, undoName=True)
        place.connectTexture(texture)
        self.assertEqual(len(cmds.listConnections(place.getFullName(), source=False, destination=True,
                                                  connections=True)) // 2, len(expected))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        cmds.undo()
        self.assertIsNone(texture.getPlacement())
        self.assertIsNone(cmds.listConnections(place.getFullName(), source=False, destination=True))

    def test_place2d_force_and_errors(self):
        """別の配置ノードの接続はforce/fでだけ置き換える。Texture2d以外はTypeError。"""
        texture = mlib.createNode("checker")
        self.assertIsInstance(texture, mlib.nodes.Texture2d)
        first = mlib.createNode("place2dTexture").connectTexture(texture)
        second = mlib.createNode("place2dTexture")
        with self.assertRaises(RuntimeError):
            second.connectTexture(texture)
        self.assertTrue(texture.getPlacement().sameNode(first))
        second.connectTexture(texture, f=True)
        self.assertTrue(texture.getPlacement().sameNode(second))
        self.assertIsNone(cmds.listConnections(first.getFullName(), source=False, destination=True))
        for bad in (mlib.createNode("composeMatrix"), cmds.createNode("transform")):
            with self.assertRaisesRegex(TypeError, "texture must be Texture2d"):
                second.connectTexture(bad)
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'force' and 'f'"):
            second.connectTexture(texture, force=True, f=True)

    def test_get_placement_other_source(self):
        """uvCoordの入力元が配置ノード以外でも、その入力元ノードを返す。"""
        texture = mlib.createNode("file")
        source = mlib.createNode("place2dTexture")
        cmds.connectAttr(source.getFullName() + ".outUV", texture.getFullName() + ".uvCoord")
        self.assertTrue(texture.getPlacement().sameNode(source))
        cmds.disconnectAttr(source.getFullName() + ".outUV", texture.getFullName() + ".uvCoord")
        other = cmds.createNode("transform")
        cmds.addAttr(other, longName="uvSpecA", attributeType="float2")
        cmds.addAttr(other, longName="uvSpecAU", attributeType="float", parent="uvSpecA")
        cmds.addAttr(other, longName="uvSpecAV", attributeType="float", parent="uvSpecA")
        cmds.connectAttr(other + ".uvSpecA", texture.getFullName() + ".uvCoord")
        placement = texture.getPlacement()
        self.assertIsInstance(placement, mlib.nodes.Transform)
        self.assertEqual(placement.getName(), other)


if __name__ == "__main__":
    unittest.main()

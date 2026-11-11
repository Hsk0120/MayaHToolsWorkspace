"""12.4.0 で形状のシェイプへ足したメソッドと createNurbsPlane を確かめる。

- NurbsSurface.getTangentsAtParam/getMatrixAtParam/getArea(pointOnSurface・手計算と突き合わせ)。
- NurbsCurve.getKnots/isPlanar/getArea/rebuild/reverse(Undo 1回・シェイプのノードを保つ)。
- Mesh.getUVShells とカラーセットの管理(polyColorSet と突き合わせ、Undo 1回)。
- Camera.getFieldOfView/getEyePoint/getViewDirection/getUpDirection/getProjectionMatrix/isOrtho。
- mlib.createNurbsPlane(短縮名・Undo 1回・不正な入力)。
- 不正な入力の例外型と、削除済みノードの RuntimeError。
"""

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase


class _Case(NamespaceCase):
    """形状を作る補助。"""

    PREFIX = "mlibV124Shapes_"

    def surface(self, scale=(1, 1, 1)):
        """幅4・長さ2(lengthRatio 0.5)の NURBS 平面を作り、シェイプのラッパーを返す。"""
        transform = cmds.nurbsPlane(name=self.name("plane#"), width=4, lengthRatio=0.5, patchesU=2, patchesV=1,
                                    axis=(0, 1, 0), constructionHistory=False)[0]
        cmds.setAttr(transform + ".translate", 1, 2, 3)
        cmds.setAttr(transform + ".scale", *scale)
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def curve(self, points, degree=3):
        """点列から NURBS カーブを作り、シェイプのラッパーを返す。"""
        transform = cmds.curve(name=self.name("curve#"), point=points, degree=degree)
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def mesh(self):
        """polyPlane(2x2 分割)を作り、シェイプのラッパーを返す。"""
        transform = cmds.polyPlane(name=self.name("mesh#"), subdivisionsX=2, subdivisionsY=2,
                                   constructionHistory=False)[0]
        return mlib.getNode(cmds.listRelatives(transform, shapes=True, fullPath=True)[0])

    def assertDeletedRaises(self, node, calls):
        """ノードを削除し、各呼出しが RuntimeError になることを確かめる。"""
        cmds.delete(node.getFullName())
        for call in calls:
            with self.subTest(call=call):
                with self.assertRaises(RuntimeError):
                    call(node)


class NurbsSurfaceFrameTest(_Case):
    """NurbsSurface の接線・マトリクス・面積。"""

    def test_tangents_match_point_on_surface(self):
        """接線は pointOnSurface の normalizedTangentU/V と一致し、非均等スケールのワールドでも向きが正しい。"""
        shape = self.surface(scale=(3, 1, 0.5))
        name = shape.getFullName()
        for flag in ({}, {"ws": True}, {"worldSpace": True}):
            with self.subTest(flag=flag):
                tangent_u, tangent_v = shape.getTangentsAtParam(0.3, 0.6, **flag)
                self.assertAlmostEqual(tangent_u.length(), 1.0)
                self.assertAlmostEqual(tangent_v.length(), 1.0)
                expected_u = cmds.pointOnSurface(name, parameterU=0.3, parameterV=0.6, normalizedTangentU=True)
                expected_v = cmds.pointOnSurface(name, parameterU=0.3, parameterV=0.6, normalizedTangentV=True)
                self.assertSequenceAlmostEqual(tangent_u, expected_u, places=6)
                self.assertSequenceAlmostEqual(tangent_v, expected_v, places=6)

    def test_matrix_at_param(self):
        """マトリクスの aim は U の接線、up は法線、位置は getPointAtParam と一致し、軸を変えられる。"""
        shape = self.surface()
        for flag in ({}, {"ws": True}):
            with self.subTest(flag=flag):
                matrix = shape.getMatrixAtParam(0.25, 0.5, **flag)
                tangent_u, _tangent_v = shape.getTangentsAtParam(0.25, 0.5, **flag)
                normal = shape.getNormalAtParam(0.25, 0.5, **flag)
                position = shape.getPointAtParam(0.25, 0.5, **flag)
                rows = [[matrix.getElement(row, column) for column in range(4)] for row in range(4)]
                self.assertSequenceAlmostEqual(rows[0][:3], tangent_u)
                self.assertSequenceAlmostEqual(rows[1][:3], normal)
                self.assertSequenceAlmostEqual(rows[3][:3], position)
                x, y, z = (om2.MVector(*row[:3]) for row in rows[:3])
                self.assertSequenceAlmostEqual(x ^ y, z)
        matrix = shape.getMatrixAtParam(0.25, 0.5, aimAxis="-z", upAxis="x")
        rows = [[matrix.getElement(row, column) for column in range(3)] for row in range(3)]
        self.assertSequenceAlmostEqual([-value for value in rows[2]], shape.getTangentsAtParam(0.25, 0.5)[0])
        self.assertSequenceAlmostEqual(rows[0], shape.getNormalAtParam(0.25, 0.5))

    def test_area(self):
        """面積はローカルで幅×長さ、ワールドではスケールを掛けた値になる。"""
        shape = self.surface(scale=(3, 1, 2))
        self.assertAlmostEqual(shape.getArea(), 4 * 2, places=6)
        self.assertAlmostEqual(shape.getArea(ws=True), 4 * 2 * 3 * 2, places=5)
        self.assertAlmostEqual(shape.getArea(worldSpace=True), shape.getArea(ws=True))

    def test_errors(self):
        """不正な入力の例外型と、削除済みノードの RuntimeError。"""
        shape = self.surface()
        for kwargs, error in (({"aimAxis": "x", "upAxis": "-x"}, ValueError), ({"aimAxis": "w"}, ValueError),
                              ({"aimAxis": 1}, TypeError), ({"worldSpace": 1}, TypeError),
                              ({"worldSpace": True, "ws": True}, TypeError)):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(error):
                    shape.getMatrixAtParam(0.5, 0.5, **kwargs)
        for u, error in ((2.0, ValueError), ("a", TypeError), (float("inf"), ValueError)):
            with self.subTest(u=u):
                with self.assertRaises(error):
                    shape.getTangentsAtParam(u, 0.5)
        with self.assertRaises(TypeError):
            shape.getArea(worldSpace="yes")
        empty = mlib.createNode("nurbsSurface", name=self.name("empty#"))
        for call in (empty.getArea, lambda: empty.getTangentsAtParam(0, 0), lambda: empty.getMatrixAtParam(0, 0)):
            with self.assertRaises(RuntimeError):
                call()
        self.assertDeletedRaises(shape, (lambda node: node.getArea(), lambda node: node.getTangentsAtParam(0, 0),
                                         lambda node: node.getMatrixAtParam(0, 0)))


class NurbsCurveAdditionsTest(_Case):
    """NurbsCurve のノット・平面判定・面積・作り直し・反転。"""

    POINTS = [(0, 0, 0), (1, 1, 0), (2, 0, 1), (3, 1, 0), (4, 0, 0)]

    def test_knots_and_planar(self):
        """getKnots は getAttr の knots と一致し、isPlanar は平面と立体で変わる。"""
        shape = self.curve(self.POINTS)
        info = cmds.createNode("curveInfo", name=self.name("info#"))
        cmds.connectAttr(shape.getFullName() + ".worldSpace[0]", info + ".inputCurve")
        self.assertSequenceAlmostEqual(shape.getKnots(), cmds.getAttr(info + ".knots")[0])
        self.assertEqual(len(shape.getKnots()), shape.getNumCVs() + shape.getDegree() - 1)
        self.assertFalse(shape.isPlanar())
        flat = self.curve([(0, 0, 0), (1, 0, 1), (2, 0, 0), (3, 0, 2)])
        self.assertTrue(flat.isPlanar())

    def test_area(self):
        """正方形(次数1)は辺の2乗、円は πr² にほぼ等しく、ワールドではスケールを含む。開いたカーブは ValueError。"""
        square = self.curve([(0, 0, 0), (2, 0, 0), (2, 0, 2), (0, 0, 2), (0, 0, 0)], degree=1)
        self.assertAlmostEqual(square.getArea(), 4.0, places=9)
        cmds.setAttr(square.getTransform().getFullName() + ".scale", 3, 1, 2)
        self.assertAlmostEqual(square.getArea(ws=True), 4.0 * 6, places=8)
        circle = mlib.createCircle(radius=2.0, sections=16, name=self.name("circle#"))
        # Maya の円は有理でない近似のため、厳密な πr² とは少し違う。
        self.assertAlmostEqual(circle.getArea(), math.pi * 4, delta=math.pi * 4 * 1e-3)
        with self.assertRaises(ValueError):
            self.curve([(0, 0, 0), (1, 0, 1), (2, 0, 0), (3, 0, 2)]).getArea()
        with self.assertRaises(ValueError):
            self.curve([(0, 0, 0), (2, 0, 0), (2, 1, 2), (0, 0, 2), (0, 0, 0)], degree=1).getArea()
        with self.assertRaises(TypeError):
            square.getArea(worldSpace=True, ws=True)

    def test_rebuild_undo(self):
        """rebuild はスパン・次数・範囲を変え、同じシェイプのノードを保ち、Undo 1回で戻る。"""
        shape = self.curve(self.POINTS)
        uuid = cmds.ls(shape.getFullName(), uuid=True)[0]
        before = shape.getCvPositions()
        start = shape.getPointAtParam(shape.getParamRange()[0])
        self.flushUndo()
        self.assertIs(shape.rebuild(6, keepRange="unit"), shape)
        self.assertUndoesInOneStep(
            lambda: self.assertEqual(len(shape.getCvPositions()), len(before)),
            lambda: (self.assertEqual(shape.getNumSpans(), 6), self.assertEqual(shape.getParamRange(), (0.0, 1.0))))
        self.assertEqual(cmds.ls(uuid)[0], cmds.ls(shape.getFullName())[0])
        shape.rebuild(3, 1, keepRange="spans")
        self.assertEqual(shape.getDegree(), 1)
        self.assertEqual(shape.getNumSpans(), 3)
        self.assertSequenceAlmostEqual(shape.getParamRange(), (0.0, 3.0))
        self.assertSequenceAlmostEqual(shape.getPointAtParam(0.0), start)
        spans = shape.getNumSpans()
        shape.rebuild()
        self.assertEqual(shape.getNumSpans(), spans)
        for args, kwargs, error in (((0,), {}, ValueError), ((True,), {}, TypeError), ((2.5,), {}, TypeError),
                                    ((None, 4), {}, ValueError), ((None, "3"), {}, TypeError),
                                    ((), {"keepRange": "keep"}, ValueError), ((), {"keepRange": 1}, TypeError)):
            with self.subTest(args=args, kwargs=kwargs):
                with self.assertRaises(error):
                    shape.rebuild(*args, **kwargs)

    def test_reverse_undo(self):
        """reverse は CV の並びを逆にし、Undo 1回で戻る。"""
        shape = self.curve(self.POINTS)
        before = shape.getCvPositions()
        self.flushUndo()
        self.assertIs(shape.reverse(), shape)
        self.assertUndoesInOneStep(
            lambda: self.assertSequenceAlmostEqual([tuple(p) for p in shape.getCvPositions()],
                                                   [tuple(p) for p in before]),
            lambda: self.assertSequenceAlmostEqual([tuple(p) for p in shape.getCvPositions()],
                                                   [tuple(p) for p in reversed(before)]))

    def test_empty_and_deleted(self):
        """形状データの無いカーブと削除済みのカーブは RuntimeError。"""
        empty = mlib.createNode("nurbsCurve", name=self.name("empty#"))
        for call in (empty.getKnots, empty.isPlanar, empty.getArea, empty.rebuild, empty.reverse):
            with self.subTest(call=call.__name__):
                with self.assertRaises(RuntimeError):
                    call()
        shape = self.curve(self.POINTS)
        self.assertDeletedRaises(shape, (lambda node: node.getKnots(), lambda node: node.isPlanar(),
                                         lambda node: node.rebuild(), lambda node: node.reverse()))


class MeshColorSetTest(_Case):
    """Mesh の UV シェルとカラーセット。"""

    def test_uv_shells(self):
        """UV シェルは getUvShellsIds の分類と一致し、UV を切ると分かれる。存在しない UV セットは ValueError。"""
        shape = self.mesh()
        self.assertEqual(shape.getUVShells(), [list(range(shape.getNumUVs()))])
        name = shape.getFullName()
        cmds.polyMapCut(name + ".e[*]", constructionHistory=False)
        shells = shape.getUVShells(uvSet="map1")
        self.assertEqual(len(shells), 4)
        count, ids = om2.MFnMesh(shape.mpath()).getUvShellsIds("map1")
        self.assertEqual(sorted(sorted(shell) for shell in shells),
                         sorted(sorted(i for i, value in enumerate(ids) if value == shell_id) for shell_id in range(count)))
        self.assertEqual(sorted(index for shell in shells for index in shell), list(range(shape.getNumUVs())))
        self.assertEqual([shell[0] for shell in shells], sorted(shell[0] for shell in shells))
        for shell in shells:
            self.assertEqual(shell, sorted(shell))
        for value, error in (("missing", ValueError), ("", ValueError), (1, TypeError)):
            with self.subTest(uvSet=value):
                with self.assertRaises(error):
                    shape.getUVShells(value)

    def test_color_sets_match_poly_color_set(self):
        """作成・現在・複製・名前変更・削除が polyColorSet の照会と一致し、それぞれ Undo 1回で戻る。"""
        shape = self.mesh()
        name = shape.getFullName()

        def names():
            return cmds.polyColorSet(name, query=True, allColorSets=True) or []

        def current():
            found = cmds.polyColorSet(name, query=True, currentColorSet=True)
            return found[0] if found else None

        self.assertEqual(shape.getColorSetNames(), [])
        self.assertIsNone(shape.getCurrentColorSet())
        self.flushUndo()
        self.assertIs(shape.createColorSet("a"), shape)
        self.assertUndoesInOneStep(lambda: self.assertEqual(names(), []), lambda: self.assertEqual(names(), ["a"]))
        shape.createColorSet("a")
        shape.createColorSet("b")
        self.assertEqual(shape.getColorSetNames(), names())
        self.assertEqual(shape.getCurrentColorSet(), current())
        self.assertEqual(current(), "b")
        self.flushUndo()
        shape.setCurrentColorSet("a")
        self.assertUndoesInOneStep(lambda: self.assertEqual(current(), "b"), lambda: self.assertEqual(current(), "a"))
        self.flushUndo()
        shape.copyColorSet("a", "c")
        self.assertUndoesInOneStep(lambda: self.assertEqual(names(), ["a", "b"]),
                                   lambda: self.assertEqual(names(), ["a", "b", "c"]))
        self.flushUndo()
        shape.renameColorSet("b", "d")
        self.assertUndoesInOneStep(lambda: self.assertEqual(names(), ["a", "b"]),
                                   lambda: self.assertEqual(names(), ["a", "d"]))
        self.flushUndo()
        shape.deleteColorSet("b")
        self.assertUndoesInOneStep(lambda: self.assertEqual(names(), ["a", "b"]),
                                   lambda: self.assertEqual(names(), ["a"]))
        self.assertEqual(shape.getColorSetNames(), ["a", "b"])

    def test_color_set_errors(self):
        """名前の型・空・有無の誤りは TypeError/ValueError で、シーンを変えない。削除済みは RuntimeError。"""
        shape = self.mesh()
        shape.createColorSet("a")
        cases = ((shape.createColorSet, ("a",), ValueError), (shape.createColorSet, ("",), ValueError),
                 (shape.createColorSet, (None,), TypeError), (shape.setCurrentColorSet, ("x",), ValueError),
                 (shape.deleteColorSet, ("x",), ValueError), (shape.renameColorSet, ("x", "y"), ValueError),
                 (shape.renameColorSet, ("a", "a"), ValueError), (shape.copyColorSet, ("a", 1), TypeError),
                 (shape.copyColorSet, ("x", "y"), ValueError))
        for method, args, error in cases:
            with self.subTest(method=method.__name__, args=args):
                with self.assertRaises(error):
                    method(*args)
                self.assertEqual(shape.getColorSetNames(), ["a"])
        self.assertDeletedRaises(shape, (lambda node: node.getColorSetNames(), lambda node: node.getUVShells(),
                                         lambda node: node.createColorSet("z")))


class CameraQueryTest(_Case):
    """Camera の画角・向き・投影。"""

    def camera(self):
        """焦点距離50の透視カメラを作り、(transform, shape) のラッパーを返す。"""
        transform, shape = cmds.camera(name=self.name("cam#"), focalLength=50)
        return mlib.getNode(transform), mlib.getNode(shape)

    def test_field_of_view(self):
        """画角は 2*atan(フィルムバック(インチ)/0.03937/2/焦点距離) と一致し、unit で単位を変えられる。"""
        _transform, shape = self.camera()
        name = shape.getFullName()
        horizontal = 2 * math.atan(cmds.getAttr(name + ".horizontalFilmAperture") / 0.03937 / 2 / 50.0)
        vertical = 2 * math.atan(cmds.getAttr(name + ".verticalFilmAperture") / 0.03937 / 2 / 50.0)
        self.assertSequenceAlmostEqual(shape.getFieldOfView(), (math.degrees(horizontal), math.degrees(vertical)),
                                       places=6)
        self.assertSequenceAlmostEqual(shape.getFieldOfView(unit="rad"), (horizontal, vertical), places=6)
        for unit, error in (("frame", ValueError), (1, TypeError)):
            with self.subTest(unit=unit):
                with self.assertRaises(error):
                    shape.getFieldOfView(unit=unit)

    def test_directions(self):
        """位置・視線・上方向は Transform の配置(xform)と一致し、ローカルは原点・-Z・+Y。"""
        transform, shape = self.camera()
        cmds.xform(transform.getFullName(), translation=(1, 2, 3), rotation=(0, 90, 0), worldSpace=True)
        self.assertSequenceAlmostEqual(shape.getEyePoint(), (1, 2, 3))
        self.assertSequenceAlmostEqual(shape.getEyePoint(ws=False), (0, 0, 0))
        self.assertSequenceAlmostEqual(shape.getViewDirection(), (-1, 0, 0))
        self.assertSequenceAlmostEqual(shape.getViewDirection(worldSpace=False), (0, 0, -1))
        self.assertSequenceAlmostEqual(shape.getUpDirection(), (0, 1, 0))
        cmds.setAttr(transform.getFullName() + ".scale", 2, 2, 2)
        self.assertAlmostEqual(shape.getViewDirection().length(), 1.0)
        with self.assertRaises(TypeError):
            shape.getEyePoint(worldSpace=True, ws=True)
        with self.assertRaises(TypeError):
            shape.getUpDirection(worldSpace=0)

    def test_projection_and_ortho(self):
        """投影マトリクスの [0][0] は 1/tan(水平画角/2) で、カメラ前方の点は画面の中央へ写る。正投影の判定。"""
        _transform, shape = self.camera()
        matrix = shape.getProjectionMatrix()
        self.assertIsInstance(matrix, mlib.Matrix)
        horizontal = shape.getFieldOfView(unit="rad")[0]
        self.assertAlmostEqual(matrix.getElement(0, 0), 1.0 / math.tan(horizontal / 2), places=5)
        point = om2.MPoint(0, 0, -10) * matrix
        self.assertAlmostEqual(point.x / point.w, 0.0)
        self.assertAlmostEqual(point.y / point.w, 0.0)
        self.assertFalse(shape.isOrtho())
        ortho = mlib.getNode(cmds.camera(name=self.name("ortho#"), orthographic=True)[1])
        self.assertTrue(ortho.isOrtho())
        self.assertDeletedRaises(shape, (lambda node: node.getFieldOfView(), lambda node: node.getEyePoint(),
                                         lambda node: node.getProjectionMatrix(), lambda node: node.isOrtho()))


class CreateNurbsPlaneTest(_Case):
    """mlib.createNurbsPlane。"""

    def test_create_and_undo(self):
        """nurbsPlane と同じ形状を作り、短縮名も受け、Undo 1回で消える。"""
        self.flushUndo()
        shape = mlib.createNurbsPlane(width=4.0, lengthRatio=0.25, patchesU=4, patchesV=2, name=self.name("ribbon"))
        self.assertIsInstance(shape, mlib.NurbsSurface)
        transform = shape.getTransform().getFullName()
        self.assertEqual(shape.getFullName().rsplit("|", 1)[-1], self.name("ribbonShape").rsplit("|", 1)[-1])
        self.assertUndoesInOneStep(lambda: self.assertFalse(cmds.objExists(transform)),
                                   lambda: self.assertTrue(cmds.objExists(transform)))
        shape = mlib.createNurbsPlane(w=4.0, lr=0.25, u=4, v=2, d=1, ax=(0, 0, 1), n=self.name("short"))
        self.assertEqual(shape.getNumSpans(), (4, 2))
        self.assertEqual(shape.getDegree(), (1, 1))
        self.assertAlmostEqual(shape.getArea(), 4.0 * 1.0, places=6)
        self.assertAlmostEqual(abs(shape.getNormalAtParam(0.5, 0.5).z), 1.0)
        self.assertFalse(cmds.listConnections(shape.getFullName() + ".create"))
        default = mlib.createNurbsPlane(name=self.name("default"))
        self.assertAlmostEqual(abs(default.getNormalAtParam(0.5, 0.5).y), 1.0)
        self.assertAlmostEqual(default.getArea(), 1.0, places=6)
        parent = self.make("transform", "parent#")
        child = mlib.createNurbsPlane(name=self.name("child"), parent=parent)
        self.assertEqual(child.getTransform().getParent().getFullName(), cmds.ls(parent, long=True)[0])

    def test_units_and_errors(self):
        """幅は UI 単位によらず cm で、不正な入力は例外になりノードを残さない。"""
        cmds.currentUnit(linear="m")
        shape = mlib.createNurbsPlane(width=2.0, name=self.name("cm"))
        cmds.currentUnit(linear="cm")
        self.assertAlmostEqual(shape.getArea(), 4.0, places=6)
        before = set(cmds.ls(self.ns + ":*"))
        cases = (({"width": 0}, ValueError), ({"lengthRatio": float("nan")}, ValueError), ({"patchesU": 0}, ValueError),
                 ({"patchesV": 1.5}, TypeError), ({"axis": (0, 0, 0)}, ValueError), ({"degree": 2}, ValueError),
                 ({"degree": True}, TypeError), ({"width": 1, "w": 1}, TypeError), ({"name": "a|b"}, ValueError),
                 ({"parent": self.name("missing")}, Exception))
        for kwargs, error in cases:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(error):
                    mlib.createNurbsPlane(**kwargs)
        self.assertEqual(set(cmds.ls(self.ns + ":*")), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

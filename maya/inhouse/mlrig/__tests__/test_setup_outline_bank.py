"""OutlineBankの傾きを、OpenMayaで独立に組んだ行列と、傾けた側の縁で床に接すること(支点が動かない・底が床に潜らない)で確かめる。"""

import math
import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import OutlineBank

HALF = 2.0
RADIUS = 3.0


def _world(node):
    """ノードのワールド行列。"""
    return om.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _matrix(plug):
    """matrixのアトリビュートの値。"""
    return om.MMatrix(cmds.getAttr(plug))


def _translate(point):
    """移動だけの行列。"""
    matrix = om.MMatrix()
    for index in range(3):
        matrix.setElement(3, index, point[index])
    return matrix


def _rotation(degrees, order=0):
    """度の回転(Mayaの rotateOrder の番号)の行列。"""
    return om.MEulerRotation([math.radians(value) for value in degrees], order).asMatrix()


def _close(test, first, second, tolerance=1e-4):
    """2つの行列の全成分が誤差の範囲で一致する。"""
    for index, (a, b) in enumerate(zip(first, second)):
        test.assertAlmostEqual(a, b, delta=tolerance, msg="element {}: {} != {}".format(index, list(first), list(second)))


class OutlineBankTest(unittest.TestCase):
    """独立計算との一致・跳ねない・縁で接する・円の輪郭・親の追従・軸とUI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """回転・移動した親の下に、コントロールと一辺4cmの正方形の底の輪郭(床 y=0 の高さ)を置く。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.parent = cmds.createNode("transform", name="floorSpace")
        cmds.setAttr(self.parent + ".translate", 4, 1, -2)
        cmds.setAttr(self.parent + ".rotate", 0, 35, 0)
        self.control = cmds.createNode("transform", name="bankCtrl", parent=self.parent)
        cmds.setAttr(self.control + ".translate", 1, 0, 2)
        corners = [(HALF, 0, HALF), (HALF, 0, -HALF), (-HALF, 0, -HALF), (-HALF, 0, HALF), (HALF, 0, HALF)]
        self.outline = cmds.curve(degree=1, point=[(x + 1, y, z + 2) for x, y, z in corners], name="outline")
        cmds.parent(self.outline, self.parent, relative=True)
        self.setup = OutlineBank.create(self.control, self.outline, name="bank")
        self.owner = str(self.setup.container)

    def _base(self):
        """底の空間(コントロールのワールド行列から回転を除いたもの)。"""
        return _translate(cmds.getAttr(self.control + ".translate")[0]) * _world(self.parent)

    def test_rest_matches_control(self):
        """回転が0なら出力はコントロールのワールド行列と一致し、reachは輪郭の大きさの2倍。"""
        _close(self, _matrix(self.owner + ".matrix"), _world(self.control))
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".reach"), 8.0, places=4)

    def test_edge_pivot_matches_independent(self):
        """面の向きへ傾けると支点は辺の中点になり、行列は ``T(-p) R T(p) B`` と一致する。"""
        cases = (((0, 0, -20), (HALF, 0, 0)), ((0, 0, 25), (-HALF, 0, 0)),
                 ((30, 0, 0), (0, 0, HALF)), ((-15, 0, 0), (0, 0, -HALF)))
        for rotate, pivot in cases:
            with self.subTest(rotate=rotate):
                cmds.setAttr(self.control + ".rotate", *rotate)
                measured = cmds.getAttr(self.owner + ".pivot")[0]
                for a, b in zip(measured, pivot):
                    self.assertAlmostEqual(a, b, delta=1e-4)
                expected = _translate([-v for v in pivot]) * _rotation(rotate) * _translate(pivot) * self._base()
                _close(self, _matrix(self.owner + ".matrix"), expected)
                python = om.MMatrix(list(OutlineBank.localMatrix(_rotation(rotate), pivot))) * self._base()
                _close(self, _matrix(self.owner + ".matrix"), python)

    def test_pivot_stays_on_floor_and_corners_stay_above(self):
        """斜めに傾けても支点は輪郭の上にあって動かない。reachを大きくすると支点が角へ寄り、底の4隅は床(y=0)へ潜らない。

        既定のreach(輪郭の大きさの2倍)では、斜めの向きの支点は角の手前の辺の上にあり、角が少し床へ潜る
        (一辺4cm・14度で約0.11cm)。支点が辺の上を滑らかに移ることとの引き換えで、rstの制限に書く。
        """
        cmds.setAttr(self.owner + ".reach", 1000.0)
        for rotate in ((10, 0, -10), (-20, 0, 5), (12, 0, 18), (40, 0, -30)):
            with self.subTest(rotate=rotate):
                cmds.setAttr(self.control + ".rotate", *rotate)
                pivot = om.MPoint(cmds.getAttr(self.owner + ".pivot")[0])
                self.assertAlmostEqual(max(abs(pivot.x), abs(pivot.z)), HALF, delta=1e-4)
                local = om.MMatrix(list(OutlineBank.localMatrix(_rotation(rotate), pivot)))
                moved = pivot * local
                self.assertAlmostEqual(moved.distanceTo(pivot), 0.0, delta=1e-6)
                for x in (-HALF, HALF):
                    for z in (-HALF, HALF):
                        corner = om.MPoint(x, 0, z) * local
                        self.assertGreater(corner.y, -0.01, (rotate, x, z, corner.y))

    def test_circle_outline_touches_on_tilted_side(self):
        """円の輪郭では支点は傾いた向きの円の上の点で、底の円は床に潜らない。reachを変えても同じ。"""
        circle = cmds.circle(normal=(0, 1, 0), radius=RADIUS, sections=16, constructionHistory=False, name="disc")[0]
        control = cmds.createNode("transform", name="discCtrl")
        setup = OutlineBank.create(control, circle, name="discBank")
        owner = str(setup.container)
        for rotate in ((15, 0, -10), (-25, 0, 30), (5, 0, 0)):
            for reach in (12.0, 100.0):
                with self.subTest(rotate=rotate, reach=reach):
                    cmds.setAttr(owner + ".reach", reach)
                    cmds.setAttr(control + ".rotate", *rotate)
                    direction = OutlineBank.direction(_rotation(rotate))
                    pivot = cmds.getAttr(owner + ".pivot")[0]
                    for a, b in zip(pivot, direction):
                        self.assertAlmostEqual(a, RADIUS * b, delta=0.02)
                    matrix = _matrix(owner + ".matrix")
                    lowest = min((om.MPoint(RADIUS * math.cos(t), 0, RADIUS * math.sin(t)) * matrix).y
                                 for t in [i * math.pi / 90.0 for i in range(180)])
                    self.assertAlmostEqual(lowest, 0.0, delta=0.02)

    def test_follows_translate_and_parent(self):
        """コントロールの移動と親の変化に付いて行き、回転0では常にコントロールと一致する。"""
        cmds.setAttr(self.control + ".translate", 3, 0.5, -1)
        cmds.setAttr(self.parent + ".rotate", 10, 60, 0)
        _close(self, _matrix(self.owner + ".matrix"), _world(self.control))
        cmds.setAttr(self.control + ".rotateZ", -20)
        # 底の空間で輪郭の中心は (1, 0, 2) - (3, 0.5, -1) = (-2, -0.5, 3)。+x側の探す点 (8, 0, 0) に最も近い点は x=0 の辺の z=1 の端。
        pivot = cmds.getAttr(self.owner + ".pivot")[0]
        for a, b in zip(pivot, (0.0, -0.5, 1.0)):
            self.assertAlmostEqual(a, b, delta=1e-4)

    def test_axis_order_and_ui_units(self):
        """上の軸 z・rotateOrder・UI単位(m・rad)でも引数と出力はcm・内部単位のまま一致する。"""
        cmds.file(new=True, force=True)
        control = cmds.createNode("transform", name="zCtrl")
        cmds.setAttr(control + ".rotateOrder", 3)
        points = [(1.5, 1.0, 0), (1.5, -1.0, 0), (-1.5, -1.0, 0), (-1.5, 1.0, 0), (1.5, 1.0, 0)]
        outline = cmds.curve(degree=1, point=points, name="zOutline")
        cmds.currentUnit(angle="rad", linear="m")
        setup = OutlineBank.create(control, outline, name="zBank", upAxis="z", reach=6.0)
        owner = str(setup.container)
        cmds.currentUnit(angle="deg", linear="cm")
        self.assertAlmostEqual(cmds.getAttr(owner + ".reach"), 6.0, places=4)
        rotate = (0, 20, 0)  # z軸を+x側へ倒す
        cmds.setAttr(control + ".rotate", *rotate)
        pivot = cmds.getAttr(owner + ".pivot")[0]
        self.assertAlmostEqual(pivot[0], 1.5, delta=1e-4)
        self.assertAlmostEqual(pivot[1], 0.0, delta=1e-4)
        expected = _translate([-v for v in pivot]) * _rotation(rotate, 3) * _translate(pivot)
        _close(self, _matrix(owner + ".matrix"), expected)

    def test_container_owns_nodes_and_undo(self):
        """生成した演算ノードは全てcontainerに入り、1回のUndoで消える。"""
        members = set(cmds.ls(cmds.container(self.owner, query=True, nodeList=True) or []))
        self.assertIn("bank_nearest", members)
        cmds.file(new=True, force=True)
        control = cmds.createNode("transform", name="undoCtrl")
        outline = cmds.circle(constructionHistory=False, name="undoOutline")[0]
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        OutlineBank.create(control, outline, name="undoBank")
        created = set(cmds.ls()) - before
        nodes = set(cmds.ls(cmds.container("undoBank", query=True, nodeList=True) or []))
        created -= set(cmds.ls(type="hyperLayout"))  # containerに付くhyperLayout
        self.assertEqual(created - nodes, {"undoBank"})
        cmds.undo()
        self.assertFalse(cmds.objExists("undoBank"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoBank.matrix"))

    def test_arguments(self):
        """transform以外・joint・曲線でない輪郭・軸・reach・名前の重複を拒否する。"""
        other = cmds.createNode("multiplyDivide")
        joint = cmds.createNode("joint")
        cube = cmds.polyCube(constructionHistory=False)[0]
        cases = (
            ((other, self.outline), {}),
            ((joint, self.outline), {}),
            ((self.control, cube), {}),
            ((self.control, self.outline), {"upAxis": "w"}),
            ((self.control, self.outline), {"reach": 0.0}),
            ((self.control, self.outline), {"reach": float("nan")}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                OutlineBank.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            OutlineBank.create(self.control, self.outline, name="bank")


if __name__ == "__main__":
    unittest.main()

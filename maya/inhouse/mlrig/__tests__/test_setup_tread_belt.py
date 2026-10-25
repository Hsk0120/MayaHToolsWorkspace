"""TreadBeltの板の位置・向き・間隔を、OpenMayaのMFnNurbsCurveで弧長から独立に求めた値と比べて確かめる。"""

import unittest

from maya import cmds
import maya.api.OpenMaya as om

from mlrig.setups import TreadBelt

COUNT = 8


def _curve_fn(curve):
    """曲線のMFnNurbsCurve(ワールドの位置を求めるためシェイプのDAGパスで作る)。"""
    selection = om.MSelectionList()
    selection.add(curve)
    return om.MFnNurbsCurve(selection.getDagPath(0).extendToShape())


def _expected(curve, fraction, normal=(0.0, 0.0, 1.0)):
    """弧長の割合 fraction の点の位置・接線・上方向(試験側の独立計算)。"""
    fn = _curve_fn(curve)
    param = fn.findParamFromLength(fraction * fn.length())
    point = fn.getPointAtParam(param, om.MSpace.kWorld)
    tangent = fn.tangent(param, om.MSpace.kWorld).normal()
    world = om.MMatrix(cmds.getAttr(curve + ".worldMatrix[0]"))
    up = om.MVector(normal) * world
    up = (up - tangent * (up * tangent)).normal()
    return point, tangent, up


class TreadBeltTest(unittest.TestCase):
    """弧長の位置と向き・等間隔・driver・裏返らない・曲線の変形・UI単位・所有とUndo・引数を確認する。"""

    def setUp(self):
        """横に長い閉じた曲線(履帯の形)を、移動・回転したtransformの下に作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.curve = cmds.circle(normal=(0, 0, 1), radius=4, sections=12, constructionHistory=False,
                                 name="treadPath")[0]
        cmds.scale(3, 1, 1, self.curve + ".cv[*]", relative=True)
        cmds.move(2, 5, -1, self.curve)
        cmds.rotate(10, 25, 0, self.curve)
        self.setup = TreadBelt.create(self.curve, COUNT, name="tread")
        self.owner = str(self.setup.container)

    def _check(self, distance, phase=0.0, owner=None, curve=None, normal=(0.0, 0.0, 1.0), count=COUNT,
               tolerance=1e-4):
        """全ての板の割合・位置・接線・上方向が独立計算と一致することを確かめる。"""
        owner, curve = owner or self.owner, curve or self.curve
        length = _curve_fn(curve).length()
        self.assertAlmostEqual(cmds.getAttr(owner + ".length"), length, places=4)
        for index, fraction in enumerate(TreadBelt.fractions(count, distance, length, phase)):
            actual = cmds.getAttr("{}.fraction{}".format(owner, index))
            # 0と1は曲線の同じ点なので、周回の境目では差を一周の分だけ許す。
            self.assertAlmostEqual(min(abs(actual - fraction), 1 - abs(actual - fraction)), 0.0, places=5)
            matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
            point, tangent, up = _expected(curve, fraction, normal)
            position = om.MPoint(matrix[12], matrix[13], matrix[14])
            front = om.MVector(matrix[0], matrix[1], matrix[2])
            top = om.MVector(matrix[8], matrix[9], matrix[10])
            self.assertLess((position - point).length(), tolerance)
            self.assertLess((front - tangent).length(), tolerance)
            self.assertLess((top - up).length(), tolerance)

    def test_matches_arc_length(self):
        """送り量0・正・負・一周を超える量と phase で、弧長から求めた位置・向きと一致する。"""
        for distance, phase in ((0.0, 0.0), (7.5, 0.0), (-13.0, 0.0), (180.0, 0.0), (3.0, 0.3), (0.0, -1.7)):
            with self.subTest(distance=distance, phase=phase):
                cmds.setAttr(self.owner + ".distance", distance)
                cmds.setAttr(self.owner + ".phase", phase)
                self._check(distance, phase)

    def test_even_spacing(self):
        """隣り合う板の間は、曲線に沿った長さで length / count に等しい。"""
        cmds.setAttr(self.owner + ".distance", 4.2)
        fn = _curve_fn(self.curve)
        length = fn.length()
        lengths = []
        for index in range(COUNT):
            matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(self.owner, index)))
            _, param = fn.closestPoint(om.MPoint(matrix[12], matrix[13], matrix[14]), space=om.MSpace.kWorld)
            lengths.append(fn.findLengthFromParam(param))
        for index in range(COUNT):
            gap = (lengths[(index + 1) % COUNT] - lengths[index]) % length
            self.assertAlmostEqual(gap, length / COUNT, places=3)

    def test_driver(self):
        """driver の変化量が送り量になり、生成時は板が動かず、一周分の送りで元の位置へ戻る。"""
        car = cmds.createNode("transform", name="vehicle")
        cmds.setAttr(car + ".translateX", 9.0)
        setup = TreadBelt.create(self.curve, 5, name="driven", driver=car + ".translateX")
        owner = str(setup.container)
        self._check(0.0, owner=owner, count=5)
        start = [cmds.getAttr("{}.matrix{}".format(owner, i)) for i in range(5)]
        cmds.setAttr(car + ".translateX", 9.0 + 6.4)
        self.assertAlmostEqual(cmds.getAttr(owner + ".distance"), 6.4, places=5)
        self._check(6.4, owner=owner, count=5)
        cmds.setAttr(car + ".translateX", 9.0 + cmds.getAttr(owner + ".length"))
        for index in range(5):
            matrix = cmds.getAttr("{}.matrix{}".format(owner, index))
            for a, b in zip(matrix, start[index]):
                self.assertAlmostEqual(a, b, places=3)

    def test_does_not_flip(self):
        """一周を細かく送っても上方向は常に面の法線側で、1ステップの向きの変化が小さい。"""
        world = om.MMatrix(cmds.getAttr(self.curve + ".worldMatrix[0]"))
        normal = (om.MVector(0, 0, 1) * world).normal()
        length = cmds.getAttr(self.owner + ".length")
        previous = None
        for step in range(121):
            cmds.setAttr(self.owner + ".distance", length * step / 120.0)
            matrix = om.MMatrix(cmds.getAttr(self.owner + ".matrix0"))
            top = om.MVector(matrix[8], matrix[9], matrix[10])
            self.assertGreater(top * normal, 0.999)
            front = om.MVector(matrix[0], matrix[1], matrix[2])
            if previous is not None:
                self.assertLess(front.angle(previous), 0.5)
            previous = front

    def test_curve_deformation(self):
        """曲線の形を変えても、長さと弧長の等間隔に追従する。"""
        cmds.move(0, 3, 0, self.curve + ".cv[2]", self.curve + ".cv[3]", relative=True, objectSpace=True)
        cmds.setAttr(self.owner + ".distance", 5.0)
        self._check(5.0)

    def test_ui_units_and_axes(self):
        """UI単位がmmでも同じ位置になり(自動の単位変換ノードが入らない)、軸と法線の指定に従う。"""
        cmds.currentUnit(linear="mm")
        conversions = set(cmds.ls(type="unitConversion"))
        setup = TreadBelt.create(self.curve, 4, name="millimeter", normal=(0, 0, -1), frontAxis="y", upAxis="x")
        owner = str(setup.container)
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertEqual(set(cmds.ls(type="unitConversion")) - conversions - members, set())
        cmds.setAttr(owner + ".distance", 60.0)  # 60mm = 6cm
        cmds.currentUnit(linear="cm")
        self.assertAlmostEqual(cmds.getAttr(owner + ".distance"), 6.0, places=5)
        length = _curve_fn(self.curve).length()
        for index, fraction in enumerate(TreadBelt.fractions(4, 6.0, length)):
            matrix = om.MMatrix(cmds.getAttr("{}.matrix{}".format(owner, index)))
            point, tangent, up = _expected(self.curve, fraction, (0, 0, -1))
            self.assertLess((om.MPoint(matrix[12], matrix[13], matrix[14]) - point).length(), 1e-4)
            self.assertLess((om.MVector(matrix[4], matrix[5], matrix[6]) - tangent).length(), 1e-4)
            self.assertLess((om.MVector(matrix[0], matrix[1], matrix[2]) - up).length(), 1e-4)

    def test_owned_and_undo(self):
        """計算ノードはcontainerが所有し、1回のUndoで作成全体が消え、Redoで戻る。"""
        members = set(cmds.container(self.owner, query=True, nodeList=True) or [])
        created = {n for n in cmds.ls() if n.startswith("tread_")}
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.file(new=True, force=True)
        curve = cmds.circle(constructionHistory=False, name="undoPath")[0]
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        TreadBelt.create(curve, 3, name="undoTread")
        self.assertTrue(cmds.objExists("undoTread.matrix2"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoTread"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoTread.matrix2"))

    def test_arguments(self):
        """開いた曲線・曲線以外・count・軸・法線・長さでないdriver・名前の重複を拒否する。"""
        line = cmds.curve(point=[(0, 0, 0), (1, 0, 0), (2, 1, 0), (3, 0, 0)], name="openPath")
        node = cmds.createNode("transform", name="notCurve")
        cases = (
            ((line, 4), {}),
            ((node, 4), {}),
            ((self.curve, 0), {}),
            ((self.curve, 2.5), {}),
            ((self.curve, True), {}),
            ((self.curve, 4), {"frontAxis": "x", "upAxis": "x"}),
            ((self.curve, 4), {"frontAxis": "w"}),
            ((self.curve, 4), {"normal": (0, 0, 0)}),
            ((self.curve, 4), {"normal": (0, 1)}),
            ((self.curve, 4), {"driver": node + ".rotateX"}),
        )
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs), self.assertRaises(ValueError):
                TreadBelt.create(*args, name="bad", **kwargs)
        self.assertFalse(cmds.objExists("bad"))
        with self.assertRaises(ValueError):
            TreadBelt.create(self.curve, 4, name="tread")


if __name__ == "__main__":
    unittest.main()

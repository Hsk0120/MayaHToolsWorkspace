"""SquashBoxの4辺の押し引きによる行列を、scalePivotを持つtransformの階層で組んだ参照と比較する。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import SquashBox

HEIGHT = 4.0
WIDTH = 3.0


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


class SquashBoxTest(unittest.TestCase):
    """作成時の姿勢・各辺・組み合わせ・体積の割合・支点の不動・rootの動き・軸・所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・移動したrootと、上→下→外→内の順に scalePivot を反対の辺に置いた参照の階層を作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.root = cmds.createNode("transform", name="root")
        cmds.setAttr(self.root + ".translate", 2, 5, -1)
        cmds.setAttr(self.root + ".rotate", 15, 30, -10)
        self.setup = SquashBox.create(self.root, name="box", height=HEIGHT, width=WIDTH)
        self.owner = str(self.setup.container)
        self.reference = {}
        parent = self.root
        for attr, pivot in (("top", (0, -HEIGHT / 2, 0)), ("bottom", (0, HEIGHT / 2, 0)),
                            ("outer", (-WIDTH / 2, 0, 0)), ("inner", (WIDTH / 2, 0, 0))):
            node = cmds.createNode("transform", name="ref_" + attr, parent=parent)
            cmds.setAttr(node + ".scalePivot", *pivot)
            self.reference[attr] = node
            parent = node
        self.leaf = parent

    def _drive(self, volume=1.0, **values):
        """containerの値を設定し、同じ値から参照の階層のscaleを設定する。"""
        cmds.setAttr(self.owner + ".volume", volume)
        for attr in ("top", "bottom", "outer", "inner"):
            amount = values.get(attr, 0.0)
            cmds.setAttr(self.owner + "." + attr, amount)
            length = HEIGHT if attr in ("top", "bottom") else WIDTH
            main, perp = 1.0 + amount / length, 1.0 - volume * amount / length
            scale = [perp, perp, perp]
            scale[1 if attr in ("top", "bottom") else 0] = main
            cmds.setAttr(self.reference[attr] + ".scale", *scale)

    def _assertMatrix(self, actual, expected, tolerance=1e-6):
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, delta=tolerance, msg="element {}".format(index))

    def _assertReference(self):
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.leaf + ".worldMatrix[0]"))
        root = _matrix(self.root + ".worldMatrix[0]")
        self._assertMatrix(_matrix(self.owner + ".localMatrix") * root, _matrix(self.owner + ".matrix"))

    def test_rest(self):
        """作成直後は単位行列で、出力がrootのワールド行列と一致する(跳ねない)。"""
        self._assertMatrix(_matrix(self.owner + ".localMatrix"), om.MMatrix())
        self._assertMatrix(_matrix(self.owner + ".matrix"), _matrix(self.root + ".worldMatrix[0]"))

    def test_each_side_and_combinations(self):
        """各辺の伸ばし・潰しと組み合わせで、参照の階層と一致する。"""
        for values in ({"top": 1.5}, {"top": -1.0}, {"bottom": 2.0}, {"bottom": -1.5}, {"outer": 1.0},
                       {"inner": -0.8}, {"top": 1.0, "outer": -0.5},
                       {"top": -1.2, "bottom": 0.7, "outer": 0.9, "inner": -0.4}):
            with self.subTest(values=values):
                self._drive(**values)
                self._assertReference()

    def test_opposite_side_stays(self):
        """1つの辺だけを動かすと反対の辺の中心は動かず、動かした辺は値だけ外へ動く。"""
        self._drive(top=1.5)
        local = _matrix(self.owner + ".localMatrix")
        bottom = om.MPoint(0, -HEIGHT / 2, 0) * local
        top = om.MPoint(0, HEIGHT / 2, 0) * local
        self.assertTrue(bottom.isEquivalent(om.MPoint(0, -HEIGHT / 2, 0), 1e-6))
        self.assertTrue(top.isEquivalent(om.MPoint(0, HEIGHT / 2 + 1.5, 0), 1e-6))
        side = om.MPoint(WIDTH / 2, -HEIGHT / 2, 0) * local
        self.assertAlmostEqual(side.x, WIDTH / 2 * (1 - 1.5 / HEIGHT), delta=1e-6)
        self._drive(inner=1.0)
        local = _matrix(self.owner + ".localMatrix")
        outer = om.MPoint(WIDTH / 2, 0, 0) * local
        inner = om.MPoint(-WIDTH / 2, 0, 0) * local
        self.assertTrue(outer.isEquivalent(om.MPoint(WIDTH / 2, 0, 0), 1e-6))
        self.assertTrue(inner.isEquivalent(om.MPoint(-WIDTH / 2 - 1.0, 0, 0), 1e-6))

    def test_volume(self):
        """volume=0なら直交する向きは変わらず、割合を変えると参照と一致する。"""
        self._drive(volume=0.0, top=2.0)
        self._assertReference()
        local = _matrix(self.owner + ".localMatrix")
        self.assertAlmostEqual(om.MVector(local[0], local[1], local[2]).length(), 1.0, delta=1e-6)
        self._drive(volume=0.4, top=-1.0, outer=0.5)
        self._assertReference()
        self.assertEqual(SquashBox.factors(1.0, 4.0, 1.0), (1.25, 0.75))

    def test_root_moves(self):
        """rootを動かす・回すと、潰した形のまま付いてくる。"""
        self._drive(top=1.0, inner=-0.5)
        cmds.setAttr(self.root + ".rotate", -40, 10, 70)
        cmds.setAttr(self.root + ".translate", -3, 1, 4)
        self._assertReference()

    def test_axes(self):
        """verticalAxis=z・sideAxis=yでは、topがZ方向へ伸ばしYとXを潰す。"""
        cmds.file(new=True, force=True)
        root = cmds.createNode("transform", name="axisRoot")
        setup = SquashBox.create(root, name="axisBox", height=2.0, width=4.0, verticalAxis="z", sideAxis="y")
        owner = str(setup.container)
        cmds.setAttr(owner + ".top", 1.0)
        local = _matrix(owner + ".localMatrix")
        self.assertTrue((om.MPoint(0, 0, -1) * local).isEquivalent(om.MPoint(0, 0, -1), 1e-6))
        self.assertTrue((om.MPoint(0, 0, 1) * local).isEquivalent(om.MPoint(0, 0, 2), 1e-6))
        self.assertAlmostEqual((om.MPoint(1, 2, -1) * local).y, 1.0, delta=1e-6)
        cmds.setAttr(owner + ".top", 0.0)
        cmds.setAttr(owner + ".outer", 2.0)
        local = _matrix(owner + ".localMatrix")
        self.assertTrue((om.MPoint(0, -2, 0) * local).isEquivalent(om.MPoint(0, -2, 0), 1e-6))
        self.assertTrue((om.MPoint(0, 2, 0) * local).isEquivalent(om.MPoint(0, 4, 0), 1e-6))

    def test_ownership_and_undo(self):
        """演算ノードはcontainerが所有し、1回のUndoで全体が消え、Redoで戻る。"""
        members = cmds.container(self.owner, query=True, nodeList=True) or []
        upstream = cmds.listHistory(self.owner + ".matrix", pruneDagObjects=True) or []
        outside = [node for node in upstream if node != self.owner and node not in members
                   and cmds.nodeType(node) not in ("transform", "hyperLayout")]
        self.assertEqual(outside, [])
        cmds.file(new=True, force=True)
        root = cmds.createNode("transform", name="undoRoot")
        before = set(cmds.ls())
        cmds.undoInfo(state=True)
        SquashBox.create(root, name="undoBox")
        self.assertTrue(cmds.objExists("undoBox"))
        cmds.undo()
        self.assertFalse(cmds.objExists("undoBox"))
        self.assertEqual(set(cmds.ls()), before)
        cmds.redo()
        self.assertTrue(cmds.objExists("undoBox.matrix"))

    def test_arguments(self):
        """軸・長さ・割合・transform以外・名前の重複を拒否する。"""
        for kwargs in ({"verticalAxis": "w"}, {"verticalAxis": "x", "sideAxis": "x"}, {"height": 0.0},
                       {"width": -1.0}, {"volume": 1.5}, {"height": float("inf")}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                SquashBox.create(self.root, name="bad", **kwargs)
        node = cmds.createNode("multiplyDivide")
        with self.assertRaises(ValueError):
            SquashBox.create(node, name="bad")
        with self.assertRaises(ValueError):
            SquashBox.create(self.root, name="box")
        self.assertFalse(cmds.objExists("bad"))


if __name__ == "__main__":
    unittest.main()

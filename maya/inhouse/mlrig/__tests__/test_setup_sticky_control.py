"""StickyControlの、変形したメッシュの表面への追従を、デフォーマーの変形から独立に求めた値と比べて確かめる。"""

import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import StickyControl


def _matrix(plug):
    return om.MMatrix(cmds.getAttr(plug))


def _close(test, first, second, tolerance=1e-4):
    """2つの行列(または列)の各成分が誤差の範囲で等しいことを確かめる。"""
    for a, b in zip(list(first), list(second)):
        test.assertAlmostEqual(a, b, delta=tolerance)


class StickyControlTest(unittest.TestCase):
    """作成直後・剛体の変形・形の変形・コントロールの相対操作・geometry指定・親の移動・所有とUndo・引数を確かめる。"""

    def setUp(self):
        """移動・回転したメッシュ(平面)と、回した親の下の、表面から少し離れたコントロールを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.mesh = cmds.polyPlane(name="face", width=10, height=10, subdivisionsX=10, subdivisionsY=10,
                                   constructionHistory=False)[0]
        cmds.setAttr(self.mesh + ".translate", 1, 5, -2)
        cmds.setAttr(self.mesh + ".rotate", 70, 15, 0)
        self.group = cmds.createNode("transform", name="ctrlGrp")
        cmds.setAttr(self.group + ".translate", -3, 2, 1)
        cmds.setAttr(self.group + ".rotate", 0, 30, 10)
        self.control = cmds.createNode("transform", name="stickyCtrl", parent=self.group)
        self.control = cmds.ls(self.control, long=True)[0]
        self.vertex = 38  # 平面の内側の頂点
        point = om.MPoint(cmds.pointPosition("{}.vtx[{}]".format(self.mesh, self.vertex), world=True))
        normal = om.MVector(0, 1, 0) * _matrix(self.mesh + ".worldMatrix[0]")
        self.point = point
        self.lifted = point + normal.normal() * 0.5
        self._place(self.lifted, (10, 20, 30))

    def _place(self, point, rotate):
        cmds.xform(self.control, worldSpace=True, translation=(point.x, point.y, point.z))
        cmds.xform(self.control, worldSpace=True, rotation=rotate)

    def _create(self, **flags):
        flags.setdefault("name", "sticky")
        return StickyControl.create(self.mesh, self.control, **flags)

    def test_rest_does_not_jump(self):
        """作成直後はコントロールのワールド行列が変わらず、matrixは生成時のワールド行列と一致する。"""
        before = _matrix(self.control + ".worldMatrix[0]")
        graph = self._create(original=self._orig())
        _close(self, _matrix(self.control + ".worldMatrix[0]"), before)
        _close(self, _matrix(str(graph.container) + ".matrix"), before)

    def _orig(self):
        """変形前の形を写したメッシュ(デフォーマーが無い場合のoriginal)。"""
        copy = cmds.duplicate(self.mesh, name="faceRest")[0]
        cmds.setAttr(copy + ".visibility", False)
        return copy

    def test_rigid_deformation(self):
        """全頂点を剛体として動かすクラスターでは、貼り付いた行列も同じ剛体の変換になる(表面からの離れと向きを保つ)。"""
        cluster, handle = cmds.cluster(self.mesh, name="bodyCluster")
        rest = _matrix(self.control + ".worldMatrix[0]")
        graph = self._create()
        _close(self, _matrix(self.control + ".worldMatrix[0]"), rest)
        handleRest = _matrix(handle + ".worldMatrix[0]")
        for translate, rotate in (((0.5, 1.0, -0.3), (0, 0, 0)), ((1, -2, 0.5), (25, -40, 10)),
                                  ((-1, 0, 2), (-60, 15, 80))):
            cmds.setAttr(handle + ".translate", *translate)
            cmds.setAttr(handle + ".rotate", *rotate)
            delta = handleRest.inverse() * _matrix(handle + ".worldMatrix[0]")
            expected = rest * delta
            _close(self, _matrix(str(graph.container) + ".matrix"), expected)
            _close(self, _matrix(self.control + ".worldMatrix[0]"), expected)

    def test_follows_shape_deformation(self):
        """頂点ごとに重みの違うクラスター(形が変わる変形)でも、頂点に置いたコントロールはその頂点の変形後の位置へ付いていく。"""
        self._place(self.point, (0, 0, 0))
        cluster, handle = cmds.cluster(self.mesh, name="softCluster")
        for index in range(121):
            column, row = index % 11, index // 11
            cmds.percent(cluster, "{}.vtx[{}]".format(self.mesh, index), value=(column / 10.0) * (row / 10.0))
        before = _matrix(self.control + ".worldMatrix[0]")
        graph = self._create()
        _close(self, _matrix(self.control + ".worldMatrix[0]"), before)
        for translate, rotate in (((0, 3, 0), (0, 0, 0)), ((1, 2, -1), (30, 0, 20)), ((-2, 0, 1), (0, -45, 0))):
            cmds.setAttr(handle + ".translate", *translate)
            cmds.setAttr(handle + ".rotate", *rotate)
            expected = cmds.pointPosition("{}.vtx[{}]".format(self.mesh, self.vertex), world=True)
            for name in (str(graph.container) + ".matrix", self.control + ".worldMatrix[0]"):
                actual = list(_matrix(name))[12:15]
                _close(self, actual, expected)
            moved = om.MVector(*expected) - om.MVector(self.point)
            self.assertGreater(moved.length(), 0.01)

    def test_control_moves_relative_to_surface(self):
        """変形後にコントロールを動かすと、ワールド行列は L · L0^-1 · matrix になる(表面の上での相対操作)。"""
        cluster, handle = cmds.cluster(self.mesh, name="bodyCluster")
        graph = self._create()
        rest = om.MMatrix(cmds.getAttr(self.control + ".matrix"))
        cmds.setAttr(handle + ".rotate", 20, 30, 0)
        cmds.setAttr(handle + ".translate", 1, 0, 0)
        cmds.setAttr(self.control + ".translate", *[v + d for v, d in zip(
            cmds.getAttr(self.control + ".translate")[0], (0.4, -0.2, 0.3))])
        cmds.setAttr(self.control + ".rotateZ", 50)
        local = om.MMatrix(cmds.getAttr(self.control + ".matrix"))
        expected = local * rest.inverse() * _matrix(str(graph.container) + ".matrix")
        _close(self, _matrix(self.control + ".worldMatrix[0]"), expected)

    def test_geometry_plug_avoids_double_deformation(self):
        """geometryに前の段のデフォーマーの出力を渡すと、後の段(コントロール自身の変形)には追従しない。"""
        body, bodyHandle = cmds.cluster(self.mesh, name="bodyCluster")
        own, ownHandle = cmds.cluster(self.mesh, name="ownCluster")
        rest = _matrix(self.control + ".worldMatrix[0]")
        graph = self._create(geometry=body + ".outputGeometry[0]")
        cmds.setAttr(ownHandle + ".translate", 0, 3, 0)
        _close(self, _matrix(str(graph.container) + ".matrix"), rest)
        handleRest = _matrix(bodyHandle + ".worldMatrix[0]")
        cmds.setAttr(bodyHandle + ".translate", 0.5, 0, 1)
        delta = handleRest.inverse() * _matrix(bodyHandle + ".worldMatrix[0]")
        _close(self, _matrix(str(graph.container) + ".matrix"), rest * delta)

    def test_parent_and_connect(self):
        """親を動かしても貼り付いた位置は保たれる。connect=Falseでは出力だけを作り、コントロールは変えない。"""
        cmds.cluster(self.mesh, name="bodyCluster")
        graph = self._create()
        before = _matrix(self.control + ".worldMatrix[0]")
        cmds.setAttr(self.group + ".translate", 5, -4, 2)
        cmds.setAttr(self.group + ".rotate", 40, 0, -20)
        _close(self, _matrix(self.control + ".worldMatrix[0]"), before)
        other = cmds.createNode("transform", name="otherCtrl")
        cmds.setAttr(other + ".translate", 2, 4, 0)
        StickyControl.create(self.mesh, other, name="other", connect=False)
        self.assertFalse(cmds.listConnections(other + ".offsetParentMatrix", source=True, destination=False))
        _close(self, _matrix("other.matrix"), _matrix(other + ".worldMatrix[0]"))

    def test_ownership_and_undo(self):
        """計算ノードは全てcontainerが所有し、1回のUndoで全て消え(接続も戻る)、Redoで戻る。"""
        cmds.cluster(self.mesh, name="bodyCluster")
        before = set(cmds.ls())
        cmds.undoInfo(stateWithoutFlush=True)
        graph = self._create()
        owner = str(graph.container)
        created = set(cmds.ls()) - before - {owner} - set(cmds.ls(type="hyperLayout"))
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        self.assertTrue(created)
        self.assertEqual(created - members, set())
        cmds.undo()
        self.assertEqual(set(cmds.ls()) - before, set())
        self.assertFalse(cmds.listConnections(self.control + ".offsetParentMatrix", source=True, destination=False))
        cmds.redo()
        self.assertTrue(cmds.listConnections(self.control + ".offsetParentMatrix", source=True, destination=False))

    def test_invalid_arguments(self):
        """不正な引数はValueErrorになる。"""
        with self.assertRaises(ValueError):
            self._create()  # デフォーマーが無く、変形前のシェイプが無い
        locator = cmds.spaceLocator(name="notMesh")[0]
        with self.assertRaises(ValueError):
            self._create(original=locator)
        with self.assertRaises(ValueError):
            StickyControl.create(locator, self.control, original=self._orig())
        with self.assertRaises(ValueError):
            StickyControl.create(self.mesh, self.mesh, original=self._orig())
        shape = cmds.listRelatives(locator, shapes=True, fullPath=True)[0]
        with self.assertRaises(ValueError):
            StickyControl.create(self.mesh, shape, original=self._orig())
        with self.assertRaises(ValueError):
            self._create(original=self._orig(), geometry="noSuchNode.outMesh")
        self._create(name="taken", original=self._orig())
        with self.assertRaises(ValueError):
            self._create(name="taken", original=self._orig())
        self.assertEqual(cmds.ls(type="container"), ["taken"])


if __name__ == "__main__":
    unittest.main(argv=["test_setup_sticky_control"], exit=False, verbosity=2)

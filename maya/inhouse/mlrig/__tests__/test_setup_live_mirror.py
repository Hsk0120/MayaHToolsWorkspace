"""LiveMirrorの鏡像を、対称面での点とベクトルの反射から独立に計算した値で確かめる。"""

import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import LiveMirror

#: 位置(cm)の許容。multMatrix・blendMatrix は倍精度だが、作成時の定数の逆行列の丸めを含む。
POSITION = 1e-6

#: 軸のベクトルの成分の許容。
AXIS = 1e-6

#: flip ごとに反転する局所の軸の番号。
FLIPPED = {"behavior": (0, 1, 2), "x": (0,), "y": (1,), "z": (2,)}


def _world(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _rows(matrix):
    """行列の3つの軸(行)と位置。"""
    rows = [om2.MVector(matrix[4 * row], matrix[4 * row + 1], matrix[4 * row + 2]) for row in range(4)]
    return rows[:3], om2.MPoint(rows[3])


def _expected(source, plane, axis, flip):
    """試験側で書いた式: 対称面の原点 o・単位法線 n で点を p - 2((p-o)・n)n、軸を a - 2(a・n)n に映し、
    flip の軸の向きを反転する。"""
    plane_axes, origin = _rows(plane)
    normal = plane_axes["xyz".index(axis)].normal()
    axes, position = _rows(source)
    point = position - normal * (2.0 * ((position - origin) * normal))
    mirrored = [axis_vector - normal * (2.0 * (axis_vector * normal)) for axis_vector in axes]
    for index in FLIPPED[flip]:
        mirrored[index] = -mirrored[index]
    return mirrored, point


class LiveMirrorTest(unittest.TestCase):
    """作成時に跳ねないこと、式との一致、上乗せ・weight・対称面の移動、所有・Undo・引数を確認する。"""

    def setUp(self):
        """回転・移動した対称面、非一様スケールの親の下の source、回転・スケールした親の下の target(joint)。"""
        cmds.file(new=True, force=True)
        self.plane = cmds.createNode("transform", name="root")
        cmds.xform(self.plane, translation=(3, 1, -2), rotation=(10, 35, -5), scale=(2, 2, 2))
        self.sourceParent = cmds.createNode("transform", name="sourceParent", parent=self.plane)
        cmds.xform(self.sourceParent, translation=(4, 2, 1), rotation=(20, -10, 30), scale=(1.5, 0.7, 1.2))
        self.source = cmds.createNode("joint", name="source", parent=self.sourceParent)
        cmds.xform(self.source, translation=(1, 2, 3), rotation=(15, 25, 35))
        self.targetParent = cmds.createNode("transform", name="targetParent")
        cmds.xform(self.targetParent, translation=(-3, 1, 2), rotation=(-30, 40, 10), scale=(0.8, 1.3, 1.1))
        self.target = cmds.createNode("joint", name="target", parent=self.targetParent)
        cmds.setAttr(self.target + ".jointOrient", 10, -20, 30)
        cmds.xform(self.target, translation=(2, -1, 0.5), rotation=(5, 15, -25))

    def _check(self, axis="x", flip="behavior", offset=None, message=""):
        """target のワールド行列が鏡像(offset があれば offset * 鏡像)と一致することを確かめる。"""
        world = _world(self.target)
        expected_axes, expected_point = _expected(_world(self.source), _world(self.plane), axis, flip)
        if offset is not None:
            matrix = om2.MMatrix()
            for row, vector in enumerate(expected_axes):
                for column in range(3):
                    matrix.setElement(row, column, vector[column])
            for column in range(3):
                matrix.setElement(3, column, expected_point[column])
            expected_axes, expected_point = _rows(offset * matrix)
        axes, point = _rows(world)
        self.assertLess((point - expected_point).length(), POSITION, message)
        for actual, expected in zip(axes, expected_axes):
            self.assertLess((actual - expected).length(), AXIS, message)

    def test_rest_does_not_move(self):
        """maintainOffset=True では作成直後に target が動かない。厳密な鏡像の位置からは maintainOffset なしでも動かない。"""
        before = _world(self.target)
        LiveMirror.create(self.source, self.target, name="mirror", plane=self.plane, maintainOffset=True)
        self.assertTrue(_world(self.target).isEquivalent(before, 1e-9))
        cmds.delete("mirror")
        self.assertTrue(_world(self.target).isEquivalent(before, 1e-9))
        # 親がshearを作らない transform を厳密な鏡像へ置いてから maintainOffset なしで作る
        # (source の親は非一様scaleなので、source の scale を1にして鏡像にshearを含めない)。
        cmds.setAttr(self.sourceParent + ".scale", 1, 1, 1)
        free = cmds.createNode("transform", name="free")
        cmds.xform(free, matrix=list(LiveMirror.mirror(_world(self.source), _world(self.plane))), worldSpace=True)
        placed = _world(free)
        LiveMirror.create(self.source, free, name="freeMirror", plane=self.plane)
        self.assertTrue(_world(free).isEquivalent(placed, 1e-6))
        # weight=0 では鏡像の位置でなくても動かない。
        cmds.delete("freeMirror")
        cmds.xform(self.target, translation=(7, 1, 1))
        placed = _world(self.target)
        LiveMirror.create(self.source, self.target, name="mirror", plane=self.plane, weight=0.0)
        self.assertTrue(_world(self.target).isEquivalent(placed, 1e-9))

    def test_random_poses_match_reflection(self):
        """乱数20姿勢(scale を含む)で、軸・flip の全組み合わせの鏡像が反射の式と一致する。"""
        rng = random.Random(29)
        for axis in "xyz":
            for flip in ("behavior", "x", "y", "z"):
                name = "mirror_{}_{}".format(axis, flip)
                LiveMirror.create(self.source, self.target, name=name, plane=self.plane, axis=axis, flip=flip)
                for _ in range(20):
                    cmds.xform(self.source, translation=[rng.uniform(-8, 8) for _ in range(3)],
                               rotation=[rng.uniform(-180, 180) for _ in range(3)],
                               scale=[rng.uniform(0.5, 2.0) for _ in range(3)])
                    self._check(axis, flip, message=name)
                    det = _world(self.target).det3x3()
                    self.assertGreater(det * _world(self.source).det3x3(), 0.0, "handedness " + name)
                cmds.delete(name)

    def test_world_plane_and_python_version(self):
        """plane=None ではワールドのYZ面。Python版 mirror() とDGの出力 mirrorMatrix が一致する。"""
        graph = LiveMirror.create(self.source, self.target, name="mirror")
        cmds.xform(self.source, translation=(2, 3, -1), rotation=(30, 60, 90))
        world = _world(self.source)
        position = om2.MPoint(world[12], world[13], world[14])
        self.assertLess((_rows(_world(self.target))[1] - om2.MPoint(-position.x, position.y, position.z)).length(),
                        POSITION)
        output = om2.MMatrix(cmds.getAttr(str(graph.container) + ".mirrorMatrix"))
        self.assertTrue(output.isEquivalent(LiveMirror.mirror(world), 1e-9))
        self.assertTrue(_world(self.target).isEquivalent(output, 1e-6))

    def test_plane_moves_and_local_edits_layer(self):
        """対称面を動かしても鏡像が保たれ、target 自身の回転・移動は作成時からの差として上乗せされる。"""
        LiveMirror.create(self.source, self.target, name="mirror", plane=self.plane)
        cmds.xform(self.plane, translation=(-5, 4, 6), rotation=(-20, 80, 15))
        cmds.xform(self.source, rotation=(40, -30, 70))
        self._check(message="plane moved")
        rest_local = om2.MMatrix(cmds.getAttr(self.target + ".matrix"))
        cmds.xform(self.target, rotation=(25, -40, 60), translation=(1, 2, 3))
        delta = om2.MMatrix(cmds.getAttr(self.target + ".matrix")) * rest_local.inverse()
        self._check(offset=delta, message="layered")

    def test_weight_and_connect(self):
        """weight で元の offsetParentMatrix と鏡像の間を補間し、connect=False では target を変えない。"""
        rest = _world(self.target)
        graph = LiveMirror.create(self.source, self.target, name="mirror", plane=self.plane)
        owner = str(graph.container)
        cmds.xform(self.source, translation=(5, -2, 4), rotation=(10, 80, -40))
        mirrored = _world(self.target)
        cmds.setAttr(owner + ".weight", 0.0)
        self.assertTrue(_world(self.target).isEquivalent(rest, 1e-6))
        cmds.setAttr(owner + ".weight", 0.5)
        middle = om2.MMatrix(cmds.getAttr(self.target + ".offsetParentMatrix"))
        blend = om2.MMatrix(cmds.getAttr(owner + ".matrix"))
        self.assertTrue(middle.isEquivalent(blend, 1e-12))
        self.assertFalse(_world(self.target).isEquivalent(rest, 1e-3))
        self.assertFalse(_world(self.target).isEquivalent(mirrored, 1e-3))
        cmds.delete(owner)
        other = cmds.createNode("transform", name="other")
        before = _world(other)
        graph = LiveMirror.create(self.source, other, name="loose", connect=False)
        self.assertIsNone(cmds.listConnections(other + ".offsetParentMatrix", source=True, destination=False))
        self.assertTrue(_world(other).isEquivalent(before, 1e-12))
        expected = LiveMirror.mirror(_world(self.source))
        self.assertTrue(om2.MMatrix(cmds.getAttr(str(graph.container) + ".matrix")).isEquivalent(expected, 1e-6))

    def test_owned_and_undo(self):
        """生成ノードはすべてcontainerが所有し単位変換が無い。1回のUndoで全体が消え、Redoで戻る。"""
        before = set(cmds.ls())
        world = _world(self.target)
        graph = LiveMirror.create(self.source, self.target, name="mirror", plane=self.plane, maintainOffset=True)
        owner = str(graph.container)
        created = set(cmds.ls()) - before
        members = set(cmds.container(owner, query=True, nodeList=True) or [])
        # containerのhyperLayoutはcontainer自身が作る表示用のノード。
        self.assertEqual(created - {owner} - set(cmds.ls(type="hyperLayout")), members)
        self.assertFalse(cmds.ls(type="unitConversion"))
        cmds.xform(self.source, rotation=(0, 90, 0))
        moved = _world(self.target)
        cmds.undo()
        cmds.undo()
        self.assertEqual(set(cmds.ls()), before)
        self.assertTrue(_world(self.target).isEquivalent(world, 1e-9))
        cmds.redo()
        cmds.redo()
        self.assertTrue(_world(self.target).isEquivalent(moved, 1e-6))

    def test_invalid_arguments_leave_nothing(self):
        """不正な引数では例外になり、何も残さない。"""
        child = cmds.createNode("transform", name="child", parent=self.target)
        connected = cmds.createNode("transform", name="connected")
        cmds.connectAttr(self.plane + ".worldMatrix[0]", connected + ".offsetParentMatrix")
        locked = cmds.createNode("transform", name="locked")
        cmds.setAttr(locked + ".offsetParentMatrix", lock=True)
        shape = cmds.createNode("locator", name="shape")
        cmds.createNode("transform", name="taken")
        before = set(cmds.ls())
        cases = (
            {"axis": "w"},
            {"flip": "xy"},
            {"weight": 1.5},
            {"weight": -0.1},
            {"name": "taken"},
            {"target": self.source},
            {"plane": child},
            {"source": child},
            {"target": connected},
            {"target": locked},
            {"source": shape},
            {"plane": shape},
        )
        for case in cases:
            arguments = {"source": self.source, "target": self.target, "name": "mirror"}
            arguments.update(case)
            with self.assertRaises(ValueError, msg=str(case)):
                LiveMirror.create(**arguments)
            self.assertEqual(set(cmds.ls()), before, str(case))


if __name__ == "__main__":
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LiveMirrorTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise AssertionError("LiveMirror tests failed")

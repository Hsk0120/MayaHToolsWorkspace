"""DollyZoomの焦点距離・距離・画角を、カメラと被写体のワールド配置から独立に計算した値で確かめる。"""

import math
import random
import unittest

from maya import cmds
from maya.api import OpenMaya as om2

from mlrig.setups import DollyZoom

#: 焦点距離(mm)・距離(cm)の相対の許容。multDoubleLinear 等は倍精度なので丸めの範囲で確かめる。
TOLERANCE = 1e-6


def _worldMatrix(node):
    return om2.MMatrix(cmds.getAttr(node + ".worldMatrix[0]"))


def _depth(camera, subject):
    """被写体の位置をカメラの視線(-Z)へ射影した距離。カメラのscaleは使わず、軸を正規化する。"""
    matrix = _worldMatrix(camera)
    forward = -om2.MVector(matrix[8], matrix[9], matrix[10]).normal()
    origin = om2.MVector(matrix[12], matrix[13], matrix[14])
    point = om2.MVector(cmds.xform(subject, query=True, worldSpace=True, translation=True))
    return (point - origin) * forward


def _screenX(camera, shape, point):
    """カメラの空間で、点が画面の横のどこに写るか(-1〜1が画面の左右の端)。"""
    matrix = _worldMatrix(camera)
    axes = [om2.MVector(matrix[4 * row], matrix[4 * row + 1], matrix[4 * row + 2]).normal() for row in range(3)]
    offset = om2.MVector(point) - om2.MVector(matrix[12], matrix[13], matrix[14])
    x, z = offset * axes[0], offset * axes[2]
    focal = cmds.getAttr(shape + ".focalLength")
    aperture = cmds.getAttr(shape + ".horizontalFilmAperture") * 25.4
    return (x / -z) * focal / (aperture / 2.0)


class DollyZoomTest(unittest.TestCase):
    """作成直後に跳ねないこと、式との一致、被写体の写る幅が保たれること、weight・範囲・所有・引数を確認する。"""

    def setUp(self):
        """回転・移動した親の下にカメラ、別の親の下に被写体を作る。"""
        cmds.file(new=True, force=True)
        rig = cmds.createNode("transform", name="cameraRig")
        cmds.setAttr(rig + ".translate", 3, 2, -4)
        cmds.setAttr(rig + ".rotate", 0, 25, 0)
        self.camera, self.shape = cmds.camera(name="shotCam")
        self.camera = cmds.parent(self.camera, rig)[0]
        self.shape = cmds.listRelatives(self.camera, shapes=True, fullPath=True)[0]
        self.camera = cmds.listRelatives(self.shape, parent=True, fullPath=True)[0]
        cmds.setAttr(self.camera + ".translate", 0, 1, 20)
        cmds.setAttr(self.camera + ".rotate", -5, 0, 0)
        cmds.setAttr(self.shape + ".focalLength", 50.0)
        cmds.setAttr(self.shape + ".horizontalFilmAperture", 1.417)
        group = cmds.createNode("transform", name="stage")
        cmds.setAttr(group + ".rotate", 10, -20, 5)
        cmds.setAttr(group + ".scale", 1.3, 0.7, 1.1)
        self.subject = cmds.createNode("transform", name="hero", parent=group)
        # 作成時の被写体をカメラの前(rig空間の原点近く)へ置く。
        cmds.xform(self.subject, worldSpace=True, translation=cmds.xform(rig, query=True, worldSpace=True,
                                                                          translation=True))
        self.setup = DollyZoom.create(self.camera, self.subject, name="dolly")
        self.owner = str(self.setup.container)

    def _check(self, msg=""):
        """DGの出力を、ワールド配置から独立に計算した値と比べる。"""
        depth = _depth(self.camera, self.subject)
        width = cmds.getAttr(self.owner + ".frameWidth")
        weight = cmds.getAttr(self.owner + ".weight")
        rest = cmds.getAttr(self.owner + ".restFocalLength")
        aperture = cmds.getAttr(self.shape + ".horizontalFilmAperture")
        zoom = depth * aperture * 25.4 / width
        expected = min(max(rest + weight * (zoom - rest), 2.5), 100000.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".depth"), depth, delta=TOLERANCE * max(1, abs(depth)),
                               msg=msg)
        self.assertAlmostEqual(cmds.getAttr(self.shape + ".focalLength"), expected, delta=TOLERANCE * expected,
                               msg=msg)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".focalLength"), expected, delta=TOLERANCE * expected,
                               msg=msg)
        self.assertAlmostEqual(DollyZoom.focalLength(depth, width, aperture, rest, weight), expected,
                               delta=TOLERANCE * expected, msg=msg)
        # 画角は式(倍精度)と一致し、Mayaのcameraが返す横の画角(度)とも一致する。angleBetweenの角度は
        # 単精度相当で1e-6度程度、Mayaのcameraの画角は内部の単精度の計算で1e-4度程度ずれるため許容を分ける。
        fov = DollyZoom.fieldOfView(expected, aperture)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".fieldOfView"), fov, delta=1e-5, msg=msg)
        self.assertAlmostEqual(cmds.camera(self.camera, query=True, horizontalFieldOfView=True), fov, delta=1e-3,
                               msg=msg)
        return depth

    def test_rest(self):
        """作成直後は焦点距離が変わらず、frameWidth は作成時の距離・焦点距離から決まる。"""
        # 演算ノードは単精度なので、作成直後の焦点距離も相対1e-6の範囲で元の値と一致する。
        self.assertAlmostEqual(cmds.getAttr(self.shape + ".focalLength"), 50.0, delta=50.0 * TOLERANCE)
        depth = self._check("rest")
        self.assertGreater(depth, 5.0)
        width = depth * 1.417 * 25.4 / 50.0
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".frameWidth"), width, delta=width * TOLERANCE)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".restFocalLength"), 50.0, delta=1e-12)
        self.assertEqual(cmds.listConnections(self.shape + ".focalLength", source=True, destination=False),
                         ["dolly"])

    def test_random_moves_keep_subject_width(self):
        """カメラ・被写体を乱数で動かしても、被写体の面で frameWidth の幅が画面の横幅にちょうど写る。"""
        generator = random.Random(27)
        width = cmds.getAttr(self.owner + ".frameWidth")
        for index in range(20):
            cmds.setAttr(self.camera + ".translate", generator.uniform(-5, 5), generator.uniform(-3, 3),
                         generator.uniform(4, 60))
            cmds.setAttr(self.camera + ".rotate", generator.uniform(-10, 10), generator.uniform(-10, 10),
                         generator.uniform(-30, 30))
            cmds.setAttr(self.subject + ".translate", generator.uniform(-1, 1), generator.uniform(-1, 1),
                         generator.uniform(-1, 1))
            depth = self._check("move {}".format(index))
            if cmds.getAttr(self.shape + ".focalLength") <= 2.5 + 1e-9:
                continue
            # 被写体からカメラの横の軸へ ±width/2 ずらした点は、画面の左右の端(±1)に写る。
            matrix = _worldMatrix(self.camera)
            side = om2.MVector(matrix[0], matrix[1], matrix[2]).normal()
            center = om2.MVector(cmds.xform(self.subject, query=True, worldSpace=True, translation=True))
            for sign in (1.0, -1.0):
                point = center + side * (sign * width / 2.0)
                self.assertAlmostEqual(_screenX(self.camera, self.shape, point) - _screenX(
                    self.camera, self.shape, center), sign, delta=1e-6, msg="edge {} depth {}".format(index, depth))

    def test_weight_and_frame_width(self):
        """weight=0 で元の焦点距離、途中の値は線形の補間、frameWidth を半分にすると焦点距離が2倍になる。"""
        cmds.setAttr(self.camera + ".translateZ", 40)
        self._check("far")
        full = cmds.getAttr(self.shape + ".focalLength")
        self.assertGreater(full, 50.0)
        cmds.setAttr(self.owner + ".weight", 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.shape + ".focalLength"), 50.0, delta=50.0 * TOLERANCE)
        cmds.setAttr(self.owner + ".weight", 0.25)
        self.assertAlmostEqual(cmds.getAttr(self.shape + ".focalLength"), 50.0 + 0.25 * (full - 50.0), delta=1e-6)
        self._check("weight")
        cmds.setAttr(self.owner + ".weight", 1.0)
        cmds.setAttr(self.owner + ".frameWidth", cmds.getAttr(self.owner + ".frameWidth") / 2.0)
        self.assertAlmostEqual(cmds.getAttr(self.shape + ".focalLength"), 2.0 * full, delta=1e-6 * full)
        cmds.setAttr(self.shape + ".horizontalFilmAperture", 0.98)
        self._check("aperture")

    def test_range_and_camera_scale(self):
        """被写体がカメラの後ろへ回ると焦点距離はMayaの下限、カメラのscaleは距離に影響しない。"""
        cmds.setAttr(self.camera + ".translateZ", -30)
        self.assertLess(cmds.getAttr(self.owner + ".depth"), 0.0)
        self.assertAlmostEqual(cmds.getAttr(self.shape + ".focalLength"), 2.5, delta=1e-9)
        self._check("behind")
        cmds.setAttr(self.camera + ".translateZ", 30)
        before = cmds.getAttr(self.owner + ".depth")
        cmds.setAttr(self.camera + ".scale", 2.0, 0.5, 3.0)
        self.assertAlmostEqual(cmds.getAttr(self.owner + ".depth"), before, delta=1e-6)
        self._check("scaled camera")

    def test_without_connect(self):
        """connect=False では焦点距離へ接続せず、出力だけを作る。カメラのシェイプも受け付ける。"""
        cmds.delete(self.owner)
        cmds.setAttr(self.shape + ".focalLength", 35.0)
        owner = str(DollyZoom.create(self.shape, self.subject, name="dolly2", connect=False, weight=0.5)
                    .container)
        self.assertFalse(cmds.listConnections(self.shape + ".focalLength", source=True, destination=False))
        cmds.setAttr(self.camera + ".translateZ", 40)
        self.assertAlmostEqual(cmds.getAttr(self.shape + ".focalLength"), 35.0, delta=1e-12)
        depth = _depth(self.camera, self.subject)
        expected = DollyZoom.focalLength(depth, cmds.getAttr(owner + ".frameWidth"), 1.417, 35.0, 0.5)
        self.assertAlmostEqual(cmds.getAttr(owner + ".focalLength"), expected, delta=1e-6 * expected)
        self.assertGreater(expected, 35.0)

    def test_container_and_undo(self):
        """演算ノードはcontainerが所有し(単位変換のノードを挟まない)、1回のUndoで全体が消えRedoで戻る。"""
        nodes = cmds.container(self.owner, query=True, nodeList=True) or []
        allowed = ("vectorProduct", "plusMinusAverage", "multiplyDivide", "blendTwoAttr", "clamp", "angleBetween")
        self.assertEqual(sorted(set(map(cmds.nodeType, nodes))), sorted(allowed))
        self.assertFalse(cmds.ls(type="unitConversion"))
        cmds.delete(self.owner)
        self.assertFalse(cmds.listConnections(self.shape + ".focalLength", source=True, destination=False))
        # 接続を外すと焦点距離の保存値が残らないことがあるため、元の値へ戻してから作り直す。
        cmds.setAttr(self.shape + ".focalLength", 50.0)
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        DollyZoom.create(self.camera, self.subject, name="dolly3")
        self.assertTrue(cmds.objExists("dolly3"))
        cmds.undo()
        self.assertFalse(cmds.objExists("dolly3"))
        self.assertFalse(cmds.listConnections(self.shape + ".focalLength", source=True, destination=False))
        cmds.redo()
        self.assertEqual(cmds.listConnections(self.shape + ".focalLength", source=True, destination=False),
                         ["dolly3"])

    def test_arguments(self):
        """不正な引数は ValueError で、何も残さない。"""
        other = cmds.createNode("transform", name="notCamera")
        behind = cmds.createNode("transform", name="behind", parent=self.camera)
        cmds.setAttr(behind + ".translate", 0.5, 0, 5)
        free = cmds.camera(name="freeCam")[0]
        zero = cmds.camera(name="zeroCam")[0]
        cmds.setAttr(cmds.listRelatives(zero, shapes=True)[0] + ".focalLength", 2.0)
        cases = [
            dict(camera="missing", subject=self.subject),
            dict(camera=other, subject=self.subject),
            dict(camera=self.camera, subject="missing"),
            dict(camera=self.camera, subject=self.camera),
            dict(camera=free, subject=self.subject, weight=1.5),
            dict(camera=free, subject=self.subject, weight=float("nan")),
            dict(camera=free, subject=behind),
            dict(camera=zero, subject=self.subject),
            dict(camera=self.camera, subject=self.subject, name="other"),
            dict(camera=free, subject=self.subject, name="dolly"),
        ]
        before = set(cmds.ls())
        for case in cases:
            with self.assertRaises(ValueError, msg=str(case)):
                DollyZoom.create(**case)
        self.assertEqual(set(cmds.ls()), before)


if __name__ == "__main__":
    unittest.main(argv=["dolly_zoom"], exit=False, verbosity=2)

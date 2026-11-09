"""RibBreathingの肋骨の回転・呼吸の制限・胸骨の追従を、OpenMayaで独立に求めた値と比較する。"""

import math
import unittest

from maya import cmds
from maya.api import OpenMaya as om

from mlrig.setups import RibBreathing

SPINE_POSITION = (1.0, 20.0, -2.0)
UP = om.MVector(0, 1, 0)
# (根元, 中央, 胸骨側の端)。肋骨は前へ下がっていて、左右で対になる。添字0・1が上段、2・3が下段。
RIBS = [
    (om.MVector(1, 4, 0), om.MVector(6, 3, 4), om.MVector(1.5, 1, 8)),
    (om.MVector(-1, 4, 0), om.MVector(-6, 3, 4), om.MVector(-1.5, 1, 8)),
    (om.MVector(1, -2, 0), om.MVector(8, -4, 4), om.MVector(2, -7, 8)),
    (om.MVector(-1, -2, 0), om.MVector(-8, -4, 4), om.MVector(-2, -7, 8)),
]
STERNUM = om.MVector(0, -3, 8.5)
LIMITS = (-0.5, 1.5)
SOFTNESS = 0.1


def _matrix(plug):
    """プラグの行列をMMatrixで返す。"""
    return om.MMatrix(cmds.getAttr(plug))


def _position(matrix):
    """行列の平行移動をMVectorで返す。"""
    return om.MVector(matrix[12], matrix[13], matrix[14])


def _soft(value):
    """呼吸の柔らかい制限を式どおりに計算する。"""
    minimum, maximum = LIMITS
    width = max(SOFTNESS * (maximum - minimum) * 0.5, 1e-3)
    upper, lower = maximum - width, minimum + width
    if value > upper:
        return upper + width * (1 - math.exp(-(value - upper) / width))
    if value < lower:
        return lower - width * (1 - math.exp(-(lower - value) / width))
    return value


def _rotated(point, head, axis, degrees):
    """headを通るaxisのまわりにpointをdegrees度回す。"""
    return head + (point - head).rotateBy(om.MQuaternion(math.radians(degrees), axis))


def _expected(index, breath, pump=10.0, bucket=10.0):
    """肋骨の(中央, 端)をspineの空間で独立に計算する。上段の重みは(1, 0.5)、下段は(0.5, 1)。"""
    head, middle, tip = RIBS[index]
    level = 0.0 if index < 2 else 1.0
    chord = tip - head
    bucket_axis = chord.normal()
    offset = middle - head
    offset = offset - bucket_axis * (offset * bucket_axis)
    sign = 1.0 if ((bucket_axis ^ offset) * UP) > 0 else -1.0
    pump_axis = (chord ^ UP).normal()
    effective = _soft(breath)
    bucket_degrees = effective * bucket * (0.5 + 0.5 * level) * sign
    pump_degrees = effective * pump * (1 - 0.5 * level)
    results = []
    for point in (middle, tip):
        bucketed = _rotated(point, head, bucket_axis, bucket_degrees)
        results.append(_rotated(bucketed, head, pump_axis, pump_degrees))
    return results


class RibBreathingTest(unittest.TestCase):
    """生成時の姿勢・2つの軸の回転・左右の対称・制限・胸骨・親・単位・所有・引数を確認する。"""

    def setUp(self):
        """胸椎の下に4本の肋骨の点と胸骨を置いたシーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(angle="deg", linear="cm")
        self.spine = cmds.createNode("transform", name="spine")
        cmds.setAttr(self.spine + ".translate", *SPINE_POSITION)
        self.ribs = []
        for index, points in enumerate(RIBS):
            names = [self._child("rib{}{}".format(index, label), point) for label, point in zip("HMT", points)]
            self.ribs.append(names)
        self.sternum = self._child("sternum", STERNUM)
        self.setup = RibBreathing.create(self.spine, self.ribs, name="breathing", sternum=self.sternum,
                                         minBreath=LIMITS[0], maxBreath=LIMITS[1], softness=SOFTNESS)
        self.owner = str(self.setup.container)

    def _child(self, name, position):
        """胸椎の子のtransformを作る。"""
        node = cmds.createNode("transform", name=name, parent=self.spine)
        cmds.setAttr(node + ".translate", position.x, position.y, position.z)
        return node

    def _get(self, attribute):
        """containerのアトリビュートの値を返す。"""
        return cmds.getAttr(self.owner + "." + attribute)

    def _breathe(self, value):
        """呼吸の値を設定する。"""
        cmds.setAttr(self.owner + ".breath", value)

    def _local(self, attribute):
        """行列出力の位置をspineの空間で返す。"""
        point = om.MPoint(_position(_matrix(self.owner + "." + attribute))) * _matrix(self.spine + ".worldInverseMatrix[0]")
        return om.MVector(point)

    def _assert_vector(self, actual, expected, delta=1e-4):
        """2つのベクトルが一致することを確かめる。"""
        self.assertLess((actual - expected).length(), delta, msg="{} != {}".format(actual, expected))

    def test_rest(self):
        """breath=0では、出力は生成時の行列のまま、expansion・超過は0で、既定の重みは高さで決まる。"""
        for index, (head, middle, tip) in enumerate(self.ribs):
            self.assertTrue(_matrix("{}.ribMatrix[{}]".format(self.owner, index)).isEquivalent(
                _matrix(head + ".worldMatrix[0]"), 1e-5))
            self._assert_vector(self._local("midMatrix[{}]".format(index)), RIBS[index][1])
            self._assert_vector(self._local("tipMatrix[{}]".format(index)), RIBS[index][2])
        self.assertTrue(_matrix(self.owner + ".sternumMatrix").isEquivalent(_matrix(self.sternum + ".worldMatrix[0]"), 1e-5))
        for attribute in ("effectiveBreath", "excessBreath", "expansion", "sternumLift"):
            self.assertAlmostEqual(self._get(attribute), 0.0, delta=1e-5)
        self.assertAlmostEqual(self._get("pumpWeight[0]"), 1.0, delta=1e-6)
        self.assertAlmostEqual(self._get("bucketWeight[0]"), 0.5, delta=1e-6)
        self.assertAlmostEqual(self._get("pumpWeight[3]"), 0.5, delta=1e-6)
        self.assertAlmostEqual(self._get("bucketWeight[3]"), 1.0, delta=1e-6)

    def test_rotation_matches_openmaya(self):
        """中央と端の位置が2つの軸の回転の合成と一致する。"""
        for breath in (0.4, 1.0, -0.3):
            self._breathe(breath)
            for index in range(len(RIBS)):
                middle, tip = _expected(index, breath)
                self._assert_vector(self._local("midMatrix[{}]".format(index)), middle)
                self._assert_vector(self._local("tipMatrix[{}]".format(index)), tip)

    def test_rib_is_rigid(self):
        """回した後も、根元・中央・端の間の距離が変わらず、根元は動かない。"""
        self._breathe(1.0)
        for index, (head, middle, tip) in enumerate(RIBS):
            head_now = self._local("ribMatrix[{}]".format(index))
            self._assert_vector(head_now, head)
            self.assertAlmostEqual((self._local("midMatrix[{}]".format(index)) - head_now).length(),
                                   (middle - head).length(), delta=1e-5)
            self.assertAlmostEqual((self._local("tipMatrix[{}]".format(index)) - head_now).length(),
                                   (tip - head).length(), delta=1e-5)

    def test_directions(self):
        """吸うと端は上がり、下へ傾いた肋骨では前へ出る。中央は左右とも上がる。"""
        self._breathe(1.0)
        for index, (_, middle, tip) in enumerate(RIBS):
            self.assertGreater(self._local("tipMatrix[{}]".format(index)).y, tip.y)
            self.assertGreater(self._local("tipMatrix[{}]".format(index)).z, tip.z)
            self.assertGreater(self._local("midMatrix[{}]".format(index)).y, middle.y)

    def test_bucket_only_keeps_tip(self):
        """ポンプを0にすると端は動かず、中央だけが動く。左右は鏡像になる。"""
        cmds.setAttr(self.owner + ".pumpAngle", 0)
        self._breathe(1.0)
        for index, (_, middle, tip) in enumerate(RIBS):
            self._assert_vector(self._local("tipMatrix[{}]".format(index)), tip)
            self.assertGreater((self._local("midMatrix[{}]".format(index)) - middle).length(), 0.1)
        left, right = self._local("midMatrix[2]"), self._local("midMatrix[3]")
        self._assert_vector(left, om.MVector(-right.x, right.y, right.z))

    def test_weights_and_angles_are_editable(self):
        """角度と重みは生成後に変更でき、重み0の肋骨は動かない。"""
        cmds.setAttr(self.owner + ".pumpWeight[0]", 0)
        cmds.setAttr(self.owner + ".bucketWeight[0]", 0)
        cmds.setAttr(self.owner + ".pumpAngle", 20)
        self._breathe(1.0)
        self._assert_vector(self._local("tipMatrix[0]"), RIBS[0][2])
        self._assert_vector(self._local("midMatrix[0]"), RIBS[0][1])
        self._assert_vector(self._local("tipMatrix[2]"), _expected(2, 1.0, pump=20.0)[1])

    def test_soft_limit(self):
        """呼吸の値は範囲の内側へ柔らかく止まり、超えた分がexcessBreathになる。"""
        for breath in (1.45, 3.0, 100.0, -0.45, -2.0, -50.0):
            self._breathe(breath)
            effective = self._get("effectiveBreath")
            self.assertAlmostEqual(effective, _soft(breath), delta=1e-5)
            self.assertAlmostEqual(self._get("excessBreath"), breath - _soft(breath), delta=1e-5)
            self.assertLessEqual(effective, LIMITS[1] + 1e-6)
            self.assertGreaterEqual(effective, LIMITS[0] - 1e-6)
        cmds.setAttr(self.owner + ".softness", 0)
        self._breathe(5.0)
        self.assertAlmostEqual(self._get("effectiveBreath"), LIMITS[1], delta=1e-2)

    def test_expansion(self):
        """expansionは中央の点の移動量の平均。"""
        self._breathe(1.0)
        total = sum((_expected(index, 1.0)[0] - RIBS[index][1]).length() for index in range(len(RIBS)))
        self.assertAlmostEqual(self._get("expansion"), total / len(RIBS), delta=1e-4)

    def test_sternum_follows_tips(self):
        """胸骨は端の平均だけ移動し、上下の端の傾きに合わせて回る。"""
        for breath in (1.0, -0.4):
            self._breathe(breath)
            rest_tips = [points[2] for points in RIBS]
            now_tips = [_expected(index, breath)[1] for index in range(len(RIBS))]
            shift = om.MVector()
            for rest, now in zip(rest_tips, now_tips):
                shift += (now - rest) * 0.25
            self._assert_vector(self._local("sternumMatrix"), STERNUM + shift)
            self.assertAlmostEqual(self._get("sternumLift"), shift * UP, delta=1e-4)
            before = (rest_tips[2] + rest_tips[3] - rest_tips[0] - rest_tips[1]).normal()
            after = (now_tips[2] + now_tips[3] - now_tips[0] - now_tips[1]).normal()
            rotation = om.MQuaternion(before, after).asMatrix()
            expected = rotation * _matrix(self.spine + ".worldMatrix[0]")
            actual = _matrix(self.owner + ".sternumMatrix")
            for row in range(3):
                for column in range(3):
                    self.assertAlmostEqual(actual.getElement(row, column), expected.getElement(row, column), delta=1e-4)

    def test_sternal_ribs_selects_tips(self):
        """sternalRibsを指定すると、その肋骨の端だけで胸骨が動く。"""
        graph = RibBreathing.create(self.spine, self.ribs, name="partial", sternum=self.sternum, sternalRibs=[0, 1])
        owner = str(graph.container)
        cmds.setAttr(owner + ".breath", 1.0)
        shift = om.MVector()
        for index in (0, 1):
            shift += (_expected(index, 1.0)[1] - RIBS[index][2]) * 0.5
        point = om.MPoint(_position(_matrix(owner + ".sternumMatrix"))) * _matrix(self.spine + ".worldInverseMatrix[0]")
        self._assert_vector(om.MVector(point), STERNUM + shift)

    def test_order_does_not_matter(self):
        """肋骨の順番を変えても、同じ肋骨の結果は変わらない。"""
        reordered = RibBreathing.create(self.spine, list(reversed(self.ribs)), name="reordered")
        owner = str(reordered.container)
        cmds.setAttr(owner + ".breath", 1.0)
        self._breathe(1.0)
        for index in range(len(RIBS)):
            mirrored = len(RIBS) - 1 - index
            self.assertTrue(_matrix("{}.ribMatrix[{}]".format(owner, mirrored)).isEquivalent(
                _matrix("{}.ribMatrix[{}]".format(self.owner, index)), 1e-5))

    def test_spine_transform(self):
        """胸椎の回転・移動・一様スケールに追従し、spineの空間での形は変わらない。"""
        cmds.setAttr(self.spine + ".rotate", 25, -40, 15)
        cmds.setAttr(self.spine + ".translate", -3, 11, 7)
        cmds.setAttr(self.spine + ".scale", 1.5, 1.5, 1.5)
        self._breathe(1.0)
        for index in range(len(RIBS)):
            middle, tip = _expected(index, 1.0)
            self._assert_vector(self._local("midMatrix[{}]".format(index)), middle)
            self._assert_vector(self._local("tipMatrix[{}]".format(index)), tip)

    def test_inputs_read_once(self):
        """肋骨の点と胸骨は生成時の値だけを使う(出力で動かしても循環しない)。"""
        cmds.setAttr(self.ribs[0][0] + ".translate", 3, 3, 3)
        cmds.setAttr(self.ribs[0][2] + ".translate", 9, 9, 9)
        cmds.setAttr(self.sternum + ".translate", 7, 7, 7)
        self._breathe(1.0)
        self._assert_vector(self._local("tipMatrix[0]"), _expected(0, 1.0)[1])
        self._assert_vector(self._local("ribMatrix[0]"), RIBS[0][0])

    def test_scene_units(self):
        """UIの角度・長さの単位が変わっても出力は変わらない。"""
        self._breathe(1.0)
        expected = _matrix(self.owner + ".tipMatrix[2]")
        expansion = self._get("expansion")
        for angle, linear in (("rad", "cm"), ("deg", "mm"), ("rad", "m")):
            cmds.currentUnit(angle=angle, linear=linear)
            self.assertTrue(_matrix(self.owner + ".tipMatrix[2]").isEquivalent(expected, 1e-5))
            self.assertAlmostEqual(self._get("expansion"), expansion, delta=1e-5)
            cmds.currentUnit(angle="deg", linear="cm")

        def build_in(unit, name):
            """UIの長さ単位をunitにして別の空間にセットアップを作り、(tipの行列, expansion)を返す。"""
            cmds.currentUnit(linear=unit)
            created = RibBreathing.create(self.spine, self.ribs, name=name, sternum=self.sternum)
            cmds.currentUnit(linear="cm")
            owner = str(created.container)
            cmds.setAttr(owner + ".breath", 1.0)
            return _matrix(owner + ".tipMatrix[2]"), cmds.getAttr(owner + ".expansion")

        for unit, name in (("mm", "builtInMm"), ("m", "builtInM")):
            matrix, value = build_in(unit, name)
            self.assertTrue(matrix.isEquivalent(expected, 1e-4))
            self.assertAlmostEqual(value, expansion, delta=1e-4)

    def test_owned_and_undo(self):
        """演算ノードはcontainerが所有し、生成は1回のUndoで消え、Redoで戻る。"""
        cmds.undoInfo(state=True)
        cmds.flushUndo()
        created = str(RibBreathing.create(self.spine, self.ribs, name="undoable").container)
        members = cmds.container(created, query=True, nodeList=True) or []
        self.assertTrue(any(cmds.nodeType(node) == "multMatrix" for node in members))
        self.assertTrue(any(cmds.nodeType(node) == "unitConversion" for node in members))
        cmds.undo()
        self.assertFalse(cmds.objExists(created))
        cmds.redo()
        self.assertTrue(cmds.objExists(created))
        cmds.setAttr(created + ".breath", 1.0)
        self.assertGreater(cmds.getAttr(created + ".expansion"), 0.01)

    def test_invalid_arguments(self):
        """範囲外の引数と不正な入力を拒否する。"""
        ribs = self.ribs
        valid = dict(name="other")
        same_height = [[self._child("flat{}{}".format(i, label), om.MVector(x, 0, z))
                        for label, x, z in (("H", i, 0), ("M", i + 5, 4), ("T", i + 1, 8))] for i in range(2)]
        vertical = [self._child("v" + label, om.MVector(*point))
                    for label, point in (("H", (0, 5, 0)), ("M", (3, 7, 0)), ("T", (0, 9, 0)))]
        straight = [self._child("s" + label, om.MVector(*point))
                    for label, point in (("H", (0, 7, 0)), ("M", (0, 7, 4)), ("T", (0, 7, 8)))]
        duplicate = [ribs[0][0], ribs[0][1], ribs[0][0]]
        bucket_up = [self._child("b" + label, om.MVector(*point))
                     for label, point in (("H", (0, -7, 0)), ("M", (0, -4, 4)), ("T", (0, -7, 8)))]
        cases = [
            dict(pumpAngle=46), dict(bucketAngle=-1), dict(pumpAngle=float("nan")),
            dict(minBreath=0.1), dict(maxBreath=-0.1), dict(softness=2), dict(minBreath=-0.01, maxBreath=4, softness=1),
            dict(up=(0, 0, 0)), dict(sternum=self.sternum, sternalRibs=[9]), dict(sternum=self.sternum, sternalRibs=[]),
        ]
        for kwargs in cases:
            with self.assertRaises(ValueError):
                RibBreathing.create(self.spine, ribs, **dict(valid, **kwargs))
        for rig in ([ribs[0]], same_height, [vertical, ribs[0]], [straight, ribs[0]], [duplicate, ribs[1]],
                    [bucket_up, ribs[0]], [ribs[0][:2], ribs[1]], [[self.spine, ribs[0][1], ribs[0][2]], ribs[1]]):
            with self.assertRaises(ValueError):
                RibBreathing.create(self.spine, rig, **valid)
        with self.assertRaises(ValueError):
            RibBreathing.create(self.spine, ribs, name="breathing")
        material = cmds.createNode("lambert")
        with self.assertRaises(ValueError):
            RibBreathing.create(material, ribs, **valid)
        self.assertFalse(cmds.objExists("other"))


if __name__ == "__main__":
    unittest.main()

"""行列・ベクトルの計算ノードの評価結果を、OpenMayaで独立に求めた値と突き合わせる。

担当A。composeMatrix・decomposeMatrix・inverseMatrix・fourByFourMatrix・multMatrix・
pickMatrix・blendMatrix・aimMatrix・vectorProduct・angleBetween・pairBlend の
``getResult`` 等と、ノード固有のメソッド(ターゲット操作・16要素の設定)の約束を固定する。
"""

import itertools
import math
import unittest
from unittest import mock

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib.util import _ArgumentError

_ORDERS = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")


def _trs(translate=(0, 0, 0), rotate=(0, 0, 0), scale=(1, 1, 1), shear=(0, 0, 0), order=0, quat=None):
    """OpenMayaのMTransformationMatrixで行列を合成する(mlibを使わない期待値)。"""
    tm = om2.MTransformationMatrix()
    tm.setTranslation(om2.MVector(*translate), om2.MSpace.kTransform)
    if quat is None:
        tm.setRotation(om2.MEulerRotation(rotate[0], rotate[1], rotate[2], order))
    else:
        tm.setRotation(om2.MQuaternion(*quat))
    tm.setScale(scale, om2.MSpace.kTransform)
    tm.setShear(shear, om2.MSpace.kTransform)
    return tm.asMatrix()


class _ResultCase(unittest.TestCase):
    """専用名前空間・cm/rad・Undo有効で実行し、終了時に戻す。"""

    def setUp(self):
        cmds.loadPlugin("matrixNodes", quiet=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="rad")
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibSpecAResults")
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


class ComposeDecomposeTest(_ResultCase):
    """composeMatrix/decomposeMatrixとMTransformationMatrixの突き合わせ。"""

    def test_compose_matches_transformation_matrix(self):
        """全回転順で、TRS・シアーの合成結果がMTransformationMatrixと一致する。"""
        node = mlib.createNode("composeMatrix")
        values = ((1.0, -2.0, 3.0), (0.3, -0.7, 1.1), (2.0, 0.5, 1.5), (0.1, -0.2, 0.3))
        node.setTranslate(values[0]).setRotate(values[1]).setScale(values[2]).setShear(values[3])
        for number, name in enumerate(_ORDERS):
            with self.subTest(order=name):
                node.setRotateOrder(name)
                expected = _trs(*values, order=number)
                self.assertClose(node.getResult(), expected)
                self.assertClose(cmds.getAttr(node.getFullName() + ".outputMatrix"), expected)

    def test_compose_quaternion_mode(self):
        """useEulerRotation=FalseではQuaternion入力を使い、Euler入力は無視する。"""
        node = mlib.createNode("composeMatrix")
        quat = om2.MQuaternion(0.3, om2.MVector(1, 2, 3).normal())
        values = (quat.x, quat.y, quat.z, quat.w)
        node.setTranslate((4, 5, 6)).setRotate((1.0, 1.0, 1.0)).setQuaternion(values).setUseEulerRotation(False)
        self.assertClose(node.getResult(), _trs((4, 5, 6), quat=values))
        node.setUseEulerRotation(True)
        self.assertClose(node.getResult(), _trs((4, 5, 6), (1.0, 1.0, 1.0)))

    def test_compose_units_are_internal(self):
        """UI単位をmm/degにしても、取得・設定はcm/radで、出力行列もcmで計算される。"""
        node = mlib.createNode("composeMatrix")
        cmds.currentUnit(linear="mm", angle="deg")
        node.setTranslate((1, 2, 3)).setRotate((0, 0, math.pi / 2))
        self.assertClose(node.getTranslate(), (1, 2, 3))
        self.assertClose(node.getRotate(), (0, 0, math.pi / 2))
        self.assertClose(cmds.getAttr(node.getFullName() + ".inputTranslate")[0], (10, 20, 30))
        self.assertClose(cmds.getAttr(node.getFullName() + ".inputRotate")[0], (0, 0, 90))
        node.setTranslate((4, 5, 6), fast=True)
        self.assertClose(node.getTranslate(), (4, 5, 6))
        self.assertClose(cmds.getAttr(node.getFullName() + ".inputTranslate")[0], (40, 50, 60))
        self.assertClose(tuple(node.getResult())[12:15], (4, 5, 6))

    def test_decompose_outputs(self):
        """出力の移動・回転(各回転順)・スケール・シアー・QuaternionがMTransformationMatrixと一致する。"""
        node = mlib.createNode("decomposeMatrix")
        matrix = _trs((1.5, -2.0, 0.5), (0.4, -0.3, 0.9), (2.0, 1.0, 0.5), (0.2, 0.0, -0.1))
        tm = om2.MTransformationMatrix(matrix)
        for fast in (False, True):
            node.setInput(mlib.maths.Matrix(), fast=fast)
            self.assertIs(node.setInput(matrix, fast=fast), node)
            self.assertClose(node.getInput(), matrix)
            for number, name in enumerate(_ORDERS):
                with self.subTest(order=name, fast=fast):
                    node.setRotateOrder(name, fast=fast)
                    plug = node.getPlug
                    self.assertClose(plug("outputTranslate").get(), tm.translation(om2.MSpace.kTransform))
                    expected = tm.rotation().reorder(number)
                    self.assertClose(plug("outputRotate").get(), (expected.x, expected.y, expected.z))
                    self.assertClose(plug("outputScale").get(), tm.scale(om2.MSpace.kTransform))
                    self.assertClose(plug("outputShear").get(), tm.shear(om2.MSpace.kTransform))
                    quat = tm.rotation(asQuaternion=True)
                    actual = tuple(plug("outputQuat").get())
                    sign = 1.0 if actual[3] * quat.w >= 0 else -1.0
                    self.assertClose(actual, (sign * quat.x, sign * quat.y, sign * quat.z, sign * quat.w))

    def test_decompose_connect_input(self):
        """接続後のgetInputは接続元を評価し、Undoで接続が外れる。"""
        compose = mlib.createNode("composeMatrix").setTranslate((1, 2, 3))
        node = mlib.createNode("decomposeMatrix")
        self.assertIs(node.connectInput(compose.getOutputPlug()), node)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDecomposeMatrixConnectInput")
        self.assertClose(node.getInput(), compose.getResult())
        self.assertClose(node.getPlug("outputTranslate").get(), (1, 2, 3))
        with self.assertRaises(RuntimeError):
            node.setInput(mlib.maths.Matrix())
        cmds.undo()
        self.assertIsNone(cmds.listConnections(node.getFullName() + ".inputMatrix", source=True))
        with self.assertRaises(RuntimeError):
            node.connectInput(compose.getPlug("inputTranslateX"))

    def test_compose_decompose_round_trip(self):
        """composeMatrix→decomposeMatrixの接続で、同じ回転順の成分へ戻る。"""
        compose = mlib.createNode("composeMatrix")
        decompose = mlib.createNode("decomposeMatrix")
        decompose.connectInput(compose.getOutputPlug())
        values = ((3.0, 2.0, 1.0), (0.5, 0.25, -0.75), (1.5, 2.5, 0.5))
        compose.setTranslate(values[0]).setRotate(values[1]).setScale(values[2])
        for number, name in enumerate(_ORDERS):
            with self.subTest(order=name):
                compose.setRotateOrder(name)
                decompose.setRotateOrder(number)
                self.assertClose(decompose.getPlug("outputTranslate").get(), values[0])
                self.assertClose(decompose.getPlug("outputRotate").get(), values[1])
                self.assertClose(decompose.getPlug("outputScale").get(), values[2])


class MatrixUtilityTest(_ResultCase):
    """inverseMatrix・fourByFourMatrix・multMatrix・pickMatrix。"""

    def test_inverse(self):
        """inverseMatrixの結果はMMatrix.inverse()と一致する。"""
        matrix = _trs((1, 2, 3), (0.3, 0.2, 0.1), (2, 1, 0.5), (0.1, 0, 0))
        node = mlib.createNode("inverseMatrix")
        self.assertIs(node.setInput(matrix), node)
        self.assertClose(node.getResult(), matrix.inverse())
        self.assertClose(node.getResult() * matrix, om2.MMatrix())
        compose = mlib.createNode("composeMatrix").setTranslate((5, 0, 0)).setScale((2, 2, 2))
        node.connectInput(compose.getOutputPlug())
        self.assertClose(node.getResult(), om2.MMatrix(compose.getResult()).inverse())

    def test_four_by_four_row_major(self):
        """setMatrixは行優先でin{行}{列}へ書き、getMatrix・getResultと一致する。"""
        values = [float(v) for v in range(1, 17)]
        values[15] = 1.0
        node = mlib.createNode("fourByFourMatrix")
        self.assertIs(node.setMatrix(values), node)
        for row in range(4):
            for column in range(4):
                self.assertEqual(cmds.getAttr("%s.in%d%d" % (node.getFullName(), row, column)), values[row * 4 + column])
        self.assertClose(node.getMatrix(), values)
        self.assertClose(node.getResult(), om2.MMatrix(values))
        self.assertClose(node.getOutputPlug().get(), values)

    def test_four_by_four_undo_fast_and_partial_failure(self):
        """16要素の設定は1回のUndoで戻る。fastはUndoなし。途中の失敗では先に書いた要素が残る。"""
        node = mlib.createNode("fourByFourMatrix")
        matrix = _trs((1, 2, 3), (0.1, 0.2, 0.3))
        node.setMatrix(matrix)
        cmds.undo()
        self.assertClose(node.getMatrix(), om2.MMatrix())
        cmds.redo()
        self.assertClose(node.getMatrix(), matrix)
        sentinel = cmds.createNode("transform")
        cmds.setAttr(sentinel + ".tx", 5)
        with mock.patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")):
            node.setMatrix(om2.MMatrix(), fast=True)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + ".tx"), 0)
        self.assertClose(node.getMatrix(), om2.MMatrix())
        with self.assertRaises(ValueError):
            node.setMatrix([1.0] * 15)
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.setMatrix(matrix, fast=0)
        self.assertClose(node.getMatrix(), om2.MMatrix())
        locked = node.getFullName() + ".in21"
        cmds.setAttr(locked, lock=True)
        try:
            values = [float(v + 2) for v in range(16)]
            for fast in (False, True):
                with self.subTest(fast=fast):
                    for number, value in enumerate(om2.MMatrix()):
                        if number != 9:
                            cmds.setAttr("%s.in%d%d" % (node.getFullName(), number // 4, number % 4), value)
                    with self.assertRaises(RuntimeError):
                        node.setMatrix(values, fast=fast)
                    actual = tuple(node.getMatrix())
                    self.assertEqual(actual[:9], tuple(values[:9]))
                    self.assertEqual(actual[9:], tuple(om2.MMatrix())[9:])
        finally:
            cmds.setAttr(locked, lock=False)

    def test_mult_matrix_logical_order(self):
        """疎な論理番号の昇順に、行ベクトル規約で掛ける(A*B*C)。"""
        a = _trs((1, 0, 0), (0, 0, 0.5))
        b = _trs((0, 2, 0), (0.3, 0, 0), (2, 2, 2))
        c = _trs((0, 0, 3), (0, 0.2, 0))
        node = mlib.createNode("multMatrix")
        node.setInput(7, c).setInput(0, a).setInput(3, b)
        self.assertEqual(sorted(cmds.getAttr(node.getFullName() + ".matrixIn", multiIndices=True)), [0, 3, 7])
        self.assertClose(node.getResult(), a * b * c)
        self.assertClose(node.getOutputPlug().get(), a * b * c)
        for index, matrix in ((0, a), (3, b), (7, c)):
            self.assertClose(node.getInput(index), matrix)
            self.assertEqual(str(node.getInputPlug(idx=index)), "%s.matrixIn[%d]" % (node.getName(), index))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibMultMatrixSetInput")
        cmds.undo()
        self.assertClose(node.getResult(), a * c)
        compose = mlib.createNode("composeMatrix").setTranslate((9, 9, 9))
        node.connectInput(idx=3, src=compose.getOutputPlug())
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibMultMatrixConnectInput")
        self.assertClose(node.getResult(), a * compose.getResult() * c)
        self.assertClose(node.getInput(3), compose.getResult())

    def test_pick_matrix_flags(self):
        """全16通りのuse*の組合せで、選んだ成分だけを合成した行列と一致する。"""
        values = ((1.0, 2.0, 3.0), (0.3, 0.2, 0.1), (2.0, 1.0, 0.5), (0.1, 0.2, 0.3))
        identity = ((0, 0, 0), (0, 0, 0), (1, 1, 1), (0, 0, 0))
        node = mlib.createNode("pickMatrix")
        node.setInput(_trs(*values))
        for flags in itertools.product((True, False), repeat=4):
            with self.subTest(flags=flags):
                node.setUseTranslate(flags[0]).setUseRotate(flags[1]).setUseScale(flags[2]).setUseShear(flags[3])
                picked = [values[i] if flags[i] else identity[i] for i in range(4)]
                self.assertClose(node.getResult(), _trs(*picked))
                self.assertEqual((node.getUseTranslate(), node.getUseRotate(), node.getUseScale(), node.getUseShear()),
                                 flags)


class BlendMatrixTest(_ResultCase):
    """blendMatrixのターゲット操作と評価。"""

    def test_blend_single_target(self):
        """移動・スケールは線形、回転はslerpで補間する。"""
        node = mlib.createNode("blendMatrix")
        target = _trs((10, 0, 0), (0, 0, math.pi / 2), (3, 3, 3))
        self.assertIs(node.setTarget(0, target, 0.5), node)
        quat = om2.MQuaternion.slerp(om2.MQuaternion(), om2.MQuaternion(math.pi / 2, om2.MVector(0, 0, 1)), 0.5)
        expected = _trs((5, 0, 0), scale=(2, 2, 2), quat=(quat.x, quat.y, quat.z, quat.w))
        self.assertClose(node.getResult(), expected)
        node.setTarget(0, target, 0.0)
        self.assertClose(node.getResult(), om2.MMatrix())
        node.setTarget(0, target, 1.0)
        self.assertClose(node.getResult(), target)

    def test_blend_targets_in_order_and_envelope(self):
        """複数ターゲットは番号順に前の結果から補間し、envelopeは各ウェイトに掛かる。"""
        node = mlib.createNode("blendMatrix")
        node.setInput(_trs((0, 0, 0)))
        node.setTarget(4, _trs((0, 20, 0)), 0.5).setTarget(1, _trs((10, 0, 0)), 0.5)
        self.assertEqual(node.getTargetIndices(), [1, 4])
        self.assertClose(tuple(node.getResult())[12:15], (2.5, 10, 0))
        node.setEnvelope(0.5)
        # envelope=0.5で各ウェイトが0.25になる: (10*0.25)*(1-0.25)=1.875、20*0.25=5。
        self.assertClose(tuple(node.getResult())[12:15], (1.875, 5, 0))
        node.setEnvelope(0.0)
        self.assertClose(node.getResult(), node.getInput())

    def test_target_access(self):
        """getTarget/getTargetPlugは既存の番号だけ、setTargetは検証してから書く。"""
        node = mlib.createNode("blendMatrix")
        self.assertEqual(node.getTargetIndices(), [])
        for method in (node.getTarget, node.getTargetPlug):
            with self.assertRaisesRegex(IndexError, "No target at logical index 0"):
                method(0)
        matrix = _trs((1, 2, 3))
        node.setTarget(idx=2, matrix=matrix, weight=0.25)
        target = node.getTarget(2)
        self.assertEqual(sorted(target), ["matrix", "weight"])
        self.assertIsInstance(target["matrix"], mlib.maths.Matrix)
        self.assertClose(target["matrix"], matrix)
        self.assertAlmostEqual(target["weight"], 0.25)
        plug = node.getTargetPlug(idx=2)
        self.assertIsInstance(plug, mlib.plugs.CompoundPlug)
        self.assertEqual(str(plug), node.getName() + ".target[2]")
        self.assertEqual(node.getTarget(2)["matrix"], node.getTarget(idx=2)["matrix"])
        # 検証の失敗では要素を作らない。
        for args, error in (((3, matrix, float("nan")), ValueError), ((3, [1, 2]), ValueError),
                            ((-1, matrix), ValueError), ((True, matrix), ValueError)):
            with self.subTest(args=args):
                with self.assertRaises(error):
                    node.setTarget(*args)
                self.assertEqual(node.getTargetIndices(), [2])
        with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'matrix'"):
            node.setTarget(3)
        with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'index'"):
            node.setTarget(matrix=matrix)
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'index' and 'idx'"):
            node.getTarget(2, idx=2)
        # fastは他のsetXxxと同じ意味で、Undoに残さず書く。
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.setTarget(3, matrix, fast=1)
        self.assertEqual(node.getTargetIndices(), [2])
        for args in ((3, matrix, float("nan")), (3, [1, 2]), (-1, matrix)):
            with self.subTest(args=args, fast=True):
                with self.assertRaises(ValueError):
                    node.setTarget(*args, fast=True)
                self.assertEqual(node.getTargetIndices(), [2])
        sentinel = cmds.createNode("transform")
        cmds.setAttr(sentinel + ".tx", 5)
        with mock.patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")):
            self.assertIs(node.setTarget(3, _trs((0, 4, 0)), 0.6, fast=True), node)
        self.assertEqual(node.getTargetIndices(), [2, 3])
        self.assertClose(node.getTarget(3)["matrix"], _trs((0, 4, 0)))
        self.assertAlmostEqual(node.getTarget(3)["weight"], 0.6)
        cmds.undo()
        self.assertEqual(cmds.getAttr(sentinel + ".tx"), 0)
        self.assertAlmostEqual(node.getTarget(3)["weight"], 0.6)
        path = node.getFullName() + ".target[3].weight"
        cmds.setAttr(path, lock=True)
        try:
            with self.assertRaises(RuntimeError):
                node.setTarget(3, matrix, 0.1, fast=True)
            self.assertAlmostEqual(node.getTarget(3)["weight"], 0.6)
        finally:
            cmds.setAttr(path, lock=False)
        # ターゲットのウェイトには上限が無く、1を超える値もそのまま保持する。
        node.setTarget(5, _trs((7, 0, 0)), 2.0)
        self.assertAlmostEqual(node.getTarget(5)["weight"], 2.0)
        # envelopeは上限1を超えるとMayaがRuntimeErrorにし、値は変わらない。
        with self.assertRaises(RuntimeError):
            node.setEnvelope(2.0)
        self.assertAlmostEqual(node.getEnvelope(), 1.0)

    def test_target_undo_and_remove(self):
        """setTarget・removeTarget・connectTargetはそれぞれ1回のUndoで戻る。"""
        node = mlib.createNode("blendMatrix")
        node.setTarget(1, _trs((1, 0, 0)), 0.4)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibBlendMatrixSetTarget")
        cmds.undo()
        self.assertEqual(node.getTargetIndices(), [])
        cmds.redo()
        self.assertEqual(node.getTargetIndices(), [1])
        source = mlib.createNode("composeMatrix").setTranslate((0, 3, 0))
        self.assertIs(node.connectTarget(1, source.getOutputPlug(), 0.75), node)
        self.assertEqual(cmds.listConnections(node.getFullName() + ".target[1].targetMatrix", source=True),
                         [source.getName()])
        self.assertAlmostEqual(node.getTarget(1)["weight"], 0.75)
        self.assertClose(node.getTarget(1)["matrix"], source.getResult())
        cmds.undo()
        self.assertIsNone(cmds.listConnections(node.getFullName() + ".target[1].targetMatrix", source=True))
        # 接続のUndoでは、接続前からあった要素(weight=0.4)ごと消える。cmdsのconnectAttrのUndoと同じ
        # Mayaの挙動。
        self.assertEqual(node.getTargetIndices(), [])
        node.setTarget(1, _trs((1, 0, 0)), 0.4)
        self.assertIs(node.removeTarget(idx=1), node)
        self.assertEqual(node.getTargetIndices(), [])
        cmds.undo()
        self.assertEqual(node.getTargetIndices(), [1])
        self.assertAlmostEqual(node.getTarget(1)["weight"], 0.4)
        with self.assertRaisesRegex(IndexError, "No element at logical index 7"):
            node.removeTarget(7)
        with self.assertRaises(ValueError):
            node.removeTarget(-1)
        with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'index'"):
            node.removeTarget()

    def test_connect_target_rules(self):
        """connectTargetは接続後にウェイトを設定し、既存接続はforceでだけ置換する。"""
        node = mlib.createNode("blendMatrix")
        first = mlib.createNode("composeMatrix")
        second = mlib.createNode("composeMatrix")
        path = node.getFullName() + ".target[0].targetMatrix"
        node.connectTarget(0, first.getOutputPlug(), 0.3)
        with self.assertRaises(RuntimeError):
            node.connectTarget(0, second.getOutputPlug())
        self.assertEqual(cmds.listConnections(path, source=True), [first.getName()])
        # forceの置換ではweightを省略すると1.0に戻る。
        node.connectTarget(idx=0, src=str(second.getOutputPlug()), f=True)
        self.assertEqual(cmds.listConnections(path, source=True), [second.getName()])
        self.assertAlmostEqual(node.getTarget(0)["weight"], 1.0)
        # ウェイトの検証は接続より前に行う。
        with self.assertRaises(ValueError):
            node.connectTarget(1, first.getOutputPlug(), float("inf"))
        self.assertEqual(node.getTargetIndices(), [0])
        with self.assertRaises(ValueError):
            node.connectTarget(-1, first.getOutputPlug())
        with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'source'"):
            node.connectTarget(1)
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'source' and 'src'"):
            node.connectTarget(1, first.getOutputPlug(), src=first.getOutputPlug())
        with self.assertRaises(TypeError):
            node.connectTarget(1, 5)


class AimMatrixTest(_ResultCase):
    """aimMatrixの評価をベクトル計算と突き合わせる。"""

    def test_aim_primary_and_secondary(self):
        """primaryは目標点へ向け、secondaryは残りの自由度で目標点の方向へ向ける(グラム・シュミット)。"""
        position, aim, up = om2.MVector(1, 1, 1), om2.MVector(1, 5, 1), om2.MVector(4, 1, 2)
        node = mlib.createNode("aimMatrix")
        node.setInput(_trs(tuple(position))).setPrimaryMatrix(_trs(tuple(aim)))
        x = (aim - position).normal()
        result = node.getResult()
        self.assertClose(tuple(result)[0:3], tuple(x))
        self.assertClose(tuple(result)[12:15], tuple(position))
        node.setSecondaryMatrix(_trs(tuple(up))).setSecondaryMode("aim")
        offset = up - position
        y = (offset - x * (offset * x)).normal()
        z = x ^ y
        expected = om2.MMatrix([x.x, x.y, x.z, 0, y.x, y.y, y.z, 0, z.x, z.y, z.z, 0,
                                position.x, position.y, position.z, 1])
        self.assertClose(node.getResult(), expected)
        self.assertClose(node.getOutputPlug().get(), expected)

    def test_aim_modes_and_envelope(self):
        """alignは目標行列の空間のベクトルへ合わせ、lockとenvelope=0は入力のまま。"""
        node = mlib.createNode("aimMatrix")
        node.setInput(_trs((1, 1, 1))).setPrimaryMatrix(_trs((0, 0, 0), (0, 0, math.pi / 2)))
        node.setPrimaryMode("align").setPrimaryVector((1, 0, 0))
        # 目標行列でZ軸周り90度回したX軸は(0, 1, 0)。
        self.assertClose(tuple(node.getResult())[0:3], (0, 1, 0))
        node.setPrimaryMode("lock")
        self.assertClose(node.getResult(), _trs((1, 1, 1)))
        # aimの目標点は目標行列の空間のprimaryTargetVectorなので原点へ戻す。
        node.setPrimaryMode("aim").setPrimaryVector((0, 0, 0)).setPrimaryMatrix(_trs((1, 1, 9))).setEnvelope(0.0)
        self.assertClose(node.getResult(), _trs((1, 1, 1)))
        node.setEnvelope(1.0).setPrimaryAxis((0, 0, 1))
        self.assertClose(node.getResult(), _trs((1, 1, 1)))


class VectorNodesTest(_ResultCase):
    """vectorProduct・angleBetweenとOpenMayaのベクトル演算。"""

    def test_vector_product_operations(self):
        """各演算モードの出力がMVector・MPoint・MMatrixの計算と一致する(float3の精度)。"""
        v1, v2 = om2.MVector(1, 2, 3), om2.MVector(-4, 5, 0.5)
        matrix = _trs((1, 2, 3), (0.3, 0.2, 0.1), (2, 1, 0.5))
        node = mlib.createNode("vectorProduct")
        node.setInput(1, tuple(v1)).setInput(2, tuple(v2)).setMatrix(matrix)
        point = om2.MPoint(v1) * matrix
        table = (
            ("none", tuple(v1)),
            ("dot", (v1 * v2,) * 3),
            ("cross", tuple(v1 ^ v2)),
            ("vector_matrix", tuple(v1 * matrix)),
            ("point_matrix", (point.x, point.y, point.z)),
        )
        for mode, expected in table:
            with self.subTest(mode=mode):
                node.setOperation(mode)
                self.assertIsInstance(node.getResult(), mlib.maths.Vector)
                self.assertClose(node.getResult(), expected, places=4)
        node.setNormalizeOutput(True)
        node.setOperation("dot")
        self.assertClose(node.getResult(), ((v1.normal() * v2.normal()),) * 3, places=5)
        node.setOperation("cross")
        self.assertClose(node.getResult(), tuple((v1 ^ v2).normal()), places=5)

    def test_vector_product_normalize_connect(self):
        """normalizeOutputの接続と、接続中の定数設定の拒否。"""
        node = mlib.createNode("vectorProduct")
        source = mlib.getNode(cmds.createNode("transform"))
        self.assertIs(node.connectNormalizeOutput(source.getPlug("visibility")), node)
        self.assertTrue(node.getNormalizeOutput())
        source.getPlug("visibility").set(False)
        self.assertFalse(node.getNormalizeOutput())
        with self.assertRaises(RuntimeError):
            node.setNormalizeOutput(True)
        cmds.undo()
        cmds.undo()
        self.assertIsNone(cmds.listConnections(node.getFullName() + ".normalizeOutput", source=True))

    def test_angle_between(self):
        """角度・回転軸・Euler回転がMVector.angle・外積・MQuaternionと一致する。"""
        node = mlib.createNode("angleBetween")
        for v1, v2 in (((1, 2, 3), (-2, 1, 0.5)), ((1, 0, 0), (0, 1, 0)), ((0, 0, 2), (0, 3, 3))):
            with self.subTest(v1=v1, v2=v2):
                a, b = om2.MVector(*v1), om2.MVector(*v2)
                node = mlib.createNode("angleBetween")
                node.setInput(1, v1).setInput(2, v2)
                self.assertAlmostEqual(node.getResult(), a.angle(b), places=6)
                # getAxisはcmdsで評価する前から評価済みの値を返す。
                expected = tuple((a ^ b).normal())
                self.assertClose(node.getAxis(), expected)
                self.assertClose(cmds.getAttr(node.getFullName() + ".axis")[0], expected)
                euler = om2.MQuaternion(a, b).asEulerRotation()
                self.assertClose(node.getRotate(), (euler.x, euler.y, euler.z))

    def test_angle_between_axis_without_cmds(self):
        """getAxisはcmdsで評価しなくても評価済みの回転軸を返す。

        axisは複合axisAngleの子で、子Plugだけの読み取りでは再計算されなかった。
        入力の変更・接続元の変更のたびに新しい値になることも確かめる。
        """
        node = mlib.createNode("angleBetween")
        node.setInput(1, (1, 2, 3)).setInput(2, (-2, 1, 0.5))
        node.getResult()
        a, b = om2.MVector(1, 2, 3), om2.MVector(-2, 1, 0.5)
        result = node.getAxis()
        self.assertIsInstance(result, mlib.maths.Vector)
        self.assertClose(result, tuple((a ^ b).normal()))
        node.setInput(2, (0, 0, 5), fast=True)
        self.assertClose(node.getAxis(), tuple((a ^ om2.MVector(0, 0, 5)).normal()))
        source = mlib.getNode(cmds.createNode("transform"))
        node.connectInput(1, source.getPlug("translate"))
        source.getPlug("translate").set((0, 3, 0))
        self.assertClose(node.getAxis(), (1, 0, 0))
        source.getPlug("translate").set((3, 0, 0))
        self.assertClose(node.getAxis(), (0, -1, 0))

    def test_angle_between_units(self):
        """UI単位をdegにしても、getResult・getRotateはradで返す。cmdsはdegで返す。"""
        node = mlib.createNode("angleBetween")
        node.setInput(1, (1, 0, 0)).setInput(2, (0, 1, 0))
        cmds.currentUnit(angle="deg")
        self.assertAlmostEqual(node.getResult(), math.pi / 2)
        self.assertAlmostEqual(cmds.getAttr(node.getFullName() + ".angle"), 90.0)
        self.assertClose(node.getRotate(), (0, 0, math.pi / 2))


class PairBlendTest(_ResultCase):
    """pairBlendの補間結果。"""

    def test_euler_interpolation(self):
        """Euler補間は移動・回転とも成分ごとの線形補間。単位はcm/rad。"""
        node = mlib.createNode("pairBlend")
        t1, t2, r1, r2 = (1, 2, 3), (5, -2, 7), (0.1, 0.2, 0.3), (0.5, -0.4, 0.9)
        node.setTranslate(1, t1).setTranslate(2, t2).setRotate(1, r1).setRotate(2, r2)
        for weight in (0.0, 0.25, 1.0):
            with self.subTest(weight=weight):
                node.setWeight(weight)
                self.assertClose(node.getResult(), [a + (b - a) * weight for a, b in zip(t1, t2)])
                self.assertClose(node.getResult("translate"), node.getResult())
                self.assertClose(node.getResult("rotate"), [a + (b - a) * weight for a, b in zip(r1, r2)])
        cmds.currentUnit(linear="mm", angle="deg")
        self.assertClose(node.getResult("rotate"), r2)
        self.assertClose(node.getResult("translate"), t2)

    def test_quaternion_interpolation(self):
        """Quaternion補間はslerpで、出力のEulerは設定した回転順で表す。"""
        node = mlib.createNode("pairBlend")
        r1, r2 = (0.2, 0.0, 0.0), (0.0, 1.2, 0.4)
        node.setRotate(1, r1).setRotate(2, r2).setRotateInterpolation("quaternion").setWeight(0.3)
        for number, name in enumerate(_ORDERS):
            with self.subTest(order=name):
                node.setRotateOrder(name)
                q1 = om2.MEulerRotation(r1[0], r1[1], r1[2], number).asQuaternion()
                q2 = om2.MEulerRotation(r2[0], r2[1], r2[2], number).asQuaternion()
                expected = om2.MQuaternion.slerp(q1, q2, 0.3).asMatrix()
                result = node.getResult("rotate")
                actual = om2.MEulerRotation(result[0], result[1], result[2], number).asMatrix()
                self.assertClose(actual, expected)


if __name__ == "__main__":
    unittest.main()

"""計算ノードの get/set/connect/Plug 系メソッドの共通の約束を、表で網羅的に固定する。

担当A。対象は aimMatrix・blendMatrix・composeMatrix・decomposeMatrix・inverseMatrix・
multMatrix・pickMatrix・pairBlend・vectorProduct・angleBetween の入力アクセサーと、
列挙値(モード・回転順)のアクセサー。各行について次を確かめる。

- ``getXxxPlug`` が対象アトリビュートを返す。``setXxx`` は自身を返し、値が往復する。
- 通常の設定は1回のUndoで戻り、Redoで再適用される。
- ``fast=True`` は cmds.setAttr を使わず、Undoに記録しない。fastがbool以外ならTypeError。
- 不正な値は検証で拒否し、値を変えない。ロック・入力接続ありの設定はRuntimeError。
- ``connectXxx`` は接続し、既存接続はforce=Trueでだけ置き換える。接続はUndoで戻る。
"""

import math
import unittest
from unittest import mock

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib
from mlib.util import _ArgumentError


_MATRIX = (1.0, 0.0, 0.0, 0.0,
           0.0, 0.0, 1.0, 0.0,
           0.0, -1.0, 0.0, 0.0,
           3.0, 4.0, 5.0, 1.0)

# kindごとの不正値と例外型。
_INVALID = {
    "vector3": (((1, 2), ValueError), ((1, 2, float("nan")), ValueError), ((1, 2, 3, 4), ValueError),
                (None, TypeError)),
    "vector4": (((0, 0, 1), ValueError), ((0, 0, 0, float("inf")), ValueError), (None, TypeError)),
    "scalar": ((float("inf"), ValueError), ("x", ValueError), (None, TypeError)),
    "bool": ((1, TypeError), ("True", TypeError), (None, TypeError)),
    "matrix": (((1, 2, 3), ValueError), ([0.0] * 15, ValueError)),
}

# (Maya型, メソッドの語幹, 番号の位置引数, アトリビュート名, 設定値, 値の種類, 接続元の種類, Plug取得の有無)
_ACCESSORS = (
    ("composeMatrix", "Translate", (), "inputTranslate", (1.0, -2.0, 3.5), "vector3", "translate", True),
    ("composeMatrix", "Rotate", (), "inputRotate", (0.1, -0.2, 0.3), "vector3", "rotate", True),
    ("composeMatrix", "Scale", (), "inputScale", (2.0, 3.0, 0.5), "vector3", "scale", True),
    ("composeMatrix", "Shear", (), "inputShear", (0.1, 0.2, -0.3), "vector3", "scale", True),
    ("composeMatrix", "Quaternion", (), "inputQuat", (0.0, 0.0, math.sqrt(0.5), math.sqrt(0.5)),
     "vector4", "quat", True),
    ("composeMatrix", "UseEulerRotation", (), "useEulerRotation", False, "bool", "visibility", True),
    ("aimMatrix", "Input", (), "inputMatrix", _MATRIX, "matrix", "matrix", True),
    ("aimMatrix", "Envelope", (), "envelope", 0.5, "scalar", "scaleX", True),
    ("aimMatrix", "PrimaryMatrix", (), "primaryTargetMatrix", _MATRIX, "matrix", "matrix", True),
    ("aimMatrix", "PrimaryAxis", (), "primaryInputAxis", (0.0, 1.0, 0.0), "vector3", "scale", True),
    ("aimMatrix", "PrimaryVector", (), "primaryTargetVector", (0.0, 0.0, 1.0), "vector3", "scale", True),
    ("aimMatrix", "SecondaryMatrix", (), "secondaryTargetMatrix", _MATRIX, "matrix", "matrix", True),
    ("aimMatrix", "SecondaryAxis", (), "secondaryInputAxis", (0.0, 0.0, 1.0), "vector3", "scale", True),
    ("aimMatrix", "SecondaryVector", (), "secondaryTargetVector", (1.0, 0.0, 0.0), "vector3", "scale", True),
    ("blendMatrix", "Input", (), "inputMatrix", _MATRIX, "matrix", "matrix", True),
    ("blendMatrix", "Envelope", (), "envelope", 0.5, "scalar", "scaleX", True),
    ("pickMatrix", "Input", (), "inputMatrix", _MATRIX, "matrix", "matrix", True),
    ("pickMatrix", "UseTranslate", (), "useTranslate", False, "bool", "visibility", True),
    ("pickMatrix", "UseRotate", (), "useRotate", False, "bool", "visibility", True),
    ("pickMatrix", "UseScale", (), "useScale", False, "bool", "visibility", True),
    ("pickMatrix", "UseShear", (), "useShear", False, "bool", "visibility", True),
    ("inverseMatrix", "Input", (), "inputMatrix", _MATRIX, "matrix", "matrix", True),
    ("decomposeMatrix", "Input", (), "inputMatrix", _MATRIX, "matrix", "matrix", True),
    ("multMatrix", "Input", (0,), "matrixIn[0]", _MATRIX, "matrix", "matrix", True),
    ("multMatrix", "Input", (5,), "matrixIn[5]", _MATRIX, "matrix", "matrix", True),
    ("pairBlend", "Weight", (), "weight", 0.25, "scalar", "scaleX", True),
    ("pairBlend", "Translate", (1,), "inTranslate1", (1.0, 2.0, 3.0), "vector3", "translate", True),
    ("pairBlend", "Translate", (2,), "inTranslate2", (-1.0, 0.5, 2.0), "vector3", "translate", True),
    ("pairBlend", "Rotate", (1,), "inRotate1", (0.1, 0.2, 0.3), "vector3", "rotate", True),
    ("pairBlend", "Rotate", (2,), "inRotate2", (-0.3, 0.2, 0.1), "vector3", "rotate", True),
    ("vectorProduct", "Input", (1,), "input1", (1.0, 2.0, 3.0), "vector3", "scale", True),
    ("vectorProduct", "Input", (2,), "input2", (-1.0, 0.5, 4.0), "vector3", "scale", True),
    ("vectorProduct", "Matrix", (), "matrix", _MATRIX, "matrix", "matrix", True),
    ("vectorProduct", "NormalizeOutput", (), "normalizeOutput", True, "bool", "visibility", False),
    ("angleBetween", "Input", (1,), "vector1", (1.0, 1.0, 0.0), "vector3", "scale", True),
    ("angleBetween", "Input", (2,), "vector2", (0.0, 1.0, 1.0), "vector3", "scale", True),
)

# (Maya型, 取得メソッド, 設定メソッド, アトリビュート名, 公開名の並び)
_ENUMS = (
    ("composeMatrix", "getRotateOrder", "setRotateOrder", "inputRotateOrder",
     ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")),
    ("aimMatrix", "getPrimaryMode", "setPrimaryMode", "primaryMode", ("lock", "aim", "align")),
    ("aimMatrix", "getSecondaryMode", "setSecondaryMode", "secondaryMode", ("none", "aim", "align")),
    ("pairBlend", "getRotateInterpolation", "setRotateInterpolation", "rotInterpolation", ("euler", "quaternion")),
    ("pairBlend", "getRotateOrder", "setRotateOrder", "rotateOrder", ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")),
    ("vectorProduct", "getOperation", "setOperation", "operation",
     ("none", "dot", "cross", "vector_matrix", "point_matrix")),
)


# 担当範囲のクラスが自身で定義する公開メソッド(現在の公開APIの一覧として固定する)。
_PUBLIC_API = {
    "AimMatrix": (
        "connectEnvelope", "connectInput", "connectPrimaryAxis", "connectPrimaryMatrix", "connectPrimaryVector",
        "connectSecondaryAxis", "connectSecondaryMatrix", "connectSecondaryVector", "getEnvelope",
        "getEnvelopePlug", "getInput", "getInputPlug", "getOutputPlug", "getPrimaryAxis", "getPrimaryAxisPlug",
        "getPrimaryMatrix", "getPrimaryMatrixPlug", "getPrimaryMode", "getPrimaryVector", "getPrimaryVectorPlug",
        "getResult", "getSecondaryAxis", "getSecondaryAxisPlug", "getSecondaryMatrix", "getSecondaryMatrixPlug",
        "getSecondaryMode", "getSecondaryVector", "getSecondaryVectorPlug", "setEnvelope", "setInput",
        "setPrimaryAxis", "setPrimaryMatrix", "setPrimaryMode", "setPrimaryVector", "setSecondaryAxis",
        "setSecondaryMatrix", "setSecondaryMode", "setSecondaryVector"),
    "AngleBetween": ("connectInput", "getAxis", "getInput", "getInputPlug", "getResult", "getRotate", "setInput"),
    "BlendMatrix": (
        "connectEnvelope", "connectInput", "connectTarget", "getEnvelope", "getEnvelopePlug", "getInput",
        "getInputPlug", "getOutputPlug", "getResult", "getTarget", "getTargetIndices", "getTargetPlug",
        "removeTarget", "setEnvelope", "setInput", "setTarget"),
    "ComposeMatrix": (
        "connectQuaternion", "connectRotate", "connectScale", "connectShear", "connectTranslate",
        "connectUseEulerRotation", "getOutputPlug", "getQuaternion", "getQuaternionPlug", "getResult", "getRotate",
        "getRotateOrder", "getRotatePlug", "getScale", "getScalePlug", "getShear", "getShearPlug", "getTranslate",
        "getTranslatePlug", "getUseEulerRotation", "getUseEulerRotationPlug", "setQuaternion", "setRotate",
        "setRotateOrder", "setScale", "setShear", "setTranslate", "setUseEulerRotation"),
    "CurveInfo": ("connectCurve",),
    "DecomposeMatrix": ("connectInput", "getInput", "getInputPlug", "getRotateOrder", "setInput", "setRotateOrder"),
    "DistanceBetween": ("connectTransforms", "getDistance", "setPoints"),
    "File": ("getColorSpace", "getFilePath", "setColorSpace", "setFilePath"),
    "FourByFourMatrix": ("getMatrix", "getOutputPlug", "getResult", "setMatrix"),
    "InverseMatrix": ("connectInput", "getInput", "getInputPlug", "getOutputPlug", "getResult", "setInput"),
    "MultMatrix": ("connectInput", "getInput", "getInputPlug", "getOutputPlug", "getResult", "setInput"),
    "PairBlend": (
        "connectRotate", "connectTranslate", "connectWeight", "getOutputPlug", "getResult", "getRotate",
        "getRotateInterpolation", "getRotateOrder", "getRotatePlug", "getTranslate", "getTranslatePlug",
        "getWeight", "getWeightPlug", "setRotate", "setRotateInterpolation", "setRotateOrder", "setTranslate",
        "setWeight"),
    "PickMatrix": (
        "connectInput", "connectUseRotate", "connectUseScale", "connectUseShear", "connectUseTranslate", "getInput",
        "getInputPlug", "getOutputPlug", "getResult", "getUseRotate", "getUseRotatePlug", "getUseScale",
        "getUseScalePlug", "getUseShear", "getUseShearPlug", "getUseTranslate", "getUseTranslatePlug", "setInput",
        "setUseRotate", "setUseScale", "setUseShear", "setUseTranslate"),
    "Place2dTexture": ("connectTexture",),
    "PointOnCurveInfo": ("connectCurve", "getNormal", "getPosition", "getTangent", "setParameter"),
    "PointOnSurfaceInfo": ("connectSurface", "getNormal", "getParameters", "getPosition", "getTangent",
                           "setParameters"),
    "Texture2d": ("getPlacement",),
    "VectorProduct": (
        "connectInput", "connectMatrix", "connectNormalizeOutput", "getInput", "getInputPlug", "getMatrix",
        "getMatrixPlug", "getNormalizeOutput", "getOperation", "getResult", "setInput", "setMatrix",
        "setNormalizeOutput", "setOperation"),
}

# 表ではなく個別のテストで確かめるメソッド(クラス名, メソッド名)。
_DEDICATED = {
    ("AngleBetween", "getAxis"), ("AngleBetween", "getResult"), ("AngleBetween", "getRotate"),
    ("BlendMatrix", "connectTarget"), ("BlendMatrix", "getTarget"), ("BlendMatrix", "getTargetIndices"),
    ("BlendMatrix", "getTargetPlug"), ("BlendMatrix", "removeTarget"), ("BlendMatrix", "setTarget"),
    ("DecomposeMatrix", "getRotateOrder"), ("DecomposeMatrix", "setRotateOrder"),
    ("FourByFourMatrix", "getMatrix"), ("FourByFourMatrix", "setMatrix"),
    ("VectorProduct", "getNormalizeOutput"),
}


def _flat(value):
    """Matrix・Vector・tuple・cmdsの[(x, y, z)]を平らなtupleへ揃える。"""
    if isinstance(value, (bool, int, float)):
        return (value,)
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], tuple):
        value = value[0]
    return tuple(value)


class _CalcCase(unittest.TestCase):
    """専用名前空間・内部単位(cm/rad)・Undo有効の状態で実行し、終了時に戻す。"""

    @staticmethod
    def methods(node, stem):
        """語幹からget/set/connect/Plug取得のメソッドを返す。"""
        return (getattr(node, "get" + stem), getattr(node, "set" + stem), getattr(node, "connect" + stem),
                getattr(node, "get" + stem + "Plug", None))

    def setUp(self):
        cmds.loadPlugin("matrixNodes", quiet=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="rad")
        self.old_namespace = cmds.namespaceInfo(currentNamespace=True)
        self.namespace = cmds.namespace(add="mlibSpecAAccessors")
        cmds.namespace(set=self.namespace)

    def tearDown(self):
        cmds.namespace(set=self.old_namespace)
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])
        cmds.undoInfo(state=self.undo_state)

    def assertClose(self, actual, expected, places=5):
        """bool・スカラー・成分列を比較する。float3入力の精度に合わせて小数5桁。"""
        actual, expected = _flat(actual), _flat(expected)
        self.assertEqual(len(actual), len(expected), (actual, expected))
        for a, e in zip(actual, expected):
            if isinstance(e, bool):
                self.assertEqual(bool(a), e)
            else:
                self.assertAlmostEqual(a, e, places=places)

    def assertSource(self, path, expected):
        """pathの入力接続元が、expected(Plug)と同じMPlugか(Noneなら接続なし)。"""
        sources = cmds.listConnections(path, source=True, destination=False, plugs=True)
        if expected is None:
            self.assertIsNone(sources)
            return
        self.assertEqual(len(sources or ()), 1, sources)
        plugs = []
        for name in (sources[0], expected.getName()):
            selection = om2.MSelectionList()
            selection.add(name)
            plugs.append(selection.getPlug(0))
        self.assertEqual(plugs[0], plugs[1], (sources[0], expected.getName()))

    def make_source(self):
        """接続元のtransformとdecomposeMatrixを作り、種類ごとのPlugと期待値を返す。"""
        name = cmds.createNode("transform")
        cmds.setAttr(name + ".translate", 1.5, 2.5, -3.5)
        cmds.setAttr(name + ".rotate", 0.2, -0.1, 0.4)
        cmds.setAttr(name + ".scale", 0.5, 0.25, 0.75)
        cmds.setAttr(name + ".visibility", False)
        decompose = cmds.createNode("decomposeMatrix")
        cmds.connectAttr(name + ".matrix", decompose + ".inputMatrix")
        node = mlib.getNode(name)
        plugs = {
            "translate": (node.getPlug("translate"), (1.5, 2.5, -3.5)),
            "rotate": (node.getPlug("rotate"), (0.2, -0.1, 0.4)),
            "scale": (node.getPlug("scale"), (0.5, 0.25, 0.75)),
            "scaleX": (node.getPlug("scaleX"), 0.5),
            "visibility": (node.getPlug("visibility"), False),
            "matrix": (node.getPlug("matrix"), tuple(cmds.getAttr(name + ".matrix"))),
            "quat": (mlib.getNode(decompose).getPlug("outputQuat"), cmds.getAttr(decompose + ".outputQuat")[0]),
        }
        return name, plugs


class AccessorTableTest(_CalcCase):
    """_ACCESSORSの各行について共通の約束を確かめる。"""

    def test_plug_and_round_trip(self):
        """Plugの名前と、設定値の取得・cmdsでの読み戻しが一致する。setは自身を返す。"""
        for kind, stem, index, attr, value, _, _, has_plug in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                node = mlib.createNode(kind)
                getter, setter, _, plug_getter = self.methods(node, stem)
                self.assertIs(setter(*index, value), node)
                self.assertClose(getter(*index), value)
                self.assertClose(cmds.getAttr(node.getFullName() + "." + attr), value)
                if has_plug:
                    plug = plug_getter(*index)
                    self.assertIsInstance(plug, mlib.plugs.Plug)
                    self.assertEqual(str(plug), node.getName() + "." + attr)
                else:
                    self.assertIsNone(plug_getter)

    def test_undo_redo(self):
        """通常の設定は1回のUndoで設定前へ戻り、Redoで再適用される。"""
        for kind, stem, index, attr, value, _, _, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                node = mlib.createNode(kind)
                getter, setter, _, _ = self.methods(node, stem)
                if kind == "multMatrix":
                    setter(*index, om2.MMatrix())
                before = getter(*index)
                setter(*index, value)
                self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibMultMatrixSetInput"
                                 if kind == "multMatrix" else "mlibDecomposeMatrixSetInput"
                                 if kind == "decomposeMatrix" else "mlibCalculationEdit")
                cmds.undo()
                self.assertClose(getter(*index), before)
                cmds.redo()
                self.assertClose(getter(*index), value)

    def test_fast_skips_cmds_and_undo(self):
        """fast=Trueはcmds.setAttrを使わず、Undoに記録しない。"""
        for kind, stem, index, attr, value, _, _, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                node = mlib.createNode(kind)
                getter, setter, _, _ = self.methods(node, stem)
                sentinel = cmds.createNode("transform")
                cmds.setAttr(sentinel + ".tx", 5)
                with mock.patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")):
                    self.assertIs(setter(*index, value, fast=True), node)
                self.assertClose(getter(*index), value)
                cmds.undo()
                self.assertEqual(cmds.getAttr(sentinel + ".tx"), 0)
                self.assertClose(getter(*index), value)

    def test_fast_must_be_bool(self):
        """fastがbool以外ならTypeErrorで、値は変わらない。"""
        for kind, stem, index, attr, value, _, _, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                node = mlib.createNode(kind)
                getter, setter, _, _ = self.methods(node, stem)
                if kind == "multMatrix":
                    setter(*index, om2.MMatrix())
                before = getter(*index)
                for flag in (1, None, "True"):
                    with self.assertRaisesRegex(TypeError, "fast must be a bool"):
                        setter(*index, value, fast=flag)
                self.assertClose(getter(*index), before)

    def test_invalid_values(self):
        """不正な値は種類ごとの例外で拒否し、通常・fastとも値を変えない。"""
        for kind, stem, index, attr, value, value_kind, _, _ in _ACCESSORS:
            node = mlib.createNode(kind)
            getter, setter, _, _ = self.methods(node, stem)
            if kind == "multMatrix":
                setter(*index, om2.MMatrix())
            before = getter(*index)
            for bad, error in _INVALID[value_kind]:
                for fast in (False, True):
                    with self.subTest(kind=kind, stem=stem, index=index, bad=bad, fast=fast):
                        with self.assertRaises(error):
                            setter(*index, bad, fast=fast)
                        self.assertClose(getter(*index), before)

    def test_locked(self):
        """ロックしたアトリビュートへの設定は通常・fastともRuntimeErrorで、値もロックも変えない。"""
        for kind, stem, index, attr, value, _, _, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                node = mlib.createNode(kind)
                getter, setter, _, _ = self.methods(node, stem)
                if kind == "multMatrix":
                    setter(*index, om2.MMatrix())
                before = getter(*index)
                path = node.getFullName() + "." + attr
                cmds.setAttr(path, lock=True)
                try:
                    for fast in (False, True):
                        with self.assertRaises(RuntimeError):
                            setter(*index, value, fast=fast)
                    self.assertClose(getter(*index), before)
                    self.assertTrue(cmds.getAttr(path, lock=True))
                finally:
                    cmds.setAttr(path, lock=False)

    def test_connect(self):
        """接続後のgetは接続元を評価し、定数の設定は接続を切らずにRuntimeError。"""
        for kind, stem, index, attr, value, _, source_kind, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                _, plugs = self.make_source()
                source, expected = plugs[source_kind]
                node = mlib.createNode(kind)
                getter, setter, connector, _ = self.methods(node, stem)
                self.assertIs(connector(*index, source), node)
                path = node.getFullName() + "." + attr
                self.assertSource(path, source)
                self.assertClose(getter(*index), expected)
                for fast in (False, True):
                    with self.assertRaises(RuntimeError):
                        setter(*index, value, fast=fast)
                self.assertSource(path, source)

    def test_connect_force_and_undo(self):
        """既存の入力はforce=Trueでだけ置き換え、接続・置換はそれぞれ1回のUndoで戻る。"""
        for kind, stem, index, attr, value, _, source_kind, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                first = self.make_source()[1][source_kind][0]
                second = self.make_source()[1][source_kind][0]
                node = mlib.createNode(kind)
                connector = self.methods(node, stem)[2]
                path = node.getFullName() + "." + attr

                connector(*index, first)
                with self.assertRaises(RuntimeError):
                    connector(*index, second)
                self.assertSource(path, first)
                self.assertIs(connector(*index, src=second, f=True), node)
                self.assertSource(path, second)
                cmds.undo()
                self.assertSource(path, first)
                cmds.undo()
                self.assertSource(path, None)
                cmds.redo()
                self.assertSource(path, first)

    def test_connect_arguments(self):
        """sourceとsrc、forceとfの同時指定と、sourceの省略はTypeError(_ArgumentError)。"""
        for kind, stem, index, attr, value, _, source_kind, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                source = self.make_source()[1][source_kind][0]
                node = mlib.createNode(kind)
                connector = self.methods(node, stem)[2]
                with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'source' and 'src'"):
                    connector(*index, source, src=source)
                with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'force' and 'f'"):
                    connector(*index, source, force=True, f=True)
                with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'source'"):
                    connector(*index)
                self.assertIsInstance(_ArgumentError(), TypeError)
                path = node.getFullName() + "." + attr.split("[")[0]
                self.assertFalse(cmds.listConnections(path, source=True, destination=False))

    def test_connect_locked(self):
        """ロックした入力への接続はRuntimeErrorで、接続もロックの解除もしない。"""
        for kind, stem, index, attr, value, _, source_kind, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                source = self.make_source()[1][source_kind][0]
                node = mlib.createNode(kind)
                getter, setter, connector, _ = self.methods(node, stem)
                if kind == "multMatrix":
                    setter(*index, om2.MMatrix())
                path = node.getFullName() + "." + attr
                cmds.setAttr(path, lock=True)
                try:
                    with self.assertRaises(RuntimeError):
                        connector(*index, source)
                    self.assertIsNone(cmds.listConnections(path, source=True, destination=False))
                    self.assertTrue(cmds.getAttr(path, lock=True))
                finally:
                    cmds.setAttr(path, lock=False)

    def test_connect_source_forms(self):
        """接続元はPlug・名前・MPlugを受け付け、ノードや数値はTypeError。

        decomposeMatrixも他の計算ノードと同じく名前・MPlugを受け付ける(FINDINGS A-1 で修正)。
        """
        for kind, stem, index, attr, value, _, source_kind, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                source = self.make_source()[1][source_kind][0]
                for form in (source.getName(), source.mplug()):
                    node = mlib.createNode(kind)
                    connector = self.methods(node, stem)[2]
                    path = node.getFullName() + "." + attr
                    self.assertIs(connector(*index, form), node)
                    self.assertSource(path, source)
                node = mlib.createNode(kind)
                connector = self.methods(node, stem)[2]
                path = node.getFullName() + "." + attr
                for bad in (5, node):
                    with self.assertRaises(TypeError):
                        connector(*index, bad)
                    self.assertIsNone(cmds.listConnections(path, source=True, destination=False))

    def test_undo_disabled(self):
        """Undoが無効でも通常の設定・接続は成功し、Undoの設定を変えない。"""
        for kind, stem, index, attr, value, _, source_kind, _ in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                source = self.make_source()[1][source_kind][0]
                node = mlib.createNode(kind)
                getter, setter, connector, _ = self.methods(node, stem)
                cmds.undoInfo(state=False)
                try:
                    setter(*index, value)
                    self.assertFalse(cmds.undoInfo(query=True, state=True))
                    self.assertClose(getter(*index), value)
                    connector(*index, source, force=True)
                    self.assertFalse(cmds.undoInfo(query=True, state=True))
                finally:
                    cmds.undoInfo(state=True)

    def test_deleted_node(self):
        """削除済みのノードでは取得・設定・Plug取得がRuntimeError。"""
        for kind, stem, index, attr, value, _, _, has_plug in _ACCESSORS:
            with self.subTest(kind=kind, stem=stem, index=index):
                node = mlib.createNode(kind)
                getter, setter, connector, plug_getter = self.methods(node, stem)
                cmds.delete(node.getFullName())
                with self.assertRaises(RuntimeError):
                    getter(*index)
                with self.assertRaises(RuntimeError):
                    setter(*index, value)
                if has_plug:
                    with self.assertRaises(RuntimeError):
                        plug_getter(*index)


class IndexedAccessorTest(_CalcCase):
    """入力番号を取るメソッドの番号の検証と別名idx。"""

    _INDEXED = (
        ("pairBlend", "Translate", (1, 2), (1.0, 2.0, 3.0)),
        ("pairBlend", "Rotate", (1, 2), (0.1, 0.2, 0.3)),
        ("vectorProduct", "Input", (1, 2), (1.0, 2.0, 3.0)),
        ("angleBetween", "Input", (1, 2), (1.0, 2.0, 3.0)),
    )

    def test_index_one_or_two(self):
        """番号は1または2だけ。0・3・bool・floatはValueError。idxは別名で、同時指定・省略はTypeError。"""
        for kind, stem, allowed, value in self._INDEXED:
            with self.subTest(kind=kind, stem=stem):
                node = mlib.createNode(kind)
                getter, setter, connector, plug_getter = self.methods(node, stem)
                for index in allowed:
                    setter(idx=index, value=value)
                    self.assertClose(getter(idx=index), value)
                    self.assertEqual(str(plug_getter(idx=index)), str(plug_getter(index)))
                for bad in (0, 3, -1, True, 1.0, "1"):
                    with self.assertRaises(ValueError):
                        plug_getter(bad)
                    with self.assertRaises(ValueError):
                        getter(bad)
                    with self.assertRaises(ValueError):
                        setter(bad, value)
                    with self.assertRaises(ValueError):
                        connector(bad, node.getPlug("message"))
                for method in (plug_getter, getter):
                    with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'index' and 'idx'"):
                        method(1, idx=1)
                    with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'index'"):
                        method()
                with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'value'"):
                    setter(1)
                with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'index'"):
                    connector(src=node.getPlug("message"))

    def test_multmatrix_index(self):
        """multMatrixの番号は非負整数。既存要素のない番号の取得はIndexError。

        2**31以上はgetInputPlug・setInput・connectInputともIndexError(docstringを修正。FINDINGS A-2 で修正)。
        """
        node = mlib.createNode("multMatrix")
        with self.assertRaisesRegex(IndexError, "No input at logical index 0"):
            node.getInputPlug(0)
        with self.assertRaisesRegex(IndexError, "No input at logical index 0"):
            node.getInput(0)
        source = self.make_source()[1]["matrix"][0]
        for bad in (-1, True, 1.0, "0", None):
            with self.subTest(bad=bad):
                for call in (lambda: node.getInputPlug(bad), lambda: node.setInput(bad, _MATRIX),
                             lambda: node.connectInput(bad, source)):
                    with self.assertRaisesRegex(ValueError, "non-negative integer"):
                        call()
        for call in (lambda: node.getInputPlug(2 ** 31), lambda: node.setInput(2 ** 31, _MATRIX),
                     lambda: node.connectInput(2 ** 31, source)):
            with self.assertRaisesRegex(IndexError, "Logical index must be in 0..2147483647"):
                call()
        self.assertEqual(cmds.getAttr(node.getFullName() + ".matrixIn", multiIndices=True), None)
        node.setInput(idx=2147483647, value=_MATRIX)
        self.assertClose(node.getInput(idx=2147483647), _MATRIX)
        with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'value'"):
            node.setInput(0)
        with self.assertRaisesRegex(_ArgumentError, "Missing required argument: 'source'"):
            node.connectInput(0)
        with self.assertRaisesRegex(_ArgumentError, "Specify only one of 'index' and 'idx'"):
            node.connectInput(0, source, idx=0)


class EnumAccessorTest(_CalcCase):
    """_ENUMSの各行について列挙値の約束を確かめる。"""

    def test_names_and_numbers(self):
        """名前(大文字小文字を問わない)と番号の両方で設定でき、取得は小文字の公開名。"""
        for kind, get_name, set_name, attr, names in _ENUMS:
            with self.subTest(kind=kind, attr=attr):
                node = mlib.createNode(kind)
                getter, setter = getattr(node, get_name), getattr(node, set_name)
                maya_names = cmds.attributeQuery(attr, node=node.getFullName(), listEnum=True)[0].split(":")
                self.assertEqual(len(maya_names), len(names))
                path = node.getFullName() + "." + attr
                for number, name in enumerate(names):
                    self.assertIs(setter(name.upper()), node)
                    self.assertEqual(getter(), name)
                    self.assertEqual(cmds.getAttr(path), number)
                    setter(0)
                    self.assertIs(setter(number), node)
                    self.assertEqual(getter(), name)

    def test_invalid(self):
        """未対応の名前・範囲外・bool・float・数字の文字列はValueErrorで、値を変えない。"""
        for kind, get_name, set_name, attr, names in _ENUMS:
            node = mlib.createNode(kind)
            getter, setter = getattr(node, get_name), getattr(node, set_name)
            before = getter()
            for bad in ("bogus", "", "1", len(names), -1, True, 1.0, None):
                for fast in (False, True):
                    with self.subTest(kind=kind, attr=attr, bad=bad, fast=fast):
                        with self.assertRaises(ValueError):
                            setter(bad, fast=fast)
                        self.assertEqual(getter(), before)
            with self.assertRaisesRegex(TypeError, "fast must be a bool"):
                setter(names[1], fast=1)
            self.assertEqual(getter(), before)
            # 名前の誤りは不正な値と選択肢を文言に示す(FINDINGS A-3 で修正)。
            with self.subTest(kind=kind, attr=attr, message=True):
                with self.assertRaises(ValueError) as caught:
                    setter("bogus")
                self.assertEqual(str(caught.exception),
                                 "Unsupported value 'bogus' (choices: %s)" % ", ".join(names))

    def test_undo_and_fast(self):
        """通常は1回のUndoで戻り、fastはcmds.setAttrを使わずUndoに残らない。"""
        for kind, get_name, set_name, attr, names in _ENUMS:
            with self.subTest(kind=kind, attr=attr):
                node = mlib.createNode(kind)
                getter, setter = getattr(node, get_name), getattr(node, set_name)
                before = getter()
                target = names[-1] if before != names[-1] else names[0]
                setter(target)
                cmds.undo()
                self.assertEqual(getter(), before)
                cmds.redo()
                self.assertEqual(getter(), target)
                sentinel = cmds.createNode("transform")
                cmds.setAttr(sentinel + ".tx", 5)
                with mock.patch.object(cmds, "setAttr", side_effect=AssertionError("setAttr")):
                    setter(before, fast=True)
                cmds.undo()
                self.assertEqual(cmds.getAttr(sentinel + ".tx"), 0)
                self.assertEqual(getter(), before)

    def test_locked_enum(self):
        """ロックした列挙アトリビュートは通常・fastともRuntimeError。"""
        for kind, get_name, set_name, attr, names in _ENUMS:
            with self.subTest(kind=kind, attr=attr):
                node = mlib.createNode(kind)
                getter, setter = getattr(node, get_name), getattr(node, set_name)
                before = getter()
                path = node.getFullName() + "." + attr
                cmds.setAttr(path, lock=True)
                try:
                    for fast in (False, True):
                        with self.assertRaises(RuntimeError):
                            setter(names[-1] if before != names[-1] else names[0], fast=fast)
                    self.assertEqual(getter(), before)
                finally:
                    cmds.setAttr(path, lock=False)

    def test_decompose_rotate_order(self):
        """decomposeMatrixの回転順は番号(int)で取得し、名前と番号0〜5で設定する。"""
        node = mlib.createNode("decomposeMatrix")
        self.assertEqual(node.getRotateOrder(), 0)
        for number, name in enumerate(("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")):
            self.assertIs(node.setRotateOrder(name.upper()), node)
            self.assertEqual(node.getRotateOrder(), number)
            self.assertIsInstance(node.getRotateOrder(), int)
            node.setRotateOrder(number, fast=True)
            self.assertEqual(node.getRotateOrder(), number)
        for bad in ("abc", 6, -1, True):
            with self.assertRaisesRegex(ValueError, "Unsupported rotation order"):
                node.setRotateOrder(bad)
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.setRotateOrder(1, fast=None)
        node.setRotateOrder(2)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibDecomposeMatrixRotateOrder")
        cmds.undo()
        self.assertEqual(node.getRotateOrder(), 5)


class ReturnTypeTest(_CalcCase):
    """取得メソッドの戻り値の型(現在の仕様)。"""

    def test_getter_types(self):
        """Matrix・Vector・tuple・float・boolの区別を固定する。"""
        Matrix, Vector = mlib.maths.Matrix, mlib.maths.Vector
        table = (
            ("composeMatrix", "getTranslate", (), Vector),
            ("composeMatrix", "getRotate", (), Vector),
            ("composeMatrix", "getScale", (), Vector),
            ("composeMatrix", "getShear", (), Vector),
            ("composeMatrix", "getQuaternion", (), tuple),
            ("composeMatrix", "getUseEulerRotation", (), bool),
            ("composeMatrix", "getRotateOrder", (), str),
            ("composeMatrix", "getResult", (), Matrix),
            ("aimMatrix", "getInput", (), Matrix),
            ("aimMatrix", "getEnvelope", (), float),
            ("aimMatrix", "getPrimaryAxis", (), Vector),
            ("aimMatrix", "getResult", (), Matrix),
            ("blendMatrix", "getResult", (), Matrix),
            ("blendMatrix", "getTargetIndices", (), list),
            ("pickMatrix", "getUseTranslate", (), bool),
            ("pickMatrix", "getResult", (), Matrix),
            ("inverseMatrix", "getResult", (), Matrix),
            ("decomposeMatrix", "getInput", (), Matrix),
            ("decomposeMatrix", "getRotateOrder", (), int),
            ("fourByFourMatrix", "getMatrix", (), Matrix),
            ("fourByFourMatrix", "getResult", (), Matrix),
            ("multMatrix", "getResult", (), Matrix),
            ("pairBlend", "getWeight", (), float),
            ("pairBlend", "getTranslate", (1,), Vector),
            ("pairBlend", "getRotate", (1,), Vector),
            ("pairBlend", "getResult", (), tuple),
            ("vectorProduct", "getInput", (1,), tuple),
            ("vectorProduct", "getMatrix", (), Matrix),
            ("vectorProduct", "getNormalizeOutput", (), bool),
            ("vectorProduct", "getResult", (), Vector),
            ("angleBetween", "getInput", (1,), Vector),
            ("angleBetween", "getResult", (), float),
            ("angleBetween", "getAxis", (), Vector),
            ("angleBetween", "getRotate", (), tuple),
            ("distanceBetween", "getDistance", (), float),
        )
        for kind, method, args, expected in table:
            with self.subTest(kind=kind, method=method):
                self.assertIs(type(getattr(mlib.createNode(kind), method)(*args)), expected)

    def test_output_plugs(self):
        """出力Plugのアトリビュート名。"""
        table = (
            ("composeMatrix", (), "outputMatrix"),
            ("aimMatrix", (), "outputMatrix"),
            ("blendMatrix", (), "outputMatrix"),
            ("pickMatrix", (), "outputMatrix"),
            ("inverseMatrix", (), "outputMatrix"),
            ("fourByFourMatrix", (), "output"),
            ("multMatrix", (), "matrixSum"),
            ("pairBlend", (), "outTranslate"),
            ("pairBlend", ("translate",), "outTranslate"),
            ("pairBlend", ("rotate",), "outRotate"),
        )
        for kind, args, attr in table:
            with self.subTest(kind=kind, args=args):
                node = mlib.createNode(kind)
                plug = node.getOutputPlug(*args)
                self.assertEqual(str(plug), node.getName() + "." + attr)
        node = mlib.createNode("pairBlend")
        for bad in ("scale", "Translate", "ROTATE", None):
            with self.assertRaisesRegex(ValueError, "kind must be translate or rotate"):
                node.getOutputPlug(bad)
            with self.assertRaisesRegex(ValueError, "kind must be translate or rotate"):
                node.getResult(bad)


class PublicApiSurfaceTest(unittest.TestCase):
    """担当範囲のクラスの公開メソッドの一覧と、表による網羅を固定する。"""

    def test_public_methods(self):
        """各クラスが自身で定義する公開メソッドは_PUBLIC_APIと一致する(追加・削除で失敗する)。"""
        for class_name, names in _PUBLIC_API.items():
            with self.subTest(cls=class_name):
                cls = getattr(mlib.nodes, class_name)
                own = sorted(name for name, value in vars(cls).items()
                             if not name.startswith("_") and callable(value))
                self.assertEqual(own, sorted(names))

    def test_tables_cover_accessors(self):
        """get/set/connect/Plug取得の各メソッドは、表または個別のテストのどれかで確かめている。"""
        covered = set(_DEDICATED)
        for kind, stem, _, _, _, _, _, has_plug in _ACCESSORS:
            name = mlib.nodes._WRAPPER_CLASSES[kind].__name__
            covered.update((name, prefix + stem) for prefix in ("get", "set", "connect"))
            if has_plug:
                covered.add((name, "get" + stem + "Plug"))
        for kind, get_name, set_name, _, _ in _ENUMS:
            name = mlib.nodes._WRAPPER_CLASSES[kind].__name__
            covered.update(((name, get_name), (name, set_name)))
        for class_name in ("AimMatrix", "BlendMatrix", "ComposeMatrix", "DecomposeMatrix", "InverseMatrix",
                           "MultMatrix", "PairBlend", "PickMatrix", "VectorProduct", "AngleBetween",
                           "FourByFourMatrix"):
            for method in _PUBLIC_API[class_name]:
                if method in ("getResult", "getOutputPlug"):
                    continue
                with self.subTest(cls=class_name, method=method):
                    self.assertIn((class_name, method), covered)


if __name__ == "__main__":
    unittest.main()

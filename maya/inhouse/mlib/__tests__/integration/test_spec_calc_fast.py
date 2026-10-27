"""計算ノード系の接続・設定メソッドに足した ``fast`` 引数の約束を、表で網羅的に固定する。

2.1.0 の担当A。対象は ``_Calculation.connect`` を通る aimMatrix・blendMatrix・composeMatrix・
pickMatrix・pairBlend・vectorProduct・angleBetween の connect*、multMatrix・decomposeMatrix・
inverseMatrix の connectInput、curveInfo・pointOnCurveInfo・pointOnSurfaceInfo の
connectCurve/connectSurface、distanceBetween.connectTransforms、blendMatrix の
connectTarget/removeTarget、place2dTexture.connectTexture、file の setFilePath/setColorSpace、
aimConstraint の setRestRotate/setOffset、ScalarGraph の sum/multiply/condition。各行について次を確かめる。

- 通常経路はシーンを変更し、Undo 1 回で呼出前の状態へ戻る。
- ``fast=True`` は cmds の編集コマンド(setAttr・connectAttr・createNode・undoInfo 等)を呼ばず、
  Undo キューへ何も残さず、通常経路と同じ接続・値になる。戻り値の型も通常経路と同じ。
- ``fast`` が bool 以外なら TypeError で、シーンを変更しない。
"""

import unittest
from contextlib import ExitStack
from unittest.mock import patch

import maya.cmds as cmds
import mlib
from mlib.common.scalarGraph import ScalarGraph
from mlib.plugs.plug import Plug
from support.specCase import NamespaceCase


# fast経路で呼んではいけないcmdsの編集コマンド。
_FORBIDDEN = ("setAttr", "connectAttr", "disconnectAttr", "removeMultiInstance", "createNode",
              "delete", "undoInfo", "aimConstraint")


def _api_only():
    """fast経路がcmdsの編集コマンドを呼んだらAssertionErrorにする。

    Returns:
        contextlib.ExitStack: withで使う差し替えの束。
    """
    stack = ExitStack()
    for name in _FORBIDDEN:
        stack.enter_context(patch.object(cmds, name, side_effect=AssertionError("cmds." + name)))
    return stack


class CalcFastTest(NamespaceCase):
    """各行で通常経路・Undo・fast経路・不正なfastを確かめる。"""

    PREFIX = "mlibSpecCalcFast_"

    def setUp(self):
        cmds.loadPlugin("matrixNodes", quiet=True)
        self.units = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, angle=True))
        cmds.currentUnit(linear="cm", angle="rad")
        super().setUp()

    def tearDown(self):
        super().tearDown()
        cmds.currentUnit(linear=self.units[0], angle=self.units[1])

    # ---- 準備 ----------------------------------------------------------------

    def source(self):
        """接続元のtransformとdecomposeMatrixを作り、種類ごとのPlugを返す。

        Returns:
            dict[str, Plug]: 接続元の種類ごとのPlug。
        """
        name = self.make("transform", "src#")
        cmds.setAttr(name + ".translate", 1.5, 2.5, -3.5)
        cmds.setAttr(name + ".rotate", 0.2, -0.1, 0.4)
        cmds.setAttr(name + ".scale", 0.5, 0.25, 0.75)
        decompose = self.make("decomposeMatrix", "srcDecompose#")
        cmds.connectAttr(name + ".matrix", decompose + ".inputMatrix")
        node = mlib.getNode(name)
        return {
            "matrix": node.getPlug("matrix"),
            "translate": node.getPlug("translate"),
            "rotate": node.getPlug("rotate"),
            "scale": node.getPlug("scale"),
            "scalar": node.getPlug("scaleX"),
            "bool": node.getPlug("visibility"),
            "quat": mlib.getNode(decompose).getPlug("outputQuat"),
        }

    def calc_rows(self):
        """_Calculation.connectを通る接続の行を返す。

        Returns:
            list[tuple]: (ラベル, Maya型, メソッド名, 位置引数の前半, 接続元の種類)。
        """
        rows = []
        for stem, kind in (("Input", "matrix"), ("Envelope", "scalar"), ("PrimaryMatrix", "matrix"),
                           ("PrimaryAxis", "scale"), ("PrimaryVector", "translate"),
                           ("SecondaryMatrix", "matrix"), ("SecondaryAxis", "scale"),
                           ("SecondaryVector", "translate")):
            rows.append(("aimMatrix", "connect" + stem, (), kind))
        for stem, kind in (("Input", "matrix"), ("Envelope", "scalar")):
            rows.append(("blendMatrix", "connect" + stem, (), kind))
        for stem, kind in (("Translate", "translate"), ("Rotate", "rotate"), ("Scale", "scale"),
                           ("Shear", "scale"), ("Quaternion", "quat"), ("UseEulerRotation", "bool")):
            rows.append(("composeMatrix", "connect" + stem, (), kind))
        for stem, kind in (("Input", "matrix"), ("UseTranslate", "bool"), ("UseRotate", "bool"),
                           ("UseScale", "bool"), ("UseShear", "bool")):
            rows.append(("pickMatrix", "connect" + stem, (), kind))
        rows += [
            ("pairBlend", "connectWeight", (), "scalar"),
            ("pairBlend", "connectTranslate", (1,), "translate"),
            ("pairBlend", "connectTranslate", (2,), "translate"),
            ("pairBlend", "connectRotate", (1,), "rotate"),
            ("pairBlend", "connectRotate", (2,), "rotate"),
            ("vectorProduct", "connectInput", (1,), "translate"),
            ("vectorProduct", "connectInput", (2,), "translate"),
            ("vectorProduct", "connectMatrix", (), "matrix"),
            ("vectorProduct", "connectNormalizeOutput", (), "bool"),
            ("angleBetween", "connectInput", (1,), "translate"),
            ("angleBetween", "connectInput", (2,), "translate"),
            ("multMatrix", "connectInput", (0,), "matrix"),
            ("multMatrix", "connectInput", (3,), "matrix"),
            ("decomposeMatrix", "connectInput", (), "matrix"),
            ("inverseMatrix", "connectInput", (), "matrix"),
        ]
        return rows

    def cases(self):
        """全行を (ラベル, 準備関数) で返す。準備関数は (呼出関数, 観察するノード名の列) を返す。

        呼出関数は ``call(**kwargs)`` で対象メソッドを呼び、戻り値を返す。

        Returns:
            list[tuple[str, callable]]: ラベルと準備関数。
        """
        result = []
        for kind, method, head, source_kind in self.calc_rows():
            def prepare(kind=kind, method=method, head=head, source_kind=source_kind):
                plugs = self.source()
                node = mlib.getNode(self.make(kind, kind + "#"))
                bound = getattr(node, method)

                def call(**kwargs):
                    return bound(*(head + (plugs[source_kind],)), **kwargs)
                return call, [node.getFullName()]
            result.append(("%s.%s%s" % (kind, method, head), prepare))

        def target_connect():
            plugs = self.source()
            node = mlib.getNode(self.make("blendMatrix", "blend#"))

            def call(**kwargs):
                return node.connectTarget(2, plugs["matrix"], 0.25, **kwargs)
            return call, [node.getFullName()]
        result.append(("blendMatrix.connectTarget", target_connect))

        def target_remove():
            plugs = self.source()
            node = self.make("blendMatrix", "blend#")
            cmds.connectAttr(plugs["matrix"].getName(), node + ".target[3].targetMatrix")
            cmds.setAttr(node + ".target[3].weight", 0.5)
            wrapper = mlib.getNode(node)

            def call(**kwargs):
                return wrapper.removeTarget(3, **kwargs)
            return call, [node]
        result.append(("blendMatrix.removeTarget", target_remove))

        for kind, method, shape in (("curveInfo", "connectCurve", "curve"),
                                    ("pointOnCurveInfo", "connectCurve", "curve"),
                                    ("pointOnSurfaceInfo", "connectSurface", "surface")):
            for world in (True, False):
                def geometry(kind=kind, method=method, shape=shape, world=world):
                    if shape == "curve":
                        transform = cmds.curve(name=self.name("crv#"), degree=1, point=[(0, 0, 0), (1, 2, 3)])
                    else:
                        transform = cmds.nurbsPlane(name=self.name("srf#"), constructionHistory=False)[0]
                    node = mlib.getNode(self.make(kind, kind + "#"))
                    bound = getattr(node, method)

                    def call(**kwargs):
                        return bound(transform, world, **kwargs)
                    return call, [node.getFullName()]
                result.append(("%s.%s(worldSpace=%s)" % (kind, method, world), geometry))

        def distance():
            first, second = self.make("transform", "a#"), self.make("transform", "b#")
            cmds.setAttr(first + ".translate", 1, 2, 3)
            node = self.make("distanceBetween", "dist#")
            cmds.setAttr(node + ".point1", 4, 5, 6)
            wrapper = mlib.getNode(node)

            def call(**kwargs):
                return wrapper.connectTransforms(first, second, **kwargs)
            return call, [node]
        result.append(("distanceBetween.connectTransforms", distance))

        def place2d():
            place = mlib.getNode(self.make("place2dTexture", "place#"))
            texture = self.make("file", "file#")

            def call(**kwargs):
                return place.connectTexture(texture, **kwargs)
            return call, [place.getFullName(), texture]
        result.append(("place2dTexture.connectTexture", place2d))

        for method, value in (("setFilePath", "textures/<UDIM>_color.png"), ("setColorSpace", "Raw")):
            def file_setter(method=method, value=value):
                node = mlib.getNode(self.make("file", "file#"))
                bound = getattr(node, method)

                def call(**kwargs):
                    return bound(value, **kwargs)
                return call, [node.getFullName()]
            result.append(("file." + method, file_setter))

        for method in ("setRestRotate", "setOffset"):
            def aim(method=method):
                target = self.make("transform", "target#")
                driven = self.make("transform", "driven#")
                constraint = cmds.aimConstraint(target, driven, name=self.name("aim#"))[0]
                node = mlib.getNode(constraint)
                bound = getattr(node, method)

                def call(**kwargs):
                    return bound((0.1, -0.2, 0.3), **kwargs)
                return call, [constraint, driven]
            result.append(("aimConstraint." + method, aim))

        for method in ("sum", "multiply", "condition"):
            def graph(method=method):
                driver = self.make("transform", "driver#")
                cmds.setAttr(driver + ".tx", 3)
                builder = ScalarGraph(createNode=mlib.createNode)
                role = self.name(method)
                plug = driver + ".tx"

                def call(**kwargs):
                    if method == "sum":
                        return builder.sum(role, plug, 2.0, subtract=True, **kwargs)
                    if method == "multiply":
                        return builder.multiply(role, plug, 4.0, **kwargs)
                    return builder.condition(role, plug, 1.0, plug, 0.5, **kwargs)
                return call, [driver]
            result.append(("ScalarGraph." + method, graph))
        return result

    # ---- 観察 ----------------------------------------------------------------

    def snapshot(self, names):
        """名前空間内の全ノードと、指定ノードの接続・書込み可能なアトリビュートの値を記録する。

        Mayaが計算する出力(arcLength等)は、Undo後のDGキャッシュの状態で読み値が変わるため比較しない。

        Args:
            names (list[str]): 観察するノード。

        Returns:
            tuple: 比較用の値。
        """
        nodes = sorted(cmds.ls(self.ns + ":*", long=True) or ())
        nodes_types = tuple((node, cmds.nodeType(node)) for node in nodes)
        connections = []
        values = []
        for name in names:
            connections += cmds.listConnections(name, source=True, destination=True, connections=True,
                                                plugs=True, skipConversionNodes=False) or []
            for attr in cmds.listAttr(name, multi=True, settable=True) or ():
                if attr.startswith(("message", "binMembership", "caching", "frozen", "isHistoricallyInteresting")):
                    continue
                if not cmds.attributeQuery(attr.split("[")[0].split(".")[-1], node=name, writable=True):
                    continue
                try:
                    values.append((name, attr, repr(cmds.getAttr(name + "." + attr))))
                except (RuntimeError, ValueError, TypeError):
                    pass
        return nodes_types, tuple(sorted(connections)), tuple(values)

    @staticmethod
    def describe(result):
        """戻り値を比較用に要約する。Undoで消える前に呼ぶ。

        Args:
            result (object): メソッドの戻り値。

        Returns:
            tuple: 型と、Plugなら名前と評価値。
        """
        if isinstance(result, Plug):
            return type(result), result.getName(), round(result.get(), 6)
        return (type(result),)

    # ---- テスト --------------------------------------------------------------

    def test_normal_undo_and_fast_match(self):
        """通常経路はUndo 1回で戻り、fastはcmdsを呼ばずUndoに残さず同じ結果になる。"""
        for label, prepare in self.cases():
            with self.subTest(label):
                call, names = prepare()
                before = self.snapshot(names)
                normal = self.describe(call())
                after = self.snapshot(names)
                self.assertNotEqual(after, before, "normal path changed nothing")
                cmds.undo()
                self.assertEqual(self.snapshot(names), before)
                cmds.flushUndo()
                with _api_only():
                    fast = call(fast=True)
                self.assertUndoEmpty()
                self.assertEqual(self.snapshot(names), after)
                self.assertEqual(self.describe(fast), normal)

    def test_fast_must_be_bool(self):
        """fastがbool以外ならTypeErrorで、シーンを変更しない。"""
        for label, prepare in self.cases():
            for bad in (1, None, "True"):
                with self.subTest(label, fast=bad):
                    call, names = prepare()
                    before = self.snapshot(names)
                    with self.assertRaises(TypeError):
                        call(fast=bad)
                    self.assertEqual(self.snapshot(names), before)

    def test_fast_force_replaces_connection(self):
        """fastでもforce=Trueで既存接続を置き換え、force=Falseでは置き換えない。"""
        plugs = self.source()
        other = self.make("transform", "other#")
        node = mlib.getNode(self.make("aimMatrix", "aim#"))
        cmds.connectAttr(other + ".matrix", node.getFullName() + ".inputMatrix")
        with self.assertRaises(RuntimeError):
            node.connectInput(plugs["matrix"], fast=True)
        with _api_only():
            node.connectInput(plugs["matrix"], force=True, fast=True)
        self.assertTrue(cmds.isConnected(plugs["matrix"].getName(), node.getFullName() + ".inputMatrix"))
        self.assertFalse(cmds.isConnected(other + ".matrix", node.getFullName() + ".inputMatrix"))

    def test_blend_target_weight_failure_keeps_connection(self):
        """connectTargetはfastでも、接続後のウェイト設定に失敗すると接続が残る。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                plugs = self.source()
                node = mlib.getNode(self.make("blendMatrix", "blend#"))
                driver = self.make("transform", "weightDriver#")
                cmds.connectAttr(driver + ".tx", node.getFullName() + ".target[1].weight")
                with self.assertRaises(RuntimeError):
                    node.connectTarget(1, plugs["matrix"], 0.5, fast=fast)
                self.assertTrue(cmds.isConnected(plugs["matrix"].getName(),
                                                 node.getFullName() + ".target[1].targetMatrix"))

    def test_scalar_graph_container_fast_not_implemented(self):
        """containerを所有先にしたScalarGraphのfast=Trueは、変更前にNotImplementedError。"""
        owner = mlib.nodes.Container.create(name=self.name("owner"))
        graph = ScalarGraph(owner)
        before = sorted(cmds.ls(self.ns + ":*") or ())
        for method, args in (("sum", (1.0, 2.0)), ("multiply", (1.0, 2.0)), ("condition", (1.0, 2.0, 3.0, 4.0))):
            with self.subTest(method):
                with self.assertRaises(NotImplementedError):
                    getattr(graph, method)(self.name(method), *args, fast=True)
                self.assertEqual(sorted(cmds.ls(self.ns + ":*") or ()), before)


if __name__ == "__main__":
    unittest.main()

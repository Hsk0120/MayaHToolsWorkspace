"""プラグ(Plug・MultiPlug・RampPlug)の docstring の Raises に書かれた例外を固定する。

- 無効な参照: 所有ノードの削除・動的アトリビュートの削除の後の照会・設定は RuntimeError。
- 範囲の照会(getSoftMin・getSoftMax・getDefault): uiUnits・unit・timeUnit の型は TypeError、
  未対応の単位名・uiUnits=True との同時指定は ValueError。
- 範囲の設定(setMin・setMax・setSoftMin・setSoftMax): 静的・数値以外のアトリビュートと不正な値は TypeError、
  不正な単位名は ValueError、ソフト値の None は NotImplementedError。例外の後は定義が変わらない。
- setMuted: bool 以外は TypeError で mute ノードを作らない。
- RampPlug.getValueAt: 実数以外は TypeError、有限でない値は ValueError。
"""

import math
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.plugs import MultiPlug, RampPlug
from support.specCase import NamespaceCase

#: 無効な参照で RuntimeError になる、引数なしの照会メソッド。
_QUERIES = (
    "getShortName", "getNiceName", "isKeyable", "isSource", "isDestination", "isHidden", "isDynamic",
    "isProxy", "getProxyMaster", "isReadable", "isWritable", "isStorable", "hasMin", "hasMax",
    "hasSoftMin", "hasSoftMax", "getSoftMin", "getSoftMax", "getDefault", "getAlias", "isMuted",
    "getDestinations",
)

#: 範囲の設定メソッド。
_SETTERS = ("setMin", "setMax", "setSoftMin", "setSoftMax")

#: 範囲の照会で単位の引数を受けるメソッド。
_LIMIT_GETTERS = ("getSoftMin", "getSoftMax", "getDefault")


class _PlugCase(NamespaceCase):
    """無効になった Plug と、範囲を持つ動的アトリビュートを作る補助。"""

    UNLOCK_NODES = True

    def dead_node_plug(self, attribute="translateX", kind="transform"):
        """所有ノードを削除した Plug を返す。"""
        node = self.make(kind, "deadNode#")
        plug = mlib.getNode(node).getPlug(attribute)
        cmds.delete(node)
        return plug

    def dead_attr_plug(self, **flags):
        """動的アトリビュートを削除した Plug を返す(所有ノードは有効なまま)。"""
        node = self.make("transform", "deadAttr#")
        options = {"attributeType": "double"}
        options.update(flags)
        cmds.addAttr(node, longName="extra", **options)
        plug = mlib.getNode(node).getPlug("extra")
        cmds.deleteAttr(node + ".extra")
        return plug

    def ranged(self):
        """最小0・最大10・ソフト最小1・ソフト最大9の動的アトリビュートを持つノードを作る。"""
        node = self.make("transform", "ranged#")
        cmds.addAttr(node, longName="amount", attributeType="double", minValue=0.0, maxValue=10.0,
                     softMinValue=1.0, softMaxValue=9.0, defaultValue=5.0, keyable=True)
        return node

    def limits(self, node, attribute="amount"):
        """attributeQuery で範囲の定義を読む(例外後に変わっていないことの確認用)。"""
        name = attribute
        return (
            cmds.attributeQuery(name, node=node, minExists=True),
            cmds.attributeQuery(name, node=node, maxExists=True),
            cmds.attributeQuery(name, node=node, minimum=True) if cmds.attributeQuery(
                name, node=node, minExists=True) else None,
            cmds.attributeQuery(name, node=node, maximum=True) if cmds.attributeQuery(
                name, node=node, maxExists=True) else None,
            cmds.attributeQuery(name, node=node, softMinExists=True),
            cmds.attributeQuery(name, node=node, softMaxExists=True),
            cmds.attributeQuery(name, node=node, softMin=True) if cmds.attributeQuery(
                name, node=node, softMinExists=True) else None,
            cmds.attributeQuery(name, node=node, softMax=True) if cmds.attributeQuery(
                name, node=node, softMaxExists=True) else None,
        )


class InvalidPlugTest(_PlugCase):
    """所有ノード・アトリビュートが無効な Plug の照会・設定は RuntimeError。"""

    def test_queries_raise_runtime_error(self):
        """削除済みノード・削除済み動的アトリビュートの Plug で、各照会が RuntimeError になる。"""
        cases = (("deletedNode", self.dead_node_plug), ("deletedAttribute", self.dead_attr_plug))
        for label, factory in cases:
            for method in _QUERIES:
                with self.subTest(case=label, method=method):
                    plug = factory()
                    with self.assertRaises(RuntimeError):
                        getattr(plug, method)()

    def test_get_destinations_with_options_raises(self):
        """getConnections へ委ねる指定(asNode 等)でも、無効な Plug は RuntimeError。"""
        for label, factory in (("deletedNode", self.dead_node_plug), ("deletedAttribute", self.dead_attr_plug)):
            for flags in ({"asNode": True}, {"skipConversionNodes": True}, {"index": 0}):
                with self.subTest(case=label, flags=flags):
                    plug = factory()
                    with self.assertRaises(RuntimeError):
                        plug.getDestinations(**flags)

    def test_setters_raise_runtime_error(self):
        """削除済みの Plug への範囲の設定・ミュートは RuntimeError で、他のノードを作らない。"""
        for label, factory in (("deletedNode", self.dead_node_plug), ("deletedAttribute", self.dead_attr_plug)):
            for method, args in [(name, (1.0,)) for name in _SETTERS] + [("setMuted", (True,))]:
                with self.subTest(case=label, method=method):
                    plug = factory()
                    before = set(cmds.ls(type="mute") or [])
                    with self.assertRaises(RuntimeError):
                        getattr(plug, method)(*args)
                    self.assertEqual(set(cmds.ls(type="mute") or []), before)


class LimitQueryArgumentTest(_PlugCase):
    """getSoftMin・getSoftMax・getDefault の引数の検証。"""

    def test_type_errors(self):
        """uiUnits が bool 以外、unit・timeUnit が文字列・None 以外は TypeError。"""
        plug = mlib.getNode(self.ranged()).getPlug("amount")
        for method in _LIMIT_GETTERS:
            for flags in ({"uiUnits": 1}, {"uiUnits": "yes"}, {"unit": 1}, {"unit": True},
                          {"timeUnit": 1}, {"timeUnit": 24.0}):
                with self.subTest(method=method, flags=flags):
                    with self.assertRaises(TypeError):
                        getattr(plug, method)(**flags)

    def test_value_errors(self):
        """未対応の単位名と、uiUnits=True との同時指定は ValueError。"""
        plug = mlib.getNode(self.ranged()).getPlug("amount")
        for method in _LIMIT_GETTERS:
            for flags in ({"unit": "furlong"}, {"timeUnit": "fortnight"},
                          {"unit": "deg", "uiUnits": True}, {"timeUnit": "sec", "uiUnits": True}):
                with self.subTest(method=method, flags=flags):
                    with self.assertRaises(ValueError):
                        getattr(plug, method)(**flags)

    def test_valid_values(self):
        """正常系: ソフト値・既定値を定義どおりに返し、角度は度、unit="rad" でラジアン。"""
        node = self.ranged()
        plug = mlib.getNode(node).getPlug("amount")
        self.assertEqual(plug.getSoftMin(), 1.0)
        self.assertEqual(plug.getSoftMax(), 9.0)
        self.assertEqual(plug.getDefault(), 5.0)
        cmds.addAttr(node, longName="spin", attributeType="doubleAngle", defaultValue=math.pi / 2,
                     softMinValue=-math.pi, softMaxValue=math.pi)
        spin = mlib.getNode(node).getPlug("spin")
        self.assertAlmostEqual(spin.getDefault(), 90.0)
        self.assertAlmostEqual(spin.getDefault(unit="rad"), math.pi / 2)
        self.assertAlmostEqual(spin.getSoftMin(), -180.0)
        self.assertAlmostEqual(spin.getSoftMax(unit="rad"), math.pi)


class SetRangeErrorTest(_PlugCase):
    """setMin・setMax・setSoftMin・setSoftMax の例外と、例外後に定義が変わらないこと。"""

    def test_static_attribute_type_error(self):
        """静的アトリビュート(translateX)は TypeError。"""
        node = self.make("transform", "static")
        plug = mlib.getNode(node).getPlug("translateX")
        before = self.limits(node, "translateX")
        for method in _SETTERS:
            with self.subTest(method=method):
                with self.assertRaises(TypeError):
                    getattr(plug, method)(1.0)
                self.assertEqual(self.limits(node, "translateX"), before)

    def test_non_numeric_attribute_type_error(self):
        """数値・単位型以外の動的アトリビュート(string・message・matrix)は TypeError。"""
        node = self.make("transform", "nonNumeric")
        cmds.addAttr(node, longName="label", dataType="string")
        cmds.addAttr(node, longName="link", attributeType="message")
        cmds.addAttr(node, longName="mat", attributeType="matrix")
        for attribute in ("label", "link", "mat"):
            plug = mlib.getNode(node).getPlug(attribute)
            for method in _SETTERS:
                with self.subTest(attribute=attribute, method=method):
                    with self.assertRaises(TypeError):
                        getattr(plug, method)(1.0)

    def test_bad_value_type_error(self):
        """値が数値・単位付きの値・None 以外(文字列・bool・list)は TypeError で、定義は変わらない。"""
        node = self.ranged()
        plug = mlib.getNode(node).getPlug("amount")
        before = self.limits(node)
        for method in _SETTERS:
            for value in ("1.0", True, [1.0]):
                with self.subTest(method=method, value=value):
                    with self.assertRaises(TypeError):
                        getattr(plug, method)(value)
                    self.assertEqual(self.limits(node), before)

    def test_unit_argument_errors(self):
        """unit・timeUnit の型違いは TypeError、未対応の単位名は ValueError で、定義は変わらない。"""
        node = self.ranged()
        plug = mlib.getNode(node).getPlug("amount")
        before = self.limits(node)
        for method in _SETTERS:
            for flags, error in (({"unit": 1}, TypeError), ({"timeUnit": 1}, TypeError),
                                 ({"unit": "furlong"}, ValueError), ({"timeUnit": "fortnight"}, ValueError)):
                with self.subTest(method=method, flags=flags):
                    with self.assertRaises(error):
                        getattr(plug, method)(2.0, **flags)
                    self.assertEqual(self.limits(node), before)

    def test_soft_none_not_implemented(self):
        """setSoftMin(None)・setSoftMax(None) は NotImplementedError で、ソフト値は残る。"""
        node = self.ranged()
        plug = mlib.getNode(node).getPlug("amount")
        before = self.limits(node)
        for method in ("setSoftMin", "setSoftMax"):
            with self.subTest(method=method):
                with self.assertRaises(NotImplementedError):
                    getattr(plug, method)(None)
                self.assertEqual(self.limits(node), before)

    def test_reversed_range_value_error(self):
        """最大値を超える最小値・最小値を下回る最大値は ValueError で、定義は変わらない(角度は度で比べる)。"""
        node = self.ranged()
        cmds.addAttr(node, longName="angle", attributeType="doubleAngle", minValue=0.0, maxValue=1.0)
        cases = (("amount", "setMin", 11.0, {}), ("amount", "setMax", -1.0, {}),
                 ("angle", "setMin", 60.0, {}), ("angle", "setMax", -5.0, {}),
                 ("angle", "setMin", 1.5, {"unit": "rad"}))
        for attribute, method, value, flags in cases:
            plug = mlib.getNode(node).getPlug(attribute)
            before = self.limits(node, attribute)
            with self.subTest(attribute=attribute, method=method, value=value):
                with self.assertRaises(ValueError):
                    getattr(plug, method)(value, **flags)
                self.assertEqual(self.limits(node, attribute), before)
        # 範囲内の値・等しい値は通る(56度は1ラジアン未満)。
        plug = mlib.getNode(node).getPlug("angle")
        self.assertIs(plug.setMin(56.0), plug)
        self.assertIs(plug.setMax(56.0), plug)

    def test_valid_set_and_undo(self):
        """正常系: 4つの設定が定義へ反映され、Undo 1回で戻る。"""
        node = self.ranged()
        plug = mlib.getNode(node).getPlug("amount")
        expected = {"setMin": (-1.0, "minimum"), "setMax": (20.0, "maximum"),
                    "setSoftMin": (2.0, "softMin"), "setSoftMax": (8.0, "softMax")}
        for method, (value, query) in expected.items():
            with self.subTest(method=method):
                before = cmds.attributeQuery("amount", node=node, **{query: True})[0]
                self.flushUndo()
                self.assertIs(getattr(plug, method)(value), plug)

                def after(query=query, value=value):
                    self.assertAlmostEqual(cmds.attributeQuery("amount", node=node, **{query: True})[0], value)

                def restored(query=query, before=before):
                    self.assertAlmostEqual(cmds.attributeQuery("amount", node=node, **{query: True})[0], before)
                self.assertUndoesInOneStep(restored, after)


class SelfConnectionTest(_PlugCase):
    """Plug.connect は通常・fast・safe のいずれでも自身への接続を RuntimeError にする。"""

    def test_self_connection(self):
        """自身への接続は接続を作らずに RuntimeError(cmds.connectAttr と同じ)。"""
        node = self.make("transform", "selfConnect#")
        plug = mlib.getNode(node).getPlug("translateX")
        for flags in ({}, {"fast": True}, {"safe": True}, {"force": True}):
            with self.subTest(flags=flags):
                with self.assertRaises(RuntimeError):
                    plug.connect(plug, **flags)
                self.assertFalse(cmds.listConnections(node + ".translateX", source=True, destination=False))


class SetMutedErrorTest(_PlugCase):
    """setMuted の例外と正常系。"""

    def animated(self):
        """translateX にキーを持つ transform を作り、その Plug を返す。"""
        node = self.make("transform", "animated#")
        cmds.setKeyframe(node, attribute="translateX", time=1, value=0.0)
        cmds.setKeyframe(node, attribute="translateX", time=10, value=5.0)
        return node, mlib.getNode(node).getPlug("translateX")

    def test_non_bool_type_error(self):
        """state が bool 以外(1・文字列・None)は TypeError で、mute ノードを作らない。"""
        node, plug = self.animated()
        for state in (1, 0, "yes", None):
            with self.subTest(state=state):
                with self.assertRaises(TypeError):
                    plug.setMuted(state)
                self.assertFalse(cmds.ls(type="mute"))
                self.assertFalse(cmds.mute(node + ".translateX", query=True))

    def test_mute_and_unmute(self):
        """正常系: True でミュート(isMuted が True)、False で解除する。"""
        node, plug = self.animated()
        self.assertFalse(plug.isMuted())
        self.assertIs(plug.setMuted(True), plug)
        self.assertTrue(plug.isMuted())
        self.assertTrue(cmds.mute(node + ".translateX", query=True))
        plug.setMuted(False)
        self.assertFalse(plug.isMuted())


class NameQueryTest(_PlugCase):
    """正常系の薄い照会(名前・別名・プロキシ・接続先)。"""

    def test_names_alias_and_proxy(self):
        """短名・ニース名・別名・プロキシの元を cmds と突き合わせる。"""
        node = self.make("transform", "named")
        other = self.make("transform", "master")
        cmds.addAttr(other, longName="weight", attributeType="double")
        cmds.addAttr(node, longName="weightProxy", proxy=other + ".weight")
        plug = mlib.getNode(node).getPlug("translateX")
        self.assertEqual(plug.getShortName(), "tx")
        self.assertEqual(plug.getNiceName(), cmds.attributeName(node + ".translateX", nice=True))
        self.assertIsNone(plug.getAlias())
        cmds.aliasAttr("slide", node + ".translateX")
        self.assertEqual(plug.getAlias(), "slide")
        proxy = mlib.getNode(node).getPlug("weightProxy")
        self.assertTrue(proxy.isProxy())
        self.assertEqual(str(proxy.getProxyMaster()), other + ".weight")
        self.assertIsNone(plug.getProxyMaster())

    def test_destinations(self):
        """getDestinations は cmds.listConnections と同じ出力先を返す。"""
        source = self.make("transform", "src")
        target = self.make("transform", "dst")
        cmds.connectAttr(source + ".translateX", target + ".translateY")
        plug = mlib.getNode(source).getPlug("translateX")
        self.assertTrue(plug.isSource())
        self.assertFalse(plug.isDestination())
        self.assertEqual([str(item) for item in plug.getDestinations()],
                         cmds.listConnections(source + ".translateX", source=False, destination=True, plugs=True))


class MultiPlugErrorTest(_PlugCase):
    """MultiPlug.getIndices・getElements は無効な参照で RuntimeError。"""

    def test_invalid_raises(self):
        """削除済みノード・削除済み動的マルチアトリビュートで RuntimeError。"""
        def dead_node():
            node = self.make("plusMinusAverage", "pma#")
            cmds.setAttr(node + ".input1D[3]", 1.0)
            multi = mlib.getNode(node).getPlug("input1D")
            cmds.delete(node)
            return multi

        def dead_attr():
            node = self.make("transform", "holder#")
            cmds.addAttr(node, longName="items", attributeType="double", multi=True)
            cmds.setAttr(node + ".items[2]", 1.0)
            multi = mlib.getNode(node).getPlug("items")
            cmds.deleteAttr(node + ".items")
            return multi

        for label, factory in (("deletedNode", dead_node), ("deletedAttribute", dead_attr)):
            for method in ("getIndices", "getElements"):
                with self.subTest(case=label, method=method):
                    multi = factory()
                    self.assertIsInstance(multi, MultiPlug)
                    with self.assertRaises(RuntimeError):
                        getattr(multi, method)()


class RampPlugErrorTest(_PlugCase):
    """RampPlug の照会の例外。"""

    def ramp(self, attribute="value"):
        """remapValue のランプの Plug を返す。"""
        node = self.make("remapValue", "remap#")
        plug = mlib.getNode(node).getPlug(attribute)
        self.assertIsInstance(plug, RampPlug)
        return node, plug

    def test_get_value_at_type_error(self):
        """position が実数以外(文字列・bool・None・list)は TypeError。"""
        _, plug = self.ramp()
        for position in ("0.5", True, None, [0.5]):
            with self.subTest(position=position):
                with self.assertRaises(TypeError):
                    plug.getValueAt(position)

    def test_get_value_at_value_error(self):
        """position が有限でない(nan・inf・-inf)は ValueError。"""
        for attribute in ("value", "color"):
            _, plug = self.ramp(attribute)
            for position in (float("nan"), float("inf"), float("-inf")):
                with self.subTest(attribute=attribute, position=position):
                    with self.assertRaises(ValueError):
                        plug.getValueAt(position)

    def test_invalid_raises(self):
        """所有ノードを削除した RampPlug の isColorRamp・getEntries・getValueAt は RuntimeError。"""
        for method, args in (("isColorRamp", ()), ("getEntries", ()), ("getValueAt", (0.5,))):
            for attribute in ("value", "color"):
                with self.subTest(method=method, attribute=attribute):
                    node, plug = self.ramp(attribute)
                    cmds.delete(node)
                    with self.assertRaises(RuntimeError):
                        getattr(plug, method)(*args)

    def test_is_color_ramp(self):
        """正常系: color は色のランプ、value は float のランプ。"""
        _, value = self.ramp("value")
        _, color = self.ramp("color")
        self.assertFalse(value.isColorRamp())
        self.assertTrue(color.isColorRamp())


if __name__ == "__main__":
    unittest.main()

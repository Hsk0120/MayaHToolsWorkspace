"""10.2.0 で足したプラグの API の契約を固定する。

- MultiPlug.compact / removeElement(shift=True): 値・入力・出力の接続(コンパウンドの子も)を移す、Undo 1回、ロックは RuntimeError。
- RampPlug: remapValue の value・color の型選択、getEntries/setEntries/getValueAt を om2 の MRampAttribute と突き合わせる。
- Plug.isProxy / getProxyMaster、Plug.getAnimCurve(layer=...)。
"""

import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.plugs import CompoundPlug, MultiPlug, RampPlug
from support.specCase import NamespaceCase


def _ramp(plug_name):
    """名前のプラグの MRampAttribute を作る。"""
    selection = om2.MSelectionList()
    selection.add(plug_name)
    return om2.MRampAttribute(selection.getPlug(0))


class _MultiCase(NamespaceCase):
    """コンパウンドの子を持つマルチアトリビュートを作る。"""

    def compound_multi(self):
        node = self.make("transform", "holder")
        cmds.addAttr(node, longName="items", attributeType="compound", numberOfChildren=2, multi=True)
        cmds.addAttr(node, longName="itemVec", attributeType="double3", parent="items")
        for axis in "XYZ":
            cmds.addAttr(node, longName="itemVec" + axis, attributeType="double", parent="itemVec")
        cmds.addAttr(node, longName="itemWeight", attributeType="double", parent="items")
        return node


class CompactTest(_MultiCase):

    def test_plain_multi_values(self):
        """数値のマルチアトリビュートの値を 0.. へ詰め、Undo 1回で戻る。"""
        node = self.make("plusMinusAverage", "pma")
        for index, value in ((2, 1.5), (5, 2.5), (9, 3.5)):
            cmds.setAttr(f"{node}.input1D[{index}]", value)
        multi = mlib.getNode(node).getPlug("input1D")
        self.flushUndo()
        self.assertIs(multi.compact(), multi)

        def after():
            self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [0, 1, 2])
            self.assertEqual([cmds.getAttr(f"{node}.input1D[{i}]") for i in range(3)], [1.5, 2.5, 3.5])

        def before():
            self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [2, 5, 9])
            self.assertEqual(cmds.getAttr(node + ".input1D[9]"), 3.5)
        self.assertUndoesInOneStep(before, after)

    def test_compound_connections_and_values(self):
        """コンパウンドの子の値・子の入力接続・要素の出力接続を移す。"""
        node = self.compound_multi()
        source = self.make("transform", "src")
        target = self.make("transform", "dst")
        cmds.setAttr(node + ".items[4].itemWeight", 0.25)
        cmds.setAttr(node + ".items[4].itemVec", 1, 2, 3)
        cmds.setAttr(node + ".items[7].itemWeight", 0.75)
        cmds.connectAttr(source + ".translate", node + ".items[7].itemVec")
        cmds.connectAttr(node + ".items[7].itemWeight", target + ".scaleX")
        multi = mlib.getNode(node).getPlug("items")
        self.flushUndo()
        multi.compact()

        def after():
            self.assertEqual(cmds.getAttr(node + ".items", multiIndices=True), [0, 1])
            self.assertEqual(cmds.getAttr(node + ".items[0].itemVec")[0], (1.0, 2.0, 3.0))
            self.assertEqual(cmds.getAttr(node + ".items[0].itemWeight"), 0.25)
            self.assertEqual(cmds.getAttr(node + ".items[1].itemWeight"), 0.75)
            self.assertEqual(cmds.listConnections(node + ".items[1].itemVec", source=True, destination=False,
                                                  plugs=True), [source + ".translate"])
            self.assertEqual(cmds.listConnections(target + ".scaleX", source=True, destination=False, plugs=True),
                             [node + ".items[1].itemWeight"])

        def before():
            self.assertEqual(cmds.getAttr(node + ".items", multiIndices=True), [4, 7])
            self.assertEqual(cmds.listConnections(target + ".scaleX", source=True, destination=False, plugs=True),
                             [node + ".items[7].itemWeight"])
        self.assertUndoesInOneStep(before, after)

    def test_already_compact_is_noop(self):
        """詰まっているマルチアトリビュートは変更しない。"""
        node = self.make("plusMinusAverage", "pma")
        cmds.setAttr(node + ".input1D[0]", 1)
        cmds.setAttr(node + ".input1D[1]", 2)
        multi = mlib.getNode(node).getPlug("input1D")
        multi.compact()
        self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [0, 1])

    def test_locked_raises(self):
        """移す要素・マルチアトリビュートのロックは RuntimeError で、何も変えない。"""
        node = self.make("plusMinusAverage", "pma")
        cmds.setAttr(node + ".input1D[3]", 1)
        cmds.setAttr(node + ".input1D[3]", lock=True)
        multi = mlib.getNode(node).getPlug("input1D")
        with self.assertRaises(RuntimeError):
            multi.compact()
        self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [3])
        with self.assertRaises(RuntimeError):
            multi.removeElement(3, shift=True)


class RemoveElementShiftTest(_MultiCase):

    def test_shift_moves_later_elements(self):
        """削除した番号より後ろを1つずつ前へ移す。前の空きはそのまま。"""
        node = self.make("plusMinusAverage", "pma")
        source = self.make("transform", "src")
        for index, value in ((0, 1.0), (2, 2.0), (3, 3.0), (5, 5.0)):
            cmds.setAttr(f"{node}.input1D[{index}]", value)
        cmds.connectAttr(source + ".tx", node + ".input1D[5]", force=True)
        cmds.setAttr(source + ".tx", 5.0)
        multi = mlib.getNode(node).getPlug("input1D")
        self.flushUndo()
        self.assertIs(multi.removeElement(2, shift=True), multi)

        def after():
            self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [0, 2, 4])
            self.assertEqual(cmds.getAttr(node + ".input1D[2]"), 3.0)
            self.assertEqual(cmds.listConnections(node + ".input1D[4]", source=True, destination=False,
                                                  plugs=True), [source + ".translateX"])

        def before():
            self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [0, 2, 3, 5])
            self.assertEqual(cmds.getAttr(node + ".input1D[2]"), 2.0)
        self.assertUndoesInOneStep(before, after)

    def test_without_shift_unchanged(self):
        """shift=False は従来どおり番号を変えない。fast は Undo に積まれない。"""
        node = self.make("plusMinusAverage", "pma")
        for index in (0, 2, 3):
            cmds.setAttr(f"{node}.input1D[{index}]", index)
        multi = mlib.getNode(node).getPlug("input1D")
        multi.removeElement(2)
        self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [0, 3])
        self.flushUndo()
        multi.removeElement(3, fast=True)
        self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [0])
        self.assertUndoEmpty()

    def test_errors(self):
        """番号の不在は IndexError、型違いは TypeError、fast と shift の同時指定は NotImplementedError。"""
        node = self.make("plusMinusAverage", "pma")
        cmds.setAttr(node + ".input1D[1]", 1)
        multi = mlib.getNode(node).getPlug("input1D")
        self.assertRaises(IndexError, multi.removeElement, 4, shift=True)
        self.assertRaises(TypeError, multi.removeElement, 1, shift=1)
        self.assertRaises(TypeError, multi.removeElement, "1", shift=True)
        self.assertRaises(NotImplementedError, multi.removeElement, 1, shift=True, fast=True)
        self.assertEqual(cmds.getAttr(node + ".input1D", multiIndices=True), [1])


class RampPlugTest(NamespaceCase):

    def remap(self):
        return self.make("remapValue", "remap")

    def test_type_selection(self):
        """value・color は RampPlug、要素はコンパウンド、通常のマルチアトリビュートは MultiPlug。"""
        node = mlib.getNode(self.remap())
        self.assertIs(type(node.getPlug("value")), RampPlug)
        self.assertIs(type(node.getPlug("color")), RampPlug)
        self.assertIsInstance(node.getPlug("value"), MultiPlug)
        self.assertIsInstance(node.getPlug("value")[0], CompoundPlug)
        self.assertIs(type(mlib.getNode(self.make("plusMinusAverage", "pma")).getPlug("input1D")), MultiPlug)
        self.assertFalse(node.getPlug("value").isColorRamp())
        self.assertTrue(node.getPlug("color").isColorRamp())

    def test_float_ramp_entries_parity(self):
        """float のランプの点と補間した値を MRampAttribute と突き合わせ、Undo 1回で戻る。"""
        name = self.remap()
        plug = mlib.getNode(name).getPlug("value")
        self.assertEqual(plug.getEntries(), [(0.0, 0.0, "linear"), (1.0, 1.0, "linear")])
        self.flushUndo()
        entries = [(0.8, 0.2, "smooth"), (0.0, 1.0, "none"), (0.5, 0.5, "spline")]
        self.assertIs(plug.setEntries(entries), plug)

        def after():
            result = plug.getEntries()
            self.assertEqual([entry[2] for entry in result], ["none", "spline", "smooth"])
            self.assertSequenceAlmostEqual([entry[0] for entry in result], [0.0, 0.5, 0.8], places=6)
            self.assertSequenceAlmostEqual([entry[1] for entry in result], [1.0, 0.5, 0.2], places=6)
            self.assertEqual(cmds.getAttr(name + ".value", multiIndices=True), [0, 1, 2])
            for position in (0.1, 0.3, 0.65, 0.9):
                with self.subTest(position=position):
                    self.assertAlmostEqual(plug.getValueAt(position),
                                           _ramp(name + ".value").getValueAtPosition(position), places=6)

        def before():
            self.assertEqual(plug.getEntries(), [(0.0, 0.0, "linear"), (1.0, 1.0, "linear")])
        self.assertUndoesInOneStep(before, after)

    def test_color_ramp_entries_parity(self):
        """色のランプは (r, g, b) で読み書きし、getValueAt を MRampAttribute と突き合わせる。"""
        name = self.remap()
        plug = mlib.getNode(name).getPlug("color")
        self.assertEqual(plug.getEntries(), [(0.0, (0.0, 0.0, 0.0), "linear"), (1.0, (1.0, 1.0, 1.0), "linear")])
        plug.setEntries([(0.0, (1, 0, 0), "linear"), (1.0, (0, 0, 1), "linear")])
        self.assertEqual(plug.getEntries(), [(0.0, (1.0, 0.0, 0.0), "linear"), (1.0, (0.0, 0.0, 1.0), "linear")])
        value = plug.getValueAt(0.25)
        expected = _ramp(name + ".color").getValueAtPosition(0.25)
        self.assertSequenceAlmostEqual(value, (expected.r, expected.g, expected.b), places=6)
        self.assertSequenceAlmostEqual(value, (0.75, 0.0, 0.25), places=5)
        # remapValue の計算結果(outColor)とも一致する。
        cmds.setAttr(name + ".inputValue", 0.25)
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".outColor")[0], value, places=5)

    def test_round_trip_after_compact(self):
        """getEntries の結果は setEntries にそのまま渡せる。compact でも点は変わらない。"""
        name = self.remap()
        plug = mlib.getNode(name).getPlug("value")
        cmds.setAttr(name + ".value[5].value_Position", 0.4)
        cmds.setAttr(name + ".value[5].value_FloatValue", 0.9)
        cmds.setAttr(name + ".value[5].value_Interp", 2)
        entries = plug.getEntries()
        plug.compact()
        self.assertEqual(cmds.getAttr(name + ".value", multiIndices=True), [0, 1, 2])
        self.assertEqual([(round(p, 6), round(v, 6), i) for p, v, i in plug.getEntries()],
                         [(round(p, 6), round(v, 6), i) for p, v, i in entries])
        plug.setEntries(entries)
        self.assertEqual(len(plug.getEntries()), 3)

    def test_errors(self):
        """不正な点は TypeError/ValueError で、既存の点を変えない。"""
        name = self.remap()
        plug = mlib.getNode(name).getPlug("value")
        color = mlib.getNode(name).getPlug("color")
        before = plug.getEntries()
        cases = (
            (TypeError, plug.setEntries, (0.0,)),
            (TypeError, plug.setEntries, [(0.0, 1.0)]),
            (TypeError, plug.setEntries, [("a", 1.0, "linear")]),
            (TypeError, plug.setEntries, [(0.0, (1, 0, 0), "linear")]),
            (TypeError, color.setEntries, [(0.0, 1.0, "linear")]),
            (TypeError, plug.setEntries, [(0.0, 1.0, 1)]),
            (ValueError, plug.setEntries, []),
            (ValueError, plug.setEntries, [(0.0, 1.0, "cubic")]),
            (ValueError, plug.setEntries, [(float("nan"), 1.0, "linear")]),
            (TypeError, plug.getValueAt, "0.5"),
            (TypeError, plug.getValueAt, True),
            (ValueError, plug.getValueAt, float("inf")),
        )
        for error, method, argument in cases:
            with self.subTest(argument=argument):
                self.assertRaises(error, method, argument)
        self.assertEqual(plug.getEntries(), before)
        cmds.setAttr(name + ".value", lock=True)
        self.assertRaises(RuntimeError, plug.setEntries, [(0.0, 1.0, "linear")])


class ProxyTest(NamespaceCase):

    def test_proxy_master(self):
        """プロキシは True と元の Plug、通常のアトリビュートは False と None。プロキシのプロキシは1段上。"""
        master = self.make("transform", "master")
        cmds.addAttr(master, longName="amount", attributeType="double", keyable=True)
        first = self.make("transform", "first")
        second = self.make("transform", "second")
        cmds.addAttr(first, longName="amountProxy", proxy=master + ".amount")
        cmds.addAttr(second, longName="amountProxy2", proxy=first + ".amountProxy")
        proxy = mlib.getNode(first).getPlug("amountProxy")
        self.assertTrue(proxy.isProxy())
        self.assertEqual(proxy.getProxyMaster(), mlib.getNode(master).getPlug("amount"))
        proxy2 = mlib.getNode(second).getPlug("amountProxy2")
        self.assertEqual(proxy2.getProxyMaster(), proxy)
        self.assertEqual(proxy2.getProxyMaster().getProxyMaster(), mlib.getNode(master).getPlug("amount"))
        plain = mlib.getNode(master).getPlug("amount")
        self.assertFalse(plain.isProxy())
        self.assertIsNone(plain.getProxyMaster())
        # om2 の判定と一致する。
        self.assertEqual(proxy.isProxy(), om2.MFnAttribute(proxy.mplug().attribute()).isProxyAttribute)


class AnimLayerCurveTest(NamespaceCase):

    def tearDown(self):
        for layer in cmds.ls(type="animLayer") or []:
            if cmds.objExists(layer) and layer.startswith(self.ns):
                cmds.delete(layer)
        super().tearDown()

    def test_layer_curve(self):
        """layer 指定はそのレイヤーのカーブ、属さないレイヤーは None、未指定は従来どおり。"""
        cube = cmds.polyCube(name=self.name("cube"))[0]
        cmds.setKeyframe(cube, attribute="translateX", time=1, value=1)
        plug = mlib.getNode(cube).getPlug("translateX")
        direct = plug.getAnimCurve()
        self.assertEqual(direct.getType(), "animCurveTL")
        layer = cmds.animLayer(self.name("L1"))
        empty = cmds.animLayer(self.name("L2"))
        base = cmds.animLayer(query=True, root=True)
        cmds.select(cube)
        cmds.animLayer(layer, edit=True, addSelectedObjects=True)
        cmds.select(clear=True)
        cmds.setKeyframe(cube, attribute="translateX", time=1, value=5, animLayer=layer)
        expected_layer = cmds.animLayer(layer, query=True, findCurveForPlug=cube + ".translateX")[0]
        expected_base = cmds.animLayer(base, query=True, findCurveForPlug=cube + ".translateX")[0]
        self.assertEqual(plug.getAnimCurve(layer=layer).getName(), expected_layer)
        self.assertEqual(plug.getAnimCurve(layer=mlib.getNode(layer)).getName(), expected_layer)
        self.assertEqual(plug.getAnimCurve(layer=base).getName(), expected_base)
        self.assertIsNone(plug.getAnimCurve(layer=empty))
        # 未指定は直接の入力(レイヤーのブレンドノード)なので animCurve ではない。
        self.assertIsNone(plug.getAnimCurve())
        self.assertIsNone(mlib.getNode(cube).getPlug("translateY").getAnimCurve(layer=layer))
        # どのレイヤーにも属さないプラグのベースレイヤーのカーブは、直接接続された animCurve。
        other = cmds.polyCube(name=self.name("other"))[0]
        cmds.setKeyframe(other, attribute="translateX", time=1, value=2)
        other_plug = mlib.getNode(other).getPlug("translateX")
        self.assertEqual(other_plug.getAnimCurve(layer=base), other_plug.getAnimCurve())
        self.assertIsNone(other_plug.getAnimCurve(layer=layer))

    def test_layer_errors(self):
        """animLayer 以外は TypeError、解決できない名前は RuntimeError。"""
        cube = cmds.polyCube(name=self.name("cube"))[0]
        plug = mlib.getNode(cube).getPlug("translateX")
        self.assertRaises(TypeError, plug.getAnimCurve, layer=1)
        self.assertRaises(TypeError, plug.getAnimCurve, layer=cube)
        self.assertRaises(RuntimeError, plug.getAnimCurve, layer=self.name("missingLayer"))


if __name__ == "__main__":
    unittest.main()

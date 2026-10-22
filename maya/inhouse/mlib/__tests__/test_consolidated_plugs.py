"""統合したPlugの単位・接続・fast/Undoを専用シーンで検証する。"""

import math
import unittest
from unittest.mock import patch

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import mlib


class ConsolidatedPlugsTest(unittest.TestCase):
    """値の単位・接続端点・Undoの有無を同時に確認する。"""

    def setUp(self):
        """独立したシーンと基準単位を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)
        self.node = mlib.createNode("transform")

    def tearDown(self):
        """表示単位を復元する。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_scalar_compound_array_ui_units_and_types(self):
        """内部値型を保ち、UIでは数値表現と疎な配列番号を返す。"""
        cmds.currentUnit(linear="m", angle="deg", time="ntsc")
        for fast in (False, True):
            self.node.getPlug("rx").set(90, uiUnits=True, fast=fast)
            self.assertAlmostEqual(self.node.getPlug("rx").get(), math.pi / 2)
            self.assertAlmostEqual(self.node.getPlug("rx").get(uiUnits=True), 90)
            translation = self.node.getPlug("translate")
            translation.set((1, 2, 3), uiUnits=True, fast=fast)
            self.assertIsInstance(translation.get(), mlib.maths.Translate)
            self.assertEqual(tuple(translation.get()), (100, 200, 300))
            self.assertEqual(translation.get(uiUnits=True), (1, 2, 3))
        cmds.addAttr(str(self.node), ln="angles", at="doubleAngle", multi=True)
        array = self.node.getPlug("angles")
        array[3].set(45, uiUnits=True, fast=True)
        array[10].set(90, uiUnits=True, fast=True)
        self.assertEqual(set(array.get()), {3, 10})
        self.assertEqual(array.get(uiUnits=True), {3: 45, 10: 90})
        self.assertFalse(hasattr(type(array), "getu"))
        self.assertFalse(hasattr(type(array), "setu"))
        with self.assertRaises(ValueError):
            self.node.getPlug("rotate").set((1, 2, 3), uiUnits=True, unit="deg")

    def test_typed_math_ui_input_is_rejected_without_writing(self):
        """数学型の内部単位と回転順序をUI数値への変換で失わない。"""
        rotate = self.node.getPlug("rotate")
        rotation = mlib.maths.EulerRotate(.2, .3, .4, order=om2.MEulerRotation.kZYX)
        before = tuple(rotate.get())
        for value in (rotation, rotation.asQuaternion()):
            with self.assertRaises(TypeError):
                rotate.set(value, uiUnits=True)
            self.assertEqual(tuple(rotate.get()), before)
            self.assertEqual(rotate.set(value, uiUnits=True, safe=True, fast=True), 1)
            self.assertEqual(tuple(rotate.get()), before)
        rotate.set(rotation)
        self.assertEqual(rotate.get().order, self.node.getPlug("rotateOrder").get())

    def test_ui_safe_updates_only_writable_children(self):
        """UI単位のsafe部分更新でも距離換算を一回だけ適用する。"""
        cmds.currentUnit(linear="m")
        translation = self.node.getPlug("translate")
        translation[1].setLocked(True)
        self.assertEqual(translation.set((1, 2, 3), safe=True, uiUnits=True), 1)
        self.assertEqual(tuple(translation.get()), (100, 0, 300))

    def test_get_source_conversion_flag_and_general_query(self):
        """省略・直結を一つのgetterで切替え、一般照会の既定は維持する。"""
        source = mlib.createNode("transform").getPlug("tx")
        conversion = mlib.createNode("unitConversion")
        source.connectTo(conversion.getPlug("input"))
        destination = self.node.getPlug("tx")
        conversion.getPlug("output").connectTo(destination)
        self.assertEqual(destination.getSource(), source)
        self.assertEqual(destination.getSource(skipConversionNodes=False).getNode(), conversion)
        self.assertEqual(destination.getSource(scn=False).getNode(), conversion)
        self.assertEqual(destination.getConnections(s=True, d=False), [conversion.getPlug("output")])
        self.assertEqual(source.getDestinations(), [destination])
        self.assertEqual(source.getDestinations(scn=False), [conversion.getPlug("input")])
        self.assertEqual(destination.getSource(asNode=True), source.getNode())
        with self.assertRaises(TypeError):
            destination.getSource(scn=True, skipConversionNodes=False)
        self.assertFalse(hasattr(type(destination), "getSourceWithConversion"))
        self.assertFalse(hasattr(type(destination), "getInputs"))

    def test_fast_connect_disconnect_and_flags_do_not_call_mutating_cmds(self):
        """fast経路は値・接続・ロックをAPIで更新しUndoへ積まない。"""
        source = mlib.createNode("transform").getPlug("tx")
        destination = self.node.getPlug("tx")
        source.set(12)
        cmds.flushUndo()
        with patch.object(cmds, "connectAttr", side_effect=AssertionError("cmds connect")), \
                patch.object(cmds, "disconnectAttr", side_effect=AssertionError("cmds disconnect")), \
                patch.object(cmds, "setAttr", side_effect=AssertionError("cmds set")):
            self.assertEqual(source.connectTo(destination, fast=True), destination)
            self.assertEqual(destination.getSource(scn=False), source)
            destination.setLocked(True, fast=True)
            replacement = self.node.getPlug("ty")
            replacement.set(33, fast=True)
            destination.connect(replacement, force=True, fast=True)
            self.assertTrue(destination.isLocked())
            self.assertEqual(destination.getSource(scn=False), replacement)
            destination.unlock(fast=True)
            destination.disconnectAll(fast=True, src=True, dst=False)
        self.assertIsNone(destination.getSource())
        self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))

    def test_normal_connection_undo_restores_existing_array_constant(self):
        """接続のUndoで演算入力の元の定数値が消えない。"""
        blend = mlib.createNode("blendWeighted")
        target = blend.getPlug("input")[4]
        target.set(7)
        source = self.node.getPlug("tx")
        source.set(21)
        cmds.flushUndo()
        target.connect(source)
        self.assertEqual(target.get(), 21)
        cmds.undo()
        self.assertIsNone(target.getSource())
        self.assertEqual(target.get(), 7)
        cmds.redo()
        self.assertEqual(target.get(), 21)

    def test_fast_array_remove_and_dynamic_attr_delete(self):
        """要素・動的アトリビュートをcmdsなしに削除し、Undoへ積まない。"""
        cmds.addAttr(str(self.node), ln="values", at="double", multi=True)
        array = self.node.getPlug("values")
        array[4].set(12)
        extra = self.node.addAttr("temporary", "double")
        extra.set(3)
        cmds.flushUndo()
        with patch.object(cmds, "removeMultiInstance", side_effect=AssertionError("cmds remove")), \
                patch.object(cmds, "deleteAttr", side_effect=AssertionError("cmds delete")):
            self.assertIs(array.removeElement(4, fast=True), array)
            self.assertEqual(array.get(), {})
            extra.delete(fast=True)
        self.assertFalse(self.node.hasAttr("temporary"))
        self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))

    def test_fast_numeric_string_matrix_and_typed_arrays(self):
        """API 2.0で構築できる型付き配列を形状と空値を維持して往復する。"""
        cases = (("doubleArray", [1.0, 2.0]), ("Int32Array", [1, -2]),
                 ("stringArray", ["a", "b"]), ("vectorArray", [(1, 2, 3)]),
                 ("pointArray", [(1, 2, 3, 1)]),
                 ("matrixArray", [tuple(om2.MMatrix())]))
        for index, (kind, value) in enumerate(cases):
            cmds.addAttr(str(self.node), ln="data" + str(index), dt=kind)
            plug = self.node.getPlug("data" + str(index))
            with patch.object(cmds, "setAttr", side_effect=AssertionError("cmds set")):
                plug.set(value, fast=True)
            self.assertEqual(plug.get(), value)
            plug.set([], fast=True)
            self.assertEqual(plug.get(), [])
        cmds.addAttr(str(self.node), ln="unsupported", dt="floatArray")
        with self.assertRaises(NotImplementedError):
            self.node.getPlug("unsupported").set([1.0], fast=True)

    def test_fast_unsupported_compound_is_rejected_before_any_write(self):
        """未対応の子データを含むfast更新は先行する数値も変更しない。"""
        from mlib._core.fastWrite import set_plug
        cmds.addAttr(str(self.node), ln="mixed", at="compound", nc=2)
        cmds.addAttr(str(self.node), ln="number", at="double", p="mixed")
        cmds.addAttr(str(self.node), ln="unsupportedChild", dt="floatArray", p="mixed")
        mixed = self.node.getPlug("mixed")
        mixed[0].set(9)
        with self.assertRaises(NotImplementedError):
            set_plug(mixed.mplug(), (1, [2.0]))
        self.assertEqual(mixed[0].get(), 9)
        with self.assertRaises(NotImplementedError):
            mixed.set((1, [2.0]), safe=True, fast=True)
        self.assertEqual(mixed[0].get(), 9)

    def test_fast_key_uses_ui_time_value_and_rejects_flags_before_creation(self):
        """キーの時刻・角度をUI単位から変換し、未対応旗は作成前に拒否する。"""
        plug = self.node.getPlug("rx")
        cmds.flushUndo()
        with patch.object(cmds, "setKeyframe", side_effect=AssertionError("cmds key")):
            self.assertIs(plug.setKey(t=24, v=90, itt="linear", ott="linear", fast=True), plug)
            plug.setKey(time=48, value=180, fast=True)
        curve = plug.getSource(scn=False).getNode()
        self.assertEqual(curve.getKeyInputs(), [1, 2])
        self.assertEqual(curve.getKeyValues(), [math.pi / 2, math.pi])
        self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))
        untouched = self.node.getPlug("ty")
        before = len(cmds.ls(type="animCurve"))
        with self.assertRaises(NotImplementedError):
            untouched.setKey(t=1, v=5, animLayer="Unsupported", fast=True)
        self.assertIsNone(untouched.getSource())
        self.assertEqual(len(cmds.ls(type="animCurve")), before)

    def test_api_element_materialization_is_not_an_undo_command(self):
        """要素確保はAPIで行い、保持番号を維持する。"""
        cmds.addAttr(str(self.node), ln="samples", at="double", multi=True)
        array = self.node.getPlug("samples")
        cmds.flushUndo()
        with patch.object(cmds, "getAttr", side_effect=AssertionError("cmds get")):
            element = array.getElement(4, create=True)
            self.assertEqual(element.get(), 0)
            added = array.addElement(8)
        self.assertEqual([p.mplug().logicalIndex() for p in added], [8])
        self.assertEqual(set(array.get()), {4, 8})
        self.assertTrue(cmds.undoInfo(q=True, undoQueueEmpty=True))

    def test_connection_undo_record_does_not_read_proxy_or_uninitialized_matrix(self):
        """定数のUndo保護がproxyや未初期化matrixの接続を妨げない。"""
        angle = self.node.addAttr("driverAngle", "doubleAngle", dv=.5)
        proxy = self.node.addAttr("proxyAngle", proxy=angle)
        self.assertEqual(proxy.get(), angle.get())
        matrix = mlib.createNode("distanceBetween").getPlug("inMatrix1")
        source = self.node.getPlug("worldMatrix")[0]
        self.assertEqual(matrix.connect(source), matrix)
        self.assertEqual(matrix.getSource(scn=False), source)

    def test_fast_alias_and_mute_query(self):
        """別名をAPIで編集し、muteの状態照会もAPIで読む。"""
        plug = self.node.getPlug("tx")
        plug.setAlias("positionX", fast=True)
        self.assertEqual(cmds.aliasAttr(str(plug), q=True), "positionX")
        plug.setAlias(fast=True)
        self.assertFalse(cmds.aliasAttr(str(plug), q=True))
        cmds.setKeyframe(str(plug), t=1, v=3)
        plug.setMuted(True)
        with patch.object(cmds, "mute", side_effect=AssertionError("cmds mute query")):
            self.assertTrue(plug.isMuted())
        with self.assertRaises(NotImplementedError):
            plug.setMuted(False, fast=True)
        plug.setMuted(False)
        self.assertFalse(plug.isMuted())


if __name__ == "__main__":
    unittest.main()

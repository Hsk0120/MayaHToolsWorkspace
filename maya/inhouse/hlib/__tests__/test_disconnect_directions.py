"""Plug.disconnectの方向指定・既存入力指定・Undo契約をMaya内で検証する。"""

import sys
import unittest

import maya.cmds as cmds
import hlib


class DisconnectDirectionsTest(unittest.TestCase):
    """直接接続だけを切断し、既存呼出しの戻り値とロック状態を保持する。"""

    def setUp(self):
        """独立した空シーンと有効なUndoキューを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def _value(self, name):
        """networkノード上に接続用のdouble Plugを作る。

        Args:
            name (str): テスト内で識別するノード名。

        Returns:
            Plug: 入出力に使用するvalueアトリビュート。
        """
        node = hlib.createNode("network", name=name)
        return node.addAttr("value", attributeType="double")

    def _chain(self, prefix):
        """一つの入力と二つの出力を持つ接続を用意する。

        Args:
            prefix (str): ノード名の接頭辞。

        Returns:
            tuple[Plug, Plug, list[Plug]]: 入力元・中心Plug・接続先列。
        """
        source = self._value(prefix + "Source")
        center = self._value(prefix + "Center")
        destinations = [self._value(prefix + "First"), self._value(prefix + "Second")]
        center.connect(source)
        for destination in destinations:
            destination.connect(center)
        return source, center, destinations

    def _connected(self, source, destination):
        """二つのPlugに直接接続が残っているか返す。

        Args:
            source (Plug): 接続元。
            destination (Plug): 接続先。

        Returns:
            bool: 直接接続の有無。
        """
        return cmds.isConnected(str(source), str(destination))

    def _assert_chain(self, source, center, destinations, incoming=True, outgoing=True):
        """接続の保持・解除を入出力別に検証する。

        Args:
            source (Plug): 入力元。
            center (Plug): 中心Plug。
            destinations (list[Plug]): 接続先。
            incoming (bool): 期待する入力接続の有無。
            outgoing (bool): 期待する出力接続の有無。
        """
        self.assertEqual(self._connected(source, center), incoming)
        for destination in destinations:
            self.assertEqual(self._connected(center, destination), outgoing)

    def test_legacy_input_defaults_and_reference_inputs_keep_return_type(self):
        """旧省略・Plug・MPlug・文字列・source別名は入力元Plugを返す。"""
        cases = ("default", "plug", "mplug", "string", "source")
        for mode in cases:
            with self.subTest(mode=mode):
                source, center, destinations = self._chain(mode)
                if mode == "default":
                    result = center.disconnect()
                elif mode == "plug":
                    result = center.disconnect(source, dst=False)
                elif mode == "mplug":
                    result = center.disconnect(source.mplug())
                elif mode == "string":
                    result = center.disconnect(str(source))
                else:
                    result = center.disconnect(source=source)
                self.assertIsInstance(result, hlib.plugs.Plug)
                self.assertEqual(result, source)
                self._assert_chain(source, center, destinations, incoming=False)
                with self.assertRaises(RuntimeError):
                    center.disconnect()
                self._assert_chain(source, center, destinations, incoming=False)

    def test_boolean_input_and_output_only_modes_preserve_other_direction(self):
        """src=Trueは入力だけ、src=False/dst=Trueは全出力だけを解除する。"""
        source, center, destinations = self._chain("inputOnly")
        self.assertEqual(center.disconnect(src=True), [source])
        self._assert_chain(source, center, destinations, incoming=False)
        source, center, destinations = self._chain("outputOnly")
        self.assertCountEqual(center.disconnect(src=False, dst=True), destinations)
        self._assert_chain(source, center, destinations, outgoing=False)

    def test_explicit_and_implicit_both_directions_return_input_before_fanout(self):
        """両方向モードは入力元を先頭に置き、全出力先を後へ返す。"""
        for explicit in (True, False):
            with self.subTest(explicit=explicit):
                source, center, destinations = self._chain("both" + str(explicit))
                result = center.disconnect(src=True, dst=True) if explicit else center.disconnect(dst=True)
                self.assertEqual(result[0], source)
                self.assertCountEqual(result[1:], destinations)
                self._assert_chain(source, center, destinations, incoming=False, outgoing=False)

    def test_aliases_and_invalid_direction_arguments_are_checked_before_mutation(self):
        """長名別名を受け付け、重複指定や不正型では接続を変更しない。"""
        source, center, destinations = self._chain("aliases")
        invalid = (
            {"src": True, "source": True},
            {"dst": True, "destination": True},
            {"src": True, "dst": 1},
            {"src": False, "destination": source},
            {"src": 1, "dst": True},
            {"source": [], "destination": True},
        )
        for kwargs in invalid:
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(TypeError):
                    center.disconnect(**kwargs)
                self._assert_chain(source, center, destinations)
        with self.assertRaises(TypeError):
            center.disconnect(True, source=True, destination=True)
        self._assert_chain(source, center, destinations)
        result = center.disconnect(source=True, destination=True)
        self.assertEqual(result[0], source)
        self.assertCountEqual(result[1:], destinations)
        self._assert_chain(source, center, destinations, incoming=False, outgoing=False)

    def test_empty_direction_modes_and_both_false_are_noops(self):
        """未接続の方向モードと両Falseは空リストを返し既存接続を保持する。"""
        source, center, destinations = self._chain("noop")
        self.assertEqual(center.disconnect(src=False, dst=False), [])
        self._assert_chain(source, center, destinations)
        empty = self._value("unconnected")
        for kwargs in ({"src": True}, {"src": False, "dst": True}, {"dst": True},
                       {"source": False, "destination": False}):
            with self.subTest(kwargs=kwargs):
                self.assertEqual(empty.disconnect(**kwargs), [])
        with self.assertRaises(RuntimeError):
            empty.disconnect(dst=False)

    def test_specified_input_with_outputs_is_strict_and_returns_plug_list(self):
        """指定入力＋全出力はstrictな入力照合を先に行う。"""
        source, center, destinations = self._chain("specified")
        unrelated = self._value("unrelated")
        center.setFlags(locked=True)
        with self.assertRaises(RuntimeError):
            center.disconnect(src=unrelated, dst=True, force=True)
        self.assertTrue(center.isLocked())
        self._assert_chain(source, center, destinations)
        center.setFlags(locked=False)
        result = center.disconnect(source=source.mplug(), destination=True)
        self.assertEqual(result[0], source)
        self.assertCountEqual(result[1:], destinations)
        self._assert_chain(source, center, destinations, incoming=False, outgoing=False)

    def test_array_search_requires_specified_source_and_keeps_legacy_targets(self):
        """naの旧検索は指定srcだけを対象とし、boolモードでは要素を展開しない。"""
        owner = hlib.createNode("network", name="arrayOwner")
        array = owner.addAttr("values", attributeType="double", multi=True)
        source = self._value("arraySource")
        other = self._value("arrayOther")
        first, second, independent = array[3], array[9], array[15]
        first.connect(source)
        second.connect(source)
        independent.connect(other)
        output = self._value("arrayOutput")
        output.connect(first)
        self.assertEqual(array.disconnect(src=True, na=True), [])
        self.assertEqual(array.disconnect(src=False, dst=True, na=True), [])
        self.assertEqual(array.disconnect(dst=True, na=True), [])
        for target in (first, second):
            self.assertTrue(self._connected(source, target))
        result = array.disconnect(source=source, nextAvailable=True)
        self.assertIsInstance(result, list)
        self.assertCountEqual(result, [first, second])
        for target in (first, second):
            self.assertFalse(self._connected(source, target))
        self.assertTrue(self._connected(other, independent))
        self.assertTrue(self._connected(first, output))
        with self.assertRaises(RuntimeError):
            array.disconnect(src=source, na=True)
        first.connect(source)
        second.connect(source)
        result = array.disconnect(src=source, dst=True, na=True)
        # 明示srcのna検索は新方向指定と併用しても旧接続先リストを維持する。
        self.assertCountEqual(result, [first, second])
        self.assertTrue(self._connected(other, independent))
        self.assertTrue(self._connected(first, output))

    def test_unit_conversion_is_kept_as_the_direct_endpoint(self):
        """変換を飛ばした遠端を解除せず、unitConversionとの直接接続を返す。"""
        source = self._value("conversionSource")
        center = self._value("conversionCenter")
        output = self._value("conversionOutput")
        conversion = hlib.createNode("unitConversion", name="conversion")
        conversion_input = conversion.getPlug("input")
        conversion_output = conversion.getPlug("output")
        conversion_input.connect(source)
        center.connect(conversion_output)
        output.connect(center)
        self.assertEqual(center.disconnect(src=True), [conversion_output])
        self.assertFalse(self._connected(conversion_output, center))
        self.assertTrue(self._connected(source, conversion_input))
        self.assertTrue(self._connected(center, output))
        center.connect(conversion_output)
        self.assertEqual(source.disconnect(src=False, dst=True), [conversion_input])
        self.assertFalse(self._connected(source, conversion_input))
        self.assertTrue(self._connected(conversion_output, center))

    def test_compound_parent_disconnect_keeps_independent_child_connections(self):
        """親の直接接続だけを解除し、子の独立した入出力へ再帰しない。"""
        source = hlib.createNode("transform", name="compoundSource")
        center = hlib.createNode("transform", name="compoundCenter")
        destination = hlib.createNode("transform", name="compoundDestination")
        incoming, parent, outgoing = source.getPlug("translate"), center.getPlug("translate"), destination.getPlug("translate")
        parent.connect(incoming)
        outgoing.connect(parent)
        child_output = hlib.createNode("transform", name="compoundChildOutput").getPlug("translateX")
        child_output.connect(center.getPlug("translateX"))
        rotate_source = source.getPlug("rotateX")
        rotate_child = center.getPlug("rotateX")
        rotate_child.connect(rotate_source)
        result = parent.disconnect(src=True, dst=True)
        self.assertEqual(result, [incoming, outgoing])
        self.assertFalse(self._connected(incoming, parent))
        self.assertFalse(self._connected(parent, outgoing))
        self.assertTrue(self._connected(center.getPlug("translateX"), child_output))
        self.assertEqual(center.getPlug("rotate").disconnect(src=True, dst=True), [])
        self.assertTrue(self._connected(rotate_source, rotate_child))

    def test_forced_fanout_restores_locks_and_is_one_undo_redo(self):
        """出力先と親のロックを復元し、全切断を1回のUndo/Redoで戻す。"""
        source, center, destinations = self._chain("locked")
        owner = hlib.createNode("network", name="lockedParent")
        # double同士で接続し、単位変換ノードを介さないcompound親ロックを作る。
        cmds.addAttr(str(owner), longName="payload", attributeType="compound", numberOfChildren=1)
        cmds.addAttr(str(owner), longName="parentValue", attributeType="double", parent="payload")
        destination = owner.getPlug("parentValue")
        destination.connect(center)
        destinations.append(destination)
        for plug in destinations[:2]:
            plug.setFlags(locked=True)
        parent = owner.getPlug("payload")
        parent.setFlags(locked=True)
        with self.assertRaises(RuntimeError):
            center.disconnect(src=False, dst=True)
        self._assert_chain(source, center, destinations)
        cmds.flushUndo()
        result = center.disconnect(src=True, dst=True, f=True)
        self.assertEqual(result[0], source)
        self.assertCountEqual(result[1:], destinations)
        self._assert_chain(source, center, destinations, incoming=False, outgoing=False)
        for plug in destinations[:2] + [parent]:
            self.assertTrue(cmds.getAttr(str(plug), lock=True))
        cmds.undo()
        self._assert_chain(source, center, destinations)
        for plug in destinations[:2] + [parent]:
            self.assertTrue(cmds.getAttr(str(plug), lock=True))
        cmds.redo()
        self._assert_chain(source, center, destinations, incoming=False, outgoing=False)
        for plug in destinations[:2] + [parent]:
            self.assertTrue(cmds.getAttr(str(plug), lock=True))

    def test_forced_outputs_restore_shared_array_parent_lock(self):
        """同じ配列親の複数要素への出力を解除し、ロックを戻してUndoする。"""
        source = self._value("lockedArraySource")
        owner = hlib.createNode("network", name="lockedArrayOwner")
        array = owner.addAttr("values", attributeType="double", multi=True)
        targets = [array[3], array[9]]
        for target in targets:
            target.connect(source)
        array.setFlags(locked=True)
        cmds.flushUndo()
        self.assertCountEqual(source.disconnect(src=False, dst=True, force=True), targets)
        self.assertTrue(array.isLocked())
        for target in targets:
            self.assertFalse(self._connected(source, target))
        cmds.undo()
        self.assertTrue(array.isLocked())
        for target in targets:
            self.assertTrue(self._connected(source, target))
        cmds.redo()
        self.assertTrue(array.isLocked())
        for target in targets:
            self.assertFalse(self._connected(source, target))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

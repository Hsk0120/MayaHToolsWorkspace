"""Plugの接続照会・判定・全切断に共通する方向指定をMaya内で検証する。"""

import inspect
import sys
import unittest

import mlib
import maya.cmds as cmds


class ConnectionDirectionsTest(unittest.TestCase):
    """入力・出力の意味、既存照会仕様、参照検査とUndo契約を検証する。"""

    def setUp(self):
        """各テストに独立した空シーンと有効なUndoキューを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_queries_share_direction_aliases_and_keep_legacy_and_rules(self):
        """sourceは入力、destinationは出力とし、旧s/dとのANDを維持する。"""
        source, center, destinations = self._chain("query")
        for method_name in ("getConnections",):
            query = getattr(center, method_name)
            for src, dst in ((True, True), (True, False), (False, True), (False, False)):
                expected = ([source] if src else []) + (destinations if dst else [])
                with self.subTest(method=method_name, src=src, dst=dst):
                    self.assertCountEqual(query(source=src, destination=dst), expected)
            self.assertCountEqual(query(s=False, source=True), destinations)
            self.assertEqual(query(d=False, destination=True), [source])
            self.assertEqual(query(s=True, source=False, d=True, destination=False), [])
            # 従来の長名方向引数はbool以外のtruthinessも受け付けている。
            self.assertEqual(query(source=1, destination=0), [source])
            self.assertCountEqual(query(source=[], destination="enabled"), destinations)

    def test_query_removed_aliases_reject_without_changing_connections(self):
        """廃止した短縮名src/dst/idxと位置・名前の重複を拒否し、既存接続を変更しない。"""
        source, center, destinations = self._chain("queryConflicts")
        for method_name in ("getConnections",):
            query = getattr(center, method_name)
            for kwargs in ({"src": True}, {"dst": False}, {"idx": 0}):
                with self.subTest(method=method_name, kwargs=kwargs):
                    with self.assertRaises(TypeError):
                        query(**kwargs)
            with self.assertRaises(TypeError):
                query(True, False, False, None, False, False, True, source=True)
        self._assert_chain(source, center, destinations)

    def test_query_filters_return_forms_and_index_keep_their_contract(self):
        """方向指定に型・ペア・ノード・単一結果・明示Plug型を併用できる。"""
        source, center, destinations = self._chain("filters")

        self.assertEqual(center.getConnections(source=True, destination=False, index=0), source)
        self.assertIsNone(center.getConnections(source=False, destination=False, index=0))
        self.assertIsNone(center.getConnections(source=True, destination=False, index=99))
        self.assertEqual(center.getConnections(source=True, destination=False, asPair=True), [(center, source)])
        self.assertCountEqual(center.getConnections(source=False, destination=True, asNode=True),
                              [plug.getNode() for plug in destinations])
        self.assertEqual(center.getConnections(source=True, destination=False, type="network", exactType=True),
                         [source])
        self.assertEqual(center.getConnections(source=True, destination=True, t="transform", et=True), [])
        # pcls は廃止。ペアの両側は型登録に従う Plug で、位置はそのまま。
        pair = center.getConnections(source=True, destination=False, asPair=True, index=0)
        self.assertIsInstance(pair[0], mlib.plugs.Plug)
        self.assertIsInstance(pair[1], mlib.plugs.Plug)
        self.assertEqual(pair, (center, source))

    def test_query_original_positional_signature_is_preserved(self):
        """従来の位置引数を保ち、短縮名の別名を持たない。"""
        names = ("self", "s", "d", "c", "t", "et", "scn", "source", "destination",
                 "connections", "type", "exactType", "skipConversionNodes", "asPair",
                 "asNode", "checkChildren", "checkElements", "index")
        # 6.0.0からscn・skipConversionNodesの既定はTrue(getSource/getDestinationsと同じ)。
        defaults = (True, True, False, None, False, True, True, True, False, None,
                    False, True, False, False, True, True, None)
        signature = inspect.signature(mlib.plugs.Plug.getConnections)
        self.assertEqual(tuple(signature.parameters), names)
        self.assertEqual(tuple(parameter.default for parameter in
                               list(signature.parameters.values())[1:len(names)]), defaults)
        for parameter in list(signature.parameters.values())[:len(names)]:
            self.assertEqual(parameter.kind, inspect.Parameter.POSITIONAL_OR_KEYWORD)
        source, center, destinations = self._chain("positional")
        self.assertEqual(center.getConnections(True, False, False, None, False, False,
                                              True, True, False, None, False, False,
                                              False, False, True, True, 0), source)
        self.assertCountEqual(center.getConnections(False, True), destinations)
        self.assertEqual(inspect.signature(center.getConnections), inspect.signature(mlib.plugs.Plug.getConnections).replace(parameters=list(inspect.signature(mlib.plugs.Plug.getConnections).parameters.values())[1:]))

    def test_query_child_and_multi_expansion_does_not_change_direct_operations(self):
        """照会は子・マルチアトリビュートを展開し、接続判定と全切断は元のMPlugの範囲を保つ。"""
        owner = mlib.createNode("network", name="hierarchyOwner")
        cmds.addAttr(str(owner), longName="payload", attributeType="compound", numberOfChildren=1)
        cmds.addAttr(str(owner), longName="childValue", attributeType="double", parent="payload")
        parent = owner.getPlug("payload")
        child = owner.getPlug("childValue")
        array = owner.addAttr("values", attributeType="double", multi=True)
        source = self._value("hierarchySource")
        destination = self._value("hierarchyDestination")
        multi_destination = self._value("hierarchyArrayDestination")
        child.connect(source)
        destination.connect(child)
        element = array[7]
        element.connect(source)
        multi_destination.connect(element)
        for target, local, output in ((parent, child, destination),
                                      (array, element, multi_destination)):
            with self.subTest(target=str(target)):
                self.assertEqual(target.getConnections(source=True, destination=False, asPair=True),
                                 [(local, source)])
                self.assertEqual(target.getConnections(source=False, destination=True), [output])
                self.assertEqual(target.getConnections(source=True, destination=True,
                                                      checkChildren=False, checkElements=False), [])
                self.assertEqual(target.isConnected(), target.mplug().isConnected)
                self.assertEqual(target.isConnected(source=True, destination=False), target.mplug().isDestination)
                self.assertEqual(target.isConnected(source=False, destination=True), target.mplug().isSource)
                self.assertFalse(target.isConnectedTo(source))
                self.assertIs(target.disconnectAll(), target)
                self.assertTrue(cmds.isConnected(str(source), str(local)))
                self.assertTrue(cmds.isConnected(str(local), str(output)))

    def test_is_connected_matches_mplug_flags_in_each_direction(self):
        """単独入力・単独出力・両方向・未接続で入力と出力の判定を揃える。"""
        source, center, destinations = self._chain("flags")
        empty = self._value("flagsEmpty")
        for target in [source, center, destinations[0], empty]:
            with self.subTest(target=str(target)):
                mp = target.mplug()
                self.assertEqual(target.isConnected(), mp.isConnected)
                self.assertEqual(target.isConnected(source=True, destination=False), mp.isDestination)
                self.assertEqual(target.isConnected(source=False, destination=True), mp.isSource)
                self.assertFalse(target.isConnected(source=False, destination=False))

    def test_is_connected_to_checks_direction_and_all_supported_inputs(self):
        """Plug・MPlug・文字列を受け付け、自身から見た入力と出力を判定する。"""
        source, center, destinations = self._chain("peers")
        unrelated = self._value("peersUnrelated")
        for peer, incoming in ((source, True), (destinations[0], False)):
            for other in (peer, peer.mplug(), str(peer)):
                with self.subTest(peer=str(peer), input_type=type(other).__name__):
                    self.assertTrue(center.isConnectedTo(other))
                    self.assertEqual(center.isConnectedTo(other, source=True, destination=False), incoming)
                    self.assertEqual(center.isConnectedTo(other, source=False, destination=True), not incoming)
                    self.assertFalse(center.isConnectedTo(other, source=False, destination=False))
        self.assertFalse(center.isConnectedTo(unrelated))
        self.assertFalse(center.isConnectedTo(center))
        self.assertTrue(source.isConnectedTo(center, source=False, destination=True))
        self.assertFalse(source.isConnectedTo(center, source=True, destination=False))

    def test_new_direction_flags_require_bool_and_reject_removed_aliases(self):
        """判定・全切断の方向はboolだけを受け付け、廃止した短縮名src/dstを拒否する。"""
        source, center, destinations = self._chain("validation")
        methods = ((center.isConnected, ()), (center.isConnectedTo, (source,)),
                   (center.disconnectAll, ()))
        invalid = ({"source": 1}, {"destination": 0}, {"source": None}, {"destination": "true"},
                   {"src": True}, {"dst": False})
        for method, args in methods:
            for kwargs in invalid:
                with self.subTest(method=method.__name__, kwargs=kwargs):
                    with self.assertRaises(TypeError):
                        method(*args, **kwargs)
                    self._assert_chain(source, center, destinations)
            with self.subTest(method=method.__name__, positional=True):
                with self.assertRaises(TypeError):
                    method(*args, True, False)
                self._assert_chain(source, center, destinations)

    def test_disconnect_all_directions_return_self_and_preserve_other_side(self):
        """全切断も入力だけ・出力だけ・両方向・両Falseを選び、自身を返す。"""
        cases = ({}, {"source": True, "destination": False}, {"source": False, "destination": True},
                 {"source": False, "destination": False})
        for index, kwargs in enumerate(cases):
            with self.subTest(kwargs=kwargs):
                source, center, destinations = self._chain("disconnect" + str(index))
                src = kwargs.get("source", True)
                dst = kwargs.get("destination", True)
                self.assertIs(center.disconnectAll(**kwargs), center)
                self._assert_chain(source, center, destinations, incoming=not src, outgoing=not dst)

    def test_disconnect_all_is_one_undo_redo(self):
        """入力と複数出力の解除を一回のUndo/Redoでまとめて戻せる。"""
        source, center, destinations = self._chain("undo")
        cmds.flushUndo()
        self.assertIs(center.disconnectAll(source=True, destination=True), center)
        self._assert_chain(source, center, destinations, incoming=False, outgoing=False)
        cmds.undo()
        self._assert_chain(source, center, destinations)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.redo()
        self._assert_chain(source, center, destinations, incoming=False, outgoing=False)

    def test_conversion_queries_and_direct_operations_keep_conversion_nodes(self):
        """照会の変換省略を維持し、判定・全切断は直接の変換端点を対象にする。"""
        source = self._value("conversionSource")
        center = self._value("conversionCenter")
        output = self._value("conversionDestination")
        conversion = mlib.createNode("unitConversion", name="conversion")
        conversion_input = conversion.getPlug("input")
        conversion_output = conversion.getPlug("output")
        conversion_input.connect(source)
        center.connect(conversion_output)
        output.connect(center)
        # 6.0.0から既定は変換ノードを飛ばす。scn=False・skipConversionNodes=Falseは直結。
        self.assertEqual(center.getConnections(source=True, destination=False), [source])
        self.assertEqual(center.getConnections(source=True, destination=False, scn=False), [conversion_output])
        self.assertEqual(source.getConnections(source=False, destination=True), [center])
        self.assertEqual(source.getConnections(source=False, destination=True, skipConversionNodes=False),
                         [conversion_input])
        self.assertTrue(center.isConnectedTo(conversion_output, source=True, destination=False))
        self.assertFalse(center.isConnectedTo(source, source=True, destination=False))
        self.assertIs(center.disconnectAll(source=True, destination=False), center)
        self.assertFalse(cmds.isConnected(str(conversion_output), str(center)))
        self.assertTrue(cmds.isConnected(str(source), str(conversion_input)))
        self.assertTrue(cmds.isConnected(str(center), str(output)))
        self.assertTrue(cmds.objExists(str(conversion)))

    def test_invalid_self_and_other_references_are_still_checked(self):
        """削除済みノード・アトリビュートの参照を照会・判定・全切断で拒否する。"""
        valid = self._value("validReference")
        deleted_node = self._value("deletedNodeReference")
        deleted_attr = self._value("deletedAttrReference")
        deleted_node.getNode().delete()
        cmds.deleteAttr(str(deleted_attr))
        for target in (deleted_node, deleted_attr):
            for method_name in ("getConnections", "isConnected", "disconnectAll"):
                with self.subTest(target=target is deleted_node, method=method_name):
                    with self.assertRaises(RuntimeError):
                        getattr(target, method_name)(source=False, destination=False)
            with self.assertRaises(RuntimeError):
                target.isConnectedTo(valid, source=True, destination=False)
            for kwargs in ({}, {"source": True, "destination": False},
                           {"source": False, "destination": False}):
                with self.subTest(target=target is deleted_node, direction=kwargs):
                    with self.assertRaises(RuntimeError):
                        valid.isConnectedTo(target, **kwargs)
        with self.assertRaises(RuntimeError):
            valid.isConnectedTo("doesNotExist.value", source=True, destination=False)

    def test_both_false_and_unconnected_calls_do_not_create_undo_entries(self):
        """両False・未接続の操作は接続を保ち、Undoキューに編集を残さない。"""
        source, center, destinations = self._chain("noop")
        empty = self._value("noopEmpty")
        cmds.flushUndo()
        self.assertEqual(center.getConnections(source=False, destination=False), [])
        self.assertFalse(center.isConnected(source=False, destination=False))
        self.assertFalse(center.isConnectedTo(source, source=False, destination=False))
        self.assertIs(center.disconnectAll(source=False, destination=False), center)
        self.assertIs(empty.disconnectAll(), empty)
        self.assertEqual(empty.getConnections(source=True, destination=True), [])
        self.assertFalse(empty.isConnected())
        self.assertFalse(empty.isConnectedTo(source))
        self._assert_chain(source, center, destinations)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_disconnect_all_does_not_force_or_unlock_locked_destinations(self):
        """全切断は既存のロック制約を守り、forceフラグを追加しない。"""
        source, center, destinations = self._chain("locked")
        destinations[0].setFlags(locked=True)
        with self.assertRaises(RuntimeError):
            center.disconnectAll(source=False, destination=True)
        self.assertTrue(destinations[0].isLocked())
        self.assertTrue(cmds.isConnected(str(center), str(destinations[0])))
        self.assertTrue(cmds.isConnected(str(source), str(center)))
        with self.assertRaises(TypeError):
            center.disconnectAll(force=True)
        self.assertTrue(destinations[0].isLocked())

    def _value(self, name):
        """接続に使用するdoubleアトリビュートのPlugを作る。

        Args:
            name (str): 所有ノード名。

        Returns:
            Plug: 作成したvalueアトリビュート。
        """
        node = mlib.createNode("network", name=name)
        return node.addAttr("value", attributeType="double")

    def _chain(self, prefix):
        """入力一つと出力二つを持つ中心Plugを作る。

        Args:
            prefix (str): ノード名の接頭辞。

        Returns:
            tuple[Plug, Plug, list[Plug]]: 入力元・中心・出力先。
        """
        source = self._value(prefix + "Source")
        center = self._value(prefix + "Center")
        destinations = [self._value(prefix + "First"), self._value(prefix + "Second")]
        center.connect(source)
        for destination in destinations:
            destination.connect(center)
        return source, center, destinations

    def _assert_chain(self, source, center, destinations, incoming=True, outgoing=True):
        """接続の保持状態を入力・出力別に確認する。

        Args:
            source (Plug): 入力元。
            center (Plug): 中心Plug。
            destinations (list[Plug]): 出力先。
            incoming (bool): 入力接続の期待値。
            outgoing (bool): 出力接続の期待値。
        """
        self.assertEqual(cmds.isConnected(str(source), str(center)), incoming)
        for destination in destinations:
            self.assertEqual(cmds.isConnected(str(center), str(destination)), outgoing)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

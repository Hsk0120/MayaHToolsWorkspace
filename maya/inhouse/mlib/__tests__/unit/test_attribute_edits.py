"""アトリビュートの再作成と追加前検証で、定義・接続・Undoを保つ。"""

import importlib
import sys
import unittest
import uuid
from unittest.mock import patch

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib

mlib.reload()


class AttributeEditsTest(unittest.TestCase):
    """専用名前空間で、破壊的な並べ替えと不正な追加を検証する。"""

    def setUp(self):
        """このテストだけが所有するノードとUndo状態を用意する。"""
        self.namespace = "mlibAttributeEdits_" + uuid.uuid4().hex
        cmds.namespace(add=self.namespace)
        self.node = mlib.getNode(cmds.createNode("network", name=self.namespace + ":node"))
        self.undo_enabled = cmds.undoInfo(query=True, state=True)
        if not self.undo_enabled:
            cmds.undoInfo(state=True)

    def tearDown(self):
        """専用ノードを削除し、元のUndo設定へ戻す。"""
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_enabled)
        self.assertEqual(cmds.undoInfo(query=True, state=True), self.undo_enabled)

    def _definition(self, name):
        """Mayaの定義とPlug状態を、比較できる値として取得する。

        Args:
            name (str): 専用ノードのアトリビュート長名。

        Returns:
            dict: 名前・範囲・定義フラグ・値・表示状態。
        """
        plug = self.node.getPlug(name)
        fn = om2.MFnAttribute(plug.mplug().attribute())
        data = {key: getattr(fn, key) for key in (
            "readable", "writable", "storable", "connectable", "cached",
            "usedAsColor", "usedAsFilename", "disconnectBehavior",
        )}
        data.update(shortName=plug.getShortName(), niceName=plug.getNiceName(),
                    value=plug.get(), default=plug.getDefault(),
                    hidden=fn.hidden, channelBoxHidden=plug.isHidden(), keyable=plug.isKeyable(),
                    channelBox=plug.mplug().isChannelBox, locked=plug.isLocked())
        for flag in ("minExists", "maxExists", "softMinExists", "softMaxExists"):
            data[flag] = cmds.attributeQuery(name, node=self.node.getFullName(), **{flag: True})
        for exists, query in (("minExists", "minimum"), ("maxExists", "maximum"),
                              ("softMinExists", "softMin"), ("softMaxExists", "softMax")):
            if data[exists]:
                data[query] = cmds.attributeQuery(name, node=self.node.getFullName(), **{query: True})
        return data

    def _linked_attributes(self):
        """内部・外部接続とaliasを持つ3個の定義を作る。

        Returns:
            Node: 外部接続先を持つノード。
        """
        for name, value in (("first", 3.0), ("second", 2.0), ("third", 1.0)):
            self.node.addAttr(name, defaultValue=value, keyable=True)
        other = mlib.getNode(cmds.createNode("network", name=self.namespace + ":other"))
        target = other.addAttr("input")
        self.node.getPlug("first").connectTo(self.node.getPlug("second"))
        self.node.getPlug("second").connectTo(self.node.getPlug("third"))
        self.node.getPlug("third").connectTo(target)
        self.node.getPlug("first").setAlias("inputAlias")
        self.node.getPlug("third").setFlags(locked=True)
        return other

    def _assert_links(self, other):
        """現在の定義を再取得し、内部・外部の接続とaliasを確認する。

        Args:
            other (Node): 外部接続先の所有ノード。
        """
        for source, target in (("first", "second"), ("second", "third")):
            self.assertTrue(cmds.isConnected(self.node.getFullName() + "." + source,
                                             self.node.getFullName() + "." + target))
        self.assertTrue(cmds.isConnected(self.node.getFullName() + ".third",
                                         other.getFullName() + ".input"))
        self.assertEqual(self.node.getPlug("inputAlias"), self.node.getPlug("first"))
        self.assertTrue(self.node.getPlug("third").isLocked())
        self.assertEqual(other.getPlug("input").get(), 3.0)

    def _ordered_names(self):
        """Maya管理のalias保管領域を除く、ユーザー定義の並びを返す。

        Returns:
            list[str]: 表示順を変更するアトリビュート長名。
        """
        return [name for name in [p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)] if name != "attributeAliasList"]

    def test_move_preserves_short_name_limits_and_flags(self):
        """短名・soft limit・表示状態・定義フラグを再作成とUndoで保つ。"""
        cmds.addAttr(self.node.getFullName(), longName="firstValue", shortName="fv",
                     niceName="First Value", attributeType="double", defaultValue=2,
                     minValue=0, maxValue=10, softMinValue=1, softMaxValue=9,
                     keyable=False, storable=False, hidden=True)
        first = self.node.getPlug("firstValue")
        first.set(4)
        first.setFlags(channelBox=True, locked=True)
        self.node.addAttr("secondValue")
        before = self._definition("firstValue")
        self.assertIs(self.node.moveAttrOrder("firstValue", 1), self.node)
        self.assertEqual([p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)], ["secondValue", "firstValue"])
        self.assertEqual(self._definition("firstValue"), before)
        self.assertFalse(first.isValid())
        cmds.undo()
        self.assertEqual([p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)], ["firstValue", "secondValue"])
        self.assertEqual(self._definition("firstValue"), before)
        cmds.redo()
        self.assertEqual(self._definition("firstValue"), before)

    def test_move_restores_all_definitions_before_internal_connections(self):
        """作成順に逆らう内部接続も、全定義生成後に一度だけ復元する。"""
        other = self._linked_attributes()
        self.node.moveAttrOrder("first", 2)
        self.assertEqual(self._ordered_names(), ["second", "third", "first"])
        self._assert_links(other)
        cmds.undo()
        self.assertEqual(self._ordered_names(), ["first", "second", "third"])
        self._assert_links(other)
        cmds.redo()
        self._assert_links(other)

    def test_move_restores_non_writable_definition(self):
        """元のreadable/writable定義で作成し、cmdsで値を復元する。"""
        cmds.addAttr(self.node.getFullName(), longName="first", attributeType="double",
                     defaultValue=4, writable=False, readable=False)
        self.node.addAttr("second")
        before = self._definition("first")
        self.node.moveAttrOrder("first", 1)
        self.assertEqual(self._definition("first"), before)

    def test_move_rolls_back_creation_failure_with_order_and_connections(self):
        """一部の再作成後の失敗でも、元の定義順・値・接続へ戻す。"""
        other = self._linked_attributes()
        module = importlib.import_module("mlib.nodes.node")
        original = module._create_movable_attr
        calls = []

        def fail_second(node, info):
            """2個目の再作成でMayaの編集失敗を模擬する。"""
            calls.append(info["longName"])
            if len(calls) == 2:
                raise RuntimeError("simulated recreation failure")
            return original(node, info)

        with patch.object(module, "_create_movable_attr", fail_second):
            with self.assertRaisesRegex(RuntimeError, "simulated recreation failure"):
                self.node.moveAttrOrder("first", 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(self._ordered_names(), ["first", "second", "third"])
        self._assert_links(other)

    def test_move_rejects_non_connectable_definition_before_changes(self):
        """cmdsで再現できない特殊フラグを、定義削除前に拒否する。"""
        first = self.node.addAttr("first")
        self.node.addAttr("second")
        om2.MFnAttribute(first.mplug().attribute()).connectable = False
        before = [p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)]
        with self.assertRaisesRegex(TypeError, "non-connectable"):
            self.node.moveAttrOrder("first", 1)
        self.assertEqual([p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)], before)
        self.assertTrue(first.isValid())

    def test_move_rejects_undo_disabled_before_changes(self):
        """復旧できないUndo無効時は、定義を削除する前に拒否する。"""
        self.node.addAttr("first")
        self.node.addAttr("second")
        # stateWithoutFlush=Falseは、Maya 2025/2027のmayapyで以後のcreateNodeの名前空間が外れるため、
        # Undoの切替えはstate=を使う。
        before = [p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)]
        cmds.undoInfo(state=False)
        try:
            with self.assertRaisesRegex(RuntimeError, "requires Undo"):
                self.node.moveAttrOrder("first", 1)
            self.assertFalse(cmds.undoInfo(query=True, state=True))
            self.assertEqual([p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)], before)
        finally:
            cmds.undoInfo(state=True)
        self.assertTrue(cmds.undoInfo(query=True, state=True))
        # 切替え後も専用名前空間の中にノードを作れる。
        probe = cmds.createNode("network", name=self.namespace + ":probe")
        self.assertEqual(probe, self.namespace + ":probe")
        # fast引数のない操作は外側の呼出しモードに依存せず通常Undoを使う。
        self.node.moveAttrOrder("first", 1)
        self.assertEqual([p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)], ["second", "first"])
        cmds.undo()
        self.assertEqual([p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)], before)

    def test_add_preflights_child_names_and_component_counts(self):
        """親追加前に子の重複・既存名・成分数・不正既定値を拒否する。"""
        self.node.addAttr("existing")
        attempts = [
            dict(childNames=["same", "same", "last"]),
            dict(childNames=["newFirst", "existing", "newLast"]),
            dict(childShortNames=["x", "x", "z"]),
            dict(childNames=["newFirst", "newSecond"]),
            dict(defaultValue=[1, 2]),
            dict(minValue=[0, 0]),
            dict(defaultValue=[1, "invalid", 3]),
        ]
        for fast in (False, True):
            for index, flags in enumerate(attempts):
                name = "attempt_{}_{}".format(int(fast), index)
                before = [p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)]
                with self.subTest(fast=fast, flags=flags):
                    with self.assertRaises((TypeError, ValueError, RuntimeError)):
                        self.node.addAttr(name, "double3", fast=fast, **flags)
                    self.assertEqual([p.getLongName() for p in self.node.getPlugs(userDefined=True, includeChildren=False)], before)

    def test_add_preflights_typed_defaults_and_keeps_default_return(self):
        """typed既定値を追加前に検証し、既定Plug返却とgetPlug=Falseを保つ。"""
        for fast in (False, True):
            for kind, value in (("matrix", [1, 2]), ("doubleArray", ["invalid"])):
                name = "invalid_{}_{}".format(int(fast), kind)
                with self.subTest(fast=fast, kind=kind):
                    with self.assertRaises((TypeError, ValueError, RuntimeError)):
                        self.node.addAttr(name, kind, defaultValue=value, fast=fast)
                    self.assertFalse(self.node.hasAttr(name))
        plug = self.node.addAttr("valid", "string", defaultValue="value")
        self.assertIsInstance(plug, mlib.plugs.StringPlug)
        self.assertEqual(plug.get(), "value")
        self.assertIsNone(self.node.addAttr("noReturn", getPlug=False))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

"""内部責務の移動後も型登録・入力検証・Undoの契約を維持する。"""
import sys
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import mlib


class InternalRefactoringTest(unittest.TestCase):
    """公開入口から内部再構成の境界条件を検証する。"""

    def setUp(self):
        """専用シーンと既定単位を用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_class_operations_keep_undo_and_deferred_calls(self):
        """アトリビュート追加のUndoとMayaへの遅延予約を維持する。"""
        import maya.utils
        from mlib.common import Deferred
        node = mlib.createNode("transform")
        plug = node.addAttr("referenceCheck", attributeType="double", defaultValue=3)
        self.assertEqual(plug.get(), 3)
        cmds.undo()
        self.assertFalse(cmds.attributeQuery("referenceCheck", node=node.getFullName(), exists=True))
        callback = lambda: None
        with patch.object(maya.utils, "executeDeferred") as enqueue:
            Deferred.call(callback, 3, value=4)
            enqueue.assert_called_once_with(callback, 3, value=4)

    def test_general_input_expansion_does_not_reenter_node_resolution(self):
        """一度きりの反復入力とPlug列を、Nodesの解決入口へ戻らず名前にする。"""
        from mlib.nodes.node import Nodes
        node = mlib.createNode("transform")
        plug = node.getPlug("tx")
        with patch.object(Nodes, "_resolve_inputs", side_effect=AssertionError("input cycle")):
            self.assertEqual(mlib.core.object.Object._input_names(x for x in [[plug]]), [plug.getFullName()])
            with self.assertRaises(TypeError):
                mlib.core.object.Object._input_names([node, node.getFullName()])


    def test_influence_single_multiple_and_scene_changes(self):
        """単数・複数検索が改名・除去後にも同じ物理番号を返す。"""
        joints = [cmds.createNode("joint") for _ in range(3)]
        mesh = cmds.polyCube(ch=False)[0]
        skin = mlib.getNode(cmds.skinCluster(joints, mesh, tsb=True)[0])
        joints[0] = cmds.rename(joints[0], "renamedInfluence")
        queries = [joints[2], joints[0], joints[2], "notAnInfluence"]
        self.assertEqual([skin._jnt_index(x) for x in queries],
                         skin._influence_indices(queries, skin.fn.influenceObjects()))
        cmds.skinCluster(skin.getFullName(), edit=True, removeInfluence=joints[1])
        self.assertIsNone(skin._jnt_index(joints[1]))
        self.assertEqual(skin._jnt_index(joints[2]), 1)
        cmds.undo()
        self.assertEqual(skin._jnt_index(joints[2]), 2)

    def test_numeric_read_write_and_units(self):
        """数値型の共有定義が通常更新・fast更新・単位規則を変えない。"""
        node = mlib.createNode("transform")
        for kind, value in (("bool", True), ("byte", 12), ("char", 3), ("short", -2),
                            ("long", 53), ("float", 1.25), ("double", 2.5)):
            name = "value_" + kind
            cmds.addAttr(node.getFullName(), longName=name, attributeType=kind)
            plug = node.getPlug(name)
            plug.set(value)
            normal = plug.get()
            plug.set(0, fast=True)
            plug.set(value, fast=True)
            self.assertEqual(plug.get(), normal)
            self.assertEqual(plug.getType(), kind)
        cmds.currentUnit(linear="m", angle="rad")
        node.getPlug("tx").set(2, fast=True)
        self.assertAlmostEqual(node.getPlug("tx").get(), 2)
        # 角度のget/setはUI単位によらずrad。
        node.getPlug("rx").set(1, fast=True)
        import math
        self.assertAlmostEqual(node.getPlug("rx").get(), 1.0)

    def test_reload_rebuilds_registry_and_caches(self):
        """新しい基底・型登録・型情報で再取得でき、独自登録を残さない。"""
        from mlib.core import registry as registry_module
        old_registry = mlib.nodes.Node._registry
        old_registry.register("temporaryRefactorType", mlib.nodes.Node)
        registry_module._INHERITED_TYPES_CACHE["temporaryRefactorType"] = ("temporaryRefactorType",)
        name = cmds.createNode("transform")
        for _ in range(2):
            mlib.reload()
            node = mlib.getNode(name)
            self.assertIs(type(node), mlib.nodes.Transform)
            self.assertIs(type(node.getPlug("tx")), mlib.plugs.DoubleLinearPlug)
            self.assertIsNot(mlib.nodes.Node._registry, old_registry)
            self.assertIsNone(mlib.nodes.Node._registry.lookup("temporaryRefactorType"))
            from mlib.core import registry as registry_module
            self.assertNotIn("temporaryRefactorType", registry_module._INHERITED_TYPES_CACHE)
            node.getPlug("tx").set(9, fast=True)
            self.assertEqual(node.getPlug("tx").get(), 9)
            self.assertIs(mlib.getNode, mlib.cmds.getNode)


    def test_deferred_validates_before_reserving(self):
        """予約引数を維持し、不正なコールバックをMayaへ渡さない。"""
        import maya.utils
        from mlib.common import Deferred
        callback = lambda value: value
        with patch.object(maya.utils, "executeDeferred") as enqueue:
            self.assertIsNone(Deferred.call(callback, 1, flag=True))
            enqueue.assert_called_once_with(callback, 1, flag=True)
            with self.assertRaises(TypeError):
                Deferred.call("print('not callable')")
            self.assertEqual(enqueue.call_count, 1)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

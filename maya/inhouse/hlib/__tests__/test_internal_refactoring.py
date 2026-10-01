"""内部責務の移動後も保存形式・部分失敗・型登録の契約を維持する。"""
import sys
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import hlib


class InternalRefactoringTest(unittest.TestCase):
    """公開入口から内部再構成の境界条件を検証する。"""

    def setUp(self):
        """専用シーンと既定単位を用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_snapshot_base_kind_and_serialized_shape(self):
        """基底Snapshotのkindによる適用と既存JSON構造を維持する。"""
        from hlib.json.snapshots import Snapshot
        node = hlib.createNode("transform")
        node.plug("tx").set(3)
        saved = hlib.json.capture([node], kind="attributes", attributes=["translateX"])
        data = saved.to_data()
        self.assertEqual(set(data), {"kind", "records", "units", "version"})
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["records"][0]["attributes"],
                         [{"name": "translateX", "type": "doubleLinear", "value": 3.0}])
        generic = Snapshot(**data)
        node.plug("tx").set(7)
        generic.apply()
        self.assertEqual(node.plug("tx").get(), 3)
        cmds.undo()
        self.assertEqual(node.plug("tx").get(), 7)
        self.assertEqual(hlib.json.loads(hlib.json.dumps(saved)).to_data(), data)

    def test_snapshot_partial_failure_and_undo(self):
        """全件検証後の実行失敗は先行変更を残し、一回のUndoで戻せる。"""
        from hlib.json import snapshots
        node = hlib.createNode("transform")
        saved = hlib.json.capture([node], kind="attributes", attributes=["translateX", "translateY"])
        node.plug("tx").set(3)
        node.plug("ty").set(4)
        original = snapshots._set_attribute

        def fail_second(name, attr):
            """二番目の更新時点でMayaの実行失敗を模擬する。"""
            if attr["name"] == "translateY":
                raise RuntimeError("second write failed")
            return original(name, attr)

        with patch.object(snapshots, "_set_attribute", side_effect=fail_second):
            with self.assertRaisesRegex(RuntimeError, "second write"):
                saved.apply()
        self.assertEqual(node.plug("tx").get(), 0)
        self.assertEqual(node.plug("ty").get(), 4)
        cmds.undo()
        self.assertEqual(node.plug("tx").get(), 3)
        self.assertEqual(node.plug("ty").get(), 4)

    def test_influence_single_multiple_and_scene_changes(self):
        """単数・複数検索が改名・除去後にも同じ物理番号を返す。"""
        joints = [cmds.createNode("joint") for _ in range(3)]
        mesh = cmds.polyCube(ch=False)[0]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, tsb=True)[0])
        joints[0] = cmds.rename(joints[0], "renamedInfluence")
        queries = [joints[2], joints[0], joints[2], "notAnInfluence"]
        self.assertEqual([skin._jnt_index(x) for x in queries],
                         skin._influence_indices(queries, skin.fn.influenceObjects()))
        cmds.skinCluster(skin.full_name(), edit=True, removeInfluence=joints[1])
        self.assertIsNone(skin._jnt_index(joints[1]))
        self.assertEqual(skin._jnt_index(joints[2]), 1)
        cmds.undo()
        self.assertEqual(skin._jnt_index(joints[2]), 2)

    def test_numeric_read_write_and_units(self):
        """数値型の共有定義が通常更新・fast更新・単位規則を変えない。"""
        node = hlib.createNode("transform")
        for kind, value in (("bool", True), ("byte", 12), ("char", 3), ("short", -2),
                            ("long", 53), ("float", 1.25), ("double", 2.5)):
            name = "value_" + kind
            cmds.addAttr(node.full_name(), longName=name, attributeType=kind)
            plug = node.plug(name)
            plug.set(value)
            normal = plug.get()
            plug.set(0, fast=True)
            plug.set(value, fast=True)
            self.assertEqual(plug.get(), normal)
            self.assertEqual(plug.data_type(), kind)
        cmds.currentUnit(linear="m", angle="rad")
        node.plug("tx").set(2, fast=True)
        self.assertAlmostEqual(node.plug("tx").get(), 2)
        # 角度のgetは従来から度。setの単位と安易に共通化しない。
        node.plug("rx").set(1, fast=True)
        import math
        self.assertAlmostEqual(node.plug("rx").get(), math.degrees(1))

    def test_reload_rebuilds_registry_and_caches(self):
        """新しい基底・型登録・型情報で再取得でき、独自登録を残さない。"""
        from hlib._core import typeHierarchy
        old_registry = hlib.nodes.Node._registry
        old_registry.register("temporaryRefactorType", hlib.nodes.Node)
        typeHierarchy._INHERITED_TYPES_CACHE["temporaryRefactorType"] = ("temporaryRefactorType",)
        name = cmds.createNode("transform")
        for _ in range(2):
            hlib.reload()
            node = hlib.getNode(name)
            self.assertIs(type(node), hlib.nodes.Transform)
            self.assertIs(type(node.plug("tx")), hlib.plugs.DoubleLinearPlug)
            self.assertIsNot(hlib.nodes.Node._registry, old_registry)
            self.assertIsNone(hlib.nodes.Node._registry.lookup("temporaryRefactorType"))
            from hlib._core import typeHierarchy
            self.assertNotIn("temporaryRefactorType", typeHierarchy._INHERITED_TYPES_CACHE)
            node.plug("tx").set(9, fast=True)
            self.assertEqual(node.plug("tx").get(), 9)
            self.assertIs(hlib.getNode, hlib.cmds.getNode)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

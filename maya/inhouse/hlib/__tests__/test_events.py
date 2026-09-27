"""scriptJob所有管理とhrigが再利用する属性操作を検証する。"""

import unittest
from unittest.mock import patch

from maya import cmds
import hlib


class CommonRigApiTest(unittest.TestCase):
    """新規シーンを作らず、テストが所有するノードだけを使用する。"""

    def setUp(self):
        """テスト専用ノードと比較用のドライバーを作る。"""
        self.node = hlib.createNode("transform", skipSelect=True)
        self.driver = hlib.createNode("transform", skipSelect=True)

    def tearDown(self):
        """所有ノードだけを削除する。"""
        hlib.delete([self.node, self.driver])

    def test_plug_lookup(self):
        """名前・ラッパー・MPlugが同じ属性を解決する。"""
        plug = self.node.plug("tx")
        for value in (plug.full_name(), plug, plug.mplug()):
            self.assertEqual(hlib.getPlug(value).full_name(), plug.full_name())

    def test_changed_value_and_lock(self):
        """無変更は更新せず、ロック付き更新を一度のUndoで戻せる。"""
        plug = self.node.add_attr("setting", attribute_type="long", default_value=0)
        plug.set_locked(True)
        self.assertFalse(plug.set_if_changed(0, unlock=True))
        self.assertTrue(plug.set_if_changed(2, unlock=True))
        self.assertTrue(plug.is_locked())
        cmds.undo()
        self.assertEqual(plug.get(), 0)
        self.assertTrue(plug.is_locked())
        cmds.redo()
        self.assertEqual(plug.get(), 2)
        self.assertTrue(plug.is_locked())

    def test_failed_write_restores_lock(self):
        """接続先への書込みを拒否した場合もロックを復元する。"""
        plug = self.node.plug("tx")
        self.driver.plug("tx").connect(plug)
        plug.set_locked(True)
        with self.assertRaises(RuntimeError):
            plug.set_if_changed(5.0, unlock=True)
        self.assertTrue(plug.is_locked())

    def test_matrix_radian_units(self):
        """hlibの行列設定がラジアン設定でも姿勢を再現する。"""
        previous = cmds.currentUnit(query=True, angle=True)
        try:
            cmds.currentUnit(angle="rad")
            cmds.setAttr(self.driver.full_name() + ".rotate", 0.2, 0.4, -0.3)
            matrix = self.driver.get_matrix(ws=True)
            self.node.set_matrix(matrix, ws=True)
            self.assertTrue(matrix.isEquivalent(self.node.get_matrix(ws=True), 1e-8))
        finally:
            cmds.currentUnit(angle=previous)

    def test_batch_rejected(self):
        """バッチでは無効な監視を作成したように振る舞わない。"""
        if not cmds.about(batch=True):
            self.skipTest("Batch-only guard")
        with self.assertRaises(RuntimeError):
            hlib.general.ScriptJob(event="SelectionChanged", callback=lambda: None)

    def test_owner_lifecycle(self):
        """Maya呼出を模倣し、重複防止・外部解除後の再登録・所有解除を検証する。"""
        live = {99}
        next_id = iter(range(100, 110))

        def script_job(**options):
            """イベント発火以外のMaya登録・解除を模倣する。"""
            if "exists" in options:
                return options["exists"] in live
            if "kill" in options:
                live.remove(options["kill"])
                return
            identifier = next(next_id)
            live.add(identifier)
            return identifier

        with patch.object(cmds, "about", return_value=False), patch.object(
            cmds, "scriptJob", side_effect=script_job
        ):
            jobs = hlib.general.ScriptJobs()
            first = jobs.add("selection", event="SelectionChanged", callback=lambda: None)
            self.assertIs(
                first, jobs.add("selection", event="SelectionChanged", callback=lambda: None)
            )
            live.remove(first.id)
            self.assertFalse(jobs.exists())
            second = jobs.add("selection", event="SelectionChanged", callback=lambda: None)
            self.assertNotEqual(first.id, second.id)
            jobs.stop()
            jobs.stop()
            self.assertEqual(live, {99})


if __name__ == "__main__":
    unittest.main()

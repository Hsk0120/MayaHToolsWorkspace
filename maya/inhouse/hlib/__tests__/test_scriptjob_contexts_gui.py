"""一時ScriptJobsの実登録・解除を使い捨てMaya GUIで検証する。"""
import unittest

from maya import cmds
import hlib


@unittest.skipIf(cmds.about(batch=True), "Requires Maya GUI for native scriptJob registration")
class NativeScriptJobContextsTest(unittest.TestCase):
    def setUp(self):
        self.node = hlib.createNode("transform", skipSelect=True)
        self.jobs = hlib.common.ScriptJobs()
        self.external = hlib.common.ScriptJob(event="SelectionChanged", callback=lambda: None)

    def tearDown(self):
        self.jobs.stop()
        self.external.stop()
        cmds.delete(self.node.getFullName())

    def test_native_registration_and_cleanup_preserve_target_and_external_job(self):
        """アトリビュート監視・イベント監視を解除しても対象ノードと外部監視を残す。"""
        before = self.jobs.add("before", event="SelectionChanged", callback=lambda: None)
        with self.jobs.temporary():
            attribute = self.jobs.add("attribute", attribute=self.node.getPlug("translateX"), callback=lambda: None)
            self.assertTrue(before.exists())
            self.assertTrue(attribute.exists())
            self.assertTrue(cmds.scriptJob(exists=before.id))
            self.assertTrue(cmds.scriptJob(exists=attribute.id))
        self.assertFalse(cmds.scriptJob(exists=before.id))
        self.assertFalse(cmds.scriptJob(exists=attribute.id))
        self.assertTrue(self.node.isValid())
        self.assertTrue(self.external.exists())

    def test_native_cleanup_after_body_exception(self):
        """本体例外をそのまま送り、実イベント監視を解除する。"""
        original = ValueError("native context body failed")
        try:
            with self.jobs.temporary():
                job = self.jobs.add("selection", event="SelectionChanged", callback=lambda: None)
                self.assertTrue(job.exists())
                raise original
        except ValueError as caught:
            self.assertIs(caught, original)
        else:
            self.fail("Original exception was suppressed")
        self.assertFalse(cmds.scriptJob(exists=job.id))
        self.assertTrue(self.external.exists())


if __name__ == "__main__":
    unittest.main()

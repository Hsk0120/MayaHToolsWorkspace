"""一時ScriptJobsの解除失敗・再試行・入れ子を模擬検証する。"""
import unittest
from unittest.mock import Mock, patch

import hlib


class ScriptJobContextsTest(unittest.TestCase):
    def test_normal_exit_stops_only_owned_jobs(self):
        """既存登録も解除対象とし、外部の監視に触れない。"""
        first, second, external = Mock(), Mock(), Mock()
        first.exists.return_value = second.exists.return_value = True
        with patch("hlib.common.scriptJobs.ScriptJob", side_effect=[first, second]):
            jobs = hlib.common.ScriptJobs()
            jobs.add("before", event="SelectionChanged", callback=lambda: None)
            with jobs.temporary() as active:
                self.assertIs(active, jobs)
                active.add("inside", event="SelectionChanged", callback=lambda: None)
            first.stop.assert_called_once_with()
            second.stop.assert_called_once_with()
            external.stop.assert_not_called()
            self.assertFalse(jobs.exists())

    def test_body_exception_survives_cleanup_failure_and_retry_is_possible(self):
        """解除失敗を通知し、元の例外を保って監視を再試行用に残す。"""
        failed, other = Mock(), Mock()
        failed.stop.side_effect = RuntimeError("cannot kill")
        body_error = ValueError("body failed")
        with patch("hlib.common.scriptJobs.ScriptJob", side_effect=[failed, other]), \
                patch("hlib.logger.warning") as warning:
            jobs = hlib.common.ScriptJobs()
            try:
                with jobs.temporary():
                    jobs.add("failed", event="SelectionChanged", callback=lambda: None)
                    jobs.add("other", event="SelectionChanged", callback=lambda: None)
                    raise body_error
            except ValueError as caught:
                self.assertIs(caught, body_error)
            else:
                self.fail("Original exception was suppressed")
            warning.assert_called_once()
            other.stop.assert_called_once_with()
            failed.stop.side_effect = None
            jobs.stop()
            self.assertEqual(failed.stop.call_count, 2)
            self.assertEqual(other.stop.call_count, 1)
            self.assertFalse(jobs.exists())

    def test_normal_exit_reports_cleanup_failure(self):
        """本体が成功した場合の解除失敗は成功扱いにしない。"""
        job = Mock()
        job.stop.side_effect = RuntimeError("cannot kill")
        with patch("hlib.common.scriptJobs.ScriptJob", return_value=job), patch("hlib.logger.warning"):
            jobs = hlib.common.ScriptJobs()
            with self.assertRaisesRegex(RuntimeError, "Failed to stop scriptJobs"):
                with jobs.temporary():
                    jobs.add("failed", event="SelectionChanged", callback=lambda: None)
            job.stop.side_effect = None
            with jobs.temporary():
                pass
            self.assertEqual(job.stop.call_count, 2)

    def test_nested_same_instance_does_not_stop_outer_jobs(self):
        """内側の入場拒否で外側監視を解除しない。"""
        job = Mock()
        with patch("hlib.common.scriptJobs.ScriptJob", return_value=job):
            jobs = hlib.common.ScriptJobs()
            with jobs.temporary():
                jobs.add("outer", event="SelectionChanged", callback=lambda: None)
                with self.assertRaisesRegex(RuntimeError, "cannot be nested"):
                    with jobs.temporary():
                        self.fail("Nested context should not enter")
                job.stop.assert_not_called()
                self.assertTrue(jobs.exists())
            job.stop.assert_called_once_with()

    def test_separate_instances_can_nest(self):
        """異なるグループの一時監視は独立して解除する。"""
        outer, inner = Mock(), Mock()
        with patch("hlib.common.scriptJobs.ScriptJob", side_effect=[outer, inner]):
            with hlib.common.ScriptJobs().temporary() as jobs:
                jobs.add("outer", event="SelectionChanged", callback=lambda: None)
                with hlib.common.ScriptJobs().temporary() as other:
                    other.add("inner", event="SelectionChanged", callback=lambda: None)
                inner.stop.assert_called_once_with()
                outer.stop.assert_not_called()
            outer.stop.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

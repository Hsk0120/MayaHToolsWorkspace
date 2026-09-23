"""hlib.utils.progress の progress_bar を検証するMaya内テスト。"""

import io
import sys
import unittest

import hlib
hlib.reload()
from hlib.utils.progress import progress_bar


class ProgressBarTest(unittest.TestCase):
    """空入力、要素の受け渡し、notify コールバック、末尾改行を検証する。"""

    def test_empty_iterable_produces_no_output(self):
        buffer = io.StringIO()
        result = list(progress_bar([], file=buffer))
        self.assertEqual(result, [])
        self.assertEqual(buffer.getvalue(), "")

    def test_yields_items_in_order_and_writes_progress(self):
        buffer = io.StringIO()
        items = ["a", "b", "c"]
        result = list(progress_bar(items, file=buffer))
        self.assertEqual(result, items)
        output = buffer.getvalue()
        self.assertIn("3/3", output)
        self.assertTrue(output.endswith("\n"))

    def test_notify_receives_progress_text_for_start_and_each_item(self):
        buffer = io.StringIO()
        received = []
        list(progress_bar(["x", "y"], file=buffer, notify=received.append))
        # 開始時の0件表示 + 要素2件分で3回。
        self.assertEqual(len(received), 3)
        self.assertTrue(all(isinstance(text, str) for text in received))
        self.assertIn("0/2", received[0])
        self.assertIn("2/2", received[-1])

    def test_prefix_is_included_in_output(self):
        buffer = io.StringIO()
        list(progress_bar(["x"], prefix="hlibTest: ", file=buffer))
        self.assertIn("hlibTest: ", buffer.getvalue())

    def test_without_notify_does_not_raise(self):
        buffer = io.StringIO()
        result = list(progress_bar(["a", "b"], file=buffer))
        self.assertEqual(result, ["a", "b"])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

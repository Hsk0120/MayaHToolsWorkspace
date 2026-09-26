"""hlib.utils.progress の progress_bar を検証するMaya内テスト。"""

import contextlib
import io
import sys
import unittest

import hlib
hlib.reload()
import hlib.utils
from hlib.utils.progress import progress_bar


def _frames(output):
    """出力全体を行頭復帰で区切り、描画ごとの文字列の一覧にする。"""
    return [frame for frame in output.split("\r") if frame]


class _WriteOnlyStream(object):
    """flush を持たない最小の出力先。"""

    def __init__(self):
        self.parts = []

    def write(self, text):
        self.parts.append(text)


class _BrokenStream(object):
    """条件に合う書き込みで、呼び出し回数入りの OSError を送出する出力先。

    Args:
        should_fail (Callable[[str], bool]): 書き込む文字列を受け取り、
            失敗させるなら True を返す関数。
    """

    def __init__(self, should_fail):
        self.should_fail = should_fail
        self.parts = []
        self.failures = 0

    def write(self, text):
        if self.should_fail(text):
            self.failures += 1
            raise OSError(f"write failure #{self.failures}")
        self.parts.append(text)


class ProgressBarOutputTest(unittest.TestCase):
    """件数が分かる入力に対する描画内容を検証する。"""

    def test_exact_output_for_known_length(self):
        buffer = io.StringIO()
        result = list(progress_bar(["a", "b", "c", "d"], width=8, stream=buffer))
        self.assertEqual(result, ["a", "b", "c", "d"])
        self.assertEqual(
            buffer.getvalue(),
            "\r|--------|   0% 0/4"
            "\r|==------|  25% 1/4"
            "\r|====----|  50% 2/4"
            "\r|======--|  75% 3/4"
            "\r|========| 100% 4/4"
            "\n",
        )

    def test_percent_uses_integer_floor_without_float_error(self):
        # 29/100 を浮動小数点で計算すると 28.99... になり得るため、整数演算で 29 になることを確認する。
        buffer = io.StringIO()
        items = list(range(100))
        received = []
        list(progress_bar(items, width=10, stream=buffer, notify=received.append))
        self.assertTrue(received[29].endswith(" 29% 29/100"))
        self.assertIn("|==--------|", received[29])
        self.assertTrue(received[-1].endswith("100% 100/100"))

    def test_items_are_returned_unchanged(self):
        marker = object()
        items = [marker, None, 0, ""]
        result = list(progress_bar(items, stream=io.StringIO()))
        self.assertEqual(len(result), 4)
        self.assertIs(result[0], marker)
        self.assertEqual(result[1:], [None, 0, ""])

    def test_label_is_trimmed_and_separated_by_one_space(self):
        buffer = io.StringIO()
        list(progress_bar(["x"], label="hlibTest:   ", width=2, stream=buffer))
        self.assertEqual(_frames(buffer.getvalue())[-1], "hlibTest: |==| 100% 1/1\n")

    def test_blank_label_is_omitted(self):
        buffer = io.StringIO()
        list(progress_bar(["x"], label="  ", width=2, stream=buffer))
        self.assertTrue(_frames(buffer.getvalue())[0].startswith("|--|"))

    def test_bar_width_is_constant(self):
        received = []
        list(progress_bar(range(7), width=5, stream=io.StringIO(), notify=received.append))
        for text in received:
            bar = text.split("|")[1]
            self.assertEqual(len(bar), 5)

    def test_more_items_than_total_keeps_bar_full(self):
        received = []
        list(progress_bar(["a", "b", "c"], total=2, width=4, stream=io.StringIO(), notify=received.append))
        self.assertEqual(received[-1], "|====| 100% 3/2")


class ProgressBarUnknownLengthTest(unittest.TestCase):
    """len() を持たない入力と total 指定を検証する。"""

    def test_generator_without_total_shows_count_only(self):
        buffer = io.StringIO()
        generator = (value * 2 for value in range(3))
        result = list(progress_bar(generator, label="scan", stream=buffer))
        self.assertEqual(result, [0, 2, 4])
        self.assertEqual(
            _frames(buffer.getvalue()),
            ["scan 0/?", "scan 1/?", "scan 2/?", "scan 3/?\n"],
        )
        self.assertNotIn("%", buffer.getvalue())

    def test_generator_with_explicit_total_shows_bar(self):
        received = []
        generator = iter(["a", "b"])
        list(progress_bar(generator, total=2, width=2, stream=io.StringIO(), notify=received.append))
        self.assertEqual(received, ["|--|   0% 0/2", "|=-|  50% 1/2", "|==| 100% 2/2"])

    def test_empty_generator_produces_no_output(self):
        buffer = io.StringIO()
        received = []
        result = list(progress_bar(iter([]), stream=buffer, notify=received.append))
        self.assertEqual(result, [])
        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(received, [])


class ProgressBarLifecycleTest(unittest.TestCase):
    """空入力、notify、途中終了の扱いを検証する。"""

    def test_empty_sequence_produces_no_output(self):
        buffer = io.StringIO()
        received = []
        result = list(progress_bar([], stream=buffer, notify=received.append))
        self.assertEqual(result, [])
        self.assertEqual(buffer.getvalue(), "")
        self.assertEqual(received, [])

    def test_notify_receives_each_drawn_line_without_control_characters(self):
        buffer = io.StringIO()
        received = []
        list(progress_bar(["x", "y"], width=4, stream=buffer, notify=received.append))
        # 最初の要素を取り出した時点の0件表示と、各要素の処理後で計3回。
        self.assertEqual(received, ["|----|   0% 0/2", "|==--|  50% 1/2", "|====| 100% 2/2"])
        for text in received:
            self.assertNotIn("\r", text)
            self.assertNotIn("\n", text)
        self.assertEqual(_frames(buffer.getvalue())[:-1], received[:-1])

    def test_notify_return_value_is_ignored(self):
        result = list(progress_bar(["a"], stream=io.StringIO(), notify=lambda text: "ignored"))
        self.assertEqual(result, ["a"])

    def test_progress_counts_only_finished_items(self):
        received = []
        iterator = progress_bar(["a", "b", "c"], width=3, stream=io.StringIO(), notify=received.append)
        self.assertEqual(next(iterator), "a")
        # 最初の要素を受け取った直後は、まだ1件も処理済みではない。
        self.assertEqual(received, ["|---|   0% 0/3"])
        self.assertEqual(next(iterator), "b")
        self.assertEqual(received[-1], "|=--|  33% 1/3")
        iterator.close()

    def test_break_closes_line_with_newline(self):
        buffer = io.StringIO()
        received = []
        iterator = progress_bar(["a", "b", "c", "d"], width=4, stream=buffer, notify=received.append)
        for item in iterator:
            if item == "b":
                break
        iterator.close()
        self.assertTrue(buffer.getvalue().endswith("\n"))
        self.assertEqual(buffer.getvalue().count("\n"), 1)
        self.assertEqual(received[-1], "|=---|  25% 1/4")

    def test_exception_in_loop_body_closes_line(self):
        buffer = io.StringIO()
        iterator = progress_bar(["a", "b"], stream=buffer)
        with self.assertRaises(RuntimeError):
            for _ in iterator:
                raise RuntimeError("stop")
        iterator.close()
        self.assertTrue(buffer.getvalue().endswith("\n"))

    def test_notify_error_on_first_draw_closes_line(self):
        # 最初の描画で notify が失敗しても、書き出し済みの行は改行で閉じてから例外を伝える。
        buffer = io.StringIO()

        def failing_notify(text):
            raise RuntimeError("notify failed")

        iterator = progress_bar(["a", "b"], width=2, stream=buffer, notify=failing_notify)
        with self.assertRaises(RuntimeError):
            next(iterator)
        self.assertEqual(buffer.getvalue(), "\r|--|   0% 0/2\n")

    def test_notify_error_on_later_draw_closes_line(self):
        buffer = io.StringIO()
        calls = []

        def notify_fails_on_second_call(text):
            calls.append(text)
            if len(calls) == 2:
                raise RuntimeError("notify failed")

        iterator = progress_bar(["a", "b"], width=2, stream=buffer, notify=notify_fails_on_second_call)
        self.assertEqual(next(iterator), "a")
        with self.assertRaises(RuntimeError):
            next(iterator)
        self.assertEqual(buffer.getvalue(), "\r|--|   0% 0/2\r|=-|  50% 1/2\n")
        self.assertEqual(buffer.getvalue().count("\n"), 1)


class ProgressBarStreamFailureTest(unittest.TestCase):
    """出力先への書き込みが失敗した場合に、先に起きた例外が伝わることを検証する。"""

    def test_first_write_failure_is_not_replaced_by_closing_newline(self):
        # 書き込みが毎回失敗する出力先。行を閉じる改行の失敗(2回目)で置き換わらないこと。
        stream = _BrokenStream(lambda text: True)
        iterator = progress_bar(["a", "b"], stream=stream)
        with self.assertRaises(OSError) as caught:
            next(iterator)
        self.assertEqual(str(caught.exception), "write failure #1")
        self.assertEqual(stream.failures, 2)

    def test_later_write_failure_is_not_replaced_by_closing_newline(self):
        stream = _BrokenStream(lambda text: "1/2" in text or text == "\n")
        iterator = progress_bar(["a", "b"], width=2, stream=stream)
        self.assertEqual(next(iterator), "a")
        with self.assertRaises(OSError) as caught:
            next(iterator)
        self.assertEqual(str(caught.exception), "write failure #1")
        self.assertEqual(stream.parts, ["\r|--|   0% 0/2"])

    def test_source_error_wins_over_closing_newline_failure(self):
        # 反復対象そのものが途中で失敗した場合も、その例外が伝わること。
        def source():
            yield "a"
            raise ValueError("source failed")

        stream = _BrokenStream(lambda text: text == "\n")
        iterator = progress_bar(source(), stream=stream)
        self.assertEqual(next(iterator), "a")
        with self.assertRaises(ValueError) as caught:
            next(iterator)
        self.assertEqual(str(caught.exception), "source failed")
        self.assertEqual(stream.failures, 1)
        self.assertEqual(stream.parts, ["\r0/?", "\r1/?"])

    def test_closing_newline_failure_on_early_close_is_not_raised(self):
        # break 後の close では、改行の失敗を送出しない(GeneratorExit を優先する)。
        stream = _BrokenStream(lambda text: text == "\n")
        iterator = progress_bar(["a", "b"], stream=stream)
        self.assertEqual(next(iterator), "a")
        iterator.close()
        self.assertEqual(stream.failures, 1)

    def test_closing_newline_failure_after_completion_is_raised(self):
        # 反復が最後まで終わった後の改行の失敗は、捨てずに呼び出し側へ伝える。
        stream = _BrokenStream(lambda text: text == "\n")
        with self.assertRaises(OSError) as caught:
            list(progress_bar(["a"], width=2, stream=stream))
        self.assertEqual(str(caught.exception), "write failure #1")
        self.assertEqual(stream.parts, ["\r|--|   0% 0/1", "\r|==| 100% 1/1"])


class ProgressBarStreamTest(unittest.TestCase):
    """出力先の解決、flush を持たない出力先、パッケージからの公開を検証する。"""

    def test_default_stream_is_resolved_at_call_time(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            result = list(progress_bar(["a"], width=2))
        self.assertEqual(result, ["a"])
        self.assertEqual(buffer.getvalue(), "\r|--|   0% 0/1\r|==| 100% 1/1\n")

    def test_stream_without_flush_is_supported(self):
        stream = _WriteOnlyStream()
        list(progress_bar(["a"], width=2, stream=stream))
        self.assertEqual("".join(stream.parts), "\r|--|   0% 0/1\r|==| 100% 1/1\n")

    def test_exported_from_utils_package(self):
        self.assertIs(hlib.utils.progress_bar, progress_bar)


class ProgressBarValidationTest(unittest.TestCase):
    """引数の検証が反復前(呼び出し時)に行われることを検証する。"""

    def test_invalid_width_raises_immediately(self):
        with self.assertRaises(ValueError):
            progress_bar(["a"], width=0)
        with self.assertRaises(TypeError):
            progress_bar(["a"], width=2.5)
        with self.assertRaises(TypeError):
            progress_bar(["a"], width=True)

    def test_invalid_total_raises_immediately(self):
        with self.assertRaises(ValueError):
            progress_bar(["a"], total=-1)
        with self.assertRaises(TypeError):
            progress_bar(["a"], total="3")

    def test_non_str_label_raises_immediately(self):
        # 反復を始める前(呼び出し時)に型の誤りを検出する。
        with self.assertRaises(TypeError):
            progress_bar(["a"], label=None)
        with self.assertRaises(TypeError):
            progress_bar(["a"], label=3)

    def test_options_are_keyword_only(self):
        with self.assertRaises(TypeError):
            progress_bar(["a"], "label")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

"""保存済みの数学型記録と、UI設定照会の入口ごとの契約を検証する。"""

import json
import sys
import unittest
from unittest import mock

import maya.cmds as cmds
import hlib


class JsonRecordCompatibilityTest(unittest.TestCase):
    """クラス名から独立した保存タグと記録の中身を固定する。"""

    def test_math_records_match_existing_serialized_shape(self):
        """全7型が従来のタグ・キー・成分・回転順序で往復する。"""
        pairs = (
            ("Vector", hlib.maths.Vector(1, 2, 3)),
            ("Translation", hlib.maths.Translate(1, 2, 3)),
            ("Scale", hlib.maths.Scale(1, 2, 3)),
            ("Shear", hlib.maths.Shear(1, 2, 3)),
            ("EulerRotation", hlib.maths.EulerRotate(1, 2, 3, order="yxz")),
            ("Quaternion", hlib.maths.Quaternion(1, 2, 3, 4)),
            ("Matrix", hlib.maths.Matrix(list(range(16)))),
        )
        for tag, value in pairs:
            with self.subTest(tag=tag):
                fields = {"values": {"type": "list", "value": list(value)}}
                if tag == "EulerRotation":
                    fields["order"] = "yxz"
                expected = {"type": "math:" + tag,
                            "value": {"type": "dict", "value": fields}}
                document = json.loads(hlib.json.dumps(value))
                self.assertEqual(document["data"], expected)
                # 保存タグを明示した既存記録も、現在の正式クラスへ復元する。
                document["data"] = expected
                restored = hlib.json.loads(json.dumps(document))
                self.assertIs(type(restored), type(value))
                self.assertEqual(list(restored), list(value))


class EditorQueryContractsTest(unittest.TestCase):
    """実UIの所有や生成をせず、照会の順序・例外・値変換を確認する。"""

    def test_editor_and_snapshot_read_the_same_values_in_requested_order(self):
        """Viewport/Outlinerの保存側も、指定した順番で標準queryを実行する。"""
        from hlib.common.viewport import Viewport
        from hlib.common.outliner import Outliner
        from hlib.json.editors import _state

        for kind, cls in (("viewport", Viewport), ("outliner", Outliner)):
            with self.subTest(kind=kind):
                flags = tuple(reversed(cls._flags[:3]))
                values = dict(zip(flags, (True, False, "native-value")))
                editor = object.__new__(cls)
                editor._name = "fixtureEditor"

                def query(name, **kwargs):
                    """生存照会と、指定されたフラグの設定値だけを返す。"""
                    self.assertEqual(name, editor.name)
                    if kwargs == {"exists": True}:
                        return True
                    self.assertTrue(kwargs.pop("query"))
                    self.assertEqual(len(kwargs), 1)
                    return values[next(iter(kwargs))]

                with mock.patch.object(cmds, cls._command, side_effect=query) as command, \
                        mock.patch.object(cmds, "about", return_value=False):
                    self.assertEqual(editor.getSettings(*flags), values)
                    first = command.call_args_list
                    command.reset_mock()
                    self.assertEqual(_state(kind, editor.name, flags)["values"], values)
                    self.assertEqual(command.call_args_list, first)
                self.assertEqual(list(values), list(flags))

    def test_public_and_snapshot_validation_keep_distinct_errors(self):
        """未対応フラグ・削除済みUIの検査と例外型を各入口で保持する。"""
        from hlib.common.viewport import Viewport
        from hlib.json.editors import _state

        editor = object.__new__(Viewport)
        editor._name = "missingEditor"
        with mock.patch.object(cmds, "modelEditor", return_value=False) as command, \
                mock.patch.object(cmds, "about", return_value=False):
            with self.assertRaisesRegex(ValueError, "Unsupported display flags"):
                editor.getSettings("unknownFlag")
            with self.assertRaisesRegex(ValueError, "Unsupported editor flags"):
                _state("viewport", editor.name, ("unknownFlag",))
            command.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "Editor no longer exists"):
                editor.getSettings("grid")
            with self.assertRaisesRegex(ValueError, "GUI editor does not exist"):
                _state("viewport", editor.name, ("grid",))
            self.assertTrue(all(call[1] == {"exists": True} for call in command.call_args_list))

    def test_timeline_snapshot_retains_raw_values_and_query_order(self):
        """保存側はcmds値を保持し、public取得側だけfloatへ変換する。"""
        from hlib.common.timeSlider import TimeSlider
        from hlib.json.editors import _state

        values = {"animationStartTime": 1, "animationEndTime": 24, "minTime": 3, "maxTime": 18}
        queried = []

        def playback(**kwargs):
            """範囲の照会フラグを記録して整数値を返す。"""
            self.assertTrue(kwargs.pop("query"))
            flag = next(iter(kwargs))
            queried.append(flag)
            return values[flag]

        def current(**kwargs):
            """現在時刻の照会順を記録して整数値を返す。"""
            self.assertEqual(kwargs, {"query": True})
            queried.append("currentTime")
            return 6

        with mock.patch.object(cmds, "playbackOptions", side_effect=playback), \
                mock.patch.object(cmds, "currentTime", side_effect=current):
            state = _state("timeline", "timeline")["values"]
            self.assertEqual(state, dict(values, currentTime=6))
            self.assertTrue(all(type(value) is int for value in state.values()))
            self.assertEqual(queried, list(values) + ["currentTime"])
            queried.clear()
            slider = TimeSlider()
            self.assertEqual(slider.getCurrentTime(), 6.0)
            self.assertEqual(slider.getPlaybackRange(), (3.0, 18.0))
            self.assertEqual(slider.getAnimationRange(), (1.0, 24.0))
            self.assertEqual(queried, ["currentTime", "minTime", "maxTime", "animationStartTime", "animationEndTime"])

    def test_range_converts_first_result_before_second_query(self):
        """先頭の数値変換が失敗した場合、後続のMaya照会を行わない。"""
        from hlib.common.timeSlider import TimeSlider

        with mock.patch.object(cmds, "playbackOptions", return_value=object()) as command:
            with self.assertRaises(TypeError):
                TimeSlider().getPlaybackRange()
        command.assert_called_once_with(query=True, minTime=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

"""Maya GUI内でUIラッパーを検証する。シーンやパネルの作成/削除はしない。"""

import sys
import unittest

import maya.cmds as cmds

import hlib

hlib.reload()


class SceneUiTest(unittest.TestCase):
    """既存UIの設定を一時変更し、finallyで元に戻す。"""

    def setUp(self):
        self.view = hlib.viewport()
        self.outliner = hlib.outliner()
        self.panel = self.view.panel()

    def test_public_api_and_reload(self):
        for name, cls in (("timeSlider", hlib.scenes.TimeSlider),
                          ("viewport", hlib.scenes.Viewport),
                          ("outliner", hlib.scenes.Outliner)):
            self.assertIs(getattr(hlib, name), getattr(hlib.cmds, name))
        self.assertIsInstance(hlib.timeSlider(), hlib.scenes.TimeSlider)
        self.assertIsInstance(self.view, hlib.scenes.Viewport)
        self.assertIsInstance(self.outliner, hlib.scenes.Outliner)
        self.assertEqual(self.view.panel(), self.panel)

    def test_viewport_restore_after_exception_and_nesting(self):
        before = self.view.settings()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with self.view.temporary_settings(grid=not before["grid"]):
                outer = self.view.settings("grid")
                with self.view.temporary_settings(grid=before["grid"]):
                    self.assertEqual(self.view.settings("grid")["grid"], before["grid"])
                self.assertEqual(self.view.settings("grid"), outer)
                raise RuntimeError("test failure")
        self.assertEqual(self.view.settings(), before)
        with self.assertRaises(ValueError):
            self.view.set_settings(grid=False, notAFlag=True)
        self.assertEqual(self.view.settings(), before)
        camera = self.view.camera()
        self.view.set_camera(camera)
        self.assertEqual(self.view.camera(), camera)

    def test_main_pane_suspend_exception_nested_and_already_disabled(self):
        view = hlib.scenes.Viewport
        before = view.is_enabled()
        calls = []
        try:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with view.suspend():
                    calls.append(1)
                    self.assertFalse(view.is_enabled())
                    with view.suspend():
                        self.assertFalse(view.is_enabled())
                    self.assertFalse(view.is_enabled())
                    raise RuntimeError("test failure")
            self.assertEqual(calls, [1])
            self.assertEqual(view.is_enabled(), before)
            view.set_enabled(False)
            with view.suspend():
                pass
            self.assertFalse(view.is_enabled())
        finally:
            view.set_enabled(before)

    def test_outliner_settings(self):
        before = self.outliner.settings()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with self.outliner.temporary_settings(showShapes=not before["showShapes"]):
                self.assertNotEqual(self.outliner.settings("showShapes")["showShapes"], before["showShapes"])
                raise RuntimeError("test failure")
        self.assertEqual(self.outliner.settings(), before)
        self.assertEqual(hlib.outliner(self.outliner.name()).name(), self.outliner.name())

    def test_timeline_validation_and_restore(self):
        slider = hlib.timeSlider()
        playback = slider.playback_range()
        animation = slider.animation_range()
        time = slider.current_time()
        try:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with slider.preserve_time():
                    slider.set_current_time(time + 0.5)
                    self.assertEqual(slider.current_time(), time + 0.5)
                    raise RuntimeError("test failure")
            self.assertEqual(slider.current_time(), time)
            slider.set_animation_range(-10, 50)
            slider.set_playback_range(1, 20)
            self.assertEqual(slider.playback_range(), (1, 20))
            self.assertEqual(slider.animation_range(), (-10, 50))
            for start, end in ((20, 1), (float("nan"), 20), (1, float("inf"))):
                with self.assertRaises(ValueError):
                    slider.set_playback_range(start, end)
            self.assertEqual(slider.playback_range(), (1, 20))
            self.assertTrue(cmds.timeControl(slider.name(), exists=True))
            selected = slider.selected_range()
            if cmds.timeControl(slider.name(), query=True, rangeVisible=True):
                self.assertEqual(selected, tuple(cmds.timeControl(slider.name(), query=True, rangeArray=True)))
            else:
                self.assertIsNone(selected)
        finally:
            slider.set_animation_range(*animation)
            slider.set_playback_range(*playback)
            slider.set_current_time(time)

    def test_time_slider_play_stop_and_is_playing(self):
        slider = hlib.timeSlider()
        self.assertFalse(slider.is_playing())
        try:
            slider.play(forward=True)
            self.assertTrue(slider.is_playing())
        finally:
            slider.stop()
        self.assertFalse(slider.is_playing())

    def test_outliner_expand_all(self):
        result = self.outliner.expand_all(True)
        self.assertIsNone(result)
        self.outliner.expand_all(False)

    def test_invalid_ui_names(self):
        with self.assertRaises(RuntimeError):
            hlib.viewport("__hlibMissingPanel__")
        with self.assertRaises(RuntimeError):
            hlib.outliner("__hlibMissingEditor__")
        with self.assertRaises(RuntimeError):
            hlib.timeSlider("__hlibMissingControl__").selected_range()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

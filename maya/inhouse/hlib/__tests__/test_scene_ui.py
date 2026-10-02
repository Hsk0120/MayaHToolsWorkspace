"""Maya GUI内でUIラッパーを検証する。シーンやパネルの作成/削除はしない。"""

import sys
import unittest

import maya.cmds as cmds

import hlib

hlib.reload()


class SceneUiTest(unittest.TestCase):
    """既存UIの設定を一時変更し、finallyで元に戻す。"""

    def setUp(self):
        self.view = hlib.getViewport()
        self.outliner = hlib.getOutliner()
        self.panel = self.view.panel

    def test_public_api_and_reload(self):
        for name, cls in (("getTimeSlider", hlib.ui.TimeSlider),
                          ("getViewport", hlib.ui.Viewport),
                          ("getOutliner", hlib.ui.Outliner)):
            self.assertIs(getattr(hlib, name), getattr(hlib.cmds, name))
        self.assertIsInstance(hlib.getTimeSlider(), hlib.ui.TimeSlider)
        self.assertIsInstance(self.view, hlib.ui.Viewport)
        self.assertIsInstance(self.outliner, hlib.ui.Outliner)
        self.assertEqual(self.view.panel, self.panel)

    def test_viewport_restore_after_exception_and_nesting(self):
        before = self.view.get_settings()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with self.view.temporary_settings(grid=not before["grid"]):
                outer = self.view.get_settings("grid")
                with self.view.temporary_settings(grid=before["grid"]):
                    self.assertEqual(self.view.get_settings("grid")["grid"], before["grid"])
                self.assertEqual(self.view.get_settings("grid"), outer)
                raise RuntimeError("test failure")
        self.assertEqual(self.view.get_settings(), before)
        with self.assertRaises(ValueError):
            self.view.set_settings(grid=False, notAFlag=True)
        self.assertEqual(self.view.get_settings(), before)
        camera = self.view.camera()
        self.view.set_camera(camera)
        self.assertEqual(self.view.camera(), camera)

    def test_main_pane_suspend_exception_nested_and_already_disabled(self):
        view = hlib.ui.Viewport
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

    def test_viewport_off_and_bake(self):
        from unittest.mock import patch
        from hlib.decorators import viewport_off
        view = hlib.ui.Viewport
        before = view.is_enabled()
        calls = []

        @viewport_off()
        def operation(fail=False):
            calls.append(1)
            self.assertFalse(view.is_enabled())
            with viewport_off():
                self.assertFalse(view.is_enabled())
            if fail:
                raise RuntimeError('viewport test failure')
            return 42

        try:
            self.assertEqual(operation(), 42)
            self.assertEqual(view.is_enabled(), before)
            with self.assertRaisesRegex(RuntimeError, 'viewport test failure'):
                operation(True)
            self.assertEqual(calls, [1, 1])
            self.assertEqual(view.is_enabled(), before)
            view.set_enabled(False)
            operation()
            self.assertFalse(view.is_enabled())
            view.set_enabled(before)
            def failed_bake(*args, **kwargs):
                self.assertFalse(view.is_enabled())
                raise RuntimeError('bake failure')
            with patch.object(cmds, 'bakeResults', side_effect=failed_bake) as bake:
                with self.assertRaisesRegex(RuntimeError, 'bake failure'):
                    hlib.bakeResults('unused')
                self.assertEqual(bake.call_count, 1)
            self.assertEqual(view.is_enabled(), before)
        finally:
            view.set_enabled(before)

    def test_outliner_settings(self):
        before = self.outliner.get_settings()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with self.outliner.temporary_settings(showShapes=not before["showShapes"]):
                self.assertNotEqual(self.outliner.get_settings("showShapes")["showShapes"], before["showShapes"])
                raise RuntimeError("test failure")
        self.assertEqual(self.outliner.get_settings(), before)
        self.assertEqual(hlib.getOutliner(self.outliner.name).name, self.outliner.name)

    def test_timeline_validation_and_restore(self):
        slider = hlib.getTimeSlider()
        playback = slider.get_playback_range()
        animation = slider.get_animation_range()
        time = slider.get_current_time()
        try:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with slider.preserve_time():
                    slider.set_current_time(time + 0.5)
                    self.assertEqual(slider.get_current_time(), time + 0.5)
                    raise RuntimeError("test failure")
            self.assertEqual(slider.get_current_time(), time)
            slider.set_animation_range(-10, 50)
            slider.set_playback_range(1, 20)
            self.assertEqual(slider.get_playback_range(), (1, 20))
            self.assertEqual(slider.get_animation_range(), (-10, 50))
            for start, end in ((20, 1), (float("nan"), 20), (1, float("inf"))):
                with self.assertRaises(ValueError):
                    slider.set_playback_range(start, end)
            self.assertEqual(slider.get_playback_range(), (1, 20))
            self.assertTrue(cmds.timeControl(slider.name(), exists=True))
            selected = slider.get_selected_range()
            if cmds.timeControl(slider.name(), query=True, rangeVisible=True):
                self.assertEqual(selected, tuple(cmds.timeControl(slider.name(), query=True, rangeArray=True)))
            else:
                self.assertIsNone(selected)
        finally:
            slider.set_animation_range(*animation)
            slider.set_playback_range(*playback)
            slider.set_current_time(time)

    def test_time_slider_play_stop_and_is_playing(self):
        slider = hlib.getTimeSlider()
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
            hlib.getViewport("__hlibMissingPanel__")
        with self.assertRaises(RuntimeError):
            hlib.getOutliner("__hlibMissingEditor__")
        with self.assertRaises(RuntimeError):
            hlib.getTimeSlider("__hlibMissingControl__").get_selected_range()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

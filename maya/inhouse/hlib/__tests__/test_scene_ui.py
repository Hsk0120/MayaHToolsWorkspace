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
        before = self.view.getSettings()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with self.view.temporarySettings(grid=not before["grid"]):
                outer = self.view.getSettings("grid")
                with self.view.temporarySettings(grid=before["grid"]):
                    self.assertEqual(self.view.getSettings("grid")["grid"], before["grid"])
                self.assertEqual(self.view.getSettings("grid"), outer)
                raise RuntimeError("test failure")
        self.assertEqual(self.view.getSettings(), before)
        with self.assertRaises(ValueError):
            self.view.setSettings(grid=False, notAFlag=True)
        self.assertEqual(self.view.getSettings(), before)
        camera = self.view.getCamera()
        self.view.setCamera(camera)
        self.assertEqual(self.view.getCamera(), camera)

    def test_main_pane_suspend_exception_nested_and_already_disabled(self):
        view = hlib.ui.Viewport
        before = view.isEnabled()
        calls = []
        try:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with view.suspend():
                    calls.append(1)
                    self.assertFalse(view.isEnabled())
                    with view.suspend():
                        self.assertFalse(view.isEnabled())
                    self.assertFalse(view.isEnabled())
                    raise RuntimeError("test failure")
            self.assertEqual(calls, [1])
            self.assertEqual(view.isEnabled(), before)
            view.setEnabled(False)
            with view.suspend():
                pass
            self.assertFalse(view.isEnabled())
        finally:
            view.setEnabled(before)

    def test_viewport_off_and_bake(self):
        from unittest.mock import patch
        from hlib.decorators import viewportOff
        view = hlib.ui.Viewport
        before = view.isEnabled()
        calls = []

        @viewportOff()
        def operation(fail=False):
            calls.append(1)
            self.assertFalse(view.isEnabled())
            with viewportOff():
                self.assertFalse(view.isEnabled())
            if fail:
                raise RuntimeError('viewport test failure')
            return 42

        try:
            self.assertEqual(operation(), 42)
            self.assertEqual(view.isEnabled(), before)
            with self.assertRaisesRegex(RuntimeError, 'viewport test failure'):
                operation(True)
            self.assertEqual(calls, [1, 1])
            self.assertEqual(view.isEnabled(), before)
            view.setEnabled(False)
            operation()
            self.assertFalse(view.isEnabled())
            view.setEnabled(before)
            def failed_bake(*args, **kwargs):
                self.assertFalse(view.isEnabled())
                raise RuntimeError('bake failure')
            with patch.object(cmds, 'bakeResults', side_effect=failed_bake) as bake:
                with self.assertRaisesRegex(RuntimeError, 'bake failure'):
                    hlib.bakeResults('unused')
                self.assertEqual(bake.call_count, 1)
            self.assertEqual(view.isEnabled(), before)
        finally:
            view.setEnabled(before)

    def test_outliner_settings(self):
        before = self.outliner.getSettings()
        with self.assertRaisesRegex(RuntimeError, "test failure"):
            with self.outliner.temporarySettings(showShapes=not before["showShapes"]):
                self.assertNotEqual(self.outliner.getSettings("showShapes")["showShapes"], before["showShapes"])
                raise RuntimeError("test failure")
        self.assertEqual(self.outliner.getSettings(), before)
        self.assertEqual(hlib.getOutliner(self.outliner.name).name, self.outliner.name)

    def test_timeline_validation_and_restore(self):
        slider = hlib.getTimeSlider()
        playback = slider.getPlaybackRange()
        animation = slider.getAnimationRange()
        time = slider.getCurrentTime()
        try:
            with self.assertRaisesRegex(RuntimeError, "test failure"):
                with slider.preserveTime():
                    slider.setCurrentTime(time + 0.5)
                    self.assertEqual(slider.getCurrentTime(), time + 0.5)
                    raise RuntimeError("test failure")
            self.assertEqual(slider.getCurrentTime(), time)
            slider.setAnimationRange(-10, 50)
            slider.setPlaybackRange(1, 20)
            self.assertEqual(slider.getPlaybackRange(), (1, 20))
            self.assertEqual(slider.getAnimationRange(), (-10, 50))
            for start, end in ((20, 1), (float("nan"), 20), (1, float("inf"))):
                with self.assertRaises(ValueError):
                    slider.setPlaybackRange(start, end)
            self.assertEqual(slider.getPlaybackRange(), (1, 20))
            self.assertTrue(cmds.timeControl(slider.getName(), exists=True))
            selected = slider.getSelectedRange()
            if cmds.timeControl(slider.getName(), query=True, rangeVisible=True):
                self.assertEqual(selected, tuple(cmds.timeControl(slider.getName(), query=True, rangeArray=True)))
            else:
                self.assertIsNone(selected)
        finally:
            slider.setAnimationRange(*animation)
            slider.setPlaybackRange(*playback)
            slider.setCurrentTime(time)

    def test_time_slider_play_stop_and_is_playing(self):
        slider = hlib.getTimeSlider()
        self.assertFalse(slider.isPlaying())
        try:
            slider.play(forward=True)
            self.assertTrue(slider.isPlaying())
        finally:
            slider.stop()
        self.assertFalse(slider.isPlaying())

    def test_outliner_expand_all(self):
        result = self.outliner.expandAll(True)
        self.assertIsNone(result)
        self.outliner.expandAll(False)

    def test_invalid_ui_names(self):
        with self.assertRaises(RuntimeError):
            hlib.getViewport("__hlibMissingPanel__")
        with self.assertRaises(RuntimeError):
            hlib.getOutliner("__hlibMissingEditor__")
        with self.assertRaises(RuntimeError):
            hlib.getTimeSlider("__hlibMissingControl__").getSelectedRange()


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

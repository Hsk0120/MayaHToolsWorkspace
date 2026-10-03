"""Colorの同期・パレット再取得・表示色のUndoを検証する。"""
import sys
import unittest
import uuid
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()
from hlib.ui import Color


class ColorTest(unittest.TestCase):
    """保持値操作は無照会、ノード更新は明示呼出のみであることを確認する。"""

    def setUp(self):
        """検証用ノードを作る。"""
        self.node = hlib.createNode('transform', name='hlibColor_' + uuid.uuid4().hex)

    def tearDown(self):
        """検証用ノードを削除する。"""
        cmds.delete(self.node)

    def test_palette_and_synchronization(self):
        """実パレット全番号と、無照会のプロパティ更新を検証する。"""
        color = Color(index=17)
        palette = Color._DEFAULT_PALETTE if cmds.about(batch=True) else [tuple(cmds.colorIndex(i, query=True)) for i in range(32)]
        self.assertEqual(color.paletteSource, 'default' if cmds.about(batch=True) else 'maya')
        with patch.object(cmds, 'colorIndex', side_effect=AssertionError('Unexpected query')):
            for i in range(32):
                color.index = i
                self.assertEqual(color.rgb, palette[i])
                self.assertEqual(color.mode, 'index')
            rgb = (.123, .456, .789)
            color.rgb = rgb
            expected = min(range(1, 32), key=lambda i: sum((a-b)**2 for a,b in zip(rgb,palette[i])))
            self.assertEqual(color.index, expected)
            self.assertEqual(color.rgb, rgb)
            self.assertEqual(color.mode, 'rgb')
            copied = color.copy()
            copied.index = 6
            self.assertEqual(color.rgb, rgb)
            self.assertNotEqual(copied.mode, color.mode)

    def test_refresh_and_failure_atomicity(self):
        """再取得では指定値を維持し、失敗しても元の状態を残す。"""
        index, rgb = Color(index=17), Color(rgb=(.1, .2, .3))
        palette = [(0., 0., 0.)] * 32
        palette[17] = (.1, .2, .3)
        with patch.object(cmds, 'about', return_value=False), patch.object(cmds, 'colorIndex', side_effect=lambda i, **kw: palette[i]):
            self.assertIs(index.refreshPalette(), index)
            rgb.refreshPalette()
        self.assertEqual(index.rgb, (.1, .2, .3))
        self.assertEqual(rgb.index, 17)
        with patch.object(cmds, 'about', return_value=False), patch.object(cmds, 'colorIndex', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                index.refreshPalette()
        self.assertEqual(index.rgb, (.1, .2, .3))
        rgb.rgb = (0, 0, 0)
        self.assertEqual(rgb.index, 1)

    def test_batch_palette(self):
        """バッチではGUI照会せず、標準値で相互変換できる。"""
        with patch.object(cmds, 'about', return_value=True), patch.object(cmds, 'colorIndex', side_effect=AssertionError('GUI query')):
            color = Color(index=13)
            self.assertEqual(color.rgb, (1, 0, 0))
            self.assertEqual(color.paletteSource, 'default')
            color.rgb = (0, 0, 1)
            self.assertEqual(color.index, 6)
            self.assertEqual(color.copy().paletteSource, 'default')
            color.refreshPalette()

    def test_default_color_and_explicit_disabled(self):
        """既定色0と無効状態を区別し、RGB単独指定も維持する。"""
        default = Color()
        self.assertEqual(default, Color(index=0))
        self.assertEqual(default.mode, 'index')
        self.assertEqual(default.index, 0)
        self.assertEqual(default.rgb, default._palette[0])
        self.assertEqual(Color(index=None, rgb=None), default)
        self.assertEqual(Color(rgb=(1, 0, 0)).mode, 'rgb')
        disabled = Color.disabled()
        self.assertNotEqual(default, disabled)
        self.assertIsNone(disabled.index)
        self.assertIsNone(disabled.rgb)
        self.assertEqual(Color.coerce(None), disabled)
        self.assertEqual([Color.coerce(value).index for value in [default, None]], [0, None])
        self.node.setOverrideColor(default)
        self.assertEqual(self.node.getOverrideColor(), default)
        self.node.setOverrideColor(None)
        self.assertEqual(self.node.getOverrideColor(), disabled)

    def test_validation_and_disabled(self):
        """不正値は既存の同期状態を壊さない。"""
        color = Color(index=6)
        before = color.copy()
        for value in (-1, 32, True, 1.5, None):
            with self.assertRaises(ValueError):
                color.index = value
            self.assertEqual(color, before)
        for value in ((1, 2), (2, 0, 0), (float('nan'), 0, 0), '123', None):
            with self.assertRaises(ValueError):
                color.rgb = value
            self.assertEqual(color, before)
        with self.assertRaises(ValueError):
            Color(index=6, rgb=(0, 0, 0))
        with self.assertRaises(TypeError):
            hash(color)
        disabled = Color.disabled()
        self.assertEqual(disabled.mode, 'disabled')
        self.assertIsNone(disabled.index)
        self.assertIsNone(disabled.rgb)
        disabled.rgb = (.1, .2, .3)
        self.assertEqual(disabled.mode, 'rgb')

    def test_node_modes_roundtrip_and_undo(self):
        """指定形式を保って適用し、Undo/Redoと取得値の再設定を確認する。"""
        n = self.node
        self.assertEqual(n.getOverrideColor().mode, 'disabled')
        color = Color(index=17)
        n.setOverrideColor(color)
        self.assertEqual(n.getOverrideColor(), color)
        cmds.undo()
        self.assertEqual(n.getOverrideColor().mode, 'disabled')
        cmds.redo()
        color.rgb = (.123, .456, .789)
        self.assertEqual(n.getOverrideColor().mode, 'index')
        n.setOverrideColor(color)
        self.assertEqual(n.getOverrideColor().mode, 'rgb')
        for a, b in zip(n.getOverrideColor().rgb, color.rgb):
            self.assertAlmostEqual(a, b, places=6)
        n.setOverrideColor(n.getOverrideColor())
        n.setOutlinerColor(Color(index=6))
        self.assertEqual(n.getOutlinerColor().mode, 'rgb')
        for a, b in zip(n.getOutlinerColor().rgb, Color(index=6).rgb):
            self.assertAlmostEqual(a, b, places=6)
        n.setOverrideColor(Color.disabled())
        self.assertEqual(n.getOverrideColor().mode, 'disabled')
        n.setOutlinerColor(None)
        self.assertEqual(n.getOutlinerColor().mode, 'disabled')

    def test_fast_and_prevalidation(self):
        """fast経路と、後続フラグのロック時に色を先に変更しないことを確認する。"""
        for fast in (False, True):
            n = self.node
            n.setOverrideColor(6, fast=fast)
            self.assertEqual(n.getOverrideColor().index, 6)
            n.plug('overrideRGBColors').setFlags(locked=True)
            try:
                with self.assertRaises(RuntimeError):
                    n.setOverrideColor((1, .5, 0), fast=fast)
                self.assertEqual(n.getOverrideColor().index, 6)
            finally:
                n.plug('overrideRGBColors').setFlags(locked=False)
            n.setOutlinerColor(17, fast=fast)
            self.assertEqual(n.getOutlinerColor().mode, 'rgb')

    def test_bulk_and_blend_colors_remain_numeric(self):
        """複数形もColorを返し、BlendColorsの計算値は表示色に制限しない。"""
        joint = hlib.createNode('joint', parent=self.node)
        joints = hlib.nodes.Joints([joint])
        joints.setOverrideColor(Color(index=17))
        self.assertEqual(joints.getOverrideColor()[0].index, 17)
        blend = hlib.createNode('blendColors')
        try:
            blend.setColor(1, (2, -1, 3))
            self.assertEqual(blend.getColor(1), (2, -1, 3))
            self.assertIsInstance(blend.colorPlug(1), hlib.plugs.Plug)
        finally:
            cmds.delete(blend)



if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])

"""Colorの同期・パレット再取得・表示色のUndoを検証する。"""
import sys
import unittest
import uuid
from unittest.mock import patch
import maya.cmds as cmds
import hlib

hlib.reload()
from hlib.general import Color, Colors


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
        self.assertEqual(color.palette_source, 'default' if cmds.about(batch=True) else 'maya')
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
            self.assertIs(index.refresh_palette(), index)
            rgb.refresh_palette()
        self.assertEqual(index.rgb, (.1, .2, .3))
        self.assertEqual(rgb.index, 17)
        with patch.object(cmds, 'about', return_value=False), patch.object(cmds, 'colorIndex', side_effect=RuntimeError('failed')):
            with self.assertRaises(RuntimeError):
                index.refresh_palette()
        self.assertEqual(index.rgb, (.1, .2, .3))
        rgb.rgb = (0, 0, 0)
        self.assertEqual(rgb.index, 1)

    def test_batch_palette(self):
        """バッチではGUI照会せず、標準値で相互変換できる。"""
        with patch.object(cmds, 'about', return_value=True), patch.object(cmds, 'colorIndex', side_effect=AssertionError('GUI query')):
            color = Color(index=13)
            self.assertEqual(color.rgb, (1, 0, 0))
            self.assertEqual(color.palette_source, 'default')
            color.rgb = (0, 0, 1)
            self.assertEqual(color.index, 6)
            self.assertEqual(color.copy().palette_source, 'default')
            color.refresh_palette()

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
        self.assertEqual(Colors([default, None]).index, [0, None])
        self.assertEqual(len(Colors()), 0)
        self.node.set_override_color(default)
        self.assertEqual(self.node.get_override_color(), default)
        self.node.set_override_color(None)
        self.assertEqual(self.node.get_override_color(), disabled)

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
        self.assertEqual(n.get_override_color().mode, 'disabled')
        color = Color(index=17)
        n.set_override_color(color)
        self.assertEqual(n.get_override_color(), color)
        cmds.undo()
        self.assertEqual(n.get_override_color().mode, 'disabled')
        cmds.redo()
        color.rgb = (.123, .456, .789)
        self.assertEqual(n.get_override_color().mode, 'index')
        n.set_override_color(color)
        self.assertEqual(n.get_override_color().mode, 'rgb')
        for a, b in zip(n.get_override_color().rgb, color.rgb):
            self.assertAlmostEqual(a, b, places=6)
        n.set_override_color(n.get_override_color())
        n.set_outliner_color(Color(index=6))
        self.assertEqual(n.get_outliner_color().mode, 'rgb')
        for a, b in zip(n.get_outliner_color().rgb, Color(index=6).rgb):
            self.assertAlmostEqual(a, b, places=6)
        n.set_override_color(Color.disabled())
        self.assertEqual(n.get_override_color().mode, 'disabled')
        n.set_outliner_color(None)
        self.assertEqual(n.get_outliner_color().mode, 'disabled')

    def test_fast_and_prevalidation(self):
        """fast経路と、後続フラグのロック時に色を先に変更しないことを確認する。"""
        for fast in (False, True):
            n = self.node
            n.set_override_color(6, fast=fast)
            self.assertEqual(n.get_override_color().index, 6)
            n.plug('overrideRGBColors').set_flags(locked=True)
            try:
                with self.assertRaises(RuntimeError):
                    n.set_override_color((1, .5, 0), fast=fast)
                self.assertEqual(n.get_override_color().index, 6)
            finally:
                n.plug('overrideRGBColors').set_flags(locked=False)
            n.set_outliner_color(17, fast=fast)
            self.assertEqual(n.get_outliner_color().mode, 'rgb')

    def test_bulk_and_blend_colors_remain_numeric(self):
        """複数形もColorを返し、BlendColorsの計算値は表示色に制限しない。"""
        joint = hlib.createNode('joint', parent=self.node)
        joints = hlib.nodes.Joints([joint])
        joints.set_override_color(Color(index=17))
        self.assertEqual(joints.get_override_color()[0].index, 17)
        blend = hlib.createNode('blendColors')
        try:
            blend.set_color(1, (2, -1, 3))
            self.assertEqual(blend.get_color(1), (2, -1, 3))
            self.assertIsInstance(blend.color_plug(1), hlib.plugs.Plug)
        finally:
            cmds.delete(blend)



class ColorsTest(unittest.TestCase):
    """値コレクションの独立性と一括同期を検証する。"""

    def test_order_and_copy(self):
        """重複を保ち、入力・コピー・スライスは互いに独立する。"""
        original = Color(index=6)
        colors = Colors([original, 6, (1, 0, 0), None])
        self.assertEqual(len(colors), 4)
        self.assertEqual(colors.index, [6, 6, 13, None])
        self.assertEqual(colors.mode, ['index', 'index', 'rgb', 'disabled'])
        with patch.object(cmds, 'colorIndex', side_effect=AssertionError('Unexpected query')):
            copied, sliced = colors.copy(), colors[:2]
            colors[0].index = 17
            self.assertEqual(original.index, 6)
            self.assertEqual(copied[0].index, 6)
            self.assertEqual(sliced.index, [6, 6])
        self.assertIsInstance(sliced, Colors)
        self.assertEqual(list(colors)[0].index, 17)
        self.assertEqual(colors[-1].mode, 'disabled')
        self.assertEqual(Colors().rgb, [])

    def test_assignment_is_prevalidated(self):
        """一括同期と、不正な後続値でも先行要素を変更しないことを検証する。"""
        colors = Colors([6, 17])
        first = colors[0]
        colors.rgb = [(1, 0, 0), (0, 0, 1)]
        self.assertEqual(colors.index, [13, 6])
        self.assertIs(colors[0], first)
        colors.index = [17, 6]
        self.assertEqual(colors.rgb, [(1, 1, 0), (0, 0, 1)])
        for name, values in [('index', [13, 32]), ('rgb', [(0, 0, 0), (2, 0, 0)]), ('index', [1])]:
            before = colors.copy()
            with self.assertRaises(ValueError):
                setattr(colors, name, values)
            self.assertEqual(list(colors), list(before))

    def test_bulk_refresh(self):
        """既存の一括APIを通して、Undoなしでパレットを更新できる。"""
        colors = Colors([6, 17])
        with patch.object(cmds, 'about', return_value=True):
            result = colors.refresh_palette()
        self.assertEqual(result, list(colors))
        self.assertEqual(colors.palette_source, ['default', 'default'])


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0]])

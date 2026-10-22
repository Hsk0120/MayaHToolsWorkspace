"""単純アクセサーを削減した演算ノードの公開Plug操作を検証する。"""

import unittest

from maya import cmds
import mlib


class ConsolidatedCalculationTests(unittest.TestCase):
    """検証を持つ専用メソッドと標準Plugの組み合わせを確認する。"""

    def setUp(self):
        """テスト専用シーンを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        """作成したノードを破棄する。"""
        cmds.file(new=True, force=True)

    def test_add_and_multiply_use_standard_output_plugs(self):
        """専用入力の検証を残し、結果と接続は標準Plugで扱う。"""
        add = mlib.createNode("addDoubleLinear")
        self.assertIs(add.setInput(1, 2), add)
        add.setInput(2, 3)
        self.assertAlmostEqual(add.getPlug("output").get(), 5)
        multiply = mlib.createNode("multiplyDivide")
        multiply.setOperation("multiply").setInput(1, (2, 3, 4)).setInput(2, (3, 4, 5))
        self.assertEqual(tuple(multiply.getPlug("output").get()), (6, 12, 20))
        with self.assertRaises(ValueError):
            add.setInput(1, float("nan"))
        self.assertNotIn("getOutputPlug", type(add).__dict__)
        self.assertNotIn("getInput", type(add).__dict__)
        self.assertNotIn("getResult", type(add).__dict__)

    def test_fixed_inputs_keep_validation_and_undo(self):
        """固定入力取得の削減後も検証・複合範囲・Undoを保つ。"""
        clamp = mlib.createNode("clamp")
        clamp.setRange((0, 0, 0), (1, 2, 3))
        clamp.setInput((2, -1, 4))
        self.assertEqual(tuple(clamp.getResult()), (1, 0, 3))
        self.assertEqual(tuple(clamp.getPlug("input").get()), (2, -1, 4))
        cmds.undo()
        self.assertEqual(tuple(clamp.getPlug("input").get()), (0, 0, 0))
        with self.assertRaises(ValueError):
            clamp.setInput((1, 2))
        conversion = mlib.createNode("unitConversion")
        conversion.setInput(3).setFactor(2)
        self.assertAlmostEqual(conversion.getPlug("output").get(), 6)

    def test_enum_and_color_semantics_stay_available(self):
        """独自モード名と色の戻り型・範囲検査を維持する。"""
        condition = mlib.createNode("condition")
        condition.setOperation("less").setInput(1, 1).setInput(2, 2)
        condition.setTrueValue((0.2, 0.4, 0.6)).setFalseValue((1, 0, 0))
        self.assertEqual(condition.getOperation(), "less")
        for actual, expected in zip(condition.getResult(), (0.2, 0.4, 0.6)):
            self.assertAlmostEqual(actual, expected, places=6)
        blend = mlib.createNode("blendColors")
        blend.setColor(1, (1, 0, 0)).setColor(2, (0, 0, 1)).setBlender(0.25)
        self.assertEqual(blend.getResult(), (0.25, 0, 0.75))
        with self.assertRaises(ValueError):
            blend.setBlender(2)

    def test_sparse_inputs_keep_nonexistent_element_checks(self):
        """疎配列の番号規約と未存在要素拒否を維持する。"""
        node = mlib.createNode("plusMinusAverage")
        node.setInput(3, 2).setInput(8, 5)
        self.assertEqual(node.getInputIndices(), [3, 8])
        self.assertAlmostEqual(node.getPlug("output1D").get(), 7)
        self.assertAlmostEqual(node.getInputPlug(3).get(), 2)
        with self.assertRaises(IndexError):
            node.getInputPlug(4)
        self.assertEqual(node.getInputIndices(), [3, 8])


if __name__ == "__main__":
    unittest.main()

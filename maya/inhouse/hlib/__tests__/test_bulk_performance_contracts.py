"""一括呼出しと参照再利用の最適化で公開APIの意味を維持する。"""
import sys
import unittest
from unittest.mock import patch

import maya.cmds as cmds
import hlib

hlib.reload()
from hlib._core.collection import bulk_api
from hlib._core.flags import flag_aliases


class BulkPerformanceContractsTest(unittest.TestCase):
    """引数の事前検証・更新順・寿命の変化を実Mayaで確認する。"""

    def setUp(self):
        """検証専用のシーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        cmds.currentUnit(linear="cm", angle="deg")

    def test_bulk_override_preflight_and_replacement(self):
        """同じ引数でも異なる実関数は全件検証し、差替えにも追従する。"""
        calls = []

        class Item(hlib.nodes.Node):
            """テスト用の単数型。"""
            def __new__(cls):
                """転送検証用の参照を、Maya照会なしで作る。"""
                return object.__new__(cls)

            def __init__(self):
                """テスト用のためMayaノードを保持しない。"""

            def edit(self, value):
                """呼出順を記録する。"""
                calls.append(value)
                return self

        class Derived(Item):
            """異なる引数を要求する派生型。"""
            def edit(self, value, required):
                """両引数の存在を事前に検証させる。"""
                calls.append(required)
                return self

        @bulk_api(Item, undo=False, writes=("edit",))
        class Items(hlib.nodes.Nodes):
            """引数検証用のコレクション。"""
            def __init__(self, items):
                """参照を保持する。"""
                self._items = list(items)

        mixed = Items([Item(), Derived()])
        with self.assertRaises(TypeError):
            mixed.edit(1)
        self.assertEqual(calls, [])
        normal = Items([Item(), Item()])
        self.assertIs(normal.edit(1), normal)
        self.assertEqual(calls, [1, 1])
        with patch.object(Item, "edit", Derived.edit):
            with self.assertRaises(TypeError):
                normal.edit(2)
        self.assertEqual(calls, [1, 1])
        normal._items[1].edit = lambda value: calls.append(value + 10)
        normal.edit(2)
        self.assertEqual(calls[-2:], [2, 12])
        self.assertIs(Items([]).edit(1).__class__, Items)

        class CustomItems(Items):
            """公開一括入口を拡張する利用側コレクション。"""
            def callEach(self, method, arguments, keyword_arguments=None):
                """利用側のoverrideへ委譲されることを確認する。"""
                return "custom"

        self.assertEqual(CustomItems([Item()]).edit(1), "custom")

    def test_flag_shape_cache_preserves_values_and_errors(self):
        """形が同じでも値をキャッシュせず、競合を本体実行前に拒否する。"""
        calls = []

        @flag_aliases(v="value")
        def operation(value, *, enabled=True):
            """渡された値をそのまま記録する。"""
            calls.append(value)
            return value

        self.assertEqual(operation(v=1), 1)
        self.assertEqual(operation(v=2), 2)
        for invoke in (lambda: operation(3, v=4), lambda: operation(value=3, v=4),
                       lambda: operation(), lambda: operation(v=3, unknown=True)):
            with self.assertRaises(TypeError):
                invoke()
        self.assertEqual(calls, [1, 2])

    def test_plug_lookup_follows_alias_rename_delete_undo(self):
        """function set再利用後もノードや動的アトリビュートの変化に追従する。"""
        node = hlib.getNode(cmds.createNode("transform"))
        cmds.addAttr(node.fullName(), ln="amount", at="double")
        node.plug("amount").set(3)
        cmds.aliasAttr("aliasAmount", node.fullName() + ".amount")
        self.assertEqual(node.plug("aliasAmount").get(), 3)
        cmds.rename(node.fullName(), "renamed")
        cmds.deleteAttr(node.fullName() + ".amount")
        with self.assertRaises(AttributeError):
            node.plug("amount")
        cmds.undo()
        self.assertEqual(node.plug("amount").get(), 3)
        cmds.deleteAttr(node.fullName() + ".amount")
        cmds.addAttr(node.fullName(), ln="amount", at="long", dv=7)
        self.assertEqual(node.plug("amount").get(), 7)

    def test_fast_matrix_matches_normal_with_units_and_joint(self):
        """直接MPlug更新でも単位とJoint補正を通常経路に合わせる。"""
        for kind in ("transform", "joint"):
            node = hlib.getNode(cmds.createNode(kind))
            if kind == "joint":
                cmds.setAttr(node.fullName() + ".jointOrient", 11, 23, 7)
            for linear, angle in (("cm", "deg"), ("m", "rad")):
                cmds.currentUnit(linear=linear, angle=angle)
                target = hlib.maths.Matrix(translate=(2, 3, 4))
                node.setMatrix(target)
                expected = list(node.getMatrix())
                node.setTranslation((0, 0, 0), at=4)
                node.setMatrix(target, fast=True)
                for a, b in zip(node.getMatrix(), expected):
                    self.assertAlmostEqual(a, b, places=7)

    def test_weight_order_holes_duplicate_and_partial_failure(self):
        """検索表を再構築し、欠番・入力順・未指定値・失敗時の更新順を保つ。"""
        joints = [cmds.createNode("joint") for _ in range(4)]
        mesh = cmds.polyCube(ch=False)[0]
        skin = hlib.getNode(cmds.skinCluster(joints, mesh, tsb=True)[0])
        cmds.skinCluster(skin.fullName(), e=True, ri=joints[1])
        skin.setWeights([joints[3], joints[0]], [.2, .3])
        values = list(skin.getWeights([joints[0], joints[3]]))
        self.assertAlmostEqual(values[0], .3)
        self.assertAlmostEqual(values[1], .2)
        with self.assertRaises(ValueError):
            skin.setWeights([joints[0], cmds.ls(joints[0], long=True)[0]], [.1, .2])
        prefix = skin.fullName() + ".weightList[0].weights"
        before = cmds.getAttr(prefix + "[0]")
        protected = cmds.getAttr(prefix + "[2]")
        cmds.setAttr(prefix + "[2]", lock=True)
        with self.assertRaises(RuntimeError):
            skin.setWeights([joints[0], joints[2]], [.4, .6])
        self.assertAlmostEqual(cmds.getAttr(prefix + "[0]"), .4)
        self.assertEqual(cmds.getAttr(prefix + "[2]"), protected)
        cmds.undo()
        self.assertAlmostEqual(cmds.getAttr(prefix + "[0]"), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

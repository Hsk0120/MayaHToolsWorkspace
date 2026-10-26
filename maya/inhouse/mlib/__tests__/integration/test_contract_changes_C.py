"""約束の変更・不具合の修正(担当C)を実Mayaで検証する。

- ls・Selection の名前のまとめた解決: 結果の並びが cmds の結果(Selection は入力)の順のままで、
  重複・インスタンス・アトリビュート・コンポーネントの扱いが名前ごとの解決と同じこと。
  件数に対して処理時間がほぼ比例し、件数の2乗にならないこと。
- 削除済みの animCurve: fast を含む全メソッドが、Mayaを異常終了させずに通常経路と同じ RuntimeError を出すこと。
- ObjectSet.isMember: DG ノード・アトリビュート・コンポーネントで cmds.sets(isMember=) と同じ結果を返すこと。
"""

import sys
import time
import unittest
import uuid

import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common.selection import Selection, _resolve_names
from mlib.components import Vertex
from mlib.nodes import AnimCurve, ObjectSet
from mlib.plugs import Plug


class _NamespaceCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、終了時に削除する。"""

    def setUp(self):
        self.ns = "mlibContractC_" + uuid.uuid4().hex
        cmds.namespace(add=self.ns)

    def tearDown(self):
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def name(self, text):
        return self.ns + ":" + text


class LsBulkResolveTest(_NamespaceCase):
    """ls の名前をまとめて解決しても、並び順と結果が cmds・名前ごとの解決と同じになることを確かめる。"""

    def setUp(self):
        super().setUp()
        self.group_a = cmds.group(empty=True, name=self.name("grpA"))
        self.group_b = cmds.group(empty=True, name=self.name("grpB"))
        box = cmds.polyCube(name=self.name("box"))[0]
        box = cmds.parent(box, self.group_a)[0]
        cmds.parent(cmds.ls(box, long=True)[0], self.group_b, addObject=True)
        self.dg = [cmds.createNode("addDoubleLinear", name=self.name("adl%d" % i)) for i in range(3)]
        self.transforms = [cmds.createNode("transform", name=self.name("t%02d" % i)) for i in range(40)]

    def test_order_matches_cmds(self):
        """16件を超える名前でも、cmds.ls の返した順に同じ完全名の参照を返す。"""
        names = list(reversed(self.transforms)) + self.dg
        expected = cmds.ls(names, long=True)
        self.assertEqual([item.getFullName() for item in mlib.ls(names, long=True)], expected)
        pattern = self.ns + ":*"
        self.assertEqual([str(item) for item in mlib.ls(pattern)], cmds.ls(pattern))

    def test_instances_and_plugs(self):
        """インスタンスの全パスと、インスタンスのアトリビュートの所有パスを名前ごとの解決と同じにする。"""
        paths = cmds.ls(self.ns + ":box", allPaths=True, long=True)
        self.assertEqual(len(paths), 2)
        self.assertEqual([item.getFullName() for item in mlib.ls(self.ns + ":box", allPaths=True, long=True)], paths)
        shape = paths[1] + "|" + self.ns + ":boxShape"
        names = [shape + ".castsShadows", paths[0] + ".worldMatrix[1]", self.dg[0] + ".input1",
                 self.transforms[0] + ".tx"]
        result = mlib.ls(names)
        # 所有インスタンスは cmds.ls が返した名前で決まるため、その名前を1件ずつ解決した結果と比べる。
        returned = cmds.ls(names)
        self.assertEqual(len(result), len(returned))
        self.assertTrue(all(isinstance(item, Plug) for item in result))
        for item, name in zip(result, returned):
            expected = mlib.getPlug(name)
            self.assertEqual(item.getNode().getFullName(), expected.getNode().getFullName())
            self.assertEqual(str(item), str(expected))

    def test_components_keep_old_path(self):
        """コンポーネントはまとめた解決の対象外で、従来どおり単体へ展開する。"""
        box = cmds.ls(self.ns + ":box", allPaths=True, long=True)[0]
        result = mlib.ls(box + ".vtx[0:2]", self.transforms[0] + ".tx", box + ".vtx[5]", flatten=True)
        self.assertEqual(sum(isinstance(item, Vertex) for item in result), 4)
        self.assertEqual([isinstance(item, Plug) for item in result].count(True), 1)
        self.assertEqual([item.index for item in result if isinstance(item, Vertex)], [0, 1, 2, 5])

    def test_duplicates_are_not_merged(self):
        """同じ名前を重ねて渡しても、選択リストの統合で結果を減らさない。"""
        name = self.transforms[0]
        found = _resolve_names([name, name, self.transforms[1]])
        self.assertIsNotNone(found[0])
        self.assertIsNone(found[1])
        self.assertIsNotNone(found[2])
        self.assertEqual([item.getFullName() for item in Selection([name, self.transforms[1], name])],
                         cmds.ls([name, self.transforms[1]], long=True))

    def test_unresolved_names_keep_errors(self):
        """解決できない名前は、従来の名前ごとの経路の例外のまま。"""
        with self.assertRaises(RuntimeError):
            Selection([self.transforms[0], self.name("missing")])
        self.assertEqual(_resolve_names([self.name("missing"), self.ns + ":t*"]), [None, None])

    def test_selection_order(self):
        """Selection の保持順は入力の順で、ワイルドカードと混ぜても名前ごとの解決と同じ。"""
        names = [self.transforms[3], self.dg[1], self.ns + ":t0*", self.transforms[1]]
        expected = []
        for name in names:
            for full in cmds.ls(name, long=True):
                if full not in expected:
                    expected.append(full)
        self.assertEqual([item.getFullName() for item in Selection(names)], expected)

    def test_time_scales_linearly(self):
        """名前の数を16倍にしても、1件あたりの時間が大きく増えない(件数の2乗にならない)。"""
        many = [cmds.createNode("transform", name=self.name("bulk%d" % i)) for i in range(3200)]

        def per_item(names):
            best = None
            for _ in range(5):
                start = time.perf_counter()
                _resolve_names(names)
                elapsed = time.perf_counter() - start
                best = elapsed if best is None else min(best, elapsed)
            return best / len(names)

        small = per_item(many[:200])
        large = per_item(many)
        # 件数の2乗なら1件あたり約16倍になる。他の処理と同時に動くと揺れるため、上限は6倍に取る。
        self.assertLess(large, small * 6.0, (small, large))


class DeletedAnimCurveTest(_NamespaceCase):
    """削除済みの animCurve に触れても異常終了せず、通常経路と同じ RuntimeError になることを確かめる。"""

    def test_fast_methods_raise_like_normal(self):
        locator = cmds.spaceLocator(name=self.name("loc"))[0]
        cmds.setKeyframe(locator, attribute="tx", time=1, value=1)
        cmds.setKeyframe(locator, attribute="tx", time=5, value=3)
        curve = mlib.getNode(cmds.listConnections(locator + ".tx")[0])
        self.assertIsInstance(curve, AnimCurve)
        state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            cmds.delete(str(curve))
        finally:
            cmds.undoInfo(stateWithoutFlush=state)
        # 再現手順と同じく、Undo の記録から削除済みノードを破棄する。
        cmds.flushUndo()
        self.assertFalse(curve.isValid())
        with self.assertRaises(RuntimeError) as normal:
            curve.setKey(2, 2.0)
        calls = {
            "setKey fast": lambda: curve.setKey(2, 2.0, fast=True),
            "removeKey fast": lambda: curve.removeKey(0, fast=True),
            "setTangent fast": lambda: curve.setTangent(0, lock=True, fast=True),
            "setInfinity fast": lambda: curve.setInfinity(pre="linear", fast=True),
            "shiftKeys fast": lambda: curve.shiftKeys(1, 1, fast=True),
            "scaleKeys fast": lambda: curve.scaleKeys(2, 2, fast=True),
            "mirror fast": lambda: curve.mirror(fast=True),
            "removeKey": lambda: curve.removeKey(0),
            "isTimeInput": curve.isTimeInput,
            "getKeyCount": curve.getKeyCount,
            "getKeyInputs": curve.getKeyInputs,
            "getKeyValues": curve.getKeyValues,
            "evaluate": lambda: curve.evaluate(1.0),
            "getTangent": lambda: curve.getTangent(0),
        }
        for label, call in calls.items():
            with self.subTest(label):
                with self.assertRaises(RuntimeError) as caught:
                    call()
                self.assertEqual(str(caught.exception), str(normal.exception))


class ObjectSetIsMemberTest(_NamespaceCase):
    """ObjectSet.isMember が DG ノードやアトリビュートでも cmds.sets(isMember=) と一致することを確かめる。"""

    def test_matches_cmds(self):
        cube = cmds.polyCube(name=self.name("cube"))[0]
        dg_in = cmds.createNode("addDoubleLinear", name=self.name("adlIn"))
        dg_out = cmds.createNode("addDoubleLinear", name=self.name("adlOut"))
        locator = cmds.spaceLocator(name=self.name("loc"))[0]
        members = [dg_in, cube + ".vtx[0:2]", cube + ".tx", dg_out + ".input1", locator]
        object_set = cmds.sets(members, name=self.name("set"))
        wrapper = mlib.getNode(object_set)
        self.assertIsInstance(wrapper, ObjectSet)
        queries = [dg_in, dg_out, dg_out + ".input1", dg_in + ".input1", cube + ".vtx[0]",
                   cube + ".vtx[0:3]", cube + ".tx", cube + ".ty", cube, locator, locator + ".tx",
                   mlib.getNode(dg_in), mlib.getPlug(dg_out + ".input1")]
        for query in queries:
            with self.subTest(str(query)):
                self.assertEqual(wrapper.isMember(query), cmds.sets(str(query), isMember=object_set))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

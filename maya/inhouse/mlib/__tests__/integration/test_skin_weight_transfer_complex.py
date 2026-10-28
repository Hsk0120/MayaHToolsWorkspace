"""複雑な階層・複数skinClusterで、influence解除時の祖先へのウェイト移送を独立計算と比べる。

対象は ``SkinCluster.removeInfluence``・``Joint.removeInfluence`` (3.0.0 で fast 引数は外した)、
およびスキンされたjointの削除(``Joint.delete``・``mlib.delete``。Maya標準の再配分に任せる約束)。
複数jointの同時解除は、単数の ``SkinCluster.removeInfluence`` を深いjointから順に一つのUndoチャンクで呼ぶ。

期待値はmlibを使わず、OpenMayaで読んだ移送前のウェイトから次の規則で計算する。

- 解除は呼出しの処理順(同時解除は深いjointから、同じ深さは指定順)に1つずつ行う。
- 移送先は、親をjointだけ辿って最初に見つかる、その時点で同じskinClusterに登録済みのinfluence。
  親がjoint以外(transform等)になった時点で探索を終える。
- 移送先があれば ``移送先 += 移送元`` として移送元の列を除く。他の列は変えない。
- 移送先がなければMaya標準の再配分(``skinCluster -removeInfluence``。interactiveは残りを合計1へ
  比例配分し、none/postは残りをそのまま残す)。残りの合計が0になる頂点では、Mayaはjointとの距離で
  配り直すため、試験データはそのような頂点を作らない。

許容誤差は1e-9とする。ウェイトはdoubleで保存され、移送の加算順の違い(複数の移送が同じ移送先へ
足される場合や、Mayaが登録解除時に行う合計1への再正規化)による差は1e-15程度に留まる。
一方、移送先の取り違えや移送漏れは0.01以上の差になるため、この誤差で区別できる。
Undo・Redo後の比較も同じ誤差を使う。
"""

import random
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.api.OpenMayaAnim as oma2
import maya.cmds as cmds
import mlib
from mlib.decorator import undoChunk, undoTransaction

TOL = 1e-9


def _uuid(name):
    """ノード名からUUIDを取得する。"""
    return cmds.ls(name, uuid=True)[0]


def _long(name):
    """ノード名から完全パスを取得する。"""
    return cmds.ls(name, long=True)[0]


def _skin_fn(skin):
    """skinCluster名からMFnSkinClusterを作る。"""
    selection = om2.MSelectionList()
    selection.add(skin)
    return oma2.MFnSkinCluster(selection.getDependNode(0))


def _geometry(skin):
    """先頭出力geometryのパスと全頂点のcomponentを作る。"""
    fn = _skin_fn(skin)
    path = om2.MDagPath.getAPathTo(fn.getOutputGeometry()[0])
    count = om2.MFnMesh(path).numVertices
    component_fn = om2.MFnSingleIndexedComponent()
    component = component_fn.create(om2.MFn.kMeshVertComponent)
    component_fn.addElements(range(count))
    return fn, path, component, count


def _influence_ids(skin):
    """登録influenceのUUIDを物理順に取得する。"""
    return [om2.MFnDependencyNode(path.node()).uuid().asString()
            for path in _skin_fn(skin).influenceObjects()]


def _snapshot(skin):
    """全influenceの頂点ウェイトを、UUIDをキーとする辞書で取得する。"""
    fn, path, component, count = _geometry(skin)
    ids = _influence_ids(skin)
    values, width = fn.getWeights(path, component)
    return {key: [values[vertex * width + column] for vertex in range(count)]
            for column, key in enumerate(ids)}


def _write_rows(skin, rows):
    """頂点ごとの {UUID: 値} をOpenMayaで正規化せずに書く(準備用。Undo対象外)。"""
    fn, path, component, count = _geometry(skin)
    ids = _influence_ids(skin)
    flat = om2.MDoubleArray()
    for vertex in range(count):
        for key in ids:
            flat.append(rows[vertex].get(key, 0.0))
    fn.setWeights(path, component, om2.MIntArray(range(len(ids))), flat, False)


def _random_rows(skin, seed, per_vertex, must=(), total=(1.0, 1.0)):
    """頂点ごとに per_vertex 本のinfluenceへ正の値を配った行を作る。

    Args:
        skin (str): 対象skinCluster。
        seed (int): 乱数の種。結果を再現するため固定する。
        per_vertex (int): 各頂点で値を持つinfluence数。
        must (Iterable[str]): 高い確率で値を持たせるjoint(移送元・移送先)。
        total (tuple[float, float]): 各頂点の合計の範囲。
    """
    rng = random.Random(seed)
    ids = _influence_ids(skin)
    must = [_uuid(name) for name in must]
    rows = []
    for _vertex in range(_geometry(skin)[3]):
        chosen = [key for key in must if rng.random() < 0.75][:per_vertex]
        rest = [key for key in ids if key not in chosen]
        rng.shuffle(rest)
        chosen += rest[:max(0, min(per_vertex, len(ids)) - len(chosen))]
        raw = [rng.uniform(0.05, 1.0) for _ in chosen]
        scale = rng.uniform(*total) / sum(raw)
        rows.append({key: value * scale for key, value in zip(chosen, raw)})
    _write_rows(skin, rows)
    return rows


def _parent_joint(path):
    """直接の親がjointならその完全パス、そうでなければNone。"""
    parents = cmds.listRelatives(path, parent=True, fullPath=True)
    if not parents or cmds.nodeType(parents[0]) != "joint":
        return None
    return parents[0]


def _joint_depth(path):
    """jointの親だけを数えた深さ。"""
    depth, current = 0, _parent_joint(path)
    while current:
        depth += 1
        current = _parent_joint(current)
    return depth


def _deep_first(paths):
    """深いjointから、同じ深さは指定順に並べる(同時解除の処理順)。"""
    unique, seen = [], set()
    for path in paths:
        key = _uuid(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return sorted(unique, key=_joint_depth, reverse=True)


def _remove_deep_first(skin, paths):
    """単数のremoveInfluenceを深いjointから順に、一つのUndoチャンクで呼ぶ。"""
    wrapper = mlib.getNode(skin)
    with undoChunk("testRemoveInfluencesDeepFirst"):
        for path in _deep_first(paths):
            wrapper.removeInfluence(path)


def _expected_removal(before, order, normalize, transfer=True):
    """移送前のウェイトから、指定順に1本ずつ解除した後のウェイトを計算する。

    Args:
        before (dict[str, list[float]]): _snapshotの結果。
        order (list[str]): 解除するjointの完全パス。処理順。
        normalize (int): skinClusterのnormalizeWeights(0 none・1 interactive・2 post)。
        transfer (bool): 祖先へ移送するか。
    """
    rows = {key: list(values) for key, values in before.items()}
    for path in order:
        source = _uuid(path)
        if source not in rows:
            continue
        target = None
        ancestor = _parent_joint(path) if transfer else None
        while ancestor:
            if _uuid(ancestor) in rows:
                target = _uuid(ancestor)
                break
            ancestor = _parent_joint(ancestor)
        column = rows.pop(source)
        if target is not None:
            rows[target] = [t + s for t, s in zip(rows[target], column)]
            continue
        # Maya標準の再配分。移送元が0の頂点は変えない。
        others = list(rows)
        for vertex, value in enumerate(column):
            if value == 0:
                continue
            remaining = sum(rows[key][vertex] for key in others)
            if remaining <= 0:
                raise AssertionError("test data must not leave a zero-sum vertex: %d" % vertex)
            if normalize == 1:
                for key in others:
                    rows[key][vertex] /= remaining
    return rows


def _max_difference(actual, expected):
    """同じキーを持つ2つのsnapshotの最大差。キーが違えば無限大。"""
    if set(actual) != set(expected):
        return float("inf")
    return max((abs(a - b) for key in actual for a, b in zip(actual[key], expected[key])), default=0.0)


class _SkinTransferCase(unittest.TestCase):
    """シーンを作り直しながら、移送の結果を独立計算と比べる共通部分。"""

    BRANCH_INFLUENCES = ("root", "spine", "chest", "armL", "handL", "f1L", "f2L", "f3tipL",
                         "clavR", "armR", "handR", "f1R", "head")

    def setUp(self):
        """使い捨てのシーンでUndoを有効にする。"""
        self._undo_state = cmds.undoInfo(query=True, state=True)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        """シーンを破棄し、Undoの状態を戻す。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=self._undo_state)

    def joint(self, name, parent=None):
        """jointを作り、完全パスを返す。位置は名前ごとに変える。"""
        kwargs = {"name": name}
        if parent:
            kwargs["parent"] = parent
        node = cmds.createNode("joint", **kwargs)
        key = cmds.ls(node, uuid=True)[0]
        path = cmds.ls(key, long=True)[0]
        cmds.setAttr(path + ".translate", len(name) * 0.5, 1.0, 0.0)
        return path

    def mesh(self, divisions=6, name="skinMesh"):
        """履歴なしの平面メッシュを作り、transformの完全パスを返す。"""
        return _long(cmds.polyPlane(name=name, sx=divisions, sy=divisions, ch=False)[0])

    def bind(self, mesh, influences, normalize=1, max_influences=10):
        """指定順にinfluenceを登録してskinCluster名を返す。"""
        return cmds.skinCluster(influences, mesh, toSelectedBones=True, normalizeWeights=normalize,
                                maximumInfluences=max_influences, obeyMaxInfluences=False)[0]

    def chain(self):
        """途中にinfluenceでないjointを挟む5段の階層と、別のroot jointを作る。

        root(inf) - a(非inf) - b(inf) - c(非inf) - d(inf) - e(inf)、side(inf)
        """
        j = {}
        j["root"] = self.joint("root")
        j["a"] = self.joint("a", j["root"])
        j["b"] = self.joint("b", j["a"])
        j["c"] = self.joint("c", j["b"])
        j["d"] = self.joint("d", j["c"])
        j["e"] = self.joint("e", j["d"])
        j["side"] = self.joint("side")
        return j

    def branch(self):
        """枝分かれした階層を作る。clavL・neck・f3Lはinfluenceにしない。

        root - spine - chest - clavL - armL - handL - {f1L, f2L, f3L - f3tipL}
                             - clavR - armR - handR - f1R
                             - neck - head
        """
        j = {}
        j["root"] = self.joint("root")
        j["spine"] = self.joint("spine", j["root"])
        j["chest"] = self.joint("chest", j["spine"])
        for side in "LR":
            j["clav" + side] = self.joint("clav" + side, j["chest"])
            j["arm" + side] = self.joint("arm" + side, j["clav" + side])
            j["hand" + side] = self.joint("hand" + side, j["arm" + side])
            j["f1" + side] = self.joint("f1" + side, j["hand" + side])
        j["f2L"] = self.joint("f2L", j["handL"])
        j["f3L"] = self.joint("f3L", j["handL"])
        j["f3tipL"] = self.joint("f3tipL", j["f3L"])
        j["neck"] = self.joint("neck", j["chest"])
        j["head"] = self.joint("head", j["neck"])
        return j

    def assertWeights(self, actual, expected, message=""):
        """2つのsnapshotがinfluenceの集合・各値とも許容誤差内で一致する。"""
        self.assertEqual(set(actual), set(expected), message + ": influence set differs")
        self.assertLessEqual(_max_difference(actual, expected), TOL, message)

    def assertUndoRedo(self, skins, before, after, steps=1):
        """steps回(呼出しの回数。既定は一回)のUndoで全skinClusterが移送前に、Redoで移送後に戻る。"""
        for _step in range(steps):
            cmds.undo()
        for skin in skins:
            self.assertWeights(_snapshot(skin), before[skin], "undo " + skin)
        for _step in range(steps):
            cmds.redo()
        for skin in skins:
            self.assertWeights(_snapshot(skin), after[skin], "redo " + skin)


class ChainTransferTest(_SkinTransferCase):
    """途中にinfluenceでないjointを挟む階層での移送先と加算。"""

    def setup_chain(self, normalize=1, total=(1.0, 1.0), seed=1):
        """チェーンにバインドし、乱数ウェイトを入れる。"""
        j = self.chain()
        mesh = self.mesh()
        skin = self.bind(mesh, [j[k] for k in ("root", "b", "d", "e", "side")], normalize=normalize)
        _random_rows(skin, seed, per_vertex=4, must=(j["b"], j["d"], j["e"]), total=total)
        return j, skin

    def test_single_removal_skips_non_influence_joints(self):
        """e→d、d→b(cを飛ばす)、b→root(aを飛ばす)。"""
        cases = (("e", "d"), ("d", "b"), ("b", "root"))
        for source, target in cases:
            with self.subTest(source=source):
                cmds.file(new=True, force=True)
                j, skin = self.setup_chain(seed={"e": 101, "d": 102, "b": 103}[source])
                wrapper = mlib.getNode(skin)
                self.assertEqual(_long(mlib.nodes.Joint(j[source]).getTransferTarget(wrapper)), j[target])
                before = _snapshot(skin)
                expected = _expected_removal(before, [j[source]], 1)
                wrapper.removeInfluence(j[source])
                after = _snapshot(skin)
                self.assertWeights(after, expected, "removeInfluence " + source)
                # 移送先の列だけが増え、他の列は変わらない。
                for key in after:
                    if key != _uuid(j[target]):
                        self.assertEqual(after[key], before[key])
                self.assertTrue(cmds.objExists(j[source]))
                self.assertUndoRedo([skin], {skin: before}, {skin: after})

    def test_parent_and_child_removed_together(self):
        """b・d・eを同時に解除すると、全てaを飛ばしてrootへ集まる。入口・指定順によらない。"""
        entries = (
            ("SkinCluster.removeInfluence deep first", True,
             lambda j, skin: _remove_deep_first(skin, [j["d"], j["e"], j["b"]])),
            # Joint単位の呼出しは呼出しごとに一つのUndoになるため、Undo/Redoの1回での確認は省く。
            ("Joint.removeInfluence", False,
             lambda j, skin: [mlib.nodes.Joint(j[k]).removeInfluence(skin) for k in "bed"]),
        )
        for label, single_undo, entry in entries:
            with self.subTest(entry=label):
                cmds.file(new=True, force=True)
                j, skin = self.setup_chain(seed=7)
                before = _snapshot(skin)
                expected = _expected_removal(before, _deep_first([j["d"], j["e"], j["b"]]), 1)
                # 独立計算の確認: rootへ3本分が加算され、sideは変わらない。
                root, side = _uuid(j["root"]), _uuid(j["side"])
                for vertex in range(len(before[root])):
                    added = sum(before[_uuid(j[k])][vertex] for k in "bde")
                    self.assertAlmostEqual(expected[root][vertex], before[root][vertex] + added, delta=TOL)
                self.assertEqual(expected[side], before[side])
                entry(j, mlib.getNode(skin))
                after = _snapshot(skin)
                self.assertWeights(after, expected, label)
                for vertex in range(len(after[root])):
                    self.assertAlmostEqual(sum(row[vertex] for row in after.values()), 1.0, delta=TOL)
                if single_undo:
                    self.assertUndoRedo([skin], {skin: before}, {skin: after})

    def test_normalize_none_and_post_keep_raw_sums(self):
        """none/postで合計が1でない頂点も、移送で頂点ごとの合計が変わらない。"""
        for normalize in (0, 2):
            with self.subTest(normalize=normalize):
                cmds.file(new=True, force=True)
                j, skin = self.setup_chain(normalize=normalize, total=(0.4, 1.6), seed=11)
                before = _snapshot(skin)
                order = _deep_first([j["e"], j["d"]])
                expected = _expected_removal(before, order, normalize)
                wrapper = mlib.getNode(skin)
                for path in order:
                    wrapper.removeInfluence(path)
                after = _snapshot(skin)
                self.assertWeights(after, expected)
                for vertex in range(len(after[_uuid(j["root"])])):
                    self.assertAlmostEqual(sum(row[vertex] for row in after.values()),
                                           sum(row[vertex] for row in before.values()), delta=TOL)
                self.assertEqual(cmds.getAttr(skin + ".normalizeWeights"), normalize)

    def test_max_influences_not_exceeded(self):
        """各頂点3本の制限で、移送の合流後も非ゼロの本数が制限を超えず、設定も変えない。"""
        j = self.chain()
        mesh = self.mesh()
        skin = self.bind(mesh, [j[k] for k in ("root", "b", "d", "e", "side")], max_influences=3)
        cmds.setAttr(skin + ".maintainMaxInfluences", True)
        _random_rows(skin, 5, per_vertex=3, must=(j["d"], j["e"]))
        before = _snapshot(skin)
        expected = _expected_removal(before, [j["e"], j["d"]], 1)
        wrapper = mlib.getNode(skin)
        wrapper.removeInfluence(j["e"])
        wrapper.removeInfluence(j["d"])
        after = _snapshot(skin)
        self.assertWeights(after, expected)
        for vertex in range(len(after[_uuid(j["root"])])):
            self.assertLessEqual(sum(1 for row in after.values() if row[vertex] > 0), 3)
        self.assertEqual(cmds.getAttr(skin + ".maxInfluences"), 3)

    def test_undo_disabled_and_outer_chunks(self):
        """Undo無効時も同じ結果。外側のundoChunkは一回で戻り、undoTransactionは例外で巻き戻る。"""
        j, skin = self.setup_chain(seed=3)
        before = _snapshot(skin)
        expected = _expected_removal(before, _deep_first([j["e"], j["d"]]), 1)
        cmds.undoInfo(state=False)
        try:
            _remove_deep_first(skin, [j["e"], j["d"]])
        finally:
            cmds.undoInfo(state=True)
        self.assertWeights(_snapshot(skin), expected, "undo disabled")

        cmds.file(new=True, force=True)
        j, skin = self.setup_chain(seed=3)
        before = _snapshot(skin)
        with undoChunk("outerSkinTransfer"):
            mlib.getNode(skin).removeInfluence(j["e"])
            mlib.nodes.Joint(j["d"]).removeInfluence()
        after = _snapshot(skin)
        self.assertWeights(after, _expected_removal(before, [j["e"], j["d"]], 1), "outer chunk")
        self.assertUndoRedo([skin], {skin: before}, {skin: after})

        cmds.file(new=True, force=True)
        j, skin = self.setup_chain(seed=3)
        before = _snapshot(skin)
        with self.assertRaises(ZeroDivisionError):
            with undoTransaction("outerSkinTransaction"):
                mlib.getNode(skin).removeInfluence(j["e"])
                mlib.nodes.Joint(j["d"]).removeInfluence()
                1 / 0
        self.assertWeights(_snapshot(skin), before, "transaction rollback")
        self.assertTrue(mlib.getNode(skin).hasInfluence(j["e"]))

    def test_rejections_leave_weights_unchanged(self):
        """移送で使うskinClusterのロック・レイヤー・最後のinfluenceを、変更前に拒否する。"""
        for locked in ("d", "e", "side"):
            with self.subTest(locked=locked):
                cmds.file(new=True, force=True)
                j, skin = self.setup_chain(seed=13)
                cmds.setAttr(j[locked] + ".lockInfluenceWeights", True)
                before = _snapshot(skin)
                with self.assertRaises(RuntimeError):
                    mlib.getNode(skin).removeInfluence(j["e"])
                self.assertWeights(_snapshot(skin), before)
        with self.subTest(case="layer"):
            cmds.file(new=True, force=True)
            j, skin = self.setup_chain(seed=13)
            layer = cmds.createNode("network", name="ngSkinToolsData_test")
            cmds.addAttr(skin, longName="layerLink", attributeType="message")
            cmds.connectAttr(layer + ".message", skin + ".layerLink")
            before = _snapshot(skin)
            with self.assertRaises(RuntimeError):
                mlib.nodes.Joint(j["e"]).removeInfluence()
            self.assertWeights(_snapshot(skin), before)
        with self.subTest(case="last"):
            cmds.file(new=True, force=True)
            j = self.chain()
            skin = self.bind(self.mesh(), [j["e"]])
            with self.assertRaises(ValueError):
                mlib.nodes.Joint(j["e"]).removeInfluence()
            self.assertTrue(mlib.getNode(skin).hasInfluence(j["e"]))


class BranchTransferTest(_SkinTransferCase):
    """枝分かれ・兄弟・従兄弟の同時解除と、同じ移送先への複数加算。"""

    def setup_branch(self, seed=21, divisions=8):
        """枝分かれ階層へ、各頂点6本のウェイトでバインドする。"""
        j = self.branch()
        skin = self.bind(self.mesh(divisions), [j[k] for k in self.BRANCH_INFLUENCES])
        _random_rows(skin, seed, per_vertex=6,
                     must=[j[k] for k in ("handL", "f1L", "f2L", "f3tipL", "handR", "f1R", "head")])
        return j, skin

    def run_case(self, names, entry="deepFirst"):
        """指定jointを同時に解除し、独立計算と比べてUndo/Redoを確かめる。"""
        j, skin = self.setup_branch()
        paths = [j[name] for name in names]
        before = _snapshot(skin)
        if entry == "deepFirst":
            order = _deep_first(paths)
            _remove_deep_first(skin, paths)
        else:
            # Joint単位で指定順に処理する(浅いjointを先に解除しても結果は同じになる)。
            order = paths
            for path in paths:
                mlib.nodes.Joint(path).removeInfluence()
        expected = _expected_removal(before, order, 1)
        after = _snapshot(skin)
        self.assertWeights(after, expected, ",".join(names))
        for name in names:
            self.assertTrue(cmds.objExists(j[name]))
            self.assertFalse(mlib.getNode(skin).hasInfluence(j[name]))
        # Joint単位の呼出しは呼出しごとに一つのUndoになる。
        steps = 1 if entry == "deepFirst" else len(paths)
        self.assertUndoRedo([skin], {skin: before}, {skin: after}, steps)
        return j, before, after

    def test_siblings_add_to_same_target(self):
        """f1L・f2L・f3tipL(f3Lを飛ばす)が全てhandLへ加算される。"""
        for entry in ("deepFirst", "joint"):
            with self.subTest(entry=entry):
                cmds.file(new=True, force=True)
                j, before, after = self.run_case(["f1L", "f2L", "f3tipL"], entry)
                hand = _uuid(j["handL"])
                for vertex in range(len(before[hand])):
                    total = before[hand][vertex] + sum(before[_uuid(j[k])][vertex] for k in ("f1L", "f2L", "f3tipL"))
                    self.assertAlmostEqual(after[hand][vertex], total, delta=TOL)

    def test_cousins_and_parent_child_across_branches(self):
        """handL・f1Lは同時に消えるhandLを飛ばしてarmLへ、handR・f1RはarmRへ、headはneckを飛ばしてchestへ。"""
        names = ["f1L", "handR", "head", "handL", "f1R"]
        for entry in ("deepFirst", "joint"):
            with self.subTest(entry=entry):
                cmds.file(new=True, force=True)
                j, before, after = self.run_case(names, entry)
                for target, sources in (("armL", ("handL", "f1L")), ("armR", ("handR", "f1R")), ("chest", ("head",))):
                    key = _uuid(j[target])
                    for vertex in range(len(before[key])):
                        total = before[key][vertex] + sum(before[_uuid(j[k])][vertex] for k in sources)
                        self.assertAlmostEqual(after[key][vertex], total, delta=TOL)

    def test_many_influences_per_vertex(self):
        """各頂点が全13本の値を持つ場合も、合流の結果と合計1が保たれる。"""
        j = self.branch()
        skin = self.bind(self.mesh(5), [j[k] for k in self.BRANCH_INFLUENCES])
        _random_rows(skin, 31, per_vertex=len(self.BRANCH_INFLUENCES))
        before = _snapshot(skin)
        paths = [j[k] for k in ("f1L", "f2L", "f3tipL", "handL", "armL", "f1R", "head", "spine")]
        expected = _expected_removal(before, _deep_first(paths), 1)
        _remove_deep_first(skin, paths)
        after = _snapshot(skin)
        self.assertWeights(after, expected)
        self.assertEqual(len(after), len(self.BRANCH_INFLUENCES) - len(paths))
        for vertex in range(len(after[_uuid(j["root"])])):
            self.assertAlmostEqual(sum(row[vertex] for row in after.values()), 1.0, delta=TOL)


class MultipleSkinTest(_SkinTransferCase):
    """複数のメッシュ・skinClusterが同じjointを使う場合の範囲と移送先。"""

    def setup_skins(self):
        """root - mid - leaf と other を、登録の異なる3つのskinClusterへバインドする。

        skin1: root・mid・leaf・other(leaf→mid)
        skin2: root・leaf・other(midが無いのでleaf→root)
        skin3: mid・leaf(leaf→mid)
        """
        j = {}
        j["root"] = self.joint("root")
        j["mid"] = self.joint("mid", j["root"])
        j["leaf"] = self.joint("leaf", j["mid"])
        j["other"] = self.joint("other")
        skins = [
            self.bind(self.mesh(4, "m1"), [j["root"], j["mid"], j["leaf"], j["other"]]),
            self.bind(self.mesh(5, "m2"), [j["root"], j["leaf"], j["other"]]),
            self.bind(self.mesh(3, "m3"), [j["mid"], j["leaf"]]),
        ]
        for seed, skin in enumerate(skins):
            _random_rows(skin, 40 + seed, per_vertex=3, must=(j["leaf"],))
        return j, skins

    def test_joint_removal_uses_each_skins_own_target(self):
        """Joint.removeInfluence()は全skinClusterから外し、移送先はskinClusterごとに決まる。"""
        j, skins = self.setup_skins()
        before = {skin: _snapshot(skin) for skin in skins}
        expected = {skin: _expected_removal(before[skin], [j["leaf"]], 1) for skin in skins}
        self.assertIn(_uuid(j["root"]), before[skins[1]])
        mlib.nodes.Joint(j["leaf"]).removeInfluence()
        after = {skin: _snapshot(skin) for skin in skins}
        for skin in skins:
            self.assertWeights(after[skin], expected[skin], skin)
        # skin2ではrootへ、skin1・skin3ではmidへ加算された。
        leaf = _uuid(j["leaf"])
        for skin, target in ((skins[0], "mid"), (skins[1], "root"), (skins[2], "mid")):
            key = _uuid(j[target])
            self.assertAlmostEqual(sum(after[skin][key]), sum(before[skin][key]) + sum(before[skin][leaf]),
                                   delta=TOL * len(after[skin][key]))
        self.assertUndoRedo(skins, before, after)

    def test_only_specified_skins_change(self):
        """SkinCluster.removeInfluence・Joint.removeInfluence(skin3)は指定外のskinClusterを変えない。"""
        j, skins = self.setup_skins()
        before = {skin: _snapshot(skin) for skin in skins}
        mlib.getNode(skins[1]).removeInfluence(j["leaf"])
        self.assertWeights(_snapshot(skins[1]), _expected_removal(before[skins[1]], [j["leaf"]], 1))
        mlib.nodes.Joint(j["leaf"]).removeInfluence(skins[2])
        self.assertWeights(_snapshot(skins[2]), _expected_removal(before[skins[2]], [j["leaf"]], 1))
        self.assertWeights(_snapshot(skins[0]), before[skins[0]])
        self.assertTrue(mlib.getNode(skins[0]).hasInfluence(j["leaf"]))

    def test_lock_in_one_skin_rejects_all_before_changes(self):
        """後のskinClusterにロックがあれば、先のskinClusterも変更しない。"""
        for label, call in (
                ("Joint", lambda j, skins: mlib.nodes.Joint(j["leaf"]).removeInfluence()),):
            with self.subTest(entry=label):
                cmds.file(new=True, force=True)
                j, skins = self.setup_skins()
                # skin2にだけ登録したjointをロックし、先に処理されるskinClusterも変えないことを確かめる。
                extra = self.joint("extra", j["leaf"])
                cmds.skinCluster(skins[1], edit=True, addInfluence=extra, weight=0.0)
                cmds.setAttr(extra + ".lockInfluenceWeights", True)
                before = {skin: _snapshot(skin) for skin in skins}
                with self.assertRaises(RuntimeError):
                    call(j, skins)
                for skin in skins:
                    self.assertWeights(_snapshot(skin), before[skin], skin)
                    self.assertTrue(mlib.getNode(skin).hasInfluence(j["leaf"]))


class AncestorlessTransferTest(_SkinTransferCase):
    """移送先が無い場合(root・transformを挟む・移送なし)のMaya標準の再配分。"""

    def setup_scene(self, normalize):
        """grp(transform) - root - mid、root - xform(transform) - under、other を作る。"""
        grp = _long(cmds.createNode("transform", name="grp"))
        j = {"root": self.joint("root", grp)}
        j["mid"] = self.joint("mid", j["root"])
        xform = _long(cmds.createNode("transform", name="xform", parent=j["root"]))
        j["under"] = self.joint("under", xform)
        j["other"] = self.joint("other")
        skin = self.bind(self.mesh(), [j[k] for k in ("root", "mid", "under", "other")], normalize=normalize)
        total = (1.0, 1.0) if normalize == 1 else (0.5, 1.5)
        _random_rows(skin, 50 + normalize, per_vertex=3, must=(j["root"], j["mid"], j["under"]), total=total)
        return j, skin

    def native(self, skin, paths):
        """Maya標準の登録解除を指定順に行った結果を記録し、Undoで戻す。"""
        cmds.undoInfo(openChunk=True)
        try:
            for path in paths:
                cmds.skinCluster(skin, edit=True, removeInfluence=path)
        finally:
            cmds.undoInfo(closeChunk=True)
        result = _snapshot(skin)
        cmds.undo()
        return result

    def test_matches_maya_standard_redistribution(self):
        """rootの解除・transformを挟むunder・移送なしのmidは、Maya標準と独立計算の両方に一致する。"""
        for normalize in (1, 0, 2):
            for name, transfer in (("root", True), ("under", True), ("mid", False)):
                with self.subTest(normalize=normalize, joint=name, transfer=transfer):
                    cmds.file(new=True, force=True)
                    j, skin = self.setup_scene(normalize)
                    wrapper = mlib.getNode(skin)
                    if name != "mid":
                        self.assertIsNone(mlib.nodes.Joint(j[name]).getTransferTarget(wrapper))
                    before = _snapshot(skin)
                    native = self.native(skin, [j[name]])
                    self.assertWeights(_snapshot(skin), before, "native undo")
                    expected = _expected_removal(before, [j[name]], normalize, transfer)
                    self.assertWeights(native, expected, "model vs Maya")
                    wrapper.removeInfluence(j[name], transferToParent=transfer)
                    self.assertWeights(_snapshot(skin), expected, "mlib")

    def test_child_then_root_together(self):
        """root・midの同時解除は、midをrootへ加算した後にrootを標準の再配分で外す。"""
        for normalize in (1, 0):
            with self.subTest(normalize=normalize):
                cmds.file(new=True, force=True)
                j, skin = self.setup_scene(normalize)
                before = _snapshot(skin)
                order = _deep_first([j["root"], j["mid"]])
                self.assertEqual(order, [j["mid"], j["root"]])
                expected = _expected_removal(before, order, normalize)
                _remove_deep_first(skin, [j["root"], j["mid"]])
                after = _snapshot(skin)
                self.assertWeights(after, expected)
                self.assertUndoRedo([skin], {skin: before}, {skin: after})


class NamingTransferTest(_SkinTransferCase):
    """名前空間・同名joint(完全パスで区別)・インスタンスを含む場合の移送先。"""

    def test_same_short_names_and_namespaces(self):
        """同名のhandを完全パスで指定し、それぞれ自分のarmへ加算する。"""
        for entry in ("deepFirst", "removeInfluence"):
            with self.subTest(entry=entry):
                cmds.file(new=True, force=True)
                j = {}
                for group in ("grpA", "grpB"):
                    grp = _long(cmds.createNode("transform", name=group))
                    root = self.joint("root", grp)
                    arm = self.joint("arm", root)
                    j[group] = (root, arm, self.joint("hand", arm))
                for namespace in ("charA", "charB"):
                    cmds.namespace(add=namespace)
                    cmds.namespace(set=namespace)
                    root = self.joint("root")
                    arm = self.joint("arm", root)
                    j[namespace] = (root, arm, self.joint("hand", arm))
                    cmds.namespace(set=":")
                influences = [path for chain in j.values() for path in chain]
                self.assertEqual(len({path.rsplit("|", 1)[-1].split(":")[-1] for path in influences}), 3)
                skin = self.bind(self.mesh(), influences)
                _random_rows(skin, 60, per_vertex=5, must=[chain[2] for chain in j.values()])
                before = _snapshot(skin)
                hands = [j["grpA"][2], j["grpB"][2], j["charA"][2]]
                order = list(hands)
                if entry == "removeInfluence":
                    for path in hands:
                        mlib.getNode(skin).removeInfluence(path)
                else:
                    _remove_deep_first(skin, hands)
                    order = _deep_first(hands)
                # 名前空間付きの部分名でも指定できる。
                mlib.nodes.Joint("charB:arm").removeInfluence()
                order.append(j["charB"][1])
                after = _snapshot(skin)
                self.assertWeights(after, _expected_removal(before, order, 1))
                for key in ("grpA", "grpB", "charA"):
                    arm, hand = _uuid(j[key][1]), _uuid(j[key][2])
                    self.assertAlmostEqual(sum(after[arm]), sum(before[arm]) + sum(before[hand]),
                                           delta=TOL * len(after[arm]))
                self.assertIn(_uuid(j["grpB"][1]), after)
                self.assertIn(_uuid(j["charB"][2]), after)

    def test_instanced_hierarchy_path(self):
        """親のtransformをインスタンス化しても、jointノード単位で同じ移送先になる。"""
        grp = _long(cmds.createNode("transform", name="rig"))
        root = self.joint("root", grp)
        mid = self.joint("mid", root)
        leaf = self.joint("leaf", mid)
        skin = self.bind(self.mesh(), [root, mid, leaf])
        _random_rows(skin, 70, per_vertex=3)
        instance = _long(cmds.instance(grp, name="rigInstance")[0])
        instance_leaf = instance + "|root|mid|leaf"
        self.assertTrue(cmds.objExists(instance_leaf))
        self.assertEqual(_uuid(instance_leaf), _uuid(leaf))
        before = _snapshot(skin)
        expected = _expected_removal(before, [leaf], 1)
        self.assertEqual(_uuid(mlib.nodes.Joint(instance_leaf).getTransferTarget(mlib.getNode(skin))), _uuid(mid))
        mlib.getNode(skin).removeInfluence(instance_leaf)
        after = _snapshot(skin)
        self.assertWeights(after, expected)
        self.assertUndoRedo([skin], {skin: before}, {skin: after})


class LargeMeshTransferTest(_SkinTransferCase):
    """数千頂点で、連続した論理番号の範囲setAttrが多数に分かれる場合。"""

    def setup_large(self):
        """5041頂点のメッシュへ、子→親の順(論理番号が親=子+1)でバインドする。"""
        j = {"root": self.joint("root")}
        j["mid"] = self.joint("mid", j["root"])
        j["leaf"] = self.joint("leaf", j["mid"])
        j["x"] = self.joint("x")
        j["y"] = self.joint("y", j["x"])
        skin = self.bind(self.mesh(70), [j[k] for k in ("leaf", "mid", "root", "y", "x")])
        _random_rows(skin, 80, per_vertex=4, must=(j["leaf"], j["mid"], j["y"]))
        return j, skin

    def logical(self, skin, path):
        """influenceの論理番号。"""
        fn = _skin_fn(skin)
        for influence in fn.influenceObjects():
            if influence.fullPathName() == path:
                return fn.indexForInfluenceObject(influence)
        raise AssertionError(path)

    def test_large_mesh_transfer(self):
        """leaf→mid→rootとy→xを続けて解除し、Undo/Redoで全頂点が戻る。"""
        j, skin = self.setup_large()
        self.assertEqual(_geometry(skin)[3], 5041)
        # 移送元と移送先の論理番号が連続し、setWeightsの範囲指定の経路を通る。
        self.assertEqual(self.logical(skin, j["mid"]), self.logical(skin, j["leaf"]) + 1)
        self.assertEqual(self.logical(skin, j["x"]), self.logical(skin, j["y"]) + 1)
        wrapper = mlib.getNode(skin)
        states = [_snapshot(skin)]
        for name in ("leaf", "mid", "y"):
            wrapper.removeInfluence(j[name])
            expected = _expected_removal(states[-1], [j[name]], 1)
            states.append(_snapshot(skin))
            self.assertWeights(states[-1], expected, name)
        for state in reversed(states[:-1]):
            cmds.undo()
            self.assertWeights(_snapshot(skin), state, "undo")
        for state in states[1:]:
            cmds.redo()
            self.assertWeights(_snapshot(skin), state, "redo")

    def test_large_mesh_set_weights_with_gaps(self):
        """論理番号の穴と順序の入替えを含む全列のsetWeightsが、全頂点で指定値になる。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                cmds.file(new=True, force=True)
                j, skin = self.setup_large()
                cmds.skinCluster(skin, edit=True, removeInfluence=j["root"])
                names = [j[k] for k in ("y", "x", "leaf", "mid")]
                rng = random.Random(90)
                values = []
                for _vertex in range(5041):
                    raw = [rng.uniform(0.0, 1.0) for _ in names]
                    values.extend(value / sum(raw) for value in raw)
                mlib.getNode(skin).setWeights(names, values, fast=fast)
                after = _snapshot(skin)
                for column, name in enumerate(names):
                    actual = after[_uuid(name)]
                    self.assertLessEqual(max(abs(actual[v] - values[v * len(names) + column]) for v in range(5041)), TOL)


class SkinnedJointDeleteTest(_SkinTransferCase):
    """スキンされたjointの削除はMaya標準の削除と同じ結果になる(独自の移送はしない)。"""

    def test_delete_matches_native(self):
        """親子・兄弟・別の枝を同時に、複数skinClusterから削除しても標準の削除と一致する。"""
        entries = (
            ("Joint.delete", lambda nodes, fast: [node.delete(fast=fast) for node in nodes]),
            ("mlib.delete", lambda nodes, fast: mlib.delete(nodes, fast=fast)),
        )
        targets = ("f1L", "handL", "f2R", "head", "clavR")
        for label, entry in entries:
            for fast in (False, True):
                with self.subTest(entry=label, fast=fast):
                    cmds.file(new=True, force=True)
                    j = self.branch()
                    j["f2R"] = self.joint("f2R", j["handR"])
                    skins = [
                        self.bind(self.mesh(6, "body"), [j[k] for k in self.BRANCH_INFLUENCES] + [j["f2R"]]),
                        self.bind(self.mesh(4, "hands"), [j[k] for k in ("chest", "handL", "f1L", "handR", "f2R")]),
                    ]
                    for seed, skin in enumerate(skins):
                        _random_rows(skin, 100 + seed, per_vertex=4,
                                     must=[j[k] for k in ("handL", "f1L", "f2R", "head")])
                    before = {skin: _snapshot(skin) for skin in skins}
                    paths = [j[k] for k in targets]
                    cmds.undoInfo(openChunk=True)
                    try:
                        cmds.delete(paths)
                    finally:
                        cmds.undoInfo(closeChunk=True)
                    native = {skin: _snapshot(skin) for skin in skins}
                    cmds.undo()
                    for skin in skins:
                        self.assertWeights(_snapshot(skin), before[skin], "native undo")
                    nodes = [mlib.nodes.Joint(path) for path in paths]
                    entry(nodes, fast)
                    for skin in skins:
                        self.assertWeights(_snapshot(skin), native[skin], label)
                    self.assertFalse(any(cmds.objExists(path) for path in paths))
                    if not fast:
                        # Joint.deleteは呼出しごと、他は一回の呼出しで一つのUndoになる。
                        for _step in range(len(nodes) if label == "Joint.delete" else 1):
                            cmds.undo()
                        for skin in skins:
                            self.assertWeights(_snapshot(skin), before[skin], "undo")
                        self.assertTrue(all(cmds.objExists(path) for path in paths))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

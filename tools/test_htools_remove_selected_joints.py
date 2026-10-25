"""HTools「removeSelectedJoints」のウェイト移送を、使い捨てmayapyで独立計算と比べる。

``python``ではなく対象Mayaの ``mayapy`` で実行する(例: ``mayapy tools/test_htools_remove_selected_joints.py``)。
作業中のMaya GUIへは送らない(シーンを作り直すため)。GUIでは明示的に ``runTests()`` を呼ぶ。

期待値はツールを使わず、OpenMayaで読んだ削除前のウェイトから次の規則で計算する。

- 選んだjointは深い順(同じ深さは選択順)に1本ずつ処理する。
- 移送先は、親をjointだけ辿って最初に見つかる、その時点で同じskinClusterに登録済みのinfluence。
  親がjoint以外になった時点で探索を終える。
- 移送先があれば ``移送先 += 移送元`` として移送元の列を除き、他の列は変えない。
- 移送先がなければ ``cmds.delete`` の標準の削除に任せる。Mayaのjoint削除は登録解除
  (``skinCluster -removeInfluence``)と違って残りを再正規化せず、normalizeWeightsの設定によらず
  移送元の列を除くだけになる(interactiveでも頂点の合計が1未満のまま残る)。

許容誤差は1e-9とする。ウェイトはdoubleで保存され、複数の移送が同じ移送先へ足される順序や、
Mayaの登録解除時の再正規化による差は1e-15程度に留まり、移送先の取り違え(0.01以上)と区別できる。
"""

from pathlib import Path
import random
import sys
import unittest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse"))

TOL = 1e-9


def _cmds():
    """maya.cmdsを遅延importする(mayapy初期化後に使うため)。"""
    import maya.cmds as cmds
    return cmds


def _uuid(name):
    """ノード名からUUIDを取得する。"""
    return _cmds().ls(name, uuid=True)[0]


def _long(name):
    """ノード名から完全パスを取得する。"""
    return _cmds().ls(name, long=True)[0]


def _geometry(skin):
    """skinClusterの関数セット・先頭geometryのパス・全頂点component・頂点数。"""
    import maya.api.OpenMaya as om2
    import maya.api.OpenMayaAnim as oma2
    selection = om2.MSelectionList()
    selection.add(skin)
    fn = oma2.MFnSkinCluster(selection.getDependNode(0))
    path = om2.MDagPath.getAPathTo(fn.getOutputGeometry()[0])
    count = om2.MFnMesh(path).numVertices
    component_fn = om2.MFnSingleIndexedComponent()
    component = component_fn.create(om2.MFn.kMeshVertComponent)
    component_fn.addElements(range(count))
    return fn, path, component, count


def _ids(fn):
    """登録influenceのUUIDを物理順に取得する。"""
    import maya.api.OpenMaya as om2
    return [om2.MFnDependencyNode(path.node()).uuid().asString() for path in fn.influenceObjects()]


def _snapshot(skin):
    """全influenceの頂点ウェイトを {UUID: 頂点順の値} で取得する。"""
    fn, path, component, count = _geometry(skin)
    ids = _ids(fn)
    values, width = fn.getWeights(path, component)
    return {key: [values[v * width + c] for v in range(count)] for c, key in enumerate(ids)}


def _random_weights(skin, seed, per_vertex, must=(), total=(1.0, 1.0)):
    """頂点ごとに per_vertex 本へ正の値を配り、OpenMayaで正規化せずに書く(準備用)。"""
    import maya.api.OpenMaya as om2
    fn, path, component, count = _geometry(skin)
    ids = _ids(fn)
    must = [_uuid(name) for name in must]
    rng = random.Random(seed)
    flat = om2.MDoubleArray()
    for _vertex in range(count):
        chosen = [key for key in must if rng.random() < 0.75][:per_vertex]
        rest = [key for key in ids if key not in chosen]
        rng.shuffle(rest)
        chosen += rest[:max(0, min(per_vertex, len(ids)) - len(chosen))]
        raw = [rng.uniform(0.05, 1.0) for _ in chosen]
        scale = rng.uniform(*total) / sum(raw)
        row = dict(zip(chosen, (value * scale for value in raw)))
        for key in ids:
            flat.append(row.get(key, 0.0))
    fn.setWeights(path, component, om2.MIntArray(range(len(ids))), flat, False)


def _parent_joint(path):
    """直接の親がjointならその完全パス、そうでなければNone。"""
    cmds = _cmds()
    parents = cmds.listRelatives(path, parent=True, fullPath=True)
    if not parents or cmds.nodeType(parents[0]) != "joint":
        return None
    return parents[0]


def _deep_first(paths):
    """jointの親だけを数えた深さの深い順(同じ深さは指定順)。重複はノード単位で除く。"""
    def depth(path):
        count, current = 0, _parent_joint(path)
        while current:
            count += 1
            current = _parent_joint(current)
        return count
    unique, seen = [], set()
    for path in paths:
        if _uuid(path) not in seen:
            seen.add(_uuid(path))
            unique.append(path)
    return sorted(unique, key=depth, reverse=True)


def _expected(before, order):
    """削除前のウェイトから、指定順に1本ずつ処理した後のウェイトを計算する。"""
    rows = {key: list(values) for key, values in before.items()}
    for path in order:
        source = _uuid(path)
        if source not in rows:
            continue
        target, ancestor = None, _parent_joint(path)
        while ancestor:
            if _uuid(ancestor) in rows:
                target = _uuid(ancestor)
                break
            ancestor = _parent_joint(ancestor)
        column = rows.pop(source)
        if target is not None:
            rows[target] = [t + s for t, s in zip(rows[target], column)]
    return rows


class RemoveSelectedJointsTest(unittest.TestCase):
    """選んだjointのウェイトを祖先influenceへ移してから削除する処理を確かめる。"""

    def setUp(self):
        """使い捨てのシーンでUndoを有効にし、ツールの関数を読み込む。"""
        cmds = _cmds()
        self.cmds = cmds
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)
        from HTools.rigging import removeSelectedJoints
        self.tool = removeSelectedJoints

    def tearDown(self):
        """シーンを破棄し、Undoの状態を戻す。"""
        self.cmds.file(new=True, force=True)
        self.cmds.undoInfo(state=self.undo_state)

    # ---- シーン構築 -------------------------------------------------------

    def joint(self, name, parent=None):
        """jointを作り、完全パスを返す。"""
        kwargs = {"name": name}
        if parent:
            kwargs["parent"] = parent
        node = self.cmds.createNode("joint", **kwargs)
        path = self.cmds.ls(self.cmds.ls(node, uuid=True)[0], long=True)[0]
        self.cmds.setAttr(path + ".translate", len(name) * 0.5, 1.0, 0.0)
        return path

    def mesh(self, divisions=6, name="skinMesh"):
        """履歴なしの平面メッシュ。"""
        return _long(self.cmds.polyPlane(name=name, sx=divisions, sy=divisions, ch=False)[0])

    def bind(self, mesh, influences, normalize=1, max_influences=10):
        """指定順にinfluenceを登録してskinCluster名を返す。"""
        return self.cmds.skinCluster(influences, mesh, toSelectedBones=True, normalizeWeights=normalize,
                                     maximumInfluences=max_influences, obeyMaxInfluences=False)[0]

    def chain(self):
        """root(inf) - a - b(inf) - c - d(inf) - e(inf) と side(inf)。a・cはinfluenceにしない。"""
        j = {"root": self.joint("root")}
        for name, parent in (("a", "root"), ("b", "a"), ("c", "b"), ("d", "c"), ("e", "d")):
            j[name] = self.joint(name, j[parent])
        j["side"] = self.joint("side")
        return j

    def branch(self):
        """root - spine - chest から左右の腕・指と neck - head へ分かれる階層。"""
        j = {"root": self.joint("root")}
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

    BRANCH_INFLUENCES = ("root", "spine", "chest", "armL", "handL", "f1L", "f2L", "f3tipL",
                         "clavR", "armR", "handR", "f1R", "head")

    # ---- 実行と判定 ---------------------------------------------------------

    def run_tool(self, paths):
        """メニューと同じ入口で、選択したjointを処理する。"""
        self.cmds.select(paths, replace=True)
        self.tool.remove_selected_joint()

    def assertWeights(self, actual, expected, message=""):
        """influenceの集合と各値が許容誤差内で一致する。"""
        self.assertEqual(set(actual), set(expected), message + ": influence set differs")
        difference = max((abs(a - b) for key in actual for a, b in zip(actual[key], expected[key])), default=0.0)
        self.assertLessEqual(difference, TOL, message)

    def check(self, skins, paths, undo=True):
        """ツールを実行し、全skinClusterを独立計算と比べ、一回のUndo/Redoを確かめる。"""
        cmds = self.cmds
        before = {skin: _snapshot(skin) for skin in skins}
        order = _deep_first(paths)
        expected = {skin: _expected(before[skin], order) for skin in skins}
        parents = {}
        for path in order:
            for child in cmds.listRelatives(path, children=True, type="transform", fullPath=True) or []:
                parents[_uuid(child)] = path
        removed = {_uuid(path) for path in paths}
        self.run_tool(paths)
        after = {skin: _snapshot(skin) for skin in skins}
        for skin in skins:
            self.assertWeights(after[skin], expected[skin], skin)
        self.assertFalse(any(cmds.ls(key) for key in removed))
        # 削除したjointの子(削除対象でないもの)は残り、削除されなかった祖先の下へ移る。
        for key, parent in parents.items():
            if key in removed:
                continue
            self.assertTrue(cmds.ls(key), key)
        if undo:
            cmds.undo()
            for skin in skins:
                self.assertWeights(_snapshot(skin), before[skin], "undo " + skin)
            self.assertTrue(all(cmds.ls(key) for key in removed))
            cmds.redo()
            for skin in skins:
                self.assertWeights(_snapshot(skin), after[skin], "redo " + skin)
        return before, after

    # ---- テスト -------------------------------------------------------------

    def test_chain_skips_non_influence_joints(self):
        """e→d、d→b(cを飛ばす)、b→root(aを飛ばす)。子は残り、親側へ付け替わる。"""
        for name, target in (("e", "d"), ("d", "b"), ("b", "root")):
            with self.subTest(joint=name):
                self.cmds.file(new=True, force=True)
                j = self.chain()
                skin = self.bind(self.mesh(), [j[k] for k in ("root", "b", "d", "e", "side")])
                _random_weights(skin, {"e": 1, "d": 2, "b": 3}[name], 4, must=(j["b"], j["d"], j["e"]))
                children = self.cmds.listRelatives(j[name], children=True, fullPath=True) or []
                child_ids = [_uuid(child) for child in children]
                parent_id = _uuid(self.cmds.listRelatives(j[name], parent=True, fullPath=True)[0])
                self.check([skin], [j[name]])
                for key in child_ids:
                    parent = self.cmds.listRelatives(self.cmds.ls(key, long=True)[0], parent=True, fullPath=True)
                    self.assertEqual(_uuid(parent[0]), parent_id)

    def test_chain_parent_and_child_together(self):
        """b・d・eと、influenceでないcを同時に削除すると、全てrootへ集まる。選択順・重複によらない。"""
        for selection in (("b", "d", "e", "c"), ("e", "c", "d", "b", "e")):
            with self.subTest(selection=selection):
                self.cmds.file(new=True, force=True)
                j = self.chain()
                skin = self.bind(self.mesh(), [j[k] for k in ("root", "b", "d", "e", "side")])
                _random_weights(skin, 7, 4, must=(j["b"], j["d"], j["e"]))
                after = self.check([skin], [j[k] for k in selection])[1][skin]
                root = _uuid(j["root"])
                for vertex in range(len(after[root])):
                    self.assertAlmostEqual(sum(row[vertex] for row in after.values()), 1.0, delta=TOL)
                self.assertTrue(self.cmds.objExists(j["a"]))

    def test_branch_siblings_and_cousins(self):
        """兄弟の指はhandLへ、handLと子は同時に消えるhandLを飛ばしarmLへ、headはchestへ。"""
        for names in (("f1L", "f2L", "f3tipL"), ("f1L", "handR", "head", "handL", "f1R", "neck")):
            with self.subTest(names=names):
                self.cmds.file(new=True, force=True)
                j = self.branch()
                skin = self.bind(self.mesh(8), [j[k] for k in self.BRANCH_INFLUENCES])
                _random_weights(skin, 21, 6, must=[j[k] for k in ("handL", "f1L", "f2L", "f3tipL", "handR", "f1R", "head")])
                self.check([skin], [j[k] for k in names])

    def test_multiple_skins_use_their_own_targets(self):
        """同じjointを使う3つのskinClusterで、移送先はskinClusterごとに決まる。"""
        j = {"root": self.joint("root")}
        j["mid"] = self.joint("mid", j["root"])
        j["leaf"] = self.joint("leaf", j["mid"])
        j["other"] = self.joint("other")
        skins = [
            self.bind(self.mesh(4, "m1"), [j["root"], j["mid"], j["leaf"], j["other"]]),
            self.bind(self.mesh(5, "m2"), [j["root"], j["leaf"], j["other"]]),
            self.bind(self.mesh(3, "m3"), [j["mid"], j["leaf"]]),
        ]
        for seed, skin in enumerate(skins):
            _random_weights(skin, 40 + seed, 3, must=(j["leaf"],))
        leaf = _uuid(j["leaf"])
        before, after = self.check(skins, [j["leaf"]])
        for skin, target in ((skins[0], "mid"), (skins[1], "root"), (skins[2], "mid")):
            key = _uuid(j[target])
            self.assertAlmostEqual(sum(after[skin][key]), sum(before[skin][key]) + sum(before[skin][leaf]),
                                   delta=TOL * len(after[skin][key]))

    def test_without_ancestor_uses_standard_deletion(self):
        """root・transformの下のjoint・root+子の同時削除は、Maya標準の削除(列を除くだけ)になる。"""
        for normalize in (1, 0, 2):
            for names in (("root",), ("under",), ("root", "mid")):
                with self.subTest(normalize=normalize, names=names):
                    cmds = self.cmds
                    cmds.file(new=True, force=True)
                    grp = _long(cmds.createNode("transform", name="grp"))
                    j = {"root": self.joint("root", grp)}
                    j["mid"] = self.joint("mid", j["root"])
                    xform = _long(cmds.createNode("transform", name="xform", parent=j["root"]))
                    j["under"] = self.joint("under", xform)
                    j["other"] = self.joint("other")
                    skin = self.bind(self.mesh(), [j[k] for k in ("root", "mid", "under", "other")], normalize)
                    total = (1.0, 1.0) if normalize == 1 else (0.5, 1.5)
                    _random_weights(skin, 50 + normalize, 3, must=(j["root"], j["mid"], j["under"]), total=total)
                    self.check([skin], [j[k] for k in names])
                    # rootの子(mid以外)はgrpの下へ移る。
                    if "root" in names:
                        self.assertEqual(cmds.listRelatives(cmds.ls("xform", long=True)[0], parent=True), ["grp"])

    def test_normalize_none_keeps_raw_sums_and_max_influences(self):
        """noneで合計が1でなくても頂点ごとの合計を保ち、合流後も非ゼロ本数が制限内に収まる。"""
        j = self.chain()
        skin = self.bind(self.mesh(), [j[k] for k in ("root", "b", "d", "e", "side")], normalize=0, max_influences=3)
        _random_weights(skin, 11, 3, must=(j["d"], j["e"]), total=(0.4, 1.6))
        before, after = (state[skin] for state in self.check([skin], [j["e"], j["d"]]))
        for vertex in range(len(after[_uuid(j["root"])])):
            self.assertAlmostEqual(sum(row[vertex] for row in after.values()),
                                   sum(row[vertex] for row in before.values()), delta=TOL)
            self.assertLessEqual(sum(1 for row in after.values() if row[vertex] > 0), 3)
        self.assertEqual(self.cmds.getAttr(skin + ".normalizeWeights"), 0)

    def test_same_short_names_namespaces_and_instances(self):
        """同名jointを完全パスで区別し、名前空間・インスタンスの別パスも同じノードとして扱う。"""
        cmds = self.cmds
        j = {}
        for group in ("grpA", "grpB"):
            grp = _long(cmds.createNode("transform", name=group))
            root = self.joint("root", grp)
            arm = self.joint("arm", root)
            j[group] = (root, arm, self.joint("hand", arm))
        cmds.namespace(add="charA")
        cmds.namespace(set="charA")
        root = self.joint("root")
        arm = self.joint("arm", root)
        j["charA"] = (root, arm, self.joint("hand", arm))
        cmds.namespace(set=":")
        skin = self.bind(self.mesh(), [path for chain in j.values() for path in chain])
        _random_weights(skin, 60, 5, must=[chain[2] for chain in j.values()])
        instance = _long(cmds.instance(_long("grpB"), name="grpBInstance")[0])
        instance_hand = instance + "|root|arm|hand"
        self.assertEqual(_uuid(instance_hand), _uuid(j["grpB"][2]))
        hands = {key: _uuid(j[key][2]) for key in j}
        before, after = (state[skin] for state in self.check(
            [skin], [j["grpA"][2], instance_hand, j["grpB"][2], "charA:hand"]))
        for key in ("grpA", "grpB", "charA"):
            arm, hand = _uuid(j[key][1]), hands[key]
            self.assertAlmostEqual(sum(after[arm]), sum(before[arm]) + sum(before[hand]), delta=TOL * len(after[arm]))

    def test_locks_and_layers_reject_before_changes(self):
        """移送元・移送先のロックとレイヤーは変更前に拒否し、無関係なinfluenceのロックは拒否しない。"""
        cmds = self.cmds
        for case in ("source", "target", "layer"):
            with self.subTest(case=case):
                cmds.file(new=True, force=True)
                j = self.chain()
                skin = self.bind(self.mesh(), [j[k] for k in ("root", "b", "d", "e", "side")])
                _random_weights(skin, 13, 4, must=(j["d"], j["e"]))
                if case == "layer":
                    layer = cmds.createNode("network", name="ngSkinToolsData_test")
                    cmds.addAttr(skin, longName="layerLink", attributeType="message")
                    cmds.connectAttr(layer + ".message", skin + ".layerLink")
                else:
                    cmds.setAttr(j["e" if case == "source" else "d"] + ".lockInfluenceWeights", True)
                before = _snapshot(skin)
                with self.assertRaises(RuntimeError):
                    self.run_tool([j["b"], j["e"]])
                self.assertWeights(_snapshot(skin), before, case)
                self.assertTrue(cmds.objExists(j["e"]) and cmds.objExists(j["b"]))
        with self.subTest(case="unrelated lock"):
            cmds.file(new=True, force=True)
            j = self.chain()
            skin = self.bind(self.mesh(), [j[k] for k in ("root", "b", "d", "e", "side")])
            _random_weights(skin, 13, 4, must=(j["d"], j["e"]))
            cmds.setAttr(j["side"] + ".lockInfluenceWeights", True)
            self.check([skin], [j["e"]])

    def test_undo_disabled_and_large_mesh(self):
        """Undo無効時も同じ結果になり、5041頂点でも全頂点が独立計算と一致してUndoで戻る。"""
        cmds = self.cmds
        j = self.chain()
        skin = self.bind(self.mesh(), [j[k] for k in ("root", "b", "d", "e", "side")])
        _random_weights(skin, 3, 4, must=(j["d"], j["e"]))
        before = _snapshot(skin)
        expected = _expected(before, _deep_first([j["e"], j["d"]]))
        cmds.undoInfo(state=False)
        try:
            self.run_tool([j["d"], j["e"]])
        finally:
            cmds.undoInfo(state=True)
        self.assertWeights(_snapshot(skin), expected, "undo disabled")

        cmds.file(new=True, force=True)
        j = self.chain()
        skin = self.bind(self.mesh(70), [j[k] for k in ("e", "d", "b", "root", "side")])
        self.assertEqual(_geometry(skin)[3], 5041)
        _random_weights(skin, 80, 4, must=(j["b"], j["d"], j["e"]))
        self.check([skin], [j["e"], j["d"], j["b"]])


def runTests():
    """テストを実行して結果を返す。"""
    return unittest.TextTestRunner(verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(RemoveSelectedJointsTest))


if __name__ == "__main__":
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        success = runTests().wasSuccessful()
    finally:
        maya.standalone.uninitialize()
    sys.exit(0 if success else 1)

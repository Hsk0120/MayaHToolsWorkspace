"""``mlib.duplicate(fast=True)`` の仕様テスト(2.1.0)。

fast が受け付ける組合せは、同じ複製元に対する ``cmds.duplicate`` の結果(戻り値・名前・親・型・
DG 接続・セットの所属・プラグのロック/キー設定可能/チャンネルボックス表示・値・選択)と突き合わせる。
通常経路は Undo 1 回で戻ること、fast は cmds を呼ばず Undo に記録しないこと、対応範囲外は
複製する前に NotImplementedError でシーンを変えないことを確かめる。

fast は名前空間付きのノードを扱わないため、ルート名前空間に英字だけの一意な接頭辞でノードを作り、
tearDown で setUp 後に増えたノードを UUID で削除する。
"""

import sys
import unittest
import uuid
from contextlib import ExitStack
from unittest.mock import patch

import maya.cmds as cmds

import mlib
mlib.reload()

#: fast 経路で呼ばれてはいけない maya.cmds の関数。
_FORBIDDEN = ("duplicate", "rename", "connectAttr", "disconnectAttr", "sets", "select", "setAttr",
              "lockNode", "parent", "delete", "createNode", "editDisplayLayerMembers")


class DuplicateFastSpecTest(unittest.TestCase):
    """fast 複製の受け付け範囲と cmds との一致を固定する。"""

    def setUp(self):
        """既存ノードの UUID・選択・Undo 設定を保存し、英字だけの接頭辞を作る。"""
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.selection = cmds.ls(selection=True, long=True)
        self.before = set(cmds.ls(uuid=True) or [])
        self.prefix = "dfx" + "".join(chr(ord("a") + int(c, 16) % 26) for c in uuid.uuid4().hex[:8])

    def tearDown(self):
        """setUp 後に増えたノードを削除し、選択と Undo 設定を戻す。"""
        cmds.namespace(setNamespace=":")
        created = [uid for uid in set(cmds.ls(uuid=True) or []) - self.before]
        names = [name for name in (cmds.ls(created, long=True) or []) if cmds.objExists(name)]
        for name in names:
            if cmds.objExists(name) and cmds.lockNode(name, query=True, lock=True)[0]:
                cmds.lockNode(name, lock=False)
        names = [name for name in names if cmds.objExists(name)]
        if names:
            cmds.delete(names)
        existing = [name for name in self.selection if cmds.objExists(name)]
        if existing:
            cmds.select(existing, replace=True)
        else:
            cmds.select(clear=True)
        cmds.undoInfo(state=self.undo_state)

    def n(self, text):
        """接頭辞付きの名前を返す。"""
        return self.prefix + text

    def forbidden(self):
        """fast 経路で maya.cmds の編集系が呼ばれたら失敗するコンテキストを返す。"""
        stack = ExitStack()
        for name in _FORBIDDEN:
            stack.enter_context(patch.object(cmds, name, side_effect=AssertionError("cmds." + name)))
        return stack

    # ---- 結果の要約 ---------------------------------------------------------------

    @staticmethod
    def _plug_flags(node):
        """プラグのロック・キー設定可能・チャンネルボックス表示の一覧を返す。"""
        def names(**flags):
            return sorted(cmds.listAttr(node, **flags) or [])
        return names(locked=True), names(keyable=True), names(channelBox=True)

    @staticmethod
    def _values(node):
        """キー設定可能・チャンネルボックスのスカラー値を返す。"""
        values = {}
        for attribute in set(cmds.listAttr(node, keyable=True) or []) | set(cmds.listAttr(node, channelBox=True) or []):
            try:
                values[attribute] = cmds.getAttr(node + "." + attribute)
            except (RuntimeError, ValueError):
                pass
        return values

    def summary(self, root):
        """複製結果の階層を比較用の値へまとめる。"""
        root = cmds.ls(root, long=True)[0]
        nodes = [root] + list(reversed(cmds.listRelatives(root, allDescendents=True, fullPath=True) or []))
        result = []
        for node in nodes:
            entry = {
                "path": node,
                "type": cmds.nodeType(node),
                "connections": sorted(cmds.listConnections(node, connections=True, plugs=True) or []),
                "sets": sorted(cmds.listSets(object=node) or []),
                "flags": self._plug_flags(node),
                "values": self._values(node),
            }
            if entry["type"] == "mesh":
                flat = cmds.xform(node + ".vtx[*]", query=True, translation=True, objectSpace=True) or []
                entry["points"] = [round(value, 6) for value in flat]
            result.append(entry)
        return {"nodes": result, "selection": cmds.ls(selection=True, long=True)}

    def assert_matches_cmds(self, source, select=None, **flags):
        """cmds・mlib 通常経路・fast の結果が一致し、Undo の扱いが契約どおりか確かめる。

        Args:
            source (str): 複製元。
            select (list[str] | None): 複製前の選択。None は選択なし。
            **flags: duplicate のフラグ。
        """
        def prepare():
            cmds.select(select, replace=True) if select else cmds.select(clear=True)
            cmds.flushUndo()

        prepare()
        expected_root = cmds.duplicate(source, **flags)[0]
        expected = self.summary(expected_root)
        cmds.undo()
        self.assertFalse(cmds.objExists(expected["nodes"][0]["path"]))

        prepare()
        normal = mlib.duplicate(source, **flags)
        self.assertEqual(self.summary(normal.getFullName()), expected)
        cmds.undo()
        self.assertFalse(cmds.objExists(expected["nodes"][0]["path"]), "normal duplicate is undone at once")

        prepare()
        with self.forbidden():
            copied = mlib.duplicate(source, fast=True, **flags)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True), "fast must not record undo")
        self.assertEqual(type(copied), type(normal))
        self.assertEqual(copied.getFullName(), expected["nodes"][0]["path"])
        self.assertEqual(self.summary(copied.getFullName()), expected)
        return copied

    # ---- 受け付ける組合せ ---------------------------------------------------------

    def test_mesh_with_history_and_shading(self):
        """履歴付き mesh は履歴を除いて複製し、shadingEngine の所属と shape 名が cmds と同じ。"""
        box = cmds.polyCube(name=self.n("box"))[0]
        cmds.setAttr(box + ".tx", 2.5)
        self.assert_matches_cmds(box)

    def test_default_shape_numbering(self):
        """``<名前>Shape<数字>`` の shape と独自名の shape の改名が cmds と同じ。"""
        cube = cmds.polyCube(name=self.n("cube1"))[0]
        cmds.rename(cmds.listRelatives(cube, shapes=True, fullPath=True)[0], self.n("cubeShape1"))
        self.assert_matches_cmds(cube)
        cmds.rename(cmds.listRelatives(cube, shapes=True, fullPath=True)[0], self.n("custom"))
        self.assert_matches_cmds(cube)

    def test_hierarchy_keeps_child_names_and_values(self):
        """子は元の名前のまま、値・ロック・キー設定可能・チャンネルボックス表示も cmds と同じ。"""
        group = cmds.createNode("transform", name=self.n("grp"))
        child = cmds.createNode("transform", name=self.n("child"), parent=group)
        cube = cmds.polyCube(name=self.n("leaf"))[0]
        cube = cmds.parent(cube, child)[0]
        cmds.setAttr(child + ".tx", 3)
        cmds.setAttr(child + ".ry", 30, lock=True)
        cmds.setAttr(child + ".v", keyable=False, channelBox=True)
        cmds.setAttr(child + ".sx", keyable=False)
        cmds.addAttr(child, longName="extra", attributeType="double", keyable=True)
        cmds.setAttr(child + ".extra", 5, lock=True)
        self.assert_matches_cmds(group)

    def test_child_under_parent(self):
        """親の下の対象は同じ親の下へ複製する。"""
        parent = cmds.createNode("transform", name=self.n("parent"))
        child = cmds.createNode("transform", name=self.n("kid"), parent=parent)
        copied = self.assert_matches_cmds(child)
        self.assertEqual(copied.getParent().getFullName(), "|" + self.n("parent"))

    def test_joint_chain_and_inverse_scale(self):
        """joint の inverseScale 接続を、ルートと途中の joint の両方で cmds と同じに作る。"""
        cmds.select(clear=True)
        root = cmds.joint(name=self.n("jroot"))
        middle = cmds.joint(name=self.n("jmid"), position=(1, 0, 0))
        cmds.joint(name=self.n("jtip"), position=(2, 0, 0))
        self.assert_matches_cmds(root)
        copied = self.assert_matches_cmds(cmds.ls(middle, long=True)[0])
        self.assertEqual(type(copied).__name__, "Joint")

    def test_object_set_membership(self):
        """objectSet の所属を複製側にも加える。"""
        box = cmds.polyCube(name=self.n("member"))[0]
        cmds.sets(box, name=self.n("set"))
        self.assert_matches_cmds(box)
        self.assertEqual(len(cmds.sets(self.n("set"), query=True)), 2)

    def test_curve_surface_locator(self):
        """nurbsCurve・nurbsSurface・locator の shape を cmds と同じ名前で複製する。"""
        curve = cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0)], name=self.n("crv"))
        surface = cmds.nurbsPlane(name=self.n("plane"), constructionHistory=False)[0]
        locator = cmds.spaceLocator(name=self.n("loc"))[0]
        for source in (curve, surface, locator):
            with self.subTest(source=source):
                self.assert_matches_cmds(source)

    def test_name_flags(self):
        """name の新規・既存名・不正文字・空文字列と、戻り値の形だけを変えるフラグ。"""
        box = cmds.polyCube(name=self.n("named"))[0]
        other = cmds.createNode("transform", name=self.n("taken"))
        for flags in ({"name": self.n("fresh")}, {"n": other}, {"name": self.n("with space")},
                      {"name": ""}, {"fullPath": True}, {"rr": True}, {"ic": False, "un": False, "po": False}):
            with self.subTest(flags=flags):
                self.assert_matches_cmds(box, **flags)

    def test_selection_rules(self):
        """選択は複製元が選択されていた場合だけ複製ルートへ置き換える。"""
        source = cmds.createNode("transform", name=self.n("sel"))
        other = cmds.createNode("transform", name=self.n("other"))
        for select in (None, [source], [other], [source, other], [source + ".tx"]):
            with self.subTest(select=select):
                self.assert_matches_cmds(source, select=select)

    def test_wrapper_input(self):
        """Node・MDagPath の入力も名前と同じに扱う。"""
        source = mlib.createNode("transform", name=self.n("wrapped"))
        self.assert_matches_cmds(source.getFullName())
        copied = mlib.duplicate(source, fast=True)
        self.assertEqual(copied.getParent(), None)
        copied = mlib.duplicate(source.mpath(), fast=True)
        self.assertTrue(copied.isValid())

    # ---- 拒否する組合せ -----------------------------------------------------------

    def assert_rejected(self, source, error=NotImplementedError, **flags):
        """fast が複製する前に拒否し、シーン・Undo を変えないことを確かめる。"""
        cmds.flushUndo()
        before = set(cmds.ls(uuid=True) or [])
        with self.assertRaises(error):
            mlib.duplicate(source, fast=True, **flags)
        self.assertEqual(set(cmds.ls(uuid=True) or []), before)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_rejects_unsupported_flags(self):
        """cmds と同じ結果を作れないフラグは NotImplementedError。"""
        source = cmds.createNode("transform", name=self.n("flags"))
        cmds.createNode("transform", name=self.n("flagsChild"), parent=source)
        for flags in ({"instanceLeaf": True}, {"ic": True}, {"upstreamNodes": True}, {"po": True},
                      {"rc": True}, {"smartTransform": True}, {"to": True}, {"query": True},
                      {"edit": True}, {"unknownFlag": 1}, {"name": "ns:copy"}, {"name": 1}):
            with self.subTest(flags=flags):
                self.assert_rejected(source, **flags)

    def test_rejects_unsupported_targets(self):
        """shape・DG ノード・コンポーネント・アトリビュートは NotImplementedError。"""
        box = cmds.polyCube(name=self.n("target"))[0]
        shape = cmds.listRelatives(box, shapes=True, fullPath=True)[0]
        dg = cmds.createNode("multiplyDivide", name=self.n("md"))
        for source in (shape, dg, box + ".vtx[0]", box + ".tx"):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_rejects_unsupported_hierarchies(self):
        """インスタンス・中間オブジェクト・未対応の型・ロック・名前空間は NotImplementedError。"""
        instanced = cmds.polyCube(name=self.n("inst"))[0]
        cmds.instance(instanced, name=self.n("instCopy"))
        self.assert_rejected(instanced)

        deformed = cmds.polyCube(name=self.n("io"))[0]
        shape = cmds.listRelatives(deformed, shapes=True)[0]
        orig = cmds.createNode("mesh", name=self.n("ioOrig"), parent=deformed)
        cmds.connectAttr(shape + ".outMesh", orig + ".inMesh")
        cmds.setAttr(orig + ".intermediateObject", 1)
        self.assert_rejected(deformed)

        constrained = cmds.createNode("transform", name=self.n("cons"))
        target = cmds.createNode("transform", name=self.n("consTarget"))
        cmds.parentConstraint(target, constrained)
        self.assert_rejected(constrained)

        locked = cmds.createNode("transform", name=self.n("locked"))
        cmds.lockNode(locked, lock=True)
        self.assert_rejected(locked)
        cmds.lockNode(locked, lock=False)

        locked_parent = cmds.createNode("transform", name=self.n("lockedParent"))
        kid = cmds.createNode("transform", name=self.n("lockedKid"), parent=locked_parent)
        cmds.lockNode(locked_parent, lock=True)
        self.assert_rejected(kid)
        cmds.lockNode(locked_parent, lock=False)

        namespace = self.n("ns")
        cmds.namespace(add=namespace)
        try:
            spaced = cmds.createNode("transform", name=namespace + ":node")
            self.assert_rejected(spaced)
            plain = cmds.createNode("transform", name=self.n("plain"))
            cmds.namespace(setNamespace=namespace)
            self.assert_rejected(plain)
        finally:
            cmds.namespace(setNamespace=":")
            cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)

    def test_rejects_unsupported_connections(self):
        """display layer・フェース単位の割り当て・出力側や階層内の接続は NotImplementedError。"""
        layered = cmds.createNode("transform", name=self.n("layered"))
        layer = cmds.createDisplayLayer(name=self.n("layer"), empty=True)
        cmds.editDisplayLayerMembers(layer, layered)
        self.assert_rejected(layered)

        faces = cmds.polyCube(name=self.n("faces"))[0]
        engine = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=self.n("faceSG"))
        cmds.sets(faces + ".f[0]", forceElement=engine)
        self.assert_rejected(faces)

        driver = cmds.createNode("transform", name=self.n("driver"))
        node = cmds.createNode("multiplyDivide", name=self.n("driven"))
        cmds.connectAttr(driver + ".tx", node + ".input1X")
        self.assert_rejected(driver)

        group = cmds.createNode("transform", name=self.n("inner"))
        first = cmds.createNode("transform", name=self.n("innerA"), parent=group)
        second = cmds.createNode("transform", name=self.n("innerB"), parent=group)
        cmds.connectAttr(first + ".tx", second + ".ty")
        self.assert_rejected(group)

    def test_input_errors_match_normal_path(self):
        """不正な fast・存在しない名前・空文字列の例外型は通常経路と同じ。"""
        source = cmds.createNode("transform", name=self.n("errors"))
        with self.assertRaises(TypeError):
            mlib.duplicate(source, fast=1)
        for value, error in ((self.n("missing"), ValueError), ("", ValueError)):
            with self.subTest(value=value):
                with self.assertRaises(error):
                    mlib.duplicate(value)
                with self.assertRaises(error):
                    mlib.duplicate(value, fast=True)
        with self.assertRaises(TypeError):
            mlib.duplicate(source, fast=True, name="a", n="b")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

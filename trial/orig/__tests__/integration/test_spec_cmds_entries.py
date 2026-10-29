"""mlib.cmds の7入口(getNode・getPlug・createNode・ls・delete・duplicate・select)の仕様テスト(担当D)。

長短名・同時指定の拒否・戻り値の型と順序・maya.cmdsとの一致・1回のUndoで戻る範囲・
fastがUndoへ記録しないこと・拒否時に何も変更しないことを、maya.cmdsの結果と突き合わせて固定する。
"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Joints
from mlib.nodes import Node
from mlib.nodes import SkinClusters
from mlib.components import Vertex
from mlib.components import Vertices
from mlib.plugs import Plug


class _CmdsCase(unittest.TestCase):
    """一時名前空間・選択・Undo設定の保存と復元を共通にする。"""

    def setUp(self):
        """一時名前空間を作り、選択とUndo設定を保存する。"""
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=True)
        self.selection = cmds.ls(selection=True, long=True)
        self.ns = "mlibSpecDCmds_" + uuid.uuid4().hex[:8]
        cmds.namespace(add=self.ns)

    def tearDown(self):
        """一時名前空間を中身ごと削除し、選択とUndo設定を戻す。"""
        cmds.select(clear=True)
        if cmds.namespace(exists=self.ns):
            for node in cmds.ls(self.ns + ":*", long=True) or []:
                if cmds.objExists(node) and cmds.lockNode(node, query=True, lock=True)[0]:
                    cmds.lockNode(node, lock=False)
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        existing = [name for name in self.selection if cmds.objExists(name)]
        if existing:
            cmds.select(existing, replace=True)
        cmds.undoInfo(state=self.undo_state)

    def name(self, leaf):
        """一時名前空間内の名前を返す。"""
        return self.ns + ":" + leaf

    def transforms(self):
        """一時名前空間内のtransformの数を返す。"""
        return len(cmds.ls(self.ns + ":*", type="transform") or [])


class GetNodeSpecTest(_CmdsCase):
    """getNodeの入力解決・型選択・例外を固定する。"""

    def test_wrapper_type_follows_registry_and_new_reference(self):
        """ラッパー型は登録表(祖先型を含む)で選び、呼ぶたびに同じノードの新しい参照を作る。"""
        joint = cmds.createNode("joint", name=self.name("joint"))
        network = cmds.createNode("network", name=self.name("network"))
        for name in (joint, network):
            node = mlib.getNode(name)
            self.assertIs(type(node), Node._registry.wrapper_class(cmds.nodeType(name)))
        first = mlib.getNode(joint)
        second = mlib.getNode(first)
        self.assertIsNot(first, second)
        self.assertEqual(first, second)
        self.assertEqual(type(first).__name__, "Joint")

    def test_owner_resolution_from_plug_component_and_api(self):
        """Plug・MPlugは所有ノード、Componentは所有シェイプ、API参照は対象ノードへ解決する。"""
        cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        shape = cmds.listRelatives(cube, shapes=True, fullPath=True)[0]
        selection = om2.MSelectionList().add(cube).add(cube + ".tx")
        self.assertEqual(mlib.getNode(cube + ".tx").getFullName(), "|" + cube)
        self.assertEqual(mlib.getNode(mlib.getPlug(cube + ".tx")).getFullName(), "|" + cube)
        self.assertEqual(mlib.getNode(selection.getPlug(1)).getFullName(), "|" + cube)
        self.assertEqual(mlib.getNode(selection.getDagPath(0)).getFullName(), "|" + cube)
        self.assertEqual(mlib.getNode(selection.getDependNode(0)).getFullName(), "|" + cube)
        vertex = Vertex(mlib.getNode(shape), 0)
        self.assertEqual(mlib.getNode(vertex).getFullName(), shape)
        self.assertEqual(mlib.getNode(Vertices(mlib.getNode(shape), [0, 1])).getFullName(), shape)

    def test_errors(self):
        """存在しない・複数一致・削除済みはRuntimeError、未対応型はTypeError、削除済みアトリビュートはValueError。"""
        cmds.createNode("transform", name=self.name("a1"))
        cmds.createNode("transform", name=self.name("a2"))
        with self.assertRaises(RuntimeError):
            mlib.getNode(self.name("missing"))
        with self.assertRaises(RuntimeError):
            mlib.getNode(self.name("a*"))
        with self.assertRaises(TypeError):
            mlib.getNode(5)
        node = mlib.getNode(self.name("a1"))
        cmds.addAttr(self.name("a1"), longName="extra", attributeType="double")
        plug = mlib.getPlug(self.name("a1") + ".extra")
        cmds.deleteAttr(self.name("a1") + ".extra")
        with self.assertRaises(ValueError):
            mlib.getNode(plug)
        cmds.delete(self.name("a1"))
        with self.assertRaises(RuntimeError):
            mlib.getNode(node)


class GetPlugSpecTest(_CmdsCase):
    """getPlugの入力・同一インスタンス・マルチアトリビュートの要素を固定する。"""

    def test_inputs_and_identity(self):
        """名前・MPlugから新しいPlug、既存Plugは同じインスタンスを返す。"""
        node = cmds.createNode("transform", name=self.name("node"))
        plug = mlib.getPlug(node + ".tx")
        self.assertIsInstance(plug, Plug)
        self.assertIs(mlib.getPlug(plug), plug)
        self.assertEqual(plug.getFullName(), mlib.getPlug(node + ".translateX").getFullName())
        mplug = om2.MSelectionList().add(node + ".ty").getPlug(0)
        self.assertEqual(mlib.getPlug(mplug).getFullName().split(".")[-1], "translateY")

    def test_multi_element_is_not_created(self):
        """未作成のマルチアトリビュートの要素も参照でき、参照取得だけでは要素を作らない。"""
        node = cmds.createNode("transform", name=self.name("node"))
        cmds.addAttr(node, longName="values", attributeType="double", multi=True)
        plug = mlib.getPlug(node + ".values[5]")
        self.assertIsInstance(plug, Plug)
        self.assertIsNone(cmds.getAttr(node + ".values", multiIndices=True))

    def test_errors(self):
        """空の名前・空のMPlugはValueError、未対応型はTypeError、解決できない名前はRuntimeError。"""
        node = cmds.createNode("transform", name=self.name("node"))
        with self.assertRaises(ValueError):
            mlib.getPlug("")
        with self.assertRaises(ValueError):
            mlib.getPlug(om2.MPlug())
        with self.assertRaises(TypeError):
            mlib.getPlug(5)
        with self.assertRaises(RuntimeError):
            mlib.getPlug(node + ".noSuchAttribute")
        with self.assertRaises(RuntimeError):
            mlib.getPlug(self.name("missing") + ".tx")


class CreateNodeSpecTest(_CmdsCase):
    """createNodeのフラグ・Undo・fastを固定する。"""

    def test_flags_and_result(self):
        """name/n・parent/p・skipSelect/ssはMayaへ渡り、実際の型のラッパーを返す。"""
        parent = mlib.createNode("transform", name=self.name("parent"))
        self.assertEqual(parent.getName(), self.name("parent"))
        child = mlib.createNode("joint", n=self.name("child"), p=parent)
        self.assertEqual(type(child).__name__, "Joint")
        self.assertEqual(cmds.listRelatives(child.getFullName(), parent=True, fullPath=True)[0], parent.getFullName())
        cmds.select(clear=True)
        mlib.createNode("transform", name=self.name("quiet"), ss=True)
        self.assertEqual(cmds.ls(selection=True), [])
        mlib.createNode("transform", name=self.name("loud"))
        self.assertEqual(cmds.ls(selection=True), [self.name("loud")])

    def test_conflicting_flags_are_rejected_before_creation(self):
        """長短名の同時指定・fastの非bool・cmdsに無いquery/editはノードを作る前にTypeError。"""
        before = self.transforms()
        # query/edit は cmds.createNode に無いフラグで、他の不明なフラグと同様に Maya が TypeError にする。
        for kwargs in (dict(name="a", n="b"), dict(parent=":", p=":"), dict(skipSelect=True, ss=True),
                       dict(shared=True, s=True), dict(query=True), dict(q=True), dict(edit=True), dict(e=True),
                       dict(fast=1)):
            with self.assertRaises(TypeError, msg=repr(kwargs)):
                mlib.createNode("transform", **kwargs)
        self.assertEqual(self.transforms(), before)

    def test_parent_validation(self):
        """parentが空文字ならValueError、存在しなければRuntimeError。"""
        before = self.transforms()
        with self.assertRaises(ValueError):
            mlib.createNode("transform", name=self.name("x"), parent="")
        with self.assertRaises(RuntimeError):
            mlib.createNode("transform", name=self.name("x"), parent=self.name("missing"))
        self.assertEqual(self.transforms(), before)

    def test_one_undo_and_fast_not_recorded(self):
        """通常は1回のUndoで作成を戻し、fast=TrueはUndoへ記録しない。"""
        mlib.createNode("transform", name=self.name("normal"))
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("normal")))
        cmds.select(clear=True)
        marker = cmds.undoInfo(query=True, undoName=True)
        node = mlib.createNode("transform", name=self.name("fast"), fast=True)
        self.assertTrue(cmds.objExists(self.name("fast")))
        self.assertEqual(type(node).__name__, "Transform")
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), marker)

    def test_fast_rejects_unsupported_flags_before_creation(self):
        """fast=Trueで対応しないフラグはノードを作る前にNotImplementedError。"""
        before = self.transforms()
        with self.assertRaises(NotImplementedError):
            mlib.createNode("transform", name=self.name("x"), fast=True, mlibUnknownFlag=1)
        self.assertEqual(self.transforms(), before)
        # name・parent・shared・skipSelectはfastでも受け付ける。
        parent = mlib.createNode("transform", name=self.name("fastParent"), fast=True, ss=True)
        child = mlib.createNode("transform", n=self.name("fastChild"), p=parent, fast=True, shared=False)
        self.assertEqual(child.getParent(), parent)

    def test_invalid_type_is_rejected_before_creation(self):
        """未知の型名は作成前にRuntimeErrorで、unknownノードを作らない。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                before = set(cmds.ls(type="unknown") or [])
                with self.assertRaisesRegex(RuntimeError, "Unknown Maya nodeType: mlibNoSuchNodeType"):
                    mlib.createNode("mlibNoSuchNodeType", name=self.name("unknownNode"), fast=fast)
                self.assertFalse(cmds.objExists(self.name("unknownNode")))
                self.assertEqual(set(cmds.ls(type="unknown") or []), before)


class LsSpecTest(_CmdsCase):
    """lsの戻り値の型・順序とcmds.lsとの一致を固定する。"""

    def setUp(self):
        """検索対象のノードを作る。"""
        super().setUp()
        self.joints = [cmds.createNode("joint", name=self.name("j%d" % i)) for i in range(3)]
        self.cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]

    def test_order_and_names_match_cmds(self):
        """結果の並びと名前はcmds.ls(long=True)と一致する。"""
        for kwargs in (dict(type="transform"), dict(long=True), dict(dag=True), dict(sn=True)):
            result = mlib.ls(self.ns + ":*", **kwargs)
            self.assertIsInstance(result, list)
            expected = cmds.ls(self.ns + ":*", long=True, **{k: v for k, v in kwargs.items() if k not in ("long", "sn")})
            self.assertEqual([item.getFullName() for item in result], expected, msg=repr(kwargs))
            self.assertTrue(all(isinstance(item, Node) for item in result))

    def test_special_collections(self):
        """type/typがjointならJoints、skinClusterならSkinClusters。結果がなければ空の同型。"""
        joints = mlib.ls(self.ns + ":*", type="joint")
        self.assertIsInstance(joints, Joints)
        self.assertEqual(len(joints), 3)
        self.assertIsInstance(mlib.ls(self.ns + ":*", typ="joint"), Joints)
        empty = mlib.ls(self.ns + ":*", type="skinCluster")
        self.assertIsInstance(empty, SkinClusters)
        self.assertEqual(len(empty), 0)

    def test_empty_inputs(self):
        """Noneや空の列だけなら全ノードを検索せず空のlistを返す。"""
        self.assertEqual(mlib.ls([]), [])
        self.assertEqual(mlib.ls(None), [])
        self.assertEqual(mlib.ls(self.name("missing*")), [])

    def test_plugs_and_components(self):
        """アトリビュート名はPlug、コンポーネント範囲は単体へ展開し、type指定で絞り込む。"""
        plugs = mlib.ls(self.cube + ".tx")
        self.assertEqual(len(plugs), 1)
        self.assertIsInstance(plugs[0], Plug)
        vertices = mlib.ls(self.cube + ".vtx[0:2]")
        self.assertEqual([item.index for item in vertices], [0, 1, 2])
        self.assertTrue(all(isinstance(item, Vertex) for item in vertices))
        cmds.select(self.cube + ".vtx[1:2]", self.cube + ".f[0]", replace=True)
        selected = mlib.ls(selection=True, type="vertex")
        self.assertEqual([item.index for item in selected], [1, 2])
        self.assertEqual(len(mlib.ls(sl=True, type="face")), 1)

    def test_wrapper_inputs_and_conflicts(self):
        """Node・コレクションを名前として渡せる。長短名の同時指定はTypeError。"""
        nodes = mlib.ls(mlib.getNode(self.joints[0]), [mlib.getNode(self.joints[1])])
        self.assertEqual([node.getName() for node in nodes], self.joints[:2])
        for kwargs in (dict(long=True, l=True), dict(type="joint", typ="joint"),
                       dict(selection=True, sl=True), {"assemblies": True, "as": True}):
            with self.assertRaises(TypeError, msg=repr(kwargs)):
                mlib.ls(self.ns + ":*", **kwargs)


class DeleteSpecTest(_CmdsCase):
    """deleteの一括削除・拒否時に何も消さないこと・Undoを固定する。"""

    def test_returns_none_and_one_undo_restores_all(self):
        """複数対象を1回で削除してNoneを返し、1回のUndoで全て戻る。"""
        names = [cmds.createNode("transform", name=self.name("n%d" % i)) for i in range(3)]
        self.assertIsNone(mlib.delete([names[0], (names[1], [names[2]])]))
        self.assertFalse(any(cmds.objExists(name) for name in names))
        cmds.undo()
        self.assertTrue(all(cmds.objExists(name) for name in names))
        mlib.delete([mlib.getNode(name) for name in names])
        self.assertFalse(any(cmds.objExists(name) for name in names))

    def test_mixed_names_and_nodes_are_rejected(self):
        """同じ対象列に名前とNodeが混在すると、何も削除せずTypeError。"""
        names = [cmds.createNode("transform", name=self.name("m%d" % i)) for i in range(2)]
        with self.assertRaises(TypeError):
            mlib.delete([mlib.getNode(names[0]), names[1]])
        self.assertTrue(all(cmds.objExists(name) for name in names))

    def test_attribute_name_string_is_rejected(self):
        """アトリビュート名の文字列もPlugと同じく、何も削除せずTypeError。"""
        attribute_owner = cmds.createNode("transform", name=self.name("owner"))
        other = cmds.createNode("transform", name=self.name("other"))
        cube = cmds.polyCube(name=self.name("attrCube"), constructionHistory=False)[0]
        faces = cmds.polyEvaluate(cube, face=True)
        for value in ([attribute_owner + ".tx", other], [other, cube + ".f[0]", attribute_owner + ".worldMatrix[0]"],
                      attribute_owner + ".translate"):
            for fast in (False, True):
                with self.subTest(value=value, fast=fast):
                    with self.assertRaisesRegex(TypeError, "Attribute names are not accepted"):
                        mlib.delete(value, fast=fast)
                    self.assertTrue(cmds.objExists(attribute_owner))
                    self.assertTrue(cmds.objExists(other))
                    self.assertEqual(cmds.polyEvaluate(cube, face=True), faces)
        # コンポーネントの文字列は従来どおり削除する。
        mlib.delete([cube + ".f[0]", other])
        self.assertEqual(cmds.polyEvaluate(cube, face=True), faces - 1)
        self.assertFalse(cmds.objExists(other))

    def test_wildcards_and_parent_with_child(self):
        """ワイルドカードは一致したノードへ展開し、親と子の両方の指定も1回で削除する。"""
        parent = cmds.createNode("transform", name=self.name("w_parent"))
        child = cmds.createNode("transform", name=self.name("w_child"), parent=parent)
        mlib.delete([self.name("w_*"), child])
        self.assertFalse(cmds.objExists(parent))

    def test_rejections_delete_nothing(self):
        """空・Plug・存在しない名前・ロック・削除不可ノードを含む場合は何も削除しない。"""
        keep = cmds.createNode("transform", name=self.name("keep"))
        locked = cmds.createNode("transform", name=self.name("locked"))
        cmds.lockNode(locked, lock=True)
        cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        cases = [
            ([], ValueError), ([keep, ""], ValueError),
            ([keep, mlib.getPlug(keep + ".tx")], TypeError), ([keep, self.name("missing")], RuntimeError),
            ([keep, locked], RuntimeError), ([keep, "persp"], RuntimeError), ([keep, 5], TypeError),
        ]
        faces = cmds.polyEvaluate(cube, face=True)
        for value, error in cases:
            with self.assertRaises(error, msg=repr(value)):
                mlib.delete(value + [cube + ".f[0]"] if isinstance(value, list) and value else value)
            self.assertTrue(cmds.objExists(keep))
            self.assertEqual(cmds.polyEvaluate(cube, face=True), faces)
        self.assertTrue(cmds.objExists(locked))

    def test_fast_rules(self):
        """fastはUndoへ記録せず、コンポーネントを含む入力は何も削除せずNotImplementedError。"""
        node = cmds.createNode("transform", name=self.name("fast"))
        cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        with self.assertRaises(NotImplementedError):
            mlib.delete([node, cube + ".f[0]"], fast=True)
        self.assertTrue(cmds.objExists(node))
        with self.assertRaises(TypeError):
            mlib.delete(node, fast="yes")
        cmds.select(clear=True)
        marker = cmds.undoInfo(query=True, undoName=True)
        mlib.delete(node, fast=True)
        self.assertFalse(cmds.objExists(node))
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), marker)

    def test_components(self):
        """コンポーネントはMayaの削除規則で消し、1回のUndoで戻る。"""
        cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        mlib.delete(cube + ".f[0:1]")
        self.assertEqual(cmds.polyEvaluate(cube, face=True), 4)
        cmds.undo()
        self.assertEqual(cmds.polyEvaluate(cube, face=True), 6)


class DuplicateSpecTest(_CmdsCase):
    """duplicateのフラグ・戻り値・Undoを固定する。"""

    def test_result_and_flags(self):
        """複製結果の先頭をラッパーで返し、name/n・parentOnly/poをMayaへ渡す。"""
        parent = cmds.createNode("transform", name=self.name("src"))
        cmds.createNode("transform", name=self.name("srcChild"), parent=parent)
        copied = mlib.duplicate(parent, name=self.name("copy"))
        self.assertIsInstance(copied, Node)
        self.assertEqual(copied.getName(), self.name("copy"))
        self.assertEqual(len(cmds.listRelatives(copied.getFullName(), children=True) or []), 1)
        only = mlib.duplicate(mlib.getNode(parent), n=self.name("only"), po=True)
        self.assertIsNone(cmds.listRelatives(only.getFullName(), children=True))
        joint = cmds.createNode("joint", name=self.name("joint"))
        self.assertEqual(type(mlib.duplicate(joint)).__name__, "Joint")

    def test_conflicts_and_undo(self):
        """長短名の同時指定はTypeErrorで複製せず、通常の複製は1回のUndoで戻る。"""
        node = cmds.createNode("transform", name=self.name("src"))
        before = self.transforms()
        for kwargs in (dict(name="a", n="b"), dict(parentOnly=True, po=True), dict(fullPath=True, f=True),
                       dict(returnRootsOnly=True, rr=True), dict(inputConnections=True, ic=True)):
            with self.assertRaises(TypeError, msg=repr(kwargs)):
                mlib.duplicate(node, **kwargs)
        self.assertEqual(self.transforms(), before)
        with self.assertRaises(ValueError):
            mlib.duplicate("")
        mlib.duplicate(node, name=self.name("copy"))
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("copy")))


class SelectSpecTest(_CmdsCase):
    """selectのフラグ・cmds.selectとの一致・Undoを固定する。"""

    def setUp(self):
        """選択対象を作る。"""
        super().setUp()
        self.a = cmds.createNode("transform", name=self.name("a"))
        self.b = cmds.createNode("transform", name=self.name("b"))
        self.cube = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]

    def selected(self):
        """現在の選択を平坦化した名前で返す。"""
        return cmds.ls(selection=True, flatten=True)

    def test_matches_cmds_select(self):
        """同じ対象・フラグでcmds.selectと同じ選択結果になり、Noneを返す。"""
        cases = [((self.a,), {}), (([self.a, self.b],), dict(add=True)), ((self.a,), dict(d=True)),
                 ((self.a,), dict(tgl=True)), ((), dict(cl=True)), (([],), {}),
                 ((self.cube + ".vtx[0:3]",), dict(r=True))]
        for args, kwargs in cases:
            cmds.select(self.b, replace=True)
            cmds.select(*args, **kwargs)
            expected = self.selected()
            cmds.select(self.b, replace=True)
            self.assertIsNone(mlib.select(*args, **kwargs))
            self.assertEqual(self.selected(), expected, msg=repr((args, kwargs)))

    def test_wrappers_and_collections(self):
        """Node・Plug・Componentsを名前へ変換して選択する。"""
        shape = mlib.getNode(cmds.listRelatives(self.cube, shapes=True, fullPath=True)[0])
        mlib.select([mlib.getNode(self.a), Vertices(shape, [0, 1, 2])])
        self.assertEqual(len(self.selected()), 4)
        mlib.select(clear=True)
        self.assertEqual(self.selected(), [])

    def test_conflicts_and_undo(self):
        """長短名の同時指定はTypeErrorで選択を変えず、通常の選択は1回のUndoで戻る。"""
        cmds.select(self.a, replace=True)
        for kwargs in (dict(clear=True, cl=True), dict(replace=True, r=True), dict(deselect=True, d=True),
                       dict(toggle=True, tgl=True), dict(hierarchy=True, hi=True), dict(noExpand=True, ne=True)):
            with self.assertRaises(TypeError, msg=repr(kwargs)):
                mlib.select(self.b, **kwargs)
        self.assertEqual(self.selected(), [self.a])
        mlib.select(self.b)
        self.assertEqual(self.selected(), [self.b])
        cmds.undo()
        self.assertEqual(self.selected(), [self.a])
        with self.assertRaises(ValueError):
            mlib.select([""])
        with self.assertRaises(TypeError):
            mlib.select([5])


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

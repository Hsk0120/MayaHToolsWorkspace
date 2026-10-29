"""mlib.createNode(作成の唯一の入口)の約束(仕様)を固定する。

対象: フラグ(長短名・同時指定の拒否・parent の受付型・shared/skipSelect の通常/fast 突き合わせ)、
戻り値の型(実際の nodeType に対応するラッパー。未登録型は Maya の継承に沿う)、未知型の拒否
(unknown ノードを残さない)、fast のロック/参照された親の拒否、1 回の Undo と fast が Undo に
残らないこと、Maya 標準の連番・自動親・名前空間・選択に従うこと、および廃止した作成経路
(``Node.create``・``Node(name, create=True)``・``SkinCluster(x, create=False)``)が無いこと。
Container.create / DagContainer.create の再定義(name 位置引数との互換と members)も確かめる。

期待値は maya.cmds で独立に求める。クラスの同一性には依存せず、``type(node).__name__`` と
``isinstance`` で比べる(動的クラスの生成前後で同じ結果になる)。
"""

import os
import sys
import tempfile
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components import Vertex, Vertices
from mlib.nodes import Container, DagContainer, DagNode, Joint, Mesh, Node, SkinCluster, Transform


class _CreateCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、Undo の設定と選択を元に戻す。"""

    def setUp(self):
        self.ns = "mlibSpecCreateNode_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.selection = cmds.ls(selection=True, long=True)

    def tearDown(self):
        for name in cmds.ls(self.ns + ":*", long=True) or []:
            if cmds.objExists(name) and cmds.lockNode(name, query=True, lock=True)[0]:
                cmds.lockNode(name, lock=False)
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)

    def name(self, text):
        return self.ns + ":" + text

    def make(self, kind="transform", text="node#", parent=None):
        flags = {"name": self.name(text), "skipSelect": True}
        if parent is not None:
            flags["parent"] = parent
        return cmds.createNode(kind, **flags)

    def nodes(self):
        """一時名前空間内のノードの UUID 集合を返す。"""
        return set(cmds.ls(self.ns + ":*", uuid=True) or [])

    @staticmethod
    def selection_roles(created, seed):
        """作成対象・自動親・既存選択を名前に依存しない役割へ変換する。"""
        roles = {cmds.ls(created, long=True)[0]: "created", cmds.ls(seed, long=True)[0]: "seed"}
        parents = cmds.listRelatives(created, parent=True, fullPath=True) or []
        if parents:
            roles[parents[0]] = "parent"
        return [roles.get(name, name) for name in cmds.ls(selection=True, long=True) or []]


class ResultTypeTest(_CreateCase):
    """戻り値は実際の nodeType に対応するラッパーで、getType は Maya の型名を返す。"""

    def test_registered_types(self):
        """登録型は対応クラス、getType は cmds.nodeType と同じ。"""
        for kind, wrapper in (("transform", Transform), ("joint", Joint), ("mesh", Mesh)):
            for fast in (False, True):
                with self.subTest(kind=kind, fast=fast):
                    node = mlib.createNode(kind, name=self.name(kind + "#"), fast=fast, skipSelect=True)
                    self.assertIs(type(node), wrapper)
                    self.assertEqual(node.getType(), cmds.nodeType(node.getFullName()))
                    self.assertEqual(node.getType(), kind)
                    self.assertEqual(Node(node.getFullName()), node)

    def test_unregistered_types_follow_maya_inheritance(self):
        """未登録型(airField・network)も unknown にせず、isinstance が Maya の継承に沿う。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                field = mlib.createNode("airField", name=self.name("field#"), fast=fast, skipSelect=True)
                self.assertEqual(field.getType(), "airField")
                self.assertEqual(field.getType(), cmds.nodeType(field.getFullName()))
                self.assertIsInstance(field, Transform)
                self.assertIsInstance(field, DagNode)
                self.assertNotIsInstance(field, Joint)
                self.assertIs(type(field), Node._registry.wrapper_class("airField"))
                self.assertEqual(field.getType(inherited=True),
                                 cmds.nodeType(field.getFullName(), inherited=True))
                network = mlib.createNode("network", name=self.name("net#"), fast=fast, skipSelect=True)
                self.assertEqual(network.getType(), "network")
                self.assertIsInstance(network, Node)
                self.assertNotIsInstance(network, DagNode)
                self.assertIs(type(network), Node._registry.wrapper_class("network"))

    def test_shape_without_parent_returns_shape_with_auto_parent(self):
        """親を省略した shape は shape を返し、getParent は Maya が自動生成した transform。"""
        for fast in (False, True):
            with self.subTest(fast=fast):
                before = set(cmds.ls(uuid=True))
                mesh = mlib.createNode("mesh", name=self.name("meshShape#"), fast=fast)
                self.assertIs(type(mesh), Mesh)
                self.assertEqual(cmds.nodeType(mesh.getFullName()), "mesh")
                parent = mesh.getParent()
                self.assertIs(type(parent), Transform)
                self.assertEqual(cmds.listRelatives(mesh.getFullName(), parent=True, fullPath=True),
                                 [parent.getFullName()])
                # 自動親は現在の名前空間(ルート)に作られるため、名前空間外の分も含めて 2 つ増える。
                self.assertEqual(len(set(cmds.ls(uuid=True)) - before), 2)
                cmds.delete(parent.getFullName())

    def test_version_compatible_type_names_are_created(self):
        """cmds.createNode が受け付ける版の互換名(2027 の addDoubleLinear→addDL 等)は作成できる。"""
        for kind in ("addDoubleLinear", "multDoubleLinear"):
            with self.subTest(kind=kind):
                node = mlib.createNode(kind, name=self.name(kind), skipSelect=True)
                self.assertEqual(node.getType(), cmds.nodeType(self.name(kind)))
                self.assertIn(node.getType(), (kind, kind.replace("DoubleLinear", "DL")))
                self.assertIs(type(node), Node._registry.wrapper_class(node.getType()))


class FlagTest(_CreateCase):
    """長短名・同時指定・parent の受付型・shared/skipSelect の通常/fast 突き合わせ。"""

    def test_long_and_short_names(self):
        """name/n・parent/p・skipSelect/ss・shared/s は同じ意味で Maya へ渡る。"""
        parent = mlib.createNode("transform", name=self.name("parent"), ss=True)
        self.assertEqual(parent.getName(), self.name("parent"))
        for fast in (False, True):
            with self.subTest(fast=fast):
                long_child = mlib.createNode("joint", name=self.name("long#"), parent=parent,
                                             skipSelect=True, shared=False, fast=fast)
                short_child = mlib.createNode("joint", n=self.name("short#"), p=parent, ss=True, s=False,
                                              fast=fast)
                for child in (long_child, short_child):
                    self.assertIs(type(child), Joint)
                    self.assertEqual(child.getParent(), parent)
                    self.assertEqual(cmds.listRelatives(child.getFullName(), parent=True, fullPath=True),
                                     [parent.getFullName()])

    def test_conflicting_flags_and_invalid_type_are_rejected_before_creation(self):
        """長短名の同時指定・fast の非 bool・cmds に無い query/edit は TypeError、type の不正は ValueError。"""
        before = self.nodes()
        for kwargs in (dict(name="a", n="b"), dict(parent=":", p=":"), dict(skipSelect=True, ss=True),
                       dict(shared=True, s=True), dict(fast=1), dict(fast=None),
                       dict(query=True), dict(q=True), dict(edit=True), dict(e=True)):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(TypeError):
                    mlib.createNode("transform", name=self.name("rejected"), **kwargs)
        for value in ("", 5, None):
            for fast in (False, True):
                with self.subTest(type=value, fast=fast):
                    with self.assertRaisesRegex(ValueError, "type must be a non-empty string"):
                        mlib.createNode(value, fast=fast)
        self.assertEqual(self.nodes(), before)
        self.assertFalse(cmds.objExists(self.name("rejected")))

    def test_parent_accepts_node_references(self):
        """parent は Node・名前・Plug(所有ノード)・MDagPath・MObject・MPlug を受け、所有ノードの下に作る。"""
        parent = Node(self.make("transform", "owner"))
        inputs = (
            ("Node", parent),
            ("str", parent.getFullName()),
            ("Plug", parent.getPlug("translateX")),
            ("MDagPath", parent.mpath()),
            ("MObject", parent.mnode()),
            ("MPlug", parent.getPlug("translateX").mplug()),
        )
        for label, value in inputs:
            for fast in (False, True):
                with self.subTest(parent=label, fast=fast):
                    child = mlib.createNode("transform", name=self.name("child#"), parent=value, fast=fast,
                                            skipSelect=True)
                    self.assertEqual(child.getParent(), parent)
                    self.assertEqual(cmds.listRelatives(child.getFullName(), parent=True, fullPath=True),
                                     [parent.getFullName()])
        # Component は所有シェイプへ解決する。shape は transform の親になれないため fast は Maya が拒否する。
        mesh_transform = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        mesh = Node(mesh_transform).getShape()
        before = self.nodes()
        with self.assertRaises((RuntimeError, TypeError)):
            mlib.createNode("transform", name=self.name("underShape"), parent=Vertex(mesh, 0), fast=True)
        self.assertEqual(self.nodes(), before)

    def test_parent_validation(self):
        """parent の空文字は ValueError、未解決は RuntimeError、複数対象(Components)は TypeError。何も作らない。"""
        mesh_transform = cmds.polyCube(name=self.name("cube"), constructionHistory=False)[0]
        mesh = Node(mesh_transform).getShape()
        before = self.nodes()
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaises(ValueError):
                    mlib.createNode("transform", name=self.name("x"), parent="", fast=fast)
                with self.assertRaises(RuntimeError):
                    mlib.createNode("transform", name=self.name("x"), parent=self.name("missing"), fast=fast)
                with self.assertRaises(TypeError):
                    mlib.createNode("transform", name=self.name("x"), parent=Vertices(mesh, [0, 1]), fast=fast)
                with self.assertRaises(TypeError):
                    mlib.createNode("transform", name=self.name("x"), parent=12, fast=fast)
        self.assertEqual(self.nodes(), before)
        self.assertFalse(cmds.objExists(self.name("x")))

    def test_skip_select_matches_cmds(self):
        """skipSelect の有無による選択は、通常・fast とも cmds.createNode と一致する(自動親を含む)。"""
        seed = self.make("transform", "seed")
        for kind in ("transform", "joint", "multiplyDivide", "mesh"):
            for skip in (False, True):
                cmds.select(seed, replace=True)
                native = cmds.createNode(kind, name=self.name("native#"), skipSelect=skip)
                expected = self.selection_roles(native, seed)
                for fast in (False, True):
                    with self.subTest(kind=kind, skipSelect=skip, fast=fast):
                        cmds.select(seed, replace=True)
                        created = mlib.createNode(kind, name=self.name("wrapped#"), skipSelect=skip, fast=fast)
                        self.assertEqual(self.selection_roles(created.getFullName(), seed), expected)
                        if kind == "mesh":
                            cmds.delete(created.getParent().getFullName())
                if kind == "mesh":
                    cmds.delete(cmds.listRelatives(native, parent=True, fullPath=True))

    def test_shared_returns_existing_node_of_same_type(self):
        """ルート名前空間の shared=True は、同名・同型のノードがあれば通常・fast とも作成せずそのノードを返す。

        cmds.createNode は同名・同型があると作成せず None を返す(ルート名前空間のみ)。mlib はその場合も
        既存ノードのラッパーを返す。
        """
        name = "mlibSpecCreateNodeShared_" + uuid.uuid4().hex[:8]
        existing = Node(cmds.createNode("transform", name=name, skipSelect=True))
        try:
            self.assertIsNone(cmds.createNode("transform", name=name, shared=True, skipSelect=True))
            for fast in (False, True):
                with self.subTest(fast=fast):
                    before = set(cmds.ls(uuid=True))
                    node = mlib.createNode("transform", name=name, shared=True, fast=fast, skipSelect=True)
                    self.assertEqual(node, existing)
                    self.assertIs(type(node), Transform)
                    self.assertEqual(set(cmds.ls(uuid=True)), before)
        finally:
            cmds.delete(name)
        # 同名が無ければ通常どおり作る。
        created = mlib.createNode("transform", name=self.name("newShared"), s=True, ss=True)
        self.assertEqual(created.getName(), self.name("newShared"))

    def test_shared_in_namespace(self):
        """名前空間付きの shared=True は、cmds が既存を再利用せず連番名で作るため通常経路もそれに従う。

        fast は名前で既存の同型ノードを探す近似のため既存ノードを返す(docstring に明記した差)。
        """
        existing = Node(self.make("transform", "nsShared"))
        normal = mlib.createNode("transform", name=self.name("nsShared"), shared=True, skipSelect=True)
        self.assertNotEqual(normal, existing)
        self.assertTrue(normal.getNodeName().startswith(self.name("nsShared")))
        self.assertEqual(normal.getType(), "transform")
        before = self.nodes()
        fast = mlib.createNode("transform", name=self.name("nsShared"), shared=True, fast=True, skipSelect=True)
        self.assertEqual(fast, existing)
        self.assertEqual(self.nodes(), before)

    def test_shared_with_different_type(self):
        """shared=True で同名ノードの型が違う場合、通常は cmds と同じく連番名で作り、fast は RuntimeError。"""
        self.make("network", "mixed")
        normal = mlib.createNode("transform", name=self.name("mixed"), shared=True, skipSelect=True)
        self.assertIs(type(normal), Transform)
        self.assertNotEqual(normal.getName(), self.name("mixed"))
        self.assertEqual(cmds.nodeType(self.name("mixed")), "network")
        before = self.nodes()
        with self.assertRaisesRegex(RuntimeError, "shared=True"):
            mlib.createNode("transform", name=self.name("mixed"), shared=True, fast=True, skipSelect=True)
        self.assertEqual(self.nodes(), before)

    def test_fast_rejects_unsupported_flags_before_creation(self):
        """fast=True で対応しないフラグは作成前に NotImplementedError。通常は Maya がフラグを判定する。"""
        before = self.nodes()
        with self.assertRaises(NotImplementedError):
            mlib.createNode("transform", name=self.name("x"), fast=True, mlibUnknownFlag=1)
        with self.assertRaises(TypeError):
            mlib.createNode("transform", name=self.name("x"), mlibUnknownFlag=1)
        self.assertEqual(self.nodes(), before)


class RejectionTest(_CreateCase):
    """未知型・ロック/参照された親の拒否と、拒否時に何も残さないこと。"""

    def test_unknown_type_is_rejected_without_leaving_nodes(self):
        """未知の nodeType は通常・fast とも RuntimeError で、unknown ノードを作らず選択も保つ。"""
        keep = self.make("transform", "keepSelected")
        for fast in (False, True):
            with self.subTest(fast=fast):
                cmds.select(keep, replace=True)
                before = set(cmds.ls(type=["unknown", "unknownDag", "unknownTransform"]) or [])
                with self.assertRaisesRegex(RuntimeError, "Unknown Maya nodeType: mlibSpecNoSuchType"):
                    mlib.createNode("mlibSpecNoSuchType", name=self.name("unknownNode"), fast=fast)
                self.assertFalse(cmds.objExists(self.name("unknownNode")))
                self.assertEqual(set(cmds.ls(type=["unknown", "unknownDag", "unknownTransform"]) or []), before)
                self.assertEqual(cmds.ls(selection=True), [keep])
        # 通常経路の作成と削除は対になり、Undo しても unknown ノードは現れない。
        cmds.undo()
        self.assertFalse(cmds.objExists(self.name("unknownNode")))

    def test_fast_rejects_locked_parent(self):
        """fast=True でロックされた親は RuntimeError で、ノードを作らない(通常は Maya が作成を許す)。"""
        parent = self.make("transform", "locked")
        cmds.lockNode(parent, lock=True)
        try:
            before = self.nodes()
            with self.assertRaisesRegex(RuntimeError, "locked or referenced"):
                mlib.createNode("transform", name=self.name("child"), parent=parent, fast=True)
            self.assertEqual(self.nodes(), before)
            self.assertFalse(cmds.objExists(self.name("child")))
        finally:
            cmds.lockNode(parent, lock=False)

    def test_fast_rejects_referenced_parent(self):
        """fast=True で参照ファイル由来の親は RuntimeError で、ノードを作らない。"""
        tmp_dir = tempfile.mkdtemp()
        ref_path = os.path.join(tmp_dir, "mlibSpecCreateNodeRef.ma")
        ref_namespace = "mlibSpecCreateNodeRefNs_" + uuid.uuid4().hex[:8]
        helper = cmds.createNode("transform", name="mlibSpecCreateNodeRefHelper")
        cmds.select(helper, replace=True)
        cmds.file(ref_path, exportSelected=True, type="mayaAscii", force=True)
        cmds.delete(helper)
        cmds.select(clear=True)
        reference_nodes = set(cmds.ls(type="reference") or [])
        cmds.file(ref_path, reference=True, namespace=ref_namespace, returnNewNodes=False)
        reference_node = next(iter(set(cmds.ls(type="reference")) - reference_nodes))
        try:
            parent = cmds.ls(ref_namespace + ":mlibSpecCreateNodeRefHelper", long=True)[0]
            self.assertTrue(cmds.referenceQuery(parent, isNodeReferenced=True))
            before = set(cmds.ls(uuid=True))
            with self.assertRaisesRegex(RuntimeError, "locked or referenced"):
                mlib.createNode("transform", name=self.name("child"), parent=parent, fast=True)
            self.assertEqual(set(cmds.ls(uuid=True)), before)
        finally:
            cmds.file(removeReference=True, referenceNode=reference_node)
            if cmds.namespace(exists=ref_namespace):
                cmds.namespace(removeNamespace=ref_namespace, deleteNamespaceContent=True)
            if os.path.exists(ref_path):
                os.remove(ref_path)
            if os.path.isdir(tmp_dir):
                os.rmdir(tmp_dir)


class UndoTest(_CreateCase):
    """通常は 1 回の Undo/Redo で作成(自動親を含む)を戻し、fast は Undo に残らない。"""

    def test_one_undo_and_redo(self):
        """作成は 1 回の Undo で消え、Redo で戻る。mesh は自動親も一緒に戻る。"""
        for kind in ("transform", "joint", "multiplyDivide", "mesh"):
            with self.subTest(kind=kind):
                cmds.flushUndo()
                created = mlib.createNode(kind, name=self.name("undo#"))
                name = created.getFullName()
                parent_name = created.getParent().getFullName() if kind == "mesh" else None
                cmds.undo()
                self.assertFalse(cmds.objExists(name))
                self.assertFalse(created.isValid())
                if parent_name is not None:
                    self.assertFalse(cmds.objExists(parent_name))
                self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
                cmds.redo()
                self.assertTrue(cmds.objExists(name))
                self.assertTrue(created.isValid())
                if parent_name is not None:
                    self.assertTrue(cmds.objExists(parent_name))
                    cmds.delete(parent_name)

    def test_fast_is_not_recorded(self):
        """fast=True は Undo キューに記録せず、直前の記録もそのまま。"""
        cmds.flushUndo()
        node = mlib.createNode("transform", name=self.name("fast"), fast=True)
        self.assertTrue(cmds.objExists(self.name("fast")))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        normal = mlib.createNode("transform", name=self.name("normal"))
        marker = cmds.undoInfo(query=True, undoName=True)
        mlib.createNode("joint", name=self.name("fastChild"), parent=node, fast=True)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), marker)
        cmds.undo()
        self.assertTrue(cmds.objExists(self.name("fast")))
        self.assertTrue(cmds.objExists(self.name("fastChild")))
        self.assertFalse(cmds.objExists(self.name("normal")))
        self.assertFalse(normal.isValid())


class MayaNamingTest(_CreateCase):
    """名前の衝突・名前空間は Maya の規則に従う。"""

    def test_name_clash_uses_maya_numbering(self):
        """同名があれば取得せず、Maya の連番名で別ノードを作る。異なる型の同名も同様。"""
        original = self.make("transform", "repeated")
        for fast in (False, True):
            with self.subTest(fast=fast):
                node = mlib.createNode("transform", name=self.name("repeated"), fast=fast, skipSelect=True)
                self.assertNotEqual(node.getName(), self.name("repeated"))
                self.assertTrue(node.getNodeName().startswith(self.name("repeated")))
                self.assertNotEqual(cmds.ls(node.getFullName(), uuid=True), cmds.ls(original, uuid=True))
        occupied = self.make("network", "differentType")
        node = mlib.createNode("transform", name=self.name("differentType"), skipSelect=True)
        self.assertEqual(cmds.nodeType(occupied), "network")
        self.assertEqual(node.getType(), "transform")
        self.assertNotEqual(node.getName(), occupied)

    def test_explicit_and_current_namespaces_follow_maya_names(self):
        """明示した名前空間と現在の名前空間は、Maya の名前解決どおりに使われる。"""
        explicit = mlib.createNode("transform", name=":" + self.name("explicit"), skipSelect=True)
        self.assertEqual(cmds.ls(explicit.getFullName(), long=True), ["|" + self.name("explicit")])
        cmds.namespace(set=self.ns)
        try:
            for fast in (False, True):
                with self.subTest(fast=fast):
                    current = mlib.createNode("joint", name="current#", fast=fast, skipSelect=True)
                    self.assertTrue(current.getNodeName().startswith(self.ns + ":current"))
                    self.assertEqual(cmds.ls(current.getFullName(), long=True), ["|" + current.getNodeName()])
        finally:
            cmds.namespace(set=":")


class RemovedCreationPathsTest(_CreateCase):
    """Node.create・Node(name, create=True)・SkinCluster(x, create=False) は無い。"""

    def test_node_create_classmethod_is_absent(self):
        """Node とその派生に create は無く、呼べば AttributeError。"""
        for wrapper in (Node, DagNode, Transform, Joint, Mesh, SkinCluster):
            with self.subTest(wrapper=wrapper.__name__):
                self.assertFalse(hasattr(wrapper, "create"))
                with self.assertRaises(AttributeError):
                    wrapper.create("transform", name=self.name("absent"))
        self.assertFalse(cmds.objExists(self.name("absent")))

    def test_constructor_create_keyword_is_rejected(self):
        """create キーワードは TypeError で、ノードを作らない。取得は従来どおり。"""
        existing = self.make("transform", "existing")
        before = self.nodes()
        for wrapper in (Node, Transform, Joint):
            for value in (True, False):
                with self.subTest(wrapper=wrapper.__name__, create=value):
                    with self.assertRaises(TypeError):
                        wrapper(self.name("viaConstructor"), create=value)
        with self.assertRaises(TypeError):
            SkinCluster(self.name("skin"), create=False)
        with self.assertRaises(TypeError):
            Transform(existing, create=True)
        self.assertEqual(self.nodes(), before)
        self.assertFalse(cmds.objExists(self.name("viaConstructor")))
        self.assertIs(type(Node(existing)), Transform)


class ContainerBuilderTest(_CreateCase):
    """Container.create / DagContainer.create は name の位置引数と members を受ける特化ビルダー。"""

    def test_create_signature(self):
        """name は位置・キーワードのどちらでも指定でき、members は作成後に所属する。"""
        member_a, member_b = Node(self.make("network", "a")), Node(self.make("network", "b"))
        for wrapper in (Container, DagContainer):
            with self.subTest(wrapper=wrapper.__name__):
                prefix = wrapper.__name__
                positional = wrapper.create(self.name(prefix + "Pos"))
                self.assertIs(type(positional), wrapper)
                self.assertEqual(positional.getNodeName(), self.name(prefix + "Pos"))
                self.assertEqual(positional.getMembers(), [])
                keyword = wrapper.create(name=self.name(prefix + "Kw"), members=[member_a, member_b])
                self.assertEqual(keyword.getNodeName(), self.name(prefix + "Kw"))
                self.assertEqual(set(keyword.getMembers()), {member_a, member_b})
                self.assertEqual(cmds.container(query=True, findContainer=[member_a.getName()]), keyword.getName())
                keyword.removeMembers(member_a, member_b)
                single = wrapper.create(self.name(prefix + "Single"), member_a)
                self.assertEqual(single.getMembers(), [member_a])
                single.removeMembers(member_a)

    def test_container_create_node_uses_real_type(self):
        """Container.createNode は実際の型のラッパーを返して所属させ、未知型は拒否する。"""
        owner = Container.create(self.name("owner"))
        node = owner.createNode("multiplyDivide")
        self.assertEqual(node.getType(), "multiplyDivide")
        self.assertEqual(node.getNodeName(), self.name("owner") + "_multiplyDivide")
        self.assertEqual(owner.getMembers(), [node])
        before = self.nodes()
        with self.assertRaises(RuntimeError):
            owner.createNode("mlibSpecNoSuchType")
        self.assertEqual(self.nodes(), before)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

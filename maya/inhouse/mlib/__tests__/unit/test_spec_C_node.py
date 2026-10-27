"""Node 単数の公開APIの約束(仕様)を固定する(担当C)。

対象: 型の選択(登録型・未登録型の Maya 継承に沿った選択・フォールバック・不一致の拒否)、作成経路が
無いこと(作成は mlib.createNode。その仕様は test_spec_cmds_createNode.py)、同一性(sameNode・
==・hash)、型の照会(getType(inherited=)・hasFn・getTypeId・getPluginName・
getClassification・isType・isLocked・isFromReferencedFile・mfn)、名前とパス、
namespace の移動と rename、アトリビュートの照会と既定値への復帰・フラグ変更、接続と履歴の照会、
削除済み(Undo の記録に残る)ノードと破棄済みノードの扱い。

既存の test_contract_changes_*.py が確かめている削除の一括化・getHistory の例外は重ねない。
"""

import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.common import Namespace
from mlib.nodes import DagNode, Joint, Mesh, Node, Nodes, Reflect, Shape, SkinCluster, Transform
from mlib.plugs import Plug


class _NamespaceCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、Undo の設定と選択を元に戻す。"""

    def setUp(self):
        self.ns = "mlibSpecCNode_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.selection = cmds.ls(selection=True, long=True)
        self.extra_namespaces = []

    def tearDown(self):
        for name in cmds.ls(self.ns + ":*", long=True) or []:
            if cmds.objExists(name):
                cmds.lockNode(name, lock=False)
        for namespace in [self.ns] + self.extra_namespaces:
            if cmds.namespace(exists=namespace):
                cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)
        cmds.select(self.selection, replace=True) if self.selection else cmds.select(clear=True)

    def name(self, text):
        return self.ns + ":" + text

    def make(self, kind="transform", text="node#", parent=None):
        flags = {"name": self.name(text), "skipSelect": True}
        if parent is not None:
            flags["parent"] = parent
        return cmds.createNode(kind, **flags)


class TypeSelectionTest(_NamespaceCase):
    """nodeType から登録型・Maya の継承に沿ったクラス・Node を選び、具体クラスの指定では非互換を拒否する。

    未登録型のクラスは登録表の規則(登録祖先型、または動的に生成したその派生クラス)で決まるため、
    クラスの同一性ではなく isinstance と登録表の結果で比べる。
    """

    def test_registered_exact_types(self):
        """登録された nodeType はそのクラスで包む。"""
        self.assertIs(type(Node(self.make("transform"))), Transform)
        self.assertIs(type(Node(self.make("joint"))), Joint)
        self.assertIs(type(Node(self.make("mesh", parent=self.make()))), Mesh)

    def test_registered_ancestor_type(self):
        """未登録の型は最も近い登録祖先型の派生になる(anisotropic は reflect の派生)。"""
        shader = cmds.shadingNode("anisotropic", asShader=True, name=self.name("aniso"))
        node = Node(shader)
        self.assertIsInstance(node, Reflect)
        self.assertIs(type(node), Node._registry.wrapper_class("anisotropic"))
        self.assertEqual(node.getType(), "anisotropic")

    def test_unregistered_types_follow_maya_inheritance(self):
        """登録祖先が無い DAG 型は DagNode・Shape の派生、DG 型は Node の派生になり、getType は Maya の型名。"""
        network = Node(self.make("network"))
        self.assertIsInstance(network, Node)
        self.assertNotIsInstance(network, DagNode)
        self.assertEqual(network.getType(), "network")
        light = self.make("pointLight", "light#", parent=self.make())
        node = Node(light)
        self.assertIsInstance(node, Shape)
        self.assertEqual(node.getType(), "pointLight")
        self.assertEqual(node.getFullName(), cmds.ls(light, long=True)[0])
        self.assertEqual(node.getParent().getFullName(), cmds.listRelatives(light, parent=True, fullPath=True)[0])
        self.assertFalse(node.isRoot())
        # shape・transform 以外の DAG 型(unknownDag 等、dagNode の直接の派生)は DagNode の派生。
        registry = Node._registry
        self.assertIs(registry.wrapper_class("dagNode"), DagNode)
        self.assertIs(registry.wrapper_class("shape"), Shape)
        self.assertTrue(issubclass(registry.wrapper_class("unknownDag"), DagNode))
        self.assertFalse(issubclass(registry.wrapper_class("unknownDag"), Transform))
        self.assertTrue(issubclass(registry.wrapper_class("pointLight"), Shape))
        self.assertTrue(issubclass(registry.wrapper_class("network"), Node))
        self.assertFalse(issubclass(registry.wrapper_class("network"), DagNode))
        self.assertIs(type(node), registry.wrapper_class("pointLight"))

    def test_concrete_class_accepts_subclass_and_rejects_others(self):
        """具体クラスの指定は派生型を受け、非互換は TypeError(差し替えない)。"""
        joint = self.make("joint")
        transform = self.make("transform")
        self.assertIs(type(Transform(joint)), Joint)
        with self.assertRaisesRegex(TypeError, "Joint requires a compatible node, got Transform"):
            Joint(transform)
        with self.assertRaises(TypeError):
            Mesh(transform)

    def test_inputs_resolve_to_owner(self):
        """Plug・MPlug は所有ノード、MDagPath はそのインスタンス、既存 Node は別ラッパー。"""
        transform = self.make()
        node = Node(transform)
        self.assertEqual(Node(transform + ".tx"), node)
        self.assertEqual(Node(node.getPlug("tx").mplug()), node)
        self.assertEqual(Node(node.mpath()), node)
        copy = Node(node)
        self.assertIsNot(copy, node)
        self.assertEqual(copy, node)

    def test_invalid_inputs(self):
        """空・存在しない・一意でない名前は RuntimeError、未対応型は TypeError。"""
        parent_a, parent_b = self.make(), self.make()
        self.make("transform", "dup", parent=parent_a)
        self.make("transform", "dup", parent=parent_b)
        for value in ("", self.name("missing"), self.name("dup")):
            with self.subTest(value=value):
                with self.assertRaises(RuntimeError):
                    Node(value)
        for value in (None, 12, 1.5, object()):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    Node(value)


class NoCreationPathTest(_NamespaceCase):
    """Node は取得専用で、Node.create と create キーワードは無い(作成は mlib.createNode)。"""

    def test_create_classmethod_is_absent(self):
        """Node・派生クラス・Nodes に create は無い。"""
        for wrapper in (Node, DagNode, Transform, Joint, Mesh, SkinCluster, Nodes):
            with self.subTest(wrapper=wrapper.__name__):
                self.assertFalse(hasattr(wrapper, "create"))
                with self.assertRaises(AttributeError):
                    wrapper.create

    def test_create_keyword_is_rejected_before_resolution(self):
        """create= は存在しない名前でも TypeError(RuntimeError より先)で、ノードを作らない。"""
        before = set(cmds.ls())
        for wrapper in (Node, Transform, Joint, SkinCluster):
            for value in (True, False):
                with self.subTest(wrapper=wrapper.__name__, create=value):
                    with self.assertRaises(TypeError):
                        wrapper(self.name("notCreated"), create=value)
        with self.assertRaises(TypeError):
            Transform(self.make(), create=True)
        with self.assertRaises(TypeError):
            Transform(self.make(), "extra")
        # 先の self.make() で作った 2 つ以外、何も残さない。
        self.assertEqual(len(set(cmds.ls()) - before), 2)
        self.assertFalse(cmds.objExists(self.name("notCreated")))
        # mlib.createNode は実際の型のラッパーを返す(詳細は test_spec_cmds_createNode.py)。
        created = mlib.createNode("joint", name=self.name("created"), skipSelect=True)
        self.assertIs(type(created), Joint)
        self.assertEqual(created.getName(), self.name("created"))


class IdentityTest(_NamespaceCase):
    """sameNode・==・hash の区別(旧 sameInstance は廃止し == へ統合)。"""

    def setUp(self):
        super().setUp()
        self.shape_parent = self.make()
        self.shape = self.make("mesh", "shape", parent=self.shape_parent)
        self.other_parent = self.make()
        cmds.parent(self.shape, self.other_parent, addObject=True, shape=True)
        self.paths = cmds.ls(self.shape, allPaths=True, long=True)

    def test_instances(self):
        """別インスタンスは sameNode だけ True、== は False。同じ保持パスは == が True。"""
        first, second = Node(self.paths[0]), Node(self.paths[1])
        self.assertTrue(first.sameNode(second))
        self.assertNotEqual(first, second)
        self.assertEqual(first, Node(self.paths[0]))
        self.assertFalse(hasattr(first, "sameInstance"))

    def test_dg_and_other_values(self):
        """DG ノードは同じノードなら sameNode・== とも True。Node 以外は両方 False。"""
        dg = Node(self.make("network"))
        self.assertTrue(dg.sameNode(Node(dg.getName())))
        self.assertEqual(dg, Node(dg.getName()))
        for value in (dg.getName(), None, dg.mnode()):
            with self.subTest(value=value):
                self.assertFalse(dg.sameNode(value))
        # MObject との == は OpenMaya 側の比較が TypeError を出すため、文字列と None だけ確かめる。
        for value in (dg.getName(), None):
            with self.subTest(value=value):
                self.assertFalse(dg == value)
        self.assertFalse(dg == dg.getName())

    def test_hash_is_stable_after_rename_and_delete(self):
        """hash は改名・削除後も変わらず、同じノードの別ラッパーと等しい。"""
        node = Node(self.make())
        value = hash(node)
        self.assertEqual(hash(Node(node.getName())), value)
        node.rename(self.name("renamedForHash"))
        self.assertEqual(hash(node), value)
        cmds.delete(node.getFullName())
        self.assertEqual(hash(node), value)


class DeletedNodeTest(_NamespaceCase):
    """削除後(Undo の記録に残る間)と破棄後(記録が消えた後)の振る舞い。"""

    def test_deleted_but_alive(self):
        """削除直後は isValid=False・isAlive=True。名前は空、型の照会は引き続き使える。"""
        name = self.make("transform", "gone")
        node = Node(name)
        cmds.delete(name)
        self.assertFalse(node.isValid())
        self.assertTrue(node.isAlive())
        self.assertEqual(str(node), "")
        self.assertEqual(node.getName(), "")
        self.assertEqual(node.getFullName(), "")
        self.assertIsNone(node.getUuid())
        self.assertEqual(repr(node), "<Transform invalid>")
        self.assertEqual(node.getType(), "transform")
        # 削除したノードは名前空間から外れるため、葉の名前だけを比べる。
        self.assertEqual(node.getNodeName(remove_namespace=True), "gone")
        self.assertFalse(node.hasAttr("tx"))
        self.assertFalse(node.isType("transform"))
        # Undo の記録に残る間は生存中として同じノード扱いになる。
        self.assertTrue(node.sameNode(node))
        self.assertTrue(node == node)

    def test_deleted_node_methods_raise(self):
        """アトリビュート・履歴・エイリアス・削除・改名は RuntimeError、接続照会は空リスト。"""
        node = Node(self.make())
        cmds.delete(node.getFullName())
        for method, args in (("getPlug", ("tx",)), ("getHistory", ()), ("getAliases", ()),
                             ("getPlugs", ()), ("delete", ()),
                             ("rename", (self.name("x"),))):
            with self.subTest(method=method):
                with self.assertRaises(RuntimeError):
                    getattr(node, method)(*args)
        self.assertEqual(node.getConnections(), [])
        with self.assertRaisesRegex(RuntimeError, "Cannot delete an invalid node"):
            node.delete()

    def test_deleted_node_rename_message(self):
        """削除済みノードの rename は通常・fast とも文言付きの RuntimeError(FINDINGS C-04 で修正)。"""
        node = Node(self.make())
        cmds.delete(node.getFullName())
        for fast in (False, True):
            with self.subTest(fast=fast):
                with self.assertRaisesRegex(RuntimeError, "^Cannot rename an invalid node$"):
                    node.rename(self.name("renamed"), fast=fast)
                with self.assertRaisesRegex(RuntimeError, "Cannot rename an invalid node"):
                    node.setNamespace(self.ns, fast=fast)
        self.assertFalse(cmds.objExists(self.name("renamed")))

    def test_destroyed_node(self):
        """Undo の記録を消すと isAlive も False になり、型の照会が RuntimeError になる。"""
        node = Node(self.make())
        cmds.delete(node.getFullName())
        cmds.flushUndo()
        self.assertFalse(node.isAlive())
        self.assertFalse(node.sameNode(node))
        self.assertFalse(node == node)
        for method in ("getType", "getTypeId", "getPluginName", "isLocked", "isFromReferencedFile",
                       "mfn", "getNodeName"):
            with self.subTest(method=method):
                with self.assertRaises(RuntimeError):
                    getattr(node, method)()


class TypeQueryTest(_NamespaceCase):
    """型・ロック・アトリビュート数の照会を OpenMaya・cmds の値と比べる。"""

    def test_type_id_and_plugin(self):
        """getTypeId は MTypeId の数値、組込み型の getPluginName は空文字列。"""
        first, second = Node(self.make()), Node(self.make())
        joint = Node(self.make("joint"))
        self.assertEqual(first.getTypeId(), om2.MFnDependencyNode(first.mnode()).typeId.id())
        self.assertEqual(first.getTypeId(), second.getTypeId())
        self.assertNotEqual(first.getTypeId(), joint.getTypeId())
        self.assertIsInstance(first.getTypeId(), int)
        self.assertEqual(first.getPluginName(), "")

    def test_classification(self):
        """getClassification は cmds.getClassification と同じ1要素のリスト。"""
        for kind in ("transform", "lambert", "network"):
            with self.subTest(kind=kind):
                node = Node(self.make(kind))
                self.assertEqual(node.getClassification(), cmds.getClassification(kind))
                self.assertEqual(len(node.getClassification()), 1)

    def test_get_type_inherited(self):
        """getType(inherited=True) は cmds.nodeType(inherited=True) と同じ順のリスト、bool 以外は TypeError。"""
        shape = Node(self.make("mesh", parent=self.make()))
        network = Node(self.make("network"))
        for node in (shape, network, Node(self.make("joint"))):
            with self.subTest(type=node.getType()):
                chain = node.getType(inherited=True)
                self.assertIsInstance(chain, list)
                self.assertEqual(chain, cmds.nodeType(node.getFullName(), inherited=True))
                self.assertEqual(chain[-1], node.getType())
                self.assertNotIn("node", chain)
                self.assertEqual(node.getType(inherited=False), node.getType())
                # 戻り値は新しいリストで、内部のキャッシュを共有しない。
                chain.append("edited")
                self.assertNotIn("edited", node.getType(inherited=True))
        self.assertEqual(shape.getType(inherited=True)[-1], "mesh")
        self.assertIn("shape", shape.getType(inherited=True))
        self.assertLess(shape.getType(inherited=True).index("shape"), shape.getType(inherited=True).index("mesh"))
        self.assertEqual(network.getType(inherited=True), ["network"])
        for value in (1, None, "yes"):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    shape.getType(inherited=value)
        # 複数形は保持順のリストを返す。
        self.assertEqual(Nodes([shape, network]).getType(inherited=True),
                         [shape.getType(inherited=True), network.getType(inherited=True)])
        self.assertEqual(Nodes([shape, network]).getType(), ["mesh", "network"])

    def test_has_fn(self):
        """hasFn は mnode().hasFn と同じで、int 以外は TypeError。"""
        shape = Node(self.make("mesh", parent=self.make()))
        network = Node(self.make("network"))
        for node, fn, expected in ((shape, om2.MFn.kMesh, True), (shape, om2.MFn.kDagNode, True),
                                   (shape, om2.MFn.kTransform, False), (network, om2.MFn.kDagNode, False),
                                   (network, om2.MFn.kDependencyNode, True)):
            with self.subTest(type=node.getType(), fn=fn):
                self.assertIs(node.hasFn(fn), expected)
                self.assertEqual(node.hasFn(fn), node.mnode().hasFn(fn))
        for value in ("kMesh", None, 1.5, True):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    shape.hasFn(value)
        self.assertEqual(Nodes([shape, network]).hasFn(om2.MFn.kDagNode), [True, False])
        cmds.delete(network.getFullName())
        cmds.flushUndo()
        with self.assertRaises(RuntimeError):
            network.hasFn(om2.MFn.kDependencyNode)

    def test_is_type(self):
        """isType は継承を含めて判定し、空・文字列以外は ValueError。"""
        shape = Node(self.make("mesh", parent=self.make()))
        self.assertTrue(shape.isType("mesh"))
        self.assertTrue(shape.isType("shape"))
        self.assertTrue(shape.isType("dagNode"))
        self.assertFalse(shape.isType("transform"))
        self.assertFalse(shape.isType("mlibNoSuchType"))
        for value in ("", None, 3):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    shape.isType(value)

    def test_locked_and_referenced(self):
        """isLocked は lockNode に追従し、ローカルのノードは参照由来でない。"""
        name = self.make()
        node = Node(name)
        self.assertFalse(node.isLocked())
        cmds.lockNode(name, lock=True)
        self.assertTrue(node.isLocked())
        cmds.lockNode(name, lock=False)
        self.assertFalse(node.isFromReferencedFile())

    def test_attr_count(self):
        """旧 getAttrCount は廃止。mfn().attributeCount() は複合の子も数える。"""
        name = self.make()
        node = Node(name)
        self.assertFalse(hasattr(node, "getAttrCount"))
        count = node.mfn().attributeCount()
        self.assertEqual(count, om2.MFnDependencyNode(node.mnode()).attributeCount())
        cmds.addAttr(name, longName="single", attributeType="double")
        self.assertEqual(node.mfn().attributeCount(), count + 1)
        cmds.addAttr(name, longName="triple", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(name, longName="triple" + axis, attributeType="double", parent="triple")
        self.assertEqual(node.mfn().attributeCount(), count + 5)


class NamePathTest(_NamespaceCase):
    """名前・パス・namespace の照会と変更。"""

    def test_dag_names(self):
        """同名がある DAG では getName は区別できる部分パス、getNodeName は葉の名前。"""
        parent_a, parent_b = self.make("transform", "pa"), self.make("transform", "pb")
        first = Node(self.make("transform", "leaf", parent=parent_a))
        self.make("transform", "leaf", parent=parent_b)
        self.assertEqual(first.getName(), cmds.ls(first.getFullName())[0])
        self.assertIn("|", first.getName())
        self.assertEqual(first.getNodeName(), self.name("leaf"))
        self.assertEqual(first.getNodeName(remove_namespace=True), "leaf")
        self.assertEqual(first.getFullName(), "|" + self.name("pa") + "|" + self.name("leaf"))
        self.assertFalse(hasattr(first, "getPath"))
        self.assertFalse(first.isRoot())
        self.assertTrue(Node(parent_a).isRoot())

    def test_dg_names(self):
        """DG ノードの getFullName はノード名で、isRoot は RuntimeError。"""
        node = Node(self.make("network", "dg"))
        self.assertEqual(node.getFullName(), self.name("dg"))
        self.assertEqual(node.getName(), self.name("dg"))
        for method in ("isRoot",):
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, "DAG"):
                    getattr(node, method)()

    def test_get_namespace(self):
        """ルートは ':'、入れ子はそのまま。"""
        root = Node(cmds.createNode("network", name="mlibSpecCRoot_" + uuid.uuid4().hex[:8], skipSelect=True))
        try:
            self.assertEqual(root.getNamespace(), Namespace(":"))
        finally:
            cmds.delete(root.getName())
        cmds.namespace(add="inner", parent=self.ns)
        node = Node(cmds.createNode("network", name=self.ns + ":inner:n", skipSelect=True))
        self.assertEqual(node.getNamespace(), Namespace(self.ns + ":inner"))

    def test_set_namespace(self):
        """無い namespace は作成し、1回の Undo で移動と作成を戻す。不正値は ValueError。"""
        node = Node(self.make("network", "moved"))
        target = "mlibSpecCMoveNs_" + uuid.uuid4().hex[:8]
        self.extra_namespaces.append(target)
        cmds.flushUndo()
        self.assertEqual(node.setNamespace(target), target + ":moved")
        self.assertTrue(cmds.namespace(exists=target))
        cmds.undo()
        self.assertFalse(cmds.namespace(exists=target))
        self.assertEqual(node.getName(), self.name("moved"))
        self.assertEqual(node.setNamespace(Namespace(self.ns)), self.name("moved"))
        for value in ("", 1, None):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "non-empty string"):
                    node.setNamespace(value)
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.setNamespace(target, fast=1)

    def test_set_namespace_fast(self):
        """fast=True も namespace を作成して移動し、Undo に記録しない。"""
        node = Node(self.make("network", "fastMoved"))
        target = "mlibSpecCFastNs_" + uuid.uuid4().hex[:8]
        self.extra_namespaces.append(target)
        cmds.flushUndo()
        self.assertEqual(node.setNamespace(target + ":", fast=True), target + ":fastMoved")
        self.assertTrue(cmds.namespace(exists=target))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        node.setNamespace(self.ns, fast=True)

    def test_rename(self):
        """rename は Maya が確定した名前を返し、不正文字は置換、空の名前は RuntimeError。"""
        node = Node(self.make("network", "orig"))
        self.assertEqual(node.rename(self.name("1bad")), self.name("bad"))
        with self.assertRaises(RuntimeError):
            node.rename("")
        with self.assertRaisesRegex(TypeError, "fast must be a bool"):
            node.rename(self.name("x"), fast="yes")
        cmds.flushUndo()
        self.assertEqual(node.rename(self.name("fastName"), fast=True), self.name("fastName"))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_rename_ignore_shape(self):
        """ignoreShape=True は Shape の名前を変えない。既定は Shape も追従する。"""
        parent = self.make("transform", "body")
        shape = self.make("mesh", "bodyShape", parent=parent)
        node = Node(parent)
        node.rename(self.name("kept"), ignoreShape=True)
        self.assertTrue(cmds.objExists(shape))
        other = Node(self.make("transform", "limb"))
        self.make("mesh", "limbShape", parent=other.getFullName())
        other.rename(self.name("follow"))
        self.assertTrue(cmds.objExists(self.name("followShape")))


class AttributeQueryTest(_NamespaceCase):
    """getPlug・hasAttr・getAliases・getPlugs(userDefined=)。"""

    def setUp(self):
        super().setUp()
        self.node_name = self.make("transform", "attrs")
        self.node = Node(self.node_name)

    def test_get_plug_errors(self):
        """空・文字列以外は ValueError、無い名前と上限超えの番号は AttributeError。"""
        for value in ("", 3, None):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    self.node.getPlug(value)
        with self.assertRaises(AttributeError):
            self.node.getPlug("mlibMissing")
        with self.assertRaisesRegex(AttributeError, "2147483647"):
            self.node.getPlug("worldMatrix[2147483648]")
        self.assertEqual(self.node.getPlug("worldMatrix[5]").getFullName(), self.node_name + ".worldMatrix[5]")

    def test_has_attr(self):
        """hasAttr は解決できる名前だけ True。不正値も例外にせず False。"""
        self.assertTrue(self.node.hasAttr("tx"))
        self.assertTrue(self.node.hasAttr("translate.translateX"))
        for value in ("mlibMissing", "", None, 3):
            with self.subTest(value=value):
                self.assertFalse(self.node.hasAttr(value))

    def test_aliases(self):
        """エイリアスが無ければ空、あれば (エイリアス名, 型付き Plug)。getPlug もエイリアスで解決する。"""
        self.assertEqual(self.node.getAliases(), [])
        cmds.addAttr(self.node_name, longName="weightA", attributeType="double")
        cmds.aliasAttr("aliasA", self.node_name + ".weightA")
        aliases = self.node.getAliases()
        self.assertEqual([alias for alias, _ in aliases], ["aliasA"])
        self.assertIsInstance(aliases[0][1], Plug)
        self.assertEqual(aliases[0][1].mplug(), self.node.getPlug("weightA").mplug())
        self.assertEqual(self.node.getPlug("aliasA").mplug(), self.node.getPlug("weightA").mplug())

    def test_extra_attrs(self):
        """getPlugs(userDefined=True) は追加順で、子は includeChildren=True のときだけ。aliasAttr の内部領域も含む。"""
        def names(include_children):
            return [plug.getLongName() for plug in
                    self.node.getPlugs(userDefined=True, includeChildren=include_children)]

        self.assertFalse(hasattr(self.node, "getExtraAttrs"))
        self.assertEqual(self.node.getPlugs(userDefined=True), [])
        cmds.addAttr(self.node_name, longName="first", attributeType="double")
        cmds.addAttr(self.node_name, longName="vec", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(self.node_name, longName="vec" + axis, attributeType="double", parent="vec")
        cmds.addAttr(self.node_name, longName="text", dataType="string")
        self.assertEqual(names(False), ["first", "vec", "text"])
        self.assertEqual(names(True), ["first", "vec", "vecX", "vecY", "vecZ", "text"])
        plugs = self.node.getPlugs(userDefined=True, includeChildren=False)
        self.assertTrue(all(isinstance(plug, Plug) for plug in plugs))
        self.assertEqual([plug.getFullName() for plug in plugs],
                         [self.node_name + "." + name for name in ("first", "vec", "text")])
        cmds.aliasAttr("firstAlias", self.node_name + ".first")
        # cmds.listAttr(userDefined=True) と同じく aliasAttr の内部アトリビュートを含む。
        self.assertIn("attributeAliasList", names(False))
        with self.assertRaises(TypeError):
            self.node.getPlugs(userDefined=True, includeChildren=1)
        with self.assertRaises(TypeError):
            self.node.getPlugs(userDefined=1)
        with self.assertRaises(TypeError):
            self.node.getPlugs(userDefined=True, keyable=True)

    def test_get_plugs_matches_list_attr(self):
        """getPlugs は listAttr と同じ順・同じ名前。"""
        names = cmds.listAttr(self.node_name, keyable=True)
        plugs = self.node.getPlugs(keyable=True)
        self.assertEqual([plug.getFullName() for plug in plugs],
                         [cmds.ls(self.node_name + "." + name)[0] for name in names])


class ResetAndFlagsTest(_NamespaceCase):
    """resetAttrs と setAttrFlags。"""

    def setUp(self):
        super().setUp()
        self.node_name = self.make("transform", "reset")
        self.node = Node(self.node_name)
        cmds.setAttr(self.node_name + ".tx", 3)
        cmds.setAttr(self.node_name + ".ty", 4)
        cmds.setAttr(self.node_name + ".ty", lock=True)
        source = self.make("plusMinusAverage", "pma")
        cmds.connectAttr(source + ".output1D", self.node_name + ".tz")
        cmds.addAttr(self.node_name, longName="extraValue", attributeType="double", keyable=True,
                     defaultValue=2.0)
        cmds.setAttr(self.node_name + ".extraValue", 7)
        cmds.addAttr(self.node_name, longName="extraText", dataType="string")

    def test_reset_all_skips_locked_and_connected(self):
        """省略時はキー設定可能で書ける数値アトリビュートだけを戻し、1回の Undo で戻る。"""
        cmds.flushUndo()
        plugs = self.node.resetAttrs()
        names = [plug.getName() for plug in plugs]
        # Transform の省略時は translate・rotate・scale・shear の子だけ(追加アトリビュートは対象外)。
        self.assertIn(self.node_name + ".tx", names)
        self.assertNotIn(self.node_name + ".extraValue", names)
        self.assertNotIn(self.node_name + ".ty", names)
        self.assertNotIn(self.node_name + ".tz", names)
        self.assertEqual(cmds.getAttr(self.node_name + ".tx"), 0.0)
        self.assertEqual(cmds.getAttr(self.node_name + ".ty"), 4.0)
        self.assertEqual(cmds.getAttr(self.node_name + ".extraValue"), 7.0)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.node_name + ".tx"), 3.0)
        # Node の既定(キー設定可能で書ける数値アトリビュート全体)は追加アトリビュートも戻す。
        cmds.flushUndo()
        names = [plug.getName() for plug in Node.resetAttrs(self.node)]
        self.assertIn(self.node_name + ".tx", names)
        self.assertIn(self.node_name + ".extraValue", names)
        self.assertNotIn(self.node_name + ".ty", names)
        self.assertNotIn(self.node_name + ".tz", names)
        self.assertEqual(cmds.getAttr(self.node_name + ".extraValue"), 2.0)
        cmds.undo()
        self.assertEqual(cmds.getAttr(self.node_name + ".extraValue"), 7.0)

    def test_reset_fast_matches_normal(self):
        """fast=True も同じアトリビュートを戻し、Undo に記録しない。"""
        expected = [plug.getName() for plug in self.node.resetAttrs()]
        cmds.undo()
        cmds.flushUndo()
        plugs = self.node.resetAttrs(fast=True)
        self.assertEqual([plug.getName() for plug in plugs], expected)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertEqual(cmds.getAttr(self.node_name + ".tx"), 0.0)

    def test_reset_explicit_errors(self):
        """明示した名前のロック・接続は RuntimeError、無い名前は AttributeError、非対応型は TypeError。"""
        for name in ("ty", "tz"):
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):
                    self.node.resetAttrs(name)
        with self.assertRaises(AttributeError):
            self.node.resetAttrs("mlibMissing")
        with self.assertRaises(TypeError):
            self.node.resetAttrs("extraText")
        with self.assertRaisesRegex(TypeError, "Specify only one of 'attributes' and 'attrs'"):
            self.node.resetAttrs("tx", attrs="tx")
        self.assertEqual([plug.getName() for plug in self.node.resetAttrs(attrs=["tx"])],
                         [self.node_name + ".tx"])

    def test_set_attr_flags(self):
        """全名前を解決してから更新し、無い名前を含めば何も変えない。戻り値は自身。"""
        with self.assertRaisesRegex(TypeError, "Missing required argument: 'attributes'"):
            self.node.setAttrFlags()
        with self.assertRaises(TypeError):
            self.node.setAttrFlags("tx", locked=1)
        with self.assertRaises(AttributeError):
            self.node.setAttrFlags(["tx", "mlibMissing"], locked=True)
        self.assertFalse(cmds.getAttr(self.node_name + ".tx", lock=True))
        cmds.flushUndo()
        self.assertIs(self.node.setAttrFlags(["tx", "rx"], locked=True, keyable=False), self.node)
        self.assertTrue(cmds.getAttr(self.node_name + ".tx", lock=True))
        self.assertFalse(cmds.getAttr(self.node_name + ".rx", keyable=True))
        cmds.undo()
        self.assertFalse(cmds.getAttr(self.node_name + ".tx", lock=True))
        self.assertTrue(cmds.getAttr(self.node_name + ".rx", keyable=True))

    def test_set_attr_flags_without_flags_changes_nothing(self):
        """フラグを全て None にすると、名前の検査だけで変更しない。"""
        self.assertIs(self.node.setAttrFlags(attrs="tx"), self.node)
        self.assertFalse(cmds.getAttr(self.node_name + ".tx", lock=True))
        with self.assertRaises(AttributeError):
            self.node.setAttrFlags("mlibMissing")


class ConnectionHistoryTest(_NamespaceCase):
    """getConnections の index・asNode・type と、getHistory の型の絞り込み。"""

    def setUp(self):
        super().setUp()
        self.target = self.make("transform", "target")
        self.pma = self.make("plusMinusAverage", "pma")
        self.md = self.make("multiplyDivide", "md")
        cmds.connectAttr(self.pma + ".output1D", self.target + ".tx")
        cmds.connectAttr(self.md + ".outputX", self.target + ".ty")
        self.node = Node(self.target)

    def test_index(self):
        """index は Python の添字と同じで、範囲外は None。idx との同時指定は TypeError。"""
        plugs = self.node.getConnections()
        self.assertEqual(len(plugs), 2)
        self.assertEqual(self.node.getConnections(index=0), plugs[0])
        self.assertEqual(self.node.getConnections(idx=-1), plugs[-1])
        self.assertIsNone(self.node.getConnections(index=5))
        with self.assertRaisesRegex(TypeError, "Specify only one of 'index' and 'idx'"):
            self.node.getConnections(index=0, idx=0)

    def test_type_and_as_node(self):
        """type で相手の型を絞り、asNode は相手のノードを返す。"""
        self.assertEqual(self.node.getConnections(type="multiplyDivide", asNode=True), [Node(self.md)])
        self.assertEqual(self.node.getConnections(type="transform"), [])
        pairs = self.node.getConnections(asPair=True)
        self.assertEqual(sorted(local.getName() for local, _ in pairs),
                         [self.target + ".tx", self.target + ".ty"])

    def test_history_type_filter(self):
        """getHistory の type は継承を含め、自身は含めない。"""
        history = self.node.getHistory()
        self.assertNotIn(self.node, history)
        self.assertEqual(set(node.getName() for node in history), {self.pma, self.md})
        self.assertEqual(self.node.getHistory(type="multiplyDivide"), [Node(self.md)])
        self.assertEqual(self.node.getHistory(type="transform"), [])
        self.assertEqual(Node(self.pma).getHistory(future=True), [self.node])


if __name__ == "__main__":
    unittest.main()

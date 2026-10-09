"""単数Node constructorの明示作成と既存入力解決の契約をMaya内で検証する。"""

import importlib
import inspect
import sys
import unittest
from unittest import mock

import hlib
import maya.cmds as cmds
from hlib._core.registry import NodeRegistry


class NodeConstructorCreateTest(unittest.TestCase):
    """登録済み具体型の作成、事前拒否、標準Mayaの選択とUndoを確認する。"""

    def setUp(self):
        """独立した空シーンと有効なUndoキューを用意する。"""
        cmds.file(new=True, force=True)
        cmds.undoInfo(state=True)

    def test_registered_concrete_classes_create_named_nodes(self):
        """代表的なDAG・DGクラスは指定名とexact登録型で新規作成する。"""
        cases = ((hlib.nodes.Transform, "transform"), (hlib.nodes.Joint, "joint"),
                 (hlib.nodes.MultiplyDivide, "multiplyDivide"))
        for wrapper_class, node_type in cases:
            with self.subTest(node_type=node_type):
                name = "constructor" + wrapper_class.__name__
                node = wrapper_class(name, create=True)
                self.assertIs(type(node), wrapper_class)
                self.assertEqual(cmds.nodeType(str(node)), node_type)
                self.assertEqual(node.getNodeName(), name)
                self.assertTrue(node.isValid())
                self.assertEqual(hlib.nodes.Node(str(node)), node)

    def test_true_always_creates_and_uses_maya_collision_numbering(self):
        """同名が存在しても取得せず、Mayaの連番規則で別ノードを作る。"""
        original = cmds.createNode("transform", name="repeated")
        first = hlib.nodes.Transform("repeated", create=True)
        second = hlib.nodes.Transform("repeated", create=True)
        self.assertEqual(first.getNodeName(), "repeated1")
        self.assertEqual(second.getNodeName(), "repeated2")
        uuids = [cmds.ls(name, uuid=True)[0] for name in (original, str(first), str(second))]
        self.assertEqual(len(set(uuids)), 3)
        occupied = cmds.createNode("network", name="differentType")
        new_transform = hlib.nodes.Transform("differentType", create=True)
        self.assertEqual(cmds.nodeType(occupied), "network")
        self.assertEqual(cmds.nodeType(str(new_transform)), "transform")
        self.assertNotEqual(new_transform.getName(), occupied)

    def test_mesh_creation_keeps_standard_auto_parent_and_typed_wrapper(self):
        """meshの標準作成が生成する親transformも保持し、Meshで初期化する。"""
        before = set(cmds.ls(uuid=True))
        mesh = hlib.nodes.Mesh("constructorMeshShape", create=True)
        self.assertIs(type(mesh), hlib.nodes.Mesh)
        self.assertEqual(cmds.nodeType(str(mesh)), "mesh")
        self.assertEqual(mesh.getNodeName(), "constructorMeshShape")
        parent = mesh.getParent()
        self.assertIs(type(parent), hlib.nodes.Transform)
        self.assertEqual(cmds.listRelatives(str(mesh), parent=True, fullPath=True),
                         [parent.getFullPath()])
        self.assertEqual(len(set(cmds.ls(uuid=True)) - before), 2)
        self.assertEqual(hlib.nodes.Node(str(mesh)), mesh)

    def test_constructors_follow_native_create_node_selection(self):
        """作成時の選択は代表型ごとにmaya.cmds.createNodeの結果と一致する。"""
        seed = cmds.createNode("transform", name="selectionSeed")
        for wrapper_class, node_type in ((hlib.nodes.Transform, "transform"),
                                          (hlib.nodes.Joint, "joint"),
                                          (hlib.nodes.MultiplyDivide, "multiplyDivide"),
                                          (hlib.nodes.Mesh, "mesh")):
            with self.subTest(node_type=node_type):
                cmds.select(seed, replace=True)
                native = cmds.createNode(node_type, name="native" + wrapper_class.__name__)
                expected = self._selection_roles(native, seed)
                cmds.select(seed, replace=True)
                created = wrapper_class("wrapped" + wrapper_class.__name__, create=True)
                self.assertEqual(self._selection_roles(str(created), seed), expected)

    def test_creation_is_one_undo_redo_including_auto_parent(self):
        """新規作成とmeshの自動親を一回のUndo/Redoで戻せる。"""
        for wrapper_class in (hlib.nodes.Transform, hlib.nodes.Joint,
                              hlib.nodes.MultiplyDivide, hlib.nodes.Mesh):
            with self.subTest(wrapper=wrapper_class.__name__):
                cmds.flushUndo()
                created = wrapper_class("undo" + wrapper_class.__name__, create=True)
                name = created.getFullName()
                parent_name = created.getParent().getFullName() if isinstance(created, hlib.nodes.Mesh) else None
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

    def test_explicit_and_current_namespaces_follow_maya_names(self):
        """明示namespaceと現在namespaceを標準の名前解決に従って使用する。"""
        cmds.namespace(add="constructorSpace")
        explicit = hlib.nodes.Transform(":constructorSpace:explicit", create=True)
        self.assertEqual(cmds.ls(str(explicit), long=True), ["|constructorSpace:explicit"])
        cmds.namespace(set="constructorSpace")
        try:
            current = hlib.nodes.Joint("current", create=True)
            self.assertEqual(cmds.ls(str(current), long=True), ["|constructorSpace:current"])
        finally:
            cmds.namespace(set=":")

    def test_false_keeps_existing_inputs_and_type_dispatch_without_editing(self):
        """create=Falseは既存の文字列・API・Plug入力と型選択を維持する。"""
        name = cmds.createNode("joint", name="existingJoint")
        original = hlib.nodes.Joint(name)
        plug = original.getPlug("translateX")
        inputs = (name, original, original.mnode(), original.mpath(), plug, plug.mplug(), str(plug))
        before = self._state()
        for value in inputs:
            with self.subTest(input_type=type(value).__name__):
                result = hlib.nodes.Node(value, create=False)
                self.assertIs(type(result), hlib.nodes.Joint)
                self.assertEqual(result, original)
                self.assertIsNot(result, original)
                self.assertEqual(hlib.nodes.Transform(value, create=False), original)
                self.assertEqual(self._state(), before)
        mesh_name = cmds.polyCube(name="componentOwner", constructionHistory=False)[0]
        mesh = hlib.nodes.Node(mesh_name).getShape()
        component = hlib.components.Vertex(mesh, 0)
        before = self._state()
        self.assertEqual(hlib.nodes.Node(component, create=False), mesh)
        self.assertEqual(hlib.nodes.Node(str(mesh) + ".vtx[0]", create=False), mesh)
        self.assertEqual(self._state(), before)

    def test_false_preserves_unknown_deleted_and_incompatible_input_errors(self):
        """取得モードでは存在しない・削除済み・非互換型を従来どおり拒否する。"""
        transform = hlib.nodes.Transform(cmds.createNode("transform", name="existingTransform"))
        deleted = hlib.nodes.Node(cmds.createNode("network", name="deletedReference"))
        deleted.delete()
        before = self._state()
        for missing in ("", "neverCreated"):
            with self.assertRaises(RuntimeError):
                hlib.nodes.Transform(missing, create=False)
        with self.assertRaises(RuntimeError):
            hlib.nodes.Node(deleted, create=False)
        with self.assertRaises(TypeError):
            hlib.nodes.Joint(transform, create=False)
        with self.assertRaises(TypeError):
            hlib.nodes.Node(123, create=False)
        self.assertEqual(self._state(), before)

    def test_create_requires_strict_bool_before_any_creation(self):
        """createは真偽値だけを受け付け、不正型ではシーンを変更しない。"""
        existing = cmds.createNode("transform", name="boolExisting")
        node_module = importlib.import_module("hlib.nodes.node")
        before = self._state()
        for value in (0, 1, None, "true", [], object()):
            for name in (existing, "notCreated"):
                with self.subTest(value_type=type(value).__name__, name=name):
                    with mock.patch.object(node_module.cmds, "createNode", wraps=cmds.createNode) as create_node:
                        with self.assertRaises(TypeError):
                            hlib.nodes.Transform(name, create=value)
                        create_node.assert_not_called()
                    self.assertEqual(self._state(), before)

    def test_invalid_creation_names_are_rejected_without_creating_nodes(self):
        """作成名は非空文字列とし、未指定・Node等の参照入力を拒否する。"""
        existing = hlib.nodes.Transform(cmds.createNode("transform", name="nameExisting"))
        before = self._state()
        for value in (None, 123, [], existing, existing.mnode(), existing.getPlug("translateX")):
            with self.subTest(input_type=type(value).__name__):
                with self.assertRaises(TypeError):
                    hlib.nodes.Transform(value, create=True)
                self.assertEqual(self._state(), before)
        with self.assertRaises(ValueError):
            hlib.nodes.Transform("", create=True)
        with self.assertRaises(TypeError):
            hlib.nodes.Transform(create=True)
        self.assertEqual(self._state(), before)

    def test_unknown_flags_and_extra_positional_arguments_fail_before_creation(self):
        """constructorへ作成コマンドのフラグや余分な位置引数を渡しても作成しない。"""
        node_module = importlib.import_module("hlib.nodes.node")
        before = self._state()
        cases = (((), {"name": "other"}), ((), {"parent": "doesNotExist"}),
                 ((), {"skipSelect": True}), ((), {"unsupported": True}),
                 ((True,), {}), (("extra",), {}))
        for args, kwargs in cases:
            with self.subTest(args=args, kwargs=kwargs):
                with mock.patch.object(node_module.cmds, "createNode", wraps=cmds.createNode) as create_node:
                    with self.assertRaises(TypeError):
                        hlib.nodes.Transform("unexpectedCreation", *args, create=True, **kwargs)
                    create_node.assert_not_called()
                self.assertEqual(self._state(), before)

    def test_unregistered_and_abstract_classes_reject_before_creation(self):
        """型を一意に作れない基底・未登録派生・Maya抽象型を生成前に拒否する。"""
        class UnregisteredTransform(hlib.nodes.Transform):
            """exact登録のないユーザー派生クラス。"""

        classes = (hlib.nodes.Node, hlib.nodes.DagNode, hlib.nodes.Shape, hlib.nodes.Constraint,
                   hlib.nodes.AnimCurve, hlib.nodes.AbstractBaseCreate, UnregisteredTransform)
        node_module = importlib.import_module("hlib.nodes.node")
        before = self._state()
        for wrapper_class in classes:
            with self.subTest(wrapper=wrapper_class.__name__):
                with mock.patch.object(node_module.cmds, "createNode", wraps=cmds.createNode) as create_node:
                    with self.assertRaises(TypeError):
                        wrapper_class("abstractCreation", create=True)
                    create_node.assert_not_called()
                self.assertEqual(self._state(), before)

    def test_creation_uses_current_exact_registration_and_rejects_multiple_types(self):
        """現在のexact登録を使用し、一クラスに複数型の登録がある場合は拒否する。"""
        class RegisteredTransform(hlib.nodes.Transform):
            """このテストの登録表でtransformに対応付ける具象型。"""

        original_registry = hlib.nodes.Node._registry
        registry = NodeRegistry(hlib.nodes.Node, resolve_inherited_types=True)
        registry.replace(dict(original_registry._classes))
        registry.register("transform", RegisteredTransform)
        with mock.patch.object(hlib.nodes.Node, "_registry", registry):
            created = RegisteredTransform("registeredCreation", create=True)
            self.assertIs(type(created), RegisteredTransform)
            self.assertEqual(cmds.nodeType(str(created)), "transform")
            self.assertIs(type(hlib.nodes.Node(str(created), create=False)), RegisteredTransform)
            registry.register("joint", RegisteredTransform)
            before = self._state()
            with self.assertRaises(TypeError):
                RegisteredTransform("ambiguousCreation", create=True)
            self.assertEqual(self._state(), before)
            self.assertEqual(RegisteredTransform(str(created), create=False), created)
        self.assertIs(hlib.nodes.Node._registry, original_registry)

    def test_skin_cluster_creation_is_rejected_but_bound_wrapping_is_preserved(self):
        """空skinClusterの生成は拒否し、バインド済み対象の取得初期化は保つ。"""
        node_module = importlib.import_module("hlib.nodes.node")
        before = self._state()
        with mock.patch.object(node_module.cmds, "createNode", wraps=cmds.createNode) as create_node:
            with self.assertRaises(TypeError):
                hlib.nodes.SkinCluster("emptySkin", create=True)
            create_node.assert_not_called()
        self.assertEqual(self._state(), before)
        joint = cmds.createNode("joint", name="boundJoint")
        mesh = cmds.polyPlane(name="boundGeometry", subdivisionsX=1, subdivisionsY=1,
                              constructionHistory=False)[0]
        skin_name = cmds.skinCluster(joint, mesh, toSelectedBones=True)[0]
        before = self._state()
        for wrapper_class in (hlib.nodes.SkinCluster, hlib.nodes.Node):
            skin = wrapper_class(skin_name, create=False)
            self.assertIs(type(skin), hlib.nodes.SkinCluster)
            self.assertTrue(skin.deforms(mesh))
            self.assertEqual([str(node) for node in skin.getInfluences()], [joint])
            self.assertEqual(skin.fn.typeName, "skinCluster")
            self.assertEqual(self._state(), before)

    def test_input_resolution_occurs_once_in_both_constructor_modes(self):
        """名前の解決結果を初期化へ引き継ぎ、作成・取得どちらも重複照会しない。"""
        node_module = importlib.import_module("hlib.nodes.node")
        existing = cmds.createNode("transform", name="resolveExisting")
        for name, create in ((existing, False), ("resolveCreation", True)):
            with self.subTest(create=create):
                with mock.patch.object(node_module, "_resolve_node", wraps=node_module._resolve_node) as resolve:
                    result = hlib.nodes.Transform(name, create=create)
                    self.assertIs(type(result), hlib.nodes.Transform)
                    self.assertEqual(resolve.call_count, 1)
                    self.assertNotIn("_pending_resolution", result.__dict__)

    def test_node_create_flags_returns_plugin_preparation_and_undo_are_preserved(self):
        """既存createの親・選択フラグと型・Undoを維持し、標準plugin準備を共有する。"""
        parent = hlib.nodes.Transform(cmds.createNode("transform", name="factoryParent"))
        plugin = hlib.common.Plugin
        with mock.patch.object(plugin, "ensureNodePlugin", wraps=plugin.ensureNodePlugin) as ensure:
            created = hlib.nodes.Transform("pluginConstructor", create=True)
            self.assertEqual(cmds.nodeType(str(created)), "transform")
            cmds.select(str(parent), replace=True)
            cmds.flushUndo()
            child = hlib.nodes.Node.create(type="joint", name="factoryChild", parent=parent, skipSelect=True)
            self.assertIs(type(child), hlib.nodes.Joint)
            self.assertEqual(child.getParent(), parent)
            self.assertEqual(cmds.ls(selection=True, long=True), [parent.getFullPath()])
            name = child.getFullName()
            cmds.undo()
            self.assertFalse(cmds.objExists(name))
            self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
            cmds.redo()
            self.assertTrue(cmds.objExists(name))
            self.assertEqual(ensure.call_args_list, [mock.call("transform"), mock.call("joint")])
        short = hlib.nodes.Node.create("transform", n="factoryShort", p=parent, ss=True)
        self.assertIs(type(short), hlib.nodes.Transform)
        self.assertEqual(short.getParent(), parent)

    def test_constructor_create_argument_is_keyword_only_with_false_default(self):
        """基底と個別初期化のcreateはキーワード専用・既定Falseに統一する。"""
        for function in (hlib.nodes.Node.__new__, hlib.nodes.Node.__init__, hlib.nodes.SkinCluster.__init__):
            with self.subTest(function=function.__qualname__):
                parameter = inspect.signature(function).parameters["create"]
                self.assertIs(parameter.default, False)
                self.assertEqual(parameter.kind, inspect.Parameter.KEYWORD_ONLY)

    @staticmethod
    def _state():
        """失敗時に保持すべきノード集合と選択を取得する。

        Returns:
            tuple[set[str], tuple[str]]: UUID集合と選択中の完全名。
        """
        return set(cmds.ls(uuid=True)), tuple(cmds.ls(selection=True, long=True) or [])

    @staticmethod
    def _selection_roles(created, seed):
        """作成対象・自動親・既存選択を名前に依存しない役割へ変換する。

        Args:
            created (str): 作成したノード名。
            seed (str): 作成前に選択した既存ノード名。

        Returns:
            list[str]: Mayaが選択した対象の役割。
        """
        roles = {cmds.ls(created, long=True)[0]: "created", cmds.ls(seed, long=True)[0]: "seed"}
        parents = cmds.listRelatives(created, parent=True, fullPath=True) or []
        if parents:
            roles[parents[0]] = "parent"
        return [roles.get(name, name) for name in cmds.ls(selection=True, long=True) or []]


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

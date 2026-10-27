"""未登録の Maya nodeType に対する動的クラス生成と型照会の仕様を固定する。

生成クラスはクラスの同一性に依存せず、``type(node).__name__``・``issubclass``・
``isType()`` で確かめる(reload・登録表変更・プラグイン操作で作り直されるため)。
"""

import importlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import maya.cmds as cmds
import mlib
mlib.reload()
from mlib.core import registry as registry_module
from mlib.core.registry import NodeRegistry
from mlib.common.plugin import Plugin


class _FallbackClass:
    """Maya のクラスを使わない汎用登録表のフォールバック。"""

    def __init__(self, value=None):
        self.value = value


class _RegisteredClass(_FallbackClass):
    """汎用登録表に登録する親クラス。"""


def _type_exists(node_type):
    """Maya がこの版で型名を認識するか(版ごとの有無で分岐するテスト用)。"""
    try:
        return bool(cmds.nodeType(node_type, isTypeName=True))
    except RuntimeError:
        return False


class _DynamicTypeCase(unittest.TestCase):
    """専用名前空間にノードを作り、終了時に削除する基底。"""

    def setUp(self):
        self.ns = cmds.namespace(add="mlibDynTypes_" + self._testMethodName[:40])

    def tearDown(self):
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)

    def make(self, node_type, parent=None):
        """名前空間内に nodeType のノードを作成し、一意名を返す。"""
        kwargs = {"name": self.ns + ":" + node_type + "#"}
        if parent is not None:
            kwargs["parent"] = parent
        return cmds.createNode(node_type, **kwargs)

    def makeLight(self):
        """transform の下に pointLight シェイプを作成し、その一意名を返す。"""
        return self.make("pointLight", parent=self.make("transform"))


class GeneratedWrapperSpecTest(_DynamicTypeCase):
    """登録の無い型に対する生成クラスの名前・親・isinstance・型名を固定する。"""

    def test_unregistered_dag_type_derives_from_nearest_registered_class(self):
        """airField(field→dynBase→transform)は Transform を親とする AirField になる。"""
        name = self.make("airField")
        node = mlib.nodes.Node(name)
        cls = type(node)
        self.assertEqual(cls.__name__, "AirField")
        self.assertIs(cls.__mro__[1], mlib.nodes.Transform)
        self.assertIsInstance(node, mlib.nodes.Transform)
        self.assertIsInstance(node, mlib.nodes.DagNode)
        self.assertIsInstance(node, mlib.nodes.Node)
        self.assertEqual(node.getType(), "airField")
        self.assertEqual(node.getType(), cmds.nodeType(name))
        self.assertEqual(cls._generated_node_type, "airField")
        self.assertTrue(cls._generated)
        self.assertEqual(cls.__module__, "mlib.nodes")
        self.assertEqual(cls.__qualname__, "AirField")
        self.assertEqual(node.getFullName(), cmds.ls(name, long=True)[0])
        self.assertIsNone(mlib.nodes.Node._registry.lookup("airField"))

    def test_intermediate_abstract_types_are_not_generated_as_parents(self):
        """登録クラスとの間の抽象型(field・dynBase)は生成せず、継承の判定は isType() で行う。"""
        node = mlib.nodes.Node(self.make("airField"))
        field_class = mlib.nodes.Field
        self.assertEqual(field_class.__name__, "Field")
        self.assertIs(field_class.__mro__[1], mlib.nodes.Transform)
        self.assertFalse(issubclass(type(node), field_class))
        self.assertNotIsInstance(node, field_class)
        self.assertTrue(node.isType("field"))
        self.assertTrue(node.isType("dynBase"))
        self.assertTrue(node.isType("transform"))
        self.assertFalse(node.isType("shape"))
        self.assertNotIn("dynBase", mlib.nodes.Node._registry._generated)

    def test_dg_type_without_registered_ancestor_derives_from_node(self):
        """network・animBlendNodeAdditive は Node を親とする生成クラスになる。"""
        for node_type, expected in (("network", "Network"),
                                    ("animBlendNodeAdditive", "AnimBlendNodeAdditive")):
            with self.subTest(node_type=node_type):
                node = mlib.nodes.Node(self.make(node_type))
                self.assertEqual(type(node).__name__, expected)
                self.assertIs(type(node).__mro__[1], mlib.nodes.Node)
                self.assertEqual(node.getType(), node_type)
                self.assertTrue(node.isType(node_type))
                self.assertFalse(isinstance(node, mlib.nodes.DagNode))

    def test_shape_type_derives_from_shape_and_keeps_dag_behaviour(self):
        """pointLight は Shape を親とする PointLight になり、親の取得が動く。"""
        light = self.makeLight()
        node = mlib.nodes.Node(light)
        self.assertEqual(type(node).__name__, "PointLight")
        self.assertIs(type(node).__mro__[1], mlib.nodes.Shape)
        self.assertIsInstance(node, mlib.nodes.Shape)
        self.assertNotIsInstance(node, mlib.nodes.Transform)
        self.assertTrue(node.isType("light"))
        self.assertEqual(node.getParent().getFullName(),
                         cmds.listRelatives(light, parent=True, fullPath=True)[0])

    def test_constraint_subtypes_derive_from_registered_constraint(self):
        """抽象型 constraint の登録により、symmetryConstraint は Constraint の派生になる。"""
        registry = mlib.nodes.Node._registry
        self.assertIs(registry.lookup("constraint"), mlib.nodes.Constraint)
        # "node" は継承列の終端に現れないので登録せず、鎖が尽きた型は fallback(Node)が親(D2-2)。
        self.assertIsNone(registry.lookup("node"))
        cls = mlib.nodes.SymmetryConstraint
        self.assertEqual(cls.__name__, "SymmetryConstraint")
        self.assertIs(cls.__mro__[1], mlib.nodes.Constraint)
        self.assertTrue(issubclass(cls, mlib.nodes.Transform))

    def test_pole_vector_constraint_follows_maya_parent(self):
        """手書きの PoleVectorConstraint は Maya と同じく pointConstraint の派生。"""
        self.assertTrue(issubclass(mlib.nodes.PoleVectorConstraint, mlib.nodes.PointConstraint))
        chain = cmds.nodeType("poleVectorConstraint", isTypeName=True, inherited=True)
        self.assertEqual(chain[-2], "pointConstraint")

    def test_generated_class_is_shared_by_all_wrapping_entries(self):
        """Node()・getNode・ls・mlib.nodes.<TypeName> は同じ生成クラスを使う。"""
        light = self.makeLight()
        cls = mlib.nodes.PointLight
        self.assertIs(mlib.nodes.PointLight, cls)
        self.assertIs(type(mlib.nodes.Node(light)), cls)
        self.assertIs(type(mlib.getNode(light)), cls)
        self.assertIs(type(mlib.ls(light)[0]), cls)
        self.assertIs(mlib.nodes.Node._registry.wrapper_class("pointLight"), cls)

    def test_explicit_construction_checks_compatibility(self):
        """生成クラスを明示した構築は互換ノードだけを受け付ける。"""
        light = self.makeLight()
        transform = cmds.listRelatives(light, parent=True, fullPath=True)[0]
        node = mlib.nodes.PointLight(light)
        self.assertEqual(type(node).__name__, "PointLight")
        self.assertEqual(type(mlib.nodes.Shape(light)).__name__, "PointLight")
        with self.assertRaises(TypeError):
            mlib.nodes.PointLight(transform)
        with self.assertRaises(TypeError):
            mlib.nodes.Transform(light)
        with self.assertRaises(TypeError):
            mlib.nodes.Field(self.make("airField"))

    def test_uppercase_first_type_name_is_kept(self):
        """先頭が大文字の型名(AISEnvFacade 等)はそのままクラス名になる。"""
        for node_type in ("AISEnvFacade", "RScontainer"):
            with self.subTest(node_type=node_type):
                if not _type_exists(node_type):
                    self.skipTest("Maya がこの版で型を認識しない: " + node_type)
                cls = getattr(mlib.nodes, node_type)
                self.assertEqual(cls.__name__, node_type)
                self.assertEqual(cls._generated_node_type, node_type)

    def test_unrecognized_type_name_falls_back_to_node_without_generation(self):
        """Maya が認識しない型名は生成せず Node を返し、負結果を保存しない。"""
        registry = mlib.nodes.Node._registry
        self.assertIs(registry.wrapper_class("mlibNoSuchTypeXYZ"), mlib.nodes.Node)
        self.assertNotIn("mlibNoSuchTypeXYZ", registry._generated)
        self.assertNotIn("mlibNoSuchTypeXYZ", registry_module._INHERITED_TYPES_CACHE)

    def test_registered_types_helper_excludes_generated_classes(self):
        """_registered_types は登録キーだけを返し、base で派生に絞れる。"""
        registry = mlib.nodes.Node._registry
        mlib.nodes.PointLight
        names = registry._registered_types()
        self.assertNotIn("node", names)
        self.assertIn("transform", names)
        self.assertNotIn("pointLight", names)
        constraints = registry._registered_types(base=mlib.nodes.Constraint)
        self.assertIn("constraint", constraints)
        self.assertIn("parentConstraint", constraints)
        self.assertNotIn("transform", constraints)
        self.assertEqual(constraints, sorted(constraints))


class ModuleAttributeSpecTest(_DynamicTypeCase):
    """mlib.nodes.<TypeName> の属性アクセスの契約を固定する。"""

    def test_unknown_type_name_raises_attribute_error(self):
        """Maya が認識しない型名は AttributeError で、hasattr/getattr の既定値も使える。"""
        with self.assertRaisesRegex(AttributeError, "unknown Maya node type 'mlibNoSuchTypeXYZ'"):
            mlib.nodes.MlibNoSuchTypeXYZ
        self.assertFalse(hasattr(mlib.nodes, "MlibNoSuchTypeXYZ"))
        self.assertIsNone(getattr(mlib.nodes, "MlibNoSuchTypeXYZ", None))

    def test_lowercase_and_private_names_are_not_generated(self):
        """先頭が小文字・先頭が _ の名前は生成の対象にせず、サブモジュールはそのまま。"""
        with self.assertRaises(AttributeError):
            mlib.nodes.pointLight
        with self.assertRaises(AttributeError):
            mlib.nodes._PointLight
        self.assertIs(mlib.nodes.transform, sys.modules["mlib.nodes.transform"])

    def test_registered_classes_and_public_names_are_unchanged(self):
        """生成クラスは __all__・モジュール辞書・dir() に入らず、登録クラスはそのまま返る。"""
        cls = mlib.nodes.PointLight
        self.assertIs(mlib.nodes.Joint, mlib.nodes._WRAPPER_CLASSES["joint"])
        self.assertNotIn("PointLight", mlib.nodes.__all__)
        self.assertNotIn("PointLight", vars(mlib.nodes))
        self.assertNotIn("PointLight", dir(mlib.nodes))
        self.assertIs(mlib.nodes.PointLight, cls)

    def test_registered_name_variants_resolve_to_registered_class(self):
        """型名の表記が規則と違う登録(THdependNode)は、属性では同名のサブモジュールが優先し、
        属性探索の本体(__getattr__)は登録表の完全一致で登録クラスを返す。"""
        self.assertIs(mlib.nodes.THdependNode, sys.modules["mlib.nodes.THdependNode"])
        self.assertIs(mlib.nodes.__getattr__("THdependNode"), mlib.nodes.THDependNode)
        self.assertIs(mlib.nodes.Node._registry.lookup("THdependNode"), mlib.nodes.THDependNode)
        self.assertIs(mlib.nodes.__getattr__("Joint"), mlib.nodes.Joint)

    def test_attribute_access_matches_wrapping(self):
        """属性で得たクラスと Node() が選ぶクラスは同じ名前で、同じ契約を持つ。"""
        light = self.makeLight()
        node = mlib.nodes.Node(light)
        self.assertEqual(type(node).__name__, mlib.nodes.PointLight.__name__)
        self.assertIsInstance(node, mlib.nodes.PointLight)
        self.assertIn("自動生成", mlib.nodes.PointLight.__doc__)


class InvalidationSpecTest(_DynamicTypeCase):
    """登録表の変更・reload・プラグイン操作で生成クラスを作り直すことを固定する。"""

    def test_registry_change_replaces_generated_class(self):
        """登録は生成より優先し、復元後は新しい生成クラスになる。"""
        light = self.makeLight()
        registry = mlib.nodes.Node._registry
        before = mlib.nodes.PointLight
        snapshot = registry._snapshot()

        class Probe(mlib.nodes.Shape):
            """登録で差し替える利用側クラス。"""

        try:
            registry.register("pointLight", Probe)
            self.assertIs(mlib.nodes.PointLight, Probe)
            self.assertIs(type(mlib.nodes.Node(light)), Probe)
            self.assertIs(type(mlib.getNode(light)), Probe)
        finally:
            registry._restore(snapshot)
        after = mlib.nodes.PointLight
        self.assertIsNot(after, before)
        self.assertIsNot(after, Probe)
        self.assertEqual(after.__name__, "PointLight")
        node = mlib.nodes.Node(light)
        self.assertEqual(type(node).__name__, "PointLight")
        self.assertNotIsInstance(node, before)
        self.assertIsInstance(node, after)

    def test_registering_intermediate_type_changes_parent_of_generated_class(self):
        """抽象型 field を登録すると、以後の AirField はそのクラスの派生になる。"""
        name = self.make("airField")
        registry = mlib.nodes.Node._registry
        snapshot = registry._snapshot()

        class FieldProbe(mlib.nodes.Transform):
            """抽象型に対応付ける利用側クラス。"""

        try:
            registry.register("field", FieldProbe)
            self.assertIs(mlib.nodes.Field, FieldProbe)
            node = mlib.nodes.Node(name)
            self.assertEqual(type(node).__name__, "AirField")
            self.assertIs(type(node).__mro__[1], FieldProbe)
            self.assertIsInstance(node, FieldProbe)
        finally:
            registry._restore(snapshot)
        self.assertIs(type(mlib.nodes.Node(name)).__mro__[1], mlib.nodes.Transform)
        self.assertIs(mlib.nodes.Field.__mro__[1], mlib.nodes.Transform)

    def test_clear_and_replace_discard_generated_classes(self):
        """clear/replace でも生成済みクラスを残さない(汎用登録表で確認)。"""
        registry = NodeRegistry(_FallbackClass, generate_classes=True)
        registry.register("transform", _RegisteredClass)
        first = registry.wrapper_class("joint")
        registry.replace({"transform": _RegisteredClass})
        self.assertIsNot(registry.wrapper_class("joint"), first)
        second = registry.wrapper_class("joint")
        registry.clear()
        self.assertEqual(registry._generated, {})
        third = registry.wrapper_class("joint")
        self.assertIsNot(third, second)
        self.assertIs(third.__mro__[1], _FallbackClass)

    def test_reload_regenerates_classes(self):
        """mlib.reload() は登録表を作り直し、保持した生成クラスは新しいラッパーに一致しない。"""
        light = self.makeLight()
        before = mlib.nodes.PointLight
        old_registry = mlib.nodes.Node._registry
        mlib.reload()
        after = mlib.nodes.PointLight
        self.assertIsNot(mlib.nodes.Node._registry, old_registry)
        self.assertIsNot(after, before)
        self.assertEqual(after.__name__, "PointLight")
        self.assertTrue(issubclass(after, mlib.nodes.Shape))
        node = mlib.getNode(light)
        self.assertEqual(type(node).__name__, "PointLight")
        self.assertIsInstance(node, after)
        self.assertNotIsInstance(node, before)
        self.assertEqual(node.getType(), "pointLight")

    def test_native_plugin_round_trip_regenerates_classes(self):
        """Plugin.load/unload の成功後に生成クラスを作り直す(型の認識自体は Maya に従う)。"""
        light = self.makeLight()
        plugin = Plugin("matrixNodes")
        was_loaded = plugin.isLoaded()
        try:
            before = mlib.nodes.PointLight
            plugin.load(quiet=True)
            loaded = mlib.nodes.PointLight
            self.assertIsNot(loaded, before)
            self.assertEqual(type(mlib.nodes.Node(light)).__name__, "PointLight")
            plugin.unload()
            unloaded = mlib.nodes.PointLight
            self.assertIsNot(unloaded, loaded)
            self.assertEqual(type(mlib.nodes.Node(light)).__name__, "PointLight")
            self.assertIsInstance(mlib.nodes.Node(light), unloaded)
        finally:
            if was_loaded and not plugin.isLoaded():
                plugin.load(quiet=True)
            elif not was_loaded and plugin.isLoaded():
                plugin.unload()

    def test_plugin_type_becomes_available_after_load(self):
        """未認識だった型は生成せず、プラグイン導入後の照会で生成する(模擬した照会)。"""
        registry = NodeRegistry(_FallbackClass, generate_classes=True)
        registry.register("transform", _RegisteredClass)
        plugin = Plugin("fixturePlugin")
        chain = ["dependNode", "transform", "optionalNode"]
        with mock.patch.object(cmds, "nodeType", side_effect=[RuntimeError("Unknown node type"), chain, chain]) as query, \
                mock.patch.object(cmds, "loadPlugin", return_value=None), \
                mock.patch.object(Plugin, "isLoaded", return_value=True):
            self.assertIs(registry.wrapper_class("optionalNode"), _FallbackClass)
            first = registry.wrapper_class("optionalNode")
            self.assertEqual(first.__name__, "OptionalNode")
            self.assertIs(first.__mro__[1], _RegisteredClass)
            self.assertIs(registry.wrapper_class("optionalNode"), first)
            self.assertIs(plugin.load(), plugin)
            second = registry.wrapper_class("optionalNode")
            self.assertIsNot(second, first)
            self.assertEqual(second.__name__, "OptionalNode")
        self.assertEqual(query.call_count, 3)

    def test_rejected_plugin_operation_keeps_generated_classes(self):
        """Maya が拒否した load/unload では生成済みクラスを捨てない。"""
        before = mlib.nodes.PointLight
        for operation in ("load", "unload"):
            with self.subTest(operation=operation):
                command = "loadPlugin" if operation == "load" else "unloadPlugin"
                with mock.patch.object(cmds, command, side_effect=RuntimeError("Rejected")):
                    with self.assertRaisesRegex(RuntimeError, "Rejected"):
                        getattr(Plugin("fixturePlugin"), operation)()
                self.assertIs(mlib.nodes.PointLight, before)


class GenericRegistrySpecTest(unittest.TestCase):
    """Maya のクラスを使わない NodeRegistry での生成・従来の継承検索・opt-in を固定する。"""

    def test_generation_uses_nearest_registered_ancestor_or_fallback(self):
        """最寄りの登録祖先型が親、無ければフォールバックが親。認識しない型名は生成しない。"""
        registry = NodeRegistry(_FallbackClass, generate_classes=True)
        registry.register("transform", _RegisteredClass)
        joint = registry.wrapper_class("joint")
        self.assertEqual(joint.__name__, "Joint")
        self.assertIs(joint.__mro__[1], _RegisteredClass)
        self.assertIs(registry.wrapper_class("joint"), joint)
        self.assertIs(registry.get("joint"), joint)
        self.assertIsNone(registry.lookup("joint"))
        network = registry.wrapper_class("network")
        self.assertEqual(network.__name__, "Network")
        self.assertIs(network.__mro__[1], _FallbackClass)
        self.assertIs(registry.wrapper_class("mlibBogusTypeXYZ"), _FallbackClass)
        self.assertEqual(joint(5).value, 5)
        self.assertEqual(joint.__module__, _FallbackClass.__module__)

    def test_registration_takes_precedence_over_generation(self):
        """登録はキャッシュ済みの生成クラスより優先し、生成クラスは捨てる。"""
        registry = NodeRegistry(_FallbackClass, generate_classes=True)
        registry.register("transform", _RegisteredClass)
        generated = registry.wrapper_class("joint")

        class JointClass(_RegisteredClass):
            """登録で差し替えるクラス。"""

        registry.register("joint", JointClass)
        self.assertIs(registry.wrapper_class("joint"), JointClass)
        self.assertNotIn("joint", registry._generated)
        self.assertIsNot(registry.wrapper_class("joint"), generated)

    def test_type_hierarchy_cache_clear_discards_generated_classes(self):
        """_clear_type_hierarchy_cache は生成する全登録表の生成済みクラスを空にする。"""
        registry = NodeRegistry(_FallbackClass, generate_classes=True)
        self.assertIn(registry, registry_module._GENERATING_REGISTRIES)
        first = registry.wrapper_class("joint")
        registry_module._clear_type_hierarchy_cache()
        self.assertEqual(registry._generated, {})
        self.assertIsNot(registry.wrapper_class("joint"), first)
        plain = NodeRegistry(_FallbackClass)
        self.assertNotIn(plain, registry_module._GENERATING_REGISTRIES)

    def test_generation_is_opt_in(self):
        """既定・継承検索のみの表は生成せず、従来どおり祖先クラス自体かフォールバックを返す。"""
        plain = NodeRegistry(_FallbackClass)
        plain.register("transform", _RegisteredClass)
        self.assertIs(plain.wrapper_class("joint"), _FallbackClass)
        inherited = NodeRegistry(_FallbackClass, resolve_inherited_types=True)
        inherited.register("transform", _RegisteredClass)
        self.assertIs(inherited.wrapper_class("joint"), _RegisteredClass)
        self.assertIs(inherited.wrapper_class("network"), _FallbackClass)
        self.assertEqual(inherited._generated, {})
        self.assertFalse(getattr(mlib.plugs.Plug._registry, "_generate_classes"))
        self.assertTrue(mlib.nodes.Node._registry._generate_classes)


class ExtensionPrioritySpecTest(_DynamicTypeCase):
    """拡張(mlib_*)の明示登録が生成より優先し、生成クラスの親にもなることを固定する。"""

    def test_extension_registration_wins_over_generation(self):
        """拡張が pointLight・field を登録すると、生成を置き換え、AirField の親になる。"""
        light = self.makeLight()
        air = self.make("airField")
        with tempfile.TemporaryDirectory(prefix="mlib_dynamic_priority_") as directory:
            name = "mlib_fixture_dynamic_priority"
            folder = Path(directory) / name
            (folder / "nodes").mkdir(parents=True)
            (folder / "__init__.py").write_text(
                "MLIB_EXTENSION_API = 1\ndef is_available(): return True\n", encoding="utf-8")
            (folder / "nodes" / "__init__.py").write_text(
                "from mlib.nodes import Shape, Transform\n"
                "class FixturePointLight(Shape): pass\n"
                "class FixtureField(Transform): pass\n"
                '_WRAPPER_CLASSES = {"pointLight": FixturePointLight, "field": FixtureField}\n',
                encoding="utf-8")
            sys.path.insert(0, directory)
            try:
                importlib.invalidate_caches()
                mlib.reload()
                self.assertEqual(mlib.core.extensions.status()[name]["state"], "loaded")
                registry = mlib.nodes.Node._registry
                self.assertEqual(registry.lookup("pointLight").__name__, "FixturePointLight")
                self.assertEqual(type(mlib.nodes.Node(light)).__name__, "FixturePointLight")
                self.assertEqual(mlib.nodes.PointLight.__name__, "FixturePointLight")
                self.assertFalse(getattr(mlib.nodes.PointLight, "_generated", False))
                air_node = mlib.nodes.Node(air)
                self.assertEqual(type(air_node).__name__, "AirField")
                self.assertEqual(type(air_node).__mro__[1].__name__, "FixtureField")
                self.assertTrue(type(air_node)._generated)
            finally:
                sys.path.remove(directory)
                mlib.reload()
        self.assertEqual(type(mlib.nodes.Node(light)).__name__, "PointLight")
        self.assertTrue(mlib.nodes.PointLight._generated)
        self.assertIs(type(mlib.nodes.Node(air)).__mro__[1], mlib.nodes.Transform)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

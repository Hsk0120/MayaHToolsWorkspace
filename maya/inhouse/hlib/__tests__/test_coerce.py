"""hlib._core.coerce の to_name/to_names/to_node/to_plug を検証するMaya内テスト。"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import hlib
hlib.reload()
from hlib._core.coerce import plug_path, to_name, to_names, to_node, to_node_name, to_plug, unique_node_name
from hlib.components import Vertex, Vertices
from hlib.nodes import Node
from hlib.plugs import ArrayPlug, Plug
from hlib.general.selection import Selection


class CoerceTest(unittest.TestCase):
    """Node/文字列の混在入力を正規化する共通ヘルパーを検証する。"""

    def setUp(self):
        self.created = []

    def tearDown(self):
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)

    def create_transform(self, name):
        node_name = cmds.createNode("transform", name=name)
        self.created.append(node_name)
        return Node(node_name)

    def test_to_name_passes_through_string_without_resolving(self):
        # 存在しない名前でも解決を試みず、そのまま返す。
        self.assertEqual(to_name("doesNotExistYet"), "doesNotExistYet")

    def test_to_name_uses_full_name_for_node(self):
        node = self.create_transform("hlibCoerceToName")
        self.assertEqual(to_name(node), node.full_name())

    def test_to_name_rejects_invalid_types_and_empty_string(self):
        with self.assertRaises(TypeError):
            to_name(123)
        with self.assertRaises(ValueError):
            to_name("")

    def test_to_names_wraps_single_node_or_string(self):
        node = self.create_transform("hlibCoerceToNamesSingle")
        self.assertEqual(to_names(node), [node.full_name()])
        self.assertEqual(to_names("literalName"), ["literalName"])

    def test_to_names_converts_mixed_iterable(self):
        node = self.create_transform("hlibCoerceToNamesMixed")
        result = to_names([node, "literalName"])
        self.assertEqual(result, [node.full_name(), "literalName"])

    def test_to_names_empty_iterable_returns_empty_list(self):
        self.assertEqual(to_names([]), [])

    def test_to_names_propagates_element_errors(self):
        with self.assertRaises(TypeError):
            to_names([123])
        with self.assertRaises(ValueError):
            to_names([""])

    def test_to_node_returns_same_instance_for_node_input(self):
        node = self.create_transform("hlibCoerceToNodeSame")
        self.assertIs(to_node(node), node)

    def test_to_node_resolves_string_to_node(self):
        node = self.create_transform("hlibCoerceToNodeResolve")
        resolved = to_node(node.name())
        self.assertIsInstance(resolved, Node)
        self.assertEqual(resolved.full_name(), node.full_name())

    def test_to_node_rejects_invalid_type(self):
        with self.assertRaises(TypeError):
            to_node(123)

    def test_to_node_raises_when_string_does_not_resolve(self):
        with self.assertRaises(RuntimeError):
            to_node("hlibCoerceDoesNotExist")


class CoerceObjectInputTest(unittest.TestCase):
    """Plug・コンポーネント・om2 オブジェクト・コレクションの正規化を検証する。"""

    def setUp(self):
        self.namespace = "hlibCoerce_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.namespace)
        cmds.namespace(setNamespace=":" + self.namespace)
        self.group = Node(cmds.createNode("transform", name="grp"))
        self.other_group = Node(cmds.createNode("transform", name="otherGrp"))
        # 短い名前が重複するノード(grp|dup と otherGrp|dup)。
        self.node = Node(cmds.createNode("transform", name="dup", parent=self.group.full_name()))
        self.twin = Node(cmds.createNode("transform", name="dup", parent=self.other_group.full_name()))
        self.network = Node(cmds.createNode("network", name="net"))
        self.cube = cmds.polyCube(name="cube", constructionHistory=False)[0]
        self.mesh = Node(self.cube).shape()

    def tearDown(self):
        cmds.namespace(setNamespace=":")
        if cmds.namespace(exists=":" + self.namespace):
            cmds.namespace(removeNamespace=":" + self.namespace, deleteNamespaceContent=True)

    def test_plug_and_mplug_become_unique_plug_names(self):
        plug = self.node.plug("tx")
        expected = self.node.name() + ".translateX"
        self.assertEqual(to_name(plug), expected)
        self.assertEqual(to_name(plug.mplug()), expected)
        # MPlug.name() は短いノード名だけのため同名ノードと区別できない。
        self.assertNotEqual(plug.mplug().name(), expected)
        self.assertEqual(len(cmds.ls(to_name(plug.mplug()))), 1)
        self.assertEqual(plug_path(plug.mplug()), "translateX")
        self.assertEqual(unique_node_name(self.node.mobject()), self.node.name())

    def test_array_plug_is_not_expanded(self):
        self.network.add_attr("values", attribute_type="double", multi=True)
        array_plug = self.network.plug("values")
        array_plug.element(0, create=True).set(1.0)
        self.assertIsInstance(array_plug, ArrayPlug)
        self.assertEqual(to_name(array_plug), self.network.name() + ".values")
        self.assertEqual(to_names(array_plug), [self.network.name() + ".values"])
        self.assertEqual(to_names([array_plug, array_plug[0]]),
                         [self.network.name() + ".values", self.network.name() + ".values[0]"])

    def test_components_are_expanded(self):
        vertex = Vertex(self.mesh, 1)
        vertices = Vertices(self.mesh, [2, 3])
        prefix = self.mesh.full_name() + ".vtx"
        self.assertEqual(to_name(vertex), prefix + "[1]")
        # 連続する番号は範囲指定にまとめる(要素ごとの名前は full_names())。
        self.assertEqual(to_names(vertices), [prefix + "[2:3]"])
        self.assertEqual(vertices.full_names(), [prefix + "[2]", prefix + "[3]"])
        self.assertEqual(to_names([vertex, vertices]), [prefix + "[1]", prefix + "[2:3]"])
        with self.assertRaises(TypeError):
            to_name(vertices)

    def test_compact_names_keep_held_order(self):
        prefix = self.mesh.full_name() + ".vtx"
        vertices = Vertices(self.mesh, [0, 1, 2, 5, 3, 4, 7])
        self.assertEqual(vertices.compact_names(),
                         [prefix + "[0:2]", prefix + "[5]", prefix + "[3:4]", prefix + "[7]"])
        self.assertEqual(Vertices(self.mesh, []).compact_names(), [])
        self.assertEqual(to_names(Vertices(self.mesh, [])), [])
        # 展開した結果は要素ごとの名前と同じ順序・同じ要素になる。
        expanded = cmds.ls(vertices.compact_names(), flatten=True, long=True)
        self.assertEqual(sorted(expanded), sorted(cmds.ls(vertices.full_names(), flatten=True, long=True)))
        everything = Vertices(self.mesh)
        self.assertEqual(to_names(everything), [prefix + "[0:%d]" % (self.mesh.num_vertices() - 1)])
        # 検証はまとめて行い、範囲外の番号を含むコレクションは ValueError になる。
        cmds.polyDelFacet(self.mesh.full_name() + ".f[0:4]")
        with self.assertRaises(ValueError):
            to_names(vertices)

    def test_api_objects(self):
        self.assertEqual(to_name(self.node.mobject()), self.node.full_name())
        self.assertEqual(to_name(self.network.mobject()), self.network.name())
        self.assertEqual(to_name(self.node.dag_path()), self.node.full_name())
        with self.assertRaises(TypeError):
            to_name(self.node.plug("tx").mplug().attribute())
        with self.assertRaises(ValueError):
            to_name(om2.MObject())
        with self.assertRaises(ValueError):
            to_name(om2.MPlug())

    def test_instanced_dag_path_is_preserved(self):
        instance = cmds.instance(self.cube, name="cubeInstance")[0]
        selection = om2.MSelectionList()
        selection.add(instance + "|" + self.mesh.node_name())
        path = selection.getDagPath(0)
        self.assertIn("cubeInstance", to_name(path))
        self.assertEqual(to_name(path), path.fullPathName())

    def test_nested_iterables_selection_and_generators(self):
        vertex = Vertex(self.mesh, 0)
        selection = Selection([self.twin, vertex])
        names = to_names([self.node, [self.twin.mobject(), (item for item in [vertex])], selection])
        self.assertEqual(names, [
            self.node.full_name(), self.twin.full_name(), vertex.full_name(),
            self.twin.full_name(), vertex.full_name(),
        ])

    def test_invalid_objects_raise_value_error(self):
        plug = self.twin.plug("tx")
        mobject = self.twin.mobject()
        path = self.twin.dag_path()
        mplug = plug.mplug()
        vertex = Vertex(self.mesh, 0)
        cmds.delete(self.twin.full_name(), self.cube)
        for value in (self.twin, plug, mobject, path, mplug, vertex):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ValueError):
                    to_name(value)

    def test_to_node_resolves_owners(self):
        plug = self.node.plug("tx")
        self.assertIs(to_node(plug), self.node)
        self.assertEqual(to_node(plug.mplug()).full_name(), self.node.full_name())
        self.assertEqual(to_node(self.node.mobject()).full_name(), self.node.full_name())
        self.assertEqual(to_node(self.node.dag_path()).full_name(), self.node.full_name())
        self.assertIs(to_node(Vertex(self.mesh, 0)), self.mesh)
        self.assertIs(to_node(Vertices(self.mesh, [0, 1])), self.mesh)
        with self.assertRaises(TypeError):
            to_node(Selection([self.node]))

    def test_to_node_rejects_plugs_of_deleted_attributes(self):
        from hlib._core.coerce import DeletedAttributeError

        plug = self.network.add_attr("doomed", attribute_type="double")
        mplug = om2.MPlug(plug.mplug())
        self.assertIs(to_node(plug), self.network)
        self.assertEqual(to_node(mplug).full_name(), self.network.full_name())
        cmds.deleteAttr(self.network.name() + ".doomed")
        # 所有ノードは有効なため、所有ノードを返すと削除済みの対象を黙って受け付けてしまう。
        # to_name と同じく ValueError(Node(...) の規則に合わせ RuntimeError の派生でもある)。
        for value in (plug, mplug):
            for convert in (to_node, to_name, to_node_name):
                with self.subTest(value=type(value).__name__, convert=convert.__name__):
                    with self.assertRaises(ValueError):
                        convert(value)
            with self.assertRaises(DeletedAttributeError) as context:
                to_node(value)
            self.assertIsInstance(context.exception, RuntimeError)
        # 所有ノードが削除済みの Plug は従来どおり無効な所有ノードを返す(扱いは呼び出し側)。
        doomed = self.twin.plug("tx")
        cmds.delete(self.twin.full_name())
        self.assertIs(to_node(doomed), self.twin)
        self.assertFalse(to_node(doomed).is_valid())

    def test_to_node_name_resolves_owner_full_paths(self):
        plug = self.node.plug("tx")
        self.assertEqual(to_node_name(plug), self.node.full_name())
        self.assertEqual(to_node_name(plug.mplug()), self.node.full_name())
        self.assertEqual(to_node_name(plug.full_name()), self.node.full_name())
        self.assertEqual(to_node_name(Vertex(self.mesh, 0)), self.mesh.full_name())
        self.assertEqual(to_node_name(self.network.mobject()), self.network.name())
        with self.assertRaises(TypeError):
            to_node_name(Vertices(self.mesh, [0, 1]))
        with self.assertRaises(RuntimeError):
            to_node_name(self.node.node_name())  # 2つの dup に一致する
        doomed = self.twin.plug("tx")
        cmds.delete(self.twin.full_name())
        with self.assertRaises(ValueError):
            to_node_name(doomed)
        with self.assertRaises(ValueError):
            to_node_name("")

    def test_to_plug(self):
        plug = self.node.plug("tx")
        self.assertIs(to_plug(plug), plug)
        self.assertEqual(to_plug(plug.mplug()).full_name(), plug.full_name())
        self.assertEqual(to_plug(plug.full_name()).full_name(), plug.full_name())
        with self.assertRaises(RuntimeError):
            # 短い名前だけでは2つの dup に一致する(存在しない名前と同じく解決できない)。
            to_plug(self.node.node_name() + ".tx")
        with self.assertRaises(TypeError):
            to_plug(self.node.full_name())
        with self.assertRaises(RuntimeError):
            to_plug(self.node.full_name() + ".hlibCoerceMissing")
        with self.assertRaises(TypeError):
            to_plug(self.node)
        self.assertIsInstance(to_plug(plug.mplug()), Plug)

    def test_to_names_can_reject_plugs(self):
        plug = self.node.plug("tx")
        names = [self.node.full_name(), plug.full_name()]
        self.assertEqual(to_names([self.node, plug]), names)
        for value in (plug, plug.mplug(), [self.node, [plug]], Selection([self.node, plug])):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    to_names(value, allow_plugs=False)
        # 文字列は解決しないため、属性名の文字列はそのまま渡す。
        self.assertEqual(to_names(names, allow_plugs=False), names)

    def test_attribute_path_plug(self):
        from hlib._core.coerce import attribute_path_plug, has_unresolved_index

        average = Node(cmds.createNode("plusMinusAverage", name="pma"))
        mobject = average.mobject()
        cases = {
            "input1D[3]": "input1D[3]",
            "input3D[2].input3Dx": "input3D[2].input3Dx",
            "i3[2].i3y": "input3D[2].input3Dy",
            "output3D": "output3D",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                mplug = attribute_path_plug(mobject, path)
                self.assertEqual(plug_path(mplug), expected)
                self.assertFalse(has_unresolved_index(mplug))
        for path in ("input3Dx", "input1D[0:2]", "missing", "operation[0]", "input1D.foo", "input3D.input3Dx",
                     "input1D[2147483648]", "input1D[4294967296]", "input3D[4294967297].input3Dx"):
            with self.subTest(path=path):
                self.assertIsNone(attribute_path_plug(mobject, path))
        # 論理インデックスの上限(符号付き 32 ビット整数の最大値)までは解決する。
        self.assertEqual(attribute_path_plug(mobject, "input1D[2147483647]").logicalIndex(), 2147483647)
        self.assertEqual(list(average.plug("input1D").mplug().getExistingArrayAttributeIndices()), [])
        cmds.aliasAttr("hlibCoerceAlias", average.name() + ".input1D[4]")
        self.assertEqual(plug_path(attribute_path_plug(mobject, "hlibCoerceAlias")), "hlibCoerceAlias")
        self.assertEqual(attribute_path_plug(mobject, "hlibCoerceAlias").logicalIndex(), 4)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

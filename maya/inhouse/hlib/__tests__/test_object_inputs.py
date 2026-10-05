"""各基底クラスの名前・Node・Plug入力解決 を検証するMaya内テスト。"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.components import Vertex, Vertices
from hlib.nodes import Node
from hlib.plugs import ArrayPlug, Plug
from hlib.scene.selection import Selection


class CoerceTest(unittest.TestCase):
    """Node/文字列の混在入力を正規化する共通ヘルパーを検証する。"""

    def setUp(self):
        self.created = []

    def tearDown(self):
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)

    def create_transform(self, name):
        nodeName = cmds.createNode("transform", name=name)
        self.created.append(nodeName)
        return Node(nodeName)

    def test_to_name_passes_through_string_without_resolving(self):
        # 存在しない名前でも解決を試みず、そのまま返す。
        from hlib.object import Object as _InputObject
        self.assertEqual(_InputObject._input_name("doesNotExistYet"), "doesNotExistYet")

    def test_to_name_uses_full_name_for_node(self):
        from hlib.object import Object as _InputObject
        node = self.create_transform("hlibCoerceToName")
        self.assertEqual(_InputObject._input_name(node), node.fullName())

    def test_to_name_rejects_invalid_types_and_empty_string(self):
        from hlib.object import Object as _InputObject
        with self.assertRaises(TypeError):
            _InputObject._input_name(123)
        with self.assertRaises(ValueError):
            _InputObject._input_name("")

    def test_to_names_wraps_single_node_or_string(self):
        from hlib.object import Object as _InputObject
        node = self.create_transform("hlibCoerceToNamesSingle")
        self.assertEqual(_InputObject._input_names(node), [node.fullName()])
        self.assertEqual(_InputObject._input_names("literalName"), ["literalName"])

    def test_to_names_rejects_mixed_iterable(self):
        from hlib.object import Object as _InputObject
        node = self.create_transform("hlibCoerceToNamesMixed")
        with self.assertRaises(TypeError):
            _InputObject._input_names([node, "literalName"])

    def test_to_names_empty_iterable_returns_empty_list(self):
        from hlib.object import Object as _InputObject
        self.assertEqual(_InputObject._input_names([]), [])

    def test_to_names_propagates_element_errors(self):
        from hlib.object import Object as _InputObject
        with self.assertRaises(TypeError):
            _InputObject._input_names([123])
        with self.assertRaises(ValueError):
            _InputObject._input_names([""])

    def test_to_node_returns_same_instance_for_node_input(self):
        from hlib.nodes.node import Node as _InputNode
        node = self.create_transform("hlibCoerceToNodeSame")
        self.assertIs(_InputNode._resolve_input(node), node)

    def test_to_node_resolves_string_to_node(self):
        from hlib.nodes.node import Node as _InputNode
        node = self.create_transform("hlibCoerceToNodeResolve")
        resolved = _InputNode._resolve_input(node.name())
        self.assertIsInstance(resolved, Node)
        self.assertEqual(resolved.fullName(), node.fullName())

    def test_to_node_rejects_invalid_type(self):
        from hlib.nodes.node import Node as _InputNode
        with self.assertRaises(TypeError):
            _InputNode._resolve_input(123)

    def test_to_node_raises_when_string_does_not_resolve(self):
        from hlib.nodes.node import Node as _InputNode
        with self.assertRaises(RuntimeError):
            _InputNode._resolve_input("hlibCoerceDoesNotExist")


class CoerceObjectInputTest(unittest.TestCase):
    """Plug・コンポーネント・om2 オブジェクト・コレクションの正規化を検証する。"""

    def setUp(self):
        self.namespace = "hlibCoerce_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.namespace)
        cmds.namespace(setNamespace=":" + self.namespace)
        self.group = Node(cmds.createNode("transform", name="grp"))
        self.other_group = Node(cmds.createNode("transform", name="otherGrp"))
        # 短い名前が重複するノード(grp|dup と otherGrp|dup)。
        self.node = Node(cmds.createNode("transform", name="dup", parent=self.group.fullName()))
        self.twin = Node(cmds.createNode("transform", name="dup", parent=self.other_group.fullName()))
        self.network = Node(cmds.createNode("network", name="net"))
        self.cube = cmds.polyCube(name="cube", constructionHistory=False)[0]
        self.mesh = Node(self.cube).shape()

    def tearDown(self):
        cmds.namespace(setNamespace=":")
        if cmds.namespace(exists=":" + self.namespace):
            cmds.namespace(removeNamespace=":" + self.namespace, deleteNamespaceContent=True)

    def test_plug_and_mplug_become_unique_plug_names(self):
        from hlib.nodes.node import Node as _InputNode
        from hlib.object import Object as _InputObject
        from hlib.plugs.plug import Plug as _InputPlug
        plug = self.node.plug("tx")
        expected = self.node.name() + ".translateX"
        self.assertEqual(_InputObject._input_name(plug), expected)
        self.assertEqual(_InputObject._input_name(plug.mplug()), expected)
        # MPlug.name() は短いノード名だけのため同名ノードと区別できない。
        self.assertNotEqual(plug.mplug().name(), expected)
        self.assertEqual(len(cmds.ls(_InputObject._input_name(plug.mplug()))), 1)
        self.assertEqual(_InputPlug._plug_path(plug.mplug()), "translateX")
        self.assertEqual(_InputNode._unique_node_name(self.node.mnode()), self.node.name())

    def test_array_plug_is_not_expanded(self):
        from hlib.object import Object as _InputObject
        self.network.addAttr("values", attributeType="double", multi=True)
        array_plug = self.network.plug("values")
        array_plug[0].set(1.0)
        self.assertIsInstance(array_plug, ArrayPlug)
        self.assertEqual(_InputObject._input_name(array_plug), self.network.name() + ".values")
        self.assertEqual(_InputObject._input_names(array_plug), [self.network.name() + ".values"])
        self.assertEqual(_InputObject._input_names([array_plug, array_plug[0]]),
                         [self.network.name() + ".values", self.network.name() + ".values[0]"])

    def test_components_are_expanded(self):
        from hlib.object import Object as _InputObject
        vertex = Vertex(self.mesh, 1)
        vertices = Vertices(self.mesh, [2, 3])
        prefix = self.mesh.fullName() + ".vtx"
        self.assertEqual(_InputObject._input_name(vertex), prefix + "[1]")
        # 連続する番号は範囲指定にまとめる(要素ごとの名前は fullNames())。
        self.assertEqual(_InputObject._input_names(vertices), [prefix + "[2:3]"])
        self.assertEqual(vertices.fullNames(), [prefix + "[2]", prefix + "[3]"])
        self.assertEqual(_InputObject._input_names([vertex, vertices]), [prefix + "[1]", prefix + "[2:3]"])
        with self.assertRaises(TypeError):
            _InputObject._input_name(vertices)

    def test_compact_names_keep_held_order(self):
        from hlib.object import Object as _InputObject
        prefix = self.mesh.fullName() + ".vtx"
        vertices = Vertices(self.mesh, [0, 1, 2, 5, 3, 4, 7])
        self.assertEqual(vertices.compactNames(),
                         [prefix + "[0:2]", prefix + "[5]", prefix + "[3:4]", prefix + "[7]"])
        self.assertEqual(Vertices(self.mesh, []).compactNames(), [])
        self.assertEqual(_InputObject._input_names(Vertices(self.mesh, [])), [])
        # 展開した結果は要素ごとの名前と同じ順序・同じ要素になる。
        expanded = cmds.ls(vertices.compactNames(), flatten=True, long=True)
        self.assertEqual(sorted(expanded), sorted(cmds.ls(vertices.fullNames(), flatten=True, long=True)))
        everything = Vertices(self.mesh)
        self.assertEqual(_InputObject._input_names(everything), [prefix + "[0:%d]" % (self.mesh.numVertices() - 1)])
        # 検証はまとめて行い、範囲外の番号を含むコレクションは ValueError になる。
        cmds.polyDelFacet(self.mesh.fullName() + ".f[0:4]")
        with self.assertRaises(ValueError):
            _InputObject._input_names(vertices)

    def test_api_objects(self):
        from hlib.object import Object as _InputObject
        self.assertEqual(_InputObject._input_name(self.node.mnode()), self.node.fullName())
        self.assertEqual(_InputObject._input_name(self.network.mnode()), self.network.name())
        self.assertEqual(_InputObject._input_name(self.node.mpath()), self.node.fullName())
        with self.assertRaises(TypeError):
            _InputObject._input_name(self.node.plug("tx").mplug().attribute())
        with self.assertRaises(ValueError):
            _InputObject._input_name(om2.MObject())
        with self.assertRaises(ValueError):
            _InputObject._input_name(om2.MPlug())

    def test_instanced_dag_path_is_preserved(self):
        from hlib.object import Object as _InputObject
        instance = cmds.instance(self.cube, name="cubeInstance")[0]
        selection = om2.MSelectionList()
        selection.add(instance + "|" + self.mesh.nodeName())
        path = selection.getDagPath(0)
        self.assertIn("cubeInstance", _InputObject._input_name(path))
        self.assertEqual(_InputObject._input_name(path), path.fullPathName())

    def test_nested_iterables_selection_and_generators(self):
        from hlib.object import Object as _InputObject
        vertex = Vertex(self.mesh, 0)
        selection = Selection([self.twin, vertex])
        names = _InputObject._input_names([self.node, [self.twin.mnode(), (item for item in [vertex])], selection])
        self.assertEqual(names, [
            self.node.fullName(), self.twin.fullName(), vertex.fullName(),
            self.twin.fullName(), vertex.fullName(),
        ])

    def test_invalid_objects_raise_value_error(self):
        from hlib.object import Object as _InputObject
        plug = self.twin.plug("tx")
        mobject = self.twin.mnode()
        path = self.twin.mpath()
        mplug = plug.mplug()
        vertex = Vertex(self.mesh, 0)
        cmds.delete(self.twin.fullName(), self.cube)
        for value in (self.twin, plug, mobject, path, mplug, vertex):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(ValueError):
                    _InputObject._input_name(value)

    def test_to_node_resolves_owners(self):
        from hlib.nodes.node import Node as _InputNode
        plug = self.node.plug("tx")
        self.assertIs(_InputNode._resolve_input(plug), self.node)
        self.assertEqual(_InputNode._resolve_input(plug.mplug()).fullName(), self.node.fullName())
        self.assertEqual(_InputNode._resolve_input(self.node.mnode()).fullName(), self.node.fullName())
        self.assertEqual(_InputNode._resolve_input(self.node.mpath()).fullName(), self.node.fullName())
        self.assertIs(_InputNode._resolve_input(Vertex(self.mesh, 0)), self.mesh)
        self.assertIs(_InputNode._resolve_input(Vertices(self.mesh, [0, 1])), self.mesh)
        with self.assertRaises(TypeError):
            _InputNode._resolve_input(Selection([self.node]))

    def test_to_node_rejects_plugs_of_deleted_attributes(self):
        from hlib.nodes.node import Node as _InputNode
        from hlib.object import Object as _InputObject
        from hlib.plugs.plug import DeletedAttributeError

        plug = self.network.addAttr("doomed", attributeType="double")
        mplug = om2.MPlug(plug.mplug())
        self.assertIs(_InputNode._resolve_input(plug), self.network)
        self.assertEqual(_InputNode._resolve_input(mplug).fullName(), self.network.fullName())
        cmds.deleteAttr(self.network.name() + ".doomed")
        # 所有ノードは有効なため、所有ノードを返すと削除済みの対象を黙って受け付けてしまう。
        # to_name と同じく ValueError(Node(...) の規則に合わせ RuntimeError の派生でもある)。
        for value in (plug, mplug):
            for convert in (_InputNode._resolve_input, _InputObject._input_name, _InputNode._input_name):
                with self.subTest(value=type(value).__name__, convert=convert.__name__):
                    with self.assertRaises(ValueError):
                        convert(value)
            with self.assertRaises(DeletedAttributeError) as context:
                _InputNode._resolve_input(value)
            self.assertIsInstance(context.exception, RuntimeError)
        # 所有ノードが削除済みの Plug は従来どおり無効な所有ノードを返す(扱いは呼び出し側)。
        doomed = self.twin.plug("tx")
        cmds.delete(self.twin.fullName())
        self.assertIs(_InputNode._resolve_input(doomed), self.twin)
        self.assertFalse(_InputNode._resolve_input(doomed).isValid())

    def test_to_node_name_resolves_owner_full_paths(self):
        from hlib.nodes.node import Node as _InputNode
        plug = self.node.plug("tx")
        self.assertEqual(_InputNode._input_name(plug), self.node.fullName())
        self.assertEqual(_InputNode._input_name(plug.mplug()), self.node.fullName())
        self.assertEqual(_InputNode._input_name(plug.fullName()), self.node.fullName())
        self.assertEqual(_InputNode._input_name(Vertex(self.mesh, 0)), self.mesh.fullName())
        self.assertEqual(_InputNode._input_name(self.network.mnode()), self.network.name())
        with self.assertRaises(TypeError):
            _InputNode._input_name(Vertices(self.mesh, [0, 1]))
        with self.assertRaises(RuntimeError):
            _InputNode._input_name(self.node.nodeName())  # 2つの dup に一致する
        doomed = self.twin.plug("tx")
        cmds.delete(self.twin.fullName())
        with self.assertRaises(ValueError):
            _InputNode._input_name(doomed)
        with self.assertRaises(ValueError):
            _InputNode._input_name("")

    def test_to_plug(self):
        from hlib.plugs.plug import Plug as _InputPlug
        plug = self.node.plug("tx")
        self.assertIs(_InputPlug._resolve_input(plug), plug)
        self.assertEqual(_InputPlug._resolve_input(plug.mplug()).fullName(), plug.fullName())
        self.assertEqual(_InputPlug._resolve_input(plug.fullName()).fullName(), plug.fullName())
        with self.assertRaises(RuntimeError):
            # 短い名前だけでは2つの dup に一致する(存在しない名前と同じく解決できない)。
            _InputPlug._resolve_input(self.node.nodeName() + ".tx")
        with self.assertRaises(TypeError):
            _InputPlug._resolve_input(self.node.fullName())
        with self.assertRaises(RuntimeError):
            _InputPlug._resolve_input(self.node.fullName() + ".hlibCoerceMissing")
        with self.assertRaises(TypeError):
            _InputPlug._resolve_input(self.node)
        self.assertIsInstance(_InputPlug._resolve_input(plug.mplug()), Plug)

    def test_to_names_can_reject_plugs(self):
        from hlib.object import Object as _InputObject
        plug = self.node.plug("tx")
        names = [self.node.fullName(), plug.fullName()]
        self.assertEqual(_InputObject._input_names([self.node, plug]), names)
        for value in (plug, plug.mplug(), [self.node, [plug]], Selection([self.node, plug])):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    _InputObject._input_names(value, allow_plugs=False)
        # 文字列は解決しないため、アトリビュート名の文字列はそのまま渡す。
        self.assertEqual(_InputObject._input_names(names, allow_plugs=False), names)

    def test_attribute_path_plug(self):
        from hlib.plugs.plug import Plug as _InputPlug

        average = Node(cmds.createNode("plusMinusAverage", name="pma"))
        mobject = average.mnode()
        cases = {
            "input1D[3]": "input1D[3]",
            "input3D[2].input3Dx": "input3D[2].input3Dx",
            "i3[2].i3y": "input3D[2].input3Dy",
            "output3D": "output3D",
        }
        for path, expected in cases.items():
            with self.subTest(path=path):
                mplug = _InputPlug._attribute_path_plug(mobject, path)
                self.assertEqual(_InputPlug._plug_path(mplug), expected)
                self.assertFalse(_InputPlug._has_unresolved_index(mplug))
        for path in ("input3Dx", "input1D[0:2]", "missing", "operation[0]", "input1D.foo", "input3D.input3Dx",
                     "input1D[2147483648]", "input1D[4294967296]", "input3D[4294967297].input3Dx"):
            with self.subTest(path=path):
                self.assertIsNone(_InputPlug._attribute_path_plug(mobject, path))
        # 論理インデックスの上限(符号付き 32 ビット整数の最大値)までは解決する。
        self.assertEqual(_InputPlug._attribute_path_plug(mobject, "input1D[2147483647]").logicalIndex(), 2147483647)
        self.assertEqual(list(average.plug("input1D").mplug().getExistingArrayAttributeIndices()), [])
        cmds.aliasAttr("hlibCoerceAlias", average.name() + ".input1D[4]")
        self.assertEqual(_InputPlug._plug_path(_InputPlug._attribute_path_plug(mobject, "hlibCoerceAlias")), "hlibCoerceAlias")
        self.assertEqual(_InputPlug._attribute_path_plug(mobject, "hlibCoerceAlias").logicalIndex(), 4)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

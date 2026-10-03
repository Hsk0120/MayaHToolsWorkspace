"""maya.cmds との受け渡しの正式仕様(docs/cmds_interop.rst)をMaya内で検証する。

- hlib のオブジェクト(Node・Plug・Component・コレクション)は ``str()`` で
  maya.cmds が一意に解決できる名前を返し、maya.cmds へそのまま渡せる。
- 短い名前が重複するノード(``grp1|dup`` と ``grp2|dup``)の Plug も一意に扱える。
- hlib のコマンドは Plug・コンポーネント・om2 オブジェクトも受け付ける。

各テストは専用の一時ネームスペースを現在のネームスペースにして作成し、
tearDown でネームスペースごと削除する。
"""
from maya.api.OpenMaya import MSpace

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds
import maya.mel as mel

import hlib

hlib.reload()
from hlib._core.attributeType import attributeType, is_internal_data_type
from hlib.components import Faces, Vertex, Vertices
from hlib.maths import EulerRotation, Translation
from hlib.nodes import Joint, Joints, Mesh, Node
from hlib.plugs import ArrayPlug, CompoundPlug, Plug
from hlib.scene.selection import Selection


class _InteropCase(unittest.TestCase):
    """一時ネームスペースを現在のネームスペースにして検証する基底クラス。"""

    def setUp(self):
        self.namespace = "hlibInterop_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.namespace)
        cmds.namespace(setNamespace=":" + self.namespace)
        cmds.select(clear=True)

    def tearDown(self):
        cmds.namespace(setNamespace=":")
        cmds.select(clear=True)
        if cmds.namespace(exists=":" + self.namespace):
            cmds.namespace(removeNamespace=":" + self.namespace, deleteNamespaceContent=True)

    def ns(self, name):
        """一時ネームスペース付きの名前を返す。"""
        return self.namespace + ":" + name

    def create(self, node_type, name, parent=None):
        """ノードを作成して hlib のラッパーを返す。"""
        kwargs = {"name": name}
        if parent is not None:
            kwargs["parent"] = parent.fullName()
        return Node(cmds.createNode(node_type, **kwargs))

    def duplicates(self):
        """短い名前が重複する grp1|dup と grp2|dup を作成する。"""
        grp1 = self.create("transform", "grp1")
        grp2 = self.create("transform", "grp2")
        return self.create("transform", "dup", grp1), self.create("transform", "dup", grp2)

    def cube(self, name="cube"):
        """構築履歴なしの立方体の Transform と Mesh を返す。"""
        transform = Node(cmds.polyCube(name=name, constructionHistory=False)[0])
        return transform, transform.shape()


class DuplicateShortNameTest(_InteropCase):
    """短い名前が重複するノードの Plug を一意に扱えることを検証する。"""

    def test_plugs_resolve_with_unique_names(self):
        dup1, dup2 = self.duplicates()
        self.assertEqual(dup1.nodeName(), dup2.nodeName())
        expected = {
            "tx": ("DoubleLinearPlug", "translateX"),
            "t": ("Double3Plug", "translate"),
            "v": ("BoolPlug", "visibility"),
        }
        for attribute, (class_name, longName) in expected.items():
            with self.subTest(attribute=attribute):
                plug = dup1.plug(attribute)
                self.assertEqual(type(plug).__name__, class_name)
                self.assertEqual(str(plug), self.ns("grp1|") + self.ns("dup.") + longName)
                self.assertEqual(plug.fullName(), str(plug))
                self.assertEqual(len(cmds.ls(str(plug))), 1)
        world = dup1.plug("worldMatrix")
        self.assertIsInstance(world, ArrayPlug)
        element = world.element(0)
        self.assertEqual(type(element).__name__, "MatrixPlug")
        self.assertEqual(str(element), dup1.name() + ".worldMatrix[0]")
        self.assertEqual(world[0].fullName(), element.fullName())

    def test_cmds_get_and_set_single_values(self):
        dup1, dup2 = self.duplicates()
        cmds.setAttr(dup1.plug("tx"), 3.0)
        # 一意な名前のため、単一の値が返る(複数一致のリストやエラーにならない)。
        self.assertEqual(cmds.getAttr(dup1.plug("tx")), 3.0)
        self.assertEqual(cmds.getAttr(dup2.plug("tx")), 0.0)
        cmds.setAttr(dup2.plug("t"), *Translation(1.0, 2.0, 3.0))
        self.assertEqual(cmds.getAttr(dup2.plug("t")), [(1.0, 2.0, 3.0)])
        self.assertEqual(dup1.plug("tx").get(), 3.0)
        dup2.plug("v").set(False)
        self.assertFalse(cmds.getAttr(str(dup2.plug("v"))))
        self.assertTrue(cmds.getAttr(str(dup1.plug("v"))))
        matrix = cmds.getAttr(dup1.plug("worldMatrix").element(0))
        self.assertEqual(len(matrix), 16)
        self.assertAlmostEqual(matrix[12], 3.0)
        self.assertAlmostEqual(cmds.getAttr(dup2.plug("worldMatrix").element(0))[13], 2.0)

    def test_connections_between_duplicates(self):
        dup1, dup2 = self.duplicates()
        source = self.create("transform", "source")
        source.plug("tx").connect(dup1.plug("tx"))
        source.plug("tx").connect(dup2.plug("tx"))
        # 以前は MPlug.name() による重複判定で2件目が失われていた。
        self.assertEqual(
            sorted(plug.fullName() for plug in source.outputs()),
            sorted([dup1.name() + ".translateX", dup2.name() + ".translateX"]),
        )
        self.assertTrue(cmds.isConnected(source.plug("tx"), dup2.plug("tx")))
        self.assertTrue(dup1.plug("tx").isConnectedTo(source.plug("tx")))
        dup2.plug("tx").disconnect()
        self.assertFalse(cmds.isConnected(str(source.plug("tx")), str(dup2.plug("tx"))))
        self.assertEqual(dup1.plug("tx").source().fullName(), source.name() + ".translateX")
        # 接続先に MPlug や一意なアトリビュート名も指定できる。
        source.plug("ty").connect(dup2.plug("ty").mplug())
        source.plug("tz").connect(dup2.plug("tz").fullName())
        self.assertTrue(cmds.isConnected(source.plug("ty"), dup2.plug("ty")))
        self.assertTrue(cmds.isConnected(source.plug("tz"), dup2.plug("tz")))

    def test_selection_with_duplicate_short_names(self):
        dup1, dup2 = self.duplicates()
        selection = Selection(
            [dup1.plug("tx"), dup2.plug("tx"), dup1.name() + ".ty", dup2.plug("tz").mplug()]
        )
        self.assertEqual(len(selection.plugs()), 4)
        self.assertEqual(len({plug.fullName() for plug in selection.plugs()}), 4)
        selection.select()
        self.assertEqual(len(cmds.ls(selection=True)), 4)
        captured = Selection([om2.MGlobal.getActiveSelectionList()])
        self.assertEqual(
            {plug.fullName() for plug in captured.plugs()},
            {plug.fullName() for plug in selection.plugs()},
        )

    def test_unresolved_index_plug_is_still_rejected(self):
        from hlib.plugs.plug import Plug as _InputPlug
        _, mesh = self.cube()
        # 要素を指定した名前は解決でき、アトリビュート型はアトリビュート定義から求める(要素は作らない)。
        name = mesh.name() + ".instObjGroups[0].objectGroups[0].objectGrpCompList"
        resolved = _InputPlug._resolve_input(name)
        self.assertEqual(attributeType(resolved.mplug()), "componentList")
        self.assertEqual(resolved.fullName(), name)
        self.assertEqual(
            mesh.plug("instObjGroups[0].objectGroups[0].objectGrpCompList").fullName(), name
        )
        # 要素を指定しない子は cmp[-1].child のような maya.cmds で解決できないプラグになるため拒否する。
        # 配列複合アトリビュートの子の配列(cmp[-1].childArray)も同じ(ArrayPlug でも str() を解決できない)。
        for name in ("objectGrpCompList", "objectGroups"):
            with self.subTest(name=name):
                with self.assertRaises(RuntimeError):
                    mesh.plug(name)
                self.assertFalse(mesh.hasAttribute(name))
        self.assertEqual(
            mesh.plug("instObjGroups[0].objectGroups").fullName(),
            mesh.name() + ".instObjGroups[0].objectGroups",
        )
        # plugs() は未確定のインデックスを含むプラグを含まない(配列 Plug を含め、すべて解決できる)。
        plugs = mesh.plugs()
        self.assertTrue(any(plug.isArray() for plug in plugs))
        self.assertFalse(any("[-1]" in plug.mplug().name() for plug in plugs))

    def test_display_layer_members_with_duplicate_names(self):
        dup1, dup2 = self.duplicates()
        layer = hlib.getNode(cmds.createDisplayLayer(name="lay", empty=True))
        layer.addMembers(dup1, dup2)
        # editDisplayLayerMembers の既定の問い合わせは葉の名前('dup')だけを返すため、
        # 完全パスで受け取って解決する。
        self.assertEqual(
            sorted(member.fullName() for member in layer.members()),
            sorted([dup1.fullName(), dup2.fullName()]),
        )


class NamingSpecTest(_InteropCase):
    """名前の追従・ネームスペース・入れ子の配列・インスタンスを検証する。"""

    def test_names_follow_rename_and_reparent(self):
        group = self.create("transform", "grp")
        node = self.create("transform", "item")
        plug = node.plug("tx")
        cmds.rename(node, ":" + self.ns("renamed"))
        self.assertEqual(str(node), self.ns("renamed"))
        self.assertEqual(str(plug), self.ns("renamed.translateX"))
        cmds.parent(node, group)
        other = self.create("transform", "renamed")
        # 同名ノードができると最短一意名はパスになる。
        self.assertEqual(str(node), self.ns("grp|") + self.ns("renamed"))
        self.assertEqual(str(plug), self.ns("grp|") + self.ns("renamed.translateX"))
        cmds.setAttr(plug, 2.0)
        self.assertEqual(node.plug("tx").get(), 2.0)
        self.assertEqual(other.plug("tx").get(), 0.0)

    def test_namespace_and_dg_node_names(self):
        node = self.create("transform", "nsNode")
        self.assertEqual(str(node), self.ns("nsNode"))
        self.assertEqual(str(node.plug("tx")), self.ns("nsNode.translateX"))
        network = self.create("network", "net")
        network.addAttribute("values", attributeType="double", multi=True)
        element = network.plug("values").element(3, create=True)
        self.assertEqual(str(element), self.ns("net.values[3]"))
        cmds.setAttr(element, 1.5)
        self.assertEqual(element.get(), 1.5)
        self.assertEqual(network.plug("values").get(), {3: 1.5})

    def test_nested_multi_compound_child(self):
        _, mesh = self.cube()
        element = mesh.plug("pnts").element(2, create=True)
        self.assertIsInstance(element, CompoundPlug)
        child = element.child("pntx")
        self.assertEqual(str(child), mesh.name() + ".pnts[2].pntx")
        cmds.setAttr(child, 0.25)
        self.assertAlmostEqual(cmds.getAttr(child), 0.25)
        self.assertAlmostEqual(child.get(), 0.25)
        self.assertAlmostEqual(cmds.getAttr(element)[0][0], 0.25)

    def test_instanced_shape(self):
        transform, _ = self.cube()
        instance = cmds.instance(transform, name="cubeInstance")[0]
        shape = Node(cmds.listRelatives(instance, shapes=True, fullPath=True)[0])
        self.assertIn("cubeInstance", shape.fullName())
        elements = shape.plug("worldMatrix").elements()
        self.assertEqual([element.mplug().logicalIndex() for element in elements], [0, 1])
        cmds.setAttr(instance + ".tx", 5.0)
        for element in elements:
            self.assertIn("|", str(element).split(".")[0])
            self.assertEqual(len(cmds.ls(str(element))), 1)
        self.assertAlmostEqual(cmds.getAttr(elements[1])[12], 5.0)
        self.assertAlmostEqual(cmds.getAttr(elements[0])[12], 0.0)
        vertex = Vertex(shape, 0)
        self.assertAlmostEqual(
            cmds.xform(vertex, query=True, worldSpace=True, translation=True)[0], 4.5
        )

    def test_invalid_node_names_are_empty(self):
        node = self.create("transform", "doomed")
        plug = node.plug("tx")
        cmds.delete(node)
        self.assertEqual(str(node), "")
        self.assertEqual(str(plug), "")
        self.assertEqual(plug.name(), "")
        self.assertEqual(repr(plug), "<Plug invalid>")

    def test_plug_names_equal_node_name_and_attribute_path(self):
        # fullName() は短い名前が一意なノードで MPlug.name() をそのまま返す(高速経路)。
        # どのノード・アトリビュートでも「Node.name() + '.' + アトリビュートパス」と同じ名前になること。
        from hlib.plugs.plug import Plug as _InputPlug

        transform, mesh = self.cube()
        cmds.setAttr(mesh.name() + ".pnts[2].pntx", 1.0)
        cmds.aliasAttr("myAlias", transform.name() + ".ty")
        base = cmds.polyCube(name="base")[0]
        target = cmds.polyCube(name="target")[0]
        blend = hlib.getNode(cmds.blendShape(target, base, name="blend")[0])
        average = self.create("plusMinusAverage", "pma")
        cmds.setAttr(average.name() + ".input3D[3].input3Dx", 1.0)
        dup1, dup2 = self.duplicates()
        box, _ = self.cube("box")
        instance = cmds.instance(box.fullName(), name="box1")[0]
        instanced = Node(cmds.listRelatives(instance, shapes=True, fullPath=True)[0])
        underworld = hlib.createNode("transform", name="under", parent=mesh)  # cubeShape->under
        self.assertIn("->", underworld.name())
        checked = 0
        for node in (
            transform,
            mesh,
            blend,
            average,
            dup1,
            dup2,
            instanced,
            underworld,
            Node("time1"),
        ):
            names = cmds.listAttr(node.fullName(), multi=True) or []
            plugs = []
            for name in names:
                try:
                    plugs.append(node.plug(name))
                except (AttributeError, RuntimeError):
                    continue
            plugs.extend(instanced.plug("worldMatrix").elements() if node is instanced else [])
            for plug in plugs:
                with self.subTest(plug=plug.fullName()):
                    self.assertEqual(plug.fullName(), node.name() + "." + _InputPlug._plug_path(plug.mplug()))
                    checked += 1
        self.assertGreater(checked, 500)
        self.assertEqual(str(transform.plug("ty")), transform.name() + ".myAlias")
        self.assertEqual(str(blend.plug("weight[0]")), blend.name() + ".target")
        self.assertIn("|", str(instanced.plug("castsShadows")).split(".")[0])


class PassToMayaCmdsTest(_InteropCase):
    """hlib のオブジェクトを maya.cmds へそのまま渡せることを検証する。"""

    def test_nodes_plugs_and_components(self):
        parent = self.create("transform", "parent")
        child = self.create("transform", "child")
        cmds.parent(child, parent)
        self.assertEqual(
            cmds.listRelatives(child, parent=True, fullPath=True), [parent.fullName()]
        )
        created = cmds.createNode("transform", name="created", parent=parent)
        self.assertEqual(
            cmds.listRelatives(created, parent=True, fullPath=True), [parent.fullName()]
        )
        cmds.xform(child, translation=(1.0, 2.0, 3.0))
        self.assertEqual(cmds.xform(child, query=True, translation=True), [1.0, 2.0, 3.0])
        cmds.connectAttr(parent.plug("tx"), child.plug("ty"))
        self.assertTrue(cmds.isConnected(parent.plug("tx"), child.plug("ty")))
        self.assertEqual(cmds.getAttr(child.plug("ty")), 0.0)

        _, mesh = self.cube()
        vertex = Vertex(mesh, 0)
        vertices = Vertices(mesh, [1, 2])
        cmds.select(vertex)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 1)
        cmds.select(vertices)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 2)
        cmds.select([child, parent.plug("tx"), vertex])
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 3)
        cmds.select(Selection([child, vertex]))
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 2)
        cmds.xform(vertex, worldSpace=True, translation=(0.0, 5.0, 0.0))
        self.assertAlmostEqual(vertex.getPosition(space=MSpace.kWorld)[1], 5.0)

        joints = Joints(
            [cmds.createNode("joint", name="jointA"), cmds.createNode("joint", name="jointB")]
        )
        cmds.select(joints)
        self.assertEqual(len(cmds.ls(selection=True)), 2)

    def test_objects_that_cannot_be_passed_directly(self):
        network = self.create("network", "net")
        network.addAttribute("values", attributeType="double", multi=True)
        array_plug = network.plug("values")
        array_plug.element(0, create=True).set(1.0)
        array_plug.element(2, create=True).set(3.0)
        # ArrayPlug は [] で要素を返すため maya.cmds がシーケンスとして扱い失敗する。
        with self.assertRaises((TypeError, ValueError, RuntimeError)):
            cmds.getAttr(array_plug, size=True)
        self.assertEqual(cmds.getAttr(str(array_plug), size=True), 2)
        self.assertEqual(cmds.getAttr(array_plug.fullName(), size=True), 2)
        # om2.MObject の str() は repr のため名前として解決できない。
        with self.assertRaises((TypeError, ValueError, RuntimeError)):
            cmds.select(network.mobject())
        # hlib のコマンドはどちらも受け付ける。
        self.assertTrue(cmds.objExists(str(array_plug)))
        hlib.select(network.mobject())
        self.assertEqual(cmds.ls(selection=True), [network.name()])

    def test_maths_values(self):
        node = self.create("transform", "node")
        rotation = EulerRotation.fromDegrees(10.0, 20.0, 30.0)
        # 回転成分はラジアン。度を受け取る maya.cmds のフラグには asDegrees() を使う。
        cmds.xform(node, rotation=rotation.asDegrees())
        self.assertAlmostEqual(cmds.getAttr(node.plug("rx")), 10.0)
        self.assertAlmostEqual(cmds.getAttr(node.plug("rz")), 30.0)
        # double3 の setAttr は成分を * で展開する。
        cmds.setAttr(node.plug("t"), *Translation(1.0, 2.0, 3.0))
        self.assertEqual(cmds.getAttr(node.plug("t")), [(1.0, 2.0, 3.0)])


class HlibCommandInputTest(_InteropCase):
    """hlib のコマンドが Plug・コンポーネント・om2 オブジェクトを受け付けることを検証する。"""

    def test_select(self):
        dup1, dup2 = self.duplicates()
        _, mesh = self.cube()
        vertex = Vertex(mesh, 0)
        vertices = Vertices(mesh, [1, 2])
        cases = [
            (dup1.plug("tx"), [dup1.plug("tx").fullName()]),
            (dup1.plug("tx").mplug(), [dup1.plug("tx").fullName()]),
            (dup1.mobject(), [dup1.name()]),
            (dup2.dagPath(), [dup2.name()]),
        ]
        for value, expected in cases:
            with self.subTest(value=type(value).__name__):
                hlib.select(value)
                self.assertEqual(cmds.ls(selection=True), expected)
        hlib.select(vertex)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 1)
        hlib.select(vertices)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 2)
        hlib.select(Selection([dup1, vertex]))
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 2)
        hlib.select([dup1, [dup2.mobject(), (item for item in [vertex])], vertices])
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 5)
        hlib.select([])
        self.assertEqual(cmds.ls(selection=True), [])
        with self.assertRaises(TypeError):
            hlib.select([object()])
        with self.assertRaises(TypeError):
            hlib.select(dup1.plug("tx").mplug().attribute())

    def test_delete(self):
        _, mesh = self.cube()
        hlib.delete(Faces(mesh, [0, 1]))
        self.assertEqual(mesh.numPolygons(), 4)
        a = self.create("transform", "a")
        b = self.create("transform", "b")
        c = self.create("transform", "c")
        hlib.delete([a.mobject(), b.dagPath()])
        hlib.delete(c.plug("tx").mplug().node())
        for node in (a, b, c):
            self.assertFalse(node.isValid())
        with self.assertRaises(ValueError):
            hlib.delete([])
        # maya.cmds.delete はアトリビュート名を渡してもエラーを表示するだけで何もしないため、Plug は拒否する。
        d = self.create("transform", "d")
        d.addAttribute("values", attributeType="double", multi=True)
        for value in (
            d.plug("tx"),
            d.plug("tx").mplug(),
            d.plug("values"),
            [d, d.plug("ty")],
            Selection([d, d.plug("tz")]),
        ):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    hlib.delete(value)
                self.assertTrue(d.isValid())
        hlib.delete(d.plug("tx").node)
        self.assertFalse(d.isValid())

    def test_blend_shape_add_target_resolves_owner_nodes(self):
        base = cmds.polyCube(name="base")[0]
        first = cmds.polyCube(name="first")[0]
        second = cmds.polyCube(name="second")[0]
        blend = hlib.getNode(cmds.blendShape(first, base, name="blend")[0])
        # Plug・"node.attribute" は所有ノードをターゲット・ベースとして扱う。
        weight = blend.addTarget(
            hlib.getNode(second).plug("tx"), base=hlib.getNode(base).shape().plug("v")
        )
        self.assertEqual(weight.fullName(), blend.name() + ".second")
        third = cmds.polyCube(name="third")[0]
        weight = blend.addTarget(third + ".translateX")
        self.assertEqual(weight.fullName(), blend.name() + ".third")

    def test_ls_group_duplicate_and_createNode(self):
        a = self.create("transform", "a")
        b = self.create("transform", "b")
        result = hlib.ls(a.mobject(), [b.dagPath()])
        self.assertEqual([node.fullName() for node in result], [a.fullName(), b.fullName()])
        self.assertEqual(hlib.ls([]), [])
        self.assertEqual(len(hlib.ls([], type="joint")), 0)
        self.assertEqual([node.fullName() for node in hlib.ls(self.ns("a"))], [a.fullName()])

        child = hlib.createNode("transform", name="child", parent=a.mobject())
        self.assertEqual(child.parentNode().fullName(), a.fullName())
        child2 = hlib.createNode("transform", name="child2", p=b.dagPath())
        self.assertEqual(child2.parentNode().fullName(), b.fullName())
        group = hlib.createGroup([child.mobject(), child2], name="grp", parent=a)
        self.assertEqual(group.parentNode().fullName(), a.fullName())
        self.assertEqual(child2.parentNode().fullName(), group.fullName())
        copy = hlib.duplicate(b.dagPath(), name="bCopy")
        self.assertTrue(copy.isValid())
        self.assertNotEqual(copy.fullName(), b.fullName())

    def test_setKeyframe_and_drivenKey(self):
        node = self.create("transform", "keyed")
        cmds.setKeyframe(node.plug("tx"), time=1, value=2.0)
        self.assertEqual(cmds.keyframe(node.plug("tx"), query=True, valueChange=True), [2.0])
        cmds.setKeyframe([node.plug("ty"), node.plug("tz")], time=1)
        self.assertEqual(cmds.keyframe(node.plug("ty"), query=True, keyframeCount=True), 1)
        self.assertEqual(cmds.keyframe(node.plug("tz"), query=True, keyframeCount=True), 1)

        driver = self.create("transform", "driver")
        driven = self.create("transform", "driven")
        relation = hlib.getDrivenKey(driver.plug("tx").mplug(), driven.plug("ty"))
        relation.setKey(0.0, 0.0)
        relation.setKey(1.0, 2.0)
        self.assertTrue(relation.exists())
        driver.plug("tx").set(1.0)
        self.assertAlmostEqual(driven.plug("ty").get(), 2.0)

    def test_constraint_resolves_owner_nodes(self):
        source = self.create("transform", "source")
        target = self.create("transform", "target")
        constraint = hlib.addConstraint(source.plug("tx"), target.mobject(), type="point")
        self.assertEqual(
            [
                Node(name).fullName()
                for name in cmds.pointConstraint(constraint, query=True, targetList=True)
            ],
            [source.fullName()],
        )
        other = self.create("transform", "other")
        target.addConstraint([other.dagPath()], "orient")
        self.assertTrue(target.plug("rx").isDestination())

    def test_node_constructor_accepts_wrappers(self):
        joint = Node(cmds.createNode("joint", name="jnt"))
        copy = Node(joint)
        self.assertIsNot(copy, joint)
        self.assertIsInstance(copy, Joint)
        self.assertEqual(copy.fullName(), joint.fullName())
        self.assertIsInstance(Node(joint.plug("tx")), Joint)
        self.assertEqual(Node(joint.plug("tx").mplug()).fullName(), joint.fullName())
        self.assertEqual(hlib.getNode(joint.plug("tx")).fullName(), joint.fullName())
        self.assertEqual(Node(joint.name() + ".tx").fullName(), joint.fullName())
        _, mesh = self.cube()
        self.assertIsInstance(Node(Vertex(mesh, 0)), Mesh)
        transform, _ = self.cube("instanced")
        instance = cmds.instance(transform, name="instancedCopy")[0]
        instanced_shape = Node(cmds.listRelatives(instance, shapes=True, fullPath=True)[0])
        self.assertEqual(Node(instanced_shape).fullName(), instanced_shape.fullName())
        cmds.delete(joint)
        with self.assertRaises(RuntimeError):
            Node(copy)
        with self.assertRaises(TypeError):
            Node(12345)


class NodeArgumentRulesTest(_InteropCase):
    """ノードが必要な引数(parent・constraint の target・Node(...))の規則を検証する。"""

    def test_createNode_parent_resolves_owner_node(self):
        group = hlib.createNode("transform", name="g")
        expected_parent = group.fullName()
        # maya.cmds.createNode はプラグ名の parent を黙って無視してワールド直下に作るが、
        # hlib は所有ノードを親にする。
        for index, parent in enumerate(
            [
                group.plug("tx"),
                group.plug("tx").mplug(),
                group.plug("worldMatrix"),
                group.name() + ".translateX",
                group.plug("worldMatrix").element(0),
            ]
        ):
            with self.subTest(parent=type(parent).__name__):
                created = hlib.createNode("transform", name="k%d" % index, parent=parent)
                self.assertEqual(created.parentNode().fullName(), expected_parent)
        child = Node.create("transform", name="viaCreate", p=group.plug("ty"))
        self.assertEqual(child.parentNode().fullName(), expected_parent)
        # Component は所有シェイプを親にする(シェイプを直接指定した場合と同じ配置)。
        _, mesh = self.cube()
        by_shape = hlib.createNode("transform", name="byShape", parent=mesh)
        by_vertex = hlib.createNode("transform", name="byVertex", parent=Vertex(mesh, 0))
        self.assertTrue(by_shape.fullName().startswith(mesh.fullName() + "->"))
        self.assertTrue(by_vertex.fullName().startswith(mesh.fullName() + "->"))
        doomed = hlib.createNode("transform", name="doomed")
        doomed_plug = doomed.plug("tx")
        cmds.delete(doomed)
        with self.assertRaises(ValueError):
            hlib.createNode("transform", name="orphan", parent=doomed_plug)
        with self.assertRaises(TypeError):
            hlib.createNode("transform", name="many", parent=Vertices(mesh, [0, 1]))

    def test_group_parent_and_empty_input(self):
        group = hlib.createNode("transform", name="g")
        item = hlib.createNode("transform", name="item")
        result = hlib.createGroup([item], name="G", parent=group.plug("tx"))
        self.assertEqual(result.parentNode().fullName(), group.fullName())
        # 空の列で maya.cmds.group が現在の選択をグループ化しないこと。
        selected = hlib.createNode("transform", name="selected")
        cmds.select(selected.fullName())
        before = set(cmds.ls(type="transform", long=True))
        for empty in ([], (value for value in [])):
            with self.subTest(empty=type(empty).__name__):
                with self.assertRaises(ValueError):
                    hlib.createGroup(empty, name="shouldNotExist")
        self.assertEqual(set(cmds.ls(type="transform", long=True)), before)
        self.assertEqual(selected.parentNode(), None)
        created = hlib.createGroup([], name="emptyGroup", empty=True)
        self.assertIsNone(cmds.listRelatives(created.fullName(), children=True))

    def test_constraint_target_must_be_transform(self):
        source = self.create("transform", "source")
        _, mesh = self.cube()
        for target in (mesh, Vertex(mesh, 0), mesh.plug("visibility")):
            with self.subTest(target=type(target).__name__):
                with self.assertRaises(TypeError):
                    hlib.addConstraint(source, target, type="point")
        target = self.create("transform", "target")
        # 拘束元の Components は所有シェイプ1つとして扱う(シェイプを使う geometry 拘束の例)。
        constraint = hlib.addConstraint(Vertices(mesh, [0, 1, 2]), target.plug("tx"), type="geometry")
        targets = cmds.geometryConstraint(constraint.fullName(), query=True, targetList=True)
        # Maya は拘束元のシェイプを、その親 Transform の名前で報告する。
        self.assertEqual(
            [Node(name).fullName() for name in targets], [mesh.transform().fullName()]
        )

    def test_constraint_sources_must_be_transforms_for_transform_types(self):
        transform, mesh = self.cube()
        transform.plug("tx").set(5.0)
        network = self.create("network", "net")
        # parent/point などは拘束元の transform の値を使う。maya.cmds はシェイプを拘束元にすると
        # ターゲットの無い(追従しない)拘束を黙って作るため、Transform 以外は TypeError。
        shape_sources = {
            "shape": mesh,
            "shape Plug": mesh.plug("castsShadows"),
            "Vertex": Vertex(mesh, 0),
            "Vertices": Vertices(mesh, [0, 1]),
            "vertex name": transform.name() + ".vtx[0]",
            "shape MPlug": mesh.plug("castsShadows").mplug(),
            "DG node": network,
        }
        for kind in ("parent", "point", "orient", "scale", "aim", "poleVector"):
            for label, source in shape_sources.items():
                with self.subTest(kind=kind, source=label):
                    target = self.create("transform", "t_%s_%s" % (kind, label.replace(" ", "")))
                    before = set(cmds.ls(type="constraint") or [])
                    with self.assertRaises(TypeError):
                        hlib.addConstraint(source, target, type=kind)
                    self.assertEqual(set(cmds.ls(type="constraint") or []), before)
        # Transform の Plug は所有 Transform を拘束元にする(拘束先が追従する)。
        followed = self.create("transform", "followed")
        constraint = hlib.addConstraint(transform.plug("tx"), followed, type="point")
        self.assertEqual(
            [node.fullName() for node in constraint.targets()], [transform.fullName()]
        )
        self.assertAlmostEqual(followed.plug("tx").get(), 5.0)
        # シェイプを使う型はシェイプ・Component を拘束元にできる。
        for kind in ("geometry", "normal", "pointOnPoly"):
            for label, source in (
                ("shape Plug", mesh.plug("castsShadows")),
                ("Vertex", Vertex(mesh, 0)),
            ):
                with self.subTest(kind=kind, source=label):
                    target = self.create("transform", "s_%s_%s" % (kind, label.replace(" ", "")))
                    result = hlib.addConstraint(source, target, type=kind)
                    self.assertEqual(
                        [node.fullName() for node in result.targets()], [transform.fullName()]
                    )

    def test_constraint_string_sources_resolve_owner_nodes(self):
        dup1, dup2 = self.duplicates()
        dup2.plug("tx").set(5.0)
        target = self.create("transform", "target")
        # "node.attribute" の文字列も所有ノードを拘束元にする(maya.cmds へプラグ名のまま
        # 渡すと拘束元として扱われない)。
        constraint = hlib.addConstraint(dup2.name() + ".tx", target, type="point")
        self.assertEqual([node.fullName() for node in constraint.targets()], [dup2.fullName()])
        self.assertAlmostEqual(cmds.getAttr(target.plug("tx")), 5.0)
        _, mesh = self.cube()
        other = self.create("transform", "other")
        geometry = other.addConstraint(mesh.name() + ".vtx[0]", "geometry")
        self.assertEqual(
            [node.fullName() for node in geometry.targets()], [mesh.transform().fullName()]
        )
        for source, error in (
            (dup1.nodeName(), RuntimeError),
            (self.ns("missing"), RuntimeError),
            ("", TypeError),
            (None, TypeError),
        ):
            with self.subTest(source=source):
                with self.assertRaises(error):
                    hlib.addConstraint(source, target, type="point")

    def duplicate_cubes(self):
        """短い名前が重複する |cg1|cb と |cg2|cb(シェイプはどちらも cbShape)を作成する。"""
        groups = [self.create("transform", "cg%d" % index) for index in (1, 2)]
        first = cmds.parent(
            cmds.polyCube(name="cb", constructionHistory=False)[0], groups[0].fullName()
        )[0]
        copy = cmds.parent(cmds.duplicate(first)[0], groups[1].fullName())[0]
        copy = cmds.rename(copy, "cb")
        cmds.rename(cmds.listRelatives(copy, shapes=True, fullPath=True)[0], "cbShape")
        self.assertEqual(len(cmds.ls(self.ns("cbShape"))), 2)
        return groups

    def test_node_resolution_errors(self):
        dup1, _ = self.duplicates()
        _, mesh = self.cube()
        self.duplicate_cubes()
        # 同名ノードがあるとプラグ名・コンポーネント名も複数に一致し、最初の一致を黙って返さない。
        for name in (
            dup1.nodeName() + ".tx",
            dup1.nodeName(),
            self.ns("cbShape.vtx[0]"),
            self.ns("cb.worldMatrix[0]"),
        ):
            with self.subTest(name=name):
                self.assertEqual(len(cmds.ls(name)), 2)
                with self.assertRaises(RuntimeError) as context:
                    Node(name)
                self.assertIn("一意", str(context.exception))
                with self.assertRaises(RuntimeError):
                    hlib.getNode(name)
        with self.assertRaises(RuntimeError) as context:
            Node(self.ns("doesNotExist"))
        self.assertIn("見つかりません", str(context.exception))
        # Components は所有シェイプ、アトリビュートの MObject は TypeError、空・削除済みは RuntimeError。
        self.assertIsInstance(hlib.getNode(Vertices(mesh, [0, 1])), Mesh)
        with self.assertRaises(TypeError):
            hlib.getNode(mesh.plug("visibility").mplug().attribute())
        with self.assertRaises(RuntimeError):
            hlib.getNode(om2.MObject())
        with self.assertRaises(RuntimeError):
            hlib.getNode(om2.MDagPath())
        doomed = self.create("transform", "doomed")
        handle_object, path = doomed.mobject(), doomed.dagPath()
        cmds.delete(doomed)
        for value in (handle_object, path):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(RuntimeError):
                    hlib.getNode(value)

    def test_patterns_matching_multiple_nodes_are_not_resolved_to_the_first(self):
        # 以前の Node(...)/hlib.getNode はパターンの最初の一致を返していた。現在は RuntimeError で、
        # パターンは hlib.ls で扱う(一致が1つだけのパターンはそのノードを返す)。
        bulk = [self.create("transform", "bulk%d" % index) for index in range(3)]
        lonely = self.create("transform", "lonely1")
        pattern = self.ns("bulk*")
        self.assertEqual(len(cmds.ls(pattern)), 3)
        for factory in (Node, hlib.getNode):
            with self.subTest(factory=factory.__name__):
                with self.assertRaises(RuntimeError) as context:
                    factory(pattern)
                self.assertIn("一意", str(context.exception))
        self.assertEqual(hlib.getNode(self.ns("lonely*")).fullName(), lonely.fullName())
        self.assertEqual(
            sorted(node.fullName() for node in hlib.ls(pattern)),
            sorted(node.fullName() for node in bulk),
        )


class InstanceSpecificWrapperTest(_InteropCase):
    """インスタンスのパスを保持するラッパーと、名前からのインスタンスの解決を検証する。"""

    def instanced_box(self):
        """|box と |grpB|box1 の2つのインスタンスを持つシェイプを作成する。"""
        box, _ = self.cube("box")
        group = self.create("transform", "grpB")
        instance = cmds.instance(box.fullName(), name="box1")[0]
        instance = cmds.parent(instance, group.fullName())[0]
        second = Node(cmds.listRelatives(instance, shapes=True, fullPath=True)[0])
        first = Node(cmds.listRelatives(box.fullName(), shapes=True, fullPath=True)[0])
        self.assertNotEqual(first.fullName(), second.fullName())
        return first, second, group

    def test_deleting_the_held_instance_does_not_retarget(self):
        """ノードが残っていても消失したインスタンスへ操作しない。"""
        first, second, group = self.instanced_box()
        vertex = Vertex(second, 1)
        cmds.delete(group.fullName() + "|" + self.ns("box1"))
        self.assertTrue(second.isValid())
        for operation in (second.fullName, second.name, vertex.fullName):
            with self.assertRaises(RuntimeError):
                operation()
        self.assertTrue(first.isValid())

    def test_names_keep_the_instance(self):
        from hlib.plugs.plug import Plug as _InputPlug
        first, second, _ = self.instanced_box()
        plug = second.plug("castsShadows")
        self.assertEqual(hlib.getNode(str(plug)).fullName(), second.fullName())
        self.assertEqual(hlib.getNode(plug.fullName()).fullName(), second.fullName())
        self.assertEqual(_InputPlug._resolve_input(str(plug)).node.fullName(), second.fullName())
        self.assertEqual(hlib.getNode(str(first.plug("castsShadows"))).fullName(), first.fullName())
        self.assertEqual(Node(str(Vertex(second, 0))).fullName(), second.fullName())
        self.assertEqual(
            [item.node.fullName() for item in Selection([str(plug)]).plugs()], [second.fullName()]
        )
        # 現在の選択(MSelectionList)はアトリビュートのインスタンスを保持しないが、インスタンスごとの
        # アトリビュート(worldMatrix[1])は要素番号のインスタンスとして取得できる。
        world = second.plug("worldMatrix").element(1)
        cmds.select(str(world))
        captured = Selection.capture()
        self.assertEqual([item.node.fullName() for item in captured.plugs()], [second.fullName()])
        self.assertEqual([item.fullName() for item in captured.plugs()], [world.fullName()])

    def test_transform_name_keeps_the_instance_of_shape_attributes(self):
        from hlib.plugs.plug import Plug as _InputPlug
        box, _ = self.cube("box")
        instance = cmds.ls(cmds.instance(box.fullName(), name="box1")[0], long=True)[0]
        shape = instance + "|" + self.ns("boxShape")
        # transform の名前でシェイプのアトリビュートを指す場合も、名前が指すインスタンスのシェイプになる。
        for text in (instance + ".castsShadows", self.ns("box1.castsShadows")):
            with self.subTest(text=text):
                self.assertEqual(_InputPlug._resolve_input(text).node.fullName(), shape)
                self.assertEqual(hlib.getNode(text).fullName(), shape)
                self.assertEqual(
                    [item.node.fullName() for item in Selection([text]).plugs()], [shape]
                )
        self.assertEqual(
            _InputPlug._resolve_input(box.fullName() + ".castsShadows").node.fullName(),
            box.fullName() + "|" + self.ns("boxShape"),
        )

    def test_world_space_attributes_follow_indirect_instances(self):
        group = self.create("transform", "g")
        child = self.create("transform", "child", group)
        first = self.create("transform", "grandchild", child)
        instance = cmds.ls(cmds.instance(group.fullName(), name="gi")[0], long=True)[0]
        cmds.setAttr(instance + ".translateX", 10)
        second = Node(instance + "|" + self.ns("child") + "|" + self.ns("grandchild"))
        self.assertEqual(second.dagPath().instanceNumber(), 1)
        # 祖先のインスタンス化による間接インスタンスも、評価前から要素として扱う。
        world = second.plug("worldMatrix")
        self.assertEqual(
            [plug.fullName() for plug in world.elements()],
            [world.fullName() + "[0]", world.fullName() + "[1]"],
        )
        self.assertEqual(sorted(world.get()), [0, 1])
        self.assertEqual(world[1].fullName(), world.fullName() + "[1]")
        # getMatrix(ws=True) はラッパーが保持するインスタンスの worldMatrix を使う。
        self.assertEqual(list(second.getMatrix(space=MSpace.kWorld)), cmds.getAttr(world.fullName() + "[1]"))
        self.assertAlmostEqual(list(second.getTranslation(space=MSpace.kWorld))[0], 10.0)
        self.assertAlmostEqual(list(first.getTranslation(space=MSpace.kWorld))[0], 0.0)
        self.assertEqual(
            list(first.getMatrix(space=MSpace.kWorld)), cmds.getAttr(first.fullName() + ".worldMatrix[0]")
        )


class ComponentNamedAttributeTest(_InteropCase):
    """コンポーネント名としても解釈されるアトリビュート(pnts・controlPoints)の名前を検証する。"""

    def test_str_plug_round_trips(self):
        from hlib.plugs.plug import Plug as _InputPlug
        transform, mesh = self.cube("pc")
        point = mesh.plug("pnts").element(3, create=True)
        # MSelectionList は "pcShape.pnts[3]" を頂点として登録するが、アトリビュートとして解決できる。
        self.assertEqual(_InputPlug._resolve_input(str(point)).fullName(), point.fullName())
        self.assertEqual(_InputPlug._resolve_input(str(point) + ".pntx").fullName(), point.fullName() + ".pntx")
        self.assertEqual(
            _InputPlug._resolve_input(mesh.name() + ".pt[3].px").fullName(), point.fullName() + ".pntx"
        )
        self.assertEqual(_InputPlug._resolve_input(transform.name() + ".pnts[3]").fullName(), point.fullName())
        source = self.create("transform", "src")
        source.plug("translate").connect(str(point))
        self.assertTrue(cmds.isConnected(source.plug("translate"), point))
        self.assertTrue(point.isConnectedTo(str(source.plug("translate"))))
        curve = Node(cmds.curve(degree=1, point=[(0, 0, 0), (1, 0, 0)], name="crv")).shape()
        control_point = curve.plug("controlPoints").element(1)
        self.assertEqual(_InputPlug._resolve_input(str(control_point)).fullName(), control_point.fullName())
        # ノードを求める場合は、コンポーネントと同じく所有シェイプになる。
        self.assertEqual(hlib.getNode(str(point)).fullName(), mesh.fullName())
        # コンポーネントの名前・範囲指定はアトリビュートではない。
        for text in (mesh.name() + ".vtx[3]", mesh.name() + ".pnts[0:3]"):
            with self.subTest(text=text):
                with self.assertRaises(TypeError):
                    _InputPlug._resolve_input(text)

    def test_resolving_does_not_create_tweaks(self):
        from hlib.plugs.plug import Plug as _InputPlug
        transform, mesh = self.cube("pc")
        # mesh の controlPoints[i] を問い合わせると Maya は pnts[i] を作り、範囲外の pnts[40] を
        # 問い合わせると pnts[7] を作る。Plug の生成ではどちらも残さない。
        for suffix in (".controlPoints[2]", ".pnts[40]", ".controlPoints[40]", ".cp[5].xv"):
            with self.subTest(suffix=suffix):
                _InputPlug._resolve_input(mesh.name() + suffix)
                self.assertEqual(
                    list(mesh.plug("pnts").mplug().getExistingArrayAttributeIndices()), []
                )
        # ワールド空間アトリビュートも要素を作らない(アトリビュート型の判定で評価も起こさない)。
        world = transform.plug("worldMatrix").mplug()
        before = list(world.getExistingArrayAttributeIndices())
        _InputPlug._resolve_input(transform.name() + ".worldMatrix[7]")
        transform.plug("worldMatrix[0]")
        self.assertEqual(list(world.getExistingArrayAttributeIndices()), before)
        self.assertNotIn(7, before)


class PlugCreationSideEffectTest(_InteropCase):
    """Plug の生成がシーンを変更しないこと(配列要素を作らない・異常終了しないこと)を検証する。"""

    def existing(self, plug):
        return list(plug.mplug().getExistingArrayAttributeIndices())

    def test_plug_creation_never_creates_elements(self):
        from hlib.plugs.plug import Plug as _InputPlug
        averages = [self.create("plusMinusAverage", "pma%d" % index) for index in range(3)]
        # 同じアトリビュートを何度 Plug にしても(以前はキャッシュの状態で結果が変わっていた)要素は作られない。
        _InputPlug._resolve_input(averages[0].name() + ".input1D[10]")
        _InputPlug._resolve_input(averages[1].name() + ".input1D[10]")
        averages[1].plug("input1D[12]")
        Selection([averages[2].name() + ".input1D[11]"])
        for average in averages:
            self.assertEqual(self.existing(average.plug("input1D")), [])
        meshes = [self.cube("cube%d" % index)[1] for index in range(2)]
        for mesh in meshes:
            child = _InputPlug._resolve_input(mesh.name() + ".pnts[50].pntx")
            self.assertEqual(child.fullName(), mesh.name() + ".pnts[50].pntx")
            self.assertEqual(self.existing(mesh.plug("pnts")), [])
        # 動的アトリビュートも要素を作らない。
        network = self.create("network", "net")
        network.addAttribute("values", attributeType="double", multi=True)
        _InputPlug._resolve_input(network.name() + ".values[4]")
        network.plug("values").element(2, create=True)
        self.assertEqual(self.existing(network.plug("values")), [2])
        Plug(network, network.plug("values").mplug().elementByLogicalIndex(7))
        self.assertEqual(self.existing(network.plug("values")), [2])
        # 既存要素・接続された要素はそのまま。
        source = self.create("transform", "source")
        cmds.connectAttr(source.plug("tx"), averages[0].name() + ".input1D[3]")
        self.assertTrue(_InputPlug._resolve_input(averages[0].name() + ".input1D[3]").isDestination())
        self.assertEqual(self.existing(averages[0].plug("input1D")), [3])
        # 要素の作成は element(create=True) で明示する。
        created = averages[1].plug("input1D").element(5, create=True)
        self.assertEqual(self.existing(averages[1].plug("input1D")), [5])
        self.assertEqual(created.fullName(), averages[1].name() + ".input1D[5]")

    def test_blend_shape_weight_plugs_do_not_create_target_elements(self):
        from hlib.plugs.plug import Plug as _InputPlug
        base = cmds.polyCube(name="base")[0]
        target = cmds.polyCube(name="target")[0]
        blend = hlib.getNode(cmds.blendShape(target, base, name="blend")[0])
        arrays = (
            "weight",
            "parentDirectory",
            "nextTarget",
            "targetVisibility",
            "targetParentVisibility",
            "inputTarget[0].inputTargetGroup",
        )
        before = {name: self.existing(blend.plug(name)) for name in arrays}
        # maya.cmds で weight[5] の型を問い合わせると parentDirectory[5] なども作られる。
        weight = _InputPlug._resolve_input(blend.name() + ".weight[5]")
        self.assertEqual(type(weight).__name__, "FloatPlug")
        blend.plug("weight[7]")
        hlib.getDrivenKey(self.create("transform", "driver").plug("tx"), blend.name() + ".weight[0]")
        Selection([blend.name() + ".weight[6]"])
        self.assertEqual({name: self.existing(blend.plug(name)) for name in arrays}, before)

    def test_internal_attributes_resolve_without_errors_or_changes(self):
        from hlib.plugs.plug import Plug as _InputPlug
        _, mesh = self.cube()
        arrays = ("edge", "face", "vrts", "uvpt", "pnts")
        before = {name: self.existing(mesh.plug(name)) for name in arrays}
        # mesh の内部アトリビュートは maya.cmds.getAttr(type=True) では例外になるが、アトリビュート定義から型を求める。
        for path, expected in (
            ("edge[1]", "long3"),
            ("face[1]", "polyFaces"),
            ("vrts[10]", "float3"),
            ("uvpt[16]", "float2"),
            ("edge[500]", "long3"),
        ):
            with self.subTest(plug=path):
                plug = mesh.plug(path)
                self.assertEqual(attributeType(plug.mplug()), expected)
                self.assertEqual(_InputPlug._resolve_input(plug.fullName()).mplug(), plug.mplug())
        self.assertEqual({name: self.existing(mesh.plug(name)) for name in arrays}, before)
        # nurbsSurface の patchUVIds の存在しない要素は、maya.cmds で型を問い合わせると Maya が
        # 異常終了する。Plug の生成は maya.cmds へ問い合わせないため安全に扱える。
        surface = Node(cmds.sphere(name="surface", constructionHistory=False)[0]).shape()
        patch = surface.plug("patchUVIds")
        count = len(self.existing(patch))
        for plug in (_InputPlug._resolve_input(surface.name() + ".patchUVIds[999]"), surface.plug("patchUVIds[998]")):
            self.assertEqual(plug.mplug().logicalIndex() in (998, 999), True)
        self.assertEqual(len(self.existing(patch)), count)
        # 内部のデータ型の存在しない要素は、値を読むと Maya が異常終了する場合があるため、
        # 値の取得と要素の作成を RuntimeError にする(maya.cmds・MPlug のどちらでも読まない)。
        self.assertTrue(is_internal_data_type(patch.mplug()))
        for call in (
            lambda: patch.element(7, create=True),
            patch.addElement,
            lambda: surface.plug("patchUVIds[3]").get(),
        ):
            with self.assertRaises(RuntimeError):
                call()
        self.assertEqual(len(self.existing(patch)), count)
        self.assertEqual(patch.get(), {})
        for plug in (mesh.plug("pnts"), mesh.plug("outMesh"), surface.plug("local")):
            self.assertFalse(is_internal_data_type(plug.mplug()))

    def test_generic_attributes_holding_matrices_use_matrix_plug(self):
        from hlib.plugs.plug import Plug as _InputPlug
        source = self.create("transform", "src")
        source.plug("t").set((2.0, 0.0, 0.0))
        choices = {}
        for label, plug in (
            ("matrix", source.plug("worldMatrix[0]")),
            ("double3", source.plug("translate")),
            ("double", source.plug("tx")),
        ):
            choice = self.create("choice", "choice_" + label)
            cmds.connectAttr(str(plug), choice.name() + ".input[0]")
            choices[label] = choice
        # cmds.getAttr(type=True) と同じく、行列を保持する generic アトリビュートは MatrixPlug になる。
        for path in ("output", "input[0]"):
            with self.subTest(path=path):
                plug = choices["matrix"].plug(path)
                self.assertEqual(type(plug).__name__, "MatrixPlug")
                self.assertEqual(type(plug.get()).__name__, "Matrix")
                self.assertAlmostEqual(list(plug.get())[12], 2.0)
        # 数値の組を保持する generic アトリビュートは子を持たないため基底の Plug のまま(get() は tuple)。
        output = choices["double3"].plug("output")
        self.assertIs(type(output), Plug)
        self.assertEqual(output.get(), (2.0, 0.0, 0.0))
        self.assertIs(type(choices["double"].plug("output")), Plug)
        self.assertEqual(choices["double"].plug("output").get(), 2.0)
        # 存在しない要素の Plug は値を読まない(要素を作らない)。
        choices["matrix"].plug("input[5]")
        _InputPlug._resolve_input(choices["matrix"].name() + ".input[6]")
        self.assertEqual(self.existing(choices["matrix"].plug("input")), [0])

    def test_value_dependent_attributes_avoid_evaluation(self):
        # 入力接続のある要素は接続元のアトリビュートの型を使い、上流を評価しない。
        from hlib.plugs.plug import Plug as _InputPlug
        counter = "hlibInteropEval_" + uuid.uuid4().hex[:8]
        source = self.create("transform", "src")
        middle = self.create("transform", "mid")
        cmds.expression(
            string="global int $%s; $%s++; %s.rx = %s.tx * 2; %s.tx = %s.tx;"
            % (counter, counter, middle.name(), source.name(), middle.name(), source.name()),
            name="counter",
        )
        choice = self.create("choice", "choice")
        cmds.connectAttr(middle.plug("worldMatrix[0]"), choice.name() + ".input[0]")
        driven = self.create("transform", "driven")
        cmds.connectAttr(
            middle.plug("rx"), driven.plug("tx")
        )  # unitConversion(generic アトリビュート)を経由する
        cmds.getAttr(driven.plug("tx"))
        cmds.getAttr(choice.name() + ".output")

        def count():
            # GUI では $tmp などの一般的な名前が別の型のグローバル変数として既に存在するため、固有の名前で読む。
            return int(mel.eval("global int $%s; $%s_read = $%s;" % (counter, counter, counter)))

        cmds.setAttr(source.plug("tx"), 5.0)
        before = count()
        destinations = middle.plug("rx").destinations()
        element = choice.plug("input[0]")
        self.assertEqual(count(), before)
        self.assertEqual(type(element).__name__, "MatrixPlug")
        self.assertEqual([type(plug).__name__ for plug in destinations], ["Plug"])
        # 入力接続の無い出力は cmds.getAttr(type=True) と同じく値を読む(評価が起こる)。
        self.assertEqual(type(choice.plug("output")).__name__, "MatrixPlug")
        # 読み取りできない generic アトリビュート(transform 系ノード共通の geometry)は値を読まない。
        # field は geometry の評価で falloffCurve[0] などの要素を作るため、読むとシーンが変わる。
        field = Node(cmds.createNode("dragField", name="drag", skipSelect=True))
        arrays = ("falloffCurve", "curveRadius", "axialMagnitude")
        before = {name: self.existing(field.plug(name)) for name in arrays}
        self.assertIs(type(field.plug("geometry")), Plug)
        _InputPlug._resolve_input(field.name() + ".geometry")
        self.assertGreater(len(field.plugs()), 100)
        self.assertEqual({name: self.existing(field.plug(name)) for name in arrays}, before)

    def test_chained_value_dependent_sources_are_evaluated(self):
        # 接続元も値によって型が変わるアトリビュート(unitConversion.output、choice.output)なら接続元を辿り、
        # 入力接続の無い接続元の値を読むため、上流の評価が起こる(cmds.getAttr(type=True) と同じ)。
        counter = "hlibInteropChain_" + uuid.uuid4().hex[:8]
        source = self.create("transform", "src")
        middle = self.create("transform", "mid")
        cmds.expression(
            string="global int $%s; $%s++; %s.rx = %s.tx * 2; %s.tx = %s.tx;"
            % (counter, counter, middle.name(), source.name(), middle.name(), source.name()),
            name="counter",
        )
        driven = self.create("transform", "driven")
        cmds.connectAttr(
            middle.plug("rx"), driven.plug("tx")
        )  # unitConversion(generic アトリビュート)を経由する
        conversion = cmds.listConnections(
            str(driven.plug("tx")), source=True, destination=False, type="unitConversion"
        )[0]
        upstream = self.create("choice", "upstream")
        cmds.connectAttr(middle.plug("worldMatrix[0]"), upstream.name() + ".input[0]")
        chains = {}
        for label, output in (
            ("unitConversion", conversion + ".output"),
            ("choice", upstream.name() + ".output"),
        ):
            downstream = self.create("choice", "down_" + label)
            cmds.connectAttr(output, downstream.name() + ".input[0]")
            chains[label] = downstream

        def count():
            # GUI では $tmp などの一般的な名前が別の型のグローバル変数として既に存在するため、固有の名前で読む。
            return int(mel.eval("global int $%s; $%s_read = $%s;" % (counter, counter, counter)))

        for label, expected in (("unitConversion", Plug), ("choice", None)):
            with self.subTest(source=label):
                cmds.getAttr(chains[label].name() + ".input[0]")
                cmds.setAttr(source.plug("tx"), float(count() + 1))
                before = count()
                element = chains[label].plug("input[0]")
                self.assertGreater(count(), before)
                if expected is not None:
                    self.assertIs(type(element), expected)
                else:
                    self.assertEqual(type(element).__name__, "MatrixPlug")

    def test_evaluation_side_effects_match_maya_cmds(self):
        # 計算される generic アトリビュートの Plug を作ると値を読むため、評価でワールド空間の出力の要素が
        # 作られる場合がある(インスタンス化されたシェイプを拘束元にした geometryConstraint)。
        # cmds.getAttr(type=True) と同じ結果になることを確かめる。
        from hlib.plugs.plug import Plug as _InputPlug
        def existing_after(read):
            transform, mesh = self.cube("gcube")
            instance = cmds.instance(transform.fullName(), name="gcubeInst")[0]
            locator = self.create("transform", "loc")
            constraint = cmds.geometryConstraint(instance, locator.fullName())[0]
            before = list(mesh.plug("worldMesh").mplug().getExistingArrayAttributeIndices())
            read(constraint + ".constraintGeometry")
            after = list(mesh.plug("worldMesh").mplug().getExistingArrayAttributeIndices())
            cmds.delete(constraint, locator.fullName(), instance, transform.fullName())
            return before, after

        hlib_result = existing_after(_InputPlug._resolve_input)
        cmds_result = existing_after(lambda name: cmds.getAttr(name, type=True))
        self.assertEqual(hlib_result, cmds_result)
        self.assertEqual(hlib_result, ([1], [0, 1]))

    def test_plugs_of_deleted_nodes_do_not_touch_nodes_with_the_same_name(self):
        network = self.create("network", "net")
        network.addAttribute("values", attributeType="double", multi=True)
        network.plug("values").element(2, create=True).set(1.0)
        array_plug = network.plug("values")
        name = network.name()
        cmds.delete(network.fullName())
        replacement = self.create("network", "net")
        replacement.addAttribute("values", attributeType="double", multi=True)
        self.assertEqual(replacement.name(), name)
        # 削除済みノードの名前で問い合わせると、同じ名前の新しいノードに要素ができてしまう。
        calls = {
            "element": lambda: array_plug.element(2),
            "getitem": lambda: array_plug[2],
            "elements": array_plug.elements,
            "get": array_plug.get,
            "create": lambda: array_plug.element(3, create=True),
            "remove": lambda: array_plug.removeElement(2),
            "nextAvailableIndex": array_plug.nextAvailableIndex,
            "Plug": lambda: Plug(network, array_plug.mplug().elementByLogicalIndex(4)),
        }
        for label, call in calls.items():
            with self.subTest(call=label):
                with self.assertRaises(RuntimeError):
                    call()
        self.assertEqual(self.existing(replacement.plug("values")), [])

    def test_message_array_elements_exist_once_connected(self):
        network = self.create("network", "net")
        network.addAttribute("links", attributeType="message", multi=True)
        array_plug = network.plug("links")
        first = array_plug.addElement()
        self.assertEqual(first.fullName(), network.name() + ".links[0]")
        # message 型の要素は値を持たないため作成できず、接続するまでは同じ番号を返す。
        self.assertEqual(array_plug.elements(), [])
        self.assertEqual(array_plug.addElement().fullName(), first.fullName())
        self.create("network", "src").plug("message").connect(first)
        self.assertEqual([plug.fullName() for plug in array_plug.elements()], [first.fullName()])
        self.assertEqual(array_plug.addElement().fullName(), network.name() + ".links[1]")


class PlugValidityTest(_InteropCase):
    """所有ノード・動的アトリビュートが削除された Plug を安全に扱えることを検証する。"""

    def test_deleted_dynamic_attribute(self):
        node = self.create("transform", "t")
        plug = node.addAttribute("foo", attributeType="double")
        array_plug = node.addAttribute("arr", attributeType="double", multi=True)
        array_plug.element(2, create=True).set(3.0)
        cmds.addAttr(node.name(), longName="cmp", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(node.name(), longName="cmp" + axis, attributeType="double", parent="cmp")
        compound = node.plug("cmp")
        child = compound.child(0)
        self.assertTrue(plug.isValid())
        for name in ("foo", "arr", "cmp"):
            cmds.deleteAttr(node.name() + "." + name)
        # 削除済みのアトリビュートの MPlug で値を読み書きすると Maya が異常終了するため、RuntimeError にする。
        for item in (plug, array_plug, compound, child):
            with self.subTest(plug=type(item).__name__):
                self.assertFalse(item.isValid())
                self.assertEqual(str(item), "")
                self.assertEqual(repr(item), "<Plug invalid>")
                self.assertFalse(cmds.objExists(str(item)))
                with self.assertRaises(RuntimeError):
                    item.get()
        for call in (
            lambda: plug.set(1.0),
            lambda: plug.set(1.0, fast=True),
            lambda: compound.set((1, 2, 3)),
            array_plug.elements,
            lambda: array_plug[2],
            array_plug.nextAvailableIndex,
            lambda: compound.child(0),
            plug.reset,
            child.parent,
        ):
            with self.assertRaises(RuntimeError):
                call()
        with self.assertRaises(ValueError):
            hlib.select(plug)
        # 同じ名前で追加し直しても、古い Plug は別のアトリビュートとして無効のまま。
        node.addAttribute("foo", attributeType="double")
        self.assertFalse(plug.isValid())
        with self.assertRaises(RuntimeError):
            plug.get()
        self.assertTrue(node.plug("foo").isValid())
        self.assertEqual(node.plug("foo").get(), 0.0)

    def test_raw_mplug_of_deleted_dynamic_attribute(self):
        # 生の MPlug も、削除済みのアトリビュートなら名前へ変換せず ValueError にする(以前は "t." や
        # "t.foo" を返し、hlib.select がノードを黙って選択していた)。
        from hlib.object import Object as _InputObject
        from hlib.plugs.plug import Plug as _InputPlug

        state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        try:
            for label in ("undoable", "without undo"):
                with self.subTest(delete=label):
                    node = self.create("transform", "t")
                    mplug = om2.MPlug(node.addAttribute("foo", attributeType="double").mplug())
                    self.assertTrue(_InputPlug._mplug_attribute_exists(mplug))
                    self.assertEqual(_InputObject._input_name(mplug), node.name() + ".foo")
                    if label == "undoable":
                        cmds.deleteAttr(node.name() + ".foo")
                    else:
                        cmds.undoInfo(stateWithoutFlush=False)
                        try:
                            cmds.deleteAttr(node.name() + ".foo")
                        finally:
                            cmds.undoInfo(stateWithoutFlush=True)
                    self.assertFalse(_InputPlug._mplug_attribute_exists(mplug))
                    cmds.select(clear=True)
                    for call in (
                        lambda: _InputObject._input_name(mplug),
                        lambda: hlib.select(mplug),
                        lambda: _InputObject._input_names([mplug]),
                    ):
                        with self.assertRaises(ValueError):
                            call()
                    self.assertEqual(cmds.ls(selection=True), [])
                    with self.assertRaises(RuntimeError):
                        _InputPlug._resolve_input(mplug)
                    cmds.delete(node.fullName())
        finally:
            cmds.undoInfo(state=state)

    def test_node_arguments_reject_deleted_attributes(self):
        # 所有ノードは有効なままアトリビュートだけが削除された Plug・MPlug は、ノードが必要な引数でも
        # 所有ノードへ解決せず、hlib のコマンド(hlib.select など)と同じく ValueError にする。
        # Node(...) の「解決できない対象は RuntimeError」の規則に合わせ、RuntimeError の派生でもある。
        from hlib.nodes.node import Node as _InputNode
        from hlib.plugs.plug import DeletedAttributeError

        parent = self.create("transform", "parent")
        child = self.create("transform", "child", parent)
        target = self.create("transform", "target")
        plugs = {
            "parent": parent.addAttribute("foo", attributeType="double"),
            "child": child.addAttribute("foo", attributeType="double"),
        }
        mplugs = {key: om2.MPlug(plug.mplug()) for key, plug in plugs.items()}
        self.assertEqual(hlib.getNode(mplugs["child"]).fullName(), child.fullName())
        self.assertTrue(parent.isParentOf(plugs["child"]))
        state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        try:
            cmds.deleteAttr(parent.name() + ".foo")
            cmds.deleteAttr(child.name() + ".foo")
            with self.assertRaises(ValueError):
                hlib.getNode(mplugs["child"])
            # Undo でアトリビュートが戻れば、同じ Plug・MPlug を再び所有ノードへ解決できる。
            cmds.undo()
            for value in (plugs["child"], mplugs["child"]):
                self.assertEqual(hlib.getNode(value).fullName(), child.fullName())
                self.assertTrue(parent.isParentOf(value))
            cmds.deleteAttr(child.name() + ".foo")
        finally:
            cmds.undoInfo(state=state)
        calls = {
            "Node": Node,
            "hlib.getNode": hlib.getNode,
            "to_node": _InputNode._resolve_input,
            "constraint source": lambda value: hlib.addConstraint(value, target, type="point"),
            "constraint target": lambda value: hlib.addConstraint(target, value, type="point"),
            "addConstraint": lambda value: target.addConstraint(value, "point"),
            "matchTransform": target.matchTransform,
        }
        for value in (plugs["child"], mplugs["child"]):
            for label, call in calls.items():
                with self.subTest(value=type(value).__name__, call=label):
                    with self.assertRaises(ValueError) as context:
                        call(value)
                    self.assertIsInstance(context.exception, DeletedAttributeError)
                    self.assertIsInstance(context.exception, RuntimeError)
            with self.assertRaises(ValueError):
                hlib.select(value)
        self.assertEqual(cmds.ls(self.ns("*"), type="pointConstraint"), [])
        # 判定メソッドは削除済みの対象に False を返す(削除前は True)。
        for value in (plugs["child"], mplugs["child"]):
            with self.subTest(owner="child", value=type(value).__name__):
                self.assertFalse(parent.isParentOf(value))
                self.assertFalse(parent.isAncestorOf(value))
        for value in (plugs["parent"], mplugs["parent"]):
            with self.subTest(owner="parent", value=type(value).__name__):
                self.assertFalse(child.isChildOf(value))

    def test_parent_queries_return_false_for_deleted_api_objects(self):
        parent = self.create("transform", "parent")
        child = self.create("transform", "child", parent)
        values = (
            child,
            child.plug("tx"),
            child.mobject(),
            child.dagPath(),
            om2.MPlug(child.plug("tx").mplug()),
        )
        for value in values:
            self.assertTrue(parent.isParentOf(value))
        cmds.delete(child.fullName())
        # 削除済みのノードを指す om2 オブジェクトも、削除済みの Node と同じく False(Node(...) は
        # RuntimeError)。空の MObject・存在しない名前は従来どおり RuntimeError。
        for value in values:
            with self.subTest(value=type(value).__name__):
                self.assertFalse(parent.isParentOf(value))
                self.assertFalse(parent.isAncestorOf(value))
        with self.assertRaises(RuntimeError):
            hlib.getNode(values[2])
        for value in (om2.MObject(), self.ns("missing")):
            with self.subTest(value=repr(value)):
                with self.assertRaises(RuntimeError):
                    parent.isParentOf(value)

    def test_renamed_attribute_and_undo(self):
        node = self.create("transform", "t")
        plug = node.addAttribute("foo", attributeType="double")
        plug.set(2.0)
        cmds.renameAttr(node.name() + ".foo", "bar")
        # 名前を変更したアトリビュートは同じアトリビュートのまま有効。
        self.assertTrue(plug.isValid())
        self.assertEqual(str(plug), node.name() + ".bar")
        self.assertEqual(plug.get(), 2.0)
        state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        try:
            cmds.deleteAttr(node.name() + ".bar")
            self.assertFalse(plug.isValid())
            cmds.undo()
            # Undo で削除を取り消したアトリビュートは、同じ Plug で再び扱える。
            self.assertTrue(plug.isValid())
            self.assertEqual(plug.get(), 2.0)
        finally:
            cmds.undoInfo(state=state)

    def test_deleted_node_plug_raises_instead_of_returning_stale_value(self):
        node = self.create("transform", "t")
        plug = node.plug("tx")
        plug.set(3.0)
        cmds.delete(node.fullName())
        self.assertFalse(plug.isValid())
        self.assertEqual(str(plug), "")
        with self.assertRaises(RuntimeError):
            plug.get()
        with self.assertRaises(RuntimeError):
            plug.set(1.0)
        with self.assertRaises(RuntimeError):
            node.plug("t")

    def test_plugs_of_nodes_deleted_without_undo(self):
        # Undo の対象から外れた削除(Undo 無効時の削除や flushUndo)では、削除済みノードの MPlug の
        # 名前・アトリビュートの問い合わせで Maya が異常終了するため、名前は空文字列、問い合わせは RuntimeError。
        node = self.create("transform", "t")
        node.addAttribute("arr", attributeType="double", multi=True).element(0, create=True).set(1.0)
        cmds.addAttr(node.name(), longName="cmp", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(node.name(), longName="cmp" + axis, attributeType="double", parent="cmp")
        plugs = [
            node.plug("arr[0]"),
            node.plug("arr"),
            node.plug("cmpX"),
            node.plug("cmp"),
            node.plug("tx"),
            node.plug("worldMatrix[0]"),
        ]
        state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=False)
        try:
            cmds.delete(node.fullName())
        finally:
            cmds.undoInfo(stateWithoutFlush=state)
        for plug in plugs:
            with self.subTest(plug=type(plug).__name__):
                self.assertFalse(plug.isValid())
                self.assertEqual(str(plug), "")
                self.assertEqual(plug.name(), "")
                self.assertEqual(repr(plug), "<Plug invalid>")
                self.assertFalse(cmds.objExists(str(plug)))
                calls = [
                    plug.attributeName,
                    plug.niceName,
                    plug.isLocked,
                    plug.isKeyable,
                    plug.isConnected,
                    plug.isDynamic,
                    plug.isHidden,
                    plug.default,
                    plug.parent,
                    plug.source,
                    plug.destinations,
                    plug.get,
                    lambda: plug.connect(self.create("transform", "x").plug("tx")),
                ]
                if not isinstance(plug, ArrayPlug):
                    calls.append(lambda: plug.set(1.0))  # 配列全体の set() は常に TypeError
                for call in calls:
                    with self.assertRaises(RuntimeError):
                        call()
                # 構造の判定は例外にしない。
                self.assertIsInstance(plug.isArray(), bool)

    def test_deleted_extension_attribute(self):
        node_type = "network"
        name = "hlibInteropExt" + uuid.uuid4().hex[:8]
        cmds.addExtension(nodeType=node_type, longName=name, attributeType="double")
        try:
            network = self.create(node_type, "net")
            plug = network.plug(name)
            plug.set(2.0)
            self.assertTrue(plug.isValid())
            self.assertEqual(plug.get(), 2.0)
            cmds.deleteExtension(nodeType=node_type, attribute=name, forceDelete=True)
            self.assertFalse(plug.isValid())
            self.assertEqual(str(plug), "")
            with self.assertRaises(RuntimeError):
                plug.get()
        finally:
            if cmds.attributeQuery(name, type=node_type, exists=True):
                cmds.deleteExtension(nodeType=node_type, attribute=name, forceDelete=True)


class NodePlugPathTest(_InteropCase):
    """Node.plug() がアトリビュートパス・エイリアスを解決することを検証する。"""

    def test_attribute_paths(self):
        from hlib.plugs.plug import Plug as _InputPlug
        average = self.create("plusMinusAverage", "pma")
        transform = self.create("transform", "t")
        base = cmds.polyCube(name="base")[0]
        target = cmds.polyCube(name="target")[0]
        blend = hlib.getNode(cmds.blendShape(target, base, name="blend")[0])
        group = "inputTarget[0].inputTargetGroup"
        before = list(blend.plug(group).mplug().getExistingArrayAttributeIndices())
        cases = [
            (average, "input1D[3]", "FloatPlug"),
            (average, "input3D[2].input3Dx", "FloatPlug"),
            (average, "input3D[2]", "CompoundPlug"),
            (average, "i3[2].i3x", "FloatPlug"),
            (transform, "worldMatrix[0]", "MatrixPlug"),
            (transform, "wm[0]", "MatrixPlug"),
            (blend, group + "[7].inputTargetItem[6000].inputComponentsTarget", "Plug"),
            (blend, "weight[0]", "FloatPlug"),
            (blend, "target", "FloatPlug"),  # weight[0] のエイリアス
        ]
        for node, path, class_name in cases:
            with self.subTest(path=path):
                plug = node.plug(path)
                self.assertEqual(type(plug).__name__, class_name)
                self.assertEqual(_InputPlug._resolve_input(plug.fullName()).mplug(), plug.mplug())
                self.assertTrue(node.hasAttribute(path))
        self.assertEqual(blend.plug("weight[0]").mplug(), blend.plug("target").mplug())
        self.assertEqual(list(blend.plug(group).mplug().getExistingArrayAttributeIndices()), before)
        self.assertEqual(
            list(average.plug("input1D").mplug().getExistingArrayAttributeIndices()), []
        )
        for path in (
            "input1D[3].foo",
            "missing[0]",
            "input1D[0:3]",
            "operation[0]",
            "missing.child",
        ):
            with self.subTest(path=path):
                with self.assertRaises(AttributeError):
                    average.plug(path)
                self.assertFalse(average.hasAttribute(path))
        # 配列要素の番号を含まない配列複合アトリビュートの子は maya.cmds で解決できないため拒否する
        # (子が配列の場合も同じ。inputTarget[-1].inputTargetGroup の ArrayPlug は作らない)。
        with self.assertRaises(RuntimeError):
            average.plug("input3Dx")
        self.assertFalse(average.hasAttribute("input3Dx"))
        for path in ("inputTargetGroup", "inputTargetItem", "inputComponentsTarget"):
            with self.subTest(path=path):
                with self.assertRaises(RuntimeError):
                    blend.plug(path)
                self.assertFalse(blend.hasAttribute(path))
        self.assertEqual(type(blend.plug(group)).__name__, "ArrayPlug")
        # Python のアトリビュートアクセスでは hasattr/getattr の既定値が使えるよう AttributeError にする。
        for node, name in (
            (average, "input3Dx"),
            (blend, "inputTargetGroup"),
            (average, "missingAttr"),
        ):
            with self.subTest(attribute=name):
                self.assertFalse(hasattr(node, name))
                self.assertIsNone(getattr(node, name, None))
                with self.assertRaises(AttributeError):
                    getattr(node, name)
        self.assertTrue(hasattr(average, "input1D"))
        # "親.子" の名前は findPlug の解決(Maya のバージョンで異なる)に従うが、いずれも拒否する。
        with self.assertRaises((RuntimeError, AttributeError)):
            average.plug("input3D.input3Dx")
        self.assertFalse(average.hasAttribute("input3D.input3Dx"))


class NodeConstructionTest(_InteropCase):
    """Node(...) が入力を1回だけ解決して、型に応じたラッパーを返すことを検証する。"""

    def test_node_input_is_resolved_once(self):
        from hlib.nodes import Transform
        from hlib.nodes import node as node_module

        joint = cmds.createNode("joint", name="jnt")
        transform = cmds.createNode("transform", name="xf")
        network = cmds.createNode("network", name="net")
        calls = []
        original = node_module._resolve_node

        def counting(value):
            calls.append(value)
            return original(value)

        node_module._resolve_node = counting
        try:
            cases = [
                (Node, joint, Joint),
                (Node, transform, Transform),
                (Node, network, Node),
                (Transform, joint, Joint),
                (Node, Node(joint).mobject(), Joint),
                (hlib.getNode, joint, Joint),
            ]
            for factory, value, expected in cases:
                with self.subTest(factory=getattr(factory, "__name__", factory), value=str(value)):
                    del calls[:]
                    result = factory(value)
                    self.assertIs(type(result), expected)
                    self.assertTrue(result.isValid())
                    self.assertEqual(len(calls), 1)
        finally:
            node_module._resolve_node = original
        # 呼び出したクラスの派生でないラッパーも初期化されている。
        with self.assertRaises(TypeError):
            Joint(transform)


class CommandEdgeCaseTest(_InteropCase):
    """hlib のコマンドの細かな規則(None・曖昧な名前・文字列のアトリビュート名)を検証する。"""

    def test_ls_accepts_none_like_maya_cmds(self):
        joint = self.create("joint", "j")
        children = cmds.listRelatives(joint.fullName(), children=True)
        self.assertIsNone(children)
        self.assertEqual(hlib.ls(children), [])
        self.assertEqual(len(hlib.ls(children, type="joint")), 0)
        self.assertEqual(cmds.ls(children, type="joint"), [])

    def test_objExists_matches_maya_cmds_for_strings(self):
        dup1, _ = self.duplicates()
        for name in (dup1.nodeName(), dup1.nodeName() + ".tx", self.ns("missing"), dup1.name()):
            with self.subTest(name=name):
                self.assertEqual(cmds.objExists(name), bool(cmds.objExists(name)))
        self.assertTrue(cmds.objExists(dup1.nodeName()))

    def test_drivenKey_accepts_plug_name_strings(self):
        from hlib.plugs.plug import Plug as _InputPlug
        base = cmds.polyCube(name="base")[0]
        target = cmds.polyCube(name="tgt")[0]
        blend = hlib.getNode(cmds.blendShape(target, base, name="bs")[0])
        weight = blend.plug("weight")[0]
        self.assertEqual(str(weight), self.ns("bs.tgt"))
        driver = self.create("transform", "driver")
        relation = hlib.getDrivenKey(driver.plug("tx"), str(weight))
        relation.setKey(0.0, 0.0)
        relation.setKey(1.0, 1.0)
        self.assertEqual(relation.drivenPlug().fullName(), weight.fullName())
        found = hlib.scene.DrivenKey.find(str(weight))
        self.assertEqual(len(found), 1)
        self.assertEqual(len(hlib.scene.DrivenKey.find(self.ns("bs.weight[0]"))), 1)
        network = self.create("network", "net")
        network.addAttribute("vals", attributeType="double", multi=True)
        network.plug("vals").element(2, create=True)
        dup1, dup2 = self.duplicates()
        for driven in (self.ns("net.vals[2]"), str(dup2.plug("ty")), self.ns("bs.weight[0]")):
            with self.subTest(driven=driven):
                relation = hlib.getDrivenKey(dup1.plug("tx"), driven)
                self.assertEqual(relation.drivenPlug().fullName(), _InputPlug._resolve_input(driven).fullName())
        with self.assertRaises(RuntimeError):
            hlib.getDrivenKey(dup1.nodeName() + ".tx", dup2.plug("tz"))  # 2つの dup に一致する
        with self.assertRaises(TypeError):
            hlib.getDrivenKey(driver.name(), dup2.plug("tz"))


class LargeComponentCollectionTest(_InteropCase):
    """多数の要素を持つコレクションを範囲指定の名前で受け渡すことを検証する。"""

    def test_large_collections_use_range_names(self):
        from hlib.object import Object as _InputObject
        plane = Node(
            cmds.polyPlane(
                name="plane", subdivisionsX=100, subdivisionsY=100, constructionHistory=False
            )[0]
        )
        mesh = plane.shape()
        vertices = Vertices(mesh)
        self.assertEqual(len(vertices), 10201)
        self.assertEqual(_InputObject._input_names(vertices), [mesh.fullName() + ".vtx[0:10200]"])
        hlib.select(vertices)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 10201)
        subset = Vertices(mesh, list(range(0, 10201, 2)))
        hlib.select(subset)
        self.assertEqual(len(cmds.ls(selection=True, flatten=True)), 5101)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

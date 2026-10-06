"""hlib Node/DAG APIを検証するMaya内テスト。"""
from maya.api.OpenMaya import MSpace

import math
import sys
import unittest

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.scene import Namespace
from hlib.nodes import Node
from hlib.maths import EulerRotation, Matrix, Quaternion, Scale, Shear, Translation, Vector


class NodeApiTest(unittest.TestCase):
    """基本Node/DAG APIを検証する。"""

    namespace = ":hlibNodeApiTest"

    def setUp(self):
        self.created = []
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        for node in reversed(self.created):
            if cmds.objExists(node):
                cmds.delete(node)
        if cmds.namespace(exists=self.namespace):
            cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)

    def create_transform(self, name):
        node = Node.create(type="transform", name=name)
        self.created.append(node.getName())
        return node

    def test_dag_paths_and_shapes(self):
        transform = self.create_transform("hlibNodeApiTransform")
        shape_name = cmds.createNode("mesh", parent=transform.getName())
        self.created.append(shape_name)
        shape = transform.getShape()

        self.assertEqual(transform.getPath(), transform.getName())
        self.assertEqual(transform.getPath(full=True), "|" + transform.getName())
        self.assertEqual(transform.getPath(), transform.getName())
        self.assertEqual(transform.getPath(full=True), "|" + transform.getName())
        self.assertTrue(transform.isRoot())
        self.assertEqual(len(transform.getShapes()), 1)
        self.assertEqual(shape.getTransform().getName(), transform.getName())
        self.assertTrue(shape.getPath(full=True).endswith("|" + shape_name))

    def test_rename_namespace_and_add_attr(self):
        transform = self.create_transform("hlibNodeApiRename")
        renamed = transform.rename("hlibNodeApiRenamed")
        self.assertEqual(renamed, "hlibNodeApiRenamed")
        self.assertEqual(transform.getName(), "hlibNodeApiRenamed")

        namespaced = transform.setNamespace(self.namespace)
        self.assertIn("hlibNodeApiRenamed", namespaced)
        self.assertEqual(transform.getNodeName(remove_namespace=True), "hlibNodeApiRenamed")
        self.assertEqual(transform.getNamespace(), Namespace(self.namespace))

        missing_namespace = ":hlibNodeApiMissing:child"
        transform.setNamespace(missing_namespace)
        self.assertTrue(Namespace(missing_namespace).exists())
        self.assertEqual(transform.getNamespace(), Namespace(missing_namespace))

        plug = transform.addAttr(
            "hlibNodeApiValue",
            attributeType="double",
            defaultValue=1.5,
        )
        self.assertEqual(plug.getLongName(), "hlibNodeApiValue")
        self.assertEqual(plug.get(), 1.5)

    def test_parent_and_connections(self):
        parent = self.create_transform("hlibNodeApiParent")
        child = self.create_transform("hlibNodeApiChild")
        source = self.create_transform("hlibNodeApiSource")
        target = self.create_transform("hlibNodeApiTarget")

        child.setParent(parent)
        self.assertEqual(child.getParent().getName(), parent.getName())
        child.setParent()
        self.assertIsNone(child.getParent())

        source.getPlug("translateX").connectTo(target.getPlug("translateX"))
        self.assertEqual([plug.getFullName() for plug in target.getInputs()], [source.getPlug("translateX").getFullName()])
        self.assertEqual([plug.getFullName() for plug in source.getOutputs()], [target.getPlug("translateX").getFullName()])
        self.assertEqual(len(source.getConnections()), 1)

        def names(plugs):
            return [plug.getFullName() for plug in plugs]

        self.assertEqual(names(target.getInputs(type="transform")), names(target.getInputs()))
        self.assertEqual(target.getInputs(type="mesh"), [])
        self.assertEqual(names(source.getOutputs(type="transform")), names(source.getOutputs()))
        self.assertEqual(source.getConnections(type="mesh"), [])

    def test_transform_matrix_round_trip_uses_om2_maths_values(self):
        transform = self.create_transform("hlibNodeApiMatrix")

        transform.setTranslation((1.0, 2.0, 3.0), at=4)
        transform.setRotation((0.0, math.radians(90.0), 0.0))
        transform.setScaling((2.0, 1.0, 1.0))

        translate = transform.getTranslation(at=4)
        self.assertIsInstance(translate, Translation)
        self.assertEqual(translate, Translation(1.0, 2.0, 3.0))

        scale = transform.getScaling()
        self.assertIsInstance(scale, Scale)
        self.assertAlmostEqual(scale.x, 2.0, places=6)

        matrix = transform.getMatrix()
        self.assertIsInstance(matrix, Matrix)
        self.assertEqual(matrix.translate, translate)

        # om2.MVector を継承するため、等価比較は om2 と同じ値の比較になり、
        # 派生型(Translation/Scale)が違っても成分が同じなら等しい。型は保持される。
        self.assertEqual(translate, Scale(1.0, 2.0, 3.0))
        self.assertIsNot(type(translate), Scale)

    def test_transform_pivot_get_set_local_and_world(self):
        transform = self.create_transform("hlibNodeApiPivot")

        default_pivot = transform.getPivot()
        self.assertIsInstance(default_pivot, Translation)
        self.assertEqual(default_pivot, Translation(0.0, 0.0, 0.0))

        result = transform.setPivot((1.0, 2.0, 3.0), kind="both", preserve=False)
        self.assertIs(result, transform)
        self.assertEqual(transform.getPivot(), Translation(1.0, 2.0, 3.0))
        cmds.undo()
        self.assertEqual(transform.getPivot(), default_pivot)
        cmds.redo()
        self.assertEqual(transform.getPivot(), Translation(1.0, 2.0, 3.0))

        transform.setTranslation((10.0, 0.0, 0.0), at=4)
        self.assertEqual(transform.getPivot(ws=True), Translation(11.0, 2.0, 3.0))

        previous_unit = cmds.currentUnit(query=True, linear=True)
        try:
            cmds.currentUnit(linear="m")
            transform.setPivot((25.0, 50.0, 75.0), ws=True, kind="both", preserve=False)
            self.assertEqual(transform.getPivot(ws=True), Translation(25.0, 50.0, 75.0))
            cmds.undo()
            self.assertEqual(transform.getPivot(ws=True), Translation(11.0, 2.0, 3.0))
            cmds.redo()
            self.assertEqual(transform.getPivot(ws=True), Translation(25.0, 50.0, 75.0))
        finally:
            cmds.currentUnit(linear=previous_unit)

    def test_transform_bounding_box_local_and_world(self):
        mesh_transform_name = cmds.polyCube(name="hlibNodeApiBoundingBoxMesh", constructionHistory=False)[0]
        self.created.append(mesh_transform_name)
        transform = Node(mesh_transform_name)

        box = transform.getBoundingBox()
        self.assertAlmostEqual(box.min.x, -0.5, places=5)
        self.assertAlmostEqual(box.max.x, 0.5, places=5)

        # boundingBox() は自身の translate は含むが、親の変換はまだ無いので world と一致する。
        transform.setTranslation((10.0, 0.0, 0.0), at=4)
        self.assertAlmostEqual(transform.getBoundingBox().min.x, 9.5, places=5)
        self.assertAlmostEqual(transform.getBoundingBox(ws=True).min.x, 9.5, places=5)

        parent = self.create_transform("hlibNodeApiBoundingBoxParent")
        parent.setTranslation((100.0, 0.0, 0.0), at=4)
        # relative=True で子のローカル translate を変えずに親子付けする
        # （既定はワールド位置維持のためローカル値が自動調整されてしまう）。
        cmds.parent(mesh_transform_name, parent.getName(), relative=True)

        # ws=False は親の translate を含まない。ws=True は含む。
        self.assertAlmostEqual(transform.getBoundingBox().min.x, 9.5, places=5)
        world_box = transform.getBoundingBox(ws=True)
        self.assertAlmostEqual(world_box.min.x, 109.5, places=5)
        self.assertAlmostEqual(world_box.max.x, 110.5, places=5)

    def test_node_lock_and_referenced_and_type_checks(self):
        transform = self.create_transform("hlibNodeApiLockType")

        self.assertFalse(transform.isLocked())
        cmds.lockNode(transform.getName(), lock=True)
        self.assertTrue(transform.isLocked())
        cmds.lockNode(transform.getName(), lock=False)

        self.assertFalse(transform.isFromReferencedFile())

        self.assertTrue(transform.isType("transform"))
        self.assertTrue(transform.isType("dagNode"))
        self.assertFalse(transform.isType("mesh"))
        with self.assertRaises(ValueError):
            transform.isType("")

    def test_ancestor_and_root_queries(self):
        grandparent = self.create_transform("hlibNodeApiRootGP")
        parent = self.create_transform("hlibNodeApiRootP")
        child = self.create_transform("hlibNodeApiRootC")
        parent.setParent(grandparent)
        child.setParent(parent)

        self.assertTrue(grandparent.isAncestorOf(child))
        self.assertTrue(grandparent.isAncestorOf(parent))
        self.assertTrue(parent.isAncestorOf(child))
        self.assertFalse(child.isAncestorOf(grandparent))
        self.assertFalse(grandparent.isAncestorOf(grandparent))

        self.assertEqual(child.getRoot().getFullName(), grandparent.getFullName())
        self.assertEqual(parent.getRoot().getFullName(), grandparent.getFullName())
        self.assertEqual(grandparent.getRoot().getFullName(), grandparent.getFullName())

    def test_shape_is_intermediate_object(self):
        mesh_transform_name = cmds.polyCube(name="hlibNodeApiIntermediate", constructionHistory=False)[0]
        self.created.append(mesh_transform_name)
        shape = Node(mesh_transform_name).getShape()

        self.assertFalse(shape.isIntermediateObject())
        cmds.setAttr(shape.getFullName() + ".intermediateObject", True)
        self.assertTrue(shape.isIntermediateObject())

    def test_plug_is_keyable_and_parent(self):
        transform = self.create_transform("hlibNodeApiPlugMeta")
        translate = transform.getPlug("translate")
        translate_x = transform.getPlug("translateX")

        self.assertTrue(translate_x.isKeyable())
        self.assertIsNone(translate.getParent())
        self.assertEqual(translate_x.getParent().getFullName(), translate.getFullName())

        cmds.setAttr(translate_x.getFullName(), keyable=False)
        self.assertFalse(translate_x.isKeyable())

    def test_plug_hidden_dynamic_limits_default_and_enum(self):
        transform = self.create_transform("hlibNodeApiPlugAttrMeta")
        cmds.addAttr(transform.getName(), longName="hlibTestNum", attributeType="double",
                     min=0, max=10, defaultValue=5, hidden=True)
        cmds.addAttr(transform.getName(), longName="hlibTestNoLimit", attributeType="double",
                     defaultValue=1.5)
        cmds.addAttr(transform.getName(), longName="hlibTestEnum", attributeType="enum",
                     enumName="A:B:C", defaultValue=1)

        num_plug = transform.getPlug("hlibTestNum")
        self.assertTrue(num_plug.isDynamic())
        self.assertTrue(num_plug.isHidden())
        self.assertTrue(num_plug.hasMin())
        self.assertTrue(num_plug.hasMax())
        self.assertEqual(num_plug.getMin(), 0.0)
        self.assertEqual(num_plug.getMax(), 10.0)
        self.assertEqual(num_plug.getDefault(), 5.0)

        no_limit_plug = transform.getPlug("hlibTestNoLimit")
        self.assertFalse(no_limit_plug.isHidden())
        self.assertFalse(no_limit_plug.hasMin())
        self.assertFalse(no_limit_plug.hasMax())
        self.assertIsNone(no_limit_plug.getMin())
        self.assertIsNone(no_limit_plug.getMax())
        self.assertEqual(no_limit_plug.getDefault(), 1.5)

        enum_plug = transform.getPlug("hlibTestEnum")
        self.assertEqual(enum_plug.getDefault(), 1)
        self.assertEqual(enum_plug.getEnumName(), "B")

        # 静的（ノード組み込み）アトリビュートは動的アトリビュートではない。
        self.assertFalse(transform.getPlug("translateX").isDynamic())
        with self.assertRaises(TypeError):
            transform.getPlug("translateX").getEnumName()

    def test_plug_readable_writable_storable_and_soft_limits(self):
        transform = self.create_transform("hlibNodeApiPlugFlags")
        cmds.addAttr(transform.getName(), longName="hlibSoftAttr", attributeType="double",
                     softMinValue=0, softMaxValue=10, defaultValue=2)
        plug = transform.getPlug("hlibSoftAttr")

        self.assertTrue(plug.isReadable())
        self.assertTrue(plug.isWritable())
        self.assertTrue(plug.isStorable())
        self.assertTrue(plug.hasSoftMin())
        self.assertTrue(plug.hasSoftMax())
        self.assertEqual(plug.getSoftMin(), 0.0)
        self.assertEqual(plug.getSoftMax(), 10.0)

        translate_x = transform.getPlug("translateX")
        self.assertTrue(translate_x.isReadable())
        self.assertTrue(translate_x.isWritable())
        self.assertTrue(translate_x.isStorable())
        self.assertFalse(translate_x.hasSoftMin())
        self.assertFalse(translate_x.hasSoftMax())

    def test_node_type_id_and_classification(self):
        transform = self.create_transform("hlibNodeApiTypeId")
        self.assertIsInstance(transform.getTypeId(), int)
        self.assertEqual(transform.getClassification(), cmds.getClassification("transform"))
        # transform は Maya 組み込みノード型なのでプラグイン名は空文字列。
        self.assertEqual(transform.getPluginName(), "")

    def test_transform_leaves_siblings_and_child_transforms(self):
        root = self.create_transform("hlibNodeApiLeavesRoot")
        branch_a = self.create_transform("hlibNodeApiLeavesA")
        branch_b = self.create_transform("hlibNodeApiLeavesB")
        leaf_a1 = self.create_transform("hlibNodeApiLeavesA1")
        branch_a.setParent(root)
        branch_b.setParent(root)
        leaf_a1.setParent(branch_a)

        self.assertEqual(
            sorted(node.getName() for node in root.getChildren()),
            ["hlibNodeApiLeavesA", "hlibNodeApiLeavesB"],
        )

        leaf_names = sorted(node.getName() for node in root.getLeaves())
        self.assertEqual(leaf_names, ["hlibNodeApiLeavesA1", "hlibNodeApiLeavesB"])
        self.assertEqual(leaf_a1.getLeaves(), [leaf_a1])

        self.assertEqual([s.getName() for s in branch_a.getSiblings()], ["hlibNodeApiLeavesB"])
        self.assertEqual(branch_b.getSiblings()[0].getName(), "hlibNodeApiLeavesA")

        world_sibling = self.create_transform("hlibNodeApiLeavesWorldSibling")
        root_sibling_names = {s.getName() for s in root.getSiblings()}
        self.assertIn("hlibNodeApiLeavesWorldSibling", root_sibling_names)
        self.assertNotIn("hlibNodeApiLeavesRoot", root_sibling_names)

    def test_plug_anim_curve_and_mute(self):
        transform = self.create_transform("hlibNodeApiAnimCurve")
        plug = transform.getPlug("translateX")

        self.assertIsNone(plug.getAnimCurve())

        cmds.setKeyframe(plug.getFullName(), time=1, value=0.0)
        cmds.setKeyframe(plug.getFullName(), time=24, value=10.0)

        curve = plug.getAnimCurve()
        self.assertIsNotNone(curve)
        self.assertTrue(curve.isType("animCurve"))

        self.assertFalse(plug.isMuted())
        result = plug.setMuted(True)
        self.assertIs(result, plug)
        self.assertTrue(plug.isMuted())
        plug.setMuted(False)
        self.assertFalse(plug.isMuted())

        # 非 animCurve 接続では animCurve() は None を返す。
        other = self.create_transform("hlibNodeApiAnimCurveOther")
        other.getPlug("translateX").connectTo(transform.getPlug("translateY"))
        self.assertIsNone(transform.getPlug("translateY").getAnimCurve())

    def test_direct_parent_child_relationship_and_attribute_count(self):
        grandparent = self.create_transform("hlibNodeApiDirectGP")
        parent = self.create_transform("hlibNodeApiDirectP")
        child = self.create_transform("hlibNodeApiDirectC")
        parent.setParent(grandparent)
        child.setParent(parent)

        self.assertTrue(grandparent.isParentOf(parent))
        self.assertFalse(grandparent.isParentOf(child))
        self.assertTrue(grandparent.isAncestorOf(child))

        self.assertTrue(parent.isChildOf(grandparent))
        self.assertFalse(child.isChildOf(grandparent))

        self.assertGreater(child.getAttrCount(), 0)

    def test_plug_delete_attr(self):
        transform = self.create_transform("hlibNodeApiDeleteAttr")
        cmds.addAttr(transform.getName(), longName="hlibDeleteMe", attributeType="double", defaultValue=1.0)
        plug = transform.getPlug("hlibDeleteMe")

        self.assertTrue(cmds.attributeQuery("hlibDeleteMe", node=transform.getName(), exists=True))
        plug.delete()
        self.assertFalse(cmds.attributeQuery("hlibDeleteMe", node=transform.getName(), exists=True))

        with self.assertRaises(RuntimeError):
            transform.getPlug("translateX").delete()

    def test_plug_delete_attr_force_unlocks_before_deleting(self):
        transform = self.create_transform("hlibNodeApiDeleteAttrForce")
        cmds.addAttr(transform.getName(), longName="hlibLockedDelete", attributeType="double", defaultValue=1.0)
        plug = transform.getPlug("hlibLockedDelete")
        plug.setFlags(locked=True)

        with self.assertRaises(RuntimeError):
            plug.delete()
        self.assertTrue(cmds.attributeQuery("hlibLockedDelete", node=transform.getName(), exists=True))

        plug.delete(force=True)
        self.assertFalse(cmds.attributeQuery("hlibLockedDelete", node=transform.getName(), exists=True))

    def test_node_plugs_enumerates_attributes_as_plug_objects(self):
        transform = self.create_transform("hlibNodeApiPlugs")

        plugs = transform.getPlugs()
        self.assertIn("translateX", {plug.getLongName() for plug in plugs})
        self.assertTrue(all(hasattr(plug, "get") for plug in plugs))
        # listAttr が報告する名前の一部（未確保の要素を持つ配列複合アトリビュートの子など）は
        # 実際には評価できず黙ってスキップされるため、件数は必ずしも一致しない。
        self.assertLessEqual(len(plugs), len(cmds.listAttr(transform.getName()) or []))

        keyable_names = set(cmds.listAttr(transform.getName(), keyable=True) or [])
        keyable_plugs = transform.getPlugs(keyable=True)
        self.assertEqual({plug.getLongName() for plug in keyable_plugs}, keyable_names)

    def test_node_aliases_returns_alias_plug_pairs(self):
        transform = self.create_transform("hlibNodeApiAliases")
        self.assertEqual(transform.getAliases(), [])

        cmds.aliasAttr("hlibTx", transform.getPlug("translateX").getFullName())
        aliases = transform.getAliases()
        self.assertEqual(len(aliases), 1)
        alias_name, plug = aliases[0]
        self.assertEqual(alias_name, "hlibTx")
        self.assertEqual(plug.getFullName(), transform.getPlug("translateX").getFullName())

    def test_plug_set_keyable_and_set_channel_box(self):
        transform = self.create_transform("hlibNodeApiKeyableCB")
        plug = transform.getPlug("translateX")

        result = plug.setFlags(keyable=False)
        self.assertIs(result, plug)
        self.assertFalse(plug.isKeyable())

        plug.setFlags(channelBox=True)
        self.assertFalse(plug.isKeyable())
        self.assertTrue(cmds.getAttr(plug.getFullName(), channelBox=True))

        plug.setFlags(keyable=True)
        self.assertTrue(plug.isKeyable())

    def test_plug_nice_name_and_is_connected_to(self):
        source = self.create_transform("hlibNodeApiNiceNameSource")
        target = self.create_transform("hlibNodeApiNiceNameTarget")

        self.assertEqual(source.getPlug("translateX").getNiceName(), "Translate X")

        source_plug = source.getPlug("translateX")
        targetPlug = target.getPlug("translateX")
        self.assertFalse(source_plug.isConnectedTo(targetPlug))

        source_plug.connectTo(targetPlug)
        self.assertTrue(source_plug.isConnectedTo(targetPlug))
        self.assertTrue(targetPlug.isConnectedTo(source_plug))
        self.assertFalse(source_plug.isConnectedTo(source.getPlug("translateY")))

    def test_plug_enum_value_reverses_enum_name(self):
        transform = self.create_transform("hlibNodeApiEnumValue")
        cmds.addAttr(transform.getName(), longName="hlibEnumValueAttr", attributeType="enum",
                     enumName="A:B:C", defaultValue=0)
        plug = transform.getPlug("hlibEnumValueAttr")

        self.assertEqual(plug.getEnumValue("B"), 1)
        self.assertEqual(plug.getEnumValue(plug.getEnumName()), 0)
        with self.assertRaises(ValueError):
            plug.getEnumValue("NotAField")
        with self.assertRaises(TypeError):
            transform.getPlug("translateX").getEnumValue("A")

    def test_plug_get_dispatches_by_attribute_type_via_om2(self):
        # Plug.get() は bool/int/float/角度・距離・時間/enum/文字列を
        # MPlug 経由で直接読み取る。cmds.getAttr の結果と一致することを
        # 各アトリビュート型ごとに確認する（角度は度、距離・時間は現在のUI単位）。
        transform = self.create_transform("hlibNodeApiPlugGetTypes")
        name = transform.getName()
        cmds.addAttr(name, longName="hlibBool", attributeType="bool", defaultValue=True)
        cmds.addAttr(name, longName="hlibLong", attributeType="long", defaultValue=42)
        cmds.addAttr(name, longName="hlibShort", attributeType="short", defaultValue=7)
        cmds.addAttr(name, longName="hlibDouble", attributeType="double", defaultValue=1.5)
        cmds.addAttr(name, longName="hlibFloat", attributeType="float", defaultValue=2.5)
        cmds.addAttr(name, longName="hlibString", dataType="string")
        cmds.setAttr(name + ".hlibString", "hello", type="string")
        cmds.addAttr(name, longName="hlibEnum", attributeType="enum", enumName="A:B:C", defaultValue=2)
        cmds.addAttr(name, longName="hlibAngle", attributeType="doubleAngle", defaultValue=0.0)
        cmds.setAttr(name + ".hlibAngle", 90.0)
        cmds.addAttr(name, longName="hlibDistance", attributeType="doubleLinear", defaultValue=0.0)
        cmds.setAttr(name + ".hlibDistance", 5.0)
        cmds.addAttr(name, longName="hlibTime", attributeType="time", defaultValue=0.0)
        cmds.setAttr(name + ".hlibTime", 3.0)

        for attribute in (
            "hlibBool", "hlibLong", "hlibShort", "hlibDouble", "hlibFloat",
            "hlibString", "hlibEnum", "hlibAngle", "hlibDistance", "hlibTime",
            "translateX", "visibility",
        ):
            with self.subTest(attribute=attribute):
                plug_value = transform.getPlug(attribute).get()
                cmds_value = cmds.getAttr(f"{name}.{attribute}")
                if attribute == "hlibAngle":
                    cmds_value = math.pi / 2
                elif attribute == "hlibTime":
                    cmds_value = 3.0 / 24
                self.assertAlmostEqual(plug_value, cmds_value) if isinstance(cmds_value, float) \
                    else self.assertEqual(plug_value, cmds_value)

        self.assertIsInstance(transform.getPlug("hlibBool").get(), bool)
        self.assertIsInstance(transform.getPlug("hlibLong").get(), int)
        self.assertIsInstance(transform.getPlug("hlibString").get(), str)

        # 読み方は Plug ごとに一度だけ選んで保持するが、単位の変換は呼び出しごとに現在の
        # UI 単位で行う(同じ Plug で単位を変えても cmds.getAttr と一致する)。
        plugs = {attribute: transform.getPlug(attribute)
                 for attribute in ("hlibDistance", "hlibTime", "hlibAngle", "translateX")}
        for plug in plugs.values():
            plug.get()
        previous = (cmds.currentUnit(query=True, linear=True), cmds.currentUnit(query=True, time=True))
        try:
            cmds.currentUnit(linear="mm", time="ntsc")
            for attribute, plug in plugs.items():
                with self.subTest(attribute=attribute, unit="mm/ntsc"):
                    self.assertAlmostEqual(plug.get(), {"hlibDistance": 5., "hlibTime": 3./24, "hlibAngle": math.pi/2, "translateX": 0.}[attribute])
        finally:
            cmds.currentUnit(linear=previous[0], time=previous[1])

    def test_plug_get_falls_back_to_cmds_for_unsupported_typed_data(self):
        # stringArray は MFnTypedAttribute だが kString ではないため、
        # om2 の直接読み取りは対象外となり cmds.getAttr にフォールバックする。
        transform = self.create_transform("hlibNodeApiPlugGetFallback")
        cmds.addAttr(transform.getName(), longName="hlibStringArray", dataType="stringArray")
        cmds.setAttr(transform.getName() + ".hlibStringArray", 2, "a", "b", type="stringArray")

        value = transform.getPlug("hlibStringArray").get()
        self.assertEqual(value, cmds.getAttr(transform.getName() + ".hlibStringArray"))

    def test_array_plug_next_available_add_and_remove_element(self):
        source = self.create_transform("hlibNodeApiArrayNextAvailSource")
        target = self.create_transform("hlibNodeApiArrayNextAvailTarget")
        array_plug = target.getPlug("worldMatrix")

        self.assertEqual(array_plug.getNextAvailableIndex(), 0)

        array_plug.getElement(0, create=True)
        self.assertEqual(array_plug.getNextAvailableIndex(), 1)
        self.assertEqual(array_plug.getNextAvailableIndex(start=5), 5)

        element = array_plug.addElement(1)[0]
        self.assertEqual(element.getLongName(), "worldMatrix")
        self.assertTrue(element.getFullName().endswith("[1]"))

        array_plug.removeElement(1)
        self.assertNotIn(1, array_plug.get())

        with self.assertRaises(IndexError):
            array_plug.removeElement(99)

    def test_transform_show_hide(self):
        transform = self.create_transform("hlibNodeApiShowHide")

        result = transform.setVisibility(False)
        self.assertIs(result, transform)
        self.assertFalse(transform.getPlug("visibility").get())

        transform.setVisibility(True)
        self.assertTrue(transform.getPlug("visibility").get())

    def test_transform_make_identity_freezes_transform(self):
        transform = self.create_transform("hlibNodeApiFreeze")
        transform.setTranslation((1.0, 2.0, 3.0), at=4)

        result = transform.makeIdentity(apply=True, translate=True)
        self.assertIs(result, transform)
        self.assertEqual(transform.getTranslation(at=4), Translation(0.0, 0.0, 0.0))

    def test_transform_unlock_and_disconnect_transform_channels_unlocks_and_disconnects(self):
        driver = self.create_transform("hlibNodeApiReleaseDriver")
        transform = self.create_transform("hlibNodeApiRelease")
        driver.getPlug("translateX").connectTo(transform.getPlug("translateX"))
        transform.getPlug("translate").setFlags(locked=True)
        transform.getPlug("rotateY").setFlags(locked=True)

        result = transform.unlockAndDisconnectTransformChannels()
        self.assertIs(result, transform)
        self.assertFalse(transform.getPlug("translate").isLocked())
        self.assertFalse(transform.getPlug("translateX").isLocked())
        self.assertFalse(transform.getPlug("rotateY").isLocked())
        self.assertIsNone(transform.getPlug("translateX").getSourceWithConversion())

    def test_transform_closest_axis_to_vector(self):
        transform = self.create_transform("hlibNodeApiClosestAxis")

        self.assertEqual(transform.getClosestAxisToVector(Vector(1.0, 0.0, 0.0)), "x")
        self.assertEqual(transform.getClosestAxisToVector(Vector(0.0, -1.0, 0.0)), "-y")
        self.assertEqual(transform.getClosestAxisToVector(Vector(0.0, 1.0, 0.0), include_negative=False), "y")

        transform.setRotation((0.0, math.radians(90.0), 0.0))
        self.assertEqual(transform.getClosestAxisToVector(Vector(0.0, 0.0, -1.0)), "x")

    def test_transform_create_offset_groups_preserves_world_position(self):
        parent = self.create_transform("hlibNodeApiOffsetParent")
        parent.setTranslation((5.0, 0.0, 0.0), at=4)
        transform = self.create_transform("hlibNodeApiOffsetChild")
        transform.setParent(parent)
        transform.setTranslation((1.0, 2.0, 3.0), at=4)
        world_translate = transform.getTranslation(ws=True, at=4)

        zero, offset = transform.createOffsetGroups("hlibNodeApiZero", "hlibNodeApiOffset")
        self.created.extend([zero.getName(), offset.getName()])

        self.assertEqual(zero.getParent().getName(), parent.getName())
        self.assertEqual(offset.getParent().getName(), zero.getName())
        self.assertEqual(transform.getParent().getName(), offset.getName())
        self.assertEqual(zero.getTranslation(ws=True, at=4), world_translate)
        self.assertEqual(offset.getTranslation(ws=True, at=4), world_translate)
        self.assertEqual(transform.getTranslation(ws=True, at=4), world_translate)
        self.assertEqual(transform.getTranslation(at=4), Translation(0.0, 0.0, 0.0))

    def test_node_is_valid_is_alive_and_has_attr(self):
        transform = self.create_transform("hlibNodeApiValidity")
        self.assertTrue(transform.isValid())
        self.assertTrue(transform.isAlive())
        self.assertTrue(transform.hasAttr("translateX"))
        self.assertFalse(transform.hasAttr("hlibNoSuchAttr"))

        cmds.delete(transform.getName())
        self.assertFalse(transform.isValid())
        self.assertIsInstance(transform.isAlive(), bool)

    def test_transform_shear_quaternion_euler_and_decompose(self):
        transform = self.create_transform("hlibNodeApiShearQuat")
        result = transform.setShearing((0.1, 0.2, 0.3))
        self.assertIs(result, transform)
        shear = transform.getShearing()
        self.assertIsInstance(shear, Shear)
        self.assertAlmostEqual(shear.x, 0.1, places=6)
        self.assertAlmostEqual(shear.y, 0.2, places=6)
        self.assertAlmostEqual(shear.z, 0.3, places=6)

        transform.setRotation((0.0, math.radians(90.0), 0.0))
        quaternion = transform.getQuaternion()
        self.assertIsInstance(quaternion, Quaternion)
        euler = transform.getEuler()
        self.assertIsInstance(euler, EulerRotation)
        self.assertAlmostEqual(euler.y, math.radians(90.0), places=6)

        matrix = transform.getMatrix(ws=True)
        self.assertIsInstance(matrix, Matrix)
        self.assertEqual(matrix, transform.getMatrix(ws=True))

    def test_transform_set_matrix_round_trips_matrix_and_rejects_non_matrix(self):
        source = self.create_transform("hlibNodeApiComposeSource")
        source.setTranslation((1.0, 2.0, 3.0), at=4)
        source.setRotation((0.0, math.radians(45.0), 0.0))
        matrix = source.getMatrix(ws=True)

        target = self.create_transform("hlibNodeApiComposeTarget")
        result = target.setMatrix(matrix, ws=True)
        self.assertIs(result, target)
        self.assertTrue(target.getMatrix(ws=True).isEquivalent(matrix, tolerance=1e-6))

        with self.assertRaises(ValueError):
            target.setMatrix((1, 2, 3))

    def test_transform_set_matrix_direct_accepts_raw_values_and_guards_invalid_node(self):
        transform = self.create_transform("hlibNodeApiSetMatrixDirect")
        matrix = Matrix(translate=(1.0, 2.0, 3.0))
        result = transform.setMatrix(matrix)
        self.assertIs(result, transform)
        self.assertEqual(transform.getTranslation(at=4), Translation(1.0, 2.0, 3.0))

        # Matrix以外の16要素入力も内部でMatrixへ変換して受け付ける。
        transform.setMatrix((
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            5.0, 6.0, 7.0, 1.0,
        ))
        self.assertEqual(transform.getTranslation(at=4), Translation(5.0, 6.0, 7.0))

        cmds.delete(transform.getName())
        with self.assertRaises(RuntimeError):
            transform.setMatrix(matrix)

    def test_transform_set_matrix_round_trip_preserves_world_for_every_rotate_order(self):
        # XYZ で分解した回転をノードの rotateOrder へ並べ替えて書き込むため、
        # xyz 以外の順序でも setMatrix / setTranslation / rotate プラグの往復で姿勢が変わらない。
        parent = self.create_transform("hlibNodeApiOrderParent")
        cmds.setAttr(parent.getFullName() + ".rotate", 10.0, 20.0, 30.0)
        for order in range(6):
            node = self.create_transform("hlibNodeApiOrder%d" % order)
            node.setParent(parent)
            name = node.getFullName()
            cmds.setAttr(name + ".rotateOrder", order)
            cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
            cmds.setAttr(name + ".rotate", 40.0, -50.0, 60.0)
            cmds.setAttr(name + ".scale", 1.0, 2.0, 3.0)
            world = node.getMatrix(ws=True)

            node.setMatrix(node.getMatrix())
            self.assertTrue(node.getMatrix(ws=True).isEquivalent(world, 1e-9), order)
            node.setMatrix(world, ws=True)
            self.assertTrue(node.getMatrix(ws=True).isEquivalent(world, 1e-9), order)
            node.setTranslation((4.0, 5.0, 6.0), at=4)
            self.assertTrue(node.getQuaternion(ws=True).isEquivalent(world.quaternion, 1e-9), order)

            before = node.getMatrix()
            rotate = node.getPlug("rotate").get()
            self.assertIsInstance(rotate, EulerRotation)
            self.assertEqual(rotate.order, order)
            node.getPlug("rotate").set(rotate)
            self.assertTrue(node.getMatrix().isEquivalent(before, 1e-9), order)
            node.setRotation(EulerRotation.fromDegrees(40.0, -50.0, 60.0, order))
            self.assertTrue(node.getMatrix().isEquivalent(before, 1e-9), order)
        with self.assertRaises(ValueError):
            node.setRotation(EulerRotation(0.1, 0.2, 0.3), unit="deg")

    def assert_channels(self, name, rotate, scale, places=9):
        for actual, expected in zip(cmds.getAttr(name + ".rotate")[0], rotate):
            self.assertAlmostEqual(actual, expected, places=places)
        for actual, expected in zip(cmds.getAttr(name + ".scale")[0], scale):
            self.assertAlmostEqual(actual, expected, places=places)

    def test_transform_negative_scale_keeps_channel_sign_pattern(self):
        # Matrix の分解は om2 の規約(Z が負)だが、ノードの取得・設定はスケールの符号を
        # 現在の scale チャンネルへ揃えるため、X をミラーしたノードでも rotate が保たれる。
        node = self.create_transform("hlibNodeApiNegativeScale")
        name = node.getFullName()
        cmds.setAttr(name + ".rotate", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".scale", -1.0, 2.0, 3.0)
        matrix = node.getMatrix()
        transformation = om2.MTransformationMatrix(matrix)
        self.assertTrue(matrix.scale.isEquivalent(Vector(*transformation.scale(om2.MSpace.kTransform)), 1e-12))
        self.assertLess(matrix.scale.z, 0.0)

        scale = node.getScaling()
        self.assertIsInstance(scale, Scale)
        self.assertTrue(scale.isEquivalent(Scale(-1.0, 2.0, 3.0), 1e-12))
        rotate = node.getRotation()
        self.assertTrue(rotate.isEquivalent(EulerRotation.fromDegrees(10.0, 20.0, 30.0), 1e-12))
        self.assertTrue(Matrix(rotate=node.getQuaternion(), scale=scale).isEquivalent(matrix, 1e-12))

        world = node.getMatrix(ws=True)
        for operation in (
            lambda: node.setMatrix(matrix),
            lambda: node.setMatrix(world, ws=True),
            lambda: node.setTranslation((0.0, 0.0, 0.0), at=4),
            lambda: node.setScaling(node.getScaling()),
            lambda: node.setShearing(node.getShearing()),
            lambda: node.setRotation((10.0, 20.0, 30.0), unit="deg"),
            lambda: node.getPlug("rotate").set(tuple(node.getPlug("rotate").get())),
        ):
            operation()
            self.assertTrue(node.getMatrix().isEquivalent(matrix, 1e-9))
            self.assert_channels(name, (10.0, 20.0, 30.0), (-1.0, 2.0, 3.0))

        # スケールだけを変えても rotate は変わらない(ミラーを解除しても姿勢が 180 度回らない)。
        node.setScaling((1.0, 2.0, 3.0))
        self.assert_channels(name, (10.0, 20.0, 30.0), (1.0, 2.0, 3.0))

    def test_set_scale_writes_the_requested_signs(self):
        # setScale / plug("scale").set で明示した符号は、現在の scale チャンネルの符号に
        # かかわらずそのまま入り、rotate も変わらない(cmds.setAttr で scale を書いた場合と同じ)。
        cases = (
            ((1.0, 1.0, 1.0), (-1.0, 1.0, 1.0)),
            ((-1.0, -2.0, 3.0), (1.0, 1.0, 1.0)),
            ((-1.0, -1.0, 1.0), (2.0, 2.0, 2.0)),
            ((1.0, 1.0, 1.0), (1.0, -1.0, 1.0)),
            ((-1.0, 1.0, 1.0), (-2.0, -3.0, -4.0)),
            ((1.0, 2.0, 3.0), (-1.0, -2.0, -3.0)),
        )
        for kind in ("transform", "joint"):
            for use_plug in (False, True):
                for order in (0, 4):
                    for start, requested in cases:
                        name = cmds.createNode(kind, name=self.namespace + ":hlibNodeApiScaleSign")
                        self.created.append(name)
                        cmds.setAttr(name + ".rotateOrder", order)
                        cmds.setAttr(name + ".rotate", 10.0, 20.0, 30.0)
                        cmds.setAttr(name + ".scale", *start)
                        node = Node(name)
                        if use_plug:
                            node.getPlug("scale").set(requested)
                        else:
                            node.setScaling(requested)
                        label = (kind, use_plug, order, start, requested)
                        for actual, expected in zip(cmds.getAttr(name + ".scale")[0], requested):
                            self.assertAlmostEqual(actual, expected, places=9, msg=label)
                        for actual, expected in zip(cmds.getAttr(name + ".rotate")[0], (10.0, 20.0, 30.0)):
                            self.assertAlmostEqual(actual, expected, places=9, msg=label)
                        self.assertTrue(node.getScaling().isEquivalent(Scale(*requested), 1e-9), label)
                        cmds.delete(name)

        # ワールド空間でも、親の行列式が正なら要求した符号の組み合わせになる。
        parent = self.create_transform("hlibNodeApiScaleSignParent")
        cmds.setAttr(parent.getFullName() + ".rotate", 30.0, 0.0, 0.0)
        cmds.setAttr(parent.getFullName() + ".scale", 2.0, 2.0, 2.0)
        child = self.create_transform("hlibNodeApiScaleSignChild")
        child.setParent(parent)
        cmds.setAttr(child.getFullName() + ".rotate", 10.0, 20.0, 30.0)
        child.setScaling((-1.0, 1.0, 1.0), ws=True)
        self.assert_channels(child.getFullName(), (10.0, 20.0, 30.0), (0.5, 0.5, -0.5))
        self.assertTrue(child.getScaling(ws=True).isEquivalent(Scale(1.0, 1.0, -1.0), 1e-9))

        # setMatrix は現在のチャンネルの符号に揃え、合わなければ om2 の規約(Z が負)で書く。
        target = self.create_transform("hlibNodeApiScaleSignMatrix")
        target.setMatrix(Matrix(scale=(-1.0, 1.0, 1.0)))
        self.assert_channels(target.getFullName(), (0.0, 180.0, 0.0), (1.0, 1.0, -1.0))
        self.assertTrue(target.getMatrix().isEquivalent(Matrix(scale=(-1.0, 1.0, 1.0)), 1e-9))

    def test_transform_matrix_writes_choose_the_closest_euler_solution(self):
        node = self.create_transform("hlibNodeApiClosestEuler")
        name = node.getFullName()
        cmds.setAttr(name + ".rotate", 370.0, -20.0, 190.0)
        node.setMatrix(node.getMatrix())
        node.setTranslation((1.0, 2.0, 3.0), at=4)
        self.assert_channels(name, (370.0, -20.0, 190.0), (1.0, 1.0, 1.0))
        # 等価な別解 (180+10, 180-(-20), 180+190) を渡しても、現在値に近い解で書く。
        node.setRotation(EulerRotation.fromDegrees(190.0, 200.0, 370.0))
        self.assert_channels(name, (370.0, -20.0, 190.0), (1.0, 1.0, 1.0))

    def test_transform_flat_rotate_values_use_the_node_rotate_order(self):
        # 3成分の値は cmds.xform と同じくノードの rotateOrder の値として扱うため、
        # plug("rotate") の get と set、getRotation と setRotation が対称になる。
        parent = self.create_transform("hlibNodeApiFlatOrderParent")
        cmds.setAttr(parent.getFullName() + ".rotate", 15.0, -25.0, 40.0)
        for order in range(6):
            node = self.create_transform("hlibNodeApiFlatOrder%d" % order)
            node.setParent(parent)
            name = node.getFullName()
            cmds.setAttr(name + ".rotateOrder", order)
            cmds.setAttr(name + ".rotate", 10.0, 20.0, 30.0)
            local = node.getMatrix()
            world = node.getMatrix(ws=True)

            rotate = node.getRotation()
            self.assertEqual(rotate.order, order)
            self.assertTrue(rotate.isEquivalent(EulerRotation.fromDegrees(10.0, 20.0, 30.0, order), 1e-12))

            plug = node.getPlug("rotate")
            plug.set(tuple(plug.get()))
            self.assert_channels(name, (10.0, 20.0, 30.0), (1.0, 1.0, 1.0))
            node.setRotation(tuple(node.getRotation()))
            node.setRotation(tuple(node.getRotation(ws=True)), ws=True)
            self.assertTrue(node.getMatrix(ws=True).isEquivalent(world, 1e-9), order)
            node.setRotation(tuple(node.getRotation(ws=True)), ws=True)
            self.assertTrue(node.getMatrix().isEquivalent(local, 1e-9), order)

            cmds.setAttr(name + ".rotate", 0.0, 0.0, 0.0)
            node.setRotation((10.0, 20.0, 30.0), unit="deg")
            self.assert_channels(name, (10.0, 20.0, 30.0), (1.0, 1.0, 1.0))
            cmds.setAttr(name + ".rotate", 0.0, 0.0, 0.0)
            plug.set(tuple(math.radians(value) for value in (10.0, 20.0, 30.0)))
            self.assert_channels(name, (10.0, 20.0, 30.0), (1.0, 1.0, 1.0))

    def test_om2_function_sets_accept_hlib_maths_values(self):
        node = self.create_transform("hlibNodeApiOm2Values")
        transformFn = om2.MFnTransform(node.mpath())
        transformFn.setTranslation(Translation(1.0, 2.0, 3.0), om2.MSpace.kTransform)
        self.assertEqual(node.getTranslation(at=4), Translation(1.0, 2.0, 3.0))

        euler = EulerRotation(0.3, -0.2, 0.1, "zyx")
        transformFn.setRotation(euler, om2.MSpace.kTransform)
        self.assertTrue(node.getQuaternion().isEquivalent(euler.asQuaternion(), 1e-9))
        quaternion = Quaternion.fromAxisAngle((0.0, 1.0, 0.0), 0.5)
        transformFn.setRotation(quaternion, om2.MSpace.kTransform)
        self.assertTrue(node.getQuaternion().isEquivalent(quaternion, 1e-9))
        transformFn.setScale(Scale(2.0, 3.0, 4.0))
        self.assertTrue(node.getScaling().isEquivalent(Scale(2.0, 3.0, 4.0), 1e-9))

        matrix = Matrix(translate=(5.0, 6.0, 7.0), rotate=EulerRotation(0.1, 0.2, 0.3, "yzx"))
        transformFn.setTransformation(om2.MTransformationMatrix(matrix))
        self.assertTrue(node.getMatrix().isEquivalent(matrix, 1e-9))

        selection = om2.MSelectionList()
        selection.add(node.getFullName())
        world = selection.getDagPath(0).inclusiveMatrix()
        self.assertTrue(node.getMatrix(ws=True).isEquivalent(world, 1e-12))
        self.assertTrue((om2.MPoint(1.0, 0.0, 0.0) * node.getMatrix(ws=True)).isEquivalent(
            om2.MPoint(node.getMatrix(ws=True).transformPoint((1.0, 0.0, 0.0))), 1e-12))

        plug = om2.MFnDependencyNode(node.mnode()).findPlug("offsetParentMatrix", False)
        plug.setMObject(om2.MFnMatrixData().create(Matrix(translate=(10.0, 0.0, 0.0))))
        self.assertEqual(node.getPlug("offsetParentMatrix").get(), Matrix(translate=(10.0, 0.0, 0.0)))

    def test_plug_structural_introspection_properties(self):
        transform = self.create_transform("hlibNodeApiPlugStructure")
        translatePlug = transform.getPlug("translate")
        translate_x_plug = transform.getPlug("translateX")
        world_matrix_plug = transform.getPlug("worldMatrix")

        self.assertTrue(translatePlug.isCompound())
        self.assertFalse(translatePlug.isArray())
        self.assertFalse(translatePlug.isElement())
        self.assertFalse(translatePlug.isChild())

        self.assertTrue(translate_x_plug.isChild())
        self.assertFalse(translate_x_plug.isCompound())

        self.assertTrue(world_matrix_plug.isArray())

        import maya.api.OpenMaya as om2
        self.assertIsInstance(translatePlug.mplug(), om2.MPlug)

        element = world_matrix_plug.getElement(0, create=True)
        self.assertTrue(element.isElement())

    def test_plug_connection_introspection_and_disconnect(self):
        source = self.create_transform("hlibNodeApiPlugConnSource")
        target = self.create_transform("hlibNodeApiPlugConnTarget")
        source_plug = source.getPlug("translateX")
        targetPlug = target.getPlug("translateX")

        self.assertFalse(source_plug.isConnected())
        self.assertFalse(source_plug.isSource())
        self.assertFalse(targetPlug.isDestination())

        source_plug.connectTo(targetPlug)
        self.assertTrue(source_plug.isConnected())
        self.assertTrue(source_plug.isSource())
        self.assertFalse(source_plug.isDestination())
        self.assertTrue(targetPlug.isConnected())
        self.assertTrue(targetPlug.isDestination())
        self.assertFalse(targetPlug.isSource())

        destinations = source_plug.getDestinationsWithConversions()
        self.assertEqual([plug.getFullName() for plug in destinations], [targetPlug.getFullName()])

        result = source_plug.disconnectAll()
        self.assertIs(result, source_plug)
        self.assertFalse(source_plug.isConnected())
        self.assertFalse(targetPlug.isConnected())
        self.assertEqual(source_plug.getDestinationsWithConversions(), [])

    def test_array_plug_elements_returns_all_existing(self):
        target = self.create_transform("hlibNodeApiArrayElements")
        array_plug = target.getPlug("worldMatrix")
        array_plug.getElement(0, create=True)

        elements = array_plug.getElements()
        self.assertEqual(len(elements), 1)
        self.assertTrue(elements[0].isElement())

    def test_bool_plug_toggle(self):
        transform = self.create_transform("hlibNodeApiBoolToggle")
        plug = transform.getPlug("visibility")
        plug.set(True)

        result = plug.toggle()
        self.assertIs(result, plug)
        self.assertFalse(plug.get())

        plug.toggle()
        self.assertTrue(plug.get())

    def test_user_attribute_names_excludes_compound_children(self):
        node = self.create_transform("hlibNodeApiUserAttrNames")
        node.addAttr("attrA", attributeType="double", defaultValue=0.0)
        cmds.addAttr(node.getFullName(), longName="attrCompound", attributeType="double3")
        cmds.addAttr(node.getFullName(), longName="attrCompoundX", attributeType="double", parent="attrCompound")
        cmds.addAttr(node.getFullName(), longName="attrCompoundY", attributeType="double", parent="attrCompound")
        cmds.addAttr(node.getFullName(), longName="attrCompoundZ", attributeType="double", parent="attrCompound")
        node.addAttr("attrB", attributeType="double", defaultValue=0.0)

        self.assertEqual(node.getExtraAttrNames(), ["attrA", "attrCompound", "attrB"])

    def test_move_attribute_reorders_and_preserves_state_and_connections(self):
        node = self.create_transform("hlibNodeApiMoveAttrNode")
        source = self.create_transform("hlibNodeApiMoveAttrSource")
        node.addAttr("attrA", attributeType="double", defaultValue=1.0, keyable=True)
        node.addAttr("attrB", attributeType="double", defaultValue=2.0, keyable=True)
        node.addAttr("attrC", attributeType="double", defaultValue=3.0, keyable=True)
        node.getPlug("attrB").set(5.0)
        node.getPlug("attrB").setFlags(locked=True)
        source.getPlug("translateX").set(7.0)
        source.getPlug("translateX").connectTo(node.getPlug("attrC"))
        self.assertEqual(node.getExtraAttrNames(), ["attrA", "attrB", "attrC"])

        result = node.moveAttrOrder("attrC", -2)

        self.assertIs(result, node)
        self.assertEqual(node.getExtraAttrNames(), ["attrC", "attrA", "attrB"])
        self.assertEqual(node.getPlug("attrA").get(), 1.0)
        self.assertEqual(node.getPlug("attrB").get(), 5.0)
        self.assertTrue(node.getPlug("attrB").isLocked())
        # attrC は接続で駆動されているため、再作成後も接続元の値がそのまま反映される。
        self.assertEqual(node.getPlug("attrC").get(), 7.0)
        reconnected_source = node.getPlug("attrC").getSourceWithConversion()
        self.assertIsNotNone(reconnected_source)
        self.assertEqual(reconnected_source.getFullName(), source.getPlug("translateX").getFullName())

    def test_move_attribute_supports_enum_and_string_attributes(self):
        node = self.create_transform("hlibNodeApiMoveAttrEnumString")
        node.addAttr("attrA", attributeType="double", defaultValue=0.0)
        node.addAttr("attrMode", attributeType="enum", enumName="Off:On:Auto", defaultValue=1)
        node.addAttr("attrLabel", dataType="string")
        node.getPlug("attrMode").set(2)
        node.getPlug("attrLabel").set("hello world")

        node.moveAttrOrder("attrMode", 1)

        self.assertEqual(node.getExtraAttrNames(), ["attrA", "attrLabel", "attrMode"])
        self.assertEqual(node.getPlug("attrMode").get(), 2)
        self.assertEqual(node.getPlug("attrMode").getEnumName(), "Auto")
        self.assertEqual(node.getPlug("attrLabel").get(), "hello world")

    def test_move_attribute_offset_clamps_and_is_a_noop_within_bounds(self):
        node = self.create_transform("hlibNodeApiMoveAttrClamp")
        node.addAttr("attrA", attributeType="double", defaultValue=0.0)
        node.addAttr("attrB", attributeType="double", defaultValue=0.0)

        result = node.moveAttrOrder("attrA", 0)
        self.assertIs(result, node)
        self.assertEqual(node.getExtraAttrNames(), ["attrA", "attrB"])

        node.moveAttrOrder("attrA", 100)
        self.assertEqual(node.getExtraAttrNames(), ["attrB", "attrA"])

        node.moveAttrOrder("attrA", -100)
        self.assertEqual(node.getExtraAttrNames(), ["attrA", "attrB"])

    def test_move_attribute_raises_for_unknown_name_and_unsupported_type(self):
        node = self.create_transform("hlibNodeApiMoveAttrErrors")
        node.addAttr("attrA", attributeType="double", defaultValue=0.0)
        cmds.addAttr(node.getFullName(), longName="attrCompound", attributeType="double3")
        cmds.addAttr(node.getFullName(), longName="attrCompoundX", attributeType="double", parent="attrCompound")
        cmds.addAttr(node.getFullName(), longName="attrCompoundY", attributeType="double", parent="attrCompound")
        cmds.addAttr(node.getFullName(), longName="attrCompoundZ", attributeType="double", parent="attrCompound")
        node.addAttr("attrB", attributeType="double", defaultValue=0.0)

        with self.assertRaises(ValueError):
            node.moveAttrOrder("doesNotExist", 1)

        with self.assertRaises(TypeError):
            node.moveAttrOrder("attrB", -1)
        # 型エラー時は何も削除・変更されていない(ダンプ段階での検証が先に走るため)。
        self.assertEqual(node.getExtraAttrNames(), ["attrA", "attrCompound", "attrB"])

    def test_unresolvable_node_name_raises_runtime_error(self):
        with self.assertRaises(RuntimeError) as context:
            Node("hlibNodeApiDoesNotExist")
        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    def test_unsupported_node_input_type_raises_type_error(self):
        with self.assertRaises(TypeError):
            Node(12345)

    def test_plug_paths_reject_indices_beyond_logical_index_range(self):
        # MPlug.elementByLogicalIndex() は範囲外の番号を別の番号へ変換する(4294967296 は 0)。
        # アトリビュートパス・要素番号では別の要素へ読み替えず、例外にする。
        average = Node.create(type="plusMinusAverage", name="hlibNodeApiIndexRange")
        self.created.append(average.getName())
        maximum = 2147483647
        self.assertEqual(average.getPlug("input1D[%d]" % maximum).mplug().logicalIndex(), maximum)
        for path in ("input1D[2147483648]", "input1D[4294967295]", "input1D[4294967296]",
                     "input1D[4294967297]", "input3D[4294967296].input3Dx"):
            with self.subTest(path=path):
                with self.assertRaises(AttributeError) as context:
                    average.getPlug(path)
                self.assertIn(str(maximum), str(context.exception))
                self.assertFalse(average.hasAttr(path))
        array_plug = average.getPlug("input1D")
        for index in (-1, maximum + 1, 4294967296):
            with self.subTest(index=index):
                with self.assertRaises(IndexError):
                    array_plug.getElement(index)
                with self.assertRaises(IndexError):
                    array_plug.getElement(index, create=True)
                with self.assertRaises(IndexError):
                    array_plug[index]
        # 要素は作られない(maya.cmds は 4294967296 を 2147483647 に切り詰めて作成する)。
        self.assertEqual(list(array_plug.mplug().getExistingArrayAttributeIndices()), [])
        created = array_plug.getElement(maximum, create=True)
        self.assertEqual(created.mplug().logicalIndex(), maximum)
        self.assertEqual(list(array_plug.mplug().getExistingArrayAttributeIndices()), [maximum])

    def test_plug_rejects_mplug_of_another_node(self):
        from hlib.plugs import Plug

        first = self.create_transform("hlibNodeApiPlugOwnerA")
        second = self.create_transform("hlibNodeApiPlugOwnerB")
        first.addAttr("hlibDynamic", attributeType="double")
        for name in ("translateX", "hlibDynamic", "worldMatrix"):
            with self.subTest(attribute=name):
                mplug = first.getPlug(name).mplug()
                self.assertEqual(Plug(first, mplug).mplug(), mplug)
                # 静的アトリビュートは同じ型の別ノードにも存在するが、所有ノードでない node は拒否する。
                with self.assertRaises(RuntimeError) as context:
                    Plug(second, mplug)
                self.assertIn("所有ノード", str(context.exception))


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

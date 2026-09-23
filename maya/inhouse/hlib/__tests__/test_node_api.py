"""hlib Node/DAG APIを検証するMaya内テスト。"""

import math
import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.namespaces import Namespace
from hlib.nodes import Node
from hlib.maths import EulerRotation, Matrix, Quaternion, Scale, Shear, Translate, Vector


class NodeApiTest(unittest.TestCase):
    """cymel相当の基本Node/DAG APIを検証する。"""

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
        self.created.append(node.name())
        return node

    def test_dag_paths_and_shapes(self):
        transform = self.create_transform("hlibNodeApiTransform")
        shape_name = cmds.createNode("mesh", parent=transform.name())
        self.created.append(shape_name)
        shape = transform.shape()

        self.assertEqual(transform.path(), transform.name())
        self.assertEqual(transform.path(full=True), "|" + transform.name())
        self.assertEqual(transform.partial_path(), transform.name())
        self.assertEqual(transform.full_path(), "|" + transform.name())
        self.assertTrue(transform.is_root())
        self.assertEqual(len(transform.shapes()), 1)
        self.assertEqual(shape.transform().name(), transform.name())
        self.assertTrue(shape.full_path().endswith("|" + shape_name))

    def test_rename_namespace_and_add_attr(self):
        transform = self.create_transform("hlibNodeApiRename")
        renamed = transform.rename("hlibNodeApiRenamed")
        self.assertEqual(renamed, "hlibNodeApiRenamed")
        self.assertEqual(transform.name(), "hlibNodeApiRenamed")

        namespaced = transform.set_namespace(self.namespace)
        self.assertIn("hlibNodeApiRenamed", namespaced)
        self.assertEqual(transform.node_name(remove_namespace=True), "hlibNodeApiRenamed")
        self.assertEqual(transform.namespace(), Namespace(self.namespace))

        missing_namespace = ":hlibNodeApiMissing:child"
        transform.set_namespace(missing_namespace)
        self.assertTrue(Namespace(missing_namespace).exists())
        self.assertEqual(transform.namespace(), Namespace(missing_namespace))

        plug = transform.add_attr(
            "hlibNodeApiValue",
            attribute_type="double",
            default_value=1.5,
        )
        self.assertEqual(plug.name, "hlibNodeApiValue")
        self.assertEqual(plug.get(), 1.5)

    def test_parent_and_connections(self):
        parent = self.create_transform("hlibNodeApiParent")
        child = self.create_transform("hlibNodeApiChild")
        source = self.create_transform("hlibNodeApiSource")
        target = self.create_transform("hlibNodeApiTarget")

        child.set_parent(parent)
        self.assertEqual(child.parent_node().name(), parent.name())
        child.set_parent()
        self.assertIsNone(child.parent_node())

        source.plug("translateX").connect(target.plug("translateX"))
        self.assertEqual([plug.full_name for plug in target.inputs()], [source.plug("translateX").full_name])
        self.assertEqual([plug.full_name for plug in source.outputs()], [target.plug("translateX").full_name])
        self.assertEqual(len(source.connections()), 1)

        def names(plugs):
            return [plug.full_name for plug in plugs]

        self.assertEqual(names(target.inputs(type="transform")), names(target.inputs()))
        self.assertEqual(target.inputs(type="mesh"), [])
        self.assertEqual(names(source.outputs(type="transform")), names(source.outputs()))
        self.assertEqual(source.connections(type="mesh"), [])

    def test_transform_matrix_round_trip_uses_dataclass_maths_values(self):
        transform = self.create_transform("hlibNodeApiMatrix")

        transform.set_translate((1.0, 2.0, 3.0))
        transform.set_rotate((0.0, math.radians(90.0), 0.0))
        transform.set_scale((2.0, 1.0, 1.0))

        translate = transform.get_translate()
        self.assertIsInstance(translate, Translate)
        self.assertEqual(translate, Translate(1.0, 2.0, 3.0))

        scale = transform.get_scale()
        self.assertIsInstance(scale, Scale)
        self.assertAlmostEqual(scale.x, 2.0, places=6)

        matrix = transform.get_matrix()
        self.assertIsInstance(matrix, Matrix)
        self.assertEqual(matrix.translate, translate)

        # Translate/Scale は dataclass 化により同一クラス同士のみ等価になる。
        self.assertNotEqual(translate, Scale(1.0, 2.0, 3.0))

    def test_transform_pivot_get_set_local_and_world(self):
        transform = self.create_transform("hlibNodeApiPivot")

        default_pivot = transform.pivot()
        self.assertIsInstance(default_pivot, Translate)
        self.assertEqual(default_pivot, Translate(0.0, 0.0, 0.0))

        result = transform.set_pivot((1.0, 2.0, 3.0))
        self.assertIs(result, transform)
        self.assertEqual(transform.pivot(), Translate(1.0, 2.0, 3.0))

        transform.set_translate((10.0, 0.0, 0.0))
        self.assertEqual(transform.pivot(ws=True), Translate(11.0, 2.0, 3.0))

    def test_transform_bounding_box_local_and_world(self):
        mesh_transform_name = cmds.polyCube(name="hlibNodeApiBoundingBoxMesh", constructionHistory=False)[0]
        self.created.append(mesh_transform_name)
        transform = Node(mesh_transform_name)

        box = transform.bounding_box()
        self.assertAlmostEqual(box.min.x, -0.5, places=5)
        self.assertAlmostEqual(box.max.x, 0.5, places=5)

        # bounding_box() は自身の translate は含むが、親の変換はまだ無いので world と一致する。
        transform.set_translate((10.0, 0.0, 0.0))
        self.assertAlmostEqual(transform.bounding_box().min.x, 9.5, places=5)
        self.assertAlmostEqual(transform.bounding_box(ws=True).min.x, 9.5, places=5)

        parent = self.create_transform("hlibNodeApiBoundingBoxParent")
        parent.set_translate((100.0, 0.0, 0.0))
        # relative=True で子のローカル translate を変えずに親子付けする
        # （既定はワールド位置維持のためローカル値が自動調整されてしまう）。
        cmds.parent(mesh_transform_name, parent.name(), relative=True)

        # ws=False は親の translate を含まない。ws=True は含む。
        self.assertAlmostEqual(transform.bounding_box().min.x, 9.5, places=5)
        world_box = transform.bounding_box(ws=True)
        self.assertAlmostEqual(world_box.min.x, 109.5, places=5)
        self.assertAlmostEqual(world_box.max.x, 110.5, places=5)

    def test_node_lock_and_referenced_and_type_checks(self):
        transform = self.create_transform("hlibNodeApiLockType")

        self.assertFalse(transform.is_locked)
        cmds.lockNode(transform.name(), lock=True)
        self.assertTrue(transform.is_locked)
        cmds.lockNode(transform.name(), lock=False)

        self.assertFalse(transform.is_referenced)

        self.assertTrue(transform.is_type("transform"))
        self.assertTrue(transform.is_type("dagNode"))
        self.assertFalse(transform.is_type("mesh"))
        with self.assertRaises(ValueError):
            transform.is_type("")

    def test_ancestor_and_root_queries(self):
        grandparent = self.create_transform("hlibNodeApiRootGP")
        parent = self.create_transform("hlibNodeApiRootP")
        child = self.create_transform("hlibNodeApiRootC")
        parent.set_parent(grandparent)
        child.set_parent(parent)

        self.assertTrue(grandparent.is_ancestor_of(child))
        self.assertTrue(grandparent.is_ancestor_of(parent))
        self.assertTrue(parent.is_ancestor_of(child))
        self.assertFalse(child.is_ancestor_of(grandparent))
        self.assertFalse(grandparent.is_ancestor_of(grandparent))

        self.assertEqual(child.root().full_name, grandparent.full_name)
        self.assertEqual(parent.root().full_name, grandparent.full_name)
        self.assertEqual(grandparent.root().full_name, grandparent.full_name)

    def test_shape_is_intermediate_object(self):
        mesh_transform_name = cmds.polyCube(name="hlibNodeApiIntermediate", constructionHistory=False)[0]
        self.created.append(mesh_transform_name)
        shape = Node(mesh_transform_name).shape()

        self.assertFalse(shape.is_intermediate_object)
        cmds.setAttr(shape.full_name + ".intermediateObject", True)
        self.assertTrue(shape.is_intermediate_object)

    def test_plug_is_keyable_and_parent(self):
        transform = self.create_transform("hlibNodeApiPlugMeta")
        translate = transform.attr("translate")
        translate_x = transform.attr("translateX")

        self.assertTrue(translate_x.is_keyable)
        self.assertIsNone(translate.parent)
        self.assertEqual(translate_x.parent.full_name, translate.full_name)

        cmds.setAttr(translate_x.full_name, keyable=False)
        self.assertFalse(translate_x.is_keyable)

    def test_plug_hidden_dynamic_limits_default_and_enum(self):
        transform = self.create_transform("hlibNodeApiPlugAttrMeta")
        cmds.addAttr(transform.name(), longName="hlibTestNum", attributeType="double",
                     min=0, max=10, defaultValue=5, hidden=True)
        cmds.addAttr(transform.name(), longName="hlibTestNoLimit", attributeType="double",
                     defaultValue=1.5)
        cmds.addAttr(transform.name(), longName="hlibTestEnum", attributeType="enum",
                     enumName="A:B:C", defaultValue=1)

        num_plug = transform.attr("hlibTestNum")
        self.assertTrue(num_plug.is_dynamic)
        self.assertTrue(num_plug.is_hidden)
        self.assertTrue(num_plug.has_min)
        self.assertTrue(num_plug.has_max)
        self.assertEqual(num_plug.min, 0.0)
        self.assertEqual(num_plug.max, 10.0)
        self.assertEqual(num_plug.default, 5.0)

        no_limit_plug = transform.attr("hlibTestNoLimit")
        self.assertFalse(no_limit_plug.is_hidden)
        self.assertFalse(no_limit_plug.has_min)
        self.assertFalse(no_limit_plug.has_max)
        self.assertIsNone(no_limit_plug.min)
        self.assertIsNone(no_limit_plug.max)
        self.assertEqual(no_limit_plug.default, 1.5)

        enum_plug = transform.attr("hlibTestEnum")
        self.assertEqual(enum_plug.default, 1)
        self.assertEqual(enum_plug.enum_name(), "B")

        # 静的（ノード組み込み）属性は動的属性ではない。
        self.assertFalse(transform.attr("translateX").is_dynamic)
        with self.assertRaises(TypeError):
            transform.attr("translateX").enum_name()

    def test_plug_readable_writable_storable_and_soft_limits(self):
        transform = self.create_transform("hlibNodeApiPlugFlags")
        cmds.addAttr(transform.name(), longName="hlibSoftAttr", attributeType="double",
                     softMinValue=0, softMaxValue=10, defaultValue=2)
        plug = transform.attr("hlibSoftAttr")

        self.assertTrue(plug.is_readable)
        self.assertTrue(plug.is_writable)
        self.assertTrue(plug.is_storable)
        self.assertTrue(plug.has_soft_min)
        self.assertTrue(plug.has_soft_max)
        self.assertEqual(plug.soft_min, 0.0)
        self.assertEqual(plug.soft_max, 10.0)

        translate_x = transform.attr("translateX")
        self.assertTrue(translate_x.is_readable)
        self.assertTrue(translate_x.is_writable)
        self.assertTrue(translate_x.is_storable)
        self.assertFalse(translate_x.has_soft_min)
        self.assertFalse(translate_x.has_soft_max)

    def test_node_type_id_and_classification(self):
        transform = self.create_transform("hlibNodeApiTypeId")
        self.assertIsInstance(transform.type_id, int)
        self.assertEqual(transform.classification(), cmds.getClassification("transform"))
        # transform は Maya 組み込みノード型なのでプラグイン名は空文字列。
        self.assertEqual(transform.plugin_name, "")

    def test_transform_leaves_siblings_and_child_transforms(self):
        root = self.create_transform("hlibNodeApiLeavesRoot")
        branch_a = self.create_transform("hlibNodeApiLeavesA")
        branch_b = self.create_transform("hlibNodeApiLeavesB")
        leaf_a1 = self.create_transform("hlibNodeApiLeavesA1")
        branch_a.set_parent(root)
        branch_b.set_parent(root)
        leaf_a1.set_parent(branch_a)

        self.assertEqual(
            sorted(node.name() for node in root.child_transforms()),
            ["hlibNodeApiLeavesA", "hlibNodeApiLeavesB"],
        )

        leaf_names = sorted(node.name() for node in root.leaves())
        self.assertEqual(leaf_names, ["hlibNodeApiLeavesA1", "hlibNodeApiLeavesB"])
        self.assertEqual(leaf_a1.leaves(), [leaf_a1])

        self.assertEqual([s.name() for s in branch_a.siblings()], ["hlibNodeApiLeavesB"])
        self.assertEqual(branch_b.siblings()[0].name(), "hlibNodeApiLeavesA")

        world_sibling = self.create_transform("hlibNodeApiLeavesWorldSibling")
        root_sibling_names = {s.name() for s in root.siblings()}
        self.assertIn("hlibNodeApiLeavesWorldSibling", root_sibling_names)
        self.assertNotIn("hlibNodeApiLeavesRoot", root_sibling_names)

    def test_plug_anim_curve_and_mute(self):
        transform = self.create_transform("hlibNodeApiAnimCurve")
        plug = transform.attr("translateX")

        self.assertIsNone(plug.anim_curve())

        cmds.setKeyframe(plug.full_name, time=1, value=0.0)
        cmds.setKeyframe(plug.full_name, time=24, value=10.0)

        curve = plug.anim_curve()
        self.assertIsNotNone(curve)
        self.assertTrue(curve.is_type("animCurve"))

        self.assertFalse(plug.is_muted)
        result = plug.mute()
        self.assertIs(result, plug)
        self.assertTrue(plug.is_muted)
        plug.unmute()
        self.assertFalse(plug.is_muted)

        # 非 animCurve 接続では anim_curve() は None を返す。
        other = self.create_transform("hlibNodeApiAnimCurveOther")
        other.attr("translateX").connect(transform.attr("translateY"))
        self.assertIsNone(transform.attr("translateY").anim_curve())

    def test_direct_parent_child_relationship_and_attribute_count(self):
        grandparent = self.create_transform("hlibNodeApiDirectGP")
        parent = self.create_transform("hlibNodeApiDirectP")
        child = self.create_transform("hlibNodeApiDirectC")
        parent.set_parent(grandparent)
        child.set_parent(parent)

        self.assertTrue(grandparent.is_parent_of(parent))
        self.assertFalse(grandparent.is_parent_of(child))
        self.assertTrue(grandparent.is_ancestor_of(child))

        self.assertTrue(parent.is_child_of(grandparent))
        self.assertFalse(child.is_child_of(grandparent))

        self.assertGreater(child.attribute_count(), 0)

    def test_plug_delete_attr(self):
        transform = self.create_transform("hlibNodeApiDeleteAttr")
        cmds.addAttr(transform.name(), longName="hlibDeleteMe", attributeType="double", defaultValue=1.0)
        plug = transform.attr("hlibDeleteMe")

        self.assertTrue(cmds.attributeQuery("hlibDeleteMe", node=transform.name(), exists=True))
        plug.delete_attr()
        self.assertFalse(cmds.attributeQuery("hlibDeleteMe", node=transform.name(), exists=True))

        with self.assertRaises(RuntimeError):
            transform.attr("translateX").delete_attr()

    def test_plug_delete_attr_force_unlocks_before_deleting(self):
        transform = self.create_transform("hlibNodeApiDeleteAttrForce")
        cmds.addAttr(transform.name(), longName="hlibLockedDelete", attributeType="double", defaultValue=1.0)
        plug = transform.attr("hlibLockedDelete")
        plug.set_locked(True)

        with self.assertRaises(RuntimeError):
            plug.delete_attr()
        self.assertTrue(cmds.attributeQuery("hlibLockedDelete", node=transform.name(), exists=True))

        plug.delete_attr(force=True)
        self.assertFalse(cmds.attributeQuery("hlibLockedDelete", node=transform.name(), exists=True))

    def test_node_plugs_enumerates_attributes_as_plug_objects(self):
        transform = self.create_transform("hlibNodeApiPlugs")

        plugs = transform.plugs()
        self.assertIn("translateX", {plug.attribute for plug in plugs})
        self.assertTrue(all(hasattr(plug, "get") for plug in plugs))
        # listAttr が報告する名前の一部（未確保の要素を持つ配列複合属性の子など）は
        # 実際には評価できず黙ってスキップされるため、件数は必ずしも一致しない。
        self.assertLessEqual(len(plugs), len(cmds.listAttr(transform.name()) or []))

        keyable_names = set(cmds.listAttr(transform.name(), keyable=True) or [])
        keyable_plugs = transform.plugs(keyable=True)
        self.assertEqual({plug.attribute for plug in keyable_plugs}, keyable_names)

    def test_node_aliases_returns_alias_plug_pairs(self):
        transform = self.create_transform("hlibNodeApiAliases")
        self.assertEqual(transform.aliases(), [])

        cmds.aliasAttr("hlibTx", transform.plug("translateX").full_name)
        aliases = transform.aliases()
        self.assertEqual(len(aliases), 1)
        alias_name, plug = aliases[0]
        self.assertEqual(alias_name, "hlibTx")
        self.assertEqual(plug.full_name, transform.plug("translateX").full_name)

    def test_plug_set_keyable_and_set_channel_box(self):
        transform = self.create_transform("hlibNodeApiKeyableCB")
        plug = transform.attr("translateX")

        result = plug.set_keyable(False)
        self.assertIs(result, plug)
        self.assertFalse(plug.is_keyable)

        plug.set_channel_box(True)
        self.assertFalse(plug.is_keyable)
        self.assertTrue(cmds.getAttr(plug.full_name, channelBox=True))

        plug.set_keyable(True)
        self.assertTrue(plug.is_keyable)

    def test_plug_nice_name_and_is_connected_to(self):
        source = self.create_transform("hlibNodeApiNiceNameSource")
        target = self.create_transform("hlibNodeApiNiceNameTarget")

        self.assertEqual(source.attr("translateX").nice_name(), "Translate X")

        source_plug = source.attr("translateX")
        target_plug = target.attr("translateX")
        self.assertFalse(source_plug.is_connected_to(target_plug))

        source_plug.connect(target_plug)
        self.assertTrue(source_plug.is_connected_to(target_plug))
        self.assertTrue(target_plug.is_connected_to(source_plug))
        self.assertFalse(source_plug.is_connected_to(source.attr("translateY")))

    def test_plug_enum_value_reverses_enum_name(self):
        transform = self.create_transform("hlibNodeApiEnumValue")
        cmds.addAttr(transform.name(), longName="hlibEnumValueAttr", attributeType="enum",
                     enumName="A:B:C", defaultValue=0)
        plug = transform.attr("hlibEnumValueAttr")

        self.assertEqual(plug.enum_value("B"), 1)
        self.assertEqual(plug.enum_value(plug.enum_name()), 0)
        with self.assertRaises(ValueError):
            plug.enum_value("NotAField")
        with self.assertRaises(TypeError):
            transform.attr("translateX").enum_value("A")

    def test_plug_get_dispatches_by_attribute_type_via_om2(self):
        # Plug.get() は bool/int/float/角度・距離・時間/enum/文字列を
        # MPlug 経由で直接読み取る。cmds.getAttr の結果と一致することを
        # 各属性型ごとに確認する（角度は度、距離・時間は現在のUI単位）。
        transform = self.create_transform("hlibNodeApiPlugGetTypes")
        name = transform.name()
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
                plug_value = transform.attr(attribute).get()
                cmds_value = cmds.getAttr(f"{name}.{attribute}")
                self.assertAlmostEqual(plug_value, cmds_value) if isinstance(cmds_value, float) \
                    else self.assertEqual(plug_value, cmds_value)

        self.assertIsInstance(transform.attr("hlibBool").get(), bool)
        self.assertIsInstance(transform.attr("hlibLong").get(), int)
        self.assertIsInstance(transform.attr("hlibString").get(), str)

    def test_plug_get_falls_back_to_cmds_for_unsupported_typed_data(self):
        # stringArray は MFnTypedAttribute だが kString ではないため、
        # om2 の直接読み取りは対象外となり cmds.getAttr にフォールバックする。
        transform = self.create_transform("hlibNodeApiPlugGetFallback")
        cmds.addAttr(transform.name(), longName="hlibStringArray", dataType="stringArray")
        cmds.setAttr(transform.name() + ".hlibStringArray", 2, "a", "b", type="stringArray")

        value = transform.attr("hlibStringArray").get()
        self.assertEqual(value, cmds.getAttr(transform.name() + ".hlibStringArray"))

    def test_array_plug_next_available_add_and_remove_element(self):
        source = self.create_transform("hlibNodeApiArrayNextAvailSource")
        target = self.create_transform("hlibNodeApiArrayNextAvailTarget")
        array_plug = target.attr("worldMatrix")

        self.assertEqual(array_plug.next_available(), 0)

        array_plug.element(0, create=True)
        self.assertEqual(array_plug.next_available(), 1)
        self.assertEqual(array_plug.next_available(start=5), 5)

        element = array_plug.add_element()
        self.assertEqual(element.attribute, "worldMatrix")
        self.assertTrue(element.full_name.endswith("[1]"))

        array_plug.remove_element(1)
        self.assertNotIn(1, array_plug.get())

        with self.assertRaises(IndexError):
            array_plug.remove_element(99)

    def test_transform_show_hide(self):
        transform = self.create_transform("hlibNodeApiShowHide")

        result = transform.hide()
        self.assertIs(result, transform)
        self.assertFalse(transform.plug("visibility").get())

        transform.show()
        self.assertTrue(transform.plug("visibility").get())

    def test_transform_make_identity_freezes_transform(self):
        transform = self.create_transform("hlibNodeApiFreeze")
        transform.set_translate((1.0, 2.0, 3.0))

        result = transform.make_identity(apply=True, translate=True)
        self.assertIs(result, transform)
        self.assertEqual(transform.get_translate(), Translate(0.0, 0.0, 0.0))

    def test_transform_release_srt_unlocks_and_disconnects(self):
        driver = self.create_transform("hlibNodeApiReleaseDriver")
        transform = self.create_transform("hlibNodeApiRelease")
        driver.plug("translateX").connect(transform.plug("translateX"))
        transform.plug("translate").set_locked(True)
        transform.plug("rotateY").set_locked(True)

        result = transform.release_srt()
        self.assertIs(result, transform)
        self.assertFalse(transform.plug("translate").is_locked)
        self.assertFalse(transform.plug("translateX").is_locked)
        self.assertFalse(transform.plug("rotateY").is_locked)
        self.assertIsNone(transform.plug("translateX").source())

    def test_transform_closest_axis_to_vector(self):
        transform = self.create_transform("hlibNodeApiClosestAxis")

        self.assertEqual(transform.closest_axis_to_vector(Vector(1.0, 0.0, 0.0)), "x")
        self.assertEqual(transform.closest_axis_to_vector(Vector(0.0, -1.0, 0.0)), "-y")
        self.assertEqual(transform.closest_axis_to_vector(Vector(0.0, 1.0, 0.0), include_negative=False), "y")

        transform.set_rotate((0.0, math.radians(90.0), 0.0))
        self.assertEqual(transform.closest_axis_to_vector(Vector(0.0, 0.0, -1.0)), "x")

    def test_transform_create_offset_groups_preserves_world_position(self):
        parent = self.create_transform("hlibNodeApiOffsetParent")
        parent.set_translate((5.0, 0.0, 0.0))
        transform = self.create_transform("hlibNodeApiOffsetChild")
        transform.set_parent(parent)
        transform.set_translate((1.0, 2.0, 3.0))
        world_translate = transform.get_translate(ws=True)

        zero, offset = transform.create_offset_groups("hlibNodeApiZero", "hlibNodeApiOffset")
        self.created.extend([zero.name(), offset.name()])

        self.assertEqual(zero.parent_node().name(), parent.name())
        self.assertEqual(offset.parent_node().name(), zero.name())
        self.assertEqual(transform.parent_node().name(), offset.name())
        self.assertEqual(zero.get_translate(ws=True), world_translate)
        self.assertEqual(offset.get_translate(ws=True), world_translate)
        self.assertEqual(transform.get_translate(ws=True), world_translate)
        self.assertEqual(transform.get_translate(), Translate(0.0, 0.0, 0.0))

    def test_node_is_valid_is_alive_and_has_attr(self):
        transform = self.create_transform("hlibNodeApiValidity")
        self.assertTrue(transform.is_valid())
        self.assertTrue(transform.is_alive())
        self.assertTrue(transform.has_attr("translateX"))
        self.assertFalse(transform.has_attr("hlibNoSuchAttr"))

        cmds.delete(transform.name())
        self.assertFalse(transform.is_valid())
        self.assertIsInstance(transform.is_alive(), bool)

    def test_transform_shear_quaternion_euler_and_decompose(self):
        transform = self.create_transform("hlibNodeApiShearQuat")
        result = transform.set_shear((0.1, 0.2, 0.3))
        self.assertIs(result, transform)
        shear = transform.get_shear()
        self.assertIsInstance(shear, Shear)
        self.assertAlmostEqual(shear.x, 0.1, places=6)
        self.assertAlmostEqual(shear.y, 0.2, places=6)
        self.assertAlmostEqual(shear.z, 0.3, places=6)

        transform.set_rotate((0.0, math.radians(90.0), 0.0))
        quaternion = transform.get_quaternion()
        self.assertIsInstance(quaternion, Quaternion)
        euler = transform.get_euler()
        self.assertIsInstance(euler, EulerRotation)
        self.assertAlmostEqual(euler.y, math.radians(90.0), places=6)

        matrix = transform.decompose()
        self.assertIsInstance(matrix, Matrix)
        self.assertEqual(matrix, transform.get_matrix(ws=True))

    def test_transform_compose_round_trips_matrix_and_rejects_non_matrix(self):
        source = self.create_transform("hlibNodeApiComposeSource")
        source.set_translate((1.0, 2.0, 3.0))
        source.set_rotate((0.0, math.radians(45.0), 0.0))
        matrix = source.get_matrix(ws=True)

        target = self.create_transform("hlibNodeApiComposeTarget")
        result = target.compose(matrix, ws=True)
        self.assertIs(result, target)
        self.assertTrue(target.get_matrix(ws=True).is_equivalent(matrix, tolerance=1e-6))

        with self.assertRaises(TypeError):
            target.compose((1, 2, 3))

    def test_transform_set_matrix_direct_accepts_raw_values_and_guards_invalid_node(self):
        transform = self.create_transform("hlibNodeApiSetMatrixDirect")
        matrix = Matrix(translate=(1.0, 2.0, 3.0))
        result = transform.set_matrix(matrix)
        self.assertIs(result, transform)
        self.assertEqual(transform.get_translate(), Translate(1.0, 2.0, 3.0))

        # Matrix以外の16要素入力も内部でMatrixへ変換して受け付ける。
        transform.set_matrix((
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            5.0, 6.0, 7.0, 1.0,
        ))
        self.assertEqual(transform.get_translate(), Translate(5.0, 6.0, 7.0))

        cmds.delete(transform.name())
        with self.assertRaises(RuntimeError):
            transform.set_matrix(matrix)

    def test_plug_structural_introspection_properties(self):
        transform = self.create_transform("hlibNodeApiPlugStructure")
        translate_plug = transform.attr("translate")
        translate_x_plug = transform.attr("translateX")
        world_matrix_plug = transform.attr("worldMatrix")

        self.assertTrue(translate_plug.is_compound)
        self.assertFalse(translate_plug.is_array)
        self.assertFalse(translate_plug.is_element)
        self.assertFalse(translate_plug.is_child)

        self.assertTrue(translate_x_plug.is_child)
        self.assertFalse(translate_x_plug.is_compound)

        self.assertTrue(world_matrix_plug.is_array)

        import maya.api.OpenMaya as om2
        self.assertIsInstance(translate_plug.mplug(), om2.MPlug)

        element = world_matrix_plug.element(0, create=True)
        self.assertTrue(element.is_element)

    def test_plug_connection_introspection_and_disconnect(self):
        source = self.create_transform("hlibNodeApiPlugConnSource")
        target = self.create_transform("hlibNodeApiPlugConnTarget")
        source_plug = source.attr("translateX")
        target_plug = target.attr("translateX")

        self.assertFalse(source_plug.is_connected)
        self.assertFalse(source_plug.is_source)
        self.assertFalse(target_plug.is_destination)

        source_plug.connect(target_plug)
        self.assertTrue(source_plug.is_connected)
        self.assertTrue(source_plug.is_source)
        self.assertFalse(source_plug.is_destination)
        self.assertTrue(target_plug.is_connected)
        self.assertTrue(target_plug.is_destination)
        self.assertFalse(target_plug.is_source)

        destinations = source_plug.destinations()
        self.assertEqual([plug.full_name for plug in destinations], [target_plug.full_name])

        result = source_plug.disconnect()
        self.assertIs(result, source_plug)
        self.assertFalse(source_plug.is_connected)
        self.assertFalse(target_plug.is_connected)
        self.assertEqual(source_plug.destinations(), [])

    def test_array_plug_elements_returns_all_existing(self):
        target = self.create_transform("hlibNodeApiArrayElements")
        array_plug = target.attr("worldMatrix")
        array_plug.element(0, create=True)

        elements = array_plug.elements()
        self.assertEqual(len(elements), 1)
        self.assertTrue(elements[0].is_element)

    def test_bool_plug_toggle(self):
        transform = self.create_transform("hlibNodeApiBoolToggle")
        plug = transform.attr("visibility")
        plug.set(True)

        result = plug.toggle()
        self.assertIs(result, plug)
        self.assertFalse(plug.get())

        plug.toggle()
        self.assertTrue(plug.get())

    def test_unresolvable_node_name_raises_runtime_error(self):
        with self.assertRaises(RuntimeError) as context:
            Node("hlibNodeApiDoesNotExist")
        self.assertIsInstance(context.exception.__cause__, RuntimeError)

    def test_unsupported_node_input_type_raises_type_error(self):
        with self.assertRaises(TypeError):
            Node(12345)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

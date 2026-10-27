"""Transform の空間・回転・シアー・親子付けの共通化(mlib 2.0、担当 2B)の約束を固定する。

対象: ``getRotate(order=)`` の二段規則、``getShear/setShear``、``resetAttrs`` の戻り値、
``setParent(r=)``、``mfn()`` と派生クラスの override、廃止した入口が無いこと、
Transforms の一括転送(``_bulk_entries``・転送 def・``__signature__``)。
期待値は cmds と om2 で独立に求める。
"""

import inspect
import math
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.maths import EulerRotate, Matrix, Shear
from mlib.maths.eulerRotate import ORDER_NAMES
from mlib.nodes import Camera, Mesh, Node, NurbsCurve, Transform, Transforms
from mlib.plugs import Plug

TOLERANCE = 1e-9

#: Transform から取り除いた入口。別名も残さない(DESIGN §2.3・§3)。
REMOVED_NAMES = (
    "transformFn", "reset", "resetPivot", "freeze", "getEuler", "getJointOrientQuaternion",
    "getOffsetParentMatrix", "setOffsetParentMatrix", "getShearing", "setShearing",
)


class _NamespaceCase(unittest.TestCase):
    """専用の一時名前空間でノードを作り、Undo の設定を元に戻す。"""

    def setUp(self):
        self.ns = "mlibSpecXformSpace_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.ns)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)

    def tearDown(self):
        if cmds.namespace(exists=self.ns):
            cmds.namespace(removeNamespace=self.ns, deleteNamespaceContent=True)
        cmds.undoInfo(state=self.undo_state)

    def name(self, text):
        return self.ns + ":" + text

    def make(self, kind="transform", text="node#", parent=None):
        flags = {"name": self.name(text), "skipSelect": True}
        if parent is not None:
            flags["parent"] = parent
        return cmds.createNode(kind, **flags)

    def assertSequenceAlmostEqual(self, actual, expected, places=9):
        actual = list(actual)
        expected = list(expected)
        self.assertEqual(len(actual), len(expected))
        for a, e in zip(actual, expected):
            self.assertAlmostEqual(a, e, places=places)

    def flushUndo(self):
        """Undo キューを空にして、以後の操作が記録する項目数を数えられるようにする。"""
        cmds.flushUndo()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def assertUndoesInOneStep(self, check_before, check_after):
        """直前の操作が Undo 1 回で戻り、キューに他の項目を残さないことを確かめる。"""
        check_after()
        self.assertFalse(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.undo()
        check_before()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))


def _world_quaternion(name):
    """cmds の worldMatrix から om2 で回転クォータニオンを独立に求める。"""
    matrix = om2.MMatrix(cmds.getAttr(name + ".worldMatrix[0]"))
    return om2.MTransformationMatrix(matrix).rotation(asQuaternion=True)


class RemovedApiTest(unittest.TestCase):
    """廃止した名前が単数・複数形・一括宣言のどこにも残っていないこと。"""

    def test_removed_names_are_absent(self):
        for name in REMOVED_NAMES:
            with self.subTest(name=name):
                self.assertFalse(hasattr(Transform, name))
                self.assertFalse(hasattr(Transforms, name))
                self.assertNotIn(name, Transforms._bulk_entries)
                self.assertNotIn(name, Transforms._bulk_methods)

    def test_renamed_names_are_present(self):
        for name in ("mfn", "resetAttrs", "getShear", "setShear", "getRotate", "setParent"):
            with self.subTest(name=name):
                self.assertTrue(callable(getattr(Transform, name)))
                self.assertTrue(callable(getattr(Transforms, name)))
                self.assertIn(name, Transforms._bulk_entries)

    def test_bulk_entries_match_singular_and_forwarders(self):
        """チェックリスト(DESIGN §6.8): 宣言・単数 def・転送 def・__signature__ が揃う。"""
        for name, (function, policy) in Transforms._bulk_entries.items():
            with self.subTest(name=name):
                self.assertIs(getattr(Transform, name), function)
                self.assertIn(policy, ("list", "self"))
                forwarder = Transforms.__dict__.get(name)
                self.assertIsNotNone(forwarder, "Transforms lacks a forwarder def for " + name)
                self.assertEqual(forwarder.__signature__, inspect.signature(function))
        self.assertEqual(Transforms._bulk_returns["resetAttrs"], "list")
        self.assertEqual(Transforms._bulk_returns["mfn"], "list")
        self.assertEqual(Transforms._bulk_returns["setShear"], "self")

    def test_setparent_signature_has_relative_alias(self):
        parameters = inspect.signature(Transform.setParent).parameters
        self.assertIn("r", parameters)
        self.assertEqual(parameters["r"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertEqual(parameters["fast"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_getrotate_signature_has_order(self):
        parameters = inspect.signature(Transform.getRotate).parameters
        self.assertIn("order", parameters)
        self.assertEqual(parameters["order"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameters["order"].default)


class MfnTest(_NamespaceCase):
    """mfn() はそのノードで最も具体的な om2 function set を毎回新規に返す。"""

    def test_transform_mfn(self):
        name = self.make()
        node = Node(name)
        fn = node.mfn()
        self.assertIsInstance(fn, om2.MFnTransform)
        self.assertEqual(fn.fullPathName(), cmds.ls(name, long=True)[0])
        self.assertIsNot(fn, node.mfn())

    def test_shape_overrides(self):
        mesh = cmds.listRelatives(cmds.polyCube(name=self.name("cube#"), constructionHistory=False)[0],
                                  shapes=True, fullPath=True)[0]
        curve = cmds.listRelatives(cmds.curve(name=self.name("curve#"), degree=1, point=[(0, 0, 0), (1, 0, 0)]),
                                   shapes=True, fullPath=True)[0]
        camera = cmds.listRelatives(cmds.camera(name=self.name("camera#"))[0], shapes=True, fullPath=True)[0]
        cases = (
            (mesh, Mesh, om2.MFnMesh),
            (curve, NurbsCurve, om2.MFnNurbsCurve),
            (camera, Camera, om2.MFnCamera),
        )
        for name, wrapper, fn_class in cases:
            with self.subTest(wrapper=wrapper.__name__):
                node = Node(name)
                self.assertIsInstance(node, wrapper)
                fn = node.mfn()
                self.assertIs(type(fn), fn_class)
                self.assertEqual(fn.fullPathName(), name)

    def test_transforms_mfn_returns_list(self):
        names = [self.make(), self.make()]
        fns = Transforms(names).mfn()
        self.assertEqual([type(fn) for fn in fns], [om2.MFnTransform, om2.MFnTransform])
        self.assertEqual([fn.fullPathName() for fn in fns], cmds.ls(names, long=True))


class GetRotateOrderTest(_NamespaceCase):
    """getRotate(order=) の二段規則。"""

    def test_default_matches_channels_and_cmds(self):
        for rotate_order in range(6):
            with self.subTest(rotateOrder=rotate_order):
                node = self._rotated(rotate_order)
                rotate = node.getRotate()
                expected = [math.radians(v) for v in cmds.getAttr(str(node) + ".rotate")[0]]
                self.assertIsInstance(rotate, EulerRotate)
                self.assertEqual(rotate.order, rotate_order)
                self.assertSequenceAlmostEqual(rotate, expected)

    def test_order_equal_to_node_order_matches_default(self):
        for rotate_order in range(6):
            with self.subTest(rotateOrder=rotate_order):
                node = self._rotated(rotate_order)
                for ws in (False, True):
                    default = node.getRotate(ws=ws)
                    by_int = node.getRotate(ws=ws, order=rotate_order)
                    by_name = node.getRotate(ws=ws, order=ORDER_NAMES[rotate_order])
                    self.assertSequenceAlmostEqual(by_int, default)
                    self.assertSequenceAlmostEqual(by_name, default)
                    self.assertEqual(by_int.order, rotate_order)
                    self.assertEqual(by_name.order, rotate_order)

    def test_other_order_is_plain_decomposition(self):
        node = self._rotated(3)
        for ws in (False, True):
            if ws:
                quaternion = _world_quaternion(str(node))
            else:
                quaternion = om2.MTransformationMatrix(
                    om2.MMatrix(cmds.getAttr(str(node) + ".matrix"))).rotation(asQuaternion=True)
            for order in (0, 1, 2, 4, 5):
                with self.subTest(ws=ws, order=order):
                    rotate = node.getRotate(ws=ws, order=order)
                    expected = quaternion.asEulerRotation().reorder(order)
                    self.assertEqual(rotate.order, order)
                    self.assertSequenceAlmostEqual(rotate, (expected.x, expected.y, expected.z))

    def test_order_zero_equals_former_geteuler(self):
        """order=0(xyz)は旧 getEuler(quaternion.asEulerRotation())と同じ値。"""
        node = self._rotated(5)
        for ws in (False, True):
            with self.subTest(ws=ws):
                attribute = ".worldMatrix[0]" if ws else ".matrix"
                matrix = om2.MMatrix(cmds.getAttr(str(node) + attribute))
                expected = om2.MTransformationMatrix(matrix).rotation(asQuaternion=True).asEulerRotation()
                rotate = node.getRotate(ws=ws, order=0)
                self.assertEqual(rotate.order, 0)
                self.assertSequenceAlmostEqual(rotate, (expected.x, expected.y, expected.z))
                self.assertSequenceAlmostEqual(node.getRotate(ws=ws, order="XYZ"), rotate)

    def test_roundtrip_with_setrotate_keeps_channels(self):
        node = self._rotated(4)
        before = cmds.getAttr(str(node) + ".rotate")[0]
        node.setRotate(node.getRotate())
        self.assertSequenceAlmostEqual(cmds.getAttr(str(node) + ".rotate")[0], before, places=6)

    def test_invalid_order_and_flags(self):
        node = self._rotated(0)
        for order in (6, -1, "abc", True, 1.5):
            with self.subTest(order=order):
                with self.assertRaises(ValueError):
                    node.getRotate(order=order)
        with self.assertRaises(TypeError):
            node.getRotate(True, ws=True)
        with self.assertRaises(ValueError):
            node.getRotate("yes")

    def test_zero_scale_axis_raises_for_both_rules(self):
        node = self._rotated(0)
        cmds.setAttr(str(node) + ".scaleY", 0.0)
        for order in (None, 0, 3):
            with self.subTest(order=order):
                with self.assertRaises(ValueError):
                    node.getRotate(order=order)

    def _rotated(self, rotate_order, rotate=(35.0, -70.0, 120.0), parent_rotate=(10.0, 20.0, 30.0)):
        parent = self.make(text="parent#")
        cmds.setAttr(parent + ".rotate", *parent_rotate)
        name = self.make(text="child#", parent=parent)
        cmds.setAttr(name + ".rotateOrder", rotate_order)
        cmds.setAttr(name + ".rotate", *rotate)
        return Node(name)


class ShearTest(_NamespaceCase):
    """getShear/setShear は Maya のアトリビュート名に揃えた入口。"""

    def test_getshear_local_matches_cmds(self):
        name = self.make()
        cmds.setAttr(name + ".shear", 0.25, -0.5, 0.75)
        shear = Node(name).getShear()
        self.assertIsInstance(shear, Shear)
        self.assertSequenceAlmostEqual(shear, cmds.getAttr(name + ".shear")[0])
        self.assertSequenceAlmostEqual(Node(name).getShear(ws=False), shear)

    def test_getshear_world_matches_om2(self):
        parent = self.make(text="parent#")
        cmds.setAttr(parent + ".shear", 0.1, 0.2, 0.3)
        cmds.setAttr(parent + ".rotate", 10.0, 20.0, 30.0)
        name = self.make(text="child#", parent=parent)
        cmds.setAttr(name + ".shear", 0.25, -0.5, 0.75)
        matrix = om2.MMatrix(cmds.getAttr(name + ".worldMatrix[0]"))
        expected = om2.MTransformationMatrix(matrix).shear(om2.MSpace.kTransform)
        for flags in ({"worldSpace": True}, {"ws": True}):
            with self.subTest(flags=flags):
                self.assertSequenceAlmostEqual(Node(name).getShear(**flags), expected)
        with self.assertRaises(TypeError):
            Node(name).getShear(True, ws=True)

    def test_setshear_undo_fast_get(self):
        name = self.make()
        node = Node(name)
        values = (0.25, -0.5, 0.75)

        def unchanged():
            self.assertSequenceAlmostEqual(cmds.getAttr(name + ".shear")[0], (0.0, 0.0, 0.0))

        def changed():
            self.assertSequenceAlmostEqual(cmds.getAttr(name + ".shear")[0], values)

        self.flushUndo()
        self.assertIs(node.setShear(values), node)
        self.assertUndoesInOneStep(unchanged, changed)

        self.flushUndo()
        self.assertIs(node.setShear(values, fast=True), node)
        changed()
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.setAttr(name + ".shear", 0.0, 0.0, 0.0)

        preview = node.setShear(values, get=True)
        self.assertSequenceAlmostEqual(preview, values)
        unchanged()

    def test_setshear_world_writes_only_shear(self):
        parent = self.make(text="parent#")
        cmds.setAttr(parent + ".rotate", 10.0, 20.0, 30.0)
        cmds.setAttr(parent + ".scale", 2.0, 1.0, 1.0)
        name = self.make(text="child#", parent=parent)
        cmds.setAttr(name + ".rotate", -15.0, 25.0, 5.0)
        before = (cmds.getAttr(name + ".rotate")[0], cmds.getAttr(name + ".scale")[0])
        node = Node(name)
        node.setShear((0.2, 0.1, -0.3), ws=True)
        self.assertSequenceAlmostEqual(node.getShear(ws=True), (0.2, 0.1, -0.3), places=6)
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".rotate")[0], before[0])
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".scale")[0], before[1])

    def test_setshear_invalid_inputs(self):
        node = Node(self.make())
        with self.assertRaises(TypeError):
            node.setShear((0.1, 0.2, 0.3), fast="yes")
        with self.assertRaises(TypeError):
            node.setShear((0.1, 0.2, 0.3), True, ws=True)
        cmds.setAttr(str(node) + ".shearXY", lock=True)
        with self.assertRaises(RuntimeError):
            node.setShear((0.1, 0.2, 0.3))
        node.setShear((0.1, 0.2, 0.3), safe=True)
        self.assertSequenceAlmostEqual(cmds.getAttr(str(node) + ".shear")[0], (0.0, 0.2, 0.3))

    def test_transforms_setshear_returns_self(self):
        names = [self.make(), self.make()]
        nodes = Transforms(names)
        self.assertIs(nodes.setShear((0.1, 0.2, 0.3)), nodes)
        for name in names:
            self.assertSequenceAlmostEqual(cmds.getAttr(name + ".shear")[0], (0.1, 0.2, 0.3))
        shears = nodes.getShear()
        self.assertEqual(len(shears), 2)
        self.assertTrue(all(isinstance(shear, Shear) for shear in shears))


class ResetAttrsTest(_NamespaceCase):
    """Transform.resetAttrs は既定で TRS とシアーを戻し、戻した Plug の list を返す。"""

    def test_default_resets_trs_and_shear_only(self):
        name = self._dirty()
        node = Node(name)
        self.flushUndo()
        plugs = node.resetAttrs()
        self.assertIsInstance(plugs, list)
        self.assertTrue(all(isinstance(plug, Plug) for plug in plugs))
        self.assertEqual([plug.getLongName() for plug in plugs], ["translate", "rotate", "scale", "shear"])
        self.assertValues(name, [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)])
        self.assertFalse(cmds.getAttr(name + ".visibility"))
        self.assertFalse(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.undo()
        self.assertValues(name, [(1.0, 2.0, 3.0), (10.0, 20.0, 30.0), (2.0, 3.0, 4.0), (0.1, 0.2, 0.3)])
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_explicit_attributes_and_alias(self):
        name = self._dirty()
        node = Node(name)
        for flags in ({"attributes": ("tx", "scale")}, {"attrs": ["tx", "scale"]}):
            with self.subTest(flags=flags):
                cmds.setAttr(name + ".translateX", 1.0)
                cmds.setAttr(name + ".scale", 2.0, 3.0, 4.0)
                plugs = node.resetAttrs(**flags)
                self.assertEqual([plug.getLongName() for plug in plugs], ["translateX", "scale"])
                self.assertEqual(cmds.getAttr(name + ".translate")[0], (0.0, 2.0, 3.0))
                self.assertEqual(cmds.getAttr(name + ".scale")[0], (1.0, 1.0, 1.0))
                self.assertSequenceAlmostEqual(cmds.getAttr(name + ".rotate")[0], (10.0, 20.0, 30.0))
        self.assertEqual([plug.getLongName() for plug in node.resetAttrs("rotate")], ["rotate"])
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".rotate")[0], (0.0, 0.0, 0.0))

    def test_fast_has_no_undo(self):
        name = self._dirty()
        self.flushUndo()
        plugs = Node(name).resetAttrs(fast=True)
        self.assertEqual(len(plugs), 4)
        self.assertValues(name, [(0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (1.0, 1.0, 1.0), (0.0, 0.0, 0.0)])
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_invalid_inputs(self):
        node = Node(self._dirty())
        with self.assertRaises(TypeError):
            node.resetAttrs(fast=1)
        with self.assertRaises(TypeError):
            node.resetAttrs("tx", attrs="ty")
        with self.assertRaises(TypeError):
            node.resetAttrs([1, 2])
        with self.assertRaises(AttributeError):
            node.resetAttrs("noSuchAttribute")
        cmds.setAttr(str(node) + ".translateX", lock=True)
        with self.assertRaises(RuntimeError):
            node.resetAttrs("translate")

    def test_transforms_returns_list_of_lists(self):
        names = [self._dirty(), self._dirty()]
        result = Transforms(names).resetAttrs()
        self.assertIsInstance(result, list)
        self.assertEqual(len(result), 2)
        for name, plugs in zip(names, result):
            self.assertEqual([plug.getLongName() for plug in plugs], ["translate", "rotate", "scale", "shear"])
            self.assertEqual(cmds.getAttr(name + ".translate")[0], (0.0, 0.0, 0.0))

    def _dirty(self):
        name = self.make()
        cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(name + ".rotate", 10.0, 20.0, 30.0)
        cmds.setAttr(name + ".scale", 2.0, 3.0, 4.0)
        cmds.setAttr(name + ".shear", 0.1, 0.2, 0.3)
        cmds.setAttr(name + ".visibility", False)
        return name

    def _values(self, name):
        return [cmds.getAttr(name + "." + attr)[0] for attr in ("translate", "rotate", "scale", "shear")]

    def assertValues(self, name, expected):
        for actual, wanted in zip(self._values(name), expected):
            self.assertSequenceAlmostEqual(actual, wanted)


class SetParentTest(_NamespaceCase):
    """setParent の relative/r と Undo。"""

    def test_relative_keeps_local_values(self):
        for flags in ({"relative": True}, {"r": True}):
            with self.subTest(flags=flags):
                parent, child = self._pair()
                node = Node(child)
                self.assertIs(node.setParent(parent, **flags), node)
                self.assertEqual(cmds.listRelatives(str(node), parent=True, fullPath=True)[0],
                                 cmds.ls(parent, long=True)[0])
                self.assertSequenceAlmostEqual(cmds.getAttr(str(node) + ".translate")[0], (1.0, 2.0, 3.0))

    def test_default_keeps_world_matrix(self):
        parent, child = self._pair()
        world = cmds.getAttr(child + ".worldMatrix[0]")
        node = Node(child)
        self.flushUndo()
        node.setParent(parent)
        self.assertSequenceAlmostEqual(cmds.getAttr(str(node) + ".worldMatrix[0]"), world, places=6)
        self.assertNotEqual(tuple(round(v, 6) for v in cmds.getAttr(str(node) + ".translate")[0]), (1.0, 2.0, 3.0))
        self.assertFalse(cmds.undoInfo(query=True, undoQueueEmpty=True))
        cmds.undo()
        self.assertIsNone(cmds.listRelatives(str(node), parent=True))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_world_and_noop(self):
        parent, child = self._pair()
        node = Node(child)
        node.setParent(parent, r=True)
        node.setParent(None, r=True)
        self.assertIsNone(cmds.listRelatives(str(node), parent=True))
        self.assertSequenceAlmostEqual(cmds.getAttr(str(node) + ".translate")[0], (1.0, 2.0, 3.0))
        self.flushUndo()
        node.setParent(None)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_fast_relative_matches_cmds(self):
        parent, child = self._pair()
        reference_child = self.make(text="reference#")
        cmds.setAttr(reference_child + ".translate", 1.0, 2.0, 3.0)
        cmds.parent(reference_child, parent, relative=True)
        node = Node(child)
        self.flushUndo()
        node.setParent(parent, r=True, fast=True)
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))
        self.assertSequenceAlmostEqual(cmds.getAttr(str(node) + ".matrix"), cmds.getAttr(reference_child + ".matrix"))

    def test_invalid_inputs(self):
        parent, child = self._pair()
        node = Node(child)
        with self.assertRaises(TypeError):
            node.setParent(parent, True, r=True)
        with self.assertRaises(TypeError):
            node.setParent(parent, fast="yes")
        node.setParent(parent, r=True)
        with self.assertRaises(RuntimeError):
            Node(parent).setParent(node)

    def test_transforms_setparent_returns_self(self):
        parent = self.make(text="parent#")
        names = [self.make(), self.make()]
        nodes = Transforms(names)
        self.assertIs(nodes.setParent(parent, r=True), nodes)
        for name in nodes.getNames():
            self.assertEqual(cmds.listRelatives(name, parent=True, fullPath=True)[0], cmds.ls(parent, long=True)[0])

    def _pair(self):
        parent = self.make(text="parent#")
        cmds.setAttr(parent + ".translate", 5.0, 0.0, 0.0)
        cmds.setAttr(parent + ".rotate", 0.0, 90.0, 0.0)
        child = self.make(text="child#")
        cmds.setAttr(child + ".translate", 1.0, 2.0, 3.0)
        return parent, child


class ConstraintSupportTest(_NamespaceCase):
    """addConstraint の対応型は Constraint 派生の登録型から求め、抽象型 constraint は除く。"""

    def test_supported_and_unsupported_types(self):
        source = self.make(text="source#")
        target = Node(self.make(text="target#"))
        for type_name in ("constraint", "bogus", "transform"):
            with self.subTest(type=type_name):
                with self.assertRaises(ValueError):
                    target.addConstraint(source, type_name)
        created = target.addConstraint(source, "parent")
        self.assertEqual(cmds.nodeType(str(created)), "parentConstraint")


class ReplacementTest(_NamespaceCase):
    """廃止した入口の代替が同じ結果を返す。"""

    def test_offset_parent_matrix_via_plug(self):
        node = Node(self.make())
        value = Matrix(om2.MTransformationMatrix().setTranslation(om2.MVector(1.0, 2.0, 3.0), om2.MSpace.kTransform).asMatrix())
        node.getPlug("offsetParentMatrix").set(value)
        self.assertTrue(om2.MMatrix(cmds.getAttr(str(node) + ".offsetParentMatrix")).isEquivalent(value))
        self.assertTrue(node.getPlug("offsetParentMatrix").get().isEquivalent(value))

    def test_reset_pivot_via_setpivot(self):
        name = self.make()
        cmds.setAttr(name + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(name + ".rotatePivot", 0.5, 0.5, 0.5)
        cmds.setAttr(name + ".scalePivot", 0.5, 0.5, 0.5)
        world = cmds.getAttr(name + ".worldMatrix[0]")
        node = Node(name)
        node.setPivot((0.0, 0.0, 0.0), worldSpace=True, kind="both")
        self.assertSequenceAlmostEqual(cmds.xform(name, query=True, worldSpace=True, rotatePivot=True), (0.0, 0.0, 0.0))
        self.assertSequenceAlmostEqual(cmds.xform(name, query=True, worldSpace=True, scalePivot=True), (0.0, 0.0, 0.0))
        self.assertSequenceAlmostEqual(cmds.getAttr(name + ".worldMatrix[0]"), world)

    def test_joint_orient_quaternion_via_getquaternion(self):
        joint = cmds.createNode("joint", name=self.name("joint#"), skipSelect=True)
        cmds.setAttr(joint + ".jointOrient", 10.0, 20.0, 30.0)
        cmds.setAttr(joint + ".rotate", 40.0, 50.0, 60.0)
        quaternion = Node(joint).getQuaternion(r=False)
        expected = om2.MEulerRotation(*(math.radians(v) for v in (10.0, 20.0, 30.0))).asQuaternion()
        self.assertSequenceAlmostEqual(quaternion, (expected.x, expected.y, expected.z, expected.w))


if __name__ == "__main__":
    unittest.main(verbosity=2)

"""get省略入口の網羅性・遅延委譲・既存参照との優先順位を検証する。"""

import ast
import importlib
import inspect
import math
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import hlib
import maya.api.OpenMaya as om2
import maya.cmds as cmds


def _short_name(getter_name):
    """正式getterから省略入口のlowerCamelCase名を取得する。

    Args:
        getter_name (str): getで始まる正式名。

    Returns:
        str: getを省略した名前。
    """
    component_names = {"getUV": "uv", "getUVs": "uvs", "getCV": "cv", "getCVs": "cvs"}
    return component_names.get(getter_name, getter_name[3].lower() + getter_name[4:])


def _getter_definitions():
    """製品ソースの全getterを列挙し、調査用の外部一覧への依存を避ける。

    Yields:
        tuple: 定義モジュール、所有クラスまたはNone、正式getter名。
    """
    root = Path(hlib.__file__).resolve().parent
    for path in sorted(root.rglob("*.py")):
        if "__tests__" in path.parts or "_docs" in path.parts or path.name == "__init__.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        module_name = "hlib." + ".".join(path.relative_to(root).with_suffix("").parts)
        for statement in tree.body:
            if isinstance(statement, ast.ClassDef):
                owner_name, members = statement.name, statement.body
            else:
                owner_name, members = None, [statement]
            for member in members:
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and re.match(r"get[A-Z]", member.name):
                    yield module_name, owner_name, member.name


class GetterAliasesTest(unittest.TestCase):
    """正式getterを維持したまま、省略名から同じ契約を利用できることを確認する。"""

    def setUp(self):
        """独立した空シーンと既定単位を用意する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)
        self.node = hlib.createNode("transform", name="getterAliasTarget")

    def tearDown(self):
        """単位を既定値へ戻す。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_all_getter_definitions_and_public_inheritance_keep_metadata(self):
        """全566件以上の実定義と公開派生型で名前・署名・フラグ情報を照合する。"""
        definitions = list(_getter_definitions())
        self.assertGreaterEqual(len(definitions), 566)
        for module_name, owner_name, getter_name in definitions:
            module = importlib.import_module(module_name)
            owner = module if owner_name is None else getattr(module, owner_name)
            alias_name = _short_name(getter_name)
            alias_owner = importlib.import_module("hlib.cmds." + alias_name) if (
                owner_name is None and module_name.startswith("hlib.cmds.")
            ) else owner
            with self.subTest(module=module_name, owner=owner_name, getter=getter_name):
                getter = getattr(owner, getter_name)
                alias = getattr(alias_owner, alias_name)
                self.assertTrue(callable(alias))
                self.assertEqual(getter.__name__, getter_name)
                self.assertEqual(alias.__name__, alias_name)
                self.assertEqual(inspect.signature(alias), inspect.signature(getter))
                self.assertEqual(alias.__annotations__, getter.__annotations__)
                self.assertEqual(alias.__hlib_getter_name__, getter_name)
                self.assertEqual(alias.__hlib_flag_aliases__, getattr(getter, "__hlib_flag_aliases__", {}))
                self.assertEqual(alias.__hlib_maya_command__, getattr(getter, "__hlib_maya_command__", None))

        for package_name in ("nodes", "plugs", "components", "common"):
            package = getattr(hlib, package_name)
            for public_name in package.__all__:
                cls = getattr(package, public_name)
                if not inspect.isclass(cls):
                    continue
                getter_names = {
                    name for base in cls.__mro__ if base.__module__.startswith("hlib.")
                    for name in base.__dict__ if re.match(r"get[A-Z]", name)
                }
                for getter_name in getter_names:
                    with self.subTest(public_class=public_name, getter=getter_name):
                        self.assertEqual(inspect.signature(getattr(cls, _short_name(getter_name))),
                                         inspect.signature(getattr(cls, getter_name)))

    def test_instance_and_subclass_getter_replacements_are_resolved_at_call_time(self):
        """継承した入口が派生overrideとインスタンス差替えへ追従し、rawフラグを保持する。"""
        marker = object()
        with patch.object(self.node, "getTranslate", return_value=marker) as getter:
            self.assertIs(self.node.translate(ws=True, at=4), marker)
            getter.assert_called_once_with(ws=True, at=4)

        class DerivedTransform(hlib.nodes.Transform):
            """継承入口が正式getterを固定していないことを確認する派生型。"""

            def getTranslate(self, *args, **kwargs):
                """受け取った引数を変更せず返す。

                Args:
                    *args: 受け取った位置引数。
                    **kwargs: 受け取ったキーワード引数。

                Returns:
                    tuple: 位置引数とキーワード引数。
                """
                return args, kwargs

        derived = object.__new__(DerivedTransform)
        derived.__dict__.update(self.node.__dict__)
        raw = {"ws": True, "worldSpace": False, "at": 4}
        self.assertEqual(derived.translate(7, **raw), ((7,), raw))
        with patch.object(DerivedTransform, "getTranslate", return_value=marker) as getter:
            self.assertIs(derived.translate(ws=False), marker)
            getter.assert_called_once_with(ws=False)

    def test_static_and_class_getters_bind_classes_and_instances_consistently(self):
        """静的17件・class2件は束縛後の署名と値を保ち、派生クラスへも追従する。"""
        counts = {staticmethod: 0, classmethod: 0}
        for module_name, owner_name, getter_name in _getter_definitions():
            if owner_name is None or not module_name.startswith("hlib.common."):
                continue
            cls = getattr(importlib.import_module(module_name), owner_name)
            descriptor = inspect.getattr_static(cls, getter_name)
            if not isinstance(descriptor, (staticmethod, classmethod)):
                continue
            counts[type(descriptor)] += 1
            alias_name = _short_name(getter_name)
            instance = object.__new__(cls)
            with self.subTest(cls=cls.__name__, getter=getter_name):
                self.assertIsInstance(inspect.getattr_static(cls, alias_name), classmethod)
                self.assertEqual(inspect.signature(getattr(instance, alias_name)),
                                 inspect.signature(getattr(instance, getter_name)))
                marker = object()
                mock = Mock(return_value=marker)
                replacement = staticmethod(mock) if isinstance(descriptor, staticmethod) else classmethod(mock)
                with patch.object(cls, getter_name, replacement):
                    for receiver in (cls, instance):
                        mock.reset_mock()
                        self.assertIs(getattr(receiver, alias_name)(9, key="raw"), marker)
                        args = (9,) if isinstance(descriptor, staticmethod) else (cls, 9)
                        mock.assert_called_once_with(*args, key="raw")
        self.assertGreaterEqual(counts[staticmethod], 17)
        self.assertGreaterEqual(counts[classmethod], 2)
        self.assertEqual(hlib.common.Preferences.angleUnit(), hlib.common.Preferences.getAngleUnit())
        self.assertEqual(hlib.common.Workspace.root(), hlib.common.Workspace.getRoot())
        self.assertEqual(hlib.common.MainWindow.name(), hlib.common.MainWindow.getName())
        self.assertEqual(hlib.common.Namespace.current(), hlib.common.Namespace.getCurrent())

        class DerivedPreferences(hlib.common.Preferences):
            """静的getterをoverrideする派生型。"""

            @staticmethod
            def getLinearUnit():
                """派生型の照会結果を返す。

                Returns:
                    str: 検証用の値。
                """
                return "derived"

        self.assertEqual(DerivedPreferences.linearUnit(), "derived")
        self.assertEqual(DerivedPreferences().linearUnit(), "derived")

        class DerivedNamespace(hlib.common.Namespace):
            """正式classmethodから生成される派生型。"""

        self.assertIsInstance(DerivedNamespace.current(), DerivedNamespace)
        self.assertIsInstance(DerivedNamespace(":").current(), DerivedNamespace)

    def test_command_aliases_keep_public_identity_and_resolve_replaced_modules(self):
        """13入口は正式モジュールを呼出時に解決し、引数の解釈を正式本体へ委ねる。"""
        getters = [(module_name, getter_name) for module_name, owner_name, getter_name in _getter_definitions()
                   if owner_name is None and module_name.startswith("hlib.cmds.")]
        self.assertEqual(len(getters), 13)
        marker, target = object(), object()
        raw = {"type": False, "typ": True, "unknownFlag": ["raw"]}
        for module_name, getter_name in getters:
            alias_name = _short_name(getter_name)
            module = importlib.import_module(module_name)
            alias_module = importlib.import_module("hlib.cmds." + alias_name)
            with self.subTest(getter=getter_name):
                alias = getattr(hlib, alias_name)
                self.assertIs(alias, getattr(hlib.cmds, alias_name))
                self.assertIs(alias, getattr(alias_module, alias_name))
                self.assertEqual(alias.__name__, alias_name)
                self.assertEqual(inspect.signature(alias), inspect.signature(getattr(module, getter_name)))
                self.assertIn(alias_name, hlib.__all__)
                self.assertIn(alias_name, hlib.cmds.__all__)
                with patch.object(module, getter_name, return_value=marker) as getter:
                    self.assertIs(alias(target, **raw), marker)
                    getter.assert_called_once_with(target, **raw)

    def test_attr_and_get_attr_match_typed_references_flags_and_units(self):
        """attrもPlugを返し、明示フラグのMaya照会と内部/UI単位を維持する。"""
        angle = self.node.getPlug("rotateX")
        angle.set(math.pi / 2)
        for entry in (hlib.attr, hlib.cmds.attr):
            self.assertIs(entry(angle), angle)
            self.assertIsInstance(entry(angle.mplug()), hlib.plugs.DoubleAnglePlug)
            self.assertEqual(entry(str(angle)), angle)
        for unit in ("deg", "rad"):
            cmds.currentUnit(angle=unit)
            self.assertEqual(hlib.attr(angle).get(), hlib.getAttr(angle).get())
            self.assertEqual(hlib.attr(angle).getu(), hlib.getAttr(angle).getu())
            for flags in ({"type": True}, {"typ": True}, {"lock": True}, {"type": False}, {"silent": True}, {"time": 3}):
                self.assertEqual(hlib.attr(angle, **flags), hlib.getAttr(angle, **flags))
        self.assertIsInstance(hlib.attr(self.node.getPlug("translate"), silent=True), hlib.maths.Vector)
        self.assertIsInstance(hlib.attr(self.node.getPlug("worldMatrix[0]"), type=False), hlib.maths.Matrix)
        for entry in (hlib.attr, hlib.getAttr):
            with self.assertRaises(TypeError):
                entry(angle, type=True, typ=True)

    def test_node_methods_take_precedence_and_explicit_plug_access_survives(self):
        """標準matrix/radiusと任意の同名アトリビュートより省略メソッドを優先する。"""
        extra = self.node.addAttr("plug", attributeType="double", defaultValue=3)
        translation = self.node.addAttr("translation", attributeType="double", defaultValue=7)
        self.node.setTranslate((4, 5, 6), at=4)
        self.assertTrue(callable(self.node.plug))
        self.assertEqual(self.node.plug("translateX"), self.node.getPlug("translateX"))
        self.assertEqual(self.node.getPlug("plug"), extra)
        self.assertEqual(self.node.getPlug("plug").get(), 3)
        self.assertTrue(self.node.matrix().isEquivalent(self.node.getMatrix()))
        self.assertIsInstance(self.node.getPlug("matrix"), hlib.plugs.MatrixPlug)
        self.assertEqual(tuple(self.node.translate(at=4)), (4, 5, 6))
        self.assertEqual(self.node.getPlug("translation"), translation)
        self.assertEqual(translation.get(), 7)
        self.assertIsInstance(self.node.getPlug("translate"), hlib.plugs.Double3Plug)
        joint = hlib.createNode("joint", name="getterAliasJoint")
        joint.setRadius(2.5)
        self.assertTrue(callable(joint.radius))
        self.assertEqual(joint.radius(), joint.getRadius())
        self.assertEqual(joint.getPlug("radius").get(), 2.5)

    def test_compound_method_priority_keeps_named_child_brackets(self):
        """node/nameと同名の子はメソッドで隠れても角括弧で取得・編集できる。"""
        name = self.node.getFullName()
        cmds.addAttr(name, longName="group", attributeType="compound", numberOfChildren=2)
        for child in ("node", "name"):
            cmds.addAttr(name, longName=child, attributeType="double", parent="group")
        compound = self.node.getPlug("group")
        compound["node"].set(8)
        compound["name"].set(9)
        self.assertTrue(callable(compound.node))
        self.assertEqual(compound.node(), self.node)
        self.assertTrue(callable(compound.name))
        self.assertEqual(compound.name(), compound.getName())
        self.assertEqual(compound["node"].get(), 8)
        self.assertEqual(compound["name"].get(), 9)
        self.assertEqual(compound.get(), (8, 9))

    def test_stored_properties_and_openmaya_standard_getters_remain_unchanged(self):
        """Component/値/保存参照の保持プロパティとMMatrix.getElementを維持する。"""
        shape = hlib.getNode(cmds.polyCube(constructionHistory=False)[0]).getShape()
        vertices = shape.getVertices([0, 2])
        vertex = vertices[0]
        for cls, name in ((type(vertex), "shape"), (type(vertex), "index"),
                          (type(vertices), "shape"), (type(vertices), "indices")):
            self.assertIsInstance(inspect.getattr_static(cls, name), property)
        self.assertEqual(vertex.shape, shape)
        self.assertEqual(vertex.index, 0)
        self.assertEqual(vertices.indices, (0, 2))
        scene = hlib.common.Scene(Path("stored.ma"))
        with patch.object(cmds, "file", side_effect=AssertionError("Stored property queried Maya")):
            self.assertEqual(scene.path, Path("stored.ma").resolve())
            self.assertEqual(scene.name, "stored.ma")
        matrix = hlib.maths.Matrix(translate=(4, 5, 6))
        self.assertIsInstance(matrix.translate, hlib.maths.Translate)
        self.assertIsInstance(matrix.quaternion, hlib.maths.Quaternion)
        self.assertIs(inspect.getattr_static(hlib.maths.Matrix, "getElement"),
                      inspect.getattr_static(om2.MMatrix, "getElement"))
        self.assertEqual(matrix.getElement(3, 0), om2.MMatrix(matrix).getElement(3, 0))
        self.assertNotIn("element", hlib.maths.Matrix.__dict__)

    def test_array_element_alias_keeps_creation_flags_exceptions_and_undo_behavior(self):
        """elementのcreate/idxは正式getterへ委譲し、既定拒否とUndoなし作成を維持する。"""
        numeric = self.node.addAttr("samples", attributeType="double", multi=True)
        message = self.node.addAttr("links", attributeType="message", multi=True)
        undo_name = cmds.undoInfo(query=True, undoName=True)
        for getter in (numeric.getElement, numeric.element):
            with self.assertRaises(IndexError):
                getter(idx=6)
        self.assertEqual(list(numeric.mplug().getExistingArrayAttributeIndices()), [])
        element = numeric.element(idx=6, create=True)
        self.assertEqual(element, numeric.getElement(6))
        self.assertEqual(list(numeric.mplug().getExistingArrayAttributeIndices()), [6])
        self.assertIsInstance(message.element(4, create=True), hlib.plugs.MessagePlug)
        self.assertEqual(list(message.mplug().getExistingArrayAttributeIndices()), [])
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), undo_name)
        with patch.object(cmds, "getAttr", side_effect=AssertionError("Invalid flags reached Maya")):
            with self.assertRaises(TypeError):
                numeric.element(index=6, idx=6)
            with self.assertRaises(TypeError):
                numeric.element(True, create=True)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

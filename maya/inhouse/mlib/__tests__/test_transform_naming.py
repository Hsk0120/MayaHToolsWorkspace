"""変換APIの改名後も値型・Plug入口・引数・保存形式を保持することを検証する。"""

import importlib
import inspect
import math
import sys
import unittest

import mlib
import maya.api.OpenMaya as om2
import maya.cmds as cmds


class TransformNamingTest(unittest.TestCase):
    """Translate・Rotate・Scaleの正式getterとアトリビュートを実Mayaで確認する。"""

    def setUp(self):
        """独立した空シーンと既定単位・Undoキューを用意する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True)

    def tearDown(self):
        """単位を既定値へ戻す。"""
        cmds.currentUnit(linear="cm", angle="deg", time="film")

    def test_public_types_and_module_paths_have_no_old_aliases(self):
        """新しい値型・ファイルを公開し、旧クラス・旧ファイル入口を残さない。"""
        maths = mlib.maths
        for module_name, class_name, base in (
                ("translate", "Translate", om2.MVector),
                ("eulerRotate", "EulerRotate", om2.MEulerRotation)):
            cls = getattr(maths, class_name)
            self.assertIs(getattr(importlib.import_module("mlib.maths." + module_name), class_name), cls)
            self.assertEqual(cls.__name__, class_name)
            self.assertTrue(issubclass(cls, base))
            self.assertIn(class_name, maths.__all__)
        for name in ("Translation", "EulerRotation", "Rotate"):
            self.assertFalse(hasattr(maths, name), name)
            self.assertNotIn(name, maths.__all__)
        for module_name in ("translation", "eulerRotation"):
            with self.assertRaises(ModuleNotFoundError):
                importlib.import_module("mlib.maths." + module_name)

    def test_node_api_renames_remove_former_method_names(self):
        """正式getter/setterを公開し、旧名とget省略メソッドを残さない。"""
        groups = (
            ((mlib.nodes.Transform, mlib.nodes.Transforms),
             ("getTranslation", "setTranslation", "translation", "getRotation", "setRotation",
              "rotation", "getScaling", "setScaling", "scaling")),
            ((mlib.nodes.ComposeMatrix,),
             ("getTranslation", "setTranslation", "translation", "getRotation", "setRotation", "rotation")),
            ((mlib.nodes.PairBlend,),
             ("getTranslation", "setTranslation", "translation", "getRotation", "setRotation", "rotation",
              "getRotationInterpolation", "setRotationInterpolation", "rotationInterpolation")),
            ((mlib.nodes.AimConstraint,),
             ("getRotationConnections", "rotationConnections", "getRestRotation", "setRestRotation",
              "restRotation", "getOutputRotation", "outputRotation")),
            ((mlib.nodes.AngleBetween,), ("getRotation", "rotation")),
            ((mlib.nodes.Joint, mlib.nodes.Joints), ("freezeRotation",)),
        )
        for classes, old_names in groups:
            for cls in classes:
                for old in old_names:
                    new = old
                    for before, after in (("Translation", "Translate"), ("translation", "translate"),
                                          ("Rotation", "Rotate"), ("rotation", "rotate"),
                                          ("Scaling", "Scale"), ("scaling", "scale")):
                        new = new.replace(before, after)
                    if not new.startswith(("get", "set", "freeze")):
                        new = "get" + new[0].upper() + new[1:]
                    with self.subTest(cls=cls.__name__, old=old, new=new):
                        self.assertTrue(callable(getattr(cls, new)))
                        self.assertFalse(hasattr(cls, old))

    def test_getters_and_attribute_plugs_keep_typed_values(self):
        """get省略名をアトリビュートへ返し、正式getterの単位・回転順序を保つ。"""
        node = mlib.createNode("transform")
        node.getPlug("rotateOrder").set(5)
        cmds.currentUnit(linear="m", angle="rad")
        self.assertIs(node.setTranslate((25, 50, 75), at=1), node)
        self.assertIs(node.setRotate((10, 20, 30), unit="deg"), node)
        self.assertIs(node.setScale((2, 3, 4)), node)
        for attr, getter, value_type in (
                ("translate", "getTranslate", mlib.maths.Translate),
                ("rotate", "getRotate", mlib.maths.EulerRotate),
                ("scale", "getScale", mlib.maths.Scale)):
            with self.subTest(attr=attr):
                self.assertFalse(callable(getattr(node, attr)))
                plug = node.getPlug(attr)
                self.assertIsInstance(plug, mlib.plugs.Double3Plug)
                self.assertIsInstance(plug.get(), value_type)
                options = {"at": 1} if attr == "translate" else {}
                self.assertIsInstance(getattr(node, getter)(**options), value_type)
                self.assertEqual(getattr(node, attr), plug)
                self.assertEqual(tuple(getattr(node, attr).get()), tuple(plug.get()))
        self.assertEqual(tuple(node.getTranslate(at=1)), (25, 50, 75))
        self.assertEqual(node.getRotate().orderName, 'zyx')
        for actual, expected in zip(node.getRotate(), (10, 20, 30)):
            self.assertAlmostEqual(actual, math.radians(expected), places=9)
        self.assertEqual(tuple(node.getScale()), (2, 3, 4))

    def test_bulk_metadata_and_calculation_only_setter_keep_existing_contract(self):
        """bulkの保持順・正式getterのメタデータ・get=Trueの非更新を維持する。"""
        nodes = [mlib.createNode("transform") for _ in range(2)]
        collection = mlib.nodes.Transforms(nodes)
        self.assertIs(collection.setTranslate((1, 2, 3), at=1), collection)
        self.assertEqual([tuple(value) for value in collection.getTranslate(at=1)], [(1, 2, 3)] * 2)
        for getter_name, short in (("getTranslate", "translate"), ("getRotate", "rotate"),
                                   ("getScale", "scale")):
            for cls in (mlib.nodes.Transform, mlib.nodes.Transforms):
                getter = getattr(cls, getter_name)
                self.assertTrue(callable(getter))
                self.assertFalse(hasattr(cls, short))
                self.assertEqual(inspect.signature(getter),
                                 inspect.signature(getattr(mlib.nodes.Transform, getter_name)))
            self.assertIs(collection._bulk_methods[getter_name], getattr(mlib.nodes.Transform, getter_name))
            self.assertNotIn(short, collection._bulk_methods)
        calculated = collection.setTranslate((4, 5, 6), False, 1, False, True)
        self.assertEqual(calculated, [[4, 5, 6]] * 2)
        self.assertEqual([tuple(value) for value in collection.getTranslate(at=1)], [(1, 2, 3)] * 2)
        with self.assertRaises(TypeError):
            collection.getTranslate(ws=True, worldSpace=True)
        self.assertEqual(mlib.nodes.Transforms().getTranslate(unknown=True), [])

    def test_renamed_setter_retains_undo_and_fast_behavior(self):
        """新名の更新も通常はUndo/Redoでき、fastはUndoキューへ追加しない。"""
        node = mlib.createNode("transform")
        node.setTranslate((1, 2, 3), at=1)
        cmds.flushUndo()
        self.assertIs(node.setTranslate((4, 5, 6), at=1), node)
        self.assertEqual(tuple(node.getTranslate(at=1)), (4, 5, 6))
        cmds.undo()
        self.assertEqual(tuple(node.getTranslate(at=1)), (1, 2, 3))
        cmds.redo()
        self.assertEqual(tuple(node.getTranslate(at=1)), (4, 5, 6))
        cmds.flushUndo()
        self.assertIs(node.setTranslate((7, 8, 9), at=1, fast=True), node)
        self.assertEqual(tuple(node.getTranslate(at=1)), (7, 8, 9))
        self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True))

    def test_calculation_nodes_and_standard_attribute_accessors_keep_arguments(self):
        """計算ノードの新名でも入力番号とMaya標準useEulerRotation入口を保持する。"""
        compose = mlib.createNode("composeMatrix")
        self.assertIs(compose.setTranslate((1, 2, 3)), compose)
        self.assertIs(compose.setRotate((0.1, 0.2, 0.3)), compose)
        self.assertEqual(tuple(compose.getTranslate()), (1, 2, 3))
        for actual, expected in zip(compose.getRotate(), (0.1, 0.2, 0.3)):
            self.assertAlmostEqual(actual, expected)
        self.assertEqual(compose.getUseEulerRotationPlug(), compose.getPlug("useEulerRotation"))
        self.assertIs(compose.setUseEulerRotation(False), compose)
        self.assertFalse(compose.getUseEulerRotation())
        source = mlib.createNode("network").addAttr("value", attributeType="bool", defaultValue=True)
        self.assertIs(compose.connectUseEulerRotation(source), compose)
        self.assertTrue(compose.getUseEulerRotation())
        self.assertTrue(compose.getUseEulerRotationPlug().isConnectedTo(source, src=True, dst=False))
        pair = mlib.createNode("pairBlend")
        self.assertIs(pair.setTranslate(1, (4, 5, 6)), pair)
        self.assertIs(pair.setTranslate(2, (7, 8, 9)), pair)
        self.assertEqual(tuple(pair.getTranslate(idx=1)), (4, 5, 6))
        self.assertEqual(tuple(pair.getTranslate(2)), (7, 8, 9))
        self.assertIs(pair.setRotateInterpolation("quaternion"), pair)
        self.assertEqual(pair.getRotateInterpolation(), "quaternion")

    def test_native_conversion_and_legacy_json_tags_return_new_classes(self):
        """標準変換名と追加変換名を併存し、旧JSONタグを新しい数学型へ復元する。"""
        from mlib.json.codec import decode, encode

        quaternion = mlib.maths.EulerRotate(0.1, 0.2, 0.3, "zyx").asQuaternion()
        before = tuple(quaternion)
        for method in (quaternion.asEulerRotation, quaternion.asEulerRotate):
            result = method()
            self.assertIsInstance(result, mlib.maths.EulerRotate)
            self.assertTrue(result.asQuaternion().isEquivalent(quaternion, 1e-12))
        self.assertEqual(tuple(quaternion), before)
        for tag, cls, fields in (
                ("Translation", mlib.maths.Translate, {"values": [1, 2, 3]}),
                ("EulerRotation", mlib.maths.EulerRotate, {"values": [0.1, 0.2, 0.3], "order": "zyx"})):
            record = {"type": "math:" + tag, "value": encode(fields)}
            restored = decode(record)
            self.assertIs(type(restored), cls)
            self.assertEqual(encode(restored), record)
            roundtrip = mlib.json.loads(mlib.json.dumps(restored))
            self.assertIs(type(roundtrip), cls)
            self.assertEqual(tuple(roundtrip), tuple(restored))
        for tag in ("Translate", "Rotate", "EulerRotate"):
            with self.assertRaises(ValueError):
                decode({"type": "math:" + tag, "value": encode({"values": [1, 2, 3]})})


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

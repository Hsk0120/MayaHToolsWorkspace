"""mlib 2.0 の名前方針(DESIGN §2・§3)を対応表データで固定する。

旧名(別名を含む)が単数・複数形クラスのどこにも残らないこと、新名が単数に定義されること、
複数形クラスが単数への一括転送を持たないこと、mlib 本体のソースに旧名の def が無いことを確かめる。
2.1.0 で lowerCamelCase へ改名した公開引数に旧名が残らないことも確かめる。
4.0.0 でマルチアトリビュートの呼び名へ揃えた ``MultiPlug``・``isMulti``・``isMultiElement``・``getMulti`` について、
旧名(``ArrayPlug``・``isArray``・``isElement``・``getArray``)が公開APIに残らないことも確かめる。
個々の新しい約束(引数・戻り値・Undo・fast)は test_spec_node_*/dag_*/transform_*/plug_* が受け持つ。
"""

import inspect
import re
import unittest
from pathlib import Path

import mlib
mlib.reload()
from mlib.nodes import DagNode, Joint, Joints, Node, Nodes, Shape, Transform
from mlib.plugs import CompoundPlug, MultiPlug, Plug

#: 廃止した名前(DESIGN §3)。単数クラスと、その複数形の双方に残らない。
REMOVED = {
    Node: ("create", "getPath", "isChildOf", "getAttrCount", "sameInstance", "getAssignedObjects",
           "getMaterials", "getExtraAttrs"),
    DagNode: ("dagFn", "getParentPath", "getFullPath", "getPartialPath", "collectSkinClusters"),
    Transform: ("transformFn", "reset", "resetPivot", "freeze", "getEuler", "getJointOrientQuaternion",
                "getShearing", "setShearing", "getOffsetParentMatrix", "setOffsetParentMatrix"),
    Joint: ("isJoint",),
    Plug: ("getDataType", "getPlugName", "lock", "getEnumFieldName", "getNextAvailable",
           "isArray", "isElement", "getArray"),
    MultiPlug: ("getNextAvailableIndex", "isArray", "isElement", "getArray"),
    CompoundPlug: ("isArray", "isElement", "getArray"),
}

#: 4.0.0 でマルチアトリビュートの呼び名へ改名したPlugの判定・取得(旧名, 新名)。
RENAMED_MULTI = (("isArray", "isMulti"), ("isElement", "isMultiElement"), ("getArray", "getMulti"))

#: 単数クラスと対応する複数形クラス。
PLURALS = {Node: Nodes, Joint: Joints}

#: 統合後に定義されている名前(DESIGN §2)。単数の def を確かめる。
REQUIRED = {
    Node: ("mfn", "hasFn", "setLocked", "getType", "isType", "resetAttrs", "getPlugs", "getConnections",
           "isParentOf", "isAncestorOf", "getName", "getFullName", "sameNode"),
    DagNode: ("mfn", "getRoot", "getSiblings", "getBoundingBox", "isIntermediateObject", "getShape",
              "show", "hide", "getSkinClusters", "getParent", "getParents", "getChildren", "mpath"),
    Transform: ("mfn", "setPivot", "getPivot", "makeIdentity", "setParent", "getRotate",
                "getShear", "setShear", "getQuaternion", "getMatrix", "setMatrix"),
    Joint: ("getJointOrient", "jointOrientToRotate", "freezeRotate", "getSkinClusters"),
}

#: 複数形が独自の集約として持つ名前(単数への転送ではない)。Joints.getSkinClusters は重複を除いた SkinClusters を返す。
PLURAL_OWN = ("getSkinClusters",)

#: 5.0.0で複数形へ明示的に戻した一括の書込み(Nodes._forward で各要素へ適用する)。
PLURAL_BULK = ("setAttrFlags", "resetAttrs", "setLocked", "setColor", "setVisibility", "show", "hide", "setParent")

#: 3.0.0 で廃止した複数形の一括転送と、その基盤の名前。
REMOVED_PLURAL = ("callEach", "getNames", "delete", "removeInfluences", "jointOrientToRotate", "freezeRotate",
                  "_bulk_entries", "_bulk_methods", "_bulk_returns", "_dispatch_shared", "_calculating_setters")


class RemovedNamesTest(unittest.TestCase):
    """旧名は単数・複数形のどちらにも無い(別名も残さない)。"""

    def test_singular_classes_have_no_removed_names(self):
        for cls, names in REMOVED.items():
            for name in names:
                with self.subTest(cls=cls.__name__, name=name):
                    self.assertFalse(hasattr(cls, name), "%s.%s remains" % (cls.__name__, name))

    def test_plural_classes_have_no_removed_names(self):
        for cls, plural in PLURALS.items():
            for base, names in REMOVED.items():
                if not issubclass(cls, base):
                    continue
                for name in names:
                    with self.subTest(cls=plural.__name__, name=name):
                        self.assertFalse(hasattr(plural, name), "%s.%s remains" % (plural.__name__, name))

    def test_multi_plug_owns_next_available(self):
        """getNextAvailable は MultiPlug だけに定義され、Plug・CompoundPlug には無い。"""
        self.assertIn("getNextAvailable", MultiPlug.__dict__)
        self.assertFalse(hasattr(Plug, "getNextAvailable"))
        self.assertFalse(hasattr(CompoundPlug, "getNextAvailable"))
        self.assertFalse(hasattr(MultiPlug, "getNextAvailableIndex"))
        parameters = inspect.signature(MultiPlug.getNextAvailable).parameters
        self.assertIn("vacant", parameters)
        self.assertEqual(parameters["vacant"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIs(parameters["vacant"].default, False)

    def test_shape_does_not_override_get_parent(self):
        """Shape.getParent の override(super 転送のみ)は削除し、DagNode の実装を継承する。"""
        self.assertNotIn("getParent", Shape.__dict__)
        self.assertIs(Shape.getParent, DagNode.getParent)

    def test_plug_operators_exist(self):
        """接続演算子(D3-5)は Plug に定義される。"""
        for name in ("__rshift__", "__lshift__", "__floordiv__"):
            with self.subTest(name=name):
                self.assertIn(name, Plug.__dict__)
                self.assertTrue(callable(getattr(Plug, name)))

    def test_unlock_has_no_undoable_argument(self):
        parameters = inspect.signature(Plug.unlock).parameters
        self.assertNotIn("undoable", parameters)
        self.assertIn("fast", parameters)
        self.assertEqual(parameters["fast"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_connections_have_no_pcls(self):
        for cls in (Node, Plug):
            with self.subTest(cls=cls.__name__):
                self.assertNotIn("pcls", inspect.signature(cls.getConnections).parameters)


class MultiRenameTest(unittest.TestCase):
    """4.0.0 の改名: ArrayPlug → MultiPlug、isArray/isElement/getArray → isMulti/isMultiElement/getMulti。

    互換の別名・旧モジュールは残さない。
    """

    def test_old_class_is_not_public(self):
        """ArrayPlug は mlib.plugs・mlib のどちらにも無く、__all__ にも無い。"""
        for module in (mlib.plugs, mlib):
            with self.subTest(module=module.__name__):
                self.assertFalse(hasattr(module, "ArrayPlug"))
                self.assertNotIn("ArrayPlug", getattr(module, "__all__", ()))
        self.assertIn("MultiPlug", mlib.plugs.__all__)
        self.assertIs(mlib.plugs.MultiPlug, MultiPlug)
        self.assertEqual(MultiPlug.__module__, "mlib.plugs.multiPlug")
        self.assertTrue(issubclass(MultiPlug, Plug))

    def test_old_module_is_removed(self):
        """旧モジュール mlib.plugs.arrayPlug は import できず、ファイルも無い。"""
        root = Path(mlib.__file__).resolve().parent
        self.assertFalse((root / "plugs" / "arrayPlug.py").exists())
        self.assertTrue((root / "plugs" / "multiPlug.py").exists())
        with self.assertRaises(ImportError):
            __import__("mlib.plugs.arrayPlug")

    def test_plug_methods_are_renamed(self):
        """新名は Plug に定義され、旧名はどのPlugクラスにも無い。"""
        for old, new in RENAMED_MULTI:
            with self.subTest(old=old, new=new):
                self.assertIn(new, Plug.__dict__)
                self.assertTrue(callable(getattr(Plug, new)))
                for cls in (Plug, MultiPlug, CompoundPlug):
                    self.assertFalse(hasattr(cls, old), "%s.%s remains" % (cls.__name__, old))
        for name in mlib.plugs.__all__:
            cls = getattr(mlib.plugs, name)
            for old, _new in RENAMED_MULTI:
                with self.subTest(cls=name, old=old):
                    self.assertFalse(hasattr(cls, old), "%s.%s remains" % (name, old))


class RequiredNamesTest(unittest.TestCase):
    """新名は単数に定義され、複数形へ同じ署名で転送される。"""

    def test_singular_classes_define_required_names(self):
        for cls, names in REQUIRED.items():
            for name in names:
                with self.subTest(cls=cls.__name__, name=name):
                    self.assertTrue(callable(getattr(cls, name)), "%s.%s missing" % (cls.__name__, name))

    def test_plural_classes_do_not_forward(self):
        """複数形クラスは明示した書込み(PLURAL_BULK)以外の一括転送を持たない。要素ごとに単数のメソッドを呼ぶ。"""
        for cls, plural in PLURALS.items():
            for base, names in REQUIRED.items():
                if not issubclass(cls, base):
                    continue
                for name in names:
                    if name in PLURAL_OWN:
                        continue
                    if name in PLURAL_BULK:
                        with self.subTest(cls=plural.__name__, bulk=name):
                            self.assertIn(name, Nodes.__dict__)
                        continue
                    with self.subTest(cls=plural.__name__, name=name):
                        self.assertFalse(hasattr(plural, name), "%s.%s remains" % (plural.__name__, name))
            for name in PLURAL_OWN:
                with self.subTest(cls=plural.__name__, own=name):
                    if plural is Joints:
                        self.assertIn(name, Joints.__dict__)
            for name in REMOVED_PLURAL:
                with self.subTest(cls=plural.__name__, name=name):
                    self.assertFalse(hasattr(plural, name), "%s.%s remains" % (plural.__name__, name))
        self.assertFalse(hasattr(mlib.nodes, "DagNodes"))
        self.assertFalse(hasattr(mlib.nodes, "Transforms"))

    def test_moved_dag_queries_live_on_dag_node(self):
        """getRoot・getSiblings・getBoundingBox・isIntermediateObject は DagNode が持ち、Transform は継承する。"""
        for name in ("getRoot", "getSiblings", "getBoundingBox", "isIntermediateObject"):
            with self.subTest(name=name):
                self.assertIn(name, DagNode.__dict__)
                self.assertNotIn(name, Transform.__dict__)

    def test_rotate_accepts_order(self):
        parameters = inspect.signature(Transform.getRotate).parameters
        self.assertIn("order", parameters)
        self.assertEqual(parameters["order"].kind, inspect.Parameter.KEYWORD_ONLY)
        self.assertIsNone(parameters["order"].default)

    def test_set_parent_has_no_short_relative(self):
        """3.0.0で短縮名rは廃止し、長名relativeだけを持つ。"""
        parameters = inspect.signature(Transform.setParent).parameters
        self.assertIn("relative", parameters)
        self.assertNotIn("r", parameters)

    def test_get_plugs_signature(self):
        parameters = inspect.signature(Node.getPlugs).parameters
        self.assertIn("userDefined", parameters)
        self.assertIn("includeChildren", parameters)
        self.assertIs(parameters["userDefined"].default, False)
        self.assertIs(parameters["includeChildren"].default, True)

    def test_show_hide_accept_fast(self):
        for name in ("show", "hide"):
            with self.subTest(name=name):
                parameters = inspect.signature(getattr(DagNode, name)).parameters
                self.assertIn("fast", parameters)
                self.assertEqual(parameters["fast"].kind, inspect.Parameter.KEYWORD_ONLY)

    def test_enum_name_accepts_value(self):
        parameters = inspect.signature(Plug.getEnumName).parameters
        self.assertIn("value", parameters)
        self.assertIsNone(parameters["value"].default)
        self.assertTrue(callable(Plug.getEnumNames))

    def test_ui_units_on_limits(self):
        for name in ("getMin", "getMax", "getSoftMin", "getSoftMax", "getDefault"):
            with self.subTest(name=name):
                parameters = inspect.signature(getattr(Plug, name)).parameters
                self.assertIn("uiUnits", parameters)
                self.assertEqual(parameters["uiUnits"].kind, inspect.Parameter.KEYWORD_ONLY)


class SourceTextTest(unittest.TestCase):
    """mlib の nodes・plugs のソースに旧名の def・集まりクラスの転送文字列が残らない。

    Plugin/Module の getPath()、components の getMaterials() は別クラスの正式名なので対象外(nodes・plugs だけを見る)。
    """

    OLD_NAMES = sorted(set(sum((list(names) for names in REMOVED.values()), [])) - {"create", "reset", "lock", "getNextAvailable"})

    def test_no_old_definitions_in_sources(self):
        root = Path(mlib.__file__).resolve().parent
        pattern = re.compile(r"^\s*def (%s)\(|\"(%s)\":" % ("|".join(self.OLD_NAMES), "|".join(self.OLD_NAMES)), re.MULTILINE)
        offenders = []
        for file in list((root / "nodes").glob("*.py")) + list((root / "plugs").glob("*.py")):
            text = file.read_text(encoding="utf-8")
            for match in pattern.finditer(text):
                offenders.append("%s: %s" % (file.relative_to(root), match.group(0).strip()))
        self.assertEqual(offenders, [])


class RenamedArgumentsTest(unittest.TestCase):
    """2.1.0 で lowerCamelCase へ改名した公開引数に旧名が残らない(互換の旧名も受け付けない)。"""

    @staticmethod
    def renamed():
        """(呼出し先の表示名, 呼出し先, 旧引数名, 新引数名)を返す。"""
        from mlib import common
        from mlib.common import references, units
        from mlib.nodes import AnimCurve, DagPose, IkHandle, Mesh, Reference, SkinCluster
        return (
            ("Node.isType", Node.isType, "node_type", "nodeType"),
            ("Node.getNodeName", Node.getNodeName, "remove_namespace", "removeNamespace"),
            ("Transform.getClosestAxisToVector", Transform.getClosestAxisToVector, "ref_vector", "refVector"),
            ("Transform.getClosestAxisToVector", Transform.getClosestAxisToVector, "include_negative", "includeNegative"),
            ("Joint.removeInfluence", Joint.removeInfluence, "transfer_to_parent", "transferToParent"),
            ("Joint.removeInfluence", Joint.removeInfluence, "skin_cluster", "skinCluster"),
            ("Joint.reparentChildren", Joint.reparentChildren, "parent_joint", "parentJoint"),
            ("SkinCluster.__init__", SkinCluster.__init__, "skin_cluster", "skinCluster"),
            ("SkinCluster.bind", SkinCluster.bind, "max_influences", "maxInfluences"),
            ("SkinCluster.removeInfluence", SkinCluster.removeInfluence, "transfer_to_parent", "transferToParent"),
            ("SkinCluster.transferWeights", SkinCluster.transferWeights, "source_target_pairs", "sourceTargetPairs"),
            ("DagPose.fromSkinCluster", DagPose.fromSkinCluster, "skin_cluster", "skinCluster"),
            ("IkHandle.getJoints", IkHandle.getJoints, "include_tip", "includeTip"),
            ("Mesh.reorderVertices", Mesh.reorderVertices, "uv_set", "uvSet"),
            ("Mesh.getVertexNormals", Mesh.getVertexNormals, "angle_weighted", "angleWeighted"),
            ("Reference.getFilename", Reference.getFilename, "with_copy_number", "withCopyNumber"),
            ("AnimCurve.shiftKeys", AnimCurve.shiftKeys, "input_offset", "inputOffset"),
            ("AnimCurve.scaleKeys", AnimCurve.scaleKeys, "value_pivot", "valuePivot"),
            ("AnimCurve.mirror", AnimCurve.mirror, "input_pivot", "inputPivot"),
            ("CompoundPlug.__getitem__", CompoundPlug.__getitem__, "name_or_index", "nameOrIndex"),
            ("DampedSpring.solve", common.DampedSpring.solve, "seconds_per_sample", "secondsPerSample"),
            ("DrivenKey.setKey", common.DrivenKey.setKey, "driver_value", "driverValue"),
            ("Plugin.ensureNodePlugin", common.Plugin.ensureNodePlugin, "node_type", "nodeType"),
            ("PluginPackage.__init__", common.PluginPackage.__init__, "minimum_version", "minimumVersion"),
            ("ScalarGraph.__init__", common.ScalarGraph.__init__, "create_node", "createNode"),
            ("ScriptJob.__init__", common.ScriptJob.__init__, "kill_with_scene", "killWithScene"),
            ("listReferences", references.listReferences, "top_level_only", "topLevelOnly"),
            ("units.convertDistance", units.convertDistance, "to_unit", "toUnit"),
        )

    def test_old_argument_names_are_absent(self):
        for label, function, old, new in self.renamed():
            with self.subTest(function=label, old=old):
                parameters = inspect.signature(function).parameters
                self.assertNotIn(old, parameters)
                self.assertIn(new, parameters)

    def test_old_keyword_raises_type_error(self):
        from mlib.common import DampedSpring, references, units
        calls = (
            ("units.convertDistance", lambda: units.convertDistance(1.0, to_unit="cm")),
            ("DampedSpring.solve", lambda: DampedSpring.solve([0.0, 1.0], seconds_per_sample=1.0 / 24.0)),
            ("listReferences", lambda: references.listReferences(top_level_only=True)),
        )
        for label, call in calls:
            with self.subTest(function=label):
                with self.assertRaises(TypeError):
                    call()


if __name__ == "__main__":
    unittest.main()

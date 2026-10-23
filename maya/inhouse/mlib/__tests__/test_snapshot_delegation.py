"""保存表現・周期CV・SDK探索と、Snapshot適用の通常Undo境界を検証する。"""

import sys
import unittest
import uuid
from unittest import mock

import maya.cmds as cmds

import mlib


class SnapshotDelegationTest(unittest.TestCase):
    """既存シーンから独立した対象だけで保存・復元の境界を比較する。"""

    def setUp(self):
        """専用名前空間と元の単位・Undo状態を保持する。"""
        self.namespace = "mlibSnapshotDelegation_" + uuid.uuid4().hex
        self.units = {key: cmds.currentUnit(query=True, **{key: True}) for key in ("linear", "angle", "time")}
        self.undo_enabled = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(stateWithoutFlush=True)
        cmds.namespace(add=self.namespace)

    def tearDown(self):
        """作成物と変更した設定だけを元へ戻す。"""
        cmds.namespace(removeNamespace=self.namespace, deleteNamespaceContent=True)
        for key, value in self.units.items():
            cmds.currentUnit(**{key: value})
        cmds.undoInfo(stateWithoutFlush=self.undo_enabled)

    def node(self, kind="network", name="node"):
        """専用名前空間内へノードを作る。"""
        return mlib.getNode(cmds.createNode(kind, name=self.namespace + ":" + name))

    def roundtrip(self, value):
        """公開JSON入口で保存・読込みを行う。"""
        return mlib.json.loads(mlib.json.dumps(value))

    def test_attribute_record_shapes_and_ui_units(self):
        """スカラー・複合値・行列が従来の保存形状とUI単位を維持する。"""
        node = self.node("transform")
        for key, value in (("linear", "m"), ("angle", "rad"), ("time", "pal")):
            cmds.currentUnit(**{key: value})
        for name, kind, value in (("charValue", "char", 65), ("timeValue", "time", 6.5)):
            cmds.addAttr(node.getFullName(), longName=name, attributeType=kind)
            cmds.setAttr(node.getFullName() + "." + name, value)
        cmds.addAttr(node.getFullName(), longName="text", dataType="string")
        cmds.setAttr(node.getFullName() + ".text", "保存値", type="string")
        cmds.addAttr(node.getFullName(), longName="matrixValue", dataType="matrix")
        matrix = list(mlib.maths.Matrix(translate=(4, 5, 6)))
        cmds.setAttr(node.getFullName() + ".matrixValue", *matrix, type="matrix")
        cmds.setAttr(node.getFullName() + ".translate", 2, 3, 4)
        cmds.setAttr(node.getFullName() + ".rotate", .2, .3, .4)
        attrs = ["translate", "rotate", "charValue", "timeValue", "text", "matrixValue"]
        snapshot = self.roundtrip(mlib.json.AttributesSnapshot.capture(node, attrs))
        records = {item["name"]: item for item in snapshot.records[0]["attributes"]}
        for name in attrs:
            expected = cmds.getAttr(node.getFullName() + "." + name)
            if name == "matrixValue":
                expected = list(expected)
            self.assertEqual(records[name]["value"], expected, name)
        self.assertIs(type(records["translate"]["value"]), list)
        self.assertIs(type(records["translate"]["value"][0]), tuple)
        cmds.setAttr(node.getFullName() + ".translate", 7, 8, 9)
        snapshot.apply()
        self.assertEqual(cmds.getAttr(node.getFullName() + ".translate"), [(2, 3, 4)])
        cmds.undo()
        self.assertEqual(cmds.getAttr(node.getFullName() + ".translate"), [(7, 8, 9)])

    def test_null_and_typed_numeric_records(self):
        """未初期化値と子を持たないtyped数値を、保存型を変えず扱う。"""
        node = self.node()
        for name, kind in (("emptyText", "string"), ("emptyMatrix", "matrix"), ("emptyTuple", "double3")):
            cmds.addAttr(node.getFullName(), longName=name, dataType=kind)
        empty = self.roundtrip(mlib.json.AttributesSnapshot.capture(node, ["emptyText", "emptyMatrix", "emptyTuple"]))
        self.assertEqual([item["value"] for item in empty.records[0]["attributes"]], [None, None, None])
        attrs = []
        for kind in ("double2", "double3", "float2", "float3", "long2", "long3", "short2", "short3"):
            name = "typed_" + kind
            cmds.addAttr(node.getFullName(), longName=name, dataType=kind)
            cmds.setAttr(node.getFullName() + "." + name, *range(1, int(kind[-1]) + 1), type=kind)
            attrs.append(name)
        captured = self.roundtrip(mlib.json.AttributesSnapshot.capture(node, attrs))
        expected = {name: cmds.getAttr(node.getFullName() + "." + name) for name in attrs}
        self.assertEqual({item["name"]: item["value"] for item in captured.records[0]["attributes"]}, expected)
        for name in attrs:
            kind = name[len("typed_"):]
            cmds.setAttr(node.getFullName() + "." + name, *([9] * int(kind[-1])), type=kind)
        captured.apply()
        self.assertEqual({name: cmds.getAttr(node.getFullName() + "." + name) for name in attrs}, expected)
        cmds.undo()
        self.assertEqual(cmds.getAttr(node.getFullName() + ".typed_double3"), [(9, 9, 9)])

    def test_all_records_are_validated_before_writing(self):
        """後続の不正レコードで、先行する正常レコードも更新されない。"""
        first, second = self.node("transform", "first"), self.node("transform", "second")
        snapshot = self.roundtrip(mlib.json.AttributesSnapshot.capture([first, second], ["translate"]))
        cmds.setAttr(first.getFullName() + ".tx", 9)
        snapshot.records[1]["attributes"][0]["value"] = [(1, 2)]
        with self.assertRaises(ValueError):
            snapshot.apply()
        self.assertEqual(cmds.getAttr(first.getFullName() + ".tx"), 9)

    def test_apply_keeps_undo_and_restores_outer_fast(self):
        """外側fastでもSnapshotの変更は単一Undoで戻り、外側の指定へ復帰する。"""
        from mlib.common._fast import _active, is_fast
        node = self.node("transform")
        snapshot = self.roundtrip(mlib.json.AttributesSnapshot.capture(node, ["translate", "visibility"]))
        cmds.setAttr(node.getFullName() + ".tx", 9)
        cmds.setAttr(node.getFullName() + ".visibility", False)
        token = _active.set(True)
        try:
            snapshot.apply()
            self.assertTrue(is_fast())
        finally:
            _active.reset(token)
        self.assertEqual(cmds.undoInfo(query=True, undoName=True), "mlibJsonApply")
        cmds.undo()
        self.assertEqual(cmds.getAttr(node.getFullName() + ".tx"), 9)
        self.assertFalse(cmds.getAttr(node.getFullName() + ".visibility"))
        cmds.redo()
        self.assertEqual(cmds.getAttr(node.getFullName() + ".tx"), 0)
        self.assertTrue(cmds.getAttr(node.getFullName() + ".visibility"))

    def test_failed_apply_restores_outer_fast_and_keeps_partial_undo(self):
        """更新中の例外でもfastが復帰し、完了済み更新は一回のUndoで戻せる。"""
        from mlib.common._fast import _active, is_fast
        import mlib.json.snapshots as snapshots
        node = self.node("transform")
        snapshot = self.roundtrip(mlib.json.AttributesSnapshot.capture(node, ["translateX", "visibility"]))
        cmds.setAttr(node.getFullName() + ".tx", 9)
        original = snapshots._set_attribute

        def write(target, attr):
            """先頭を設定し、後続の更新時に実行中エラーを再現する。"""
            self.assertFalse(is_fast())
            if attr["name"] == "visibility":
                raise RuntimeError("snapshot write failure")
            return original(target, attr)

        token = _active.set(True)
        try:
            with mock.patch.object(snapshots, "_set_attribute", side_effect=write):
                with self.assertRaisesRegex(RuntimeError, "snapshot write failure"):
                    snapshot.apply()
            self.assertTrue(is_fast())
        finally:
            _active.reset(token)
        self.assertEqual(cmds.getAttr(node.getFullName() + ".tx"), 0)
        cmds.undo()
        self.assertEqual(cmds.getAttr(node.getFullName() + ".tx"), 9)

    def test_curve_units_rational_periodic_and_undo(self):
        """CVのAPI番号・ウェイト・UI単位と、周期カーブの通常Undoを維持する。"""
        for unit in ("cm", "m", "in"):
            cmds.currentUnit(linear=unit)
            for kind in ("open", "periodic", "rational"):
                with self.subTest(unit=unit, kind=kind):
                    name = self.namespace + ":" + unit + "_" + kind
                    if kind == "periodic":
                        transform = cmds.circle(name=name, constructionHistory=False)[0]
                    elif kind == "rational":
                        transform = cmds.curve(name=name, degree=1, pointWeight=[(1, 2, 3, 2), (4, 5, 6, 3)])
                    else:
                        transform = cmds.curve(name=name, degree=1, point=[(1, 2, 3), (4, 5, 6)])
                    curve = mlib.getNode(transform).getShape()
                    snapshot = self.roundtrip(mlib.json.NurbsCurveSnapshot.capture(curve))
                    expected = [cmds.xform(cv.getFullName(), query=True, translation=True, objectSpace=True) for cv in curve.getCVs()]
                    self.assertEqual(snapshot.records[0]["positions"], expected)
                    weights = [p.w for p in curve.getCvPositions()]
                    cmds.xform(curve.getFullName() + ".cv[0]", translation=(7, 8, 9), objectSpace=True)
                    snapshot.apply()
                    actual = [cmds.xform(cv.getFullName(), query=True, translation=True, objectSpace=True) for cv in curve.getCVs()]
                    for actual_point, expected_point in zip(actual, expected):
                        for actual_value, expected_value in zip(actual_point, expected_point):
                            self.assertAlmostEqual(actual_value, expected_value)
                    self.assertEqual([p.w for p in curve.getCvPositions()], weights)
                    cmds.undo()
                    restored = cmds.xform(curve.getFullName() + ".cv[0]", query=True, translation=True, objectSpace=True)
                    for actual_value, expected_value in zip(restored, (7, 8, 9)):
                        self.assertAlmostEqual(actual_value, expected_value)

    def test_sdk_reference_queries_keep_conversion_and_weight_policy(self):
        """関係検索はweight駆動を除外し、保存探索は変換とweightのSDKも含める。"""
        from mlib.json.snapshots import _connections, _sdk_nodes
        drivers = [self.node(name=name) for name in ("a", "b", "weight", "driven")]
        for node in drivers:
            cmds.addAttr(node.getFullName(), longName="value", attributeType="double")
        curves = [self.node("animCurveUU", name) for name in ("curveA", "curveB", "curveWeight")]
        blend, conversion = self.node("blendWeighted", "blend"), self.node("unitConversion", "conversion")
        for driver, curve in zip(drivers, curves):
            cmds.connectAttr(driver.getFullName() + ".value", curve.getFullName() + ".input")
            cmds.setKeyframe(curve.getFullName(), float=0, value=0)
        cmds.connectAttr(curves[0].getFullName() + ".output", conversion.getFullName() + ".input")
        cmds.connectAttr(conversion.getFullName() + ".output", blend.getFullName() + ".input[7]")
        cmds.connectAttr(curves[1].getFullName() + ".output", blend.getFullName() + ".input[2]")
        cmds.connectAttr(curves[2].getFullName() + ".output", blend.getFullName() + ".weight[7]")
        cmds.connectAttr(blend.getFullName() + ".output", drivers[3].getFullName() + ".value")
        found = mlib.common.DrivenKey.find(drivers[3].getPlug("value"))
        native = cmds.listConnections(blend.getFullName() + ".input", source=True, destination=False, skipConversionNodes=True) or []
        expected_drivers = [cmds.listConnections(name + ".input", source=True, destination=False, plugs=True)[0] for name in native]
        self.assertEqual([r.getDriverPlug().getFullName() for r in found], [mlib.getPlug(name).getFullName() for name in expected_drivers])
        self.assertEqual(set(_sdk_nodes([drivers[3]])), set(curves + [blend, conversion]))
        for node in curves + [blend, conversion]:
            raw = cmds.listConnections(node.getFullName(), source=True, destination=True, connections=True, plugs=True) or []
            expected = [(mlib.json.PlugRef.capture(raw[i]), mlib.json.PlugRef.capture(raw[i + 1])) for i in range(0, len(raw), 2)]
            self.assertEqual(_connections(node), expected)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

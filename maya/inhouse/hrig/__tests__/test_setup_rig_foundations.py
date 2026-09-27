"""hrigから還元した基礎APIを独立したMayaシーンで検証する。"""

import math
import unittest
from maya import cmds
import hlib
from hrig.setups import ControlShape, SoftIK
from hlib.utils.scalarGraph import ScalarGraph
from hlib.nodes import Container
from hlib.general.units import Units


class RigFoundationsTest(unittest.TestCase):
    """所有、疎な参照配列、形状、数値と単位の契約を確認する。"""

    def setUp(self):
        """隔離シーンと単位を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True, infinity=True)

    def test_container_and_scalar_graph(self):
        """演算評価、動的ラッパー、改名と所有削除を確認する。"""
        owner = hlib.nodes.Container.create("owned")
        self.assertIsInstance(hlib.getNode(owner.full_name()), hlib.nodes.Container)
        source = hlib.createNode("transform", name="external")
        source.add_attr(long_name="value", attribute_type="double", default_value=3)
        graph = ScalarGraph(owner)
        total = graph.sum("sum", source.plug("value"), 2)
        product = graph.multiply("product", total, 4)
        chosen = graph.condition("pick", product, 15, product, 0)
        self.assertAlmostEqual(hlib.getPlug(chosen).get(), 20)
        owner.rename("renamed")
        self.assertEqual(len(owner.members()), 3)
        node = owner.create_node("multiplyDivide")
        self.assertIn(node.uuid(), [n.uuid() for n in owner.members()])
        cmds.undo()
        self.assertEqual(len(owner.members()), 3)
        hlib.delete(owner)
        self.assertTrue(source.is_valid())
        self.assertFalse(cmds.ls(type="multiplyDivide"))

    def test_sparse_messages(self):
        """穴のあるmessage配列を読み、末尾へ追加してUndoする。"""
        owner = hlib.createNode("network", name="refs")
        array = owner.add_attr(long_name="items", attribute_type="message", multi=True)
        first = hlib.createNode("transform", name="first")
        second = hlib.createNode("transform", name="second")
        first.plug("message").connect(owner.plug("items[3]"))
        second.plug("message").connect(owner.plug("items[7]"))
        self.assertEqual(list(array.source_nodes()), [3, 7])
        index = array.append_message(second)
        self.assertEqual(index, 8)
        second.rename("renamedSecond")
        self.assertEqual(array.source_nodes()[8].name(), "renamedSecond")
        cmds.undo()
        cmds.undo()
        self.assertEqual(list(array.source_nodes()), [3, 7])
        invalid = owner.add_attr(long_name="values", attribute_type="double", multi=True)
        with self.assertRaises(TypeError):
            invalid.append_message(first)

    def test_shape_undo_and_units(self):
        """形状追加は既存のTRSとシェイプを変更せず、m単位でも成立する。"""
        cmds.currentUnit(linear="m")
        target = hlib.createNode("joint", name="control")
        target.plug("tx").set(2)
        target.plug("rz").set(25)
        self.assertEqual(target.plug("tx").data_type(), "doubleLinear")
        self.assertEqual(target.plug("rz").data_type(), "doubleAngle")
        before = list(target.get_matrix())
        first = ControlShape.circle(target, radius=0.02)
        second = ControlShape.circle(target, radius=0.03, normal=(0, 1, 0))
        self.assertEqual(len(target.shapes()), 2)
        self.assertEqual(list(target.get_matrix()), before)
        cmds.undo()
        self.assertEqual(len(target.shapes()), 1)
        self.assertTrue(first[0].is_valid())
        self.assertFalse(second[0].is_valid())
        with self.assertRaises(ValueError):
            ControlShape.circle(target, normal=(0, 0, 0))
        self.assertEqual(len(target.shapes()), 1)

    def test_soft_distance(self):
        """標準DGの評価を数学的参照値と比較する。"""
        graph = hlib.getNode(SoftIK.create("soft", 8))
        for softness in (0, 1, 8):
            for distance in (0, 2, 7, 8, 12):
                graph.plug("distance").set(distance)
                graph.plug("softness").set(softness)
                self.assertAlmostEqual(
                    graph.plug("ratio").get() * distance,
                    SoftIK.distance(distance, 8, softness),
                    places=5,
                )
        with self.assertRaises(ValueError):
            SoftIK.distance(1, 0, 0)

    def test_conversion(self):
        """距離・角度・FPSの変換はシーン単位を変更しない。"""
        cmds.currentUnit(linear="m", angle="rad", time="ntsc")
        self.assertEqual(Units.distance_to_ui(100), 1)
        self.assertEqual(Units.distance_from_ui(1), 100)
        self.assertAlmostEqual(Units.angle_to_ui(math.pi), math.pi)
        self.assertAlmostEqual(Units.angle_from_ui(math.pi), math.pi)
        self.assertAlmostEqual(Units.seconds_per_frame(), 1 / 30)
        self.assertEqual(Units.linear(), "m")
        self.assertEqual(Units.angle(), "rad")

    def test_skin_bind_and_copy(self):
        """スキンのバインド・近似転送・履歴照会を共通APIで行う。"""
        joint = hlib.createNode("joint", name="bone")
        source = cmds.polyCube(name="source", constructionHistory=False)[0]
        target = cmds.polyCube(name="target", constructionHistory=False)[0]
        skin = hlib.nodes.SkinCluster.bind(source, [joint])
        copied = hlib.nodes.SkinCluster.bind(target, [joint])
        self.assertTrue(skin.deforms(source))
        self.assertFalse(skin.deforms(target))
        skin.copy_weights_to(copied)
        self.assertAlmostEqual(
            cmds.skinPercent(
                copied.full_name(), target + ".vtx[0]", query=True, transform=joint.full_name()
            ),
            1,
        )
        with self.assertRaises(ValueError):
            hlib.nodes.SkinCluster.bind(source, [joint])
        with self.assertRaises(ValueError):
            skin.copy_weights_to(skin)

    def test_maya_compatible_values(self):
        """属性検索と表示単位は型付きPlugの取得規則と区別して維持する。"""

        node = hlib.createNode("transform", name="rawUnits")
        node.add_attr(long_name="marker", attribute_type="message")
        cmds.setAttr(node.full_name() + ".tx", 200)
        cmds.setAttr(node.full_name() + ".rz", 90)
        cmds.currentUnit(linear="m", angle="rad")
        self.assertAlmostEqual(hlib.getAttr(node.full_name() + ".tx"), 2)
        self.assertAlmostEqual(hlib.getAttr(node.full_name() + ".rz"), math.pi / 2)
        self.assertEqual(
            [p.node.uuid() for p in hlib.ls("*.marker", recursive=True)], [node.uuid()]
        )
        self.assertEqual([n.uuid() for n in hlib.ls(node.uuid(), long=True)], [node.uuid()])
        self.assertTrue(hlib.getAttr(node.full_name() + ".tx", settable=True))
        cmds.setAttr(node.full_name() + ".tx", lock=True)
        self.assertFalse(hlib.getAttr(node.full_name() + ".tx", settable=True))

    def test_maya_command_boundary_in_hrig(self):
        """指定した標準コマンドのみmaya.cmds直接使用を許可する。"""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "hrig"
        violations = []
        for path in root.rglob("*.py"):
            if "__tests__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    if any(
                        a.name in ("maya.mel", "maya.utils", "json") or "OpenMaya" in a.name
                        for a in item.names
                    ):
                        violations.append(str(path))
                elif isinstance(item, ast.ImportFrom):
                    if (
                        item.module in ("maya.mel", "maya.utils", "json")
                        or "OpenMaya" in (item.module or "")
                        or (
                            item.module in ("maya", "maya.api")
                            and any(
                                a.name in ("mel", "utils") or "OpenMaya" in a.name
                                for a in item.names
                            )
                        )
                    ):
                        violations.append(str(path))
                if (
                    isinstance(item, ast.Call)
                    and isinstance(item.func, ast.Attribute)
                    and isinstance(item.func.value, ast.Name)
                    and item.func.value.id == "cmds"
                    and item.func.attr
                    not in {
                        "parent",
                        "menu",
                        "about",
                        "listHistory",
                        "objExists",
                        "deleteUI",
                        "menuItem",
                        "keyframe",
                        "playbackOptions",
                        "listConnections",
                        "setKeyframe",
                        "currentTime",
                        "cutKey",
                        "listRelatives",
                    }
                ):
                    violations.append(str(path) + ":" + item.func.attr)
        self.assertEqual(violations, [])

    def test_editor_batch_guards(self):
        """GUIを持たない場合は親を返さず、エディター起動を明示的に拒否する。"""
        from hlib.general import MainWindow, NodeEditor, GraphEditor

        if not cmds.about(batch=True):
            self.skipTest("Batch-only contract")
        self.assertIsNone(MainWindow.name())
        self.assertIsNone(MainWindow.widget())
        for editor in (NodeEditor, GraphEditor):
            with self.assertRaises(RuntimeError):
                editor.show()

    def test_plain_json_compatibility(self):
        """既存属性の通常JSONを外枠なしで保存・復元し、型付き形式と分離する。"""
        import json

        data = {"name": "腕", "restLengths": [4.0, 3.5], "enabled": True, "optional": None}
        text = hlib.json.JsonText.dumps(data)
        self.assertEqual(text, json.dumps(data))
        self.assertEqual(hlib.json.JsonText.loads(json.dumps(data)), data)
        self.assertEqual(json.loads(text), data)
        self.assertEqual(hlib.json.JsonText.loads(b"[1, 2]"), [1, 2])
        self.assertIn("腕", hlib.json.JsonText.dumps(data, ensure_ascii=False))
        with self.assertRaises(ValueError):
            hlib.json.JsonText.loads("{")
        with self.assertRaises(ValueError):
            hlib.json.JsonText.dumps(float("nan"), allow_nan=False)
        self.assertEqual(hlib.json.loads(hlib.json.dumps(data)), data)
        self.assertEqual(json.loads(hlib.json.dumps(data))["format"], "hlib.json")

    def test_typed_commands_and_rename(self):
        """生成・検索・接続・属性の戻り値を型付き参照で保持し、改名へ追従する。"""
        polygon = hlib.createPolygon(type="cube", name="typedMesh")
        self.assertIsInstance(polygon, hlib.nodes.Mesh)
        mesh = polygon.transform()
        history = next(
            node
            for node in [hlib.getNode(value) for value in (cmds.listHistory(polygon) or [])]
            if node.type() == "polyCube"
        )
        self.assertIsInstance(mesh, hlib.nodes.Transform)
        self.assertEqual(history.type(), "polyCube")
        shape = [
            hlib.getNode(value)
            for value in (cmds.listRelatives(mesh, shapes=True, fullPath=True) or [])
        ][0]
        self.assertEqual(shape.type(), "mesh")
        marker = hlib.addAttr(mesh, longName="marker", attributeType="double", defaultValue=2)
        self.assertIsInstance(marker, hlib.plugs.Plug)
        self.assertEqual(hlib.getAttr(marker), 2)
        self.assertIsInstance(hlib.getAttr(mesh.plug("translate")), hlib.maths.Vector)
        self.assertIsInstance(hlib.getAttr(mesh.plug("worldMatrix[0]")), hlib.maths.Matrix)
        owner = hlib.createSet(mesh, name="typedSet")
        self.assertIsInstance(owner, hlib.nodes.ObjectSet)
        self.assertEqual(owner.members()[0].uuid(), mesh.uuid())
        target = hlib.createNode("transform", name="typedTarget")
        constraint = hlib.addConstraint(mesh, target, maintainOffset=True)
        self.assertIsInstance(constraint, hlib.nodes.ParentConstraint)
        weight = constraint.weight_plugs()[0]
        self.assertIsInstance(weight, hlib.plugs.Plug)
        self.assertEqual(constraint.targets()[0].uuid(), mesh.uuid())
        pairs = [
            hlib.getPlug(value)
            for value in (
                cmds.listConnections(target.plug("tx"), s=True, d=False, p=True, c=True) or []
            )
        ]
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(isinstance(p, hlib.plugs.Plug) for p in pairs))
        mesh.rename("renamedTypedMesh")
        self.assertEqual(marker.node.name(), "renamedTypedMesh")
        self.assertEqual(
            [hlib.getNode(value) for value in (cmds.listRelatives(shape, parent=True) or [])][
                0
            ].uuid(),
            mesh.uuid(),
        )
        with self.assertRaises(TypeError):
            hlib.executeDeferred("print('not accepted')")

    def test_standard_curve_commands(self):
        """円・カーブを型付き参照で生成し、短縮フラグ・照会・Undoを検証する。"""
        shape = hlib.createNurbs(type="circle", n="typedCircle", r=2.5, ch=True)
        self.assertIsInstance(shape, hlib.nodes.NurbsCurve)
        transform = shape.transform()
        history = next(
            node
            for node in [hlib.getNode(value) for value in (cmds.listHistory(shape) or [])]
            if node.type() == "makeNurbCircle"
        )
        self.assertIsInstance(transform, hlib.nodes.Transform)
        self.assertAlmostEqual(history.plug("radius").get(), 2.5)
        curve = hlib.createCurve(d=1, p=[(0, 0, 0), (2, 0, 0)], n="typedCurve")
        self.assertIsInstance(curve, hlib.nodes.Transform)
        name = curve.full_name()
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertTrue(cmds.objExists(name))

    def test_general_layout(self):
        """各実装がgeneralに一つだけ存在し、選択入口も新クラスを返す。"""
        from pathlib import Path
        from hlib.general import Units, Workspace, Selection

        for cls, module in ((Units, "units"), (Workspace, "workspace"), (Selection, "selection")):
            self.assertEqual(cls.__module__, "hlib.general." + module)
            self.assertFalse((Path(hlib.__file__).parent / (module + ".py")).exists())
        self.assertIsInstance(hlib.captureSelection(), Selection)

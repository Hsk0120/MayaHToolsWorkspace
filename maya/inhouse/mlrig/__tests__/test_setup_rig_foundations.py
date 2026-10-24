"""mlrigから還元した基礎APIを独立したMayaシーンで検証する。"""

import math
import unittest
from maya import cmds
import mlib
from mlrig.setups import ControlShape, SoftIK
from mlib.common.scalarGraph import ScalarGraph
from mlib.nodes import Container
from mlib.common import units
from mlib.decorator import nativeUnits


class RigFoundationsTest(unittest.TestCase):
    """所有、疎な参照配列、形状、数値と単位の契約を確認する。"""

    def setUp(self):
        """隔離シーンと単位を初期化する。"""
        cmds.file(new=True, force=True)
        cmds.currentUnit(linear="cm", angle="deg", time="film")
        cmds.undoInfo(state=True, infinity=True)

    def test_container_and_scalar_graph(self):
        """演算評価、動的ラッパー、改名と所有削除を確認する。"""
        owner = mlib.nodes.Container.create("owned")
        self.assertIsInstance(mlib.getNode(owner.getFullName()), mlib.nodes.Container)
        source = mlib.createNode("transform", name="external")
        source.addAttr(longName="value", attributeType="double", defaultValue=3)
        graph = ScalarGraph(owner)
        total = graph.sum("sum", source.getPlug("value"), 2)
        product = graph.multiply("product", total, 4)
        chosen = graph.condition("pick", product, 15, product, 0)
        self.assertAlmostEqual(mlib.getPlug(chosen).get(), 20)
        owner.rename("renamed")
        self.assertEqual(len(owner.getMembers()), 3)
        node = owner.createNode("multiplyDivide")
        self.assertIn(node.getUuid(), [n.getUuid() for n in owner.getMembers()])
        cmds.undo()
        self.assertEqual(len(owner.getMembers()), 3)
        mlib.delete(owner)
        self.assertTrue(source.isValid())
        self.assertFalse(cmds.ls(type="multiplyDivide"))

    def test_sparse_messages(self):
        """穴のあるmessage配列を読み、末尾へ追加してUndoする。"""
        owner = mlib.createNode("network", name="refs")
        array = owner.addAttr(longName="items", attributeType="message", multi=True)
        first = mlib.createNode("transform", name="first")
        second = mlib.createNode("transform", name="second")
        first.getPlug("message").connectTo(owner.getPlug("items[3]"))
        second.getPlug("message").connectTo(owner.getPlug("items[7]"))
        self.assertEqual(list(array.getSourceNodes()), [3, 7])
        index = array.appendMessage(second)
        self.assertEqual(index, 8)
        second.rename("renamedSecond")
        self.assertEqual(array.getSourceNodes()[8].getName(), "renamedSecond")
        cmds.undo()
        cmds.undo()
        self.assertEqual(list(array.getSourceNodes()), [3, 7])
        invalid = owner.addAttr(longName="values", attributeType="double", multi=True)
        with self.assertRaises(TypeError):
            invalid.appendMessage(first)

    def test_shape_undo_and_units(self):
        """形状追加は既存のTRSとシェイプを変更せず、m単位でも成立する。"""
        cmds.currentUnit(linear="m")
        target = mlib.createNode("joint", name="control")
        target.getPlug("tx").set(2)
        target.getPlug("rz").set(math.radians(25))
        self.assertEqual(target.getPlug("tx").getDataType(), "doubleLinear")
        self.assertEqual(target.getPlug("rz").getDataType(), "doubleAngle")
        before = list(target.getMatrix())
        first = ControlShape.circle(target, radius=0.02)
        second = ControlShape.circle(target, radius=0.03, normal=(0, 1, 0))
        self.assertEqual(len(target.getShapes()), 2)
        self.assertEqual(list(target.getMatrix()), before)
        cmds.undo()
        self.assertEqual(len(target.getShapes()), 1)
        self.assertTrue(first[0].isValid())
        self.assertFalse(second[0].isValid())
        with self.assertRaises(ValueError):
            ControlShape.circle(target, normal=(0, 0, 0))
        self.assertEqual(len(target.getShapes()), 1)

    def test_soft_distance(self):
        """標準DGの評価を数学的参照値と比較する。"""
        graph = mlib.getNode(SoftIK.create("soft", 8))
        for softness in (0, 1, 8):
            for distance in (0, 2, 7, 8, 12):
                graph.getPlug("distance").set(distance)
                graph.getPlug("softness").set(softness)
                self.assertAlmostEqual(
                    graph.getPlug("ratio").get() * distance,
                    SoftIK.distance(distance, 8, softness),
                    places=5,
                )
        with self.assertRaises(ValueError):
            SoftIK.distance(1, 0, 0)

    def test_conversion(self):
        """距離・角度・FPSの変換はシーン単位を変更しない。"""
        cmds.currentUnit(linear="m", angle="rad", time="ntsc")
        self.assertEqual(units.distanceToUi(100), 1)
        self.assertEqual(units.distanceFromUi(1), 100)
        self.assertAlmostEqual(units.angleToUi(math.pi), math.pi)
        self.assertAlmostEqual(units.angleFromUi(math.pi), math.pi)
        self.assertAlmostEqual(units.secondsPerFrame(), 1 / 30)
        self.assertEqual(cmds.currentUnit(query=True, linear=True), "m")
        self.assertEqual(cmds.currentUnit(query=True, angle=True), "rad")
        self.assertEqual(cmds.currentUnit(query=True, time=True), "ntsc")

    def test_skin_bind_and_copy(self):
        """スキンのバインド・近似転送・履歴照会を共通APIで行う。"""
        joint = mlib.createNode("joint", name="bone")
        source = cmds.polyCube(name="source", constructionHistory=False)[0]
        target = cmds.polyCube(name="target", constructionHistory=False)[0]
        skin = mlib.nodes.SkinCluster.bind(source, [joint])
        copied = mlib.nodes.SkinCluster.bind(target, [joint])
        self.assertTrue(skin.deforms(source))
        self.assertFalse(skin.deforms(target))
        skin.copyWeightsTo(copied)
        self.assertAlmostEqual(
            cmds.skinPercent(
                copied.getFullName(), target + ".vtx[0]", query=True, transform=joint.getFullName()
            ),
            1,
        )
        with self.assertRaises(ValueError):
            mlib.nodes.SkinCluster.bind(source, [joint])
        with self.assertRaises(ValueError):
            skin.copyWeightsTo(skin)

    def test_maya_compatible_values(self):
        """アトリビュート参照を取得し、UI単位と固定単位を明示して読み分ける。"""

        node = mlib.createNode("transform", name="rawUnits")
        node.addAttr(longName="marker", attributeType="message")
        cmds.setAttr(node.getFullName() + ".tx", 200)
        cmds.setAttr(node.getFullName() + ".rz", 90)
        rotation = mlib.getPlug(node.getFullName() + ".rz")
        self.assertIsInstance(rotation, mlib.plugs.Plug)
        self.assertAlmostEqual(rotation.get(uiUnits=True), 90)
        self.assertAlmostEqual(rotation.get(), math.pi / 2)
        cmds.currentUnit(linear="m", angle="rad")
        translation = mlib.getPlug(node.getFullName() + ".tx")
        self.assertAlmostEqual(translation.get(uiUnits=True), 2)
        self.assertAlmostEqual(translation.get(), 200)
        self.assertAlmostEqual(rotation.get(uiUnits=True), math.pi / 2)
        self.assertEqual(
            [p.getNode().getUuid() for p in mlib.ls("*.marker", recursive=True)], [node.getUuid()]
        )
        self.assertEqual([n.getUuid() for n in mlib.ls(node.getUuid(), long=True)], [node.getUuid()])
        self.assertTrue(node.getPlug("tx").isSettable())
        cmds.setAttr(node.getFullName() + ".tx", lock=True)
        self.assertFalse(node.getPlug("tx").isSettable())

    def test_maya_command_boundary_in_mlrig(self):
        """標準照会と利用箇所を限定した生成・UI処理だけcmds直接使用を許可する。"""
        import ast
        from pathlib import Path

        root = Path(__file__).resolve().parents[2] / "mlrig"
        # 廃止したコマンドラッパーの代替は、実際の使用ファイルに限定する。
        direct_commands = {
            "channel_controls.py": {"reorder"},
            "bendLayer.py": {"sets"},
            "drivenLayer.py": {"sets"},
            "limb.py": {"sets", "ikHandle"},
            "reverse_foot.py": {"sets"},
            "spaceLayer.py": {"sets"},
            "twistLayer.py": {"sets"},
            "examples/humanoid.py": {
                "polyCube", "polySphere", "polyCylinder", "mirrorJoint", "shadingNode", "sets",
            },
            "examples/limb_demo.py": {"polyCube", "makeIdentity"},
            "setups/coneReader.py": {"curve"},
            "setups/controlShape.py": {"circle", "curve"},
            "setups/splineIK.py": {"curve", "ikHandle"},
            # Rotate Plane IK・自由度・優先角度・ポールベクター・回転の受け渡しは mlib に入口が無い Maya 標準の操作。
            "setups/hingeIK.py": {"ikHandle", "joint", "spaceLocator", "poleVectorConstraint"},
            "setups/planarIK.py": {"joint", "orientConstraint"},
        }
        violations = []
        for path in root.rglob("*.py"):
            if "__tests__" in path.parts:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
            for item in ast.walk(tree):
                if isinstance(item, ast.Import):
                    if any(
                        a.name == "maya.utils" or "OpenMaya" in a.name
                        for a in item.names
                    ):
                        violations.append(str(path))
                elif isinstance(item, ast.ImportFrom):
                    if (
                        item.module == "maya.utils"
                        or "OpenMaya" in (item.module or "")
                        or (
                            item.module in ("maya", "maya.api")
                            and any(
                                a.name == "utils" or "OpenMaya" in a.name
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
                    } | direct_commands.get(path.relative_to(root).as_posix(), set())
                ):
                    violations.append(str(path) + ":" + item.func.attr)
        self.assertEqual(violations, [])

    def test_menu_batch_guard(self):
        """GUIを持たない場合、mlrigのメニューを作成しない。"""
        from mlrig.menu import Menu

        if not cmds.about(batch=True):
            self.skipTest("Batch-only contract")
        self.assertIsNone(Menu.install())

    def test_plain_json_compatibility(self):
        """ControlRigが通常JSONを保存し、既存の通常JSONから機能種別を読む。"""
        import json
        from mlrig.controlRig import ControlRig

        rig = ControlRig._create("jsonControl", "aim")
        definition = rig.root.getPlug("mlrigControlDefinition")
        self.assertEqual(json.loads(definition.get()), {"kind": "aim"})
        self.assertEqual(ControlRig(rig.root).kind(), "aim")
        definition.set(json.dumps({"kind": "finger", "label": "腕"}, ensure_ascii=False))
        self.assertEqual(ControlRig(rig.root).kind(), "finger")
        definition.set("{")
        with self.assertRaises(ValueError):
            ControlRig(rig.root).kind()

    def test_typed_commands_and_rename(self):
        """生成・検索・接続・属性の戻り値を型付き参照で保持し、改名へ追従する。"""
        polygon = mlib.getNode(cmds.polyCube(name="typedMesh")[0]).getShape()
        self.assertIsInstance(polygon, mlib.nodes.Mesh)
        mesh = polygon.getTransform()
        history = next(
            node
            for node in [mlib.getNode(value) for value in (cmds.listHistory(polygon) or [])]
            if node.getType() == "polyCube"
        )
        self.assertIsInstance(mesh, mlib.nodes.Transform)
        self.assertEqual(history.getType(), "polyCube")
        shape = [
            mlib.getNode(value)
            for value in (cmds.listRelatives(mesh, shapes=True, fullPath=True) or [])
        ][0]
        self.assertEqual(shape.getType(), "mesh")
        marker = mesh.addAttr(longName="marker", attributeType="double", defaultValue=2)
        self.assertIsInstance(marker, mlib.plugs.Plug)
        self.assertEqual(mlib.getPlug(marker).get(uiUnits=True), 2)
        self.assertIsInstance(mlib.getPlug(mesh.getPlug("translate")).get(), mlib.maths.Vector)
        self.assertIsInstance(mlib.getPlug(mesh.getPlug("worldMatrix[0]")).get(), mlib.maths.Matrix)
        owner = mlib.getNode(cmds.sets(mesh.getFullName(), name="typedSet"))
        self.assertIsInstance(owner, mlib.nodes.ObjectSet)
        self.assertEqual(owner.getMembers()[0].getUuid(), mesh.getUuid())
        target = mlib.createNode("transform", name="typedTarget")
        constraint = target.addConstraint(mesh, maintainOffset=True)
        self.assertIsInstance(constraint, mlib.nodes.ParentConstraint)
        weight = constraint.getWeightPlugs()[0]
        self.assertIsInstance(weight, mlib.plugs.Plug)
        self.assertEqual(constraint.getTargets()[0].getUuid(), mesh.getUuid())
        pairs = [
            mlib.getPlug(value)
            for value in (
                cmds.listConnections(target.getPlug("tx"), s=True, d=False, p=True, c=True) or []
            )
        ]
        self.assertEqual(len(pairs), 2)
        self.assertTrue(all(isinstance(p, mlib.plugs.Plug) for p in pairs))
        mesh.rename("renamedTypedMesh")
        self.assertEqual(marker.getNode().getName(), "renamedTypedMesh")
        self.assertEqual(
            [mlib.getNode(value) for value in (cmds.listRelatives(shape, parent=True) or [])][
                0
            ].getUuid(),
            mesh.getUuid(),
        )
        with self.assertRaises(TypeError):
            mlib.common.Deferred.call("print('not accepted')")

    def test_standard_curve_commands(self):
        """円・カーブを型付き参照で生成し、短縮フラグ・照会・Undoを検証する。"""
        shape = mlib.getNode(cmds.circle(n="typedCircle", r=2.5, ch=True)[0]).getShape()
        self.assertIsInstance(shape, mlib.nodes.NurbsCurve)
        transform = shape.getTransform()
        history = next(
            node
            for node in [mlib.getNode(value) for value in (cmds.listHistory(shape) or [])]
            if node.getType() == "makeNurbCircle"
        )
        self.assertIsInstance(transform, mlib.nodes.Transform)
        self.assertAlmostEqual(history.getPlug("radius").get(), 2.5)
        curve = mlib.getNode(cmds.curve(d=1, p=[(0, 0, 0), (2, 0, 0)], n="typedCurve"))
        self.assertIsInstance(curve, mlib.nodes.Transform)
        name = curve.getFullName()
        cmds.undo()
        self.assertFalse(cmds.objExists(name))
        cmds.redo()
        self.assertTrue(cmds.objExists(name))

    def test_package_layout(self):
        """各実装が用途別パッケージに一つだけ存在し、選択入口も新クラスを返す。"""
        from pathlib import Path
        from mlib.common import Selection

        self.assertEqual(Selection.__module__, "mlib.common.selection")
        self.assertFalse((Path(mlib.__file__).parent / "selection.py").exists())
        self.assertIsInstance(Selection.capture(), Selection)

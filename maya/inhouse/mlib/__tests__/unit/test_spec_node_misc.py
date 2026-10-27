"""Reference・Container・DagPose・マテリアル系・Constraint・AnimCurve の参照の少ないAPIの約束を固定する(担当C)。

対象: Reference.mfn・getFilename の引数・isFromReferencedFile、Container の公開名
(publishName・bindAttr・unbindAttr・unpublishName)と removeContainer、DagPose.getNotAtPose・getMemberIndices、
ShadingEngine.getShaderPlug、Node.getAssignedObjects・getMaterials、File のパスと色空間、
Texture2d.getPlacement、Place2dTexture.connectTexture、Constraint.getWeightAliases、AnimCurve.isTimeInput。
"""

import os
import shutil
import tempfile
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.components import Face
from mlib.nodes import Container, DagPose, File, Node, Place2dTexture, Reference
from mlib.plugs import Plug
from support.specCase import NamespaceCase


class _SpecCase(NamespaceCase):
    """このテストファイルの名前空間の先頭と、共通基底からの差分。"""

    PREFIX = "mlibSpecNodeMisc_"
    CLEAR_SELECTION = True


class ReferenceSpecTest(unittest.TestCase):
    """同じファイルを2回参照し、コピー番号付きの参照を作る。開いているシーンは new しない。"""

    def setUp(self):
        self.tmp_dir = tempfile.mkdtemp()
        self.path = os.path.join(self.tmp_dir, "mlibSpecCRef.ma").replace("\\", "/")
        helper = cmds.createNode("transform", name="mlibSpecCRefHelper")
        cmds.select(helper, replace=True)
        cmds.file(self.path, exportSelected=True, type="mayaAscii", force=True)
        cmds.delete(helper)
        cmds.select(clear=True)
        tag = uuid.uuid4().hex[:8]
        self.namespaces = ["mlibSpecCRefA_" + tag, "mlibSpecCRefB_" + tag]
        for namespace in self.namespaces:
            cmds.file(self.path, reference=True, namespace=namespace)
        self.refs = [cmds.referenceQuery(namespace + ":mlibSpecCRefHelper", referenceNode=True)
                     for namespace in self.namespaces]

    def tearDown(self):
        for ref in self.refs:
            if cmds.objExists(ref):
                cmds.file(removeReference=True, referenceNode=ref)
        shutil.rmtree(self.tmp_dir, ignore_errors=True)

    def test_reference_fn(self):
        """mfn は自身の MFnReference。"""
        fn = Node(self.refs[0]).mfn()
        self.assertIsInstance(fn, om2.MFnReference)
        self.assertEqual(fn.name(), self.refs[0])

    def test_get_filename_default_and_unresolved(self):
        """既定はコピー番号の無い解決済みの完全パス。resolved=False も同じファイル(パス変数なし)。"""
        second = Node(self.refs[1])
        self.assertIsInstance(second, Reference)
        self.assertEqual(second.getFilename(),
                         cmds.referenceQuery(self.refs[1], filename=True, withoutCopyNumber=True))
        self.assertEqual(second.getFilename(resolved=False), self.path)

    def test_get_filename_with_copy_number(self):
        """withCopyNumber=True は referenceQuery(filename=True) と同じ完全パスで、2つ目以降に {1} 等が付く。

        フラグは MFnReference.fileName の3番目の引数へ渡す。
        """
        expected = cmds.referenceQuery(self.refs[1], filename=True)
        self.assertTrue(expected.endswith("{1}"))
        self.assertEqual(Node(self.refs[1]).getFilename(withCopyNumber=True), expected)
        self.assertEqual(Node(self.refs[1]).getFilename(withCopyNumber=True), self.path + "{1}")
        first = Node(self.refs[0]).getFilename(withCopyNumber=True)
        self.assertEqual(first, cmds.referenceQuery(self.refs[0], filename=True))
        self.assertEqual(first, self.path)

    def test_from_referenced_file_and_edit_filters(self):
        """参照内のノードは isFromReferencedFile=True。成功した編集だけが既定で返り、失敗の指定では空。"""
        content = Node(self.namespaces[0] + ":mlibSpecCRefHelper")
        self.assertTrue(content.isFromReferencedFile())
        self.assertFalse(Node(self.refs[0]).isFromReferencedFile())
        cmds.setAttr(content.getFullName() + ".translateX", 3)
        reference = Node(self.refs[0])
        self.assertEqual(len(reference.getEditStrings()), 1)
        self.assertEqual(reference.getEditStrings(successful=False, failed=True), [])
        self.assertEqual(reference.getEditAttrNames(successful=False), [])
        self.assertEqual(Node(self.refs[1]).getEditNodeNames(), [])


class ContainerPublishTest(_SpecCase):
    """公開名の作成・Bind・解除・削除と removeContainer。"""

    def setUp(self):
        super().setUp()
        self.container = Container.create(self.name("box"))
        self.member = Node(cmds.createNode("multiplyDivide", name=self.name("md"), skipSelect=True))
        self.outside = Node(cmds.createNode("transform", name=self.name("outside"), skipSelect=True))
        self.container.addMembers(self.member)

    def test_publish_bind_unbind_unpublish(self):
        """未 Bind の公開名を作り、Bind・解除・削除の順に状態が変わる。"""
        self.assertEqual(self.container.publishName("inX"), "inX")
        self.assertEqual(self.container.getPublishedAttrs(), {"inX": None})
        plug = self.container.bindAttr("inX", self.member.getPlug("input1X"))
        self.assertIsInstance(plug, Plug)
        self.assertEqual(self.container.getPublishedAttrs()["inX"].getFullName(), self.member.getName() + ".input1X")
        self.assertIsNone(self.container.unbindAttr("inX"))
        self.assertEqual(self.container.getPublishedAttrs(), {"inX": None})
        self.assertIsNone(self.container.unpublishName("inX"))
        self.assertEqual(self.container.getPublishedAttrs(), {})

    def test_bind_by_name(self):
        """bindAttr は名前の Plug も受ける。"""
        self.container.publishName("inY")
        self.assertEqual(self.container.bindAttr("inY", self.member.getName() + ".input1Y").getFullName(),
                         self.member.getName() + ".input1Y")

    def test_errors(self):
        """重複の公開・Bind 済みや無い名前の Bind・未 Bind の解除・Bind 済みの削除・非メンバーは ValueError。"""
        self.container.publishName("inX")
        with self.assertRaises(ValueError):
            self.container.publishName("inX")
        with self.assertRaises(ValueError):
            self.container.bindAttr("missing", self.member.getPlug("input1X"))
        with self.assertRaises(ValueError):
            self.container.bindAttr("inX", self.outside.getPlug("tx"))
        with self.assertRaises(ValueError):
            self.container.unbindAttr("inX")
        self.container.bindAttr("inX", self.member.getPlug("input1X"))
        with self.assertRaises(ValueError):
            self.container.bindAttr("inX", self.member.getPlug("input1Y"))
        with self.assertRaises(ValueError):
            self.container.unpublishName("inX")
        self.assertEqual(list(self.container.getPublishedAttrs()), ["inX"])

    def test_publish_undo(self):
        """publishName は1回の Undo で取り消せる。"""
        cmds.flushUndo()
        self.container.publishName("undoMe")
        cmds.undo()
        self.assertEqual(self.container.getPublishedAttrs(), {})

    def test_remove_container_keeps_members(self):
        """removeContainer はメンバーを残して自身を消し、None を返す。1回の Undo で戻る。"""
        cmds.flushUndo()
        self.assertIsNone(self.container.removeContainer())
        self.assertFalse(self.container.isValid())
        self.assertTrue(self.member.isValid())
        cmds.undo()
        restored = Node(self.name("box"))
        self.assertEqual(restored.getMembers(), [self.member])


class DagPoseSpecTest(_SpecCase):
    """getNotAtPose・isAtPose・getMemberIndices。"""

    def setUp(self):
        super().setUp()
        self.a = cmds.joint(name=self.name("a"))
        self.b = cmds.joint(name=self.name("b"), position=(1, 0, 0))
        cmds.select(clear=True)
        self.pose = cmds.dagPose(self.a, self.b, save=True, name=self.name("pose"))
        self.node = Node(self.pose)

    def test_not_at_pose(self):
        """保存姿勢と違うメンバーだけを返し、isAtPose はその空判定。"""
        self.assertIsInstance(self.node, DagPose)
        self.assertEqual(self.node.getNotAtPose(), [])
        self.assertTrue(self.node.isAtPose())
        cmds.setAttr(self.b + ".rotateZ", 30)
        self.assertEqual(self.node.getNotAtPose(), [Node(self.b)])
        self.assertFalse(self.node.isAtPose())

    def test_member_indices_skip_disconnected(self):
        """切断した要素の番号は除き、残りの番号は詰めない。"""
        self.assertEqual(self.node.getMemberIndices(), [0, 1])
        self.assertTrue(cmds.isConnected(self.a + ".message", self.pose + ".members[0]"))
        cmds.disconnectAttr(self.a + ".message", self.pose + ".members[0]")
        self.assertEqual(self.node.getMemberIndices(), [1])
        self.assertEqual(self.node.getMembers(), [Node(self.b)])

    def test_deleted_pose(self):
        """削除済みのポーズは RuntimeError。"""
        cmds.delete(self.pose)
        for method in ("getMemberIndices", "getNotAtPose", "isAtPose"):
            with self.subTest(method=method):
                with self.assertRaisesRegex(RuntimeError, "invalid dagPose"):
                    getattr(self.node, method)()


class MaterialTest(_SpecCase):
    """ShadingEngine.getShaderPlug と、マテリアル・割り当ての照会。"""

    def setUp(self):
        super().setUp()
        self.cube = cmds.polyCube(name=self.name("cube"))[0]
        self.material = cmds.shadingNode("lambert", asShader=True, name=self.name("mat"))
        self.group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=self.name("matSG"))
        cmds.connectAttr(self.material + ".outColor", self.group + ".surfaceShader")
        cmds.sets(self.cube, edit=True, forceElement=self.group)

    def test_shader_plug(self):
        """接続元の出力 Plug、未接続は None、不正な種類は ValueError。"""
        group = Node(self.group)
        self.assertEqual(group.getShaderPlug().getFullName(), self.material + ".outColor")
        self.assertIsNone(group.getShaderPlug("volume"))
        self.assertIsNone(group.getShaderPlug("displacement"))
        with self.assertRaisesRegex(ValueError, "kind must be"):
            group.getShaderPlug("light")
        empty = cmds.sets(renderable=True, noSurfaceShader=True, empty=True, name=self.name("emptySG"))
        self.assertIsNone(Node(empty).getShaderPlug())

    @staticmethod
    def assigned(node):
        """node に繋がる ShadingEngine の割り当て先を保持順に集める。"""
        return [member for engine in node.getShadingEngines() for member in engine.getMembers()]

    @staticmethod
    def materials(node):
        """node に繋がる ShadingEngine のサーフェスシェーダーを重複なしで集める。"""
        result = []
        for engine in node.getShadingEngines():
            shader = engine.getShader()
            if shader is not None and shader not in result:
                result.append(shader)
        return result

    def test_assigned_objects_and_materials(self):
        """割り当て先は ShadingEngine.getMembers()、マテリアルは getShader() を getShadingEngines() ごとに集める。"""
        shape = Node(self.cube).getShape()
        self.assertEqual(self.assigned(Node(self.material)), [shape])
        self.assertEqual(self.materials(shape), [Node(self.material)])

    def test_face_assignment(self):
        """フェース単位の割り当てでは Face を返し、Shape のマテリアルは重複なしで両方。"""
        cmds.sets(self.cube + ".f[0]", edit=True, forceElement="initialShadingGroup")
        assigned = self.assigned(Node(self.material))
        self.assertTrue(assigned)
        self.assertTrue(all(isinstance(item, Face) for item in assigned))
        materials = self.materials(Node(self.cube).getShape())
        self.assertIn(Node(self.material), materials)
        self.assertEqual(len(materials), 2)


class TextureTest(_SpecCase):
    """File・Texture2d・Place2dTexture。"""

    def setUp(self):
        super().setUp()
        self.file = Node(cmds.shadingNode("file", asTexture=True, name=self.name("tex")))
        self.place = Node(cmds.shadingNode("place2dTexture", asUtility=True, name=self.name("place")))

    def test_file_path(self):
        """トークンを展開せずに保持し、文字列以外は TypeError。1回の Undo で戻る。"""
        self.assertIsInstance(self.file, File)
        self.assertEqual(self.file.getFilePath(), "")
        cmds.flushUndo()
        self.assertIs(self.file.setFilePath("C:/textures/a.<UDIM>.png"), self.file)
        self.assertEqual(self.file.getFilePath(), "C:/textures/a.<UDIM>.png")
        cmds.undo()
        self.assertEqual(self.file.getFilePath(), "")
        with self.assertRaisesRegex(TypeError, "path must be a string"):
            self.file.setFilePath(5)

    def test_color_space(self):
        """色空間名を設定・取得する。名前は検証せずに保存し、str 以外は何も変えず TypeError。
        """
        self.assertEqual(self.file.getColorSpace(), cmds.getAttr(self.file.getName() + ".colorSpace"))
        self.assertIs(self.file.setColorSpace("Raw"), self.file)
        self.assertEqual(self.file.getColorSpace(), "Raw")
        self.file.setColorSpace("mlibNoSuchColorSpace")
        self.assertEqual(self.file.getColorSpace(), "mlibNoSuchColorSpace")
        for value in (5, None, b"Raw", ["Raw"]):
            with self.assertRaises(TypeError):
                self.file.setColorSpace(value)
            self.assertEqual(self.file.getColorSpace(), "mlibNoSuchColorSpace")

    def test_connect_texture_and_placement(self):
        """標準の配置アトリビュートをつなぎ、getPlacement はその配置ノード。同じ接続の繰り返しは何もしない。"""
        self.assertIsNone(self.file.getPlacement())
        self.assertIsInstance(self.place, Place2dTexture)
        self.assertIs(self.place.connectTexture(self.file), self.place)
        self.assertEqual(self.file.getPlacement(), self.place)
        self.assertEqual(cmds.listConnections(self.file.getName() + ".uvCoord", source=True, plugs=True),
                         [self.place.getName() + ".outUV"])
        count = len(cmds.listConnections(self.place.getName(), source=False, destination=True) or [])
        self.place.connectTexture(self.file)
        self.assertEqual(len(cmds.listConnections(self.place.getName(), source=False, destination=True) or []), count)

    def test_connect_texture_force_and_errors(self):
        """別の配置ノードからは force=True で置き換え、既定は RuntimeError。Texture2d 以外は TypeError。"""
        self.place.connectTexture(self.file)
        other = Node(cmds.shadingNode("place2dTexture", asUtility=True, name=self.name("other")))
        with self.assertRaises(RuntimeError):
            other.connectTexture(self.file)
        self.assertIs(other.connectTexture(self.file, f=True), other)
        self.assertEqual(self.file.getPlacement(), other)
        with self.assertRaisesRegex(TypeError, "Specify only one of 'force' and 'f'"):
            other.connectTexture(self.file, force=True, f=True)
        material = cmds.shadingNode("lambert", asShader=True, name=self.name("notTexture"))
        with self.assertRaisesRegex(TypeError, "texture must be Texture2d"):
            other.connectTexture(material)


class ConstraintAnimCurveTest(_SpecCase):
    """Constraint.getWeightAliases と AnimCurve.isTimeInput。"""

    def test_weight_aliases(self):
        """getTargets と同じ順の weight 名。ノードの aliasAttr を列挙する getAliases とは別。"""
        first = cmds.createNode("transform", name=self.name("first"), skipSelect=True)
        second = cmds.createNode("transform", name=self.name("second"), skipSelect=True)
        driven = cmds.createNode("transform", name=self.name("driven"), skipSelect=True)
        constraint = cmds.parentConstraint(first, second, driven)[0]
        node = Node(constraint)
        aliases = node.getWeightAliases()
        self.assertEqual(aliases, cmds.parentConstraint(constraint, query=True, weightAliasList=True))
        self.assertEqual(len(aliases), 2)
        self.assertEqual([target.getName() for target in node.getTargets()], [first, second])
        # parentConstraint の weight は aliasAttr ではなく動的アトリビュートなので、getAliases には出ない。
        self.assertTrue(all(node.hasAttr(alias) for alias in aliases))
        self.assertEqual([plug.getFullName().split(".")[-1] for plug in node.getWeightPlugs()], aliases)

    def test_is_time_input(self):
        """横軸が時間の T 型は True、U 型は False。削除済みは RuntimeError。"""
        for kind, expected in (("animCurveTL", True), ("animCurveTA", True), ("animCurveUL", False),
                               ("animCurveUU", False)):
            with self.subTest(kind=kind):
                curve = Node(cmds.createNode(kind, name=self.name(kind), skipSelect=True))
                self.assertIs(curve.isTimeInput(), expected)
        deleted = Node(cmds.createNode("animCurveTT", name=self.name("deletedCurve"), skipSelect=True))
        cmds.delete(deleted.getName())
        with self.assertRaises(RuntimeError):
            deleted.isTimeInput()


if __name__ == "__main__":
    unittest.main()

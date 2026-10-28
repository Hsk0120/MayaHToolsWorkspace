"""mlib の OpenMaya 直読みメソッドが maya.cmds の生の値と一致し続けることを検証する。

## この専用ファイルの目的

``docs/mlib-api-design.md`` の方針により、読み取り専用の照会は ``cmds`` ではなく ``om2``/``oma2`` を直接使う。
その置き換えが「今この瞬間だけ正しい」で終わらないよう、mlib の戻り値と
同じ情報を ``cmds`` 側から取得した生の値を**同じテスト内で突き合わせる**ことで、
将来の Maya バージョン変更や API の挙動変化、リファクタによる回帰を検知する。

他の test_*.py にある「期待する固定値になるか」だけのテストと違い、ここでは
必ず ``cmds.xxx(...)`` の呼び出し結果を片方の値として使う。新しく cmds→om2
の置き換えを行った場合は、対応する突き合わせをこのファイルに追加すること
(対象メソッドの単体テスト自体は、そのメソッドの機能テストが既にある
test_*.py にそのまま残してよい。このファイルは「cmds との一致」専任)。

## 既に他ファイルで cmds との突き合わせを行っている箇所(重複させない)

- ``Plug.get()`` のアトリビュート型ごとの分岐: ``test_node_api.py`` の
  ``test_plug_get_dispatches_by_attribute_type_via_om2``
  (bool/int/float/enum/文字列/角度/距離/時間を ``cmds.getAttr`` と突き合わせ)
- joint の jointOrient/rotateAxis 角度単位: ``test_joint.py`` の
  ``test_set_rotate_preserves_joint_orient_and_rotate_axis``
- ``Plugin``: ``test_plugin.py``(``cmds.pluginInfo`` と突き合わせ)
- ``Reference``: ``test_reference.py``(``cmds.referenceQuery`` と突き合わせ)

## このファイルの突き合わせ

- ``Node.getAliases()`` と ``cmds.aliasAttr(query=True)``
- ``Node.inputs/outputs/connections`` と ``cmds.listConnections(plugs=True)``
  (短い名前が重複するノードを含む。``Plug.getFullName()`` の一意な名前と一致すること)
- ``Namespace`` と ``cmds.namespace``/``cmds.namespaceInfo``
- Plug のアトリビュート型判定(アトリビュート定義から om2 で求める ``mlib.core.attributeType.attributeType``)と
  ``cmds.getAttr(<プラグ名>, type=True)``。transform・mesh・nurbsCurve・blendShape・
  plusMinusAverage・multiplyDivide・time・joint の代表的なアトリビュート、addAttr の全アトリビュート型・データ型の
  動的アトリビュート、多数のノード型の既存プラグで突き合わせる。cmds へ問い合わせるのは存在する要素だけで、
  存在しない要素は同じアトリビュートの既存要素と同じ型名になり要素が作られないことを確かめる。
  値によって型が変わる generic アトリビュート(``choice`` の ``input``/``output``、``unitConversion``)は、
  参照は基底 ``Plug`` のまま保持し、行列を保持する場合だけ ``get()`` の戻り値が
  ``mlib.maths.Matrix`` になることと、現在値がcmdsと一致することを確かめる。
- コンポーネント名としても解釈されるアトリビュート名(``pnts[i]``・``controlPoints[i]``)を
  om2 でアトリビュートパスを辿って解決した ``to_plug`` と、``cmds.connectAttr`` が接続するプラグ
- ワールド空間アトリビュートのインスタンス番号の要素(``instanceCount(True)``)と
  ``cmds.ls(allPaths=True)``、インスタンスごとの ``Transform.getMatrix(ws=True)`` と
  ``cmds.xform(query=True, matrix=True, worldSpace=True)``
- ``Transform.getMatrix`` (ローカルはMPlug、ワールドは対象インスタンスのDAGパスから取得)
  と ``cmds.getAttr``/``cmds.xform(query=True, matrix=True)``、
  ``mlib.maths.Matrix`` の分解(行列式が負の場合を含む)と ``cmds.xform(matrix=...)`` で
  書き込まれるチャンネル値・decomposeMatrix ノードの出力、``Transform.getRotate``/
  ``setRotate`` の3成分と ``cmds.xform(rotation=...)`` (全回転順序)

### 2.1.0 で om2 へ置き換えた読み取り(``_NewSceneCase`` 以降のクラス)

- ``Plug.isSettable()`` (``MPlug.isFreeToChange() == kFreeToChange``)と ``cmds.getAttr(settable=True)``。
  自身・複合の親・子のロック、入力接続、キー、lockNode、出力・``writable=False`` の動的アトリビュート
  (cmds は定義の writable を見ないので True)、配列・要素・複合配列の子・メッシュの pnts 要素
- ``Node.resetAttrs()`` の省略時の絞込み(``_require_writable``)と ``cmds.listAttr(keyable, scalar)``・
  ``getAttr(settable=True)``・入力接続(通常/fast とも。Transform は独自の resetAttrs のため DG ノードで確認)
- moveAttrOrder の enum 再作成情報(``_enum_definition``)と ``cmds.attributeQuery(listEnum=True)``
  (欠番・負の値・値の逆順・重複値・空白を含む名前)
- ``IkHandle.getJoints()`` (startJoint・endEffector の接続と DAG 親)と ``cmds.ikHandle(jointList=True)``
  (RP/SC/スプライン、1本の骨、途中から、名前空間、チェーンのインスタンス)
- ``Node.getHistory()`` (``MItDependencyGraph`` の深さ優先・ノード単位、Transform は中間でない直下の Shape)と
  ``cmds.listHistory`` の順序・範囲(複数 Shape・中間 Shape だけの Transform・インスタンス・デフォーマー・
  コンストレイント・循環・名前空間・future/past・type フィルター)
- ``Node.getPlugs()`` のフラグ無し・``keyable``・``scalar`` (定義の深さ優先の走査)と ``cmds.listAttr`` の名前を
  ``getPlug`` で解決した並び(多数のノード型・動的な配列/複合/複合配列・Shape の visibility の keyable 上書き・
  includeChildren)
- ``Plug.getAnimLayers()`` (blend ノードの message 出力先を om2 で取得)と
  ``cmds.animLayer(query=True, affectedLayers=True)``・``animLayer(attribute=True)``
- ``mlib.common.references.listReferences``/``createReference`` (``MItDependencyNodes(kReference)`` を名前順に)と
  ``cmds.ls(type="reference")``・``referenceQuery(parent=True)`` (入れ子・同じファイルの複数参照・アンロード・
  作成順と名前順が異なる参照ノード)
- ``Shape.scaleGeometry`` の NURBS サーフェス分岐(``MFnNurbsSurface.cvPosition`` で読む)と 2.0.0 の
  ``cmds.ls(flatten=True)``/``cmds.xform`` による結果(開いた/周期的、負のスケール、object/world、cm/m、
  周期の重複番号)

- ``Namespace.create`` の relativeNames 照会(``om2.MNamespace.relativeNames``)、選択・ドリブンキーの存在確認
  (``MSelectionList.add`` と ``cmds.objExists``)、``SkinCluster.deforms``/``bind`` の既スキン判定
  (``DagNode.getSkinClusters``)、``Lambert``/``StandardSurface`` の基底(``registry._inherited_node_types``):
  ``test_spec_common_edits.py``・``test_spec_skin_fast.py`` で突き合わせ(他ファイル)

### cmds のまま残したもの(突き合わせで om2 が一致しなかった・照会できない)

- ``_resolve_node`` の一意性の文言(``cmds.ls`` の一致数): ``MSelectionList.add``・
  ``MGlobal.getSelectionListByName`` はどちらも複数に一致する名前を数えずに失敗するため
"""
from maya.api.OpenMaya import MSpace

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import mlib
mlib.reload()
from mlib.nodes import Node
from mlib.common import Namespace
from mlib.plugs import Plug
from mlib.core.attributeType import attributeType


class NodeAliasesParityTest(unittest.TestCase):
    """Node.getAliases() が cmds.aliasAttr(query=True) と一致し続けることを検証する。"""

    def setUp(self):
        self.node = mlib.createNode(type="transform", name="mlibParityAliases")

    def tearDown(self):
        if cmds.objExists(self.node.getName()):
            cmds.delete(self.node.getName())

    def test_aliases_matches_cmds_aliasAttr(self):
        cmds.aliasAttr("mlibParityAliasTx", self.node.getPlug("translateX").getFullName())
        cmds.aliasAttr("mlibParityAliasTy", self.node.getPlug("translateY").getFullName())

        # cmds.aliasAttr(query=True) はフラットな [alias1, longName1, alias2, longName2, ...]
        # を返す。longName は Plug.getLongName(ロング名)と直接比較できる。
        raw = cmds.aliasAttr(self.node.getName(), query=True) or []
        expected = {(raw[index], raw[index + 1]) for index in range(0, len(raw), 2)}

        actual = {(alias, plug.getLongName()) for alias, plug in self.node.getAliases()}
        self.assertEqual(actual, expected)

    def test_aliases_empty_matches_cmds_when_no_alias_set(self):
        self.assertEqual(cmds.aliasAttr(self.node.getName(), query=True), None)
        self.assertEqual(self.node.getAliases(), [])


class NodeConnectionsParityTest(unittest.TestCase):
    """Node.inputs/outputs/getConnections(type=) が cmds.listConnections と一致し続けることを検証する。"""

    def setUp(self):
        self.created = []

    def tearDown(self):
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)

    def create_transform(self, name):
        node = mlib.createNode(type="transform", name=name)
        self.created.append(node.getName())
        return node

    def test_inputs_matches_cmds_listConnections_source_side(self):
        source = self.create_transform("mlibParityConnSource")
        target = self.create_transform("mlibParityConnTarget")
        source.getPlug("translateX").connectTo(target.getPlug("translateX"))

        expected = set(cmds.listConnections(target.getName(), source=True, destination=False, plugs=True) or [])
        actual = {plug.getFullName() for plug in target.getConnections(True, False)}
        self.assertEqual(actual, expected)

    def test_outputs_matches_cmds_listConnections_destination_side(self):
        source = self.create_transform("mlibParityConnSource2")
        target = self.create_transform("mlibParityConnTarget2")
        source.getPlug("translateX").connectTo(target.getPlug("translateX"))

        expected = set(cmds.listConnections(source.getName(), source=False, destination=True, plugs=True) or [])
        actual = {plug.getFullName() for plug in source.getConnections(False, True)}
        self.assertEqual(actual, expected)

    def test_connections_type_filter_matches_cmds_listConnections_type_filter(self):
        source = self.create_transform("mlibParityConnSource3")
        target = self.create_transform("mlibParityConnTarget3")
        mesh_target = cmds.polyCube(name="mlibParityConnMeshTarget", constructionHistory=False)[0]
        self.created.append(mesh_target)
        source.getPlug("translateX").connectTo(target.getPlug("translateX"))

        expected_transform = set(
            cmds.listConnections(source.getName(), source=False, destination=True, plugs=True, type="transform") or []
        )
        actual_transform = {plug.getFullName() for plug in source.getConnections(False, True, type='transform')}
        self.assertEqual(actual_transform, expected_transform)

        expected_mesh = set(
            cmds.listConnections(source.getName(), source=False, destination=True, plugs=True, type="mesh") or []
        )
        actual_mesh = {plug.getFullName() for plug in source.getConnections(False, True, type='mesh')}
        self.assertEqual(actual_mesh, expected_mesh)
        self.assertEqual(actual_mesh, set())

    def test_connections_with_duplicate_short_names_match_cmds_listConnections(self):
        # grp1|dup と grp2|dup のように短い名前が重複しても、mlib の一意なプラグ名が
        # cmds.listConnections の返す名前と一致し、どちらの接続も失われないこと。
        groups = [self.create_transform("mlibParityDupGroup%d" % index) for index in (1, 2)]
        duplicates = [
            Node(cmds.createNode("transform", name="mlibParityDup", parent=group.getFullName()))
            for group in groups
        ]
        source = self.create_transform("mlibParityDupSource")
        for duplicate in duplicates:
            source.getPlug("translateX").connectTo(duplicate.getPlug("translateX"))
            source.getPlug("translateY").connectTo(duplicate.getPlug("translateZ"))

        expected = set(cmds.listConnections(source.getName(), source=False, destination=True, plugs=True) or [])
        actual = {plug.getFullName() for plug in source.getConnections(False, True)}
        self.assertEqual(len(actual), 4)
        self.assertEqual(actual, expected)
        for duplicate in duplicates:
            expected_inputs = set(
                cmds.listConnections(duplicate.getName(), source=True, destination=False, plugs=True) or []
            )
            self.assertEqual({plug.getFullName() for plug in duplicate.getConnections(True, False)}, expected_inputs)


class NamespaceParityTest(unittest.TestCase):
    """Namespace(om2.MNamespaceベース) が cmds.namespace/namespaceInfo と一致し続けることを検証する。"""

    root_name = ":mlibParityNamespace"

    def setUp(self):
        if cmds.namespace(exists=self.root_name):
            cmds.namespace(removeNamespace=self.root_name, deleteNamespaceContent=True)
        cmds.namespace(add="mlibParityNamespace")
        cmds.namespace(add="child", parent=self.root_name)
        self.nodeName = cmds.createNode("transform", name=self.root_name + ":parityNode")

    def tearDown(self):
        if cmds.namespace(exists=self.root_name):
            cmds.namespace(removeNamespace=self.root_name, deleteNamespaceContent=True)

    def test_exists_matches_cmds_namespace_exists(self):
        self.assertEqual(Namespace(self.root_name).exists(), bool(cmds.namespace(exists=self.root_name)))
        self.assertEqual(
            Namespace(":mlibParityDoesNotExist").exists(),
            bool(cmds.namespace(exists=":mlibParityDoesNotExist")),
        )

    def test_children_matches_cmds_namespaceInfo_listOnlyNamespaces(self):
        expected_raw = cmds.namespaceInfo(
            self.root_name, listOnlyNamespaces=True, recurse=False, absoluteName=True,
        ) or []
        expected = {name if name.startswith(":") else f"{self.root_name}:{name}" for name in expected_raw}

        actual = {child.name for child in Namespace(self.root_name).getChildren()}
        self.assertEqual(actual, expected)

    def test_nodes_matches_cmds_namespaceInfo_listOnlyDependencyNodes(self):
        # cmds.namespaceInfo(absoluteName=True) は先頭に ":" を付けるが、
        # Node.name()(MFnDependencyNode.name())は付けないため、比較のため揃える。
        expected = {
            name.lstrip(":") for name in cmds.namespaceInfo(
                self.root_name, listOnlyDependencyNodes=True, recurse=False, absoluteName=True,
            ) or []
        }

        actual = {node.getName() for node in Namespace(self.root_name).getNodes()}
        self.assertEqual(actual, expected)

    def test_nodes_recurse_matches_cmds_namespaceInfo_recurse(self):
        expected = {
            name.lstrip(":") for name in cmds.namespaceInfo(
                self.root_name, listOnlyDependencyNodes=True, recurse=True, absoluteName=True,
            ) or []
        }

        actual = {node.getName() for node in Namespace(self.root_name).getNodes(recurse=True)}
        self.assertEqual(actual, expected)


class TransformMatrixParityTest(unittest.TestCase):
    """Transform の行列取得と mlib.maths の分解が cmds / decomposeMatrix と一致し続けることを検証する。

    ``Transform.getMatrix`` はローカルをMPlug、ワールドをDAGパスから取得する。
    ``mlib.maths.Matrix`` は om2.MMatrix を継承し、om2.MTransformationMatrix と同じ規約
    (行列式が負なら Z スケールを負にして 180 度を補う)で分解する。その規約が
    ``cmds.xform(matrix=...)`` によるチャンネル値と decomposeMatrix ノードの出力に
    一致することを突き合わせる。``Transform.getRotate`` / ``setRotate`` の3成分が
    ``cmds.xform(rotation=...)`` と同じくノードの rotateOrder の値であることも突き合わせる。
    """

    def setUp(self):
        import maya.api.OpenMaya as om2
        from mlib.maths import Matrix

        self.om2 = om2
        self.Matrix = Matrix
        self.created = []
        parent = cmds.createNode("transform", name="mlibParityMatrixParent")
        child = cmds.createNode("transform", name="mlibParityMatrixChild", parent=parent)
        self.created.append(parent)
        cmds.setAttr(parent + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(parent + ".rotate", 10.0, 20.0, 30.0)
        cmds.setAttr(child + ".translate", 4.0, 5.0, 6.0)
        cmds.setAttr(child + ".rotate", 40.0, -50.0, 60.0)
        cmds.setAttr(child + ".scale", 1.0, 2.0, 3.0)
        self.child = cmds.ls(child, long=True)[0]

    def tearDown(self):
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)

    def assert_sequence_almost_equal(self, actual, expected, places=9):
        self.assertEqual(len(actual), len(expected))
        for index, (a, b) in enumerate(zip(actual, expected)):
            self.assertAlmostEqual(a, b, places=places, msg="index {}: {} != {}".format(index, actual, expected))

    def test_get_matrix_matches_cmds_getAttr_and_xform(self):
        node = Node(self.child)
        self.assertEqual(list(node.getMatrix()), cmds.getAttr(self.child + ".matrix"))
        self.assertEqual(list(node.getMatrix(worldSpace=True)), cmds.getAttr(self.child + ".worldMatrix[0]"))
        self.assert_sequence_almost_equal(
            list(node.getMatrix(worldSpace=True)), cmds.xform(self.child, query=True, worldSpace=True, matrix=True))
        self.assert_sequence_almost_equal(
            tuple(node.getTranslate(worldSpace=True, at=4)), cmds.xform(self.child, query=True, worldSpace=True, translation=True))

    def test_world_matrix_follows_the_dag_instance(self):
        # getMatrix(ws=True) はラッパーの DAG パスのインスタンス番号の worldMatrix 要素を読む。
        group = cmds.createNode("transform", name="mlibParityInstanceGroup")
        other = cmds.createNode("transform", name="mlibParityInstanceOther")
        self.created.extend([group, other])
        leaf = cmds.createNode("transform", name="mlibParityInstanceLeaf", parent=group)
        cmds.setAttr(leaf + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(other + ".translate", 5.0, 0.0, 0.0)
        cmds.setAttr(other + ".rotate", 0.0, 30.0, 0.0)
        cmds.parent(cmds.ls(leaf, long=True)[0], other, addObject=True, relative=True)
        paths = cmds.ls("mlibParityInstanceLeaf", allPaths=True, long=True)
        self.assertEqual(len(paths), 2)
        for path in paths:
            node = Node(path)
            self.assert_sequence_almost_equal(
                list(node.getMatrix(worldSpace=True)), cmds.xform(path, query=True, worldSpace=True, matrix=True))

    def test_negative_determinant_decomposition_matches_xform_and_decompose_matrix(self):
        om2 = self.om2
        source = self.Matrix(
            translate=(1.0, -2.0, 3.0),
            rotate=(0.4, -0.3, 1.2),
            scale=(-2.0, 3.0, 4.0),
            shear=(0.1, 0.2, -0.3),
        )
        self.assertLess(source.det4x4(), 0.0)
        parts = source.decompose()

        target = cmds.createNode("transform", name="mlibParityNegativeTarget")
        self.created.append(target)
        cmds.xform(target, matrix=list(source))
        self.assert_sequence_almost_equal(tuple(parts["scale"]), cmds.getAttr(target + ".scale")[0])
        self.assert_sequence_almost_equal(tuple(parts["shear"]), cmds.getAttr(target + ".shear")[0])
        self.assert_sequence_almost_equal(parts["euler"].asDegrees(), cmds.getAttr(target + ".rotate")[0])
        self.assert_sequence_almost_equal(tuple(parts["translate"]), cmds.getAttr(target + ".translate")[0])
        self.assertLess(cmds.getAttr(target + ".scaleZ"), 0.0)
        self.assertTrue(Node(target).getMatrix().isEquivalent(source, 1e-9))

        if not cmds.pluginInfo("matrixNodes", query=True, loaded=True):
            cmds.loadPlugin("matrixNodes", quiet=True)
        decompose = cmds.createNode("decomposeMatrix", name="mlibParityNegativeDecompose")
        self.created.append(decompose)
        cmds.setAttr(decompose + ".inputMatrix", *list(source), type="matrix")
        self.assert_sequence_almost_equal(tuple(parts["scale"]), cmds.getAttr(decompose + ".outputScale")[0])
        self.assert_sequence_almost_equal(tuple(parts["shear"]), cmds.getAttr(decompose + ".outputShear")[0])
        self.assert_sequence_almost_equal(parts["euler"].asDegrees(), cmds.getAttr(decompose + ".outputRotate")[0])
        quaternion = om2.MQuaternion(*cmds.getAttr(decompose + ".outputQuat")[0])
        self.assertTrue(parts["quaternion"].isEquivalent(quaternion, 1e-9))

    def test_rotate_values_match_xform_in_every_rotate_order(self):
        # rotateAxis が 0 で、親が一様スケール(ワールド行列にシアーが無い)の transform が対象。
        # ワールド空間の Euler の解は xform と異なり得るため、回転行列で比較する。
        import math

        om2 = self.om2
        node = Node(self.child)
        for order in range(6):
            cmds.setAttr(self.child + ".rotateOrder", order)
            cmds.setAttr(self.child + ".rotate", 40.0, -50.0, 60.0)
            local = node.getRotate()
            self.assertEqual(local.order, order)
            self.assert_sequence_almost_equal(local.asDegrees(), cmds.xform(self.child, query=True, rotation=True))

            world = node.getRotate(worldSpace=True)
            self.assertEqual(world.order, order)
            queried = cmds.xform(self.child, query=True, worldSpace=True, rotation=True)
            expected = om2.MEulerRotation([math.radians(value) for value in queried], order)
            self.assertTrue(world.asMatrix().isEquivalent(expected.asMatrix(), 1e-9), order)

            node.setRotate((10.0, -20.0, 30.0), unit="deg", worldSpace=True)
            queried = cmds.xform(self.child, query=True, worldSpace=True, rotation=True)
            expected = om2.MEulerRotation([math.radians(value) for value in queried], order)
            wanted = om2.MEulerRotation(math.radians(10.0), math.radians(-20.0), math.radians(30.0), order)
            self.assertTrue(wanted.asMatrix().isEquivalent(expected.asMatrix(), 1e-9), order)

class PlugAttributeTypeParityTest(unittest.TestCase):
    """Plug のアトリビュート型判定が cmds.getAttr(type=True) と一致し続けることを検証する。

    Plug(node, mplug) は登録済みラッパー(DoubleLinearPlug/Double3Plug 等)を選ぶために
    ``cmds.getAttr(<プラグ名>, type=True)`` と同じ型名を使う。mlib はその型名をアトリビュート定義から
    om2 で求める(``mlib.core.attributeType.attributeType``)ため、既存のプラグについて
    cmds の生の値と一致することを確かめる。``cmds.getAttr(type=True)`` は存在しない配列要素を
    問い合わせると要素を作る(Maya が異常終了するアトリビュートもある)ため、cmds へ問い合わせるのは
    存在する要素(ワールド空間アトリビュートはインスタンス番号の要素)だけにする。
    """

    #: 動的アトリビュートとして追加する attributeType(単体と multi)。
    ATTRIBUTE_TYPES = ("bool", "long", "short", "byte", "char", "enum", "float", "double",
                       "doubleAngle", "doubleLinear", "floatAngle", "floatLinear", "time",
                       "message", "matrix", "fltMatrix")
    #: 動的アトリビュートとして追加する dataType。
    DATA_TYPES = ("string", "stringArray", "matrix", "doubleArray", "floatArray", "Int32Array",
                  "Int64Array", "vectorArray", "floatVectorArray", "pointArray", "matrixArray",
                  "componentList", "mesh", "nurbsCurve", "nurbsSurface", "lattice", "sphere",
                  "double2", "double3", "float2", "float3", "long2", "long3", "short2", "short3",
                  "reflectanceRGB", "spectrumRGB")
    #: 子アトリビュートとともに追加する複合アトリビュートの attributeType、子の attributeType、子の数。
    COMPOUND_TYPES = (
        ("double2", "double", 2), ("double3", "double", 3), ("double4", "double", 4),
        ("float2", "float", 2), ("float3", "float", 3), ("long2", "long", 2), ("long3", "long", 3),
        ("short2", "short", 2), ("short3", "short", 3), ("reflectance", "float", 3),
        ("spectrum", "float", 3), ("compound", "double", 3),
    )

    def setUp(self):
        self.namespace = "mlibParityPlugType_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.namespace)
        cmds.namespace(setNamespace=":" + self.namespace)

    def tearDown(self):
        cmds.namespace(setNamespace=":")
        if cmds.namespace(exists=":" + self.namespace):
            cmds.namespace(removeNamespace=":" + self.namespace, deleteNamespaceContent=True)

    @staticmethod
    def exists(mplug):
        """プラグの経路上の配列要素がすべて存在するか(cmds へ問い合わせてよいか)を返す。"""
        current = mplug
        while current.isElement or current.isChild:
            if current.isElement:
                array = current.array()
                index = current.logicalIndex()
                if index < 0:
                    return False
                instances = 0
                node = array.node()
                if node.hasFn(om2.MFn.kDagNode) and om2.MFnAttribute(array.attribute()).worldSpace:
                    instances = om2.MFnDagNode(node).instanceCount(True)
                if index >= instances and index not in list(array.getExistingArrayAttributeIndices()):
                    return False
                current = array
            else:
                current = current.parent()
        return True

    def assert_matches_cmds(self, plug):
        """存在するプラグについて、mlib の型名・ラッパーが cmds の型名と一致することを確かめる。"""
        self.assertTrue(self.exists(plug.mplug()), plug.getFullName())
        expected = cmds.getAttr(plug.getFullName(), type=True)
        self.assertEqual(attributeType(plug.mplug()), expected)
        resolved = Plug._registry.lookup(expected)
        if resolved is not None:
            self.assertIs(type(plug), resolved)
        return expected

    def plugs_of(self, node):
        """ノードの全アトリビュートから、存在する配列要素と複合アトリビュートの子まで含めたプラグを列挙する。"""
        fn = om2.MFnDependencyNode(node.mnode())
        result = []

        def visit(mplug, depth):
            if depth > 6:
                return
            if mplug.isArray:
                indices = list(mplug.getExistingArrayAttributeIndices())[:2]
                if not indices and self.exists(mplug.elementByLogicalIndex(0)):
                    indices = [0]  # 評価前のワールド空間アトリビュートのインスタンス番号の要素
                for index in indices:
                    visit(mplug.elementByLogicalIndex(index), depth + 1)
                return
            result.append(mplug)
            if mplug.isCompound:
                for index in range(mplug.numChildren()):
                    visit(mplug.child(index), depth + 1)

        for index in range(fn.attributeCount()):
            attribute = fn.attribute(index)
            if not om2.MFnAttribute(attribute).parent.isNull():
                continue
            visit(fn.findPlug(attribute, False), 0)
        return result

    def test_representative_plugs_match_cmds_getAttr_type(self):
        transform = Node(cmds.createNode("transform", name="transform"))
        mesh = Node(cmds.polyCube(name="cube", constructionHistory=False)[0]).getShape()
        cmds.setAttr(mesh.getName() + ".pnts[0].pntx", 0.25)
        curve = Node(cmds.curve(name="curve", degree=1, point=[(0, 0, 0), (1, 0, 0)])).getShape()
        target = cmds.polyCube(name="target")[0]
        base = cmds.polyCube(name="base")[0]
        blend = Node(cmds.blendShape(target, base, name="blend")[0])
        average = Node(cmds.createNode("plusMinusAverage", name="average"))
        cmds.setAttr(average.getName() + ".input1D[0]", 1.0)
        cmds.setAttr(average.getName() + ".input3D[0].input3Dx", 1.0)
        multiply = Node(cmds.createNode("multiplyDivide", name="multiply"))
        joint = Node(cmds.createNode("joint", name="joint"))
        cases = [
            (transform, "tx", "doubleLinear"), (transform, "t", "double3"), (transform, "r", "double3"),
            (transform, "s", "double3"), (transform, "v", "bool"), (transform, "rotateOrder", "enum"),
            (transform, "worldMatrix[0]", "matrix"), (transform, "parentMatrix[0]", "matrix"),
            (transform, "rx", "doubleAngle"), (transform, "message", "message"),
            (mesh, "pnts[0]", "float3"), (mesh, "pnts[0].pntx", "floatLinear"), (mesh, "outMesh", "mesh"),
            (curve, "controlPoints[0]", "double3"), (curve, "controlPoints[0].xValue", "doubleLinear"),
            (curve, "local", "nurbsCurve"),
            (blend, "weight[0]", "float"), (blend, "envelope", "float"),
            (average, "input1D[0]", "float"), (average, "input3D[0]", "float3"),
            (average, "operation", "enum"),
            (multiply, "input1", "float3"), (multiply, "input1X", "float"),
            (Node("time1"), "outTime", "time"),
            (joint, "jointOrient", "double3"), (joint, "jointOrientX", "doubleAngle"),
        ]
        for node, path, expected in cases:
            with self.subTest(plug=node.getName() + "." + path):
                plug = node.getPlug(path)
                self.assertEqual(self.assert_matches_cmds(plug), expected)

    def test_mesh_control_points_are_float3_like_cmds(self):
        # controlPoints は mesh と nurbsCurve が共有する double3 のアトリビュート定義だが、getAttr(type=True) は
        # mesh で float3 を返す(Maya が float の頂点座標として扱うため)。mlib も同じ型名になること。
        mesh = Node(cmds.polyCube(name="cpCube", constructionHistory=False)[0]).getShape()
        # controlPoints[i] の問い合わせで Maya が作る pnts[i] を先に作っておく。
        cmds.setAttr(mesh.getName() + ".pnts[0].pntx", 0.0)
        point = mesh.getPlug("controlPoints[0]")
        self.assertEqual(self.assert_matches_cmds(point), "float3")
        self.assertEqual(type(point).__name__, "CompoundPlug")
        self.assertEqual(self.assert_matches_cmds(point["xValue"]), "doubleLinear")
        curve = Node(cmds.curve(name="cpCurve", degree=1, point=[(0, 0, 0), (1, 0, 0)])).getShape()
        self.assertEqual(type(curve.getPlug("controlPoints[0]")).__name__, "Double3Plug")

    def test_dynamic_attributes_match_cmds_getAttr_type(self):
        network = Node(cmds.createNode("network", name="network"))
        name = network.getName()
        for attribute_type_name in self.ATTRIBUTE_TYPES:
            kwargs = {"enumName": "a:b"} if attribute_type_name == "enum" else {}
            cmds.addAttr(name, longName="at_" + attribute_type_name, attributeType=attribute_type_name, **kwargs)
            cmds.addAttr(name, longName="multi_" + attribute_type_name, attributeType=attribute_type_name,
                         multi=True, **kwargs)
        for dataType in self.DATA_TYPES:
            cmds.addAttr(name, longName="dt_" + dataType, dataType=dataType)
        for parent_type, child_type, count in self.COMPOUND_TYPES:
            parent = "cp_" + parent_type
            kwargs = {"numberOfChildren": count} if parent_type == "compound" else {}
            cmds.addAttr(name, longName=parent, attributeType=parent_type, **kwargs)
            for index in range(count):
                cmds.addAttr(name, longName="%s_%d" % (parent, index), attributeType=child_type, parent=parent)
        cmds.addAttr(name, longName="cp_linear", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(name, longName="cp_linear" + axis, attributeType="doubleLinear", parent="cp_linear")
        # 動的アトリビュートの配列要素は、値の設定・接続で作ってから問い合わせる。
        source = Node(cmds.createNode("transform", name="source"))
        for attribute_type_name in self.ATTRIBUTE_TYPES:
            element = "%s.multi_%s[0]" % (name, attribute_type_name)
            if attribute_type_name == "message":
                cmds.connectAttr(source.getName() + ".message", element)
            elif attribute_type_name in ("matrix", "fltMatrix"):
                cmds.setAttr(element, *[1.0 if index % 5 == 0 else 0.0 for index in range(16)], type="matrix")
            else:
                cmds.setAttr(element, 1)
        checked = {}
        top_level = [attribute for attribute in cmds.listAttr(name, userDefined=True) or []
                     if not network.getPlug(attribute).isChild()]
        for plug in [network.getPlug(attribute) for attribute in top_level]:
            plugs = [plug[0]] if plug.isArray() else [plug]
            if plug.isCompound():
                plugs.extend(plug.getChildren())
            for item in plugs:
                with self.subTest(plug=item.getFullName()):
                    checked[item.getAttrName()[1:]] = self.assert_matches_cmds(item)
        # 代表的な型名(登録ラッパーのキーを含む)が cmds と同じであること。
        expected = {
            "at_double": "double", "at_long": "long", "at_bool": "bool", "at_enum": "enum",
            "at_matrix": "matrix", "at_fltMatrix": "matrix", "at_message": "message",
            "multi_double[0]": "double", "multi_message[0]": "message", "dt_string": "string",
            "dt_matrix": "matrix", "dt_Int64Array": "Int64Array", "dt_double3": "double3",
            "cp_double3": "double3", "cp_float3": "float3", "cp_compound": "TdataCompound",
            "cp_reflectance": "reflectanceRGB", "cp_linear": "double3", "cp_linearX": "doubleLinear",
        }
        self.assertEqual({key: checked.get(key) for key in expected}, expected)
        self.assertGreater(len(checked), 80)

    def test_existing_plugs_of_many_node_types_match_cmds(self):
        cube, poly_cube = cmds.polyCube(name="cube")
        curve = cmds.curve(name="curve", degree=3, point=[(0, 0, 0), (1, 0, 0), (2, 1, 0), (3, 0, 0)])
        root = cmds.createNode("joint", name="rootJoint")
        tip = cmds.createNode("joint", name="tipJoint", parent=root)
        skin = cmds.skinCluster(root, tip, cube, name="skin")[0]
        sphere = cmds.sphere(name="sphere", constructionHistory=False)[0]
        target = cmds.polyCube(name="blendTarget")[0]
        base = cmds.polyCube(name="blendBase")[0]
        blend = cmds.blendShape(target, base, name="blend")[0]
        names = [cube, poly_cube, curve, root, skin, sphere, blend, "time1",
                 cmds.listRelatives(cube, shapes=True, fullPath=True)[0],
                 cmds.listRelatives(curve, shapes=True, fullPath=True)[0],
                 cmds.listRelatives(sphere, shapes=True, fullPath=True)[0],
                 cmds.createNode("transform", name="transform"),
                 cmds.createNode("multMatrix", name="multMatrix"),
                 cmds.createNode("plusMinusAverage", name="average"),
                 cmds.createNode("unitConversion", name="conversion"),
                 cmds.createNode("pointLight", name="lightShape")]
        checked = value_dependent = 0
        for node in [Node(name) for name in names]:
            for mplug in self.plugs_of(node):
                name = node.getName() + "." + mplug.partialName(False, True, True, True, False, True)
                try:
                    expected = cmds.getAttr(name, type=True)
                except (RuntimeError, ValueError):
                    continue  # mesh の内部アトリビュートなど、maya.cmds が型を返さないプラグ
                actual = attributeType(mplug)
                with self.subTest(plug=name):
                    if actual is None:
                        # 値によって型が変わるアトリビュート(generic アトリビュート・任意データの typed アトリビュート)だけが None。
                        attribute = mplug.attribute()
                        self.assertTrue(
                            attribute.hasFn(om2.MFn.kGenericAttribute)
                            or attribute.hasFn(om2.MFn.kTypedAttribute), name)
                        value_dependent += 1
                        continue
                    self.assertEqual(actual, expected)
                checked += 1
        self.assertGreater(checked, 1000)
        self.assertGreater(value_dependent, 0)

    def test_generic_attributes_holding_matrices_match_cmds(self):
        # 値によって型が変わる generic アトリビュートは、アトリビュート定義からは型名が決まらない(None)。Plug の生成は
        # 値を評価せず基底Plugを保ち、get()が現在値を解釈する。
        source = Node(cmds.createNode("transform", name="genericSource"))
        cmds.addAttr(source.getName(), longName="dbl", attributeType="double")
        cmds.addAttr(source.getName(), longName="colour", attributeType="float3")
        for axis in "RGB":
            cmds.addAttr(source.getName(), longName="colour" + axis, attributeType="float", parent="colour")
        sources = ("worldMatrix[0]", "matrix", "translate", "colour", "tx", "visibility", "dbl")
        checked = set()
        choices = []
        for index, attribute in enumerate(sources):
            choice = Node(cmds.createNode("choice", name="genericChoice%d" % index))
            choices.append(choice)
            cmds.connectAttr(source.getName() + "." + attribute, choice.getName() + ".input[0]")
            for path in ("output", "input[0]"):
                plug = choice.getPlug(path)
                name = plug.getFullName()
                with self.subTest(plug=name, source=attribute):
                    self.assertTrue(self.exists(plug.mplug()))
                    self.assertIsNone(attributeType(plug.mplug()))
                    expected = cmds.getAttr(name, type=True)
                    checked.add(expected)
                    self.assertIs(type(plug), Plug)
                    if expected == "matrix":
                        self.assertIsInstance(plug.get(), mlib.maths.Matrix)
                        for value, reference in zip(plug.get(), cmds.getAttr(name)):
                            self.assertAlmostEqual(value, reference)
                    else:
                        # double3・float3 などの数値の組や数値を保持する場合は基底の Plug。
                        reference = cmds.getAttr(name)
                        if isinstance(reference, list) and len(reference) == 1 and isinstance(reference[0], tuple):
                            reference = reference[0]
                        self.assertEqual(plug.get(), reference)
        self.assertTrue({"matrix", "double3", "float3"} <= checked, checked)
        # 入力接続の有無や接続元がgenericかどうかにかかわらず参照型は変えない。
        stored = Node(cmds.createNode("choice", name="genericStored"))
        cmds.setAttr(stored.getName() + ".input[2]", 3.0)
        standalone = Node(cmds.createNode("unitConversion", name="genericStandalone"))
        cmds.setAttr(standalone.getName() + ".input", 3.0)
        chained = Node(cmds.createNode("choice", name="genericChained"))
        cmds.connectAttr(choices[0].getName() + ".output", chained.getName() + ".input[0]")
        converted = Node(cmds.createNode("transform", name="genericConverted"))
        cmds.connectAttr(source.getName() + ".rx", converted.getName() + ".tx")
        conversion = Node(cmds.listConnections(converted.getName() + ".tx", source=True, destination=False)[0])
        for plug in (stored.getPlug("input[2]"), standalone.getPlug("input"), chained.getPlug("input[0]"),
                     chained.getPlug("output"), conversion.getPlug("input"), conversion.getPlug("output")):
            name = plug.getFullName()
            with self.subTest(plug=name):
                expected = cmds.getAttr(name, type=True)
                self.assertIs(type(plug), Plug)
                value = plug.get()
                reference = cmds.getAttr(name)
                if expected == "matrix":
                    self.assertIsInstance(value, mlib.maths.Matrix)
                    for actual, raw in zip(value, reference):
                        self.assertAlmostEqual(actual, raw)
                else:
                    if isinstance(reference, list) and len(reference) == 1 and isinstance(reference[0], tuple):
                        reference = reference[0]
                    self.assertEqual(value, reference)
        self.assertIs(type(chained.getPlug("input[0]")), Plug)
        self.assertEqual(standalone.getPlug("input").get(), 3.0)
        # 同じoutput参照を保持したままselectorで値の型を切り替える。
        choice = choices[0]
        cmds.connectAttr(source.getName() + ".dbl", choice.getName() + ".input[1]")
        output = choice.getPlug("output")
        for selector in (0, 1, 0, 1, 0):
            cmds.setAttr(choice.getName() + ".selector", selector)
            value = output.get()
            reference = cmds.getAttr(output.getFullName())
            self.assertIs(type(output), Plug)
            if selector == 0:
                self.assertIsInstance(value, mlib.maths.Matrix)
                for actual, raw in zip(value, reference):
                    self.assertAlmostEqual(actual, raw)
            else:
                self.assertEqual(value, reference)

    def test_missing_elements_resolve_like_existing_elements_without_changes(self):
        # 存在しない配列要素もアトリビュート定義から同じ型名になり、要素は作られない。cmds へは存在する
        # 要素だけを問い合わせる(存在しない要素の問い合わせは要素を作るため)。
        average = Node(cmds.createNode("plusMinusAverage", name="pma"))
        cmds.setAttr(average.getName() + ".input1D[0]", 1.0)
        cmds.setAttr(average.getName() + ".input3D[0].input3Dx", 1.0)
        mesh = Node(cmds.polyCube(name="missingCube", constructionHistory=False)[0]).getShape()
        cmds.setAttr(mesh.getName() + ".pnts[0].pntx", 0.0)
        network = Node(cmds.createNode("network", name="missingNet"))
        cmds.addAttr(network.getName(), longName="vals", attributeType="double", multi=True)
        cmds.setAttr(network.getName() + ".vals[0]", 1.0)
        base = cmds.polyCube(name="missingBase")[0]
        target = cmds.polyCube(name="missingTarget")[0]
        blend = Node(cmds.blendShape(target, base, name="missingBlend")[0])
        item = "inputTarget[0].inputTargetGroup[0].inputTargetItem[6000]"
        # (存在しない要素のプラグ, 同じアトリビュートの既存要素のプラグ, 要素が作られうる配列)
        cases = [
            (average, "input1D[10]", "input1D[0]", "input1D"),
            (average, "input3D[4].input3Dx", "input3D[0].input3Dx", "input3D"),
            (average, "input3D[4]", "input3D[0]", "input3D"),
            (mesh, "pnts[50].pntx", "pnts[0].pntx", "pnts"),
            (mesh, "pnts[50]", "pnts[0]", "pnts"),
            (network, "vals[4]", "vals[0]", "vals"),
            (blend, "weight[5]", "weight[0]", "weight"),
            (blend, "inputTarget[0].inputTargetGroup[3].inputTargetItem[6000].inputPointsTarget",
             item + ".inputPointsTarget", "inputTarget[0].inputTargetGroup"),
        ]
        for node, missing, existing, array_path in cases:
            with self.subTest(plug=missing):
                existing_plug = node.getPlug(existing)
                expected = self.assert_matches_cmds(existing_plug)
                array = node.getPlug(array_path)
                before = list(array.mplug().getExistingArrayAttributeIndices())
                missing_plug = node.getPlug(missing)
                self.assertFalse(self.exists(missing_plug.mplug()))
                self.assertEqual(attributeType(missing_plug.mplug()), expected)
                self.assertIs(type(missing_plug), type(existing_plug))
                self.assertEqual(list(array.mplug().getExistingArrayAttributeIndices()), before)


class NameResolutionParityTest(unittest.TestCase):
    """om2 で解決する名前・インスタンスの扱いが maya.cmds と一致し続けることを検証する。"""

    def setUp(self):
        self.namespace = "mlibParityNames_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.namespace)
        cmds.namespace(setNamespace=":" + self.namespace)

    def tearDown(self):
        cmds.namespace(setNamespace=":")
        if cmds.namespace(exists=":" + self.namespace):
            cmds.namespace(removeNamespace=":" + self.namespace, deleteNamespaceContent=True)

    def test_component_named_attributes_match_cmds_connectAttr(self):
        from mlib.plugs.plug import Plug as _InputPlug

        cube = Node(cmds.polyCube(name="cube", constructionHistory=False)[0])
        mesh = cube.getShape()
        curve = Node(cmds.curve(name="curve", degree=1, point=[(0, 0, 0), (1, 0, 0)])).getShape()
        cmds.lattice(cmds.polyCube(name="latticed", constructionHistory=False)[0], name="lat")
        lattice = Node(cmds.ls(self.namespace + ":*", type="lattice", long=True)[0])
        source = Node(cmds.createNode("transform", name="source"))
        other = Node(cmds.createNode("transform", name="other"))
        # MSelectionList はこれらを頂点・CV として登録するが、cmds.connectAttr はアトリビュートとして接続する。
        # 単位変換ノードが挟まらないよう、距離・倍率のアトリビュートどうしを接続する。
        cases = [
            (source.getPlug("translate"), mesh.getName() + ".pnts[3]"),
            (source.getPlug("tx"), mesh.getName() + ".pnts[4].pntx"),
            (source.getPlug("ty"), mesh.getName() + ".pt[5].py"),
            (other.getPlug("translate"), cube.getName() + ".pnts[6]"),
            (source.getPlug("scale"), curve.getName() + ".controlPoints[1]"),
            (source.getPlug("sz"), lattice.getName() + ".controlPoints[2].xValue"),
        ]
        for source_plug, text in cases:
            with self.subTest(plug=text):
                cmds.connectAttr(str(source_plug), text)
                resolved = _InputPlug._resolve_input(text)
                self.assertEqual(resolved.getSource(skipConversionNodes=False).mplug(), source_plug.mplug())
                self.assertIn(resolved.mplug(), list(source_plug.mplug().connectedTo(False, True)))
                self.assertEqual(cmds.getAttr(str(resolved), type=True), cmds.getAttr(text, type=True))

    def test_instance_elements_and_world_matrix_match_cmds(self):
        group = cmds.createNode("transform", name="group")
        child = cmds.createNode("transform", name="child", parent=group)
        cmds.createNode("transform", name="leaf", parent=child)
        instance = cmds.instance(group, name="groupInstance")[0]
        cmds.setAttr(instance + ".translate", 3, 4, 5)
        leaf = cmds.ls(self.namespace + ":leaf", long=True)[0]
        paths = cmds.ls(leaf, allPaths=True, long=True)
        self.assertEqual(len(paths), 2)
        world = Node(leaf).getPlug("worldMatrix")
        # 間接インスタンスを含むインスタンス数は cmds.ls(allPaths=True) の数と一致する。
        self.assertEqual(sorted(world.get()), list(range(len(paths))))
        for path in paths:
            with self.subTest(path=path):
                node = Node(path)
                expected = cmds.xform(path, query=True, matrix=True, worldSpace=True)
                actual = list(node.getMatrix(worldSpace=True))
                for value, reference in zip(actual, expected):
                    self.assertAlmostEqual(value, reference)


class _NewSceneCase(unittest.TestCase):
    """新規シーンで始め、Undoと単位・時刻の設定を元に戻す(名前に依存する突き合わせ用)。"""

    def setUp(self):
        cmds.file(new=True, force=True)
        self.undo_state = cmds.undoInfo(query=True, state=True)
        cmds.undoInfo(state=True)
        self.linear = cmds.currentUnit(query=True, linear=True)
        self.angle = cmds.currentUnit(query=True, angle=True)

    def tearDown(self):
        cmds.currentUnit(linear=self.linear, angle=self.angle)
        cmds.undoInfo(state=self.undo_state)
        cmds.file(new=True, force=True)


class PlugSettableParityTest(_NewSceneCase):
    """Plug.isSettable() (MPlug.isFreeToChange)と cmds.getAttr(settable=True) の一致。

    ロック(自身・複合の親・子)、入力接続、キー、lockNode、書込み禁止の出力・動的アトリビュート、
    配列と要素、複合配列の子、メッシュの pnts 要素で確かめる。cmds の settable は定義の writable を
    見ないため、``worldMatrix``・``outputX``・``writable=False`` の動的アトリビュートも True になる。
    """

    def test_is_settable_matches_cmds_getAttr_settable(self):
        node = cmds.createNode("transform", name="settable")
        driver = cmds.createNode("transform", name="settableDriver")
        cmds.setAttr(node + ".tx", lock=True)
        cmds.connectAttr(driver + ".ry", node + ".ry")
        cmds.setAttr(node + ".scale", lock=True)
        cmds.setKeyframe(node + ".tz", time=1, value=1)
        cmds.addAttr(node, longName="plain", attributeType="double")
        cmds.addAttr(node, longName="readOnly", attributeType="double", writable=False)
        cmds.addAttr(node, longName="multiValue", attributeType="double", multi=True)
        cmds.setAttr(node + ".multiValue[3]", 1)
        cmds.addAttr(node, longName="vector", attributeType="double3")
        for axis in "XYZ":
            cmds.addAttr(node, longName="vector" + axis, attributeType="double", parent="vector")
        cmds.setAttr(node + ".vectorY", lock=True)
        mesh = cmds.polyCube(name="settableCube")[0]
        shape = cmds.listRelatives(mesh, shapes=True)[0]
        multiply = cmds.createNode("multiplyDivide", name="settableMultiply")
        locked = cmds.createNode("transform", name="settableLockedNode")
        cmds.lockNode(locked, lock=True)
        names = [node + "." + attribute for attribute in (
            "tx", "ty", "tz", "translate", "rotate", "ry", "scale", "sx", "plain", "readOnly",
            "multiValue", "multiValue[3]", "multiValue[7]", "vector", "vectorX", "vectorY",
            "worldMatrix", "worldMatrix[0]", "matrix", "message", "parentMatrix[0]", "boundingBox",
            "center", "visibility", "instObjGroups[0].objectGroups[0].objectGroupId")]
        names += [multiply + ".output", multiply + ".outputX", multiply + ".input1X",
                  shape + ".vrts", shape + ".pnts", shape + ".pnts[0]", shape + ".inMesh", shape + ".outMesh",
                  locked + ".tx", locked + ".translate"]
        try:
            for name in names:
                with self.subTest(plug=name):
                    self.assertIs(mlib.getPlug(name).isSettable(), bool(cmds.getAttr(name, settable=True)))
        finally:
            cmds.lockNode(locked, lock=False)


class NodeResetAttrsParityTest(_NewSceneCase):
    """Node.resetAttrs() の省略時の絞込みと、cmds.listAttr(keyable, scalar)・getAttr(settable) の一致。

    書込み禁止の定義が無い keyable な scalar では、``_require_writable`` による除外は
    ``getAttr(settable=True)`` が False のもの(ロック・入力接続・親のロック)と一致する。
    通常経路と fast で同じアトリビュートを選ぶことも確かめる。Transform は独自の resetAttrs を
    持つため、Node.resetAttrs を使う DG ノードで確かめる。
    """

    def expected(self, name):
        """cmds だけで求めた、リセット対象(既定値を持ち入力接続が無く settable)のロング名。"""
        result = []
        for attribute in cmds.listAttr(name, keyable=True, scalar=True) or []:
            plug = name + "." + attribute
            if not cmds.objExists(plug) or cmds.attributeQuery(attribute, node=name, multi=True):
                continue  # 番号の無い配列の子と配列自体(要素ごとに reset する)は対象外。
            if cmds.listConnections(plug, source=True, destination=False):
                continue
            if not cmds.getAttr(plug, settable=True):
                continue
            if mlib.getPlug(plug).getDefault() is None:
                continue
            result.append(cmds.attributeQuery(attribute, node=name, longName=True))
        return result

    def test_reset_attrs_selection_matches_cmds(self):
        driver = cmds.createNode("transform", name="resetDriver")
        multiply = cmds.createNode("multiplyDivide", name="resetMultiply")
        cmds.setAttr(multiply + ".input1X", lock=True)
        cmds.connectAttr(driver + ".ty", multiply + ".input1Y")
        cmds.setAttr(multiply + ".input2", lock=True)
        cmds.setKeyframe(multiply + ".input1Z", time=1, value=1)
        network = cmds.createNode("network", name="resetNetwork")
        cmds.addAttr(network, longName="custom", attributeType="double", keyable=True, defaultValue=2)
        cmds.addAttr(network, longName="choice", attributeType="enum", enumName="a:b:c", keyable=True)
        cmds.addAttr(network, longName="locked", attributeType="double", keyable=True)
        cmds.setAttr(network + ".locked", lock=True)
        cmds.addAttr(network, longName="driven", attributeType="double", keyable=True)
        cmds.connectAttr(driver + ".tx", network + ".driven")
        cmds.addAttr(network, longName="vector", attributeType="double3", keyable=True)
        for axis in "XYZ":
            cmds.addAttr(network, longName="vector" + axis, attributeType="double", parent="vector", keyable=True)
        cmds.setAttr(network + ".vector", lock=True)
        names = (multiply, network, cmds.createNode("plusMinusAverage", name="resetAverage"),
                 cmds.createNode("condition", name="resetCondition"))
        for name in names:
            for fast in (False, True):
                with self.subTest(node=name, fast=fast):
                    expected = self.expected(name)
                    actual = [plug.getLongName() for plug in mlib.getNode(name).resetAttrs(fast=fast)]
                    self.assertEqual(sorted(actual), sorted(expected))


class EnumDefinitionParityTest(_NewSceneCase):
    """moveAttrOrder の再作成情報(``_enum_definition``)と cmds.attributeQuery(listEnum=True) の一致。"""

    def test_enum_definition_matches_attribute_query_list_enum(self):
        from mlib.nodes.node import _enum_definition

        node = cmds.createNode("transform", name="enumOwner")
        definitions = ["a:b:c", "a=1:b=5", "a=2:b:c", "x=-1:y", "p=3:q=1", "a=1:b=1", "s p:t", "only"]
        for index, definition in enumerate(definitions):
            name = "choice{}".format(index)
            cmds.addAttr(node, longName=name, attributeType="enum", enumName=definition)
            with self.subTest(definition=definition):
                expected = cmds.attributeQuery(name, node=node, listEnum=True)[0]
                self.assertEqual(_enum_definition(mlib.getPlug(node + "." + name)), expected)


class IkHandleJointsParityTest(_NewSceneCase):
    """IkHandle.getJoints()(startJoint・endEffector の接続と DAG 親)と cmds.ikHandle(jointList=True) の一致。

    RP/SC/スプライン、1本の骨、チェーンの途中から、名前空間、チェーンのインスタンスがある場合を確かめる。
    """

    def chain(self, count, prefix, axis=0):
        cmds.select(clear=True)
        joints = []
        for index in range(count):
            position = [0, 0, 0]
            position[axis] = index
            joints.append(cmds.joint(position=position, name="{}{}".format(prefix, index)))
        cmds.select(clear=True)
        return joints

    def test_get_joints_matches_cmds_joint_list(self):
        handles = []
        joints = self.chain(5, "ikLong")
        handles.append(cmds.ikHandle(startJoint=joints[0], endEffector=joints[4])[0])
        handles.append(cmds.ikHandle(startJoint=joints[1], endEffector=joints[3], solver="ikSCsolver")[0])
        short = self.chain(2, "ikShort", axis=1)
        handles.append(cmds.ikHandle(startJoint=short[0], endEffector=short[1])[0])
        spline = self.chain(6, "ikSpline", axis=2)
        handles.append(cmds.ikHandle(startJoint=spline[0], endEffector=spline[5], solver="ikSplineSolver")[0])
        cmds.namespace(add="ikParity")
        spaced = self.chain(3, "ikParity:spaced")
        handles.append(cmds.ikHandle(startJoint=spaced[0], endEffector=spaced[2])[0])
        cmds.instance(joints[0])
        for handle in handles:
            with self.subTest(handle=handle):
                expected = cmds.ls(cmds.ikHandle(handle, query=True, jointList=True), uuid=True)
                node = mlib.getNode(handle)
                self.assertEqual([joint.getUuid() for joint in node.getJoints()], expected)
                with_tip = node.getJoints(includeTip=True)
                self.assertEqual([joint.getUuid() for joint in with_tip[:-1]], expected)
                self.assertEqual(with_tip[-1], node.getEndJoint())


class NodeHistoryParityTest(_NewSceneCase):
    """Node.getHistory()(MItDependencyGraph の深さ優先)と cmds.listHistory の順序・範囲の一致。

    Shapeを持つTransform(中間オブジェクトだけのTransformを含む)・複数Shape・インスタンス・
    skinCluster/blendShape/構築履歴・コンストレイント・循環接続・接続の無いノード・名前空間・
    future/past と type フィルターで確かめる。
    """

    def expected(self, name, future, kind=None):
        names = cmds.listHistory(name, future=future) or []
        own = cmds.ls(name, uuid=True)[0]
        result = []
        for item in names:
            uuid = cmds.ls(item, uuid=True)[0]
            if uuid == own or uuid in result:
                continue
            if kind is None or kind in (cmds.nodeType(item, inherited=True) or []):
                result.append(uuid)
        return result

    def test_history_matches_cmds_list_history(self):
        cube = cmds.polyCube(name="historyCube")[0]
        cmds.polyBevel(cube + ".e[0]")
        cmds.select(clear=True)
        root = cmds.joint(name="historyRoot")
        tip = cmds.joint(position=(0, 1, 0), name="historyTip")
        cmds.skinCluster(root, tip, cube)
        cmds.blendShape(cmds.duplicate(cube)[0], cube, frontOfChain=True)
        cmds.setKeyframe(cube + ".tx")
        first = cmds.circle(name="historyCircleA")[0]
        second = cmds.circle(name="historyCircleB")[0]
        moved = cmds.listRelatives(second, shapes=True, fullPath=True)[0]
        cmds.parent(moved, first, shape=True, relative=True)
        hidden = cmds.polySphere(name="historyHidden")[0]
        cmds.setAttr(cmds.listRelatives(hidden, shapes=True, fullPath=True)[0] + ".intermediateObject", 1)
        locator = cmds.spaceLocator(name="historyLocator")[0]
        cmds.parentConstraint(tip, locator)
        left = cmds.createNode("multiplyDivide", name="historyLeft")
        right = cmds.createNode("multiplyDivide", name="historyRight")
        cmds.connectAttr(left + ".outputX", right + ".input1X")
        cmds.connectAttr(right + ".outputX", left + ".input1Y")
        cmds.createNode("transform", name="historyAlone")
        cmds.namespace(add="historyNs")
        cmds.polyCube(name="historyNs:cube")
        cmds.instance(cube, name="historyInstance")
        names = cmds.ls(dependencyNodes=True) or []
        names = [name for name in names if name.startswith(("history", "skinCluster", "blendShape", "polyBevel",
                                                            "bindPose", "historyNs:"))]
        names += cmds.ls(type=("animCurve", "parentConstraint", "mesh", "nurbsCurve")) or []
        names += ["initialShadingGroup", "time1"]
        self.assertGreater(len(names), 20)
        for name in names:
            node = mlib.getNode(name)
            for future in (False, True):
                with self.subTest(node=name, future=future):
                    actual = [item.getUuid() for item in node.getHistory(future=future)]
                    self.assertEqual(actual, self.expected(name, future))
        for name, kind in ((cube, "geometryFilter"), (cube, "mesh"), (root, "dagNode"), (locator, "constraint")):
            for future in (False, True):
                with self.subTest(node=name, type=kind, future=future):
                    actual = [item.getUuid() for item in mlib.getNode(name).getHistory(type=kind, future=future)]
                    self.assertEqual(actual, self.expected(name, future, kind))


class NodeGetPlugsParityTest(_NewSceneCase):
    """Node.getPlugs()(フラグ無し・keyable・scalar を om2 の定義の走査で列挙)と cmds.listAttr の一致。

    期待値は 2.0.0 の実装と同じく、``cmds.listAttr`` の名前を ``getPlug`` で解決できたものの並び。
    多数のノード型、動的な配列・複合・複合配列、Shape の keyable 上書き(visibility)で確かめる。
    """

    def expected(self, node, include_children, **flags):
        result = []
        for name in cmds.listAttr(node.getFullName(), **flags) or []:
            try:
                plug = node.getPlug(name)
            except (AttributeError, RuntimeError, ValueError):
                continue
            if include_children or not plug.mplug().isChild:
                result.append((plug.getFullName(), type(plug).__name__))
        return result

    def test_get_plugs_matches_cmds_list_attr(self):
        cube = cmds.polyCube(name="plugsCube")[0]
        cmds.blendShape(cmds.duplicate(cube)[0], cube, name="plugsBlend")
        cmds.addAttr(cube, longName="values", attributeType="double", multi=True, keyable=True)
        cmds.setAttr(cube + ".values[2]", 1)
        cmds.addAttr(cube, longName="pairs", attributeType="compound", numberOfChildren=2, multi=True)
        cmds.addAttr(cube, longName="pairA", attributeType="double", parent="pairs", keyable=True)
        cmds.addAttr(cube, longName="pairB", attributeType="double", parent="pairs")
        cmds.addAttr(cube, longName="label", dataType="string")
        cmds.addAttr(cube, longName="mode", attributeType="enum", enumName="a:b", keyable=True)
        cmds.addAttr(cube, longName="toggle", attributeType="bool", keyable=True)
        cmds.addAttr(cube, longName="offset", attributeType="double3", keyable=True)
        for axis in "XYZ":
            cmds.addAttr(cube, longName="offset" + axis, attributeType="double", parent="offset", keyable=True)
        cmds.addAttr(cube, longName="pose", attributeType="matrix")
        sphere = cmds.sphere(name="plugsSphere")[0]
        cmds.select(clear=True)
        joint = cmds.joint(name="plugsJoint")
        skin = cmds.skinCluster(joint, cmds.polyCube(name="plugsSkinned")[0])[0]
        locator = cmds.spaceLocator(name="plugsLocator")[0]
        constraint = cmds.parentConstraint(joint, locator)[0]
        names = [cube, "plugsBlend", cmds.listRelatives(cube, shapes=True)[0], sphere,
                 cmds.listRelatives(sphere, shapes=True)[0], joint, skin, constraint,
                 cmds.listRelatives(locator, shapes=True)[0], "persp", "perspShape"]
        for kind in ("multiplyDivide", "plusMinusAverage", "blendColors", "choice", "unitConversion",
                     "condition", "decomposeMatrix", "animCurveTL", "lambert", "place2dTexture", "time",
                     "pairBlend", "nurbsCurve", "camera"):
            names.append(cmds.createNode(kind))
        flag_sets = ({}, {"keyable": True}, {"scalar": True}, {"keyable": True, "scalar": True})
        for name in names:
            node = mlib.getNode(name)
            for flags in flag_sets:
                for include_children in (True, False):
                    with self.subTest(node=name, flags=flags, includeChildren=include_children):
                        actual = [(plug.getFullName(), type(plug).__name__)
                                  for plug in node.getPlugs(includeChildren=include_children, **flags)]
                        self.assertEqual(actual, self.expected(node, include_children, **flags))


class PlugAnimLayersParityTest(_NewSceneCase):
    """Plug.getAnimLayers()(blend ノードの message 出力先の animLayer を om2 で取得)と cmds.animLayer の一致。

    期待値は ``cmds.animLayer(query=True, affectedLayers=True)`` の順から、そのアトリビュートを
    含むレイヤー(``animLayer(attribute=True)``)とベースレイヤーを残したもの。
    """

    def test_anim_layers_match_cmds_anim_layer(self):
        node = cmds.createNode("transform", name="layered")
        cmds.setKeyframe(node + ".tx", value=1)
        cmds.setKeyframe(node + ".rx", value=1)
        cmds.animLayer("layerA")
        cmds.animLayer("layerB")
        cmds.animLayer("layerC", parent="layerA")
        for layer in ("layerA", "layerB"):
            cmds.animLayer(layer, edit=True, attribute=[node + ".tx", node + ".rx"])
        cmds.animLayer("layerC", edit=True, attribute=node + ".tx")
        cmds.select(node)
        affected = cmds.animLayer(query=True, affectedLayers=True)
        root = cmds.animLayer(query=True, root=True)
        for attribute in ("translateX", "rotateX", "translateY"):
            name = node + "." + attribute
            with self.subTest(plug=name):
                expected = [layer for layer in affected
                            if layer == root or name in (cmds.animLayer(layer, query=True, attribute=True) or [])]
                self.assertEqual(mlib.getPlug(name).getAnimLayers(), expected)


class ReferencesParityTest(_NewSceneCase):
    """listReferences/createReference(MItDependencyNodes(kReference))と cmds.ls(type="reference") の一致。

    入れ子の参照、同じファイルの複数回の参照、アンロード中の参照、作成順と名前順が異なる手作りの
    参照ノードで、順序(名前の文字コード順)と topLevelOnly を確かめる。
    """

    def setUp(self):
        super().setUp()
        import tempfile
        from pathlib import Path

        self.directory = Path(tempfile.mkdtemp(prefix="mlibParityReferences_"))
        cmds.polyCube(name="referencedCube")
        self.child = self.directory / "child.ma"
        cmds.file(rename=str(self.child))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)
        cmds.file(str(self.child), reference=True, namespace="nested")
        cmds.polySphere(name="referencedSphere")
        self.parent = self.directory / "parent.ma"
        cmds.file(rename=str(self.parent))
        cmds.file(save=True, type="mayaAscii")
        cmds.file(new=True, force=True)

    def tearDown(self):
        import shutil

        super().tearDown()
        shutil.rmtree(str(self.directory), ignore_errors=True)

    def expected(self, top_level_only=False):
        names = [name for name in cmds.ls(type="reference") or [] if name != "sharedReferenceNode"]
        if top_level_only:
            names = [name for name in names if not cmds.referenceQuery(name, referenceNode=True, parent=True)]
        return names

    def test_list_and_create_references_match_cmds_ls(self):
        from mlib.common.references import createReference, listReferences

        first = createReference(self.parent, namespace="first")
        self.assertEqual(first.getName(), cmds.referenceQuery(str(self.parent), referenceNode=True))
        createReference(self.child, namespace="direct")
        again = createReference(self.parent, namespace="second")
        self.assertEqual(again.getParentReference(), None)
        cmds.file(unloadReference=again.getName())
        for top_level_only in (False, True):
            with self.subTest(top_level_only=top_level_only):
                actual = [reference.getName() for reference in listReferences(topLevelOnly=top_level_only)]
                self.assertEqual(actual, self.expected(top_level_only))
        # 作成順と名前順が異なる参照ノード(ファイルを持たないため topLevelOnly は照会しない)。
        for name in ("zzManualRN", "aaManualRN", "MmManualRN", "_underscoreRN", "B2ManualRN"):
            cmds.createNode("reference", name=name)
        self.assertEqual([reference.getName() for reference in listReferences()], self.expected())


class SurfaceScaleGeometryParityTest(_NewSceneCase):
    """Shape.scaleGeometry の NURBS サーフェス分岐(MFnNurbsSurface で読む)と cmds.ls/xform の一致。

    2.0.0 の実装(``cmds.ls(flatten=True)`` で展開し ``cmds.xform`` で読み書き)を複製したサーフェスへ
    適用し、全CVの結果が一致することを、開いた/周期的なサーフェス・負のスケールのTransform・
    object/world 空間・cm/m・全CV/番号指定(周期の重複番号を含む)で確かめる。
    """

    def scale_with_cmds(self, shape, factors, pivot, indices, ws):
        center = [om2.MDistance(value).asUnits(om2.MDistance.uiUnit()) for value in pivot]
        if indices is None:
            components = [shape + ".cv[*][*]"]
        else:
            path = mlib.getNode(shape).mpath()
            fn = om2.MFnNurbsSurface(path)
            components, seen = [], set()
            for row in indices:
                row = tuple(
                    value % (count - degree) if form == om2.MFnNurbsSurface.kPeriodic else value
                    for value, count, degree, form in zip(
                        row, (fn.numCVsInU, fn.numCVsInV), (fn.degreeInU, fn.degreeInV), (fn.formInU, fn.formInV)))
                if row not in seen:
                    seen.add(row)
                    components.append("{}.cv[{}][{}]".format(shape, *row))
        components = cmds.ls(components, flatten=True) or []
        positions = [cmds.xform(component, query=True, translation=True, worldSpace=ws, objectSpace=not ws)
                     for component in components]
        for component, position in zip(components, positions):
            values = [center[i] + (position[i] - center[i]) * factors[i] for i in range(3)]
            cmds.xform(component, translation=values, worldSpace=ws, objectSpace=not ws)

    def test_scale_geometry_surface_matches_cmds_xform(self):
        makers = (lambda: cmds.sphere(constructionHistory=False)[0],
                  lambda: cmds.nurbsPlane(constructionHistory=False, patchesU=3, patchesV=2)[0],
                  lambda: cmds.torus(constructionHistory=False)[0])
        cases = ((None, False), (None, True), ([(0, 0), (1, 2), (6, 9), (0, 8)], False), ([(2, 1), (3, 3)], True))
        for unit in ("cm", "m"):
            cmds.currentUnit(linear=unit)
            for make_index, make in enumerate(makers):
                for indices, ws in cases:
                    with self.subTest(unit=unit, surface=make_index, indices=indices, ws=ws):
                        transform = make()
                        cmds.setAttr(transform + ".translate", 1, 2, 3)
                        cmds.setAttr(transform + ".scale", 2, 1, -1)
                        copy = cmds.duplicate(transform)[0]
                        shape = cmds.listRelatives(transform, shapes=True, fullPath=True)[0]
                        copy_shape = cmds.listRelatives(copy, shapes=True, fullPath=True)[0]
                        fn = om2.MFnNurbsSurface(mlib.getNode(shape).mpath())
                        limit = (fn.numCVsInU, fn.numCVsInV)
                        valid = None if indices is None else [
                            row for row in indices if row[0] < limit[0] and row[1] < limit[1]]
                        mlib.getNode(shape).scaleGeometry((2.0, 0.5, -1.5), worldSpace=ws, pivot=(0.5, 1.0, -2.0),
                                                          indices=valid)
                        self.scale_with_cmds(copy_shape, (2.0, 0.5, -1.5), (0.5, 1.0, -2.0), valid, ws)
                        actual = fn.cvPositions(om2.MSpace.kObject)
                        expected = om2.MFnNurbsSurface(mlib.getNode(copy_shape).mpath()).cvPositions(
                            om2.MSpace.kObject)
                        self.assertEqual(len(actual), len(expected))
                        for first, second in zip(actual, expected):
                            for a, b in zip(first, second):
                                self.assertAlmostEqual(a, b, places=6)
                        cmds.delete(transform, copy)
        cmds.currentUnit(linear="cm")


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

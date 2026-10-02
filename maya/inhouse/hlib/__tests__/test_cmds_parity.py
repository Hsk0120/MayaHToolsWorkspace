"""hlib の OpenMaya 直読みメソッドが maya.cmds の生の値と一致し続けることを検証する。

## この専用ファイルの目的

``hlib/docs/development.rst`` の「maya.cmds と OpenMaya API 2.0 の使い分け」の
方針により、読み取り専用の照会は ``cmds`` ではなく ``om2``/``oma2`` を直接使う。
その置き換えが「今この瞬間だけ正しい」で終わらないよう、hlib の戻り値と
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
- ``Preferences``: ``test_units.py``(``cmds.currentUnit`` と突き合わせ)
- ``Workspace``: ``test_workspace.py``(``cmds.workspace`` と突き合わせ)
- ``Plugin``: ``test_plugin.py``(``cmds.pluginInfo`` と突き合わせ)
- ``Reference``: ``test_reference.py``(``cmds.referenceQuery`` と突き合わせ)

## このファイルの突き合わせ

- ``Node.aliases()`` と ``cmds.aliasAttr(query=True)``
- ``Node.inputs/outputs/connections`` と ``cmds.listConnections(plugs=True)``
  (短い名前が重複するノードを含む。``Plug.full_name()`` の一意な名前と一致すること)
- ``Namespace`` と ``cmds.namespace``/``cmds.namespaceInfo``
- Plug のアトリビュート型判定(アトリビュート定義から om2 で求める ``hlib._core.attributeType.attribute_type``)と
  ``cmds.getAttr(<プラグ名>, type=True)``。transform・mesh・nurbsCurve・blendShape・
  plusMinusAverage・multiplyDivide・time・joint の代表的なアトリビュート、addAttr の全アトリビュート型・データ型の
  動的アトリビュート、多数のノード型の既存プラグで突き合わせる。cmds へ問い合わせるのは存在する要素だけで、
  存在しない要素は同じアトリビュートの既存要素と同じ型名になり要素が作られないことを確かめる。
  値によって型が変わる generic アトリビュート(``choice`` の ``input``/``output``、``unitConversion``)は、
  行列を保持する場合だけ cmds と同じ ``matrix`` (``MatrixPlug``)になることを確かめる
  (入力接続のある要素は接続元の型、接続の無い要素は値、接続元も値によって型が変わる場合は
  接続元を辿った結果)
- コンポーネント名としても解釈されるアトリビュート名(``pnts[i]``・``controlPoints[i]``)を
  om2 でアトリビュートパスを辿って解決した ``to_plug`` と、``cmds.connectAttr`` が接続するプラグ
- ワールド空間アトリビュートのインスタンス番号の要素(``instanceCount(True)``)と
  ``cmds.ls(allPaths=True)``、インスタンスごとの ``Transform.get_matrix(ws=True)`` と
  ``cmds.xform(query=True, matrix=True, worldSpace=True)``
- ``Transform.get_matrix`` (ローカルはMPlug、ワールドは対象インスタンスのDAGパスから取得)
  と ``cmds.getAttr``/``cmds.xform(query=True, matrix=True)``、
  ``hlib.maths.Matrix`` の分解(行列式が負の場合を含む)と ``cmds.xform(matrix=...)`` で
  書き込まれるチャンネル値・decomposeMatrix ノードの出力、``Transform.get_rotate``/
  ``set_rotate`` の3成分と ``cmds.xform(rotation=...)`` (全回転順序)
"""

import sys
import unittest
import uuid

import maya.api.OpenMaya as om2
import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.scene import Namespace
from hlib.plugs import Plug
from hlib._core.attributeType import attribute_type


class NodeAliasesParityTest(unittest.TestCase):
    """Node.aliases() が cmds.aliasAttr(query=True) と一致し続けることを検証する。"""

    def setUp(self):
        self.node = Node.create(type="transform", name="hlibParityAliases")

    def tearDown(self):
        if cmds.objExists(self.node.name()):
            cmds.delete(self.node.name())

    def test_aliases_matches_cmds_aliasAttr(self):
        cmds.aliasAttr("hlibParityAliasTx", self.node.plug("translateX").full_name())
        cmds.aliasAttr("hlibParityAliasTy", self.node.plug("translateY").full_name())

        # cmds.aliasAttr(query=True) はフラットな [alias1, longName1, alias2, longName2, ...]
        # を返す。longName は Plug.attribute_name(ロング名)と直接比較できる。
        raw = cmds.aliasAttr(self.node.name(), query=True) or []
        expected = {(raw[index], raw[index + 1]) for index in range(0, len(raw), 2)}

        actual = {(alias, plug.attribute_name()) for alias, plug in self.node.aliases()}
        self.assertEqual(actual, expected)

    def test_aliases_empty_matches_cmds_when_no_alias_set(self):
        self.assertEqual(cmds.aliasAttr(self.node.name(), query=True), None)
        self.assertEqual(self.node.aliases(), [])


class NodeConnectionsParityTest(unittest.TestCase):
    """Node.inputs/outputs/connections(type=) が cmds.listConnections と一致し続けることを検証する。"""

    def setUp(self):
        self.created = []

    def tearDown(self):
        for name in reversed(self.created):
            if cmds.objExists(name):
                cmds.delete(name)

    def create_transform(self, name):
        node = Node.create(type="transform", name=name)
        self.created.append(node.name())
        return node

    def test_inputs_matches_cmds_listConnections_source_side(self):
        source = self.create_transform("hlibParityConnSource")
        target = self.create_transform("hlibParityConnTarget")
        source.plug("translateX").connect(target.plug("translateX"))

        expected = set(cmds.listConnections(target.name(), source=True, destination=False, plugs=True) or [])
        actual = {plug.full_name() for plug in target.inputs()}
        self.assertEqual(actual, expected)

    def test_outputs_matches_cmds_listConnections_destination_side(self):
        source = self.create_transform("hlibParityConnSource2")
        target = self.create_transform("hlibParityConnTarget2")
        source.plug("translateX").connect(target.plug("translateX"))

        expected = set(cmds.listConnections(source.name(), source=False, destination=True, plugs=True) or [])
        actual = {plug.full_name() for plug in source.outputs()}
        self.assertEqual(actual, expected)

    def test_connections_type_filter_matches_cmds_listConnections_type_filter(self):
        source = self.create_transform("hlibParityConnSource3")
        target = self.create_transform("hlibParityConnTarget3")
        mesh_target = cmds.polyCube(name="hlibParityConnMeshTarget", constructionHistory=False)[0]
        self.created.append(mesh_target)
        source.plug("translateX").connect(target.plug("translateX"))

        expected_transform = set(
            cmds.listConnections(source.name(), source=False, destination=True, plugs=True, type="transform") or []
        )
        actual_transform = {plug.full_name() for plug in source.outputs(type="transform")}
        self.assertEqual(actual_transform, expected_transform)

        expected_mesh = set(
            cmds.listConnections(source.name(), source=False, destination=True, plugs=True, type="mesh") or []
        )
        actual_mesh = {plug.full_name() for plug in source.outputs(type="mesh")}
        self.assertEqual(actual_mesh, expected_mesh)
        self.assertEqual(actual_mesh, set())

    def test_connections_with_duplicate_short_names_match_cmds_listConnections(self):
        # grp1|dup と grp2|dup のように短い名前が重複しても、hlib の一意なプラグ名が
        # cmds.listConnections の返す名前と一致し、どちらの接続も失われないこと。
        groups = [self.create_transform("hlibParityDupGroup%d" % index) for index in (1, 2)]
        duplicates = [
            Node(cmds.createNode("transform", name="hlibParityDup", parent=group.full_name()))
            for group in groups
        ]
        source = self.create_transform("hlibParityDupSource")
        for duplicate in duplicates:
            source.plug("translateX").connect(duplicate.plug("translateX"))
            source.plug("translateY").connect(duplicate.plug("translateZ"))

        expected = set(cmds.listConnections(source.name(), source=False, destination=True, plugs=True) or [])
        actual = {plug.full_name() for plug in source.outputs()}
        self.assertEqual(len(actual), 4)
        self.assertEqual(actual, expected)
        for duplicate in duplicates:
            expected_inputs = set(
                cmds.listConnections(duplicate.name(), source=True, destination=False, plugs=True) or []
            )
            self.assertEqual({plug.full_name() for plug in duplicate.inputs()}, expected_inputs)


class NamespaceParityTest(unittest.TestCase):
    """Namespace(om2.MNamespaceベース) が cmds.namespace/namespaceInfo と一致し続けることを検証する。"""

    root_name = ":hlibParityNamespace"

    def setUp(self):
        if cmds.namespace(exists=self.root_name):
            cmds.namespace(removeNamespace=self.root_name, deleteNamespaceContent=True)
        cmds.namespace(add="hlibParityNamespace")
        cmds.namespace(add="child", parent=self.root_name)
        self.node_name = cmds.createNode("transform", name=self.root_name + ":parityNode")

    def tearDown(self):
        if cmds.namespace(exists=self.root_name):
            cmds.namespace(removeNamespace=self.root_name, deleteNamespaceContent=True)

    def test_exists_matches_cmds_namespace_exists(self):
        self.assertEqual(Namespace(self.root_name).exists(), bool(cmds.namespace(exists=self.root_name)))
        self.assertEqual(
            Namespace(":hlibParityDoesNotExist").exists(),
            bool(cmds.namespace(exists=":hlibParityDoesNotExist")),
        )

    def test_children_matches_cmds_namespaceInfo_listOnlyNamespaces(self):
        expected_raw = cmds.namespaceInfo(
            self.root_name, listOnlyNamespaces=True, recurse=False, absoluteName=True,
        ) or []
        expected = {name if name.startswith(":") else f"{self.root_name}:{name}" for name in expected_raw}

        actual = {child.name for child in Namespace(self.root_name).children()}
        self.assertEqual(actual, expected)

    def test_nodes_matches_cmds_namespaceInfo_listOnlyDependencyNodes(self):
        # cmds.namespaceInfo(absoluteName=True) は先頭に ":" を付けるが、
        # Node.name()(MFnDependencyNode.name())は付けないため、比較のため揃える。
        expected = {
            name.lstrip(":") for name in cmds.namespaceInfo(
                self.root_name, listOnlyDependencyNodes=True, recurse=False, absoluteName=True,
            ) or []
        }

        actual = {node.name() for node in Namespace(self.root_name).nodes()}
        self.assertEqual(actual, expected)

    def test_nodes_recurse_matches_cmds_namespaceInfo_recurse(self):
        expected = {
            name.lstrip(":") for name in cmds.namespaceInfo(
                self.root_name, listOnlyDependencyNodes=True, recurse=True, absoluteName=True,
            ) or []
        }

        actual = {node.name() for node in Namespace(self.root_name).nodes(recurse=True)}
        self.assertEqual(actual, expected)


class TransformMatrixParityTest(unittest.TestCase):
    """Transform の行列取得と hlib.maths の分解が cmds / decomposeMatrix と一致し続けることを検証する。

    ``Transform.get_matrix`` はローカルをMPlug、ワールドをDAGパスから取得する。
    ``hlib.maths.Matrix`` は om2.MMatrix を継承し、om2.MTransformationMatrix と同じ規約
    (行列式が負なら Z スケールを負にして 180 度を補う)で分解する。その規約が
    ``cmds.xform(matrix=...)`` によるチャンネル値と decomposeMatrix ノードの出力に
    一致することを突き合わせる。``Transform.get_rotate`` / ``set_rotate`` の3成分が
    ``cmds.xform(rotation=...)`` と同じくノードの rotateOrder の値であることも突き合わせる。
    """

    def setUp(self):
        import maya.api.OpenMaya as om2
        from hlib.maths import Matrix

        self.om2 = om2
        self.Matrix = Matrix
        self.created = []
        parent = cmds.createNode("transform", name="hlibParityMatrixParent")
        child = cmds.createNode("transform", name="hlibParityMatrixChild", parent=parent)
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
        self.assertEqual(list(node.get_matrix()), cmds.getAttr(self.child + ".matrix"))
        self.assertEqual(list(node.get_matrix(ws=True)), cmds.getAttr(self.child + ".worldMatrix[0]"))
        self.assert_sequence_almost_equal(
            list(node.get_matrix(ws=True)), cmds.xform(self.child, query=True, worldSpace=True, matrix=True))
        self.assert_sequence_almost_equal(
            tuple(node.get_translate(ws=True)), cmds.xform(self.child, query=True, worldSpace=True, translation=True))

    def test_world_matrix_follows_the_dag_instance(self):
        # get_matrix(ws=True) はラッパーの DAG パスのインスタンス番号の worldMatrix 要素を読む。
        group = cmds.createNode("transform", name="hlibParityInstanceGroup")
        other = cmds.createNode("transform", name="hlibParityInstanceOther")
        self.created.extend([group, other])
        leaf = cmds.createNode("transform", name="hlibParityInstanceLeaf", parent=group)
        cmds.setAttr(leaf + ".translate", 1.0, 2.0, 3.0)
        cmds.setAttr(other + ".translate", 5.0, 0.0, 0.0)
        cmds.setAttr(other + ".rotate", 0.0, 30.0, 0.0)
        cmds.parent(cmds.ls(leaf, long=True)[0], other, addObject=True, relative=True)
        paths = cmds.ls("hlibParityInstanceLeaf", allPaths=True, long=True)
        self.assertEqual(len(paths), 2)
        for path in paths:
            node = Node(path)
            self.assert_sequence_almost_equal(
                list(node.get_matrix(ws=True)), cmds.xform(path, query=True, worldSpace=True, matrix=True))

    def test_negative_determinant_decomposition_matches_xform_and_decompose_matrix(self):
        om2 = self.om2
        source = self.Matrix(
            translate=(1.0, -2.0, 3.0),
            rotate=(0.4, -0.3, 1.2),
            scale=(-2.0, 3.0, 4.0),
            shear=(0.1, 0.2, -0.3),
        )
        self.assertLess(source.determinant(), 0.0)
        parts = source.decompose()

        target = cmds.createNode("transform", name="hlibParityNegativeTarget")
        self.created.append(target)
        cmds.xform(target, matrix=list(source))
        self.assert_sequence_almost_equal(tuple(parts["scale"]), cmds.getAttr(target + ".scale")[0])
        self.assert_sequence_almost_equal(tuple(parts["shear"]), cmds.getAttr(target + ".shear")[0])
        self.assert_sequence_almost_equal(parts["euler"].as_degrees(), cmds.getAttr(target + ".rotate")[0])
        self.assert_sequence_almost_equal(tuple(parts["translate"]), cmds.getAttr(target + ".translate")[0])
        self.assertLess(cmds.getAttr(target + ".scaleZ"), 0.0)
        self.assertTrue(Node(target).get_matrix().is_equivalent(source, 1e-9))

        if not cmds.pluginInfo("matrixNodes", query=True, loaded=True):
            cmds.loadPlugin("matrixNodes", quiet=True)
        decompose = cmds.createNode("decomposeMatrix", name="hlibParityNegativeDecompose")
        self.created.append(decompose)
        cmds.setAttr(decompose + ".inputMatrix", *list(source), type="matrix")
        self.assert_sequence_almost_equal(tuple(parts["scale"]), cmds.getAttr(decompose + ".outputScale")[0])
        self.assert_sequence_almost_equal(tuple(parts["shear"]), cmds.getAttr(decompose + ".outputShear")[0])
        self.assert_sequence_almost_equal(parts["euler"].as_degrees(), cmds.getAttr(decompose + ".outputRotate")[0])
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
            local = node.get_rotate()
            self.assertEqual(local.order, order)
            self.assert_sequence_almost_equal(local.as_degrees(), cmds.xform(self.child, query=True, rotation=True))

            world = node.get_rotate(ws=True)
            self.assertEqual(world.order, order)
            queried = cmds.xform(self.child, query=True, worldSpace=True, rotation=True)
            expected = om2.MEulerRotation([math.radians(value) for value in queried], order)
            self.assertTrue(world.asMatrix().isEquivalent(expected.asMatrix(), 1e-9), order)

            node.set_rotate((10.0, -20.0, 30.0), unit="deg", ws=True)
            queried = cmds.xform(self.child, query=True, worldSpace=True, rotation=True)
            expected = om2.MEulerRotation([math.radians(value) for value in queried], order)
            wanted = om2.MEulerRotation(math.radians(10.0), math.radians(-20.0), math.radians(30.0), order)
            self.assertTrue(wanted.asMatrix().isEquivalent(expected.asMatrix(), 1e-9), order)

class PlugAttributeTypeParityTest(unittest.TestCase):
    """Plug のアトリビュート型判定が cmds.getAttr(type=True) と一致し続けることを検証する。

    Plug(node, mplug) は登録済みラッパー(DoubleLinearPlug/Double3Plug 等)を選ぶために
    ``cmds.getAttr(<プラグ名>, type=True)`` と同じ型名を使う。hlib はその型名をアトリビュート定義から
    om2 で求める(``hlib._core.attributeType.attribute_type``)ため、既存のプラグについて
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
        self.namespace = "hlibParityPlugType_" + uuid.uuid4().hex[:12]
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
        """存在するプラグについて、hlib の型名・ラッパーが cmds の型名と一致することを確かめる。"""
        self.assertTrue(self.exists(plug.mplug()), plug.full_name())
        expected = cmds.getAttr(plug.full_name(), type=True)
        self.assertEqual(attribute_type(plug.mplug()), expected)
        resolved = Plug._registry.lookup(expected)
        if resolved is not None:
            self.assertIs(type(plug), resolved)
        return expected

    def plugs_of(self, node):
        """ノードの全アトリビュートから、存在する配列要素と複合アトリビュートの子まで含めたプラグを列挙する。"""
        fn = om2.MFnDependencyNode(node.mobject())
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
        mesh = Node(cmds.polyCube(name="cube", constructionHistory=False)[0]).shape()
        cmds.setAttr(mesh.name() + ".pnts[0].pntx", 0.25)
        curve = Node(cmds.curve(name="curve", degree=1, point=[(0, 0, 0), (1, 0, 0)])).shape()
        target = cmds.polyCube(name="target")[0]
        base = cmds.polyCube(name="base")[0]
        blend = Node(cmds.blendShape(target, base, name="blend")[0])
        average = Node(cmds.createNode("plusMinusAverage", name="average"))
        cmds.setAttr(average.name() + ".input1D[0]", 1.0)
        cmds.setAttr(average.name() + ".input3D[0].input3Dx", 1.0)
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
            with self.subTest(plug=node.name() + "." + path):
                plug = node.plug(path)
                self.assertEqual(self.assert_matches_cmds(plug), expected)

    def test_mesh_control_points_are_float3_like_cmds(self):
        # controlPoints は mesh と nurbsCurve が共有する double3 のアトリビュート定義だが、getAttr(type=True) は
        # mesh で float3 を返す(Maya が float の頂点座標として扱うため)。hlib も同じ型名になること。
        mesh = Node(cmds.polyCube(name="cpCube", constructionHistory=False)[0]).shape()
        # controlPoints[i] の問い合わせで Maya が作る pnts[i] を先に作っておく。
        cmds.setAttr(mesh.name() + ".pnts[0].pntx", 0.0)
        point = mesh.plug("controlPoints[0]")
        self.assertEqual(self.assert_matches_cmds(point), "float3")
        self.assertEqual(type(point).__name__, "CompoundPlug")
        self.assertEqual(self.assert_matches_cmds(point.child("xValue")), "doubleLinear")
        curve = Node(cmds.curve(name="cpCurve", degree=1, point=[(0, 0, 0), (1, 0, 0)])).shape()
        self.assertEqual(type(curve.plug("controlPoints[0]")).__name__, "Double3Plug")

    def test_dynamic_attributes_match_cmds_getAttr_type(self):
        network = Node(cmds.createNode("network", name="network"))
        name = network.name()
        for attribute_type_name in self.ATTRIBUTE_TYPES:
            kwargs = {"enumName": "a:b"} if attribute_type_name == "enum" else {}
            cmds.addAttr(name, longName="at_" + attribute_type_name, attributeType=attribute_type_name, **kwargs)
            cmds.addAttr(name, longName="multi_" + attribute_type_name, attributeType=attribute_type_name,
                         multi=True, **kwargs)
        for data_type in self.DATA_TYPES:
            cmds.addAttr(name, longName="dt_" + data_type, dataType=data_type)
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
                cmds.connectAttr(source.name() + ".message", element)
            elif attribute_type_name in ("matrix", "fltMatrix"):
                cmds.setAttr(element, *[1.0 if index % 5 == 0 else 0.0 for index in range(16)], type="matrix")
            else:
                cmds.setAttr(element, 1)
        checked = {}
        top_level = [attribute for attribute in cmds.listAttr(name, userDefined=True) or []
                     if not network.plug(attribute).is_child()]
        for plug in [network.plug(attribute) for attribute in top_level]:
            plugs = [plug.element(0)] if plug.is_array() else [plug]
            if plug.is_compound():
                plugs.extend(plug.children())
            for item in plugs:
                with self.subTest(plug=item.full_name()):
                    checked[item.name()] = self.assert_matches_cmds(item)
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
                name = node.name() + "." + mplug.partialName(False, True, True, True, False, True)
                try:
                    expected = cmds.getAttr(name, type=True)
                except (RuntimeError, ValueError):
                    continue  # mesh の内部アトリビュートなど、maya.cmds が型を返さないプラグ
                actual = attribute_type(mplug)
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
        # 存在する要素の値が行列なら cmds.getAttr(type=True) と同じ "matrix" として MatrixPlug を選ぶ。
        from hlib.plugs.plug import _held_matrix_type

        source = Node(cmds.createNode("transform", name="genericSource"))
        cmds.addAttr(source.name(), longName="dbl", attributeType="double")
        cmds.addAttr(source.name(), longName="colour", attributeType="float3")
        for axis in "RGB":
            cmds.addAttr(source.name(), longName="colour" + axis, attributeType="float", parent="colour")
        sources = ("worldMatrix[0]", "matrix", "translate", "colour", "tx", "visibility", "dbl")
        checked = set()
        choices = []
        for index, attribute in enumerate(sources):
            choice = Node(cmds.createNode("choice", name="genericChoice%d" % index))
            choices.append(choice)
            cmds.connectAttr(source.name() + "." + attribute, choice.name() + ".input[0]")
            for path in ("output", "input[0]"):
                plug = choice.plug(path)
                name = plug.full_name()
                with self.subTest(plug=name, source=attribute):
                    self.assertTrue(self.exists(plug.mplug()))
                    self.assertIsNone(attribute_type(plug.mplug()))
                    expected = cmds.getAttr(name, type=True)
                    checked.add(expected)
                    if expected == "matrix":
                        self.assertEqual(_held_matrix_type(plug.mplug()), "matrix")
                        self.assertEqual(type(plug).__name__, "MatrixPlug")
                        for value, reference in zip(plug.get(), cmds.getAttr(name)):
                            self.assertAlmostEqual(value, reference)
                    else:
                        # double3・float3 などの数値の組や数値を保持する場合は基底の Plug。
                        self.assertIsNone(_held_matrix_type(plug.mplug()))
                        self.assertIs(type(plug), Plug)
        self.assertTrue({"matrix", "double3", "float3"} <= checked, checked)
        # 入力接続の無い要素は値を読み、接続元も値によって型が変わるアトリビュートなら接続元を辿る。
        stored = Node(cmds.createNode("choice", name="genericStored"))
        cmds.setAttr(stored.name() + ".input[2]", 3.0)
        standalone = Node(cmds.createNode("unitConversion", name="genericStandalone"))
        cmds.setAttr(standalone.name() + ".input", 3.0)
        chained = Node(cmds.createNode("choice", name="genericChained"))
        cmds.connectAttr(choices[0].name() + ".output", chained.name() + ".input[0]")
        converted = Node(cmds.createNode("transform", name="genericConverted"))
        cmds.connectAttr(source.name() + ".rx", converted.name() + ".tx")
        conversion = Node(cmds.listConnections(converted.name() + ".tx", source=True, destination=False)[0])
        for plug in (stored.plug("input[2]"), standalone.plug("input"), chained.plug("input[0]"),
                     chained.plug("output"), conversion.plug("input"), conversion.plug("output")):
            name = plug.full_name()
            with self.subTest(plug=name):
                expected = cmds.getAttr(name, type=True)
                self.assertEqual(_held_matrix_type(plug.mplug()), "matrix" if expected == "matrix" else None)
                self.assertEqual(type(plug).__name__, "MatrixPlug" if expected == "matrix" else "Plug")
        self.assertEqual(type(chained.plug("input[0]")).__name__, "MatrixPlug")
        self.assertEqual(standalone.plug("input").get(), 3.0)

    def test_missing_elements_resolve_like_existing_elements_without_changes(self):
        # 存在しない配列要素もアトリビュート定義から同じ型名になり、要素は作られない。cmds へは存在する
        # 要素だけを問い合わせる(存在しない要素の問い合わせは要素を作るため)。
        average = Node(cmds.createNode("plusMinusAverage", name="pma"))
        cmds.setAttr(average.name() + ".input1D[0]", 1.0)
        cmds.setAttr(average.name() + ".input3D[0].input3Dx", 1.0)
        mesh = Node(cmds.polyCube(name="missingCube", constructionHistory=False)[0]).shape()
        cmds.setAttr(mesh.name() + ".pnts[0].pntx", 0.0)
        network = Node(cmds.createNode("network", name="missingNet"))
        cmds.addAttr(network.name(), longName="vals", attributeType="double", multi=True)
        cmds.setAttr(network.name() + ".vals[0]", 1.0)
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
                existing_plug = node.plug(existing)
                expected = self.assert_matches_cmds(existing_plug)
                array = node.plug(array_path)
                before = list(array.mplug().getExistingArrayAttributeIndices())
                missing_plug = node.plug(missing)
                self.assertFalse(self.exists(missing_plug.mplug()))
                self.assertEqual(attribute_type(missing_plug.mplug()), expected)
                self.assertIs(type(missing_plug), type(existing_plug))
                self.assertEqual(list(array.mplug().getExistingArrayAttributeIndices()), before)


class NameResolutionParityTest(unittest.TestCase):
    """om2 で解決する名前・インスタンスの扱いが maya.cmds と一致し続けることを検証する。"""

    def setUp(self):
        self.namespace = "hlibParityNames_" + uuid.uuid4().hex[:12]
        cmds.namespace(add=self.namespace)
        cmds.namespace(setNamespace=":" + self.namespace)

    def tearDown(self):
        cmds.namespace(setNamespace=":")
        if cmds.namespace(exists=":" + self.namespace):
            cmds.namespace(removeNamespace=":" + self.namespace, deleteNamespaceContent=True)

    def test_component_named_attributes_match_cmds_connectAttr(self):
        from hlib.plugs.plug import Plug as _InputPlug

        cube = Node(cmds.polyCube(name="cube", constructionHistory=False)[0])
        mesh = cube.shape()
        curve = Node(cmds.curve(name="curve", degree=1, point=[(0, 0, 0), (1, 0, 0)])).shape()
        cmds.lattice(cmds.polyCube(name="latticed", constructionHistory=False)[0], name="lat")
        lattice = Node(cmds.ls(self.namespace + ":*", type="lattice", long=True)[0])
        source = Node(cmds.createNode("transform", name="source"))
        other = Node(cmds.createNode("transform", name="other"))
        # MSelectionList はこれらを頂点・CV として登録するが、cmds.connectAttr はアトリビュートとして接続する。
        # 単位変換ノードが挟まらないよう、距離・倍率のアトリビュートどうしを接続する。
        cases = [
            (source.plug("translate"), mesh.name() + ".pnts[3]"),
            (source.plug("tx"), mesh.name() + ".pnts[4].pntx"),
            (source.plug("ty"), mesh.name() + ".pt[5].py"),
            (other.plug("translate"), cube.name() + ".pnts[6]"),
            (source.plug("scale"), curve.name() + ".controlPoints[1]"),
            (source.plug("sz"), lattice.name() + ".controlPoints[2].xValue"),
        ]
        for source_plug, text in cases:
            with self.subTest(plug=text):
                cmds.connectAttr(str(source_plug), text)
                resolved = _InputPlug._resolve_input(text)
                self.assertEqual(resolved.source().mplug(), source_plug.mplug())
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
        world = Node(leaf).plug("worldMatrix")
        # 間接インスタンスを含むインスタンス数は cmds.ls(allPaths=True) の数と一致する。
        self.assertEqual(sorted(world.get()), list(range(len(paths))))
        for path in paths:
            with self.subTest(path=path):
                node = Node(path)
                expected = cmds.xform(path, query=True, matrix=True, worldSpace=True)
                actual = list(node.get_matrix(ws=True))
                for value, reference in zip(actual, expected):
                    self.assertAlmostEqual(value, reference)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

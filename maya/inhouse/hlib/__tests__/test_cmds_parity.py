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

- ``Plug.get()`` の属性型ごとの分岐: ``test_node_api.py`` の
  ``test_plug_get_dispatches_by_attribute_type_via_om2``
  (bool/int/float/enum/文字列/角度/距離/時間を ``cmds.getAttr`` と突き合わせ)
- joint の jointOrient/rotateAxis 角度単位: ``test_joint.py`` の
  ``test_set_rotate_preserves_joint_orient_and_rotate_axis``
- ``Units``: ``test_units.py``(``cmds.currentUnit`` と突き合わせ)
- ``Workspace``: ``test_workspace.py``(``cmds.workspace`` と突き合わせ)
- ``Plugin``: ``test_plugin.py``(``cmds.pluginInfo`` と突き合わせ)
- ``Reference``: ``test_reference.py``(``cmds.referenceQuery`` と突き合わせ)

## このファイルの突き合わせ

- ``Node.aliases()`` と ``cmds.aliasAttr(query=True)``
- ``Node.inputs/outputs/connections`` と ``cmds.listConnections(plugs=True)``
- ``Namespace`` と ``cmds.namespace``/``cmds.namespaceInfo``
- ``Transform.get_matrix`` (om2 の MPlug から直接読む。ワールド空間はインスタンスごとの
  ``worldMatrix`` の要素)と ``cmds.getAttr``/``cmds.xform(query=True, matrix=True)``、
  ``hlib.maths.Matrix`` の分解(行列式が負の場合を含む)と ``cmds.xform(matrix=...)`` で
  書き込まれるチャンネル値・decomposeMatrix ノードの出力、``Transform.get_rotate``/
  ``set_rotate`` の3成分と ``cmds.xform(rotation=...)`` (全回転順序)
"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.namespaces import Namespace


class NodeAliasesParityTest(unittest.TestCase):
    """Node.aliases() が cmds.aliasAttr(query=True) と一致し続けることを検証する。"""

    def setUp(self):
        self.node = Node.create(type="transform", name="hlibParityAliases")

    def tearDown(self):
        if cmds.objExists(self.node.name()):
            cmds.delete(self.node.name())

    def test_aliases_matches_cmds_aliasAttr(self):
        cmds.aliasAttr("hlibParityAliasTx", self.node.attr("translateX").full_name())
        cmds.aliasAttr("hlibParityAliasTy", self.node.attr("translateY").full_name())

        # cmds.aliasAttr(query=True) はフラットな [alias1, longName1, alias2, longName2, ...]
        # を返す。longName は Plug.attribute(ロング名)と直接比較できる。
        raw = cmds.aliasAttr(self.node.name(), query=True) or []
        expected = {(raw[index], raw[index + 1]) for index in range(0, len(raw), 2)}

        actual = {(alias, plug.attribute()) for alias, plug in self.node.aliases()}
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
        source.attr("translateX").connect(target.attr("translateX"))

        expected = set(cmds.listConnections(target.name(), source=True, destination=False, plugs=True) or [])
        actual = {plug.full_name() for plug in target.inputs()}
        self.assertEqual(actual, expected)

    def test_outputs_matches_cmds_listConnections_destination_side(self):
        source = self.create_transform("hlibParityConnSource2")
        target = self.create_transform("hlibParityConnTarget2")
        source.attr("translateX").connect(target.attr("translateX"))

        expected = set(cmds.listConnections(source.name(), source=False, destination=True, plugs=True) or [])
        actual = {plug.full_name() for plug in source.outputs()}
        self.assertEqual(actual, expected)

    def test_connections_type_filter_matches_cmds_listConnections_type_filter(self):
        source = self.create_transform("hlibParityConnSource3")
        target = self.create_transform("hlibParityConnTarget3")
        mesh_target = cmds.polyCube(name="hlibParityConnMeshTarget", constructionHistory=False)[0]
        self.created.append(mesh_target)
        source.attr("translateX").connect(target.attr("translateX"))

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

        actual = {child.name() for child in Namespace(self.root_name).children()}
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

    ``Transform.get_matrix`` は hlib の Plug ラッパーを介さず om2 の MPlug から直接読む。
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


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

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
"""

import sys
import unittest

import maya.cmds as cmds

import hlib
hlib.reload()
from hlib.nodes import Node
from hlib.scenes import Namespace


class NodeAliasesParityTest(unittest.TestCase):
    """Node.aliases() が cmds.aliasAttr(query=True) と一致し続けることを検証する。"""

    def setUp(self):
        self.node = Node.create(type="transform", name="hlibParityAliases")

    def tearDown(self):
        if cmds.objExists(self.node.name()):
            cmds.delete(self.node.name())

    def test_aliases_matches_cmds_aliasAttr(self):
        cmds.aliasAttr("hlibParityAliasTx", self.node.attr("translateX").full_name)
        cmds.aliasAttr("hlibParityAliasTy", self.node.attr("translateY").full_name)

        # cmds.aliasAttr(query=True) はフラットな [alias1, longName1, alias2, longName2, ...]
        # を返す。longName は Plug.attribute(ロング名)と直接比較できる。
        raw = cmds.aliasAttr(self.node.name(), query=True) or []
        expected = {(raw[index], raw[index + 1]) for index in range(0, len(raw), 2)}

        actual = {(alias, plug.attribute) for alias, plug in self.node.aliases()}
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
        actual = {plug.full_name for plug in target.inputs()}
        self.assertEqual(actual, expected)

    def test_outputs_matches_cmds_listConnections_destination_side(self):
        source = self.create_transform("hlibParityConnSource2")
        target = self.create_transform("hlibParityConnTarget2")
        source.attr("translateX").connect(target.attr("translateX"))

        expected = set(cmds.listConnections(source.name(), source=False, destination=True, plugs=True) or [])
        actual = {plug.full_name for plug in source.outputs()}
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
        actual_transform = {plug.full_name for plug in source.outputs(type="transform")}
        self.assertEqual(actual_transform, expected_transform)

        expected_mesh = set(
            cmds.listConnections(source.name(), source=False, destination=True, plugs=True, type="mesh") or []
        )
        actual_mesh = {plug.full_name for plug in source.outputs(type="mesh")}
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


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])

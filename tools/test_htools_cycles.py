"""サイクル調査を使い捨てmayapyで検証する。GUIでは明示的にrunTestsを呼ぶ。"""

from pathlib import Path
import sys
import unittest
from unittest import mock


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "maya/inhouse"))


class CycleInspectorTest(unittest.TestCase):
    """実DG・DAGと入力拒否、調査時の状態維持を確認する。"""

    def setUp(self):
        """他のシーンに触れず、このテストで作ったノードだけを記録する。"""
        import maya.cmds as cmds
        self.cmds = cmds
        self.nodes = []
        self.selection = cmds.ls(selection=True, long=True) or []

    def tearDown(self):
        """作成したノードを削除し、選択を戻す。"""
        existing = [n for n in self.nodes if self.cmds.objExists(n)]
        if existing:
            self.cmds.delete(existing)
        self.cmds.select(self.selection, replace=True)

    def createNode(self, kind):
        """検証用ノードを作って後始末の対象へ加える。"""
        node = self.cmds.createNode(kind, name="htoolsCycleTest#")
        self.nodes.append(node)
        return node

    def test_dg_cycle_and_state(self):
        """実サイクルの接続方向・選択・評価時チェック設定が維持される。"""
        from HTools.rigging.inspectCycles import formatReport
        from HTools.rigging.inspectCycles import inspectCycles
        a, b = self.createNode("multiplyDivide"), self.createNode("multiplyDivide")
        self.cmds.connectAttr(a + ".outputX", b + ".input1X")
        self.cmds.connectAttr(b + ".outputX", a + ".input1X")
        self.cmds.select(a)
        selection = self.cmds.ls(selection=True)
        evaluation = self.cmds.cycleCheck(query=True, evaluation=True)
        result = inspectCycles([a])
        self.assertTrue(result["groups"])
        connections = {edge for group in result["groups"] for edge in group["connections"]}
        self.assertIn((a + ".outputX", b + ".input1X"), connections)
        self.assertIn((b + ".outputX", a + ".input1X"), connections)
        self.assertEqual(selection, self.cmds.ls(selection=True))
        self.assertEqual(evaluation, self.cmds.cycleCheck(query=True, evaluation=True))
        self.assertIn(a, formatReport(result))
        self.assertFalse(any(group["errors"] for group in result["groups"]))
        self.assertTrue(inspectCycles([a + ".input1X"], first_only=True)["groups"])

    def test_clean_node(self):
        """循環のないノードでは結果が空になる。"""
        from HTools.rigging.inspectCycles import inspectCycles
        self.assertEqual([], inspectCycles([self.createNode("multiplyDivide")])["groups"])

    def test_dag_cycle(self):
        """子のワールド行列が親へ戻る循環をDAG込みで検出する。"""
        from HTools.rigging.inspectCycles import inspectCycles
        parent, child = self.createNode("transform"), self.createNode("transform")
        matrix = self.createNode("decomposeMatrix")
        self.cmds.parent(child, parent)
        self.cmds.connectAttr(child + ".worldMatrix[0]", matrix + ".inputMatrix")
        self.cmds.connectAttr(matrix + ".outputTranslate", parent + ".translate")
        result = inspectCycles([parent], include_dag=True)
        self.assertTrue(result["groups"])
        self.assertTrue(any(group["parents"] for group in result["groups"]))
        self.assertFalse(any(group["errors"] for group in result["groups"]))

    def test_invalid_input_does_not_scan(self):
        """空選択や不正時間が全体検索へ流れない。"""
        from HTools.rigging.inspectCycles import inspectCycles
        with mock.patch("hlib.scene.cycle.cmds.cycleCheck") as scan:
            for targets, seconds in [([], 10), (None, 0), (None, float("nan"))]:
                with self.assertRaises(ValueError):
                    inspectCycles(targets, seconds=seconds)
            scan.assert_not_called()

    def test_multiple_paths(self):
        """複数の独立した循環を区切り付きで取得する。"""
        from HTools.rigging.inspectCycles import inspectCycles
        nodes = [self.createNode("multiplyDivide") for _ in range(2)]
        for node in nodes:
            self.cmds.connectAttr(node + ".outputX", node + ".input1X")
        result = inspectCycles(nodes)
        detected = {name for group in result["groups"] for name in group["nodes"]}
        self.assertEqual(set(nodes), detected)
        self.assertGreaterEqual(len(result["groups"]), 2)

    def test_cycle_wrappers_and_live_connections(self):
        """経路は型と順序を保持し、照会は接続変更と改名に追従する。"""
        from hlib.scene import Cycle
        from hlib.plugs import Plug
        from hlib.nodes import Node
        a, b = self.createNode("multiplyDivide"), self.createNode("multiplyDivide")
        self.cmds.connectAttr(a + ".outputX", b + ".input1X")
        self.cmds.connectAttr(b + ".outputX", a + ".input1X")
        cycles = Cycle.find(Node(a))
        self.assertTrue(cycles)
        self.assertTrue(all(isinstance(c, Cycle) for c in cycles))
        cycle = Cycle([a + ".outputX", b + ".input1X"])
        self.assertIsInstance(cycle.plugs, tuple)
        self.assertTrue(all(isinstance(p, Plug) for p in cycle.plugs))
        self.assertEqual([p.fullName() for p in cycle.plugs], [a + ".outputX", b + ".input1X"])
        self.assertEqual(len(cycle.getConnections()), 1)
        self.cmds.disconnectAttr(a + ".outputX", b + ".input1X")
        self.assertEqual(cycle.getConnections(), [])
        renamed = self.cmds.rename(a, "renamedCycleTest#")
        self.nodes[0] = renamed
        self.assertEqual(cycle.plugs[0].fullName(), renamed + ".outputX")
        self.assertTrue(Cycle.find(cycle.plugs[0]) == [])

    def test_live_parent_wrappers(self):
        """親子関係をNodeで返し、付け替え後は現在の関係を返す。"""
        from hlib.scene import Cycle
        from hlib.nodes import DagNode
        parent, child = self.createNode("transform"), self.createNode("transform")
        self.cmds.parent(child, parent)
        cycle = Cycle([child + ".translateX"])
        pairs = cycle.getParents()
        self.assertEqual(len(pairs), 1)
        self.assertTrue(all(isinstance(n, DagNode) for n in pairs[0]))
        self.assertEqual(pairs[0][0].name(), parent)
        self.cmds.parent(child, world=True)
        self.assertEqual(cycle.getParents(), [])


def runTests():
    """テストを実行して結果を返す。"""
    return unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CycleInspectorTest))


if __name__ == "__main__":
    import maya.standalone
    maya.standalone.initialize(name="python")
    try:
        success = runTests().wasSuccessful()
    finally:
        maya.standalone.uninitialize()
    sys.exit(0 if success else 1)

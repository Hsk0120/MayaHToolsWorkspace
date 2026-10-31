"""乱数で選んだ mlib の編集を続けて行い、1操作 = 1回のUndo で全部戻り、Redo で全部やり直せることを確かめる。

単体の Undo 検査(test_undo_coverage)では見えない、続けて行ったときの名前・親子・接続の食い違いを探す。
シーンの状態は、名前空間内のノードの完全パス・型・主なアトリビュートの値・接続で比べる。
"""

import random
import sys
import unittest

import maya.cmds as cmds

import mlib
mlib.reload()
from support.specCase import NamespaceCase

#: 1シナリオあたりの操作数。
STEPS = 40

#: シナリオ数(シードの数)。
SCENARIOS = 6

#: 比べるアトリビュート。
ATTRIBUTES = ("translate", "rotate", "scale", "visibility", "rotateOrder")


class UndoSequenceStressTest(NamespaceCase):
    """連続した編集のUndo・Redo。"""

    PREFIX = "mlibUndoStress_"

    def snapshot(self):
        """名前空間内のノード・値・接続を比べられる形で返す。"""
        nodes = sorted(cmds.ls(self.ns + ":*", long=True) or [])
        state = []
        for node in nodes:
            entry = [node, cmds.nodeType(node)]
            if cmds.objectType(node, isAType="transform"):
                for attribute in ATTRIBUTES:
                    value = cmds.getAttr(node + "." + attribute)
                    entry.append((attribute, [round(v, 6) for v in value[0]] if isinstance(value, list) else value))
            for attribute in cmds.listAttr(node, userDefined=True) or []:
                entry.append(("user", attribute, cmds.getAttr(node + "." + attribute)))
            keys = cmds.keyframe(node, query=True, timeChange=True) or []
            entry.append(("keys", [round(v, 6) for v in keys]))
            state.append(entry)
        connections = sorted(
            tuple(pair) for node in nodes
            for pair in zip(*[iter(cmds.listConnections(node, source=True, destination=False, plugs=True,
                                                        connections=True) or [])] * 2)
        )
        return state, connections

    def transforms(self):
        """名前空間内のTransform(シェイプ・joint以外)のラッパーを返す。"""
        names = cmds.ls(self.ns + ":*", type="transform", long=True) or []
        return [mlib.getNode(name) for name in names if cmds.nodeType(name) == "transform"]

    def step(self, rng, index):
        """乱数で1つの編集を選んで実行する。実行しなかった場合はFalse。"""
        nodes = self.transforms()
        kind = rng.choice(("create", "create", "parent", "move", "rotate", "attr", "connect", "key", "rename",
                           "curve", "delete", "shape"))
        if kind == "create" or not nodes:
            parent = rng.choice(nodes) if nodes and rng.random() < 0.5 else None
            mlib.createNode("transform", name=self.name("n%d" % index), parent=parent, skipSelect=True)
            return True
        node = rng.choice(nodes)
        if not node.isValid():
            return False
        if kind == "parent":
            others = [other for other in nodes if other != node and not node.isAncestorOf(other)]
            target = rng.choice(others) if others and rng.random() < 0.7 else None
            if target is None and node.getParent() is None:
                return False
            node.setParent(target)
        elif kind == "move":
            node.setTranslation([rng.uniform(-5, 5) for _ in range(3)], worldSpace=rng.random() < 0.5, safe=True)
        elif kind == "rotate":
            node.setRotate([rng.uniform(-90, 90) for _ in range(3)], worldSpace=rng.random() < 0.5, safe=True)
        elif kind == "attr":
            name = "extra%d" % index
            node.addAttr(longName=name, attributeType="double", defaultValue=rng.uniform(0, 1))
        elif kind == "connect":
            others = [other for other in nodes if other != node]
            if not others:
                return False
            target = rng.choice(others).getPlug(rng.choice(("tx", "ty", "tz")))
            if target.getSource() is not None or target.isLocked():
                return False
            node.getPlug(rng.choice(("tx", "ty", "tz"))).connectTo(target)
        elif kind == "key":
            if any(node.getPlug(name).getSource() is not None for name in ("tx", "ry")):
                return False
            node.setKey(["tx", "ry"], time=rng.randrange(1, 50))
        elif kind == "rename":
            node.rename(self.name("r%d" % index))
        elif kind == "curve":
            mlib.createCurve([(0, 0, 0), (rng.uniform(1, 3), 0, 0)], name=self.name("c%d" % index), parent=node)
        elif kind == "delete":
            if node.getChildren(allDescendents=True):
                return False
            mlib.delete(node)
        elif kind == "shape":
            curves = [other for other in nodes if other.getShapes() and other != node]
            if not curves:
                return False
            curves[0].getShapes()[0].setParent(node)
        return True

    def test_each_step_undo_and_redo_in_sequence(self):
        """続けて行う各操作が、1回のUndoで直前の状態へ、Redoで操作後の状態へ戻る。"""
        for seed in range(SCENARIOS):
            rng = random.Random(100 + seed)
            for index in range(STEPS):
                before = self.snapshot()
                cmds.flushUndo()
                if not self.step(rng, seed * 1000 + index):
                    continue
                name = cmds.undoInfo(query=True, undoName=True)
                after = self.snapshot()
                if after == before:
                    continue
                with self.subTest(seed=seed, step=index, chunk=name):
                    cmds.undo()
                    self.assertEqual(self.snapshot(), before, "undo " + name)
                    self.assertTrue(cmds.undoInfo(query=True, undoQueueEmpty=True), "more than one chunk: " + name)
                    cmds.redo()
                    self.assertEqual(self.snapshot(), after, "redo " + name)
            cmds.delete(cmds.ls(self.ns + ":*") or [])

    def test_undo_all_and_redo_all(self):
        """各シナリオで、全操作をUndoすると最初の状態、全部Redoすると最後の状態に戻る。"""
        for seed in range(SCENARIOS):
            with self.subTest(seed=seed):
                rng = random.Random(100 + seed)
                # Undoの履歴の長さに上限があると古い操作から捨てられるため、この検査では無制限にする。
                infinity = cmds.undoInfo(query=True, infinity=True)
                cmds.undoInfo(state=True, infinity=True)
                self.addCleanup(cmds.undoInfo, infinity=infinity)
                cmds.flushUndo()
                start = self.snapshot()
                log = []
                for index in range(STEPS):
                    if self.step(rng, seed * 1000 + index):
                        log.append(cmds.undoInfo(query=True, undoName=True))
                end = self.snapshot()
                # 値が変わらない操作はUndoへ積まれないため、回数ではなくキューが空になるまで戻す。
                while not cmds.undoInfo(query=True, undoQueueEmpty=True):
                    cmds.undo()
                self.assertEqual(self.snapshot(), start, "undo all: " + ", ".join(log))
                while not cmds.undoInfo(query=True, redoQueueEmpty=True):
                    cmds.redo()
                self.assertEqual(self.snapshot(), end, "redo all")
                cmds.delete(cmds.ls(self.ns + ":*") or [])

if __name__ == "__main__":
    result = unittest.main(exit=False, verbosity=1).result
    sys.exit(0 if result.wasSuccessful() else 1)

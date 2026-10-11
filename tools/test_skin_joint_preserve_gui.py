"""隔離Maya GUI専用のscriptJob子保持テスト。通常のユーザーGUIへ送信しない。"""

import json
import os
import sys
import traceback
from pathlib import Path

import maya.cmds as cmds
import maya.mel as mel

ROOT = Path(__file__).resolve().parents[1]
RESULT = Path(os.environ.get("HTOOLS_PRESERVE_GUI_RESULT",
                             str(ROOT / ".maya-output/preserve-children-gui/result.json")))


def run():
    """専用GUIのidle境界を挟み、補正とUndo/Redoを実イベントで確認する。"""
    if os.environ.get("HTOOLS_PRESERVE_GUI_TEST") != "1":
        raise RuntimeError("Run only in the isolated GUI test process.")
    sys.path.insert(0, str(ROOT / "maya/inhouse"))
    from HTools.rigging import editSkinJoints as tool
    cmds.file(new=True, force=True)
    cmds.undoInfo(state=True)
    parent = cmds.joint(position=(0, 0, 0))
    child = cmds.joint(position=(0, 3, 0))
    tip = cmds.joint(position=(2, 5, 0))
    cmds.setAttr(child + ".rotate", 12, -20, 7)
    cmds.select(parent)
    tool.run()
    tool.setPreserveChildren(True)
    baseline = [cmds.xform(j, query=True, worldSpace=True, matrix=True) for j in (child, tip)]
    checks = []

    def checkChildren():
        """子と孫のワールド行列を確認する。"""
        for j, matrix in zip((child, tip), baseline):
            actual = cmds.xform(j, query=True, worldSpace=True, matrix=True)
            assert max(abs(a-b) for a, b in zip(actual, matrix)) < 1e-7, (j, actual, matrix)

    def edit():
        """Channel Boxと同じアトリビュート編集を行う。"""
        cmds.setAttr(parent + ".jointOrientY", 35)

    def checkEdit():
        """idle処理後の子保持を確認する。"""
        checkChildren()
        assert abs(cmds.getAttr(parent + ".jointOrientY") - 35) < 1e-7
        checks.append("jointOrient child preservation")
        cmds.undo()

    def checkUndo():
        """1回のUndoで親の編集と子の補正が戻ることを確認する。"""
        checkChildren()
        assert abs(cmds.getAttr(parent + ".jointOrientY")) < 1e-7
        checks.append("single Undo")
        cmds.redo()

    def checkRedo():
        """Redoで補正状態が再現されることを確認する。"""
        checkChildren()
        assert abs(cmds.getAttr(parent + ".jointOrientY") - 35) < 1e-7
        checks.append("Redo")
        cmds.setAttr(parent + ".jointOrientX", -22)

    def repeated():
        """連続編集でも初期の子姿勢を保持する。"""
        checkChildren()
        checks.append("repeated edit")
        tool.setPreserveChildren(False)
        cmds.setAttr(parent + ".jointOrientZ", 40)

    def disabled():
        """終了後に補正が行われないことを確認する。"""
        actual = cmds.xform(child, query=True, worldSpace=True, matrix=True)
        assert max(abs(a-b) for a,b in zip(actual, baseline[0])) > 0.01
        checks.append("disabled")
        tool.setPreserveChildren(True)
        cmds.select(child)

    saved_tip = []

    def newSelection():
        """選択変更で新しい親子の監視へ切り替わることを確認する。"""
        saved_tip[:] = cmds.xform(tip, query=True, worldSpace=True, matrix=True)
        cmds.setAttr(child + ".jointOrientZ", 19)

    def selectionResult():
        """新しい選択の子保持を確認し、UIを再生成する。"""
        actual = cmds.xform(tip, query=True, worldSpace=True, matrix=True)
        assert max(abs(a-b) for a,b in zip(actual, saved_tip)) < 1e-7
        checks.append("selection change")
        tool.run()
        cmds.setAttr(child + ".jointOrientX", 14)

    def reopenResult():
        """再表示後の保持とUI削除時の監視解放を確認する。"""
        actual = cmds.xform(tip, query=True, worldSpace=True, matrix=True)
        assert max(abs(a-b) for a,b in zip(actual, saved_tip)) < 1e-7
        checks.append("window reopen")
        cmds.deleteUI(tool._WINDOW)
        cmds.setAttr(child + ".jointOrientY", 31)

    def closedResult():
        """UI削除後は補正が残らないことを確認する。"""
        actual = cmds.xform(tip, query=True, worldSpace=True, matrix=True)
        assert max(abs(a-b) for a,b in zip(actual, saved_tip)) > 0.01
        checks.append("window cleanup")
        assert tool._owner() is None
        assert not tool._recoveryFolder().joinpath(str(os.getpid()) + ".json").exists()
        # 生存する別プロセスの記録と、クラッシュを模した終了済みプロセスの記録を分ける。
        folder = tool._recoveryFolder()
        folder.mkdir(parents=True, exist_ok=True)
        stale = folder / "stale-test.json"
        stale.write_text(json.dumps(dict(pid=2147483647, contexts=[False, False, False])), encoding="utf-8")
        other = folder / "other-process-test.json"
        other.write_text(json.dumps(dict(pid=(4 if os.name == "nt" else 1), contexts=[True, True, True])), encoding="utf-8")
        tool.run()
        assert tool.getPreserveChildren() == [False, False, False]
        assert not stale.exists()
        if tool._processAlive(4 if os.name == "nt" else 1):
            assert other.exists()
        other.unlink(missing_ok=True)
        checks.append("stale journal recovery / other process isolation")
        tool.setPreserveChildren(True)
        assert tool.getPreserveChildren() == [True, True, True]
        first_owner = tool._owner()
        first_jobs = cmds.scriptJob(listJobs=True)
        import importlib
        import runpy
        importlib.reload(tool)
        tool.run()
        runpy.run_path(str(ROOT / "maya/inhouse/HTools/rigging/editSkinJoints.py"), run_name="__main__")
        assert tool._owner() is first_owner
        assert cmds.scriptJob(listJobs=True) == first_jobs
        checks.append("singleton across reload and runpy")
        cmds.deleteUI(tool._WINDOW)
        assert tool.getPreserveChildren() == [False, False, False]
        assert first_owner.closed and not first_owner.callbacks
        assert first_owner.preserver.stopped
        assert not first_owner.preserver.jobs and not first_owner.preserver.events
        assert not first_owner.preserver.callbacks
        checks.append("context restoration and callback cleanup")

    skin_state = {}

    def skinLifecycle():
        """閉じる・保存・再開でenvelopeを無効なまま残さないことを確認する。"""
        cmds.select(clear=True)
        joint = cmds.joint(position=(8, 0, 0))
        mesh = cmds.polyCube()[0]
        skin = cmds.skinCluster(joint, mesh, toSelectedBones=True)[0]
        skin_state.update(joint=joint, skin=skin)
        cmds.setAttr(skin + ".envelope", 0.65)
        cmds.select(joint)
        tool.run()
        tool.beginEdit()
        cmds.setAttr(joint + ".jointOrientY", 12)
        cmds.deleteUI(tool._WINDOW)
        assert abs(cmds.getAttr(skin + ".envelope") - 0.65) < 1e-7
        assert tool._readSession()["paused"]
        assert abs(cmds.getAttr(joint + ".jointOrientY") - 12) < 1e-7
        tool.run()
        tool.beginEdit()
        assert cmds.getAttr(skin + ".envelope") == 0
        tool.setPreserveChildren(True)
        scene = RESULT.parent / "safe-save.ma"
        cmds.file(rename=str(scene))
        cmds.file(save=True, type="mayaAscii", force=True)
        assert tool._readSession()["paused"]
        assert abs(cmds.getAttr(skin + ".envelope") - 0.65) < 1e-7
        assert not tool._owner().enabled
        cmds.file(str(scene), open=True, force=True)
        assert tool._readSession()["paused"]
        assert abs(cmds.getAttr(skin + ".envelope") - 0.65) < 1e-7
        tool.beginEdit()
        tool.finishEdit()
        assert not cmds.objExists(tool._SESSION)
        checks.append("close pauses envelopes / save pauses / reopen and resume")

    def matchSteps(command, hierarchy):
        """標準メニューの実コマンドを、選択構成ごとにidleを挟んで検証する。"""
        state = {}

        def matrices(nodes):
            """対象のワールド行列を読み取る。"""
            return {node: cmds.xform(node, query=True, worldSpace=True, matrix=True)
                    for node in nodes}

        def check(expected):
            """誤差を含めて行列を比較する。"""
            for node, matrix in expected.items():
                actual = matrices([node])[node]
                error = max(abs(a - b) for a, b in zip(actual, matrix))
                assert error < 1e-6, (command, hierarchy, node, error)

        def checkAttrs(actual, expected):
            """Undo時の浮動小数点丸めを許容し、ピボットを含む編集値を比較する。"""
            if isinstance(expected, (list, tuple)):
                assert len(actual) == len(expected)
                for a, b in zip(actual, expected):
                    checkAttrs(a, b)
            else:
                assert abs(actual - expected) < 1e-6, (command, hierarchy, actual, expected)

        def setup():
            """編集対象・未編集の子孫・Matchの参照を独立したシーンに作る。"""
            cmds.file(new=True, force=True)
            cmds.select(clear=True)
            a = cmds.joint(name="matchRoot", position=(0, 0, 0))
            b = cmds.joint(name="matchChild", position=(0, 3, 0))
            c = cmds.joint(name="matchTip", position=(2, 5, 0))
            f = cmds.joint(name="matchLeaf", position=(3, 7, 1))
            cmds.select(clear=True)
            d = cmds.joint(name="otherRoot", position=(-4, 0, 0))
            e = cmds.joint(name="otherChild", position=(-4, 3, 0))
            target = cmds.createNode("transform", name="matchReference")
            cmds.setAttr(target + ".translate", 5, 2, -3)
            cmds.setAttr(target + ".rotate", 20, -35, 17)
            cmds.setAttr(target + ".scale", 1.3, 0.8, 1.1)
            cmds.xform(target, pivots=(1, 2, -1))
            sources = {"single": [a], "multiple": [a, d],
                       "parent-child": [a, b], "ancestor-descendant": [a, c]}[hierarchy]
            preserved = [node for node in (b, c, e, f) if node not in sources]
            state.update(sources=sources, preserved=matrices(preserved),
                         before=matrices(sources), reference=matrices([target]))
            tool.run()
            tool.setPreserveChildren(True)
            state["beforeAttrs"] = [tool._owner().preserver.signature(node) for node in sources]
            cmds.select(sources + [target])

        def apply():
            """選択通知後に標準Matchを実行し、補正前の直接編集結果を保存する。"""
            mel.eval(command + ";")
            state["matched"] = matrices(state["sources"])
            state["matchedAttrs"] = [tool._owner().preserver.signature(node) for node in state["sources"]]
            if command != "MatchPivots":
                assert state["beforeAttrs"] != state["matchedAttrs"], (command, "No attributes changed")
                assert any(max(abs(a - b) for a, b in zip(state["before"][node], matrix)) > 0.01
                           for node, matrix in state["matched"].items())

        def applied():
            """子保持・Match結果・参照不変を確認して1回Undoする。"""
            check(state["preserved"])
            check(state["matched"])
            check(state["reference"])
            state["preservedAttrs"] = [tool._owner().preserver.signature(node) for node in state["sources"]]
            state["undoName"] = cmds.undoInfo(query=True, undoName=True)
            cmds.undo()
            state["immediateUndo"] = matrices(list(state["before"]) + list(state["preserved"]))

        def undone():
            """単一Undoで編集前へ戻ることを確認してRedoする。"""
            (RESULT.parent / "match-diagnostic.json").write_text(
                json.dumps(dict(command=command, hierarchy=hierarchy, state=state,
                                afterIdle=matrices(list(state["before"]) + list(state["preserved"])))),
                encoding="utf-8")
            check(state["preserved"])
            check(state["before"])
            checkAttrs([tool._owner().preserver.signature(node) for node in state["sources"]], state["beforeAttrs"])
            cmds.redo()

        def redone():
            """Redoでも子保持とMatch結果が両立することを確認する。"""
            check(state["preserved"])
            check(state["matched"])
            checkAttrs([tool._owner().preserver.signature(node) for node in state["sources"]], state["preservedAttrs"])
            node = state["sources"][0]
            cmds.setAttr(node + ".translateX", cmds.getAttr(node + ".translateX") + 1)
            state["second"] = matrices(state["sources"])

        def secondApplied():
            """次の直接編集も子を保持することを確認し、Undoを開始する。"""
            check(state["preserved"])
            check(state["second"])
            cmds.undo()

        def backFirst():
            """2操作目を戻して、さらにMatchをUndoする。"""
            check(state["preserved"])
            check(state["matched"])
            cmds.undo()

        def backOriginal():
            """連続Undoの到達点を確認し、MatchをRedoする。"""
            check(state["preserved"])
            check(state["before"])
            cmds.redo()

        def redoFirst():
            """補正で残りのRedo履歴が消失しないことを確認する。"""
            check(state["preserved"])
            check(state["matched"])
            assert not cmds.undoInfo(query=True, redoQueueEmpty=True), (command, hierarchy, "Redo queue lost")
            cmds.redo()

        def redoSecond():
            """連続Redoでも直接編集と子保持が再現することを確認する。"""
            check(state["preserved"])
            check(state["second"])
            checks.append(command + " / " + hierarchy + " / two Undo / two Redo")

        return setup, apply, applied, undone, redone, secondApplied, backFirst, backOriginal, redoFirst, redoSecond

    actions = [edit, checkEdit, checkUndo, checkRedo, repeated, disabled,
               newSelection, selectionResult, reopenResult, closedResult, skinLifecycle]
    for command in ("MatchTranslation", "MatchRotation", "MatchScaling", "MatchTransform", "MatchPivots"):
        for hierarchy in ("single", "multiple", "parent-child", "ancestor-descendant"):
            actions.extend(matchSteps(command, hierarchy))

    animation = {}

    def animationSetup():
        """時間変更による親のアニメーションを直接編集と区別するシーンを作る。"""
        cmds.file(new=True, force=True)
        cmds.select(clear=True)
        root = cmds.joint()
        leaf = cmds.joint(position=(2, 3, 0))
        cmds.setKeyframe(root, attribute="rotateY", time=0, value=0)
        cmds.setKeyframe(root, attribute="rotateY", time=10, value=45)
        cmds.currentTime(0)
        animation.update(root=root, leaf=leaf, local=cmds.getAttr(leaf + ".matrix"),
                         world=cmds.getAttr(leaf + ".worldMatrix[0]"))
        cmds.select(root)
        tool.run()
        tool.setPreserveChildren(True)

    def changeTime():
        """通常のフレーム変更を行う。"""
        cmds.currentTime(10)

    def afterTime():
        """子がアニメーションには追従し、ローカル値を補正されないことを確認する。"""
        leaf = animation["leaf"]
        assert max(abs(a - b) for a, b in zip(animation["local"], cmds.getAttr(leaf + ".matrix"))) < 1e-7
        current = cmds.getAttr(leaf + ".worldMatrix[0]")
        assert max(abs(a - b) for a, b in zip(animation["world"], current)) > 0.1
        animation["world"] = current
        cmds.setAttr(animation["root"] + ".jointOrientZ", 15)

    def afterTimeEdit():
        """フレーム変更後の直接編集には、新しい姿勢を基準に補正が働く。"""
        current = cmds.getAttr(animation["leaf"] + ".worldMatrix[0]")
        assert max(abs(a - b) for a, b in zip(animation["world"], current)) < 1e-7
        checks.append("animation follows time / direct edit preserves new pose")

    actions.extend((animationSetup, changeTime, afterTime, afterTimeEdit))
    steps = iter(actions)

    def step():
        """次の検証をidleに実行し、結果をファイルへ保存する。"""
        try:
            action = next(steps)
        except StopIteration:
            RESULT.write_text(json.dumps(dict(ok=True, checks=checks)), encoding="utf-8")
            cmds.quit(force=True)
            return
        try:
            (RESULT.parent / "progress.json").write_text(
                json.dumps(dict(pid=os.getpid(), step=action.__name__, checks=checks)), encoding="utf-8")
            action()
        except Exception:
            RESULT.write_text(json.dumps(dict(ok=False, checks=checks,
                                              error=traceback.format_exc())), encoding="utf-8")
            cmds.quit(force=True)
            return
        cmds.evalDeferred(step, lowestPriority=True)

    cmds.evalDeferred(step, lowestPriority=True)


if __name__ == "__main__":
    cmds.evalDeferred(run, lowestPriority=True)

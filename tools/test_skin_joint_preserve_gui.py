"""隔離Maya GUI専用のscriptJob子保持テスト。通常のユーザーGUIへ送信しない。"""

import json
import os
import sys
import traceback
from pathlib import Path

import maya.cmds as cmds

ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / ".maya-output/preserve-children-gui/result.json"


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

    steps = iter((edit, checkEdit, checkUndo, checkRedo, repeated, disabled,
                  newSelection, selectionResult, reopenResult, closedResult, skinLifecycle))

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

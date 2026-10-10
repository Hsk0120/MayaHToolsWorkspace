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
    tool.setPreserveChildren(True)
    tool.run()
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

    steps = iter((edit, checkEdit, checkUndo, checkRedo, repeated, disabled,
                  newSelection, selectionResult, reopenResult, closedResult))

    def step():
        """次の検証をidleに実行し、結果をファイルへ保存する。"""
        try:
            action = next(steps)
        except StopIteration:
            RESULT.write_text(json.dumps(dict(ok=True, checks=checks)), encoding="utf-8")
            cmds.quit(force=True)
            return
        try:
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

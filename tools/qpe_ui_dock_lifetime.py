"""専用Mayaで共有親の不変性と削除・即再生成の寿命を検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "maya/inhouse/QuickPathExplorer/python"))
sys.path.insert(0, str(ROOT / "tools"))
from qpeQt import QtCore, QtWidgets, shiboken
from qpe_ui_maya import pause


def state(widget):
    """比較用にサイズ制約を値として取得する。"""
    policy = widget.sizePolicy()
    return {"horizontal": str(policy.horizontalPolicy()), "vertical": str(policy.verticalPolicy()),
            "minimum": [widget.minimumWidth(), widget.minimumHeight()]}


def main(output_dir, finished):
    """他エディターを残してQPEを再生成し、遅延破棄後まで確認する。"""
    from maya import cmds
    import qpeDock
    import qpeHost
    out = Path(output_dir)
    os.environ["QPE_SETTINGS_FILE"] = str(out / "settings.json")
    errors = []
    old_hook = sys.excepthook
    sys.excepthook = lambda *info: errors.append("".join(traceback.format_exception(*info)))
    result = {"status": "passed", "errors": errors}

    def save():
        """途中結果も残し、失敗した段階を特定できるようにする。"""
        (out / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        # Mayaが所有する共有タブと実際のQPEで確認する。
        app = QtWidgets.QApplication.instance()
        original_style = int(shiboken.getCppPointer(app.style())[0])
        editor = qpeHost.show(str(out))
        pause(700)
        peers = ["qpeProbePeerA", "qpeProbePeerB"]
        for peer in peers:
            cmds.workspaceControl(peer, label=peer, floating=True, loadImmediately=True)
            cmds.setParent(peer)
            cmds.columnLayout()
            cmds.textField(text="Independent editor")
        cmds.workspaceControl(peers[0], edit=True, dockToMainWindow=("right", False))
        cmds.workspaceControl(peers[1], edit=True, tabToControl=(peers[0], -1))
        cmds.workspaceControl(qpeHost.CONTROL, edit=True, tabToControl=(peers[0], -1))
        pause(900)
        watcher = qpeDock._watcher
        tab = editor.parentWidget()
        while tab is not None and not isinstance(tab, QtWidgets.QTabWidget):
            tab = tab.parentWidget()
        result["watchedAncestors"] = [type(w).__name__ + ":" + w.objectName() for w in watcher.targets if shiboken.isValid(w)]
        result["tabFound"] = tab is not None
        assert tab is not None, "Shared Maya tab was not created"
        if tab is not None:
            qpe_index = next(i for i in range(tab.count()) if tab.widget(i).isAncestorOf(editor))
            other_index = next(i for i in range(tab.count()) if i != qpe_index)
            tab.setCurrentIndex(other_index)
            pause(600)
            result["peerSettled"] = state(tab)
            tab.setCurrentIndex(qpe_index)
            pause(600)
            result["qpeActive"] = state(tab)
            assert result["qpeActive"] == result["peerSettled"], "Shared tab constraints changed"
            assert set(watcher.targets) == {editor, watcher.control}, "Shared parent is monitored"
            tab.setCurrentIndex(other_index)
            result["peerImmediatelyAfterSwitch"] = state(tab)
            pause(600)
            result["peerAfterDelay"] = state(tab)
            tab.setCurrentIndex(qpe_index)
            pause(600)
            cmds.deleteUI(qpeHost.CONTROL)
            pause(700)
            result["oldTabAliveAfterDelete"] = shiboken.isValid(tab)
            if shiboken.isValid(tab):
                result["peerAfterQpeDelete"] = state(tab)
            result["watcherAliveAfterDelete"] = shiboken.isValid(watcher)
            result["controlExistsAfterDelete"] = cmds.workspaceControl(qpeHost.CONTROL, exists=True)
            result["editorAliveAfterDelete"] = shiboken.isValid(editor)
            replacement = qpeHost.show(str(out))
            pause(900)
            result["regeneration"] = {
                "newEditor": replacement is not editor,
                "watcherReused": qpeDock._watcher is watcher,
                "watcherTracksNewEditor": qpeDock._watcher.widget is replacement,
                "oldEditorAlive": shiboken.isValid(editor),
                "oldEditorVisible": editor.isVisible() if shiboken.isValid(editor) else None,
                "oldEditorParent": editor.parentWidget().objectName() if shiboken.isValid(editor) and editor.parentWidget() else None,
                "oldWatcherTargets": [w.objectName() for w in qpeDock._watcher.targets if shiboken.isValid(w)],
            }
            assert replacement is not editor
            assert qpeDock._watcher is not watcher
            assert qpeDock._watcher.widget is replacement
            if shiboken.isValid(watcher):
                assert not watcher.active and not watcher.targets
                watcher.flush()  # 古い通知が来ても新画面の状態へ作用しない。
                watcher.restorePlacement()
            replacement._dockViewport.grab().save(str(out / "regenerated.png"))
            # MayaのuiScriptが同名の新controlを先に作った経路でも旧内容を返さない。
            old_generation = qpeDock._closeGeneration
            cmds.deleteUI(qpeHost.CONTROL)
            cmds.workspaceControl(qpeHost.CONTROL, label="QPE restored control", floating=True,
                                  retain=True, loadImmediately=True,
                                  uiScript="import qpeHost; qpeHost.restore()")
            restored = qpeHost._window
            assert restored is not replacement
            assert qpeDock._control_widget(qpeHost.CONTROL).isAncestorOf(restored)
            assert qpeDock._watcher.widget is restored
            # 削除で保存されたclosed状態は標準復元で維持される。明示表示で開く。
            assert qpeHost.show() is restored
            current_watcher = qpeDock._watcher
            qpeDock.closed(old_generation)
            assert qpeDock._watcher is current_watcher and current_watcher.active
            result["uiScriptRecreation"] = "new control receives new content and watcher"
        result["applicationStyleUnchanged"] = original_style == int(shiboken.getCppPointer(app.style())[0])
        assert result["applicationStyleUnchanged"]
        save()

        # 同じDockWatcherを制御可能な共有Qtタブでも試し、Mayaの再生成と区別する。
        shared = QtWidgets.QTabWidget()
        shared.setMinimumSize(430, 310)
        peer = QtWidgets.QLineEdit("Independent tool")
        dummy = QtWidgets.QWidget()
        dummy._dockViewport = QtWidgets.QScrollArea(dummy)
        dummy._dockViewport.setMinimumSize(240, 160)
        shared.addTab(peer, "Peer")
        shared.addTab(dummy, "QPE surrogate")
        shared.setCurrentIndex(1)
        shared.show()
        before = state(shared)
        controlled = qpeDock.DockWatcher(dummy)
        controlled.timer.stop()
        active = state(shared)
        dummy.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(dummy, QtCore.QEvent.DeferredDelete)
        pause(100)
        after = state(shared)
        result["controlledDestruction"] = {"before": before, "qpeActive": active, "after": after,
            "watcherDestroyed": not shiboken.isValid(controlled), "peerAlive": shiboken.isValid(peer),
            "sharedConstraintsLeaked": after != before}
        assert before == active == after, "Shared constraints leaked after destruction"
        assert not shiboken.isValid(controlled)
        assert shiboken.isValid(peer)
        shared.close()
        shared.deleteLater()
        for peer_name in peers:
            cmds.deleteUI(peer_name)
    except Exception:
        result["status"] = "error"
        result["error"] = traceback.format_exc()
    def finish_after_event_loop():
        """通常ループが旧Qtを破棄した後、新監視の生存と同一性を判定する。"""
        # 一連の操作を抜け、通常イベントループが遅延破棄を処理した後も記録する。
        current = qpeDock._watcher
        result["afterOuterEventLoop"] = {
            "watcherAlive": current is not None and shiboken.isValid(current),
            "currentEditorAlive": qpeHost._window is not None and shiboken.isValid(qpeHost._window),
            "watcherTracksCurrentEditor": current is not None and current.widget is qpeHost._window,
        }
        if (not all(result["afterOuterEventLoop"].values()) or errors):
            result["status"] = "error"
        if result["status"] == "passed":
            try:
                retained = qpeHost._window
                previous = qpeDock._watcher
                cmds.workspaceControl(qpeHost.CONTROL, edit=True, close=True)
                assert not previous.active and not previous.targets
                previous.flush()
                previous.restorePlacement()
                assert qpeHost.show() is retained
                assert qpeDock._watcher is not previous
                assert qpeDock._watcher.widget is retained
                assert qpeDock._watcher.isCurrent()
                result["closeReopen"] = "same editor, fresh watcher, stale callbacks ignored"
            except Exception:
                result["status"] = "error"
                result["error"] = traceback.format_exc()
        sys.excepthook = old_hook
        save()
        finished(result)
    save()
    QtCore.QTimer.singleShot(700, finish_after_event_loop)

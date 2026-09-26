"""別プロセス間で起動復元・右ドック・閉じた場合の非復元を確認する。"""
import json
import os
from pathlib import Path
import traceback


def main(output_dir, finished):
    """GUIランナーから実行する起動フェーズ別テスト。"""
    from maya import cmds
    import hedit
    from hedit import startup, docking
    result = {'status': 'error', 'checks': []}
    stage = os.environ['HEDIT_SESSION_STAGE']
    try:
        # テストランナーは全userSetupを無効化するため、同じ入口を明示実行する。
        # 通常環境ではscripts/userSetup.pyがこのinitializeを遅延呼出する。
        if stage == 'write':
            host = hedit.show(floating=False)
            cmds.workspaceControl(docking.CONTROL, edit=True, dockToMainWindow=('right', False))
            window = host.editor
            tabs = window.findChild(docking.QtWidgets.QTabWidget)
            tabs.currentWidget().setPlainText('restart_probe = 91')
            tabs.currentWidget().document().setModified(True)
            action_type = getattr(docking.QtWidgets, 'QAction', None)
            if action_type is None:
                from PySide6.QtGui import QAction
                action_type = QAction
            next(a for a in window.findChildren(action_type) if a.text() == 'New MEL tab').trigger()
            tabs.currentWidget().setPlainText('int $restoreMel = 42;')
            tabs.currentWidget().document().setModified(True)
            tabs.setCurrentIndex(0)
            startup.record()
            # 子画面を閉じるとC++側のタブ保存が完了する。ドック自体は保持する。
            window.close()
            cmds.workspaceLayoutManager(save=True)
            assert json.loads(startup.state_path().read_text(encoding='utf-8'))['open']
            result['checks'].append('saved_open_right_dock_and_unsaved_code')
        elif stage == 'read':
            saved = json.loads(startup.state_path().read_text(encoding='utf-8'))
            result['native_workspace_restored_before_initialize'] = docking._host is not None
            startup.initialize()
            assert docking._host is not None, 'Startup did not create hedit'
            assert cmds.workspaceControl(docking.CONTROL, exists=True)
            assert not cmds.workspaceControl(docking.CONTROL, query=True, floating=True)
            window = docking._host.editor
            # 本文が存在するだけでは非表示reporterへの誤挿入を検出できない。
            from maya import OpenMayaUI
            control = docking.wrapInstance(int(OpenMayaUI.MQtUtil.findControl(docking.CONTROL)), docking.QtWidgets.QWidget)
            assert control.isAncestorOf(docking._host), 'Editor host was attached outside workspaceControl'
            assert docking._host.isVisible() and window.isVisible(), 'Restored editor is hidden'
            tabs = window.findChild(docking.QtWidgets.QTabWidget)
            assert tabs.currentWidget().isVisible(), 'Active restored tab is hidden'
            assert tabs.currentWidget().toPlainText() == 'restart_probe = 91'
            assert tabs.count() == 2 and tabs.widget(1).property('language') == 'mel'
            assert tabs.widget(1).toPlainText() == 'int $restoreMel = 42;'
            # 右側に置いたドックを、同じMaya設定フォルダーから復元できたか確認する。
            from maya import OpenMayaUI
            main_window = docking.wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), docking.QtWidgets.QWidget)
            center = docking._host.mapToGlobal(docking.QtCore.QPoint(docking._host.width() // 2, 0)).x()
            assert center > main_window.mapToGlobal(main_window.rect().center()).x(), 'Right dock placement was lost'
            window.grab().save(str(Path(output_dir, 'restored.png')))
            result['checks'].append('startup_restored_right_dock_state_and_code')
            cmds.workspaceControl(docking.CONTROL, edit=True, close=True)
            assert not json.loads(startup.state_path().read_text(encoding='utf-8'))['open']
            cmds.workspaceLayoutManager(save=True)
        else:
            startup.initialize()
            assert not cmds.workspaceControl(docking.CONTROL, exists=True) or not cmds.workspaceControl(docking.CONTROL, query=True, visible=True)
            result['checks'].append('closed_editor_not_reopened')
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)

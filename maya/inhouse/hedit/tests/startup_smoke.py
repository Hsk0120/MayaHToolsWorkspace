"""別プロセス間で、プラグインのロードだけによるWindowメニュー登録・起動復元・右ドック・
閉じた場合の非復元を確認する。"""
import json
import os
from pathlib import Path
import sys
import traceback

MENU_COMMAND = 'hedit -show'
# 復元は次のイベントループ、メニュー登録は同期またはidleで行うため、検証まで待つ。
SETTLE_MS = 2000


def main(output_dir, finished):
    """GUIランナーから実行する起動フェーズ別テスト。"""
    from maya import cmds
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    result = {'status': 'error', 'checks': []}
    stage = os.environ['HEDIT_SESSION_STAGE']

    def done():
        Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
        finished(result)

    def check():
        try:
            _check(stage, output_dir, result)
            result['status'] = 'passed'
        except Exception:
            result['error'] = traceback.format_exc()
        done()

    try:
        result['loaded_before_entry'] = bool(cmds.pluginInfo('hedit', query=True, loaded=True))
        # テストランナーは全userSetupを無効化するため、scripts/userSetup.pyと同じ入口を明示実行する。
        cmds.loadPlugin('hedit')
    except Exception:
        result['error'] = traceback.format_exc()
        done()
        return
    QtCore.QTimer.singleShot(SETTLE_MS, check)


def _check(stage, output_dir, result):
    """``HEDIT_SESSION_STAGE`` の段階ごとの検証を行い、確かめた項目を ``result["checks"]`` に足す。

    Args:
        stage (str): 段階(``write``・``read``・``closed``・``float_write``・``float_read``)。
        output_dir (str): 出力先。
        result (dict): 結果の辞書。
    """
    from maya import cmds, mel, OpenMayaUI
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import hedit_host as host
    assert cmds.menuItem(host.MENU, exists=True), 'Window menu item was not added by plugin load'
    assert cmds.menuItem(host.MENU, query=True, command=True) == MENU_COMMAND
    assert cmds.menuItem(host.MENU, query=True, sourceType=True) == 'mel'
    icon = Path(cmds.menuItem(host.MENU, query=True, image=True))
    assert icon.name == 'hedit.svg' and icon.is_file(), 'Window menu icon is missing: {}'.format(icon)
    result['checks'].append('window_menu_added_by_plugin_load')
    QtWidgets = host.QtWidgets
    if stage == 'write':
        # Windowメニューのクリックと同じコマンド(MEL)で開く。
        mel.eval(cmds.menuItem(host.MENU, query=True, command=True))
        window = host.docked_editor()
        assert window is not None and window.isVisible(), 'Window menu command did not show hedit'
        result['checks'].append('window_menu_command_opened_editor')
        cmds.workspaceControl(host.CONTROL, edit=True, dockToMainWindow=('right', False))
        window = host.editor()
        tabs = window.findChild(QtWidgets.QTabWidget)
        tabs.currentWidget().setPlainText('restart_probe = 91')
        tabs.currentWidget().document().setModified(True)
        action_type = getattr(QtWidgets, 'QAction', None)
        if action_type is None:
            from PySide6.QtGui import QAction
            action_type = QAction
        next(a for a in window.findChildren(action_type) if a.text() == 'New MEL tab').trigger()
        tabs.currentWidget().setPlainText('int $restoreMel = 42;')
        tabs.currentWidget().document().setModified(True)
        tabs.setCurrentIndex(0)
        host.save_state()
        # 子画面を閉じるとC++側のタブ保存が完了する。ドック自体は保持する。
        window.close()
        cmds.workspaceLayoutManager(save=True)
        assert json.loads(host.state_path().read_text(encoding='utf-8'))['open']
        result['checks'].append('saved_open_right_dock_and_unsaved_code')
    elif stage == 'read':
        window = host.docked_editor()
        assert window is not None, 'Plugin load did not restore hedit'
        assert cmds.workspaceControl(host.CONTROL, exists=True)
        assert not cmds.workspaceControl(host.CONTROL, query=True, floating=True)
        # 本文が存在するだけでは非表示reporterへの誤挿入を検出できない。
        control = host.control()
        assert control.isAncestorOf(window), 'Editor was attached outside workspaceControl'
        assert window.isVisible(), 'Restored editor is hidden'
        assert len(host.visible_editors()) == 1
        tabs = window.findChild(QtWidgets.QTabWidget)
        assert tabs.currentWidget().isVisible(), 'Active restored tab is hidden'
        assert tabs.currentWidget().toPlainText() == 'restart_probe = 91'
        assert tabs.count() == 2 and tabs.widget(1).property('language') == 'mel'
        assert tabs.widget(1).toPlainText() == 'int $restoreMel = 42;'
        # 右側に置いたドックを、同じMaya設定フォルダーから復元できたか確認する。
        main_window = host.wrapInstance(int(OpenMayaUI.MQtUtil.mainWindow()), QtWidgets.QWidget)
        center = window.mapToGlobal(window.rect().center()).x()
        assert center > main_window.mapToGlobal(main_window.rect().center()).x(), 'Right dock placement was lost'
        window.grab().save(str(Path(output_dir, 'restored.png')))
        result['checks'].append('plugin_load_restored_right_dock_state_and_code')
        cmds.workspaceControl(host.CONTROL, edit=True, close=True)
        assert not json.loads(host.state_path().read_text(encoding='utf-8'))['open']
        cmds.workspaceLayoutManager(save=True)
    elif stage == 'float_write':
        # フローティングのまま開いて終了する(ドックの配置はMayaのワークスペースへ保存される)。
        mel.eval(cmds.menuItem(host.MENU, query=True, command=True))
        assert cmds.workspaceControl(host.CONTROL, query=True, floating=True)
        host.save_state()
        cmds.workspaceLayoutManager(save=True)
        result['checks'].append('saved_floating_dock')
    elif stage == 'float_read':
        # 必要なプラグインが未ロードのまま起動すると、Mayaは保存済みのフローティングのドックを閉じ、
        # closeCommandを実行する。以前はそこでheditコマンドが無く「Cannot find procedure "hedit"」になった。
        mel.eval(cmds.menuItem(host.MENU, query=True, command=True))
        window = host.docked_editor()
        assert window is not None and window.isVisible(), 'Window menu did not reopen the floating dock'
        text = host.output_text()
        assert 'Cannot find procedure "hedit"' not in text, [line for line in text.splitlines() if 'Error' in line]
        result['checks'].append('floating_dock_restart_without_missing_command_error')
    else:
        assert not cmds.workspaceControl(host.CONTROL, exists=True) or not cmds.workspaceControl(host.CONTROL, query=True, visible=True)
        result['checks'].append('closed_editor_not_reopened')
        # 保存済みの空のドックが残った状態でWindowメニューから開く。表示の瞬間にMayaがuiScriptで
        # 中身を作り直すため、先に画面を入れると破棄されて落ちていた(表示してから入れる)。
        mel.eval(cmds.menuItem(host.MENU, query=True, command=True))
        window = host.docked_editor()
        assert window is not None and window.isVisible(), 'Window menu did not reopen hedit into the saved dock'
        assert len(host.visible_editors()) == 1
        result['checks'].append('window_menu_reopens_into_saved_dock')
        cmds.unloadPlugin('hedit')
        assert not cmds.menuItem(host.MENU, exists=True), 'Window menu item remained after unload'
        result['checks'].append('window_menu_removed_by_unload')

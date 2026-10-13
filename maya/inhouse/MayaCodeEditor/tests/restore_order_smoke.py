"""起動時の順番が入れ替わっても、ドックしたMaya Code Editorが再表示されることを専用GUIで検証する。

Mayaの起動時は、ワークスペースの復元で保存済みのドックが作られ、そのuiScriptがプラグインのロードより前に
動くことがある。そのときuiScriptは「空のドックを後で隠す」をevalDeferredで予約する。0.7.1までは、
予約が実行される前にロードすると、表示されたままの空のドックを「復元済み」とみなして開いていない状態
(``open: false``)を保存し、さらに後から隠されて、そのMayaでも次の起動でも再表示されなかった。

ここでは、プラグインを外した状態で保存済みと同じドック(uiScript付き)を作り、予約の実行前(early)と
実行後(late)にロードして、画面が入り、開いた状態が保存されることを確かめる。uiScriptは、古い版
(保存済みのワークスペースに残っているもの)と今の版の両方で試す。
"""
import json
from pathlib import Path
import sys
import traceback

CONTROL_SCRIPT = '`workspaceControl -exists mayaCodeEditorWorkspaceControl`'
HIDE = 'workspaceControl -e -visible false mayaCodeEditorWorkspaceControl'
UI_SCRIPTS = {
    # 0.7.1まで: 予約した処理は、実行時にロード済みでも空のドックを隠す。
    'legacy': ('if (`pluginInfo -q -loaded mayaCodeEditor`) mayaCodeEditor -restore; '
               'else evalDeferred "if (' + CONTROL_SCRIPT + ') ' + HIDE + '";'),
    # 今の版(src/plugin/dock.cppのkUiScript): 実行時にロード済みなら何もしない。
    'current': ('if (`pluginInfo -q -loaded mayaCodeEditor`) mayaCodeEditor -restore; '
                'else evalDeferred "if (!`pluginInfo -q -loaded mayaCodeEditor` && ' + CONTROL_SCRIPT + ') '
                + HIDE + '";'),
}


def main(output_dir, finished):
    """GUIランナー(``tools/run_mlib_gui_versions.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` と画像の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore
    except ImportError:
        from PySide2 import QtCore
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gui_host as host
    result = {'status': 'error', 'checks': [], 'cases': {}}

    def wait(ms):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    def run_case(script_name, order):
        cmds.loadPlugin('mayaCodeEditor', quiet=True)
        wait(800)
        cmds.mayaCodeEditor(show=True, floating=False)
        wait(800)
        state = Path(cmds.mayaCodeEditor(sessionPath=True)).with_name('ui.json')
        cmds.unloadPlugin('mayaCodeEditor')
        wait(500)
        # 前回は開いていた(アンロードは「閉じた」と記録するので書き戻す)。
        state.write_text(json.dumps({'version': 1, 'open': True, 'floating': False, 'layout': ''}), encoding='utf-8')
        # 保存済みのワークスペースから作り直されたドック。プラグイン未ロードなので、uiScriptが隠す処理を予約する。
        cmds.workspaceControl(host.CONTROL, label='Maya Code Editor', retain=True, loadImmediately=True,
                              uiScript=UI_SCRIPTS[script_name])
        cmds.workspaceControl(host.CONTROL, edit=True, dockToControl=('TimeSlider', 'top'))
        if order == 'late':
            wait(1500)  # 予約した処理が先に動く。
        cmds.loadPlugin('mayaCodeEditor', quiet=True)
        # 復元はMayaの遅延実行の最後に動くので、Mayaが他の処理を待たせていると少し遅れる(2024で約1.5秒)。
        for attempt in range(50):
            wait(200)
            if host.docked_editor() is not None:
                break
        wait(1500)  # 後から隠されないこと(予約済みの処理が動き終わること)も確かめる。
        entry = {
            'visible': cmds.workspaceControl(host.CONTROL, query=True, visible=True),
            'attached': host.docked_editor() is not None,
            'open': json.loads(state.read_text(encoding='utf-8')).get('open'),
        }
        result['cases']['{}_{}'.format(script_name, order)] = entry
        assert entry['visible'] and entry['attached'] and entry['open'], (script_name, order, entry)
        cmds.unloadPlugin('mayaCodeEditor')
        wait(500)
        if cmds.workspaceControl(host.CONTROL, exists=True):
            cmds.deleteUI(host.CONTROL)
        wait(300)

    try:
        for script_name in ('legacy', 'current'):
            for order in ('early', 'late'):
                run_case(script_name, order)
                result['checks'].append('restored_{}_{}'.format(script_name, order))
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)

"""Mayaの非表示reporterが見つからない場合の代わりの出力の取り込みを、専用GUIで検証する。

環境変数 ``HEDIT_OUTPUT_FALLBACK=1`` で、reporterが見つからないMayaと同じ動きにしてから編集画面を開き、
print・警告・エラーが出力欄に出ること(編集画面が開けること)を確かめる。
"""
import json
import os
from pathlib import Path
import sys
import traceback


def main(output_dir, finished):
    """GUIランナー(``tools/run_hlib_gui_versions.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` と画像の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtWidgets

    def wait(ms=300):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    result = {'status': 'error', 'checks': []}
    try:
        # 出力の取り込みは編集画面を作るときに始まるので、その前に環境変数を設定する。
        os.environ['HEDIT_OUTPUT_FALLBACK'] = '1'
        cmds.loadPlugin('hedit', quiet=True)
        import hedit
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import hedit_host
        hedit.show()
        window = hedit_host.editor()
        assert window is not None, 'Editor did not open without the reporter'
        result['checks'].append('editor_opens_without_reporter')
        output = window.findChild(QtWidgets.QPlainTextEdit, 'output')
        print('fallback_print_probe')
        cmds.warning('fallback_warning_probe')
        for attempt in range(30):
            wait(100)
            if '// Warning: fallback_warning_probe' in output.toPlainText():
                break
        text = output.toPlainText()
        assert 'fallback_print_probe\n' in text, repr(text[-400:])
        # Maya 2022 は Script Editor と同じく行末に「 // 」を付ける。
        assert ('// Warning: fallback_warning_probe\n' in text
                or '// Warning: fallback_warning_probe // \n' in text), repr(text[-400:])
        result['checks'].append('print_and_warning_shown')
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    finally:
        os.environ.pop('HEDIT_OUTPUT_FALLBACK', None)
    Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)

"""専用GUIでMaya標準reporterとheditのライブ出力を比較する。"""
import json
from pathlib import Path
import traceback


def main(output_dir, finished):
    """GUIランナー(``tools/run_hlib_gui_versions.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` と画像の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
    from maya import cmds, mel, OpenMaya, OpenMayaUI
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
        from shiboken2 import wrapInstance
    # hedit.*はhedit.mllに同梱されており、プラグインのロードでimportできるようになる。
    cmds.loadPlugin('hedit', quiet=True)
    import hedit
    result={'status':'error', 'cases':[]}
    callback=None
    temporary=None
    def wait():
        loop=QtCore.QEventLoop(); QtCore.QTimer.singleShot(80,loop.quit)
        (loop.exec if hasattr(loop,'exec') else loop.exec_)()
    try:
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import hedit_host
        hedit.show(); window=hedit_host.editor()
        output=window.findChild(QtWidgets.QPlainTextEdit,'output')
        temporary=cmds.window(); cmds.columnLayout()
        reporter=cmds.cmdScrollFieldReporter()
        widget=wrapInstance(int(OpenMayaUI.MQtUtil.findControl(reporter)),QtWidgets.QWidget)
        records=[]
        callback=OpenMaya.MCommandMessage.addCommandOutputCallback(lambda msg,kind,data: records.append([int(kind),str(msg)]))
        cases=[
            ('python_print',lambda: print('probe_python')),
            ('python_blank_lines',lambda: print('probe_blank\n\nlast')),
            ('literal_comment',lambda: print('// literal comment')),
            ('python_fragments',lambda: print('probe_fragment','on')),
            ('info',lambda: OpenMaya.MGlobal.displayInfo('probe_info\nsecond\n\nlast\n')),
            ('warning',lambda: OpenMaya.MGlobal.displayWarning('probe_warning\nsecond\n\nlast\n')),
            ('error',lambda: OpenMaya.MGlobal.displayError('probe_error\nsecond')),
            ('cmds_warning',lambda: cmds.warning('probe_cmds_warning')),
            ('mel_print',lambda: mel.eval('print "probe_mel\\n";')),
            ('mel_warning',lambda: mel.eval('warning "probe_mel_warning";')),
            ('mel_result',lambda: OpenMaya.MGlobal.executeCommand('about -version;',True,False)),
            ('python_execute',lambda: OpenMaya.MGlobal.executePythonCommand("print('probe_executed')",True,False)),
            ('python_exception',lambda: OpenMaya.MGlobal.executePythonCommand("raise ValueError('probe_exception')",True,False)),
        ]
        wait()
        action_type = getattr(QtWidgets, 'QAction', None) or QtGui.QAction

        def run_cases(mode):
            for name, emit in cases:
                cmds.cmdScrollFieldReporter(reporter,edit=True,clear=True); next(a for a in window.findChildren(action_type) if a.text() == 'Clear output').trigger(); records[:]=[]
                try: emit()
                except Exception: pass
                # 起動プラグインの追加出力も含め、25ms描画キューが追い付くまで有界待機する。
                for attempt in range(25):
                    wait()
                    if widget.property('plainText') == output.toPlainText():
                        break
                result['cases'].append({'mode':mode,'name':name,'events':list(records),'native':widget.property('plainText'),'hedit':output.toPlainText()})

        # 速い方式(既定): MayaのScript Editorと同じ形に自分で整える。違いはPythonから呼んだcmds.warningの
        # 先頭の記号(#が//になる)だけ。
        run_cases('fast')
        for case in result['cases']:
            expected = case['native']
            if case['name'] == 'cmds_warning':
                # Maya 2022 は最後に「 # 」、2023 以降は付けない。どちらも速い方式では // の形になる。
                expected = expected.replace('# Warning: probe_cmds_warning # ', '// Warning: probe_cmds_warning // ', 1)
                expected = expected.replace('# Warning: probe_cmds_warning\n', '// Warning: probe_cmds_warning\n', 1)
            assert case['hedit'] == expected, ('fast', case['name'], case['native'], case['hedit'])
        # 正確な方式(Exact Script Editor output format): reporterの整形をそのまま使い、全て同じになる。
        exact = next(a for a in window.findChildren(action_type) if a.objectName() == 'option_exactOutput')
        exact.setChecked(True)
        wait()
        try:
            run_cases('exact')
        finally:
            exact.setChecked(False)
        assert all(case['native'] == case['hedit'] for case in result['cases'] if case['mode'] == 'exact'), 'Native output mismatch'
        # 専用reporterとhedit双方の保持上限を超えても末尾が重複・欠落しない。
        next(a for a in window.findChildren(getattr(QtWidgets, 'QAction', None) or QtGui.QAction) if a.text() == 'Clear output').trigger()
        print('\n'.join('retention_%d' % i for i in range(5100)))
        # 5,100行は25msの描画キューで少しずつ反映されるので、追い付くまで有界に待つ。
        # Maya自身の遅れた出力(updateRendererUI; など)が後ろに付くことがあるので、末尾一致ではなく
        # 最後の2行が1回だけ・順番どおりにあることで確かめる。
        tail = 'retention_5098\nretention_5099\n'
        for attempt in range(40):
            wait()
            if tail in output.toPlainText():
                break
        assert output.toPlainText().count(tail) == 1, repr(output.toPlainText()[-300:])
        assert output.toPlainText().count('retention_5099') == 1
        assert 'retention_0\n' not in output.toPlainText()
        print('after_retention')
        for attempt in range(40):
            wait()
            if 'after_retention\n' in output.toPlainText():
                break
        text = output.toPlainText()
        assert text.count('after_retention\n') == 1 and text.index('after_retention') > text.index(tail), repr(text[-300:])
        result['retention'] = 'passed'
        result['status']='passed'
    except Exception:
        result['error']=traceback.format_exc()
    finally:
        if callback is not None: OpenMaya.MMessage.removeCallback(callback)
        if temporary: cmds.deleteUI(temporary)
    Path(output_dir,'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    finished(result)

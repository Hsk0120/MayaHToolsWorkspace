"""専用GUIでMaya標準reporterとheditのライブ出力を比較する。"""
import json
from pathlib import Path
import traceback


def main(output_dir, finished):
    from maya import cmds, mel, OpenMaya, OpenMayaUI
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        from shiboken6 import wrapInstance
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
        from shiboken2 import wrapInstance
    import hedit
    result={'status':'error', 'cases':[]}
    callback=None
    temporary=None
    def wait():
        loop=QtCore.QEventLoop(); QtCore.QTimer.singleShot(80,loop.quit)
        (loop.exec if hasattr(loop,'exec') else loop.exec_)()
    try:
        host=hedit.show(); window=host.editor
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
        for name, emit in cases:
            cmds.cmdScrollFieldReporter(reporter,edit=True,clear=True); next(a for a in window.findChildren(getattr(QtWidgets, 'QAction', None) or QtGui.QAction) if a.text() == 'Clear output').trigger(); records[:]=[]
            try: emit()
            except Exception: pass
            # 起動プラグインの追加出力も含め、25ms描画キューが追い付くまで有界待機する。
            for attempt in range(25):
                wait()
                if widget.property('plainText') == output.toPlainText():
                    break
            result['cases'].append({'name':name,'events':list(records),'native':widget.property('plainText'),'hedit':output.toPlainText()})
        assert all(case['native'] == case['hedit'] for case in result['cases']), 'Native output mismatch'
        # 専用reporterとhedit双方の保持上限を超えても末尾が重複・欠落しない。
        next(a for a in window.findChildren(getattr(QtWidgets, 'QAction', None) or QtGui.QAction) if a.text() == 'Clear output').trigger()
        print('\n'.join('retention_%d' % i for i in range(5100)))
        wait()
        assert output.toPlainText().endswith('retention_5099\n')
        assert output.toPlainText().count('retention_5099') == 1
        assert 'retention_0\n' not in output.toPlainText()
        print('after_retention')
        wait()
        assert output.toPlainText().endswith('after_retention\n')
        result['retention'] = 'passed'
        result['status']='passed'
    except Exception:
        result['error']=traceback.format_exc()
    finally:
        if callback is not None: OpenMaya.MMessage.removeCallback(callback)
        if temporary: cmds.deleteUI(temporary)
    Path(output_dir,'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    finished(result)

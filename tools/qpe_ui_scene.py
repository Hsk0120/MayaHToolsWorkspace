"""保存操作・用語・Maya標準履歴を隔離シーンで検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch
from qpe_ui_maya import pause, waitFor
from qpeQt import QtCore, QtWidgets, QtTest


def main(output_dir, finished=None):
    """専用Maya以外ではシーン操作を行わず、UIのみ確認する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    from quickPathExplorer import Explorer
    folder = out / 'Scenes 日本語 $test'
    folder.mkdir(exist_ok=True)
    note = folder / 'notes.txt'
    note.write_text('fixture', encoding='utf8')
    e = Explorer(maya=bool(finished))
    e.resize(1360, 920)
    e.show()
    e.setBrowseRoot(str(out))
    e.navigate(str(folder))
    checks, recorder = [], None
    try:
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == 1)
        assert e.saveType.currentData() == 'mayaBinary'
        labels = [a.text() for a in e.createFileMenu([str(note)]).actions()]
        assert 'Delete' in labels and 'Move to Recycle Bin…' not in labels
        assert 'Properties' in labels
        assert e.organizer.operationLabel('trash') == 'Delete'
        assert e.saveAsButton.isVisible() == bool(finished)
        assert e.newSceneButton.isVisible() == bool(finished)
        checks.append('Windows Delete/Properties labels; Binary default; Save Scene As visible only in Maya')
        if finished:
            from maya import cmds
            from qpeHost import perform
            e.actionRequested.connect(lambda action: perform(e, action))
            cmds.file(new=True, force=True)
            cmds.createNode('transform', name='qpeSceneMarker')
            if os.environ.get('QPE_RECORD_SCENE'):
                from qpe_record_full import Recorder
                recorder = Recorder(e, out)

            def stage(code, title):
                """実画面を保存し、録画時は操作結果を読める時間を設ける。"""
                if recorder:
                    recorder.step(code, title)
                    recorder.hold()
                e.grab().save(str(out / (code + '.png')))

            QtTest.QTest.mouseClick(e.saveAsButton, QtCore.Qt.LeftButton)
            pause(100)
            assert e.inspectorButton.isChecked() and e.operationTabs.currentWidget() is e.savePanel
            assert not list(folder.glob('*.mb'))
            e.fileName.setText('original')
            stage('01', 'Save Scene As / 保存前に名前・形式・保存先を確認 / 既定は .mb')
            assert e.fileName.height() >= e.fileName.fontMetrics().height() + 4
            assert e.saveType.height() >= e.saveType.fontMetrics().height() + 4
            QtTest.QTest.mouseClick(e.actionButtons['saveAs'], QtCore.Qt.LeftButton)
            original = folder / 'original.mb'
            assert original.is_file() and cmds.file(query=True, type=True) == ['mayaBinary']
            original_bytes = original.read_bytes()
            stage('02', 'Maya Binary の実ファイルを保存しました')
            e.fileName.setText('copy')
            QtTest.QTest.mouseClick(e.actionButtons['saveAs'], QtCore.Qt.LeftButton)
            assert (folder / 'copy.mb').is_file() and original.read_bytes() == original_bytes
            checks.append('Save Scene As opens editor without writing; commits Binary; renamed copy preserves original')
            e.saveType.setCurrentIndex(e.saveType.findData('mayaAscii'))
            e.fileName.setText('ascii')
            QtTest.QTest.mouseClick(e.actionButtons['saveAs'], QtCore.Qt.LeftButton)
            ascii_path = folder / 'ascii.ma'
            assert ascii_path.is_file() and cmds.file(query=True, type=True) == ['mayaAscii']
            checks.append('explicit Maya ASCII remains available')
            for path, kind in ((original, 'mayaBinary'), (ascii_path, 'mayaAscii'), (original, 'mayaBinary')):
                cmds.file(new=True, force=True)
                e.requestFiles('open', [str(path)])
                assert cmds.objExists('qpeSceneMarker')
                names = cmds.optionVar(query='RecentFilesList')
                types = cmds.optionVar(query='RecentFilesTypeList')
                matched = [i for i, name in enumerate(names) if Path(name) == path]
                assert len(matched) == 1 and types[matched[0]] == kind
            checks.append('successful ma/mb Open registers real Maya Recent Files and matching types without duplicates')
            stage('03', 'Open 成功後に Maya 標準 Recent Files へ登録 / 重複なし')
            before = list(cmds.optionVar(query='RecentFilesList'))
            cmds.setAttr('qpeSceneMarker.tx', 3)
            with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Cancel):
                e.requestFiles('open', [str(ascii_path)])
            assert list(cmds.optionVar(query='RecentFilesList')) == before
            assert Path(cmds.file(query=True, sceneName=True)) == original
            cmds.file(modified=False)
            with patch('qpeHost.cmds.file', side_effect=RuntimeError('read failure')), patch.object(QtWidgets.QMessageBox, 'warning'):
                e.requestFiles('open', [str(ascii_path)])
            assert list(cmds.optionVar(query='RecentFilesList')) == before
            checks.append('cancelled or failed Open leaves standard Recent Files unchanged')
            stage('04', 'キャンセル・読込失敗では履歴を変更しない / 元のシーンを維持')
            cmds.setAttr('qpeSceneMarker.tx', 7)
            with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Cancel):
                QtTest.QTest.mouseClick(e.newSceneButton, QtCore.Qt.LeftButton)
            assert cmds.objExists('qpeSceneMarker') and cmds.file(query=True, modified=True)
            # 保存先ダイアログの取消でSaveSceneが戻った場合も新規へ進めない。
            with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Save), patch('qpeHost.mel.eval'):
                QtTest.QTest.mouseClick(e.newSceneButton, QtCore.Qt.LeftButton)
            assert cmds.objExists('qpeSceneMarker') and cmds.file(query=True, modified=True)
            with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Save), patch('qpeHost.mel.eval', side_effect=RuntimeError('save failure')), patch.object(QtWidgets.QMessageBox, 'warning'):
                QtTest.QTest.mouseClick(e.newSceneButton, QtCore.Qt.LeftButton)
            assert cmds.objExists('qpeSceneMarker') and cmds.file(query=True, modified=True)
            with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Discard):
                QtTest.QTest.mouseClick(e.newSceneButton, QtCore.Qt.LeftButton)
            assert not cmds.file(query=True, sceneName=True) and not cmds.objExists('qpeSceneMarker')
            assert original.read_bytes() == original_bytes
            assert list(cmds.optionVar(query='RecentFilesList')) == before
            with patch.object(QtWidgets.QMessageBox, 'question') as prompt:
                QtTest.QTest.mouseClick(e.newSceneButton, QtCore.Qt.LeftButton)
                prompt.assert_not_called()
            cmds.file(str(original), open=True, force=True)
            cmds.setAttr('qpeSceneMarker.tx', 9)
            with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Save):
                QtTest.QTest.mouseClick(e.newSceneButton, QtCore.Qt.LeftButton)
            assert not cmds.file(query=True, sceneName=True) and not cmds.objExists('qpeSceneMarker')
            cmds.file(str(original), open=True, force=True)
            assert cmds.getAttr('qpeSceneMarker.tx') == 9
            checks.append('New Scene: Cancel, cancelled/failed Save preserve scene; Discard preserves disk; Save persists edits; clean scene needs no prompt')
            QtTest.QTest.mouseClick(e.newSceneButton, QtCore.Qt.LeftButton)
            stage('05', 'New Scene / 保存・破棄・キャンセルを確認 / 新規シーンには既存ファイルを上書きしない')
            import qpeHost
            dock = qpeHost.show(str(out))
            try:
                cmds.file(str(original), open=True, force=True)
                waitFor(lambda: Path(dock.currentDirectory) == folder)
                dock.navigate(str(out))
                qpeHost.refresh(dock)
                cmds.file(save=True)
                pause(100)
                assert Path(dock.currentDirectory) == out
                cmds.setAttr('qpeSceneMarker.tx', 11)
                with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Cancel):
                    dock.requestFiles('open', [str(ascii_path)])
                assert Path(dock.currentDirectory) == out
                cmds.file(modified=False)
                dock.requestFiles('open', [str(ascii_path)])
                waitFor(lambda: Path(dock.currentDirectory) == folder)
                dock.navigate(str(out))
                cmds.file(new=True, force=True)
                pause(100)
                assert Path(dock.currentDirectory) == out
                checks.append('actual host SceneOpened follows external and QPE opens; refresh, Save, Cancel and New leave browsing location unchanged')
            finally:
                cmds.deleteUI(qpeHost.CONTROL)
        result = dict(status='passed', checks=checks)
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    if recorder:
        recorder.timer.stop()
        recorder.capture()
        manifest = []
        for i, sample in enumerate(recorder.samples):
            duration = recorder.samples[i+1]['seconds']-sample['seconds'] if i+1 < len(recorder.samples) else .15
            manifest.extend(["file '%s'" % (recorder.frames / ('%05d.png' % i)).as_posix(), 'duration %.6f' % duration])
        manifest.append("file '%s'" % (recorder.frames / ('%05d.png' % (len(recorder.samples)-1))).as_posix())
        (out / 'frames.txt').write_text('\n'.join(manifest), encoding='utf8')
        result['recording'] = 'frames captured; encode outside Maya'
    e.grab().save(str(out / 'overview.png'))
    e.close()
    e.deleteLater()
    QtCore.QCoreApplication.sendPostedEvents(e, QtCore.QEvent.DeferredDelete)
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    QtCore.QThreadPool.globalInstance().waitForDone(10000)
    sys.exit(0 if result['status'] == 'passed' else 1)

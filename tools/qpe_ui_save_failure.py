"""Maya Save Asの書込失敗とキャンセル時に未保存シーンを保護する回帰。"""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'maya/inhouse/QuickPathExplorer/python'))


def main(output_dir, finished):
    """専用シーンへ書込失敗を注入し、名前・内容・再試行を照合する。"""
    from maya import cmds
    from qpeQt import QtWidgets
    import qpeHost
    out = Path(output_dir)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    checks = []
    try:
        e = qpeHost.show(str(out))
        for named in (False, True):
            cmds.file(new=True, force=True)
            cmds.createNode('transform', name='QPE_UnsavedPayload')
            if named:
                cmds.file(rename=str(out / 'original.ma'))
                cmds.file(save=True, type='mayaAscii')
            cmds.setAttr('QPE_UnsavedPayload.tx', 37)
            original = cmds.file(query=True, sceneName=True)
            target = out / ('named.mb' if named else 'untitled.mb')
            e.navigate(str(out))
            e.fileName.setText(target.name)
            real_save_as = qpeHost.OpenMayaLegacy.MFileIO.saveAs

            def fail_save(path, file_type, force):
                """検査後に保存先が失われた状態を実際のMaya書込で再現する。"""
                return real_save_as((out / 'absent' / target.name).as_posix(), file_type, force)

            with patch.object(qpeHost.OpenMayaLegacy.MFileIO, 'saveAs', side_effect=fail_save), patch.object(QtWidgets.QMessageBox, 'warning'):
                qpeHost.perform(e, 'saveAs')
            current = cmds.file(query=True, sceneName=True)
            assert current == original, (original, current)
            assert cmds.getAttr('QPE_UnsavedPayload.tx') == 37
            assert cmds.file(query=True, modified=True)
            assert not target.exists()
            assert not e._mayaActionRunning
            assert e.status.text() and not e.status.text().startswith('Completed:')
            assert 'Could not save scene to:' in e.status.text()
            assert target.as_posix() in e.status.text().replace('\\', '/')
            checks.append('Save As failure preserves name/content/modified flag: ' + str(named))
            qpeHost.perform(e, 'saveAs')
            assert target.is_file() and Path(cmds.file(query=True, sceneName=True)) == target
            checks.append('Save As retry succeeds: ' + str(named))
            cmds.setAttr('QPE_UnsavedPayload.tx', 51)
            with patch.object(QtWidgets.QMessageBox, 'question', return_value=QtWidgets.QMessageBox.Cancel):
                qpeHost.perform(e, 'new')
            assert cmds.getAttr('QPE_UnsavedPayload.tx') == 51
            assert Path(cmds.file(query=True, sceneName=True)) == target
            checks.append('New Scene cancellation preserves unsaved content: ' + str(named))
        folder = out / '日本語フォルダー'
        folder.mkdir()
        for extension, file_type in (('.ma', 'mayaAscii'), ('.mb', 'mayaBinary')):
            target = folder / ('日本語 保存' + extension)
            e.navigate(str(folder))
            e.saveType.setCurrentIndex(e.saveType.findData(file_type))
            e.fileName.setText(target.name)
            cmds.setAttr('QPE_UnsavedPayload.tx', 111)
            cmds.setAttr('QPE_UnsavedPayload.tx', 222)
            qpeHost.perform(e, 'saveAs')
            assert target.is_file(), (target, e.status.text())
            assert Path(cmds.file(query=True, sceneName=True)) == target
            assert cmds.file(query=True, type=True) == [file_type]
            assert target.as_posix() in [value.replace('\\', '/') for value in cmds.optionVar(query='RecentFilesList')]
            cmds.undo()
            assert cmds.getAttr('QPE_UnsavedPayload.tx') == 111
            cmds.redo()
            assert cmds.getAttr('QPE_UnsavedPayload.tx') == 222
            cmds.file(target.as_posix(), open=True, force=True)
            assert cmds.getAttr('QPE_UnsavedPayload.tx') == 222
            checks.append('Unicode/space path, type, recent, Undo/Redo and reopen: ' + extension)
        result = {'status': 'passed', 'checks': checks, 'input': 'Maya GUI API with controlled write failure'}
    except Exception:
        result = {'status': 'failed', 'checks': checks, 'error': traceback.format_exc()}
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    finished(result)

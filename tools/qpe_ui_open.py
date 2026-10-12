"""Openのホスト分岐と起動失敗を隔離データで検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause, waitFor, selectFile
from qpeQt import QtCore, QtGui, QtWidgets, QtTest


def main(output_dir, finished=None):
    """OS起動は捕捉し、Mayaシーンは専用GUIで実際に読み込む。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out/'settings.json')
    from quickPathExplorer import Explorer
    from qpeSettings import readSettings
    root = out/'Files with spaces 日本語'
    root.mkdir(exist_ok=True)
    files = []
    for suffix in ('txt', 'png', 'pdf', 'mp4', 'fbx', 'unknown', 'ma', 'mb'):
        path = root/('test.'+suffix)
        path.write_text('QPE isolated fixture', encoding='utf8')
        files.append(path)
    e = Explorer(maya=bool(finished))
    e.resize(1200, 850)
    e.show()
    e.navigate(str(root))
    checks = []
    try:
        waitFor(lambda: e.fileProxy.rowCount(e.files.rootIndex()) == len(files))
        if finished:
            from qpeHost import perform
            from maya import cmds
            e.actionRequested.connect(lambda action: perform(e, action))
        else:
            e.actionRequested.connect(lambda action: e.openAssociatedFile(e.operationPaths()[0]) if action == 'open' else None)
        with patch.object(QtGui.QDesktopServices, 'openUrl', return_value=True) as launch:
            selectFile(e, files[0])
            pause(150)
            launch.assert_not_called()
            e.openSelectedFile()
            assert Path(launch.call_args[0][0].toLocalFile()) == files[0]
            launch.reset_mock()
            selectFile(e, files[1])
            e.openFileIndex(e.files.currentIndex())
            assert Path(launch.call_args[0][0].toLocalFile()) == files[1]
            launch.reset_mock()
            e.activateWindow()
            e.raise_()
            e.files.setFocus()
            pause(150)
            QtTest.QTest.keyClick(e.files, QtCore.Qt.Key_Space)
            assert launch.call_count == 1
            for path in files[2:6] if finished else files[2:]:
                launch.reset_mock()
                e.requestFiles('open', [str(path)])
                assert launch.call_count == 1
                assert Path(launch.call_args[0][0].toLocalFile()) == path
        checks.append('selection does not launch; Open/double-click handler/Space dispatch one exact local URL')
        checks.append('non-scene extensions use OS associations (launch mocked; native app verified separately)')
        failed = root/'failed.txt'
        failed.write_text('failure fixture')
        before = readSettings().get('recents', [])
        with patch.object(QtGui.QDesktopServices, 'openUrl', return_value=False), patch.object(e.organizer, 'report') as report:
            assert not e.openAssociatedFile(str(failed))
            assert 'Could not launch' in report.call_args[0][0]
        assert readSettings().get('recents', []) == before
        with patch.object(QtGui.QDesktopServices, 'openUrl', side_effect=RuntimeError('launch error')):
            assert not e.openAssociatedFile(str(failed))
        assert readSettings().get('recents', []) == before
        checks.append('rejected and exceptional launches report failure without adding Recent')
        if finished:
            for suffix, kind in (('ma', 'mayaAscii'), ('mb', 'mayaBinary')):
                cmds.file(new=True, force=True)
                cmds.createNode('transform', name='qpeOpenMarker')
                scene = root/('real.'+suffix)
                cmds.file(rename=str(scene))
                cmds.file(save=True, type=kind, force=True)
                cmds.file(new=True, force=True)
                with patch.object(QtGui.QDesktopServices, 'openUrl') as launch:
                    e.requestFiles('open', [str(scene)])
                    launch.assert_not_called()
                assert cmds.objExists('qpeOpenMarker')
                assert Path(cmds.file(query=True, sceneName=True)) == scene
            checks.append('real .ma and .mb load into current isolated Maya without external launch')
        result = dict(status='passed', checks=checks, limitations=['OS acceptance does not prove external application completed loading'])
    except Exception:
        result = dict(status='error', checks=checks, error=traceback.format_exc())
    e.grab().save(str(out/'open-routing.png'))
    e.close()
    pause(300)
    (out/'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(result), flush=True)
    if finished:
        finished(result)
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication([])
    result = main(sys.argv[1])
    sys.exit(0 if result['status'] == 'passed' else 1)

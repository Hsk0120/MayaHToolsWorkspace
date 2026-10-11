"""専用のMaya GUIで両版のドック表示と共通ケースを計測する。"""
import json
import os
from pathlib import Path
import sys
import time
import traceback


def main(output_dir, finished):
    """既存の隔離GUIランナーから呼び出される。

    Args:
        output_dir (Path): 証跡の保存先。
        finished (callable): 結果を受けて専用Mayaを終了する関数。
    """
    from maya import cmds
    from PySide6 import QtCore, QtWidgets, QtTest
    import shiboken6
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root / 'maya/inhouse/QuickPathExplorer/python'))
    import qpePrototypeHost as qpeHost
    from qpeBenchmark import benchmark
    directory = Path(output_dir)
    result = dict(status='error', measurements=[], checks=[])
    try:
        for round_index in range(int(os.environ['QPE_ROUNDS'])):
            for language in (('cpp', 'python') if round_index % 2 == 0 else ('python', 'cpp')):
                start = time.perf_counter()
                widget = qpeHost.show(language, path='')
                QtWidgets.QApplication.processEvents()
                startup = (time.perf_counter() - start) * 1000
                assert widget.isVisible()
                output = directory / ('maya_{}_{}.json'.format(language, round_index))
                if language == 'cpp':
                    code = qpeHost.library().qpeBenchmark(shiboken6.getCppPointer(widget)[0],
                        os.environ['QPE_CONFIG'].encode('utf-8'), str(output).encode('utf-8'))
                    assert code == 0
                    measurement = json.loads(output.read_text())
                else:
                    measurement = benchmark(widget, os.environ['QPE_CONFIG'], str(output))
                assert measurement['passed']
                measurement.update(host='maya', round=round_index, startup_ms=startup)
                result['measurements'].append(measurement)
                name = 'QuickPathExplorer_' + language
                cmds.workspaceControl(name, edit=True, dockToMainWindow=('right', False))
                assert not cmds.workspaceControl(name, query=True, floating=True)
                cmds.workspaceControl(name, edit=True, floating=True)
                assert cmds.workspaceControl(name, query=True, floating=True)
                if round_index == 0:
                    # QtTestで実キー入力と列クリックを検証する。操作は専用データだけに限定する。
                    settings = json.loads(Path(os.environ['QPE_CONFIG']).read_text(encoding='utf-8'))
                    address = widget.findChild(QtWidgets.QLineEdit, 'address')
                    address.setText(settings['check_path'])
                    address.setFocus()
                    QtTest.QTest.keyClick(address, QtCore.Qt.Key_Return)
                    model = widget.findChild(QtWidgets.QFileSystemModel, 'fileModel')
                    view = widget.findChild(QtWidgets.QColumnView, 'columns')
                    from qpeBenchmark import waitFor
                    assert waitFor(lambda: model.rowCount(view.rootIndex()) == 3)
                    child_index = model.index(settings['check_path'] + '/subfolder')
                    column = next(c for c in view.findChildren(QtWidgets.QListView) if c.rootIndex() == view.rootIndex())
                    rect = column.visualRect(child_index)
                    QtTest.QTest.mouseClick(column.viewport(), QtCore.Qt.LeftButton, pos=rect.center())
                    QtWidgets.QApplication.processEvents()
                    assert view.currentIndex() == child_index
                    assert any(c.rootIndex() == child_index for c in view.findChildren(QtWidgets.QListView))
                    QtTest.QTest.keyClick(column, QtCore.Qt.Key_Right)
                    QtTest.QTest.keyClick(column, QtCore.Qt.Key_Left)
                    widget.window().grab().save(str(directory / (language + '_maya_window.png')))
                    # 実際のMayaファイルを作り、共有ホストの読み込み3操作を検証する。
                    scene_path = (directory / (language + '_probe.ma')).as_posix()
                    cmds.file(new=True, force=True)
                    cmds.createNode('transform', name='qpeProbe')
                    cmds.file(rename=scene_path)
                    cmds.file(save=True, type='mayaAscii')
                    address.setText(directory.as_posix())
                    address.returnPressed.emit()
                    assert waitFor(lambda: model.index(scene_path).isValid())
                    view.setCurrentIndex(model.index(scene_path))
                    cmds.file(new=True, force=True)
                    qpeHost._mayaAction(widget, 'open')
                    assert cmds.objExists('qpeProbe')
                    cmds.file(new=True, force=True)
                    qpeHost._mayaAction(widget, 'import')
                    assert cmds.objExists('qpeProbe')
                    cmds.file(new=True, force=True)
                    qpeHost._mayaAction(widget, 'reference')
                    assert cmds.file(query=True, reference=True)
                    cmds.file(new=True, force=True)
                    cmds.createNode('transform', name='qpeUnsavedKeep')
                    # 専用シーンで破棄確認をCancelし、未保存内容が保持されることを確認する。
                    QtCore.QTimer.singleShot(0, lambda: QtWidgets.QApplication.activeModalWidget().reject())
                    qpeHost._mayaAction(widget, 'open')
                    assert cmds.objExists('qpeUnsavedKeep') and cmds.file(query=True, modified=True)
                    cmds.file(new=True, force=True)
                cmds.deleteUI(name)
                QtWidgets.QApplication.processEvents()
        result['checks'] = ['both_visible', 'dock_and_float', 'shared_cases_and_file_counts', 'unicode', 'filter', 'invalid_path', 'keyboard_address', 'mouse_column_expand', 'maya_open_import_reference', 'unsaved_open_cancel_preserves_scene']
        result['status'] = 'passed'
    except BaseException:
        result['error'] = traceback.format_exc()
    (directory / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    finished(result)

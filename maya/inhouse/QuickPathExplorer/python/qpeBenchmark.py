"""C++のbenchmark.cppと同じ条件のモデル準備・イベント反映計測。"""
import json
import time
from pathlib import Path
from PySide6 import QtCore, QtWidgets


def waitFor(condition):
    """GUIイベントを処理しながら条件成立を待つ。

    Args:
        condition (callable): 終了条件。

    Returns:
        bool: 15秒以内に成立したか。
    """
    start = time.perf_counter()
    while not condition():
        QtWidgets.QApplication.processEvents()
        if time.perf_counter() - start > 15:
            return False
        QtCore.QThread.msleep(1)
    QtWidgets.QApplication.processEvents()
    return True


def benchmark(widget, config, output):
    """専用検証画面で件数と操作を検証し計測値を保存する。

    Args:
        widget (QWidget): 試作画面。
        config (str): 共通ケースJSON。
        output (str): 結果JSONの出力先。

    Returns:
        dict: 判定と計測値。
    """
    settings = json.loads(Path(config).read_text(encoding='utf-8'))
    model = widget.findChild(QtWidgets.QFileSystemModel, 'fileModel')
    view = widget.findChild(QtWidgets.QColumnView, 'columns')
    address = widget.findChild(QtWidgets.QLineEdit, 'address')
    loaded = set()

    def onLoaded(path):
        """読み込み完了したパスを記録する。

        Args:
            path (str): モデルが読み込んだパス。
        """
        loaded.add(QtCore.QDir.cleanPath(path))

    model.directoryLoaded.connect(onLoaded)
    result = {'implementation': 'python', 'qt': QtCore.qVersion(), 'passed': True, 'cases': []}
    try:
        for item in settings['cases']:
            path = QtCore.QDir.cleanPath(item['path'])
            start = time.perf_counter()
            if item.get('mode') == 'select':
                index = model.index(path)
                view.setCurrentIndex(index)
                if model.canFetchMore(index):
                    model.fetchMore(index)
            else:
                address.setText(path)
                address.returnPressed.emit()
                index = view.rootIndex()
            ok = waitFor(lambda: path in loaded and model.rowCount(index) == item['count'])
            elapsed = (time.perf_counter() - start) * 1000
            result['cases'].append({'name': item['name'], 'ms': elapsed, 'rows': model.rowCount(index), 'passed': ok})
            result['passed'] &= ok
        check_path = settings['check_path']
        address.setText(check_path)
        address.returnPressed.emit()
        result['check_loaded'] = waitFor(lambda: QtCore.QDir.cleanPath(check_path) in loaded)
        pattern = widget.findChild(QtWidgets.QLineEdit, 'filter')
        pattern.setText('*.ma')
        result['filter_check'] = waitFor(lambda: model.rowCount(view.rootIndex()) == 2)
        view.setCurrentIndex(model.index(check_path + '/日本語 scene.ma'))
        QtWidgets.QApplication.processEvents()
        result['unicode_selection_check'] = '日本語 scene.ma' in widget.findChild(QtWidgets.QLabel, 'info').text()
        old_root = view.rootIndex()
        address.setText(check_path + '/missing')
        address.returnPressed.emit()
        result['invalid_path_check'] = old_root == view.rootIndex()
        pattern.clear()
        address.setText(check_path)
        result['filter_cleared'] = waitFor(lambda: model.rowCount(view.rootIndex()) == 3)
        view.setCurrentIndex(model.index(check_path + '/image.txt'))
        view.setCurrentIndex(model.index(check_path + '/日本語 scene.ma'))
        QtWidgets.QApplication.processEvents()
        result['passed'] &= all(result[key] for key in ('check_loaded', 'filter_cleared', 'filter_check', 'unicode_selection_check', 'invalid_path_check'))
        widget.grab().save(str(output) + '.png')
        # 証跡の描画とPNG圧縮は、全ケースの計測が終わってから行う。
        for item in settings['cases']:
            if item['name'] == 'deep_root':
                address.setText(item['path'])
                address.returnPressed.emit()
            elif item['name'].startswith('depth_'):
                view.setCurrentIndex(model.index(item['path']))
            else:
                continue
            QtWidgets.QApplication.processEvents()
            if item['name'] == 'depth_03':
                widget.grab().save(str(output) + '.columns.png')
                break
    finally:
        model.directoryLoaded.disconnect(onLoaded)
    Path(output).write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result

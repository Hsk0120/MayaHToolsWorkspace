"""最小ドック幅で場所欄と操作ボタンが重ならないことを検証する。"""
import json
import os
from pathlib import Path
import sys
import traceback

sys.path.insert(0, str(Path(__file__).resolve().parent))
from qpe_ui_maya import pause
from qpeQt import QtCore, QtWidgets


def main(output_dir, finished=None):
    """専用QPEのナビゲーションを実際のQt配置で検査する。"""
    out = Path(output_dir).resolve()
    out.mkdir(parents=True, exist_ok=True)
    os.environ['QPE_SETTINGS_FILE'] = str(out / 'settings.json')
    if finished:
        import qpeHost
        e = qpeHost.show(str(out))
        container = e._dockViewport
    else:
        from quickPathExplorer import Explorer
        e = Explorer(maya=True)
        container = QtWidgets.QScrollArea()
        container.setFrameShape(QtWidgets.QFrame.NoFrame)
        container.setWidgetResizable(True)
        container.setMinimumSize(240, 160)
        container.setWidget(e)
        e.modern.watchViewport(container.viewport())
        container.show()
    checks = []
    try:
        pause(800)  # Mayaの起動時配置復元が終わってから手動リサイズを模擬する。
        for width in (240, 260, 300, 400, 800):
            container.window().resize(width, 700)
            pause(400)
            assert abs(container.width() - width) <= 8, (width, container.width())
            items = [e.navigationBar.itemAt(index).widget() for index in range(e.navigationBar.count())]
            rectangles = []
            for item in items:
                if item is not None and item.isVisible():
                    point = item.mapTo(e.navigationFrame, QtCore.QPoint())
                    rectangles.append((item.objectName() or item.__class__.__name__,
                                       QtCore.QRect(point, item.size())))
            rectangles.sort(key=lambda value: value[1].left())
            geometry = [(name, [rect.x(), rect.y(), rect.width(), rect.height()]) for name, rect in rectangles]
            for (left_name, left), (right_name, right) in zip(rectangles, rectangles[1:]):
                assert not left.intersects(right), (width, left_name, right_name, geometry)
            assert rectangles[-1][1].right() < e.navigationFrame.width(), (width, geometry, e.navigationFrame.width())
            checks.append({'width': width, 'actual': container.width(), 'items': geometry})
        result = {'status': 'passed', 'checks': checks, 'input': 'Qt programmatic resize'}
    except Exception:
        result = {'status': 'failed', 'checks': checks, 'error': traceback.format_exc()}
    container.grab().save(str(out / 'result.png'))
    (out / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    if finished:
        finished(result)
    else:
        container.close()
    return result


if __name__ == '__main__':
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    print(main(sys.argv[1])['status'])

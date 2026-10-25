"""画面の下へドックしたMaya Code Editorの高さを、境界のドラッグで変えられることを専用GUIで検証する。

画面の一番下(``workspaceControl -dockToMainWindow bottom``。コマンドラインの下)は、高さが固定の行としか
隣り合わないため、Mayaは高さを変えられない(Maya標準の部品でも同じ)。0.7.1から、初めてドックするときは
タイムスライダーの上に入れ、一番下に残ったドックは開いたときに移す。ドラッグは本物のカーソルを動かさず、
分割の取っ手へマウスのイベントを送って行う。
"""
import json
from pathlib import Path
import sys
import traceback

OTHER_DOCK = 'mceProbeBottomDock'


def main(output_dir, finished):
    """GUIランナー(``maya/inhouse/mlib/__tests__/runGui.py``)が、専用の Maya GUI の中で呼ぶ入口。

    Args:
        output_dir (str): 結果の ``result.json`` と画像の出力先。
        finished (callable): 終了時に結果の辞書を渡して呼ぶ関数(Maya の終了はランナーが行う)。
    """
    from maya import cmds
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
    except ImportError:
        from PySide2 import QtCore, QtGui, QtWidgets
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import gui_host as host
    result = {'status': 'error', 'checks': [], 'drags': []}

    def wait(ms=300):
        loop = QtCore.QEventLoop()
        QtCore.QTimer.singleShot(ms, loop.quit)
        (loop.exec if hasattr(loop, 'exec') else loop.exec_)()

    # Mayaはドックの付け替えで部品を作り直す。PySide2は同じアドレスの古いラッパーを返すことがあるので、
    # 親をたどらず、生存中の部品(QApplication.allWidgets)と画面上の位置で調べる。
    def widget_of(name):
        """QWidget | None: MayaのUI名に対応する、生存中のQtの部品。"""
        from maya import OpenMayaUI
        pointer = OpenMayaUI.MQtUtil.findControl(name)
        return host._live_widget(int(pointer)) if pointer else None

    def global_rect(widget):
        return QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), widget.size())

    def below_time_slider():
        """bool: ドックが、タイムスライダーより下(コマンドラインの下)にあるか。"""
        return global_rect(widget_of(host.CONTROL)).top() > global_rect(widget_of('TimeSlider')).top()

    def border_handle():
        """QSplitterHandle: ドックの上の境界(縦の分割の取っ手)。"""
        control = global_rect(widget_of(host.CONTROL))
        best = None
        for widget in QtWidgets.QApplication.allWidgets():
            if not isinstance(widget, QtWidgets.QSplitterHandle) or not widget.isVisible():
                continue
            if widget.orientation() != QtCore.Qt.Vertical:
                continue
            rect = global_rect(widget)
            if rect.right() < control.left() or rect.left() > control.right():
                continue
            # タブの見出しの分だけ、ドックの部品の上端は取っ手から離れる。
            distance = abs(control.top() - rect.bottom())
            if distance <= 40 and (best is None or distance < best[0]):
                best = (distance, widget)
        assert best is not None, 'border handle not found'
        return best[1]

    def send(target, kind, position, buttons):
        types = {'move': QtCore.QEvent.MouseMove, 'press': QtCore.QEvent.MouseButtonPress,
                 'release': QtCore.QEvent.MouseButtonRelease}
        button = QtCore.Qt.NoButton if kind == 'move' else QtCore.Qt.LeftButton
        event = QtGui.QMouseEvent(types[kind], QtCore.QPointF(position), QtCore.QPointF(target.mapToGlobal(position)),
                                  button, buttons, QtCore.Qt.NoModifier)
        QtWidgets.QApplication.sendEvent(target, event)

    def drag_border(delta):
        """ドックの上の境界を縦に ``delta`` px ドラッグし、(前の高さ, 後の高さ) を返す。"""
        handle = border_handle()
        before = widget_of(host.CONTROL).height()
        center = handle.rect().center()
        send(handle, 'press', center, QtCore.Qt.LeftButton)
        for step in range(1, 11):
            send(handle, 'move', center + QtCore.QPoint(0, delta * step // 10), QtCore.Qt.LeftButton)
            wait(10)
        send(handle, 'release', center + QtCore.QPoint(0, delta), QtCore.Qt.NoButton)
        wait(300)
        return before, widget_of(host.CONTROL).height()

    def assert_resizable(label):
        shrink = drag_border(100)
        grow = drag_border(-100)
        result['drags'].append({'label': label, 'shrink': shrink, 'grow': grow})
        assert shrink[1] < shrink[0] and grow[1] > grow[0], (label, shrink, grow)

    try:
        cmds.loadPlugin('mayaCodeEditor', quiet=True)

        # 1. ドックが無い状態から、ドッキングして開く。タイムスライダーの上に入り、高さを変えられる。
        cmds.mayaCodeEditor(show=True, floating=False)
        wait(1200)
        assert not cmds.workspaceControl(host.CONTROL, query=True, floating=True)
        assert not below_time_slider(), 'new docked control is below the time slider'
        assert_resizable('new_docked')
        result['checks'].append('new_dock_above_time_slider_resizable')

        # 2. 0.7.0までの位置(画面の一番下)に入ったドック。開き直すと、本文を保ったままタイムスライダーの上へ移る。
        window = host.editor()
        window.findChild(QtWidgets.QTabWidget).currentWidget().setPlainText('dock_resize_probe = 1')
        address = host.pointer(window)
        cmds.workspaceControl(host.CONTROL, edit=True, dockToMainWindow=('bottom', False))
        wait(500)
        assert below_time_slider()
        before, after = drag_border(-100)
        assert before == after, 'precondition: Maya resized the bottom dock ({} -> {})'.format(before, after)
        cmds.workspaceControl(host.CONTROL, edit=True, close=True)
        wait(300)
        cmds.mayaCodeEditor(show=True)
        wait(1200)
        assert not below_time_slider(), 'bottom dock was not moved'
        window = host.editor()
        assert host.pointer(window) == address and host.docked_editor() is not None
        assert window.findChild(QtWidgets.QTabWidget).currentWidget().toPlainText() == 'dock_resize_probe = 1'
        assert_resizable('moved')
        result['checks'].append('bottom_dock_moved_and_resizable')

        # 3. 一番下に高さを変えられる別のドックが並んでいれば、その境界で変えられるので移さない。
        cmds.workspaceControl(OTHER_DOCK, label=OTHER_DOCK, retain=False, floating=True, initialHeight=200)
        cmds.setParent(OTHER_DOCK)
        cmds.columnLayout()
        cmds.button(label='other')
        cmds.workspaceControl(OTHER_DOCK, edit=True, dockToMainWindow=('bottom', False))
        cmds.workspaceControl(host.CONTROL, edit=True, dockToMainWindow=('bottom', False))
        wait(500)
        cmds.mayaCodeEditor(show=True)
        wait(1200)
        assert below_time_slider(), 'moved although another resizable dock is next to it'
        cmds.deleteUI(OTHER_DOCK)
        result['checks'].append('not_moved_next_to_resizable_dock')

        # 4. 浮動のドックはそのまま。
        cmds.workspaceControl(host.CONTROL, edit=True, floating=True)
        cmds.mayaCodeEditor(show=True)
        wait(800)
        assert cmds.workspaceControl(host.CONTROL, query=True, floating=True)
        result['checks'].append('floating_untouched')
        result['status'] = 'passed'
    except Exception:
        result['error'] = traceback.format_exc()
    Path(output_dir, 'result.json').write_text(json.dumps(result), encoding='utf-8')
    finished(result)

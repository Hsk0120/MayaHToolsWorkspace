"""Maya標準ドックの保存・復元と終了時の開閉状態を管理する。"""
from maya import cmds
from maya import OpenMayaUI
from qpeQt import QtCore, QtWidgets, shiboken
from qpeSettings import readSettings, writeSettings

CONTROL = 'QuickPathExplorerWorkspaceControl'
_watcher = None
_quitting = False
_open = False
_started = False
_quitJob = None


def _control_widget(name):
    """Maya所有のコントロールを所有権を移さず取得する。"""
    pointer = OpenMayaUI.MQtUtil.findControl(name)
    if pointer:
        for widget in QtWidgets.QApplication.allWidgets():
            if shiboken.isValid(widget) and int(shiboken.getCppPointer(widget)[0]) == int(pointer):
                return widget
    return None


def _dock_splitter(control):
    """再ドックで無効になった親ラッパーを使わず、直接の分割領域を返す。"""
    # 全ウィジェット走査にはMayaが付け替え中の旧splitterも含まれる。
    # 現在のcontrolから直接たどり、無関係な破棄待ちの領域を参照しない。
    item = control
    while item is not None and shiboken.isValid(item):
        parent = item.parentWidget()
        if parent is None or not shiboken.isValid(parent):
            break
        if isinstance(parent, QtWidgets.QSplitter):
            return parent, item
        item = parent
    return None


def _repair_fixed_row_dock():
    """固定行の下だけに挟まれたドックを、リサイズできる位置へ移す。"""
    if not cmds.workspaceControl(CONTROL, exists=True) or cmds.workspaceControl(CONTROL, query=True, floating=True):
        return
    control = _control_widget(CONTROL)
    parent = control.parentWidget() if control is not None else None
    while parent is not None:
        if isinstance(parent, QtWidgets.QTabWidget) and parent.count() > 1:
            # 利用者が他エディターとまとめたタブを自動的に分離しない。
            return
        parent = parent.parentWidget()
    found = _dock_splitter(control) if control is not None else None
    slider, main = _control_widget('TimeSlider'), _control_widget('MainPane')
    if found is None or slider is None:
        return
    splitter, item = found
    if not shiboken.isValid(splitter) or not shiboken.isValid(item):
        return
    if splitter.orientation() != QtCore.Qt.Vertical:
        return
    index = splitter.indexOf(item)
    slider_index = -1
    for i in range(splitter.count()):
        row = splitter.widget(i)
        if row.isAncestorOf(slider) and not (main and row.isAncestorOf(main)):
            slider_index = i
    if slider_index < 0 or index <= slider_index:
        return
    fixed = [_control_widget(name) for name in ('TimeSlider', 'RangeSlider', 'CommandLine', 'HelpLine')]
    for i in range(slider_index + 1, splitter.count()):
        other = splitter.widget(i)
        if i != index and other.isVisible() and not any(w and other.isAncestorOf(w) for w in fixed):
            return
    if slider.isVisible():
        cmds.workspaceControl(CONTROL, edit=True, dockToControl=('TimeSlider', 'top'))
    elif main and main.isVisible():
        cmds.workspaceControl(CONTROL, edit=True, dockToControl=('MainPane', 'bottom'))


def stateKey():
    """Mayaの版ごとに保存先を分ける。"""
    return 'mayaDock' + str(cmds.about(majorVersion=True))


def savedState():
    """破損した設定を除いた前回の配置を返す。"""
    value = readSettings().get(stateKey(), {})
    return value if isinstance(value, dict) else {}


class DockWatcher(QtCore.QObject):
    """移動・サイズ変更・ドックの付け替えをまとめて保存する。"""

    def __init__(self, widget):
        """画面を所有者として保存タイマーと監視対象を登録する。"""
        super().__init__(widget)
        self.widget = widget
        self.targets = []
        self._tab_limits = None
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.flush)
        self.bind()

    def bind(self):
        """ドック移動後に変化した親のウィンドウへ監視を付け直す。"""
        # Mayaはドック移動時にタブ/スタック側だけを付け替える場合がある。
        # 内容とトップウィンドウだけでなく、その間の親の変更も監視する。
        targets = [target for target in QtWidgets.QApplication.allWidgets()
                   if shiboken.isValid(target) and (target is self.widget or target.isAncestorOf(self.widget))]
        for target in self.targets:
            if shiboken.isValid(target):
                target.removeEventFilter(self)
        self.targets = [target for target in targets if target is not None]
        for target in self.targets:
            target.installEventFilter(self)
        self._update_tab_limits()

    def _update_tab_limits(self):
        """QPE表示中だけ、Mayaのタブが記憶したサイズを最小値に使わない。"""
        tab = self.widget.parentWidget()
        while tab is not None and not isinstance(tab, QtWidgets.QTabWidget):
            tab = tab.parentWidget()
        active = (tab is not None and tab.currentWidget() is not None
                  and tab.currentWidget().isAncestorOf(self.widget))
        previous = self._tab_limits
        if previous and (not active or previous[0] is not tab):
            old_tab, policy, minimum = previous
            if shiboken.isValid(old_tab):
                old_tab.setSizePolicy(policy)
                old_tab.setMinimumSize(minimum)
                old_tab.updateGeometry()
            self._tab_limits = None
        if active and self._tab_limits is None:
            self._tab_limits = (tab, tab.sizePolicy(), tab.minimumSize())
            # Mayaのタブは現在サイズをminimumSizeHintとして返すことがある。
            # 共有エディターの制約は変更せず、QPEを表示する間だけ無視する。
            area = self.widget._dockViewport
            tab.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Ignored)
            tab.setMinimumSize(area.minimumWidth() + 4,
                               area.minimumHeight() + tab.tabBar().sizeHint().height() + 4)
            tab.updateGeometry()

    def eventFilter(self, watched, event):
        """イベントを妨げず、配置が落ち着いてから保存する。"""
        if not _quitting and event.type() in (QtCore.QEvent.Move, QtCore.QEvent.Resize,
                QtCore.QEvent.ParentChange, QtCore.QEvent.Show, QtCore.QEvent.Hide,
                QtCore.QEvent.WindowStateChange):
            self.timer.start()
        return False

    def flush(self):
        """監視の更新と保存を行う。"""
        if not _quitting:
            _repair_fixed_row_dock()
            self.bind()
            saveState()


def saveState():
    """QPEの配置だけを保存し、他のMayaパネルの配置は変更しない。"""
    if _quitting or not cmds.workspaceControl(CONTROL, exists=True):
        return
    from qpeHost import _window
    if _window is None or not shiboken.isValid(_window):
        return
    # ドックのタブ順・入れ子はMayaのワークスペース自身に保存させる。
    # stateStringはユーザー定義値であり、配置のシリアライズではない。
    state = dict(savedState(), open=_open,
                 floating=cmds.workspaceControl(CONTROL, query=True, floating=True))
    state.pop('state', None)
    if state['floating']:
        rect = _window.window().normalGeometry()
        if rect.isValid():
            state['geometry'] = [rect.x(), rect.y(), rect.width(), rect.height()]
    _window.saveLayout()
    if state != savedState():
        writeSettings({stateKey(): state})


def closed():
    """明示的に閉じた場合だけ次回の自動表示を止める。"""
    global _open
    if not _quitting:
        _open = False
        saveState()


def quitting():
    """終了時の非表示・破棄で開閉状態が上書きされる前に保存する。"""
    global _quitting
    saveState()
    _quitting = True
    if _watcher is not None and shiboken.isValid(_watcher):
        _watcher.timer.stop()
    from qpeHost import _window
    if _window is not None and shiboken.isValid(_window):
        # MayaがQtを破棄し始めてからのHide通知では遅い場合がある。
        # 開いていた状態を保存した後、まだQtが有効な終了通知で監視・読込を止める。
        for timer in _window.findChildren(QtCore.QTimer):
            timer.stop()
        organizer = _window.organizer
        if organizer.task:
            organizer.task.cancel.set()
        for job in organizer.queue:
            job[-1]['state'] = 'Saved for recovery'
        organizer.queue.clear()
        workspace = organizer.workspace
        workspace.serial += 1
        workspace.thumbnailSerial += 1
        workspace.productivity.serial += 1
        for task in (workspace.task, workspace.productivity.task):
            if task:
                task.cancel.set()
        for dialog in organizer.dialogs:
            if shiboken.isValid(dialog):
                dialog.close()
        _window.hide()
        # Python終了時までQt子ウィジェットを残すとshibokenの破棄順で落ちる場合がある。
        # workspaceControl自体は残してMayaのドック保存を保ち、QPE内容だけ先に破棄する。
        _window.deleteLater()
        QtCore.QCoreApplication.sendPostedEvents(_window, QtCore.QEvent.DeferredDelete)


def opened(widget, restoring=False):
    """復元スクリプトと終了通知を重複せず登録する。

    Args:
        widget (Explorer): Mayaに取り付け済みの画面。
        restoring (bool): Maya標準の配置復元から呼ばれた場合。
    """
    global _watcher, _open, _quitJob
    _open = savedState().get('open', True) if restoring else True
    cmds.workspaceControl(CONTROL, edit=True,
                          uiScript='import qpeHost; qpeHost.restore()',
                          closeCommand='import qpeDock; qpeDock.closed()')
    if _watcher is None or not shiboken.isValid(_watcher):
        _watcher = DockWatcher(widget)
    if _quitJob is None or not cmds.scriptJob(exists=_quitJob):
        _quitJob = cmds.scriptJob(event=['quitApplication', quitting], runOnce=True)
    if not _open:
        QtCore.QTimer.singleShot(0, hideClosed)
    _watcher.timer.start()


def hideClosed():
    """標準復元が閉じていたQPEを表示した場合だけ非表示に戻す。"""
    if not _open and cmds.workspaceControl(CONTROL, exists=True):
        cmds.workspaceControl(CONTROL, edit=True, visible=False)


def restoreState(widget):
    """標準の保存ドックがない場合にQPE個別の状態から復元する。

    Args:
        widget (Explorer): 新規作成した画面。
    """
    state = savedState()
    if cmds.workspaceControl(CONTROL, query=True, floating=True):
        geometry = state.get('geometry')
        if isinstance(geometry, list) and len(geometry) == 4 and all(isinstance(v, int) for v in geometry):
            rect = QtCore.QRect(*geometry)
            screens = QtWidgets.QApplication.screens()
            if not any(screen.availableGeometry().intersects(rect) for screen in screens):
                rect.moveTopLeft(screens[0].availableGeometry().topLeft() + QtCore.QPoint(40, 40))
            widget.window().setGeometry(rect)
    cmds.workspaceControl(CONTROL, edit=True, restore=True)


def startup():
    """前回開いていたQPEだけをMayaの起動処理後に復元する。"""
    global _started
    if _started:
        return
    _started = True
    if savedState().get('open', False):
        from maya import utils
        utils.executeDeferred(restorePrevious)


def restorePrevious():
    """標準復元済みならタブの選択や折り畳みを変更せず内容を補う。"""
    from qpeHost import show, restore
    if cmds.workspaceControl(CONTROL, exists=True):
        restore()
    else:
        show()

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
_closeGeneration = 0


def _control_widget(name):
    """既存ラッパーを優先し、他UIのラッパーを新たに作らない。"""
    pointer = OpenMayaUI.MQtUtil.findControl(name)
    if not pointer:
        return None
    # Qt5で既存の派生型をQWidgetとして包み直すと、旧ラッパーが無効になる場合がある。
    # allWidgets()で全UIをラップせず、Python側で既に生きている対象だけを再利用する。
    for widget in shiboken.getAllValidWrappers():
        if (isinstance(widget, QtWidgets.QWidget) and shiboken.isValid(widget)
                and int(shiboken.getCppPointer(widget)[0]) == int(pointer)):
            return widget
    widget = shiboken.wrapInstance(int(pointer), QtWidgets.QWidget)
    return widget if shiboken.isValid(widget) else None


def _parent_widget(widget):
    """再ドックで無効になった親はたどらず、補正を中止できるようにする。"""
    if widget is None or not shiboken.isValid(widget):
        return None
    try:
        parent = widget.parentWidget()
        return parent if parent is not None and shiboken.isValid(parent) else None
    except RuntimeError:
        # Qt5では親の付け替え中に無効なPythonラッパーが返る場合がある。
        return None


def _dock_splitter(control):
    """再ドックで無効になった親ラッパーを使わず、直接の分割領域を返す。"""
    # 全ウィジェット走査にはMayaが付け替え中の旧splitterも含まれる。
    # 現在のcontrolから直接たどり、無関係な破棄待ちの領域を参照しない。
    item = control
    while item is not None and shiboken.isValid(item):
        parent = _parent_widget(item)
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
    parent = _parent_widget(control)
    parents = []
    while parent is not None:
        # Qt5の一時的な親ラッパーを判定中に解放しない。監視や所有権は付けない。
        parents.append(parent)
        if isinstance(parent, QtWidgets.QTabWidget) and parent.count() > 1:
            # 利用者が他エディターとまとめたタブを自動的に分離しない。
            return
        parent = _parent_widget(parent)
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
    """QPEの画面と専用workspaceControlだけを監視する。"""

    def __init__(self, widget):
        """画面の寿命に属するタイマーを作り、共有親には変更を加えない。"""
        super().__init__(widget)
        self.widget = widget
        self.control = _control_widget(CONTROL)
        self.targets = []
        self.active = True
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(350)
        self.timer.timeout.connect(self.flush)
        # 配置補正は表示・復元時に一度だけ予約し、保存処理から切り離す。
        self.restoreTimer = QtCore.QTimer(self)
        self.restoreTimer.setSingleShot(True)
        self.restoreTimer.timeout.connect(self.restorePlacement)
        widget.destroyed.connect(self.stop)
        self.bind()

    def isCurrent(self):
        """遅延通知が現在の画面・現在のドックに属するかを確認する。"""
        from qpeHost import _window
        if (_quitting or not self.active or _watcher is not self or _window is not self.widget
                or not shiboken.isValid(self.widget)):
            return False
        control = _control_widget(CONTROL)
        if control is None or not control.isAncestorOf(self.widget):
            return False
        # Mayaは再ドック時に専用controlも作り直す。新しい画面の親にだけ付け直す。
        if self.control is not control:
            self.control = control
            self.bind()
        return True

    def bind(self):
        """Maya本体・共有タブ・共有splitterへの監視は設置しない。"""
        for target in self.targets:
            if shiboken.isValid(target):
                target.removeEventFilter(self)
        self.targets = [target for target in (self.widget, self.control)
                        if target is not None and shiboken.isValid(target)]
        for target in self.targets:
            target.installEventFilter(self)

    @QtCore.Slot()
    def stop(self):
        """旧画面の予約と監視を解除する。繰り返し呼んでも安全。"""
        self.active = False
        # Maya Qt5では親のdestroyed通知までに子タイマーが削除される場合がある。
        # Python参照を保持している利用側からの停止も、Qt破棄後には何もしない。
        if not shiboken.isValid(self):
            self.targets = []
            return
        for timer in (self.timer, self.restoreTimer):
            if shiboken.isValid(timer):
                timer.stop()
        for target in self.targets:
            if shiboken.isValid(target):
                target.removeEventFilter(self)
        self.targets = []

    def eventFilter(self, watched, event):
        """QPEの変化だけ保存を予約し、イベントは通常どおり配送する。"""
        if self.active and not _quitting and event.type() in (
                QtCore.QEvent.Move, QtCore.QEvent.Resize, QtCore.QEvent.ParentChange,
                QtCore.QEvent.Show, QtCore.QEvent.Hide, QtCore.QEvent.WindowStateChange):
            self.timer.start()
        return False

    def flush(self):
        """現在の画面の状態だけを保存し、レイアウトは変更しない。"""
        if self.isCurrent():
            saveState()

    def restorePlacement(self):
        """表示時の補正を生存中の画面にだけ適用する。"""
        if self.isCurrent():
            if _open:
                _repair_fixed_row_dock()
            else:
                hideClosed()


def releaseWatcher():
    """再生成前に旧監視を止め、遅延破棄を通常のQtループへ任せる。"""
    global _watcher
    previous, _watcher = _watcher, None
    if previous is not None and shiboken.isValid(previous):
        previous.stop()
        previous.deleteLater()


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


def closed(generation=None):
    """現在のドックを閉じた通知だけで次回の自動表示を止める。

    Args:
        generation (int | None): 登録したcloseCommandの世代。古い通知は無視する。
    """
    global _open
    if not _quitting and generation == _closeGeneration:
        _open = False
        saveState()
        releaseWatcher()


def quitting():
    """終了時の非表示・破棄で開閉状態が上書きされる前に保存する。"""
    global _quitting
    saveState()
    _quitting = True
    releaseWatcher()
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
    global _watcher, _open, _quitJob, _closeGeneration
    _open = savedState().get('open', True) if restoring else True
    _closeGeneration += 1
    cmds.workspaceControl(CONTROL, edit=True,
                          uiScript='import qpeHost; qpeHost.restore()',
                          closeCommand='import qpeDock; qpeDock.closed(%d)' % _closeGeneration)
    if (_watcher is None or not shiboken.isValid(_watcher)
            or _watcher.widget is not widget or not _watcher.active):
        releaseWatcher()
        _watcher = DockWatcher(widget)
    if _quitJob is None or not cmds.scriptJob(exists=_quitJob):
        _quitJob = cmds.scriptJob(event=['quitApplication', quitting], runOnce=True)
    # Mayaのタブ・親の付け替えが完了してから、この表示要求だけを補正する。
    _watcher.restoreTimer.start(350)
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

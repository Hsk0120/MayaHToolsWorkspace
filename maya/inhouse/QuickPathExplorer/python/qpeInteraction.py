"""選択を変えない右クリックと、列ごとの入力をまとめる。"""
from qpeQt import QtCore, QtGui, QtWidgets, shiboken


class Interaction(QtCore.QObject):
    """このブラウザーの一覧だけを監視し、Mayaの入力には触れない。"""

    def __init__(self, explorer):
        """動的に増えるカラムも同じ入力規則で扱う。

        Args:
            explorer (Explorer): 対象ブラウザー。
        """
        super().__init__(explorer)
        self.explorer = explorer
        self.drag = None
        app = QtWidgets.QApplication.instance()
        self.attach(explorer.files)
        app.focusChanged.connect(self.updateFocus)

    def attach(self, view):
        """生存中の一覧だけへ監視を登録する。

        Args:
            view (QAbstractItemView): 対象一覧。
        """
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)
        view.viewport().setMouseTracking(True)
        view.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)

    def viewFor(self, watched):
        """対象のviewportから一覧を取得する。

        Args:
            watched (QObject): イベント対象。

        Returns:
            QAbstractItemView | None: このブラウザーの一覧。
        """
        if not isinstance(watched, QtWidgets.QWidget):
            return None
        owner = self.explorer
        if watched is owner.files or isinstance(watched, QtWidgets.QListView):
            return watched
        view = watched.parentWidget()
        if view is owner.files or (isinstance(view, QtWidgets.QListView) and owner.columns.isAncestorOf(view)):
            if watched is view.viewport():
                return view
        return None

    def updateFocus(self, *unused):
        """操作中の列と祖先経路の選択色を分ける。

        Args:
            unused (tuple): Qtのフォーカス通知。
        """
        owner = self.explorer
        if not shiboken.isValid(owner):
            return
        focus = QtWidgets.QApplication.focusWidget()
        for view in owner.columns.findChildren(QtWidgets.QListView):
            active = (focus is view or view.isAncestorOf(focus)) if focus is not None else False
            color = '#326c7b' if active and owner.window().isActiveWindow() else '#50565b'
            if view.property('qpeSelectionColor') != color:
                view.setProperty('qpeSelectionColor', color)
                view.setStyleSheet('QListView::item:selected { background: %s; color: white; }' % color)

    def eventFilter(self, watched, event):
        """右クリック・ホイール・境界操作を一覧内で処理する。

        Args:
            watched (QObject): イベント対象。
            event (QEvent): Qtイベント。

        Returns:
            bool: この部品が処理を終えたか。
        """
        owner = self.explorer
        view = self.viewFor(watched)
        kind = event.type()
        if view is None:
            return False
        if view is owner.files and kind == QtCore.QEvent.MouseButtonDblClick and event.button() == QtCore.Qt.LeftButton:
            owner.openFileIndex(view.indexAt(event.pos()))
            # QtのdoubleClickedによる再実行を防ぎ、最初の選択状態によらず一度だけ開く。
            return True
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.RightButton:
            # Qt標準のmousePressEventによる選択変更を止める。メニューはContextMenuで開く。
            return True
        if kind == QtCore.QEvent.ContextMenu:
            point = view.visualRect(view.currentIndex()).center() if event.reason() == QtGui.QContextMenuEvent.Keyboard else event.pos()
            if view is owner.files:
                owner._fileMenu(point)
            else:
                owner._folderMenu(view.viewport().mapTo(owner.columns.viewport(), point))
            return True
        if kind == QtCore.QEvent.Wheel:
            pixel = event.pixelDelta()
            angle = event.angleDelta()
            delta = pixel if not pixel.isNull() else angle
            dx, dy = delta.x(), delta.y()
            if event.modifiers() & QtCore.Qt.ShiftModifier and not dx:
                dx, dy = dy, 0
            horizontal = owner.columns.horizontalScrollBar() if view is not owner.files else view.horizontalScrollBar()
            # 斜め入力の小さい方も捨てない。境界では両成分をここで消費する。
            for bar, amount in ((horizontal, dx), (view.verticalScrollBar(), dy)):
                if pixel.isNull():
                    amount = amount / 120.0 * bar.singleStep() * QtWidgets.QApplication.wheelScrollLines()
                bar.setValue(bar.value() - round(amount))
            event.accept()
            return True
        if kind == QtCore.QEvent.KeyPress:
            focus = QtWidgets.QApplication.focusWidget()
            if focus not in (view, view.viewport()):
                return False
            key = event.key()
            if key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and event.modifiers() == QtCore.Qt.NoModifier:
                if view is owner.files and len(owner.selectedPaths()) != 1:
                    return True
                path = owner.selectedPath() if view is owner.files else owner.currentDirectory
                owner.renamePath(path)
                return True
            if key == QtCore.Qt.Key_Space and view is owner.files and event.modifiers() == QtCore.Qt.NoModifier:
                owner.toggleQuickLook()
                return True
        if view is not owner.files and kind in (QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseMove,
                                                 QtCore.QEvent.MouseButtonRelease, QtCore.QEvent.MouseButtonDblClick):
            x = event.pos().x()
            edge = x >= watched.width() - max(5, round(5 * getattr(owner.columns, 'columnScale', 1)))
            if kind == QtCore.QEvent.MouseButtonDblClick and event.button() == QtCore.Qt.LeftButton and edge:
                owner.columns.resetWidth(view.rootIndex())
                return True
            if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton and edge:
                self.drag = (QtCore.QPersistentModelIndex(view.rootIndex()), event.globalPos().x(), view.width())
                watched.grabMouse()
                return True
            if kind == QtCore.QEvent.MouseMove:
                if self.drag:
                    index, start, width = self.drag
                    owner.columns.setManualWidth(QtCore.QModelIndex(index), width + event.globalPos().x() - start)
                    return True
                watched.setCursor(QtCore.Qt.SplitHCursor if edge else QtCore.Qt.ArrowCursor)
            if kind == QtCore.QEvent.MouseButtonRelease and self.drag:
                index, start, width = self.drag
                # Qt5でmove通知がまとめられた場合も、最後のポインター位置を反映する。
                owner.columns.setManualWidth(QtCore.QModelIndex(index), width + event.globalPos().x() - start)
                self.drag = None
                watched.releaseMouse()
                return True
        return False

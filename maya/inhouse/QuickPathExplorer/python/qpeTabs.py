"""フォルダーごとのナビゲーション状態を保持するタブ。"""
import copy
import os
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets
from qpeFileIcons import folderIcon


class TabGlyphButton(QtWidgets.QAbstractButton):
    """背景を常時描かない、線画の閉じる・追加ボタン。"""

    def __init__(self, strip, glyph, parent):
        """塗りつぶしはホバーと押下時のみ使用する。"""
        super().__init__(parent)
        self.strip = strip
        self.glyph = glyph
        self.setFocusPolicy(QtCore.Qt.NoFocus)
        self.setAccessibleName('Close tab' if glyph == 'close' else 'New tab')
        self.setToolTip('Close tab' if glyph == 'close' else 'New folder tab')

    def sizeHint(self):
        """小さな図形に十分なクリック領域を確保する。"""
        size = round(28 * self.strip.scale)
        return QtCore.QSize(size, size)

    def enterEvent(self, event):
        """ホバー背景を更新する。"""
        super().enterEvent(event)
        self.update()

    def leaveEvent(self, event):
        """ホバー背景を消す。"""
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        """DPI倍率に合わせて細い×または＋を描く。"""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        colors = self.strip.colors()
        scale = self.strip.scale
        if self.underMouse() or self.isDown():
            painter.setPen(QtCore.Qt.NoPen)
            color = QtGui.QColor(colors['text'])
            color.setAlpha(28 if self.isDown() else 18)
            painter.setBrush(color)
            rect = QtCore.QRectF(self.rect()).adjusted(2 * scale, 2 * scale, -2 * scale, -2 * scale)
            painter.drawRoundedRect(rect, 4 * scale, 4 * scale)
        glyph_color = QtGui.QColor(colors['text'])
        if not self.isEnabled():
            glyph_color.setAlpha(75)
        painter.setPen(QtGui.QPen(glyph_color, max(1.0, scale)))
        center = QtCore.QRectF(self.rect()).center()
        radius = 4 * scale
        if self.glyph == 'close':
            painter.drawLine(center + QtCore.QPointF(-radius, -radius), center + QtCore.QPointF(radius, radius))
            painter.drawLine(center + QtCore.QPointF(radius, -radius), center + QtCore.QPointF(-radius, radius))
        else:
            painter.drawLine(center + QtCore.QPointF(-radius, 0), center + QtCore.QPointF(radius, 0))
            painter.drawLine(center + QtCore.QPointF(0, -radius), center + QtCore.QPointF(0, radius))
        painter.end()


class FolderTabBar(QtWidgets.QTabBar):
    """標準幅から均等に縮み、下限以降は横送りするタブ。"""

    def mouseReleaseEvent(self, event):
        """中ボタンで対象タブを閉じる。固定タブの保護は既存のcloseへ委ねる。"""
        if event.button() == QtCore.Qt.MiddleButton:
            index = self.tabAt(event.pos())
            if index >= 0:
                self.tabCloseRequested.emit(index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def tabInserted(self, index):
        """Qt標準の四角い閉じるボタンを置き換える。"""
        super().tabInserted(index)
        for side in (QtWidgets.QTabBar.LeftSide, QtWidgets.QTabBar.RightSide):
            previous = self.tabButton(index, side)
            if previous:
                self.setTabButton(index, side, None)
                previous.deleteLater()
        button = TabGlyphButton(self.parentWidget(), 'close', self)
        button.clicked.connect(lambda: self._closeButtonClicked(button))
        self.setTabButton(index, QtWidgets.QTabBar.RightSide, button)
        self.setTabIcon(index, folderIcon())

    def _closeButtonClicked(self, button):
        """追加・削除後も現在の番号を解決して対象タブを閉じる。"""
        for index in range(self.count()):
            if self.tabButton(index, QtWidgets.QTabBar.RightSide) is button:
                self.tabCloseRequested.emit(index)
                break

    def mouseMoveEvent(self, event):
        """非選択タブのホバーを再描画する。"""
        super().mouseMoveEvent(event)
        self.update()

    def leaveEvent(self, event):
        """マウスが離れたタブのホバーを解除する。"""
        super().leaveEvent(event)
        self.update()

    def paintEvent(self, event):
        """角丸の面、左寄せのアイコンと名前、控えめな区切りを描く。"""
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        strip = self.parentWidget()
        colors = strip.colors()
        painter.fillRect(self.rect(), strip.bandColor())
        scale = strip.scale
        hover = self.tabAt(self.mapFromGlobal(QtGui.QCursor.pos())) if self.underMouse() else -1
        for index in range(self.count()):
            rect = QtCore.QRectF(self.tabRect(index))
            if not rect.intersects(QtCore.QRectF(self.rect())):
                continue
            selected = index == self.currentIndex()
            if selected or index == hover:
                painter.setPen(QtCore.Qt.NoPen)
                painter.setBrush(QtGui.QColor(colors['window']) if selected else strip.bandColor().lighter(104))
                path = QtGui.QPainterPath()
                path.addRoundedRect(rect.adjusted(1, 1, -1, 5 * scale), 7 * scale, 7 * scale)
                painter.save()
                painter.setClipRect(rect)
                painter.drawPath(path)
                painter.restore()
            elif index + 1 != self.currentIndex():
                painter.setPen(QtGui.QPen(QtGui.QColor(colors['border']), 1))
                painter.drawLine(QtCore.QPointF(rect.right(), rect.top() + 9 * scale),
                                 QtCore.QPointF(rect.right(), rect.bottom() - 9 * scale))
            icon_size = round(16 * scale)
            self.tabIcon(index).paint(painter, QtCore.QRect(round(rect.left() + 12 * scale),
                                      round(rect.center().y() - icon_size / 2), icon_size, icon_size))
            text_rect = rect.adjusted(36 * scale, 0, -36 * scale, 0)
            painter.setPen(QtGui.QColor(colors['text']))
            text = self.fontMetrics().elidedText(self.tabText(index), QtCore.Qt.ElideRight, max(0, int(text_rect.width())))
            painter.drawText(text_rect, QtCore.Qt.AlignLeft | QtCore.Qt.AlignVCenter, text)
            if selected and self.hasFocus():
                painter.setPen(QtGui.QPen(QtGui.QColor(colors['muted']), 1, QtCore.Qt.DotLine))
                painter.setBrush(QtCore.Qt.NoBrush)
                painter.drawRoundedRect(rect.adjusted(3, 3, -3, -3), 4, 4)
        painter.end()

    def tabSizeHint(self, index):
        """名前の長さによらないDPI適用済みの幅を返す。

        Args:
            index (int): タブ番号。

        Returns:
            QSize: 標準240、最小100論理ピクセルの寸法。
        """
        scale = self.parentWidget().scale
        width = max(round(100 * scale), min(round(240 * scale),
                    self.width() // max(1, self.count())))
        return QtCore.QSize(width, max(round(32 * scale), self.fontMetrics().height() + round(12 * scale)))

    def minimumTabSizeHint(self, index):
        """Qtが長い名前だけを追加で圧縮することを防ぐ。"""
        return self.tabSizeHint(index)


class FolderTabStrip(QtWidgets.QWidget):
    """タブ列と末尾の追加ボタンを一つの幅配分として扱う。"""

    def __init__(self, parent):
        """操作領域を作り、OSのDPIはQtの論理座標に委ねる。"""
        super().__init__(parent)
        self.scale = 1.0
        self.bar = FolderTabBar(self)
        self.bar.setExpanding(False)
        self.bar.setTabsClosable(True)
        self.bar.setUsesScrollButtons(True)
        self.bar.setDrawBase(False)
        self.bar.setMouseTracking(True)
        self.bar.setElideMode(QtCore.Qt.ElideRight)
        self.addButton = TabGlyphButton(self, 'add', self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def colors(self):
        """Mayaを含む現在のホスト配色を取得する。"""
        appearance = getattr(self.parentWidget(), 'appearance', None)
        return appearance.theme.colors if appearance else dict(window='#f9f9f9',
                base='#ffffff', text='#202020', inactive='#e5e5e5', border='#dddddd')

    def paintEvent(self, event):
        """非選択側のタブ帯を選択タブと区別する。"""
        painter = QtGui.QPainter(self)
        painter.fillRect(self.rect(), self.bandColor())
        painter.end()

    def bandColor(self):
        """タブバーと余白に同じ帯色を使用する。"""
        color = QtGui.QColor(self.colors()['window'])
        return color.darker(108) if color.lightness() > 128 else color.darker(125)

    def refresh(self):
        """タブ枚数・ウィンドウ幅・Maya/UI倍率から配置を更新する。"""
        appearance = getattr(self.parentWidget(), 'appearance', None)
        self.scale = appearance.dpiScale * appearance.uiPercent / 100.0 if appearance else 1.0
        height = max(round(32 * self.scale), self.fontMetrics().height() + round(12 * self.scale))
        self.setFixedHeight(height)
        button_width = round(36 * self.scale)
        gap = round(4 * self.scale)
        width = min(self.bar.count() * round(240 * self.scale), max(1, self.width() - button_width - gap))
        self.bar.setGeometry(0, 0, width, height)
        # 幅が同じでも枚数・倍率が変わった場合はQtの寸法キャッシュを更新する。
        self.bar.setIconSize(QtCore.QSize(round(16 * self.scale), round(16 * self.scale)))
        self.bar.setExpanding(True)
        self.bar.setExpanding(False)
        for index in range(self.bar.count()):
            button = self.bar.tabButton(index, QtWidgets.QTabBar.RightSide)
            if button:
                button.setFixedSize(button.sizeHint())
        self.addButton.setGeometry(width + gap, 0, button_width, height)

    def resizeEvent(self, event):
        """ウィンドウの拡縮に追従して各タブを再配分する。"""
        super().resizeEvent(event)
        self.refresh()


class FolderTabs(QtCore.QObject):
    """一つの表示モデルを使い、要求世代を更新してタブを切り替える。"""

    def __init__(self, explorer):
        """タブバーと追加ボタンを既存ウィンドウへ組み込む。"""
        super().__init__(explorer)
        self.explorer = explorer
        self.states = [None]
        self.closed = []
        self.active = 0
        self.pendingSerial = None
        self.strip = FolderTabStrip(explorer)
        self.bar = self.strip.bar
        self.bar.addTab('Folder')
        self.addButton = self.strip.addButton
        explorer.layout().insertWidget(0, self.strip)
        self.bar.currentChanged.connect(self.switch)
        self.bar.tabCloseRequested.connect(self.close)
        self.addButton.clicked.connect(self.add)
        self.updateTitle()
        self.strip.refresh()

    def snapshot(self):
        """現在の履歴・選択・表示位置を独立した値として保存する。"""
        e = self.explorer
        e._rememberColumns()
        flags = self.states[self.active] or {} if self.active >= 0 else {}
        return dict(path=e.currentDirectory, root=e.browseRoot, pinned=bool(flags.get('pinned')), locked=bool(flags.get('locked')),
                    history=list(e._history), index=e._historyIndex,
                    columns=copy.deepcopy(e._columnStates), search=e.search.text(),
                    filter=e.fileFilter.currentIndex(), selected=e.selectedPaths(),
                    vertical=e.files.verticalScrollBar().value())

    def updateTitle(self):
        """現在のフォルダー名とフルパスをタブへ表示する。"""
        path = self.explorer.currentDirectory
        self.bar.setTabText(self.active, Path(path).name or path or 'Folder')
        self.updateTabPresentation(self.active)

    def updateTabPresentation(self, index):
        """固定状態を再表示後も示し、閉じられないボタンを無効にする。"""
        state = self.states[index] or {}
        path = self.explorer.currentDirectory if index == self.active else state.get('path', '')
        pinned = bool(state.get('pinned'))
        self.bar.setTabToolTip(index, path + ('\nPinned — unpin to close' if pinned else '')
                              + ('\nLocation locked — navigation opens a new tab' if state.get('locked') else ''))
        button = self.bar.tabButton(index, QtWidgets.QTabBar.RightSide)
        if button:
            button.setEnabled(not pinned)
            button.setToolTip('Pinned — unpin to close' if pinned else 'Close tab')
            button.setAccessibleName(button.toolTip())

    def add(self):
        """現在の場所を起点とする独立したタブを追加する。"""
        state = self.snapshot()
        state.update(pinned=False, locked=False)
        self.states.append(state)
        index = self.bar.addTab('Folder')
        self.strip.refresh()
        self.bar.setCurrentIndex(index)

    def switch(self, index):
        """モデル要求を更新し、保存済みのタブ状態を復元する。"""
        if index < 0 or index == self.active:
            return
        if self.active >= 0 and self.pendingSerial != self.explorer._navigationSerial:
            self.states[self.active] = self.snapshot()
        self.active = index
        state = self.states[index]
        e = self.explorer
        e.browseRoot = state['root']
        e._columnStates = copy.deepcopy(state['columns'])
        e._history = list(state['history'])
        e._historyIndex = state['index']
        e.search.setText(state['search'])
        e.fileFilter.setCurrentIndex(state['filter'])
        # 別タブのカラムを新タブの保存状態に書き戻さない。
        e._fromColumn = True
        try:
            e.navigate(state['path'], record=False)
        finally:
            e._fromColumn = False
        serial = e._navigationSerial
        self.pendingSerial = serial
        attempts = [0]

        def restore():
            """古いタブの遅延復元を破棄し、読込完了後に選択を戻す。"""
            if e._suspended or serial != e._navigationSerial:
                return
            attempts[0] += 1
            if e.fileModel.states.get(e.currentDirectory, ('loading', ''))[0] == 'loading' and attempts[0] < 100:
                QtCore.QTimer.singleShot(30, restore)
                return
            selection = e.files.selectionModel()
            for path in state['selected']:
                item = e.fileProxy.mapFromSource(e.fileModel.index(path))
                if item.isValid():
                    selection.select(item, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
                    selection.setCurrentIndex(item, QtCore.QItemSelectionModel.NoUpdate)
            e.files.verticalScrollBar().setValue(state['vertical'])
            self.pendingSerial = None
            saved = state['columns'].get(os.path.normcase(e.currentDirectory))
            if saved:
                e._restoreColumns(saved, serial)
        QtCore.QTimer.singleShot(0, restore)

    def openPath(self, path):
        """メニュー開始時のフォルダーを新しいタブで開く。

        Args:
            path (str): 固定されたフォルダーのパス。
        """
        state = self.snapshot()
        state.update(path=path, selected=[], columns={}, history=[path], index=0,
                     search='', filter=0, vertical=0, pinned=False, locked=False)
        self.states.append(state)
        index = self.bar.addTab('Folder')
        self.strip.refresh()
        self.bar.setCurrentIndex(index)

    def close(self, index):
        """最後の一枚を残し、閉じたタブの状態だけを破棄する。"""
        if len(self.states) == 1 or (self.states[index] or {}).get('pinned'):
            return
        self.closed.append(self.snapshot() if index == self.active else copy.deepcopy(self.states[index]))
        self.closed = self.closed[-20:]
        if index == self.active:
            self.bar.setCurrentIndex(index - 1 if index else 1)
        self.bar.blockSignals(True)
        self.states.pop(index)
        self.bar.removeTab(index)
        if index < self.active:
            self.active -= 1
        self.bar.setCurrentIndex(self.active)
        self.bar.blockSignals(False)
        self.strip.refresh()

    def reopen(self):
        """最後に閉じたタブを元の表示状態で戻す。"""
        if not self.closed:
            return
        self.states.append(self.closed.pop())
        self.bar.addTab('Folder')
        self.strip.refresh()
        self.bar.setCurrentIndex(len(self.states) - 1)

    def session(self):
        """JSONへ保存できるタブ全体の値を返す。"""
        states = copy.deepcopy(self.states)
        if self.pendingSerial != self.explorer._navigationSerial:
            states[self.active] = self.snapshot()
        return dict(version=1, active=self.active, states=states, closed=self.closed)

    def saveSession(self):
        """MayaとWindows単体を別のキーへ保存する。"""
        from qpeSettings import writeSettings
        if self.explorer.currentDirectory:
            writeSettings({self.explorer._settingsKey + 'Tabs': self.session()})

    def restoreSession(self, value=None):
        """保存済みタブを復元し、消失した場所は一覧として報告する。"""
        from qpeSettings import readSettings
        value = value or readSettings().get(self.explorer._settingsKey + 'Tabs', {})
        if not isinstance(value, dict) or value.get('version') != 1:
            return False
        states, missing, original_indices = [], [], []
        for original_index, state in enumerate(value.get('states', [])[:100]):
            if not isinstance(state, dict) or not isinstance(state.get('path'), str):
                continue
            if not os.path.isdir(state['path']):
                missing.append(state['path'])
                continue
            if not all(key in state for key in ('root', 'history', 'index', 'columns', 'search', 'filter', 'selected', 'vertical')):
                continue
            states.append(copy.deepcopy(state))
            original_indices.append(original_index)
        if not states:
            return False
        self.bar.blockSignals(True)
        while self.bar.count():
            self.bar.removeTab(0)
        self.states = states
        for state in states:
            self.bar.addTab(Path(state['path']).name or state['path'])
        self.active = -1
        self.pendingSerial = None
        requested = int(value.get('active', 0))
        selected = original_indices.index(requested) if requested in original_indices else min(max(0, requested), len(states) - 1)
        self.bar.setCurrentIndex(selected)
        self.bar.blockSignals(False)
        self.strip.refresh()
        self.switch(selected)
        for index in range(len(states)):
            self.updateTabPresentation(index)
        self.closed = [s for s in value.get('closed', []) if isinstance(s, dict) and os.path.isdir(s.get('path', ''))][-20:]
        if missing:
            self.explorer.status.setText('Unavailable saved tabs: ' + '\n'.join(missing))
            self.explorer.status.show()
        return True

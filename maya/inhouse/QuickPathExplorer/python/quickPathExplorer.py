"""上下分割とお気に入りを備えた、Maya非依存のファイルブラウザー。"""
import os
import sys
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets, QAction, shiboken
from qpeSettings import readSettings, writeSettings
from qpePreview import PreviewJob
from qpeFileOperations import createEntry, renameEntry
from qpeAppearance import Appearance, BrowserItemDelegate
from qpeInlineRename import InlineRename
from qpeInteraction import Interaction
from qpeContextMenu import ContextMenu
from qpeDirectoryModel import DirectoryModel
from qpeFileIcons import FileIcons, fileType

ICON = Path(__file__).resolve().parents[1] / 'icons/quickPathExplorer.png'


class FolderModel(DirectoryModel):
    """省略された長い名前をホバーで全文確認できるモデル。"""

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """ツールチップにはフォルダーのフルパスを返す。

        Args:
            index (QModelIndex): 項目。
            role (int): Qtの要求するデータ種別。

        Returns:
            object: 標準データまたはフルパス。
        """
        if role == QtCore.Qt.ToolTipRole and index.isValid():
            return self.filePath(index)
        return super().data(index, role)


class FileFilter(QtCore.QSortFilterProxyModel):
    """検索中もルートの祖先フォルダーを保持する。"""

    def lessThan(self, left, right):
        """サイズ列は単位付き表示に関係なく実バイト数で比較する。

        Args:
            left (QModelIndex): 比較元。
            right (QModelIndex): 比較先。

        Returns:
            bool: 左を先に並べるか。
        """
        if left.column() == 1:
            return (left.data(QtCore.Qt.EditRole) or 0) < (right.data(QtCore.Qt.EditRole) or 0)
        return super().lessThan(left, right)

    def filterAcceptsRow(self, row, parent):
        """フォルダーの祖先と検索に一致するファイルを通す。

        Args:
            row (int): 行。
            parent (QModelIndex): 親。

        Returns:
            bool: 表示対象か。
        """
        index = self.sourceModel().index(row, 0, parent)
        if self.sourceModel().isDir(index):
            # QFileSystemModelは以前rootPathにしたディレクトリをFiles指定でも保持する。
            # 現在のルートまでの祖先だけを通し、訪問済みの子フォルダーは一覧へ出さない。
            root = getattr(self, 'directoryRoot', '')
            path = os.path.normcase(self.sourceModel().filePath(index)).replace('\\', '/').rstrip('/')
            return not root or root == path or root.startswith(path + '/')
        return super().filterAcceptsRow(row, parent)


class ColumnStyle(QtWidgets.QProxyStyle):
    """カラムの自動横移動を即時にして保存位置との競合を防ぐ。"""

    def styleHint(self, hint, option=None, widget=None, returnData=None):
        """横移動アニメーションだけを無効にする。

        Args:
            hint (QStyle.StyleHint): Qtの表示指定。
            option (QStyleOption | None): 描画設定。
            widget (QWidget | None): 描画対象。
            returnData (QStyleHintReturn | None): 追加戻り値。

        Returns:
            int: Qtの表示設定値。
        """
        if hint == QtWidgets.QStyle.SH_Widget_Animation_Duration:
            # 即時完了ではQtが子列と選択モデルの接続を省略するため、最短の完了通知を使う。
            if isinstance(widget, QtWidgets.QColumnView) and widget.currentIndex().parent() == widget.rootIndex():
                return 1
            return 0
        return super().styleHint(hint, option, widget, returnData)


class FolderColumns(QtWidgets.QColumnView):
    """選択変更で列が破棄される前に表示状態を通知する。"""
    aboutToNavigate = QtCore.Signal()

    def __init__(self, parent=None):
        """Qtが子列を表示した後にも空状態を更新する。

        Args:
            parent (QWidget | None): 所有者。
        """
        super().__init__(parent)
        self.widthMode = readSettings().get('columnWidthMode', 'fit')
        self._manualWidths = {}
        self._pendingSelectionPath = False
        self._hintTimer = QtCore.QTimer(self)
        self._hintTimer.setSingleShot(True)
        self._hintTimer.timeout.connect(self.finishColumns)

    def finishColumns(self):
        """Qtの選択接続後に、空一覧更新で隠れた現在列を復元する。"""
        ancestors = []
        index = self.currentIndex()
        while index.isValid():
            ancestors.append(index)
            index = index.parent()
        for view in self.findChildren(QtWidgets.QListView):
            if view.rootIndex().isValid() and view.rootIndex() not in ancestors:
                view.hide()
        views = [view for view in self.findChildren(QtWidgets.QListView)
                 if view.rootIndex().isValid() and view.rootIndex() == self.currentIndex()]
        # Qtが破棄待ちの列を保持していても、重複した列は表示しない。
        if views and self.emptyChild(self.currentIndex()):
            for view in views:
                view.hide()
        elif views and not any(view.isVisible() for view in views):
            views[-1].show()
        if self._pendingSelectionPath:
            self._pendingSelectionPath = False
            # 明示した階層移動だけで祖先のハイライトを確定する。
            # 非同期完了や再描画では、ユーザーの選択集合を変更しない。
            for view in self.findChildren(QtWidgets.QListView):
                child = self.currentIndex()
                while child.isValid() and child.parent() != view.rootIndex():
                    child = child.parent()
                selection = view.selectionModel()
                if view.isVisible() and child.isValid() and not selection.isSelected(child):
                    selection.select(child, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
        self.refreshHints()

    def emptyChild(self, index):
        """読込完了した空の末尾列かを返す。

        Args:
            index (QModelIndex): 列が表示する親。

        Returns:
            bool: 起点を除く空の列か。読込中・エラーは表示を保つ。
        """
        return (index.isValid() and index != self.rootIndex()
                and self.model().states.get(self.model().filePath(index), ('loading', ''))[0] == 'ready'
                and self.model().rowCount(index) == 0)

    def fitColumns(self):
        """階層数に応じて列を縮め、読める最小幅を保つ。"""
        if getattr(self, '_fittingColumns', False):
            return
        index = self.currentIndex()
        if not index.isValid():
            return
        scale = getattr(self, 'columnScale', 1.0)
        minimum = round(80 * scale)
        roots = []
        current = self.currentIndex()
        while current.isValid():
            roots.insert(0, current)
            if current == self.rootIndex():
                break
            current = current.parent()
        widths = [self.contentWidth(root) for root in roots]
        empty = self.emptyChild(roots[-1])
        if empty:
            widths[-1] = 0
        visible_count = len(roots) - int(empty)
        budget = self.viewport().width() - 2
        excess = max(0, sum(widths) - budget)
        # 現在地に近い4列は名前幅を保持し、古い祖先だけを縮める。
        # 保持した名前幅が収まらない場合は、省略せず横スクロールを使う。
        for i in range(max(0, visible_count - 4) if self.widthMode == 'fit' else 0):
            limit = minimum
            reduction = min(excess, max(0, widths[i] - limit))
            widths[i] -= reduction
            excess -= reduction
        self._fittingColumns = True
        try:
            anchor = self.horizontalAnchor()
            self.horizontalScrollBar().setValue(0)
            # Qt既定の列最小幅も更新しないとsetColumnWidthsの縮小が制限される。
            for view in self.findChildren(QtWidgets.QListView):
                view.setMinimumWidth(0 if self.emptyChild(view.rootIndex()) else minimum)
            self.setColumnWidths(widths)
            # グリップ非表示時のsetColumnWidthsは隣の列位置を再配置しない。
            # Qt自身のレイアウト経路で列位置とスクロール範囲を再計算する。
            if sum(widths) <= self.viewport().width():
                self.horizontalScrollBar().setValue(0)
            super().resizeEvent(QtGui.QResizeEvent(self.size(), self.size()))
            for view in self.findChildren(QtWidgets.QListView):
                if self.emptyChild(view.rootIndex()):
                    view.hide()
            if sum(widths) > self.viewport().width():
                self.restoreHorizontalAnchor(anchor)
        finally:
            self._fittingColumns = False
        self.refreshHints()

    def horizontalAnchor(self):
        """左端のカラム識別子と内部オフセットを取得する。

        Returns:
            tuple | None: 親パスと列内の論理ピクセル位置。
        """
        views = [v for v in self.findChildren(QtWidgets.QListView)
                 if v.isVisible() and v.rootIndex().isValid()]
        views.sort(key=lambda v: v.mapTo(self.viewport(), QtCore.QPoint()).x())
        for view in views:
            x = view.mapTo(self.viewport(), QtCore.QPoint()).x()
            if x + view.width() > 0:
                return (self.model().filePath(view.rootIndex()), -x)
        return None

    def restoreHorizontalAnchor(self, anchor):
        """同じカラムを基準に幅変更後の位置を復元する。

        Args:
            anchor (tuple | None): 親パスと列内オフセット。
        """
        if anchor is None:
            return
        path, offset = anchor
        views = {self.model().filePath(v.rootIndex()): v for v in self.findChildren(QtWidgets.QListView)
                 if v.isVisible() and v.rootIndex().isValid()}
        while path not in views:
            parent = str(Path(path).parent).replace('\\', '/')
            if parent == path:
                break
            path = parent
            offset = 0
        view = views.get(path)
        if view is not None:
            bar = self.horizontalScrollBar()
            x = view.mapTo(self.viewport(), QtCore.QPoint()).x()
            bar.setValue(bar.value() + x + min(offset, view.width() - 1))

    def contentWidth(self, root):
        """名前が読める幅を算出し、長すぎる名前には上限を設ける。

        Args:
            root (QModelIndex): 列が表示する親。

        Returns:
            int: DPI適用後の幅。
        """
        scale = getattr(self, 'columnScale', 1.0)
        path = self.model().filePath(root)
        if path in self._manualWidths:
            return round(self._manualWidths[path] * scale)
        metrics = self.fontMetrics()
        width = 0
        for row in range(self.model().rowCount(root)):
            width = max(width, metrics.horizontalAdvance(str(self.model().index(row, 0, root).data() or '')))
            if width >= round(1000 * scale):
                break
        return max(round(80 * scale), min(round(1040 * scale), width + round(48 * scale)))

    def setWidthMode(self, mode):
        """列幅方針を変更し保存する。

        Args:
            mode (str): fitまたはnames。
        """
        self.widthMode = mode if mode in ('fit', 'names') else 'fit'
        writeSettings({'columnWidthMode': self.widthMode})
        self.fitColumns()

    def setManualWidth(self, root, width):
        """境界ドラッグで変更した幅をセッション内で保持する。

        Args:
            root (QModelIndex): 列の親。
            width (int): 指定幅。
        """
        scale = getattr(self, 'columnScale', 1.0)
        self._manualWidths[self.model().filePath(root)] = max(100, min(1000, width / scale))
        if self.widthMode != 'names':
            self.setWidthMode('names')
        else:
            self.fitColumns()

    def resetWidth(self, root):
        """境界ダブルクリックで名前の幅へ戻す。

        Args:
            root (QModelIndex): 列の親。
        """
        self._manualWidths.pop(self.model().filePath(root), None)
        self.setWidthMode('names')

    def refreshHints(self, *unused):
        """子フォルダーが無い列にも意味が分かる表示を出す。

        Args:
            unused (tuple): モデルの変更通知。
        """
        for view in self.findChildren(QtWidgets.QListView):
            if hasattr(self, 'interaction'):
                self.interaction.attach(view)
            # Qtが後から作る子ビューにも、ホスト既定値ではなく同じ文字・行高を渡す。
            view.setFont(self.font())
            view.setProperty('qpeRowHeight', self.property('qpeRowHeight') or 22)
            if not isinstance(view.itemDelegate(), BrowserItemDelegate) or view.itemDelegate().parent() is not view:
                view.setItemDelegate(BrowserItemDelegate(view))
            view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAsNeeded)
            view.setAlternatingRowColors(True)
            if not view.isVisible() or not view.rootIndex().isValid():
                continue
            label = view.viewport().findChild(QtWidgets.QLabel, 'emptyColumnHint')
            if label is None:
                label = QtWidgets.QLabel('No subfolders', view.viewport())
                label.setObjectName('emptyColumnHint')
                label.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
                label.setAlignment(QtCore.Qt.AlignTop | QtCore.Qt.AlignHCenter)
                label.setWordWrap(True)
            label.setFont(self.font())
            path = view.model().filePath(view.rootIndex())
            state, error = view.model().states.get(path, ('loading', ''))
            label.setText(error if state == 'error' else 'No subfolders' if state == 'ready' else 'Loading…')
            label.setGeometry(6, 12, max(0, view.viewport().width() - 12), 60)
            label.setVisible(view.model().rowCount(view.rootIndex()) == 0)
        if hasattr(self, 'interaction'):
            self.interaction.updateFocus()

    def folderLoaded(self, path):
        """空の列と読込待ちの列を区別する。

        Args:
            path (str): 読込済みフォルダー。
        """
        if not hasattr(self, '_loadedFolders'):
            self._loadedFolders = set()
        self._loadedFolders.add(path)
        self.fitColumns()
        self._hintTimer.start(30)
        self.refreshHints()

    def resizeEvent(self, event):
        """ウィンドウやサイドバー変更に列幅を追従させる。

        Args:
            event (QResizeEvent): サイズ変更通知。
        """
        anchor = self.horizontalAnchor()
        super().resizeEvent(event)
        self.fitColumns()
        self.restoreHorizontalAnchor(anchor)

    def currentChanged(self, current, previous):
        """以前の列を保持できる時点で通知する。

        Args:
            current (QModelIndex): 新しい選択。
            previous (QModelIndex): 以前の選択。
        """
        self.aboutToNavigate.emit()
        self._pendingSelectionPath = True
        super().currentChanged(current, previous)

    def scrollTo(self, index, hint=QtWidgets.QAbstractItemView.EnsureVisible):
        """即時スクロール後にQtの子カラム・選択モデル更新も完了させる。

        Args:
            index (QModelIndex): 表示するフォルダー。
            hint (QAbstractItemView.ScrollHint): 表示位置の指定。
        """
        super().scrollTo(index, hint)
        self.fitColumns()
        # Qtはアニメーション完了時に子列の選択モデルを切り替える。
        # 即時移動では完了通知が無いため、移動後の可視範囲で再評価させる。
        super().scrollTo(index, hint)
        # リサイズ直後も「選択行」だけでなく、その子一覧まで可視範囲へ収める。
        for view in self.findChildren(QtWidgets.QListView):
            if view.isVisible() and view.rootIndex() == index:
                bounds = QtCore.QRect(view.mapTo(self.viewport(), QtCore.QPoint()), view.size())
                bar = self.horizontalScrollBar()
                if bounds.width() > self.viewport().width():
                    bar.setValue(bar.value() + bounds.left())
                elif bounds.right() >= self.viewport().width():
                    bar.setValue(bar.value() + bounds.right() - self.viewport().width() + 1)
                elif bounds.left() < 0:
                    bar.setValue(bar.value() + bounds.left())
                break
        self._hintTimer.start(30)


class Explorer(QtWidgets.QWidget):
    """上段のフォルダー階層と下段のファイル操作を同期する画面。"""
    actionRequested = QtCore.Signal(str)

    def __init__(self, parent=None, maya=False, dpi_scale=1.0):
        """部品を作り、専用設定を復元する。

        Args:
            parent (QWidget | None): Qt所有者。
            maya (bool): Maya用操作を有効にするか。
            dpi_scale (float): ホストが指定したDPI倍率。
        """
        super().__init__(parent)
        self.setObjectName('qpeExplorer')
        self.setWindowTitle('QuickPathExplorer')
        self.setWindowIcon(QtGui.QIcon(str(ICON)))
        self.resize(1240, 790)
        self._maya = maya
        self.currentDirectory = ''
        self.browseRoot = ''
        self._inlineRename = None
        self._actionPaths = None
        self._quickLook = None
        self._loadedFileFolders = set()
        self._columnStates = {}
        self._fromColumn = False
        self._navigationSerial = 0
        self._history = []
        self._historyIndex = -1
        self._syncing = False
        self._project = ''
        self._projectFolders = []
        self._previewSerial = 0
        self._previewPath = ''
        self._suspended = False
        self.traceSink = None
        self._previewJobs = {}
        self._image = QtGui.QImage()
        self._settingsKey = 'mayaLayout' if maya else 'standaloneLayout'
        self._buildUi()
        self._buildMenus()
        self._loadPlaces()
        self._restoreLayout()
        self.appearance = Appearance(self, dpi_scale)
        from qpeTabs import FolderTabs
        self.folderTabs = FolderTabs(self)
        self.interaction = Interaction(self)
        self.columns.interaction = self.interaction
        self.columns.refreshHints()
        self._connectDirectoryModels()

    def _connectDirectoryModels(self):
        """世代管理モデルの通知と表示位置保持を接続する。"""
        for model in (self.folderModel, self.fileModel):
            model.traceSink = lambda event: self.traceSink(event) if self.traceSink is not None else None
            model.directoryStateChanged.connect(self._updateFileSummary)
        self.folderModel.snapshotAboutToApply.connect(self._beforeDirectorySnapshot)
        self.folderModel.snapshotApplied.connect(self._afterDirectorySnapshot)

    def _beforeDirectorySnapshot(self):
        """非同期差分反映前の表示基準を保持する。"""
        self._snapshotAnchor = self.columns.horizontalAnchor()
        self._snapshotVertical = {self.folderModel.filePath(v.rootIndex()): v.verticalScrollBar().value()
                                  for v in self.columns.findChildren(QtWidgets.QListView)}

    def _afterDirectorySnapshot(self):
        """再描画だけでユーザーの表示位置を変えない。"""
        self.columns._hintTimer.start(30)
        self.columns.refreshHints()
        self.columns.restoreHorizontalAnchor(self._snapshotAnchor)
        for view in self.columns.findChildren(QtWidgets.QListView):
            path = self.folderModel.filePath(view.rootIndex())
            if path in self._snapshotVertical:
                view.verticalScrollBar().setValue(self._snapshotVertical[path])

    def _buildUi(self):
        """サイドバーとリサイズできる上下段を構築する。"""
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 8)
        bar = QtWidgets.QHBoxLayout()
        layout.addLayout(bar)
        self.sidebarButton = QtWidgets.QToolButton(self)
        self.sidebarButton.setObjectName('sidebarToggle')
        self.sidebarButton.setIcon(QtGui.QIcon(str(ICON.parent / 'sidebar.svg')))
        self.sidebarButton.setIconSize(QtCore.QSize(20, 20))
        self.sidebarButton.setToolTip('Show / hide sidebar')
        self.sidebarButton.setAccessibleName('Toggle sidebar')
        self.sidebarButton.setCheckable(True)
        bar.addWidget(self.sidebarButton)
        for name, callback in [('Back', self._back), ('Forward', self._forward)]:
            button = QtWidgets.QToolButton(self)
            button.setIcon(QtGui.QIcon(str(ICON.parent / (name.lower() + '.svg'))))
            button.setIconSize(QtCore.QSize(20, 20))
            button.setToolTip(name)
            button.setAccessibleName(name)
            button.clicked.connect(callback)
            button.setEnabled(False)
            setattr(self, name.lower() + 'Button', button)
            bar.addWidget(button)
        self.address = QtWidgets.QLineEdit(self)
        self.address.setObjectName('address')
        self.address.setPlaceholderText('Folder path')
        self.address.returnPressed.connect(lambda: self.navigate(self.address.text()))
        bar.addWidget(self.address, 1)
        self.locationsButton = QtWidgets.QToolButton(self)
        self.locationsButton.setText('★')
        self.locationsButton.setAccessibleName('Quick locations')
        self.locationsButton.setToolTip('Favorites / current project / current scene folder')
        self.locationsButton.clicked.connect(self._quickLocations)
        bar.addWidget(self.locationsButton)
        self.displayButton = QtWidgets.QToolButton(self)
        self.displayButton.setText('Aa')
        self.displayButton.setObjectName('displaySettings')
        self.displayButton.setToolTip('Display settings: font size / UI scale')
        self.displayButton.clicked.connect(lambda: self.appearance.show())
        bar.addWidget(self.displayButton)
        self.rootButton = QtWidgets.QToolButton(self)
        self.rootButton.setToolButtonStyle(QtCore.Qt.ToolButtonTextOnly)
        self.rootButton.clicked.connect(lambda: self.setBrowseRoot('' if self.browseRoot else self.currentDirectory))
        self.rootButton.setToolTip('Focus on this folder / show full drive hierarchy')
        self.rootButton.hide()
        bar.addWidget(self.rootButton)
        self.outer = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        self.outer.setObjectName('outerSplitter')
        self.outer.setChildrenCollapsible(False)
        layout.addWidget(self.outer, 1)
        self.places = QtWidgets.QTreeWidget(self.outer)
        self.places.setObjectName('places')
        self.places.setHeaderHidden(True)
        self.places.setMinimumWidth(180)
        self.places.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.places.itemClicked.connect(self._placeClicked)
        self.places.itemDoubleClicked.connect(self._placeActivated)
        self._placeIcons = FileIcons()
        self._placeFolderIcon = QtWidgets.QFileIconProvider().icon(QtWidgets.QFileIconProvider.Folder)
        self._placeRefreshTimer = QtCore.QTimer(self)
        self._placeRefreshTimer.setSingleShot(True)
        self._placeRefreshTimer.timeout.connect(self._loadPlaces)
        self.places.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.places.customContextMenuRequested.connect(self._placeMenu)
        self.vertical = QtWidgets.QSplitter(QtCore.Qt.Vertical, self.outer)
        self.vertical.setObjectName('verticalSplitter')
        self.vertical.setChildrenCollapsible(False)
        upper = QtWidgets.QWidget(self.vertical)
        upper_layout = QtWidgets.QHBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        self._sidebarWidth = 185
        self.sidebarButton.toggled.connect(self.setSidebarVisible)
        self.places.hide()
        self.folderModel = FolderModel(self)
        self.folderModel.setObjectName('folderModel')
        self.folderModel.setReadOnly(True)
        self.folderModel.setOption(QtWidgets.QFileSystemModel.DontUseCustomDirectoryIcons, True)
        self.folderModel.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.NoDotAndDotDot)
        self.columns = FolderColumns(upper)
        # Maya共有スタイルは所有せず、独立したQtスタイルをこのビューだけに適用する。
        self._columnStyle = ColumnStyle(QtWidgets.QStyleFactory.create('Fusion'))
        self._columnStyle.setParent(self.columns)
        self.columns.setStyle(self._columnStyle)
        self.columns.setResizeGripsVisible(False)
        self.columns.aboutToNavigate.connect(self._rememberColumns)
        self.columns.setObjectName('folderColumns')
        self.columns.setMinimumHeight(110)
        self.columns.setModel(self.folderModel)
        self.folderModel.directoryLoaded.connect(self.columns.folderLoaded)
        self.folderModel.rowsInserted.connect(self.columns.refreshHints)
        self.folderModel.rowsRemoved.connect(self.columns.refreshHints)
        self.columns.setColumnWidths([210] * 16)
        self.columns.selectionModel().currentChanged.connect(self._folderChanged)
        upper_layout.addWidget(self.columns)
        self.lower = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self.vertical)
        self.lower.setObjectName('lowerSplitter')
        self.lower.setChildrenCollapsible(False)
        file_panel = QtWidgets.QWidget(self.lower)
        file_panel.setMinimumWidth(230)
        file_panel.setMinimumHeight(210)
        file_layout = QtWidgets.QVBoxLayout(file_panel)
        file_layout.setContentsMargins(0, 0, 0, 0)
        self.folderLabel = QtWidgets.QLabel('FILES', file_panel)
        self.folderLabel.setTextFormat(QtCore.Qt.PlainText)
        file_layout.addWidget(self.folderLabel)
        filters = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit(file_panel)
        self.search.setObjectName('fileSearch')
        self.search.setPlaceholderText('Filter file names…')
        self.search.setClearButtonEnabled(True)
        self.fileFilter = QtWidgets.QComboBox(file_panel)
        self.fileFilter.setObjectName('fileFilter')
        for title, patterns in [('All files', []), ('Maya scenes', ['*.ma', '*.mb']),
                                ('Images', ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.tif', '*.tiff']),
                                ('FBX / OBJ', ['*.fbx', '*.obj']), ('Scripts', ['*.py', '*.mel'])]:
            self.fileFilter.addItem(title, patterns)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.fileFilter)
        file_layout.addLayout(filters)
        self.fileModel = DirectoryModel(self)
        self.fileModel.setObjectName('fileModel')
        self.fileModel.setReadOnly(True)
        self.fileModel.setFilter(QtCore.QDir.Files | QtCore.QDir.NoDotAndDotDot)
        self.fileModel.setNameFilterDisables(False)
        self.fileProxy = FileFilter(self)
        self.fileProxy.setSourceModel(self.fileModel)
        self.fileProxy.setFilterKeyColumn(0)
        self.fileProxy.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.files = QtWidgets.QTreeView(file_panel)
        self.files.setObjectName('fileList')
        self.files.setModel(self.fileProxy)
        self.files.setRootIsDecorated(False)
        self.files.setItemsExpandable(False)
        self.files.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.files.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.files.setAlternatingRowColors(True)
        self.files.setSortingEnabled(True)
        self.files.sortByColumn(0, QtCore.Qt.AscendingOrder)
        self.files.setColumnWidth(0, 235)
        self.files.setColumnWidth(1, 85)
        self.files.setColumnHidden(2, False)
        self.files.header().setStretchLastSection(False)
        self.files.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.files.header().setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        self.files.header().setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        self.files.header().setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.files.selectionModel().currentChanged.connect(self._fileChanged)
        self.files.selectionModel().selectionChanged.connect(self._selectionChanged)
        self.files.doubleClicked.connect(self.openFileIndex)
        self.files.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.files.customContextMenuRequested.connect(self._fileMenu)
        file_layout.addWidget(self.files, 1)
        self.emptyFiles = QtWidgets.QLabel('', self.files.viewport())
        self.emptyFiles.setAlignment(QtCore.Qt.AlignCenter)
        self.emptyFiles.setWordWrap(True)
        self.emptyFiles.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
        self.files.viewport().installEventFilter(self)
        self.fileModel.directoryLoaded.connect(self._filesLoaded)
        self.fileProxy.modelReset.connect(self._configureFileHeader)
        self.fileProxy.columnsInserted.connect(self._configureFileHeader)
        for signal in (self.fileProxy.rowsInserted, self.fileProxy.rowsRemoved, self.fileProxy.modelReset, self.fileProxy.layoutChanged):
            signal.connect(self._updateFileSummary)
        self.search.textChanged.connect(self.fileProxy.setFilterFixedString)
        self.fileFilter.currentIndexChanged.connect(self._filterChanged)
        self.actionsPanel = QtWidgets.QWidget(self.outer)
        self.actionsPanel.setObjectName('inspectorPanel')
        self.actionsPanel.setMinimumWidth(240)
        self.inspectorButton = QtWidgets.QToolButton(self)
        self.inspectorButton.setObjectName('inspectorToggle')
        self.inspectorButton.setIcon(QtGui.QIcon(str(ICON.parent / 'inspector.svg')))
        self.inspectorButton.setAccessibleName('Toggle details sidebar')
        self.inspectorButton.setToolTip('Show / hide file information and actions')
        self.inspectorButton.setCheckable(True)
        self.inspectorButton.toggled.connect(self.setInspectorVisible)
        bar.addWidget(self.inspectorButton)
        self._inspectorWidth = 340
        self.actionsPanel.hide()
        actions = QtWidgets.QVBoxLayout(self.actionsPanel)
        actions.setAlignment(QtCore.Qt.AlignTop)
        actions.setContentsMargins(6, 0, 6, 0)
        self.operationTabs = QtWidgets.QTabWidget(self.actionsPanel)
        self.operationTabs.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Maximum)
        actions.addWidget(self.operationTabs)
        self.readPanel = QtWidgets.QWidget(self.operationTabs)
        self.savePanel = QtWidgets.QWidget(self.operationTabs)
        self.operationTabs.addTab(self.readPanel, 'Selected file')
        if self._maya:
            self.operationTabs.addTab(self.savePanel, 'Save scene')
        else:
            self.savePanel.hide()
        self.readLayout = QtWidgets.QVBoxLayout(self.readPanel)
        self.saveLayoutUi = QtWidgets.QVBoxLayout(self.savePanel)
        self.readTarget = QtWidgets.QLabel('Select a file below', self.readPanel)
        self.readTarget.setTextFormat(QtCore.Qt.PlainText)
        self.readTarget.setWordWrap(True)
        self.readLayout.addWidget(self.readTarget)
        self.sceneTarget = QtWidgets.QLabel('Current scene: unsaved', self.savePanel)
        self.sceneTarget.setTextFormat(QtCore.Qt.PlainText)
        self.sceneTarget.setWordWrap(True)
        self.saveLayoutUi.addWidget(self.sceneTarget)
        read_buttons = QtWidgets.QHBoxLayout()
        save_buttons = QtWidgets.QVBoxLayout()
        self.readLayout.addLayout(read_buttons)
        self.saveLayoutUi.addLayout(save_buttons)
        self.actionButtons = {}
        for label, key in [('Open', 'open'), ('Import', 'import'), ('Reference', 'reference'),
                           ('Save current scene', 'save'), ('Save scene here…', 'saveAs'), ('Export selection here…', 'export')]:
            button = QtWidgets.QPushButton(label, self.actionsPanel)
            button.clicked.connect(lambda checked=False, action=key:
                                   self.requestFiles(action, self.selectedPaths()) if action in ('open', 'import', 'reference')
                                   else self.actionRequested.emit(action))
            (read_buttons if key in ('open', 'import', 'reference') else save_buttons).addWidget(button)
            button.setObjectName('action_' + key)
            self.actionButtons[key] = button
            if key != 'open' and not self._maya:
                button.setEnabled(False)
                button.setToolTip('Available when running inside Maya')
        self._button('Maya Options…', lambda: self.actionRequested.emit('options'), actions).setVisible(self._maya)
        if self._maya:
            from qpeReadOptions import ReadOptions
            self.readOptions = ReadOptions(self.readPanel)
            self.readLayout.addWidget(self.readOptions)
        self.details = QtWidgets.QWidget(self.actionsPanel)
        actions.addWidget(self.details, 1)
        self.details.setObjectName('detailsPanel')
        self.details.setMinimumWidth(180)
        detail_layout = QtWidgets.QVBoxLayout(self.details)
        detail_layout.setAlignment(QtCore.Qt.AlignTop)
        detail_layout.setContentsMargins(6, 0, 0, 0)

        self.preview = QtWidgets.QLabel('Select a file', self.details)
        self.preview.setObjectName('preview')
        self.preview.setAlignment(QtCore.Qt.AlignCenter)
        self.preview.setMinimumSize(160, 60)
        self.preview.setMaximumHeight(260)
        self.preview.setSizePolicy(QtWidgets.QSizePolicy.Ignored, QtWidgets.QSizePolicy.Expanding)
        self.preview.setFrameShape(QtWidgets.QFrame.StyledPanel)
        self.preview.setTextFormat(QtCore.Qt.PlainText)
        detail_layout.addWidget(self.preview, 1)
        self.previewText = QtWidgets.QPlainTextEdit(self.details)
        self.previewText.setObjectName('textPreview')
        self.previewText.setReadOnly(True)
        self.previewText.setToolTip('Text preview (first 16 KiB)')
        self.previewText.hide()
        detail_layout.addWidget(self.previewText, 1)
        self.metadata = QtWidgets.QLabel('Name / type / size / modified / path', self.details)
        self.metadata.setObjectName('metadata')
        self.metadata.setTextFormat(QtCore.Qt.RichText)
        self.metadata.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.metadata.setWordWrap(True)
        self.metadata.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        actions.removeWidget(self.operationTabs)
        actions.addWidget(self.operationTabs)
        self.detailsHeading = QtWidgets.QLabel('Details', self.details)
        actions.addWidget(self.detailsHeading)
        actions.addWidget(self.metadata)
        actions.addStretch(1)

        save_line = QtWidgets.QVBoxLayout()
        save_line.addWidget(QtWidgets.QLabel('File name', self))
        self.fileName = QtWidgets.QLineEdit(self)
        self.fileName.setObjectName('fileName')
        self.fileName.setPlaceholderText('Scene name for Save As / Export Selection')
        save_line.addWidget(self.fileName, 1)
        self.saveType = QtWidgets.QComboBox(self)
        self.saveType.setObjectName('saveType')
        self.saveType.addItem('Maya ASCII (.ma)', 'mayaAscii')
        self.saveType.addItem('Maya Binary (.mb)', 'mayaBinary')
        save_line.addWidget(self.saveType)
        for index in range(save_line.count()):
            save_line.itemAt(index).widget().setVisible(self._maya)
        self.saveLayoutUi.addLayout(save_line)
        self.saveDestination = QtWidgets.QLabel('', self.savePanel)
        self.saveDestination.setTextFormat(QtCore.Qt.PlainText)
        self.saveDestination.setWordWrap(True)
        self.saveLayoutUi.addWidget(self.saveDestination)
        save_buttons.removeWidget(self.actionButtons['save'])
        self.saveLayoutUi.insertWidget(1, self.actionButtons['save'])
        self.saveLayoutUi.removeItem(save_buttons)
        self.saveLayoutUi.addLayout(save_buttons)
        self.fileName.textChanged.connect(self._updateSaveTarget)
        self.saveType.currentIndexChanged.connect(self._updateSaveTarget)
        self.footer = QtWidgets.QLabel('0 items', self)
        self.footer.setObjectName('fileFooter')
        layout.addWidget(self.footer)
        self.status = QtWidgets.QLabel('', self)
        self.status.setObjectName('status')
        self.status.setTextFormat(QtCore.Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.hide()
        layout.addWidget(self.status)
        self.outer.setSizes([185, 1055, 0])
        self.vertical.setSizes([296, 444])
        self.lower.setSizes([1055])
        self.operationTabs.currentChanged.connect(self._operationTabChanged)
        self._operationTabChanged(0)
        self._updateActions()

    def _configureFileHeader(self, *unused):
        """非同期モデルの再構築後もファイル名へ余白を配分する。

        Args:
            unused (tuple): モデルの列追加通知。
        """
        header = self.files.header()
        if header.count() < 4:
            return
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.ResizeToContents)
        self.files.setColumnHidden(2, False)

    def setInspectorVisible(self, visible):
        """右側全高の情報・操作パネルを切り替え、一覧の幅を確保する。

        Args:
            visible (bool): 表示するか。
        """
        self._setSidePanelVisible(self.actionsPanel, visible)
        if visible:
            self._operationTabChanged(self.operationTabs.currentIndex())

    def setSidebarVisible(self, visible):
        """左サイドバーの開閉では右ペインの幅を維持する。"""
        self._setSidePanelVisible(self.places, visible)

    def _setSidePanelVisible(self, panel, visible):
        """左右の実幅を保持し、開閉で増減した幅は中央だけへ配分する。

        Args:
            panel (QWidget): 開閉するサイドバー。
            visible (bool): 表示するか。
        """
        if panel.isHidden() == (not visible):
            return
        sizes = self.outer.sizes()
        if not self.places.isHidden() and sizes[0] > 0:
            self._sidebarWidth = sizes[0]
        if not self.actionsPanel.isHidden() and sizes[2] > 0:
            self._inspectorWidth = sizes[2]
        if not hasattr(self, '_sideLayoutTimer'):
            self._sideLayoutTimer = QtCore.QTimer(self)
            self._sideLayoutTimer.setSingleShot(True)
            self._sideLayoutTimer.timeout.connect(self._finishSideLayout)
        if not self._sideLayoutTimer.isActive():
            self._sideUpdatesEnabled = self.outer.updatesEnabled()
        self._sideRevealChild = visible
        self.outer.setUpdatesEnabled(False)
        try:
            panel.setVisible(visible)
            left = 0 if self.places.isHidden() else self._sidebarWidth
            right = 0 if self.actionsPanel.isHidden() else self._inspectorWidth
            handles = int(not self.places.isHidden()) + int(not self.actionsPanel.isHidden())
            total = self.outer.contentsRect().width() - handles * self.outer.handleWidth()
            self.outer.setSizes([left, max(1, total - left - right), right])
            self.columns.parentWidget().layout().activate()
        finally:
            self._sideLayoutTimer.start(0)

    def _finishSideLayout(self):
        """Qtの配置確定後に横位置を決め、途中状態を描画せず一度に表示する。"""
        try:
            self.columns.fitColumns()
            if self._sideRevealChild:
                # 階層移動用scrollToは選択とアニメーションにも作用する。
                # 開閉では列を作り直さず、最後の可視列へ必要な距離だけ移動する。
                views = [view for view in self.columns.findChildren(QtWidgets.QListView)
                         if view.isVisible() and view.rootIndex().isValid()]
                if views:
                    view = max(views, key=lambda v: v.mapTo(self.columns.viewport(), QtCore.QPoint()).x())
                    x = view.mapTo(self.columns.viewport(), QtCore.QPoint()).x()
                    width = self.columns.viewport().width()
                    delta = x if view.width() > width or x < 0 else max(0, x + view.width() - width)
                    bar = self.columns.horizontalScrollBar()
                    bar.setValue(bar.value() + delta)
        finally:
            self.outer.setUpdatesEnabled(self._sideUpdatesEnabled)

    def openFileIndex(self, index):
        """ダブルクリックした行だけを開く。以前の選択集合には依存しない。

        Args:
            index (QModelIndex): クリックしたプロキシ項目。
        """
        if not index.isValid():
            return
        index = index.sibling(index.row(), 0)
        path = self.fileModel.filePath(self.fileProxy.mapToSource(index))
        if not os.path.isfile(path):
            return
        self.files.selectionModel().setCurrentIndex(index, QtCore.QItemSelectionModel.ClearAndSelect | QtCore.QItemSelectionModel.Rows)
        self.requestFiles('open', [path])

    def _operationTabChanged(self, index):
        """未表示の保存フォームがプレビューの高さを奪わないようにする。

        Args:
            index (int): 表示するタブ。
        """
        reading = self.operationTabs.currentWidget() is self.readPanel
        self.details.setVisible(reading)
        self.metadata.setVisible(reading)
        self.detailsHeading.setVisible(reading)
        for i in range(self.operationTabs.count()):
            panel = self.operationTabs.widget(i)
            panel.setSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                QtWidgets.QSizePolicy.Preferred if i == index else QtWidgets.QSizePolicy.Ignored)
            panel.updateGeometry()
        self.operationTabs.updateGeometry()
        panel = self.operationTabs.currentWidget()
        if panel is not None and panel.layout() is not None:
            layout = panel.layout()
            height = layout.heightForWidth(max(200, self.operationTabs.width() - 10)) if layout.hasHeightForWidth() else layout.sizeHint().height()
            self.operationTabs.setMaximumHeight(max(1, height) + self.operationTabs.tabBar().sizeHint().height() + 10)

    def _button(self, title, callback, layout):
        """ボタンを作る。

        Args:
            title (str): 表示名。
            callback (callable): クリック処理。
            layout (QLayout): 追加先。

        Returns:
            QPushButton: 作成したボタン。
        """
        button = QtWidgets.QPushButton(title, self)
        button.clicked.connect(callback)
        layout.addWidget(button)
        return button

    def _buildMenus(self):
        """カラムの右クリック操作と画面内ショートカットを作る。"""
        self.columns.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.columns.customContextMenuRequested.connect(self._folderMenu)
        for sequence, callback in [('Alt+Left', self._back), ('Alt+Right', self._forward),
                                   ('Alt+Up', self._up), ('Ctrl+L', self._focusAddress), ('Ctrl+D', self.addFavorite)]:
            action = QAction(self)
            action.setShortcut(QtGui.QKeySequence(sequence))
            action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(callback)
            self.addAction(action)
        for view in (self.files, self.columns):
            action = QAction(view)
            action.setShortcut(QtGui.QKeySequence('F2'))
            action.setShortcutContext(QtCore.Qt.WidgetWithChildrenShortcut)
            action.triggered.connect(lambda checked=False, v=view: self.renamePath(
                (self.selectedPath() if len(self.selectedPaths()) == 1 else '') if v is self.files else self.currentDirectory))
            view.addAction(action)

    def _focusAddress(self):
        """フォルダーパス入力欄を選択する。"""
        self.address.setFocus()
        self.address.selectAll()

    def _rememberColumns(self):
        """移動前の横位置・列幅・各階層の縦位置をフォルダー別に保持する。"""
        if self._syncing or not self.currentDirectory:
            return
        positions = {}
        for view in self.columns.findChildren(QtWidgets.QListView):
            if view.rootIndex().isValid():
                positions[self.folderModel.filePath(view.rootIndex())] = view.verticalScrollBar().value()
        self._columnStates[os.path.normcase(self.currentDirectory)] = {
            'root': self.browseRoot,
            'widths': self.columns.columnWidths(),
            'horizontal': self.columns.horizontalScrollBar().value(), 'vertical': positions}

    def _restoreColumns(self, state, serial):
        """Qtの列作成後に、今回の移動に対応する状態だけを復元する。

        Args:
            state (dict): 保存済み表示位置。
            serial (int): 移動番号。
        """
        if not shiboken.isValid(self) or self._suspended or serial != self._navigationSerial:
            return
        self.columns.fitColumns()
        self.columns.horizontalScrollBar().setValue(state['horizontal'])
        for view in self.columns.findChildren(QtWidgets.QListView):
            path = self.folderModel.filePath(view.rootIndex())
            if path in state['vertical']:
                view.verticalScrollBar().setValue(state['vertical'][path])

    def _folderMenu(self, position):
        """カラムの補助操作を表示する。

        Args:
            position (QPoint): 表示位置。
        """
        index = self.columns.indexAt(position)
        target = self.folderModel.filePath(index) if index.isValid() else self.currentDirectory
        # 空白部分では、そのカラムが表示しているフォルダーを作成先にする。
        if not index.isValid():
            for view in self.columns.findChildren(QtWidgets.QListView):
                point = view.viewport().mapFrom(self.columns.viewport(), position)
                if view.isVisible() and view.viewport().rect().contains(point):
                    target = self.folderModel.filePath(view.rootIndex())
                    break
        menu = self.createFolderMenu(target, background=not index.isValid())
        view = next((v for v in self.columns.findChildren(QtWidgets.QListView)
                     if v.isVisible() and v.rootIndex() == index.parent()), None) if index.isValid() else None
        self._execContext(menu, self.columns.viewport().mapToGlobal(position), view, index)

    def createFolderMenu(self, target, background=False):
        """右クリックしたフォルダーを対象にメニューを構築する。

        Args:
            target (str): 操作するフォルダー。
            background (bool): 項目ではなく列の空白か。

        Returns:
            QMenu: 実行前のメニュー。
        """
        menu = ContextMenu(self)
        menu.addAction('This Folder Information' if background else 'Information', lambda: self.showTargetInfo([target]))
        if not background:
            menu.addAction('Rename…', lambda: self.renamePath(target)).setEnabled(bool(target) and Path(target).parent != Path(target))
        menu.addAction('New Text File…', lambda: self.newEntry(target, folder=False))
        menu.addAction('New Folder…', lambda: self.newEntry(target, folder=True))
        menu.addAction('Explore from this folder', lambda: self.setBrowseRoot(target))
        if self._maya:
            menu.addAction('Save current scene here…', lambda: self.prepareSave(target))
        menu.addAction('Copy Path', lambda: QtWidgets.QApplication.clipboard().setText(target))
        menu.addAction('Show in Explorer', lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(target)))
        menu.addSeparator()
        for title, callback in [('Go to folder…', self._focusAddress), ('Back', self._back),
                                ('Forward', self._forward), ('Parent Folder', self._up),
                                ('Add Favorite', lambda: self.addFavoritePath(target))]:
            menu.addAction(title, callback)
        if self._maya:
            menu.addAction('Current Project', lambda: self.actionRequested.emit('project'))
            menu.addAction('Current Scene Folder', lambda: self.actionRequested.emit('sceneFolder'))
        menu.addSeparator()
        menu.addAction('Display Settings…', lambda: self.appearance.show())
        return menu

    def _execContext(self, menu, position, view=None, index=QtCore.QModelIndex()):
        """元の選択を変えずにメニュー対象を輪郭で示す。

        Args:
            menu (QMenu): 実行するメニュー。
            position (QPoint): 画面座標。
            view (QAbstractItemView | None): 対象一覧。
            index (QModelIndex): 右クリック項目。
        """
        outline = None
        if view is not None and index.isValid():
            outline = QtWidgets.QFrame(view.viewport())
            outline.setObjectName('contextTargetOutline')
            outline.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)
            outline.setStyleSheet('QFrame { border: 2px solid #69adc4; border-radius: 3px; background: transparent; }')
            rect = view.visualRect(index)
            rect.setLeft(0)
            rect.setRight(view.viewport().width() - 1)
            outline.setGeometry(rect)
            outline.show()
        menu.setFont(self.font())
        self.trace('menu-open')
        try:
            menu.exec_(position)
        finally:
            if outline is not None and shiboken.isValid(outline):
                outline.hide()
                outline.deleteLater()
            menu.deleteLater()
            self.trace('menu-close')

    def setBrowseRoot(self, path):
        """指定したフォルダー以下にカラムの表示を絞る。

        Args:
            path (str): 起点。空文字はドライブからの表示。
        """
        if path and not os.path.isdir(path):
            return
        self.browseRoot = os.path.abspath(path).replace('\\', '/') if path else ''
        self._columnStates.clear()
        self._syncing = True
        try:
            self.navigate(self.browseRoot or self.currentDirectory)
        finally:
            self._syncing = False

    def _quickLocations(self):
        """サイドバーを開かずによく使う場所へ移動する。"""
        menu = self.createLocationsMenu()
        menu.exec_(self.locationsButton.mapToGlobal(QtCore.QPoint(0, self.locationsButton.height())))
        menu.deleteLater()

    def createLocationsMenu(self):
        """お気に入り・Mayaの場所・探索起点をひとつのメニューにまとめる。

        Returns:
            QMenu: 移動メニュー。
        """
        menu = QtWidgets.QMenu(self)
        menu.setFont(self.font())
        if self._maya:
            menu.addAction('Current Project', lambda: self.actionRequested.emit('project'))
            menu.addAction('Current Scene Folder', lambda: self.actionRequested.emit('sceneFolder'))
            menu.addSeparator()
        paths = readSettings().get('favorites', [])
        if not paths:
            menu.addAction('No favorites yet').setEnabled(False)
        for path in paths:
            action = menu.addAction(Path(path).name or path,
                                    lambda checked=False, p=path: self._visitPlace(p))
            action.setToolTip(path)
        menu.addAction('Add current folder to favorites', self.addFavorite)
        menu.addSeparator()
        menu.addAction('Explore from current folder', lambda: self.setBrowseRoot(self.currentDirectory))
        menu.addAction('Show full drive hierarchy', lambda: self.setBrowseRoot(''))
        return menu

    def prepareSave(self, directory):
        """保存先を表示して入力に移る。まだシーンは保存しない。

        Args:
            directory (str): 保存したいフォルダー。
        """
        if self.navigate(directory):
            self.inspectorButton.setChecked(True)
            self.operationTabs.setCurrentWidget(self.savePanel)
            self.fileName.setFocus()
            self.fileName.selectAll()

    def navigate(self, path, record=True):
        """上下段をフォルダーへ同期する。

        Args:
            path (str): 移動先。
            record (bool): 履歴を追加するか。

        Returns:
            bool: 移動できたか。
        """
        path = QtCore.QDir.fromNativeSeparators(os.path.abspath(os.path.expanduser(path)))
        if not os.path.isdir(path):
            self.status.setText('Folder not found or unavailable: ' + path)
            self.status.show()
            return False
        editor = self._inlineRename
        if editor is not None and shiboken.isValid(editor):
            editor.finish(False)
        if self.browseRoot:
            normalized = os.path.normcase(path).replace('\\', '/').rstrip('/')
            root_path = os.path.normcase(self.browseRoot).replace('\\', '/').rstrip('/')
            if normalized != root_path and not normalized.startswith(root_path + '/'):
                self.browseRoot = ''
        changed = path != self.currentDirectory
        if not self._fromColumn:
            self._rememberColumns()
        state = self._columnStates.get(os.path.normcase(path))
        if state and state.get('root', '') != self.browseRoot:
            state = None
        self._navigationSerial += 1
        serial = self._navigationSerial
        self._syncing = True
        try:
            self.currentDirectory = path
            anchor = self.browseRoot or Path(path).anchor.replace('\\', '/')
            chain = [path]
            while chain[-1] != anchor:
                parent = str(Path(chain[-1]).parent).replace('\\', '/')
                if parent == chain[-1]:
                    break
                chain.append(parent)
            self.folderModel.activate(chain)
            self.fileModel.activate([path])
            self.columns.setToolTip(path)
            self.address.setText(path)
            root = self.folderModel.setRootPath(anchor)
            if self.folderModel.index(path) == root and self.columns.currentIndex() != root:
                # 起点自身は表示行に存在せず、Qtの選択変更だけでは古い子列が残る。
                # 列の起点をいったん外し、起点の一覧だけを再構築する。
                self.columns.setRootIndex(QtCore.QModelIndex())
            if self.columns.rootIndex() != root:
                self.columns.setRootIndex(root)
            self.columns.setCurrentIndex(self.folderModel.index(path))
            self.columns.scrollTo(self.folderModel.index(path))
            self.fileProxy.directoryRoot = os.path.normcase(path).replace('\\', '/').rstrip('/')
            self.fileProxy.invalidateFilter()
            file_root = self.fileModel.setRootPath(path)
            self.files.setRootIndex(self.fileProxy.mapFromSource(file_root))
            self.files.clearSelection()
            self.files.setCurrentIndex(QtCore.QModelIndex())
            self._clearDetails()
            self.folderLabel.setText('FILES  ·  ' + (Path(path).name or path))
            if changed and record:
                self._history = self._history[:self._historyIndex + 1] + [path]
                self._historyIndex = len(self._history) - 1
            self.backButton.setEnabled(self._historyIndex > 0)
            self.forwardButton.setEnabled(self._historyIndex < len(self._history) - 1)
            self._updateSaveTarget()
            self._updateActions()
            self.status.clear()
            self.status.hide()
            recents = [path] + [p for p in readSettings().get('recents', []) if p != path]
            if not writeSettings({'recents': recents[:10], 'lastPath': path}):
                self.status.setText('Settings could not be saved. ' + path)
                self.status.show()
            self._loadPlaces()
            self.rootButton.setText(('Root: ' + self.fontMetrics().elidedText(Path(self.browseRoot).name, QtCore.Qt.ElideMiddle, 130) + ' ×')
                                    if self.browseRoot else 'Focus folder')
            self.rootButton.show()
            self._updateFileSummary()
        finally:
            self._syncing = False
        if state and not self._fromColumn:
            self._restoreColumns(state, serial)
            QtCore.QTimer.singleShot(0, lambda: self._restoreColumns(state, serial))
        if hasattr(self, 'folderTabs'):
            self.folderTabs.updateTitle()
        self.trace('navigate', serial=serial)
        return True

    def _filesLoaded(self, path):
        """非同期の読込完了を記録して件数を更新する。

        Args:
            path (str): 読込が終わったフォルダー。
        """
        self._loadedFileFolders.add(os.path.normcase(path))
        if not self._suspended and os.path.normcase(path) == os.path.normcase(self.currentDirectory):
            self._updateFileSummary()

    def _updateFileSummary(self, *unused):
        """上下段を同じフォルダー名で結び、件数と空状態を表示する。

        Args:
            unused (tuple): モデルの更新通知。
        """
        if not hasattr(self, 'emptyFiles') or not self.currentDirectory:
            return
        count = self.fileProxy.rowCount(self.files.rootIndex())
        loaded = os.path.normcase(self.currentDirectory) in self._loadedFileFolders
        filtered = bool(self.search.text() or self.fileFilter.currentIndex())
        suffix = '{} files{}'.format(count, ' · filtered' if filtered else '') if loaded or count else 'Loading…'
        self.folderLabel.setText('{}  ·  {}'.format(Path(self.currentDirectory).name or self.currentDirectory, suffix))
        self.folderLabel.setToolTip(self.currentDirectory)
        self.emptyFiles.setText('No matching files — clear the filters above.' if filtered else
                                ('No files in this folder. Subfolders are shown above.' if loaded else 'Loading files…'))
        state, error = self.fileModel.states.get(self.currentDirectory, ('loading', ''))
        if state == 'error':
            self.emptyFiles.setText(error)
        self.emptyFiles.setVisible(count == 0)
        self.emptyFiles.setGeometry(self.files.viewport().rect().adjusted(16, 8, -16, -8))
        self._updateFooter()
        self.columns.refreshHints()

    def _updateFooter(self):
        """一覧件数・選択件数・選択サイズをフッターへ表示する。"""
        if not hasattr(self, 'footer'):
            return
        count = self.fileProxy.rowCount(self.files.rootIndex())
        paths = self.selectedPaths()
        text = '{} items'.format(count)
        if paths:
            size = sum(QtCore.QFileInfo(path).size() for path in paths)
            text += '  |  {} selected  ·  {}'.format(len(paths), QtCore.QLocale.system().formattedDataSize(size))
        self.footer.setText(text)

    def eventFilter(self, watched, event):
        """空状態の説明を一覧の中央に追従させる。

        Args:
            watched (QObject): 監視対象。
            event (QEvent): Qtイベント。

        Returns:
            bool: 標準イベント処理を妨げない。
        """
        if hasattr(self, 'emptyFiles') and watched is self.files.viewport() and event.type() == QtCore.QEvent.Resize:
            self.emptyFiles.setGeometry(watched.rect().adjusted(16, 8, -16, -8))
        return super().eventFilter(watched, event)

    def _folderChanged(self, index, previous):
        """フォルダー選択を下段へ反映する。

        Args:
            index (QModelIndex): 新しい選択。
            previous (QModelIndex): 前の選択。
        """
        if not self._syncing and index.isValid():
            self._fromColumn = True
            try:
                self.navigate(self.folderModel.filePath(index))
            finally:
                self._fromColumn = False

    def _back(self):
        """履歴の一つ前へ移動する。"""
        if self._historyIndex > 0 and os.path.isdir(self._history[self._historyIndex - 1]):
            self._historyIndex -= 1
            self.navigate(self._history[self._historyIndex], record=False)

    def _forward(self):
        """履歴の次へ移動する。"""
        if self._historyIndex + 1 < len(self._history) and os.path.isdir(self._history[self._historyIndex + 1]):
            self._historyIndex += 1
            self.navigate(self._history[self._historyIndex], record=False)

    def _up(self):
        """現在フォルダーの親へ移動する。"""
        if self.currentDirectory:
            self.navigate(str(Path(self.currentDirectory).parent))

    def _loadPlaces(self):
        """ファイルとフォルダーのお気に入り・最近の場所を更新する。"""
        # 単クリックで移動しても、二回目のクリックまで対象行を動かさない。
        if self._placeRefreshTimer.isActive():
            return
        expanded = {self.places.topLevelItem(i).text(0): self.places.topLevelItem(i).isExpanded()
                    for i in range(self.places.topLevelItemCount())}
        scroll = self.places.verticalScrollBar().value()
        self.places.clear()
        settings = readSettings()
        groups = [('Favorites', settings.get('favorites', [])),
                  ('Recent', settings.get('recents', []))]
        for title, paths in groups:
            group = QtWidgets.QTreeWidgetItem(self.places, [title])
            group.setFlags(group.flags() & ~QtCore.Qt.ItemIsSelectable)
            for path in dict.fromkeys(paths):
                item = QtWidgets.QTreeWidgetItem(group, [Path(path).name or path])
                item.setData(0, QtCore.Qt.UserRole, path)
                item.setToolTip(0, path)
                item.setIcon(0, self._placeFolderIcon if os.path.isdir(path)
                             else self._placeIcons.icon(path))
            group.setExpanded(expanded.get(title, True))
        self.places.verticalScrollBar().setValue(scroll)

    def _placeClicked(self, item, column):
        """左ペインの場所へ移動する。

        Args:
            item (QTreeWidgetItem): 対象。
            column (int): 列番号。
        """
        path = item.data(0, QtCore.Qt.UserRole)
        self._placeRefreshTimer.start(QtWidgets.QApplication.doubleClickInterval() + 50)
        self._visitPlace(path)

    def _visitPlace(self, path):
        """共通の場所リンクでフォルダー移動またはファイル選択を行う。

        Args:
            path (str | None): 対象パス。
        """
        if path and os.path.isfile(path):
            if os.path.normcase(str(Path(path).parent)) != os.path.normcase(self.currentDirectory):
                self.navigate(str(Path(path).parent))
            self._selectWhenReady(path)
        elif path:
            self.navigate(path)

    def _placeActivated(self, item, column):
        """左一覧のファイルはダブルクリックで固定対象を開く。

        Args:
            item (QTreeWidgetItem): 対象項目。
            column (int): 列番号。
        """
        path = item.data(0, QtCore.Qt.UserRole)
        if path and os.path.isfile(path):
            self.requestFiles('open', [path])

    def _placeMenu(self, position):
        """お気に入り削除のメニューを表示する。

        Args:
            position (QPoint): 表示位置。
        """
        item = self.places.itemAt(position)
        if item and item.parent() and item.parent().text(0) == 'Favorites':
            path = item.data(0, QtCore.Qt.UserRole)
            menu = QtWidgets.QMenu(self)
            menu.addAction('Remove Favorite', lambda: self.removeFavorite(path))
            menu.exec_(self.places.viewport().mapToGlobal(position))

    def addFavorite(self):
        """現在フォルダーを重複なしでお気に入りへ追加する。"""
        self.addFavoritePath(self.currentDirectory)

    def addFavoritePath(self, path):
        """指定フォルダーをお気に入りへ追加する。

        Args:
            path (str): 追加先。
        """
        if path:
            paths = readSettings().get('favorites', [])
            if path not in paths:
                paths.append(path)
            writeSettings({'favorites': paths})
            self._loadPlaces()

    def removeFavorite(self, path):
        """お気に入りを削除する。

        Args:
            path (str): 対象フォルダー。
        """
        writeSettings({'favorites': [p for p in readSettings().get('favorites', []) if p != path]})
        self._loadPlaces()

    def setProject(self, path, folders):
        """プロジェクトの場所を受け取る。

        Args:
            path (str): ルート。
            folders (list[str]): プロジェクト内フォルダー。
        """
        self._project = path
        self._projectFolders = folders
        self._loadPlaces()

    def selectedPath(self):
        """選択ファイルを返す。

        Returns:
            str: 未選択なら空文字。
        """
        current = self.files.currentIndex()
        if not self.files.selectionModel().isSelected(current):
            selected = self.files.selectionModel().selectedRows(0)
            current = selected[0] if selected else QtCore.QModelIndex()
        index = self.fileProxy.mapToSource(current)
        return self.fileModel.filePath(index) if index.isValid() else ''

    def selectedPaths(self):
        """実際に選択されているファイルを表示順で返す。

        Returns:
            list[str]: 選択パス。
        """
        indexes = sorted(self.files.selectionModel().selectedRows(0), key=lambda index: index.row())
        return [self.fileModel.filePath(self.fileProxy.mapToSource(index)) for index in indexes]

    def operationPaths(self):
        """メニュー操作中だけ明示対象を使い、通常は選択集合を返す。

        Returns:
            list[str]: 今回の処理対象。
        """
        return list(self._actionPaths) if self._actionPaths is not None else self.selectedPaths()

    def requestFiles(self, action, paths):
        """選択を変えずに対象をホストへ渡す。

        Args:
            action (str): open/import/reference。
            paths (list[str]): メニュー作成時に確定した対象。
        """
        if not paths or (action == 'open' and len(paths) != 1):
            return
        if not self.validateTargets(paths):
            return
        previous = self._actionPaths
        self._actionPaths = tuple(paths)
        try:
            self.actionRequested.emit(action)
        finally:
            self._actionPaths = previous
        recents = list(dict.fromkeys(list(paths) + readSettings().get('recents', [])))[:10]
        writeSettings({'recents': recents})
        QtCore.QTimer.singleShot(0, self._loadPlaces)

    def toggleQuickLook(self):
        """Spaceで選択ファイルのプレビューを拡大表示する。"""
        if self._quickLook is not None and self._quickLook.isVisible():
            self._quickLook.close()
            return
        if not self.selectedPath():
            return
        dialog = QtWidgets.QDialog(self)
        dialog.setWindowTitle(Path(self.selectedPath()).name)
        dialog.setFont(self.font())
        dialog.resize(720, 520)
        layout = QtWidgets.QVBoxLayout(dialog)
        label = QtWidgets.QLabel(dialog)
        label.setObjectName('quickLookImage')
        label.setAlignment(QtCore.Qt.AlignCenter)
        layout.addWidget(label)
        text = QtWidgets.QPlainTextEdit(dialog)
        text.setObjectName('quickLookText')
        text.setReadOnly(True)
        layout.addWidget(text)
        action = QAction(dialog)
        action.setShortcut(QtGui.QKeySequence('Space'))
        action.triggered.connect(dialog.close)
        dialog.addAction(action)
        if self._quickLook is not None:
            self._quickLook.deleteLater()
        self._quickLook = dialog
        self._refreshQuickLook()
        dialog.show()

    def _refreshQuickLook(self):
        """非同期プレビューの完了を拡大画面にも反映する。"""
        dialog = self._quickLook
        if dialog is None:
            return
        dialog.setWindowTitle(Path(self.selectedPath()).name or 'Quick Look')
        label = dialog.findChild(QtWidgets.QLabel, 'quickLookImage')
        text = dialog.findChild(QtWidgets.QPlainTextEdit, 'quickLookText')
        has_image = not self._image.isNull()
        label.setVisible(has_image)
        text.setVisible(not has_image)
        if has_image:
            label.setPixmap(QtGui.QPixmap.fromImage(self._image).scaled(680, 450, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))
        else:
            text.setPlainText(self.previewText.toPlainText() or self.preview.text())

    def _filterChanged(self, index):
        """形式フィルターを適用する。

        Args:
            index (int): 選択項目。
        """
        self.fileModel.setNameFilters(self.fileFilter.itemData(index) or [])

    def _fileChanged(self, index, previous):
        """詳細を更新し、プレビューは別スレッドへ渡す。

        Args:
            index (QModelIndex): 新しい選択。
            previous (QModelIndex): 以前の選択。
        """
        path = self.selectedPath()
        if path and path == self._previewPath:
            self._updateActions()
            return
        self._clearDetails()
        if not path or not os.path.isfile(path):
            self._updateActions()
            return
        info = QtCore.QFileInfo(path)
        import html
        rows = [('Type', fileType(path)),
                ('Size', QtCore.QLocale.system().formattedDataSize(info.size())),
                ('Location', self.fontMetrics().elidedText(info.absolutePath(), QtCore.Qt.ElideMiddle, 180)),
                ('Modified', info.lastModified().toString('yyyy-MM-dd HH:mm'))]
        self.metadata.setText('<table cellspacing="0" cellpadding="6">' + ''.join(
            '<tr><td valign="top">{}</td><td>{}</td></tr>'.format(html.escape(label), html.escape(value))
            for label, value in rows) + '</table>')
        self.metadata.setToolTip(path)
        self.preview.setText('Loading preview…')
        serial = self._previewSerial
        self._previewPath = path
        self.trace('preview-start', serial=serial, path=path)
        job = PreviewJob(serial, path)
        job.signals.ready.connect(self._previewReady)
        self._previewJobs[serial] = job
        QtCore.QThreadPool.globalInstance().start(job)
        self._updateActions()

    def _selectionChanged(self, *unused):
        """現在項目を動かさない選択解除でもプレビュー対象を同期する。

        Args:
            unused (tuple): 選択モデルの変更情報。
        """
        if self.selectedPath() != self._previewPath:
            self._fileChanged(self.files.currentIndex(), QtCore.QModelIndex())
        self._updateActions()

    def _clearDetails(self):
        """古い非同期プレビューを無効化する。"""
        self._previewSerial += 1
        self._previewPath = ''
        self._image = QtGui.QImage()
        self.preview.clear()
        self.preview.setText('Select a file')
        self.preview.show()
        self.previewText.hide()
        self.previewText.clear()
        self.metadata.clear()
        self._refreshQuickLook()

    def _previewReady(self, serial, image, text):
        """最新の要求だけを表示する。

        Args:
            serial (int): 要求番号。
            image (QImage): 結果画像。
            text (str): 文字プレビューまたは説明。
        """
        job = self._previewJobs.pop(serial, None)
        accepted = (not self._suspended and serial == self._previewSerial
                    and job is not None and job.path == self._previewPath
                    and job.path == self.selectedPath())
        self.trace('preview-result', serial=serial, accepted=accepted)
        if not accepted:
            return
        self._image = image
        if not image.isNull():
            self._resizePreview()
        elif text.startswith('TEXT\n'):
            self.preview.setText('Text preview (first 16 KiB)')
            self.preview.hide()
            self.previewText.setPlainText(text[5:])
            self.previewText.show()
            if Path(self._previewPath).suffix.lower() in ('.ma', '.mb', '.fbx'):
                self.previewText.hide()
                self.preview.setPixmap(self._placeIcons.icon(self._previewPath).pixmap(96, 96))
                self.preview.show()
        else:
            self.preview.setText(text)
        self._refreshQuickLook()

    def _resizePreview(self):
        """読込済み画像を詳細欄のサイズに合わせる。"""
        if not self._image.isNull():
            self.preview.setPixmap(QtGui.QPixmap.fromImage(self._image).scaled(
                self.preview.size(), QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation))

    def resizeEvent(self, event):
        """プレビューを整える。

        Args:
            event (QResizeEvent): Qtイベント。
        """
        super().resizeEvent(event)
        self._resizePreview()
        if hasattr(self, 'saveDestination'):
            self._operationTabChanged(self.operationTabs.currentIndex())

    def _updateActions(self):
        """選択に応じて読込系ボタンを有効化する。"""
        self._updateFooter()
        paths = self.selectedPaths()
        selected = bool(paths)
        if hasattr(self, 'readTarget'):
            self.readTarget.setText(Path(self.selectedPath()).name if selected else 'Select a file in the list')
            if len(paths) > 1:
                self.readTarget.setText('{} files selected'.format(len(paths)))
            self.readTarget.setToolTip(self.selectedPath())
            if hasattr(self, 'saveDestination'):
                self._operationTabChanged(self.operationTabs.currentIndex())
        for key in ('open', 'import', 'reference'):
            self.actionButtons[key].setEnabled(selected and (len(paths) == 1 if key == 'open' else self._maya))

    def targetPath(self):
        """Save As/Exportの保存先を返す。

        Returns:
            str: 不正または未入力なら空文字。
        """
        name = self.fileName.text().strip()
        if not name or name in ('.', '..') or any(c in name for c in '/\\:'):
            return ''
        extension = '.ma' if self.saveType.currentData() == 'mayaAscii' else '.mb'
        name = os.path.splitext(name)[0] + extension
        return os.path.join(self.currentDirectory, name).replace('\\', '/') if self.currentDirectory else ''

    def _updateSaveTarget(self, *unused):
        """保存先を表示する。

        Args:
            unused (tuple): Qtシグナルの未使用値。
        """
        target = self.targetPath() or '(enter a file name)'
        for key in ('saveAs', 'export'):
            self.actionButtons[key].setToolTip(target)
        self.fileName.setToolTip(target)
        if hasattr(self, 'saveDestination'):
            self.saveDestination.setText('Destination: ' + target)

    def copyPath(self):
        """ファイルまたは現在フォルダーのパスをコピーする。"""
        QtWidgets.QApplication.clipboard().setText(self.selectedPath() or self.currentDirectory)

    def revealFolder(self):
        """OSで現在フォルダーを開く。"""
        if self.currentDirectory:
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.currentDirectory))

    def newFolder(self):
        """入力した単一の名前で新規フォルダーを作る。"""
        self.newEntry(self.currentDirectory, folder=True)

    def newEntry(self, directory, folder=False):
        """入力を受けて、指定場所へ空ファイルまたはフォルダーを作る。

        Args:
            directory (str): 作成先。
            folder (bool): フォルダーを作るか。
        """
        if not directory:
            return
        name, ok = QtWidgets.QInputDialog.getText(self, 'New Folder' if folder else 'New Text File',
            'Folder name' if folder else 'Text file name (.txt)',
            QtWidgets.QLineEdit.Normal, 'New Folder' if folder else 'New File.txt')
        if not ok:
            return
        try:
            if not folder:
                if not name.strip():
                    raise ValueError('Enter a text file name.')
                if not Path(name).suffix:
                    name += '.txt'
                elif Path(name).suffix.lower() != '.txt':
                    raise ValueError('Use .txt for a text file. Use Save scene here to create a Maya scene.')
            path = createEntry(directory, name, folder)
            self.navigate(directory)
            if not folder:
                self._selectWhenReady(path)
            self.status.setText('Created: ' + path)
            self.status.show()
        except (OSError, ValueError) as error:
            self.status.setText(str(error))
            self.status.show()

    def renamePath(self, path, name=None):
        """リネーム後に履歴とお気に入りの子孫パスも移す。

        Args:
            path (str): 対象ファイルまたはフォルダー。
            name (str | None): 確定済みの名前。未指定なら一覧内で編集。
        """
        if not path or Path(path).parent == Path(path):
            return
        if not self.validateTargets([path]):
            return
        if name is None:
            self.startInlineRename(path)
            return
        was_folder = os.path.isdir(path)
        try:
            if was_folder:
                # Windowsでは表示中の子フォルダーの監視ハンドルが改名を妨げる。
                # 一時解除後はモデルごと作り直して監視とキャッシュを確実に再開する。
                self.folderModel.setOption(QtWidgets.QFileSystemModel.DontWatchForChanges, True)
                self.fileModel.setOption(QtWidgets.QFileSystemModel.DontWatchForChanges, True)
            try:
                target = renameEntry(path, name)
            finally:
                if was_folder:
                    self._resetFileModels()
        except (OSError, ValueError) as error:
            if was_folder:
                self.navigate(self.currentDirectory, record=False)
            self.status.setText(str(error))
            self.status.show()
            return
        old = os.path.normcase(path).replace('\\', '/').rstrip('/')

        def remap(value):
            """変更したフォルダーとその子孫だけを新しいパスへ移す。

            Args:
                value (str): 以前のパス。

            Returns:
                str: 更新したパス。
            """
            normalized = os.path.normcase(value).replace('\\', '/')
            if normalized == old or (was_folder and normalized.startswith(old + '/')):
                return target + value.replace('\\', '/')[len(old):]
            return value

        self._history = [remap(value) for value in self._history]
        if self.browseRoot:
            self.browseRoot = remap(self.browseRoot)
        settings = readSettings()
        writeSettings({key: [remap(value) for value in settings.get(key, [])] for key in ('favorites', 'recents')})
        self._columnStates.clear()
        self.navigate(remap(self.currentDirectory), record=False)
        if not was_folder:
            self._selectWhenReady(target)
        self.status.setText('Renamed: ' + target)
        self.status.show()

    def startInlineRename(self, path):
        """対象行の上で編集し、ファイルの拡張子を選択から外す。

        Args:
            path (str): 編集対象。
        """
        if os.path.isdir(path):
            index = self.folderModel.index(path)
            views = [v for v in self.columns.findChildren(QtWidgets.QListView)
                     if v.isVisible() and v.rootIndex() == index.parent()]
            if not views:
                self.browseRoot = ''
                self.navigate(str(Path(path).parent))
                index = self.folderModel.index(path)
                views = [v for v in self.columns.findChildren(QtWidgets.QListView)
                         if v.isVisible() and v.rootIndex() == index.parent()]
            if not views:
                return
            view = views[-1]
        else:
            view = self.files
            index = self.fileProxy.mapFromSource(self.fileModel.index(path))
        if not index.isValid():
            return
        view.scrollTo(index)
        editor = InlineRename(view.viewport(), Path(path).name,
                              len(Path(path).name if os.path.isdir(path) else Path(path).stem))
        editor.setFont(self.font())
        rect = view.visualRect(index)
        editor.setGeometry(rect.adjusted(0, 0, 0, max(0, editor.sizeHint().height() - rect.height())))
        editor.committed.connect(lambda value: self.renamePath(path, value))
        self._inlineRename = editor
        editor.show()
        editor.setFocus()

    def _resetFileModels(self):
        """改名で監視を解除したモデルを、同じフィルター設定で再作成する。"""
        self._syncing = True
        try:
            old_folder, old_file = self.folderModel, self.fileModel
            self.folderModel = FolderModel(self)
            self.folderModel.setObjectName('folderModel')
            self.folderModel.setReadOnly(True)
            self.folderModel.setOption(QtWidgets.QFileSystemModel.DontUseCustomDirectoryIcons, True)
            self.folderModel.setFilter(old_folder.filter())
            self.columns.setModel(self.folderModel)
            self.columns.selectionModel().currentChanged.connect(self._folderChanged)
            self.columns._loadedFolders = set()
            self.folderModel.directoryLoaded.connect(self.columns.folderLoaded)
            self.folderModel.rowsInserted.connect(self.columns.refreshHints)
            self.folderModel.rowsRemoved.connect(self.columns.refreshHints)
            self.fileModel = DirectoryModel(self)
            self.fileModel.setObjectName('fileModel')
            self.fileModel.setReadOnly(True)
            self.fileModel.setFilter(old_file.filter())
            self.fileModel.setNameFilters(old_file.nameFilters())
            self.fileModel.setNameFilterDisables(False)
            self._loadedFileFolders.clear()
            self.fileModel.directoryLoaded.connect(self._filesLoaded)
            self.fileProxy.setSourceModel(self.fileModel)
            self._connectDirectoryModels()
            old_folder.suspend()
            old_file.suspend()
            old_folder.deleteLater()
            old_file.deleteLater()
        finally:
            self._syncing = False

    def _selectWhenReady(self, path):
        """非同期一覧の更新を待って作成・改名したファイルを選択する。

        Args:
            path (str): 選択先。
        """
        serial = self._navigationSerial
        timer = QtCore.QTimer(self)
        attempts = [0]

        def select():
            """現在フォルダーに残っている間だけ有限回試行する。"""
            attempts[0] += 1
            index = self.fileProxy.mapFromSource(self.fileModel.index(path))
            if serial != self._navigationSerial or attempts[0] >= 40 or index.isValid():
                timer.stop()
                timer.deleteLater()
                if serial == self._navigationSerial and index.isValid():
                    self.files.setCurrentIndex(index)
                    self.files.scrollTo(index)
        timer.timeout.connect(select)
        timer.start(50)

    def _fileMenu(self, position):
        """一覧の補助メニューを表示する。

        Args:
            position (QPoint): 表示位置。
        """
        index = self.files.indexAt(position)
        paths = []
        if index.isValid():
            index = index.sibling(index.row(), 0)
            path = self.fileModel.filePath(self.fileProxy.mapToSource(index))
            paths = self.selectedPaths() if path in self.selectedPaths() else [path]
        menu = self.createFileMenu(paths)
        self._execContext(menu, self.files.viewport().mapToGlobal(position), self.files, index)

    def createFileMenu(self, paths=None):
        """選択ファイルに対する操作メニューを構築する。

        Args:
            paths (list[str] | None): 明示対象。空リストなら空白用。

        Returns:
            QMenu: 実行前のメニュー。
        """
        menu = ContextMenu(self)
        paths = self.selectedPaths() if paths is None else list(paths)
        directory = self.currentDirectory
        menu.addAction('Information' if paths else 'This Folder Information',
                       lambda: self.showTargetInfo(paths or [directory]))
        if paths:
            menu.addAction('Add to Favorites', lambda: [self.addFavoritePath(path) for path in paths])
            for title, key in [('Open', 'open'), ('Import', 'import'), ('Reference', 'reference')]:
                if key == 'open' or self._maya:
                    menu.addAction(title, lambda checked=False, action=key: self.requestFiles(action, paths)).setEnabled(key != 'open' or len(paths) == 1)
            menu.addSeparator()
            menu.addAction('Rename…', lambda: self.renamePath(paths[0])).setEnabled(len(paths) == 1)
        menu.addAction('New Text File…', lambda: self.newEntry(directory, folder=False))
        menu.addAction('New Folder…', lambda: self.newEntry(directory, folder=True))
        if self._maya:
            menu.addAction('Save current scene here…', lambda: self.prepareSave(directory))
        menu.addAction('Copy Path', lambda: QtWidgets.QApplication.clipboard().setText('\n'.join(paths) if paths else directory))
        menu.addAction('Show Folder in Explorer', lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(directory)))
        menu.addSeparator()
        menu.addAction('Display Settings…', lambda: self.appearance.show())
        return menu

    def saveLayout(self):
        """分割幅をホスト別に保存する。"""
        writeSettings({self._settingsKey: {'outer': self.outer.sizes(), 'vertical': self.vertical.sizes(),
            'lower': self.lower.sizes(), 'version': 4, 'size': [self.width(), self.height()]}})

    def _restoreLayout(self):
        """保存した分割幅を復元する。"""
        value = readSettings().get(self._settingsKey, {})
        if value.get('version') not in (2, 3, 4):
            return
        for key, splitter in [('outer', self.outer), ('vertical', self.vertical), ('lower', self.lower)]:
            sizes = value.get(key)
            if key == 'vertical' and value.get('version') != 4:
                continue
            if key == 'outer' and value.get('version') == 2:
                continue
            if isinstance(sizes, list) and len(sizes) == splitter.count() and all(isinstance(v, int) and v >= 0 for v in sizes):
                splitter.setSizes(sizes)
        size = value.get('size')
        if isinstance(size, list) and len(size) == 2 and all(isinstance(v, int) for v in size):
            self.resize(max(800, min(size[0], 2400)), max(500, min(size[1], 1600)))

    def hideEvent(self, event):
        """非表示時にレイアウトを保存する。

        Args:
            event (QHideEvent): Qtイベント。
        """
        self.saveLayout()
        self._suspended = True
        self.folderModel.suspend()
        self.fileModel.suspend()
        self._previewSerial += 1
        self._previewPath = ''
        self._navigationSerial += 1
        super().hideEvent(event)

    def showEvent(self, event):
        """再表示時は古い要求を再利用せず選択から読み直す。

        Args:
            event (QShowEvent): 表示通知。
        """
        super().showEvent(event)
        self._suspended = False
        if hasattr(self, 'folderModel') and self.currentDirectory:
            self.folderModel.activate(list(self.folderModel._active))
            self.fileModel.activate([self.currentDirectory])
        if hasattr(self, 'files') and self.selectedPath():
            self._fileChanged(self.files.currentIndex(), QtCore.QModelIndex())

    def trace(self, operation, **values):
        """明示的に接続した検証先だけへ状態を通知する。

        Args:
            operation (str): 操作の種類。
            **values: 要求番号や採否。
        """
        if self.traceSink is not None:
            focus = QtWidgets.QApplication.focusWidget()
            self.traceSink(dict(operation=operation, directory=self.currentDirectory,
                                navigation=self._navigationSerial,
                                selected=self.selectedPaths(), previewPath=self._previewPath,
                                horizontal=self.columns.horizontalScrollBar().value(),
                                focus=focus.objectName() if focus is not None else None, **values))

    def validateTargets(self, paths):
        """対象消失や読取権限不足を表示し、別項目への代替を防ぐ。

        Args:
            paths (list[str]): 固定済み対象。

        Returns:
            bool: 全対象が存在し読み取れるか。
        """
        for path in paths:
            if not os.path.exists(path) or not os.access(path, os.R_OK):
                self.status.setText('Target is missing or inaccessible: ' + path)
                self.status.show()
                return False
        return True

    def showTargetInfo(self, paths):
        """選択を変更せず固定した対象の情報を表示する。

        Args:
            paths (list[str]): メニュー開始時の対象。
        """
        if self.validateTargets(paths):
            QtWidgets.QMessageBox.information(self, 'Information', '\n'.join(paths))


def main():
    """Windows単体ブラウザーを起動する。"""
    if hasattr(QtCore.Qt, 'AA_EnableHighDpiScaling'):
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_EnableHighDpiScaling)
        QtWidgets.QApplication.setAttribute(QtCore.Qt.AA_UseHighDpiPixmaps)
    app = QtWidgets.QApplication(sys.argv)
    window = Explorer()
    window.actionRequested.connect(lambda action: QtGui.QDesktopServices.openUrl(
        QtCore.QUrl.fromLocalFile(window.operationPaths()[0])) if action == 'open' and len(window.operationPaths()) == 1 else None)
    window.show()
    path = sys.argv[1] if len(sys.argv) > 1 else readSettings().get('lastPath', str(Path.home()))
    window.navigate(path if os.path.isdir(path) else str(Path.home()))
    return app.exec_()


if __name__ == '__main__':
    sys.exit(main())

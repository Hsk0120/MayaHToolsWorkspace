"""下段の表示切替、コマンド検索、操作履歴と設定をまとめる。"""
import datetime
import json
import os
import time
from collections import OrderedDict
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets, shiboken
from qpeSettings import readSettings, writeSettings
from qpeAdvancedIO import searchAdvanced, summarize
from qpePreview import PreviewJob


class WorkspaceFeatures(QtCore.QObject):
    """既存のナビゲーションを保ち、任意の下段表示を所有する。"""

    def __init__(self, tools):
        """QtウィジェットはGUIスレッドだけで生成する。"""
        super().__init__(tools.explorer)
        self.tools, self.e = tools, tools.explorer
        self.serial, self.path = 0, ''
        self.task = None
        self.cache = OrderedDict()
        self.previewJobs = {}
        self.pendingImages = []
        self.thumbnailSerial = 0
        self.restoring = False
        self.items = {}
        self.allPaths = []
        self.selectedBefore = []
        layout = self.e.files.parentWidget().layout()
        self.bar = QtWidgets.QWidget()
        row = QtWidgets.QHBoxLayout(self.bar)
        row.setContentsMargins(0, 0, 0, 0)
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(['Details', 'Thumbnails', 'Extended details'])
        self.flat = QtWidgets.QCheckBox('Include subfolders')
        self.group = QtWidgets.QComboBox()
        self.group.addItems(['No groups', 'Extension', 'Date modified (by day)', 'Location', 'Tag'])
        self.labelFilter = QtWidgets.QComboBox()
        self.labelFilter.setMinimumContentsLength(8)
        self.labelFilter.setSizeAdjustPolicy(QtWidgets.QComboBox.AdjustToMinimumContentsLengthWithIcon)
        self.labelFilter.addItem('All tags', '')
        settings = QtWidgets.QToolButton()
        settings.setText('File list columns…')
        settings.clicked.connect(self.columns)
        for widget in (self.mode, self.flat, self.group, self.labelFilter, settings):
            row.addWidget(widget)
        row.addStretch()
        layout.insertWidget(layout.indexOf(self.e.files), self.bar)
        index = layout.indexOf(self.e.files)
        layout.removeWidget(self.e.files)
        self.stack = QtWidgets.QStackedWidget()
        self.stack.addWidget(self.e.files)
        self.grid = FileGrid()
        self.grid.setViewMode(QtWidgets.QListView.IconMode)
        self.grid.setResizeMode(QtWidgets.QListView.Adjust)
        self.grid.setMovement(QtWidgets.QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setIconSize(QtCore.QSize(128, 88))
        self.grid.setGridSize(QtCore.QSize(165, 130))
        self.tree = FileTree()
        self.tree.setHeaderLabels(['Name', 'Size', 'Extension', 'Date modified', 'Tags', 'Rating', 'Location', 'Dimensions', 'Availability'])
        self.tree.setAlternatingRowColors(True)
        self.tree.setSortingEnabled(True)
        self.tree.setColumnWidth(0, 260)
        self.tree.setColumnWidth(1, 90)
        self.tree.setColumnWidth(4, 110)
        self.stack.addWidget(self.grid)
        self.stack.addWidget(self.tree)
        layout.insertWidget(index, self.stack, 1)
        for view in (self.tree, self.grid):
            view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
            view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            view.customContextMenuRequested.connect(lambda point, v=view: self.context(v, point))
            view.itemSelectionChanged.connect(self.selectionChanged)
            view.itemDoubleClicked.connect(self.openItem)
            view.installEventFilter(self)
            view.viewport().installEventFilter(self)
            view.viewport().setAcceptDrops(True)
            view.setDragEnabled(True)
            view.setDefaultDropAction(QtCore.Qt.CopyAction)
        self.grid.verticalScrollBar().valueChanged.connect(self.scheduleImages)
        self.mode.currentIndexChanged.connect(self.viewChanged)
        self.flat.toggled.connect(self.viewChanged)
        self.group.currentIndexChanged.connect(self.viewChanged)
        self.labelFilter.currentIndexChanged.connect(self.viewChanged)
        self.tree.header().sortIndicatorChanged.connect(self.saveView)
        self.tree.header().sectionResized.connect(self.saveView)
        self.e.fileModel.directoryLoaded.connect(self.loaded)
        self.e.search.textChanged.connect(self.refresh)
        self.e.fileFilter.currentIndexChanged.connect(self.refresh)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.populate)
        self.shortcuts = []
        from qpeProductivity import Productivity
        self.productivity = Productivity(self)
        self.installShortcuts()

    def active(self):
        """下段が拡張表示かを返す。"""
        return self.stack.currentWidget() is not self.e.files

    def selected(self):
        """グループ見出しを除外した選択パスを返す。"""
        view = self.stack.currentWidget()
        if view is self.e.files:
            return []
        return [str(i.data(QtCore.Qt.UserRole) if view is self.grid else i.data(0, QtCore.Qt.UserRole))
                for i in view.selectedItems() if (i.data(QtCore.Qt.UserRole) if view is self.grid else i.data(0, QtCore.Qt.UserRole))]

    def selectionChanged(self):
        """プレビューと操作対象を同じ選択へ揃える。"""
        self.e._selectionChanged()
        self.e._updateFooter()

    def current(self):
        """現在項目が選択内なら優先し、選択外なら選択集合へ戻る。"""
        view = self.stack.currentWidget()
        item = view.currentItem() if view is not self.e.files else None
        if item and item.isSelected():
            return item.data(QtCore.Qt.UserRole) if view is self.grid else item.data(0, QtCore.Qt.UserRole)
        paths = self.selected()
        return paths[0] if paths else ''

    def openItem(self, item, column=0):
        """フォルダーは移動、ファイルはホストへ渡す。"""
        path = item.data(QtCore.Qt.UserRole) if isinstance(item, QtWidgets.QListWidgetItem) else item.data(0, QtCore.Qt.UserRole)
        if path:
            self.e.navigate(path) if os.path.isdir(path) else self.e.requestFiles('open', [path])

    def context(self, view, point):
        """選択外の対象もメニュー開始時点で固定する。"""
        item = view.itemAt(point)
        path = (item.data(QtCore.Qt.UserRole) if view is self.grid else item.data(0, QtCore.Qt.UserRole)) if item else None
        paths = self.selected()
        if path and path not in paths:
            paths = [path]
        menu = self.e.createFileMenu(paths) if paths else QtWidgets.QMenu(self.e)
        if not paths:
            self.tools.addMenu(menu, [], self.e.currentDirectory)
        menu.exec_(view.viewport().mapToGlobal(point))

    def eventFilter(self, watched, event):
        """拡張一覧内のキーだけを処理し、編集欄やIMEへ干渉しない。"""
        kind = event.type()
        if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.RightButton:
            return True
        if kind in (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove, QtCore.QEvent.Drop) and event.mimeData().hasUrls():
            if kind == QtCore.QEvent.Drop:
                paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
                self.tools.transfer('move' if event.keyboardModifiers() & QtCore.Qt.ShiftModifier else 'copy', paths)
            event.acceptProposedAction()
            return True
        if kind == QtCore.QEvent.Resize and watched is self.grid.viewport():
            QtCore.QTimer.singleShot(0, self.scheduleImages)
        if kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride) and QtWidgets.QApplication.focusWidget() in (self.grid, self.tree):
            key, mods = event.key(), event.modifiers()
            if mods == QtCore.Qt.ControlModifier:
                actions = {QtCore.Qt.Key_C: lambda: self.tools.clipboard(self.selected()),
                           QtCore.Qt.Key_X: lambda: self.tools.clipboard(self.selected(), True),
                           QtCore.Qt.Key_V: lambda: self.tools.paste(self.e.currentDirectory),
                           QtCore.Qt.Key_Z: self.tools.undo, QtCore.Qt.Key_Y: self.redo}
                if key in actions:
                    if kind == QtCore.QEvent.ShortcutOverride:
                        event.accept()
                    else:
                        actions[key]()
                    return True
            if mods == QtCore.Qt.NoModifier and key in (QtCore.Qt.Key_Delete, QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_F2, QtCore.Qt.Key_Space):
                if kind == QtCore.QEvent.ShortcutOverride:
                    event.accept()
                    return True
                paths = self.selected()
                if key == QtCore.Qt.Key_Delete:
                    self.tools.transfer('trash', paths)
                elif paths and key in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_F2):
                    if len(paths) == 1:
                        self.e.renamePath(paths[0])
                elif paths:
                    self.e.openSelectedFile()
                return True
        return False

    def loaded(self, path):
        """現在の場所の更新だけを表示へ反映する。"""
        if os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(self.e.currentDirectory)):
            self.refresh()

    def navigate(self):
        """場所ごとの表示設定を復元する。"""
        self.saveView()
        self.serial += 1
        if self.task:
            self.task.cancel.set()
        self.tree.clear()
        self.grid.clear()
        self.items = {}
        self.tree.blockSignals(False)
        self.grid.blockSignals(False)
        self.path = self.e.currentDirectory
        self.productivity.navigated()
        values = readSettings().get('folderViews', {}).get(os.path.normcase(self.path), {})
        self.restoring = True
        self.mode.setCurrentIndex(int(values.get('mode', 0)))
        self.flat.setChecked(bool(values.get('flat', False)))
        self.group.setCurrentIndex(int(values.get('group', 0)))
        for column in range(1, 9):
            self.tree.setColumnHidden(column, column in values.get('hidden', []))
        for column, width in enumerate(values.get('widths', [])):
            self.tree.setColumnWidth(column, max(40, min(1000, int(width))))
        self.tree.sortItems(int(values.get('sort', 0)), QtCore.Qt.DescendingOrder if values.get('descending') else QtCore.Qt.AscendingOrder)
        self.restoring = False
        self.viewChanged()

    def saveView(self, *unused):
        """設定変更時だけ現在の場所へ記録する。"""
        if self.restoring or not self.path:
            return
        values = readSettings().get('folderViews', {})
        values[os.path.normcase(self.path)] = dict(mode=self.mode.currentIndex(), flat=self.flat.isChecked(),
            group=self.group.currentIndex(), hidden=[c for c in range(1, 9) if self.tree.isColumnHidden(c)],
            widths=[self.tree.columnWidth(c) for c in range(8)], sort=self.tree.sortColumn(),
            descending=self.tree.header().sortIndicatorOrder() == QtCore.Qt.DescendingOrder)
        writeSettings({'folderViews': values})

    def viewChanged(self, *unused):
        """表示を切り替えても選択パスを引き継ぐ。"""
        if self.restoring:
            return
        self.selectedBefore = self.e.selectedPaths()
        mode = self.mode.currentIndex()
        self.stack.setCurrentIndex(2 if (self.flat.isChecked() or self.group.currentIndex() or self.labelFilter.currentData()) and mode == 0 else mode)
        if not self.active() and self.selectedBefore:
            selection = self.e.files.selectionModel()
            selection.clearSelection()
            for path in self.selectedBefore:
                index = self.e.fileProxy.mapFromSource(self.e.fileModel.index(path))
                if index.isValid():
                    selection.select(index, QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Rows)
        self.saveView()
        self.refresh()

    def refresh(self, *unused):
        """連続したモデル通知をまとめ、再描画でカラム位置を動かさない。"""
        if hasattr(self, 'timer'):
            self.timer.start(100)

    def populate(self):
        """通常は採用済みモデルを再利用し、再帰だけワーカーへ送る。"""
        if self.labelFilter.currentData() and not self.active():
            self.stack.setCurrentIndex(2)
        if not self.active():
            return
        self.serial += 1
        serial = self.serial
        if self.task:
            self.task.cancel.set()
        if self.flat.isChecked():
            from qpeTools import launchTask
            root = self.e.currentDirectory
            def done(result, error):
                """ナビゲーション後の古い一覧を捨てる。"""
                if not shiboken.isValid(self.e) or self.serial != serial:
                    return
                self.task = None
                if error:
                    self.tools.report(error)
                else:
                    self.render(result['paths'])
                    if result['errors']:
                        self.tools.report('{} read errors'.format(len(result['errors'])))
            self.task = launchTask(lambda c, p: searchAdvanced([root], hidden=self.tools.hidden, cancel=c), done)
        else:
            root = self.e.files.rootIndex()
            paths = [self.e.fileModel.filePath(self.e.fileProxy.mapToSource(self.e.fileProxy.index(row, 0, root)))
                     for row in range(self.e.fileProxy.rowCount(root))]
            self.render(paths)

    def render(self, paths):
        """追加情報とラベルを可視化し、選択・スクロールを復元する。"""
        import fnmatch
        selected = set(self.selected() or self.selectedBefore)
        self.selectedBefore = []
        scroll = self.stack.currentWidget().verticalScrollBar().value()
        self.allPaths = list(paths)
        self.restoring = True
        labels = readSettings().get('fileLabels', {})
        tag = self.labelFilter.currentData()
        all_tags = sorted({t for v in labels.values() for t in v.get('tags', [])})
        self.labelFilter.blockSignals(True)
        self.labelFilter.clear()
        self.labelFilter.addItem('All tags', '')
        for value in all_tags:
            self.labelFilter.addItem(value, value)
        self.labelFilter.setCurrentIndex(max(0, self.labelFilter.findData(tag)))
        self.labelFilter.blockSignals(False)
        self.tree.setSortingEnabled(False)
        self.tree.blockSignals(True)
        self.grid.blockSignals(True)
        self.tree.clear()
        self.grid.clear()
        self.items = {}
        groups = {}
        patterns = self.e.fileFilter.currentData() or []
        query = self.e.search.text().lower()
        def add(path):
            """一行分のデータだけを生成する。"""
            name = Path(path).name
            metadata = labels.get(os.path.normcase(os.path.abspath(path)), {})
            if query not in name.lower() or (tag and tag not in metadata.get('tags', [])):
                return
            if patterns and not any(fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns):
                return
            try:
                info = os.stat(path)
            except OSError:
                return
            modified = datetime.datetime.fromtimestamp(info.st_mtime).strftime('%Y-%m-%d %H:%M')
            values = [name, QtCore.QLocale.system().formattedDataSize(info.st_size), Path(path).suffix,
                      modified, ', '.join(metadata.get('tags', [])), '★' * metadata.get('rating', 0), str(Path(path).parent)]
            from qpeProductivityIO import availability
            state, blocked = availability(attributes=getattr(info, 'st_file_attributes', 0), reparse_tag=getattr(info, 'st_reparse_tag', 0))
            item = FileRow(values + ['', state])
            item.setData(0, QtCore.Qt.UserRole, path)
            item.setData(1, QtCore.Qt.UserRole, info.st_size)
            item.setToolTip(0, path)
            icon = self.e._placeIcons.icon(path)
            item.setIcon(0, icon)
            if metadata.get('tags'):
                item.setForeground(4, QtGui.QBrush(QtGui.QColor('#669ecc')))
            group = self.group.currentText()
            key = {'Extension': values[2] or 'No extension', 'Date modified (by day)': modified[:10], 'Location': values[6],
                   'Tag': values[4] or 'No tags'}.get(group, '')
            if key:
                if key not in groups:
                    groups[key] = QtWidgets.QTreeWidgetItem([key])
                    groups[key].setFlags(QtCore.Qt.ItemIsEnabled)
                    self.tree.addTopLevelItem(groups[key])
                    groups[key].setExpanded(True)
                groups[key].addChild(item)
            else:
                self.tree.addTopLevelItem(item)
            grid_item = QtWidgets.QListWidgetItem(icon, name)
            grid_item.setSizeHint(self.grid.gridSize())
            grid_item.setData(QtCore.Qt.UserRole, path)
            grid_item.setToolTip(path + '\n' + state + '\n' + values[4] + ' ' + values[5])
            self.grid.addItem(grid_item)
            item.setSelected(path in selected)
            grid_item.setSelected(path in selected)
            self.items[path] = (grid_item, info.st_mtime_ns, info.st_size)
        iterator, serial = iter(paths), self.serial
        def appendChunk():
            """大量の項目でもQtイベントを処理する時間を挟む。"""
            if serial != self.serial or not shiboken.isValid(self.e):
                return
            for unused in range(40):
                try:
                    add(next(iterator))
                except StopIteration:
                    self.tree.setSortingEnabled(True)
                    self.tree.blockSignals(False)
                    self.grid.blockSignals(False)
                    self.restoring = False
                    self.stack.currentWidget().verticalScrollBar().setValue(scroll)
                    self.selectionChanged()
                    self.scheduleImages()
                    self.loadDimensions(serial)
                    return
            QtCore.QTimer.singleShot(0, appendChunk)
        appendChunk()

    def loadDimensions(self, serial):
        """画像ヘッダーの読取りもワーカーへ分離する。"""
        if self.stack.currentWidget() is not self.tree or self.tree.isColumnHidden(7):
            return
        from qpeTools import launchTask
        paths = list(self.items)
        def read(cancel, progress):
            """画像形式の寸法だけを読み、本体を展開しない。"""
            sizes = {}
            for path in paths:
                if cancel.is_set():
                    break
                from qpeProductivityIO import availability
                if availability(path)[1]:
                    continue
                if Path(path).suffix.lower() in ('.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp', '.webp'):
                    size = QtGui.QImageReader(path).size()
                    if size.isValid():
                        sizes[path] = '{} × {}'.format(size.width(), size.height())
            return sizes
        def done(result, error):
            """現在の一覧だけへ寸法を反映する。"""
            if not shiboken.isValid(self.e) or self.serial != serial or error:
                return
            iterator = QtWidgets.QTreeWidgetItemIterator(self.tree)
            while iterator.value():
                item = iterator.value()
                item.setText(7, result.get(item.data(0, QtCore.Qt.UserRole), ''))
                iterator += 1
        launchTask(read, done)

    def scheduleImages(self, *unused):
        """可視サムネイルだけを最大2件ずつ読込み、256件を上限に保持する。"""
        if self.e._suspended or self.stack.currentWidget() is not self.grid:
            return
        for path, (item, modified, size) in self.items.items():
            if not self.grid.visualItemRect(item).intersects(self.grid.viewport().rect()):
                continue
            sidecar = Path(path + '.qpe.png')
            try:
                sidecar_time = sidecar.stat().st_mtime_ns if sidecar.exists() else 0
            except OSError:
                sidecar_time = 0
            key = (path, modified, size, sidecar_time)
            if key in self.cache:
                image = self.cache[key]
                if not image.isNull():
                    item.setIcon(QtGui.QIcon(QtGui.QPixmap.fromImage(image)))
                self.cache.move_to_end(key)
                continue
            if any(job.path == path for job in self.previewJobs.values()):
                continue
            if len(self.previewJobs) >= 2:
                return
            self.thumbnailSerial += 1
            job = PreviewJob(self.thumbnailSerial, path)
            job.cacheKey = key
            job.signals.ready.connect(self.imageReady)
            self.previewJobs[job.serial] = job
            QtCore.QThreadPool.globalInstance().start(job)

    def imageReady(self, serial, image, text):
        """GUIスレッドでだけPixmapへ変換し、古いパスへ反映しない。"""
        job = self.previewJobs.pop(serial, None)
        if not job or self.e._suspended:
            return
        self.cache[job.cacheKey] = image.scaled(160, 110, QtCore.Qt.KeepAspectRatio, QtCore.Qt.SmoothTransformation)
        while len(self.cache) > 256:
            self.cache.popitem(last=False)
        self.scheduleImages()

    def columns(self):
        """Metadataの表示列を選択する。名前列は常に残す。"""
        menu = QtWidgets.QMenu(self.e)
        for column in range(1, 9):
            action = menu.addAction(self.tree.headerItem().text(column))
            action.setCheckable(True)
            action.setChecked(not self.tree.isColumnHidden(column))
            action.toggled.connect(lambda checked, c=column: self.setColumn(c, checked))
        menu.exec_(QtGui.QCursor.pos())

    def setColumn(self, column, visible):
        """列選択を現在の場所に保存する。"""
        self.tree.setColumnHidden(column, not visible)
        self.mode.setCurrentIndex(2)
        self.saveView()

    def addTools(self, menu):
        """追加機能は既存Tools内へまとめる。"""
        menu.addSeparator()
        for title, callback in self.commands().values():
            menu.addAction(title, callback)

    def commands(self):
        """安定したIDをショートカット保存にも使う。"""
        return {
            'palette': ('Find command…', self.palette),
            'saveWorkspace': ('Save tab set…', self.productivity.saveSet),
            'loadWorkspace': ('Open tab set…', self.productivity.loadSet),
            'deleteWorkspace': ('Delete tab set…', self.productivity.deleteSet),
            'previousWorkspace': ('Restore previous tab set', lambda: self.e.folderTabs.restoreSession(readSettings().get('previousWorkspace', {}))),
            'archive': ('Browse ZIP…', self.productivity.archive),
            'diagnose': ('Diagnose file usage / availability…', self.productivity.diagnose),
            'locksmith': ('Configure File Locksmith CLI…', self.productivity.configureDiagnosis),
            'jobs': ('File jobs / retry…', self.jobs),
            'recoverTransfers': ('Resume unfinished transfers…', self.recoverTransfers),
            'history': ('File operation history…', self.history),
            'redo': ('Redo file operation', self.redo),
            'summary': ('Calculate selected / folder size…', self.summary),
            'openFile': ('Open selected file', self.e.openSelectedFile),
            'settings': ('QPE settings / export…', self.settings),
            'labels': ('Manage label names…', self.manageLabels),
            'thumbnails': ('View: thumbnails', lambda: self.mode.setCurrentIndex(1)),
            'metadata': ('View: extended details / tags', lambda: self.mode.setCurrentIndex(2)),
            'flat': ('View: toggle subfolders', lambda: self.flat.setChecked(not self.flat.isChecked()))}

    def palette(self):
        """メニュー全体を検索し、元のアクションをそのまま実行する。"""
        self.tools.populateTools()
        dialog = QtWidgets.QDialog(self.e)
        dialog.setWindowTitle('Find command')
        dialog.resize(540, 480)
        layout = QtWidgets.QVBoxLayout(dialog)
        query, listing = QtWidgets.QLineEdit(), QtWidgets.QListWidget()
        layout.addWidget(query)
        layout.addWidget(listing)
        actions = []
        def collect(menu, prefix=''):
            """サブメニューも検索対象にする。"""
            for action in menu.actions():
                if action.menu():
                    collect(action.menu(), prefix + action.text() + ' / ')
                elif not action.isSeparator() and action.text() != 'Find command…':
                    actions.append((prefix + action.text(), action))
        collect(self.tools.toolsMenu)
        def fill():
            """文字列を含むコマンドを表示する。"""
            listing.clear()
            for title, action in actions:
                if query.text().casefold() in title.casefold():
                    item = QtWidgets.QListWidgetItem(title)
                    item.setData(QtCore.Qt.UserRole, action)
                    if not action.isEnabled():
                        item.setFlags(item.flags() & ~QtCore.Qt.ItemIsEnabled & ~QtCore.Qt.ItemIsSelectable)
                    listing.addItem(item)
            for index in range(listing.count()):
                if listing.item(index).flags() & QtCore.Qt.ItemIsEnabled:
                    listing.setCurrentRow(index)
                    break
        def execute(item=None):
            """ダイアログを閉じてからコマンドを呼ぶ。"""
            item = item or listing.currentItem()
            if item:
                action = item.data(QtCore.Qt.UserRole)
                if not action.isEnabled():
                    return
                dialog.accept()
                action.trigger()
        query.textChanged.connect(fill)
        query.returnPressed.connect(execute)
        listing.itemActivated.connect(execute)
        fill()
        query.setFocus()
        dialog.exec_()

    def installShortcuts(self):
        """入力欄からの発火を避け、QPEの子ウィジェットだけに限定する。"""
        for shortcut in self.shortcuts:
            shortcut.setEnabled(False)
            shortcut.deleteLater()
        self.shortcuts = []
        shortcut_class = getattr(QtGui, 'QShortcut', None) or QtWidgets.QShortcut
        keys = {'palette': 'Ctrl+Shift+P', 'jobs': 'Ctrl+Shift+J', 'history': 'Ctrl+Shift+H'}
        keys.update(readSettings().get('commandKeys', {}))
        for name, sequence in keys.items():
            if name not in self.commands() or not sequence:
                continue
            shortcut = shortcut_class(QtGui.QKeySequence(sequence), self.e)
            shortcut.setContext(QtCore.Qt.WidgetWithChildrenShortcut)
            shortcut.activated.connect(lambda n=name: self.shortcut(n))
            self.shortcuts.append(shortcut)

    def shortcut(self, name):
        """編集コントロールがフォーカスを持つ間は起動しない。"""
        focus = QtWidgets.QApplication.focusWidget()
        if focus is None or not (focus is self.e or self.e.isAncestorOf(focus)):
            return
        if isinstance(focus, (QtWidgets.QLineEdit, QtWidgets.QTextEdit, QtWidgets.QPlainTextEdit, QtWidgets.QAbstractSpinBox, QtWidgets.QComboBox)):
            return
        self.commands()[name][1]()

    def addFileActions(self, menu, paths):
        """固定対象に対応した追加コマンドを付ける。"""
        if paths:
            menu.addAction('Diagnose usage / availability…', lambda: self.productivity.diagnose(paths))
        if len(paths) == 1 and Path(paths[0]).suffix.lower() == '.zip':
            menu.addAction('Browse ZIP…', lambda: self.productivity.archive(paths[0]))
        if paths:
            menu.addAction('Calculate size / count…', lambda: self.summary(paths))

    def summary(self, paths=None):
        """重い容量計算は明示操作でバックグラウンド実行する。"""
        paths = paths if isinstance(paths, list) else self.e.selectedPaths() or [self.e.currentDirectory]
        def done(result):
            """読み取れなかった項目も集計と分けて示す。"""
            size = QtCore.QLocale.system().formattedDataSize
            self.tools.showText('Files: {files}\nFolders: {folders}\nSize: {size}\nDrive free: {free}\nErrors:\n{errors}'.format(
                files=result['files'], folders=result['folders'], size=size(result['bytes']), free=size(result['free']), errors='\n'.join(result['errors'])))
        self.tools.run('Calculate size', lambda c, p: summarize(paths, c), done)



    def mergeChoices(self, paths, destination):
        """結合する同名ファイルの日時・サイズを比較し個別選択する。"""
        dialog = QtWidgets.QDialog(self.e)
        dialog.setWindowTitle('Merge folders — destination-only files are kept')
        dialog.resize(900, 500)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel('Copy only. Each merged folder has a whole-folder Undo backup.'))
        table = QtWidgets.QTreeWidget()
        table.setHeaderLabels(['Relative path', 'Source size / modified', 'Destination size / modified', 'Action'])
        table.header().setStretchLastSection(False)
        table.header().setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        for column in (1, 2, 3):
            table.header().setSectionResizeMode(column, QtWidgets.QHeaderView.ResizeToContents)
        layout.addWidget(table)
        rows = []
        def addConflict(src, dst, relative):
            """異なるルートに同名の相対パスがあっても別々に選択する。"""
            def info(p):
                """判断に必要な種類・サイズ・日時を表示する。"""
                value = p.stat()
                size = '—' if p.is_dir() else QtCore.QLocale.system().formattedDataSize(value.st_size)
                return '{} / {} / {}'.format('Folder' if p.is_dir() else 'File', size,
                    datetime.datetime.fromtimestamp(value.st_mtime).isoformat(' ', 'seconds'))
            item = QtWidgets.QTreeWidgetItem([relative, info(src), info(dst)])
            item.setToolTip(0, str(src) + '\n' + str(dst))
            for column in (1, 2):
                item.setToolTip(column, item.text(column))
            table.addTopLevelItem(item)
            combo = QtWidgets.QComboBox()
            for label, action in [('Replace', 'replace'), ('Skip', 'skip'), ('Keep both (new name)', 'rename')]:
                combo.addItem(label, action)
            table.setItemWidget(item, 3, combo)
            rows.append((str(src), combo))
        for path in paths:
            source = Path(path)
            target = Path(destination) / source.name
            if not source.is_dir() or not target.is_dir():
                if target.exists():
                    addConflict(source, target, source.name)
                continue
            for root, dirs, files in os.walk(str(source), followlinks=False):
                from qpeTransactions import isLink
                dirs[:] = [name for name in dirs if not isLink(Path(root) / name)]
                for name in files + dirs:
                    src = Path(root) / name
                    relative = src.relative_to(source).as_posix()
                    dst = target / relative
                    if not dst.exists() or (src.is_dir() and dst.is_dir()):
                        continue
                    addConflict(src, dst, source.name + '/' + relative)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec_() != QtWidgets.QDialog.Accepted:
            return None
        return {name: combo.currentData() for name, combo in rows}

    def redo(self):
        """ファイル用RedoをMayaのUndoとは分離する。"""
        try:
            record = json.loads(self.tools.engine.redoJournal.read_text(encoding='utf8'))
        except (OSError, ValueError) as error:
            self.tools.report('No available Redo: ' + str(error))
            return
        self.tools.run('Redo file operation', lambda c, p: self.tools.engine.redo(),
            lambda result: self.tools.remapRecords([(e['source'], e['target']) for e in record['entries']]
                if record['action'] in ('move', 'rename') and not result['errors'] else []))

    def jobs(self):
        """実行中・待機中・完了した操作と再試行を表示する。"""
        dialog = QtWidgets.QDialog(self.e)
        dialog.setWindowTitle('File jobs')
        dialog.resize(1200, 440)
        layout = QtWidgets.QVBoxLayout(dialog)
        table = QtWidgets.QTreeWidget()
        table.setHeaderLabels(['Operation', 'State', 'Transferred', 'Result'])
        layout.addWidget(table)
        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        def refresh():
            """行を更新しながら選択したジョブを維持する。"""
            selected_item = table.currentItem()
            selected = selected_item.data(0, QtCore.Qt.UserRole) if selected_item else None
            vertical = table.verticalScrollBar().value()
            table.clear()
            for record in self.tools.jobRecords:
                result = record.get('result')
                detail = record.get('error', '')
                if isinstance(result, dict):
                    detail = '{} completed / {} errors'.format(len(result.get('completed', [])), len(result.get('errors', [])))
                item = QtWidgets.QTreeWidgetItem([record['title'], record['state'], str(record['bytes']), detail])
                item.setData(0, QtCore.Qt.UserRole, id(record))
                table.addTopLevelItem(item)
                if selected == id(record):
                    table.setCurrentItem(item)
            table.verticalScrollBar().setValue(vertical)
            pause_button.setText('Resume queue' if self.tools.queuePaused else 'Pause queue')
        def retry():
            """選択したジョブの失敗・未完了対象だけを再投入する。"""
            index = table.indexOfTopLevelItem(table.currentItem())
            if index >= 0:
                record = self.tools.jobRecords[index]
                if record.get('retry') and isinstance(record.get('result'), dict) and record['result'].get('retry'):
                    record['retry'](record['result'])
        def pause():
            """現在のI/Oは継続し、次のジョブの開始だけを止める。"""
            self.tools.queuePaused = not self.tools.queuePaused
            pause_button.setText('Resume queue' if self.tools.queuePaused else 'Pause queue')
            self.tools.nextJob()
        def cancelQueue():
            """待機中のジョブだけを中止する。"""
            for job in self.tools.queue:
                job[-1]['state'] = 'Cancelled before start'
            self.tools.queue.clear()
        def pauseActive():
            """実行中転送のハッシュ/コピーをブロック境界で停止・再開する。"""
            record = getattr(self.tools, 'activeRecord', {})
            flag = record.get('paused')
            if self.tools.task and flag is not None:
                if flag.is_set():
                    flag.clear()
                    record['state'] = 'Running'
                else:
                    flag.set()
                    record['state'] = 'Paused'

        def moveQueued(amount):
            """選択した待機ジョブを移動し、復元時の順も記録する。"""
            selected = table.indexOfTopLevelItem(table.currentItem())
            if selected < 0:
                return
            record = self.tools.jobRecords[selected]
            queue = self.tools.queue
            index = next((i for i, job in enumerate(queue) if job[-1] is record), -1)
            target = index + amount
            if index < 0 or not 0 <= target < len(queue):
                return
            queue[index], queue[target] = queue[target], queue[index]
            from qpeRecovery import writeJob
            for position, job in enumerate(queue):
                if job[-1].get('jobPath'):
                    path = job[-1]['jobPath']
                    value = json.loads(Path(path).read_text(encoding='utf8'))
                    value['order'] = time.time() + position
                    writeJob(path, value)
            order = {id(job[-1]): i for i, job in enumerate(queue)}
            self.tools.jobRecords[:] = [r for r in self.tools.jobRecords if id(r) not in order] + [job[-1] for job in queue]
            refresh()

        for title, callback in [('Pause / resume active transfer', pauseActive),
                                ('Move up', lambda: moveQueued(-1)), ('Move down', lambda: moveQueued(1))]:
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        pause_button = QtWidgets.QPushButton('Pause queue')
        pause_button.clicked.connect(pause)
        row.addWidget(pause_button)
        for title, callback in [('Cancel active', lambda: self.tools.task.cancel.set() if self.tools.task else None),
                                ('Cancel queued', cancelQueue), ('Retry failed items', retry)]:
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        timer = QtCore.QTimer(dialog)
        timer.timeout.connect(refresh)
        dialog.finished.connect(timer.stop)
        timer.start(500)
        refresh()
        self.tools.dialogs.append(dialog)
        dialog.show()

    def recoverTransfers(self):
        """再起動前のジョブを利用者が確認して再開する。自動書込みはしない。"""
        from qpeRecovery import pendingJobs, writeJob
        pending = pendingJobs(self.tools.engine.directory.parent / 'jobs')
        dialog = QtWidgets.QDialog(self.e)
        dialog.setWindowTitle('Resume unfinished transfers')
        dialog.resize(960, 480)
        layout = QtWidgets.QVBoxLayout(dialog)
        layout.addWidget(QtWidgets.QLabel('Resume validates prepared sources and destinations. Interrupted files restart from the beginning.\nUnprepared queued jobs read the current source contents. Ambiguous commits require manual review.'))
        table = QtWidgets.QTreeWidget()
        table.setHeaderLabels(['Operation', 'State', 'Sources', 'Destination'])
        layout.addWidget(table)
        for path, value in pending:
            item = QtWidgets.QTreeWidgetItem([self.tools.operationLabel(value['action']), value['state'], '\n'.join(value['paths']), value['destination']])
            item.setData(0, QtCore.Qt.UserRole, path)
            table.addTopLevelItem(item)
        def resume():
            """選んだジョブだけ共通キューへ戻す。"""
            item = table.currentItem()
            if item:
                self.tools.resumeTransfer(item.data(0, QtCore.Qt.UserRole))
                dialog.close()
        def discard():
            """記録だけを除外し、原本やUndoバックアップは削除しない。"""
            item = table.currentItem()
            if not item:
                return
            path = item.data(0, QtCore.Qt.UserRole)
            if any(r.get('jobPath') == path and r['state'] in ('Queued', 'Running', 'Paused') for r in self.tools.jobRecords):
                self.tools.report('Cancel the active/queued transfer before discarding its record.')
                return
            try:
                with self.tools.engine.exclusive():
                    value = json.loads(Path(path).read_text(encoding='utf8'))
                    value['state'] = 'Discarded'
                    writeJob(path, value)
            except (OSError, RuntimeError) as error:
                self.tools.report(str(error))
                return
            table.takeTopLevelItem(table.indexOfTopLevelItem(item))
        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        for title, callback in [('Resume selected', resume), ('Discard record', discard)]:
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.tools.dialogs.append(dialog)
        dialog.show()

    def history(self):
        """戻せる順序とバックアップ保持条件を明示する。"""
        dialog = QtWidgets.QDialog(self.e)
        dialog.setWindowTitle('File operation history — Undo applies to the latest operation')
        dialog.resize(850, 460)
        layout = QtWidgets.QVBoxLayout(dialog)
        listing = QtWidgets.QTreeWidget()
        listing.setHeaderLabels(['Time', 'Operation', 'Items', 'Target'])
        layout.addWidget(listing)
        try:
            with self.tools.engine.exclusive():
                history = list(self.tools.engine.history)
        except Exception as error:
            self.tools.report(str(error))
            return
        for record in reversed(history):
            stamp = datetime.datetime.fromtimestamp(record.get('time', 0)).isoformat(' ', 'seconds') if record.get('time') else 'Earlier history'
            listing.addTopLevelItem(QtWidgets.QTreeWidgetItem([stamp, self.tools.operationLabel(record['action']), str(len(record['entries'])),
                '\n'.join(e['target'] or e['source'] for e in record['entries'])]))
        layout.addWidget(QtWidgets.QLabel('Undo / Redo verifies contents and refuses externally changed files.\nHistory backups use disk space. Cleanup is explicit, never automatic.'))
        row = QtWidgets.QHBoxLayout()
        layout.addLayout(row)
        for title, callback in [('Undo latest', self.tools.undo), ('Redo latest undo', self.redo),
                                ('Backup storage size', lambda: self.summary(self.backupPaths())),
                                ('Clean up expired history…', self.cleanupHistory)]:
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            row.addWidget(button)
        self.tools.dialogs.append(dialog)
        dialog.show()

    def backupPaths(self):
        """外部に退避した移動元も容量表示へ含める。"""
        return [str(self.tools.engine.directory)] + [e['sourceBackup'] for record in self.tools.engine.history
            for e in record['entries'] if e.get('sourceBackup')]

    def cleanupHistory(self):
        """保持設定の期限・容量を超える古い履歴を確認して削除する。"""
        values = readSettings().get('preferences', {})
        days, budget = values.get('undoDays', 30), values.get('undoMiB', 1024)
        if QtWidgets.QMessageBox.question(self.e, 'Clean up Undo history',
                'Remove oldest Undo backups older than {} days or exceeding {} MiB?\nRemoved operations cannot be undone.'.format(days, budget),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel) == QtWidgets.QMessageBox.Yes:
            self.tools.run('Clean up Undo history', lambda c, p: self.tools.engine.prune(days, budget * 1024 * 1024))

    def settings(self):
        """表示・保持条件・キー割当・外部設定を一つの画面にまとめる。"""
        from qpePreferences import PreferencesDialog
        dialog = PreferencesDialog(self)
        self.tools.dialogs.append(dialog)
        dialog.show()

    def manageLabels(self):
        """タグ名を全項目で改名または削除する。"""
        values = readSettings().get('fileLabels', {})
        names = sorted({tag for value in values.values() for tag in value.get('tags', [])})
        old, ok = QtWidgets.QInputDialog.getItem(self.e, 'Manage tags', 'Tag', names, 0, False)
        if not ok or not old:
            return
        new, ok = QtWidgets.QInputDialog.getText(self.e, 'Rename tag', 'New name (empty removes this tag)', text=old)
        if not ok:
            return
        for value in values.values():
            value['tags'] = list(dict.fromkeys(new.strip() if tag == old else tag for tag in value.get('tags', []) if tag != old or new.strip()))
        writeSettings({'fileLabels': values})
        self.refresh()


class FileRow(QtWidgets.QTreeWidgetItem):
    """サイズ列を文字列順ではなく数値順に並べる。"""

    def __lt__(self, other):
        """グループ見出しを含む場合は通常の文字列比較に戻す。"""
        if self.treeWidget().sortColumn() == 1:
            left, right = self.data(1, QtCore.Qt.UserRole), other.data(1, QtCore.Qt.UserRole)
            if left is not None and right is not None:
                return left < right
        column = self.treeWidget().sortColumn()
        return self.text(column).casefold() < other.text(column).casefold()


class FileGrid(QtWidgets.QListWidget):
    """OSへファイルURLを渡すサムネイル一覧。"""

    def mimeData(self, items):
        """独自Qt項目ではなくExplorer互換URLを渡す。"""
        data = QtCore.QMimeData()
        data.setUrls([QtCore.QUrl.fromLocalFile(i.data(QtCore.Qt.UserRole)) for i in items if i.data(QtCore.Qt.UserRole)])
        return data


class FileTree(QtWidgets.QTreeWidget):
    """グループ見出しをドラッグ対象に含めない一覧。"""

    def mimeData(self, items):
        """所在を持つ行だけを外部へ渡す。"""
        data = QtCore.QMimeData()
        data.setUrls([QtCore.QUrl.fromLocalFile(i.data(0, QtCore.Qt.UserRole)) for i in items if i.data(0, QtCore.Qt.UserRole)])
        return data

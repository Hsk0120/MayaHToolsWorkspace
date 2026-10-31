"""ファイル整理機能を既存のカラムUIへ接続する。"""
import os
import re
import shutil
import struct
import subprocess
import threading
import time
from pathlib import Path
from qpeQt import QAction, QtCore, QtGui, QtWidgets, shiboken
from qpeSettings import readSettings, writeSettings, settingsPath
from qpeTransactions import FileTransactions, Cancelled
from qpeSearch import searchFiles, duplicateFiles, hashFile, compareFolders, createZip, extractZip, sceneInfo, everythingSearch

_jobs = set()


class TaskSignals(QtCore.QObject):
    """ワーカーの進捗と結果をGUIへ渡す。"""
    progress = QtCore.Signal(str, int)
    finished = QtCore.Signal(object, str)


class Task(QtCore.QRunnable):
    """キャンセル可能なPython処理。Qtウィジェットへ直接触れない。"""

    def __init__(self, function):
        """処理に中止フラグと進捗通知を渡す。"""
        super().__init__()
        self.function = function
        self.cancel = threading.Event()
        self.signals = TaskSignals()

    def run(self):
        """例外も結果として返し、UIを操作可能な状態へ戻す。"""
        try:
            result = self.function(self.cancel, self.signals.progress.emit)
            error = ''
        except Exception as exception:
            result, error = None, str(exception)
        self.signals.finished.emit(result, error)


def launchTask(function, callback, progress=None):
    """実行中のワーカーを保持し、Qtのイベントループで結果を受け取る。"""
    task = Task(function)
    _jobs.add(task)

    def finished(result, error):
        """生存期間を終了し、接続先へ配送する。"""
        _jobs.discard(task)
        callback(result, error)
    task.signals.finished.connect(finished)
    if progress:
        task.signals.progress.connect(progress)
    QtCore.QThreadPool.globalInstance().start(task)
    return task


class ResultsDialog(QtWidgets.QDialog):
    """世代で古い結果を捨てる、範囲検索と保存検索の画面。"""
    rowsReady = QtCore.Signal(int, object)

    def __init__(self, tools):
        """検索条件と結果の所在を同じ画面に置く。"""
        super().__init__(tools.explorer)
        self.tools = tools
        self.serial = 0
        self.task = None
        self.setWindowTitle('Search files — including subfolders')
        self.resize(840, 530)
        layout = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        advanced = QtWidgets.QWidget(self)
        advanced_form = QtWidgets.QFormLayout(advanced)
        self.root = QtWidgets.QLineEdit(tools.explorer.currentDirectory)
        self.query = QtWidgets.QLineEdit()
        self.types = QtWidgets.QLineEdit()
        self.content = QtWidgets.QLineEdit()
        self.content.setPlaceholderText('Text contents — up to 16 MiB/file; .mb excluded')
        self.types.setPlaceholderText('*.ma;*.mb or leave empty')
        self.days = QtWidgets.QSpinBox()
        self.days.setRange(0, 36500)
        self.days.setSpecialValueText('Any date')
        self.days.setSuffix(' days')
        self.backend = QtWidgets.QComboBox()
        self.backend.addItems(['Folder scan', 'Everything CLI (optional)'])
        self.kind = QtWidgets.QComboBox()
        self.kind.addItems(['Files', 'Folders', 'Both'])
        self.minimum = QtWidgets.QSpinBox()
        self.maximum = QtWidgets.QSpinBox()
        for spin in (self.minimum, self.maximum):
            spin.setRange(0, 2147483647)
            spin.setSuffix(' KiB')
        self.exclude = QtWidgets.QLineEdit()
        self.tags = QtWidgets.QLineEdit()
        self.tagMode = QtWidgets.QComboBox()
        self.tagMode.addItems(['All', 'Any'])
        self.live = QtWidgets.QCheckBox('Refresh every 10 seconds while visible')
        self.root.setToolTip('Multiple scope folders: separate with ;')
        for label, control in [('Name / wildcard', self.query), ('Scope folder', self.root)]:
            form.addRow(label, control)
        for label, control in [('File types', self.types), ('Containing text', self.content), ('Modified within', self.days),
                               ('Search using', self.backend), ('Items', self.kind), ('Minimum size', self.minimum), ('Maximum size (0 = any)', self.maximum),
                               ('Exclude folders (;)', self.exclude), ('Tags (,)', self.tags), ('Match tags', self.tagMode), ('', self.live)]:
            advanced_form.addRow(label, control)
        layout.addLayout(form)
        self.advancedToggle = QtWidgets.QToolButton(self)
        self.advancedToggle.setText('More search options')
        self.advancedToggle.setCheckable(True)
        self.advancedToggle.toggled.connect(advanced.setVisible)
        layout.addWidget(self.advancedToggle)
        layout.addWidget(advanced)
        advanced.hide()
        row = QtWidgets.QHBoxLayout()
        for title, callback in [('Search', self.search), ('Stop', self.stop), ('Save search…', self.saveQuery)]:
            button = QtWidgets.QPushButton(title)
            button.clicked.connect(callback)
            button.setAutoDefault(False)
            if title == 'Search':
                self.searchButton = button
                button.setDefault(True)
            row.addWidget(button)
        layout.addLayout(row)
        self.results = QtWidgets.QTreeWidget()
        self.results.setHeaderLabels(['Name', 'Location', 'Matching lines'])
        self.results.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.results.setAlternatingRowColors(True)
        self.results.setColumnWidth(0, 250)
        self.results.setColumnWidth(1, 320)
        self.results.setMinimumHeight(160)
        self.results.setTextElideMode(QtCore.Qt.ElideMiddle)
        self.results.itemDoubleClicked.connect(self.locate)
        self.results.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.results.customContextMenuRequested.connect(self.menu)
        layout.addWidget(self.results, 1)
        self.status = QtWidgets.QLabel('Double-click a result to select it in its folder.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.rowsReady.connect(self.appendBatch)
        self.liveTimer = QtCore.QTimer(self)
        self.liveTimer.setInterval(10000)
        self.liveTimer.timeout.connect(self.liveRefresh)
        self.liveTimer.start()
        self.setTabOrder(self.query, self.root)
        self.query.setFocus()

    def resultItem(self, path):
        """表示場所は検索起点からの相対パス、実操作には絶対パスを保持する。"""
        parent = Path(path).parent
        location = str(parent)
        for root in self.root.text().split(';'):
            try:
                relative = parent.relative_to(Path(root.strip()))
                location = str(relative) if len(self.root.text().split(';')) == 1 else Path(root.strip()).name + '/' + str(relative)
                break
            except ValueError:
                continue
        item = QtWidgets.QTreeWidgetItem([Path(path).name, location])
        item.setData(0, QtCore.Qt.UserRole, path)
        item.setToolTip(0, path)
        item.setToolTip(1, str(parent))
        return item

    def liveRefresh(self):
        """表示中だけ定期再評価し、要求を重ねない。"""
        if self.live.isChecked() and self.isVisible() and not self.task:
            self.search()

    def restoreAdvanced(self, values):
        """保存検索の追加条件を復元する。"""
        for name in ('kind', 'tagMode'):
            getattr(self, name).setCurrentText(values.get(name, 'Files' if name == 'kind' else 'All'))
        for name in ('minimum', 'maximum'):
            getattr(self, name).setValue(int(values.get(name, 0)))
        for name in ('exclude', 'tags', 'content'):
            getattr(self, name).setText(values.get(name, ''))
        self.live.setChecked(bool(values.get('live', False)))

    def appendBatch(self, serial, paths):
        """現在の世代だけを小分けで表示する。"""
        if serial != self.serial:
            return
        for path in paths:
            item = self.resultItem(path)
            self.results.addTopLevelItem(item)
        self.status.setText('{} results — searching…'.format(self.results.topLevelItemCount()))

    def conditions(self):
        """再実行できる検索条件を返す。"""
        return dict(root=self.root.text(), query=self.query.text(), extensions=self.types.text(), days=self.days.value(),
                    kind=self.kind.currentText(), minimum=self.minimum.value(), maximum=self.maximum.value(),
                    content=self.content.text(), exclude=self.exclude.text(), tags=self.tags.text(), tagMode=self.tagMode.currentText(), live=self.live.isChecked())

    def search(self):
        """前回を無効化し、GUIスレッド外で検索する。"""
        self.stop()
        serial = self.serial
        options = self.conditions()
        roots = [p.strip() for p in options['root'].split(';') if p.strip()]
        if not roots or not all(os.path.isdir(p) for p in roots):
            self.status.setText('Choose an existing scope folder.')
            return
        days = options.pop('days')
        options['since'] = time.time() - days * 86400 if days else 0
        options['hidden'] = self.tools.hidden
        options.pop('live')
        self.results.clear()
        self.status.setText('Searching…')
        if self.backend.currentIndex():
            executable = readSettings().get('everythingExecutable') or shutil.which('es.exe')
            if not executable:
                self.status.setText('Install Everything and its es.exe CLI, or use Folder scan. Configure the CLI in Tools.')
                return
            if options['extensions'] or days or len(roots) != 1 or options['kind'] != 'Files' or any(options[k] for k in ('minimum', 'maximum', 'exclude', 'tags', 'content')):
                self.status.setText('Everything mode uses its query syntax; clear File types / Modified within or use Folder scan.')
                return
            function = lambda cancel, progress: everythingSearch(options['query'], options['root'], executable, cancel)
        else:
            from qpeAdvancedIO import searchAdvanced
            options.pop('root')
            options.update(roots=roots, minimum=options['minimum'] * 1024, maximum=options['maximum'] * 1024,
                           labels=readSettings().get('fileLabels', {}))
            function = lambda cancel, progress: searchAdvanced(cancel=cancel,
                batch=lambda paths: self.rowsReady.emit(serial, paths), **options)

        def completed(result, error):
            """終了・次要求の後に来た結果は表示しない。"""
            if not shiboken.isValid(self) or serial != self.serial:
                return
            self.task = None
            if error:
                self.status.setText(error)
                return
            if self.backend.currentIndex() or self.results.topLevelItemCount() != len(result['paths']):
                self.setPaths(result['paths'])
            for index in range(self.results.topLevelItemCount()):
                item = self.results.topLevelItem(index)
                hits = result.get('matches', {}).get(item.data(0, QtCore.Qt.UserRole), [])
                text = '\n'.join('{}: {}'.format(line, snippet) for line, snippet in hits)
                item.setText(2, text.split('\n')[0] if text else '')
                item.setToolTip(2, text)
            self.status.setToolTip('\n'.join(result.get('omitted', [])))
            self.status.setText('{} results. {} read errors.{}'.format(len(result['paths']), len(result['errors']),
                                '\n' + '\n'.join(result['errors'][:3]) if result['errors'] else ' {} files omitted (hover for reasons).'.format(len(result.get('omitted', [])))))
        self.task = launchTask(function, completed)
        if self.live.isChecked():
            self.liveTimer.start()

    def setPaths(self, paths):
        """結果を文字列として表示し、絶対パスを保持する。"""
        self.results.clear()
        for path in paths:
            item = self.resultItem(path)
            self.results.addTopLevelItem(item)

    def locate(self, item, column=0):
        """開く操作はせず、元のフォルダーで選択する。"""
        path = item.data(0, QtCore.Qt.UserRole)
        self.tools.explorer.navigate(str(Path(path).parent))
        self.tools.explorer._selectWhenReady(path)

    def menu(self, point):
        """検索結果も共通のファイル操作へ接続する。"""
        item = self.results.itemAt(point)
        if not item:
            return
        selected = self.results.selectedItems()
        paths = [i.data(0, QtCore.Qt.UserRole) for i in (selected if item in selected else [item])]
        menu = self.tools.explorer.createFileMenu(paths)
        menu.exec_(self.results.viewport().mapToGlobal(point))

    def stop(self):
        """実行中の要求と遅延結果を無効化する。"""
        self.serial += 1
        if self.task:
            self.task.cancel.set()
        self.task = None
        if hasattr(self, 'liveTimer'):
            self.liveTimer.stop()
        self.status.setText('Stopped')

    def closeEvent(self, event):
        """閉じた検索の結果で画面を書き換えない。"""
        self.stop()
        super().closeEvent(event)

    def saveQuery(self):
        """検索条件を名前付きで保存する。"""
        name, ok = QtWidgets.QInputDialog.getText(self, 'Save search', 'Name')
        if ok and name.strip():
            values = readSettings().get('savedSearches', {})
            values[name.strip()] = self.conditions()
            writeSettings({'savedSearches': values})
            self.tools.explorer._loadPlaces()


class Organizer(QtCore.QObject):
    """メニュー、クリップボード、検索、ファイル操作を束ねる。"""

    def __init__(self, explorer):
        """ホスト別のUIを保持し、実処理は共有の操作基盤へ委譲する。"""
        super().__init__(explorer)
        self.explorer = explorer
        self.engine = FileTransactions(settingsPath().parent / 'undo')
        self.task = None
        self.dialogs = []
        self.hidden = bool(readSettings().get('showHidden', False))
        for model in (explorer.folderModel, explorer.fileModel):
            model.showHidden = self.hidden
        self.button = QtWidgets.QToolButton(explorer)
        self.button.setText('Tools')
        self.button.setMinimumWidth(self.button.fontMetrics().horizontalAdvance('Tools') + 30)
        self.button.setToolTip('Search, file operations, saved searches and utilities')
        self.button.setPopupMode(QtWidgets.QToolButton.InstantPopup)
        self.toolsMenu = QtWidgets.QMenu(self.button)
        self.toolsMenu.aboutToShow.connect(self.populateTools)
        self.button.setMenu(self.toolsMenu)
        explorer.navigationBar.addWidget(self.button)
        self.dropStart = None
        self.views = {}
        explorer.files.setDragEnabled(False)
        explorer.files.viewport().setAcceptDrops(True)
        explorer.places.viewport().setAcceptDrops(True)
        explorer.files.viewport().installEventFilter(self)
        explorer.files.installEventFilter(self)
        explorer.places.viewport().installEventFilter(self)
        explorer.folderTabs.bar.setAcceptDrops(True)
        explorer.folderTabs.bar.installEventFilter(self)
        self.attachView(explorer.columns)
        for view in explorer.columns.findChildren(QtWidgets.QListView):
            self.attachView(view)
        self.second = None
        self.queue = []
        self.jobRecords = []
        self.queuePaused = False
        from qpeWorkspace import WorkspaceFeatures
        self.workspace = WorkspaceFeatures(self)
        from qpeRecovery import pendingJobs
        remaining = pendingJobs(self.engine.directory.parent / 'jobs')
        if remaining:
            QtCore.QTimer.singleShot(0, lambda: self.report('{} saved transfer(s). Tools → Resume unfinished transfers.'.format(len(remaining))))

    def attachView(self, view):
        """動的なフォルダーカラムを共通のコピー先として登録する。"""
        if view in self.views:
            return
        view.viewport().setAcceptDrops(True)
        view.viewport().installEventFilter(self)
        view.installEventFilter(self)
        self.views[view.viewport()] = view
        self.views[view] = view
        self.explorer.appearance.textSizeKeys.attach(view)
        # MayaはCtrl+TabのKeyPressを標準ビュー切替へ使うため、Qtの
        # ショートカット配送で先に処理する。この一覧自身にフォーカスがある時だけ有効。
        for sequence, step in (('Ctrl+Tab', 1), ('Ctrl+Shift+Tab', -1)):
            action = QAction(view)
            action.setShortcut(QtGui.QKeySequence(sequence))
            action.setShortcutContext(QtCore.Qt.WidgetShortcut)
            action.triggered.connect(lambda checked=False, offset=step: self.cycleTab(offset))
            view.addAction(action)
        view.destroyed.connect(lambda: self._forgetView(view))

    def cycleTab(self, offset):
        """フォーカスされた一覧のタブを指定方向へ一度だけ切り替える。"""
        tabs = self.explorer.folderTabs
        if tabs.bar.count():
            tabs.bar.setCurrentIndex((tabs.active + offset) % tabs.bar.count())

    def _forgetView(self, view):
        """破棄済みカラムを保持しない。"""
        self.views = {key: value for key, value in self.views.items() if value is not view}

    def clipboardHasFiles(self):
        """外部アプリが所有するQt5の無効なMIMEラッパーを扱う。"""
        data = QtWidgets.QApplication.clipboard().mimeData()
        return bool(data is not None and shiboken.isValid(data) and data.hasUrls())

    def report(self, text):
        """結果を閉じないステータス欄へ表示する。"""
        self.explorer.status.setText(text)
        self.explorer.status.show()

    def run(self, title, function, callback=None, retry=None, record=None):
        """書込みを直列化し、進捗・中止・完了結果を明示する。"""
        if record is None:
            record = dict(title=title, state='Queued', bytes=0, started=0, result=None, retry=retry)
        if not any(r is record for r in self.jobRecords):
            self.jobRecords.append(record)
        if self.task or self.queuePaused:
            self.queue.append((title, function, callback, retry, record))
            self.report('{} queued operation(s)'.format(len(self.queue)))
            return
        self.activeRecord = record
        record.update(state='Running', started=time.monotonic())
        dialog = QtWidgets.QProgressDialog(title, 'Cancel', 0, 0, self.explorer)
        dialog.setWindowTitle('QuickPathExplorer — file operation')
        dialog.setWindowModality(QtCore.Qt.NonModal)
        dialog.setMinimumDuration(0)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        total = [0]

        def progress(path, amount):
            """頻繁な更新を一定間隔にまとめてUIを保つ。"""
            if path.startswith('@total:'):
                record['total'] = int(path.split(':', 1)[1])
                if shiboken.isValid(dialog) and record['total']:
                    dialog.setRange(0, 1000)
                return
            total[0] += amount
            record['bytes'] = total[0]
            if shiboken.isValid(dialog):
                elapsed = max(0.1, time.monotonic() - record['started'])
                if record.get('total'):
                    dialog.setValue(min(1000, int(total[0] * 1000 / record['total'])))
                dialog.setLabelText('{}\n{}\n{} — {}/s'.format(title, path,
                    QtCore.QLocale.system().formattedDataSize(total[0]),
                    QtCore.QLocale.system().formattedDataSize(int(total[0] / elapsed))))

        def completed(result, error):
            """完了した操作だけを一覧とUndo表示へ反映する。"""
            self.task = None
            if shiboken.isValid(dialog):
                dialog.close()
            record.update(result=result, error=error, state='Failed' if error else 'Completed')
            if not shiboken.isValid(self.explorer):
                return
            if error:
                self.report(error)
            else:
                if isinstance(result, dict) and 'completed' in result:
                    record['state'] = 'Cancelled' if result['cancelled'] else ('Partial / failed' if result['errors'] else 'Completed')
                    self.report('{}: {} completed, {} skipped, {} failed{}'.format(title,
                        len(result['completed']), len(result['skipped']), len(result['errors']),
                        ' — cancelled' if result['cancelled'] else ''))
                    if result['errors']:
                        self.showText('\n'.join(result['errors']))
                    if result.get('warnings'):
                        record['state'] = 'Completed / history warning'
                        self.report(title + ': files completed — Undo history needs recovery. Do not repeat the transfer.')
                        self.showText('\n'.join(result['warnings']))
                    if title == 'Move' and self.engine.history:
                        entries = self.engine.history[-1]['entries']
                        self.remapRecords([(entry['source'], entry['target']) for entry in entries if entry.get('moved')])
                else:
                    self.report(title + ': completed')
                if callback:
                    callback(result)
            for model in (self.explorer.folderModel, self.explorer.fileModel):
                for path in list(model._active):
                    model.request(path)
            location = Path(self.explorer.currentDirectory)
            if not location.is_dir():
                while location.parent != location and not location.is_dir():
                    location = location.parent
                self.explorer.navigate(str(location))
            self.workspace.refresh()
            QtCore.QTimer.singleShot(0, self.nextJob)
        self.task = launchTask(function, completed, progress)
        dialog.canceled.connect(self.task.cancel.set)
        dialog.show()

    def nextJob(self):
        """予約を依頼順に実行し、待機中の一時停止を尊重する。"""
        if self.queue and not self.task and not self.queuePaused:
            self.run(*self.queue.pop(0))

    @staticmethod
    def operationLabel(action):
        """保存済みの操作識別子を変更せず、画面向けの名前を返す。

        Args:
            action (str): 履歴・転送の内部操作名。

        Returns:
            str: Windows向けの表示名。
        """
        return {'trash': 'Delete', 'duplicate': 'Create Copy'}.get(action, action.title())

    def transfer(self, action, paths, destination=None, conflict=None):
        """固定済み対象を操作し、同名の扱いを開始前に選ぶ。"""
        paths = list(dict.fromkeys(paths))
        if not paths:
            return
        destination = destination or self.explorer.currentDirectory
        if action == 'trash':
            if QtWidgets.QMessageBox.question(self.explorer, 'Delete',
                    'Move {} item(s) to Recycle Bin?\n{}'.format(len(paths), '\n'.join(paths)),
                    QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
                return
        elif conflict is None and any((Path(destination) / Path(path).name).exists() for path in paths):
            options = ['Keep both (new name)', 'Skip existing', 'Replace (Undo backup)']
            if action == 'copy' and any(Path(p).is_dir() and (Path(destination) / Path(p).name).is_dir() for p in paths):
                options.append('Merge folders (keep destination-only files)')
            choice, ok = QtWidgets.QInputDialog.getItem(self.explorer, 'Existing names',
                'Apply to this operation', options, 0, False)
            if not ok:
                return
            conflict = {'Keep both (new name)': 'rename', 'Skip existing': 'skip', 'Replace (Undo backup)': 'replace',
                        options[-1]: 'merge' if len(options) == 4 else 'replace'}[choice]
        choices = self.workspace.mergeChoices(paths, destination) if conflict == 'merge' else {}
        if choices is None:
            return
        if action in ('copy', 'move', 'duplicate'):
            from qpeRecovery import createJob
            path = createJob(self.engine.directory.parent / 'jobs', action, paths, destination, conflict or 'rename', choices)
            self.resumeTransfer(path)
        else:
            self.run(self.operationLabel(action), lambda c, p: self.engine.run(action, paths, destination, conflict or 'rename', c, p, choices),
                     retry=lambda result: self.transfer(action, result.get('retry', []), destination, conflict))

    def resumeTransfer(self, path):
        """保存済み転送を明示的に再開し、一時停止制御を共有する。"""
        from qpeRecovery import executeJob, PauseControl
        if any(r.get('jobPath') == path and r['state'] in ('Running', 'Paused', 'Queued') for r in self.jobRecords):
            self.report('This transfer is already active or queued.')
            return
        import json
        value = json.loads(Path(path).read_text(encoding='utf8'))
        title = self.operationLabel(value['action'])
        paused = threading.Event()
        record = dict(title=title, state='Queued', bytes=0, started=0, result=None,
                      retry=lambda result: self.resumeTransfer(path), paused=paused, jobPath=path)
        self.run(title, lambda c, p: executeJob(self.engine, path, PauseControl(c, paused), p),
                 callback=lambda result: self.remapCompletedTransfer(path), retry=record['retry'], record=record)

    def remapCompletedTransfer(self, path):
        """移動が確定した保存ジョブだけお気に入りへ反映する。"""
        import json
        value = json.loads(Path(path).read_text(encoding='utf8'))
        if value['action'] == 'move':
            ids = {i['transaction'] for i in value['items'] if i['state'] == 'Completed'}
            self.remapRecords([(e['source'], e['target']) for t in self.engine.history if ids.intersection(t.get('recoveryTransactions', [t['id']]))
                               for e in t['entries'] if e.get('moved')])

    def clipboard(self, paths, cut=False):
        """Explorerと相互運用するURLとWindows DropEffectを設定する。"""
        data = QtCore.QMimeData()
        data.setUrls([QtCore.QUrl.fromLocalFile(path) for path in paths])
        data.setData('application/x-qt-windows-mime;value="Preferred DropEffect"', struct.pack('<I', 2 if cut else 1))
        data.setData('application/x-qpe-cut', b'1' if cut else b'0')
        QtWidgets.QApplication.clipboard().setMimeData(data)
        self.report(('Cut' if cut else 'Copied') + ': {} item(s)'.format(len(paths)))

    def paste(self, destination):
        """ファイルURLのみ受け付け、切り取り／コピーを共通処理へ渡す。"""
        data = QtWidgets.QApplication.clipboard().mimeData()
        if data is None or not shiboken.isValid(data) or not data.hasUrls():
            return
        effect = bytes(data.data('application/x-qt-windows-mime;value="Preferred DropEffect"'))
        cut = bytes(data.data('application/x-qpe-cut')) == b'1' or effect[:4] == struct.pack('<I', 2)
        self.transfer('move' if cut else 'copy', [u.toLocalFile() for u in data.urls() if u.isLocalFile()], destination)

    def addMenu(self, menu, paths, directory):
        """既存の右クリック対象を保持して機能を追加する。"""
        menu.addSeparator()
        if paths:
            menu.addAction('Copy', lambda: self.clipboard(paths))
            menu.addAction('Cut', lambda: self.clipboard(paths, True))
            menu.addAction('Create Copy', lambda: self.transfer('duplicate', paths, conflict='rename'))
            menu.addAction('Delete', lambda: self.transfer('trash', paths))
            menu.addAction('Batch Rename…', lambda: self.batchRename(paths))
            menu.addAction('Tags / rating / collection…', lambda: self.tag(paths))
            menu.addAction('Create ZIP…', lambda: self.zip(paths))
            if len(paths) == 1:
                path = paths[0]
                menu.addAction('Properties', lambda: self.shell(path, 'properties'))
                if os.path.isfile(path):
                    menu.addAction('Open with…', lambda: self.shell(path, 'openas'))
                    menu.addAction('SHA-256', lambda: self.run('SHA-256', lambda c, p: hashFile(path, c), self.showText))
                    if Path(path).suffix.lower() == '.zip':
                        menu.addAction('Extract ZIP…', lambda: self.unzip(path))
                    if Path(path).suffix.lower() in ('.ma', '.mb'):
                        menu.addAction('Scene information / dependencies', lambda: self.run('Scene information', lambda c, p: sceneInfo(path), self.showText))
        menu.addAction('Paste', lambda: self.paste(directory)).setEnabled(self.clipboardHasFiles())
        menu.addAction('Undo file operation', self.undo).setEnabled(bool(self.engine.history) and not self.task)
        self.workspace.addFileActions(menu, paths)

    def populateTools(self):
        """常設ボタンを増やさず、低頻度機能をまとめる。"""
        menu = self.toolsMenu
        menu.clear()
        menu.addAction('Search subfolders…', self.search)
        saved = menu.addMenu('Saved searches')
        for name, conditions in readSettings().get('savedSearches', {}).items():
            saved.addAction(name, lambda checked=False, value=conditions: self.search(value))
        menu.addAction('Browse tags / collections…', self.browseTags)
        hidden = menu.addAction('Show hidden files')
        hidden.setCheckable(True)
        hidden.setChecked(self.hidden)
        hidden.toggled.connect(self.setHidden)
        menu.addAction('Second file pane', self.toggleSecond)
        menu.addAction('Compare folders and copy changes…', self.compare)
        menu.addAction('Find duplicate files…', self.duplicates)
        menu.addAction('Undo file operation', self.undo).setEnabled(bool(self.engine.history) and not self.task)
        menu.addAction('Open Undo storage', lambda: QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(str(self.engine.directory))))
        menu.addAction('Discard Undo history…', self.discardHistory)
        menu.addSeparator()
        menu.addAction('Reopen closed tab', self.explorer.folderTabs.reopen)
        if self.explorer._maya:
            menu.addAction('Save read settings preset…', self.saveReadPreset)
            presets = menu.addMenu('Load read settings preset')
            for name, state in readSettings().get('readPresets', {}).items():
                presets.addAction(name, lambda checked=False, value=state: self.explorer.readOptions.restore(value))
            menu.addAction('Existing Maya namespaces…', self.namespaces)
            menu.addAction('Save scene information and thumbnail…', self.sidecar)
        menu.addSeparator()
        menu.addAction('Configure Everything CLI…', lambda: self.configureExecutable('everythingExecutable'))
        self.workspace.addTools(menu)
        self.groupTools()
        if hasattr(self.explorer, 'modern'):
            self.explorer.modern.addNavigationMenu(menu)

    def groupTools(self):
        """画面を越える長いメニューを、操作名を保ったまま用途別に整理する。"""
        groups = {
            'Search / organize': ['Saved searches', 'Browse tags / collections…', 'Manage label names…',
                'Compare folders and copy changes…', 'Find duplicate files…', 'Calculate selected / folder size…'],
            'View': ['Show hidden files', 'Second file pane', 'View: thumbnails', 'View: extended details / tags',
                'View: toggle subfolders', 'Open selected file', 'Browse ZIP…'],
            'Transfers / history': ['File jobs / retry…', 'Resume unfinished transfers…', 'Undo file operation',
                'Redo file operation', 'File operation history…', 'Open Undo storage', 'Clean up expired history…', 'Discard Undo history…'],
            'Tabs / tab sets': ['Reopen closed tab', 'Save tab set…', 'Open tab set…',
                'Delete tab set…', 'Restore previous tab set'],
            'Maya': ['Save read settings preset…', 'Load read settings preset', 'Existing Maya namespaces…',
                'Save scene information and thumbnail…'],
            'Settings / diagnostics': ['QPE settings / export…',
                'Configure Everything CLI…', 'Configure File Locksmith CLI…', 'Diagnose file usage / availability…']}
        actions = {action.text(): action for action in self.toolsMenu.actions() if not action.isSeparator()}
        paths = self.explorer.selectedPaths()
        availability = {
            'Reopen closed tab': bool(self.explorer.folderTabs.closed),
            'Open tab set…': bool(readSettings().get('tabSets')),
            'Delete tab set…': bool(readSettings().get('tabSets')),
            'Restore previous tab set': bool(readSettings().get('previousWorkspace')),
            'Open selected file': len(paths) == 1,
            'Browse ZIP…': len(paths) == 1 and Path(paths[0]).suffix.lower() == '.zip',
            'Redo file operation': self.engine.redoJournal.exists() and not self.task}
        for title, enabled in availability.items():
            actions[title].setEnabled(bool(enabled))
        actions['Second file pane'].setCheckable(True)
        actions['Second file pane'].setChecked(self.second is not None and self.second.isVisible())
        for action in list(self.toolsMenu.actions()):
            if action.isSeparator():
                self.toolsMenu.removeAction(action)
        for title, names in groups.items():
            available = [actions[name] for name in names if name in actions]
            if not available:
                continue
            submenu = self.toolsMenu.addMenu(title)
            for action in available:
                self.toolsMenu.removeAction(action)
                submenu.addAction(action)

    def undo(self):
        """MayaのUndoとは別の履歴を戻す。"""
        entries = list(self.engine.history[-1]['entries']) if self.engine.history else []
        action = self.engine.history[-1]['action'] if self.engine.history else ''
        self.run('Undo file operation', lambda c, p: self.engine.undo(),
                 lambda result: self.remapRecords([(v['target'], v['source']) for v in entries]
                                                  if action in ('move', 'rename') else []))

    def remapRecords(self, pairs):
        """改名・移動に合わせてラベルと場所リンクを更新する。"""
        if not pairs:
            return
        def remap(path):
            """フォルダーの子孫も同じ新しい場所へ移す。"""
            for source, target in pairs:
                source_key = os.path.normcase(os.path.abspath(source))
                key = os.path.normcase(os.path.abspath(path))
                if key == source_key:
                    return target
                if key.startswith(source_key + os.sep):
                    return str(Path(target) / os.path.relpath(path, source))
            return path
        settings = readSettings()
        writeSettings({'fileLabels': {os.path.normcase(os.path.abspath(remap(path))): value
                                      for path, value in settings.get('fileLabels', {}).items()},
                       'favorites': [remap(p) for p in settings.get('favorites', [])],
                       'recents': [remap(p) for p in settings.get('recents', [])]})
        e = self.explorer
        current = remap(e.currentDirectory)
        if current != e.currentDirectory and os.path.isdir(current):
            e.navigate(current)
        e._loadPlaces()

    def discardHistory(self):
        """バックアップ削除を具体的に確認してから容量を解放する。"""
        if QtWidgets.QMessageBox.question(self.explorer, 'Discard file Undo history',
                'Delete QPE Undo backups and forget all file-operation history?\nCompleted file operations remain in place. They will no longer be undoable.',
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel) == QtWidgets.QMessageBox.Yes:
            self.run('Discard Undo history', lambda c, p: self.engine.discardHistory())

    def setHidden(self, value):
        """カラムと一覧を同時に再列挙する。"""
        self.hidden = value
        writeSettings({'showHidden': value})
        for model in (self.explorer.folderModel, self.explorer.fileModel):
            model.showHidden = value
            for path in list(model._active):
                model.request(path)

    def search(self, conditions=None):
        """独立した検索ウィンドウを開く。"""
        dialog = ResultsDialog(self)
        self.dialogs.append(dialog)
        if isinstance(conditions, dict):
            dialog.root.setText(conditions.get('root', self.explorer.currentDirectory))
            dialog.query.setText(conditions.get('query', ''))
            dialog.types.setText(conditions.get('extensions', ''))
            dialog.days.setValue(conditions.get('days', 0))
            dialog.restoreAdvanced(conditions)
        dialog.show()
        dialog.query.setFocus()
        if isinstance(conditions, dict):
            dialog.search()
        return dialog

    def showText(self, text):
        """長い結果は選択・コピーできるウィンドウへ表示する。"""
        dialog = QtWidgets.QDialog(self.explorer)
        dialog.setWindowTitle('QuickPathExplorer — result')
        dialog.resize(780, 500)
        layout = QtWidgets.QVBoxLayout(dialog)
        content = QtWidgets.QPlainTextEdit(str(text))
        content.setReadOnly(True)
        layout.addWidget(content)
        self.dialogs.append(dialog)
        dialog.show()

    def batchRename(self, paths):
        """名前の変換をプレビューし、衝突のない計画だけを実行する。"""
        dialog = QtWidgets.QDialog(self.explorer)
        dialog.setWindowTitle('Batch Rename — preview before applying')
        dialog.resize(720, 470)
        layout = QtWidgets.QVBoxLayout(dialog)
        form = QtWidgets.QFormLayout()
        fields = {}
        for key, label in [('find', 'Find'), ('replace', 'Replace'), ('prefix', 'Prefix'), ('suffix', 'Suffix')]:
            fields[key] = QtWidgets.QLineEdit()
            form.addRow(label, fields[key])
        regex = QtWidgets.QCheckBox('Regular expression')
        sequence = QtWidgets.QCheckBox('Append sequence (001, 002, …)')
        form.addRow(regex)
        form.addRow(sequence)
        layout.addLayout(form)
        table = QtWidgets.QTreeWidget()
        table.setHeaderLabels(['Before', 'After'])
        table.setColumnWidth(0, 320)
        layout.addWidget(table)
        status = QtWidgets.QLabel()
        layout.addWidget(status)
        apply = QtWidgets.QPushButton('Apply rename')
        layout.addWidget(apply)
        plan = []

        def preview():
            """入力ごとに計画を再生成し、無効な変更を実行できなくする。"""
            from qpeFileOperations import validateName
            plan[:] = []
            table.clear()
            names = set()
            try:
                for number, value in enumerate(paths, 1):
                    path = Path(value)
                    base = path.name if path.is_dir() else path.stem
                    find, replace = fields['find'].text(), fields['replace'].text()
                    if find:
                        base = re.sub(find, replace, base) if regex.isChecked() else base.replace(find, replace)
                    name = fields['prefix'].text() + base + fields['suffix'].text()
                    if sequence.isChecked():
                        name += '_{:03d}'.format(number)
                    if not path.is_dir():
                        name += path.suffix
                    validateName(name)
                    target = path.with_name(name)
                    key = os.path.normcase(str(target))
                    if key in names or (name != path.name and target.exists()):
                        raise ValueError('Name conflict: ' + str(target))
                    names.add(key)
                    plan.append((str(path), name))
                    QtWidgets.QTreeWidgetItem(table, [path.name, name])
                status.setText('Changes can be undone using Undo file operation.')
                apply.setEnabled(any(Path(p).name != n for p, n in plan))
            except (ValueError, re.error) as error:
                status.setText(str(error))
                apply.setEnabled(False)

        def commit():
            """プレビューの値を固定して実行する。"""
            pairs = list(plan)
            dialog.accept()
            self.run('Batch Rename', lambda c, p: self.engine.rename(pairs),
                     lambda result: self.remapRecords([(p, str(Path(p).with_name(n))) for p, n in pairs]))
        for field in fields.values():
            field.textChanged.connect(preview)
        regex.toggled.connect(preview)
        sequence.toggled.connect(preview)
        apply.clicked.connect(commit)
        preview()
        self.dialogs.append(dialog)
        dialog.show()

    def tag(self, paths):
        """ファイル自体を書き換えず、QPE専用メタデータを編集する。"""
        values = readSettings().get('fileLabels', {})
        current = values.get(os.path.normcase(os.path.abspath(paths[0])), {}) if len(paths) == 1 else {}
        dialog = QtWidgets.QDialog(self.explorer)
        dialog.setWindowTitle('QPE labels (local to this user)')
        form = QtWidgets.QFormLayout(dialog)
        tags = QtWidgets.QLineEdit(', '.join(current.get('tags', [])))
        collection = QtWidgets.QLineEdit(current.get('collection', ''))
        rating = QtWidgets.QSpinBox()
        rating.setRange(0, 5)
        rating.setValue(current.get('rating', 0))
        for title, widget in [('Tags (comma separated)', tags), ('Collection', collection), ('Rating (0–5)', rating)]:
            form.addRow(title, widget)
        button = QtWidgets.QPushButton('Save')
        form.addRow(button)

        def save():
            """対象集合へ同じメタデータを保存する。"""
            for path in paths:
                values[os.path.normcase(os.path.abspath(path))] = dict(tags=[t.strip() for t in tags.text().split(',') if t.strip()],
                    rating=rating.value(), collection=collection.text().strip())
            writeSettings({'fileLabels': values})
            self.workspace.refresh()
            dialog.accept()
        button.clicked.connect(save)
        dialog.exec_()

    def browseTags(self):
        """タグ・コレクション・評価による仮想一覧を表示する。"""
        query, ok = QtWidgets.QInputDialog.getText(self.explorer, 'Labels', 'Tag / collection, or rating:3 (minimum). Empty = all')
        if not ok:
            return
        values = readSettings().get('fileLabels', {})
        paths = []
        for path, value in values.items():
            accepted = not query or query.lower() in ' '.join(value.get('tags', []) + [value.get('collection', '')]).lower()
            if query.startswith('rating:'):
                try:
                    accepted = value.get('rating', 0) >= int(query.split(':')[1])
                except ValueError:
                    self.report('Use rating:0 through rating:5')
                    return
            if accepted and os.path.exists(path):
                paths.append(path)
        dialog = self.search()
        dialog.setWindowTitle('Tags / collections')
        dialog.setPaths(paths)
        dialog.status.setText('{} labeled items'.format(len(paths)))

    def zip(self, paths):
        """保存先を指定してZIPを作る。"""
        path, unused = QtWidgets.QFileDialog.getSaveFileName(self.explorer, 'Create ZIP',
            str(Path(paths[0]).parent / 'archive.zip'), 'ZIP (*.zip)')
        if path:
            def create(cancel, progress):
                """新規アーカイブもUndoの対象にする。"""
                output = createZip(paths, path, cancel)
                self.engine.recordCreation(output)
                return output
            self.run('Create ZIP', create)

    def unzip(self, path):
        """既存ファイルを上書きしない新規フォルダーへ展開する。"""
        target, ok = QtWidgets.QInputDialog.getText(self.explorer, 'Extract ZIP', 'New destination folder', text=str(Path(path).with_suffix('')))
        if ok:
            def extract(cancel, progress):
                """展開した新規フォルダーをUndoへ登録する。"""
                output = extractZip(path, target, cancel)
                self.engine.recordCreation(output)
                return output
            self.run('Extract ZIP', extract)

    def duplicates(self):
        """現在の範囲の同一内容ファイルを削除せず一覧にする。"""
        root = self.explorer.currentDirectory
        self.run('Find duplicate files', lambda c, p: duplicateFiles(root, c),
                 lambda result: self.showText('\n\n'.join('\n'.join(g) for g in result['groups']) + '\nErrors: ' + str(result['errors'])))

    def compare(self):
        """一方向同期の差分を先に表示し、余分な宛先ファイルは削除しない。"""
        source = self.explorer.currentDirectory
        target = QtWidgets.QFileDialog.getExistingDirectory(self.explorer, 'Choose destination for folder comparison')
        if not target or Path(source).resolve() == Path(target).resolve():
            return

        def show(result):
            """具体的な差分を確認してから同期する。"""
            self.showText('\n'.join('{}: {}'.format(c['state'], c['target']) for c in result['changes'])
                          + '\nTarget-only (kept):\n' + '\n'.join(result['targetOnly']) + '\nRead errors: ' + str(result['errors']))
            if result['errors'] or not result['changes']:
                return
            if QtWidgets.QMessageBox.question(self.explorer, 'Copy changes to destination',
                'Copy {} new/changed files from\n{}\nto\n{}?\nTarget-only files are kept. Replaced files have Undo backups.'.format(len(result['changes']), source, target),
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel, QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
                return

            def sync(cancel, progress):
                """相対パスを維持し、各ファイルを共通処理で置換する。"""
                from qpeAdvancedIO import synchronize
                return synchronize(self.engine, result['changes'], cancel, progress)
            def retry(outcome):
                """失敗分だけを同じ同期基盤へ再投入する。"""
                from qpeAdvancedIO import synchronize
                self.run('Retry copying changes', lambda c, p: synchronize(self.engine, outcome['retry'], c, p), retry=retry)
            QtCore.QTimer.singleShot(0, lambda: self.run('Copy changes (one-way)', sync, retry=retry))
        self.run('Compare folders', lambda c, p: compareFolders(source, target, c), show)

    def shell(self, path, verb):
        """Windowsのプロパティ／アプリ選択をOSに任せる。"""
        if os.name != 'nt':
            self.report('Windows shell integration is only available on Windows.')
            return
        if verb == 'openas':
            subprocess.Popen(['rundll32.exe', 'shell32.dll,OpenAs_RunDLL', os.path.abspath(path)])
            return
        import ctypes
        from ctypes import wintypes

        class ExecuteInfo(ctypes.Structure):
            """ShellExecuteExW用の構造体。"""
            _fields_ = [('cbSize', wintypes.DWORD), ('fMask', ctypes.c_ulong), ('hwnd', wintypes.HWND),
                        ('lpVerb', wintypes.LPCWSTR), ('lpFile', wintypes.LPCWSTR), ('lpParameters', wintypes.LPCWSTR),
                        ('lpDirectory', wintypes.LPCWSTR), ('nShow', ctypes.c_int), ('hInstApp', wintypes.HINSTANCE),
                        ('lpIDList', ctypes.c_void_p), ('lpClass', wintypes.LPCWSTR), ('hkeyClass', wintypes.HKEY),
                        ('dwHotKey', wintypes.DWORD), ('hIcon', wintypes.HANDLE), ('hProcess', wintypes.HANDLE)]
        info = ExecuteInfo()
        info.cbSize, info.fMask, info.lpVerb, info.lpFile, info.nShow = ctypes.sizeof(info), 0xC, verb, os.path.abspath(path), 1
        if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
            self.report('Windows could not show the properties.')

    def configureExecutable(self, key):
        """外部ツールの実行ファイルを明示的に選ぶ。"""
        path, unused = QtWidgets.QFileDialog.getOpenFileName(self.explorer, 'Choose application', '', 'Executable (*.exe);;All files (*)')
        if path:
            writeSettings({key: path})



    def saveTabs(self):
        """現在の作業タブを名前付きセットとして保存する。"""
        self.workspace.productivity.saveSet()

    def saveReadPreset(self):
        """読込設定をシーン変更なしで保存する。"""
        name, ok = QtWidgets.QInputDialog.getText(self.explorer, 'Read settings preset', 'Name')
        if ok and name.strip():
            values = readSettings().get('readPresets', {})
            values[name.strip()] = self.explorer.readOptions.snapshot()
            writeSettings({'readPresets': values})

    def namespaces(self):
        """Maya内の既存ネームスペースをGUIスレッドで照会する。"""
        from maya import cmds
        names = cmds.namespaceInfo(':', listOnlyNamespaces=True, recurse=True) or []
        name, ok = QtWidgets.QInputDialog.getItem(self.explorer, 'Existing namespaces', 'Use for current read settings', names, 0, False)
        if ok:
            options = self.explorer.readOptions
            values = options.controls['import' if options.currentIndex() == 0 else 'reference']
            values['mode'].setCurrentIndex(1)
            values['name'].setText(name)

    def sidecar(self):
        """現在のシーン用メタデータとサムネイルを明示操作で保存する。"""
        from qpeSceneMetadata import saveCurrent
        try:
            self.report(saveCurrent(self.explorer))
        except (OSError, RuntimeError, ValueError) as error:
            self.report(str(error))

    def toggleSecond(self):
        """独立した場所を表示する任意の2番目の一覧を切り替える。"""
        if self.second is None:
            self.second = SecondPane(self)
            self.explorer.lower.addWidget(self.second)
            self.explorer.lower.setSizes([600, 400])
        else:
            self.second.setVisible(not self.second.isVisible())

    def eventFilter(self, watched, event):
        """編集欄に触れず、ファイル一覧の操作とドロップだけを処理する。"""
        e = self.explorer
        kind = event.type()
        if kind not in (QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride, QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove,
                        QtCore.QEvent.Drop, QtCore.QEvent.MouseButtonPress, QtCore.QEvent.MouseMove,
                        QtCore.QEvent.MouseButtonRelease) or not shiboken.isValid(e.files):
            return False
        view = e.files if watched in (e.files, e.files.viewport()) else self.views.get(watched)
        is_files = view is e.files
        paths = e.selectedPaths if is_files else lambda: [e.folderModel.filePath(view.currentIndex())] if view and view.currentIndex().isValid() else []
        if kind in (QtCore.QEvent.KeyPress, QtCore.QEvent.ShortcutOverride) and view and QtWidgets.QApplication.focusWidget() in (view, view.viewport()):
            key, modifiers = event.key(), event.modifiers()
            if modifiers == QtCore.Qt.ControlModifier:
                actions = {QtCore.Qt.Key_C: lambda: self.clipboard(paths()),
                           QtCore.Qt.Key_X: lambda: self.clipboard(paths(), True),
                           QtCore.Qt.Key_V: lambda: self.paste(e.currentDirectory),
                           QtCore.Qt.Key_Z: self.undo, QtCore.Qt.Key_F: self.search,
                           QtCore.Qt.Key_T: e.folderTabs.add,
                           QtCore.Qt.Key_W: lambda: e.folderTabs.close(e.folderTabs.active)}
                if key in actions:
                    # ホストのQActionより先に、この一覧が扱うキーだけを予約する。
                    # 操作自体はKeyPressで一度だけ実行し、編集欄には触れない。
                    if kind == QtCore.QEvent.ShortcutOverride:
                        event.accept()
                    else:
                        actions[key]()
                    return True
            if modifiers == (QtCore.Qt.ControlModifier | QtCore.Qt.ShiftModifier) and key in (
                    QtCore.Qt.Key_T, QtCore.Qt.Key_N):
                if kind == QtCore.QEvent.ShortcutOverride:
                    event.accept()
                else:
                    if key == QtCore.Qt.Key_N:
                        e.newFolder()
                    elif key == QtCore.Qt.Key_T:
                        e.folderTabs.reopen()
                return True
            if key == QtCore.Qt.Key_Delete and modifiers == QtCore.Qt.NoModifier:
                if kind == QtCore.QEvent.ShortcutOverride:
                    event.accept()
                else:
                    self.transfer('trash', paths())
                return True
        if kind in (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove):
            if event.mimeData().hasUrls():
                event.acceptProposedAction()
                return True
        if kind == QtCore.QEvent.Drop and event.mimeData().hasUrls():
            paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            if watched is e.places.viewport():
                for path in paths:
                    e.addFavoritePath(path)
            else:
                destination = e.currentDirectory
                if watched is e.folderTabs.bar:
                    index = e.folderTabs.bar.tabAt(event.pos())
                    if index >= 0 and index != e.folderTabs.active:
                        destination = e.folderTabs.states[index]['path']
                elif view and not is_files:
                    index = view.indexAt(event.pos())
                    destination = e.folderModel.filePath(index if index.isValid() else view.rootIndex())
                self.transfer('move' if event.keyboardModifiers() & QtCore.Qt.ShiftModifier else 'copy', paths, destination)
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            return True
        if view and watched is view.viewport():
            if kind == QtCore.QEvent.MouseButtonPress and event.button() == QtCore.Qt.LeftButton:
                self.dropStart = event.pos() if is_files or event.pos().x() < watched.width() - 8 else None
            elif kind == QtCore.QEvent.MouseMove and self.dropStart is not None and event.buttons() & QtCore.Qt.LeftButton:
                if (event.pos() - self.dropStart).manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                    self.dropStart = None
                    values = paths()
                    if values:
                        drag = QtGui.QDrag(view)
                        data = QtCore.QMimeData()
                        data.setUrls([QtCore.QUrl.fromLocalFile(p) for p in values])
                        drag.setMimeData(data)
                        drag.exec_(QtCore.Qt.CopyAction | QtCore.Qt.MoveAction, QtCore.Qt.CopyAction)
                        return True
            elif kind == QtCore.QEvent.MouseButtonRelease:
                self.dropStart = None
        return False


class SecondPane(QtWidgets.QWidget):
    """Qtの非同期ファイルモデルを使う独立したコピー先ビュー。"""

    def __init__(self, tools):
        """場所入力と一覧を作り、共通操作メニューへ接続する。"""
        super().__init__(tools.explorer.lower)
        self.tools = tools
        layout = QtWidgets.QVBoxLayout(self)
        self.address = QtWidgets.QLineEdit(tools.explorer.currentDirectory)
        layout.addWidget(self.address)
        self.model = QtWidgets.QFileSystemModel(self)
        self.model.setReadOnly(True)
        self.view = QtWidgets.QTreeView()
        self.view.setModel(self.model)
        self.view.setRootIsDecorated(False)
        self.view.setItemsExpandable(False)
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.view.setAlternatingRowColors(True)
        self.view.setSortingEnabled(True)
        self.view.setColumnWidth(0, 220)
        self.view.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self.menu)
        self.view.doubleClicked.connect(self.open)
        self.view.setDragEnabled(True)
        self.view.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self.view.viewport().setAcceptDrops(True)
        self.view.viewport().installEventFilter(self)
        layout.addWidget(self.view)
        up = QtWidgets.QPushButton('Parent folder')
        up.clicked.connect(lambda: self.navigate(str(Path(self.address.text()).parent)))
        layout.addWidget(up)
        self.address.returnPressed.connect(lambda: self.navigate(self.address.text()))
        self.navigate(self.address.text())

    def navigate(self, path):
        """有効な場所だけを表示する。"""
        if os.path.isdir(path):
            self.address.setText(os.path.abspath(path))
            self.view.setRootIndex(self.model.setRootPath(path))

    def open(self, index):
        """フォルダーを辿り、ファイルは既存ホストへ渡す。"""
        path = self.model.filePath(index)
        if self.model.isDir(index):
            self.navigate(path)
        else:
            self.tools.explorer.requestFiles('open', [path])

    def menu(self, point):
        """第2ペインの対象と貼付先を固定する。"""
        index = self.view.indexAt(point)
        selected = self.view.selectionModel().selectedRows(0)
        paths = [self.model.filePath(i) for i in selected] if index in selected else [self.model.filePath(index)] if index.isValid() else []
        menu = QtWidgets.QMenu(self)
        self.tools.addMenu(menu, paths, self.address.text())
        menu.exec_(self.view.viewport().mapToGlobal(point))

    def eventFilter(self, watched, event):
        """ドロップ先を第2ペインのディレクトリへ固定する。"""
        if event.type() in (QtCore.QEvent.DragEnter, QtCore.QEvent.DragMove) and event.mimeData().hasUrls():
            event.acceptProposedAction()
            return True
        if event.type() == QtCore.QEvent.Drop and event.mimeData().hasUrls():
            self.tools.transfer('move' if event.keyboardModifiers() & QtCore.Qt.ShiftModifier else 'copy',
                [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()], self.address.text())
            event.setDropAction(QtCore.Qt.CopyAction)
            event.accept()
            return True
        return False

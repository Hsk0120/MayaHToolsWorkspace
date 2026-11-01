"""世代付きスナップショットだけをGUIへ反映するディレクトリモデル。"""
import fnmatch
import os
import threading
import time
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets
from qpeFileIcons import FileIcons, folderIcon
import qpeNative

PATH = QtCore.Qt.UserRole + 1
DIRECTORY = QtCore.Qt.UserRole + 2
SORT_VALUE = QtCore.Qt.UserRole + 3


def normalized(path):
    """モデル内のパス表記を統一する。

    Args:
        path (str): 入力。

    Returns:
        str: 絶対パス。
    """
    return os.path.abspath(path).replace('\\', '/')


class ScanSignals(QtCore.QObject):
    """ワーカから値だけをGUIへ配送する。"""
    ready = QtCore.Signal(str, int, object, str)


class ScanJob(QtCore.QRunnable):
    """ファイルシステムの読込をGUIスレッドから分離する。"""

    def __init__(self, path, generation):
        """要求識別子を保持する。

        Args:
            path (str): ディレクトリ。
            generation (int): 要求世代。
        """
        super().__init__()
        self.path, self.generation = path, generation
        self.signals = ScanSignals()
        self.cancelled = threading.Event()
        self.showHidden = False
        self.directoriesOnly = False

    def run(self):
        """途中失敗も含め、一つの要求に一つのスナップショットを返す。"""
        entries, error = [], ''
        try:
            if self.cancelled.is_set():
                return
            with os.scandir(self.path) as iterator:
                for entry in iterator:
                    if self.cancelled.is_set():
                        break
                    try:
                        directory = entry.is_dir()
                        # 上段カラムはフォルダーだけ。大量ファイルのサイズ/時刻は調べない。
                        if self.directoriesOnly and not directory:
                            continue
                        info = entry.stat()
                        if not self.showHidden and (entry.name.startswith('.') or getattr(info, 'st_file_attributes', 0) & 2):
                            continue
                        entries.append((entry.name, directory, info.st_size, info.st_mtime))
                    except FileNotFoundError:
                        continue
        except OSError as exception:
            entries, error = [], str(exception)
        self.signals.ready.emit(self.path, self.generation, entries, error)


class DirectoryModel(QtGui.QStandardItemModel):
    """列挙結果を採用前に検証し、既存行の識別子を保って差分更新する。"""
    directoryLoaded = QtCore.Signal(str)
    directoryStateChanged = QtCore.Signal(str)
    snapshotAboutToApply = QtCore.Signal()
    snapshotApplied = QtCore.Signal()

    def __init__(self, parent=None, icons=None):
        """要求、監視、GUI所有の行を初期化する。

        Args:
            parent (QObject | None): 所有者。
            icons (FileIcons | None): 同一ウィンドウの表示領域で共有するGUI専用キャッシュ。
        """
        super().__init__(parent)
        self.setHorizontalHeaderLabels(['Name', 'Size', 'Extension', 'Date modified'])
        self._filter = QtCore.QDir.AllDirs
        self._names = []
        self._items = {}
        self._directoryItems = {}
        self._active = set()
        self._generations = {}
        self._serial = 0
        self._jobs = {}
        self._pendingMerges = {}
        self._mergeTimer = QtCore.QTimer(self)
        self._mergeTimer.setSingleShot(True)
        self._mergeTimer.timeout.connect(self._drainMerge)
        self._snapshots = {}
        self._appliedSnapshots = {}
        self.states = {}
        self.suspended = False
        self.traceSink = None
        self.jobFactory = ScanJob
        self.showHidden = False
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self.request)
        self._icons = icons if icons is not None else FileIcons()
        # Windowsのstyle.standardIconもShellを呼ぶため、行ごとに生成しない。
        self._placeholderIcon = QtWidgets.QApplication.style().standardIcon(QtWidgets.QStyle.SP_FileIcon)

    def setReadOnly(self, value):
        """既存UIと同じ入口を持ち、編集は常に専用操作へ委譲する。

        Args:
            value (bool): 互換引数。行は常に読み取り専用。
        """

    def setOption(self, option, value):
        """改名時はWindowsの監視ハンドルを解除する。

        Args:
            option (QFileSystemModel.Option): 既存UIの指定。
            value (bool): 有効か。
        """
        if option == QtWidgets.QFileSystemModel.DontWatchForChanges and value:
            self.suspend()

    def setFilter(self, value):
        """表示する項目の種類を設定する。

        Args:
            value (QDir.Filters): ディレクトリかファイル。
        """
        self._filter = value

    def filter(self):
        """表示対象の種類を返す。

        Returns:
            QDir.Filters: 現在の指定。
        """
        return self._filter

    def setNameFilterDisables(self, value):
        """一致しない項目は常に非表示とする。

        Args:
            value (bool): 既存UI互換引数。
        """

    def nameFilters(self):
        """ファイル形式フィルターを返す。

        Returns:
            list[str]: パターン。
        """
        return list(self._names)

    def setNameFilters(self, patterns):
        """保持した採用済みデータにフィルターを適用する。

        Args:
            patterns (list[str]): ワイルドカード。
        """
        self._names = list(patterns)
        for path in list(self._active):
            if path in self._snapshots:
                generation = self._generations.get(path)
                pending = self._pendingMerges.pop(generation, None)
                self._merge(path, self._snapshots[path])
                if pending is not None:
                    self._finishMerge(path, generation, pending[2])

    def filePath(self, index):
        """項目のパスを取得する。

        Args:
            index (QModelIndex): 項目。

        Returns:
            str: パス。
        """
        return str(index.sibling(index.row(), 0).data(PATH) or '') if index.isValid() else ''

    def fileName(self, index):
        """項目名を取得する。

        Args:
            index (QModelIndex): 項目。

        Returns:
            str: 表示名。
        """
        return str(index.sibling(index.row(), 0).data() or '')

    def isDir(self, index):
        """項目がディレクトリかを返す。

        Args:
            index (QModelIndex): 項目。

        Returns:
            bool: ディレクトリか。
        """
        return bool(index.sibling(index.row(), 0).data(DIRECTORY))

    def pathIndex(self, path):
        """パス索引を取得する。行索引はQt標準へ任せPythonの仮想呼出しを避ける。

        Args:
            path (str): 項目のパス。

        Returns:
            QModelIndex: 項目。
        """
        path = normalized(path)
        item = self._items.get(path)
        if item is None and os.path.exists(path):
            item = self._ensure(path, os.path.isdir(path))
        return item.index() if item is not None else QtCore.QModelIndex()

    def _ensure(self, path, directory=True, values=None):
        """パスの祖先と項目をGUIスレッドで作る。

        Args:
            path (str): 正規化済みパス。
            directory (bool): 項目種別。
            values (tuple | None): 新規行のサイズ・拡張子・更新時刻。

        Returns:
            QStandardItem: 保持する行。
        """
        if path in self._items:
            return self._items[path]
        parent_path = normalized(str(Path(path).parent))
        parent = self.invisibleRootItem() if parent_path == path else self._ensure(parent_path)
        item = QtGui.QStandardItem(Path(path).name or path)
        item.setData(item.text(), SORT_VALUE)
        item.setData(path, PATH)
        item.setData(directory, DIRECTORY)
        item.setEditable(False)
        if not directory:
            # フィルター解除時に全ファイルへhasChildrenを照会する必要はない。
            item.setFlags(item.flags() | QtCore.Qt.ItemNeverHasChildren)
        # 一覧構築ではShellへ入らず、可視行のアイコンだけ後から取得する。
        item.setIcon(folderIcon() if directory else self._placeholderIcon)
        columns = [item] + [QtGui.QStandardItem('') for unused in range(3)]
        if values is not None:
            # ビューへ接続する前に値を揃え、追加後の3回の変更通知/ソートを避ける。
            for column, value in enumerate(values, 1):
                self._setColumnValue(columns[column], column, value)
        name = item.text().lower()
        row, end = 0, parent.rowCount()
        if end and parent.child(end - 1).text().lower() <= name:
            row = end
        while row < end:
            middle = (row + end) // 2
            if parent.child(middle).text().lower() < name:
                row = middle + 1
            else:
                end = middle
        # 全体のlayoutChangedはQColumnViewの後続列を閉じる場合があるため、
        # 最初から名前順に挿入して既存行の選択・表示を保つ。
        parent.insertRow(row, columns)
        self._items[path] = item
        if directory:
            self._directoryItems[path] = item
        return item

    def _setColumnValue(self, item, column, value):
        """表示値は更新時だけ作り、数値/日時の並べ替えキーを別に保持する。"""
        if item.data(SORT_VALUE) == value:
            return
        item.setData(value, SORT_VALUE)
        display = QtCore.QLocale.system().formattedDataSize(value) if column == 1 else value
        item.setData(display, QtCore.Qt.DisplayRole)

    def refreshDirectoryVisibility(self, previous, current):
        """ファイルビューのルート変更で表示対象が変わるフォルダー行だけ通知する。"""
        if previous == current:
            return
        for path, item in self._directoryItems.items():
            parent = os.path.normcase(str(Path(path).parent)).replace('\\', '/').rstrip('/')
            if parent in (previous, current):
                index = item.index()
                self.dataChanged.emit(index, index, [DIRECTORY])

    def setRootPath(self, path):
        """表示するルートを取得する。要求開始はactivateが担当する。

        Args:
            path (str): 表示ルート。

        Returns:
            QModelIndex: ルート索引。
        """
        return self._ensure(normalized(path)).index()

    def activate(self, paths):
        """表示経路を更新し、以前の経路と要求世代を失効させる。

        Args:
            paths (list[str]): 表示するディレクトリ列。
        """
        self.suspended = False
        active = {normalized(path) for path in paths}
        for previous in self._active - active:
            # 前回の一覧に存在しなくても、表示中の経路として保護した行がある。
            # 経路を離れた後は同じ一覧でも再適用し、その保護行を削除する。
            parent = normalized(str(Path(previous).parent))
            snapshot = self._snapshots.get(parent)
            name = Path(previous).name
            if snapshot is not None and not any(entry[0] == name for entry in snapshot):
                self._appliedSnapshots.pop(parent, None)
        self._active = active
        for job in self._jobs.values():
            self._trace('invalidate', job.path, job.generation, False)
            if hasattr(job, 'cancelled'):
                job.cancelled.set()
        self._jobs.clear()
        self._generations.clear()
        self._pendingMerges.clear()
        self._mergeTimer.stop()
        watched = self._watcher.directories()
        if watched:
            self._watcher.removePaths(watched)
        valid = [p for p in self._active if os.path.isdir(p)]
        if valid:
            self._watcher.addPaths(valid)
        for path in sorted(self._active):
            self.request(path)

    def request(self, path):
        """同じパスでも必ず新しい要求番号を発行する。

        Args:
            path (str): 対象ディレクトリ。
        """
        path = normalized(path)
        if self.suspended or path not in self._active:
            return
        self._pendingMerges.pop(self._generations.get(path), None)
        previous = self._jobs.pop(self._generations.get(path), None)
        if previous is not None:
            self._trace('invalidate', previous.path, previous.generation, False)
            if hasattr(previous, 'cancelled'):
                previous.cancelled.set()
        self._serial += 1
        generation = self._serial
        self._generations[path] = generation
        self.states[path] = ('loading', '')
        job = self.jobFactory(path, generation)
        job.showHidden = self.showHidden
        job.directoriesOnly = bool(self._filter & QtCore.QDir.AllDirs)
        self._jobs[generation] = job
        job.signals.ready.connect(self.receive)
        self._trace('start', path, generation, True)
        self.directoryStateChanged.emit(path)
        QtCore.QThreadPool.globalInstance().start(job)

    def receive(self, path, generation, entries, error):
        """対象と世代を照合してから行に触れる。

        Args:
            path (str): 対象。
            generation (int): 要求番号。
            entries (list): 読み取った値。
            error (str): 失敗理由。
        """
        job = self._jobs.pop(generation, None)
        accepted = (job is not None and not self.suspended and path in self._active
                    and self._generations.get(path) == generation)
        self._trace('result', path, generation, accepted)
        if not accepted:
            return
        self._snapshots[path] = entries if not error else []
        entries = self._snapshots[path]
        signature = (tuple(entries), tuple(self._names), self._filter)
        if len(entries) >= 256 and self._appliedSnapshots.get(path) != signature:
            # 列挙は完了していても行の作成でGUIを占有しない。
            # 世代付きの小分け反映により、先頭を描画した後も移動・取消を受け付ける。
            self._pendingMerges[generation] = (path, self._mergeSteps(path, entries), error)
            if not self._mergeTimer.isActive():
                self._mergeTimer.start(0)
            return
        self._merge(path, entries)
        self._finishMerge(path, generation, error)

    def _finishMerge(self, path, generation, error):
        """最後の行まで反映した現行世代だけを完了として通知する。"""
        if self.suspended or self._generations.get(path) != generation or path not in self._active:
            return
        self.states[path] = ('error' if error else 'ready', error)
        self.directoryStateChanged.emit(path)
        self.directoryLoaded.emit(path)

    def hasCompleteSnapshot(self, path):
        """現在のフィルターで全件反映済みなら、再列挙を待たず表示状態を復元できる。"""
        entries = self._snapshots.get(path)
        return (entries is not None and self._appliedSnapshots.get(path)
                == (tuple(entries), tuple(self._names), self._filter))

    def _drainMerge(self):
        """1回最大512行/約12msでGUIへ制御を返し、複数カラムを順番に進める。"""
        if not self._pendingMerges:
            return
        generation = next(iter(self._pendingMerges))
        path, steps, error = self._pendingMerges.pop(generation)
        if not self.suspended and path in self._active and self._generations.get(path) == generation:
            complete = False
            self.snapshotAboutToApply.emit()
            try:
                deadline = time.perf_counter() + .012
                for unused in range(512):
                    try:
                        next(steps)
                    except StopIteration:
                        complete = True
                        break
                    if time.perf_counter() >= deadline:
                        break
            finally:
                self.snapshotApplied.emit()
            if complete:
                self._finishMerge(path, generation, error)
            elif self._generations.get(path) == generation and not self.suspended:
                self._pendingMerges[generation] = (path, steps, error)
        if self._pendingMerges:
            self._mergeTimer.start(1)

    def _merge(self, path, entries):
        """既存項目を維持し、削除・追加だけを行う。

        Args:
            path (str): 親。
            entries (list): 採用済みスナップショット。
        """
        if self._appliedSnapshots.get(path) == (tuple(entries), tuple(self._names), self._filter):
            return
        self.snapshotAboutToApply.emit()
        try:
            for unused in self._mergeSteps(path, entries):
                pass
        finally:
            self.snapshotApplied.emit()

    def _mergeSteps(self, path, entries):
        """整列済みの行を順次反映する。途中取消では完了キャッシュを確定しない。"""
        # 世代照合と再列挙は維持し、同じ結果での全行再設定だけ省く。
        # 検索形式や種別が変わった場合は同一ディレクトリでも再適用する。
        signature = (tuple(entries), tuple(self._names), self._filter)
        if self._appliedSnapshots.get(path) == signature:
            return
        parent = self._ensure(path)
        folders = bool(self._filter & QtCore.QDir.AllDirs)
        wanted = {normalized(path + '/' + name): (name, directory, size, modified)
                  for name, directory, size, modified in entries
                  if (directory if folders else not directory)
                  and (directory or not self._names or any(fnmatch.fnmatch(name.lower(), p.lower()) for p in self._names))}
        # ファイルモデルでも現在のルートへ至る祖先ノードは保持する。
        retained = {p for p in self._items if any(a == p or a.startswith(p.rstrip('/') + '/') for a in self._active)}
        for child_path, (name, directory, size, modified) in sorted(wanted.items(), key=lambda pair: pair[0].lower()):
            values = (size, 'Folder' if directory else Path(name).suffix,
                      QtCore.QDateTime.fromMSecsSinceEpoch(round(modified * 1000)))
            item = self._items.get(child_path)
            if item is None:
                self._ensure(child_path, directory, values)
            else:
                for column, value in enumerate(values, 1):
                    self._setColumnValue(parent.child(item.row(), column), column, value)
            yield
        for row in range(parent.rowCount() - 1, -1, -1):
            child_path = parent.child(row).data(PATH)
            if child_path not in wanted and child_path not in retained:
                for key in list(self._items):
                    if key == child_path or key.startswith(child_path.rstrip('/') + '/'):
                        self._items.pop(key, None)
                        self._directoryItems.pop(key, None)
                        self._appliedSnapshots.pop(key, None)
                        self._snapshots.pop(key, None)
                        self.states.pop(key, None)
                parent.removeRow(row)
                yield
        self._appliedSnapshots[path] = signature

    def suspend(self):
        """非表示・破棄・改名前に全要求を失効させる。"""
        self.suspended = True
        for job in self._jobs.values():
            self._trace('invalidate', job.path, job.generation, False)
            if hasattr(job, 'cancelled'):
                job.cancelled.set()
        self._jobs.clear()
        self._generations.clear()
        self._pendingMerges.clear()
        self._mergeTimer.stop()
        paths = self._watcher.directories()
        if paths:
            self._watcher.removePaths(paths)

    def _trace(self, operation, path, generation, accepted):
        """接続済みの検証先だけへ採否を通知する。

        Args:
            operation (str): 開始または完了。
            path (str): 対象。
            generation (int): 要求番号。
            accepted (bool): 採用可否。
        """
        if self.traceSink is not None:
            self.traceSink(dict(operation='directory-' + operation, model=self.objectName(),
                                path=path, generation=generation, accepted=accepted))

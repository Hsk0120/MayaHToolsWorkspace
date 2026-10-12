"""世代付きスナップショットだけをGUIへ反映するディレクトリモデル。"""
import fnmatch
import os
import threading
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets
from qpeFileIcons import FileIcons, folderIcon

PATH = QtCore.Qt.UserRole + 1
DIRECTORY = QtCore.Qt.UserRole + 2


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
                        info = entry.stat()
                        if entry.name.startswith('.') or getattr(info, 'st_file_attributes', 0) & 2:
                            continue
                        entries.append((entry.name, entry.is_dir(), info.st_size, info.st_mtime))
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

    def __init__(self, parent=None):
        """要求、監視、GUI所有の行を初期化する。

        Args:
            parent (QObject | None): 所有者。
        """
        super().__init__(parent)
        self.setHorizontalHeaderLabels(['Name', 'Size', 'Type', 'Date Modified'])
        self._filter = QtCore.QDir.AllDirs
        self._names = []
        self._items = {}
        self._active = set()
        self._generations = {}
        self._serial = 0
        self._jobs = {}
        self._snapshots = {}
        self.states = {}
        self.suspended = False
        self.traceSink = None
        self.jobFactory = ScanJob
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._watcher.directoryChanged.connect(self.request)
        self._icons = FileIcons()

    def data(self, index, role=QtCore.Qt.DisplayRole):
        """サイズの表示だけをQt標準形式へ変換し、編集値は数値で保持する。

        Args:
            index (QModelIndex): 項目。
            role (int): Qtの要求するデータ種別。

        Returns:
            object: Qt標準の単位付きサイズ、または保存された値。
        """
        value = super().data(index, role)
        if role == QtCore.Qt.DisplayRole and index.column() == 1 and isinstance(value, int):
            # QFileSystemModelと同様にOSのロケールを使う。
            # Mayaが既定ロケールの桁区切りを無効化していても標準一覧と一致させる。
            return QtCore.QLocale.system().formattedDataSize(value)
        return value

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
                self._merge(path, self._snapshots[path])

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

    def hasChildren(self, parent=QtCore.QModelIndex()):
        """読込前や空のディレクトリにも子カラムを用意する。

        Args:
            parent (QModelIndex): 親。

        Returns:
            bool: 子一覧を表示できるか。
        """
        return self.isDir(parent) if parent.isValid() else super().hasChildren(parent)

    def index(self, *args):
        """Qtの行索引と既存UIのパス索引を扱う。

        Args:
            *args: 行・列・親、またはパス。

        Returns:
            QModelIndex: 項目。
        """
        if args and isinstance(args[0], str):
            path = normalized(args[0])
            item = self._items.get(path)
            if item is None and os.path.exists(path):
                item = self._ensure(path, os.path.isdir(path))
            return item.index() if item is not None else QtCore.QModelIndex()
        return super().index(*args)

    def _ensure(self, path, directory=True):
        """パスの祖先と項目をGUIスレッドで作る。

        Args:
            path (str): 正規化済みパス。
            directory (bool): 項目種別。

        Returns:
            QStandardItem: 保持する行。
        """
        if path in self._items:
            return self._items[path]
        parent_path = normalized(str(Path(path).parent))
        parent = self.invisibleRootItem() if parent_path == path else self._ensure(parent_path)
        item = QtGui.QStandardItem(Path(path).name or path)
        item.setData(path, PATH)
        item.setData(directory, DIRECTORY)
        item.setEditable(False)
        item.setIcon(folderIcon() if directory else self._icons.icon(path))
        row, end = 0, parent.rowCount()
        while row < end:
            middle = (row + end) // 2
            if parent.child(middle).text().lower() < item.text().lower():
                row = middle + 1
            else:
                end = middle
        # 全体のlayoutChangedはQColumnViewの後続列を閉じる場合があるため、
        # 最初から名前順に挿入して既存行の選択・表示を保つ。
        parent.insertRow(row, [item] + [QtGui.QStandardItem('') for unused in range(3)])
        self._items[path] = item
        return item

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
        self._active = {normalized(path) for path in paths}
        for job in self._jobs.values():
            self._trace('invalidate', job.path, job.generation, False)
            if hasattr(job, 'cancelled'):
                job.cancelled.set()
        self._jobs.clear()
        self._generations.clear()
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
        self._merge(path, self._snapshots[path])
        self.states[path] = ('error' if error else 'ready', error)
        self.directoryStateChanged.emit(path)
        self.directoryLoaded.emit(path)

    def _merge(self, path, entries):
        """既存項目を維持し、削除・追加だけを行う。

        Args:
            path (str): 親。
            entries (list): 採用済みスナップショット。
        """
        parent = self._ensure(path)
        folders = bool(self._filter & QtCore.QDir.AllDirs)
        wanted = {normalized(path + '/' + name): (name, directory, size, modified)
                  for name, directory, size, modified in entries
                  if (directory if folders else not directory)
                  and (directory or not self._names or any(fnmatch.fnmatch(name.lower(), p.lower()) for p in self._names))}
        # ファイルモデルでも現在のルートへ至る祖先ノードは保持する。
        retained = {p for p in self._items if any(a == p or a.startswith(p.rstrip('/') + '/') for a in self._active)}
        self.snapshotAboutToApply.emit()
        try:
            for child_path, (name, directory, size, modified) in sorted(wanted.items(), key=lambda pair: pair[0].lower()):
                item = self._ensure(child_path, directory)
                for column, value in ((1, size), (2, 'Folder' if directory else Path(name).suffix),
                                      (3, QtCore.QDateTime.fromMSecsSinceEpoch(round(modified * 1000)))):
                    parent.child(item.row(), column).setData(value, QtCore.Qt.DisplayRole)
            for row in range(parent.rowCount() - 1, -1, -1):
                child_path = parent.child(row).data(PATH)
                if child_path not in wanted and child_path not in retained:
                    for key in list(self._items):
                        if key == child_path or key.startswith(child_path.rstrip('/') + '/'):
                            self._items.pop(key, None)
                    parent.removeRow(row)
        finally:
            self.snapshotApplied.emit()

    def suspend(self):
        """非表示・破棄・改名前に全要求を失効させる。"""
        self.suspended = True
        for job in self._jobs.values():
            self._trace('invalidate', job.path, job.generation, False)
            if hasattr(job, 'cancelled'):
                job.cancelled.set()
        self._jobs.clear()
        self._generations.clear()
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

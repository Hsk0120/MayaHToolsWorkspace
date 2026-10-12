"""パス候補、作業セット、ZIP閲覧を既存UIへ加える。"""
import copy
import os
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets, shiboken
from qpeSettings import readSettings, writeSettings


class Productivity(QtCore.QObject):
    """常設のボタンを増やさず、既存欄とToolsを拡張する。"""

    def __init__(self, workspace):
        """入力候補はワーカーから受け取り、古い候補は捨てる。"""
        super().__init__(workspace.e)
        self.w, self.e = workspace, workspace.e
        self.serial = 0
        self.task = None
        self.model = QtCore.QStringListModel(self)
        self.completer = QtWidgets.QCompleter(self.model, self)
        self.completer.setCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.completer.setCompletionMode(QtWidgets.QCompleter.UnfilteredPopupCompletion)
        self.e.address.setCompleter(self.completer)
        self.timer = QtCore.QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.complete)
        self.e.address.textEdited.connect(self.edited)
        self.e.address.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.e.address.customContextMenuRequested.connect(self.addressMenu)
        self.e.folderTabs.bar.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.e.folderTabs.bar.customContextMenuRequested.connect(self.tabMenu)

    def addressMenu(self, point):
        """標準の文字編集メニューに祖先と最近のパスを加える。"""
        menu = self.e.address.createStandardContextMenu()
        ancestors = menu.addMenu('Parent folders')
        for parent in Path(self.e.currentDirectory).parents:
            ancestors.addAction(str(parent), lambda checked=False, path=str(parent): self.e.navigate(path))
        recent = menu.addMenu('Recent paths')
        for path in reversed(readSettings().get('pathHistory', [])[-20:]):
            recent.addAction(path, lambda checked=False, p=path: self.e.navigate(p))
        menu.exec_(self.e.address.mapToGlobal(point))

    def edited(self, text):
        """変更した瞬間に前の候補を無効化する。"""
        self.serial += 1
        self.completer.popup().hide()
        self.timer.start(180)

    def complete(self):
        """パス履歴と子フォルダー候補をGUIスレッド外で作る。"""
        from qpeTools import launchTask
        serial, text = self.serial, self.e.address.text()
        history = readSettings().get('pathHistory', [])
        def find(cancel, progress):
            """部分入力が示す親だけを列挙し、候補数を制限する。"""
            value = os.path.expandvars(os.path.expanduser(text)).replace('\\', '/')
            folder, prefix = os.path.split(value)
            found = [p for p in reversed(history) if text.casefold() in p.casefold()][:30]
            if folder and os.path.isdir(folder):
                with os.scandir(folder) as entries:
                    for item in entries:
                        if cancel.is_set():
                            break
                        if item.name.casefold().startswith(prefix.casefold()) and item.is_dir():
                            found.append(item.path.replace('\\', '/'))
                        if len(found) >= 150:
                            break
            return list(dict.fromkeys(found))
        def ready(result, error):
            """フォーカスを奪わず、現在入力に対応する候補だけ表示する。"""
            if not shiboken.isValid(self.e) or serial != self.serial:
                return
            self.task = None
            self.model.setStringList(result or [])
            if result and self.e.address.hasFocus():
                self.completer.complete()
        if self.task:
            self.task.cancel.set()
        self.task = launchTask(find, ready)

    def navigated(self):
        """存在する移動先だけを件数制限付きで履歴へ追加する。"""
        self.serial += 1
        self.timer.stop()
        path = self.e.currentDirectory
        history = [p for p in readSettings().get('pathHistory', []) if p != path]
        writeSettings({'pathHistory': (history + [path])[-60:]})

    def tabMenu(self, point):
        """固定と場所ロックをタブの右クリックから変更する。"""
        tabs = self.e.folderTabs
        index = tabs.bar.tabAt(point)
        if index < 0:
            return
        menu = QtWidgets.QMenu(self.e)
        for key, title in [('pinned', 'Pin tab (prevent closing)'), ('locked', 'Lock location (navigate in new tab)')]:
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(bool((tabs.states[index] or {}).get(key)))
            action.toggled.connect(lambda checked, k=key: self.setTabFlag(index, k, checked))
        menu.exec_(tabs.bar.mapToGlobal(point))

    def setTabFlag(self, index, key, value):
        """タブ固有の属性をセッションへ保持する。"""
        tabs = self.e.folderTabs
        state = tabs.snapshot() if index == tabs.active else copy.deepcopy(tabs.states[index])
        state[key] = value
        tabs.states[index] = state
        tabs.saveSession()
        tabs.updateTabPresentation(index)

    def saveSet(self, name=None):
        """名前付きでタブ一式を保存する。既存セットは確認して置換する。"""
        if not isinstance(name, str):
            name, ok = QtWidgets.QInputDialog.getText(self.e, 'Save workspace', 'Workspace name')
            if not ok:
                return
        name = name.strip()
        if not name:
            return
        sets = readSettings().get('tabSets', {})
        if name in sets and QtWidgets.QMessageBox.question(self.e, 'Replace workspace', name,
                QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.Cancel) != QtWidgets.QMessageBox.Yes:
            return
        sets[name.strip()] = self.e.folderTabs.session()
        writeSettings({'tabSets': sets})

    def loadSet(self, name=None):
        """現在のセットを退避してから保存済みタブを復元する。"""
        sets = readSettings().get('tabSets', {})
        if not sets:
            self.w.tools.report('Save a workspace first.')
            return
        if not isinstance(name, str):
            name, ok = QtWidgets.QInputDialog.getItem(self.e, 'Load workspace', 'Workspace', sorted(sets), 0, False)
            if not ok:
                return
        if name in sets:
            writeSettings({'previousWorkspace': self.e.folderTabs.session()})
            self.e.folderTabs.restoreSession(sets[name])

    def deleteSet(self):
        """選んだ作業セットだけ削除する。"""
        sets = readSettings().get('tabSets', {})
        name, ok = QtWidgets.QInputDialog.getItem(self.e, 'Delete workspace', 'Workspace', sorted(sets), 0, False)
        if ok and name in sets:
            del sets[name]
            writeSettings({'tabSets': sets})


    def archive(self, path=None):
        """ZIPの内部一覧を開く。明示的な抽出まで書き込まない。"""
        path = path if isinstance(path, str) else self.e.selectedPath()
        if not path or Path(path).suffix.lower() != '.zip':
            self.w.tools.report('Select a ZIP file first.')
            return
        dialog = ArchiveDialog(path, self.w.tools)
        self.w.tools.dialogs.append(dialog)
        dialog.show()

    def diagnose(self, paths=None):
        """OS状態と使用中アプリを読み取って報告する。"""
        from qpeProductivityIO import diagnose
        paths = paths if isinstance(paths, list) else self.e.selectedPaths() or [self.e.currentDirectory]
        executable = readSettings().get('fileLocksmith', '')
        self.w.tools.run('Diagnose file usage / availability', lambda c, p: diagnose(paths, executable), self.w.tools.showText)

    def configureDiagnosis(self):
        """任意のFile Locksmith CLIを利用者が指定する。"""
        path, unused = QtWidgets.QFileDialog.getOpenFileName(self.e, 'PowerToys FileLocksmithCLI.exe', '', 'Executable (*.exe)')
        if path:
            writeSettings({'fileLocksmith': path})


class ArchiveDialog(QtWidgets.QDialog):
    """ZIP内のパスを一覧し、選んだ項目だけ新規場所へ抽出する。"""

    def __init__(self, path, tools):
        """アーカイブ列挙を非同期で実行する。"""
        super().__init__(tools.explorer)
        from qpeTools import launchTask
        from qpeProductivityIO import zipEntries
        self.path, self.tools = path, tools
        self.setWindowTitle('Browse ZIP — ' + Path(path).name)
        self.resize(850, 550)
        layout = QtWidgets.QVBoxLayout(self)
        self.table = QtWidgets.QTreeWidget()
        self.table.setHeaderLabels(['Path in ZIP', 'Size', 'Type'])
        self.table.setColumnWidth(0, 540)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        layout.addWidget(self.table)
        self.status = QtWidgets.QLabel('Reading archive…')
        layout.addWidget(self.status)
        self.extract = QtWidgets.QPushButton('Extract selected…')
        self.extract.setEnabled(False)
        self.extract.clicked.connect(self.extractItems)
        layout.addWidget(self.extract)
        def ready(result, error):
            """閉じた画面へ結果を配送しない。"""
            if not shiboken.isValid(self) or not self.isVisible():
                return
            if error:
                self.status.setText(error)
                return
            for entry in result:
                item = QtWidgets.QTreeWidgetItem([entry['name'], QtCore.QLocale.system().formattedDataSize(entry['size']),
                    'Folder' if entry['folder'] else 'Encrypted' if entry['encrypted'] else 'File'])
                self.table.addTopLevelItem(item)
            self.status.setText('{} entries — read-only browsing'.format(len(result)))
            self.extract.setEnabled(True)
        self.task = launchTask(lambda c, p: zipEntries(path), ready)

    def extractItems(self):
        """新規抽出フォルダーだけを作り、Undoへ登録する。"""
        from qpeProductivityIO import extractSelected
        names = [item.text(0) for item in self.table.selectedItems()]
        if not names:
            return
        target, ok = QtWidgets.QInputDialog.getText(self, 'Extract selected', 'New destination folder',
            text=str(Path(self.path).with_suffix('')) + '_selected')
        if ok and target:
            def extract(cancel, progress):
                """他のファイル操作と同じ排他を使う。"""
                with self.tools.engine.exclusive():
                    result = extractSelected(self.path, names, target, cancel)
                    self.tools.engine.recordCreation(result)
                    return result
            self.tools.run('Extract selected ZIP entries', extract)

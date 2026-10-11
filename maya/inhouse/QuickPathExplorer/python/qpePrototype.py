"""Qt部品をC++版と揃えたPython版ファイルブラウザー。"""
import sys
from pathlib import Path
from PySide6 import QtCore, QtGui, QtWidgets


class Explorer(QtWidgets.QWidget):
    """Qt親子所有で管理する読み取り中心の試作画面。"""

    def __init__(self, parent=None):
        """表示部品と非同期ファイルモデルを構築する。

        Args:
            parent (QWidget | None): Qt所有者。
        """
        super().__init__(parent)
        self.setObjectName('qpeExplorer')
        self.setWindowTitle('QuickPathExplorer — Python prototype')
        self.resize(1100, 600)
        layout = QtWidgets.QVBoxLayout(self)
        toolbar = QtWidgets.QHBoxLayout()
        up = QtWidgets.QPushButton('Up', self)
        home = QtWidgets.QPushButton('Home', self)
        self.address = QtWidgets.QLineEdit(self)
        self.address.setObjectName('address')
        self.filter = QtWidgets.QLineEdit(self)
        self.filter.setObjectName('filter')
        self.filter.setPlaceholderText('Filter: *.ma *.mb')
        self.filter.setMaximumWidth(220)
        toolbar.addWidget(up)
        toolbar.addWidget(home)
        toolbar.addWidget(self.address, 1)
        toolbar.addWidget(self.filter)
        layout.addLayout(toolbar)
        self.model = QtWidgets.QFileSystemModel(self)
        self.model.setObjectName('fileModel')
        self.model.setReadOnly(True)
        self.model.setOption(QtWidgets.QFileSystemModel.DontUseCustomDirectoryIcons, True)
        self.model.setFilter(QtCore.QDir.AllDirs | QtCore.QDir.Files | QtCore.QDir.NoDotAndDotDot)
        self.model.setNameFilterDisables(False)
        self.view = QtWidgets.QColumnView(self)
        self.view.setObjectName('columns')
        self.view.setModel(self.model)
        self.view.setColumnWidths([240, 240, 240, 240])
        self.view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        layout.addWidget(self.view, 1)
        self.info = QtWidgets.QLabel('Select a file or folder', self)
        self.info.setObjectName('info')
        self.info.setTextFormat(QtCore.Qt.PlainText)
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        open_button = QtWidgets.QPushButton('Open with default application', self)
        layout.addWidget(open_button)
        self.address.returnPressed.connect(self._navigateAddress)
        up.clicked.connect(self._up)
        home.clicked.connect(self._home)
        self.filter.textChanged.connect(self._filterChanged)
        self.view.selectionModel().currentChanged.connect(self._selectionChanged)
        open_button.clicked.connect(self._open)

    def _navigateAddress(self):
        """パス欄を使って移動する。"""
        self.navigate(self.address.text())

    def navigate(self, path):
        """フォルダーを表示する。無効パスでは元の表示を保持する。

        Args:
            path (str): 移動先。
        """
        if not QtCore.QFileInfo(path).isDir():
            self.info.setText('Folder not found: ' + path)
            return
        index = self.model.setRootPath(QtCore.QDir(path).absolutePath())
        self.view.setRootIndex(index)
        self.address.setText(self.model.filePath(index))

    def _up(self):
        """表示起点の親へ移動する。"""
        directory = QtCore.QDir(self.model.filePath(self.view.rootIndex()))
        directory.cdUp()
        self.navigate(directory.path())

    def _home(self):
        """ユーザーのホームを表示する。"""
        self.navigate(QtCore.QDir.homePath())

    def _filterChanged(self, text):
        """フォルダーを保持しながらファイルを絞る。

        Args:
            text (str): 空白区切りの名前パターン。
        """
        self.model.setNameFilters(text.split())

    def _selectionChanged(self, index, previous):
        """選択内容の情報を文字として表示する。

        Args:
            index (QModelIndex): 新しい選択。
            previous (QModelIndex): 前の選択。
        """
        file = self.model.fileInfo(index)
        self.info.setText(file.absoluteFilePath() + ('  [folder]' if file.isDir() else '  [{} bytes]'.format(file.size())))

    def _open(self):
        """明示的なボタン操作で関連付けアプリを開く。"""
        index = self.view.currentIndex()
        if index.isValid():
            QtGui.QDesktopServices.openUrl(QtCore.QUrl.fromLocalFile(self.model.filePath(index)))


def main():
    """Windows単体のアプリケーションを起動する。"""
    app = QtWidgets.QApplication(sys.argv)
    window = Explorer()
    window.show()

    def start():
        """イベントループ開始後にパス移動または計測を実行する。"""
        if len(sys.argv) == 5 and sys.argv[1] == '--bench':
            Path(sys.argv[4]).write_text('ready', encoding='utf-8')
            from qpeBenchmark import benchmark
            result = benchmark(window, sys.argv[2], sys.argv[3])
            app.exit(0 if result['passed'] else 1)
        else:
            window.navigate(sys.argv[1] if len(sys.argv) > 1 else QtCore.QDir.homePath())

    QtCore.QTimer.singleShot(0, start)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())

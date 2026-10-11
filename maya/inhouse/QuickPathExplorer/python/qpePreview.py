"""選択ファイルをUIスレッドの外でプレビューする。"""
from pathlib import Path
from qpeQt import QtCore, QtGui


class PreviewSignals(QtCore.QObject):
    """GUIスレッドへ読込結果を配送する。"""
    ready = QtCore.Signal(int, QtGui.QImage, str)


class PreviewJob(QtCore.QRunnable):
    """QPixmapやMaya APIを触らず、制限付きでファイルを読む。"""

    def __init__(self, serial, path):
        """要求を保持する。

        Args:
            serial (int): 要求番号。
            path (str): 対象パス。
        """
        super().__init__()
        self.serial = serial
        self.path = path
        self.signals = PreviewSignals()

    def run(self):
        """画像/テキストを読み、失敗も結果として配送する。"""
        image = QtGui.QImage()
        text = 'No preview for this file type'
        try:
            suffix = Path(self.path).suffix.lower()
            if suffix in ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff', '.webp'):
                reader = QtGui.QImageReader(self.path)
                size = reader.size()
                if size.isValid() and size.width() * size.height() <= 64000000:
                    reader.setAutoTransform(True)
                    reader.setScaledSize(size.scaled(720, 480, QtCore.Qt.KeepAspectRatio))
                    image = reader.read()
                    text = reader.errorString() if image.isNull() else ''
                else:
                    text = 'Preview skipped: image is too large or unsupported'
            elif suffix in ('.ma', '.txt', '.py', '.mel', '.json', '.md', '.csv'):
                with open(self.path, 'rb') as stream:
                    text = 'TEXT\n' + stream.read(16384).decode('utf-8', errors='replace')
        except OSError as error:
            text = str(error)
        self.signals.ready.emit(self.serial, image, text)

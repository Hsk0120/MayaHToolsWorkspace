"""拡張子を文字と色で区別する、DPIに対応したファイルアイコン。"""
import hashlib
from pathlib import Path
from qpeQt import QtCore, QtGui

# アプリケーションが明確な形式は同じ配色に揃える。
# FBXはAutodesk FBX Reviewの青緑系。関連付け先の変更や実行ファイルの読込は行わない。
APPLICATION_COLORS = {
    'ma': '#36a6c8', 'mb': '#36a6c8', 'mel': '#36a6c8',
    'fbx': '#159b9d',
    'blend': '#e87d0d',
    'psd': '#155a9e', 'psb': '#155a9e',
    'ai': '#c87508',
    'aep': '#6554c0', 'aepx': '#6554c0',
    'prproj': '#6554c0',
    'hip': '#df692a', 'hiplc': '#df692a', 'hipnc': '#df692a',
    'py': '#3776ab', 'pyw': '#3776ab',
}


class FileIcons:
    """拡張子ごとの描画をキャッシュし、ファイル数に比例する描画を避ける。"""

    def __init__(self):
        """GUIスレッドで使うアイコンキャッシュを初期化する。"""
        self._cache = {}

    def icon(self, path):
        """拡張子付きの書類アイコンを複数解像度で返す。

        Args:
            path (str): ファイルパス。ファイル自体は読み込まない。

        Returns:
            QIcon: 大小文字を区別せず共有するアイコン。
        """
        extension = Path(path).suffix.lstrip('.').lower()
        if extension in self._cache:
            return self._cache[extension]
        label = extension.upper() if extension else '—'
        if len(label) > 4:
            label = label[:3] + '…'
        hue = int(hashlib.sha256(extension.encode('utf-8')).hexdigest()[:4], 16) % 360
        color = (QtGui.QColor(APPLICATION_COLORS[extension]) if extension in APPLICATION_COLORS
                 else QtGui.QColor.fromHsv(hue, 145, 155))
        icon = QtGui.QIcon()
        for size in (16, 20, 24, 32, 40, 48, 64, 96):
            pixmap = QtGui.QPixmap(size, size)
            pixmap.fill(QtCore.Qt.transparent)
            painter = QtGui.QPainter(pixmap)
            painter.setRenderHint(QtGui.QPainter.Antialiasing)
            painter.scale(size / 32.0, size / 32.0)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor('#dce3ec'))
            painter.drawRoundedRect(QtCore.QRectF(5, 1, 22, 30), 3, 3)
            painter.setBrush(color)
            painter.drawRoundedRect(QtCore.QRectF(0, 12, 32, 16), 3, 3)
            font = QtGui.QFont('Segoe UI')
            font.setPixelSize(12 if len(label) <= 3 else 10)
            font.setBold(True)
            painter.setFont(font)
            painter.setPen(QtGui.QColor('white'))
            painter.drawText(QtCore.QRectF(0, 11, 32, 17), QtCore.Qt.AlignCenter, label)
            painter.end()
            icon.addPixmap(pixmap)
        self._cache[extension] = icon
        return icon

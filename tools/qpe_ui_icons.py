"""編集可能なSVGからQtで配布用PNGとICOを生成する。"""
import struct
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'maya/inhouse/QuickPathExplorer/python'))
from qpeQt import QtCore, QtGui, QtWidgets, QtSvg


def main():
    """同じSVGを各解像度でラスタライズする。"""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    folder = ROOT / 'maya/inhouse/QuickPathExplorer/icons'
    renderer = QtSvg.QSvgRenderer(str(folder / 'quickPathExplorer.svg'))
    frames = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        image = QtGui.QImage(size, size, QtGui.QImage.Format_ARGB32)
        image.fill(QtCore.Qt.transparent)
        painter = QtGui.QPainter(image)
        renderer.render(painter)
        painter.end()
        data = QtCore.QByteArray()
        buffer = QtCore.QBuffer(data)
        buffer.open(QtCore.QIODevice.WriteOnly)
        image.save(buffer, 'PNG')
        frames.append((size, bytes(data)))
        if size == 256:
            image.save(str(folder / 'quickPathExplorer.png'))
    offset = 6 + len(frames) * 16
    header = struct.pack('<HHH', 0, 1, len(frames))
    entries = b''
    for size, data in frames:
        entries += struct.pack('<BBBBHHII', size % 256, size % 256, 0, 0, 1, 32, len(data), offset)
        offset += len(data)
    (folder / 'quickPathExplorer.ico').write_bytes(header + entries + b''.join(data for size, data in frames))


if __name__ == '__main__':
    main()

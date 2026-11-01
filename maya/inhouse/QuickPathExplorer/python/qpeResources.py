"""プラグイン同梱素材と通常Python版の素材パスを共通化する。"""
import sys
from pathlib import Path, PurePosixPath
from qpeQt import QtCore


def iconDirectory():
    """実行方式に合う素材ディレクトリを返す。展開ファイルは作らない。"""
    if QtCore.QFile.exists(':/qpe/icons/quickPathExplorer.png'):
        return PurePosixPath(':/qpe/icons')
    return (Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]) / 'icons'

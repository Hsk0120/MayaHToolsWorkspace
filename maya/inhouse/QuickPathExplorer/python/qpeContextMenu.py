"""閉じるためのクリックを背後の一覧へ渡さないメニュー。"""
from qpeQt import QtCore, QtWidgets


class ContextMenu(QtWidgets.QMenu):
    """Qtのポップアップ配送を利用し、外側の押下だけを消費する。"""

    def mousePressEvent(self, event):
        """外側クリックは閉じる操作として処理する。

        Args:
            event (QMouseEvent): メニューが受け取った押下。
        """
        if not self.rect().contains(event.pos()):
            self.setAttribute(QtCore.Qt.WA_NoMouseReplay)
            self.close()
            event.accept()
            return
        super().mousePressEvent(event)

"""一覧の位置を保ったまま名前を編集する小さな入力部品。"""
from qpeQt import QtCore, QtWidgets


class InlineRename(QtWidgets.QLineEdit):
    """Enterまたはフォーカス移動で確定し、Escapeで中止する。"""
    committed = QtCore.Signal(str)

    def __init__(self, parent, name, stem_length):
        """拡張子を残して名前部分を選択する。

        Args:
            parent (QWidget): 一覧のviewport。
            name (str): 現在の名前。
            stem_length (int): 最初に選択する文字数。
        """
        super().__init__(parent)
        self.setObjectName('inlineRename')
        self._finished = False
        self._composing = False
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setText(name)
        self.setSelection(0, stem_length)

    def finish(self, commit):
        """一度だけ編集を終了する。

        Args:
            commit (bool): 名前変更を要求するか。
        """
        if self._finished:
            return
        self._finished = True
        value = self.text()
        self.close()
        if commit:
            self.committed.emit(value)

    def keyPressEvent(self, event):
        """確定とキャンセルを一覧のショートカットより先に処理する。

        Args:
            event (QKeyEvent): キー入力。
        """
        if self._composing:
            super().keyPressEvent(event)
            return
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter, QtCore.Qt.Key_Escape):
            self.finish(event.key() != QtCore.Qt.Key_Escape)
        else:
            super().keyPressEvent(event)

    def inputMethodEvent(self, event):
        """IME変換中のEnterやEscapeでリネームを終了させない。

        Args:
            event (QInputMethodEvent): 変換文字列と確定文字列。
        """
        self._composing = bool(event.preeditString())
        super().inputMethodEvent(event)

    def event(self, event):
        """編集中は親ビューの名前変更ショートカットを遮断する。

        Args:
            event (QEvent): 入力通知。

        Returns:
            bool: Qtのイベント処理結果。
        """
        if event.type() == QtCore.QEvent.ShortcutOverride:
            event.accept()
            return True
        return super().event(event)

    def focusOutEvent(self, event):
        """別の場所へ移動した場合も入力を確定する。

        Args:
            event (QFocusEvent): フォーカス変更。
        """
        super().focusOutEvent(event)
        self.finish(True)

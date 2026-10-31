"""閉じるためのクリックを背後の一覧へ渡さないメニュー。"""
from qpeQt import QtCore, QtGui, QtWidgets


class ContextMenu(QtWidgets.QMenu):
    """Qtのポップアップ配送を利用し、外側の押下だけを消費する。"""

    def organize(self):
        """固定対象を持つ既存アクションを、頻度別のグループへ移す。

        コールバックを作り直さず、右クリック開始時の対象と有効条件を保つ。
        ショートカットはこのポップアップ内だけで有効にする。
        """
        groups = {
            'New': ('New Folder…', 'New Text File…', 'Save Scene As…'),
            'Organize': ('Add Favorite', 'Add to Favorites', 'Create Copy', 'Batch Rename…',
                         'Tags / rating / collection…', 'Undo file operation'),
            'Advanced': ('Create ZIP…', 'Extract ZIP…', 'Browse ZIP…', 'SHA-256',
                         'Scene information / dependencies', 'Diagnose usage / availability…',
                         'Calculate size / count…'),
            'Navigation / view': ('Set as start folder', 'Address bar…', 'Back', 'Forward', 'Up',
                                  'Current Project', 'Current Scene Folder', 'Display Settings…',
                                  'Open in File Explorer', 'Show Folder in Explorer'),
        }
        actions = list(self.actions())
        by_name = {action.text(): action for action in actions if not action.isSeparator()}
        for action in actions:
            self.removeAction(action)
        primary = ('Open', 'Open in new tab', 'Import', 'Reference', 'Open with…')
        editing = ('Cut', 'Copy', 'Paste', 'Rename…', 'Delete', 'Copy Path')
        for names in (primary, editing):
            for name in names:
                if name in by_name:
                    self.addAction(by_name.pop(name))
            if self.actions() and not self.actions()[-1].isSeparator():
                self.addSeparator()
        for title, names in groups.items():
            items = [by_name.pop(name) for name in names if name in by_name]
            if items:
                submenu = self.addMenu(title)
                for action in items:
                    submenu.addAction(action)
        self.addSeparator()
        for action in by_name.values():
            if action.text() in ('Information', 'This Folder Information'):
                action.setText('Show paths…')
            self.addAction(action)
        shortcuts = {'Cut': 'Ctrl+X', 'Copy': 'Ctrl+C', 'Paste': 'Ctrl+V',
                     'Rename…': 'F2', 'Delete': 'Delete'}
        for action in actions:
            if action.text() in shortcuts:
                action.setShortcut(QtGui.QKeySequence(shortcuts[action.text()]))
                action.setShortcutContext(QtCore.Qt.WidgetShortcut)

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

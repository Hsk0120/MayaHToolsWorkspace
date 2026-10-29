"""Windowsのアプリ配色とMaya用配色をQPE内だけへ適用する。"""
from pathlib import Path
from qpeQt import QtCore, QtGui, QtWidgets
from qpeSettings import readSettings, writeSettings


def windowsColors():
    """Windowsの明暗とアクセントを読み、取得不可なら標準の白と青を返す。

    Returns:
        tuple: ライト表示かどうかとアクセント色。
    """
    light, accent = True, '#0078d4'
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize') as key:
            light = bool(winreg.QueryValueEx(key, 'AppsUseLightTheme')[0])
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\DWM') as key:
            accent = '#{:06x}'.format(winreg.QueryValueEx(key, 'ColorizationColor')[0] & 0xffffff)
    except (ImportError, OSError):
        pass
    return light, accent


class Theme(QtCore.QObject):
    """寸法・選択・フォーカスを変更せず、子ウィジェットへ配色を継承する。"""

    def __init__(self, widget):
        """ホスト別の初期色とWindows設定の変更監視を用意する。

        Args:
            widget (Explorer): 配色対象。
        """
        super().__init__(widget)
        self.widget = widget
        self.mode = readSettings().get('standaloneTheme', 'light')
        if self.mode not in ('system', 'light', 'dark', 'finder'):
            self.mode = 'system'
        self.signature = None
        self.refresh()
        if not widget._maya:
            self.timer = QtCore.QTimer(self)
            self.timer.setInterval(2000)
            self.timer.timeout.connect(self.refresh)
            self.timer.start()

    def refresh(self):
        """変更がある時だけ配色を更新し、Mayaのグローバル設定は保持する。"""
        signature = (False, '#326c7b') if self.widget._maya else windowsColors()
        if not self.widget._maya and self.mode != 'system':
            signature = (self.mode in ('light', 'finder'), '#0a64d8' if self.mode == 'finder' else signature[1])
        if signature == self.signature:
            return
        self.signature = signature
        self.light, accent = signature
        self.colors = (dict(window='#f3f3f3', base='#ffffff', alternate='#f7f8fa',
                            text='#202020', border='#d8d8d8', muted='#737373',
                            inactive='#e5edf5', folder='#667c8c', bar='#eeeeee') if self.light else
                       dict(window='#303030', base='#2b2b2b', alternate='#333638',
                            text='#e4e7eb', border='#484848', muted='#999999',
                            inactive='#50565b', folder='#90b8c5', bar='#30363a'))
        if self.mode == 'finder' and not self.widget._maya:
            # Finderを参考にした不透明な近似色。macOSの材質・実測値ではない。
            self.colors.update(window='#e9e9eb', base='#ffffff', alternate='#f1f1f3',
                               text='#262626', border='#cccccf', muted='#6b6b70',
                               inactive='#dcdce0', folder='#66717a', bar='#e2e2e5')
        # 撮影したWindows Explorer詳細ペインの主要な面色へ合わせる。
        windows_theme = not self.widget._maya and self.mode != 'finder'
        if windows_theme:
            self.colors.update(
                dict(window='#f9f9f9', base='#ffffff', alternate='#fafafa',
                     text='#1a1a1a', border='#e5e5e5', muted='#707070',
                     inactive='#e5e5e5', bar='#f9f9f9') if self.light else
                dict(window='#222222', base='#191919', alternate='#1d1d1d',
                     text='#f2f2f2', border='#383838', muted='#a6a6a6',
                     inactive='#383838', bar='#222222'))
        self.colors['accent'] = accent
        rgb = QtGui.QColor(accent)
        # アクセントが明るくても選択文字を判読できる色を選ぶ。
        self.colors['selectedText'] = '#202020' if rgb.lightnessF() > 0.6 else '#ffffff'
        self.colors['selection'] = ('#d9d9d9' if self.light else '#505050') if windows_theme else accent
        if windows_theme:
            self.colors['selectedText'] = self.colors['text']
        palette = QtGui.QPalette(self.widget.palette())
        for role, key in [('Window', 'window'), ('WindowText', 'text'), ('Base', 'base'),
                          ('AlternateBase', 'alternate'), ('Text', 'text'), ('Button', 'window'),
                          ('ButtonText', 'text'), ('ToolTipBase', 'base'), ('ToolTipText', 'text'),
                          ('Highlight', 'selection'), ('HighlightedText', 'selectedText')]:
            palette.setColor(getattr(QtGui.QPalette, role), QtGui.QColor(self.colors[key]))
        for role in (QtGui.QPalette.Text, QtGui.QPalette.ButtonText, QtGui.QPalette.WindowText):
            palette.setColor(QtGui.QPalette.Disabled, role, QtGui.QColor(self.colors['muted']))
        self.widget.setPalette(palette)
        self.widget.setAutoFillBackground(True)
        self.updateIcons()
        if hasattr(self.widget, 'appearance'):
            self.widget.appearance.applyStyle()
        if hasattr(self.widget, 'interaction'):
            self.widget.interaction.updateFocus()

    def setMode(self, mode):
        """Windows配色の追従または固定表示を保存する。

        Args:
            mode (str): system、light、dark、finderのいずれか。
        """
        if mode not in ('system', 'light', 'dark', 'finder') or self.widget._maya:
            return
        self.mode = mode
        self.signature = None
        if not writeSettings({'standaloneTheme': mode}):
            self.widget.status.setText('Display settings could not be saved.')
            self.widget.status.show()
        self.refresh()

    def updateIcons(self):
        """操作アイコンだけを文字色へ着色し、拡張子のブランド色は維持する。"""
        import sys
        folder = (Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]) / 'icons'
        for name in ('sidebar', 'back', 'forward', 'inspector'):
            source = QtGui.QIcon(str(folder / (name + '.svg')))
            icon = QtGui.QIcon()
            for size in (20, 40, 60):
                pixmap = source.pixmap(size, size)
                painter = QtGui.QPainter(pixmap)
                painter.setCompositionMode(QtGui.QPainter.CompositionMode_SourceIn)
                painter.fillRect(pixmap.rect(), QtGui.QColor(self.colors['text']))
                painter.end()
                icon.addPixmap(pixmap)
            getattr(self.widget, name + 'Button').setIcon(icon)

    def style(self):
        """配色だけのスタイルを返す。

        Returns:
            str: QPEに限定して使用するQtスタイル。
        """
        style = '''
            QWidget { color: %(text)s; background-color: %(window)s; }
            QColumnView { background: %(base)s; border: none; }
            QPushButton, QToolButton { background: %(window)s; color: %(text)s;
                border: 1px solid %(border)s; border-radius: 3px; }
            QPushButton:hover, QToolButton:hover { background: %(inactive)s; }
            QPushButton:pressed, QToolButton:checked { background: %(accent)s; color: %(selectedText)s; }
            QGroupBox, QTabWidget::pane { background: %(window)s; border: 1px solid %(border)s; }
            QTreeView, QListView, QPlainTextEdit, QTextEdit, QLineEdit, QComboBox {
                background-color: %(base)s; color: %(text)s;
                alternate-background-color: %(alternate)s;
                selection-background-color: %(selection)s; selection-color: %(selectedText)s;
            }
            QColumnView QListView { border: none; border-right: 1px solid %(border)s; }
            QTabBar::tab { padding: 7px 14px; border: none; border-right: 1px solid %(border)s; }
            QTabWidget#operationTabs > QTabBar::tab { padding: 7px 8px; }
            QPushButton[primaryAction="true"] { border: 1px solid %(accent)s; }
            QTabBar::tab:selected { background: %(base)s; border-bottom: 2px solid %(accent)s; }
            QLabel#fileFooter { border-top: 1px solid %(border)s; padding: 5px 3px; color: %(muted)s; }
            QHeaderView::section, QTabBar::tab { background: %(window)s; color: %(text)s; }
            QMenu { background: %(base)s; color: %(text)s; border: 1px solid %(border)s; }
            QMenu::item:selected { background: %(accent)s; color: %(selectedText)s; }
            QMenu::item:disabled, QPushButton:disabled, QToolButton:disabled { color: %(muted)s; }
        ''' % self.colors

        if not self.widget._maya and self.mode != 'finder':
            style += '''
                QWidget#inspectorPanel, QWidget#inspectorPanel QWidget { background: %(base)s; }
                QWidget#inspectorPanel { border-left: 1px solid %(border)s; }
                QWidget#inspectorPanel QLabel#preview, QWidget#inspectorPanel QPlainTextEdit#textPreview, QWidget#inspectorPanel QPlainTextEdit#textPreview QWidget { background: %(window)s; border: none; }
                QTreeView::item:selected { background: %(selection)s; color: %(selectedText)s; }
                QToolButton { background: transparent; border: 1px solid transparent; }
                QToolButton:hover, QToolButton:checked { background: %(inactive)s; color: %(text)s; }
                QHeaderView::section { background: %(base)s; color: %(muted)s;
                    border: none; border-bottom: 1px solid %(border)s; }
                QLineEdit, QComboBox { border: 1px solid %(border)s; border-radius: 4px; }
                QLineEdit:focus { border: 1px solid %(accent)s; }
                QWidget#inspectorPanel QPushButton { background: %(window)s; }
                QWidget#inspectorPanel QPushButton:hover { background: %(inactive)s; }
            ''' % self.colors
        if self.mode == 'finder' and not self.widget._maya:
            style += """
                QTreeWidget#places { background: #e5e5e8; alternate-background-color: #e5e5e8;
                    border: none; border-right: 1px solid #cccccf; }
                QToolButton { background: transparent; border: 1px solid transparent; }
                QToolButton:hover, QToolButton:checked { background: #d5d5d9; color: #262626; }
                QLineEdit, QComboBox { border: 1px solid #c5c5ca; border-radius: 4px; }
                QLineEdit:focus { border: 1px solid #0a64d8; }
                QHeaderView::section { background: #ededee; border: none;
                    border-bottom: 1px solid #cccccf; color: #57575c; }
                QTreeView::item:selected { background: #0a64d8; color: white; }
            """
        return style

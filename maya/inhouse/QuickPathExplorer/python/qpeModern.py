"""QPE内の表示規則と段階的な表示設定。ホスト全体は変更しない。"""
from qpeQt import QtCore, QtGui, QtWidgets
from pathlib import Path
import sys


class SummaryLabel(QtWidgets.QLabel):
    """場所名が長くてもツールバーを押し広げず、件数を末尾に残す。"""

    def paintEvent(self, event):
        """保持テキストを変えず、描画時だけ中央を省略する。"""
        painter = QtGui.QPainter(self)
        painter.setPen(self.palette().color(QtGui.QPalette.WindowText))
        painter.setFont(self.font())
        rect = self.contentsRect().adjusted(8, 0, -8, 0)
        text = self.fontMetrics().elidedText(self.text(), QtCore.Qt.ElideMiddle, max(0, rect.width()))
        painter.drawText(rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, text)
        painter.end()


def style(colors, px, font_size):
    """意味別の色とDPI適用済み寸法で、全子画面の部品を揃える。

    Args:
        colors (dict): 現在のホスト配色。
        px (callable): ホストとユーザー倍率を一度適用する関数。
        font_size (int): 表示文字サイズ。

    Returns:
        str: QPEだけに適用するQtスタイル。
    """
    values = dict(colors)
    folder = (Path(sys._MEIPASS) if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]) / 'icons'
    values['chevron'] = (folder / ('chevron-dark.svg' if QtGui.QColor(colors['base']).lightness() > 128 else 'chevron-light.svg')).as_posix()
    values.update(radius=px(5), gap=px(4), inset=px(8), row=px(4),
                  small=max(px(11), font_size - px(1)), scroll=px(12), rail=px(3),
                  minimum=px(28), icon=px(16), arrow_width=px(12), arrow_height=px(8), drop=px(24))
    return '''
        QToolButton { background: transparent; border: 1px solid transparent;
            border-radius: %(radius)spx; padding: %(gap)spx; }
        QPushButton { background: %(window)s; border: 1px solid %(border)s;
            border-radius: %(radius)spx; padding: %(gap)spx %(inset)spx; }
        QToolButton:hover, QPushButton:hover { background: %(inactive)s; }
        QToolButton:checked, QPushButton:checked { background: %(inactive)s; color: %(text)s;
            border-color: %(border)s; }
        QToolButton:pressed, QPushButton:pressed { background: %(selection)s; color: %(selectedText)s; }
        QToolButton:focus, QPushButton:focus, QComboBox:focus, QLineEdit:focus {
            border: 1px solid %(accent)s; }
        QLineEdit, QComboBox, QSpinBox { border: 1px solid %(border)s;
            border-radius: %(radius)spx; padding: %(gap)spx %(inset)spx; background: %(base)s; }
        QComboBox { padding-right: %(drop)spx; }
        QComboBox::drop-down { border: none; width: %(drop)spx; }
        QComboBox::down-arrow { image: url("%(chevron)s"); width: %(arrow_width)spx; height: %(arrow_height)spx; }
        QToolButton::menu-indicator { image: url("%(chevron)s"); width: %(inset)spx; height: %(gap)spx; }
        QTreeView, QListView, QPlainTextEdit { border: none; }
        QColumnView QListView { border-right: 1px solid %(border)s; }
        QTreeWidget#places { background: %(window)s; border: none; border-right: 1px solid %(border)s; }
        QTreeView::item:hover, QListView::item:hover { background: %(inactive)s; }
        QTreeView::item:selected, QListView::item:selected { background: %(selection)s; color: %(selectedText)s; }
        QHeaderView::section { background: %(base)s; color: %(muted)s;
            border: none; border-bottom: 1px solid %(border)s; padding: %(row)spx %(inset)spx; }
        QSplitter::handle { background: %(border)s; }
        QSplitter::handle:hover { background: %(accent)s; }
        QWidget#inspectorPanel { background: %(base)s; border-left: 1px solid %(border)s; }
        QLabel#sectionHeading, QLabel#folderSummary, QLabel#fileTitle { font-weight: 600; }
        QLabel#readTarget, QLabel#fileFooter { color: %(muted)s; font-size: %(small)spx; }
        QLabel#preview { border: none; background: %(base)s; border-radius: %(radius)spx; }
        QTabWidget::pane { border: none; }
        QTabBar::tab { border: none; padding: %(inset)spx; }
        QTabBar::tab:selected { background: %(base)s; border-bottom: 2px solid %(accent)s; }
        QGroupBox { border: 1px solid %(border)s; border-radius: %(radius)spx;
            margin-top: %(inset)spx; padding-top: %(inset)spx; }
        QFrame#viewOptions { background: %(window)s; border: 1px solid %(border)s;
            border-radius: %(radius)spx; }
        QToolButton[filterChip="true"] { background: %(inactive)s; padding: %(gap)spx %(inset)spx; }
        QMenu { padding: %(gap)spx; border: 1px solid %(border)s; }
        QMenu::item { padding: %(gap)spx %(minimum)spx %(gap)spx %(inset)spx; }
        QScrollBar:vertical { background: transparent; width: %(scroll)spx; margin: 0; }
        QScrollBar:horizontal { background: transparent; height: %(scroll)spx; margin: 0; }
        QScrollBar::handle:vertical { background: %(muted)s; border: %(rail)spx solid %(base)s;
            border-radius: %(radius)spx; min-height: %(minimum)spx; }
        QScrollBar::handle:horizontal { background: %(muted)s; border: %(rail)spx solid %(base)s;
            border-radius: %(radius)spx; min-width: %(minimum)spx; }
        QScrollBar::handle:hover { background: %(text)s; }
        QScrollBar::handle:pressed { background: %(accent)s; }
    ''' % values


class ModernLayout(QtCore.QObject):
    """既存の表示設定を再利用し、適用中の条件だけを常設する。"""

    def __init__(self, explorer):
        """設定の所有者をQPEに限定し、外側クリックとEscapeで閉じる。"""
        super().__init__(explorer)
        self.e = explorer
        self.w = explorer.organizer.workspace
        self.button = QtWidgets.QToolButton(explorer)
        self.button.setObjectName('viewOptionsButton')
        self.button.setToolTip('View: layout, grouping, tags and columns')
        self.button.setAccessibleName('View options')
        explorer.fileToolbar.addWidget(self.button)
        self.popup = QtWidgets.QFrame(explorer, QtCore.Qt.Popup)
        self.popup.setObjectName('viewOptions')
        form = QtWidgets.QFormLayout(self.popup)
        form.setContentsMargins(12, 12, 12, 12)
        form.setSpacing(8)
        form.setFieldGrowthPolicy(QtWidgets.QFormLayout.AllNonFixedFieldsGrow)
        row = self.w.bar.layout()
        columns_button = row.itemAt(4).widget()
        for label, widget in [('Layout', self.w.mode), ('Scope', self.w.flat),
                              ('Group by', self.w.group), ('Filter tag', self.w.labelFilter),
                              ('Details', columns_button)]:
            row.removeWidget(widget)
            form.addRow(label, widget)
        self.chips = []
        panel_layout = self.w.bar.parentWidget().layout()
        bar_index = panel_layout.indexOf(self.w.bar)
        panel_layout.removeWidget(self.w.bar)
        self.chipScroll = QtWidgets.QScrollArea(explorer)
        self.chipScroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.chipScroll.setWidgetResizable(True)
        self.chipScroll.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        self.chipScroll.setWidget(self.w.bar)
        panel_layout.insertWidget(bar_index, self.chipScroll)
        for control, reset in [(explorer.search, explorer.search.clear),
                               (explorer.fileFilter, lambda: explorer.fileFilter.setCurrentIndex(0)),
                               (self.w.flat, lambda: self.w.flat.setChecked(False)),
                               (self.w.group, lambda: self.w.group.setCurrentIndex(0)),
                               (self.w.labelFilter, lambda: self.w.labelFilter.setCurrentIndex(0))]:
            chip = QtWidgets.QToolButton(self.w.bar)
            chip.setProperty('filterChip', True)
            chip.clicked.connect(reset)
            row.insertWidget(len(self.chips), chip)
            self.chips.append((control, chip))
        self.button.clicked.connect(self.showOptions)
        explorer.search.textChanged.connect(self.refresh)
        explorer.fileFilter.currentIndexChanged.connect(self.refresh)
        self.w.flat.toggled.connect(self.refresh)
        self.w.mode.currentIndexChanged.connect(self.refresh)
        self.w.group.currentIndexChanged.connect(self.refresh)
        self.w.labelFilter.currentIndexChanged.connect(self.refresh)
        self.refresh()
        self.applyMetrics()

    def applyMetrics(self):
        """後から生成した設定・拡張一覧も、同じ行高と倍率へ合わせる。"""
        scale = self.e.appearance.dpiScale * self.e.appearance.uiPercent / 100.0
        px = lambda value: max(1, round(value * scale))
        self.popup.layout().setContentsMargins(px(12), px(12), px(12), px(12))
        self.popup.layout().setSpacing(px(8))
        self.w.bar.layout().setSpacing(px(4))
        self.button.setMinimumHeight(px(28))
        from qpeAppearance import BrowserItemDelegate
        self.w.tree.setProperty('qpeRowHeight', self.e.files.property('qpeRowHeight'))
        if not isinstance(self.w.tree.itemDelegate(), BrowserItemDelegate):
            self.w.tree.setItemDelegate(BrowserItemDelegate(self.w.tree))
        self.w.tree.doItemsLayout()

    def showOptions(self):
        """現在のボタン直下で開き、画面端では収まる位置へ補正する。"""
        self.popup.adjustSize()
        point = self.button.mapToGlobal(QtCore.QPoint(0, self.button.height()))
        screen = self.button.screen().availableGeometry()
        point.setX(max(screen.left(), min(point.x(), screen.right() - self.popup.width())))
        point.setY(max(screen.top(), min(point.y(), screen.bottom() - self.popup.height())))
        self.popup.move(point)
        self.popup.show()
        self.w.mode.setFocus(QtCore.Qt.PopupFocusReason)

    def refresh(self, *unused):
        """適用中条件を省略表示し、全文と解除操作をツールチップで伝える。"""
        self.button.setText('View · ' + self.w.mode.currentText())
        visible = False
        for control, chip in self.chips:
            if isinstance(control, QtWidgets.QLineEdit):
                text = control.text()
            elif isinstance(control, QtWidgets.QCheckBox):
                text = control.text() if control.isChecked() else ''
            else:
                text = control.currentText() if control.currentIndex() > 0 else ''
            chip.setVisible(bool(text))
            chip.setText((text[:16] + '…' if len(text) > 17 else text) + '  ×')
            chip.setToolTip('Clear: ' + text)
            chip.setAccessibleName('Clear filter: ' + text)
            visible = visible or bool(text)
        self.w.bar.setVisible(visible)
        self.chipScroll.setVisible(visible)
        scale = self.e.appearance.dpiScale * self.e.appearance.uiPercent / 100.0
        self.chipScroll.setFixedHeight(max(round(44 * scale), self.w.bar.sizeHint().height() + round(12 * scale)))

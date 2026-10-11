"""ホストのDPIとユーザー指定を分けて扱う表示設定。"""
from qpeQt import QtCore, QtGui, QtWidgets, shiboken
from qpeSettings import readSettings, writeSettings


class BrowserItemDelegate(QtWidgets.QStyledItemDelegate):
    """フォルダー・ファイル・サイドバーで共通の行高を使用する。"""

    def paint(self, painter, option, index):
        """共通の行描画でもカラムの階層矢印を保持する。

        Args:
            painter (QPainter): Qtの描画先。
            option (QStyleOptionViewItem): 描画条件。
            index (QModelIndex): 項目。
        """
        view = self.parent()
        if isinstance(view, QtWidgets.QListView):
            item_option = QtWidgets.QStyleOptionViewItem(option)
            self.initStyleOption(item_option, index)
            arrow_space = max(12, option.fontMetrics.height())
            item_option.text = option.fontMetrics.elidedText(item_option.text, QtCore.Qt.ElideRight,
                                                           max(0, option.rect.width() - arrow_space - 6))
            view.style().drawControl(QtWidgets.QStyle.CE_ItemViewItem, item_option, painter, view)
            arrow = QtWidgets.QStyleOption()
            arrow_size = max(6, round(option.fontMetrics.height() * .5))
            arrow.rect = QtCore.QRect(option.rect.right() - arrow_space,
                                     option.rect.center().y() - arrow_size // 2, arrow_size, arrow_size)
            arrow.palette = option.palette
            arrow.state = QtWidgets.QStyle.State_Enabled
            view.style().drawPrimitive(QtWidgets.QStyle.PE_IndicatorArrowRight, arrow, painter, view)
        else:
            super().paint(painter, option, index)

    def sizeHint(self, option, index):
        """フォントとUI倍率に追従した行の大きさを返す。

        Args:
            option (QStyleOptionViewItem): 描画条件。
            index (QModelIndex): 項目。

        Returns:
            QSize: 文字が欠けず、各一覧で揃う行高。
        """
        size = super().sizeHint(option, index)
        height = self.parent().property('qpeRowHeight') or 22
        size.setHeight(max(height, option.fontMetrics.height() + 4))
        return size


class Appearance:
    """Explorer内の寸法だけを拡大し、Maya全体の設定は変更しない。"""

    def __init__(self, widget, dpi_scale):
        """基準寸法を一度だけ記録する。

        Args:
            widget (Explorer): 対象画面。
            dpi_scale (float): MayaのDPI倍率。単体Qtでは1。
        """
        self.widget = widget
        self.dpiScale = dpi_scale
        self.key = 'mayaAppearance' if widget._maya else 'standaloneAppearance'
        self.dialog = None
        self.dimensions = [(w, w.minimumSize(), w.maximumSize())
                           for w in widget.findChildren(QtWidgets.QWidget)]
        self.layouts = [(layout, layout.contentsMargins(), layout.spacing())
                        for layout in widget.findChildren(QtWidgets.QLayout)]
        self.baseFont = QtGui.QFont('Segoe UI')
        self.baseFont.setWeight(QtGui.QFont.Normal)
        value = readSettings().get(self.key, {})
        value = value if isinstance(value, dict) else {}
        self.fontSize = self._number(value.get('fontSize'), 12, 10, 24)
        self.uiPercent = self._number(value.get('uiPercent'), 100, 75, 200)
        self.apply(self.fontSize, self.uiPercent, save=False)

    @staticmethod
    def _number(value, default, low, high):
        """破損した保存値を既定値へ戻す。

        Args:
            value (object): 保存値。
            default (int): 既定値。
            low (int): 最小値。
            high (int): 最大値。

        Returns:
            int: 範囲内の整数。
        """
        return max(low, min(high, value)) if type(value) is int else default

    def apply(self, font_size, ui_percent, save=True):
        """文字・アイコン・余白・最小寸法を元の基準から再計算する。

        Args:
            font_size (int): DPI適用前の文字ピクセルサイズ。
            ui_percent (int): ユーザー指定のUI倍率。
            save (bool): 専用設定へ保存するか。
        """
        self.fontSize = self._number(font_size, 12, 10, 24)
        self.uiPercent = self._number(ui_percent, 100, 75, 200)
        scale = self.dpiScale * self.uiPercent / 100.0
        px = lambda value: max(1, round(value * scale)) if value else 0
        font_pixels = max(1, round(self.fontSize * scale))
        # ホスト全体に影響させず、QPE内だけ細いトラックとホバー強調を使う。
        self.widget.setStyleSheet('''
            QWidget { font-family: "Segoe UI"; font-size: %dpx; font-weight: normal; }
            QTreeView, QListView { color: #e4e7eb; background-color: #2b2b2b; alternate-background-color: #333638; }
            QColumnView QListView { border: none; border-right: 1px solid #484848; }
            QLineEdit, QComboBox, QPushButton { padding: %dpx %dpx; }
            QHeaderView::section { padding: %dpx %dpx; font-weight: normal; }
            QTabBar::tab { padding: %dpx %dpx; }
            QScrollBar:vertical { background: transparent; width: %dpx; margin: 0; }
            QScrollBar:horizontal { background: transparent; height: %dpx; margin: 0; }
            QScrollBar::handle { background: rgba(145,145,145,100); border-radius: %dpx; }
            QScrollBar::handle:hover { background: rgba(165,165,165,190); }
            QScrollBar::handle:pressed { background: rgba(185,185,185,220); }
            QScrollBar::handle:vertical { min-height: %dpx; }
            QScrollBar::handle:horizontal { min-width: %dpx; }
            QScrollBar::add-line, QScrollBar::sub-line { width: 0; height: 0; border: none; }
            QScrollBar::add-page, QScrollBar::sub-page { background: transparent; }
        ''' % (font_pixels, px(3), px(6), px(4), px(6), px(5), px(8),
               px(7), px(7), px(3), px(28), px(28)))
        font = QtGui.QFont(self.baseFont)
        font.setPixelSize(max(1, round(self.fontSize * scale)))
        self.widget.setFont(font)
        for w, minimum, maximum in self.dimensions:
            if not shiboken.isValid(w):
                continue
            w.setFont(font)
            w.setMinimumSize(px(minimum.width()), px(minimum.height()))
            w.setMaximumSize(px(maximum.width()) if maximum.width() < 16777215 else 16777215,
                             px(maximum.height()) if maximum.height() < 16777215 else 16777215)
        for layout, margins, spacing in self.layouts:
            if not shiboken.isValid(layout):
                continue
            layout.setContentsMargins(*(px(v) for v in (margins.left(), margins.top(), margins.right(), margins.bottom())))
            if spacing >= 0:
                layout.setSpacing(px(spacing))
        for button in self.widget.findChildren(QtWidgets.QToolButton):
            button.setIconSize(QtCore.QSize(px(20), px(20)))
        for view in (self.widget.columns, self.widget.files, self.widget.places):
            view.setIconSize(QtCore.QSize(px(16), px(16)))
            view.setProperty('qpeRowHeight', max(px(22), QtGui.QFontMetrics(font).height() + px(6)))
            if view is not self.widget.columns and not isinstance(view.itemDelegate(), BrowserItemDelegate):
                view.setItemDelegate(BrowserItemDelegate(view))
        self.widget.places.setIndentation(px(16))
        for control in (self.widget.address, self.widget.search, self.widget.fileFilter,
                        self.widget.sidebarButton, self.widget.backButton, self.widget.forwardButton,
                        self.widget.locationsButton, self.widget.displayButton, self.widget.rootButton,
                        self.widget.inspectorButton):
            control.setMinimumHeight(max(px(28), QtGui.QFontMetrics(font).height() + px(8)))
        self.widget.folderLabel.setStyleSheet('background: #30363a; color: #e4e7eb; padding: %dpx %dpx;' % (px(5), px(6)))
        for splitter in (self.widget.outer, self.widget.vertical, self.widget.lower):
            splitter.setHandleWidth(px(4))
        # 最小カラム幅は大きな文字にも追従させる。
        self.widget.columns.columnScale = scale * max(1.0, self.fontSize / 12.0)
        self.widget.columns.fitColumns()
        if self.widget.columns.currentIndex().isValid():
            self.widget.columns.scrollTo(self.widget.columns.currentIndex())
        for view in self.widget.columns.findChildren(QtWidgets.QListView):
            view.setFont(font)
            view.setIconSize(QtCore.QSize(px(16), px(16)))
            view.doItemsLayout()
        self.widget.files.doItemsLayout()
        self.widget.places.doItemsLayout()
        self.widget.files.setColumnWidth(0, px(235))
        self.widget.files.setColumnWidth(1, px(85))
        self.widget.preview.setMaximumHeight(px(260))
        self.widget.previewText.setMaximumHeight(px(230))
        self.widget._operationTabChanged(self.widget.operationTabs.currentIndex())
        if self.dialog is not None:
            self.dialog.setFont(font)
            presets = {(12, 100): 0, (12, 125): 1, (12, 150): 2}
            self.presetCombo.blockSignals(True)
            self.presetCombo.setCurrentIndex(presets.get((self.fontSize, self.uiPercent), 3))
            self.presetCombo.blockSignals(False)
            self.effectiveSize.setText('Displayed text: {} px · UI: {:.0f}% of host'.format(font.pixelSize(), self.uiPercent))
            self.dialog.adjustSize()
        if save and not writeSettings({self.key: {'fontSize': self.fontSize, 'uiPercent': self.uiPercent}}):
            self.widget.status.setText('Display settings could not be saved.')
            self.widget.status.show()

    def show(self):
        """即時反映する表示設定ダイアログを開く。"""
        if self.dialog is not None:
            self.dialog.show()
            self.dialog.raise_()
            return
        dialog = QtWidgets.QDialog(self.widget)
        self.dialog = dialog
        dialog.setWindowTitle('Display Settings')
        dialog.setFont(self.widget.font())
        layout = QtWidgets.QFormLayout(dialog)
        layout.addRow(QtWidgets.QLabel('Maya DPI: {:.0f}%'.format(self.dpiScale * 100)
                                      if self.widget._maya else 'DPI: Windows / Qt automatic', dialog))
        self.presetCombo = QtWidgets.QComboBox(dialog)
        self.presetCombo.setObjectName('displayPreset')
        self.presetCombo.addItems(['Standard', 'Larger', 'Largest', 'Custom'])
        layout.addRow('Size', self.presetCombo)
        self.effectiveSize = QtWidgets.QLabel(dialog)
        layout.addRow(self.effectiveSize)
        self.widthCombo = QtWidgets.QComboBox(dialog)
        self.widthCombo.setObjectName('columnWidthMode')
        self.widthCombo.addItem('Fit window', 'fit')
        self.widthCombo.addItem('Fit names (Finder)', 'names')
        self.widthCombo.setCurrentIndex(1 if self.widget.columns.widthMode == 'names' else 0)
        self.widthCombo.currentIndexChanged.connect(lambda index: self.widget.columns.setWidthMode(self.widthCombo.itemData(index)))
        layout.addRow('Column width', self.widthCombo)
        advancedButton = QtWidgets.QToolButton(dialog)
        advancedButton.setText('Advanced settings')
        advancedButton.setCheckable(True)
        layout.addRow(advancedButton)
        advanced = QtWidgets.QWidget(dialog)
        advanced_layout = QtWidgets.QFormLayout(advanced)
        self.fontSpin = QtWidgets.QSpinBox(advanced)
        self.fontSpin.setObjectName('displayFontSize')
        self.fontSpin.setRange(10, 24)
        self.fontSpin.setValue(self.fontSize)
        advanced_layout.addRow('Font size (before scaling)', self.fontSpin)
        self.scaleSpin = QtWidgets.QSpinBox(advanced)
        self.scaleSpin.setObjectName('displayUiScale')
        self.scaleSpin.setRange(75, 200)
        self.scaleSpin.setSingleStep(25)
        self.scaleSpin.setSuffix(' %')
        self.scaleSpin.setValue(self.uiPercent)
        advanced_layout.addRow('UI scale (includes text)', self.scaleSpin)
        layout.addRow(advanced)
        advanced.hide()
        advancedButton.toggled.connect(advanced.setVisible)
        advancedButton.toggled.connect(lambda unused: dialog.adjustSize())
        self.fontSpin.valueChanged.connect(self._changed)
        self.scaleSpin.valueChanged.connect(self._changed)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.RestoreDefaults | QtWidgets.QDialogButtonBox.Close, dialog)
        buttons.button(QtWidgets.QDialogButtonBox.RestoreDefaults).clicked.connect(self._reset)
        buttons.rejected.connect(dialog.hide)
        layout.addRow(buttons)
        self.presetCombo.activated.connect(self.setPreset)
        self.apply(self.fontSize, self.uiPercent, save=False)
        dialog.show()

    def setPreset(self, index):
        """用途が分かる三段階の表示サイズを設定する。

        Args:
            index (int): 標準・大きめ・特大の選択。
        """
        if index not in (0, 1, 2):
            return
        self.fontSpin.blockSignals(True)
        self.scaleSpin.blockSignals(True)
        self.fontSpin.setValue(12)
        self.scaleSpin.setValue((100, 125, 150)[index])
        self.fontSpin.blockSignals(False)
        self.scaleSpin.blockSignals(False)
        self.apply(12, (100, 125, 150)[index])

    def _changed(self, value):
        """操作した値を直ちに反映する。

        Args:
            value (int): Qtの変更通知値。
        """
        self.apply(self.fontSpin.value(), self.scaleSpin.value())

    def _reset(self):
        """Maya標準倍率を保った既定表示へ戻す。"""
        self.setPreset(0)

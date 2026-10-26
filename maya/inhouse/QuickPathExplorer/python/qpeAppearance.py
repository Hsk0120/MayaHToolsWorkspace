"""ホストのDPIとユーザー指定を分けて扱う表示設定。"""
from qpeQt import QtCore, QtGui, QtWidgets, shiboken
from qpeSettings import readSettings, writeSettings
from qpeTheme import Theme


class BrowserItemDelegate(QtWidgets.QStyledItemDelegate):
    """フォルダー・ファイル・サイドバーで共通の行高を使用する。"""

    def initStyleOption(self, option, index):
        """矢印の分だけ文字を省略し、背景とアイコンはQt標準描画へ渡す。

        Args:
            option (QStyleOptionViewItem): Qtが描画に使用する項目情報。
            index (QModelIndex): 描画する項目。
        """
        super().initStyleOption(option, index)
        view = self.parent()
        if isinstance(view, QtWidgets.QListView) and option.rect.isValid():
            arrow_space = max(12, option.fontMetrics.height())
            option.text = option.fontMetrics.elidedText(
                option.text, QtCore.Qt.ElideRight,
                max(0, option.rect.width() - arrow_space - view.iconSize().width() - 12))

    def paint(self, painter, option, index):
        """共通の行描画でもカラムの階層矢印を保持する。

        Args:
            painter (QPainter): Qtの描画先。
            option (QStyleOptionViewItem): 描画条件。
            index (QModelIndex): 項目。
        """
        view = self.parent()
        # QWidget.style()はPySide側にQStyleSheetStyleへの参照を残す。
        # 共有スタイルのDLL終了順による再無効化を避け、Qt内部で描画させる。
        super().paint(painter, option, index)
        if isinstance(view, QtWidgets.QListView):
            arrow_space = max(12, option.fontMetrics.height())
            model = index.model()
            path = model.filePath(index)
            ready = model.states.get(path, ('loading', ''))[0] == 'ready'
            has_children = not ready or model.rowCount(index) > 0
            color = option.palette.color(QtGui.QPalette.Text)
            if option.state & QtWidgets.QStyle.State_Selected:
                color = QtGui.QColor(view.property('qpeSelectionText') or option.palette.color(QtGui.QPalette.HighlightedText).name())
            if has_children:
                painter.save()
                painter.setRenderHint(QtGui.QPainter.Antialiasing)
                painter.setPen(QtGui.QPen(QtGui.QColor(color), max(1.0, arrow_space / 12.0)))
                x = option.rect.right() - arrow_space / 2 - 2
                y = option.rect.center().y()
                radius = arrow_space / 4.0
                painter.drawPolyline(QtGui.QPolygonF([
                    QtCore.QPointF(x - radius / 2, y - radius),
                    QtCore.QPointF(x + radius / 2, y),
                    QtCore.QPointF(x - radius / 2, y + radius)]))
                painter.restore()

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
        self.theme = Theme(widget)
        self.dpiScale = dpi_scale
        self.key = 'mayaAppearance' if widget._maya else 'standaloneAppearance'
        self.dialog = None
        # QLineEditの消去ボタンなど、Qt内部が生成した部品の寸法はQtに任せる。
        # 再生成を繰り返すと内部部品のラッパーがisValidでもminimumSizeで落ちる
        # Maya Qt6環境があるため、QPEがPythonで作った部品だけを直接操作する。
        self.dimensions = [(w, w.minimumSize(), w.maximumSize())
                           for w in widget.findChildren(QtWidgets.QWidget)
                           if shiboken.isValid(w) and shiboken.createdByPython(w)]
        self.layouts = [(layout, layout.contentsMargins(), layout.spacing())
                        for layout in widget.findChildren(QtWidgets.QLayout)
                        if shiboken.isValid(layout) and shiboken.createdByPython(layout)]
        self.baseFont = QtGui.QFont('Segoe UI')
        self.baseFont.setWeight(QtGui.QFont.Normal)
        value = readSettings().get(self.key, {})
        value = value if isinstance(value, dict) else {}
        self.fontSize = self._number(value.get('fontSize'), 12, 10, 24)
        self.uiPercent = self._number(value.get('uiPercent'), 100, 75, 200)
        self.density = value.get('density', 'compact')
        if self.density not in ('compact', 'comfortable'):
            self.density = 'compact'
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
        self.applyStyle()
        font = QtGui.QFont(self.baseFont)
        font.setPixelSize(max(1, round(self.fontSize * scale)))
        self.widget.setFont(font)
        if hasattr(self.widget, 'folderTabs'):
            self.widget.folderTabs.strip.refresh()
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
            button.setIconSize(QtCore.QSize(px(16), px(16)))
        for view in (self.widget.columns, self.widget.files, self.widget.places):
            view.setIconSize(QtCore.QSize(px(16), px(16)))
            view.setProperty('qpeRowHeight', max(px(28 if self.density == 'comfortable' else 24), QtGui.QFontMetrics(font).height() + px(6)))
            if view is not self.widget.columns and not isinstance(view.itemDelegate(), BrowserItemDelegate):
                view.setItemDelegate(BrowserItemDelegate(view))
        self.widget.places.setIndentation(px(16))
        for control in (self.widget.address, self.widget.search, self.widget.fileFilter,
                        self.widget.sidebarButton, self.widget.backButton, self.widget.forwardButton,
                        self.widget.locationsButton, self.widget.displayButton, self.widget.rootButton,
                        self.widget.inspectorButton):
            control.setMinimumHeight(max(px(28), QtGui.QFontMetrics(font).height() + px(8)))

        for splitter in (self.widget.outer, self.widget.vertical, self.widget.lower):
            splitter.setHandleWidth(px(3))
        # 最小カラム幅は大きな文字にも追従させる。
        self.widget.columns.columnScale = scale * max(1.0, self.fontSize / 12.0)
        self.widget.columns.fitColumns()
        if self.widget.columns.currentIndex().isValid():
            self.widget.columns.scrollTo(self.widget.columns.currentIndex())
        for view in self.widget.columns.findChildren(QtWidgets.QListView):
            view.setFont(font)
            view.setProperty('qpeRowHeight', self.widget.columns.property('qpeRowHeight'))
            view.setIconSize(QtCore.QSize(px(16), px(16)))
            view.doItemsLayout()
        self.widget.files.doItemsLayout()
        self.widget.places.doItemsLayout()
        # フォント変更後も余白をファイル名へ配分する。固定幅へ戻すと右側が空く。
        self.widget._configureFileHeader()
        self.widget.files.header().resizeSections()
        self.widget.preview.setMaximumHeight(px(180))
        self.widget.previewText.setMaximumHeight(px(230))
        self.widget._operationTabChanged(self.widget.operationTabs.currentIndex())
        if hasattr(self.widget, 'modern'):
            self.widget.modern.refresh()
            self.widget.modern.applyMetrics()
        if self.dialog is not None:
            self.dialog.setFont(font)
            presets = {(12, 100): 0, (13, 125): 1, (13, 150): 2}
            self.presetCombo.blockSignals(True)
            self.presetCombo.setCurrentIndex(presets.get((self.fontSize, self.uiPercent), 3))
            self.presetCombo.blockSignals(False)
            self.densityCombo.blockSignals(True)
            self.densityCombo.setCurrentIndex(int(self.density == 'comfortable'))
            self.densityCombo.blockSignals(False)
            self.effectiveSize.setText('Displayed text: {} px · UI: {:.0f}% of host'.format(font.pixelSize(), self.uiPercent))
            self.dialog.adjustSize()
        if save and not writeSettings({self.key: {'fontSize': self.fontSize, 'uiPercent': self.uiPercent, 'density': self.density}}):
            self.widget.status.setText('Display settings could not be saved.')
            self.widget.status.show()

    def applyStyle(self):
        """配色変更だけでは列幅・スクロール・フォーカスを変更しない。"""
        scale = self.dpiScale * self.uiPercent / 100.0
        px = lambda value: max(1, round(value * scale)) if value else 0
        font_pixels = max(1, round(self.fontSize * scale))
        # ホスト全体に影響させず、QPE内だけ細いトラックとホバー強調を使う。
        from qpeModern import style
        self.widget.setStyleSheet(self.theme.style() + '''
            QWidget { font-family: "Segoe UI"; font-size: %dpx; font-weight: normal; }
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
               px(7), px(7), px(3), px(28), px(28)) + style(self.theme.colors, px, font_pixels))
        colors = self.theme.colors
        self.widget.folderLabel.setStyleSheet(
            'background: transparent; color: %s; padding: %dpx %dpx; font-weight: 600;' %
            (colors['text'], px(4), px(8)))

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
        if not self.widget._maya:
            theme_combo = QtWidgets.QComboBox(dialog)
            for label, mode in [('Classic Light', 'finder'), ('Windows theme', 'system'), ('Windows Light', 'light'), ('Windows Dark', 'dark')]:
                theme_combo.addItem(label, mode)
            theme_combo.setCurrentIndex(theme_combo.findData(self.theme.mode))
            theme_combo.currentIndexChanged.connect(lambda index: self.theme.setMode(theme_combo.itemData(index)))
            layout.addRow('Color', theme_combo)
        layout.addRow(QtWidgets.QLabel('Maya DPI: {:.0f}%'.format(self.dpiScale * 100)
                                      if self.widget._maya else 'DPI: Windows / Qt automatic', dialog))
        self.presetCombo = QtWidgets.QComboBox(dialog)
        self.presetCombo.setObjectName('displayPreset')
        self.presetCombo.addItems(['Standard', 'Larger', 'Largest', 'Custom'])
        layout.addRow('Size', self.presetCombo)
        density = QtWidgets.QComboBox(dialog)
        self.densityCombo = density
        density.addItems(['Compact', 'Comfortable'])
        density.setCurrentIndex(int(self.density == 'comfortable'))
        density.currentIndexChanged.connect(self.setDensity)
        layout.addRow('Row spacing', density)
        self.effectiveSize = QtWidgets.QLabel(dialog)
        layout.addRow(self.effectiveSize)
        self.widthCombo = QtWidgets.QComboBox(dialog)
        self.widthCombo.setObjectName('columnWidthMode')
        self.widthCombo.addItem('Fit window', 'fit')
        self.widthCombo.addItem('Fit folder names', 'names')
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

    def setDensity(self, index):
        """文字倍率を変えずに一覧の行間だけを切り替える。"""
        self.density = 'comfortable' if index else 'compact'
        self.apply(self.fontSize, self.uiPercent)

    def setPreset(self, index):
        """用途が分かる三段階の表示サイズを設定する。

        Args:
            index (int): 標準・大きめ・特大の選択。
        """
        if index not in (0, 1, 2):
            return
        self.fontSpin.blockSignals(True)
        self.scaleSpin.blockSignals(True)
        self.fontSpin.setValue(12 if index == 0 else 13)
        self.scaleSpin.setValue((100, 125, 150)[index])
        self.fontSpin.blockSignals(False)
        self.scaleSpin.blockSignals(False)
        self.apply(self.fontSpin.value(), (100, 125, 150)[index])

    def _changed(self, value):
        """操作した値を直ちに反映する。

        Args:
            value (int): Qtの変更通知値。
        """
        self.apply(self.fontSpin.value(), self.scaleSpin.value())

    def _reset(self):
        """Maya標準倍率を保った既定表示へ戻す。"""
        self.density = 'compact'
        self.setPreset(0)

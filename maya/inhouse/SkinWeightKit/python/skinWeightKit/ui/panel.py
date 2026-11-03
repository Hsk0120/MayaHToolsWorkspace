"""Skin Weight Kit の画面。メインウィンドウの右端に縦に置く、折りたためるセクションを並べたパネル。

ボタンの処理は :mod:`skinWeightKit.core` を呼ぶだけにし、失敗はMayaの警告として表示する。
workspaceControl・optionVar・Paint Skin Weights ツールの起動は、mlib が持たない画面側の操作なので cmds を使う。
"""

import functools

import maya.cmds as cmds
import maya.OpenMayaUI as omui

from mlib.common import ScriptJobs, Selection

from ..core import (blend, cleanup, deformers, hold, influences, reduction, sample, selectionTools, shells, skin,
                    symmetry, target, transfer, weights)
from ..core import paint as paint_core
from . import paint as paint_ui
from .qt import QtCore, QtGui, QtWidgets, wrapInstance

#: workspaceControl の名前。
CONTROL = "SkinWeightKitWorkspaceControl"

#: 表示状態を覚える optionVar の名前。
VISIBLE_OPTION = "skinWeightKitVisible"

#: パネルの初めの幅(px)。
WIDTH = 300

#: 値を設定するボタンの値。
PRESETS = (0.0, 0.1, 0.25, 0.5, 0.75, 0.9, 1.0)

#: インフルエンスの一覧の列。
LOCK_COLUMN, NAME_COLUMN, VALUE_COLUMN = range(3)

#: 一覧の値の棒の色。
BAR_COLOR = QtGui.QColor(70, 140, 150)

_panel = {"widget": None}


def _warn(error):
    """失敗をMayaの警告として表示する。

    Args:
        error (Exception): 失敗の例外。

    Returns:
        None: 値を返さない。
    """
    cmds.warning("Skin Weight Kit: {}".format(error))


def _message(text):
    """ビューポートに短い知らせを出す。

    Args:
        text (str): 表示する文。

    Returns:
        None: 値を返さない。
    """
    cmds.inViewMessage(assistMessage=text, position="botCenter", fade=True, fadeStayTime=1200)


def _open_help():
    """HTools の説明ページの Skin Weight Kit のページを開く。

    Returns:
        str: 開いたURL。
    """
    try:
        # HTools が読み込めない環境でもパネルを使えるよう、押したときに読み込む。
        from HTools import toolHelp
    except ImportError:
        raise RuntimeError("The HTools documentation is not available in this Maya")
    return toolHelp.openHelp("rigging", "skinWeightKit")


def run(function, *args, **kwargs):
    """処理を呼び、想定内の失敗は警告にする。

    Args:
        function (Callable): 呼ぶ処理。
        *args: 位置引数。
        **kwargs: キーワード引数。

    Returns:
        object: 処理の戻り値。失敗したらNone。
    """
    try:
        return function(*args, **kwargs)
    except (ValueError, RuntimeError, KeyError, TypeError, IndexError) as error:
        _warn(error)
        return None


def _action(menu, label, callback, tip):
    """説明付きのメニューの項目を足す。

    Args:
        menu (QtWidgets.QMenu): メニュー。
        label (str): 表示名。
        callback (Callable): 選んだときの処理。
        tip (str): 項目にマウスを乗せたときの説明。

    Returns:
        QtWidgets.QAction: 足した項目。
    """
    action = menu.addAction(label)
    # QMenu は既定で項目のツールチップを出さないため、表示を有効にする。
    menu.setToolTipsVisible(True)
    action.setToolTip(tip)
    action.triggered.connect(lambda *_: callback())
    return action


class Section(QtWidgets.QWidget):
    """見出しを押すと中身を折りたためる区切り(Modeling Toolkit と同じ考え方)。

    Args:
        title (str): 見出し。
        expanded (bool): 初めに開いておくか。
        parent (QtWidgets.QWidget | None): 親。
    """

    def __init__(self, title, expanded=True, parent=None):
        super().__init__(parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.header = QtWidgets.QToolButton(self)
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(expanded)
        self.header.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.header.setStyleSheet("QToolButton { font-weight: bold; text-align: left; border: none; padding: 3px; }")
        self.header.setToolTip("{}\nClick to show or hide this section.".format(title))
        self.body = QtWidgets.QWidget(self)
        self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(6, 0, 2, 4)
        self.body_layout.setSpacing(3)
        layout.addWidget(self.header)
        layout.addWidget(self.body)
        self.header.toggled.connect(self._toggled)
        self._toggled(expanded)

    def _toggled(self, state):
        """開閉に合わせて矢印と中身の表示を変える。"""
        self.header.setArrowType(QtCore.Qt.DownArrow if state else QtCore.Qt.RightArrow)
        self.body.setVisible(state)

    def row(self, *widgets):
        """部品を横に並べた行を足す。

        Args:
            *widgets (QtWidgets.QWidget): 並べる部品。

        Returns:
            QtWidgets.QHBoxLayout: 足した行。
        """
        layout = QtWidgets.QHBoxLayout()
        layout.setSpacing(3)
        for widget in widgets:
            layout.addWidget(widget)
        self.body_layout.addLayout(layout)
        return layout


def _button(text, tip, callback=None):
    """説明付きのボタンを作る。

    Args:
        text (str): 表示名。
        tip (str): ツールチップ(1行目は見出し)。
        callback (Callable | None): 押したときの処理。

    Returns:
        QtWidgets.QPushButton: 作ったボタン。
    """
    button = QtWidgets.QPushButton(text)
    button.setToolTip(tip)
    button.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
    if callback is not None:
        button.clicked.connect(lambda *_: callback())
    return button


def _spin(value, minimum, maximum, decimals, step, tip, width=64):
    """説明付きの数値の欄を作る(decimals が0なら整数)。

    Returns:
        QtWidgets.QAbstractSpinBox: 作った欄。
    """
    if decimals:
        spin = QtWidgets.QDoubleSpinBox()
        spin.setDecimals(decimals)
    else:
        spin = QtWidgets.QSpinBox()
    spin.setRange(minimum, maximum)
    spin.setSingleStep(step)
    spin.setValue(value)
    spin.setFixedWidth(width)
    spin.setToolTip(tip)
    return spin


class SlideSlider(QtWidgets.QSlider):
    """押してから離すまでの増減を、離したときに1回の Undo で書くスライダー(離すと中央へ戻る)。

    Args:
        parent (QtWidgets.QWidget | None): 親。
    """

    def __init__(self, parent=None):
        super().__init__(QtCore.Qt.Horizontal, parent)
        self.setRange(-100, 100)
        self.setValue(0)
        self.onPress = None
        self.onDrag = None
        self.onRelease = None
        self._dragging = False
        self.sliderPressed.connect(self._pressed)
        self.sliderReleased.connect(self._released)
        self.valueChanged.connect(self._changed)

    def _pressed(self):
        """ドラッグを始める。"""
        self._dragging = bool(self.onPress is None or self.onPress())

    def _changed(self, value):
        """ドラッグ中だけ量を反映する(溝のクリックでは何もしない)。"""
        if self._dragging and self.onDrag is not None:
            self.onDrag(value / 100.0)

    def _released(self):
        """ドラッグを終え、中央へ戻す。"""
        if self._dragging and self.onRelease is not None:
            self.onRelease()
        self._dragging = False
        self.blockSignals(True)
        self.setValue(0)
        self.blockSignals(False)


class BarDelegate(QtWidgets.QStyledItemDelegate):
    """ウェイトの列に、値の割合だけ塗った棒と数値を描く。"""

    def paint(self, painter, option, index):
        """棒を描いてから、通常どおり文字を描く。"""
        value = index.data(QtCore.Qt.UserRole)
        if isinstance(value, float) and value > 0.0:
            rect = QtCore.QRect(option.rect)
            rect.setWidth(int(round(rect.width() * min(1.0, value))))
            painter.fillRect(rect.adjusted(0, 1, 0, -1), BAR_COLOR)
        super().paint(painter, option, index)


class SkinWeightKitPanel(QtWidgets.QWidget):
    """Skin Weight Kit の本体。

    Args:
        parent (QtWidgets.QWidget | None): 親。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("SkinWeightKit")
        self.target = None
        self.active = None
        self.move_session = None
        self.slide_session = None
        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(2, 2, 2, 2)
        self.title = QtWidgets.QLabel("Select a skinned mesh")
        self.title.setToolTip("Target\nThe mesh, skinCluster and number of selected vertices the tools work on.\n"
                              "Select vertices, edges or faces to edit them, or the mesh to work on all of it.")
        self.title.setWordWrap(True)
        help_button = QtWidgets.QToolButton()
        help_button.setText("?")
        help_button.setToolTip("Help\nOpen the Skin Weight Kit page of the HTools documentation in the web browser.")
        help_button.clicked.connect(lambda *_: run(_open_help))
        header = QtWidgets.QHBoxLayout()
        header.addWidget(self.title, 1)
        header.addWidget(help_button)
        outer.addLayout(header)
        scroll = QtWidgets.QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        content = QtWidgets.QWidget()
        self.content_layout = QtWidgets.QVBoxLayout(content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        self.table_vertices = []
        self.brush_mode = "smooth"
        for build in (self._influences, self._table, self._select, self._weight, self._brushes, self._blend,
                      self._smooth, self._copy_mirror, self._cleanup, self._game, self._bind, self._settings,
                      self._files):
            self.content_layout.addWidget(build())
        self.content_layout.addStretch(1)
        scroll.setWidget(content)
        outer.addWidget(scroll)
        self.jobs = ScriptJobs()
        for event in ("SelectionChanged", "Undo", "Redo", "SceneOpened"):
            self.jobs.add(event, event=event, callback=self.refresh)
        self.refresh()

    # --- セクション -----------------------------------------------------------------

    def _influences(self):
        """インフルエンスの一覧(検索・使用中だけ・ロック・値)。"""
        section = Section("Influences")
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("Search...")
        self.search.setToolTip("Search\nShow only the influences whose names contain this text.")
        self.search.textChanged.connect(lambda *_: self._apply_filter())
        self.used_only = QtWidgets.QCheckBox("Used only")
        self.used_only.setToolTip("Used Only\nShow only the influences that affect the selected vertices.")
        self.used_only.toggled.connect(lambda *_: self._apply_filter())
        section.row(self.search, self.used_only)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(3)
        self.tree.setHeaderLabels(["Lock", "Influence", "Weight"])
        self.tree.setRootIsDecorated(False)
        self.tree.setUniformRowHeights(True)
        self.tree.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree.setMinimumHeight(180)
        header = self.tree.header()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(LOCK_COLUMN, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(NAME_COLUMN, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(VALUE_COLUMN, QtWidgets.QHeaderView.Fixed)
        self.tree.setColumnWidth(VALUE_COLUMN, 80)
        self.tree.setItemDelegateForColumn(VALUE_COLUMN, BarDelegate(self.tree))
        self.tree.setToolTip("Influences\n"
                             "Click an influence to make it the active one that the Weight buttons change.\n"
                             "Double-click to select the vertices it affects. Check Lock to keep its weights\n"
                             "unchanged by every tool. Weight shows the average over the selected vertices.\n"
                             "Click the Influence or Weight header to sort; click again to reverse.\n\n"
                             "Right click for lock, selection and add/remove options.")
        self.tree.setSortingEnabled(True)
        # 初めは skinCluster の順(並べ替えなし)にする。
        header.setSortIndicator(-1, QtCore.Qt.AscendingOrder)
        self.tree.itemClicked.connect(self._item_clicked)
        self.tree.itemDoubleClicked.connect(lambda item, _column: self._select_affected(item.text(NAME_COLUMN)))
        self.tree.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._influence_menu)
        section.body_layout.addWidget(self.tree)
        return section

    def _influence_menu(self, position):
        """一覧の右クリックメニュー。"""
        menu = QtWidgets.QMenu(self.tree)
        item = self.tree.itemAt(position)
        name = item.text(NAME_COLUMN) if item else None
        if name:
            _action(menu, "Select affected vertices", functools.partial(self._select_affected, name),
                    "Select every vertex this influence affects.")
            _action(menu, "Select the influence", functools.partial(self._select_node, name),
                    "Select the joint itself (for example to move it).")
            _action(menu, "Lock all others", functools.partial(self._lock_others, name),
                    "Unlock this influence and lock all the others, so only it and the active influence change.")
            menu.addSeparator()
        if name and self.active and name != self.active:
            _action(menu, "Move active weights here", functools.partial(self._move_weights, self.active, name),
                    "Add the weights of the active influence ({}) to this influence and set the active one to 0.\n"
                    "Works on the selected vertices, or the whole mesh.".format(self.active))
            _action(menu, "Move weights to active", functools.partial(self._move_weights, name, self.active),
                    "Add the weights of this influence to the active influence ({}) and set this one to 0.\n"
                    "Works on the selected vertices, or the whole mesh.".format(self.active))
            _action(menu, "Ramp from active to here", functools.partial(self._ramp, self.active, name),
                    "Blend the selected vertices from the active influence ({}) to this influence along the line\n"
                    "between the two joints, using the Ramp easing in the Blend section.".format(self.active))
            menu.addSeparator()
        _action(menu, "Select all influences", self._select_all_influences,
                "Select every joint (influence) of the target skinCluster, for example to check or key them.")
        _action(menu, "Select used influences", self._select_used_influences,
                "Select only the joints that affect the selected vertices.")
        _action(menu, "Lock all", functools.partial(self._lock_all, True), "Lock every influence.")
        _action(menu, "Unlock all", functools.partial(self._lock_all, False), "Unlock every influence.")
        menu.addSeparator()
        _action(menu, "Add selected joints", self._add_influences,
                "Add the selected joints to the skinCluster with zero weight. Select the mesh too so the\n"
                "target stays the same.")
        if name:
            _action(menu, "Remove influence", functools.partial(self._remove_influence, name),
                    "Move this influence's weights to its nearest parent influence, then remove it.")
        menu.exec_(self.tree.viewport().mapToGlobal(position))

    def _weight(self):
        """値の設定(プリセット・Set/Add/Scale・Paint)。"""
        section = Section("Weight")
        buttons = []
        for value in PRESETS:
            button = _button("{:g}".format(value), "Weight {:g}\n"
                             "Click: set the active influence to {:g} on the selected vertices.\n"
                             "Shift+click: add {:g}. Ctrl+click: subtract {:g}.\n"
                             "The other unlocked influences are scaled so each vertex sums to 1."
                             .format(value, value, value, value),
                             functools.partial(self._preset, value))
            button.setMinimumWidth(24)
            buttons.append(button)
        section.row(*buttons)
        self.mode = QtWidgets.QComboBox()
        for label, name in (("Add", "add"), ("Scale", "scale")):
            self.mode.addItem(label, name)
        self.mode.setToolTip("Step Mode\n"
                             "Add: the - and + buttons subtract or add the step.\n"
                             "Scale: the - and + buttons multiply the weight by (1 - step) or (1 + step).")
        self.step = _spin(0.05, 0.001, 1.0, 3, 0.01, "Step\nThe amount the - and + buttons change the active "
                          "influence by.")
        minus = _button("-", "Decrease\nDecrease the active influence on the selected vertices by the step.",
                        functools.partial(self._step, -1))
        plus = _button("+", "Increase\nIncrease the active influence on the selected vertices by the step.",
                       functools.partial(self._step, 1))
        section.row(self.mode, self.step, minus, plus)
        self.value = _spin(0.5, 0.0, 1.0, 3, 0.05, "Value\nThe weight the Set button writes.")
        set_button = _button("Set", "Set Value\nSet the active influence to the value on the selected vertices.",
                             lambda: self._apply_value(self.value.value(), "set"))
        paint = _button("Paint", "Paint Skin Weights\n"
                        "Open Maya's Paint Skin Weights tool on the target mesh with the active influence.\n"
                        "Use it to see the weights as colors and to paint them.", self._paint)
        flood = _button("Flood", "Flood\nSet the active influence to the value on every vertex of the target mesh\n"
                        "(or only the selected vertices). The other unlocked influences are rebalanced.",
                        lambda: self._edit(weights.flood, self._require_active(), self.value.value()))
        section.row(self.value, set_button, flood, paint)
        return section

    def _table(self):
        """選んだ頂点ごとのウェイトの表(既定は閉じる。開いているときだけ更新する)。"""
        self.table_section = Section("Vertex Table", expanded=False)
        self.table = QtWidgets.QTableWidget()
        self.table.setMinimumHeight(160)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.table.setToolTip("Vertex Table\n"
                              "The weights of each selected vertex (up to 500), one column per influence it uses.\n"
                              "Type a value in a cell to set that influence on that vertex; with several cells of the\n"
                              "same column selected, the value is set on all of them. The other unlocked influences\n"
                              "are rebalanced. Red Sum: the weights do not sum to 1. Yellow row: more influences than\n"
                              "the skinCluster's max influences.")
        self.table.itemChanged.connect(self._table_edited)
        self.table_section.body_layout.addWidget(self.table)
        self.table_section.header.toggled.connect(lambda state: self._refresh_table() if state else None)
        return self.table_section

    def _refresh_table(self):
        """表を、今の対象で作り直す(セクションが閉じていれば何もしない)。"""
        if not self.table_section.header.isChecked():
            return
        self.table.blockSignals(True)
        self.table.clear()
        self.table_vertices = []
        data = None
        if self.target is not None and self.target.skin is not None and self.target.vertices:
            data = run(weights.table, self.target)
        if not data:
            self.table.setRowCount(0)
            self.table.setColumnCount(0)
            self.table.blockSignals(False)
            return
        limit = self.target.skin.getMaxInfluences()
        self.table_vertices = data["vertices"]
        self.table.setColumnCount(len(data["influences"]) + 1)
        self.table.setRowCount(len(data["vertices"]))
        self.table.setHorizontalHeaderLabels(data["influences"] + ["Sum"])
        self.table.setVerticalHeaderLabels(["vtx[{}]".format(vertex) for vertex in data["vertices"]])
        warning = QtGui.QColor(110, 100, 40)
        for row, values in enumerate(data["rows"]):
            over = bool(limit) and data["counts"][row] > limit
            for column, value in enumerate(values):
                item = QtWidgets.QTableWidgetItem("{:.3f}".format(value) if value > 0.0 else "")
                if over:
                    item.setBackground(warning)
                self.table.setItem(row, column, item)
            total = QtWidgets.QTableWidgetItem("{:.3f}".format(data["sums"][row]))
            total.setFlags(total.flags() & ~QtCore.Qt.ItemIsEditable)
            if abs(data["sums"][row] - 1.0) > 1e-3:
                total.setBackground(QtGui.QColor(140, 50, 50))
            self.table.setItem(row, len(values), total)
        self.table.resizeColumnsToContents()
        self.table.blockSignals(False)

    def _table_edited(self, item):
        """セルの書換えを、その列の選んだセルの頂点へ反映する。"""
        column = item.column()
        header = self.table.horizontalHeaderItem(column)
        if header is None or column >= self.table.columnCount() - 1:
            return
        try:
            value = float(item.text() or 0.0)
        except ValueError:
            _warn("Enter a number between 0 and 1")
            self._refresh_table()
            return
        rows = {cell.row() for cell in self.table.selectedItems() if cell.column() == column}
        rows.add(item.row())
        vertices = [self.table_vertices[row] for row in sorted(rows) if row < len(self.table_vertices)]
        run(lambda: weights.setVertexValues(self._require_target(), vertices, header.text(), value))
        self.refresh()

    def _select(self):
        """選択を広げる・狭める、エッジのループ・リング。"""
        section = Section("Select")
        section.row(
            _button("Grow", "Grow Selection\nAdd the neighbors of the selected vertices to the selection.",
                    functools.partial(self._edit, selectionTools.grow, refresh=False)),
            _button("Shrink", "Shrink Selection\nRemove the border vertices from the selection.",
                    functools.partial(self._edit, selectionTools.shrink, refresh=False)),
            _button("Loop", "Edge Loop\nSelect the edge loops of the selected edges (continuing straight through\n"
                    "vertices where four edges meet).", lambda: run(selectionTools.selectLoop)),
            _button("Ring", "Edge Ring\nSelect the edge rings of the selected edges (crossing four-sided faces to "
                    "the\nopposite edge).", lambda: run(selectionTools.selectRing)))
        self.range_min = _spin(0.0, 0.0, 1.0, 3, 0.05, "Minimum\nThe lowest active-influence weight to select.",
                               width=60)
        self.range_max = _spin(1.0, 0.0, 1.0, 3, 0.05, "Maximum\nThe highest active-influence weight to select.",
                               width=60)
        section.row(self.range_min, self.range_max,
                    _button("Select by Weight", "Select by Weight\nSelect the vertices whose active-influence "
                            "weight is between the\nminimum and maximum (within the selected vertices, or the whole "
                            "mesh).",
                            self._select_in_range))
        return section

    def _select_in_range(self):
        """アクティブなインフルエンスの値が範囲内の頂点を選ぶ。"""
        count = run(lambda: influences.selectInRange(self._require_target(), self._require_active(),
                                                     self.range_min.value(), self.range_max.value()))
        if count is not None:
            _message("Selected {} vertices".format(count))

    def _blend(self):
        """スライド・ソフト選択・ランプ。"""
        section = Section("Blend")
        label = QtWidgets.QLabel("Slide")
        label.setToolTip("Slide\nDrag the slider next to it.")
        self.slider = SlideSlider()
        self.slider.setToolTip("Slide Weights\n"
                               "Drag right to increase and left to decrease the active influence on the selected\n"
                               "vertices. With Soft Select on, vertices change by their soft selection falloff.\n"
                               "The slider returns to the center when released, and one drag is one undo.")
        self.slider.onPress = self._slide_start
        self.slider.onDrag = self._slide_drag
        self.slider.onRelease = self._slide_finish
        section.row(label, self.slider)
        section.row(_button("Soft Selection to Weight", "Soft Selection to Weight\n"
                            "Set the active influence to the soft selection falloff of each vertex (1 at the\n"
                            "selected vertices, fading out). Turn on Soft Select (B) and select vertices first.",
                            self._from_soft_selection))
        self.easing = QtWidgets.QComboBox()
        for label_text, name in (("Linear", "linear"), ("Smooth", "smooth")):
            self.easing.addItem(label_text, name)
        self.easing.setToolTip("Ramp Easing\nLinear: an even blend. Smooth: slower at both ends (smoothstep).")
        ramp_button = _button("Ramp to...", "Ramp\nBlend the selected vertices from the active influence to another\n"
                              "influence along the line between the two joints. Click and choose the end influence\n"
                              "(or right click it in the list).")
        ramp_button.clicked.connect(lambda *_: self._ramp_menu(ramp_button))
        section.row(self.easing, ramp_button)
        self.deformer_list = QtWidgets.QComboBox()
        self.deformer_list.setToolTip("Deformer\nThe deformer (cluster, softMod, deltaMush ...) on the target mesh "
                                      "whose weights\nDeformer to Weight reads.")
        section.row(self.deformer_list,
                    _button("Deformer to Weight", "Deformer to Weight\nSet the active influence to the chosen "
                            "deformer's weight on each vertex\n(vertices with weight 0 are left alone). Paint a "
                            "cluster comfortably, then turn it\ninto joint weights. Works on the selected vertices, "
                            "or the whole mesh.", self._deformer_to_weight))
        return section

    def _ramp_menu(self, owner):
        """ランプの終わりのインフルエンスを選ぶメニュー。"""
        if not self.active:
            _warn("Click an influence in the list first")
            return
        menu = QtWidgets.QMenu(owner)
        for index in range(self.tree.topLevelItemCount()):
            name = self.tree.topLevelItem(index).text(NAME_COLUMN)
            if name != self.active:
                _action(menu, name, functools.partial(self._ramp, self.active, name),
                        "Blend from {} to {}.".format(self.active, name))
        menu.exec_(owner.mapToGlobal(QtCore.QPoint(0, owner.height())))

    def _smooth(self):
        """ハンマー・平均・スムーズ。"""
        section = Section("Smooth")
        section.row(
            _button("Hammer", "Hammer\nReplace the weights of each selected vertex with the average of its\n"
                    "neighbors (using the Method below). Fixes single vertices that stick out.",
                    lambda: self._edit(weights.hammer, self.smooth_method.currentData(), self.smooth_radius.value())),
            _button("Average", "Average\nGive every selected vertex the same weights: the average of the selection.",
                    functools.partial(self._edit, weights.average)))
        self.strength = _spin(0.5, 0.0, 1.0, 2, 0.1, "Strength\nHow far each pass moves the weights toward the "
                              "neighbor average (0 to 1).")
        self.iterations = _spin(1, 1, 50, 0, 1, "Iterations\nHow many smoothing passes to run. More passes "
                                "spread the smoothing further.", width=48)
        section.row(self.strength, self.iterations,
                    _button("Smooth", "Smooth\nBlend the weights of the selected vertices toward their neighbors\n"
                            "by the strength, repeated for the number of iterations.", self._run_smooth))
        self.smooth_method = QtWidgets.QComboBox()
        for label_text, name in (("Uniform", "uniform"), ("Distance", "distance"), ("Cotangent", "cotangent")):
            self.smooth_method.addItem(label_text, name)
        self.smooth_method.setToolTip("Smooth Method (also used by the Smooth and Sharpen brushes)\n"
                                      "Uniform: plain average of the connected neighbors (Maya-style).\n"
                                      "Distance: neighbors weighted by 1 / edge length, so dense areas pull less.\n"
                                      "Cotangent: weights from the triangle angles; follows the surface shape and\n"
                                      "is robust to uneven or stretched triangles.")
        self.smooth_radius = _spin(0.0, 0.0, 100.0, 2, 0.1, "Gap Radius (cm)\nAlso blend with vertices within this "
                                   "distance that are not connected by edges\n(between fingers, layered or separate "
                                   "pieces). 0 uses only connected neighbors.", width=64)
        self.smooth_keep_max = QtWidgets.QCheckBox("Keep max")
        self.smooth_keep_max.setToolTip("Keep Max Influences\nWhile smoothing, never let a vertex use more influences "
                                        "than the\nskinCluster's max influences (the smallest are dropped).")
        section.row(self.smooth_method, self.smooth_radius, self.smooth_keep_max)
        section.row(
            _button("Shell Average", "Shell Average\nGive every vertex of each shell (connected piece) the average\n"
                    "weights of that shell, so the piece moves without bending. Works on the shells that contain\n"
                    "the selected vertices, or every shell of the selected mesh.",
                    lambda: self._edit(shells.unifyShells, "average")),
            _button("Shell Rigid", "Shell Rigid\nBind every vertex of each shell 100% to the influence with the\n"
                    "largest average weight in that shell (rigid parts such as armor plates or buttons).",
                    lambda: self._edit(shells.unifyShells, "rigid")))
        return section

    def _game(self):
        """ゲームエンジン向けのリダクション(0に近い値の削除・最大数への振り直し・精度の丸め)と診断。"""
        section = Section("Game Cleanup")
        self.game_prune = _spin(0.01, 0.0, 0.5, 4, 0.005, "Prune Below\nWeights below this value are set to 0 "
                                "(0 keeps every weight).", width=72)
        self.game_max = QtWidgets.QComboBox()
        for count in (1, 2, 3, 4, 6, 8):
            self.game_max.addItem("Max {}".format(count), count)
        self.game_max.setCurrentIndex(3)
        self.game_max.setToolTip("Max Influences\nThe most influences a vertex may keep (the engine's limit, for\n"
                                 "example 4 or 8). The largest weights are kept and rebalanced to sum to 1.")
        section.row(self.game_prune, self.game_max)
        self.game_precision = QtWidgets.QComboBox()
        labels = {"off": "No rounding", "8-bit": "8-bit (1/255)", "16-bit": "16-bit (1/65535)"}
        for name, steps in reduction.PRECISIONS:
            self.game_precision.addItem(labels.get(name, name.capitalize()), steps)
        self.game_precision.setCurrentIndex(4)
        self.game_precision.setToolTip("Precision\nRound the weights to the precision the engine stores (8-bit is\n"
                                       "1/255 steps). Rounding errors are spread so each vertex sums to exactly 1.")
        section.row(self.game_precision)
        self.game_unused = QtWidgets.QCheckBox("Remove unused")
        self.game_unused.setToolTip("Remove Unused Influences\nAfter cleaning up, remove the influences that no "
                                    "longer affect any vertex.")
        self.game_limit = QtWidgets.QCheckBox("Lock skin max")
        self.game_limit.setChecked(True)
        self.game_limit.setToolTip("Lock Skin Max Influences\nSet the skinCluster's max influences to the limit and\n"
                                   "turn on Maintain Max Influences, so later painting keeps the limit.")
        self.game_scope = QtWidgets.QComboBox()
        for label_text, name in (("Target only", "target"), ("All selected meshes", "selected"),
                                 ("All skinned meshes in scene", "scene")):
            self.game_scope.addItem(label_text, name)
        self.game_scope.setToolTip("Scope\nTarget only: the selected vertices, or the target mesh.\n"
                                   "All selected meshes: every selected skinned mesh (whole meshes).\n"
                                   "All skinned meshes in scene: every skinned mesh, for a final pass before export.")
        section.row(self.game_unused, self.game_limit)
        section.row(self.game_scope)
        self.max_bones = _spin(64, 1, 1024, 0, 1, "Max Bones\nThe most influences the skinCluster may keep (for "
                               "engines with a\nbone limit per mesh or draw call).", width=60)
        section.row(self.max_bones,
                    _button("Limit Bones", "Limit Bones\nRemove influences until the skinCluster has at most Max "
                            "Bones,\nstarting from the joint with the smallest total weight. Each removed joint's "
                            "weights go\nto its nearest parent influence. Locked joints and joints without a parent "
                            "influence are kept.", self._limit_bones))
        self.helper_pattern = QtWidgets.QLineEdit("*_end")
        self.helper_pattern.setToolTip("Helper Joint Patterns\nName patterns of joints that should not deform in the "
                                       "engine, separated by\ncommas (* matches any text), for example *_end, "
                                       "*_helper.")
        section.row(self.helper_pattern,
                    _button("Remove Matching", "Remove Matching Joints\nRemove the joint influences whose names match "
                            "the patterns. Their weights\nare moved to the nearest parent influence first. One undo.",
                            self._remove_matching))
        section.row(
            _button("Analyze", "Analyze\nReport the most influences used, influences per vertex, and how many\n"
                    "vertices are over the limit, not normalized, have weights below Prune Below or off the\n"
                    "precision grid. Nothing is changed.", self._analyze),
            _button("Select Problems", "Select Problems\nSelect the vertices Clean Up would fix (over the limit,\n"
                    "not normalized, tiny weights, off the precision grid).", self._select_problems),
            _button("Clean Up", "Clean Up\nFor each vertex: set weights below Prune Below to 0, keep the largest up\n"
                    "to Max Influences, rebalance to sum to 1 and round to the precision. One undo.",
                    self._game_cleanup))
        self.report = QtWidgets.QLabel("")
        self.report.setWordWrap(True)
        self.report.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
        self.report.setToolTip("Report\nThe result of Analyze or Clean Up.")
        section.body_layout.addWidget(self.report)
        section.row(_button("Copy Report", "Copy Report\nCopy the report text to the clipboard (to paste into a chat "
                            "or ticket).", self._copy_report))
        return section

    def _copy_mirror(self):
        """頂点のコピー/ペーストとミラー。"""
        section = Section("Copy / Mirror")
        section.row(
            _button("Copy", "Copy Weights\nCopy the weights of the selected vertex (the average if several are "
                    "selected).", functools.partial(self._edit, weights.copy, refresh=False)),
            _button("Paste", "Paste Weights\nPaste the copied weights onto every selected vertex. Influences are\n"
                    "matched by name, so you can paste onto another mesh with the same joints.",
                    functools.partial(self._edit, weights.paste)))
        section.row(
            _button("Sample", "Sample Vertices\nRemember the weights and positions of the selected vertices as the\n"
                    "sample for Average and Proximity.", self._sample),
            _button("Average", "Apply Sample Average\nGive every selected vertex the average weights of the sample\n"
                    "vertices (for rigid parts).", lambda: self._edit(sample.apply, "average")),
            _button("Proximity", "Apply Sample by Proximity\nGive each selected vertex a blend of the sample weights,\n"
                    "weighted by how close each sample vertex is (inverse distance squared). Fix the weights at both\n"
                    "ends of an edge loop, sample them, then apply to the loop for a smooth transition.",
                    lambda: self._edit(sample.apply, "proximity")))
        section.row(
            _button("Hold", "Hold Weights\nRemember the weights of the whole target mesh (in memory, until Maya is "
                    "closed).", self._hold),
            _button("Fetch", "Fetch Weights\nRestore the weights remembered by Hold in one undo (only the selected\n"
                    "vertices, if any). Try a big change, then go back without undoing step by step.",
                    functools.partial(self._edit, hold.fetch)))
        self.axis = QtWidgets.QComboBox()
        for name in ("x", "y", "z"):
            self.axis.addItem(name.upper(), name)
        self.axis.setToolTip("Mirror Axis\nThe axis the mesh is mirrored across (X mirrors left and right).")
        self.positive = QtWidgets.QCheckBox("+ to -")
        self.positive.setChecked(True)
        self.positive.setToolTip("Direction\nChecked: copy from the + side to the - side. Unchecked: from - to +.")
        section.row(self.axis, self.positive,
                    _button("Mirror", "Mirror Weights\nMirror the weights of the whole mesh across the axis.\n"
                            "Influences are paired by left/right names (Maya's Mirror Skin Weights).",
                            self._mirror))
        self.tolerance = _spin(0.01, 0.0001, 10.0, 4, 0.01, "Tolerance\nHow far (cm, object space) the opposite "
                               "vertex may be from the exact mirrored position.", width=72)
        section.row(self.tolerance,
                    _button("Mirror Selected", "Mirror Selected Vertices\n"
                            "Copy the weights of the selected vertices to the vertices on the other side of the axis.\n"
                            "Influences are swapped by left/right names (L_/R_, _l/_r, Left/Right ...); influences\n"
                            "without a side keep their name.", self._mirror_selected))
        return section

    def _cleanup(self):
        """プルーン・最大数・丸め・正規化・不正な頂点。"""
        section = Section("Cleanup")
        self.prune_value = _spin(0.01, 0.0001, 0.5, 4, 0.005, "Prune Threshold\nWeights below this value are "
                                 "removed by Prune.", width=72)
        section.row(self.prune_value,
                    _button("Prune", "Prune\nSet weights below the threshold to 0 and rebalance the rest.\n"
                            "Works on the selected vertices, or the whole mesh.",
                            lambda: self._edit(cleanup.prune, self.prune_value.value())))
        self.max_count = _spin(4, 1, 32, 0, 1, "Max Influences\nThe most influences a vertex may have.", width=48)
        section.row(self.max_count,
                    _button("Limit", "Limit Influences\nKeep only the largest weights on each vertex up to the max\n"
                            "influences and rebalance. Works on the selection, or the whole mesh.",
                            lambda: self._edit(cleanup.limitInfluences, self.max_count.value())))
        self.decimals = _spin(3, 1, 6, 0, 1, "Decimals\nThe number of decimal places Round keeps.", width=48)
        section.row(self.decimals,
                    _button("Round", "Round\nRound the weights to the decimals, keeping each vertex's sum at 1.",
                            lambda: self._edit(cleanup.roundWeights, self.decimals.value())))
        section.row(
            _button("Normalize", "Normalize\nMake the weights of each vertex sum to 1 (locked influences are kept).",
                    functools.partial(self._edit, cleanup.normalize)),
            _button("Select Bad", "Select Bad Vertices\nSelect the vertices whose weights do not sum to 1, or that\n"
                    "have more influences than the skinCluster's max influences.", self._select_bad))
        return section

    def _bind(self):
        """バインド・バインドポーズ・ジョイントの移動・不要なインフルエンス。"""
        section = Section("Bind")
        self.method = QtWidgets.QComboBox()
        for label, name in (("Closest distance", "closest"), ("Closest in hierarchy", "hierarchy"),
                            ("Heat map", "heatMap")):
            self.method.addItem(label, name)
        self.method.setToolTip("Bind Method\nHow the first weights are computed when binding.")
        self.bind_max = _spin(4, 1, 32, 0, 1, "Max Influences\nThe most influences per vertex when binding.",
                              width=48)
        section.row(self.method, self.bind_max)
        section.row(
            _button("Bind", "Bind Skin\nSelect joints and meshes, then click to bind each mesh that is not skinned "
                    "yet.", self._bind_skin),
            _button("Bind Pose", "Go to Bind Pose\nReturn the joints of the target skin to the pose they were bound "
                    "in.", functools.partial(self._edit, skin.goToBindPose, refresh=False)))
        self.move_button = _button("Move Joints", "Move Joints\n"
                                   "1. Select joints and press this button (it stays on).\n"
                                   "2. Move or rotate the joints; the skinned mesh does not change.\n"
                                   "3. Press it again to make the new positions the bind positions.")
        self.move_button.setCheckable(True)
        self.move_button.toggled.connect(self._move_joints)
        section.row(self.move_button,
                    _button("Remove Unused", "Remove Unused Influences\nRemove the influences that affect no vertex.",
                            functools.partial(self._edit, skin.removeUnusedInfluences)))
        section.row(_button("Closest Joint", "Assign Closest Joint\nBind each selected vertex (or every vertex of "
                            "the mesh) 100% to the nearest bone\n(the line from a joint to its child joints). Use it "
                            "for quick rigid starting weights,\nthen Smooth to blend. Locked influences are kept.",
                            functools.partial(self._edit, weights.assignClosest)))
        section.row(_button("Remove Selected Joints", "Remove Selected Joints\n"
                            "Remove the selected joints from every skinCluster they influence. Their weights are\n"
                            "moved to the nearest parent influence first, so the mesh keeps its shape. When a parent\n"
                            "and child are both selected, the weights collect in the remaining ancestor. Joints with\n"
                            "no parent influence are left to Maya's default redistribution. One undo.",
                            self._remove_joints))
        return section

    def _settings(self):
        """skinCluster の設定(既定は閉じる。開いているときだけ読み込む)。"""
        self.settings_section = Section("Skin Settings", expanded=False)
        self.skinning_method = QtWidgets.QComboBox()
        for label_text, name in (("Classic Linear", "classicLinear"), ("Dual Quaternion", "dualQuaternion"),
                                 ("Weight Blended", "weightBlended")):
            self.skinning_method.addItem(label_text, name)
        self.skinning_method.setToolTip("Skinning Method\nClassic Linear: standard linear blend skinning (every "
                                        "engine).\nDual Quaternion: keeps volume when twisting (check engine "
                                        "support).\nWeight Blended: blends the two by a per-vertex map.")
        self.normalize_mode = QtWidgets.QComboBox()
        for label_text, name in (("Normalize: None", "none"), ("Normalize: Interactive", "interactive"),
                                 ("Normalize: Post", "post")):
            self.normalize_mode.addItem(label_text, name)
        self.normalize_mode.setToolTip("Normalize Weights\nInteractive keeps every vertex summing to 1 while editing "
                                       "(recommended).\nPost normalizes only when deforming. None never normalizes.")
        self.settings_section.row(self.skinning_method)
        self.settings_section.row(self.normalize_mode)
        self.settings_max = _spin(4, 1, 32, 0, 1, "Max Influences\nThe skinCluster's max influences per vertex.",
                                  width=48)
        self.settings_maintain = QtWidgets.QCheckBox("Maintain max")
        self.settings_maintain.setToolTip("Maintain Max Influences\nKeep painting and editing within the max "
                                          "influences.")
        self.settings_section.row(self.settings_max, self.settings_maintain,
                                  _button("Apply", "Apply Skin Settings\nWrite these settings to the target "
                                          "skinCluster (one undo).", self._apply_settings))
        self.settings_section.header.toggled.connect(lambda state: self._refresh_settings() if state else None)
        return self.settings_section

    def _refresh_settings(self):
        """skinCluster の設定を読み込む(セクションが閉じていれば何もしない)。"""
        if not self.settings_section.header.isChecked():
            return
        if self.target is None or self.target.skin is None:
            return
        settings = run(skin.getSettings, self.target)
        if settings is None:
            return
        self.skinning_method.setCurrentIndex(self.skinning_method.findData(settings["skinningMethod"]))
        self.normalize_mode.setCurrentIndex(self.normalize_mode.findData(settings["normalizeWeights"]))
        self.settings_max.setValue(settings["maxInfluences"])
        self.settings_maintain.setChecked(settings["maintainMaxInfluences"])

    def _apply_settings(self):
        """設定を skinCluster へ書く。"""
        result = self._edit(skin.setSettings, self.skinning_method.currentData(), self.normalize_mode.currentData(),
                            self.settings_max.value(), self.settings_maintain.isChecked())
        if result is not None:
            _message("Applied the skin settings")

    def _files(self):
        """別のメッシュへのコピー・書き出し・読込み。"""
        section = Section("Transfer / Files", expanded=False)
        self.copy_source = None
        section.row(
            _button("Pick Source", "Pick Source Mesh\nRemember the selected skinned mesh as the source for Copy "
                    "from\nSource.", self._pick_source),
            _button("Copy from Source", "Copy from Source\nCopy weights from the picked source mesh onto the "
                    "selected\nvertices (or the whole target mesh), using the closest source vertex in world "
                    "space.\nInfluences are matched by name. Good for fixing only part of a mesh.",
                    self._copy_from_source))
        section.row(_button("Add Source Influences", "Add Source Influences\nAdd the influences of the picked source "
                            "mesh that the target skinCluster does not\nhave yet (with zero weight), so Copy from "
                            "Source can match every influence.", self._add_source_influences))
        section.row(_button("Copy Skin to Meshes", "Copy Skin to Meshes\n"
                            "Select the skinned source mesh first, then the meshes to copy to. Weights are copied\n"
                            "by closest point; meshes that are not skinned are bound to the same joints first.",
                            self._copy_skin))
        self.import_method = QtWidgets.QComboBox()
        for label_text, name in (("By vertex index", "index"), ("By closest position", "position")):
            self.import_method.addItem(label_text, name)
        self.import_method.setToolTip("Import Method\nBy vertex index: the mesh must have the same vertex count.\n"
                                      "By closest position: each vertex takes the weights of the nearest vertex\n"
                                      "in the file (object space), so it works on a changed or different mesh.")
        self.import_missing = QtWidgets.QCheckBox("Add missing")
        self.import_missing.setToolTip("Add Missing Influences\nAdd influences that are in the file but not in the\n"
                                       "skinCluster, when joints with those names exist in the scene.")
        section.row(self.import_method, self.import_missing)
        section.row(
            _button("Export...", "Export Weights\nSave the weights and vertex positions of the target mesh to a JSON\n"
                    "file.", self._export),
            _button("Import...", "Import Weights\nLoad weights from a JSON file onto the selected vertices, or the\n"
                    "whole mesh. Influences are matched by name.", self._import))
        return section

    # --- 一覧の更新 -----------------------------------------------------------------

    def _keep_target_for_joints(self, resolved):
        """ジョイントだけを選んだときは対象のメッシュを保ち、そのジョイントをアクティブにする。

        ビューポートでジョイントをクリックして、塗る・値を入れるインフルエンスを切り替えられるようにする。

        Args:
            resolved (Target | None): 選択から決めた対象。

        Returns:
            Target | None: 使う対象。
        """
        if resolved is not None or self.target is None or self.target.skin is None:
            return resolved
        try:
            joints = skin.selectedJoints()
            if not joints or not self.target.mesh.isValid():
                return resolved
            names = [node.getNodeName() for node in self.target.skin.getInfluences()]
        except (ValueError, RuntimeError):
            return resolved
        for joint in joints:
            if joint.getNodeName() in names:
                self.active = joint.getNodeName()
                break
        return self.target

    def refresh(self):
        """選択に合わせて、見出しとインフルエンスの一覧を作り直す。

        Returns:
            None: 値を返さない。
        """
        try:
            resolved = target.resolve()
        except (ValueError, RuntimeError):
            resolved = None
        self.target = self._keep_target_for_joints(resolved)
        try:
            self.title.isVisible()
        except RuntimeError:
            # Qt 側の部品が破棄された後に呼ばれたら、監視を外して終える。
            self.jobs.stop()
            return
        self.title.setText(self.target.label() if self.target is not None else "Select a skinned mesh")
        listed = run(influences.listInfluences, self.target) or []
        self.tree.blockSignals(True)
        self.tree.clear()
        for info in listed:
            item = QtWidgets.QTreeWidgetItem()
            item.setCheckState(LOCK_COLUMN, QtCore.Qt.Checked if info.locked else QtCore.Qt.Unchecked)
            item.setText(NAME_COLUMN, info.name)
            if info.value is not None:
                item.setText(VALUE_COLUMN, "{:.3f}".format(info.value))
                item.setData(VALUE_COLUMN, QtCore.Qt.UserRole, float(info.value))
            item.setData(NAME_COLUMN, QtCore.Qt.UserRole, info.value or 0.0)
            self.tree.addTopLevelItem(item)
            if info.name == self.active:
                self.tree.setCurrentItem(item)
        self.tree.blockSignals(False)
        self._apply_filter()
        current_source = self.transfer_source.currentText()
        self.transfer_source.blockSignals(True)
        self.transfer_source.clear()
        self.transfer_source.addItems([info.name for info in listed])
        if current_source:
            self.transfer_source.setCurrentIndex(max(0, self.transfer_source.findText(current_source)))
        self.transfer_source.blockSignals(False)
        self.deformer_list.clear()
        if self.target is not None:
            found = run(deformers.listDeformers, self.target.mesh) or []
            self.deformer_list.addItems([node.getNodeName() for node in found])
        self._refresh_table()
        self._refresh_settings()

    def _apply_filter(self):
        """検索と「使用中だけ」に合わせて行を隠す。"""
        text = self.search.text().lower()
        used = self.used_only.isChecked()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            hidden = text not in item.text(NAME_COLUMN).lower()
            if used and item.data(NAME_COLUMN, QtCore.Qt.UserRole) <= influences.THRESHOLD:
                hidden = True
            item.setHidden(hidden)

    def _item_clicked(self, item, column):
        """クリックでアクティブにし、ロックの列ならロックを切り替える。"""
        name = item.text(NAME_COLUMN)
        self.active = name
        self._sync_paint()
        if column == LOCK_COLUMN and self.target is not None and self.target.skin is not None:
            node = run(influences.find, self.target.skin, name)
            if node is not None:
                run(influences.setLocked, [node], item.checkState(LOCK_COLUMN) == QtCore.Qt.Checked)
                self.refresh()

    # --- 操作 -----------------------------------------------------------------------

    def _require_target(self):
        """対象を返す。無ければ例外にする。"""
        if self.target is None:
            raise ValueError("Select a skinned mesh or its vertices")
        return self.target

    def _require_active(self):
        """アクティブなインフルエンスを返す。無ければ例外にする。"""
        if not self.active:
            raise ValueError("Click an influence in the list first")
        return self.active

    def _edit(self, function, *args, **kwargs):
        """対象に処理を行い、一覧を更新する。"""
        refresh = kwargs.pop("refresh", True)

        def call():
            """対象を確かめてから処理を呼ぶ。"""
            return function(self._require_target(), *args, **kwargs)

        result = run(call)
        if refresh:
            self.refresh()
        return result

    def _apply_value(self, value, mode):
        """アクティブなインフルエンスの値を変える。"""
        result = run(lambda: weights.setValue(self._require_target(), self._require_active(), value, mode))
        self.refresh()
        return result

    def _preset(self, value):
        """プリセットのボタン(Shift は加算、Ctrl は減算)。"""
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ShiftModifier:
            self._apply_value(value, "add")
        elif modifiers & QtCore.Qt.ControlModifier:
            self._apply_value(-value, "add")
        else:
            self._apply_value(value, "set")

    def _step(self, direction):
        """- と + のボタン。"""
        step = self.step.value()
        if self.mode.currentData() == "scale":
            self._apply_value(1.0 + direction * step, "scale")
        else:
            self._apply_value(direction * step, "add")

    def _run_smooth(self):
        """スムーズのボタン。"""
        self._edit(weights.smooth, self.strength.value(), self.iterations.value(), self.smooth_method.currentData(),
                   self.smooth_radius.value(), self.smooth_keep_max.isChecked())

    def _brushes(self):
        """独自のブラシ(Maya のユーザーペイントのツールを使う)。"""
        section = Section("Brushes")
        tips = {
            "smooth": "Smooth Brush\nPaint to blend the weights toward the neighbors, using the Method, Gap Radius\n"
                      "and Keep max of the Smooth section. Stronger brush values smooth more.",
            "sharpen": "Sharpen Brush\nPaint to push the weights away from the neighbor average, making the\n"
                       "boundaries between influences crisper (the opposite of Smooth).",
            "remove": "Remove Brush\nPaint to reduce the active influence; its weight goes to the other unlocked\n"
                      "influences in proportion.",
            "add": "Add Brush\nPaint to increase the active influence, taking weight from the others in proportion.",
            "transfer": "Transfer Brush\nPaint to move weight from the 'From' influence to the active influence\n"
                        "(other influences are untouched).",
        }
        buttons = [_button(name.capitalize(), tips[name] + "\n\nBrush size, opacity and falloff are in Maya's Tool "
                           "Settings. One stroke is one undo. Press Q to leave the brush.",
                           functools.partial(self._start_brush, name)) for name in paint_core.MODES]
        section.row(*buttons[:3])
        section.row(*buttons[3:])
        label = QtWidgets.QLabel("From")
        label.setToolTip("From\nThe influence the Transfer brush takes weight from.")
        self.transfer_source = QtWidgets.QComboBox()
        self.transfer_source.setToolTip("Transfer From\nThe influence the Transfer brush moves weight from (to the "
                                        "active influence).")
        section.row(label, self.transfer_source)
        return section

    def _paint_settings(self):
        """ブラシのストロークの始めに読む設定を返す。"""
        return {"mode": self.brush_mode, "influence": self.active, "source": self.transfer_source.currentText() or None,
                "method": self.smooth_method.currentData(), "radius": self.smooth_radius.value(),
                "keepMax": self.smooth_keep_max.isChecked()}

    def _start_brush(self, mode):
        """ブラシのツールにする。"""
        def call():
            """対象のメッシュを選んでから、ブラシのツールにする。"""
            current = self._require_target()
            current.requireSkin()
            if mode in ("remove", "add", "transfer"):
                self._require_active()
            if not current.hasComponents():
                cmds.select(str(current.mesh.getTransform() or current.mesh))
            self.brush_mode = mode
            paint_ui.start(self._paint_settings)
            _message("{} brush: paint on the mesh (Q to leave)".format(mode.capitalize()))
        run(call)

    def _mirror(self):
        """ミラーのボタン。"""
        self._edit(skin.mirror, self.axis.currentData(), self.positive.isChecked())

    def _hold(self):
        """ウェイトを覚える。"""
        count = self._edit(hold.hold, refresh=False)
        if count is not None:
            _message("Held the weights of {} vertices".format(count))

    def _deformer_to_weight(self):
        """選んだデフォーマーのウェイトを、アクティブなインフルエンスの値にする。"""
        name = self.deformer_list.currentText()
        if not name:
            _warn("The target mesh has no deformer with weights")
            return
        count = run(lambda: deformers.toInfluence(self._require_target(), name, self._require_active()))
        if count is not None:
            _message("Set {} vertices from {}".format(count, name))
        self.refresh()

    def _copy_report(self):
        """診断の結果をクリップボードへコピーする。"""
        text = self.report.text()
        if not text:
            _warn("Run Analyze first")
            return
        QtWidgets.QApplication.clipboard().setText(text)
        _message("Copied the report")

    def _remove_matching(self):
        """パターンに合うジョイントを外す。"""
        removed = self._edit(influences.removeMatching, self.helper_pattern.text())
        if removed is not None:
            text = "Removed {} matching joint influence{}".format(len(removed), "" if len(removed) == 1 else "s")
            self.report.setText(text)
            _message(text)

    def _limit_bones(self):
        """インフルエンスの数を上限まで減らす。"""
        removed = self._edit(reduction.limitBones, self.max_bones.value())
        if removed is not None:
            text = "Removed {} influences".format(len(removed)) if removed else "Already within the bone limit"
            self.report.setText(text)
            _message(text)

    def _pick_source(self):
        """選んだメッシュを、コピー元として覚える。"""
        def call():
            """対象のメッシュがバインドされていれば覚える。"""
            current = self._require_target()
            current.requireSkin()
            self.copy_source = current.mesh
            return current.mesh.getNodeName()
        name = run(call)
        if name is not None:
            _message("Source: {}".format(name))

    def _add_source_influences(self):
        """覚えたメッシュのインフルエンスのうち、対象に無いものを足す。"""
        def call():
            """覚えたメッシュの skinCluster のインフルエンスを足す。"""
            if self.copy_source is None or not self.copy_source.isValid():
                raise ValueError("Pick a source mesh first")
            skins = self.copy_source.getSkinClusters()
            if not skins:
                raise ValueError("The source mesh is not skinned")
            return influences.addInfluences(self._require_target(), skins[0].getInfluences())
        count = run(call)
        if count is not None:
            _message("Added {} influences".format(count))
        self.refresh()

    def _copy_from_source(self):
        """覚えたメッシュから、選んだ頂点へコピーする。"""
        def call():
            """覚えたメッシュを元にしてコピーする。"""
            if self.copy_source is None or not self.copy_source.isValid():
                raise ValueError("Pick a source mesh first")
            skins = self.copy_source.getSkinClusters()
            source = target.Target(self.copy_source, skins[0] if skins else None, None)
            return transfer.copyFromMesh(source, self._require_target())
        count = run(call)
        if count is not None:
            _message("Copied weights onto {} vertices".format(count))
        self.refresh()

    def _sample(self):
        """選んだ頂点を見本として覚える。"""
        count = self._edit(sample.sampleVertices, refresh=False)
        if count is not None:
            _message("Sampled {} vertices".format(count))

    def _mirror_selected(self):
        """選んだ頂点だけのミラー。"""
        result = self._edit(symmetry.mirrorVertices, self.axis.currentData(), self.tolerance.value())
        if result is not None:
            copied, unmatched = result
            _message("Mirrored {} vertices".format(copied) +
                     (" ({} had no opposite vertex)".format(unmatched) if unmatched else ""))

    def _move_weights(self, source, destination):
        """インフルエンスのウェイトを移す。"""
        self._edit(weights.moveWeights, source, destination)

    def _ramp(self, start, end):
        """2つのインフルエンスの間のランプ。"""
        self._edit(blend.ramp, start, end, self.easing.currentData())

    def _slide_start(self):
        """スライドを始める(ソフト選択の重みと、開始時の値を覚える)。"""
        def call():
            """ソフト選択とアクティブなインフルエンスからセッションを作る。"""
            current, falloff = blend.softTarget()
            return blend.SlideSession(current, self._require_active(), falloff)
        self.slide_session = run(call)
        return self.slide_session is not None

    def _slide_drag(self, amount):
        """ドラッグ中の量を反映する。"""
        if self.slide_session is not None:
            run(self.slide_session.apply, amount)

    def _slide_finish(self):
        """離したときに1回の Undo で書く。"""
        if self.slide_session is not None:
            session, self.slide_session = self.slide_session, None
            run(session.finish)
            self.refresh()

    def _from_soft_selection(self):
        """ソフト選択の重みをアクティブなインフルエンスの値にする。"""
        count = run(lambda: blend.fromSoftSelection(self._require_active()))
        if count is not None:
            _message("Set {} vertices from the soft selection".format(count))
        self.refresh()

    def _select_affected(self, name):
        """インフルエンスが影響する頂点を選ぶ。"""
        count = self._edit(influences.selectAffected, name, refresh=False)
        if count is not None:
            _message("Selected {} vertices".format(count))

    def _select_node(self, name):
        """インフルエンス自体を選ぶ。"""
        def call():
            """skinCluster のインフルエンスを探して選ぶ。"""
            cmds.select(str(influences.find(self._require_target().requireSkin(), name)))
        run(call)

    def _lock_others(self, name):
        """指定以外をロックする。"""
        def call():
            """skinCluster のインフルエンスを探してロックを変える。"""
            current = self._require_target()
            influences.lockOthers(current, [influences.find(current.requireSkin(), name)])
        run(call)
        self.refresh()

    def _select_all_influences(self):
        """対象の skinCluster の全インフルエンスを選ぶ。"""
        def call():
            """インフルエンスを選ぶ。"""
            Selection(self._require_target().requireSkin().getInfluences()).select()
        run(call)

    def _select_used_influences(self):
        """選んだ頂点に影響しているインフルエンスだけを選ぶ。"""
        def call():
            """選んだ頂点での平均が0より大きいインフルエンスを選ぶ。"""
            current = self._require_target()
            current.requireVertices()
            used = [info.node for info in influences.listInfluences(current) if info.value and info.value > 0.0]
            Selection(used).select()
            return len(used)
        count = run(call)
        if count is not None:
            _message("Selected {} influences".format(count))

    def _lock_all(self, state):
        """全部をロック・解除する。"""
        run(lambda: influences.setLocked(self._require_target().requireSkin().getInfluences(), state))
        self.refresh()

    def _add_influences(self):
        """選んだジョイントを足す。"""
        count = run(lambda: influences.addInfluences(self._require_target(), skin.selectedJoints()))
        if count is not None:
            _message("Added {} influences".format(count))
        self.refresh()

    def _remove_influence(self, name):
        """インフルエンスを外す。"""
        if self.active == name:
            self.active = None
        self._edit(influences.removeInfluence, name)

    def _select_bad(self):
        """不正な頂点を選ぶ。"""
        count = self._edit(cleanup.selectBadVertices, refresh=False)
        if count is not None:
            _message("Selected {} bad vertices".format(count) if count else "No bad vertices")

    def _bind_skin(self):
        """選んだジョイントとメッシュをバインドする。"""
        created = run(lambda: skin.bind(skin.selectedJoints(), skin.selectedMeshes(), self.bind_max.value(),
                                        self.method.currentData()))
        if created is not None:
            _message("Bound {} meshes".format(len(created)))
        self.refresh()

    def _remove_joints(self):
        """選んだジョイントを外し、ウェイトを親へ移す。"""
        removed = run(lambda: influences.removeJoints(skin.selectedJoints()))
        if removed is not None:
            orphans = [joint for joint, _skin, parent in removed if parent is None]
            text = "Removed {} joint influence{}".format(len(removed), "" if len(removed) == 1 else "s")
            if orphans:
                text += " ({} had no parent influence: {})".format(len(orphans), ", ".join(sorted(set(orphans))))
            _message(text)
        self.refresh()

    def _move_joints(self, state):
        """ジョイントの移動のトグル。"""
        if state:
            self.move_session = run(lambda: skin.MoveJointsSession(skin.selectedJoints()).start())
            if self.move_session is None:
                self._set_checked(self.move_button, False)
            return
        if self.move_session is not None:
            run(self.move_session.finish)
            self.move_session = None

    @staticmethod
    def _set_checked(button, state):
        """シグナルを出さずにボタンの押した状態を変える。"""
        button.blockSignals(True)
        button.setChecked(state)
        button.blockSignals(False)

    def _copy_skin(self):
        """最初に選んだメッシュから、残りのメッシュへコピーする。"""
        def call():
            """選んだメッシュの先頭をコピー元にする。"""
            meshes = skin.selectedMeshes()
            if len(meshes) < 2:
                raise ValueError("Select the skinned source mesh first, then the meshes to copy to")
            source = target.Target(meshes[0], meshes[0].getSkinClusters()[0] if meshes[0].getSkinClusters()
                                   else None, None)
            return skin.copySkin(source, meshes[1:])
        count = run(call)
        if count is not None:
            _message("Copied skin to {} meshes".format(count))
        self.refresh()

    def _export(self):
        """書き出し先を聞いて書き出す。"""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Weights", "", "JSON (*.json)")
        if path:
            count = self._edit(transfer.exportWeights, path, refresh=False)
            if count is not None:
                _message("Exported {} vertices".format(count))

    def _import(self):
        """ファイルを聞いて読み込む。"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import Weights", "", "JSON (*.json)")
        if path:
            self.importFrom(path)

    def importFrom(self, path):
        """パネルの設定(対応のさせ方・足りないインフルエンスの追加)でファイルを読み込む。

        Args:
            path (str): 読み込むファイル。

        Returns:
            int | None: 書いた頂点の数。失敗したらNone。
        """
        count = self._edit(transfer.importWeights, path, self.import_method.currentData(),
                           self.import_missing.isChecked())
        if count is not None:
            _message("Imported weights onto {} vertices".format(count))
        return count

    def _game_targets(self):
        """ゲーム向けの整理の対象(選んだメッシュ・シーン全体ならメッシュ全体を並べる)。"""
        scope = self.game_scope.currentData()
        if scope == "target":
            return [self._require_target()]
        meshes = skin.skinnedMeshes() if scope == "scene" else skin.selectedMeshes()
        targets = [target.Target(mesh, mesh.getSkinClusters()[0], None) for mesh in meshes if mesh.getSkinClusters()]
        if not targets:
            raise ValueError("No skinned meshes found" if scope == "scene" else "Select skinned meshes")
        return targets

    def _game_settings(self):
        """ゲーム向けの整理の設定(しきい値・最大数・段階)。"""
        return self.game_prune.value(), self.game_max.currentData(), self.game_precision.currentData()

    def _analyze(self):
        """選んだ対象を診断して、結果を出す。"""
        def call():
            """対象ごとに診断し、文にする。"""
            threshold, limit, steps = self._game_settings()
            return "\n\n".join(reduction.formatReport(reduction.analyze(current, threshold, limit, steps),
                                                      current.mesh.getNodeName())
                               for current in self._game_targets())
        text = run(call)
        if text is not None:
            self.report.setText(text)

    def _select_problems(self):
        """直すべき頂点を選ぶ。"""
        def call():
            """対象を診断して、問題のある頂点を選ぶ。"""
            threshold, limit, steps = self._game_settings()
            return reduction.selectProblems(self._require_target(), threshold, limit, steps)
        count = run(call)
        if count is not None:
            _message("Selected {} vertices to fix".format(count) if count else "No problems found")

    def _game_cleanup(self):
        """ゲーム向けの整理を行い、結果を出す。"""
        def call():
            """設定のとおりにリダクションする。"""
            threshold, limit, steps = self._game_settings()
            return reduction.reduce(self._game_targets(), threshold, limit, steps,
                                    removeUnused=self.game_unused.isChecked(), setSkinLimit=self.game_limit.isChecked())
        summary = run(call)
        if summary is not None:
            text = "Cleaned {} vertices on {} mesh{}".format(summary["vertices"], summary["meshes"],
                                                             "" if summary["meshes"] == 1 else "es")
            if summary["removedInfluences"]:
                text += ", removed {} unused influences".format(summary["removedInfluences"])
            self.report.setText(text)
            _message(text)
        self.refresh()

    def _paint(self):
        """Maya の Paint Skin Weights ツールを、対象とアクティブなインフルエンスで開く。"""
        def call():
            """メッシュを選んでからツールを開く。"""
            current = self._require_target()
            current.requireSkin()
            if not current.hasComponents():
                cmds.select(str(current.mesh))
            cmds.ArtPaintSkinWeightsTool()
            self._sync_paint()
        run(call)

    def _sync_paint(self):
        """Paint Skin Weights ツールを使っていれば、塗るインフルエンスをアクティブなものにする。"""
        if not self.active or self.target is None or self.target.skin is None:
            return
        context = cmds.currentCtx()
        if cmds.contextInfo(context, c=True) != "artAttrSkin":
            return
        node = run(influences.find, self.target.skin, self.active)
        if node is not None:
            run(cmds.artAttrSkinPaintCtx, context, edit=True, influence=str(node))

    def closeEvent(self, event):
        """閉じるときに scriptJob を外し、ジョイントの移動を終える。"""
        self.stop()
        super().closeEvent(event)

    def stop(self):
        """scriptJob を外し、ジョイントの移動を終える。

        Returns:
            None: 値を返さない。
        """
        self.jobs.stop()
        if self.move_session is not None:
            run(self.move_session.finish)
            self.move_session = None


def _build():
    """workspaceControl の中にパネルを作る(uiScript からも呼ぶ)。

    Returns:
        SkinWeightKitPanel | None: 作ったパネル。workspaceControl が見つからなければNone。
    """
    pointer = omui.MQtUtil.findControl(CONTROL)
    if pointer is None:
        return None
    parent = wrapInstance(int(pointer), QtWidgets.QWidget)
    existing = parent.findChildren(SkinWeightKitPanel)
    if existing:
        # workspaceControl の作成時に uiScript が組み立て済みなら、二重に作らない。
        _panel["widget"] = existing[0]
        return existing[0]
    layout = parent.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    widget = SkinWeightKitPanel(parent)
    layout.addWidget(widget)
    _panel["widget"] = widget
    return widget


def _stop_existing():
    """作ってあるパネルの scriptJob を外す。"""
    if _panel["widget"] is not None:
        try:
            _panel["widget"].stop()
        except RuntimeError:
            # Qt 側の部品が先に破棄されていれば、外すものは無い。
            pass
    _panel["widget"] = None


def show():
    """パネルをメインウィンドウの右端に、独立した縦の領域としてドックして表示する。

    Returns:
        str: workspaceControl の名前。
    """
    if cmds.workspaceControl(CONTROL, exists=True):
        _stop_existing()
        cmds.deleteUI(CONTROL)
    cmds.workspaceControl(CONTROL, label="Skin Weight Kit", retain=False, floating=False,
                          dockToMainWindow=("right", False), initialWidth=WIDTH, widthProperty="preferred",
                          uiScript="import skinWeightKit.ui.panel as _panel; _panel._build()",
                          visibleChangeCommand=_remember_visibility)
    _build()
    cmds.optionVar(intValue=(VISIBLE_OPTION, 1))
    return CONTROL


def hide():
    """パネルを閉じる。

    Returns:
        None: 値を返さない。
    """
    _stop_existing()
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.deleteUI(CONTROL)
    cmds.optionVar(intValue=(VISIBLE_OPTION, 0))


def toggle():
    """パネルの表示・非表示を切り替える。

    Returns:
        bool: 表示したらTrue。
    """
    if cmds.workspaceControl(CONTROL, exists=True) and cmds.workspaceControl(CONTROL, query=True, visible=True):
        hide()
        return False
    show()
    return True


def wasVisible():
    """前回の表示状態を返す(未設定なら表示しない)。

    Returns:
        bool: 表示していたらTrue。
    """
    return cmds.optionVar(exists=VISIBLE_OPTION) and bool(cmds.optionVar(query=VISIBLE_OPTION))


def _remember_visibility(*_):
    """表示状態を optionVar へ覚える(workspaceControl の閉じるボタン用)。閉じたら scriptJob を外す。"""
    visible = cmds.workspaceControl(CONTROL, exists=True) and cmds.workspaceControl(CONTROL, query=True, visible=True)
    cmds.optionVar(intValue=(VISIBLE_OPTION, int(bool(visible))))
    if not visible:
        # retain=False のため閉じると部品が破棄される。破棄後に選択の変更で呼ばれないよう監視を外す。
        _stop_existing()

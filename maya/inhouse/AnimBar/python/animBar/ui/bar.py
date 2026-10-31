"""Anim Bar の画面。タイムスライダーの上にドックする横長のツールバー。

ボタンの処理は :mod:`animBar.core` を呼ぶだけにし、失敗はMayaの警告として表示する。
スライダーのドラッグは、押してから離すまでを1回のUndoにまとめる。
"""

import functools

import maya.cmds as cmds
import maya.OpenMayaUI as omui

from mlib.common import Time
from mlib.decorator import undoChunk

from ..core import (animCopy, crashRecovery, keys, keyTransform, mirror, selectSets, spaceTools, tangents,
                    timeline, timing, tween, viewTools)
from . import icons
from .qt import QtCore, QtGui, QtWidgets, wrapInstance

#: workspaceControl の名前。
CONTROL = "AnimBarWorkspaceControl"

#: 表示状態を覚える optionVar の名前。
VISIBLE_OPTION = "animBarVisible"

#: バーの高さ(px)。
HEIGHT = 34

_STYLE = """
QWidget#AnimBar {{ background: {background}; }}
QFrame#AnimBarSection {{ background: {panel}; border: 1px solid {line}; border-radius: 4px; }}
QLabel#AnimBarTitle {{ color: {muted}; font-size: 9px; padding: 0 2px; }}
QToolButton {{ background: transparent; border: none; border-radius: 3px; padding: 1px; }}
QToolButton:hover {{ background: {line}; }}
QToolButton:checked {{ background: {teal}; }}
QToolButton#AnimBarSet {{ color: {background}; font-weight: bold; padding: 0 6px; }}
QSlider::groove:horizontal {{ height: 4px; background: {line}; border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 10px; margin: -5px 0; border-radius: 5px; background: {teal}; }}
QComboBox, QDoubleSpinBox {{ background: {background}; color: {text}; border: 1px solid {line}; border-radius: 3px;
    padding: 0 4px; }}
""".format(**icons.PALETTE)

_bar = {"widget": None}


def _warn(error):
    """失敗をMayaの警告として表示する。

    Args:
        error (Exception): 失敗の例外。

    Returns:
        None: 値を返さない。
    """
    cmds.warning("Anim Bar: {}".format(error))


def _message(text):
    """ビューポートに短い知らせを出す。

    Args:
        text (str): 表示する文。

    Returns:
        None: 値を返さない。
    """
    cmds.inViewMessage(assistMessage=text, position="botCenter", fade=True, fadeStayTime=1200)


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


class Section(QtWidgets.QFrame):
    """見出しとボタンを並べる区切り。

    Args:
        title (str): 見出し。
        parent (QtWidgets.QWidget | None): 親。
    """

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setObjectName("AnimBarSection")
        self.layout_ = QtWidgets.QHBoxLayout(self)
        self.layout_.setContentsMargins(3, 1, 3, 1)
        self.layout_.setSpacing(1)
        label = QtWidgets.QLabel(title)
        label.setObjectName("AnimBarTitle")
        self.layout_.addWidget(label)

    def button(self, iconName, tip, callback=None, menu=None, checkable=False):
        """アイコンのボタンを足す。

        Args:
            iconName (str): :mod:`icons` の名前。
            tip (str): ツールチップ。
            callback (Callable | None): 押したときの処理。
            menu (Callable | None): 右クリックのメニューを作る関数(QMenuを受け取る)。左クリックの処理が無ければ左でも開く。
            checkable (bool): 押した状態を保つボタンにする。

        Returns:
            QtWidgets.QToolButton: 足したボタン。
        """
        button = QtWidgets.QToolButton(self)
        button.setIcon(icons.icon(iconName))
        button.setIconSize(QtCore.QSize(22, 22))
        button.setToolTip(tip + ("\nRight click for options" if menu and callback else ""))
        button.setCheckable(checkable)
        if callback is not None:
            button.clicked.connect(lambda *_: run(callback))
        if menu is not None:
            def popup(position, owner=button, build=menu):
                """右クリックのメニューを、その時点の状態で作って出す。"""
                popup_menu = QtWidgets.QMenu(owner)
                build(popup_menu)
                popup_menu.exec_(owner.mapToGlobal(position))
            button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(popup)
            if callback is None:
                button.clicked.connect(lambda *_, owner=button: popup(QtCore.QPoint(0, owner.height())))
        self.layout_.addWidget(button)
        return button

    def widget(self, widget):
        """ボタン以外の部品を足す。

        Args:
            widget (QtWidgets.QWidget): 部品。

        Returns:
            QtWidgets.QWidget: 足した部品。
        """
        self.layout_.addWidget(widget)
        return widget


def _action(menu, label, callback, checked=None):
    """メニューの項目を足す。

    Args:
        menu (QtWidgets.QMenu): メニュー。
        label (str): 表示名。
        callback (Callable): 選んだときの処理。
        checked (bool | None): チェック付きの項目にするなら状態。

    Returns:
        QtWidgets.QAction: 足した項目。
    """
    action = menu.addAction(label)
    if checked is not None:
        action.setCheckable(True)
        action.setChecked(checked)
    action.triggered.connect(lambda *_: run(callback))
    return action


class UndoSlider(QtWidgets.QSlider):
    """押してから離すまでの変更を1回のUndoにまとめるスライダー。

    Args:
        minimum (int): 最小値。
        maximum (int): 最大値。
        value (int): 初めの値。
        snapBack (int | None): 離したら戻す値。Noneは戻さない。
        parent (QtWidgets.QWidget | None): 親。
    """

    def __init__(self, minimum, maximum, value, snapBack=None, parent=None):
        super().__init__(QtCore.Qt.Horizontal, parent)
        self.setRange(minimum, maximum)
        self.setValue(value)
        self.setFixedWidth(110)
        self.snapBack = snapBack
        self.onPress = None
        self.onDrag = None
        self.sliderPressed.connect(self._pressed)
        self.sliderReleased.connect(self._released)
        self.valueChanged.connect(self._changed)
        self._dragging = False
        # 押してから離すまでを1回のUndoにまとめる(開閉が別々のシグナルになるため open/close を使う)。
        self._chunk = undoChunk("animBarSlider")

    def _pressed(self):
        """Undoのまとまりを開いてから、ドラッグを始める。"""
        self._chunk.open()
        self._dragging = True
        if self.onPress is not None:
            run(self.onPress)
        self._changed(self.value())

    def _released(self):
        """ドラッグを終え、Undoのまとまりを閉じる。"""
        self._dragging = False
        self._chunk.close()
        if self.snapBack is not None:
            self.blockSignals(True)
            self.setValue(self.snapBack)
            self.blockSignals(False)

    def _changed(self, value):
        """値が変わったら処理を呼ぶ(クリックで値を変えたときも)。"""
        if self.onDrag is None:
            return
        if self._dragging:
            run(self.onDrag, value)
        else:
            with undoChunk("animBarSlider"):
                if self.onPress is not None:
                    run(self.onPress)
                run(self.onDrag, value)


class AnimBar(QtWidgets.QWidget):
    """Anim Bar の本体。

    Args:
        parent (QtWidgets.QWidget | None): 親。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnimBar")
        self.setStyleSheet(_STYLE)
        self.setAttribute(QtCore.Qt.WA_StyledBackground, True)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(4)
        self.session = None
        for build in (self._tween, self._keyTransform, self._tangents, self._time, self._pose, self._space,
                      self._view):
            layout.addWidget(build())
        self.sets = Section("Sets")
        layout.addWidget(self.sets)
        layout.addStretch(1)
        self.refreshSets()
        self._job = cmds.scriptJob(event=("SceneOpened", self.refreshSets), protected=True)

    # --- セクション -----------------------------------------------------------------

    def _tween(self):
        """ツイーンのスライダーと決まった比率のボタン。"""
        section = Section("Tween")
        section.button("keyPrevious", "Copy the previous key", lambda: tween.copyNeighborKey(-1))
        slider = UndoSlider(-50, 150, 50)
        slider.setToolTip("Tween between the previous and next keys (drag past the ends to overshoot)")
        slider.onDrag = lambda value: tween.tween(value / 100.0)
        section.widget(slider)
        section.button("keyNext", "Copy the next key", lambda: tween.copyNeighborKey(1))
        section.button("tween", "Tween presets", menu=self._tween_menu)
        return section

    def _tween_menu(self, menu):
        """ツイーンの決まった比率。"""
        for percent in (-30, -10, 10, 25, 33, 50, 66, 75, 90, 110, 130):
            _action(menu, "Tween {}%".format(percent), functools.partial(tween.tween, percent / 100.0))

    def _keyTransform(self):
        """キーの変形のスライダー・モード・細かい足し引き。"""
        section = Section("Keys")
        self.mode = QtWidgets.QComboBox()
        for name, label in keyTransform.MODES:
            self.mode.addItem(label, name)
        self.mode.setToolTip("Key transform mode")
        section.widget(self.mode)
        slider = UndoSlider(-100, 100, 0, snapBack=0)
        slider.setToolTip("Drag to transform the selected keys toward the mode's goal")
        slider.onPress = self._start_session
        slider.onDrag = lambda value: self.session.apply(value / 100.0) if self.session else None
        section.widget(slider)
        section.button("range", "Blend frames (left/right)", menu=self._frame_menu)
        section.button("minus", "Subtract the step from the selected keys",
                       lambda: keyTransform.nudgeValue(-self.step.value()))
        self.step = QtWidgets.QDoubleSpinBox()
        self.step.setRange(0.001, 1000)
        self.step.setDecimals(3)
        self.step.setValue(1.0)
        self.step.setFixedWidth(64)
        self.step.setToolTip("Step for precise value changes")
        section.widget(self.step)
        section.button("add", "Add the step to the selected keys", lambda: keyTransform.nudgeValue(self.step.value()))
        return section

    def _start_session(self):
        """スライダーを押したときに、選んだキーの開始時の値を覚える。"""
        self.session = keyTransform.KeySession(self.mode.currentData(), seed=int(Time.getCurrent() * 1000))

    def _frame_menu(self, menu):
        """blendToFrame の左右の時刻。"""
        for side in ("left", "right"):
            frame = keyTransform.getBlendFrame(side)
            label = "Set {} frame to current ({})".format(side.title(), "unset" if frame is None else "{:g}".format(frame))
            _action(menu, label, functools.partial(keyTransform.setBlendFrame, side))

    def _tangents(self):
        """接線のボタン。"""
        section = Section("Tangents")
        for kind in tangents.MAYA_TYPES + tangents.COMPUTED_TYPES:
            section.button("tangent_" + kind, "{} tangent".format(kind.title()),
                           functools.partial(tangents.setTangent, kind),
                           menu=functools.partial(self._tangent_menu, kind))
        return section

    def _tangent_menu(self, kind, menu):
        """接線の入力側・出力側だけの設定。"""
        _action(menu, "In tangent only", functools.partial(tangents.setTangent, kind, "in"))
        _action(menu, "Out tangent only", functools.partial(tangents.setTangent, kind, "out"))

    def _time(self):
        """キーの時間・再生範囲・プレイブラスト。"""
        section = Section("Time")
        section.button("nudgeLeft", "Move keys one frame earlier", lambda: timing.nudgeKeys(-1),
                       menu=functools.partial(self._nudge_menu, -1))
        section.button("nudgeRight", "Move keys one frame later", lambda: timing.nudgeKeys(1),
                       menu=functools.partial(self._nudge_menu, 1))
        section.button("insert", "Insert a frame after the current time", lambda: timing.insertFrames(1))
        section.button("remove", "Remove a frame after the current time", lambda: timing.insertFrames(-1))
        section.button("share", "Share keys between the selected objects", timing.shareKeys,
                       menu=lambda menu: _action(menu, "Share only the selected keys",
                                                 lambda: timing.shareKeys(selectedOnly=True)))
        section.button("jumpPrevious", "Jump to the previous key", lambda: timeline.jumpToKey(-1))
        section.button("jumpNext", "Jump to the next key", lambda: timeline.jumpToKey(1))
        section.button("range", "Fit the playback range to the selected keys", timeline.frameSelectedKeys,
                       menu=self._range_menu)
        section.button("playblast", "Playblast the viewport", timeline.playblast, menu=self._playblast_menu)
        return section

    def _nudge_menu(self, direction, menu):
        """キーを動かす量と、シーン全体を動かす操作。"""
        for frames in (2, 5, 10):
            _action(menu, "Move {} frames".format(frames * direction), functools.partial(timing.nudgeKeys, frames * direction))
        _action(menu, "Move every key at the current time in the scene",
                functools.partial(timing.nudgeKeys, direction, True))

    def _range_menu(self, menu):
        """保存した再生範囲。"""
        _action(menu, "Save current range...", self._save_range)
        ranges = timeline.savedRanges()
        if ranges:
            menu.addSeparator()
            for name, (start, end) in sorted(ranges.items()):
                _action(menu, "{}  ({:g}-{:g})".format(name, start, end), functools.partial(timeline.useRange, name))
            remove = menu.addMenu("Remove")
            for name in sorted(ranges):
                _action(remove, name, functools.partial(timeline.removeRange, name))
            _action(remove, "Remove all", timeline.removeRange)

    def _save_range(self):
        """名前を聞いて再生範囲を保存する。"""
        name, ok = QtWidgets.QInputDialog.getText(self, "Save Range", "Range name:")
        if ok:
            timeline.saveRange(name.strip() or None)

    def _playblast_menu(self, menu):
        """カメラを選んでのプレイブラスト・直前の再生・カメラの複製。"""
        for camera in cmds.listCameras(perspective=True) or []:
            _action(menu, "Playblast " + camera, functools.partial(timeline.playblast, camera))
        menu.addSeparator()
        _action(menu, "Play last playblast", timeline.playLastPlayblast)
        _action(menu, "Duplicate selected camera (baked)", timeline.duplicateCamera)

    def _pose(self):
        """ポーズ・アニメーションのコピー。"""
        section = Section("Pose")
        section.button("reset", "Reset the selected channels to defaults", timing.resetValues,
                       menu=self._reset_menu)
        section.button("mirror", "Mirror the pose to the opposite side", lambda: mirror.mirrorPose(mode="mirror"),
                       menu=lambda menu: _action(menu, "Copy the opposite side onto the selection",
                                                 lambda: mirror.mirrorPose(mode="self")))
        section.button("flip", "Swap the poses of both sides", lambda: mirror.mirrorPose(mode="flip"))
        section.button("transformAll", "Apply the change at this frame to every key", timing.transformAll)
        section.button("copy", "Copy animation", animCopy.copyAnimation,
                       menu=lambda menu: _action(menu, "Copy the playback range only",
                                                 lambda: animCopy.copyAnimation(timeRange=Time.getPlaybackRange())))
        section.button("paste", "Paste animation onto the selection", animCopy.pasteAnimation, menu=self._paste_menu)
        return section

    def _reset_menu(self, menu):
        """リセットするアトリビュートの組。"""
        for label, names in (("Translate", ["translate"]), ("Rotate", ["rotate"]), ("Scale", ["scale"]),
                             ("Translate, Rotate and Scale", ["translate", "rotate", "scale"])):
            _action(menu, "Reset " + label, functools.partial(timing.resetValues, None, names))

    def _paste_menu(self, menu):
        """貼付けのしかた。"""
        _action(menu, "Paste in place (start at the current frame)", lambda: animCopy.pasteAnimation(inPlace=True))
        _action(menu, "Paste to another character (match names)", lambda: animCopy.pasteAnimation(mode="name"))
        _action(menu, "Paste mirrored (invert cycle)", lambda: animCopy.pasteAnimation(invertCycle=True))

    def _space(self):
        """位置合わせ・スペース切替・仮のピボット・仮のコンストレイント。"""
        section = Section("Space")
        section.button("align", "Align the selection to the last selected object", spaceTools.align,
                       menu=self._align_menu)
        section.button("space", "Switch space keeping the world position", self._switch_space)
        section.button("pivot", "Create a temporary pivot", spaceTools.createTempPivot,
                       menu=lambda menu: _action(menu, "Clear temporary pivots", spaceTools.clearTempPivots))
        section.button("follow", "Make the selection follow the last selected object (baked)",
                       spaceTools.fakeConstraint,
                       menu=lambda menu: _action(menu, "Follow on the master's keys only",
                                                 lambda: spaceTools.fakeConstraint(rangeMode="keys")))
        return section

    def _align_menu(self, menu):
        """位置合わせの内容と範囲。"""
        _action(menu, "Align position only", lambda: spaceTools.align(rotate=False))
        _action(menu, "Align rotation only", lambda: spaceTools.align(translate=False))
        _action(menu, "Align on the target's keys", lambda: spaceTools.align(rangeMode="keys"))
        _action(menu, "Align over the playback range", lambda: spaceTools.align(rangeMode="range"))

    def _switch_space(self):
        """スペース切替のアトリビュートと値を聞いて切り替える。"""
        nodes = keys.selectedNodes()
        if not nodes:
            raise ValueError("Select a control with a space attribute")
        node = nodes[0]
        names = [plug.getLongName() for plug in node.getPlugs(userDefined=True) if plug.getType() == "enum"]
        if not names:
            raise ValueError("The control has no enum attribute to switch")
        name, ok = QtWidgets.QInputDialog.getItem(self, "Switch Space", "Attribute:", names, 0, False)
        if not ok:
            return
        choices = node.getPlug(name).getEnumNames()
        value, ok = QtWidgets.QInputDialog.getItem(self, "Switch Space", "Space:", choices, 0, False)
        if not ok:
            return
        ranges = ["Current frame", "On the control's keys", "Playback range"]
        span, ok = QtWidgets.QInputDialog.getItem(self, "Switch Space", "Frames:", ranges, 0, False)
        if ok:
            spaceTools.switchSpace(node, name, choices.index(value), ("current", "keys", "range")[ranges.index(span)])

    def _view(self):
        """モーショントレイル・細かい移動・タンブル・退避。"""
        section = Section("View")
        section.button("trail", "Create motion trails", viewTools.createMotionTrails,
                       menu=lambda menu: _action(menu, "Clear motion trails", viewTools.clearMotionTrails))
        micro = section.button("micro", "Micro transform (smaller manipulator steps)", None,
                               menu=self._micro_menu, checkable=True)
        micro.clicked.disconnect()
        micro.toggled.connect(lambda state: run(viewTools.setMicroTransform, state))
        tumble = section.button("tumble", "Tumble around the selection", checkable=True)
        tumble.setChecked(run(viewTools.isTumbleOnObjects) or False)
        tumble.toggled.connect(lambda state: run(viewTools.setTumbleOnObjects, state))
        recovery = section.button("recovery", "Animation backup", None, menu=self._recovery_menu, checkable=True)
        recovery.clicked.disconnect()
        recovery.toggled.connect(lambda state: run(crashRecovery.setEnabled, state))
        return section

    def _micro_menu(self, menu):
        """細かい移動の倍率。"""
        for factor in viewTools.MICRO_FACTORS:
            _action(menu, "Step x{:g}".format(factor), functools.partial(viewTools.setMicroFactor, factor))

    def _recovery_menu(self, menu):
        """退避の操作。"""
        _action(menu, "Back up now", lambda: _message("Backed up {} curves".format(crashRecovery.backup())))
        if crashRecovery.hasBackup():
            _action(menu, "Restore the backup", crashRecovery.restore)
            _action(menu, "Discard the backup", crashRecovery.discard)

    # --- 選択セット -----------------------------------------------------------------

    def refreshSets(self):
        """選択セットのボタンを作り直す。"""
        layout = self.sets.layout_
        while layout.count() > 1:
            item = layout.takeAt(1)
            if item.widget():
                item.widget().deleteLater()
        for node in run(selectSets.sets) or []:
            button = QtWidgets.QToolButton(self.sets)
            button.setObjectName("AnimBarSet")
            button.setText(selectSets.label(node))
            color = icons.SET_COLORS[selectSets.color(node) % len(icons.SET_COLORS)]
            button.setStyleSheet("QToolButton#AnimBarSet {{ background: {}; }}".format(color))
            button.setToolTip("Click to select, Shift to add, Ctrl to remove\nRight click for options")
            button.clicked.connect(lambda *_, target=node: self._select_set(target))
            button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda position, target=node, owner=button: self._set_menu(target, owner, position))
            layout.addWidget(button)
        add = self.sets.button("add", "Create a select set from the selection", self._create_set,
                               menu=self._sets_menu)
        return add

    def _select_set(self, node):
        """修飾キーに応じて選択セットを選ぶ。"""
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        mode = "add" if modifiers & QtCore.Qt.ShiftModifier else "remove" if modifiers & QtCore.Qt.ControlModifier \
            else "replace"
        run(selectSets.selectSet, node, mode)

    def _create_set(self):
        """名前を聞いて選択セットを作る。"""
        name, ok = QtWidgets.QInputDialog.getText(self, "Select Set", "Set name:")
        if ok and name.strip():
            selectSets.createSet(name, colorIndex=len(selectSets.sets()))
            self.refreshSets()

    def _set_menu(self, node, owner, position):
        """選択セットの編集メニュー。"""
        menu = QtWidgets.QMenu(owner)
        _action(menu, "Add selection", lambda: selectSets.editSet(node, add=keys.selectedNodes()))
        _action(menu, "Remove selection", lambda: selectSets.editSet(node, remove=keys.selectedNodes()))
        _action(menu, "Rename...", lambda: self._rename_set(node))
        colors = menu.addMenu("Color")
        for index in range(len(icons.SET_COLORS)):
            action = _action(colors, "Color {}".format(index + 1),
                             functools.partial(self._recolor_set, node, index))
            action.setIcon(self._swatch(icons.SET_COLORS[index]))
        menu.addSeparator()
        _action(menu, "Delete", lambda: (selectSets.deleteSet(node), self.refreshSets()))
        menu.exec_(owner.mapToGlobal(position))

    def _rename_set(self, node):
        """表示名を聞いて変える。"""
        name, ok = QtWidgets.QInputDialog.getText(self, "Select Set", "New name:", text=selectSets.label(node))
        if ok and name.strip():
            selectSets.editSet(node, name=name)
            self.refreshSets()

    def _recolor_set(self, node, index):
        """色を変える。"""
        selectSets.editSet(node, colorIndex=index)
        self.refreshSets()

    @staticmethod
    def _swatch(value):
        """色見本のアイコン。"""
        pixmap = QtGui.QPixmap(12, 12)
        pixmap.fill(QtGui.QColor(value))
        return QtGui.QIcon(pixmap)

    def _sets_menu(self, menu):
        """選択セット全体の操作。"""
        _action(menu, "Refresh", self.refreshSets)
        _action(menu, "Export select sets...", self._export_sets)
        _action(menu, "Import select sets...", self._import_sets)

    def _export_sets(self):
        """書き出し先を聞いて書き出す。"""
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Export Select Sets", "", "JSON (*.json)")
        if path:
            _message("Exported {} select sets".format(selectSets.exportSets(path)))

    def _import_sets(self):
        """ファイルを聞いて読み込む。"""
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Import Select Sets", "", "JSON (*.json)")
        if path:
            namespace, ok = QtWidgets.QInputDialog.getText(self, "Import Select Sets", "Namespace (optional):")
            if ok:
                selectSets.importSets(path, namespace.strip())
                self.refreshSets()

    def closeEvent(self, event):
        """閉じるときに scriptJob を外す。"""
        if cmds.scriptJob(exists=self._job):
            cmds.scriptJob(kill=self._job, force=True)
        super().closeEvent(event)


def _build():
    """workspaceControl の中にバーを作る(uiScript からも呼ぶ)。

    Returns:
        AnimBar | None: 作ったバー。workspaceControl が見つからなければNone。
    """
    pointer = omui.MQtUtil.findControl(CONTROL)
    if pointer is None:
        return None
    parent = wrapInstance(int(pointer), QtWidgets.QWidget)
    existing = parent.findChildren(AnimBar)
    if existing:
        # workspaceControl の作成時に uiScript が組み立て済みなら、二重に作らない。
        _bar["widget"] = existing[0]
        return existing[0]
    layout = parent.layout()
    if layout is None:
        layout = QtWidgets.QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    widget = AnimBar(parent)
    layout.addWidget(widget)
    _bar["widget"] = widget
    return widget


def show():
    """バーをタイムスライダーの上にドックして表示する。

    Returns:
        str: workspaceControl の名前。
    """
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.deleteUI(CONTROL)
    cmds.workspaceControl(CONTROL, label="Anim Bar", retain=False, floating=False,
                          dockToControl=("TimeSlider", "top"), initialHeight=HEIGHT, heightProperty="fixed",
                          uiScript="import animBar.ui.bar as _bar; _bar._build()",
                          visibleChangeCommand=_remember_visibility)
    _build()
    cmds.optionVar(intValue=(VISIBLE_OPTION, 1))
    return CONTROL


def hide():
    """バーを閉じる。

    Returns:
        None: 値を返さない。
    """
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.deleteUI(CONTROL)
    _bar["widget"] = None
    cmds.optionVar(intValue=(VISIBLE_OPTION, 0))


def toggle():
    """バーの表示・非表示を切り替える。

    Returns:
        bool: 表示したらTrue。
    """
    if cmds.workspaceControl(CONTROL, exists=True) and cmds.workspaceControl(CONTROL, query=True, visible=True):
        hide()
        return False
    show()
    return True


def wasVisible():
    """前回の表示状態を返す(未設定なら表示)。

    Returns:
        bool: 表示していたらTrue。
    """
    return not cmds.optionVar(exists=VISIBLE_OPTION) or bool(cmds.optionVar(query=VISIBLE_OPTION))


def _remember_visibility(*_):
    """表示状態を optionVar へ覚える(workspaceControl の閉じるボタン用)。"""
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.optionVar(intValue=(VISIBLE_OPTION, int(cmds.workspaceControl(CONTROL, query=True, visible=True))))

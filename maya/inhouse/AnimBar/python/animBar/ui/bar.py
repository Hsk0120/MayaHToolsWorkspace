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
from . import icons, preferences
from .qt import QtCore, QtGui, QtWidgets, wrapInstance

#: workspaceControl の名前。
CONTROL = "AnimBarWorkspaceControl"

#: 表示状態を覚える optionVar の名前。
VISIBLE_OPTION = "animBarVisible"

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

#: キーを対象にするボタンの共通の説明。
_KEY_TARGETS = ("Works on the keys selected in the Graph Editor / Dope Sheet, the range selected\n"
                "in the Time Slider (Shift+drag), or else the selected objects' keys at the current frame.")

#: メニューの項目向けの短い共通の説明。
_KEY_TARGETS_SHORT = "Works on the selected keys, or the keys at the current frame."

#: キー変形のモードごとの説明(コンボボックスの項目のツールチップ)。
_MODE_TIPS = {
    "blendToNeighbors": "Right: toward the next key. Left: toward the previous key.",
    "blendToDefault": "Right: toward the attribute's default value. Left: push away from it.",
    "blendToFrame": "Toward the values at the Left/Right frames set with the frame button.",
    "blendToMirror": "Toward the opposite side control's value at the same frame.",
    "pushPull": "Right: exaggerate away from the line between the neighbor keys. Left: flatten toward it.",
    "easeInOut": "Keep both ends of the selection and reshape the keys between. Right: ease in. Left: ease out.",
    "noise": "Add random noise. The slider sets the strength.",
    "scaleFromLeft": "Scale the value range around the unselected key before the selection.",
    "scaleFromRight": "Scale the value range around the unselected key after the selection.",
    "scaleFromAverage": "Scale the value range around the average of the selected keys.",
    "scaleFromDefault": "Scale the value range around the attribute's default value.",
}

#: 接線の種類ごとの説明。
_TANGENT_TIPS = {
    "auto": "Maya's Auto tangent: smooth, without overshooting the key values.",
    "spline": "Maya's Spline tangent: smooth curve through the keys.",
    "linear": "Maya's Linear tangent: straight lines between the keys.",
    "flat": "Maya's Flat tangent: horizontal tangents (the motion stops at the key).",
    "step": "Maya's Stepped tangent: hold the value until the next key (for blocking).",
    "clamped": "Maya's Clamped tangent: spline, but flat when neighbor values are equal.",
    "plateau": "Maya's Plateau tangent: spline, but flat at peaks, valleys and the first/last keys.",
    "flow": "Tangent along the line between the previous and next keys (flat at the first/last keys).",
    "bounce": "Flat at peaks and valleys, flow everywhere else (good for bounces and impacts).",
}


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
        self.title = title
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
        size = preferences.iconSize()
        button.setIcon(icons.icon(iconName, size))
        button.setIconSize(QtCore.QSize(size, size))
        # 右クリックの説明を書いていないボタンにだけ、右クリックで選べることを添える。
        hint = menu is not None and callback is not None and "Right click" not in tip
        button.setToolTip(tip + ("\n\nRight click for more options" if hint else ""))
        button.setCheckable(checkable)
        if callback is not None:
            button.clicked.connect(lambda *_: run(callback))
        if menu is not None:
            # 確認用のスクリプト(guiCheck)がメニューを組み立てて調べられるように、作る関数を持たせる。
            button.menuBuilder = menu

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


def _action(menu, label, callback, checked=None, tip=None):
    """メニューの項目を足す。

    Args:
        menu (QtWidgets.QMenu): メニュー。
        label (str): 表示名。
        callback (Callable): 選んだときの処理。
        checked (bool | None): チェック付きの項目にするなら状態。
        tip (str | None): 項目にマウスを乗せたときの説明。

    Returns:
        QtWidgets.QAction: 足した項目。
    """
    action = menu.addAction(label)
    if checked is not None:
        action.setCheckable(True)
        action.setChecked(checked)
    if tip:
        # QMenu は既定で項目のツールチップを出さないため、説明を付けるメニューでは表示を有効にする。
        menu.setToolTipsVisible(True)
        action.setToolTip(tip)
    action.triggered.connect(lambda *_: run(callback))
    return action


def _submenu(menu, label, tip):
    """説明付きのサブメニューを足す。

    Args:
        menu (QtWidgets.QMenu): 親のメニュー。
        label (str): 表示名。
        tip (str): サブメニューの項目にマウスを乗せたときの説明。

    Returns:
        QtWidgets.QMenu: 足したサブメニュー。
    """
    submenu = menu.addMenu(label)
    menu.setToolTipsVisible(True)
    submenu.menuAction().setToolTip(tip)
    return submenu


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


def _global_pos(event):
    """マウスのイベントの画面上の座標を返す(PySide6 と PySide2 の違いを吸収する)。

    Args:
        event (QtGui.QMouseEvent): マウスのイベント。

    Returns:
        QtCore.QPoint: 画面上の座標。
    """
    if hasattr(event, "globalPosition"):
        return event.globalPosition().toPoint()
    return event.globalPos()


class DockGrip(QtWidgets.QWidget):
    """左端のつまみ。ドラッグでバーをドックから外して動かし、ダブルクリックで浮動とドックを切り替える。

    見出しのタブの行を隠しているので、タイムスライダー等と同じ点線のつまみをドックから外す入口にする。
    外した後の浮動の窓は、Mayaの窓と同じくタブをドラッグしてほかの場所へドックできる。

    Args:
        parent (QtWidgets.QWidget | None): 親。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnimBarGrip")
        self.setFixedWidth(10)
        self.setCursor(QtCore.Qt.SizeAllCursor)
        self.setToolTip("Move Anim Bar\n"
                        "Drag to undock the bar and move it as a floating window.\n"
                        "Double-click to float it, or to dock it above the Time Slider again.\n\n"
                        "Right click for more options")
        self.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._popup)
        # 押した位置(画面上)と、ドラッグ中の浮動の窓の左上から見たつかんだ点。
        self._press = None
        self._offset = None

    def paintEvent(self, event):
        """2列の点を描く。"""
        painter = QtGui.QPainter(self)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(icons.color("muted"))
        for x in (3, 7):
            for y in range(5, self.height() - 4, 4):
                painter.drawRect(QtCore.QRectF(x - 0.75, y, 1.5, 1.5))
        painter.end()

    def mousePressEvent(self, event):
        """左ボタンを押した位置を覚える。"""
        if event.button() == QtCore.Qt.LeftButton:
            self._press = _global_pos(event)
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        """少し動かしたらドックから外し、その後は浮動の窓をマウスに付いて動かす。"""
        position = _global_pos(event)
        if self._offset is not None:
            self.window().move(position - self._offset)
            return
        if self._press is None or \
                (position - self._press).manhattanLength() < QtWidgets.QApplication.startDragDistance():
            return
        self._press = None
        if not isFloating():
            run(setFloating, True)
        window = self.window()
        # つかんだ点がマウスの下に来るように窓を寄せ、窓が替わってもマウスを受け取り続けるようにつかむ。
        self._offset = self.mapTo(window, QtCore.QPoint(self.width() // 2, self.height() // 2))
        window.move(position - self._offset)
        self.grabMouse()

    def mouseReleaseEvent(self, event):
        """ドラッグを終える。"""
        if self._offset is not None:
            self._offset = None
            self.releaseMouse()
        self._press = None
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        """浮動とドックを切り替える。"""
        if event.button() == QtCore.Qt.LeftButton:
            run(setFloating, not isFloating())

    def _popup(self, position):
        """右クリックのメニュー。"""
        menu = QtWidgets.QMenu(self)
        if isFloating():
            _action(menu, "Dock above the Time Slider", lambda: setFloating(False),
                    tip="Put the bar back above the Time Slider.")
        else:
            _action(menu, "Float", lambda: setFloating(True), tip="Undock the bar into a floating window.")
        _action(menu, "Settings...", openSettings, tip="Open the Anim Bar settings.")
        menu.addSeparator()
        _action(menu, "Close", hide, tip="Hide the Anim Bar. Show it again from Windows > Anim Bar.")
        menu.exec_(self.mapToGlobal(position))


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
        layout.setContentsMargins(0, 2, 4, 2)
        layout.setSpacing(4)
        self.session = None
        layout.addWidget(DockGrip(self))
        layout.addWidget(self._settings_button())
        #: 見出しから区切りへの辞書(設定の画面で表示・非表示を切り替える)。
        self.sections = {}
        for build in (self._tween, self._keyTransform, self._tangents, self._time, self._pose, self._space,
                      self._view):
            section = build()
            self.sections[section.title] = section
            layout.addWidget(section)
        self.sets = Section("Sets")
        self.sections["Sets"] = self.sets
        layout.addWidget(self.sets)
        layout.addStretch(1)
        self.refreshSets()
        self.applyPreferences()
        self._job = cmds.scriptJob(event=("SceneOpened", self.refreshSets), protected=True)

    def _settings_button(self):
        """設定の画面を開く歯車のボタン。"""
        button = QtWidgets.QToolButton(self)
        button.setObjectName("AnimBarSettings")
        size = preferences.iconSize()
        button.setIcon(icons.icon("settings", size))
        button.setIconSize(QtCore.QSize(size, size))
        button.setToolTip("Anim Bar Settings\n"
                          "Choose which sections to show, the button size, the playblast options,\n"
                          "the animation backup and the micro transform step, or reset them to the defaults.")
        button.clicked.connect(lambda *_: run(openSettings))
        return button

    def applyPreferences(self):
        """覚えた設定のうち、作り直さずに変えられるもの(区切りの表示・退避のボタン)を反映する。

        Returns:
            None: 値を返さない。
        """
        hidden = preferences.hiddenSections()
        for title, section in self.sections.items():
            section.setVisible(title not in hidden)
        self.recovery.blockSignals(True)
        self.recovery.setChecked(crashRecovery.isEnabled())
        self.recovery.blockSignals(False)

    # --- セクション -----------------------------------------------------------------

    def _tween(self):
        """ツイーンのスライダーと決まった比率のボタン。"""
        section = Section("Tween")
        section.button("keyPrevious", "Copy Previous Key\n"
                       "Set the keys at the current frame to the values of the previous key.\n"
                       "Uses the selected Graph Editor keys, or else the selected objects.",
                       lambda: tween.copyNeighborKey(-1))
        slider = UndoSlider(-50, 150, 50)
        slider.setToolTip("Tween\n"
                          "Drag to set the selected objects at the current frame between the previous key (left)\n"
                          "and the next key (right). The middle is 50%. Drag past the ends to overshoot.\n"
                          "Creates keys where needed. Attributes without both neighbor keys are left unchanged.\n"
                          "One drag is one undo.")
        slider.onDrag = lambda value: tween.tween(value / 100.0)
        section.widget(slider)
        section.button("keyNext", "Copy Next Key\n"
                       "Set the keys at the current frame to the values of the next key.\n"
                       "Uses the selected Graph Editor keys, or else the selected objects.",
                       lambda: tween.copyNeighborKey(1))
        section.button("tween", "Tween Presets\n"
                       "Click to choose a fixed tween ratio (-30% to 130%), or extend the motion line\n"
                       "of the previous/next two keys into the current frame.", menu=self._tween_menu)
        return section

    def _tween_menu(self, menu):
        """ツイーンの決まった比率。"""
        for percent in (-30, -10, 10, 25, 33, 50, 66, 75, 90, 110, 130):
            if percent < 0 or percent > 100:
                detail = "Overshoot past the {} key.".format("previous" if percent < 0 else "next")
            else:
                detail = "0% is the previous key, 100% is the next key."
            _action(menu, "Tween {}%".format(percent), functools.partial(tween.tween, percent / 100.0),
                    tip="Set the current frame {}% of the way from the previous key to the next key.\n{}"
                    .format(percent, detail))
        menu.addSeparator()
        _action(menu, "Extend the line of the previous two keys", lambda: tween.tweenLinear(-1),
                tip="Continue the motion of the two keys before the current frame in a straight line\n"
                    "and key the result at the current frame.")
        _action(menu, "Extend the line of the next two keys", lambda: tween.tweenLinear(1),
                tip="Trace the motion of the two keys after the current frame back in a straight line\n"
                    "and key the result at the current frame.")

    def _keyTransform(self):
        """キーの変形のスライダー・モード・細かい足し引き。"""
        section = Section("Keys")
        self.mode = QtWidgets.QComboBox()
        for name, label in keyTransform.MODES:
            self.mode.addItem(label, name)
            self.mode.setItemData(self.mode.count() - 1, _MODE_TIPS.get(name, ""), QtCore.Qt.ToolTipRole)
        self.mode.setToolTip("Key Transform Mode\n"
                             "Choose what the slider next to it does. Hover over each item for details.")
        section.widget(self.mode)
        slider = UndoSlider(-100, 100, 0, snapBack=0)
        slider.setToolTip("Key Transform\n"
                          "Drag left or right to change the keys by the chosen mode. The slider returns to\n"
                          "the center when released, and one drag is one undo.\n"
                          + _KEY_TARGETS + "\n"
                          "Hold Shift when pressing to scale from the average, Ctrl to blend to the default.")
        slider.onPress = self._start_session
        slider.onDrag = lambda value: self.session.apply(value / 100.0) if self.session else None
        section.widget(slider)
        section.button("range", "Blend Frames\n"
                       "Click to store the current frame as the Left or Right frame used by the Frame mode.",
                       menu=self._frame_menu)
        section.button("minus", "Subtract Step\n"
                       "Subtract the step value from the keys.\n" + _KEY_TARGETS,
                       lambda: keyTransform.nudgeValue(-self.step.value()))
        self.step = QtWidgets.QDoubleSpinBox()
        self.step.setRange(0.001, 1000)
        self.step.setDecimals(3)
        self.step.setValue(1.0)
        self.step.setFixedWidth(64)
        self.step.setToolTip("Step\n"
                             "The amount the - and + buttons subtract or add. Angles are in degrees, distances in cm.")
        section.widget(self.step)
        section.button("add", "Add Step\n"
                       "Add the step value to the keys.\n" + _KEY_TARGETS,
                       lambda: keyTransform.nudgeValue(self.step.value()))
        return section

    def _start_session(self):
        """スライダーを押したときに、選んだキーの開始時の値を覚える(修飾キーでモードを一時的に替える)。"""
        self.session = keyTransform.KeySession(self._session_mode(), seed=int(Time.getCurrent() * 1000))

    def _session_mode(self):
        """押した修飾キーに合わせたモードを返す(Shift は平均から拡大・縮小、Ctrl は既定値へ近づける)。"""
        modifiers = QtWidgets.QApplication.keyboardModifiers()
        if modifiers & QtCore.Qt.ShiftModifier:
            return "scaleFromAverage"
        if modifiers & QtCore.Qt.ControlModifier:
            return "blendToDefault"
        return self.mode.currentData()

    def _frame_menu(self, menu):
        """blendToFrame の左右の時刻。"""
        for side in ("left", "right"):
            frame = keyTransform.getBlendFrame(side)
            label = "Set {} frame to current ({})".format(side.title(), "unset" if frame is None else "{:g}".format(frame))
            _action(menu, label, functools.partial(keyTransform.setBlendFrame, side),
                    tip="Store the current frame as the {} frame. In the Frame mode, dragging the slider {}\n"
                        "blends the keys toward the values at this frame.".format(side, side))

    def _tangents(self):
        """接線のボタン。"""
        section = Section("Tangents")
        for kind in tangents.MAYA_TYPES + tangents.COMPUTED_TYPES:
            section.button("tangent_" + kind, "{} Tangent\n{}\n{}".format(kind.title(), _TANGENT_TIPS.get(kind, ""),
                                                                          _KEY_TARGETS),
                           functools.partial(tangents.setTangent, kind),
                           menu=functools.partial(self._tangent_menu, kind))
        return section

    def _tangent_menu(self, kind, menu):
        """接線の入力側・出力側だけの設定と、対象のキーの選び方。"""
        _action(menu, "In tangent only", functools.partial(tangents.setTangent, kind, "in"),
                tip="Change only the tangent coming into the keys (left side). " + _KEY_TARGETS_SHORT)
        _action(menu, "Out tangent only", functools.partial(tangents.setTangent, kind, "out"),
                tip="Change only the tangent leaving the keys (right side). " + _KEY_TARGETS_SHORT)
        menu.addSeparator()
        _action(menu, "First key of each curve", functools.partial(tangents.setTangent, kind, scope="first"),
                tip="Change the first key of every animated attribute of the selected objects\n"
                    "(the first key inside the range selected in the Time Slider, if any).")
        _action(menu, "Last key of each curve", functools.partial(tangents.setTangent, kind, scope="last"),
                tip="Change the last key of every animated attribute of the selected objects\n"
                    "(the last key inside the range selected in the Time Slider, if any).")
        _action(menu, "Every key (or the highlighted range)", functools.partial(tangents.setTangent, kind, scope="all"),
                tip="Change every key of the selected objects, or only the keys inside the range\n"
                    "selected in the Time Slider.")

    def _time(self):
        """キーの時間・再生範囲・プレイブラスト。"""
        section = Section("Time")
        nudge = ("\n" + _KEY_TARGETS + "\n"
                 "Keys that would hit an unselected neighbor key are not moved. When moving the keys at the\n"
                 "current frame, the current frame follows them.")
        section.button("nudgeLeft", "Nudge Keys Earlier\nMove the keys one frame earlier." + nudge,
                       lambda: timing.nudgeKeys(-1), menu=functools.partial(self._nudge_menu, -1))
        section.button("nudgeRight", "Nudge Keys Later\nMove the keys one frame later." + nudge,
                       lambda: timing.nudgeKeys(1), menu=functools.partial(self._nudge_menu, 1))
        section.button("insert", "Insert Frame\n"
                       "Move every key of the selected objects after the current frame one frame later\n"
                       "to make room.", lambda: timing.insertFrames(1))
        section.button("remove", "Remove Frame\n"
                       "Move every key of the selected objects after the current frame one frame earlier.\n"
                       "Nothing changes if a key would overlap a key at or before the current frame.",
                       lambda: timing.insertFrames(-1))
        section.button("share", "Share Keys\n"
                       "Key every animated attribute of the selected objects at every frame where any of them\n"
                       "has a key. The new keys keep the curve shapes (values do not change).", timing.shareKeys,
                       menu=lambda menu: _action(menu, "Share only the selected keys",
                                                 lambda: timing.shareKeys(selectedOnly=True),
                                                 tip="Use only the frames of the keys selected in the Graph Editor\n"
                                                     "and key every selected object at those frames."))
        section.button("jumpPrevious", "Jump to Previous Key\n"
                       "Move the current frame to the previous key of the selected objects.",
                       lambda: timeline.jumpToKey(-1),
                       menu=lambda menu: (
                           _action(menu, "Jump to the selected keys", lambda: timeline.jumpToKey(0),
                                   tip="Move the current frame to the average frame of the keys selected in the\n"
                                       "Graph Editor, or else to the first key of the selected objects."),
                           _action(menu, "Follow the selected keys",
                                   lambda: timeline.setJumpToSelectedKey(not timeline.isJumpToSelectedKey()),
                                   checked=timeline.isJumpToSelectedKey(),
                                   tip="While checked, the current frame moves to the selected keys every time\n"
                                       "the key selection changes.")))
        section.button("jumpNext", "Jump to Next Key\n"
                       "Move the current frame to the next key of the selected objects.",
                       lambda: timeline.jumpToKey(1))
        section.button("range", "Fit Playback Range\n"
                       "Set the playback range to the selected Graph Editor keys, or else to all keys\n"
                       "of the selected objects. Right click to save and reuse named ranges.",
                       timeline.frameSelectedKeys, menu=self._range_menu)
        section.button("playblast", "Playblast\n"
                       "Playblast the playback range, or the range selected in the Time Slider.\n"
                       "Right click to choose a camera, play the last playblast or change the settings\n"
                       "(sound, HUD, overscan, size).", timeline.playblast, menu=self._playblast_menu)
        return section

    def _nudge_menu(self, direction, menu):
        """キーを動かす量と、シーン全体を動かす操作。"""
        for frames in (2, 5, 10):
            _action(menu, "Move {} frames".format(frames * direction), functools.partial(timing.nudgeKeys, frames * direction),
                    tip="Move the keys {} frames {}. {}".format(frames, "later" if direction > 0 else "earlier",
                                                                 _KEY_TARGETS_SHORT))
        _action(menu, "Move every key at the current time in the scene",
                functools.partial(timing.nudgeKeys, direction, True),
                tip="Move the keys at the current frame on every animation curve in the scene one frame {},\n"
                    "regardless of the selection.".format("later" if direction > 0 else "earlier"))

    def _range_menu(self, menu):
        """保存した再生範囲。"""
        _action(menu, "Save current range...", self._save_range,
                tip="Save the current playback range under a name, to switch back to it later from this menu.")
        ranges = timeline.savedRanges()
        if ranges:
            menu.addSeparator()
            for name, (start, end) in sorted(ranges.items()):
                _action(menu, "{}  ({:g}-{:g})".format(name, start, end), functools.partial(timeline.useRange, name),
                        tip="Set the playback range to frames {:g}-{:g}.".format(start, end))
            remove = _submenu(menu, "Remove", "Delete saved ranges.")
            for name in sorted(ranges):
                _action(remove, name, functools.partial(timeline.removeRange, name),
                        tip="Delete the saved range '{}'.".format(name))
            _action(remove, "Remove all", timeline.removeRange, tip="Delete every saved range.")

    def _save_range(self):
        """名前を聞いて再生範囲を保存する。"""
        name, ok = QtWidgets.QInputDialog.getText(self, "Save Range", "Range name:")
        if ok:
            timeline.saveRange(name.strip() or None)

    def _playblast_menu(self, menu):
        """カメラを選んでのプレイブラスト・直前の再生・カメラの複製。"""
        for camera in cmds.listCameras(perspective=True) or []:
            _action(menu, "Playblast " + camera, functools.partial(timeline.playblast, camera),
                    tip="Playblast through the camera '{}' instead of the active viewport's camera.".format(camera))
        menu.addSeparator()
        _action(menu, "Play last playblast", timeline.playLastPlayblast,
                tip="Play the movie made by the last playblast again.")
        _action(menu, "Duplicate selected camera (baked)", timeline.duplicateCamera,
                tip="Duplicate the selected camera as an independent camera with its animation baked on every\n"
                    "frame of the playback range (constraints and parents removed). Useful for layout checks.")
        menu.addSeparator()
        settings = timeline.playblastSettings()
        options = _submenu(menu, "Settings", "Options used by every playblast from this button (remembered).")
        _action(options, "Include sound", lambda: timeline.setPlayblastSettings(sound=not settings["sound"]),
                checked=settings["sound"], tip="Include the Time Slider's sound in the movie.")
        _action(options, "Show HUD and ornaments",
                lambda: timeline.setPlayblastSettings(showOrnaments=not settings["showOrnaments"]),
                checked=settings["showOrnaments"], tip="Include the heads-up display and other viewport ornaments.")
        _action(options, "Use the highlighted range",
                lambda: timeline.setPlayblastSettings(useRange=not settings["useRange"]), checked=settings["useRange"],
                tip="When a range is selected in the Time Slider (Shift+drag), playblast only that range.")
        overscan = _submenu(options, "Overscan", "Show more of the scene around the camera frame while playblasting.")
        for value in (None, 1.1, 1.2, 1.3):
            _action(overscan, "Keep camera setting" if value is None else "{:g}".format(value),
                    functools.partial(timeline.setPlayblastSettings, overscan=value),
                    checked=settings["overscan"] == value,
                    tip="Use the camera's own overscan." if value is None else
                    "Set the camera's overscan to {:g} during the playblast and restore it afterwards.".format(value))
        size = _submenu(options, "Size", "Movie size relative to the viewport size.")
        for percent in (50, 75, 100):
            _action(size, "{}%".format(percent), functools.partial(timeline.setPlayblastSettings, percent=percent),
                    checked=settings["percent"] == percent,
                    tip="Make the movie {}% of the viewport size.".format(percent))
        _action(options, "Load default settings", timeline.resetPlayblastSettings,
                tip="Return every playblast setting to its default.")

    def _mirror_menu(self, menu):
        """ミラーの右クリックメニュー(反対側から写す・反転するアトリビュートの規則)。"""
        _action(menu, "Copy the opposite side onto the selection", lambda: mirror.mirrorPose(mode="self"),
                tip="The reverse of Mirror Pose: copy the pose of the opposite side controls onto the selected ones.")
        menu.addSeparator()
        _action(menu, "Mirror animation (highlighted range or selected keys)",
                lambda: mirror.mirrorAnimation(mode="mirror"),
                tip="Copy the animation of the selected controls onto the opposite side. Uses the range selected\n"
                    "in the Time Slider, or else the range of the selected Graph Editor keys, or else all keys.\n"
                    "Keys of the opposite side outside the range are kept.")
        _action(menu, "Swap animation of both sides", lambda: mirror.mirrorAnimation(mode="flip"),
                tip="Exchange the animation of the selected controls and their opposite side controls\n"
                    "(same range rules as Mirror animation).")
        _action(menu, "Select the opposite side", mirror.selectOpposite,
                tip="Replace the selection with the opposite side controls.")
        _action(menu, "Add the opposite side to the selection", lambda: mirror.selectOpposite(add=True),
                tip="Keep the selection and also select the opposite side controls.")
        menu.addSeparator()
        rules = mirror.setInvertRules()
        for side, label, owner in (("side", "Invert on side controls", "left/right controls"),
                                   ("center", "Invert on center controls", "center controls (no opposite side)")):
            submenu = _submenu(menu, label, "Choose which attributes change sign when mirroring {}.".format(owner))
            for name in ("translateX", "translateY", "translateZ", "rotateX", "rotateY", "rotateZ"):
                _action(submenu, name, functools.partial(self._toggle_invert, side, name),
                        checked=name in rules[side],
                        tip="Checked: {} is negated when mirrored onto {}.".format(name, owner))
        _action(menu, "Load default invert rules", mirror.resetInvertRules,
                tip="Return the inverted attributes of side and center controls to the defaults.")

    @staticmethod
    def _toggle_invert(side, name):
        """反転の規則のアトリビュートを1つ入れ替える。"""
        current = list(mirror.setInvertRules()[side])
        if name in current:
            current.remove(name)
        else:
            current.append(name)
        mirror.setInvertRules(**{side: current})

    def _pose(self):
        """ポーズ・アニメーションのコピー。"""
        section = Section("Pose")
        section.button("reset", "Reset to Default\n"
                       "Reset the selected objects' attributes to their default values (only the attributes\n"
                       "selected in the Channel Box, if any). With keys selected in the Graph Editor,\n"
                       "set those keys to the default values instead.", timing.resetValues,
                       menu=self._reset_menu)
        section.button("mirror", "Mirror Pose\n"
                       "Copy the pose of the selected controls onto the opposite side controls\n"
                       "(found by names such as L_/R_, _L/_R, Left/Right).\n"
                       "Right click to mirror animation, select the opposite side or change which attributes\n"
                       "are inverted.", lambda: mirror.mirrorPose(mode="mirror"),
                       menu=self._mirror_menu)
        section.button("flip", "Flip Pose\n"
                       "Swap the poses of the selected controls and their opposite side controls.",
                       lambda: mirror.mirrorPose(mode="flip"))
        self.transformAll = section.button(
            "transformAll", "Transform All\n"
            "1. Press this button (it stays on).\n"
            "2. Change the pose of the selected animated controls at the current frame.\n"
            "3. Press it again to add the same change to every key of those attributes.\n"
            "Right click to apply the change now or cancel.",
            None, menu=self._transform_all_menu, checkable=True)
        self.transformAll.clicked.disconnect()
        self.transformAll.toggled.connect(self._toggle_transform_all)
        section.button("copy", "Copy Animation\n"
                       "Copy the animation of the selected objects (only the range selected in the Time Slider,\n"
                       "if any). Paste it with the button next to it.", animCopy.copyAnimation,
                       menu=lambda menu: _action(menu, "Copy the playback range only",
                                                 lambda: animCopy.copyAnimation(timeRange=Time.getPlaybackRange()),
                                                 tip="Copy only the keys inside the current playback range."))
        section.button("paste", "Paste Animation\n"
                       "Paste the copied animation onto the selected objects in the order they were copied\n"
                       "(one copied object can be pasted onto many). Keys inside the pasted range are replaced,\n"
                       "keys outside it are kept. Right click to paste at the current frame, by name onto\n"
                       "another character, or mirrored as an offset cycle.",
                       animCopy.pasteAnimation, menu=self._paste_menu)
        return section

    def _toggle_transform_all(self, state):
        """transformAll のトグル。押して始め、もう一度押して反映する。"""
        if state:
            if not run(timing.startTransformAll):
                self._set_checked(self.transformAll, False)
                _warn("Select animated controls for transform all")
            return
        if timing.isTransformAllActive() and run(timing.finishTransformAll) is None and timing.isTransformAllActive():
            # 反映できなかった(時刻が違う等)ときは押した状態に戻し、やり直せるようにする。
            self._set_checked(self.transformAll, True)

    def _transform_all_menu(self, menu):
        """transformAll のすぐに反映する操作とやめる操作。"""
        _action(menu, "Apply the change at this frame now", timing.transformAll,
                tip="Without using the toggle: after changing the pose at the current frame (before keying it),\n"
                    "add the difference from the curve to every key of the changed attributes.")
        if timing.isTransformAllActive():
            _action(menu, "Cancel transform all",
                    lambda: (timing.cancelTransformAll(), self._set_checked(self.transformAll, False)),
                    tip="Stop Transform All without changing any keys.")

    @staticmethod
    def _set_checked(button, state):
        """シグナルを出さずにボタンの押した状態を変える。"""
        button.blockSignals(True)
        button.setChecked(state)
        button.blockSignals(False)

    def _reset_menu(self, menu):
        """リセットするアトリビュートの組。"""
        for label, names in (("Translate", ["translate"]), ("Rotate", ["rotate"]), ("Scale", ["scale"]),
                             ("Translate, Rotate and Scale", ["translate", "rotate", "scale"])):
            _action(menu, "Reset " + label, functools.partial(timing.resetValues, None, names),
                    tip="Reset only the {} of the selected objects to the default values.".format(label.lower()))

    def _paste_menu(self, menu):
        """貼付けのしかた。"""
        _action(menu, "Paste in place (start at the current frame)", lambda: animCopy.pasteAnimation(inPlace=True),
                tip="Paste onto the selected objects, shifted so that the first copied key lands on the current frame.")
        _action(menu, "Paste to another character (match names)", lambda: animCopy.pasteAnimation(mode="name"),
                tip="Select any control of the other character and paste. Each copied object is pasted onto the\n"
                    "object with the same name in that control's namespace (missing ones are skipped).")
        _action(menu, "Paste mirrored (invert cycle)", lambda: animCopy.pasteAnimation(invertCycle=True),
                tip="Paste onto the opposite side controls with mirrored values, offset by half of the copied range\n"
                    "(keys past the end wrap to the start). Makes the other half of a cycle such as a walk.")

    def _space(self):
        """位置合わせ・スペース切替・仮のピボット・仮のコンストレイント。"""
        section = Section("Space")
        section.button("align", "Align\n"
                       "Select the objects to move, then the target last, and click to match their position\n"
                       "and rotation to the target. Right click for position/rotation only, or to align on\n"
                       "the target's keys or over the playback range.", spaceTools.align,
                       menu=self._align_menu)
        section.button("space", "Switch Space\n"
                       "Select a control with a space switch (enum) attribute and click. Choose the attribute,\n"
                       "the new space and the frames; the control keeps its world position and rotation.",
                       self._switch_space)
        section.button("pivot", "Temporary Pivot\n"
                       "Create a locator at the selection that the selected objects follow. Move or rotate\n"
                       "the locator to pose them around a new pivot, then right click > Clear temporary pivots\n"
                       "to key the result and remove the locator.", spaceTools.createTempPivot,
                       menu=lambda menu: _action(menu, "Clear temporary pivots", spaceTools.clearTempPivots,
                                                 tip="Key the objects at their current pose and remove every\n"
                                                     "temporary pivot locator."))
        section.button("follow", "Fake Constraint\n"
                       "Select the followers, then the master last, and click. The followers are keyed on every\n"
                       "frame of the playback range to keep their current offset to the master (no constraint\n"
                       "is created). Right click to key only on the master's keys.",
                       spaceTools.fakeConstraint,
                       menu=lambda menu: _action(menu, "Follow on the master's keys only",
                                                 lambda: spaceTools.fakeConstraint(rangeMode="keys"),
                                                 tip="Key the followers only at the frames where the master\n"
                                                     "has keys, instead of every frame."))
        return section

    def _align_menu(self, menu):
        """位置合わせの内容と範囲。"""
        _action(menu, "Align position only", lambda: spaceTools.align(rotate=False),
                tip="Match only the position to the last selected object, keeping the rotation.")
        _action(menu, "Align rotation only", lambda: spaceTools.align(translate=False),
                tip="Match only the rotation to the last selected object, keeping the position.")
        _action(menu, "Align on the target's keys", lambda: spaceTools.align(rangeMode="keys"),
                tip="Align and key at every frame where the last selected object has keys.")
        _action(menu, "Align over the playback range", lambda: spaceTools.align(rangeMode="range"),
                tip="Align and key on every frame of the playback range.")

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
        section.button("trail", "Motion Trail\n"
                       "Create motion trails of the selected objects over the playback range.\n"
                       "Right click to remove the trails made by this button.", viewTools.createMotionTrails,
                       menu=lambda menu: _action(menu, "Clear motion trails", viewTools.clearMotionTrails,
                                                 tip="Delete every motion trail made by this button."))
        micro = section.button("micro", "Micro Transform\n"
                               "While on, moving or rotating the selected objects with the manipulator changes\n"
                               "them by a fraction of the drag, for fine adjustments.\n"
                               "Right click to choose the fraction (x0.5 to x0.05).", None,
                               menu=self._micro_menu, checkable=True)
        micro.clicked.disconnect()
        micro.toggled.connect(lambda state: run(viewTools.setMicroTransform, state))
        tumble = section.button("tumble", "Tumble on Objects\n"
                                "While on, the camera tumbles around the selected objects instead of its center\n"
                                "of interest.", checkable=True)
        tumble.setChecked(run(viewTools.isTumbleOnObjects) or False)
        tumble.toggled.connect(lambda state: run(viewTools.setTumbleOnObjects, state))
        recovery = section.button("recovery", "Animation Backup\n"
                                  "While on, the keys of the scene are backed up every {:g} minutes while Maya\n"
                                  "is idle, and the backup is deleted when the scene is saved. If Maya crashes,\n"
                                  "you are asked to restore the newer backup when the scene is opened again.\n"
                                  "Right click to back up now, restore or discard the backup."
                                  .format(crashRecovery.INTERVAL / 60.0),
                                  None, menu=self._recovery_menu, checkable=True)
        recovery.clicked.disconnect()
        # 起動時に前回の状態で有効にしていれば、押した状態で表示する。
        recovery.setChecked(crashRecovery.isEnabled())
        recovery.toggled.connect(lambda state: run(crashRecovery.setEnabled, state))
        self.recovery = recovery
        return section

    def _micro_menu(self, menu):
        """細かい移動の倍率。"""
        for factor in viewTools.MICRO_FACTORS:
            _action(menu, "Step x{:g}".format(factor), functools.partial(viewTools.setMicroFactor, factor),
                    checked=viewTools.getMicroFactor() == factor,
                    tip="While Micro Transform is on, a manipulator drag changes the value by {:g}% of the drag."
                    .format(factor * 100))

    def _recovery_menu(self, menu):
        """退避の操作。"""
        _action(menu, "Back up now", lambda: _message("Backed up {} curves".format(crashRecovery.backup())),
                tip="Write the keys of the scene to the backup file now (works even while the backup is off).")
        if crashRecovery.hasBackup():
            _action(menu, "Restore the backup", crashRecovery.restore,
                    tip="Replace the animation of the attributes with the same names by the backed up keys.")
            _action(menu, "Discard the backup", crashRecovery.discard, tip="Delete the backup file of this scene.")

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
            button.setToolTip("Select Set: {}\n"
                              "Click to select the members, Shift+click to add them to the selection,\n"
                              "Ctrl+click to remove them from it.\n\n"
                              "Right click to add or remove the selection, rename, recolor or delete the set."
                              .format(selectSets.label(node)))
            button.clicked.connect(lambda *_, target=node: self._select_set(target))
            button.setContextMenuPolicy(QtCore.Qt.CustomContextMenu)
            button.customContextMenuRequested.connect(
                lambda position, target=node, owner=button: self._set_menu(target, owner, position))
            layout.addWidget(button)
        add = self.sets.button("add", "New Select Set\n"
                               "Create a select set button from the current selection (you are asked for a name).\n"
                               "Right click to refresh, export or import the sets.", self._create_set,
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
        _action(menu, "Add selection", lambda: selectSets.editSet(node, add=keys.selectedNodes()),
                tip="Add the selected objects to this set.")
        _action(menu, "Remove selection", lambda: selectSets.editSet(node, remove=keys.selectedNodes()),
                tip="Remove the selected objects from this set.")
        _action(menu, "Rename...", lambda: self._rename_set(node), tip="Change the name shown on the button.")
        colors = _submenu(menu, "Color", "Change the color of the button.")
        for index in range(len(icons.SET_COLORS)):
            action = _action(colors, "Color {}".format(index + 1),
                             functools.partial(self._recolor_set, node, index), tip="Use this color for the button.")
            action.setIcon(self._swatch(icons.SET_COLORS[index]))
        menu.addSeparator()
        _action(menu, "Delete", lambda: (selectSets.deleteSet(node), self.refreshSets()),
                tip="Delete this select set. The member objects are not deleted.")
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
        _action(menu, "Refresh", self.refreshSets,
                tip="Rebuild the set buttons from the select sets in the scene.")
        _action(menu, "Export select sets...", self._export_sets,
                tip="Save every select set to a JSON file. Members are written without namespaces.")
        _action(menu, "Import select sets...", self._import_sets,
                tip="Load select sets from a JSON file. Enter a namespace to apply them to a referenced character;\n"
                    "members that are not found are skipped.")

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
    # 作成の途中はドック先が決まっていないので、組み立てが終わってからタブの行を隠す。
    cmds.evalDeferred(_hide_tab_bar, lowestPriority=True)
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
    # ドックし直す(親が替わる)たびに、新しいドック先でもタブの行を隠す。
    parent.installEventFilter(_DockWatcher(widget))
    _bar["widget"] = widget
    return widget


class _DockWatcher(QtCore.QObject):
    """workspaceControl の親が替わったら、タブの行を隠す処理をやり直す。"""

    def eventFilter(self, watched, event):
        """親が替わったら、配置が落ち着いてからタブの行を隠す。"""
        if event.type() == QtCore.QEvent.ParentChange:
            cmds.evalDeferred(_hide_tab_bar, lowestPriority=True)
        return False


class _TabBarHider(QtCore.QObject):
    """ドック先のタブの行(見出しの「Anim Bar」)を、タブが1つのときだけ隠し続ける。

    Mayaはパネルの開閉などで配置を組み直すたびに、タブの行を表示し、その高さを含めてドックの高さを決め直す。
    そのためタブの行の表示・非表示を見張り、表示されたら隠して、空いた高さを隣の一番大きい場所へ返す。
    同じ場所へ別のパネルをタブで重ねたときは、切り替えのためにタブの行を残す。

    Args:
        tabs (QtWidgets.QTabWidget): workspaceControl が入っているタブの部品。
    """

    def __init__(self, tabs):
        super().__init__(tabs)
        # Mayaは部品のPython側の参照を無効にすることがあるので、タブの部品は保持せず親から毎回取り直す。
        # 表示の処理が終わってから直すため、イベントの後へ遅らせる(部品と一緒に破棄される)。
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.apply)
        tabs.setTabBarAutoHide(True)
        tabs.tabBar().installEventFilter(self)

    def eventFilter(self, watched, event):
        """タブの行が表示・非表示になったら、隠し直しと高さの調整を予約する。"""
        if event.type() in (QtCore.QEvent.Show, QtCore.QEvent.Hide):
            self._timer.start(0)
        return False

    def apply(self):
        """タブが1つならタブの行を隠し、ドックの高さを中身の高さへ詰める。

        Returns:
            None: 値を返さない。
        """
        tabs = self.parent()
        # 浮動の窓では、タブの行が窓を動かす取っ手になるので残す。
        if not isinstance(tabs, QtWidgets.QTabWidget) or tabs.count() > 1 or isFloating():
            return
        tabs.tabBar().hide()
        splitter = tabs.parentWidget()
        if not isinstance(splitter, QtWidgets.QSplitter) or splitter.orientation() != QtCore.Qt.Vertical:
            return
        index = splitter.indexOf(tabs)
        sizes = splitter.sizes()
        extra = sizes[index] - tabs.sizeHint().height()
        others = [position for position in range(len(sizes)) if position != index]
        if extra <= 0 or not others:
            return
        largest = max(others, key=lambda position: sizes[position])
        sizes[index] -= extra
        sizes[largest] += extra
        splitter.setSizes(sizes)


def _hide_tab_bar():
    """ドック先のタブの部品に :class:`_TabBarHider` を付ける(付いていれば調整だけする)。

    Returns:
        None: 値を返さない。
    """
    pointer = omui.MQtUtil.findControl(CONTROL)
    if pointer is None:
        return
    # workspaceControl → QStackedWidget → QTabWidget の順に入っている。浮動中など、ほかの構成なら何もしない。
    stack = wrapInstance(int(pointer), QtWidgets.QWidget).parentWidget()
    tabs = stack.parentWidget() if stack is not None else None
    if not isinstance(tabs, QtWidgets.QTabWidget):
        return
    hiders = tabs.findChildren(_TabBarHider)
    hider = hiders[0] if hiders else _TabBarHider(tabs)
    hider.apply()


def show():
    """バーをタイムスライダーの上にドックして表示する。

    Returns:
        str: workspaceControl の名前。
    """
    if cmds.workspaceControl(CONTROL, exists=True):
        if cmds.workspaceControl(CONTROL, query=True, visible=True):
            # 表示中なら、浮動の位置やドック先を変えずにそのまま出す。
            cmds.workspaceControl(CONTROL, edit=True, restore=True)
            return CONTROL
        cmds.deleteUI(CONTROL)
    cmds.workspaceControl(CONTROL, label="Anim Bar", retain=False, floating=False,
                          dockToControl=("TimeSlider", "top"), initialHeight=preferences.barHeight(),
                          heightProperty="fixed",
                          uiScript="import animBar.ui.bar as _bar; _bar._build()",
                          visibleChangeCommand=_remember_visibility)
    _build()
    cmds.optionVar(intValue=(VISIBLE_OPTION, 1))
    return CONTROL


def rebuild():
    """バーを作り直す(ボタンの大きさを変えたとき)。浮動中なら、作り直した後も浮動にする。

    Returns:
        str: workspaceControl の名前。
    """
    floating = isFloating()
    if cmds.workspaceControl(CONTROL, exists=True):
        cmds.deleteUI(CONTROL)
    _bar["widget"] = None
    show()
    if floating:
        setFloating(True)
    return CONTROL


def isFloating():
    """バーが浮動の窓になっているかを返す。

    Returns:
        bool: 浮動ならTrue。表示していなければFalse。
    """
    return bool(cmds.workspaceControl(CONTROL, exists=True) and
                cmds.workspaceControl(CONTROL, query=True, floating=True))


def setFloating(floating):
    """バーを浮動の窓にする、またはタイムスライダーの上へドックし直す。

    Args:
        floating (bool): Trueは浮動にする。Falseはタイムスライダーの上へドックする。

    Returns:
        bool: 変えた後に浮動ならTrue。表示していなければFalse。
    """
    if not cmds.workspaceControl(CONTROL, exists=True):
        return False
    if floating:
        cmds.workspaceControl(CONTROL, edit=True, floating=True)
    else:
        cmds.workspaceControl(CONTROL, edit=True, dockToControl=("TimeSlider", "top"))
        cmds.evalDeferred(_hide_tab_bar, lowestPriority=True)
    return isFloating()


def openSettings():
    """設定の画面を開く。

    Returns:
        QtWidgets.QDialog: 設定の画面。
    """
    # 設定の画面はバーを作り直す処理を呼ぶため、循環しないよう呼出し時に読み込む。
    from . import settingsDialog
    return settingsDialog.showDialog()


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

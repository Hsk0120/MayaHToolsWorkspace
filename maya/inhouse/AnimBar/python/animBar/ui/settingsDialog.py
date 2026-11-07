"""Anim Bar の設定の画面。区切りの表示・ボタンの大きさ・プレイブラスト・退避・細かい移動をまとめて変える。

変えた設定はすぐに覚えてバーへ反映する(OK を押す必要はない)。
"""

import maya.cmds as cmds
import maya.OpenMayaUI as omui

from ..core import crashRecovery, timeline, viewTools
from . import bar, preferences
from .qt import QtCore, QtWidgets, wrapInstance

#: 開いている画面(1つだけ開く)。
_dialog = {"widget": None}

#: プレイブラストのオーバースキャンの選択肢(Noneはカメラの設定のまま)。
_OVERSCANS = (None, 1.1, 1.2, 1.3)

#: プレイブラストの大きさの選択肢(%)。
_PERCENTS = (50, 75, 100)


def showDialog():
    """設定の画面を開く(開いていれば前に出す)。

    Returns:
        SettingsDialog: 設定の画面。
    """
    dialog = _dialog["widget"]
    try:
        alive = dialog is not None and bool(dialog.objectName())
    except RuntimeError:
        # Qt 側で破棄済みのラッパー。
        alive = False
    if not alive:
        pointer = omui.MQtUtil.mainWindow()
        parent = wrapInstance(int(pointer), QtWidgets.QWidget) if pointer is not None else None
        dialog = SettingsDialog(parent)
        _dialog["widget"] = dialog
    dialog.refresh()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
    return dialog


class SettingsDialog(QtWidgets.QDialog):
    """Anim Bar の設定の画面。

    Args:
        parent (QtWidgets.QWidget | None): 親(Mayaのメインウィンドウ)。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("AnimBarSettings")
        self.setWindowTitle("Anim Bar Settings")
        layout = QtWidgets.QVBoxLayout(self)

        sections = QtWidgets.QGroupBox("Sections")
        sections.setToolTip("Sections shown on the bar. Hide the ones you do not use to save space.")
        grid = QtWidgets.QGridLayout(sections)
        self.sectionBoxes = {}
        for index, name in enumerate(preferences.SECTIONS):
            box = QtWidgets.QCheckBox(name)
            box.toggled.connect(lambda state, section=name: self._set_section(section, state))
            grid.addWidget(box, index // 4, index % 4)
            self.sectionBoxes[name] = box
        layout.addWidget(sections)

        appearance = QtWidgets.QGroupBox("Appearance")
        form = QtWidgets.QFormLayout(appearance)
        self.size = QtWidgets.QComboBox()
        for name, label, icon, height in preferences.SIZES:
            self.size.addItem("{} ({} px)".format(label, height), name)
        self.size.setToolTip("Size of the buttons and the height of the bar. The bar is rebuilt when changed.")
        self.size.currentIndexChanged.connect(self._set_size)
        form.addRow("Button size:", self.size)
        layout.addWidget(appearance)

        playblast = QtWidgets.QGroupBox("Playblast")
        form = QtWidgets.QFormLayout(playblast)
        self.sound = QtWidgets.QCheckBox("Include sound")
        self.sound.setToolTip("Include the Time Slider's sound in the movie.")
        self.sound.toggled.connect(lambda state: self._set_playblast(sound=state))
        form.addRow(self.sound)
        self.ornaments = QtWidgets.QCheckBox("Show HUD and ornaments")
        self.ornaments.setToolTip("Include the heads-up display and other viewport ornaments.")
        self.ornaments.toggled.connect(lambda state: self._set_playblast(showOrnaments=state))
        form.addRow(self.ornaments)
        self.useRange = QtWidgets.QCheckBox("Use the highlighted range")
        self.useRange.setToolTip("When a range is selected in the Time Slider (Shift+drag), playblast only that range.")
        self.useRange.toggled.connect(lambda state: self._set_playblast(useRange=state))
        form.addRow(self.useRange)
        self.overscan = QtWidgets.QComboBox()
        for value in _OVERSCANS:
            self.overscan.addItem("Keep camera setting" if value is None else "{:g}".format(value), value)
        self.overscan.setToolTip("Show more of the scene around the camera frame while playblasting.")
        self.overscan.currentIndexChanged.connect(
            lambda index: self._set_playblast(overscan=self.overscan.itemData(index)))
        form.addRow("Overscan:", self.overscan)
        self.percent = QtWidgets.QComboBox()
        for value in _PERCENTS:
            self.percent.addItem("{}%".format(value), value)
        self.percent.setToolTip("Movie size relative to the viewport size.")
        self.percent.currentIndexChanged.connect(
            lambda index: self._set_playblast(percent=self.percent.itemData(index)))
        form.addRow("Size:", self.percent)
        layout.addWidget(playblast)

        tools = QtWidgets.QGroupBox("Tools")
        form = QtWidgets.QFormLayout(tools)
        self.recovery = QtWidgets.QCheckBox("Animation backup")
        self.recovery.setToolTip("Back up the keys of the scene every {:g} minutes while Maya is idle\n"
                                 "(the same as the backup button in the View section)."
                                 .format(crashRecovery.INTERVAL / 60.0))
        self.recovery.toggled.connect(self._set_recovery)
        form.addRow(self.recovery)
        self.micro = QtWidgets.QComboBox()
        for factor in viewTools.MICRO_FACTORS:
            self.micro.addItem("x{:g}".format(factor), factor)
        self.micro.setToolTip("While Micro Transform is on, a manipulator drag changes the value by this fraction.")
        self.micro.currentIndexChanged.connect(
            lambda index: bar.run(viewTools.setMicroFactor, self.micro.itemData(index)))
        form.addRow("Micro transform step:", self.micro)
        layout.addWidget(tools)

        buttons = QtWidgets.QHBoxLayout()
        reset = QtWidgets.QPushButton("Reset to Defaults")
        reset.setToolTip("Reset every Anim Bar setting above. Saved ranges, select sets and backups are kept.")
        reset.clicked.connect(self._reset)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        close = QtWidgets.QPushButton("Close")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        layout.addLayout(buttons)

    def refresh(self):
        """覚えている設定を画面へ読み込む(読み込み中は変更の処理を呼ばない)。

        Returns:
            None: 値を返さない。
        """
        widgets = list(self.sectionBoxes.values()) + [self.size, self.sound, self.ornaments, self.useRange,
                                                      self.overscan, self.percent, self.recovery, self.micro]
        for widget in widgets:
            widget.blockSignals(True)
        hidden = preferences.hiddenSections()
        for name, box in self.sectionBoxes.items():
            box.setChecked(name not in hidden)
        self.size.setCurrentIndex(max(0, self.size.findData(preferences.size())))
        settings = timeline.playblastSettings()
        self.sound.setChecked(bool(settings["sound"]))
        self.ornaments.setChecked(bool(settings["showOrnaments"]))
        self.useRange.setChecked(bool(settings["useRange"]))
        self.overscan.setCurrentIndex(max(0, self.overscan.findData(settings["overscan"])))
        self.percent.setCurrentIndex(max(0, self.percent.findData(settings["percent"])))
        self.recovery.setChecked(crashRecovery.isEnabled())
        self.micro.setCurrentIndex(max(0, self.micro.findData(viewTools.getMicroFactor())))
        for widget in widgets:
            widget.blockSignals(False)

    def _apply_to_bar(self):
        """表示中のバーへ、作り直さずに変えられる設定を反映する。"""
        widget = bar._bar["widget"]
        if widget is not None:
            try:
                widget.applyPreferences()
            except RuntimeError:
                # バーが閉じられて Qt 側で破棄済み。
                bar._bar["widget"] = None

    def _set_section(self, name, visible):
        """区切りの表示を覚えて反映する。"""
        bar.run(preferences.setSectionVisible, name, visible)
        self._apply_to_bar()

    def _set_size(self, index):
        """ボタンの大きさを覚え、表示中ならバーを作り直す。"""
        bar.run(preferences.setSize, self.size.itemData(index))
        if cmds.workspaceControl(bar.CONTROL, exists=True):
            bar.rebuild()

    def _set_playblast(self, **settings):
        """プレイブラストの設定を覚える。"""
        bar.run(timeline.setPlayblastSettings, **settings)

    def _set_recovery(self, state):
        """退避を有効・無効にし、バーのボタンもそろえる。"""
        bar.run(crashRecovery.setEnabled, state)
        self._apply_to_bar()

    def _reset(self):
        """確認してから、すべての設定を既定へ戻す。"""
        answer = QtWidgets.QMessageBox.question(
            self, "Reset Anim Bar Settings",
            "Reset every Anim Bar setting to the default?\nSaved ranges, select sets and backups are kept.")
        if answer != QtWidgets.QMessageBox.Yes:
            return
        size = preferences.size()
        bar.run(preferences.resetAll)
        self.refresh()
        if preferences.size() != size and cmds.workspaceControl(bar.CONTROL, exists=True):
            bar.rebuild()
        else:
            self._apply_to_bar()

"""Maya内でサンプル構成を編集する、レイヤーパネル形式のUI。"""

from functools import partial

import hlib
from hlib.ui import MainWindow
from hlib.ui import NodeEditor
from hlib.ui import GraphEditor

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import isValid
except ImportError:
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import isValid

from hlib.decorators.undo import undoTransaction
from .sampleBuilder import SampleBuilder
from .moduleRegistry import ModuleRegistry
from .skirtRig import SkirtRig
from .splineRig import SplineRig
from .controlRig import ControlRig
from .tweakLayer import TweakLayer


class LayerEditor(QtWidgets.QDialog):
    """モジュールをフォルダー、機能をレイヤー行として表示する。"""

    _instance = None
    LABELS = {
        "fk": "FK",
        "ik": "IK",
        "soft": "Soft IK",
        "helper": "基本補助骨",
        "space": "空間切り替え",
        "foot": "リバースフット",
        "twist": "ツイスト補助骨",
        "bend": "肘・膝の補助骨",
        "driven": "Swing / Twist · Driven Key",
        "follow": "回転追従補助骨",
        "spring": "揺れ物（ベイク）",
        "pose": "ポーズ補正（RBF）",
        "spline": "Spline IK",
        "stretch": "伸縮・体積補正",
        "finger": "指 Curl / Spread",
        "aim": "首・視線 Aim",
        "tweak": "局所 Tweak",
    }
    OPTIONAL = (
        "soft",
        "helper",
        "foot",
        "twist",
        "bend",
        "driven",
        "follow",
        "radial",
        "spring",
        "pose",
        "spline",
        "stretch",
        "finger",
        "aim",
    )

    def __init__(self, parent=None):
        """UIと、寿命に連動するMayaイベント監視を生成する。

        Args:
            parent (QWidget | None): Mayaメインウィンドウ。
        """
        super().__init__(parent)
        self.setObjectName("hrigLayerEditor")
        self.setWindowTitle("hrig · Layer Editor")
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.resize(620, 900)
        self.setMinimumSize(530, 660)
        self._busy = False
        self._pending = False
        self._closed = False
        self._jobs = hlib.events.ScriptJobs()
        self._attributes = hlib.events.ScriptJobs()
        self.setStyleSheet("""
            QDialog { background:#24262c; color:#e3e5ed; }
            QLabel { color:#d5d8e2; } QGroupBox { color:#aeb5c8; border:1px solid #424650;
                border-radius:6px; margin-top:12px; padding-top:12px; }
            QGroupBox::title { subcontrol-origin:margin; left:12px; }
            QLineEdit,QComboBox,QSpinBox { background:#30333b; color:#eceef5; padding:5px;
                border:1px solid #454a58; border-radius:4px; }
            QPushButton { background:#3d424f; color:#eef0f7; border:0; padding:7px 12px; border-radius:4px; }
            QPushButton:hover { background:#51586a; } QPushButton:disabled { color:#777e8c; }
            QPushButton#primary { background:#7361c5; }
            QTreeWidget { background:#292c33; alternate-background-color:#2e3139; color:#e7e9f2;
                border:1px solid #424650; border-radius:5px; outline:0; }
            QTreeWidget::item { height:32px; } QTreeWidget::item:selected { background:#534876; }
            QHeaderView::section { background:#353945; color:#bac0d0; border:0; padding:7px; }
        """)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        title = QtWidgets.QLabel("hrig  /  LAYERS")
        title.setStyleSheet("font-size:21px; font-weight:600; color:#f0edff;")
        layout.addWidget(title)
        layout.addWidget(QtWidgets.QLabel("モジュールを作成し、必要な機能をレイヤーとして追加"))
        create_box = QtWidgets.QGroupBox("新規モジュール")
        row = QtWidgets.QHBoxLayout(create_box)
        self.module_name = QtWidgets.QLineEdit("limb01")
        self.module_name.setPlaceholderText("一意なモジュール名")
        self.module_type = QtWidgets.QComboBox()
        self.module_type.addItems(
            [
                "3関節 · FK / IK",
                "メッシュ付きデモ",
                "スカート · 4方向",
                "スカート · 8方向",
                "背骨 · Spline IK",
                "尻尾 · Spline IK",
                "指 · Curl / Spread",
                "首・視線 · Aim",
            ]
        )
        self.create_button = QtWidgets.QPushButton("＋ 作成")
        self.create_button.setObjectName("primary")
        self.create_button.clicked.connect(partial(self._run, self.create_module))
        for widget in (self.module_name, self.module_type, self.create_button):
            row.addWidget(widget)
        layout.addWidget(create_box)
        self.skirt_options = QtWidgets.QWidget()
        options = QtWidgets.QHBoxLayout(self.skirt_options)
        options.setContentsMargins(0, 0, 0, 0)
        self.skirt_count = QtWidgets.QSpinBox()
        self.skirt_count.setRange(8, 256)
        self.skirt_count.setValue(16)
        self.skirt_depth = QtWidgets.QSpinBox()
        self.skirt_depth.setRange(2, 32)
        self.skirt_depth.setValue(3)
        self.skirt_radius = QtWidgets.QDoubleSpinBox()
        self.skirt_length = QtWidgets.QDoubleSpinBox()
        for control, value in ((self.skirt_radius, 3), (self.skirt_length, 5)):
            control.setRange(0.01, 100000)
            control.setValue(value)
        for label, control in (
            ("骨列数", self.skirt_count),
            ("各列", self.skirt_depth),
            ("半径", self.skirt_radius),
            ("長さ", self.skirt_length),
        ):
            options.addWidget(QtWidgets.QLabel(label))
            options.addWidget(control)
        self.module_type.currentIndexChanged.connect(self._module_options)
        layout.addWidget(self.skirt_options)
        self.spline_options = QtWidgets.QWidget()
        spline_options = QtWidgets.QHBoxLayout(self.spline_options)
        spline_options.setContentsMargins(0, 0, 0, 0)
        self.spline_joints = QtWidgets.QSpinBox()
        self.spline_joints.setRange(3, 64)
        self.spline_joints.setValue(7)
        self.spline_controls = QtWidgets.QSpinBox()
        self.spline_controls.setRange(4, 32)
        self.spline_controls.setValue(4)
        self.spline_length = QtWidgets.QDoubleSpinBox()
        self.spline_length.setRange(0.01, 100000)
        self.spline_length.setValue(10)
        for label, control in (
            ("骨数", self.spline_joints),
            ("コントロール", self.spline_controls),
            ("全長", self.spline_length),
        ):
            spline_options.addWidget(QtWidgets.QLabel(label))
            spline_options.addWidget(control)
        layout.addWidget(self.spline_options)
        self._module_options()
        toolbar = QtWidgets.QHBoxLayout()
        self.mode = QtWidgets.QComboBox()
        self.mode.addItems(["FK", "IK"])
        self.lod = QtWidgets.QComboBox()
        self.lod.addItems(["Low LOD", "Full LOD"])
        self.mode.activated.connect(partial(self._run, self.change_mode))
        self.lod.activated.connect(partial(self._run, self.change_lod))
        toolbar.addWidget(QtWidgets.QLabel("選択モジュール"))
        toolbar.addWidget(self.mode)
        toolbar.addWidget(self.lod)
        toolbar.addStretch()
        refresh = QtWidgets.QPushButton("更新")
        refresh.clicked.connect(self.refresh)
        toolbar.addWidget(refresh)
        layout.addLayout(toolbar)
        self.tree = QtWidgets.QTreeWidget()
        self.tree.setHeaderLabels(["使用", "モジュール / レイヤー", "評価"])
        self.tree.setColumnWidth(0, 58)
        self.tree.setColumnWidth(1, 325)
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setExpandsOnDoubleClick(False)
        self.tree.itemChanged.connect(self._item_changed)
        self.tree.itemSelectionChanged.connect(self._selection_changed)
        self.tree.itemDoubleClicked.connect(partial(self._run, self.select_node))
        layout.addWidget(self.tree, 1)
        layout.addWidget(QtWidgets.QLabel("チェック＝使用設定　●＝評価中　○＝停止・未追加"))
        add_box = QtWidgets.QGroupBox("サンプルレイヤーを追加")
        add_layout = QtWidgets.QVBoxLayout(add_box)
        row = QtWidgets.QHBoxLayout()
        self.layer_type = QtWidgets.QComboBox()
        for kind in ("twist", "bend", "driven", "foot", "soft", "helper"):
            self.layer_type.addItem(self.LABELS[kind], kind)
        for kind, label in (
            ("followTwist", "Twistのみ追従"),
            ("followSwing", "Swingのみ追従"),
            ("followHalf", "回転の割合追従"),
        ):
            self.layer_type.addItem(label, kind)
        self.count = QtWidgets.QSpinBox()
        self.layer_type.addItem(self.LABELS["spring"], "spring")
        self.layer_type.addItem(self.LABELS["pose"], "pose")
        self.layer_type.addItem(self.LABELS["stretch"], "stretch")
        self.layer_type.addItem(self.LABELS["tweak"], "tweak")
        self.count.setRange(1, 64)
        self.count.setValue(3)
        self.count.setSuffix(" 本")
        self.component = QtWidgets.QComboBox()
        self.component.addItems(["swingZ", "swingY", "swingX", "twist"])
        self.axis = QtWidgets.QComboBox()
        self.axis.addItems(["x", "y", "z"])
        self.axis.setToolTip("Twistの長手軸")
        self.ratio = QtWidgets.QDoubleSpinBox()
        self.ratio.setRange(0, 100)
        self.ratio.setValue(50)
        self.ratio.setSuffix(" %")
        self.addButton = QtWidgets.QPushButton("＋ 追加")
        self.addButton.clicked.connect(partial(self._run, self.add_layer))
        for widget in (
            self.layer_type,
            self.count,
            self.component,
            self.axis,
            self.ratio,
            self.addButton,
        ):
            row.addWidget(widget)
        add_layout.addLayout(row)
        self.layer_hint = QtWidgets.QLabel()
        self.layer_hint.setWordWrap(True)
        add_layout.addWidget(self.layer_hint)
        self.layer_type.currentIndexChanged.connect(self._layer_options)
        layout.addWidget(add_box)
        buttons = QtWidgets.QHBoxLayout()
        for label, action in (
            ("シーンで選択", self.select_node),
            ("ノードグラフ", self.open_graph),
            ("SDKカーブ", self.open_curve),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(partial(self._run, action))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.bake_button = QtWidgets.QPushButton("揺れを再ベイク（再生範囲）")
        self.bake_button.clicked.connect(partial(self._run, self.bake_spring))
        layout.addWidget(self.bake_button)
        self.pose_button = QtWidgets.QPushButton("ポーズ補正を登録・編集")
        self.pose_button.clicked.connect(partial(self._run, self.edit_poses))
        layout.addWidget(self.pose_button)
        self.status = QtWidgets.QLabel("モジュールを作成、または一覧から選択してください。")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        for event in ("Undo", "Redo", "SceneOpened", "NewSceneOpened", "NameChanged"):
            self._jobs.add(event, event=event, callback=self.schedule_refresh)
        self._layer_options()
        self.refresh()

    @classmethod
    def show_window(cls):
        """同じウィンドウを再利用して表示する。

        Returns:
            LayerEditor: 表示中のインスタンス。
        """
        if cls._instance is None or not isValid(cls._instance):
            # Qtの親取得はUI実装側で行い、基礎ライブラリhlibへ依存を持ち込まない。
            name = MainWindow.name()
            parent = next((window for window in QtWidgets.QApplication.topLevelWidgets()
                           if window.objectName() == name), None)
            cls._instance = cls(parent)
        cls._instance.show()
        cls._instance.raise_()
        cls._instance.activateWindow()
        return cls._instance

    def _run(self, action, *unused):
        """UI操作の失敗をパネル内へ表示し、Mayaへ例外を漏らさない。

        Args:
            action (Callable): 引数なしの操作。
            *unused: Qtシグナルの引数。
        """
        try:
            message = action()
            self.status.setText(message if isinstance(message, str) else "完了")
        except Exception as error:
            self.status.setText("操作できません: " + str(error))
        # itemChanged/doubleClickedの発火中に行を破棄するとQtの内部参照が無効になる。
        self.schedule_refresh()

    def schedule_refresh(self):
        """イベントの連続通知を一度の更新にまとめる。"""
        if not self._pending and not self._closed:
            self._pending = True
            QtCore.QTimer.singleShot(0, self._scheduled_refresh)

    def _scheduled_refresh(self):
        """ウィンドウが生存する場合だけ一覧を更新する。"""
        self._pending = False
        if not self._closed:
            self.refresh()

    def current(self):
        """現在行の部位と選択先を解決する。

        Returns:
            tuple[LimbRig, dict]: 保存済みUUIDで再取得した部位と行情報。
        """
        item = self.tree.currentItem()
        data = item.data(0, QtCore.Qt.UserRole) if item else None
        if not data:
            raise ValueError("モジュールまたはレイヤーを選択してください")
        roots = [item.fullName() for item in hlib.ls(data["root"], long=True)] or []
        if not roots:
            raise ValueError("モジュールが削除されています")
        return ModuleRegistry.get(roots[0]), data

    def _row(self, parent, label, data, active=None):
        """行を追加する。

        Args:
            parent (QTreeWidget | QTreeWidgetItem): 親。
            label (str): 表示名。
            data (dict): 参照情報。
            active (bool | None): 評価状態。

        Returns:
            QTreeWidgetItem: 新規行。
        """
        item = QtWidgets.QTreeWidgetItem(
            parent, ["", label, "" if active is None else ("● 評価中" if active else "○ 停止")]
        )
        item.setData(0, QtCore.Qt.UserRole, data)
        if active is not None:
            item.setForeground(2, QtGui.QColor("#8ed4b1" if active else "#9097a8"))
        return item

    def refresh(self, *unused):
        """シーンを変更せず、モジュールと評価状態を再取得する。

        Args:
            *unused: Qtシグナルの引数。
        """
        if self._closed or self._busy:
            return
        self._busy = True
        current = self.tree.currentItem()
        selected = current.data(0, QtCore.Qt.UserRole) if current else None
        expanded = {}
        scroll = self.tree.verticalScrollBar().value()
        for item in self.rows():
            data = item.data(0, QtCore.Qt.UserRole)
            expanded[(data["root"], data["role"])] = item.isExpanded()
        self._attributes.stop()
        self.tree.clear()
        from .channel_controls import _states
        from .twistLayer import TwistLayer
        from .bendLayer import BendLayer
        from .drivenLayer import DrivenLayer
        from .followLayer import FollowLayer

        try:
            for root in ModuleRegistry.roots():
                rig = ModuleRegistry.get(root)
                uuid = rig.root.uuid()
                data = {"root": uuid, "role": "module", "target": uuid}
                root_item = self._row(self.tree, rig.root.name(), data)
                root_item.setIcon(1, self.style().standardIcon(QtWidgets.QStyle.SP_DirIcon))
                root_item.setExpanded(True)
                self._tweak_rows(rig, root_item)
                if isinstance(rig, ControlRig):
                    self._control_rows(rig, root_item)
                    continue
                if isinstance(rig, SplineRig):
                    self._spline_rows(rig, root_item)
                    continue
                if isinstance(rig, SkirtRig):
                    self._skirt_rows(rig, root_item)
                    continue
                states = _states(rig)
                for role, label in self.LABELS.items():
                    if not rig.root.hasAttr("channel_" + role):
                        continue
                    node = hlib.getNode(rig._member("channel_" + role))
                    item = self._row(
                        root_item,
                        label,
                        {"root": uuid, "role": role, "target": node.uuid()},
                        states.get(role, False),
                    )
                    if role in self.OPTIONAL:
                        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
                        item.setCheckState(
                            0, QtCore.Qt.Checked if rig.layer_enabled(role) else QtCore.Qt.Unchecked
                        )
                    groups = (
                        TwistLayer(rig).segments()
                        if role == "twist"
                        else (
                            BendLayer(rig).groups()
                            if role == "bend"
                            else (
                                DrivenLayer(rig).graphs()
                                if role == "driven"
                                else FollowLayer(rig).groups() if role == "follow" else {}
                            )
                        )
                    )
                    for identifier, group in groups.items():
                        self._row(
                            item,
                            identifier,
                            {"root": uuid, "role": role + ":" + identifier, "target": group.uuid()},
                        )
                    item.setExpanded(True)
                for name in ("hrigMode", "hrigLod") + tuple(
                    "hrigEnabled_" + role for role in self.OPTIONAL
                ):
                    if rig.root.hasAttr(name):
                        self._attributes.add(
                            (uuid, name),
                            attribute=rig.root.plug(name),
                            callback=self.schedule_refresh,
                            kill_with_scene=True,
                        )
            for item in self.rows():
                data = item.data(0, QtCore.Qt.UserRole)
                item.setExpanded(expanded.get((data["root"], data["role"]), True))
                if data == selected:
                    self.tree.setCurrentItem(item)
            if self.tree.currentItem() is None and self.tree.topLevelItemCount():
                self.tree.setCurrentItem(self.tree.topLevelItem(0))
            self.tree.verticalScrollBar().setValue(scroll)
        finally:
            self._busy = False
        self._selection_changed()

    def _module_options(self, *unused):
        """モジュールの種類に対応した骨数と寸法を表示する。

        Args:
            *unused: Qtシグナル引数。
        """
        self.skirt_options.setVisible(self.module_type.currentIndex() in (2, 3))
        self.spline_options.setVisible(self.module_type.currentIndex() in (4, 5))

    def _spline_rows(self, rig, root_item):
        """SplineモジュールのFK/IK・コントロール・変形骨を表示する。

        Args:
            rig (SplineRig): 対象モジュール。
            root_item (QTreeWidgetItem): モジュール行。
        """
        uuid = rig.root.uuid()
        fk = self._row(
            root_item,
            "FK骨列",
            {"root": uuid, "role": "fk", "target": rig.root.plug("fkGroup").sourceWithConversion().node().uuid()},
            not rig.active(),
        )
        for i, bone in enumerate(rig.members("fk")):
            self._row(
                fk,
                "FK {:02d}".format(i + 1),
                {"root": uuid, "role": "fk:" + str(i), "target": bone.uuid()},
            )
        item = self._row(
            root_item,
            "Spline IK",
            {"root": uuid, "role": "spline", "target": uuid},
            rig.active(),
        )
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.Checked if rig.layer_enabled() else QtCore.Qt.Unchecked)
        for i, control in enumerate(rig.controls()):
            self._row(
                item,
                "カーブ {:02d}".format(i + 1),
                {"root": uuid, "role": "spline:" + str(i), "target": control.uuid()},
            )
        group = rig.root.plug("deformGroup").sourceWithConversion().node()
        self._row(
            root_item,
            "変形骨（{}本）".format(len(rig.joints())),
            {"root": uuid, "role": "deform", "target": group.uuid()},
        )
        from .splineStretchLayer import SplineStretchLayer

        stretch = SplineStretchLayer(rig)
        settings = stretch.settings()
        if settings is not None:
            item = self._row(
                root_item,
                self.LABELS["stretch"],
                {"root": uuid, "role": "stretch", "target": settings.uuid()},
                stretch.active(),
            )
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
            item.setCheckState(
                0, QtCore.Qt.Checked if rig.layer_enabled("stretch") else QtCore.Qt.Unchecked
            )
        attrs = ["mode", "lod", "enabled"]
        if rig.root.hasAttr("hrigEnabled_stretch"):
            attrs.append("hrigEnabled_stretch")
        for name in attrs:
            self._attributes.add(
                (uuid, name),
                attribute=rig.root.plug(name),
                callback=self.schedule_refresh,
                kill_with_scene=True,
            )

    def _skirt_rows(self, rig, root_item):
        """スカートの放射状レイヤーと操作先を表示する。

        Args:
            rig (SkirtRig): 対象モジュール。
            root_item (QTreeWidgetItem): モジュール行。
        """
        uuid = rig.root.uuid()
        item = self._row(
            root_item,
            "方向ブレンド · 設定（Blend / Falloff）",
            {"root": uuid, "role": "radial", "target": uuid},
            rig.layer_enabled() and rig.lod() == 1,
        )
        item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable)
        item.setCheckState(0, QtCore.Qt.Checked if rig.layer_enabled() else QtCore.Qt.Unchecked)
        for index, chain in enumerate(rig.driver_chains()):
            self._row(
                item,
                "ドライバー {:02d}".format(index + 1),
                {"root": uuid, "role": "driver:" + str(index), "target": chain[0].uuid()},
            )
        group = rig.root.plug("followerGroup").sourceWithConversion().node()
        self._row(
            root_item,
            "変形骨（{}列）".format(len(rig.chains())),
            {"root": uuid, "role": "followers", "target": group.uuid()},
        )
        from .followLayer import FollowLayer

        follow = self._row(
            root_item,
            self.LABELS["follow"],
            {"root": uuid, "role": "follow", "target": uuid},
            rig.layer_enabled("follow") and rig.lod() == 1 and bool(rig.follow_joints()),
        )
        follow.setFlags(follow.flags() | QtCore.Qt.ItemIsUserCheckable)
        follow.setCheckState(
            0, QtCore.Qt.Checked if rig.layer_enabled("follow") else QtCore.Qt.Unchecked
        )
        for identifier, group in FollowLayer(rig).groups().items():
            self._row(
                follow,
                identifier,
                {"root": uuid, "role": "follow:" + identifier, "target": group.uuid()},
            )
        attrs = ["enabled", "lod"]
        from .secondaryLayer import SecondaryLayer

        groups = SecondaryLayer(rig).groups()
        for kind in ("spring", "pose"):
            members = {
                i: g
                for i, g in groups.items()
                if kind == "spring" or g.plug("poseGraph").sourceWithConversion() is not None
            }
            active = rig.layer_enabled(kind) and rig.lod() == 1 and bool(members)
            if kind == "spring":
                active = active and any(g.plug("baked").get() for g in members.values())
            layer = self._row(
                root_item, self.LABELS[kind], {"root": uuid, "role": kind, "target": uuid}, active
            )
            layer.setFlags(layer.flags() | QtCore.Qt.ItemIsUserCheckable)
            layer.setCheckState(
                0, QtCore.Qt.Checked if rig.layer_enabled(kind) else QtCore.Qt.Unchecked
            )
            for index, group in members.items():
                self._row(
                    layer,
                    "ドライバー {:02d}".format(index + 1),
                    {"root": uuid, "role": kind + ":" + str(index), "target": group.uuid()},
                )
        for kind in ("follow", "spring", "pose"):
            if rig.root.hasAttr("hrigEnabled_" + kind):
                attrs.append("hrigEnabled_" + kind)
        for name in attrs:
            self._attributes.add(
                (uuid, name),
                attribute=rig.root.plug(name),
                callback=self.schedule_refresh,
                kill_with_scene=True,
            )

    def _tweak_rows(self, rig, parent):
        """局所操作を全モジュール共通の独立行へ表示する。

        Args:
            rig: 対象モジュール。
            parent (QTreeWidgetItem): モジュール行。
        """
        for identifier, group in TweakLayer(rig).groups().items():
            active = rig.lod() == 1 and bool(group.plug("enabled").get())
            row = self._row(
                parent,
                "Tweak · " + identifier,
                dict(root=rig.root.uuid(), role="tweak:" + identifier, target=group.uuid()),
                active,
            )
            row.setFlags(row.flags() | QtCore.Qt.ItemIsUserCheckable)
            row.setCheckState(
                0, QtCore.Qt.Checked if group.plug("enabled").get() else QtCore.Qt.Unchecked
            )
            self._row(
                row,
                "操作コントロール",
                dict(
                    root=rig.root.uuid(),
                    role="tweakControl:" + identifier,
                    target=group.plug("control").sourceWithConversion().node().uuid(),
                ),
            )
            self._attributes.add(
                group.uuid(),
                attribute=group.plug("enabled"),
                callback=self.schedule_refresh,
                kill_with_scene=True,
            )

    def _control_rows(self, rig, parent):
        """指・Aimの設定と操作ノードを表示する。

        Args:
            rig (ControlRig): 対象。
            parent (QTreeWidgetItem): モジュール行。
        """
        kind = rig.kind()
        row = self._row(
            parent,
            self.LABELS[kind],
            dict(root=rig.root.uuid(), role=kind, target=rig.group("layer").uuid()),
            rig.lod() == 1 and rig.layer_enabled(kind),
        )
        row.setFlags(row.flags() | QtCore.Qt.ItemIsUserCheckable)
        row.setCheckState(0, QtCore.Qt.Checked if rig.layer_enabled(kind) else QtCore.Qt.Unchecked)
        for node in rig.members("controls"):
            self._row(
                row,
                node.name(),
                dict(root=rig.root.uuid(), role="control:" + node.uuid(), target=node.uuid()),
            )
        for attr in ("enabled", "lod"):
            self._attributes.add(
                (rig.root.uuid(), attr),
                attribute=rig.root.plug(attr),
                callback=self.schedule_refresh,
                kill_with_scene=True,
            )

    def edit_poses(self):
        """選択したスカート列の登録・編集パネルを開く。"""
        from .poseEditor import PoseEditor

        rig, data = self.current()
        if not isinstance(rig, SkirtRig):
            raise ValueError("スカートを選択してください")
        role = data["role"]
        index = int(role.split(":")[1]) if role.startswith(("spring:", "pose:", "driver:")) else 0
        self._pose_editor = PoseEditor(rig, index, self)
        self._pose_editor.show()

    def rows(self):
        """行を上から順に取得する。Maya同梱Qtのiterator寿命に依存しない。

        Returns:
            list[QTreeWidgetItem]: 現在の行。refresh後は再取得する。
        """
        result = []
        pending = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while pending:
            item = pending.pop(0)
            result.append(item)
            pending[0:0] = [item.child(i) for i in range(item.childCount())]
        return result

    def _selection_changed(self):
        """選択部位のMode/LODを表示する。選択自体はシーンを編集しない。"""
        if self._busy:
            return
        try:
            rig, _ = self.current()
            control = isinstance(rig, ControlRig)
            skirt = isinstance(rig, SkirtRig)
            spline = isinstance(rig, SplineRig)
            self.mode.setCurrentIndex(0 if skirt or control else int(rig.mode() == "ik"))
            self.lod.setCurrentIndex(rig.lod())
            enabled = True
        except ValueError:
            enabled = False
            control = False
            skirt = False
            spline = False
        self.lod.setEnabled(enabled)
        self.mode.setEnabled(enabled and not skirt and not control)
        self.mode.setToolTip(
            "Spline IK → FKは姿勢を維持。FK → IKは近似フィットし、最大位置誤差を表示します。"
            if spline
            else "姿勢を合わせてFK/IKを切り替えます。"
        )
        follow = str(self.layer_type.currentData()).startswith("follow")
        secondary = self.layer_type.currentData() in ("spring", "pose")
        stretch = self.layer_type.currentData() == "stretch"
        self.addButton.setEnabled(
            enabled
            and (
                self.layer_type.currentData() == "tweak"
                or (spline and stretch)
                or (skirt and (follow or secondary))
                or (not spline and not skirt and not control and not secondary)
            )
        )
        self.bake_button.setEnabled(enabled and skirt)
        self.pose_button.setEnabled(enabled and skirt)

    def _item_changed(self, item, column):
        """使用設定の変更を既存レイヤーAPIへ渡す。

        Args:
            item (QTreeWidgetItem): 変更行。
            column (int): 列。
        """
        if self._busy or column != 0:
            return
        data = item.data(0, QtCore.Qt.UserRole)
        enabled = item.checkState(0) == QtCore.Qt.Checked
        roots = [item.fullName() for item in hlib.ls(data["root"], long=True)] or []
        if roots and data["role"].startswith("tweak:"):
            group = hlib.getNode([item.fullName() for item in hlib.ls(data["target"], long=True)][0])
            with undoTransaction("hrig.Tweak.enabled"):
                group.plug("enabled").set(enabled)
                TweakLayer(ModuleRegistry.get(roots[0])).update()
            self.schedule_refresh()
        elif roots and data["role"] in self.OPTIONAL:
            self._run(
                partial(ModuleRegistry.get(roots[0]).set_layer_enabled, data["role"], enabled)
            )

    def _layer_options(self, *unused):
        """選んだサンプルで使う入力欄だけを表示する。

        Args:
            *unused: Qtシグナルの引数。
        """
        kind = self.layer_type.currentData()
        follow = kind.startswith("follow")
        self.count.setVisible(kind == "twist")
        self.component.setVisible(kind == "driven")
        self.axis.setVisible(kind == "driven" or follow)
        self.ratio.setVisible(follow)
        self.layer_hint.setText(
            {
                "tweak": "選択中のモジュール内の骨へ局所操作を追加。骨未選択なら先頭の変形骨を使用します。",
                "twist": "上側の2関節間に等間隔で補助骨を追加します。",
                "bend": "現在姿勢を基準に、50%回転の骨と内外の骨を追加します。",
                "driven": "中間関節の分解角 → SDK → サンプル骨のtranslateY。キー: -90°/-1、0°/0、90°/1。",
                "foot": "IKコントロールへリバースフットを追加します。",
                "soft": "モジュールに含まれるSoft IKを有効化します。",
                "helper": "モジュールに含まれる基本補助骨を有効化します。",
                "followTwist": "Twistだけを指定割合で追従。入力は腕脚の中間骨／スカートの先頭ドライバー。",
                "followSwing": "Swingだけを指定割合で追従。Twist軸を選択してください（スカートはY）。",
                "followHalf": "全回転をQuaternionで割合追従。50%なら入力回転の半分です。",
                "spring": "スカート先頭列を再生範囲でベイク。手付けの回転キーや設定を変えたら再ベイクしてください。",
                "pose": "スカート先頭ドライバーのRX/RZ → 4ポーズの回転補正。基準は0度、登録角は60度です。",
                "stretch": "腕脚・Splineへ伸縮と体積補正を追加。設定行を選択してChannel Boxで調整します。",
            }[kind]
        )
        self._selection_changed()

    def create_module(self):
        """入力名でモジュールを作り、その行を選択する。"""
        if self.module_type.currentIndex() == 6:
            from .fingerRig import FingerRig

            rig = FingerRig.create(self.module_name.text().strip())
        elif self.module_type.currentIndex() == 7:
            from .aimRig import AimRig

            rig = AimRig.create(self.module_name.text().strip())
        elif self.module_type.currentIndex() >= 4:
            rig = SplineRig.create(
                self.module_name.text().strip(),
                self.spline_joints.value(),
                self.spline_controls.value(),
                self.spline_length.value(),
                "y" if self.module_type.currentIndex() == 4 else "z",
            )
        elif self.module_type.currentIndex() >= 2:
            rig = SkirtRig.create(
                self.module_name.text().strip(),
                driver_count=4 if self.module_type.currentIndex() == 2 else 8,
                chain_count=self.skirt_count.value(),
                joints_per_chain=self.skirt_depth.value(),
                radius=self.skirt_radius.value(),
                length=self.skirt_length.value(),
            )
        else:
            rig = SampleBuilder.module(
                self.module_name.text().strip(), self.module_type.currentIndex() == 1
            )
        self.refresh()
        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            if item.data(0, QtCore.Qt.UserRole)["root"] == rig.root.uuid():
                self.tree.setCurrentItem(item)
        prefix = (
            ("spine" if self.module_type.currentIndex() == 4 else "tail")
            if self.module_type.currentIndex() >= 4
            else ("skirt" if self.module_type.currentIndex() >= 2 else "limb")
        )
        prefix = {6: "hand", 7: "look"}.get(self.module_type.currentIndex(), prefix)
        self.module_name.setText(
            SampleBuilder.next_id(set([item.name() for item in hlib.ls()]), prefix)
        )

    def add_layer(self):
        """選択モジュールにサンプルを追加する。"""
        rig, _ = self.current()
        if self.layer_type.currentData() == "tweak":
            selected = [
                n
                for n in (
                    [item.fullName() for item in hlib.ls(selection=True, type="joint", long=True)]
                    or []
                )
                if n.startswith(rig.root.fullName() + "|")
            ]
            layer = TweakLayer(rig)
            layer.add(
                SampleBuilder.next_id(set(layer.groups()), "tweak"),
                selected[0] if selected else rig.joints()[0],
            )
            return
        SampleBuilder.layer(
            rig,
            self.layer_type.currentData(),
            self.count.value(),
            self.component.currentText(),
            self.axis.currentText(),
            self.ratio.value() / 100,
        )

    @undoTransaction("hrig.LayerEditor.mode")
    def change_mode(self):
        """姿勢を合わせてFK/IKを切り替える。"""
        rig, _ = self.current()
        mode = ("fk", "ik")[self.mode.currentIndex()]
        message = None
        if mode != rig.mode():
            if isinstance(rig, SplineRig):
                if mode == "fk":
                    rig.match_fk()
                else:
                    error = rig.match_ik()
                    message = "Spline近似: 最大位置誤差 {:.6g}（現在の距離単位）".format(error)
            else:
                rig.match_fk() if mode == "fk" else rig.match_ik()
            rig.set_mode(mode)
        return message

    def change_lod(self):
        """選択部位のLODを変更する。"""
        self.current()[0].set_lod(self.lod.currentIndex())

    def bake_spring(self):
        """選択した揺れ列を再生範囲で再計算する。"""
        rig, data = self.current()
        if not isinstance(rig, SkirtRig):
            raise ValueError("Select a skirt module")
        role = data["role"]
        index = int(role.split(":")[1]) if role.startswith(("spring:", "pose:", "driver:")) else 0
        rig.bake_spring(index)

    def select_node(self):
        """現在行の設定ノードをMayaで選択する。"""
        _, data = self.current()
        names = [item.fullName() for item in hlib.ls(data["target"], long=True)] or []
        if names:
            hlib.select(names, replace=True)

    def open_graph(self):
        """設定ノードを選択し、標準ノードエディターを開く。"""
        self.select_node()
        NodeEditor.show()

    def open_curve(self):
        """SDKの詳細行を選択して、標準グラフエディターでカーブを編集する。"""
        _, data = self.current()
        node = hlib.getNode(
            ([item.fullName() for item in hlib.ls(data["target"], long=True)] or [""])[0]
        )
        if not node.hasAttr("curve"):
            raise ValueError("Driven Keyの子行（sdk1など）を選択してください")
        hlib.select(node.plug("curve").sourceWithConversion().node(), replace=True)
        GraphEditor.show()

    def closeEvent(self, event):
        """自身の監視を解除して閉じる。

        Args:
            event (QCloseEvent): Qt終了イベント。
        """
        self._closed = True
        self._jobs.stop()
        self._attributes.stop()
        super().closeEvent(event)

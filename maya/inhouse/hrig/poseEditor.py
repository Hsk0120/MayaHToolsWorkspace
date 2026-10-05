"""スカートのRBF回転補正を登録・編集するパネル。"""

from functools import partial

try:
    from PySide6 import QtWidgets, QtCore
except ImportError:
    from PySide2 import QtWidgets, QtCore

from hrig.setups import PoseRbf
from .secondaryLayer import SecondaryLayer


class PoseEditor(QtWidgets.QDialog):
    """入力ポーズと各骨XYZ補正角を表で編集する。変更は適用時のみシーンへ反映。"""

    def __init__(self, rig, driver_index=0, parent=None):
        """対象列の登録を読み込む。

        Args:
            rig (SkirtRig): 対象スカート。
            driver_index (int): 出力補正列。
            parent (QWidget | None): 親UI。
        """
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.setWindowTitle("hrig · ポーズ補正の登録・編集")
        self.resize(1050, 500)
        self.rig = rig
        self.index = driver_index
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(
            QtWidgets.QLabel(
                "入力・補正角は度。表の編集は「適用」で反映します。最低2ポーズ、重複不可。"
            )
        )
        self.driver = QtWidgets.QComboBox()
        self.driver.addItems(
            ["補正列 {:02d}".format(i + 1) for i in range(len(rig.driver_chains()))]
        )
        self.driver.setCurrentIndex(driver_index)
        self.driver.currentIndexChanged.connect(self._choose)
        layout.addWidget(self.driver)
        self.inputs_label = QtWidgets.QLabel()
        self.inputs_label.setWordWrap(True)
        layout.addWidget(self.inputs_label)
        self.scales = QtWidgets.QLineEdit()
        self.scales.setToolTip("入力ごとの正の距離スケールをカンマ区切りで指定")
        layout.addWidget(QtWidgets.QLabel("入力スケール（カンマ区切り）"))
        layout.addWidget(self.scales)
        self.table = QtWidgets.QTableWidget()
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        for label, action in (
            ("現在入力で登録", self.capture),
            ("選択行の入力を取得", self.recapture),
            ("選択行を削除", self.remove),
            ("シーンから再読込", self.reload),
            ("適用", self.apply),
        ):
            button = QtWidgets.QPushButton(label)
            button.clicked.connect(partial(self._run, action))
            row.addWidget(button)
        layout.addLayout(row)
        self.status = QtWidgets.QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.reload()

    def graph(self):
        """現在の補正グラフを保存参照から解決する。

        Returns:
            PoseRbf | None: 未登録ならNone。
        """
        group = SecondaryLayer(self.rig).groups().get(self.index)
        source = group.plug("poseGraph").sourceWithConversion() if group is not None else None
        return PoseRbf(source.node()) if source is not None else None

    def _choose(self, index):
        """列選択を変更し、編集表を再読込する。

        Args:
            index (int): 対象列。
        """
        self.index = index
        self._run(self.reload)

    def reload(self):
        """保存済みデータを読み込む。未登録列はRX/RZの2入力から開始する。"""
        graph = self.graph()
        width = len(self.rig.driver_chains()[self.index]) * 3
        data = graph.data() if graph else dict(poses=[], values=[], scales=[60, 60])
        if graph:
            names = []
            for i in range(len(data["scales"])):
                source = graph.container.plug("inputs[{}]".format(i)).sourceWithConversion()
                if source is not None and source.node().type() == "unitConversion":
                    source = source.node().plug("input").sourceWithConversion()
                names.append(source.fullName() if source is not None else "未接続")
        else:
            node = self.rig.driver_chains()[self.index][0]
            names = [node.name() + ".rotate" + axis for axis in "XZ"]
        self.inputs_label.setText(
            "入力順: " + " / ".join(names) + "\n列変更・再読込は未適用の編集を破棄します。"
        )
        self.input_count = len(data["scales"])
        self.output_count = width
        self.scales.setText(", ".join(str(v) for v in data["scales"]))
        self.table.setColumnCount(self.input_count + width)
        self.table.setHorizontalHeaderLabels(
            ["入力{} (度)".format(i + 1) for i in range(self.input_count)]
            + ["骨{} {}補正".format(i // 3 + 1, "XYZ"[i % 3]) for i in range(width)]
        )
        self.table.setRowCount(0)
        for pose, values in zip(data["poses"], data["values"]):
            self._append(list(pose) + list(values))
        self.status.setText(
            "未登録: この列の先頭骨のRX/RZを入力に使用。現在入力を2姿勢以上登録してください。"
            if not graph
            else "保存済み登録を読み込みました。Undo後は再読込してください。"
        )

    def _append(self, values):
        """数値行を表へ追加する。

        Args:
            values (list[float]): 入力と出力。
        """
        row = self.table.rowCount()
        self.table.insertRow(row)
        for column, value in enumerate(values):
            self.table.setItem(row, column, QtWidgets.QTableWidgetItem(format(value, ".12g")))
        self.table.selectRow(row)

    def inputs(self):
        """現在入力を度で取得する。

        Returns:
            list[float]: 入力値。
        """
        graph = self.graph()
        if graph:
            return graph.capture()
        joint = self.rig.driver_chains()[self.index][0]
        # hlibのscalar角度getはシーンの表示単位によらず度を返す。
        return [joint.plug("rotate" + a).get() for a in "XZ"]

    def capture(self):
        """現在入力とゼロ補正を新しい登録行へ追加する。"""
        self._append(self.inputs() + [0.0] * self.output_count)

    def recapture(self):
        """選択行の出力を保ち、入力のみ現在値へ置き換える。"""
        row = self.table.currentRow()
        if row < 0:
            raise ValueError("登録行を選択してください")
        for column, value in enumerate(self.inputs()):
            self.table.setItem(row, column, QtWidgets.QTableWidgetItem(format(value, ".12g")))

    def remove(self):
        """選択した登録行を表から削除する。"""
        for row in sorted({i.row() for i in self.table.selectedIndexes()}, reverse=True):
            self.table.removeRow(row)

    def apply(self):
        """検証済みデータをUndo可能な操作として適用する。"""
        rows = [
            [float(self.table.item(r, c).text()) for c in range(self.table.columnCount())]
            for r in range(self.table.rowCount())
        ]
        poses = [row[: self.input_count] for row in rows]
        values = [row[self.input_count :] for row in rows]
        scales = [float(value.strip()) for value in self.scales.text().split(",")]
        PoseRbf.coefficients(poses, values, scales)
        if len(scales) != self.input_count:
            raise ValueError("入力スケールの数が一致しません")
        graph = self.graph()
        if graph:
            graph.set_data(poses, values, scales)
        else:
            joint = self.rig.driver_chains()[self.index][0]
            SecondaryLayer(self.rig).add_pose(
                self.index, [joint.plug("rotateX"), joint.plug("rotateZ")], poses, values, scales
            )
        self.status.setText("{}ポーズを適用しました。".format(len(poses)))

    def _run(self, action, *unused):
        """UIのエラーを表示し、編集表を保持する。

        Args:
            action (callable): 操作。
            *unused: Qtシグナル引数。
        """
        try:
            action()
        except Exception as error:
            self.status.setText(str(error))

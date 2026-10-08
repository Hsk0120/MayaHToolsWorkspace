"""Gaussian RBFの係数を解き、Maya標準DGでポーズを評価する。"""

from maya import cmds

from hlib.json import JsonText as json
import math

import hlib

from hlib import getPlug as to_plug
from hlib.decorator import undoTransaction


class PoseRbf:
    """小規模ポーズセット向けの、履歴を持たない多入力・多出力補間。"""

    def __init__(self, container):
        """作成済みグラフを保持する。

        Args:
            container (str | Node): createで生成したcontainer。
        """
        self.container = hlib.nodes.Container(container)

    @staticmethod
    def coefficients(poses, values, scales):
        """Gaussianの補間係数を部分ピボット付き消去法で解く。

        Args:
            poses (Sequence[Sequence[float]]): 登録入力。
            values (Sequence[Sequence[float]]): 各登録入力での出力。
            scales (Sequence[float]): 入力軸ごとの正の距離スケール。

        Returns:
            list[list[float]]: poseごとの出力係数。
        """
        if not 2 <= len(poses) <= 64 or len(values) != len(poses) or not scales:
            raise ValueError("Expected 2..64 poses and corresponding values")
        if not values[0] or any(len(p) != len(scales) for p in poses):
            raise ValueError("Pose dimensions do not match")
        if any(len(v) != len(values[0]) for v in values):
            raise ValueError("Value dimensions do not match")
        if not all(math.isfinite(v) and v > 0 for v in scales):
            raise ValueError("Scales must be positive finite values")
        if not all(math.isfinite(v) for row in list(poses) + list(values) for v in row):
            raise ValueError("Pose data must be finite")
        size = len(poses)
        matrix = [
            [math.exp(-sum(((a - b) / s) ** 2 for a, b, s in zip(p, q, scales))) for q in poses]
            + list(values[i])
            for i, p in enumerate(poses)
        ]
        for column in range(size):
            pivot = max(range(column, size), key=lambda row: abs(matrix[row][column]))
            if abs(matrix[pivot][column]) < 1e-8:
                raise ValueError(
                    "Duplicate or ill-conditioned poses; separate poses or reduce scales"
                )
            matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
            divisor = matrix[column][column]
            matrix[column] = [v / divisor for v in matrix[column]]
            for row in range(size):
                if row != column:
                    factor = matrix[row][column]
                    matrix[row] = [a - factor * b for a, b in zip(matrix[row], matrix[column])]
        return [row[size:] for row in matrix]

    def _node(self, kind, suffix):
        """内部ノードを所有containerへ登録する。

        Args:
            kind (str): 標準ノード型。
            suffix (str): 用途。

        Returns:
            Node: 新規ノード。
        """
        node = hlib.nodes.Node.create(
            kind, name=self.container.getName() + "_" + suffix, skipSelect=True
        )
        self.container.addMembers(node)
        return node

    @classmethod
    @undoTransaction("hrig.PoseRbf.create")
    def create(cls, drivers, poses, values, scales, name="poseRbf"):
        """ポーズデータを標準演算ノードへ展開する。

        Args:
            drivers (Sequence[str | Plug]): 数値scalar入力。角度は度へ変換する。
            poses (Sequence[Sequence[float]]): 登録入力。角度は度。
            values (Sequence[Sequence[float]]): 登録出力。単位なし。
            scales (Sequence[float]): 入力ごとの距離スケール。
            name (str): 一意なcontainer名。

        Returns:
            PoseRbf: outputs配列を公開する補間グラフ。

        Note:
            Gaussian RBFであり、Maya Pose Editorとの互換形式ではない。
            Euler入力の180度ラップは扱わない。入力範囲外ではゼロへ減衰する。
            登録間で負値やオーバーシュートがあり得る。必要なら出力側で制限する。
        """
        coefficients = cls.coefficients(poses, values, scales)
        drivers = [to_plug(p) for p in drivers]
        if len(drivers) != len(scales) or cmds.objExists(name):
            raise ValueError("Driver count mismatch or name exists")
        for plug in drivers:
            kind = hlib.getAttr(plug.getFullName(), type=True)
            if (
                kind not in ("double", "float", "long", "short", "doubleAngle")
                or plug.isArray()
            ):
                raise ValueError("Use scalar numeric/angle drivers")
        graph = cls(hlib.nodes.Container.create(name=name))
        owner = graph.container
        for attr in ("inputs", "outputs", "coefficients"):
            owner.addAttr(longName=attr, attributeType="double", multi=True)
        owner.addAttr(longName="data", dataType="string")
        owner.getPlug("data").set(json.dumps(dict(poses=poses, values=values, scales=scales)))
        for index, source in enumerate(drivers):
            destination = owner.getPlug("inputs")[index]
            if hlib.getAttr(source.getFullName(), type=True) == "doubleAngle":
                convert = graph._node("unitConversion", "degrees{}".format(index))
                source.connectTo(convert.getPlug("input"))
                convert.getPlug("conversionFactor").set(180 / math.pi)
                convert.getPlug("output").connectTo(destination)
            else:
                source.connectTo(destination)
        graph._build(poses, values, scales, coefficients)
        return graph

    @undoTransaction("hrig.PoseRbf.set_values")
    def set_values(self, values):
        """登録入力を維持して、ポーズの出力値を編集する。

        Args:
            values (Sequence[Sequence[float]]): 元と同じ行数・出力数の新しい値。
        """
        data = json.loads(self.container.getPlug("data").get())
        coefficients = self.coefficients(data["poses"], values, data["scales"])
        if len(values[0]) != len(data["values"][0]):
            raise ValueError("Output count cannot change")
        for i, row in enumerate(coefficients):
            for j, value in enumerate(row):
                self.container.getPlug("coefficients")[i * len(row) + j].set(value)
        data["values"] = values
        self.container.getPlug("data").set(json.dumps(data))

    def data(self):
        """保存済みの登録入力・出力・スケールのコピーを取得する。

        Returns:
            dict: poses/values/scales。角度入力は度。
        """
        return json.loads(self.container.getPlug("data").get())

    def capture(self):
        """現在の入力を取得する。角度単位のUI設定によらず度を返す。

        Returns:
            list[float]: 入力順の値。
        """
        return [
            self.container.getPlug("inputs")[i].get()
            for i in range(len(self.data()["scales"]))
        ]

    def _build(self, poses, values, scales, coefficients):
        """入力口を保持して補間ノードを構築する。

        Args:
            poses (list): 入力行。
            values (list): 出力行。
            scales (list): 距離スケール。
            coefficients (list): 検証済み補間係数。
        """
        owner = self.container
        totals = [self._node("plusMinusAverage", "sum{}".format(i)) for i in range(len(values[0]))]
        for i, pose in enumerate(poses):
            distance = self._node("plusMinusAverage", "distance{}".format(i))
            for j, (center, scale) in enumerate(zip(pose, scales)):
                delta = self._node("plusMinusAverage", "delta{}_{}".format(i, j))
                delta.getPlug("operation").set(2)
                owner.getPlug("inputs")[j].connectTo(delta.getPlug("input1D")[0])
                delta.getPlug("input1D")[1].set(center)
                square = self._node("multiplyDivide", "square{}_{}".format(i, j))
                delta.getPlug("output1D").connectTo(square.getPlug("input1X"))
                delta.getPlug("output1D").connectTo(square.getPlug("input2X"))
                normalized = self._node("multiplyDivide", "scale{}_{}".format(i, j))
                square.getPlug("outputX").connectTo(normalized.getPlug("input1X"))
                normalized.getPlug("input2X").set(-1 / scale**2)
                normalized.getPlug("outputX").connectTo(distance.getPlug("input1D")[j])
            kernel = self._node("multiplyDivide", "kernel{}".format(i))
            kernel.getPlug("operation").set(3)
            kernel.getPlug("input1X").set(math.e)
            distance.getPlug("output1D").connectTo(kernel.getPlug("input2X"))
            for j, total in enumerate(totals):
                coefficient = owner.getPlug("coefficients")[i * len(totals) + j]
                coefficient.set(coefficients[i][j])
                weight = self._node("multiplyDivide", "weight{}_{}".format(i, j))
                kernel.getPlug("outputX").connectTo(weight.getPlug("input1X"))
                coefficient.connectTo(weight.getPlug("input2X"))
                weight.getPlug("outputX").connectTo(total.getPlug("input1D")[i])
        for j, total in enumerate(totals):
            total.getPlug("output1D").connectTo(owner.getPlug("outputs")[j])

    @undoTransaction("hrig.PoseRbf.set_data")
    def set_data(self, poses, values, scales):
        """外部接続を維持して登録の追加・削除・編集を反映する。

        Args:
            poses (Sequence[Sequence[float]]): 新しい2〜64登録入力。
            values (Sequence[Sequence[float]]): 各登録の出力。
            scales (Sequence[float]): 正の入力スケール。

        Note:
            入出力の次元数は変更できない。重複等を変更前に検証する。
            生成済み計算ノードを再構築するため、内部ノードへの独自接続は保持しない。
        """
        coefficients = self.coefficients(poses, values, scales)
        old = self.data()
        if len(scales) != len(old["scales"]) or len(values[0]) != len(old["values"][0]):
            raise ValueError("Input/output count cannot change")
        # 入力の角度変換ノードは残し、安定したcontainer入出力を保つ。
        keep = set()
        for i in range(len(scales)):
            source = self.container.getPlug("inputs")[i].getSourceWithConversion()
            if source is not None:
                keep.add(source.getNode().getUuid())
        owned = self.container.getMembers()
        remove = [n for n in owned if hlib.nodes.Node(n).getUuid() not in keep]
        if remove:
            hlib.delete(remove)
        self._build(poses, values, scales, coefficients)
        self.container.getPlug("data").set(json.dumps(dict(poses=poses, values=values, scales=scales)))

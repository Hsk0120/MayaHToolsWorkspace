"""Gaussian RBFの係数を解き、Maya標準DGでポーズを評価する。"""

from maya import cmds

from hlib.json import JsonText as json
import math

import hlib

from hlib import getPlug as to_plug
from hlib.decorators.undo import undo_transaction


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
            kind, name=self.container.name() + "_" + suffix, skipSelect=True
        )
        self.container.add(node)
        return node

    @classmethod
    @undo_transaction("hrig.PoseRbf.create")
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
            kind = hlib.getAttr(plug.full_name(), type=True)
            if (
                kind not in ("double", "float", "long", "short", "doubleAngle")
                or plug.mplug().isArray
            ):
                raise ValueError("Use scalar numeric/angle drivers")
        graph = cls(hlib.nodes.Container.create(name=name))
        owner = graph.container
        for attr in ("inputs", "outputs", "coefficients"):
            owner.add_attr(long_name=attr, attribute_type="double", multi=True)
        owner.add_attr(long_name="data", data_type="string")
        owner.plug("data").set(json.dumps(dict(poses=poses, values=values, scales=scales)))
        for index, source in enumerate(drivers):
            destination = owner.plug("inputs[{}]".format(index))
            if hlib.getAttr(source.full_name(), type=True) == "doubleAngle":
                convert = graph._node("unitConversion", "degrees{}".format(index))
                source.connect(convert.plug("input"))
                convert.plug("conversionFactor").set(180 / math.pi)
                convert.plug("output").connect(destination)
            else:
                source.connect(destination)
        graph._build(poses, values, scales, coefficients)
        return graph

    @undo_transaction("hrig.PoseRbf.set_values")
    def set_values(self, values):
        """登録入力を維持して、ポーズの出力値を編集する。

        Args:
            values (Sequence[Sequence[float]]): 元と同じ行数・出力数の新しい値。
        """
        data = json.loads(self.container.plug("data").get())
        coefficients = self.coefficients(data["poses"], values, data["scales"])
        if len(values[0]) != len(data["values"][0]):
            raise ValueError("Output count cannot change")
        for i, row in enumerate(coefficients):
            for j, value in enumerate(row):
                self.container.plug("coefficients[{}]".format(i * len(row) + j)).set(value)
        data["values"] = values
        self.container.plug("data").set(json.dumps(data))

    def data(self):
        """保存済みの登録入力・出力・スケールのコピーを取得する。

        Returns:
            dict: poses/values/scales。角度入力は度。
        """
        return json.loads(self.container.plug("data").get())

    def capture(self):
        """現在の入力を取得する。角度単位のUI設定によらず度を返す。

        Returns:
            list[float]: 入力順の値。
        """
        return [
            self.container.plug("inputs[{}]".format(i)).get()
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
                delta.plug("operation").set(2)
                owner.plug("inputs[{}]".format(j)).connect(delta.plug("input1D[0]"))
                delta.plug("input1D[1]").set(center)
                square = self._node("multiplyDivide", "square{}_{}".format(i, j))
                delta.plug("output1D").connect(square.plug("input1X"))
                delta.plug("output1D").connect(square.plug("input2X"))
                normalized = self._node("multiplyDivide", "scale{}_{}".format(i, j))
                square.plug("outputX").connect(normalized.plug("input1X"))
                normalized.plug("input2X").set(-1 / scale**2)
                normalized.plug("outputX").connect(distance.plug("input1D[{}]".format(j)))
            kernel = self._node("multiplyDivide", "kernel{}".format(i))
            kernel.plug("operation").set(3)
            kernel.plug("input1X").set(math.e)
            distance.plug("output1D").connect(kernel.plug("input2X"))
            for j, total in enumerate(totals):
                coefficient = owner.plug("coefficients[{}]".format(i * len(totals) + j))
                coefficient.set(coefficients[i][j])
                weight = self._node("multiplyDivide", "weight{}_{}".format(i, j))
                kernel.plug("outputX").connect(weight.plug("input1X"))
                coefficient.connect(weight.plug("input2X"))
                weight.plug("outputX").connect(total.plug("input1D[{}]".format(i)))
        for j, total in enumerate(totals):
            total.plug("output1D").connect(owner.plug("outputs[{}]".format(j)))

    @undo_transaction("hrig.PoseRbf.set_data")
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
            source = self.container.plug("inputs[{}]".format(i)).source()
            if source is not None:
                keep.add(source.node.uuid())
        owned = self.container.members()
        remove = [n for n in owned if hlib.nodes.Node(n).uuid() not in keep]
        if remove:
            hlib.delete(remove)
        self._build(poses, values, scales, coefficients)
        self.container.plug("data").set(json.dumps(dict(poses=poses, values=values, scales=scales)))

"""二点間、またはTransformの原点間の距離を扱う。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..util import _ArgumentError, _UNSET
from .node import Node
from .transform import Transform


class DistanceBetween(Node):
    """distanceBetweenノードを参照し、inMatrix1/2で変換したpoint1/2間の距離を評価する。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新（Undoなし）。途中の変更は自動で戻さない。

    Note:
        distance・point1/2のアトリビュート型はMayaの版で異なる(2027は単位なしのdouble、
        2022〜2025は距離型)。mlibの値はどの版でもcmで扱うが、UI単位がcm以外のときの
        ``cmds.getAttr`` の値は版により変わる。
    """

    def setPoints(self, point1, point2, *, fast=False):
        """各入力マトリクスの空間で二点をcmで設定する。マトリクスは変更しない。

        両方の点を検証してからpoint1、point2の順に書く。途中の書込み失敗は先行変更を戻さない。

        Args:
            point1 (Iterable[float]): 第一の点。XYZ順の有限な3成分、cm。
            point2 (Iterable[float]): 第二の点。同じ単位・形式。
            fast (bool): 既定Falseは通常更新。TrueはUndoなしのOpenMaya更新。

        Returns:
            DistanceBetween: 自身。

        Raises:
            TypeError: fastがbool以外、または座標を数値列へ変換できない型の場合。
            ValueError: 座標が3成分でない、不正な数値文字列、または非有限値の場合。
            RuntimeError: ロックや入力接続などで設定できない場合。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibDistanceBetweenSetPoints"):
            import math

            points = [tuple(float(v) for v in point) for point in (point1, point2)]
            if any(len(point) != 3 or not all(math.isfinite(v) for v in point) for point in points):
                raise ValueError("Points must contain three finite coordinates")
            for name, point in zip(("point1", "point2"), points):
                self.getPlug(name).set(point, fast=fast)
            return self

    def connectTransforms(self, first, second, force=_UNSET, *, f=_UNSET):
        """二つのTransformのワールドマトリクスを接続し、原点間距離を測る。

        両方のTransformを解決して型を検査し、point1/2を原点へ戻した後にマトリクスを順に接続する。
        失敗時の先行変更は戻さない。Undoは有効時だけ記録する。

        Args:
            first (Transform | str): 第一のTransform。ラッパーが解決したDAGパスを使う。
            second (Transform | str): 第二のTransform。
            force (bool): 既存のマトリクス入力接続を置き換えるか。 別名 ``f`` も使用可能。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            DistanceBetween: 自身。point1/2は原点にリセットする。

        Raises:
            TypeError: Transform以外を指定した場合。
            RuntimeError: ロックや既存接続により変更できない場合。
        """
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if force is _UNSET:
            force = False
        with undoChunk("mlibDistanceBetweenConnectTransforms"):
            from .node import Node as _InputNode
            nodes = [_InputNode._resolve_input(first), _InputNode._resolve_input(second)]
            if not all(isinstance(node, Transform) for node in nodes):
                raise TypeError("Both inputs must be transforms")
            self.setPoints((0, 0, 0), (0, 0, 0))
            for number, node in enumerate(nodes, 1):
                index = node.mpath().instanceNumber()
                node.getPlug("worldMatrix")[index].connectTo(
                    self.getPlug(f"inMatrix{number}"), force=force)
            return self

    def getDistance(self):
        """評価済み距離。内部距離単位cm。

        Returns:
            float: 評価済み距離。内部距離単位cm。
        """
        return self.getPlug("distance").get()

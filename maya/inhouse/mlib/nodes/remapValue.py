"""ランプで値を再マッピングする。色ランプも操作できる。"""

from . import _calculation
from .node import Node

#: ランプの種類から、ランプ・出力のアトリビュート名。
_RAMPS = {"value": ("value", "outValue"), "color": ("color", "outColor")}


class RemapValue(Node):
    """ランプで値を再マッピングする。色ランプも操作できる。

    ランプは ``kind`` で選ぶ。``"value"`` は値のランプ(``value``。出力 ``outValue``)、``"color"`` は色のランプ
    (``color``。出力 ``outColor``)。ランプの点は :class:`~mlib.plugs.rampPlug.RampPlug` で扱う。
    """

    def setInput(self, inputValue=None, inputMin=None, inputMax=None, outputMin=None, outputMax=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            inputValue (float | Plug | str | None): 再マッピングする値。
            inputMin (float | Plug | str | None): 入力の範囲の下限(ランプの位置0)。
            inputMax (float | Plug | str | None): 入力の範囲の上限(ランプの位置1)。
            outputMin (float | Plug | str | None): 出力の範囲の下限(ランプの値0)。
            outputMax (float | Plug | str | None): 出力の範囲の上限(ランプの値1)。

        Returns:
            RemapValue: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "inputValue": inputValue,
            "inputMin": inputMin,
            "inputMax": inputMax,
            "outputMin": outputMin,
            "outputMax": outputMax,
        })

    def getRampPoints(self, kind="value"):
        """ランプの点を、位置の昇順で取得する(:meth:`RampPlug.getEntries` と同じ)。

        Args:
            kind (str): ``"value"`` は値のランプ、``"color"`` は色のランプ。

        Returns:
            list[tuple[float, float | tuple[float, float, float], str]]: (位置, 値, 補間の名前)の並び。

        Raises:
            ValueError: kindが ``"value"``・``"color"`` 以外の場合。
        """
        return self._ramp(kind).getEntries()

    def setRampPoints(self, points, kind="value"):
        """ランプの点を、既存の点をすべて置き換えて設定する(:meth:`RampPlug.setEntries` と同じ)。1回のUndoで戻せる。

        Args:
            points (list[tuple[float, float | tuple[float, float, float], str]]): (位置, 値, 補間の名前)の並び。
                補間は ``"none"``・``"linear"``・``"smooth"``・``"spline"``。
            kind (str): ``"value"`` は値のランプ、``"color"`` は色のランプ。

        Returns:
            RemapValue: 自身。

        Raises:
            TypeError: 点の形・型が不正な場合。
            ValueError: kindが未対応、pointsが空、数値が有限でない、または補間が未対応の名前の場合。
            RuntimeError: ノードが無効な場合、またはMayaが設定を拒否した場合。
        """
        self._ramp(kind).setEntries(points)
        return self

    def addRampPoint(self, position, value, interpolation="linear", kind="value"):
        """ランプへ点を1つ足す。既存の点は残す。1回のUndoで戻せる。

        Args:
            position (float): ランプ上の位置。
            value (float | Iterable[float]): 値(色のランプは ``(r, g, b)``)。
            interpolation (str): ``"none"``・``"linear"``・``"smooth"``・``"spline"``。
            kind (str): ``"value"`` は値のランプ、``"color"`` は色のランプ。

        Returns:
            RemapValue: 自身。

        Raises:
            TypeError: 位置・値・補間の型が不正な場合。
            ValueError: kind・補間が未対応、または数値が有限でない場合。
            RuntimeError: ノードが無効な場合、またはMayaが設定を拒否した場合。
        """
        ramp = self._ramp(kind)
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            value = tuple(value)
        ramp.setEntries(ramp.getEntries() + [(position, value, interpolation)])
        return self

    def getResult(self, kind="value"):
        """出力の現在の値を取得する。

        Args:
            kind (str): ``"value"`` は ``outValue``、``"color"`` は ``outColor``。

        Returns:
            float | tuple[float, float, float]: 再マッピングした値、または色(RGB)。

        Raises:
            ValueError: kindが ``"value"``・``"color"`` 以外の場合。
        """
        return self.getOutputPlug(kind).get()

    def getOutputPlug(self, kind="value"):
        """出力のアトリビュートを取得する(接続元に使う)。

        Args:
            kind (str): ``"value"`` は ``outValue``、``"color"`` は ``outColor``。

        Returns:
            Plug: 出力のアトリビュート。

        Raises:
            ValueError: kindが ``"value"``・``"color"`` 以外の場合。
        """
        return self.getPlug(_RAMPS[_calculation.choice(kind, _RAMPS, "kind")][1])

    def _ramp(self, kind):
        """ランプのアトリビュートを取得する。

        Args:
            kind (str): ``"value"`` または ``"color"``。

        Returns:
            RampPlug: ランプのアトリビュート。

        Raises:
            ValueError: kindが ``"value"``・``"color"`` 以外の場合。
        """
        return self.getPlug(_RAMPS[_calculation.choice(kind, _RAMPS, "kind")][0])

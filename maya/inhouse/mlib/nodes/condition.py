"""2値の比較により出力を切り替える。"""

from . import _calculation
from .node import Node

#: 比較の種類の名前(Mayaの ``operation`` の番号順)。
_OPERATIONS = ("equal", "notEqual", "greaterThan", "greaterOrEqual", "lessThan", "lessOrEqual")


class Condition(Node):
    """2値の比較により出力を切り替える。"""

    def setInput(self, firstTerm=None, secondTerm=None, colorIfTrue=None, colorIfFalse=None):
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            firstTerm (float | Plug | str | None): 比較する1つ目の値。
            secondTerm (float | Plug | str | None): 比較する2つ目の値。
            colorIfTrue (Iterable[float] | Plug | str | None): 比較が成り立つときの出力(RGB)。
            colorIfFalse (Iterable[float] | Plug | str | None): 比較が成り立たないときの出力(RGB)。

        Returns:
            Condition: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        return _calculation.set_inputs(self, "setInput", {
            "firstTerm": firstTerm,
            "secondTerm": secondTerm,
            "colorIfTrue": colorIfTrue,
            "colorIfFalse": colorIfFalse,
        })

    def getOperation(self):
        """比較の種類を名前で取得する(``operation``)。

        Returns:
            str: ``"equal"``・``"notEqual"``・``"greaterThan"``・``"greaterOrEqual"``・``"lessThan"``・
                ``"lessOrEqual"`` のいずれか。
        """
        return _calculation.get_enum(self, "operation", _OPERATIONS)

    def setOperation(self, operation):
        """比較の種類を名前または番号で設定する(``operation``)。1回のUndoで戻せる。

        Args:
            operation (str | int): ``"equal"``・``"notEqual"``・``"greaterThan"``・``"greaterOrEqual"``・``"lessThan"``・
                ``"lessOrEqual"`` のいずれか、またはMayaの番号(0から)。

        Returns:
            Condition: 自身。

        Raises:
            TypeError: operationが文字列・int以外の場合。
            ValueError: 未対応の名前・範囲外の番号の場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込みを拒否した場合。
        """
        return _calculation.set_enum(self, "setOperation", "operation", operation, _OPERATIONS, "operation")

    def getResult(self):
        """出力 ``outColor`` の現在の値を取得する。

        Returns:
            tuple[float, float, float]: 比較の結果の色(RGB)。
        """
        return self.getOutputPlug().get()

    def getOutputPlug(self):
        """出力のアトリビュート ``outColor`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        return self.getPlug("outColor")

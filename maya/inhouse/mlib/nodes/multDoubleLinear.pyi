# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""距離型の2入力を乗算する(Maya 2026以降の型名は ``multDL``)。"""

from . import _calculation
from .node import Node
from mlib.plugs.plug import Plug



class MultDoubleLinear(Node):
    """距離型の2入力を乗算する。

    Maya 2026で ``multDoubleLinear`` は ``multDL`` へ改名された。mlibはどの版でも両方の型名を
    受け付け(``createNode``・``ls(type=)``・``isType``)、どちらの型のノードもこのクラスで扱う。
    ``getType()`` はその版の実際の型名を返す。``MultDL`` は同じクラスの別名。
    """
    def setInput(self, input1: float | Plug | str | None = ..., input2: float | Plug | str | None = ...) -> MultDoubleLinear:
        """主な入力をまとめて設定する。値は書き込み、Plug は接続する。

        Plug・MPlug・``"node.attr"`` の文字列は接続元として接続し(既存の入力は置き換える)、それ以外は
        値として書き込む(接続されていれば先に外す)。Noneの入力は変更しない。1回のUndoで戻せる。

        Args:
            input1 (float | Plug | str | None): 1つ目の値。
            input2 (float | Plug | str | None): 2つ目の値。

        Returns:
            MultDoubleLinear: 自身。

        Raises:
            TypeError: 接続元の型が不正な場合。
            RuntimeError: ノードが無効な場合、またはMayaが書込み・接続を拒否した場合(それまでの変更は戻す)。
        """
        ...
    def getResult(self) -> float:
        """出力 ``output`` の現在の値を取得する。

        Returns:
            float: input1 * input2。
        """
        ...
    def getOutputPlug(self) -> Plug:
        """出力のアトリビュート ``output`` を取得する(接続元に使う)。

        Returns:
            Plug: 出力のアトリビュート。
        """
        ...
MultDL = MultDoubleLinear

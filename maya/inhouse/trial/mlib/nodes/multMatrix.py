"""マトリクスを配列の順番で乗算するmultMatrixを扱う。"""

from ..decorator import _edit_context, _pick_alias
from ..maths import Matrix
from ..util import _ArgumentError, _UNSET
from .node import Node


class MultMatrix(Node):
    """matrixInの論理インデックス順にマトリクスを乗算する。"""

    def getInputPlug(self, index=_UNSET, *, idx=_UNSET):
        """既存入力のPlugを取得する。未存在要素は作成しない。

        Args:
            index (int): 非負の論理インデックス。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Plug: 入力アトリビュートの参照。

        Raises:
            ValueError: indexが整数でない・負数・boolの場合。
            IndexError: 指定した入力要素が存在しない、または番号が論理番号の範囲(0..2147483647)を超える場合。
        """
        index = _pick_alias(index, idx, "index", "idx")
        plug = self.getPlug("matrixIn")[self._index(index)]
        if index not in self.getPlug("matrixIn").mplug().getExistingArrayAttributeIndices():
            raise IndexError(f"No input at logical index {index}")
        return plug

    def getInput(self, index=_UNSET, *, idx=_UNSET):
        """既存入力の評価値を取得する。接続済みなら接続元を評価する。

        Args:
            index (int): 入力の論理インデックス。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Matrix: 現在の入力値。

        Raises:
            ValueError: indexが整数でない・負数・boolの場合。
            IndexError: 入力要素が存在しない、または番号が範囲外の場合。
        """
        index = _pick_alias(index, idx, "index", "idx")
        return self.getInputPlug(index).get()

    def setInput(self, index=_UNSET, value=_UNSET, *, fast=False, idx=_UNSET):
        """指定スロットに定数マトリクスを設定する。入力接続は切断しない。

        Args:
            index (int): 非負の論理インデックス。 別名 ``idx`` も使用可能。
            value (Matrix | Iterable[float]): Maya規約のマトリクス。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            MultMatrix: 自身。

        Raises:
            ValueError: インデックスが整数でない・負数・boolの場合、またはマトリクスが不正な場合。
            IndexError: インデックスが論理番号の範囲(0..2147483647)を超える場合。
            RuntimeError: ロックや入力接続により設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        index = _pick_alias(index, idx, "index", "idx")
        if value is _UNSET:
            raise _ArgumentError("Missing required argument: 'value'")
        with _edit_context("mlibMultMatrixSetInput", fast):
            index = self._index(index)
            value = Matrix(value)
            self.getPlug("matrixIn")[index].set(value, fast=fast)
            return self

    def connectInput(self, index=_UNSET, source=_UNSET, force=_UNSET, *, fast=False, idx=_UNSET, src=_UNSET, f=_UNSET):
        """マトリクスPlugを指定スロットへ接続する。

        Args:
            index (int): 非負の論理インデックス。 別名 ``idx`` も使用可能。
            source (Plug): 接続元のマトリクスPlug。 別名 ``src`` も使用可能。
            force (bool): 既存入力を置き換えるか。 別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。
            src (Plug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            MultMatrix: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: インデックスが整数でない・負数・boolの場合。
            IndexError: インデックスが論理番号の範囲(0..2147483647)を超える場合。
            RuntimeError: 型不一致などでMayaが接続を拒否した場合。
        """
        index = _pick_alias(index, idx, "index", "idx")
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _edit_context("mlibMultMatrixConnectInput", fast):
            index = self._index(index)
            from ..plugs.plug import Plug
            source = Plug._resolve_input(source)
            source.connectTo(self.getPlug("matrixIn")[index], force=force, fast=fast)
            return self

    def getOutputPlug(self):
        """matrixSum出力。別ノードへの接続に使用する。

        Returns:
            MatrixPlug: matrixSum出力。別ノードへの接続に使用する。
        """
        return self.getPlug("matrixSum")

    def getResult(self):
        """現在の入力を乗算した評価済みマトリクス。

        Returns:
            Matrix: 現在の入力を乗算した評価済みマトリクス。
        """
        return self.getOutputPlug().get()

    @staticmethod
    def _index(index):
        """非負の整数インデックスを検証する。型・負数はValueError、上限超えはIndexError。

        Args:
            index: 対象要素の番号または探索開始番号。
        """
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Matrix index must be a non-negative integer")
        from ..plugs.arrayPlug import ArrayPlug
        return ArrayPlug._validate_index(index)

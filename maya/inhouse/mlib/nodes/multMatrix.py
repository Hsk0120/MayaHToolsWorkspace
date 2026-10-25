"""マトリクスを配列の順番で乗算するmultMatrixを扱う。"""

from contextlib import nullcontext

from ..decorator import undoChunk
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
            ValueError: indexが非負整数でない場合。
            IndexError: 指定した入力要素が存在しない、または番号が範囲外の場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
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
            IndexError: 入力要素が存在しない場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
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
            ValueError: インデックスやマトリクスが不正な場合。
            RuntimeError: ロックや入力接続により設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        if value is _UNSET:
            raise _ArgumentError("Missing required argument: 'value'")
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibMultMatrixSetInput"):
            index = self._index(index)
            value = Matrix(value)
            self.getPlug("matrixIn")[index].set(value, fast=fast)
            return self

    def connectInput(self, index=_UNSET, source=_UNSET, force=_UNSET, *, idx=_UNSET, src=_UNSET, f=_UNSET):
        """マトリクスPlugを指定スロットへ接続する。

        Args:
            index (int): 非負の論理インデックス。 別名 ``idx`` も使用可能。
            source (Plug): 接続元のマトリクスPlug。 別名 ``src`` も使用可能。
            force (bool): 既存入力を置き換えるか。 別名 ``f`` も使用可能。
            idx (int): indexの別名。同時指定は不可。
            src (Plug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            MultMatrix: 自身。

        Raises:
            ValueError: インデックスが不正な場合。
            RuntimeError: 型不一致などでMayaが接続を拒否した場合。
        """
        if idx is not _UNSET:
            if index is not _UNSET:
                raise _ArgumentError("Specify only one of 'index' and 'idx'")
            index = idx
        if src is not _UNSET:
            if source is not _UNSET:
                raise _ArgumentError("Specify only one of 'source' and 'src'")
            source = src
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if index is _UNSET:
            raise _ArgumentError("Missing required argument: 'index'")
        if source is _UNSET:
            raise _ArgumentError("Missing required argument: 'source'")
        if force is _UNSET:
            force = False
        with undoChunk("mlibMultMatrixConnectInput"):
            index = self._index(index)
            from ..plugs.plug import Plug
            source = Plug._resolve_input(source)
            source.connectTo(self.getPlug("matrixIn")[index], force=force)
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
        """非負の整数インデックスを検証する。不正値はValueError。

        Args:
            index: 対象要素の番号または探索開始番号。
        """
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Matrix index must be a non-negative integer")
        from ..plugs.arrayPlug import ArrayPlug
        return ArrayPlug._validate_index(index)

"""マトリクスを変換成分に分解するdecomposeMatrixを扱う。"""

from contextlib import nullcontext

from ..decorator import undoChunk
from ..maths import Matrix
from ..maths.eulerRotate import orderIndex
from ..util import _ArgumentError, _UNSET
from .node import Node


class DecomposeMatrix(Node):
    """Mayaのマトリクス分解ノード。接続先の親空間やjointOrientの補正は行わない。"""

    def getInputPlug(self):
        """inputMatrixの参照。

        Returns:
            MatrixPlug: inputMatrixの参照。
        """
        return self.getPlug("inputMatrix")

    def getInput(self):
        """現在の入力マトリクス。接続済みなら接続元を評価する。

        Returns:
            Matrix: 現在の入力マトリクス。接続済みなら接続元を評価する。
        """
        return self.getInputPlug().get()

    def setInput(self, value, *, fast=False):
        """定数マトリクスを入力する。入力接続は切断しない。

        Args:
            value (Matrix | Iterable[float]): Maya規約のマトリクス。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            RuntimeError: ロックや入力接続により設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibDecomposeMatrixSetInput"):
            self.getPlug("inputMatrix").set(Matrix(value), fast=fast)
            return self

    def getRotateOrder(self):
        """入力回転順序。MayaのrotateOrderと同じ番号0〜5。

        Returns:
            int: 入力回転順序。MayaのrotateOrderと同じ番号0〜5。
        """
        return self.getPlug("inputRotateOrder").get()

    def setRotateOrder(self, order, *, fast=False):
        """出力Euler回転の回転順序を指定する。

        Args:
            order (str | int): xyz、yzx、zxy、xzy、yxz、zyxのいずれかの名前(大文字小文字を
                問わない)、または番号0〜5(``EulerRotate.order`` やrotateOrderアトリビュートと同じ
                並び。``om2.MEulerRotation.kXYZ``〜``kZYX``)。
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            ValueError: 未対応の回転順序(範囲外の番号、boolを含む)の場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        with nullcontext() if fast else undoChunk("mlibDecomposeMatrixRotateOrder"):
            self.getPlug("inputRotateOrder").set(orderIndex(order), fast=fast)
            return self

    def connectInput(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """マトリクスPlugを入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元のマトリクスPlug。 別名 ``src`` も使用可能。
            force (bool): 既存入力を置き換えるか。 別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            TypeError: fastがbool以外、またはsourceがPlug・名前・MPlugのいずれでもない、または名前がアトリビュートを指していない場合。
            ValueError: sourceが空文字列または空のMPlugの場合。
            RuntimeError: 名前を解決できない場合、または型不一致などでMayaが接続を拒否した場合。
        """
        if src is not _UNSET:
            if source is not _UNSET:
                raise _ArgumentError("Specify only one of 'source' and 'src'")
            source = src
        if f is not _UNSET:
            if force is not _UNSET:
                raise _ArgumentError("Specify only one of 'force' and 'f'")
            force = f
        if source is _UNSET:
            raise _ArgumentError("Missing required argument: 'source'")
        if force is _UNSET:
            force = False
        if not isinstance(fast, bool):
            raise TypeError("fast must be a bool")
        from ..plugs.plug import Plug
        source = Plug._resolve_input(source)
        with nullcontext() if fast else undoChunk("mlibDecomposeMatrixConnectInput"):
            source.connectTo(self.getPlug("inputMatrix"), force=force, fast=fast)
            return self

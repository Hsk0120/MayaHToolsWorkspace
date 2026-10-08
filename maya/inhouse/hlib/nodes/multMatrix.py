"""行列を配列の順番で乗算するmultMatrixを扱う。"""

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Matrix
from .node import Node


class MultMatrix(Node):
    """matrixInの論理インデックス順に行列を乗算する。"""

    @flag_aliases(idx="index")
    def getInputPlug(self, index):
        """既存入力のPlugを取得する。未存在要素は作成しない。

        Args:
            index (int): 非負の論理インデックス。 別名 ``idx`` も使用可能。
        Returns:
            Plug: 入力アトリビュートの参照。
        Raises:
            ValueError: indexが非負整数でない場合。
            IndexError: 指定した入力要素が存在しない、または番号が範囲外の場合。
        """
        plug = self.getPlug("matrixIn")[self._index(index)]
        if index not in self.getPlug("matrixIn").mplug().getExistingArrayAttributeIndices():
            raise IndexError(f"No input at logical index {index}")
        return plug

    @flag_aliases(idx="index")
    def getInput(self, index):
        """既存入力の評価値を取得する。接続済みなら接続元を評価する。

        Args:
            index (int): 入力の論理インデックス。 別名 ``idx`` も使用可能。
        Returns:
            Matrix: 現在の入力値。
        Raises:
            IndexError: 入力要素が存在しない場合。
        """
        return self.getInputPlug(index).get()

    @flag_aliases(idx="index")
    @fast_edit
    @undoChunk("hlibMultMatrixSetInput")
    def setInput(self, index, value, *, fast=False):
        """指定スロットに定数行列を設定する。入力接続は切断しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            index (int): 非負の論理インデックス。 別名 ``idx`` も使用可能。
            value (Matrix | Iterable[float]): Maya規約の行列。

        Returns:
            MultMatrix: 自身。

        Raises:
            ValueError: インデックスや行列が不正な場合。
            RuntimeError: ロックや入力接続により設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        index = self._index(index)
        value = Matrix(value)
        self.getPlug("matrixIn")[index].set(value)
        return self

    @flag_aliases(idx="index", src="source", f="force")
    @undoChunk("hlibMultMatrixConnectInput")
    def connectInput(self, index, source, force=False):
        """行列Plugを指定スロットへ接続する。

        Args:
            index (int): 非負の論理インデックス。 別名 ``idx`` も使用可能。
            source (Plug): 接続元の行列Plug。 別名 ``src`` も使用可能。
            force (bool): 既存入力を置き換えるか。 別名 ``f`` も使用可能。

        Returns:
            MultMatrix: 自身。

        Raises:
            ValueError: インデックスが不正な場合。
            RuntimeError: 型不一致などでMayaが接続を拒否した場合。
        """
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
        """現在の入力を乗算した評価済み行列。

        Returns:
            Matrix: 現在の入力を乗算した評価済み行列。
        """
        return self.getOutputPlug().get()

    @_getter_alias(getInputPlug)
    def inputPlug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInputPlug(*args, **kwargs)

    @_getter_alias(getInput)
    def input(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInput(*args, **kwargs)

    @_getter_alias(getOutputPlug)
    def outputPlug(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getOutputPlug(*args, **kwargs)

    @_getter_alias(getResult)
    def result(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getResult(*args, **kwargs)

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

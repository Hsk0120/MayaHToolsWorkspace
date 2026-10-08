"""行列を変換成分に分解するdecomposeMatrixを扱う。"""

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
from ..decorator import undoChunk
from ..maths import Matrix
from ..maths.eulerRotation import orderIndex
from .node import Node


class DecomposeMatrix(Node):
    """Mayaの行列分解ノード。接続先の親空間やjointOrientの補正は行わない。"""

    def getInputPlug(self):
        """inputMatrixの参照。

        Returns:
            MatrixPlug: inputMatrixの参照。
        """
        return self.getPlug("inputMatrix")

    def getInput(self):
        """現在の入力行列。接続済みなら接続元を評価する。

        Returns:
            Matrix: 現在の入力行列。接続済みなら接続元を評価する。
        """
        return self.getInputPlug().get()

    @fast_edit
    @undoChunk("hlibDecomposeMatrixSetInput")
    def setInput(self, value, *, fast=False):
        """定数行列を入力する。入力接続は切断しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (Matrix | Iterable[float]): Maya規約の行列。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            RuntimeError: ロックや入力接続により設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self.getPlug("inputMatrix").set(Matrix(value))
        return self

    def getRotateOrder(self):
        """入力回転順序。MayaのrotateOrderと同じ番号0〜5。

        Returns:
            int: 入力回転順序。MayaのrotateOrderと同じ番号0〜5。
        """
        return self.getPlug("inputRotateOrder").get()

    @fast_edit
    @undoChunk("hlibDecomposeMatrixRotateOrder")
    def setRotateOrder(self, order, *, fast=False):
        """出力Euler回転の回転順序を指定する。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            order (str | int): xyz、yzx、zxy、xzy、yxz、zyxのいずれかの名前(大文字小文字を
                問わない)、または番号0〜5(``EulerRotation.order`` やrotateOrderアトリビュートと同じ
                並び。``om2.MEulerRotation.kXYZ``〜``kZYX``)。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            ValueError: 未対応の回転順序(範囲外の番号、boolを含む)の場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        self.getPlug("inputRotateOrder").set(orderIndex(order))
        return self

    @flag_aliases(src="source", f="force")
    @undoChunk("hlibDecomposeMatrixConnectInput")
    def connectInput(self, source, force=False):
        """行列Plugを入力へ接続する。

        Args:
            source (Plug): 接続元の行列Plug。 別名 ``src`` も使用可能。
            force (bool): 既存入力を置き換えるか。 別名 ``f`` も使用可能。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            RuntimeError: 型不一致などでMayaが接続を拒否した場合。
        """
        source.connectTo(self.getPlug("inputMatrix"), force=force)
        return self

    def outputPlugs(self):
        """dict[str, Plug]: translate・rotate・scale・shearをキーとする出力Plug。

        rotateの子Plug.get()はrad、translateはcmで返す。
        出力を接続する場合はMayaが接続先のアトリビュート単位を扱う。
        """
        return {key: self.getPlug(name) for key, name in (
            ("translate", "outputTranslate"), ("rotate", "outputRotate"),
            ("scale", "outputScale"), ("shear", "outputShear"))}

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

    @_getter_alias(getRotateOrder)
    def rotateOrder(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getRotateOrder(*args, **kwargs)

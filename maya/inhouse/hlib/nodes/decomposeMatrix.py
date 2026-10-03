"""行列を変換成分に分解するdecomposeMatrixを扱う。"""

from .._core.registry import node_wrapper
from ..decorators._fast import fast_edit
from ..decorators.undo import undoChunk
from ..maths import Matrix
from ..maths.eulerRotation import orderIndex
from .node import Node


@node_wrapper("decomposeMatrix")
class DecomposeMatrix(Node):
    """Mayaの行列分解ノード。接続先の親空間やjointOrientの補正は行わない。"""

    def inputPlug(self):
        """MatrixPlug: inputMatrixの参照。"""
        return self.plug("inputMatrix")

    def getInput(self):
        """Matrix: 現在の入力行列。接続済みなら接続元を評価する。"""
        return self.inputPlug().get()

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
        self.plug("inputMatrix").set(Matrix(value))
        return self

    def getRotateOrder(self):
        """int: 入力回転順序。MayaのrotateOrderと同じ番号0〜5。"""
        return self.plug("inputRotateOrder").get()

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
        self.plug("inputRotateOrder").set(orderIndex(order))
        return self

    @undoChunk("hlibDecomposeMatrixConnectInput")
    def connectInput(self, source, force=False):
        """行列Plugを入力へ接続する。

        Args:
            source (Plug): 接続元の行列Plug。
            force (bool): 既存入力を置き換えるか。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            RuntimeError: 型不一致などでMayaが接続を拒否した場合。
        """
        source.connect(self.plug("inputMatrix"), force=force)
        return self

    def outputPlugs(self):
        """dict[str, Plug]: translate・rotate・scale・shearをキーとする出力Plug。

        rotateの子Plug.get()はrad、translateはcmで返す。
        出力を接続する場合はMayaが接続先のアトリビュート単位を扱う。
        """
        return {key: self.plug(name) for key, name in (
            ("translate", "outputTranslate"), ("rotate", "outputRotate"),
            ("scale", "outputScale"), ("shear", "outputShear"))}

"""行列を変換成分に分解するdecomposeMatrixを扱う。"""

from ..decorators._fast import fast_edit

from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..maths import Matrix
from ..maths.eulerRotation import order_index
from .node import Node


@node_wrapper("decomposeMatrix")
class DecomposeMatrix(Node):
    """Mayaの行列分解ノード。接続先の親空間やjointOrientの補正は行わない。"""

    def input_plug(self):
        """MatrixPlug: inputMatrixの参照。"""
        return self.plug("inputMatrix")

    def get_input(self):
        """Matrix: 現在の入力行列。接続済みなら接続元を評価する。"""
        return self.input_plug().get()

    def get_rotate_order(self):
        """int: 入力回転順序。MayaのrotateOrderと同じ番号0〜5。"""
        return self.plug("inputRotateOrder").get()

    @fast_edit
    @undo_chunk("hlibDecomposeMatrixSetInput")
    def set_input(self, value, *, fast=False):
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

    @undo_chunk("hlibDecomposeMatrixConnectInput")
    def connect_input(self, source, force=False):
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

    @fast_edit
    @undo_chunk("hlibDecomposeMatrixRotateOrder")
    def set_rotate_order(self, order, *, fast=False):
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
        self.plug("inputRotateOrder").set(order_index(order))
        return self

    def output_plugs(self):
        """dict[str, Plug]: translate・rotate・scale・shearをキーとする出力Plug。

        rotateの子Plug.get()は度、translateは現在の距離表示単位で返す。
        出力を接続する場合はMayaが接続先のアトリビュート単位を扱う。
        """
        return {key: self.plug(name) for key, name in (
            ("translate", "outputTranslate"), ("rotate", "outputRotate"),
            ("scale", "outputScale"), ("shear", "outputShear"))}

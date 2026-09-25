"""行列を変換成分に分解するdecomposeMatrixを扱う。"""

from ..decorators._fast import fast_edit

from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from ..maths import Matrix
from .node import Node


@node_wrapper("decomposeMatrix")
class DecomposeMatrix(Node):
    """Mayaの行列分解ノード。接続先の親空間やjointOrientの補正は行わない。"""

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
            order (str): xyz、yzx、zxy、xzy、yxz、zyxのいずれか。

        Returns:
            DecomposeMatrix: 自身。

        Raises:
            ValueError: 未対応の回転順序の場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        """
        orders = ("xyz", "yzx", "zxy", "xzy", "yxz", "zyx")
        if order not in orders:
            raise ValueError("Unsupported rotation order")
        self.plug("inputRotateOrder").set(orders.index(order))
        return self

    def output_plugs(self):
        """dict[str, Plug]: translate・rotate・scale・shearをキーとする出力Plug。

        rotateの子Plug.get()は度、translateは現在の距離表示単位で返す。
        出力を接続する場合はMayaが接続先の属性単位を扱う。
        """
        return {key: self.plug(name) for key, name in (
            ("translate", "outputTranslate"), ("rotate", "outputRotate"),
            ("scale", "outputScale"), ("shear", "outputShear"))}

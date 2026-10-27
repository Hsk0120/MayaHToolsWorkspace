"""内積・外積・マトリクスによる点/ベクトル変換。"""

from ..decorator import _pick_alias
from ..maths import Matrix, Vector
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .shadingDependNode import ShadingDependNode


class VectorProduct(ShadingDependNode):
    """vectorProductノードを参照し、内積・外積・マトリクスによる点/ベクトル変換を扱う。

    値設定では入力接続を切らない。通常編集はUndo有効時にまとめ、fast=TrueはUndo設定を変えないOM2直接更新(Undoなし)。途中の変更は自動で戻さない。
    """

    def getInputPlug(self, index=_UNSET, *, idx=_UNSET):
        """入力のPlugを取得する。

        Args:
            index (int): 入力番号1または2。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        index = _pick_alias(index, idx, "index", "idx")
        return self.getPlug(f"input{_Calculation.index(index, (1, 2))}")

    def getInput(self, index=_UNSET, *, idx=_UNSET):
        """入力の評価値を取得する。

        Args:
            index (int): 入力番号1または2。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            tuple[float, float, float]: 現在の値。
        """
        index = _pick_alias(index, idx, "index", "idx")
        return self.getInputPlug(index).get()

    def setInput(self, index=_UNSET, value=_UNSET, *, fast=False, idx=_UNSET):
        """入力へ定数値を設定する。

        Args:
            index (int): 入力番号1または2。
            value (Iterable[float]): XYZ順の有限な3成分。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。
        """
        index = _pick_alias(index, idx, "index", "idx")
        if value is _UNSET:
            raise _ArgumentError("Missing required argument: 'value'")
        with _Calculation.edit_context(self, "setInput", fast):
            _Calculation.set_value(value, _Calculation.vector, self.getInputPlug, index, fast=fast)
            return self

    def connectInput(self, index=_UNSET, source=_UNSET, force=_UNSET, *, fast=False, idx=_UNSET, src=_UNSET, f=_UNSET):
        """入力へ接続する。

        Args:
            index (int): 入力番号1または2。
            source (Plug | str | MPlug): 接続元。別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。
        """
        index = _pick_alias(index, idx, "index", "idx")
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectInput", fast):
            _Calculation.connect(source, self.getInputPlug, index, force=force, fast=fast)
            return self

    def getOperation(self):
        """現在のモード名を取得する。

        Returns:
            str: none, dot, cross, vector_matrix, point_matrix。
        """
        return _Calculation.enum_name(self.getPlug("operation"), ("none", "dot", "cross", "vector_matrix", "point_matrix"))

    def setOperation(self, mode, *, fast=False):
        """vectorProductの演算モードを設定する。

        Args:
            mode (str | int): none, dot, cross, vector_matrix, point_matrix、またはMayaの番号。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            VectorProduct: 自身。
        """
        with _Calculation.edit_context(self, "setOperation", fast):
            value = _Calculation.enum_value(mode, ("none", "dot", "cross", "vector_matrix", "point_matrix"))
            self.getPlug("operation").set(value, fast=fast)
            return self

    def getMatrixPlug(self):
        """マトリクスのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("matrix")

    def getMatrix(self):
        """マトリクスの評価値を取得する。

        Returns:
            Matrix: 現在の値。
        """
        return self.getMatrixPlug().get()

    def setMatrix(self, value, *, fast=False):
        """マトリクスへ定数値を設定する。

        Args:
            value (Matrix | Iterable[float]): Matrix(value)で解釈するマトリクス。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            VectorProduct: 自身。
        """
        with _Calculation.edit_context(self, "setMatrix", fast):
            _Calculation.set_value(value, Matrix, self.getMatrixPlug, fast=fast)
            return self

    def connectMatrix(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """マトリクスへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectMatrix", fast):
            _Calculation.connect(source, self.getMatrixPlug, force=force, fast=fast)
            return self

    def getNormalizeOutput(self):
        """出力正規化の評価値を取得する。

        Returns:
            bool: 現在の値。
        """
        return self.getPlug("normalizeOutput").get()

    def setNormalizeOutput(self, value, *, fast=False):
        """出力正規化へ定数値を設定する。

        Args:
            value (bool): 出力を正規化するか。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。

        Returns:
            VectorProduct: 自身。
        """
        with _Calculation.edit_context(self, "setNormalizeOutput", fast):
            _Calculation.set_value(value, _Calculation.boolean, self.getPlug, "normalizeOutput", fast=fast)
            return self

    def connectNormalizeOutput(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """出力正規化へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。別名 ``src`` も使用可能。
            force (bool): 既存接続を置き換えるか。別名 ``f`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            VectorProduct: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectNormalizeOutput", fast):
            _Calculation.connect(source, self.getPlug, "normalizeOutput", force=force, fast=fast)
            return self

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。

        Returns:
            Vector: 計算結果。
        """
        return Vector(self.getPlug("output").get())

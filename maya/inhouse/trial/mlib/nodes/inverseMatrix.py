"""逆マトリクスを計算する。Maya付属matrixNodesの明示的なロードが必要。"""

from ..decorator import _pick_alias
from ..maths import Matrix
from ..util import _UNSET
from ._calculation import _Calculation
from .THdependNode import THDependNode


class InverseMatrix(THDependNode):
    """inverseMatrixノードを参照し、逆マトリクスを評価する。Maya付属matrixNodesの明示的なロードが必要。

    値設定は入力接続を切断しない。通常の設定・接続はUndo有効時にチャンクへ記録する。
    設定・接続のfast=TrueはUndoなしのOM2直接更新で、Undo設定は変えない。途中失敗の変更は自動で戻さない。
    """

    def getInputPlug(self):
        """入力のPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("inputMatrix")

    def getInput(self):
        """入力の評価値を取得する。

        Returns:
            Matrix: 現在の値。
        """
        return self.getInputPlug().get()

    def setInput(self, value, *, fast=False):
        """入力へ定数値を設定する。

        Args:
            value (Matrix | Iterable[float]): Matrix(value)で解釈するマトリクス。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            InverseMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setInput", fast):
            value = Matrix(value)
            self.getInputPlug().set(value, fast=fast)
            return self

    def connectInput(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """入力へ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            InverseMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectInput", fast):
            # plugs は nodes を参照するため、循環importを避けて呼出し時に取得する。
            from ..plugs.plug import Plug
            Plug._resolve_input(source).connectTo(self.getInputPlug(), force=force, fast=fast)
            return self

    def getOutputPlug(self):
        """計算結果の接続用Plugを取得する。

        Returns:
            Plug: 出力参照。
        """
        return self.getPlug("outputMatrix")

    def getResult(self):
        """現在の入力をMayaで評価した結果を取得する。

        Returns:
            Matrix: 計算結果。
        """
        return Matrix(self.getOutputPlug().get())

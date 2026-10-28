"""論理番号順にマトリクスをブレンドする。加重平均ではない。"""

from ..decorator import _pick_alias
from ..maths import Matrix
from ..util import _ArgumentError, _UNSET
from ._calculation import _Calculation
from .node import Node


class BlendMatrix(Node):
    """blendMatrixノードを参照し、論理番号順のマトリクスブレンドを扱う。加重平均ではない。

    ターゲットは疎な論理番号で扱い、getTargetPlugは既存要素だけを参照する。
    値設定は入力接続を切断しない。通常の設定・接続・削除はUndo有効時にチャンクへ記録する。
    設定・接続・削除のfast=TrueはUndoなしのOM2直接更新。Undo設定は変えず、途中失敗の変更は自動で戻さない。
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
            BlendMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setInput", fast):
            _Calculation.set_value(value, Matrix, self.getInputPlug, fast=fast)
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
            BlendMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectInput", fast):
            _Calculation.connect(source, self.getInputPlug, force=force, fast=fast)
            return self

    def getEnvelopePlug(self):
        """全体ウェイトのPlugを取得する。

        Returns:
            Plug: 接続・値操作用の参照。
        """
        return self.getPlug("envelope")

    def getEnvelope(self):
        """全体ウェイトの評価値を取得する。

        Returns:
            float: 現在の値。
        """
        return self.getEnvelopePlug().get()

    def setEnvelope(self, value, *, fast=False):
        """全体ウェイトへ定数値を設定する。

        Args:
            value (float): 有限な全体ウェイト。
            fast (bool): TrueはUndoなしのOpenMaya更新。

        Returns:
            BlendMatrix: 自身。
        """
        with _Calculation.edit_context(self, "setEnvelope", fast):
            _Calculation.set_value(value, _Calculation.scalar, self.getEnvelopePlug, fast=fast)
            return self

    def connectEnvelope(self, source=_UNSET, force=_UNSET, *, fast=False, src=_UNSET, f=_UNSET):
        """全体ウェイトへ接続する。

        Args:
            source (Plug | str | MPlug): 接続元。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。
        """
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectEnvelope", fast):
            _Calculation.connect(source, self.getEnvelopePlug, force=force, fast=fast)
            return self

    def getTargetIndices(self):
        """既存ターゲットの論理番号を取得する。

        Returns:
            list[int]: 疎な論理番号。
        """
        return list(self.getPlug("target").mplug().getExistingArrayAttributeIndices())

    def getTargetPlug(self, index=_UNSET, *, idx=_UNSET):
        """既存ターゲットを参照する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            CompoundPlug: ターゲット。
        """
        index = _pick_alias(index, idx, "index", "idx")
        plug = self.getPlug("target")[_Calculation.index(index)]
        if index not in self.getTargetIndices():
            raise IndexError(f"No target at logical index {index}")
        return plug

    def connectTarget(self, index=_UNSET, source=_UNSET, weight=1.0, force=_UNSET, *, fast=False, idx=_UNSET,
        src=_UNSET, f=_UNSET):
        """マトリクスPlugをターゲットへ接続し、その後ウェイトを設定する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            source (Plug | str | MPlug): 接続元。
            weight (float): 有限なウェイト。
            force (bool): Trueで既存の入力接続を置き換える。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。
            src (Plug | str | MPlug): sourceの別名。同時指定は不可。
            f (bool): forceの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。ウェイト設定が失敗しても、先に完了した接続は残る(fast=Trueでも同じ)。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 番号・ウェイトが不正な場合。
            RuntimeError: ロックや型不一致などで接続・設定できない場合。

        Note:
            weightを省略すると1.0を設定する(既存のウェイトは引き継がない)。
            Undoでは接続とウェイト設定をまとめて戻す。接続前から要素があった場合も、
            MayaのconnectAttrのUndoにより要素ごと消え、以前のウェイトは戻らない(Mayaの挙動)。
            ``fast=True`` は通常と同じ検証の後、接続とウェイト設定をOpenMayaで直接行う(Undoなし)。
            接続後にウェイト設定が失敗した場合も接続は残り、自動では戻さない。
        """
        index = _pick_alias(index, idx, "index", "idx")
        source = _pick_alias(source, src, "source", "src")
        force = _pick_alias(force, f, "force", "f", default=False)
        with _Calculation.edit_context(self, "connectTarget", fast):
            # plugs は nodes を参照するため、循環importを避けて呼出し時に取得する。
            from ..plugs.plug import Plug
            index = _Calculation.index(index)
            source, weight = Plug._resolve_input(source), _Calculation.scalar(weight)
            target = self.getPlug("target")[index]
            source.connectTo(target["targetMatrix"], force=force, fast=fast)
            target["weight"].set(weight, fast=fast)
            return self

    def removeTarget(self, index=_UNSET, *, fast=False, idx=_UNSET):
        """指定論理番号のターゲット要素を、接続ごと削除する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
        """
        index = _pick_alias(index, idx, "index", "idx")
        with _Calculation.edit_context(self, "removeTarget", fast):
            self.getPlug("target").removeElement(_Calculation.index(index), fast=fast)
            return self

    def getTarget(self, index=_UNSET, *, idx=_UNSET):
        """ターゲットの評価値を取得する。

        Args:
            index (int): 既存の論理番号。 別名 ``idx`` も使用可能。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            dict: matrix/weight。
        """
        index = _pick_alias(index, idx, "index", "idx")
        target = self.getTargetPlug(index)
        return {"matrix": Matrix(target["targetMatrix"].get()), "weight": target["weight"].get()}

    def setTarget(self, index=_UNSET, matrix=_UNSET, weight=1.0, *, fast=False, idx=_UNSET):
        """ターゲットのマトリクスとウェイトを順に設定する。

        番号・マトリクス・有限ウェイトを検証してから書き込む。ウェイト設定が失敗しても、先に設定したマトリクスは残る。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            matrix (Matrix | Iterable[float]): マトリクス。
            weight (float): 有限なウェイト。上限は無い。
            fast (bool): TrueはUndoなしのOpenMaya更新。既定False。
            idx (int): indexの別名。同時指定は不可。

        Returns:
            BlendMatrix: 自身。

        Raises:
            TypeError: fastがbool以外の場合。
            ValueError: 番号・マトリクス・ウェイトが不正な場合。
            RuntimeError: ロックや入力接続により設定できない場合。

        ``fast=True`` は通常と同じ検証の後にOpenMayaで直接更新する(Undoなし)。
        完了済みの直接更新は自動で戻さない。
        """
        index = _pick_alias(index, idx, "index", "idx")
        if matrix is _UNSET:
            raise _ArgumentError("Missing required argument: 'matrix'")
        with _Calculation.edit_context(self, "setTarget", fast):
            index = _Calculation.index(index)
            matrix, weight = Matrix(matrix), _Calculation.scalar(weight)
            target = self.getPlug("target")[index]
            target["targetMatrix"].set(matrix, fast=fast)
            target["weight"].set(weight, fast=fast)
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

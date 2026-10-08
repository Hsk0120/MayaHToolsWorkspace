"""重み付き加算ノード。ウェイトの正規化はしない。"""

import math

import maya.cmds as cmds

from .._core.flags import flag_aliases
from .._core.getterAlias import _getter_alias
from ..common._fast import fast_edit
from ..decorator import undoChunk
from .node import Node


class BlendWeighted(Node):
    """input[i] * weight[i]を合計する。weightの既定値は1。"""

    def getInputIndices(self):
        """存在するinputの論理番号。疎な配列を保持する。

        Returns:
            list[int]: 存在するinputの論理番号。疎な配列を保持する。
        """
        return list(self.getPlug("input").mplug().getExistingArrayAttributeIndices())

    def getInputPlugs(self):
        """既存入力の番号とPlug。

        Returns:
            dict[int, Plug]: 既存入力の番号とPlug。
        """
        return {i: self.getPlug("input")[i] for i in self.getInputIndices()}

    def getWeights(self):
        """既存inputに対応するウェイト。未設定要素は1。

        Returns:
            dict[int, float]: 既存inputに対応するウェイト。未設定要素は1。
        """
        return {i: self.getWeight(i) for i in self.getInputIndices()}

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
        plug = self.getPlug("input")[self._index(index)]
        if index not in self.getInputIndices():
            raise IndexError(f"No input at logical index {index}")
        return plug

    @flag_aliases(idx="index")
    def getInput(self, index):
        """既存入力の評価値を取得する。接続済みなら接続元を評価する。

        Args:
            index (int): 入力の論理インデックス。 別名 ``idx`` も使用可能。
        Returns:
            float: 現在の入力値。
        Raises:
            IndexError: 入力要素が存在しない場合。
        """
        return self.getInputPlug(index).get()

    @flag_aliases(idx="index")
    @fast_edit
    @undoChunk("hlibBlendWeightedInput")
    def setInput(self, index, value, *, fast=False):
        """定数入力を設定する。既存接続は切断しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            value (float): 有限の入力値。
        Returns:
            BlendWeighted: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        return self._set("input", index, value)

    @flag_aliases(idx="index")
    def getWeight(self, index):
        """既存inputに対応する倍率を取得する。未設定weightは1を返す。

        Args:
            index (int): inputの論理インデックス。 別名 ``idx`` も使用可能。
        Returns:
            float: 評価済み倍率。未設定のweight要素は作成しない。
        Raises:
            IndexError: inputが存在しない場合。
        """
        self.getInputPlug(index)
        weights = self.getPlug("weight")
        if index not in weights.mplug().getExistingArrayAttributeIndices():
            return 1.0
        return weights[index].get()

    @flag_aliases(idx="index")
    @fast_edit
    @undoChunk("hlibBlendWeightedWeight")
    def setWeight(self, index, value, *, fast=False):
        """ウェイトを設定する。負値も使用可能。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            value (float): 有限の倍率。
        Returns:
            BlendWeighted: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        return self._set("weight", index, value)

    @flag_aliases(idx="index", src="source", f="force")
    @undoChunk("hlibBlendWeightedConnect")
    def connectInput(self, index, source, force=False):
        """入力を接続する。

        Args:
            index (int): 非負の論理番号。 別名 ``idx`` も使用可能。
            source (Plug): 接続元。 別名 ``src`` も使用可能。
            force (bool): 既存接続を置換するか。 別名 ``f`` も使用可能。
        Returns:
            BlendWeighted: 自身。
        """
        index = self._index(index)
        target = f"{self.getFullName()}.input[{index}]"
        if index in self.getInputIndices() and not cmds.listConnections(target, source=True, destination=False):
            # connectAttrのUndoだけでは配列要素の定数値が失われるため履歴に記録する。
            self.getPlug("input")[index].set(self.getPlug("input")[index].get())
        cmds.connectAttr(source.getFullName(), target, force=force)
        return self

    def getOutputPlug(self):
        """出力プラグ。

        Returns:
            Plug: 出力プラグ。
        """
        return self.getPlug("output")

    def getResult(self):
        """現在の重み付き合計。

        Returns:
            float: 現在の重み付き合計。
        """
        return self.getOutputPlug().get()

    @_getter_alias(getInputIndices)
    def inputIndices(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInputIndices(*args, **kwargs)

    @_getter_alias(getInputPlugs)
    def inputPlugs(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getInputPlugs(*args, **kwargs)

    @_getter_alias(getWeights)
    def weights(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getWeights(*args, **kwargs)

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

    @_getter_alias(getWeight)
    def weight(self, *args, **kwargs):
        """get付きの取得メソッドへ委譲する省略入口。

        Args:
            *args: 正式getterへ渡す位置引数。
            **kwargs: 正式getterへ渡すキーワード引数。

        Returns:
            object: 正式getterと同じ戻り値。

        Note:
            引数・例外・単位・Undoの仕様は正式getterと同じ。
        """
        return self.getWeight(*args, **kwargs)

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
        """非負の整数を検証する。不正値はValueError。

        Args:
            index: 対象要素の番号または探索開始番号。
        """
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Expected a non-negative integer index")
        from ..plugs.arrayPlug import ArrayPlug
        return ArrayPlug._validate_index(index)

    def _set(self, attr, index, value):
        """有限値を設定する。通常はcmds、fastは保持するMPlugへ書く。

        Args:
            attr: 対象のアトリビュート名または保存情報。
            index: 対象要素の番号または探索開始番号。
            value: 変換・設定する入力値。
        """
        index, value = self._index(index), float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        self.getPlug(attr)[index].set(value)
        return self

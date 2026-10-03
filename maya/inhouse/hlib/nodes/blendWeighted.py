"""重み付き加算ノード。ウェイトの正規化はしない。"""

from ..decorators._fast import fast_edit

import math
import maya.cmds as cmds
from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from .node import Node


@node_wrapper("blendWeighted")
class BlendWeighted(Node):
    """input[i] * weight[i]を合計する。weightの既定値は1。"""

    @staticmethod
    def _index(index):
        """非負の整数を検証する。不正値はValueError。"""
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Expected a non-negative integer index")
        from ..plugs.arrayPlug import ArrayPlug
        return ArrayPlug._validate_index(index)

    def inputIndices(self):
        """list[int]: 存在するinputの論理番号。疎な配列を保持する。"""
        return list(self.plug("input").mplug().getExistingArrayAttributeIndices())

    def inputPlugs(self):
        """dict[int, Plug]: 既存入力の番号とPlug。"""
        return {i: self.plug("input").element(i) for i in self.inputIndices()}

    def getWeights(self):
        """dict[int, float]: 既存inputに対応するウェイト。未設定要素は1。"""
        return {i: self.getWeight(i) for i in self.inputIndices()}

    def _set(self, attr, index, value):
        """有限値を設定する。通常はcmds、fastは保持するMPlugへ書く。"""
        index, value = self._index(index), float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        self.plug(attr)._element_reference(index).set(value)
        return self

    def inputPlug(self, index):
        """既存入力のPlugを取得する。未存在要素は作成しない。

        Args:
            index (int): 非負の論理インデックス。
        Returns:
            Plug: 入力アトリビュートの参照。
        Raises:
            ValueError: indexが非負整数でない場合。
            IndexError: 指定した入力要素が存在しない、または番号が範囲外の場合。
        """
        return self.plug("input").element(self._index(index))

    def getInput(self, index):
        """既存入力の評価値を取得する。接続済みなら接続元を評価する。

        Args:
            index (int): 入力の論理インデックス。
        Returns:
            float: 現在の入力値。
        Raises:
            IndexError: 入力要素が存在しない場合。
        """
        return self.inputPlug(index).get()

    def getWeight(self, index):
        """既存inputに対応する倍率を取得する。未設定weightは1を返す。

        Args:
            index (int): inputの論理インデックス。
        Returns:
            float: 評価済み倍率。未設定のweight要素は作成しない。
        Raises:
            IndexError: inputが存在しない場合。
        """
        self.inputPlug(index)
        weights = self.plug("weight")
        if index not in weights.mplug().getExistingArrayAttributeIndices():
            return 1.0
        return weights.element(index).get()

    @fast_edit
    @undoChunk("hlibBlendWeightedInput")
    def setInput(self, index, value, *, fast=False):
        """定数入力を設定する。既存接続は切断しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            index (int): 非負の論理番号。
            value (float): 有限の入力値。
        Returns:
            BlendWeighted: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        return self._set("input", index, value)

    @fast_edit
    @undoChunk("hlibBlendWeightedWeight")
    def setWeight(self, index, value, *, fast=False):
        """ウェイトを設定する。負値も使用可能。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            index (int): 非負の論理番号。
            value (float): 有限の倍率。
        Returns:
            BlendWeighted: 自身。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        return self._set("weight", index, value)

    @undoChunk("hlibBlendWeightedConnect")
    def connectInput(self, index, source, force=False):
        """入力を接続する。

        Args:
            index (int): 非負の論理番号。
            source (Plug): 接続元。
            force (bool): 既存接続を置換するか。
        Returns:
            BlendWeighted: 自身。
        """
        index = self._index(index)
        target = f"{self.fullName()}.input[{index}]"
        if index in self.inputIndices() and not cmds.listConnections(target, source=True, destination=False):
            # connectAttrのUndoだけでは配列要素の定数値が失われるため履歴に記録する。
            self.plug("input").element(index).set(self.plug("input").element(index).get())
        cmds.connectAttr(source.fullName(), target, force=force)
        return self

    def outputPlug(self):
        """Plug: 出力プラグ。"""
        return self.plug("output")

    def result(self):
        """float: 現在の重み付き合計。"""
        return self.outputPlug().get()

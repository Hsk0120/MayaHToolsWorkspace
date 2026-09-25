"""重み付き加算ノード。ウェイトの正規化はしない。"""

from ..decorators._fast import fast_edit
from .._core.fast_write import set_attr

import math
import maya.cmds as cmds
from .._core.registry import node_wrapper
from ..decorators.undo import undo_chunk
from .node import Node


@node_wrapper("blendWeighted")
class BlendWeighted(Node):
    """input[i] * weight[i]を合計する。weightの既定値は1。"""

    @staticmethod
    def _index(index):
        """非負の整数を検証する。不正値はValueError。"""
        if isinstance(index, bool) or not isinstance(index, int) or index < 0:
            raise ValueError("Expected a non-negative integer index")
        return index

    def input_indices(self):
        """list[int]: 存在するinputの論理番号。疎な配列を保持する。"""
        return cmds.getAttr(self.full_name() + ".input", multiIndices=True) or []

    def input_plugs(self):
        """dict[int, Plug]: 既存入力の番号とPlug。"""
        return {i: self.plug("input").element(i) for i in self.input_indices()}

    def weights(self):
        """dict[int, float]: 既存inputに対応するウェイト。未設定要素は1。"""
        return {i: cmds.getAttr(f"{self.full_name()}.weight[{i}]") for i in self.input_indices()}

    def _set(self, attr, index, value):
        """有限値をcmdsで設定する。呼び出し元がUndoをまとめる。"""
        index, value = self._index(index), float(value)
        if not math.isfinite(value):
            raise ValueError("Expected a finite value")
        set_attr(f"{self.full_name()}.{attr}[{index}]", value)
        return self

    @fast_edit
    @undo_chunk("hlibBlendWeightedInput")
    def set_input(self, index, value, *, fast=False):
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
    @undo_chunk("hlibBlendWeightedWeight")
    def set_weight(self, index, value, *, fast=False):
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

    @undo_chunk("hlibBlendWeightedConnect")
    def connect_input(self, index, source, force=False):
        """入力を接続する。

        Args:
            index (int): 非負の論理番号。
            source (Plug): 接続元。
            force (bool): 既存接続を置換するか。
        Returns:
            BlendWeighted: 自身。
        """
        index = self._index(index)
        target = f"{self.full_name()}.input[{index}]"
        if index in self.input_indices() and not cmds.listConnections(target, source=True, destination=False):
            # connectAttrのUndoだけでは配列要素の定数値が失われるため履歴に記録する。
            set_attr(target, cmds.getAttr(target))
        cmds.connectAttr(source.full_name(), target, force=force)
        return self

    def output(self):
        """Plug: 出力プラグ。"""
        return self.plug("output")

    def result(self):
        """float: 現在の重み付き合計。"""
        return self.output().get()

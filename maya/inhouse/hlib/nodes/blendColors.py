"""二つのRGB入力をblenderで補間する。"""

from ..decorators._fast import fast_edit

import math
import maya.cmds as cmds
from .._core.registry import node_wrapper
from ..decorators.undo import undoChunk
from .node import Node


@node_wrapper("blendColors")
class BlendColors(Node):
    """color1 * blender + color2 * (1 - blender)を評価するノード。"""

    @staticmethod
    def _index(index):
        """入力番号1または2を検証する。不正値はValueError。"""
        if isinstance(index, bool) or not isinstance(index, int) or index not in (1, 2):
            raise ValueError("Color index must be 1 or 2")
        return index

    def colorPlug(self, index):
        """入力色のPlugを取得する。

        Args:
            index (int): Mayaアトリビュート名に対応する1または2。
        Returns:
            CompoundPlug: RGB入力。get()で値を取得できる。
        """
        return self.plug(f"color{self._index(index)}")

    def getColor(self, index):
        """指定した入力の RGB 値を取得する。

        Args:
            index (int): 入力番号。colorPlug() の番号規約に従う。

        Returns:
            tuple[float, float, float]: 計算用 RGB。表示色 Color へは変換しない。
        """
        return tuple(self.colorPlug(index).get())

    @fast_edit
    @undoChunk("hlibBlendColorsSetColor")
    def setColor(self, index, value, *, fast=False):
        """入力色を設定する。既存接続は切断しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            index (int): 1または2。
            value (Iterable[float]): RGB順の有限な3要素。0～1には制限しない。
        Returns:
            BlendColors: 自身。
        Raises:
            ValueError: 番号、要素数、数値が不正な場合。
            RuntimeError: ロックや接続によりMayaが設定を拒否した場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        target = self.colorPlug(index)
        values = tuple(float(v) for v in value)
        if len(values) != 3 or not all(math.isfinite(v) for v in values):
            raise ValueError("Color must contain three finite values")
        target.set(values)
        return self

    @undoChunk("hlibBlendColorsConnectColor")
    def connectColor(self, index, source, force=False):
        """入力色へ接続する。互換性はMayaが判定する。

        Args:
            index (int): 1または2。
            source (Plug): 接続元の3要素Plug。
            force (bool): 既存接続を置換するか。
        Returns:
            BlendColors: 自身。
        """
        source.connect(self.colorPlug(index), force=force)
        return self

    def blenderPlug(self):
        """Plug: 補間係数。0ならcolor2、1ならcolor1。"""
        return self.plug("blender")

    def getBlender(self):
        """補間係数の評価値を取得する。

        Returns:
            float: color2からcolor1への補間係数。
        """
        return self.blenderPlug().get()

    @fast_edit
    @undoChunk("hlibBlendColorsSetBlender")
    def setBlender(self, value, *, fast=False):
        """補間係数を設定する。既存接続は切断しない。

        Args:
            fast (bool): TrueはOpenMaya直接更新（Undoなし）。既定False。
            value (float): 0～1の有限値。
        Returns:
            BlendColors: 自身。
        Raises:
            ValueError: 非有限値または範囲外の場合。
            RuntimeError: ロックや接続により設定できない場合。

        ``fast=True`` はOpenMaya直接更新（Undoなし）。既定の ``False`` は通常処理。
        fastがbool以外ならTypeError。完了済みの直接更新は自動で戻さない。
        """
        value = float(value)
        if not math.isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Blender must be a finite value between 0 and 1")
        self.blenderPlug().set(value)
        return self

    @undoChunk("hlibBlendColorsConnectBlender")
    def connectBlender(self, source, force=False):
        """補間係数に接続する。接続元の値は制限しない。

        Args:
            source (Plug): 接続元の数値Plug。
            force (bool): 既存接続を置換するか。
        Returns:
            BlendColors: 自身。
        """
        source.connect(self.blenderPlug(), force=force)
        return self

    def outputPlug(self):
        """CompoundPlug: RGB出力。別アトリビュートへの接続に使用する。"""
        return self.plug("output")

    def result(self):
        """tuple[float, float, float]: 評価済みRGB値。"""
        return tuple(self.outputPlug().get())

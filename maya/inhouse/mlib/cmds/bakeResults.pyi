# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ノードのアトリビュートの評価結果をフレームごとのキーへ焼き込み、そのアニメーションカーブを返す(``cmds.bakeResults`` 相当)。

コンストレイント・エクスプレッション・ドリブンキー等で動いているアトリビュートを、指定した範囲のフレームごとに
評価してキーにする。焼き込みの間に動かした現在時刻は、終わったら元へ戻す。

.. code-block:: python

    import mlib

    curves = mlib.bakeResults(["arm_CTRL", "leg_CTRL"], time=(1, 120), simulation=True)
"""

import math
import numbers
import re
import maya.api.OpenMaya as om2
import maya.cmds as cmds
from ..core.object import Object
from ..decorator import undoChunk
from typing import Sequence
from mlib.nodes.animCurve import AnimCurve
from mlib.nodes.node import Node

_ARGUMENT_FLAGS: frozenset
_REJECTED_FLAGS: frozenset

def bakeResults(nodes: Node | str | Sequence[Node | str], attributes: str | Sequence[str] | None = ..., time: tuple[float, float] | None = ..., sampleBy: float = ..., **kwargs: object) -> list[AnimCurve]:
    """ノードのアトリビュートの評価結果をキーへ焼き込み、焼き込んだアニメーションカーブを返す。

    選択状態は参照しない。time を省略すると再生範囲(``mlib.common.Time.getPlaybackRange()``)を焼き込む。
    attributes を省略するとMayaの既定(各ノードのキー設定可能なアトリビュート)を対象にする。
    Mayaの既定(``simulation=False``)では入力を持たない静的なアトリビュートにはキーを作らない。すべての
    フレームを順に評価する必要がある場合(ダイナミクス等)は ``simulation=True`` を渡す。
    焼き込みで現在時刻が動いた場合は終了後に元の時刻へ戻す。fast引数は持たない(OpenMayaに同等機能が無い)。
    Undo有効時は1回で戻せる。

    Args:
        nodes (Node | str | Sequence[Node | str]): 焼き込むノード、またはその列。
        attributes (str | Sequence[str] | None): 焼き込むアトリビュート名(``"translateX"``・``"tx"``・
            コンパウンドアトリビュートの ``"translate"`` も可)。None はMayaの既定(キー設定可能なもの)。
        time (tuple[float, float] | None): 焼き込む範囲 (開始, 終了)。現在のUI時間単位のフレームで、両端を含む。
            None は再生範囲。
        sampleBy (float): キーを作る間隔(フレーム)。正の数。既定1。
        **kwargs (object): ``cmds.bakeResults`` のその他のフラグ(``simulation``・``preserveOutsideKeys``・
            ``sparseAnimCurveBake``・``disableImplicitControl``・``minimizeRotation``・``shape``・
            ``hierarchy`` 等。長名・短名とも可)。

    Returns:
        list[AnimCurve]: nodes(``shape`` が有効なら直下のShapeも)の対象アトリビュートを動かすアニメーション
            カーブ(新しく作られたもの・書き換えたもの)。``hierarchy`` で増えた子孫のカーブは含まない。
            焼き込むものが無ければ空リスト。

    Raises:
        TypeError: 引数で受けるフラグ・query・editフラグを ``**kwargs`` に渡した場合、attributesが文字列・
            文字列の列・None以外の場合、またはtime・sampleByが数値でない場合。
        ValueError: nodesが空、timeが2個の有限な数値でない・開始が終了より後、またはsampleByが正の有限な
            数でない場合。
        RuntimeError: 名前を解決できない、またはMayaが焼き込みを拒否した場合。
    """
    ...

def _attribute_names(attributes: str | Sequence[str] | None) -> list[str] | None:
    """attributes の指定を、cmds.bakeResults へ渡すアトリビュート名のリストへ正規化する。

    Args:
        attributes (str | Sequence[str] | None): アトリビュート名、その列、またはNone。

    Returns:
        list[str] | None: アトリビュート名。NoneはMayaの既定。

    Raises:
        TypeError: 文字列・文字列の列・None以外の場合。
        ValueError: 空の列、または空文字列を含む場合。
    """
    ...

def _time_range(time: Sequence[float]) -> tuple[float, float]:
    """time の指定 (開始, 終了) を検証する。

    Args:
        time (Sequence[float]): 開始と終了のフレーム。

    Returns:
        tuple[float, float]: (開始, 終了)。

    Raises:
        TypeError: 数値の列でない場合。
        ValueError: 2個でない、有限でない、または開始が終了より後の場合。
    """
    ...

def _driving_curves(owner: str, names: list[str] | None) -> list[str]:
    """ノードの対象アトリビュートへ直接(単位変換ノードを飛ばして)つながるアニメーションカーブを返す。

    Args:
        owner (str): ノードのフルパス。
        names (list[str] | None): 焼き込んだアトリビュート名。Noneはキー設定可能なアトリビュート。

    Returns:
        list[str]: アニメーションカーブの名前。接続の順で重複なし。
    """
    ...

def _attribute_base(name: str) -> str:
    """アトリビュートのパスから論理番号を除き、末尾のアトリビュート名を返す(``"weight[0]"`` は ``"weight"``)。

    Args:
        name (str): アトリビュート名またはパス。

    Returns:
        str: 論理番号を除いた末尾のアトリビュート名。
    """
    ...

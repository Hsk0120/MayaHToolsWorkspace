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

#: 引数で受けるため、``**kwargs`` では受け付けないフラグ(長名・短名)。
_ARGUMENT_FLAGS = frozenset(("attribute", "at", "time", "t", "sampleBy", "sb"))

#: 照会・編集のフラグ(bakeResults は焼き込み専用)。
_REJECTED_FLAGS = frozenset(("query", "q", "edit", "e"))


def bakeResults(nodes, attributes=None, time=None, sampleBy=1, **kwargs):
    """ノードのアトリビュートの評価結果をキーへ焼き込み、焼き込んだアニメーションカーブを返す。

    選択状態は参照しない。time を省略すると再生範囲(``mlib.Time.getPlaybackRange()``)を焼き込む。
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
    # nodes・common はcmdsを参照するため、循環importを避けて関数内で読み込む。
    from ..common.sceneTime import Time
    from ..nodes.animCurve import AnimCurve
    from ..nodes.node import Node

    duplicated = sorted(_ARGUMENT_FLAGS.intersection(kwargs))
    if duplicated:
        raise TypeError(f"Pass these as arguments of bakeResults: {', '.join(duplicated)}")
    rejected = sorted(_REJECTED_FLAGS.intersection(kwargs))
    if rejected:
        raise TypeError(f"bakeResults does not accept: {', '.join(rejected)}")
    items = [nodes] if isinstance(nodes, (str, Object)) or not hasattr(nodes, "__iter__") else list(nodes)
    if not items:
        raise ValueError("bakeResults requires at least one node")
    targets = [Node(Object._input_name(item)) for item in items]
    names = _attribute_names(attributes)
    start, end = Time.getPlaybackRange() if time is None else _time_range(time)
    if isinstance(sampleBy, bool) or not isinstance(sampleBy, numbers.Real):
        raise TypeError("sampleBy must be a number")
    if not math.isfinite(sampleBy) or sampleBy <= 0:
        raise ValueError(f"sampleBy must be a positive finite number, got {sampleBy}")
    flags = dict(kwargs, time=(start, end), sampleBy=sampleBy)
    if names is not None:
        flags["attribute"] = names
    full_names = [node.getFullName() for node in targets]
    current = cmds.currentTime(query=True)
    try:
        with undoChunk("mlibBakeResults"):
            cmds.bakeResults(full_names, **flags)
    finally:
        if cmds.currentTime(query=True) != current:
            cmds.currentTime(current, update=True)
    # 結果の照会はUndoのまとまりの外で行う。
    with_shapes = kwargs.get("shape", kwargs.get("s", True))
    result = []
    for node in targets:
        owners = [node.getFullName()]
        if with_shapes and node.hasFn(om2.MFn.kTransform):
            owners += cmds.listRelatives(owners[0], shapes=True, noIntermediate=True, fullPath=True) or []
        for owner in owners:
            for curve in _driving_curves(owner, names):
                if curve not in result:
                    result.append(curve)
    return [AnimCurve(curve) for curve in result]


def _attribute_names(attributes):
    """attributes の指定を、cmds.bakeResults へ渡すアトリビュート名のリストへ正規化する。

    Args:
        attributes (str | Sequence[str] | None): アトリビュート名、その列、またはNone。

    Returns:
        list[str] | None: アトリビュート名。NoneはMayaの既定。

    Raises:
        TypeError: 文字列・文字列の列・None以外の場合。
        ValueError: 空の列、または空文字列を含む場合。
    """
    if attributes is None:
        return None
    names = [attributes] if isinstance(attributes, str) else list(attributes) if isinstance(
        attributes, (list, tuple)) else None
    if names is None or not all(isinstance(name, str) for name in names):
        raise TypeError("attributes must be an attribute name, a sequence of names, or None")
    if not names or not all(names):
        raise ValueError("attributes must not be empty or contain an empty name")
    return names


def _time_range(time):
    """time の指定 (開始, 終了) を検証する。

    Args:
        time (Sequence[float]): 開始と終了のフレーム。

    Returns:
        tuple[float, float]: (開始, 終了)。

    Raises:
        TypeError: 数値の列でない場合。
        ValueError: 2個でない、有限でない、または開始が終了より後の場合。
    """
    if isinstance(time, (str, bytes)) or not isinstance(time, (list, tuple)):
        raise TypeError("time must be a (start, end) pair of frames or None")
    if len(time) != 2:
        raise ValueError(f"time must have 2 values (start, end), got {len(time)}")
    if not all(isinstance(value, numbers.Real) and not isinstance(value, bool) for value in time):
        raise TypeError("time must contain numbers")
    start, end = float(time[0]), float(time[1])
    if not (math.isfinite(start) and math.isfinite(end)):
        raise ValueError("time must be finite")
    if start > end:
        raise ValueError(f"time start must not be after end: {start} > {end}")
    return start, end


def _driving_curves(owner, names):
    """ノードの対象アトリビュートへ直接(単位変換ノードを飛ばして)つながるアニメーションカーブを返す。

    Args:
        owner (str): ノードのフルパス。
        names (list[str] | None): 焼き込んだアトリビュート名。Noneはキー設定可能なアトリビュート。

    Returns:
        list[str]: アニメーションカーブの名前。接続の順で重複なし。
    """
    if names is None:
        wanted = {_attribute_base(name) for name in cmds.listAttr(owner, keyable=True) or []}
    else:
        wanted = set()
        for name in names:
            if not cmds.attributeQuery(_attribute_base(name), node=owner, exists=True):
                continue
            wanted.add(cmds.attributeQuery(_attribute_base(name), node=owner, longName=True))
            wanted.update(cmds.attributeQuery(_attribute_base(name), node=owner, listChildren=True) or [])
    pairs = cmds.listConnections(owner, source=True, destination=False, type="animCurve", connections=True,
                                 skipConversionNodes=True) or []
    curves = []
    for destination, curve in zip(pairs[::2], pairs[1::2]):
        if _attribute_base(destination.split(".", 1)[1]) in wanted and curve not in curves:
            curves.append(curve)
    return curves


def _attribute_base(name):
    """アトリビュートのパスから論理番号を除き、末尾のアトリビュート名を返す(``"weight[0]"`` は ``"weight"``)。

    Args:
        name (str): アトリビュート名またはパス。

    Returns:
        str: 論理番号を除いた末尾のアトリビュート名。
    """
    return re.sub(r"\[\d+\]", "", name).rsplit(".", 1)[-1]

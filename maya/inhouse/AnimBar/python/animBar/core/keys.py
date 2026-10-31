"""アニメーションの編集で共通に使う、対象の選び方とキーの照会。

対象の選び方は次の順に決める。

1. Graph Editor でキーを選んでいれば、そのカーブと選んだキー。
2. Channel Box でアトリビュートを選んでいれば、選んだノードのそのアトリビュート。
3. それ以外は、選んだノードのキー可能なアトリビュート。

カーブは :class:`mlib.nodes.AnimCurve`、アトリビュートは :class:`mlib.plugs.Plug` で扱う。
"""

import math
from collections import namedtuple

import maya.cmds as cmds

from mlib.common import Selection, Time

#: キーの比較で同じ時刻とみなす差(フレーム)。
TIME_EPSILON = 1e-4

#: 対象のカーブと、そのカーブで扱うキーの番号。plug は駆動先のアトリビュート(無ければNone)。
Target = namedtuple("Target", ("curve", "indices", "plug"))


def selectedNodes():
    """選択しているノードを、選択順に返す。

    Returns:
        list[Node]: 選択しているノード。コンポーネントは所有ノードにする。
    """
    nodes = []
    for node in Selection.capture().getOwners():
        if node not in nodes:
            nodes.append(node)
    return nodes


def keyablePlugs(node, channelBox=True):
    """ノードのキー可能なアトリビュートを返す。

    Channel Box で選んだアトリビュートがあり、channelBox=True なら、その中でこのノードのものだけを返す。

    Args:
        node (Node): 対象ノード。
        channelBox (bool): TrueはChannel Boxの選択を優先する。

    Returns:
        list[Plug]: 書き込めるキー可能なアトリビュート(ロック・接続されたものを除く。animCurveの接続は含む)。
    """
    if channelBox:
        chosen = [plug for plug in _channel_box_plugs() if plug.getNode() == node]
        if chosen:
            return chosen
    return node.getPlugs(keyable=True, scalar=True, writable=True)


def animatedPlugs(node, channelBox=True):
    """ノードの、animCurveが直接つながったキー可能なアトリビュートを返す。

    Args:
        node (Node): 対象ノード。
        channelBox (bool): TrueはChannel Boxの選択を優先する。

    Returns:
        list[Plug]: アニメーションのあるアトリビュート。
    """
    return [plug for plug in keyablePlugs(node, channelBox) if plug.getAnimCurve() is not None]


def graphEditorKeys():
    """Graph Editor・Dope Sheet で選んでいるキーを、カーブごとの番号で返す。

    Returns:
        dict[AnimCurve, list[int]]: 選んだキーの番号(昇順)。何も選んでいなければ空。
    """
    if not _key_editor_visible():
        return {}
    selected = Selection.getKeyframes()
    return {curve: selected.getIndices(curve) for curve in selected.getCurves()}


def _key_editor_visible():
    """キーを選ぶ画面(Graph Editor・Dope Sheet)が開いているかを返す。

    閉じた画面で前に選んだキーが残っていても、それを対象にしないために使う。GUI の無いバッチでは
    選んだキーをそのまま使う(テストやスクリプトから選んで呼ぶため)。

    Returns:
        bool: 開いていれば(またはバッチなら)True。
    """
    if cmds.about(batch=True):
        return True
    for panel in cmds.getPanel(visiblePanels=True) or []:
        if cmds.getPanel(typeOf=panel) == "scriptedPanel" and                 cmds.scriptedPanel(panel, query=True, type=True) in ("graphEditor", "dopeSheetPanel"):
            return True
    return False


def keyIndexAt(curve, time):
    """指定した時刻のキーの番号を返す。

    Args:
        curve (AnimCurve): カーブ。
        time (float): 時刻(フレーム)。

    Returns:
        int | None: キーの番号。その時刻にキーが無ければNone。
    """
    for index, value in enumerate(curve.getKeyInputs()):
        if abs(value - time) < TIME_EPSILON:
            return index
    return None


def neighborKeys(curve, time):
    """指定した時刻の前と後ろのキーの番号を返す(その時刻のキーは含めない)。

    Args:
        curve (AnimCurve): カーブ。
        time (float): 時刻(フレーム)。

    Returns:
        tuple[int | None, int | None]: (前のキー, 後ろのキー)。無ければNone。
    """
    previous = following = None
    for index, value in enumerate(curve.getKeyInputs()):
        if value < time - TIME_EPSILON:
            previous = index
        elif value > time + TIME_EPSILON and following is None:
            following = index
    return previous, following


def targets(create=False):
    """編集対象のカーブとキーを返す。

    Graph Editor でキーを選んでいればそれを使う。選んでいなければ、選んだノードの
    アトリビュートのうち現在時刻にキーがあるものを使う。create=True なら、現在時刻に
    キーが無いアトリビュートにもキーを打ってから対象にする(アニメーションの無いものにも打つ)。
    create="animated" なら、アニメーションのあるアトリビュートだけに、カーブの形を変えずに
    (その時刻のカーブの値で)キーを足す。

    Args:
        create (bool | str): Trueは現在時刻にキーを作ってから返す。``"animated"`` はアニメーションの
            あるアトリビュートだけに作る。

    Returns:
        list[Target]: 対象。何も無ければ空。
    """
    selected = graphEditorKeys()
    if selected:
        return [Target(curve, indices, drivenPlug(curve)) for curve, indices in selected.items()]
    now = Time.getCurrent()
    result = []
    for node in selectedNodes():
        plugs = keyablePlugs(node) if create is True else animatedPlugs(node)
        for plug in plugs:
            curve = plug.getAnimCurve()
            if curve is None or keyIndexAt(curve, now) is None:
                if not create:
                    continue
                plug.setKey(time=now, insert=curve is not None)
                curve = plug.getAnimCurve()
            index = keyIndexAt(curve, now)
            if index is not None:
                result.append(Target(curve, [index], plug))
    return result


def keyTimesOf(nodes, selectedOnly=False):
    """ノードのアニメーションにあるキーの時刻を、重複を除いて昇順で返す。

    Args:
        nodes (Iterable[Node]): 対象ノード。
        selectedOnly (bool): TrueはGraph Editorで選んだキーだけ。

    Returns:
        list[float]: キーの時刻(フレーム)。
    """
    times = set()
    if selectedOnly:
        for curve, indices in graphEditorKeys().items():
            inputs = curve.getKeyInputs()
            times.update(inputs[index] for index in indices)
    else:
        for node in nodes:
            for plug in animatedPlugs(node, channelBox=False):
                times.update(plug.getAnimCurve().getKeyInputs())
    return sorted(_unique(times))


def setKeyValue(curve, index, value):
    """番号で指定したキーの値を、時刻と接線型を保って変える。

    Args:
        curve (AnimCurve): カーブ。
        index (int): キーの番号。
        value (float): 新しい値(角度は度)。

    Returns:
        None: 値を返さない。
    """
    if not math.isfinite(value):
        raise ValueError("Key value must be finite")
    curve.getKeyframe(index).setValue(value)


def curveSnapshot(curve, timeRange=None):
    """カーブのキーを、接線(型・角度・ウェイト・ロック)とインフィニティごと書き出す。

    Args:
        curve (AnimCurve): カーブ。
        timeRange (tuple[float, float] | None): 書き出す範囲(両端を含む)。Noneは全キー。

    Returns:
        dict: ``{"weighted": bool, "infinity": {"pre": ..., "post": ...}, "keys": [...]}``。
            ``keys`` の各要素は ``[時刻, 値, 接線の辞書]``(接線の辞書は AnimCurve.getTangent の内容から
            weightedTangents を除いたもの)。JSON へそのまま書ける。
    """
    entries = []
    weighted = False
    for index, (time, value) in enumerate(zip(curve.getKeyInputs(), curve.getKeyValues())):
        if timeRange is not None and not timeRange[0] - TIME_EPSILON <= time <= timeRange[1] + TIME_EPSILON:
            continue
        tangent = dict(curve.getTangent(index))
        weighted = tangent.pop("weightedTangents")
        entries.append([time, value, tangent])
    return {"weighted": bool(weighted), "infinity": curve.getInfinity(), "keys": entries}


def applySnapshot(curve, snapshot, offset=0.0, transform=None, replace="range"):
    """:func:`curveSnapshot` の内容をカーブへ書き戻す。

    Args:
        curve (AnimCurve): 書き込むカーブ。
        snapshot (dict): :func:`curveSnapshot` の戻り値。
        offset (float): 時刻へ足す量(フレーム)。
        transform (callable | None): 値を変える関数 ``f(value) -> value``(左右の反転など)。
            値を反転した場合は接線の角度も反転する。
        replace (str): ``"range"`` は書き込む範囲の既存のキーだけを消す(範囲の外のキーは残す)。
            ``"all"`` は全キーを置き換える。

    Returns:
        int: 書き込んだキーの数。
    """
    entries = snapshot["keys"]
    if not entries:
        return 0
    times = [entry[0] + offset for entry in entries]
    flipped = transform is not None and transform(1.0) < 0
    values = [entry[1] if transform is None else transform(entry[1]) for entry in entries]
    types = [_key_tangents(entry[2]) for entry in entries]
    if replace == "all":
        curve.replaceKeys([(time, value) + pair for time, value, pair in zip(times, values, types)])
    elif replace == "range":
        if curve.getKeyCount():
            curve.removeKey(time=(min(times), max(times)))
        for time, value, pair in zip(times, values, types):
            curve.setKey(time, value, *pair)
    else:
        raise ValueError("replace must be 'range' or 'all'")
    if snapshot.get("weighted") and curve.getKeyCount():
        curve.setTangent(0, weightedTangents=True)
    inputs = curve.getKeyInputs()
    for time, entry in zip(times, entries):
        index = _closest_index(inputs, time)
        tangent = entry[2]
        # ロックを外してから角度・ウェイトを書き、最後に元のロックへ戻す(ロック中は片側の変更が反対側へ移るため)。
        curve.setTangent(index, lock=False)
        # 角度・ウェイトを書くと接線型は fixed になるため、fixed の側だけ書く。
        handles = {}
        for side in ("in", "out"):
            if tangent.get(side + "TangentType") != "fixed" or side + "Angle" not in tangent:
                continue
            angle = tangent[side + "Angle"]
            handles[side + "Angle"] = -angle if flipped else angle
            if snapshot.get("weighted") and side + "Weight" in tangent:
                handles[side + "Weight"] = tangent[side + "Weight"]
        if handles:
            curve.setTangent(index, **handles)
        curve.setTangent(index, lock=bool(tangent.get("lock", True)))
        if snapshot.get("weighted"):
            curve.setTangent(index, weightLock=bool(tangent.get("weightLock", False)))
    infinity = snapshot.get("infinity")
    if infinity:
        curve.setInfinity(pre=infinity["pre"], post=infinity["post"])
    return len(entries)


def _key_tangents(tangent):
    """キーを打つときに渡せる接線型を返す。

    setKeyframe は fixed と、入力側の step・stepnext を受け付けないため、それらは省く(Mayaの既定で打つ)。
    fixed は後から角度を書いて戻す。

    Args:
        tangent (dict): 接線の辞書。

    Returns:
        tuple[str | None, str | None]: (入力接線型, 出力接線型)。
    """
    tangent_in = tangent.get("inTangentType") or None
    tangent_out = tangent.get("outTangentType") or None
    if tangent_in in ("fixed", "step", "stepnext"):
        tangent_in = None
    if tangent_out == "fixed":
        tangent_out = None
    return tangent_in, tangent_out


def _closest_index(inputs, time):
    """時刻に最も近いキーの番号を返す。"""
    return min(range(len(inputs)), key=lambda index: abs(inputs[index] - time))


def keyValue(curve, index):
    """番号で指定したキーの値を返す。

    Args:
        curve (AnimCurve): カーブ。
        index (int): キーの番号。

    Returns:
        float: 値(角度は度)。
    """
    return curve.getKeyValues()[index]


def defaultValue(plug):
    """アトリビュートの既定値を、Plug.getと同じ単位(角度は度・距離はcm)の数値で返す。

    Args:
        plug (Plug | None): アトリビュート。Noneは0。

    Returns:
        float: 既定値。
    """
    if plug is None:
        return 0.0
    value = plug.getDefault()
    if isinstance(value, (int, float)):
        return float(value)
    return 0.0


def drivenPlug(curve):
    """カーブが駆動するアトリビュートを返す。

    Args:
        curve (AnimCurve): カーブ。

    Returns:
        Plug | None: 出力の接続先。無ければNone。
    """
    destinations = curve.getDrivenPlugs()
    return destinations[0] if destinations else None


def _channel_box_plugs():
    """Channel Box で選んでいるアトリビュートを返す(GUIが無ければ空)。

    Returns:
        list[Plug]: 選んでいるアトリビュート。
    """
    try:
        return list(Selection.getChannelBoxPlugs())
    except RuntimeError:
        return []


def _unique(values):
    """浮動小数の誤差で重なった時刻をまとめる。

    Args:
        values (Iterable[float]): 時刻。

    Returns:
        list[float]: まとめた時刻。
    """
    result = []
    for value in sorted(values):
        if not result or value - result[-1] > TIME_EPSILON:
            result.append(value)
    return result

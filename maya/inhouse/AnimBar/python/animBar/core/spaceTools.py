"""ワールドの位置・向きを扱うツール(位置合わせ・スペース切替・仮のピボット・仮のコンストレイント)。

どれもワールドのマトリクスを求めてから書き戻すので、親子やコンストレイントの作りに依存しない。
範囲を指定した操作は、範囲の各フレーム(または対象のキーのある時刻)でキーを打つ。
"""

import maya.cmds as cmds

import mlib
from mlib.common import Time
from mlib.decorator import undoChunk

from . import keys

#: 仮のピボットのロケーターに付ける目印のアトリビュート名。
PIVOT_ATTRIBUTE = "animBarTempPivot"

#: 仮のコンストレイントのロケーターに付ける目印のアトリビュート名。
FOLLOW_ATTRIBUTE = "animBarFakeConstraint"


def _frames(rangeMode, nodes):
    """操作する時刻の並びを返す。

    Args:
        rangeMode (str): ``"current"`` は現在時刻、``"keys"`` は対象のキーのある時刻、``"range"`` は再生範囲の各フレーム。
        nodes (Iterable[Node]): キーの時刻を調べる対象。

    Returns:
        list[float]: 時刻。
    """
    if rangeMode == "current":
        return [Time.getCurrent()]
    if rangeMode == "keys":
        return keys.keyTimesOf(nodes) or [Time.getCurrent()]
    if rangeMode == "range":
        start, end = Time.getPlaybackRange()
        return [float(frame) for frame in range(int(start), int(end) + 1)]
    raise ValueError("rangeMode must be current, keys or range")


def _key_transform(node, time, translate=True, rotate=True):
    """移動・回転のチャンネルのうち、書けるものにキーを打つ。

    Args:
        node (Transform): 対象。
        time (float): 時刻。
        translate (bool): 移動にキーを打つか。
        rotate (bool): 回転にキーを打つか。

    Returns:
        None: 値を返さない。
    """
    names = ([axis for axis in ("tx", "ty", "tz")] if translate else []) + \
            ([axis for axis in ("rx", "ry", "rz")] if rotate else [])
    writable = [name for name in names if not node.getPlug(name).isLocked() and
                (node.getPlug(name).getSource() is None or keys.animCurveOf(node.getPlug(name)) is not None)]
    if writable:
        node.setKey(writable, time=time)


def _filter_rotation(nodes):
    """回転のカーブへオイラーフィルタを掛け、フレームごとに求めた回転の180度の反転をなくす。

    Args:
        nodes (Iterable[Transform]): 対象。

    Returns:
        None: 値を返さない。
    """
    curves = []
    for node in nodes:
        for name in ("rx", "ry", "rz"):
            curve = keys.animCurveOf(node.getPlug(name))
            if curve is not None and curve.getKeyCount() > 1:
                curves.append(curve.getFullName())
    if curves:
        # mlib にはオイラーフィルタの入口が無いため、Mayaのコマンドを使う(Undoに記録される)。
        cmds.filterCurve(curves, filter="euler")


@undoChunk("animBarAlign")
def align(slaves=None, master=None, translate=True, rotate=True, rangeMode="current"):
    """選んだノード(最後以外)を、最後に選んだノードの位置・向きへ合わせる。

    Args:
        slaves (Iterable[Transform] | None): 合わせるノード。Noneは選択の最後以外。
        master (Transform | None): 合わせ先。Noneは選択の最後。
        translate (bool): 位置を合わせる。
        rotate (bool): 向きを合わせる。
        rangeMode (str): ``"current"``・``"keys"``(合わせ先のキーの時刻)・``"range"``(再生範囲)。

    Returns:
        int: 合わせた回数(ノード × 時刻)。

    Raises:
        ValueError: 合わせ先と合わせるノードが揃わない場合。
    """
    if slaves is None or master is None:
        selected = keys.selectedNodes()
        if len(selected) < 2:
            raise ValueError("Select the objects to align, then the target last")
        slaves, master = selected[:-1], selected[-1]
    slaves = list(slaves)
    count = 0
    with Time.preserved():
        for time in _frames(rangeMode, [master]):
            Time.setCurrent(time)
            for slave in slaves:
                slave.matchTransform(master, position=translate, rotation=rotate, scale=False)
                if rangeMode != "current" or any(keys.animCurveOf(slave.getPlug(n)) is not None
                                                 for n in ("tx", "ty", "tz", "rx", "ry", "rz")):
                    _key_transform(slave, time, translate, rotate)
                count += 1
    if rangeMode != "current" and rotate:
        _filter_rotation(slaves)
    return count


@undoChunk("animBarSpaceSwitch")
def switchSpace(node, attribute, value, rangeMode="current"):
    """スペース切替のアトリビュートを変えても、ワールドの位置・向きが変わらないようにする。

    各時刻でワールドのマトリクスを覚え、アトリビュートを変えてから同じワールドのマトリクスへ戻して
    キーを打つ。

    Args:
        node (Transform): コントロール。
        attribute (str): スペース切替のアトリビュート(enum・数値)。
        value (int | float): 新しい値。
        rangeMode (str): ``"current"``・``"keys"``(コントロールのキーの時刻)・``"range"``(再生範囲)。

    Returns:
        int: 切り替えた時刻の数。
    """
    plug = node.getPlug(attribute)
    frames = _frames(rangeMode, [node])
    with Time.preserved():
        matrices = []
        for time in frames:
            Time.setCurrent(time)
            matrices.append(node.getMatrix(worldSpace=True))
        for time, matrix in zip(frames, matrices):
            Time.setCurrent(time)
            plug.set(value)
            if keys.animCurveOf(plug) is not None or rangeMode != "current":
                plug.setKey(time=time)
            node.setMatrix(matrix, worldSpace=True, safe=True)
            _key_transform(node, time)
    if rangeMode != "current":
        _filter_rotation([node])
    return len(frames)


@undoChunk("animBarCreateTempPivot")
def createTempPivot(nodes=None, position=None):
    """選んだノードを、仮のピボット(ロケーター)の周りで動かせるようにする。

    ロケーターを置き、各ノードをロケーターへペアレントコンストレイントでつなぐ(オフセットを保つ)。
    ロケーターを回して位置を決め、:func:`clearTempPivots` で外すと、そのフレームにキーを打って元に戻る。

    Args:
        nodes (Iterable[Transform] | None): 対象。Noneは選択。
        position (Sequence[float] | None): ピボットのワールド位置(cm)。Noneは最後のノードの位置。

    Returns:
        Transform: 仮のピボットのロケーター。
    """
    nodes = keys.selectedNodes() if nodes is None else list(nodes)
    if not nodes:
        raise ValueError("Select the objects to rotate around a temporary pivot")
    locator = mlib.createLocator(name="animBarTempPivot").getParent()
    locator.addAttr(longName=PIVOT_ATTRIBUTE, attributeType="message")
    locator.setTranslation(position if position is not None else nodes[-1].getTranslation(worldSpace=True),
                           worldSpace=True)
    locator.setRotate(nodes[-1].getRotate(worldSpace=True), worldSpace=True)
    for node in nodes:
        constraint = node.addConstraint(locator, type="parent", maintainOffset=True)
        constraint.addAttr(longName=PIVOT_ATTRIBUTE, attributeType="message")
        locator.getPlug("message").connectTo(constraint.getPlug(PIVOT_ATTRIBUTE))
    mlib.select(locator)
    return locator


@undoChunk("animBarClearTempPivots")
def clearTempPivots():
    """仮のピボットを全部外す。外す前に、つないだノードの今の位置・向きにキーを打つ。

    Returns:
        int: 外したピボットの数。
    """
    # コンストレイントも transform で同じ目印を持つため、ロケーター(ピボット)だけを選ぶ。
    pivots = [node for node in mlib.ls(type="transform") if node.hasAttr(PIVOT_ATTRIBUTE) and
              not node.isType("constraint")]
    now = Time.getCurrent()
    for pivot in pivots:
        constraints = []
        for destination in pivot.getPlug("message").getDestinations():
            if destination.getNode() not in constraints:
                constraints.append(destination.getNode())
        for target in constraints:
            if not target.isValid():
                continue
            driven = [destination.getNode() for destination in target.getPlug("constraintTranslateX").getDestinations()]
            matrices = [(node, node.getMatrix(worldSpace=True)) for node in driven]
            mlib.delete(target)
            for node, matrix in matrices:
                node.setMatrix(matrix, worldSpace=True, safe=True)
                _key_transform(node, now)
        mlib.delete(pivot)
    return len(pivots)


@undoChunk("animBarFakeConstraint")
def fakeConstraint(slaves=None, master=None, rangeMode="range"):
    """選んだノードを、最後に選んだノードについて動くようにキーを打つ(コンストレイントを使わない)。

    呼んだときの現在時刻のマスターとの相対の位置・向きを保ち、範囲の各時刻でマスターの動きに合わせてキーを打つ。
    終わりに回転のカーブへオイラーフィルタを掛ける。

    Args:
        slaves (Iterable[Transform] | None): ついて動くノード。Noneは選択の最後以外。
        master (Transform | None): マスター。Noneは選択の最後。
        rangeMode (str): ``"range"``(再生範囲)・``"keys"``(マスターのキーの時刻)。

    Returns:
        int: キーを打った回数(ノード × 時刻)。
    """
    if slaves is None or master is None:
        selected = keys.selectedNodes()
        if len(selected) < 2:
            raise ValueError("Select the objects to follow, then the master last")
        slaves, master = selected[:-1], selected[-1]
    slaves = list(slaves)
    frames = _frames(rangeMode, [master])
    with Time.preserved():
        offsets = [(slave, slave.getMatrix(worldSpace=True) * master.getMatrix(worldSpace=True).inverse())
                   for slave in slaves]
        targets = []
        for time in frames:
            Time.setCurrent(time)
            world = master.getMatrix(worldSpace=True)
            targets.append((time, [(slave, offset * world) for slave, offset in offsets]))
        count = 0
        for time, items in targets:
            Time.setCurrent(time)
            for slave, matrix in items:
                slave.setMatrix(matrix, worldSpace=True, safe=True)
                _key_transform(slave, time)
                count += 1
    _filter_rotation(slaves)
    return count

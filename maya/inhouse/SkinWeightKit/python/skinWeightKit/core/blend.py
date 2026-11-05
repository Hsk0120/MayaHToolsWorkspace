"""減衰をつけたウェイトの変更(スライド・ソフト選択からの設定・2本の間のランプ)。

- スライド: ソフト選択の重み(無効なら選んだ頂点は1)に比例して、アクティブなインフルエンスを増減する。
  ドラッグ中は Undo なしで書き、離したときに元へ戻してから最後の値を1回の Undo で書く。
- ソフト選択からの設定: ソフト選択の重みを、そのままアクティブなインフルエンスの値にする。
- ランプ: 2つのインフルエンスの位置を結ぶ線へ頂点を投影し、その割合で2つの間を配分する。
"""

from mlib.common import Selection
from mlib.decorator import undoChunk

from . import influences as influences_module
from . import target as target_module
from . import weights as weights_module

#: ランプの補間の名前。
EASINGS = ("linear", "smooth")


def softTarget():
    """ソフト選択から、対象と頂点ごとの重みを返す。

    Returns:
        tuple[Target, dict[int, float]]: 対象と {頂点番号: 重み}(0より大きいものだけ)。

    Raises:
        ValueError: バインドしたメッシュの頂点を選んでいない場合。
    """
    found = Selection.getSoftSelection()
    if not found:
        raise ValueError("Select vertices of a skinned mesh (soft selection is used when it is on)")
    # 複数のメッシュにまたがる場合は、最初のメッシュだけを使う。
    mesh, weights = next(iter(found.items()))

    weights = {index: weight for index, weight in weights.items() if weight > weights_module.TOLERANCE}
    skins = mesh.getSkinClusters()
    current = target_module.Target(mesh, skins[0] if skins else None, sorted(weights))
    current.requireSkin()
    return current, weights


class SlideSession(object):
    """スライダーのドラッグの間、開始時の値を保ち、量を変えるたびに計算し直す。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): 増減するインフルエンス。
        falloff (dict[int, float] | None): {頂点番号: 重み}。Noneは選んだ頂点をすべて1にする。

    Raises:
        ValueError: インフルエンスがロックされている場合。
    """

    def __init__(self, target, influence, falloff=None):
        self.skin = target.requireSkin()
        self.influences = self.skin.getInfluences()
        node = influences_module.find(self.skin, influence)
        if influences_module.isLocked(node):
            raise ValueError("{} is locked".format(node.getNodeName()))
        if falloff is None:
            falloff = {index: 1.0 for index in target.requireVertices()}
        self.vertices = sorted(falloff)
        self.falloff = [falloff[index] for index in self.vertices]
        self.locked = [influences_module.isLocked(other) for other in self.influences]
        self.column = self.influences.index(node)
        self.original = weights_module.readRows(self.skin, self.influences, self.vertices)
        self.amount = 0.0

    def rows(self, amount):
        """量に対する行を返す(シーンは変えない)。

        Args:
            amount (float): 加える量(-1〜1。頂点ごとに重みを掛ける)。

        Returns:
            list[list[float]]: 頂点の順の行。
        """
        return [weights_module.fitColumn(row, self.column, row[self.column] + amount * weight, self.locked)
                for row, weight in zip(self.original, self.falloff)]

    def apply(self, amount):
        """量を反映する(Undo なし。ドラッグ中の表示用)。

        Args:
            amount (float): 加える量。

        Returns:
            None: 値を返さない。
        """
        self.amount = float(amount)
        weights_module.writeRows(self.skin, self.influences, self.vertices, self.rows(self.amount), fast=True)

    def finish(self):
        """元の値へ戻してから、最後の量を1回の Undo で書く。

        Returns:
            int: 変えた頂点の数(量が0なら0)。
        """
        weights_module.writeRows(self.skin, self.influences, self.vertices, self.original, fast=True)
        if abs(self.amount) <= weights_module.TOLERANCE:
            return 0
        with undoChunk("skinWeightKitSlide"):
            weights_module.writeRows(self.skin, self.influences, self.vertices, self.rows(self.amount))
        return len(self.vertices)

    def cancel(self):
        """元の値へ戻す(Undo に残さない)。

        Returns:
            None: 値を返さない。
        """
        self.amount = 0.0
        weights_module.writeRows(self.skin, self.influences, self.vertices, self.original, fast=True)


@undoChunk("skinWeightKitSlideBy")
def slide(target, influence, amount, falloff=None):
    """スライドを1回で行う(スライダーを使わない操作やスクリプト用)。

    Args:
        target (Target): 対象。
        influence (mlib.Node | str): 増減するインフルエンス。
        amount (float): 加える量(-1〜1)。
        falloff (dict[int, float] | None): {頂点番号: 重み}。Noneは選んだ頂点をすべて1にする。

    Returns:
        int: 変えた頂点の数。
    """
    session = SlideSession(target, influence, falloff)
    session.amount = float(amount)
    weights_module.writeRows(session.skin, session.influences, session.vertices, session.rows(session.amount))
    return len(session.vertices)


@undoChunk("skinWeightKitSoftSelection")
def fromSoftSelection(influence, current=None, falloff=None):
    """ソフト選択の重みを、そのままインフルエンスの値にする(他のインフルエンスで合計を1にする)。

    Args:
        influence (mlib.Node | str): 値を設定するインフルエンス。
        current (Target | None): 対象。Noneはソフト選択から決める。
        falloff (dict[int, float] | None): {頂点番号: 重み}。Noneはソフト選択から決める。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: インフルエンスがロックされている場合。
    """
    if current is None or falloff is None:
        current, falloff = softTarget()
    skin = current.requireSkin()
    influences = skin.getInfluences()
    node = influences_module.find(skin, influence)
    if influences_module.isLocked(node):
        raise ValueError("{} is locked".format(node.getNodeName()))
    locked = [influences_module.isLocked(other) for other in influences]
    column = influences.index(node)
    vertices = sorted(falloff)
    rows = weights_module.readRows(skin, influences, vertices)
    written = [weights_module.fitColumn(row, column, falloff[vertex], locked) for vertex, row in zip(vertices, rows)]
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)


def _ease(value, easing):
    """補間の割合を返す。"""
    value = min(1.0, max(0.0, value))
    if easing == "smooth":
        return value * value * (3.0 - 2.0 * value)
    return value


@undoChunk("skinWeightKitRamp")
def ramp(target, start, end, easing="linear"):
    """選んだ頂点を、2つのインフルエンスの位置を結ぶ線へ投影し、その割合で2つの間を配分する。

    頂点ごとに2つの合計は保つ(合計が0の頂点は、ロック以外の全部を2つへ集める)。線の始点側は start が1、
    終点側は end が1になる。

    Args:
        target (Target): 対象。
        start (mlib.Node | str): 始点側のインフルエンス(transform)。
        end (mlib.Node | str): 終点側のインフルエンス(transform)。
        easing (str): :data:`EASINGS` の名前。

    Returns:
        int: 変えた頂点の数。

    Raises:
        ValueError: 2つが同じ・同じ位置・ロックされている、または easing が不正な場合。
    """
    if easing not in EASINGS:
        raise ValueError("easing must be one of " + ", ".join(EASINGS))
    skin = target.requireSkin()
    vertices = target.requireVertices()
    influences = skin.getInfluences()
    nodes = [influences_module.find(skin, start), influences_module.find(skin, end)]
    if nodes[0] == nodes[1]:
        raise ValueError("Choose two different influences")
    for node in nodes:
        if influences_module.isLocked(node):
            raise ValueError("{} is locked".format(node.getNodeName()))
    origin = nodes[0].getTranslation(worldSpace=True)
    axis = nodes[1].getTranslation(worldSpace=True) - origin
    length_squared = axis * axis
    if length_squared <= weights_module.TOLERANCE:
        raise ValueError("The two influences are at the same position")
    locked = [influences_module.isLocked(node) for node in influences]
    columns = [influences.index(node) for node in nodes]
    positions = target.mesh.getVertices(vertices).getPosition(worldSpace=True)
    rows = weights_module.readRows(skin, influences, vertices)
    written = []
    for position, row in zip(positions, rows):
        ratio = _ease(((position - origin) * axis) / length_squared, easing)
        total = row[columns[0]] + row[columns[1]]
        new = list(row)
        if total <= weights_module.TOLERANCE:
            # 2つに値が無ければ、ロック以外の全部を2つへ集める。
            new = [value if locked[index] else 0.0 for index, value in enumerate(row)]
            total = max(0.0, 1.0 - sum(new))
        new[columns[0]] = total * (1.0 - ratio)
        new[columns[1]] = total * ratio
        written.append(weights_module.fitRow(new, row, locked))
    weights_module.writeRows(skin, influences, vertices, written)
    return len(vertices)

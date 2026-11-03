"""つながった頂点のまとまり(シェル)ごとに、ウェイトをそろえる(硬いパーツを1つの塊として動かす)。

鎧の板・ボタン・アクセサリーのように、変形させずに動かしたいパーツに使う。頂点を選んでいれば、
その頂点を含むシェル全体を対象にする。
"""

from mlib.decorator import undoChunk

from . import influences as influences_module
from . import weights as weights_module

#: そろえ方。``average`` はシェルの平均、``rigid`` は平均で最も大きい1つのインフルエンスに100%。
MODES = ("average", "rigid")


def shellsOf(mesh, vertices=None):
    """メッシュのシェル(辺でつながった頂点のまとまり)を返す。

    Args:
        mesh (mlib.nodes.Mesh): メッシュ。
        vertices (Iterable[int] | None): この頂点を含むシェルだけを返す。Noneは全部。

    Returns:
        list[list[int]]: シェルごとの頂点の番号(昇順)。
    """
    wanted = None if vertices is None else set(vertices)
    shells = [list(shell.indices) for shell in mesh.getShells()]
    return [shell for shell in shells if wanted is None or wanted.intersection(shell)]


@undoChunk("skinWeightKitShells")
def unifyShells(target, mode="average"):
    """シェルごとに、すべての頂点を同じウェイトにする。

    Args:
        target (Target): 対象(頂点を選んでいればその頂点を含むシェル、メッシュなら全シェル)。
        mode (str): :data:`MODES` の名前。

    Returns:
        int: そろえたシェルの数。

    Raises:
        ValueError: mode が不正な場合。
    """
    if mode not in MODES:
        raise ValueError("mode must be one of " + ", ".join(MODES))
    skin = target.requireSkin()
    influences = skin.getInfluences()
    locked = [influences_module.isLocked(node) for node in influences]
    shells = shellsOf(target.mesh, target.vertices)
    for shell in shells:
        rows = weights_module.readRows(skin, influences, shell)
        mean = [sum(column) / len(rows) for column in zip(*rows)]
        if mode == "rigid":
            free = [index for index in range(len(mean)) if not locked[index]]
            if free:
                best = max(free, key=lambda index: mean[index])
                mean = [mean[index] if locked[index] else (1.0 if index == best else 0.0)
                        for index in range(len(mean))]
        weights_module.writeRows(skin, influences, shell, [weights_module.fitRow(mean, row, locked) for row in rows])
    return len(shells)

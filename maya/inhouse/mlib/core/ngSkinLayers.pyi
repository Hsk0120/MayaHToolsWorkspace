# tools/generate_mlib_stubs.py が mlib の docstring から生成した型スタブ。直接編集しない。
"""ngSkinTools2のスキニングレイヤーへ、influenceの解除に伴うウェイトの移送を反映する。"""

import maya.cmds as cmds

_PLUGIN: str

def _layer_api(skin_name: str) -> tuple[object, object] | None:
    """レイヤーが有効なskinClusterのAPIとLayersを返す。

    Args:
        skin_name (str): skinClusterの名前。

    Returns:
        tuple[object, object] | None: ngSkinTools2のAPIとLayers。プラグイン未ロード・APIなし・レイヤーなしはNone。
    """
    ...

def _move_layer_weights(skin_name: str, moves: dict[int, int], redistributed: list[int], remaining: list[int], vertex_count: int, *, fast: bool = ...) -> bool:
    """全レイヤーで、解除するinfluenceのウェイトを移送先または残りのinfluenceへ移す。

    Args:
        skin_name (str): skinClusterの名前。
        moves (dict[int, int]): 移送元と移送先の論理番号。
        redistributed (list[int]): 移送先がなく、残りのinfluenceへ比率を保って配る論理番号。
        remaining (list[int]): 解除後も残るinfluenceの論理番号。
        vertex_count (int): 頂点数。
        fast (bool): TrueはレイヤーのUndoを記録しない。

    Returns:
        bool: レイヤーへ反映した場合True。ngSkinTools2のレイヤーが使えない場合はFalse。
    """
    ...

def _move_in_layer(layer: object, moves: dict[int, int], redistributed: list[int], remaining: list[int], vertex_count: int, undo: bool) -> None:
    """1つのレイヤーのウェイトを移し、変わった列だけを書き込む。

    Args:
        layer (object): ngSkinTools2のレイヤー。
        moves (dict[int, int]): 移送元と移送先の論理番号。
        redistributed (list[int]): 残りのinfluenceへ配る論理番号。
        remaining (list[int]): 解除後も残るinfluenceの論理番号。
        vertex_count (int): 頂点数。
        undo (bool): Undoを記録するか。

    Returns:
        None: 値を返さない。
    """
    ...

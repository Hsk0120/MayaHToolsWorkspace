"""Maya の選択状態を一時的に保存・復元するコンテキストマネージャ。"""

import contextlib

import maya.api.OpenMaya as om2
import maya.cmds as cmds

from .undo import undo_chunk


@contextlib.contextmanager
def preserved_selection():
    """ブロックの前後で Maya の選択状態を保存・復元する。

    ブロック内で選択状態を変更する操作を行っても、ブロックを抜ける際（例外時を含む）に
    開始時点の選択状態へ復元する。undo_chunk と同様、復元は cleanup であり、ブロック内で
    行った操作そのもののロールバックは行わない。
    選択の復元にはUndo対応のselectを使い、ブロック全体を一回のUndoにまとめる。
    コンポーネント選択も保持する。ブロック内で削除された対象は復元対象から除く。

    Yields:
        None: ブロック内で自由に選択状態を変更してよい。
    """
    original = om2.MGlobal.getActiveSelectionList()
    with undo_chunk("hlibPreservedSelection"):
        try:
            yield
        finally:
            names = original.getSelectionStrings()
            surviving = [name for name in names if cmds.objExists(name)]
            if surviving:
                cmds.select(surviving, replace=True, noExpand=True)
            else:
                cmds.select(clear=True)

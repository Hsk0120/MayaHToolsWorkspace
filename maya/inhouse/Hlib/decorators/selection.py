"""Maya の選択状態を一時的に保存・復元するコンテキストマネージャ。"""

import contextlib

import maya.cmds as cmds


@contextlib.contextmanager
def preserved_selection():
    """ブロックの前後で Maya の選択状態を保存・復元する。

    ブロック内で選択状態を変更する操作を行っても、ブロックを抜ける際（例外時を含む）に
    開始時点の選択状態へ復元する。undo_chunk と同様、復元は cleanup であり、ブロック内で
    行った操作そのもののロールバックは行わない。

    Yields:
        None: ブロック内で自由に選択状態を変更してよい。
    """
    original = cmds.ls(selection=True, long=True) or []
    try:
        yield
    finally:
        if original:
            cmds.select(original, replace=True)
        else:
            cmds.select(clear=True)

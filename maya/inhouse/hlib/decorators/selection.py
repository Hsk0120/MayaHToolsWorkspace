"""Maya の選択状態を一時的に保存・復元するコンテキストマネージャ。"""

import contextlib

import maya.api.OpenMaya as om2


@contextlib.contextmanager
def preserved_selection():
    """ブロックの前後で Maya の選択状態を保存・復元する。

    ブロック内で選択状態を変更する操作を行っても、ブロックを抜ける際（例外時を含む）に
    開始時点の選択状態へ復元する。undo_chunk と同様、復元は cleanup であり、ブロック内で
    行った操作そのもののロールバックは行わない（この復元操作自体も Undo の対象にはならない）。
    ``MSelectionList`` をそのまま保存・復元するため、コンポーネント選択
    （例: 頂点の範囲選択）も文字列化を経ずに正確に復元される。

    Yields:
        None: ブロック内で自由に選択状態を変更してよい。
    """
    original = om2.MGlobal.getActiveSelectionList()
    try:
        yield
    finally:
        om2.MGlobal.setActiveSelectionList(original)

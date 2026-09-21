import contextlib
import functools

import maya.cmds as cmds


@contextlib.contextmanager
def undo_chunk(name=None):
    """複数の Maya 操作を 1 回の Undo チャンクにまとめる。

    Args:
        name (str | None): Maya Undo キューに表示するチャンク名。

    Yields:
        None: コンテキスト内で実行した Maya 操作を同じ Undo として扱う。
    """
    opened = False
    try:
        kwargs = {"openChunk": True}
        if name:
            kwargs["chunkName"] = str(name)
        cmds.undoInfo(**kwargs)
        opened = True
        yield
    finally:
        if opened:
            try:
                cmds.undoInfo(closeChunk=True)
            except Exception:
                pass


def undoable(name=None):
    """関数を Maya の単一 Undo チャンクで実行するデコレータを返す。

    Args:
        name (str | None): Undo チャンク名。省略時は関数名を使用する。

    Returns:
        Callable: 対象関数をラップするデコレータ。
    """

    def decorator(func):
        chunk_name = name or getattr(func, "__name__", "UndoChunk")

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            with undo_chunk(chunk_name):
                return func(*args, **kwargs)

        return wrapper

    return decorator